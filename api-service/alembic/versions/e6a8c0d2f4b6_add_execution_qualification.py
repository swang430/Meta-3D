# -*- coding: utf-8 -*-
"""P2-45: add server-owned execution policy and BS site certification.

Revision ID: e6a8c0d2f4b6
Revises: d73b5f6a1c20
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "e6a8c0d2f4b6"
down_revision: Union[str, Sequence[str], None] = "d73b5f6a1c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if table_exists("test_cases") and not column_exists(
        "test_cases", "execution_policy"
    ):
        op.add_column(
            "test_cases",
            sa.Column(
                "execution_policy",
                sa.JSON(),
                nullable=True,
                comment="Server-owned Diagnostic/Formal policy; dedicated endpoint only",
            ),
        )
    if table_exists("instrument_connections") and not column_exists(
        "instrument_connections", "base_station_site_certification"
    ):
        op.add_column(
            "instrument_connections",
            sa.Column(
                "base_station_site_certification",
                sa.JSON(),
                nullable=True,
                comment="Server-owned BaseStation site certification; dedicated API only",
            ),
        )


def downgrade() -> None:
    if table_exists("instrument_connections") and column_exists(
        "instrument_connections", "base_station_site_certification"
    ):
        op.drop_column("instrument_connections", "base_station_site_certification")
    if table_exists("test_cases") and column_exists(
        "test_cases", "execution_policy"
    ):
        op.drop_column("test_cases", "execution_policy")
