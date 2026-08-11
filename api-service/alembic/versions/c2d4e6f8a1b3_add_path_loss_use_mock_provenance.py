"""add path-loss calibration mock provenance

Revision ID: c2d4e6f8a1b3
Revises: f6c2d8a41b73
Create Date: 2026-08-11

The nullable tri-state is intentional: ``False`` is an explicitly real
instrument measurement, ``True`` is simulated, and ``NULL`` preserves the
unknown provenance of brownfield rows and old import packages.  No server
default or backfill may silently promote unknown data to real.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "c2d4e6f8a1b3"
down_revision: Union[str, Sequence[str], None] = "f6c2d8a41b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if table_exists("probe_path_loss_calibrations") and not column_exists(
        "probe_path_loss_calibrations", "use_mock"
    ):
        op.add_column(
            "probe_path_loss_calibrations",
            sa.Column(
                "use_mock",
                sa.Boolean(),
                nullable=True,
                comment=(
                    "校准数据来源: false=真实仪器测量, true=模拟生成, "
                    "NULL=迁移前历史或导入来源未知"
                ),
            ),
        )


def downgrade() -> None:
    if table_exists("probe_path_loss_calibrations") and column_exists(
        "probe_path_loss_calibrations", "use_mock"
    ):
        op.drop_column("probe_path_loss_calibrations", "use_mock")
