"""add test_steps.needs JSONB for P1-1 plan-level pre-flight

Revision ID: a1b2c3d4e5f6
Revises: e863f092696b
Create Date: 2026-05-16 00:00:00.000000

P1-1 plan-level pre-flight needs a place on each step template to
declare which canonical capability tokens the step requires of the
lab's bound drivers. The validator (`app/services/preflight.py`)
reads `TestStep.needs` for every step in the plan, then asks each
driver in the lab whether it exposes those tokens (via the
`driver.capabilities` set landed in P2-2, PR #21).

Kept as a top-level column rather than nesting in `parameters`
because `needs` is a step-template *contract* — invariant across
executions — while `parameters` is per-execution user input. Mixing
would muddle the schema.

Default `[]` so existing rows stay permissive (no capability
gates) — only steps that opt into a `needs` declaration go through
gap-checking. Seed updates ship in the same PR for the F64
calibration-tone step (`needs=["ce.interference_generator"]`) so
this PR has at least one dogfood row.

Idempotency
-----------
Greenfield Postgres deploys hit baseline create_all() first, which
already produces the column from the model definition. Brownfield
PG runs the column add. Either path no-ops harmlessly. SQLite test
DBs use create_all() exclusively and don't run alembic.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e863f092696b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not column_exists('test_steps', 'needs'):
        op.add_column(
            'test_steps',
            sa.Column(
                'needs', sa.JSON(), nullable=False,
                server_default='[]',
                comment='P1-1: list of canonical capability tokens this step '
                        'requires; checked by app/services/preflight.py against '
                        'each driver.capabilities (see app/hal/capabilities.py:'
                        'KNOWN_CAPABILITIES for the vocabulary).',
            ),
        )


def downgrade() -> None:
    if column_exists('test_steps', 'needs'):
        op.drop_column('test_steps', 'needs')
