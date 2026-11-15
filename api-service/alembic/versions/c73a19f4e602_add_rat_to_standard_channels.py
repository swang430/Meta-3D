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
_CHECK_SQL = (
    "(radio_technology = 'nr5g' AND channel_kind = 'nr_arfcn' "
    "AND arfcn IS NOT NULL AND lte_dl_earfcn IS NULL) OR "
    "(radio_technology = 'lte' AND channel_kind = 'lte_dl_earfcn' "
    "AND arfcn IS NULL AND lte_dl_earfcn IS NOT NULL)"
)
# PostgreSQL 14.20 临时表实测的 SQLAlchemy 反射文本。
# 只接受这个已核对的形式；不去括号、不推断任意 SQL 的语义等价性。
_CHECK_SQL_POSTGRESQL = (
    "radio_technology::text = 'nr5g'::text AND channel_kind::text = 'nr_arfcn'::text "
    "AND arfcn IS NOT NULL AND lte_dl_earfcn IS NULL OR "
    "radio_technology::text = 'lte'::text AND channel_kind::text = 'lte_dl_earfcn'::text "
    "AND arfcn IS NULL AND lte_dl_earfcn IS NOT NULL"
)


def upgrade() -> None:
    if not table_exists(_TABLE):
        return
    bind = op.get_bind()
    existing_check = next(
        (check for check in sa.inspect(bind).get_check_constraints(_TABLE)
         if check["name"] == _CHECK),
        None,
    )
    if existing_check is not None:
        expected = (
            _CHECK_SQL_POSTGRESQL if bind.dialect.name == "postgresql" else _CHECK_SQL
        )
        if existing_check["sqltext"] != expected:
            raise RuntimeError(
                f"{_CHECK} 的现有定义与迁移要求不一致，已停止迁移；"
                "请核对约束定义后再继续。"
            )

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
        if existing_check is None:
            batch.create_check_constraint(_CHECK, _CHECK_SQL)


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
