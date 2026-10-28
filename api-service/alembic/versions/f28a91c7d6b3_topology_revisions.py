"""新增不可变拓扑修订；不扫描或改写已有JSON。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.db.migration_helpers import column_exists, table_exists

revision = 'f28a91c7d6b3'
down_revision = 'e19d87fa4269'
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists('switch_topologies', 'revision'):
        op.add_column('switch_topologies', sa.Column('revision', sa.Integer(), nullable=False, server_default='0'))
    if not table_exists('switch_topology_revisions'):
        op.create_table('switch_topology_revisions',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('topology_id', sa.UUID(), sa.ForeignKey('switch_topologies.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('revision', sa.Integer(), nullable=False),
            sa.Column('operation', sa.String(20), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('restored_from_revision', sa.Integer(), nullable=True),
            sa.Column('snapshot', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
            sa.Column('recorded_metadata', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
            sa.UniqueConstraint('topology_id', 'revision', name='uq_switch_topology_revision'))


def downgrade():
    if table_exists('switch_topology_revisions'):
        op.drop_table('switch_topology_revisions')
    if column_exists('switch_topologies', 'revision'):
        op.drop_column('switch_topologies', 'revision')
