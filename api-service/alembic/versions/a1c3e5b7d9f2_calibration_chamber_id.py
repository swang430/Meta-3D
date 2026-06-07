"""校准链路 chamber-scoping foundation: 5 张 probe-keyed 校准表加 chamber_id (nullable)

为消除"多暗室下 probe_id 不再全局唯一 → 按 probe_id 取校准会取错暗室数据"的隐患,
给以下 5 张按探头索引的校准表加 nullable chamber_id 列 + 索引:
  - probe_amplitude_calibrations
  - probe_phase_calibrations
  - probe_polarization_calibrations
  - probe_patterns            (测量路径活跃消费方 probe_pattern.consumer 已按它过滤)
  - probe_calibration_validity

设计要点:
- **nullable**: 现有单暗室 dummy 数据保持 NULL (不强制回填); 查询侧 prefer exact-chamber,
  回退 NULL/legacy, 故 import 端尚未写 chamber_id 前 (该改造 backlog) 不造成回归。
- probe_calibration_validity 的 PK 仍仅 probe_id; 真正 per-(probe,chamber) 汇总需把 PK
  改复合, 连同 check_validity/report 的 chamber 作用域一并 backlog。

幂等 + 仅 PostgreSQL 做 DDL; SQLite 等由 model create_all 直接物化 (已含该列),
本迁移在 SQLite 上 no-op (pytest 用 create_all, 不跑本迁移)。

Revision ID: a1c3e5b7d9f2
Revises: e3f1a2b4c5d6
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1c3e5b7d9f2"
down_revision = "e3f1a2b4c5d6"
branch_labels = None
depends_on = None

_TABLES = [
    "probe_amplitude_calibrations",
    "probe_phase_calibrations",
    "probe_polarization_calibrations",
    "probe_patterns",
    "probe_calibration_validity",
]


def _has_column(bind, table: str, col: str) -> bool:
    return any(c["name"] == col for c in sa.inspect(bind).get_columns(table))


def _has_index(bind, table: str, idx: str) -> bool:
    return any(i["name"] == idx for i in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite 等: schema 由 model create_all 物化 (已含 chamber_id + 索引), 无需迁移。
        return

    for table in _TABLES:
        if not _has_column(bind, table, "chamber_id"):
            op.add_column(
                table,
                sa.Column(
                    "chamber_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                    comment="关联暗室配置 ID (校准 chamber-scoping; NULL=未标注/legacy)",
                ),
            )
        idx = f"ix_{table}_chamber_id"
        if not _has_index(bind, table, idx):
            op.create_index(idx, table, ["chamber_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in _TABLES:
        idx = f"ix_{table}_chamber_id"
        if _has_index(bind, table, idx):
            op.drop_index(idx, table_name=table)
        if _has_column(bind, table, "chamber_id"):
            op.drop_column(table, "chamber_id")
