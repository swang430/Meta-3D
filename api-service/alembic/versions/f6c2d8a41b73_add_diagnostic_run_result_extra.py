"""persist structured diagnostic sequence results

Revision ID: f6c2d8a41b73
Revises: c8e1f5a2d4b7
Create Date: 2026-08-06

``output_excerpt`` remains a bounded human-readable recap.  Sequence evidence
such as post-write SCPI status/BAND observations must survive independently of
that 2 KB limit, so ``result_extra`` stores the structured result JSON.

The guard supports both brownfield databases and greenfield baseline upgrades:
the baseline imports current models and may therefore have created this column
already before this migration is reached.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import column_exists, table_exists


revision: str = "f6c2d8a41b73"
down_revision: Union[str, Sequence[str], None] = "c8e1f5a2d4b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    if table_exists("diagnostic_runs") and not column_exists(
        "diagnostic_runs", "result_extra"
    ):
        op.add_column(
            "diagnostic_runs",
            sa.Column("result_extra", _JSON, nullable=True),
        )


def downgrade() -> None:
    if table_exists("diagnostic_runs") and column_exists(
        "diagnostic_runs", "result_extra"
    ):
        op.drop_column("diagnostic_runs", "result_extra")
