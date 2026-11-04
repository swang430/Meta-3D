"""保存四类信道诊断来源；不回填历史。"""
from alembic import op
import sqlalchemy as sa
from app.db.migration_helpers import column_exists
revision = 'd5e7f9012345'
down_revision = 'c4d6e8f01234'
branch_labels = None
depends_on = None
TABLES = ('doppler_calibrations', 'spatial_correlation_calibrations', 'angular_spread_calibrations', 'eis_validations')
def upgrade():
    for table in TABLES:
        if not column_exists(table, 'diagnostic_provenance'):
            op.add_column(table, sa.Column('diagnostic_provenance', sa.JSON(), nullable=True))
def downgrade():
    for table in TABLES:
        if column_exists(table, 'diagnostic_provenance'):
            op.drop_column(table, 'diagnostic_provenance')
