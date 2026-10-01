from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import AssessmentKind, AttendanceStatus

Risk = str  # on_track | watch | at_risk


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
    name: str = Field(min_length=1, max_length=120)


class SectionIn(BaseModel):
    course_id: str
    name: str = Field(min_length=1, max_length=60)


class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    grade_level: int = Field(ge=1, le=12)
    section_id: str


class StudentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    grade_level: int | None = Field(default=None, ge=1, le=12)
    section_id: str | None = None


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


class ScoreOut(BaseModel):
    assessment_id: str
    title: str
    kind: AssessmentKind
    due_date: date
    max_points: float
    points: float | None
    pct: float | None


class AttendanceOut(ORM):
    day: date
    status: AttendanceStatus


class NoteOut(ORM):
    id: str
    body: str
    created_at: datetime


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class StudentDetail(StudentSummary):
    scores: list[ScoreOut]
    attendance: list[AttendanceOut]
    absences: int
    tardies: int
    notes: list[NoteOut]


# ── gradebook ───────────────────────────────────────────────────────────
class AssessmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: AssessmentKind = AssessmentKind.test
    max_points: float = Field(default=100, gt=0)
    due_date: date = Field(default_factory=date.today)


class AssessmentOut(ORM):
    id: str
    section_id: str
    title: str
    kind: AssessmentKind
    max_points: float
    due_date: date


class ScoreEntry(BaseModel):
    student_id: str
    points: float | None = Field(default=None, ge=0)


class ScoresIn(BaseModel):
    scores: list[ScoreEntry]


class GradebookRow(BaseModel):
    student_id: str
    name: str
    average: float | None
    letter: str | None
    points: dict[str, float | None]  # assessment_id -> points


class Gradebook(BaseModel):
    section: SectionOut
    assessments: list[AssessmentOut]
    rows: list[GradebookRow]


# ── attendance ──────────────────────────────────────────────────────────
class AttendanceMark(BaseModel):
    student_id: str
    status: AttendanceStatus


class AttendanceIn(BaseModel):
    day: date = Field(default_factory=date.today)
    marks: list[AttendanceMark]


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
    csv: str = Field(max_length=500_000)


class ImportResult(BaseModel):
    created: int
    skipped: list[str]  # human-readable reasons, one per rejected row
