"""Insufficient evidence is distinct from both healthy progress and attention flags."""

import asyncio
import json
import zipfile
from dataclasses import asdict, replace
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from superteacher import ai, ai_tools, metrics, reports
from superteacher.accounts import CurrentUser
from superteacher.calendar import school_today
from superteacher.config import get_settings
from superteacher.models import (
    OWNER_ID,
    Assessment,
    AssessmentKind,
    AttendanceRecord,
    AttendanceStatus,
    Course,
    InsightCache,
    Note,
    Score,
    Section,
    Student,
    User,
)
from superteacher.queries import iter_summaries, load_students
from superteacher.routers.system import overview
from tests.ai_fakes import FakeAI
from tests.test_legacy_archive_import import capture as legacy_capture  # noqa: F401
from tests.test_legacy_archive_import import run as import_synthetic
from tests.test_reports import mk_assessment, mk_class, mk_student, set_scores

AS_OF = date(2026, 10, 2)
STATES = ("unknown", "on_track", "watch", "at_risk")


@pytest.mark.parametrize("case", ["empty", "notes", "future-work", "future-attendance", "excused", "due-null-test"])
def test_no_evidence_pure_orm_bounded_agree_as_of(client, session_factory, case):
    with session_factory() as db:
        section = Section(name="Synthetic", course=Course(name="Evidence", owner_id=OWNER_ID))
        student = Student(name="No evidence", grade_level=7, section=section)
        db.add(student)
        points, statuses = [], []
        if case == "notes":
            student.notes.append(Note(body="A teacher observation"))
        if case in ("future-work", "due-null-test"):
            due = AS_OF + timedelta(days=1) if case == "future-work" else AS_OF
            assessment = Assessment(id="test", title="Work", kind=AssessmentKind.test,
                                    max_points=100, due_date=due, section=section)
            student.scores.append(Score(assessment=assessment, points=90 if case == "future-work" else None))
            points = [metrics.make_point("test", "Work", AssessmentKind.test, due, 100,
                                         90 if case == "future-work" else None)]
        if case in ("future-attendance", "excused"):
            status = AttendanceStatus.present if case == "future-attendance" else AttendanceStatus.excused
            day = AS_OF + timedelta(days=1) if case == "future-attendance" else AS_OF
            student.attendance.append(AttendanceRecord(day=day, status=status))
            statuses = [] if day > AS_OF else [status]
        db.commit()
        pure = metrics.compute_from(points, statuses, AS_OF)
        orm = metrics.compute(load_students(db, OWNER_ID)[0], AS_OF)
        bounded = next(iter_summaries(db, OWNER_ID, today=AS_OF))[1]
        assert asdict(pure) == asdict(orm) == asdict(bounded)
        assert pure.risk == "unknown" and pure.risk_reasons == []
        assert all(getattr(pure, key) is None for key in ("average", "attendance_rate", "homework_rate", "trend"))
        assert pure.missing == (1 if case == "due-null-test" else 0)
        insight = ai.rule_insight(student, pure)
        assert "not enough data" in insight.headline
        assert not insight.strengths
        assert any("Record or review" in action for action in insight.actions)
        assert not any("stretch" in action for action in insight.actions)
        if pure.missing:
            assert "Agree a catch-up plan for the missing work" in insight.actions


def test_due_boundaries_zero_and_historical_cutoff(client, session_factory):
    with session_factory() as db:
        section = Section(name="P1", course=Course(name="Math", owner_id=OWNER_ID))
        student = Student(name="Zero is evidence", grade_level=7, section=section)
        student.scores.append(Score(assessment=Assessment(title="Test", kind=AssessmentKind.test,
                                   section=section, due_date=AS_OF, max_points=100), points=0))
        student.attendance.append(AttendanceRecord(day=AS_OF, status=AttendanceStatus.present))
        db.add(student)
        db.commit()
        for cutoff, expected in ((AS_OF - timedelta(days=1), "unknown"), (AS_OF, "at_risk")):
            orm = metrics.compute(student, cutoff)
            bounded = next(iter_summaries(db, OWNER_ID, today=cutoff))[1]
            assert asdict(orm) == asdict(bounded)
            assert orm.risk == expected
        assert orm.average == 0 and orm.letter == "F" and orm.attendance_rate == 100
    for kind, expected in ((AssessmentKind.test, "unknown"), (AssessmentKind.homework, "on_track")):
        point = metrics.make_point("missing", "Due today", kind, AS_OF, 100, None)
        before = metrics.compute_from([point], [], AS_OF - timedelta(days=1))
        due = metrics.compute_from([point], [], AS_OF)
        assert before.risk == "unknown" and before.missing == 0 and before.homework_rate is None
        assert due.risk == expected and due.missing == 1 and due.average is None
        assert due.homework_rate == (0 if kind == AssessmentKind.homework else None)
        assert "Agree a catch-up plan for the missing work" in ai.rule_insight(student, due).actions
    present = metrics.compute_from([], [AttendanceStatus.present], AS_OF)
    assert present.risk == "on_track" and present.average is None and present.attendance_rate == 100


@pytest.mark.parametrize("kind", [AssessmentKind.test, AssessmentKind.homework])
def test_due_null_orm_bounded_boundary(client, session_factory, kind):
    with session_factory() as db:
        section = Section(name="P1", course=Course(name="Math", owner_id=OWNER_ID))
        student = Student(name="Pending work", grade_level=7, section=section)
        student.scores.append(Score(assessment=Assessment(title="Due", kind=kind,
                                   section=section, due_date=AS_OF, max_points=100), points=None))
        db.add(student)
        db.commit()
        for cutoff in (AS_OF - timedelta(days=1), AS_OF):
            orm = metrics.compute(student, cutoff)
            bounded = next(iter_summaries(db, OWNER_ID, today=cutoff))[1]
            pure = metrics.compute_from(orm.scores, [], cutoff)
            assert asdict(orm) == asdict(bounded) == asdict(pure)
            assert orm.missing == int(cutoff == AS_OF)
            if kind == AssessmentKind.homework and cutoff == AS_OF:
                assert orm.homework_rate == 0 and orm.risk == "on_track"
            else:
                assert orm.homework_rate is None and orm.risk == "unknown"


@pytest.mark.parametrize("evidence,risk", [
    ({"average": 0}, "at_risk"), ({"average": 64.9}, "at_risk"),
    ({"average": 65}, "watch"), ({"average": 71.9}, "watch"), ({"average": 72}, "on_track"),
    ({"average": 90}, "on_track"), ({"attendance_rate": 79.9}, "watch"),
    ({"attendance_rate": 80}, "on_track"), ({"attendance_rate": 90}, "on_track"),
    ({"homework_rate": 0}, "on_track"),
    ({"attendance_rate": 89, "homework_rate": 69}, "watch"),
    ({"attendance_rate": 79, "homework_rate": 69}, "at_risk"),
    ({"trend": -7.9}, "on_track"), ({"trend": -8}, "on_track"), ({"trend": -15}, "watch"),
    ({"average": 70, "trend": -8}, "at_risk"),
])
def test_known_thresholds_unchanged(evidence, risk):
    metric = metrics.StudentMetrics(as_of=AS_OF, **evidence)
    metrics._assess_risk(metric)
    assert metric.risk == risk


def test_mixed_counts_attention_filters_tools_and_tenancy(client, session_factory, monkeypatch):
    section = mk_class(client)
    students = [mk_student(client, section, name) for name in ("No evidence", "Healthy", "Watch", "At risk")]
    assessment = mk_assessment(client, section, "Due test")
    set_scores(client, assessment, {students[1]["id"]: 90, students[2]["id"]: 70, students[3]["id"]: 0})
    with session_factory() as db:
        foreign = User(id="foreign00001", email="foreign@example.invalid")
        foreign_student = Student(name="Foreign roster", grade_level=7,
                                  section=Section(name="Hidden", course=Course(name="Foreign", owner_id=foreign.id)))
        db.add(foreign_student)
        db.add(foreign)
        db.commit()
        foreign_id, foreign_section = foreign_student.id, foreign_student.section_id
        foreign_course = foreign_student.section.course_id
    roster = client.get("/api/students").json()
    assert {row["name"]: row["risk"] for row in roster} == dict(zip((s["name"] for s in students), STATES, strict=True))
    for student, state in zip(students, STATES, strict=True):
        detail = client.get(f"/api/students/{student['id']}").json()
        assert detail["risk"] == state
        filtered = client.get("/api/students", params={"risk": state})
        assert filtered.status_code == 200
        assert [row["id"] for row in filtered.json()] == [student["id"]]
    assert client.get("/api/students", params={"risk": "invented"}).status_code == 422
    for path in ("/api/overview", f"/api/reports/sections/{section['id']}/summary"):
        response = client.get(path)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["students"] == sum(result[state] for state in STATES) == 4
        assert all(result[state] == 1 for state in STATES)
        assert [row["name"] for row in result["attention"]] == ["At risk", "Watch"]
    assert client.get("/api/overview", params={"section_id": foreign_section}).json()["students"] == 0
    assert client.get("/api/overview", params={"course_id": foreign_course}).json()["students"] == 0
    assert client.get(f"/api/students/{foreign_id}").status_code == 404
    assert client.get(f"/api/reports/sections/{foreign_section}/summary").status_code == 404
    with session_factory() as db:
        stats = json.loads(ai_tools.execute(db, "class_stats", {}))
        assert stats == ai_tools.class_stats(load_students(db), ai_tools.ClassStatsArgs())
        assert stats["status_counts"] == dict.fromkeys(STATES, 1)
        assert stats["sections"][0]["unknown"] == 1
        assert sum(stats["sections"][0]["status_counts"].values()) == 4
        unknown = json.loads(ai_tools.execute(db, "find_students", {"risk": "unknown"}))
        assert unknown["total_matches"] == 1 and unknown["students"][0]["status"] == "unknown"
        assert unknown["students"][0]["missing"] == 1
        graded = json.loads(ai_tools.execute(db, "find_students", {"risk": "unknown", "max_average": 100}))
        assert graded["total_matches"] == 0
        assert "status unknown" in ai_tools.execute(db, "get_student", {"student_id": students[0]["id"]})
        monkeypatch.setattr(ai, "setting_int", lambda *args: 1)
        context, _ = ai.build_context_parts(db)
        assert "'unknown': 1" in context and "not enough data" in context
        assert "status at_risk" in context and "status unknown" not in context
        assert "1 more students flagged" in context  # watch only, not unknown
    schema = next(tool for tool in ai_tools.TOOLS if tool["name"] == "find_students")
    assert set(schema["input_schema"]["properties"]["risk"]["enum"]) == set(STATES)


def test_unknown_does_not_displace_attention_cap(client):
    section = mk_class(client)
    for i in range(9):
        mk_student(client, section, f"A unknown {i}")
    flagged = [mk_student(client, section, f"Concern {i}") for i in range(9)]
    assessment = mk_assessment(client, section, "Test")
    set_scores(client, assessment, {s["id"]: 50 if i < 5 else 70 for i, s in enumerate(flagged)})
    result = client.get("/api/overview").json()
    assert result["unknown"] == 9 and result["at_risk"] == 5 and result["watch"] == 4
    assert len(result["attention"]) == 8
    assert [row["risk"] for row in result["attention"]] == ["at_risk"] * 5 + ["watch"] * 3


def test_old_on_track_empty_cache_misses_and_unknown_ai_prompt(client, session_factory, monkeypatch):
    section = mk_class(client)
    student = mk_student(client, section, "Synthetic learner")
    with session_factory() as db:
        loaded = load_students(db, student_id=student["id"])[0]
        current = metrics.compute(loaded)
        old = replace(current, risk="on_track")
        old_fingerprint = metrics.fingerprint(loaded, old)
        assert old_fingerprint != metrics.fingerprint(loaded, current)
        db.add(InsightCache(student_id=loaded.id, fingerprint=old_fingerprint,
                            model=get_settings().anthropic_insight_model,
                            payload={"headline": "On track", "strengths": [],
                                     "concerns": [], "actions": ["Stretch task"]}))
        db.commit()
        fallback = asyncio.run(ai.ai_insight(db, loaded))
        assert fallback.source == "rules" and "not enough data" in fallback.headline
        fake = FakeAI(creates=[json.dumps({"headline": "Not enough evidence", "strengths": [],
                                          "concerns": [], "actions": ["Record attendance"]})])
        monkeypatch.setattr(ai, "client", lambda: fake)
        generated = asyncio.run(ai.ai_insight(db, loaded))
        assert generated.source == "ai" and len(fake.create_calls) == 1
        request = fake.create_calls[0]
        assert "Status unknown means insufficient" in request["system"]
        assert "status unknown" in request["messages"][0]["content"]


@pytest.fixture
def synthetic_capture(request):
    return request.getfixturevalue("legacy_capture")


def test_synthetic_adapter_roster_handoff_is_unknown(tmp_path, synthetic_capture):
    # Only the adapter owner's existing invented fixture is used; no archive from outside this test.
    import_synthetic(tmp_path, synthetic_capture)
    destination = tmp_path / "handoff.db"
    with zipfile.ZipFile(tmp_path / "bundle.zip") as bundle:
        destination.write_bytes(bundle.read("native.db"))
    engine = create_engine(f"sqlite:///{destination}")
    try:
        with Session(engine) as db:
            students = load_students(db, "rehearsal001")
            assert len(students) == 2
            for model in (Assessment, Score, AttendanceRecord, Note, InsightCache):
                assert db.scalar(select(func.count()).select_from(model)) == 0
            bounded = list(iter_summaries(db, "rehearsal001", today=school_today()))
            assert all(m.risk == "unknown" for _, m in bounded)
            result = overview(db=db, user=CurrentUser("rehearsal001", "rehearsal@example.invalid"))
            assert result.students == result.unknown == 2 and result.attention == []
            summary = reports.class_summary(students[0].section, students)
            assert summary.unknown == 2 and summary.attention == []
            for student, metric in bounded:
                assert "not enough data" in ai.rule_insight(student, metric).headline
    finally:
        engine.dispose()
