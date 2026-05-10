"""baseline (pre-alembic schema snapshot)

Revision ID: 40fd1c51ff40
Revises: 
Create Date: 2026-05-10 22:04:08.730910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40fd1c51ff40'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: this revision marks the schema state at the moment alembic
    was introduced. The DB at that moment was managed by
    Base.metadata.create_all() in app/db/database.py and reflected
    whatever was in the model files when each table was first created —
    NOT necessarily the current state of the model files. Subsequent
    revisions take over from here and supply the deltas that
    create_all() never produced (it only creates new tables; it cannot
    add columns to existing ones)."""


def downgrade() -> None:
    """No-op."""
