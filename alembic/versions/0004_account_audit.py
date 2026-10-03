"""IDs-only account action audit, retained after account deletion.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_action_audit",
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=12), nullable=False),
        sa.Column("target_id", sa.String(length=12), nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.CheckConstraint(
            "(action = 'delete' AND outcome = 'committed') OR (action = 'export' AND outcome = 'requested')",
            name="ck_account_action_audit_event",
        ),
    )


def downgrade() -> None:
    # Explicit schema downgrade removes retained security events; it is not an account operation.
    op.drop_table("account_action_audit")
