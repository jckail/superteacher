"""Durable anonymous demo budgets.

Revision ID: 0005demo
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005demo"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_usage_counters",
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("subject", "day", "kind"),
    )


def downgrade() -> None:
    op.drop_table("demo_usage_counters")
