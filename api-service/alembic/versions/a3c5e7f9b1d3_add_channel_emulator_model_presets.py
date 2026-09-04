# -*- coding: utf-8 -*-
"""加 instrument_connections.channel_emulator_model_presets（P2-58 ②，镜像 f2a4c6e8b0d1）。

Revision ID: a3c5e7f9b1d3
Revises: f2a4c6e8b0d1
Create Date: 2026-09-04

加列迁移：方言无关（memory ``feedback_addcolumn_migration_dialect_agnostic``），
``table_exists`` / ``column_exists`` 双守门，SQLite 与 PG 都跑，二次 upgrade 幂等。
回填是**便利不是正确性**：没回填到的行，首次切型号时
``save_channel_emulator_model_preset`` 的「旧活动未存过先快照」分支会补上。
"""

import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "a3c5e7f9b1d3"
down_revision: Union[str, Sequence[str], None] = "f2a4c6e8b0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not table_exists("instrument_connections"):
        return
    if not column_exists("instrument_connections", "channel_emulator_model_presets"):
        op.add_column(
            "instrument_connections",
            sa.Column(
                "channel_emulator_model_presets",
                sa.JSON(),
                nullable=True,
                comment=(
                    "服务端持有的信道仿真器分型号 saved preset，键 = InstrumentModel.id；"
                    "活动连接字段仍是执行真值"
                ),
            ),
        )

    # 回填：channelEmulator 品类、已选型号、endpoint 非空、列仍为 NULL 的连接行，
    # 用活动连接字段为 selected_model_id 生成首个 preset。
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                """
                SELECT ic.id, ic.endpoint, ic.protocol, ic.notes,
                       ic.connection_params, cat.selected_model_id
                  FROM instrument_connections AS ic
                  JOIN instrument_categories AS cat ON cat.id = ic.category_id
                 WHERE cat.category_key = 'channelEmulator'
                   AND cat.selected_model_id IS NOT NULL
                   AND ic.endpoint IS NOT NULL
                   AND TRIM(ic.endpoint) <> ''
                   AND ic.channel_emulator_model_presets IS NULL
                """
            )
        )
        .mappings()
        .all()
    )
    table = sa.table(
        "instrument_connections",
        sa.column("id"),
        sa.column("channel_emulator_model_presets", sa.JSON()),
    )
    for row in rows:
        raw_params = row["connection_params"]
        if isinstance(raw_params, str):
            raw_params = json.loads(raw_params)
        # 有意**不剔任何键**：available_channel_models / alignment_name /
        # topology_profile_id / default_emulation_file / smu_project_scan 全是操作员或
        # 同步维护的型号配置资产（设计稿 §2，外审 #451 R2）；CE 今天没有运行期回读键。
        params = dict(raw_params or {})
        # 方言无关的规范键：PG 原生 UUID 回来带连字符，SQLite 存的是 32 位 hex；
        # parse_channel_emulator_model_presets 要求键 == str(UUID)。
        model_id = str(uuid.UUID(str(row["selected_model_id"])))
        preset = {
            "schema_version": 1,
            "model_id": model_id,
            "endpoint": str(row["endpoint"]).strip(),
            "controller": str(row["protocol"] or "").strip(),
            "notes": str(row["notes"] or "").strip(),
            "connection_params": params,
        }
        bind.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(channel_emulator_model_presets={model_id: preset})
        )


def downgrade() -> None:
    if table_exists("instrument_connections") and column_exists(
        "instrument_connections", "channel_emulator_model_presets"
    ):
        op.drop_column("instrument_connections", "channel_emulator_model_presets")
