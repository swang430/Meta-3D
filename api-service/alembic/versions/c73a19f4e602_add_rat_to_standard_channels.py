# -*- coding: utf-8 -*-
"""P1-73A: make StandardChannel frequency identity RAT-aware.

Revision ID: c73a19f4e602
Revises: b7c9e1f3a5d7
Create Date: 2026-08-26

Existing rows are unambiguously NR because the pre-P1-73 schema only admitted
NR-ARFCN.  The temporary server defaults perform that exact translation; they
are removed in the same migration so every new writer must be explicit.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "c73a19f4e602"
down_revision: Union[str, Sequence[str], None] = "b7c9e1f3a5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "standard_channel_definitions"
_CHECK = "ck_scd_rat_channel_identity"


def upgrade() -> None:
    if not table_exists(_TABLE):
        return
    if not column_exists(_TABLE, "radio_technology"):
        op.add_column(
            _TABLE,
            sa.Column(
                "radio_technology", sa.String(16), nullable=False,
                server_default="nr5g",
                comment="RAT identity: nr5g | lte",
            ),
        )
    if not column_exists(_TABLE, "channel_kind"):
        op.add_column(
            _TABLE,
            sa.Column(
                "channel_kind", sa.String(32), nullable=False,
                server_default="nr_arfcn",
                comment="Channel number kind: nr_arfcn | lte_dl_earfcn",
            ),
        )
    if not column_exists(_TABLE, "lte_dl_earfcn"):
        op.add_column(
            _TABLE,
            sa.Column(
                "lte_dl_earfcn", sa.Integer(), nullable=True,
                comment="LTE downlink EARFCN; NR rows keep NULL",
            ),
        )

    # Batch works for SQLite migration-chain tests and becomes ALTER on PG.
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            "arfcn", existing_type=sa.Integer(), nullable=True,
        )
        batch.alter_column(
            "radio_technology", existing_type=sa.String(16),
            nullable=False, server_default=None,
        )
        batch.alter_column(
            "channel_kind", existing_type=sa.String(32),
            nullable=False, server_default=None,
        )
        batch.create_check_constraint(
            _CHECK,
            "(radio_technology = 'nr5g' AND channel_kind = 'nr_arfcn' "
            "AND arfcn IS NOT NULL AND lte_dl_earfcn IS NULL) OR "
            "(radio_technology = 'lte' AND channel_kind = 'lte_dl_earfcn' "
            "AND arfcn IS NULL AND lte_dl_earfcn IS NOT NULL)",
        )


def downgrade() -> None:
    if not table_exists(_TABLE) or not column_exists(_TABLE, "radio_technology"):
        return
    bind = op.get_bind()
    lte_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM standard_channel_definitions "
            "WHERE radio_technology = 'lte'"
        )
    ).scalar_one()
    if lte_count:
        raise RuntimeError(
            "cannot downgrade c73a19f4e602 while LTE StandardChannel rows exist"
        )

    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_CHECK, type_="check")
        batch.alter_column("arfcn", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("lte_dl_earfcn")
        batch.drop_column("channel_kind")
        batch.drop_column("radio_technology")
