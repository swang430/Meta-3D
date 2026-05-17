"""add instrument_topology_profiles for P2-1 Phase 2.1

Revision ID: c7a91b3e5d04
Revises: a1b2c3d4e5f6
Create Date: 2026-05-17 16:00:00.000000

P2-1 Phase 2.1 — persist UXM topology profiles in the DB so operators
can create / edit / delete them via GUI without a code change +
redeploy. The 7 in-code built-in templates in
``app/hal/uxm_test_profiles.py`` are seeded via
``app.services.bootstrap.topology_profiles_seeder`` (rows-as-data lives
in bootstrap per the project's split: alembic owns schema, bootstrap
owns default rows).

Flat column layout (not a single JSON blob) mirrors
``chamber_configurations`` — makes ``SELECT ... WHERE band='N78'`` cheap
and Pydantic schemas easy to map.

Idempotency
-----------
Greenfield Postgres deploys hit baseline ``create_all()`` first, which
already produces the table from the model definition; this migration
detects the table exists and skips. Brownfield PG runs the
``create_table``. Either path no-ops harmlessly. SQLite test DBs use
``create_all()`` exclusively and don't run alembic.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import index_exists, table_exists


revision: str = 'c7a91b3e5d04'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not table_exists('instrument_topology_profiles'):
        op.create_table(
            'instrument_topology_profiles',
            sa.Column(
                'id', postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column(
                'profile_id', sa.String(length=100), nullable=False,
                comment="Stable identifier — built-ins use code-defined IDs "
                        "('caict_n78_2x2'); operator-created use 'custom_<slug>'.",
            ),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column(
                'category', sa.String(length=50), nullable=False,
                server_default='general',
            ),
            # NR cell
            sa.Column('band', sa.String(length=20), nullable=False, server_default='N78'),
            sa.Column('frequency_mhz', sa.Float(), nullable=False, server_default='3500.0'),
            sa.Column('bandwidth_mhz', sa.Float(), nullable=False, server_default='100.0'),
            sa.Column('scs_khz', sa.Integer(), nullable=False, server_default='30'),
            sa.Column('duplex', sa.String(length=10), nullable=False, server_default='TDD'),
            sa.Column('arfcn', sa.Integer(), nullable=True),
            # MIMO
            sa.Column('mimo_layers', sa.Integer(), nullable=False, server_default='2'),
            sa.Column('mimo_port_preset', sa.String(length=20), nullable=False, server_default='2x2'),
            # Power
            sa.Column('dl_power_dbm', sa.Float(), nullable=False, server_default='-50.0'),
            sa.Column('ssb_power_dbm', sa.Float(), nullable=False, server_default='-50.0'),
            # FRC / modulation
            sa.Column('modulation', sa.String(length=20), nullable=False, server_default='256QAM'),
            sa.Column('target_mcs', sa.Integer(), nullable=False, server_default='28'),
            # MAC throughput knobs
            sa.Column('sched_algo', sa.String(length=20), nullable=False, server_default='FULLBUFFER'),
            sa.Column('enable_amc', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('tdd_pattern', sa.String(length=20), nullable=False, server_default='DDDSU'),
            sa.Column('tdd_period', sa.String(length=20), nullable=False, server_default='5MS'),
            sa.Column('harq_max_trans', sa.Integer(), nullable=False, server_default='4'),
            sa.Column('harq_processes', sa.Integer(), nullable=False, server_default='16'),
            sa.Column('csi_rs_ports', sa.Integer(), nullable=True),
            sa.Column('stat_count', sa.Integer(), nullable=False, server_default='5000'),
            # Cell + state file
            sa.Column('cell_id', sa.String(length=20), nullable=False, server_default='CELL0'),
            sa.Column(
                'state_file', sa.String(length=500), nullable=True,
                comment='Optional UXM .state file path; when set, '
                        'set_cell_config short-circuits to MMEM:LOAD:STATe.',
            ),
            # Compat declaration
            sa.Column(
                'compatible_test_apps', sa.JSON(), nullable=False,
                server_default='[]',
                comment='List of Test App PROFILE_NAME values this profile is '
                        'compatible with (e.g. ["5G_NR_Test"]). Empty = any.',
            ),
            sa.Column('notes', sa.Text(), nullable=True, server_default=''),
            # System preset marker (clone-to-edit pattern)
            sa.Column(
                'is_system_preset', sa.Boolean(), nullable=False,
                server_default='false',
                comment='True for the 7 built-in profiles seeded by '
                        'app.services.bootstrap.topology_profiles_seeder; '
                        'rejects PUT/DELETE. Operator copies clear it.',
            ),
            # Audit
            sa.Column(
                'created_at', sa.DateTime(), nullable=False,
                server_default=sa.text('now()'),
            ),
            sa.Column(
                'updated_at', sa.DateTime(), nullable=True,
                server_default=sa.text('now()'),
            ),
            sa.Column('created_by', sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('profile_id', name='uq_topology_profile_id'),
        )

    if not index_exists(
        'instrument_topology_profiles',
        'ix_instrument_topology_profiles_profile_id',
    ):
        op.create_index(
            op.f('ix_instrument_topology_profiles_profile_id'),
            'instrument_topology_profiles', ['profile_id'], unique=False,
        )

    if not index_exists(
        'instrument_topology_profiles',
        'ix_instrument_topology_profiles_is_system_preset',
    ):
        op.create_index(
            op.f('ix_instrument_topology_profiles_is_system_preset'),
            'instrument_topology_profiles', ['is_system_preset'], unique=False,
        )


def downgrade() -> None:
    if index_exists(
        'instrument_topology_profiles',
        'ix_instrument_topology_profiles_is_system_preset',
    ):
        op.drop_index(
            op.f('ix_instrument_topology_profiles_is_system_preset'),
            table_name='instrument_topology_profiles',
        )
    if index_exists(
        'instrument_topology_profiles',
        'ix_instrument_topology_profiles_profile_id',
    ):
        op.drop_index(
            op.f('ix_instrument_topology_profiles_profile_id'),
            table_name='instrument_topology_profiles',
        )
    if table_exists('instrument_topology_profiles'):
        op.drop_table('instrument_topology_profiles')
