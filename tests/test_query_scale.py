"""Synthetic scale contracts; no production data or network calls."""

from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import event, insert, select
from sqlalchemy.orm import Session

from superteacher import metrics
from superteacher.accounts import ensure_owner
from superteacher.calendar import school_today
from superteacher.db import Base
from superteacher.models import Assessment, AttendanceRecord, Course, Score, Section, Student
from superteacher.queries import iter_summaries, load_students, load_summaries


def seed_scale(engine, students=240, assignments=12, days=20):
    Base.metadata.create_all(engine)
    today = school_today()
    with Session(engine) as db:
        owner_id = ensure_owner(db)
    with engine.begin() as conn:
        conn.execute(insert(Course), [{"id": "course", "name": "Synthetic Science", "owner_id": owner_id}])
        conn.execute(
            insert(Section), [{"id": f"sec{i}", "course_id": "course", "name": f"Period {i}"} for i in range(4)]
        )
        conn.execute(
            insert(Student),
            [
                {"id": f"s{i:06}", "name": f"Student {i:06}", "grade_level": 9, "section_id": f"sec{i % 4}"}
                for i in range(students)
            ],
        )
        conn.execute(
            insert(Assessment),
            [
                {
                    "id": f"a{sec}-{j}",
                    "section_id": f"sec{sec}",
                    "title": f"Assignment {j:03}",
                    "kind": ["test", "quiz", "homework", "project"][j % 4],
                    "max_points": 100,
                    "due_date": today + timedelta(days=j - assignments + 2),
                }
                for sec in range(4)
                for j in range(assignments)
            ],
        )
        for start in range(0, students, 100):
            conn.execute(
                insert(Score),
                [
                    {
                        "id": f"g{i}-{j}",
                        "student_id": f"s{i:06}",
                        "assessment_id": f"a{i % 4}-{j}",
                        "points": None if (i + j) % 7 == 0 else float(45 + (i * 7 + j * 3) % 56),
                    }
                    for i in range(start, min(start + 100, students))
                    for j in range(assignments)
                ],
            )
            conn.execute(
                insert(AttendanceRecord),
                [
                    {
                        "id": f"t{i}-{j}",
                        "student_id": f"s{i:06}",
                        "day": today - timedelta(days=j),
                        "status": ["present", "present", "present", "absent", "tardy", "excused"][(i + j) % 6],
                    }
                    for i in range(start, min(start + 100, students))
                    for j in range(days)
                ],
            )


def test_batched_metrics_match_orm_and_do_not_hydrate_history(engine):
    seed_scale(engine)
    with Session(engine) as db:
        expected = {s.id: asdict(metrics.compute(s)) for s in load_students(db)}
    queries = []
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, sql, params, context, many: queries.append(sql))
    with Session(engine) as db:
        actual = list(iter_summaries(db, batch_size=40, retain_scores=False))
        assert len(queries) == 1 + 2 * 6
        assert not any(isinstance(obj, (Score, Assessment, AttendanceRecord)) for obj in db.identity_map.values())
        for student, metric in actual:
            want = expected[student.id]
            want["scores"] = []
            assert asdict(metric) == want


def test_filter_scopes_history_and_preserves_scores(engine):
    seed_scale(engine)
    queries = []
    event.listen(
        engine, "before_cursor_execute", lambda conn, cursor, sql, params, context, many: queries.append((sql, params))
    )
    with Session(engine) as db:
        rows = load_summaries(db, student_id="s000003")
        assert len(rows) == 1
        assert len(rows[0][1].scores) == 12
        assert len(queries) == 3
        assert queries[1][1] == ("s000003",)
        assert queries[2][1] == ("s000003", school_today().isoformat())
        assert db.scalar(select(Student.id).where(Student.id == "s000003")) == rows[0][0].id


def test_future_attendance_and_historical_cutoff_agree(engine):
    seed_scale(engine, students=4)
    today = school_today()
    with engine.begin() as conn:
        conn.execute(
            insert(AttendanceRecord),
            {"id": "future", "student_id": "s000003", "day": today + timedelta(days=1), "status": "absent"},
        )
    with Session(engine) as db:
        student = load_students(db, student_id="s000003")[0]
        for cutoff in (today, today - timedelta(days=10)):
            expected = metrics.compute(student, cutoff)
            actual = load_summaries(db, student_id=student.id, today=cutoff)[0][1]
            assert asdict(actual) == asdict(expected)
            assert actual.absences == sum(a.status.value == "absent" and a.day <= cutoff for a in student.attendance)


def benchmark_scale(students=1000, assignments=40, days=60):
    """Run manually with python -m tests.test_query_scale; output reproducible JSON evidence."""
    import gc
    import json
    import time
    import tracemalloc

    from sqlalchemy import create_engine

    from superteacher.ai_tools import (
        ClassStatsArgs,
        FindStudentsArgs,
        GetStudentArgs,
        class_stats,
        execute,
        find_students,
        get_student,
    )

    engine = create_engine("sqlite://")
    seed_scale(engine, students, assignments, days)
    measurements = []
    try:
        for name, args, schema, legacy in [
            ("get_student", {"student_id": "s000003"}, GetStudentArgs, get_student),
            (
                "find_students",
                {"section": "Period 2", "sort_by": "average", "limit": 25},
                FindStudentsArgs,
                find_students,
            ),
            ("class_stats", {}, ClassStatsArgs, class_stats),
        ]:
            expected = None
            for mode in ("before", "after"):
                gc.collect()
                queries = []

                def capture(conn, cursor, sql, params, context, many, captured=queries):
                    captured.append(sql)

                event.listen(engine, "before_cursor_execute", capture)
                tracemalloc.start()
                started = time.perf_counter()
                with Session(engine) as db:
                    if mode == "before":
                        result = legacy(load_students(db), schema(**args))
                        expected = result
                    else:
                        text = execute(db, name, args)
                        result = text if name == "get_student" else json.loads(text)
                        assert result == expected
                    elapsed = time.perf_counter() - started
                    _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                event.remove(engine, "before_cursor_execute", capture)
                measurements.append(
                    {
                        "tool": name,
                        "mode": mode,
                        "seconds": round(elapsed, 3),
                        "peak_mib": round(peak / 1024**2, 2),
                        "sql_queries": len(queries),
                    }
                )
        print(
            json.dumps(
                {
                    "students": students,
                    "scores": students * assignments,
                    "attendance": students * days,
                    "measurements": measurements,
                },
                indent=2,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    benchmark_scale()
