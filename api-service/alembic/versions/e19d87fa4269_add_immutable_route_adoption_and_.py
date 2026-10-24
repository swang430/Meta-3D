"""add immutable route adoption and current selection

Revision ID: e19d87fa4269
Revises: c1e3f5a7b9d2
Create Date: 2026-10-24 18:08:09.220481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.db.migration_helpers import table_exists, index_exists


# revision identifiers, used by Alembic.
revision: str = 'e19d87fa4269'
down_revision: Union[str, Sequence[str], None] = 'c1e3f5a7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """仅新增空表；不为历史采集回填确认或认证状态。"""
    # baseline uses current Base.metadata; both fresh and create_all databases
    # may already contain these tables. Guard each operation, not DB exceptions.
    if not table_exists('route_calibration_applications'):
        op.create_table('route_calibration_applications',
        sa.Column('id',sa.UUID(),primary_key=True),
        sa.Column('lab_profile_id',sa.UUID(),sa.ForeignKey('lab_profiles.id'),nullable=False),
        sa.Column('acquisition_run_id',sa.UUID(),sa.ForeignKey('diagnostic_runs.id'),nullable=False),
        sa.Column('topology_id',sa.UUID(),sa.ForeignKey('switch_topologies.id'),nullable=False),
        sa.Column('chain_id',sa.String(500),nullable=False),
        sa.Column('idempotency_key',sa.UUID(),nullable=False),
        sa.Column('request_payload',sa.JSON(),nullable=False),
        sa.Column('record',sa.JSON(),nullable=False),
        sa.UniqueConstraint('lab_profile_id','idempotency_key',name='uq_route_application_idempotency'))
    if not index_exists('route_calibration_applications','ix_route_calibration_applications_lab_profile_id'):
        op.create_index('ix_route_calibration_applications_lab_profile_id',
            'route_calibration_applications',['lab_profile_id'])
    if not table_exists('route_calibration_selections'):
        op.create_table('route_calibration_selections',
        sa.Column('id',sa.UUID(),primary_key=True),
        sa.Column('lab_profile_id',sa.UUID(),sa.ForeignKey('lab_profiles.id'),nullable=False),
        sa.Column('topology_id',sa.UUID(),sa.ForeignKey('switch_topologies.id'),nullable=False),
        sa.Column('operating_mode',sa.String(100),nullable=False),
        sa.Column('chain_id',sa.String(500),nullable=False),
        sa.Column('frequency_mhz',sa.Float(),nullable=False),
        sa.Column('reference_identity_digest',sa.String(64),nullable=False),
        sa.Column('application_id',sa.UUID(),sa.ForeignKey('route_calibration_applications.id'),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.UniqueConstraint('lab_profile_id','topology_id','operating_mode','chain_id',
            'frequency_mhz','reference_identity_digest',name='uq_route_selection_scope'))


def downgrade() -> None:
    """仅撤销本revision的两张表。"""
    if table_exists('route_calibration_selections'):
        op.drop_table('route_calibration_selections')
    if index_exists('route_calibration_applications','ix_route_calibration_applications_lab_profile_id'):
        op.drop_index('ix_route_calibration_applications_lab_profile_id',table_name='route_calibration_applications')
    if table_exists('route_calibration_applications'):
        op.drop_table('route_calibration_applications')
