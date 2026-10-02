"""Synthetic cursor API acceptance; no application/student data fixtures."""

from datetime import date

import pytest

from superteacher.models import OWNER_ID, Assessment, AssessmentKind, Course, Score, Section, Student


def populate(session_factory, count=37):
    with session_factory() as db:
        course = Course(name="Course", owner_id=OWNER_ID)
        section = Section(name="Section", course=course)
        db.add(section)
        db.flush()
        assessment = Assessment(
            section_id=section.id, title="Due", kind=AssessmentKind.test, due_date=date(2020, 1, 1), max_points=100
        )
        db.add(assessment)
        db.flush()
        names = ["Alpha", "alpha", "Ångström", "İpek", "100%_\\", "Same", "Same"]
        for i in range(count):
            student = Student(id=f"student-{i:05}", name=names[i % len(names)], grade_level=9, section_id=section.id)
            db.add(student)
            db.flush()
            if i % 4 != 3:
                db.add(Score(student_id=student.id, assessment_id=assessment.id, points=[0, 68.123456789, 95][i % 4]))
        db.commit()
        return course.id, section.id


def walk(client, **params):
    rows = []
    while True:
        response = client.get(
            "/api/students/page",
            params={k: v for k, v in params.items() if k != "cursor"},
            headers={"X-Roster-Cursor": params["cursor"]} if "cursor" in params else {},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["items"]) <= params.get("limit", 50)
        assert all("scores" not in row and "notes" not in row for row in body["items"])
        rows.extend(body["items"])
        if body["next_cursor"] is None:
            return rows, body
        params["cursor"] = body["next_cursor"]


def test_static_page_endpoint(client, session_factory):
    populate(session_factory)
    rows, page = walk(client, limit=7)
    assert len(rows) == page["total_matches"] == page["total_scoped"] == 37
    assert len({r["id"] for r in rows}) == 37
    assert client.get("/api/students").status_code == 200


@pytest.mark.parametrize("sort", ["name", "section", "average", "trend", "attendance_rate", "homework_rate", "risk"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_pages_equal_independent_reference(client, session_factory, sort, direction):
    populate(session_factory)
    all_rows = client.get("/api/students").json()
    rank = {"at_risk": 0, "watch": 1, "unknown": 2, "on_track": 3}

    def primary(row):
        if sort == "name":
            return row["name"].lower()
        if sort == "section":
            return row["course"] + " " + row["section"]
        if sort == "risk":
            return rank[row["risk"]]
        return row[sort]

    expected = sorted(all_rows, key=lambda r: (r["name"], r["id"]))
    present = [r for r in expected if primary(r) is not None]
    absent = [r for r in expected if primary(r) is None]
    expected = sorted(present, key=primary, reverse=direction == "desc") + absent
    rows, _ = walk(client, limit=3, sort=sort, dir=direction)
    assert rows == expected


def test_literal_python_lower_search_and_counts(client, session_factory):
    populate(session_factory)
    rows, body = walk(client, limit=2, q="  %_\\  ")
    assert len(rows) == body["total_matches"] == 5
    assert body["total_scoped"] == 37
    rows, _ = walk(client, limit=2, q="ång")
    assert len(rows) == 5


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 201}, {"sort": "bad"}, {"dir": "bad"}, {"risk": "bad"}, {"q": "a" * 121}]
)
def test_ordinary_query_validation(client, params):
    assert client.get("/api/students/page", params=params).status_code == 422


def test_cursor_binding_and_generic_rejection(client, session_factory):
    populate(session_factory)
    cursor = client.get("/api/students/page", params={"limit": 2}).json()["next_cursor"]
    for change in [
        {"limit": 3},
        {"q": "Alpha"},
        {"sort": "name"},
        {"dir": "desc"},
        {"risk": "unknown"},
        {"course_id": "other"},
    ]:
        response = client.get("/api/students/page", params={"limit": 2, **change}, headers={"X-Roster-Cursor": cursor})
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid continuation"}
    for bad in ["", "bad", cursor + "x", "x" * 8193, client.app.state.auth.issue()]:
        response = client.get("/api/students/page", params={"limit": 2}, headers={"X-Roster-Cursor": bad})
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid continuation"}


@pytest.mark.parametrize("risk,expected", [("at_risk", 10), ("watch", 9), ("unknown", 9), ("on_track", 9)])
def test_all_risk_filters(client, session_factory, risk, expected):
    populate(session_factory)
    rows, body = walk(client, limit=2, risk=risk)
    assert len(rows) == body["total_matches"] == expected
    assert body["total_scoped"] == 37
    assert all(row["risk"] == risk for row in rows)


def test_owner_scope_and_cross_owner_cursor(client, session_factory, caplog):
    from superteacher.accounts import CurrentUser
    from superteacher.auth import current_user
    from superteacher.models import User

    populate(session_factory)
    with session_factory() as db:
        db.add(User(id="foreign", email="foreign@example.test"))
        db.flush()
        course = Course(owner_id="foreign", name="FOREIGN PRIVATE")
        section = Section(course=course, name="FOREIGN SECTION")
        db.add(section)
        db.flush()
        db.add_all(
            [Student(id=f"foreign-{i}", name="FOREIGN NAME", grade_level=9, section_id=section.id) for i in range(220)]
        )
        db.commit()
        foreign_course, foreign_section = course.id, section.id
    for scope in [{"course_id": foreign_course}, {"section_id": foreign_section}, {"section_id": "missing"}]:
        rows, body = walk(client, **scope)
        assert rows == [] and body["total_scoped"] == body["total_matches"] == 0
    token = client.get("/api/students/page", params={"limit": 2}).json()["next_cursor"]
    client.app.dependency_overrides[current_user] = lambda: CurrentUser("foreign", "foreign@example.test")
    response = client.get("/api/students/page", params={"limit": 2}, headers={"X-Roster-Cursor": token})
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid continuation"}
    assert "FOREIGN NAME" not in caplog.text
    assert token not in caplog.text
    client.app.dependency_overrides.pop(current_user)


def test_fixed_date_due_metrics_and_deleted_anchor(client, session_factory, monkeypatch):
    from superteacher.routers import roster

    first_day = date(2020, 1, 1)
    monkeypatch.setattr(roster, "school_today", lambda: first_day)
    _, section_id = populate(session_factory, 7)
    with session_factory() as db:
        future = Assessment(
            section_id=section_id, title="Tomorrow", due_date=date(2020, 1, 2), kind=AssessmentKind.test, max_points=100
        )
        db.add(future)
        db.flush()
        db.add_all([Score(student_id=f"student-{i:05}", assessment_id=future.id, points=100) for i in range(7)])
        db.commit()
    first = client.get("/api/students/page", params={"sort": "name", "limit": 2}).json()
    anchor = first["items"][-1]["id"]
    with session_factory() as db:
        student = db.get(Student, anchor)
        db.delete(student)
        db.commit()
    monkeypatch.setattr(roster, "school_today", lambda: date(2020, 1, 2))
    response = client.get(
        "/api/students/page", params={"sort": "name", "limit": 2}, headers={"X-Roster-Cursor": first["next_cursor"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == "2020-01-01"
    assert body["total_matches"] == 6
    assert all(r["id"] not in {r["id"] for r in first["items"]} for r in body["items"])


@pytest.mark.parametrize(
    "change",
    [
        {"v": True},
        {"v": 2},
        {"purpose": "session"},
        {"as_of": "20200101"},
        {"key": [0, float("nan"), "Alpha", "id"]},
        {"key": [0, float("inf"), "Alpha", "id"]},
        {"key": [False, 1, "Alpha", "id"]},
        {"key": [1, 1, "Alpha", "id"]},
    ],
)
def test_signed_malformed_cursor_rejected(client, session_factory, change):
    populate(session_factory)
    codec = client.app.state.auth.roster_cursor_serializer()
    first = client.get("/api/students/page", params={"sort": "average", "limit": 2}).json()
    payload = codec.loads(first["next_cursor"])
    payload.update(change)
    response = client.get(
        "/api/students/page", params={"sort": "average", "limit": 2}, headers={"X-Roster-Cursor": codec.dumps(payload)}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid continuation"}


def test_page_token_cannot_be_session_cookie(client, session_factory):
    populate(session_factory)
    token = client.get("/api/students/page", params={"limit": 2}).json()["next_cursor"]
    assert not client.app.state.auth.valid(token)


def test_large_roster_selection_bound_without_history_hydration(client, session_factory, engine):
    import sys

    from sqlalchemy import event

    from superteacher.queries import roster_page
    from superteacher.roster_pagination import PageQuery

    populate(session_factory, 2100)
    high_water = 0
    scanned = 0
    statements = []

    def trace(frame, event_name, arg):
        nonlocal high_water, scanned
        if frame.f_code is roster_page.__code__ and event_name == "line":
            high_water = max(high_water, len(frame.f_locals.get("retained", [])))
            scanned = max(scanned, frame.f_locals.get("total_scoped", 0))
        return trace

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with session_factory() as db:
            sys.settrace(trace)
            try:
                rows, matches, scoped = roster_page(db, OWNER_ID, PageQuery(limit=7), date(2020, 1, 1))
            finally:
                sys.settrace(None)
            assert len(rows) == high_water == 8
            assert scanned == matches == scoped == 2100
            for _, student, metric in rows:
                assert metric.scores == []
                assert "scores" not in student.__dict__
                assert "attendance" not in student.__dict__
                assert "notes" not in student.__dict__
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    # Columns/history in batches, not a single query per student or ORM hydration.
    assert sum("FROM scores" in sql for sql in statements) == 11
    assert sum("FROM attendance" in sql for sql in statements) == 11


def test_live_rename_insert_transfer_and_refresh(client, session_factory):
    from superteacher.models import User

    populate(session_factory, 7)
    params = {"sort": "name", "limit": 2}
    first = client.get("/api/students/page", params=params).json()
    with session_factory() as db:
        remaining = db.get(Student, "student-00006")
        remaining.name = "AAA moved before cursor"
        db.add(User(id="other", email="other@example.test"))
        db.flush()
        course = Course(owner_id="other", name="Other")
        section = Section(course=course, name="Other")
        db.add(section)
        db.flush()
        db.get(Student, "student-00005").section_id = section.id
        db.add(
            Student(
                id="inserted",
                name=first["items"][-1]["name"],
                grade_level=9,
                section_id=first["items"][-1]["section_id"],
            )
        )
        db.commit()
    remaining, body = walk(client, cursor=first["next_cursor"], **params)
    assert "student-00006" not in {r["id"] for r in remaining}
    assert "student-00005" not in {r["id"] for r in remaining}
    assert body["total_scoped"] == 7
    refreshed, _ = walk(client, **params)
    assert refreshed[1]["id"] == "student-00006"
    assert len(refreshed) == 7


def test_cursor_key_rotation(client, session_factory):
    from superteacher.auth import AuthState
    from superteacher.config import Settings

    populate(session_factory)
    token = client.get("/api/students/page", params={"limit": 2}).json()["next_cursor"]
    client.app.state.auth = AuthState(Settings(auth_disabled=True, session_secret="rotated-secret"))
    response = client.get("/api/students/page", params={"limit": 2}, headers={"X-Roster-Cursor": token})
    assert response.status_code == 400


def test_history_results_close_when_metric_computation_fails(client, session_factory, monkeypatch):
    from superteacher import queries

    populate(session_factory, 3)
    with session_factory() as db:
        original = db.execute
        history_results = []

        def execute(statement, *args, **kwargs):
            result = original(statement, *args, **kwargs)
            if "FROM scores" in str(statement) or "FROM attendance" in str(statement):
                history_results.append(result)
            return result

        monkeypatch.setattr(db, "execute", execute)

        def fail(*args, **kwargs):
            raise RuntimeError("synthetic computation failure")

        monkeypatch.setattr(queries.metrics, "compute_from", fail)
        with pytest.raises(RuntimeError, match="synthetic"):
            list(queries.iter_summaries(db, today=date(2020, 1, 1)))
        assert history_results
        assert all(result.closed for result in history_results)


def test_metrics_preserve_weighted_due_null_and_active_history(client, session_factory, monkeypatch):
    from superteacher import metrics
    from superteacher.models import AttendanceRecord, AttendanceStatus
    from superteacher.queries import owned_student
    from superteacher.routers import roster

    cutoff = date(2020, 1, 1)
    monkeypatch.setattr(roster, "school_today", lambda: cutoff)
    _, section_id = populate(session_factory, 1)
    with session_factory() as db:
        active = db.get(Section, section_id)
        old = Section(name="Old", course_id=active.course_id)
        db.add(old)
        db.flush()
        for i, (section, kind, day, maximum, points) in enumerate(
            [
                (section_id, AssessmentKind.homework, cutoff, 20, 20),
                (section_id, AssessmentKind.quiz, cutoff, 40, 20),
                (section_id, AssessmentKind.test, cutoff, 100, None),
                (section_id, AssessmentKind.homework, cutoff, 10, None),
                (section_id, AssessmentKind.test, date(2020, 1, 2), 100, 100),
                (old.id, AssessmentKind.test, cutoff, 100, 100),
            ]
        ):
            assessment = Assessment(
                section_id=section, title=f"Additional {i}", kind=kind, due_date=day, max_points=maximum
            )
            db.add(assessment)
            db.flush()
            db.add(Score(student_id="student-00000", assessment_id=assessment.id, points=points))
        db.add_all(
            [
                AttendanceRecord(student_id="student-00000", day=cutoff, status=AttendanceStatus.present),
                AttendanceRecord(student_id="student-00000", day=date(2020, 1, 2), status=AttendanceStatus.absent),
            ]
        )
        db.commit()
        expected = metrics.compute(owned_student(db, OWNER_ID, "student-00000"), cutoff)
    row = client.get("/api/students/page").json()["items"][0]
    for attr in ["average", "trend", "homework_rate", "attendance_rate", "missing", "risk", "risk_reasons"]:
        assert row[attr] == getattr(expected, attr)
    assert row["missing"] == 2
    assert row["homework_rate"] == 50
    assert row["attendance_rate"] == 100


def test_json_size_tracks_limit_not_roster_size(client, session_factory):
    populate(session_factory, 2100)
    small = client.get("/api/students/page", params={"limit": 2})
    large = client.get("/api/students/page", params={"limit": 200})
    assert len(small.json()["items"]) == 2
    assert len(large.json()["items"]) == 200
    assert len(large.content) > len(small.content) * 20


@pytest.mark.parametrize("students,extra_history", [(200, 0), (2100, 0), (1, 4000)])
def test_record_fixed_limit_memory_cost(client, session_factory, students, extra_history):
    import tracemalloc

    from superteacher.queries import roster_page
    from superteacher.roster_pagination import PageQuery

    _, section_id = populate(session_factory, students)
    if extra_history:
        with session_factory() as db:
            assessments = [
                Assessment(
                    id=f"long-{i}",
                    section_id=section_id,
                    title=f"History {i}",
                    kind=AssessmentKind.test,
                    due_date=date(2020, 1, 1),
                    max_points=100,
                )
                for i in range(extra_history)
            ]
            db.add_all(assessments)
            db.flush()
            db.add_all([Score(student_id="student-00000", assessment_id=a.id, points=50) for a in assessments])
            db.commit()
    with session_factory() as db:
        tracemalloc.start()
        try:
            retained, matches, scoped = roster_page(db, OWNER_ID, PageQuery(limit=7), date(2020, 1, 1))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert len(retained) <= 8
        assert matches == scoped == students
        print(f"ROSTER_MEMORY students={students} extra_history={extra_history} peak_bytes={peak}")


def diverse_metric_roster(session_factory):
    from superteacher.models import AttendanceRecord, AttendanceStatus

    cutoff = date(2020, 2, 1)
    cases = [([20, 80, 80, 80], 2, 2), ([80, 20, 20, 20], 0, 0), ([50, 50, 50, 50], 1, 1), (None, None, None)]
    with session_factory() as db:
        courses = [Course(owner_id=OWNER_ID, name=name) for name in ["Alpha", "beta"]]
        db.add_all(courses)
        db.flush()
        sections = [
            Section(course_id=courses[0].id, name="Z"),
            Section(course_id=courses[0].id, name="A"),
            Section(course_id=courses[1].id, name="B"),
        ]
        db.add_all(sections)
        db.flush()
        for section_index, section in enumerate(sections):
            quiz = [
                Assessment(
                    id=f"quiz-{section_index}-{i}",
                    section_id=section.id,
                    title=f"Quiz {i}",
                    kind=AssessmentKind.quiz,
                    due_date=date(2020, 1, i + 2),
                    max_points=100,
                )
                for i in range(4)
            ]
            homework = [
                Assessment(
                    id=f"hw-{section_index}-{i}",
                    section_id=section.id,
                    title=f"Homework {i}",
                    kind=AssessmentKind.homework,
                    due_date=date(2020, 1, 1),
                    max_points=100,
                )
                for i in range(2)
            ]
            db.add_all(quiz + homework)
            db.flush()
            for case_index, (quiz_points, hw_count, attendance_count) in enumerate(cases):
                # Duplicate raw names and equal primary metrics force id tie resolution across pages.
                for twin in range(2):
                    student = Student(
                        id=f"diverse-{section_index}-{case_index}-{twin}",
                        name=f"Same {case_index}",
                        grade_level=9,
                        section_id=section.id,
                    )
                    db.add(student)
                    db.flush()
                    if quiz_points is not None:
                        db.add_all(
                            [
                                Score(student_id=student.id, assessment_id=a.id, points=points)
                                for a, points in zip(quiz, quiz_points, strict=True)
                            ]
                        )
                        db.add_all(
                            [
                                Score(student_id=student.id, assessment_id=a.id, points=50 if i < hw_count else None)
                                for i, a in enumerate(homework)
                            ]
                        )
                        db.add_all(
                            [
                                AttendanceRecord(
                                    student_id=student.id,
                                    day=date(2020, 1, i + 1),
                                    status=AttendanceStatus.present
                                    if i < attendance_count
                                    else AttendanceStatus.absent,
                                )
                                for i in range(2)
                            ]
                        )
        db.commit()
    return cutoff


@pytest.mark.parametrize("sort", ["trend", "attendance_rate", "homework_rate", "section"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_diverse_metric_and_multisection_traversal(client, session_factory, monkeypatch, sort, direction):
    from superteacher.routers import roster

    cutoff = diverse_metric_roster(session_factory)
    monkeypatch.setattr(roster, "school_today", lambda: cutoff)
    reference = client.get("/api/students").json()
    assert len(reference) == 24

    def primary(row):
        return row["course"] + " " + row["section"] if sort == "section" else row[sort]

    if sort == "section":
        assert {primary(row) for row in reference} == {"Alpha A", "Alpha Z", "beta B"}
    else:
        values = {primary(row) for row in reference}
        assert None in values and 0 in values
        if sort == "trend":
            assert any(value < 0 for value in values if value is not None)
            assert any(value > 0 for value in values if value is not None)
        else:
            assert values == {None, 0, 50, 100}
    ties = sorted(reference, key=lambda row: (row["name"], row["id"]))
    nonnull = [row for row in ties if primary(row) is not None]
    null = [row for row in ties if primary(row) is None]
    expected = sorted(nonnull, key=primary, reverse=direction == "desc") + null
    actual, envelope = walk(client, limit=1, sort=sort, dir=direction)
    assert actual == expected
    assert len({row["id"] for row in actual}) == 24
    assert envelope["total_matches"] == envelope["total_scoped"] == 24


def test_changed_metrics_live_continuation_and_risk_restart(client, session_factory):
    from sqlalchemy import select

    from superteacher.models import User

    _, section_id = populate(session_factory, 5)
    with session_factory() as db:
        for i, points in enumerate([10, 20, 30, 40, 50]):
            score = db.scalar(select(Score).where(Score.student_id == f"student-{i:05}"))
            if score is None:
                assessment_id = db.scalar(select(Assessment.id).where(Assessment.section_id == section_id))
                score = Score(student_id=f"student-{i:05}", assessment_id=assessment_id)
                db.add(score)
            score.points = points
        db.add(User(id="metric-foreign", email="metric-foreign@example.test"))
        db.flush()
        foreign_course = Course(owner_id="metric-foreign", name="Foreign metric course")
        foreign_section = Section(course=foreign_course, name="Foreign metric section")
        db.add(foreign_section)
        db.flush()
        foreign_student = Student(
            id="metric-foreign-student", name="PRIVATE METRIC NAME", grade_level=9, section_id=foreign_section.id
        )
        foreign_assessment = Assessment(
            section_id=foreign_section.id,
            title="Private",
            kind=AssessmentKind.test,
            due_date=date(2020, 1, 1),
            max_points=100,
        )
        db.add_all([foreign_student, foreign_assessment])
        db.flush()
        foreign_score = Score(student_id=foreign_student.id, assessment_id=foreign_assessment.id, points=100)
        db.add(foreign_score)
        db.commit()
        foreign_course_id = foreign_course.id
    params = {"sort": "average", "risk": "at_risk", "limit": 2}
    first = client.get("/api/students/page", params=params).json()
    assert [row["average"] for row in first["items"]] == [10, 20]
    assert first["total_matches"] == first["total_scoped"] == 5
    with session_factory() as db:
        for student_id, points in [
            ("student-00000", 60),
            ("student-00002", 90),
            ("student-00003", 5),
            ("metric-foreign-student", 0),
        ]:
            db.scalar(select(Score).where(Score.student_id == student_id)).points = points
        db.commit()
    remaining, current = walk(client, cursor=first["next_cursor"], **params)
    assert [(row["id"], row["average"]) for row in remaining] == [("student-00004", 50), ("student-00000", 60)]
    # A row moving after the stored key repeats; one moving before is omitted, one exiting risk disappears.
    assert current["total_matches"] == 4 and current["total_scoped"] == 5
    restarted, _ = walk(client, **params)
    assert [(row["id"], row["average"]) for row in restarted] == [
        ("student-00003", 5),
        ("student-00001", 20),
        ("student-00004", 50),
        ("student-00000", 60),
    ]
    scoped, empty = walk(client, course_id=foreign_course_id, **params)
    assert scoped == [] and empty["total_matches"] == empty["total_scoped"] == 0
    assert all(row["id"] != "metric-foreign-student" for row in remaining + restarted)
