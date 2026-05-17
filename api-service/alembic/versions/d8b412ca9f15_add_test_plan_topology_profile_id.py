"""add test_plans.topology_profile_id for P2-1 Phase 2.3

Revision ID: d8b412ca9f15
Revises: c7a91b3e5d04
Create Date: 2026-05-17 18:00:00.000000

P2-1 Phase 2.3 — optional plan-level UXM topology override.
When set, ``TestExecutionService.start_test_plan`` applies the
referenced profile to the baseStation driver before the first test
case runs. When null, the binding-level selection in
``InstrumentConnection.connection_params['topology_profile_id']``
(set at HAL bring-up) remains in effect.

Why stable-string ID instead of UUID FK to
``instrument_topology_profiles``:

- A topology profile may legitimately be deleted while a draft plan
  still references it (operator workflow: build profile → reference
  → realise profile was wrong → delete + create new). Hard FK
  would either block the delete or null the column via ON DELETE
  SET NULL — both surface the error far from where the operator can
  fix it. Stable string ID lets the start-time apply log a clean
  warning ("profile X not found, falling back to binding-level")
  and proceed.
- Matches the existing ``connection_params['topology_profile_id']``
  shape (also stable string), so the same
  ``topology_profile_service.get_dataclass`` lookup serves both.

Idempotency: column-level guard via ``column_exists``. Greenfield
``create_all`` produces the column from the model; brownfield runs
the ``add_column``. Either path no-ops harmlessly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists


revision: str = 'd8b412ca9f15'
down_revision: Union[str, Sequence[str], None] = 'c7a91b3e5d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not column_exists('test_plans', 'topology_profile_id'):
        op.add_column(
            'test_plans',
            sa.Column(
                'topology_profile_id', sa.String(length=100), nullable=True,
                comment='P2-1 Phase 2.3: optional plan-level UXM topology '
                        'override. References '
                        'instrument_topology_profiles.profile_id; null = '
                        'use binding-level selection. Stable string ID, '
                        'not UUID FK.',
            ),
        )


def downgrade() -> None:
    if column_exists('test_plans', 'topology_profile_id'):
        op.drop_column('test_plans', 'topology_profile_id')
