"""Deterministic demo data: the same classroom every time, with a few stories worth finding."""

import random
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calendar import school_today
from .models import (
    Assessment,
    AssessmentKind,
    AttendanceRecord,
    AttendanceStatus,
    Course,
    Score,
    Section,
    Student,
)  # fmt: skip

FIRST = [
    "Ava",
    "Liam",
    "Maya",
    "Noah",
    "Zoe",
    "Ethan",
    "Isla",
    "Lucas",
    "Amara",
    "Mateo",
    "Priya",
    "Owen",
    "Sofia",
    "Jayden",
    "Nora",
    "Kai",
    "Layla",
    "Eli",
    "Chloe",
    "Diego",
    "Hana",
    "Theo",
    "Imani",
    "Felix",
]
LAST = [
    "Nguyen",
    "Patel",
    "Garcia",
    "Johnson",
    "Kim",
    "Okafor",
    "Rossi",
    "Haddad",
    "Larsen",
    "Silva",
    "Cohen",
    "Reyes",
    "Tanaka",
    "Brooks",
    "Mendez",
    "Novak",
    "Adeyemi",
    "Fischer",
    "Morales",
    "Ivanov",
]

PLAN = {
    "Algebra I": ["Period 1", "Period 3"],
    "World History": ["Period 2", "Period 5"],
    "Biology": ["Period 4"],
}
TITLES = {
    AssessmentKind.homework: ["Homework {n}"],
    AssessmentKind.quiz: ["Quiz {n}"],
    AssessmentKind.test: ["Unit Test {n}"],
    AssessmentKind.project: ["Project {n}"],
}


def school_days(end: date, n: int) -> list[date]:
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


STARTER_PLAN = {"Algebra I": ["Period 1"], "Biology": ["Period 4"]}


def seed_starter(db: Session, owner_id: str, today: date | None = None) -> None:
    """A small synthetic classroom for a brand-new account (deterministic, invented names only)."""
    seed_demo(db, today=today, owner_id=owner_id, plan=STARTER_PLAN, per_section=6)


def seed_demo(
    db: Session,
    today: date | None = None,
    seed: int = 7,
    owner_id: str | None = None,
    plan: dict[str, list[str]] | None = None,
    per_section: int = 9,
) -> None:
    if owner_id is None:
        from .accounts import ensure_owner

        owner_id = ensure_owner(db)
    if db.scalar(select(Course.id).where(Course.owner_id == owner_id).limit(1)):
        return  # never touch existing data
    rng = random.Random(seed)
    today = today or school_today()
    names = [f"{first} {last}" for first in FIRST for last in LAST]
    rng.shuffle(names)
    name_iter = iter(names)
    days = school_days(today, 30)

    for course_name, section_names in (plan or PLAN).items():
        course = Course(name=course_name, owner_id=owner_id)
        db.add(course)
        for sname in section_names:
            section = Section(course=course, name=sname)
            db.add(section)
            students = []
            for i in range(per_section):
                st = Student(name=next(name_iter), grade_level=rng.choice([9, 9, 10, 10, 11]), section=section)
                # hidden ground truth: base ability, drift over the term, how often they show up / hand in work
                st._ability = rng.gauss(84, 9)
                st._drift = rng.choice([0, 0, 0, 0, 0.2, -0.2]) if i else -0.7  # first student slides
                st._presence = rng.choice([0.99, 0.98, 0.97, 0.96, 0.93, 0.88]) if i != 1 else 0.7
                st._diligence = rng.choice([1.0, 1.0, 0.97, 0.95, 0.9, 0.7])
                students.append(st)
            db.add_all(students)
            db.flush()

            # ~10 weeks of coursework, one item every few days
            specs = []
            for n in range(1, 25):
                due = today - timedelta(days=int(70 - n * 3))
                kind = (
                    AssessmentKind.test if n % 8 == 0
                    else AssessmentKind.project if n % 11 == 0
                    else AssessmentKind.quiz if n % 4 == 0
                    else AssessmentKind.homework
                )  # fmt: skip
                specs.append((kind, due))
            counters: dict[AssessmentKind, int] = {}
            for step, (kind, due) in enumerate(specs):
                counters[kind] = counters.get(kind, 0) + 1
                a = Assessment(
                    section=section, kind=kind, due_date=due,
                    title=TITLES[kind][0].format(n=counters[kind]),
                    max_points=10 if kind is AssessmentKind.homework else 100 if kind is AssessmentKind.test else 20,
                )  # fmt: skip
                db.add(a)
                db.flush()
                for st in students:
                    if due > today:
                        pts = None
                    else:
                        handed_in = kind is not AssessmentKind.homework or rng.random() < st._diligence
                        handed_in = handed_in and (
                            kind is not AssessmentKind.project or rng.random() < st._diligence + 0.1
                        )
                        pct = max(25, min(100, st._ability + st._drift * step * 0.5 + rng.gauss(0, 6)))
                        pts = round(pct / 100 * a.max_points) if handed_in else None
                    db.add(Score(assessment=a, student=st, points=pts))

            for st in students:
                for d in days:
                    r = rng.random()
                    status = (
                        AttendanceStatus.present if r < st._presence
                        else AttendanceStatus.tardy if r < st._presence + (1 - st._presence) * 0.3
                        else AttendanceStatus.excused if r < st._presence + (1 - st._presence) * 0.5
                        else AttendanceStatus.absent
                    )  # fmt: skip
                    db.add(AttendanceRecord(student=st, day=d, status=status))
    db.commit()
