"""Helpers shared by alembic migrations.

The drift-fix migrations in this project need to be idempotent against
schema state because we support three deploy paths converging into one:

1. **Brownfield** — DB existed before alembic adoption with tables
   created by ``Base.metadata.create_all()``. Stamped at the baseline
   revision so the drift-fix migrations actually run and add the
   columns the model declared but ``create_all`` never produced.

2. **Greenfield via baseline** — the baseline revision now runs
   ``create_all()`` to produce every table in current model state. The
   subsequent drift-fix / system-preset migrations should detect the
   columns / tables already exist and skip without erroring.

3. **In-between weirdness** — e.g. a half-rolled-back deploy. Per-op
   guards mean each migration step adds only what's missing.

The cost of guarding every op is one ``inspect()`` call per migration.
The benefit is that fresh CI databases, customer deployments, and
existing brownfield DBs all reach the same end state via the same
``alembic upgrade head`` command.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def _inspector():
    return sa.inspect(op.get_bind())


def table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    insp = _inspector()
    if table_name not in insp.get_table_names():
        return False
    return column_name in {c["name"] for c in insp.get_columns(table_name)}


def index_exists(table_name: str, index_name: str) -> bool:
    insp = _inspector()
    if table_name not in insp.get_table_names():
        return False
    return index_name in {ix["name"] for ix in insp.get_indexes(table_name)}
