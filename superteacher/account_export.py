"""Column-only account JSON stream, preserving the existing download schema.

These are live reads, not a snapshot. Every subtree rechecks current ownership;
concurrent moves/deletes may change the document during export. Result buffers
and output chunks are bounded, but a single note/string/insight JSON value can
still be large. Slow consumers hold the iterator's session open until cleanup.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Assessment, AttendanceRecord, Course, InsightCache, Note, Score, Section, Student, User

FETCH_ROWS = 100
CHUNK_BYTES = 64 * 1024


def _iso(value):
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class AccountMetadata:
    email: str
    created_at: str | None
    exported_at: str


def read_metadata(db: Session, owner_id: str, email: str, *, exported_at: datetime | None = None) -> AccountMetadata:
    result = db.execute(select(User.created_at).where(User.id == owner_id))
    try:
        created_at = result.scalar_one_or_none()
    finally:
        result.close()
    return AccountMetadata(email, _iso(created_at), (exported_at or datetime.now(UTC)).isoformat())


def _rows(db, query):
    result = db.execute(query.execution_options(yield_per=FETCH_ROWS))
    try:
        for partition in result.partitions(FETCH_ROWS):
            yield from partition
    finally:
        result.close()


def _json(value):
    # One record only; large individual text/payload values are not size-limited.
    return json.dumps(value, separators=(",", ":"))


def _array(records):
    yield "["
    first = True
    try:
        for record in records:
            if not first:
                yield ","
            first = False
            yield _json(record)
    finally:
        records.close()
    yield "]"


def _student_scope(owner_id, section_id, student_id):
    return (
        select(Student.id)
        .join(Section)
        .join(Course)
        .where(Student.id == student_id, Student.section_id == section_id, Course.owner_id == owner_id)
    )


def _scores(db, scope, owner_id):
    rows = _rows(
        db,
        select(
            Score.id,
            Assessment.id.label("assessment_id"),
            Score.points,
            Assessment.title,
            Assessment.kind,
            Assessment.max_points,
            Assessment.due_date,
            Section.id.label("section_id"),
            Section.name.label("section"),
            Course.id.label("course_id"),
            Course.name.label("course"),
        )
        .join(Assessment, Score.assessment_id == Assessment.id)
        .join(Section, Assessment.section_id == Section.id)
        .join(Course, Section.course_id == Course.id)
        .where(Score.student_id.in_(scope), Course.owner_id == owner_id)
        .order_by(Assessment.due_date, Assessment.id),
    )
    try:
        for row in rows:
            yield {**row._mapping, "kind": row.kind.value, "due_date": _iso(row.due_date)}
    finally:
        rows.close()


def _attendance(db, scope):
    rows = _rows(
        db,
        select(AttendanceRecord.day, AttendanceRecord.status)
        .where(AttendanceRecord.student_id.in_(scope))
        .order_by(AttendanceRecord.day),
    )
    try:
        for row in rows:
            yield {"day": _iso(row.day), "status": row.status.value}
    finally:
        rows.close()


def _notes(db, scope):
    rows = _rows(
        db, select(Note.id, Note.body, Note.created_at).where(Note.student_id.in_(scope)).order_by(Note.created_at)
    )
    try:
        for row in rows:
            yield {"id": row.id, "body": row.body, "created_at": _iso(row.created_at)}
    finally:
        rows.close()


def _assessments(db, owner_id, section_id):
    rows = _rows(
        db,
        select(Assessment.id, Assessment.title, Assessment.kind, Assessment.max_points, Assessment.due_date)
        .join(Section)
        .join(Course)
        .where(Section.id == section_id, Course.owner_id == owner_id)
        .order_by(Assessment.due_date, Assessment.title),
    )
    try:
        for row in rows:
            yield {**row._mapping, "kind": row.kind.value, "due_date": _iso(row.due_date)}
    finally:
        rows.close()


def _students(db, owner_id, section_id):
    rows = _rows(
        db,
        select(Student.id, Student.name, Student.grade_level)
        .join(Section)
        .join(Course)
        .where(Student.section_id == section_id, Course.owner_id == owner_id)
        .order_by(Student.name),
    )
    first = True
    try:
        for student in rows:
            if not first:
                yield ","
            first = False
            yield _json(dict(student._mapping))[:-1] + ',"scores":'
            scope = _student_scope(owner_id, section_id, student.id)
            yield from _array(_scores(db, scope, owner_id))
            yield ',"attendance":'
            yield from _array(_attendance(db, scope))
            yield ',"notes":'
            yield from _array(_notes(db, scope))
            yield ',"insight":'
            insight_rows = _rows(
                db,
                select(InsightCache.model, InsightCache.payload, InsightCache.created_at).where(
                    InsightCache.student_id.in_(scope)
                ),
            )
            try:
                insight = next(insight_rows, None)
                yield _json(
                    None
                    if insight is None
                    else {
                        "model": insight.model,
                        "payload": insight.payload,
                        "created_at": _iso(insight.created_at),
                    }
                )
            finally:
                insight_rows.close()
            yield "}"
    finally:
        rows.close()


def _sections(db, owner_id, course_id):
    rows = _rows(
        db,
        select(Section.id, Section.name, Section.course_id)
        .join(Course)
        .where(Section.course_id == course_id, Course.owner_id == owner_id)
        .order_by(Section.name),
    )
    first = True
    try:
        for section in rows:
            if not first:
                yield ","
            first = False
            yield _json(dict(section._mapping))[:-1] + ',"assessments":'
            yield from _array(_assessments(db, owner_id, section.id))
            yield ',"students":['
            yield from _students(db, owner_id, section.id)
            yield "]}"
    finally:
        rows.close()


def _document(db, owner_id, metadata):
    yield '{"exported_at":' + _json(metadata.exported_at) + ',"account":'
    yield _json({"email": metadata.email, "created_at": metadata.created_at}) + ',"courses":['
    rows = _rows(db, select(Course.id, Course.name).where(Course.owner_id == owner_id).order_by(Course.name))
    first = True
    try:
        for course in rows:
            if not first:
                yield ","
            first = False
            yield _json(dict(course._mapping))[:-1] + ',"sections":['
            yield from _sections(db, owner_id, course.id)
            yield "]}"
    finally:
        rows.close()
    yield "]}"


def account_chunks(factory: Callable[[], Session], owner_id: str, metadata: AccountMetadata) -> Iterator[bytes]:
    """The source owns session/results; shared response cleanup closes this source."""
    with factory() as db:
        document = _document(db, owner_id, metadata)
        buffer = bytearray()
        try:
            for fragment in document:
                encoded = fragment.encode("utf-8")
                for start in range(0, len(encoded), CHUNK_BYTES):
                    part = encoded[start : start + CHUNK_BYTES]
                    if len(buffer) + len(part) > CHUNK_BYTES:
                        yield bytes(buffer)
                        buffer.clear()
                    buffer.extend(part)
                    if len(buffer) == CHUNK_BYTES:
                        yield bytes(buffer)
                        buffer.clear()
            if buffer:
                yield bytes(buffer)
        finally:
            document.close()
