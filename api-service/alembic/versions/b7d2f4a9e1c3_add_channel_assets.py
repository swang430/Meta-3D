"""add channel_assets (P2-16 信道资产多态化 S1)

Revision ID: b7d2f4a9e1c3
Revises: e9c47a1f3b82
Create Date: 2026-06-28

ChannelAsset: 四源 (GCM/B-1/B-2/RT) 统一的多态信道资产实体, 对 TestCase 暴露
channel_asset_id。判别键 source_type 决定 payload 形态。幂等 (table_exists),
方言无关 (add-table, 守门; 同 e9c47a1f3b82 模式 —— 非约束手术不套 PG-only)。
canonical_name unique nullable (custom 为 null, PG/SQLite 均允许多 NULL unique)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import index_exists, table_exists

revision: str = 'b7d2f4a9e1c3'
down_revision: Union[str, Sequence[str], None] = 'e9c47a1f3b82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    if not table_exists('channel_assets'):
        op.create_table(
            'channel_assets',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('source_type', sa.String(length=32), nullable=False),
            sa.Column('canonical_name', sa.String(length=512), nullable=True),
            sa.Column('derived_from', sa.String(length=512), nullable=True),
            sa.Column('allowed_targets', _JSON, nullable=False),
            sa.Column('center_frequency_hz', sa.Float(), nullable=True),
            sa.Column('bandwidth_mhz', sa.Float(), nullable=True),
            sa.Column('is_los', sa.Boolean(), nullable=True),
            sa.Column('k_factor_db', sa.Float(), nullable=True),
            sa.Column('ue_velocity_mps', _JSON, nullable=True),
            sa.Column('payload', _JSON, nullable=False),
            sa.Column('instrument_connection_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('associated_file_path', sa.String(length=1024), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
            sa.Column('created_by', sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='uq_channel_assets_name'),
            sa.UniqueConstraint('canonical_name', name='uq_channel_assets_canonical_name'),
        )
    if not index_exists('channel_assets', 'ix_channel_assets_name'):
        op.create_index(op.f('ix_channel_assets_name'), 'channel_assets', ['name'], unique=True)
    if not index_exists('channel_assets', 'ix_channel_assets_canonical_name'):
        op.create_index(
            op.f('ix_channel_assets_canonical_name'), 'channel_assets', ['canonical_name'],
            unique=True)
    if not index_exists('channel_assets', 'ix_channel_assets_source_type'):
        op.create_index(
            op.f('ix_channel_assets_source_type'), 'channel_assets', ['source_type'], unique=False)
    if not index_exists('channel_assets', 'ix_channel_assets_is_active'):
        op.create_index(
            op.f('ix_channel_assets_is_active'), 'channel_assets', ['is_active'], unique=False)


def downgrade() -> None:
    for idx in ('ix_channel_assets_is_active', 'ix_channel_assets_source_type',
                'ix_channel_assets_canonical_name', 'ix_channel_assets_name'):
        if index_exists('channel_assets', idx):
            op.drop_index(op.f(idx), table_name='channel_assets')
    if table_exists('channel_assets'):
        op.drop_table('channel_assets')
