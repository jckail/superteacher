from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

from .calendar import school_today
from .models import AssessmentKind, AttendanceStatus

Risk = Literal["unknown", "on_track", "watch", "at_risk"]
RosterSort = Literal["name", "section", "average", "trend", "attendance_rate", "homework_rate", "risk"]
RosterDirection = Literal["asc", "desc"]


class CalendarOut(BaseModel):
    timezone: str
    today: date


def _scrub_surrogates(v):
    """Lone UTF-16 surrogates ("\\ud800" in JSON) are valid JSON but cannot be encoded by SQLite/UTF-8 (-> 500)."""
    if isinstance(v, str) and any("\ud800" <= ch <= "\udfff" for ch in v):
        return "".join("\ufffd" if "\ud800" <= ch <= "\udfff" else ch for ch in v)
    return v


def _sanitize(multiline: bool):
    """NFC-normalise (so visually identical names compare equal) and refuse text SQLite/JSON/CSV/prompts mishandle:
    lone surrogates (crash the DB driver -> 500), NUL and other control characters."""
    allowed = "\n\r\t" if multiline else ""

    def check(v):
        if not isinstance(v, str):
            return v
        v = unicodedata.normalize("NFC", _scrub_surrogates(v))
        if any(unicodedata.category(ch) == "Cc" and ch not in allowed for ch in v):
            raise ValueError("contains control or invalid characters")
        return v

    return check


# Trimmed, non-blank text: "   " is rejected (422) instead of being stored as an empty name.
def _text(max_length: int, multiline: bool = False):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length),
        BeforeValidator(_sanitize(multiline)),
    ]


def _finite(v):
    # Starlette can't JSON-encode NaN/Infinity, so echoing one back in a 422 body would turn it into a 500.
    # Swap it for a string so pydantic rejects it with a serialisable error.
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return "non-finite number"
    return v


Num = Annotated[float, BeforeValidator(_finite)]

# Identifiers sent by the client: bounded, and safe to bind as a SQL parameter.
Id = Annotated[str, StringConstraints(max_length=64), BeforeValidator(_scrub_surrogates)]

MAX_BATCH = 1000  # entries per scores / attendance PUT


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── roster ──────────────────────────────────────────────────────────────
class SectionOut(ORM):
    id: str
    name: str
    course_id: str


class CourseOut(ORM):
    id: str
    name: str
    sections: list[SectionOut]


class CourseIn(BaseModel):
    name: _text(120)
    initial_section_name: _text(60) | None = None


class SectionIn(BaseModel):
    course_id: Id
    name: _text(60)


class StudentIn(BaseModel):
    name: _text(120)
    grade_level: int = Field(ge=1, le=12)
    section_id: Id


class StudentPatch(BaseModel):
    name: _text(120) | None = None
    grade_level: int | None = Field(default=None, ge=1, le=12)
    section_id: Id | None = None

    @model_validator(mode="after")
    def _no_explicit_null(self):
        # Omit a field to leave it alone; sending null would violate NOT NULL columns.
        for k in self.model_fields_set:
            if getattr(self, k) is None:
                raise ValueError(f"{k} cannot be null")
        return self


class StudentSummary(BaseModel):
    id: str
    name: str
    grade_level: int
    section_id: str
    section: str
    course_id: str
    course: str
    average: float | None
    letter: str | None
    gpa: float | None
    trend: float | None
    attendance_rate: float | None
    homework_rate: float | None
    missing: int
    risk: Risk
    risk_reasons: list[str]


class StudentPage(BaseModel):
    items: list[StudentSummary]
    next_cursor: str | None
    as_of: date
    total_matches: int
    total_scoped: int


class ScoreOut(BaseModel):
    assessment_id: str
    title: str
    kind: AssessmentKind
    due_date: date
    max_points: float
    points: float | None
    pct: float | None


class GradeHistorySection(BaseModel):
    section_id: str
    section: str
    course_id: str
    course: str
    scores: list[ScoreOut]


class GradeHistory(BaseModel):
    student_id: str
    active_section_id: str
    sections: list[GradeHistorySection]


class AttendanceOut(ORM):
    day: date
    status: AttendanceStatus


class NoteOut(ORM):
    id: str
    body: str
    created_at: datetime


class NoteIn(BaseModel):
    body: _text(2000, multiline=True)


class StudentDetail(StudentSummary):
    as_of: date
    scores: list[ScoreOut]
    attendance: list[AttendanceOut]
    absences: int
    tardies: int
    notes: list[NoteOut]


# ── gradebook ───────────────────────────────────────────────────────────
class AssessmentIn(BaseModel):
    title: _text(120)
    kind: AssessmentKind = AssessmentKind.test
    max_points: Num = Field(default=100, gt=0, le=1_000_000, allow_inf_nan=False)
    due_date: date = Field(default_factory=school_today)


class AssessmentPatch(BaseModel):
    title: _text(120) | None = None
    kind: AssessmentKind | None = None
    max_points: Num | None = Field(default=None, gt=0, le=1_000_000, allow_inf_nan=False)
    due_date: date | None = None

    @model_validator(mode="after")
    def _no_explicit_null(self):
        for key in self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class AssessmentOut(ORM):
    id: str
    section_id: str
    title: str
    kind: AssessmentKind
    max_points: float
    due_date: date


class ScoreEntry(BaseModel):
    student_id: Id
    points: Num | None = Field(default=None, ge=0, allow_inf_nan=False)


class ScoresIn(BaseModel):
    scores: list[ScoreEntry] = Field(max_length=MAX_BATCH)


class GradebookRow(BaseModel):
    student_id: str
    name: str
    average: float | None
    letter: str | None
    points: dict[str, float | None]  # assessment_id -> points


class Gradebook(BaseModel):
    as_of: date
    section: SectionOut
    assessments: list[AssessmentOut]
    rows: list[GradebookRow]


# ── attendance ──────────────────────────────────────────────────────────
class AttendanceMark(BaseModel):
    student_id: Id
    status: AttendanceStatus


class AttendanceIn(BaseModel):
    day: date = Field(default_factory=school_today)
    marks: list[AttendanceMark] = Field(max_length=MAX_BATCH)


class AttendanceSheetRow(BaseModel):
    student_id: str
    name: str
    status: AttendanceStatus | None


class AttendanceSheet(BaseModel):
    section: SectionOut
    day: date
    rows: list[AttendanceSheetRow]


# ── overview ────────────────────────────────────────────────────────────
class Overview(BaseModel):
    students: int
    average: float | None
    attendance_rate: float | None
    homework_rate: float | None
    at_risk: int
    watch: int
    on_track: int
    unknown: int
    distribution: dict[str, int]  # letter band -> count
    attention: list[StudentSummary]


# ── insights ────────────────────────────────────────────────────────────
class Insight(BaseModel):
    headline: str
    strengths: list[str]
    concerns: list[str]
    actions: list[str]
    source: str  # "ai" | "rules"
    model: str | None = None
    generated_at: datetime | None = None


class ImportIn(BaseModel):
    csv: Annotated[str, BeforeValidator(_scrub_surrogates)] = Field(max_length=500_000)


class ImportResult(BaseModel):
    created: int
    skipped: list[str]  # human-readable reasons, one per rejected row
