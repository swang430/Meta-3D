"""校准链路 chamber-scoping foundation: 5 张 probe-keyed 校准表加 chamber_id (nullable)

为消除"多暗室下 probe_id 不再全局唯一 → 按 probe_id 取校准会取错暗室数据"的隐患,
给以下 5 张按探头索引的校准表加 nullable chamber_id 列 + 索引:
  - probe_amplitude_calibrations
  - probe_phase_calibrations
  - probe_polarization_calibrations
  - probe_patterns            (测量路径活跃消费方 probe_pattern.consumer 已按它过滤)
  - probe_calibration_validity

设计要点:
- **nullable**: 现有单暗室 dummy 数据保持 NULL; 查询侧 prefer exact-chamber, 回退 NULL/legacy,
  故 import 端尚未写 chamber_id 前 (该改造 backlog) 不造成回归。
- probe_calibration_validity 的 PK 仍仅 probe_id; 真正 per-(probe,chamber) 汇总需把 PK
  改复合, 连同 check_validity/report 的 chamber 作用域一并 backlog。

**方言无关 + 逐列守门** (Codex P2 on #156 修正): 这是 add-column 型迁移, 与 #155
(e3f1a2b4c5d6) 那种"约束手术 + PG-only no-op"不同 —— 必须像 f1d23a7b9c84 一样在**所有**
方言上跑, 用 column_exists/index_exists 守门保证幂等。这样三条收敛路径 (见
app/db/migration_helpers 模块说明) 都到同一终态:
  - brownfield SQLite (create_all 未产出新列) → 本迁移补列;
  - greenfield via baseline (create_all 已物化新列) → 守门跳过, 不报错;
  - PG → 正常 add_column。
若只在 PG 跑, brownfield SQLite dev/fallback DB upgrade 后会缺列, 后续查询 (model 与
consumer 已引用 chamber_id) 撞 missing-column。

Revision ID: a1c3e5b7d9f2
Revises: e3f1a2b4c5d6
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import column_exists, index_exists

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


def upgrade() -> None:
    for table in _TABLES:
        if not column_exists(table, "chamber_id"):
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
        if not index_exists(table, idx):
            op.create_index(idx, table, ["chamber_id"])


def downgrade() -> None:
    for table in _TABLES:
        idx = f"ix_{table}_chamber_id"
        if index_exists(table, idx):
            op.drop_index(idx, table_name=table)
        if column_exists(table, "chamber_id"):
            op.drop_column(table, "chamber_id")
