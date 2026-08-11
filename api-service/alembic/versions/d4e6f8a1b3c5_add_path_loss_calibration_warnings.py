"""persist path-loss calibration warnings

Revision ID: d4e6f8a1b3c5
Revises: c2d4e6f8a1b3
Create Date: 2026-08-11

Warnings were previously visible only in the synchronous start response.  The
certificate now retains the same list so later ``/latest`` reads remain
auditable.  Historical rows stay ``NULL`` because old versions did not record
this fact; converting them to ``[]`` would falsely claim that no warnings
occurred.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "d4e6f8a1b3c5"
down_revision: Union[str, Sequence[str], None] = "c2d4e6f8a1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if table_exists("probe_path_loss_calibrations") and not column_exists(
        "probe_path_loss_calibrations", "warnings"
    ):
        op.add_column(
            "probe_path_loss_calibrations",
            sa.Column(
                "warnings",
                sa.JSON(),
                nullable=True,
                comment=(
                    "校准期间产生的警告列表（含仪表清理失败）；"
                    "NULL=迁移前未记录"
                ),
            ),
        )


def downgrade() -> None:
    if table_exists("probe_path_loss_calibrations") and column_exists(
        "probe_path_loss_calibrations", "warnings"
    ):
        op.drop_column("probe_path_loss_calibrations", "warnings")
