"""保留运行器逐项采样证据。已有样本仍按客户端来源读取。"""
from alembic import op
import sqlalchemy as sa
from app.db.migration_helpers import column_exists

revision = "a819beb04188"
down_revision = "d5e7f9012345"
branch_labels = None
depends_on = None


def upgrade():
    if not column_exists("vrt_kpi_samples", "observation"):
        op.add_column("vrt_kpi_samples", sa.Column("observation", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("vrt_kpi_samples", "observation")
