"""Enforce the existing API's numeric and enum domains in storage.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CONSTRAINTS = (
    (
        "students",
        "ck_students_grade_level",
        "grade_level BETWEEN 1 AND 12 AND grade_level = CAST(grade_level AS INTEGER)",
    ),
    ("assessments", "ck_assessments_max_points", "max_points > 0 AND max_points <= 1000000"),
    ("assessments", "ck_assessments_kind", "kind IN ('test', 'quiz', 'homework', 'project')"),
    ("scores", "ck_scores_points", "points >= 0 AND points <= 1.7976931348623157e308"),
    ("attendance", "ck_attendance_status", "status IN ('present', 'tardy', 'absent', 'excused')"),
)


def upgrade() -> None:
    connection = op.get_bind()
    # Validate every table before changing any schema. Do not silently repair or
    # discard legacy data, and avoid partial SQLite DDL on a predictable failure.
    for table, name, expression in CONSTRAINTS:
        invalid = connection.execute(sa.text(f"SELECT id FROM {table} WHERE NOT ({expression}) LIMIT 1")).first()
        if invalid is not None:
            raise RuntimeError(
                f"Cannot apply 0002: {table} contains data violating {name}. "
                "Existing data has not been changed; correct the invalid rows explicitly before retrying."
            )
    for table in dict.fromkeys(item[0] for item in CONSTRAINTS):
        with op.batch_alter_table(table) as batch:
            for constraint_table, name, expression in CONSTRAINTS:
                if constraint_table == table:
                    batch.create_check_constraint(name, expression)


def downgrade() -> None:
    for table in reversed(dict.fromkeys(item[0] for item in CONSTRAINTS)):
        with op.batch_alter_table(table) as batch:
            for constraint_table, name, _ in CONSTRAINTS:
                if constraint_table == table:
                    batch.drop_constraint(name, type_="check")
