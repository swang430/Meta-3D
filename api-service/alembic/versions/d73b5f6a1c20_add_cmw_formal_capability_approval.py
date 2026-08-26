# -*- coding: utf-8 -*-
"""P1-73B: add the sole CMW500 LTE 2x2 formal approval source.

Revision ID: d73b5f6a1c20
Revises: c73a19f4e602
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "d73b5f6a1c20"
down_revision: Union[str, Sequence[str], None] = "c73a19f4e602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "instrument_connections"


def upgrade() -> None:
    if not table_exists(_TABLE):
        return
    if not column_exists(_TABLE, "cmw500_lte_2x2_formal_enabled"):
        op.add_column(
            _TABLE,
            sa.Column(
                "cmw500_lte_2x2_formal_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment="CMW500 LTE 2x2 formal approval; dedicated API only",
            ),
        )
    if not column_exists(_TABLE, "cmw500_lte_2x2_formal_updated_at"):
        op.add_column(
            _TABLE,
            sa.Column(
                "cmw500_lte_2x2_formal_updated_at",
                sa.DateTime(),
                nullable=True,
                comment="Server-owned timestamp of latest approval change",
            ),
        )
    op.execute(
        sa.text(
            "UPDATE instrument_connections "
            "SET cmw500_lte_2x2_formal_enabled = false "
            "WHERE cmw500_lte_2x2_formal_enabled IS NULL"
        )
    )
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            "cmw500_lte_2x2_formal_enabled",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    if not table_exists(_TABLE):
        return
    with op.batch_alter_table(_TABLE) as batch:
        if column_exists(_TABLE, "cmw500_lte_2x2_formal_updated_at"):
            batch.drop_column("cmw500_lte_2x2_formal_updated_at")
        if column_exists(_TABLE, "cmw500_lte_2x2_formal_enabled"):
            batch.drop_column("cmw500_lte_2x2_formal_enabled")
