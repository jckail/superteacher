"""Self-service account endpoints: full JSON export and hard delete (sessions + every owned row)."""

import hmac
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import accounts
from ..accounts import CurrentUser
from ..auth import clear_cookie, current_user
from ..db import get_db
from ..models import (
    Assessment,
    AttendanceRecord,
    AuthSession,
    Course,
    InsightCache,
    LoginToken,
    Note,
    Score,
    Section,
    Student,
    UsageCounter,
    User,
)

router = APIRouter(tags=["account"])


class DeleteAccountIn(BaseModel):
    email: str = Field(max_length=320)  # must retype the account's own address


def _iso(v):
    return v.isoformat() if v is not None else None


@router.get("/account/export")
def export_account(db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    """Everything the user owns, as one JSON document."""
    courses = db.scalars(select(Course).where(Course.owner_id == user.id).order_by(Course.name)).all()
    out_courses = []
    for c in courses:
        sections = []
        for sec in db.scalars(select(Section).where(Section.course_id == c.id).order_by(Section.name)):
            assessments = db.scalars(
                select(Assessment)
                .where(Assessment.section_id == sec.id)
                .order_by(Assessment.due_date, Assessment.title)
            ).all()
            students = []
            for st in db.scalars(select(Student).where(Student.section_id == sec.id).order_by(Student.name)):
                insight = db.get(InsightCache, st.id)
                students.append(
                    {
                        "id": st.id,
                        "name": st.name,
                        "grade_level": st.grade_level,
                        "scores": [
                            {
                                "id": score.id,
                                "assessment_id": assessment.id,
                                "points": score.points,
                                "title": assessment.title,
                                "kind": assessment.kind.value,
                                "max_points": assessment.max_points,
                                "due_date": assessment.due_date.isoformat(),
                                "section_id": history_section.id,
                                "section": history_section.name,
                                "course_id": history_course.id,
                                "course": history_course.name,
                            }
                            for score, assessment, history_section, history_course in db.execute(
                                select(Score, Assessment, Section, Course)
                                .join(Assessment, Score.assessment_id == Assessment.id)
                                .join(Section, Assessment.section_id == Section.id)
                                .join(Course, Section.course_id == Course.id)
                                .where(Score.student_id == st.id, Course.owner_id == user.id)
                                .order_by(Assessment.due_date, Assessment.id)
                            )
                        ],
                        "attendance": [
                            {"day": a.day.isoformat(), "status": a.status.value}
                            for a in db.scalars(
                                select(AttendanceRecord)
                                .where(AttendanceRecord.student_id == st.id)
                                .order_by(AttendanceRecord.day)
                            )
                        ],
                        "notes": [
                            {"id": n.id, "body": n.body, "created_at": _iso(n.created_at)}
                            for n in db.scalars(select(Note).where(Note.student_id == st.id).order_by(Note.created_at))
                        ],
                        "insight": None
                        if insight is None
                        else {
                            "model": insight.model,
                            "payload": insight.payload,
                            "created_at": _iso(insight.created_at),
                        },
                    }
                )
            sections.append(
                {
                    "id": sec.id,
                    "name": sec.name,
                    "course_id": c.id,
                    "assessments": [
                        {
                            "id": a.id,
                            "title": a.title,
                            "kind": a.kind.value,
                            "max_points": a.max_points,
                            "due_date": a.due_date.isoformat(),
                        }
                        for a in assessments
                    ],
                    "students": students,
                }
            )
        out_courses.append({"id": c.id, "name": c.name, "sections": sections})
    row = db.get(User, user.id)
    doc = {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": {"email": user.email, "created_at": _iso(row.created_at if row else None)},
        "courses": out_courses,
    }
    return Response(
        json.dumps(doc, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="super-teacher-export.json"',
            "Cache-Control": "no-store",
        },
    )


def purge_user(db: Session, user_id: str, email: str) -> None:
    """Hard-delete a user and everything hanging off them, bottom-up and explicitly (so it does not depend on the
    database enforcing ON DELETE CASCADE)."""
    courses = select(Course.id).where(Course.owner_id == user_id)
    sections = select(Section.id).where(Section.course_id.in_(courses))
    students = select(Student.id).where(Student.section_id.in_(sections))
    assessments = select(Assessment.id).where(Assessment.section_id.in_(sections))
    db.execute(delete(Score).where(Score.student_id.in_(students)))
    db.execute(delete(Score).where(Score.assessment_id.in_(assessments)))
    db.execute(delete(AttendanceRecord).where(AttendanceRecord.student_id.in_(students)))
    db.execute(delete(Note).where(Note.student_id.in_(students)))
    db.execute(delete(InsightCache).where(InsightCache.student_id.in_(students)))
    db.execute(delete(Student).where(Student.section_id.in_(sections)))
    db.execute(delete(Assessment).where(Assessment.section_id.in_(sections)))
    db.execute(delete(Section).where(Section.course_id.in_(courses)))
    db.execute(delete(Course).where(Course.owner_id == user_id))
    db.execute(delete(UsageCounter).where(UsageCounter.user_id == user_id))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    db.execute(delete(LoginToken).where(LoginToken.email == email))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()


@router.delete("/account", status_code=204)
def delete_account(
    body: DeleteAccountIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    """Irreversible. Needs the CSRF header (enforced by ``current_user``) AND the account's address typed again."""
    st = request.app.state.auth
    if not st.accounts:
        raise HTTPException(404, "Not Found")
    typed = accounts.normalize_email(body.email) or ""
    if not hmac.compare_digest(typed.encode(), user.email.encode()):
        raise HTTPException(422, "Type your account email address exactly to confirm.")
    purge_user(db, user.id, user.email)
    done = Response(status_code=204)
    clear_cookie(done, request, st)
    return done
