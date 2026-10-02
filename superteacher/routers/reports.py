from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from .. import accounts
from .. import reports as svc
from ..accounts import CurrentUser
from ..auth import current_user, settings_of
from ..db import get_db
from ..models import Section
from ..queries import load_students, owned_section
from .roster import get_student_or_404

router = APIRouter(tags=["reports"])


class ParentUpdateIn(BaseModel):
    tone: svc.Tone = "warm"


class ParentUpdateOut(BaseModel):
    subject: str
    body: str
    source: str  # "ai" | "template"


def _section_or_404(db: Session, owner_id: str, section_id: str) -> Section:
    sec = owned_section(db, owner_id, section_id, selectinload(Section.assessments), selectinload(Section.course))
    if not sec:
        raise HTTPException(404, "Section not found")
    return sec


@router.get("/reports/sections/{section_id}/gradebook.csv")
def gradebook_csv(section_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    sec = _section_or_404(db, user.id, section_id)
    body = svc.gradebook_csv(sec, load_students(db, user.id, section_id=section_id))
    name = f"gradebook-{svc.slug(sec.course.name)}-{svc.slug(sec.name)}.csv"
    return Response(
        "\ufeff" + body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


@router.get("/reports/sections/{section_id}/summary", response_model=svc.ClassSummary)
def class_summary(section_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    sec = _section_or_404(db, user.id, section_id)
    return svc.class_summary(sec, load_students(db, user.id, section_id=section_id))


@router.post("/reports/students/{student_id}/parent-update", response_model=ParentUpdateOut)
async def parent_update(
    student_id: str,
    body: ParentUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
):
    student = get_student_or_404(db, user.id, student_id)

    def charge() -> None:
        try:
            accounts.consume_quota(db, settings_of(request), user.id, "parent_update")
        except accounts.QuotaExceeded as e:
            raise accounts.quota_http_error(e) from None

    draft, source = await svc.parent_update(student, body.tone, before_call=charge)
    return ParentUpdateOut(subject=draft.subject, body=draft.body, source=source)
