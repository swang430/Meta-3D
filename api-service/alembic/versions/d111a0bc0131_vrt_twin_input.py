"""独立保存服务端生成的数字孪生输入，旧配置不回填。"""
import sqlalchemy as sa
from alembic import op
from app.db.migration_helpers import column_exists

revision = "d111a0bc0131"
down_revision = "c87a1e6fd120"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists("test_executions", "vrt_twin_input"):
        op.add_column("test_executions", sa.Column("vrt_twin_input", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("test_executions", "vrt_twin_input")
