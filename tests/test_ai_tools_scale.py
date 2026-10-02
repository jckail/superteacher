import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, insert
from sqlalchemy.orm import Session

from superteacher import metrics
from superteacher.ai_tools import (
    ClassStatsArgs,
    FindStudentsArgs,
    GetStudentArgs,
    class_stats,
    execute,
    find_students,
    get_student,
)
from superteacher.calendar import school_today
from superteacher.models import Note, Student
from superteacher.queries import load_students
from tests.test_query_scale import seed_scale


@pytest.mark.parametrize("sort_by", ["name", "average", "attendance", "trend", "missing"])
@pytest.mark.parametrize("descending", [False, True])
def test_find_is_exact_with_bounded_ranking(engine, sort_by, descending):
    seed_scale(engine)
    args = {"sort_by": sort_by, "descending": descending, "limit": 7, "min_missing": 1}
    with Session(engine) as db:
        students = load_students(db)
        expected = find_students(students, FindStudentsArgs(**args))
        full = [(s, metrics.compute(s)) for s in students]
        full = [(s, m) for s, m in full if m.missing >= 1]
        attribute = {
            "name": None,
            "average": "average",
            "attendance": "attendance_rate",
            "trend": "trend",
            "missing": "missing",
        }[sort_by]

        def key(row):
            return row[0].name.lower() if attribute is None else getattr(row[1], attribute)

        known = sorted([r for r in full if key(r) is not None], key=key, reverse=descending)
        ranked = known + [r for r in full if key(r) is None]
        assert [row["id"] for row in expected["students"]] == [s.id for s, _ in ranked[:7]]
    with Session(engine) as db:
        assert json.loads(execute(db, "find_students", args)) == expected
        assert len([s for s in db.identity_map.values() if isinstance(s, Student)]) <= 7


def test_scoped_get_and_stats_equal_existing_semantics(engine):
    seed_scale(engine)
    with Session(engine) as db:
        students = load_students(db)
        expected_get = get_student(students, GetStudentArgs(student_id="s000003"))
        expected_stats = class_stats(students, ClassStatsArgs(section="Period 2"))
        pool = [metrics.compute(s) for s in students if s.section.name == "Period 2"]
        assert expected_stats["average"] == round(metrics.mean_of(m.average for m in pool), 1)
        assert expected_stats["attendance"] == round(metrics.mean_of(m.attendance_rate for m in pool), 1)
    queries = []
    event.listen(
        engine, "before_cursor_execute", lambda conn, cursor, sql, params, context, many: queries.append((sql, params))
    )
    with Session(engine) as db:
        assert execute(db, "get_student", {"student_id": "s000003"}) == expected_get
        assert len(queries) == 4
        assert queries[1][1] == ("s000003",)
        assert queries[2][1] == ("s000003", school_today().isoformat())
        assert len([s for s in db.identity_map.values() if isinstance(s, Student)]) <= 1
    queries.clear()
    with Session(engine) as db:
        assert json.loads(execute(db, "class_stats", {"section": "Period 2"})) == expected_stats
        assert len(queries) == 3
        assert len(queries[1][1]) == 60
        assert len(queries[2][1]) == 61


def test_get_limits_notes_and_ambiguous_history(engine):
    seed_scale(engine)
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(Note),
            [
                {"id": f"note{i}", "student_id": "s000003", "body": f"Note {i}", "created_at": now - timedelta(days=i)}
                for i in range(100)
            ],
        )
    with Session(engine) as db:
        result = execute(db, "get_student", {"student_id": "s000003"})
        assert result.count("<note date=") == 5
        assert "Note 5" not in result
        assert len([s for s in db.identity_map.values() if isinstance(s, Note)]) <= 5
        ambiguous = json.loads(execute(db, "get_student", {"name": "Student"}))
        assert len(ambiguous["candidates"]) == 10


def test_tool_unicode_and_literal_wildcards(engine):
    seed_scale(engine, students=4)
    with Session(engine) as db:
        s = db.get(Student, "s000000")
        s.name = "İPEK Ünal_%"
        s.section.name = "Ünicode_%"
        db.commit()
        for args in [{"name_contains": "ünal_%"}, {"name_contains": "i"}, {"section": "ünicode_%"}]:
            expected = find_students(load_students(db), FindStudentsArgs(**args))
            assert json.loads(execute(db, "find_students", args)) == expected
