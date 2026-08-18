"""Add complete structured evidence for diagnostic sequence runs.

Revision ID: a4c6e8f0b2d4
Revises: f8a1c3e5b7d9
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import column_exists, table_exists


revision = "a4c6e8f0b2d4"
down_revision = "f8a1c3e5b7d9"
branch_labels = None
depends_on = None


_JSON_PG_OR_SQLITE = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(), "sqlite"
)


def upgrade() -> None:
    if table_exists("diagnostic_runs") and not column_exists(
        "diagnostic_runs", "sequence_evidence"
    ):
        op.add_column(
            "diagnostic_runs",
            sa.Column("sequence_evidence", _JSON_PG_OR_SQLITE, nullable=True),
        )


def downgrade() -> None:
    if table_exists("diagnostic_runs") and column_exists(
        "diagnostic_runs", "sequence_evidence"
    ):
        op.drop_column("diagnostic_runs", "sequence_evidence")
