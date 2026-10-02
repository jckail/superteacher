"""Column summary must equal the native pure reference without ORM histories."""

from datetime import date, timedelta

import pytest
from sqlalchemy import event

from superteacher import metrics, reports
from superteacher.models import (
    OWNER_ID,
    Assessment,
    AssessmentKind,
    AttendanceRecord,
    AttendanceStatus,
    Course,
    Score,
    Section,
    Student,
    User,
)
from superteacher.queries import load_students, owned_section

CUTOFF = date(2026, 10, 2)


def populate(factory, students=405, assessments=7, old_history=0, long_attendance=0):
    with factory() as db:
        db.add(User(id="foreign", email="foreign@example.invalid"))
        db.add_all(
            [
                Course(id="course", owner_id=OWNER_ID, name="Science Ω"),
                Course(id="foreign", owner_id="foreign", name="FOREIGN-COURSE"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Section(id="active", course_id="course", name="Blue"),
                Section(id="old", course_id="course", name="Previous"),
                Section(id="empty", course_id="course", name="Empty"),
                Section(id="foreign", course_id="foreign", name="FOREIGN-SECTION"),
            ]
        )
        db.flush()
        names = ["unknown", "zero", "near-letter", "same", "same", "Éva", "éva"]
        db.add_all(
            [
                Student(
                    id=f"s{i:06}",
                    name=names[i] if i < len(names) else f"Student {i:06}",
                    grade_level=9,
                    section_id="active",
                )
                for i in range(students)
            ]
        )
        db.add(Student(id="foreign", name="FOREIGN-STUDENT", grade_level=8, section_id="foreign"))
        db.add_all(
            [
                Assessment(
                    id=f"a{i:06}",
                    title="Same" if i in (1, 2) else f"Task {i}",
                    section_id="active",
                    kind=list(AssessmentKind)[i % 4],
                    max_points=30 if i == 0 else 10,
                    due_date=CUTOFF + timedelta(days=1)
                    if i == 3
                    else CUTOFF
                    if i in (1, 2)
                    else CUTOFF - timedelta(days=i % 3),
                )
                for i in reversed(range(assessments))
            ]
        )
        db.add(
            Assessment(
                id="foreign",
                title="FOREIGN-ASSESSMENT",
                section_id="foreign",
                kind=AssessmentKind.test,
                max_points=100,
                due_date=CUTOFF,
            )
        )
        db.add_all(
            [
                Assessment(
                    id=f"old{i:06}",
                    title="OLD-CANARY",
                    section_id="old",
                    kind=AssessmentKind.test,
                    max_points=100,
                    due_date=CUTOFF,
                )
                for i in range(old_history)
            ]
        )
        db.flush()
        for i in range(students):
            for j in range(assessments):
                # absent and explicit null scores differ as events, but both are
                # missing report cells; a future grade is still a report stat.
                if i == 0 or (i + j) % 17 == 0:
                    continue
                points = None if (i + j) % 11 == 0 else 0 if i == 1 else (27.899 if i == 2 and j == 0 else 4 + i % 7)
                db.add(Score(student_id=f"s{i:06}", assessment_id=f"a{j:06}", points=points))
            db.add(Score(student_id=f"s{i:06}", assessment_id="foreign", points=100))
            if i:
                for offset, status in [
                    (0, AttendanceStatus.absent if i % 3 == 0 else AttendanceStatus.present),
                    (1, AttendanceStatus.tardy if i % 2 else AttendanceStatus.excused),
                    (45, AttendanceStatus.present if i % 7 == 6 else AttendanceStatus.absent),
                    (-1, AttendanceStatus.absent),
                ]:
                    db.add(AttendanceRecord(student_id=f"s{i:06}", day=CUTOFF - timedelta(days=offset), status=status))
        if students:
            db.add_all(
                [Score(student_id="s000000", assessment_id=f"old{i:06}", points=100) for i in range(old_history)]
            )
            db.add_all(
                [
                    AttendanceRecord(
                        student_id="s000000",
                        day=CUTOFF - timedelta(days=100 + i),
                        status=AttendanceStatus.excused if i % 2 else AttendanceStatus.present,
                    )
                    for i in range(long_attendance)
                ]
            )
        db.commit()


def reference(factory, section="active"):
    with factory() as db:
        sec = owned_section(db, OWNER_ID, section)
        return reports.class_summary(sec, load_students(db, OWNER_ID, section_id=section), CUTOFF)


def test_endpoint_matches_pure_reference_without_history_orm(client, session_factory, monkeypatch):
    populate(session_factory)
    expected = reference(session_factory).model_dump(mode="json")
    loaded = []
    monkeypatch.setattr("superteacher.routers.reports.school_today", lambda: CUTOFF)

    def on_load(session, instance):
        loaded.append(type(instance).__name__)

    event.listen(session_factory.class_, "loaded_as_persistent", on_load)
    try:
        response = client.get("/api/reports/sections/active/summary")
    finally:
        event.remove(session_factory.class_, "loaded_as_persistent", on_load)
    assert response.status_code == 200
    assert response.json() == expected
    assert not {"Score", "Assessment", "AttendanceRecord", "Student"}.intersection(loaded)
    assert expected["unknown"] >= 1 and expected["students"] == 405
    assert len(expected["attention"]) > 8  # class summary has no Overview cap
    assert "FOREIGN" not in str(response.json())


@pytest.mark.parametrize(
    "students,assessments,old_history,long_attendance",
    [
        (0, 0, 0, 0),
        (0, 5, 0, 0),
        (5, 0, 0, 0),
        (4, 1, 0, 0),
        (5, 1, 0, 0),
        (7, 11, 1505, 2005),
        (205, 24, 0, 0),
    ],
)
def test_complete_schema_equality_across_native_shapes(
    client, session_factory, students, assessments, old_history, long_attendance
):
    from superteacher.report_summary import build_summary

    populate(session_factory, students, assessments, old_history, long_attendance)
    expected = reference(session_factory)
    with session_factory() as db:
        actual = build_summary(db, OWNER_ID, "active", CUTOFF)
    assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
    assert "OLD-CANARY" not in str(actual) and "FOREIGN" not in str(actual)


def test_null_zero_rounding_future_and_lifetime_attendance(client, session_factory):
    from superteacher.report_summary import build_summary

    populate(session_factory, students=7, assessments=4)
    # A single due test puts the unrounded value below A while the DTO rounds
    # to 93.0. Zero remains graded, explicit null/absent remain missing.
    from sqlalchemy import delete

    with session_factory() as db:
        db.execute(delete(Score).where(Score.student_id == "s000002", Score.assessment_id.in_(["a000001", "a000002"])))
        db.commit()
    with session_factory() as db:
        result = build_summary(db, OWNER_ID, "active", CUTOFF)
    assert result == reference(session_factory)
    future = next(a for a in result.assessments if a.id == "a000003")
    assert future.graded > 0 and future.missing_pct is None
    today = next(day for day in result.attendance if day.day == CUTOFF)
    assert today.marked == 6 and today.absent == 2
    # Lifetime rates include an old absent day, unlike the strip.
    assert result.attendance_rate != today.rate
    with session_factory() as db:
        student = load_students(db, OWNER_ID, student_id="s000002")[0]
        computed = metrics.compute(student, CUTOFF)
        assert round(computed.average, 1) == 93.0 and computed.letter == "A-"


def test_unknown_evidence_and_all_excused_strip(client, session_factory):
    from sqlalchemy import delete

    from superteacher.report_summary import build_summary

    populate(session_factory, students=4, assessments=0)
    with session_factory() as db:
        db.execute(delete(AttendanceRecord))
        db.add(AttendanceRecord(student_id="s000001", day=CUTOFF, status=AttendanceStatus.excused))
        db.commit()
    with session_factory() as db:
        result = build_summary(db, OWNER_ID, "active", CUTOFF)
    assert result == reference(session_factory)
    assert result.unknown == 4 and result.on_track == result.watch == result.at_risk == 0
    assert result.average is result.attendance_rate is None and result.attention == []
    assert result.attendance[0].marked == 1 and result.attendance[0].rate is None


class ResultProbe:
    def __init__(self, result, query, probes):
        self.result, self.query = result, query
        self.closed, self.sizes = False, []
        probes.append(self)

    def first(self):
        return self.result.first()

    def all(self):
        rows = self.result.all()
        self.sizes.append(len(rows))
        return rows

    def partitions(self, size):
        for rows in self.result.partitions(size):
            self.sizes.append(len(rows))
            yield rows

    def close(self):
        self.result.close()
        self.closed = True


def tracking_factory(factory):
    from sqlalchemy.orm import Session, sessionmaker

    probes, sessions = [], []

    class TrackingSession(Session):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.closed = False
            sessions.append(self)

        def execute(self, query, *args, **kwargs):
            return ResultProbe(super().execute(query, *args, **kwargs), query, probes)

        def close(self):
            super().close()
            self.closed = True

    return sessionmaker(bind=factory.kw["bind"], class_=TrackingSession), probes, sessions


def test_fetch_groups_query_shape_and_orm_bounds(client, session_factory, monkeypatch):
    from superteacher import report_summary as summary

    populate(session_factory, students=405, assessments=19, old_history=1505)
    tracked, probes, sessions = tracking_factory(session_factory)
    group_sizes = []
    original = summary._stat

    def observe(assessment, percentages, submitted, count, today):
        group_sizes.append((assessment.id, len(percentages), submitted, count))
        return original(assessment, percentages, submitted, count, today)

    monkeypatch.setattr(summary, "_stat", observe)
    with tracked() as db:
        actual = summary.build_summary(db, OWNER_ID, "active", CUTOFF)
        assert not db.identity_map
    assert actual == reference(session_factory)
    assert all(p.closed for p in probes) and all(s.closed for s in sessions)
    assert len(probes) == 5 + 2 * 3
    student_probes = [p for p in probes if "FROM students JOIN" in str(p.query)]
    assert len(student_probes) == 1 and max(student_probes[0].sizes) <= 200
    history = [p for p in probes if "FROM scores JOIN" in str(p.query) or "FROM attendance JOIN" in str(p.query)]
    assert max(size for p in history for size in p.sizes) <= 1000
    assert len(group_sizes) == 19 and len({aid for aid, *_ in group_sizes}) == 19
    assert all(size <= submitted <= count == 405 for _, size, submitted, count in group_sizes)
    score_queries = [str(p.query) for p in probes if "FROM scores JOIN" in str(p.query)]
    assert len(score_queries) == 4  # three metric batches plus one stats cursor
    assert all(
        "courses.owner_id" in q and "students.section_id" in q and "assessments.section_id" in q for q in score_queries
    )
    assert all("courses.owner_id" in str(p.query) and "students.section_id" in str(p.query) for p in history)
    # No old/foreign rows enter either active score scan, despite the long history.
    metric_scores = [p for p in probes if "FROM scores JOIN" in str(p.query) and "ORDER BY" not in str(p.query)]
    stats_scores = [p for p in probes if "FROM scores JOIN" in str(p.query) and "ORDER BY" in str(p.query)]
    assert sum(sum(p.sizes) for p in metric_scores) == sum(stats_scores[0].sizes) <= 405 * 19


@pytest.mark.parametrize("failure", ["metrics", "stat", "fetch"])
def test_result_and_request_session_cleanup_on_failures(client, session_factory, monkeypatch, failure):
    from superteacher import report_summary as summary

    populate(session_factory, students=205, assessments=7)
    tracked, probes, sessions = tracking_factory(session_factory)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic report failure")

    if failure == "metrics":
        monkeypatch.setattr(summary.metrics, "compute_from", fail)
    elif failure == "stat":
        monkeypatch.setattr(summary, "_stat", fail)
    else:
        original = ResultProbe.partitions

        def failed_rows(probe, size):
            for rows in original(probe, size):
                yield rows
                if "FROM scores JOIN" in str(probe.query):
                    fail()

        monkeypatch.setattr(ResultProbe, "partitions", failed_rows)
    with pytest.raises(RuntimeError, match="synthetic report failure"), tracked() as db:
        summary.build_summary(db, OWNER_ID, "active", CUTOFF)
    assert probes and all(p.closed for p in probes)
    assert sessions and all(s.closed for s in sessions)


def test_foreign_unknown_and_empty_sections(client, session_factory):
    from superteacher.report_summary import build_summary

    populate(session_factory, students=5)
    for sid in ("foreign", "missing"):
        response = client.get(f"/api/reports/sections/{sid}/summary")
        assert response.status_code == 404 and response.json() == {"detail": "Section not found"}
    with session_factory() as db:
        empty = build_summary(db, OWNER_ID, "empty", CUTOFF)
    assert empty == reference(session_factory, "empty")


def test_transfer_rechecks_current_owner_before_each_history_read(client, session_factory, monkeypatch):
    from sqlalchemy import update

    from superteacher.report_summary import build_summary

    populate(session_factory, students=7)
    with session_factory() as db:
        execute = db.execute
        moved = False

        def move_before_history(query, *args, **kwargs):
            nonlocal moved
            if not moved and "FROM scores JOIN" in str(query):
                moved = True
                with db.connection().execute(
                    update(Student).where(Student.id == "s000001").values(section_id="foreign")
                ):
                    pass
            return execute(query, *args, **kwargs)

        monkeypatch.setattr(db, "execute", move_before_history)
        result = build_summary(db, OWNER_ID, "active", CUTOFF)
    assert moved and result.students == 7  # initial authorized metadata remains live-read provenance
    assert result.unknown == 2
    assert all(item.id != "s000001" for item in result.attention)
    assert "FOREIGN" not in str(result)


@pytest.mark.parametrize(
    "students,assessments,old_history,long_attendance",
    [
        (60, 6, 0, 0),
        (120, 6, 0, 0),
        (60, 24, 0, 0),
        (60, 6, 1505, 0),
        (60, 6, 0, 1505),
    ],
)
def test_record_allocation_shapes(client, session_factory, students, assessments, old_history, long_attendance):
    import gc
    import json
    import tracemalloc

    from superteacher.report_summary import build_summary

    populate(session_factory, students, assessments, old_history, long_attendance)
    expected = reference(session_factory)
    with session_factory() as db:
        assert build_summary(db, OWNER_ID, "active", CUTOFF) == expected  # warm SQL compilation
    gc.collect()
    tracemalloc.start()
    with session_factory() as db:
        actual = build_summary(db, OWNER_ID, "active", CUTOFF)
    _, column_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()
    tracemalloc.start()
    pure = reference(session_factory)
    _, reference_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert actual == pure == expected
    print(
        json.dumps(
            {
                "shape": [students, assessments, old_history, long_attendance],
                "column_peak": column_peak,
                "reference_peak": reference_peak,
            }
        )
    )
