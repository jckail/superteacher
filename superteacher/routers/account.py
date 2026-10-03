"""Self-service account endpoints: full JSON export and hard delete (sessions + every owned row)."""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import account_audit, account_export, accounts
from ..accounts import CurrentUser
from ..auth import clear_cookie, current_user
from ..db import get_db
from ..gradebook_export import ClosingStreamingResponse
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


@router.get("/account/export")
def export_account(request: Request, user: CurrentUser = Depends(current_user)):
    """Stream owned data with a source-owned session, independently of dependencies."""
    factory = request.app.state.session_factory
    with factory() as db:
        metadata = account_export.read_metadata(db, user.id, user.email)
        account_audit.record(db, user.id, action="export")
        db.commit()  # Records a request, never delivery or completed serialization.
    return ClosingStreamingResponse(
        account_export.account_chunks(factory, user.id, metadata),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="super-teacher-export.json"',
            "Cache-Control": "no-store",
        },
    )


def purge_user(db: Session, user_id: str, email: str) -> None:
    """Hard-delete a user and everything hanging off them, bottom-up and explicitly (so it does not depend on the
    database enforcing ON DELETE CASCADE). Caller owns commit/rollback."""
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
    try:
        account_audit.record(db, user.id, action="delete")
        purge_user(db, user.id, user.email)
        db.commit()  # The surviving audit event and all deletions are one transaction.
    except Exception:
        db.rollback()
        raise
    done = Response(status_code=204)
    clear_cookie(done, request, st)
    return done
