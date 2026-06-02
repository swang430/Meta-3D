"""add standard_channel_definitions (P2-12 SCD)

Revision ID: b9e2c7a40f31
Revises: f1d23a7b9c84
Create Date: 2026-06-01

P2-12 slice 2: Standard Channel Definition — 软件掌控的标准信道文件定义
(见 docs/architecture/testcase-driven-instrument-config.md §9)。P1-10 之后第一张新表
(P2-11/P2-10 都是 config 不是表)。幂等 (table_exists), 跟 c7a91b3e5d04 同模式。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import index_exists, table_exists

revision: str = 'b9e2c7a40f31'
down_revision: Union[str, Sequence[str], None] = 'f1d23a7b9c84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not table_exists('standard_channel_definitions'):
        op.create_table(
            'standard_channel_definitions',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            # 规范配置 (真值)
            sa.Column('band', sa.String(length=16), nullable=False),
            sa.Column('arfcn', sa.Integer(), nullable=False),
            sa.Column('bandwidth_mhz', sa.Integer(), nullable=False),
            sa.Column('model', sa.String(length=32), nullable=False),
            sa.Column('scenario', sa.String(length=32), nullable=False),
            sa.Column('mimo', sa.String(length=16), nullable=False),
            sa.Column('polarization', sa.String(length=8), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            # 标准名 (派生, denormalized)
            sa.Column('standard_name', sa.String(length=255), nullable=False),
            # 关联 (synced projection)
            sa.Column('instrument_connection_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('associated_file_path', sa.String(length=512), nullable=True),
            sa.Column(
                'association_source', sa.String(length=32), nullable=False,
                server_default='declared_only',
            ),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
            sa.ForeignKeyConstraint(
                ['instrument_connection_id'], ['instrument_connections.id'],
                ondelete='CASCADE',
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'instrument_connection_id', 'standard_name',
                name='uq_scd_binding_standard_name',
            ),
        )
    if not index_exists(
        'standard_channel_definitions', 'ix_standard_channel_definitions_standard_name'
    ):
        op.create_index(
            op.f('ix_standard_channel_definitions_standard_name'),
            'standard_channel_definitions', ['standard_name'], unique=False,
        )
    if not index_exists(
        'standard_channel_definitions',
        'ix_standard_channel_definitions_instrument_connection_id',
    ):
        op.create_index(
            op.f('ix_standard_channel_definitions_instrument_connection_id'),
            'standard_channel_definitions', ['instrument_connection_id'], unique=False,
        )


def downgrade() -> None:
    for idx in (
        'ix_standard_channel_definitions_instrument_connection_id',
        'ix_standard_channel_definitions_standard_name',
    ):
        if index_exists('standard_channel_definitions', idx):
            op.drop_index(op.f(idx), table_name='standard_channel_definitions')
    if table_exists('standard_channel_definitions'):
        op.drop_table('standard_channel_definitions')
