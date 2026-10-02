"""Relational model.

Course 1─* Section 1─* Student 1─* Score *─1 Assessment *─1 Section
                         Student 1─* AttendanceRecord
                         Student 1─* Note
                         Student 1─1 InsightCache

Grades and attendance are real rows (not "85%" strings in JSON blobs), so every
number the UI shows is derived — see ``metrics.py``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(UTC)


class AssessmentKind(enum.StrEnum):
    test = "test"
    quiz = "quiz"
    homework = "homework"
    project = "project"


class AttendanceStatus(enum.StrEnum):
    present = "present"
    tardy = "tardy"
    absent = "absent"
    excused = "excused"


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    sections: Mapped[list[Section]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Section.name"
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("course_id", "name"),)

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(60))
    course: Mapped[Course] = relationship(back_populates="sections")
    students: Mapped[list[Student]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="Student.name"
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="Assessment.due_date"
    )


class Student(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120), index=True)
    grade_level: Mapped[int] = mapped_column()
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    section: Mapped[Section] = relationship(back_populates="students")
    scores: Mapped[list[Score]] = relationship(cascade="all, delete-orphan", back_populates="student")
    attendance: Mapped[list[AttendanceRecord]] = relationship(
        cascade="all, delete-orphan",
        back_populates="student",
        # Keep each student's days chronological without a global day-ordered
        # scan when selectinload fetches attendance for many students.
        order_by="(AttendanceRecord.student_id, AttendanceRecord.day)",
    )
    notes: Mapped[list[Note]] = relationship(
        cascade="all, delete-orphan", back_populates="student", order_by="Note.created_at.desc()"
    )
    insight: Mapped[InsightCache | None] = relationship(cascade="all, delete-orphan", uselist=False)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[AssessmentKind] = mapped_column(Enum(AssessmentKind), default=AssessmentKind.test)
    max_points: Mapped[float] = mapped_column(Float, default=100.0)
    due_date: Mapped[date] = mapped_column(Date, default=date.today)
    section: Mapped[Section] = relationship(back_populates="assessments")
    scores: Mapped[list[Score]] = relationship(cascade="all, delete-orphan", back_populates="assessment")


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("assessment_id", "student_id"),)

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    # NULL points = assignment exists but nothing turned in yet (counts as missing).
    points: Mapped[float | None] = mapped_column(Float, nullable=True)
    assessment: Mapped[Assessment] = relationship(back_populates="scores")
    student: Mapped[Student] = relationship(back_populates="scores")


class AttendanceRecord(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "day"),)

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus))
    student: Mapped[Student] = relationship(back_populates="attendance")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    student: Mapped[Student] = relationship(back_populates="notes")


class InsightCache(Base):
    """Latest AI-written insight for a student; ``fingerprint`` invalidates it when the data changes."""

    __tablename__ = "insights"

    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
