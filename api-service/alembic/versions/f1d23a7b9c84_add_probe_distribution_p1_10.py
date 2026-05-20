"""add chamber_configurations.probe_distribution (P1-10)

Revision ID: f1d23a7b9c84
Revises: d8b412ca9f15
Create Date: 2026-05-19 22:30:00.000000

P1-10 (Non-Ring Chamber Plumbing, cross-repo ChannelEgine Phase 8): 给
``chamber_configurations`` 加 ``probe_distribution`` 列, 取值
``"ring" | "multi-ring" | "custom"``。

历史含义: 此前 MIMO-First → ChannelEgine 链路硬编码 ``distribution = "ring"``,
ChannelEgine 也只支持 ring 公式 (port idx → 等距 azimuth)。Phase 8 (cross-repo
2026-05-19) ChannelEgine 扩成接受 ``multi-ring`` / ``custom`` + 显式
``probe_positions``。MIMO-First 这边落到 DB schema 的 plumbing。

向后兼容: server_default = "ring", 历史行直接拿到 ring 默认值, 不影响现有
lab 8-probe ring smoke。

Idempotency: 用 ``column_exists`` 守门, 重跑无副作用。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists


revision: str = 'f1d23a7b9c84'
down_revision: Union[str, Sequence[str], None] = 'd8b412ca9f15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not column_exists('chamber_configurations', 'probe_distribution'):
        op.add_column(
            'chamber_configurations',
            sa.Column(
                'probe_distribution',
                sa.String(length=20),
                nullable=False,
                server_default='ring',
                comment="探头分布: ring (默认/等距) | multi-ring | custom (P1-10)",
            ),
        )


def downgrade() -> None:
    if column_exists('chamber_configurations', 'probe_distribution'):
        op.drop_column('chamber_configurations', 'probe_distribution')
