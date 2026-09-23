"""Persist probe-pattern execution provenance and warnings.

Revision ID: b9d2f4a6c8e0
Revises: a8c1e3f5b7d9
Create Date: 2026-09-23

All columns are nullable intentionally. Historical rows and vendor imports did
not freeze a LabProfile route, and their missing provenance must not be
backfilled from mutable current topology state.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import column_exists, index_exists, table_exists


revision: str = "b9d2f4a6c8e0"
down_revision: Union[str, Sequence[str], None] = "a8c1e3f5b7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "probe_patterns"
_COLUMNS = (
    ("warnings", sa.JSON(), "本行校准过程告警；NULL=历史记录未持久化告警"),
    (
        "lab_profile_id",
        postgresql.UUID(as_uuid=True),
        "本次校准冻结的 LabProfile ID；NULL=历史/导入/模拟未冻结",
    ),
    ("operating_mode", sa.String(length=50), "本次校准冻结的运行模式"),
    ("topology_id", sa.String(length=255), "本次校准解析到的 SwitchTopology ID"),
    ("chain_id", sa.String(length=255), "本行冻结 RF chain ID"),
    ("ce_port", sa.String(length=255), "本行校准使用的信道仿真器端口"),
)


def upgrade() -> None:
    if not table_exists(_TABLE):
        return
    for name, column_type, comment in _COLUMNS:
        if not column_exists(_TABLE, name):
            op.add_column(
                _TABLE,
                sa.Column(name, column_type, nullable=True, comment=comment),
            )
    index_name = "ix_probe_patterns_lab_profile_id"
    if not index_exists(_TABLE, index_name):
        op.create_index(index_name, _TABLE, ["lab_profile_id"])


def downgrade() -> None:
    if not table_exists(_TABLE):
        return
    index_name = "ix_probe_patterns_lab_profile_id"
    if index_exists(_TABLE, index_name):
        op.drop_index(index_name, table_name=_TABLE)
    for name, _column_type, _comment in reversed(_COLUMNS):
        if column_exists(_TABLE, name):
            op.drop_column(_TABLE, name)
