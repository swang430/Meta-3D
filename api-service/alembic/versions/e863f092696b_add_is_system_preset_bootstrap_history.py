"""add is_system_preset + bootstrap_history

Revision ID: e863f092696b
Revises: 83211f12daf2
Create Date: 2026-05-10 23:01:35.375981

Two related changes that enable the bootstrap-seeded "factory defaults"
workflow:

1. ``chamber_configurations.is_system_preset`` — flags rows seeded by
   ``scripts.bootstrap`` as canonical out-of-the-box options. The API
   rejects PUT/DELETE on such rows. To customize, the user clones via
   ``POST /chambers/{id}/duplicate`` and edits the copy.

2. ``bootstrap_history`` — per-DB tombstone of which seeders have run
   and at what version. Lets ``scripts.bootstrap`` be safely re-run any
   number of times, and lets a future seeder version bump trigger
   exactly one update on existing installations.

Idempotency
-----------
Both ops are guarded by inspector checks: on greenfield DBs the
baseline's create_all() will have produced these structures already, so
this migration becomes a no-op there. On brownfield DBs they're newly
created. See ``alembic/_helpers.py`` for the helper rationale.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, index_exists, table_exists


revision: str = 'e863f092696b'
down_revision: Union[str, Sequence[str], None] = '83211f12daf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not table_exists('bootstrap_history'):
        op.create_table(
            'bootstrap_history',
            sa.Column('seeder_name', sa.String(length=100), nullable=False,
                      comment="Stable identifier of the seeder, e.g. 'chamber_presets'"),
            sa.Column('seeder_version', sa.Integer(), nullable=False,
                      comment='Bump this in the seeder when default data changes; '
                              'bootstrap re-runs when DB version < code version'),
            sa.Column('rows_inserted', sa.Integer(), nullable=False,
                      server_default='0',
                      comment='How many rows the last successful run created'),
            sa.Column('rows_skipped', sa.Integer(), nullable=False,
                      server_default='0',
                      comment='How many rows were already present and left untouched'),
            sa.Column('last_run_at', sa.DateTime(), server_default=sa.text('now()'),
                      nullable=False),
            sa.PrimaryKeyConstraint('seeder_name'),
        )

    if not column_exists('chamber_configurations', 'is_system_preset'):
        op.add_column(
            'chamber_configurations',
            sa.Column(
                'is_system_preset', sa.Boolean(), nullable=False,
                server_default='false',
                comment='True for canonical out-of-the-box presets seeded by '
                        'scripts.bootstrap; rejects PUT/DELETE. User copies clear it.',
            ),
        )

    if not index_exists(
        'chamber_configurations', 'ix_chamber_configurations_is_system_preset'
    ):
        op.create_index(
            op.f('ix_chamber_configurations_is_system_preset'),
            'chamber_configurations', ['is_system_preset'], unique=False,
        )


def downgrade() -> None:
    if index_exists(
        'chamber_configurations', 'ix_chamber_configurations_is_system_preset'
    ):
        op.drop_index(
            op.f('ix_chamber_configurations_is_system_preset'),
            table_name='chamber_configurations',
        )
    if column_exists('chamber_configurations', 'is_system_preset'):
        op.drop_column('chamber_configurations', 'is_system_preset')
    if table_exists('bootstrap_history'):
        op.drop_table('bootstrap_history')
