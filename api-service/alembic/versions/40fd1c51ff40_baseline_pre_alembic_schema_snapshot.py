"""baseline (pre-alembic schema snapshot)

Revision ID: 40fd1c51ff40
Revises:
Create Date: 2026-05-10 22:04:08.730910

The first revision in the alembic chain. Bootstraps the schema for
greenfield databases (CI, new customer installs); a no-op for
brownfield databases that were already managed by
``Base.metadata.create_all()`` before alembic was introduced.

Mechanics
---------
``Base.metadata.create_all(checkfirst=True)`` is the default — it only
issues CREATE TABLE for tables not already present. Combined with the
follow-up drift-fix / system-preset migrations guarding their own ops
behind ``inspect()`` checks (see ``alembic/_helpers.py``), both paths
converge to the same end state without a separate "fresh install"
script.

A NOTE ON HISTORICAL FIDELITY
-----------------------------
A strictly-correct alembic baseline would hand-write CREATE TABLE
statements representing the schema **at the moment alembic was
introduced**, so that running the full chain end-to-end reproduces the
historical evolution. We deliberately don't do that here — keeping a
frozen DDL snapshot in lockstep with model edits is high-effort for
zero practical payoff (nobody runs the chain to recover an historical
state). Instead this revision pins to *current* model state, and the
subsequent migrations remain useful for brownfield catch-up.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "40fd1c51ff40"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_models_loaded() -> None:
    """Walk app.models/* so every Base subclass registers on Base.metadata
    before we touch the engine. Without this, only modules re-exported
    from ``app/models/__init__.py`` are visible to create_all/drop_all,
    and a freshly-added model file silently goes missing."""
    import importlib
    import pkgutil

    import app.models as _models_pkg

    for mod_info in pkgutil.iter_modules(_models_pkg.__path__):
        importlib.import_module(f"{_models_pkg.__name__}.{mod_info.name}")


def upgrade() -> None:
    _ensure_models_loaded()
    from app.db.database import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Tear the schema down. Only ever invoked by an operator running
    ``alembic downgrade base`` — destructive, do not run in prod."""
    _ensure_models_loaded()
    from app.db.database import Base

    Base.metadata.drop_all(bind=op.get_bind())
