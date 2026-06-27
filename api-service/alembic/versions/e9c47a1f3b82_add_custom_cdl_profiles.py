"""add custom_cdl_profiles (P2-15 自定义 CDL 簇编辑)

Revision ID: e9c47a1f3b82
Revises: a1c3e5b7d9f2
Create Date: 2026-06-27

CustomCDLProfile: operator 自定义 CDL 信道 (簇级参数可编辑), 喂 input_mode=custom →
ChannelEgine 合成。平行 DUTProfile/SIMProfile, 簇列表存 JSONB。幂等 (table_exists),
方言无关 (add-table, 守门; 跟 c4a91f8e2d70 / d5b82c9f3e41 同模式 —— 非约束手术不套 PG-only)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import index_exists, table_exists

revision: str = 'e9c47a1f3b82'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5b7d9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    if not table_exists('custom_cdl_profiles'):
        op.create_table(
            'custom_cdl_profiles',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('center_frequency_hz', sa.Float(), nullable=True),
            sa.Column('pathloss_db', sa.Float(), nullable=True),
            sa.Column('is_los', sa.Boolean(), nullable=True),
            sa.Column('k_factor_db', sa.Float(), nullable=True),
            sa.Column('ue_velocity_mps', _JSON, nullable=True),
            sa.Column('clusters', _JSON, nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
            sa.Column('created_by', sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='uq_custom_cdl_profiles_name'),
        )
    if not index_exists('custom_cdl_profiles', 'ix_custom_cdl_profiles_name'):
        op.create_index(
            op.f('ix_custom_cdl_profiles_name'), 'custom_cdl_profiles', ['name'], unique=True)
    if not index_exists('custom_cdl_profiles', 'ix_custom_cdl_profiles_is_active'):
        op.create_index(
            op.f('ix_custom_cdl_profiles_is_active'), 'custom_cdl_profiles', ['is_active'],
            unique=False)


def downgrade() -> None:
    for idx in ('ix_custom_cdl_profiles_is_active', 'ix_custom_cdl_profiles_name'):
        if index_exists('custom_cdl_profiles', idx):
            op.drop_index(op.f(idx), table_name='custom_cdl_profiles')
    if table_exists('custom_cdl_profiles'):
        op.drop_table('custom_cdl_profiles')
