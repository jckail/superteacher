"""Column-only CSV reads and response cleanup.

Retains assessment metadata and at most STUDENT_BATCH_SIZE students' active
score cells. Header/row width and that score matrix scale with assessment count;
retained transfer histories and attendance are never read. These are live reads,
not a database snapshot. A slow reader can hold the stream session open.
"""

import asyncio
import csv
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from threading import Lock

import anyio
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from . import metrics, reports
from .models import Assessment, Course, Score, Section, Student

STUDENT_BATCH_SIZE = 200
SCORE_FETCH_SIZE = 1000
CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class GradebookMetadata:
    course: str
    section: str
    assessments: list


def read_metadata(db: Session, owner_id: str, section_id: str) -> GradebookMetadata | None:
    result = db.execute(
        select(Course.name, Section.name).join(Section).where(Course.owner_id == owner_id, Section.id == section_id)
    )
    try:
        names = result.first()
    finally:
        result.close()
    if names is None:
        return None
    result = db.execute(
        select(Assessment.id, Assessment.title, Assessment.kind, Assessment.due_date, Assessment.max_points)
        .join(Section)
        .join(Course)
        .where(Course.owner_id == owner_id, Section.id == section_id)
        # Match Section.assessments' due-date order, then the legacy stable
        # due/title sort. Equal due/title columns retain the relationship order.
        .order_by(Assessment.due_date)
    )
    try:
        assessments = sorted(result.all(), key=lambda a: (a.due_date, a.title))
    finally:
        result.close()
    return GradebookMetadata(names[0], names[1], assessments)


class _RowSink:
    def write(self, value: str) -> str:
        return value


def csv_chunks(
    factory: Callable[[], Session], owner_id: str, section_id: str, metadata: GradebookMetadata, as_of: date
) -> Iterator[bytes]:
    """Own the session inside the iterator, independent of request dependencies."""
    writer = csv.writer(_RowSink(), lineterminator="\r\n")

    def chunks(row, prefix=""):
        encoded = (prefix + writer.writerow(row)).encode("utf-8")
        for start in range(0, len(encoded), CHUNK_BYTES):
            yield encoded[start : start + CHUNK_BYTES]

    yield from chunks(
        [reports.csv_safe(h) for h in ["Student", "Average (%)", "Letter"]]
        + [reports.csv_safe(f"{a.title} ({reports._points(a.max_points)} pts)") for a in metadata.assessments],
        "\ufeff",
    )
    by_id = {a.id: a for a in metadata.assessments}
    with factory() as db:
        after = None
        while True:
            query = (
                select(Student.id, Student.name)
                .join(Section)
                .join(Course)
                .where(Course.owner_id == owner_id, Student.section_id == section_id)
                .order_by(Student.name, Student.id)
                .limit(STUDENT_BATCH_SIZE)
            )
            if after is not None:
                name, sid = after
                query = query.where(or_(Student.name > name, and_(Student.name == name, Student.id > sid)))
            result = db.execute(query)
            try:
                students = result.all()
            finally:
                result.close()
            if not students:
                return
            scores = {s.id: {} for s in students}
            result = db.execute(
                select(Score.student_id, Score.assessment_id, Score.points)
                .join(Student, Student.id == Score.student_id)
                .join(Section, Section.id == Student.section_id)
                .join(Course)
                .join(Assessment, Assessment.id == Score.assessment_id)
                .where(
                    Course.owner_id == owner_id,
                    Student.section_id == section_id,
                    Assessment.section_id == section_id,
                    Student.id.in_(scores),
                )
                .execution_options(yield_per=SCORE_FETCH_SIZE)
            )
            try:
                for batch in result.partitions(SCORE_FETCH_SIZE):
                    for sc in batch:
                        if sc.assessment_id in by_id:
                            scores[sc.student_id][sc.assessment_id] = sc.points
            finally:
                result.close()
            for student in students:
                cells = scores.pop(student.id)
                points = [
                    metrics.make_point(a.id, a.title, a.kind, a.due_date, a.max_points, value)
                    for aid, value in cells.items()
                    for a in [by_id[aid]]
                ]
                computed = metrics.compute_from(points, [], as_of)
                yield from chunks(
                    [
                        reports.csv_safe(student.name),
                        "" if computed.average is None else round(computed.average, 1),
                        reports.csv_safe(computed.letter or ""),
                    ]
                    + [reports._points(cells.get(a.id)) for a in metadata.assessments]
                )
            after = (students[-1].name, students[-1].id)


class _SerializedSource:
    """A cancelled await can leave Starlette's next worker running.

    Serialize next/close in the workers themselves. Cleanup can then await close
    while an abandoned next worker finishes, without closing an executing source.
    """

    def __init__(self, source: Iterator[bytes]):
        self._source = source
        self._lock = Lock()
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            if self._closed:
                raise StopIteration
            return next(self._source)

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                self._source.close()


class ClosingStreamingResponse(StreamingResponse):
    """Close the sync source after active worker execution finishes.

    AnyIO cancellation shields do not prevent raw asyncio.Task.cancel from
    abandoning an awaited worker. The source's worker-side lock coordinates
    next/close independently of the cancelled await. Synchronous batch work
    must finish before cleanup; this does not interrupt database operations.
    """

    def __init__(self, content: Iterator[bytes], **kwargs):
        self._source = _SerializedSource(content)
        super().__init__(self._source, **kwargs)

    async def __call__(self, scope, receive, send):
        failure = None
        try:
            await super().__call__(scope, receive, send)
        except BaseException as exc:
            failure = exc
            raise
        finally:

            async def close_source():
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(self._source.close)

            # The serving runtime is asyncio. Retain ownership of this task:
            # even repeated raw Task.cancel must not detach close's worker.
            with anyio.CancelScope(shield=True):
                cleanup = asyncio.create_task(close_source())
                cancelled = None
                while True:
                    try:
                        await asyncio.shield(cleanup)
                        break
                    except asyncio.CancelledError as exc:
                        cancelled = exc
                        if cleanup.done():
                            # A terminal cancellation belongs to cleanup, not
                            # another outer cancel. Propagate its result rather
                            # than spinning on an already cancelled task.
                            cleanup.result()
                            break
                if failure is None and cancelled is not None:
                    raise cancelled
