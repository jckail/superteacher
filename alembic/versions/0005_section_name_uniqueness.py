"""Case-insensitive section names within a course.

Revision ID: 0005
Revises: 0004

Courses already reject case variants with ``uq_courses_owner_name`` on
``(owner_id, lower(name))``. Sections only had the exact ``UNIQUE(course_id, name)``,
so "Period 1" and "period 1" were distinct rows. The router check is still the
friendly 409; this index is what makes a race fail in the database.

SQLite ``lower()`` folds ASCII only, the same expression courses already use.
This revision adds an index. It does not rebuild ``sections``, so it does not
need batch table recreation. ``superteacher.db.run_migrations`` still turns
foreign keys off before the transaction, matching 0002/0003.

Existing case-variant rows are listed and the upgrade stops before any DDL.
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

INDEX = "uq_sections_course_lower_name"


def _case_duplicates(bind):
    return bind.execute(
        sa.text(
            """
            SELECT s.id AS id, s.course_id AS course_id, s.name AS name
            FROM sections AS s
            WHERE EXISTS (
                SELECT 1
                FROM sections AS other
                WHERE other.course_id = s.course_id
                  AND other.id != s.id
                  AND lower(other.name) = lower(s.name)
            )
            ORDER BY s.course_id, s.id
            """
        )
    ).all()


def upgrade() -> None:
    bind = op.get_bind()
    # Validate before DDL so a predictable collision does not stop halfway through schema changes.
    duplicates = _case_duplicates(bind)
    if duplicates:
        listing = "; ".join(f"course_id={row.course_id} id={row.id} name={row.name!r}" for row in duplicates)
        raise RuntimeError(
            "Cannot apply 0005: sections contains case-variant names for the same course. "
            "Existing data has not been changed; rename the colliding sections explicitly before retrying. "
            f"Collisions: {listing}"
        )
    op.create_index(INDEX, "sections", ["course_id", sa.text("lower(name)")], unique=True)


def downgrade() -> None:
    op.drop_index(INDEX, table_name="sections")
