"""OTA准备快照独立保存，不信任历史客户端配置。"""
import sqlalchemy as sa
from alembic import op
from app.db.migration_helpers import column_exists
revision = 'e112a0bc0132'
down_revision = 'd111a0bc0131'
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists('test_executions', 'vrt_ota_setup'):
        op.add_column('test_executions', sa.Column('vrt_ota_setup', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('test_executions', 'vrt_ota_setup')
