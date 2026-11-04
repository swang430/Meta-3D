"""追加采集撤销记录，不修改历史采用。"""
from alembic import op
import sqlalchemy as sa
from app.db.migration_helpers import table_exists

revision = 'c4d6e8f01234'
down_revision = 'f28a91c7d6b3'
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists('route_calibration_revocations'):
        op.create_table('route_calibration_revocations',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('lab_profile_id', sa.UUID(), sa.ForeignKey('lab_profiles.id'), nullable=False),
            sa.Column('acquisition_run_id', sa.UUID(), sa.ForeignKey('diagnostic_runs.id'), nullable=False),
            sa.Column('application_id', sa.UUID(), sa.ForeignKey('route_calibration_applications.id'), nullable=False),
            sa.Column('record', sa.JSON(), nullable=False),
            sa.UniqueConstraint('lab_profile_id', 'acquisition_run_id', name='uq_route_revoked_run'))


def downgrade():
    if table_exists('route_calibration_revocations'):
        op.drop_table('route_calibration_revocations')
