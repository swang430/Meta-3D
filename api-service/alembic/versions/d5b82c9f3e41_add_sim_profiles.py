"""add sim_profiles (SIMProfile SIM/eSIM 身份+鉴权声明)

Revision ID: d5b82c9f3e41
Revises: c4a91f8e2d70
Create Date: 2026-06-05

SIMProfile: 测试卡身份 (IMSI/PLMN) + 鉴权凭据 (Ki/OPc/算法) 声明 (P2-13 阶段 1, 平行
DUTProfile)。规划期 operator 登记卡池, 供 SIM↔UXM 一致性校验 + attach 后实测 IMSI 核对。
幂等 (table_exists), 跟 c4a91f8e2d70 同模式。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import index_exists, table_exists

revision: str = 'd5b82c9f3e41'
down_revision: Union[str, Sequence[str], None] = 'c4a91f8e2d70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    if not table_exists('sim_profiles'):
        op.create_table(
            'sim_profiles',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('imsi', sa.String(length=20), nullable=True),
            sa.Column('iccid', sa.String(length=25), nullable=True),
            sa.Column('mcc', sa.String(length=3), nullable=True),
            sa.Column('mnc', sa.String(length=3), nullable=True),
            sa.Column('ki', sa.String(length=64), nullable=True),
            sa.Column('opc', sa.String(length=64), nullable=True),
            sa.Column('auth_algorithm', sa.String(length=20), nullable=True),
            sa.Column('card_kind', sa.String(length=20), nullable=True),
            sa.Column('sim_form', sa.String(length=10), nullable=True),
            sa.Column('eid', sa.String(length=40), nullable=True),
            sa.Column('esim_profile_id', sa.String(length=64), nullable=True),
            sa.Column('extra_metadata', _JSON, nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
            sa.Column('created_by', sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='uq_sim_profiles_name'),
        )
    if not index_exists('sim_profiles', 'ix_sim_profiles_name'):
        op.create_index(op.f('ix_sim_profiles_name'), 'sim_profiles', ['name'], unique=True)
    if not index_exists('sim_profiles', 'ix_sim_profiles_is_active'):
        op.create_index(
            op.f('ix_sim_profiles_is_active'), 'sim_profiles', ['is_active'], unique=False,
        )


def downgrade() -> None:
    for idx in ('ix_sim_profiles_is_active', 'ix_sim_profiles_name'):
        if index_exists('sim_profiles', idx):
            op.drop_index(op.f(idx), table_name='sim_profiles')
    if table_exists('sim_profiles'):
        op.drop_table('sim_profiles')
