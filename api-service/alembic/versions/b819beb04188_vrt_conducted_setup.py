"""独立保存服务端生成的传导准备记录，旧配置不回填。"""
import sqlalchemy as sa
from alembic import op
from app.db.migration_helpers import column_exists

revision = "b819beb04188"
down_revision = "a819beb04188"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists("test_executions", "vrt_conducted_setup"):
        op.add_column("test_executions", sa.Column("vrt_conducted_setup", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("test_executions", "vrt_conducted_setup")
