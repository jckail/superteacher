"""accounts: users, server-side sessions, login tokens, quotas, courses.owner_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02

Existing courses are backfilled to a deterministic "owner" user (the passcode owner). The global UNIQUE(name) on
courses becomes UNIQUE(owner_id, lower(name)).

SQLite note: replacing the unique constraint recreates ``courses`` (batch mode). Foreign keys must be OFF while that
happens or ``DROP TABLE courses`` would cascade-delete every section; ``superteacher.db.run_migrations`` and
``alembic/env.py`` switch the pragma off before the transaction starts. This revision refuses to run otherwise.
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OWNER_ID = "owner0000000"
OWNER_EMAIL = "owner@superteacher.invalid"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" and bind.exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError("Run this migration with PRAGMA foreign_keys=OFF (see the module docstring).")

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_hash"),
    )
    with op.batch_alter_table("sessions", schema=None) as b:
        b.create_index(b.f("ix_sessions_user_id"), ["user_id"], unique=False)
    op.create_table(
        "login_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    with op.batch_alter_table("login_tokens", schema=None) as b:
        b.create_index("ix_login_tokens_email_created", ["email", "created_at"], unique=False)
    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day", "kind"),
    )
    op.create_table(
        "ai_budget",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day"),
    )

    with op.batch_alter_table("courses", schema=None) as b:
        b.add_column(sa.Column("owner_id", sa.String(length=12), nullable=True))

    if bind.execute(sa.text("select 1 from courses limit 1")).first():
        bind.execute(
            sa.text("insert into users (id, email, created_at, disabled) values (:i, :e, CURRENT_TIMESTAMP, 0)"),
            {"i": OWNER_ID, "e": OWNER_EMAIL},
        )
        bind.execute(sa.text("update courses set owner_id = :i"), {"i": OWNER_ID})

    naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("courses", schema=None, naming_convention=naming) as b:
        b.alter_column("owner_id", existing_type=sa.String(length=12), nullable=False)
        b.drop_constraint("uq_courses_name", type_="unique")
        b.create_foreign_key("fk_courses_owner_id_users", "users", ["owner_id"], ["id"], ondelete="CASCADE")
        b.create_index(b.f("ix_courses_owner_id"), ["owner_id"], unique=False)
    op.create_index("uq_courses_owner_name", "courses", ["owner_id", sa.text("lower(name)")], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" and bind.exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError("Run this migration with PRAGMA foreign_keys=OFF (see the module docstring).")
    op.drop_index("uq_courses_owner_name", table_name="courses")
    with op.batch_alter_table("courses", schema=None) as b:
        b.drop_index(b.f("ix_courses_owner_id"))
        b.drop_column("owner_id")  # fails (by design) if two owners share a course name
        b.create_unique_constraint("uq_courses_name", ["name"])
    op.drop_table("ai_budget")
    op.drop_table("usage_counters")
    op.drop_table("login_tokens")
    op.drop_table("sessions")
    op.drop_table("users")
