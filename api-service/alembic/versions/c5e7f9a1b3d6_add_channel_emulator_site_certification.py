# -*- coding: utf-8 -*-
"""Add the server-owned Channel Emulator site certification column.

Revision ID: c5e7f9a1b3d6
Revises: a3c5e7f9b1d3
Create Date: 2026-09-05

Historical rows stay NULL.  A migration cannot infer site certification from
connection configuration, old booleans, local tests, or a past driver status.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "c5e7f9a1b3d6"
down_revision: Union[str, Sequence[str], None] = "a3c5e7f9b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not table_exists("instrument_connections"):
        return
    if not column_exists(
        "instrument_connections", "channel_emulator_site_certification"
    ):
        op.add_column(
            "instrument_connections",
            sa.Column(
                "channel_emulator_site_certification",
                sa.JSON(),
                nullable=True,
                comment=(
                    "Server-owned Channel Emulator site certification; "
                    "dedicated API only"
                ),
            ),
        )


def downgrade() -> None:
    if table_exists("instrument_connections") and column_exists(
        "instrument_connections", "channel_emulator_site_certification"
    ):
        op.drop_column(
            "instrument_connections", "channel_emulator_site_certification"
        )
