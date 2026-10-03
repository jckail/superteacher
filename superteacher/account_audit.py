"""Fixed IDs-only self-service account events; caller owns the transaction."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .models import AccountActionAudit


def record(db: Session, user_id: str, *, action: str) -> None:
    if action not in {"delete", "export"}:
        raise ValueError("Unsupported account audit action")
    db.add(
        AccountActionAudit(
            event_id=uuid.uuid4().hex,
            occurred_at=datetime.now(UTC),
            actor_id=user_id,
            target_id=user_id,
            action=action,
            outcome="committed" if action == "delete" else "requested",
        )
    )
    db.flush()  # Fail before deleting rows or sending response headers.
