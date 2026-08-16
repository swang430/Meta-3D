"""persist explicit provenance for formal probe calibration consumers

Revision ID: e7a9c1d3f5b7
Revises: d4e6f8a1b3c5
Create Date: 2026-08-16

Historical rows remain NULL because their real/mock source cannot be proven.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "e7a9c1d3f5b7"
down_revision: Union[str, Sequence[str], None] = "d4e6f8a1b3c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "probe_amplitude_calibrations",
    "probe_phase_calibrations",
    "probe_polarization_calibrations",
    "probe_patterns",
    "link_calibrations",
    "rf_chain_calibrations",
    "multi_frequency_path_losses",
)


def upgrade() -> None:
    for table in TABLES:
        if table_exists(table) and not column_exists(table, "use_mock"):
            op.add_column(
                table,
                sa.Column(
                    "use_mock",
                    sa.Boolean(),
                    nullable=True,
                    comment="False=真实校准；True=模拟；NULL=历史来源未知",
                ),
            )


def downgrade() -> None:
    for table in reversed(TABLES):
        if table_exists(table) and column_exists(table, "use_mock"):
            op.drop_column(table, "use_mock")
