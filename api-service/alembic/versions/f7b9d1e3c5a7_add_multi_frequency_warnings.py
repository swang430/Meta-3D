"""Persist multi-frequency path-loss calibration warnings.

Revision ID: f7b9d1e3c5a7
Revises: c5e7f9a1b3d6
Create Date: 2026-09-23

Historical rows stay NULL because older releases did not retain the warning
list.  Treating them as an empty list would falsely claim that the run was
observed and warning-free.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "f7b9d1e3c5a7"
down_revision: Union[str, Sequence[str], None] = "c5e7f9a1b3d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if table_exists("multi_frequency_path_losses") and not column_exists(
        "multi_frequency_path_losses", "warnings"
    ):
        op.add_column(
            "multi_frequency_path_losses",
            sa.Column(
                "warnings",
                sa.JSON(),
                nullable=True,
                comment="校准期间产生的警告列表；NULL=迁移前未记录",
            ),
        )


def downgrade() -> None:
    if table_exists("multi_frequency_path_losses") and column_exists(
        "multi_frequency_path_losses", "warnings"
    ):
        op.drop_column("multi_frequency_path_losses", "warnings")
