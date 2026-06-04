"""add dut_profiles (DUTProfile 自声明能力)

Revision ID: c4a91f8e2d70
Revises: b9e2c7a40f31
Create Date: 2026-06-04

DUTProfile: DUT 自声明能力档案 (平行 LabProfile)。规划期 operator 填 DUT spec
(max layers/调制/频段/UE category/双工), 供 attach 前 TestCase 校验 + 后续跟 UXM 协商
交叉核对。幂等 (table_exists), 跟 b9e2c7a40f31 / c7a91b3e5d04 同模式。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import index_exists, table_exists

revision: str = 'c4a91f8e2d70'
down_revision: Union[str, Sequence[str], None] = 'b9e2c7a40f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    if not table_exists('dut_profiles'):
        op.create_table(
            'dut_profiles',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('manufacturer', sa.String(length=255), nullable=True),
            sa.Column('model_name', sa.String(length=255), nullable=True),
            sa.Column('max_dl_layers', sa.Integer(), nullable=True),
            sa.Column('max_ul_layers', sa.Integer(), nullable=True),
            sa.Column('max_modulation_dl', sa.String(length=20), nullable=True),
            sa.Column('max_modulation_ul', sa.String(length=20), nullable=True),
            sa.Column('ue_category', sa.String(length=40), nullable=True),
            sa.Column('duplex_mode', sa.String(length=10), nullable=True),
            sa.Column('supported_bands', _JSON, nullable=True),
            sa.Column('extra_metadata', _JSON, nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
            sa.Column('created_by', sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='uq_dut_profiles_name'),
        )
    if not index_exists('dut_profiles', 'ix_dut_profiles_name'):
        op.create_index(op.f('ix_dut_profiles_name'), 'dut_profiles', ['name'], unique=True)
    if not index_exists('dut_profiles', 'ix_dut_profiles_is_active'):
        op.create_index(
            op.f('ix_dut_profiles_is_active'), 'dut_profiles', ['is_active'], unique=False,
        )


def downgrade() -> None:
    for idx in ('ix_dut_profiles_is_active', 'ix_dut_profiles_name'):
        if index_exists('dut_profiles', idx):
            op.drop_index(op.f(idx), table_name='dut_profiles')
    if table_exists('dut_profiles'):
        op.drop_table('dut_profiles')
