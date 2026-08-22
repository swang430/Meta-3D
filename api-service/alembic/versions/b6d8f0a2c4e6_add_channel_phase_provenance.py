"""Add explicit provenance to channel phase calibrations.

Revision ID: b6d8f0a2c4e6
Revises: a4c6e8f0b2d4
"""

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision = "b6d8f0a2c4e6"
down_revision = "a4c6e8f0b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if table_exists("channel_phase_calibrations") and not column_exists(
        "channel_phase_calibrations", "use_mock"
    ):
        op.add_column(
            "channel_phase_calibrations",
            sa.Column("use_mock", sa.Boolean(), nullable=True),
        )


def downgrade() -> None:
    if table_exists("channel_phase_calibrations") and column_exists(
        "channel_phase_calibrations", "use_mock"
    ):
        op.drop_column("channel_phase_calibrations", "use_mock")
