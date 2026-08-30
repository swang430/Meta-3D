# -*- coding: utf-8 -*-
"""Add server-owned BaseStation model presets.

Revision ID: f2a4c6e8b0d1
Revises: e6a8c0d2f4b6
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists


revision: str = "f2a4c6e8b0d1"
down_revision: Union[str, Sequence[str], None] = "e6a8c0d2f4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not table_exists("instrument_connections"):
        return
    if not column_exists("instrument_connections", "base_station_model_presets"):
        op.add_column(
            "instrument_connections",
            sa.Column(
                "base_station_model_presets",
                sa.JSON(),
                nullable=True,
                comment=(
                    "Server-owned saved BaseStation drafts keyed by model id; "
                    "active connection remains execution truth"
                ),
            ),
        )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT ic.id, ic.endpoint, ic.protocol, ic.notes,
                   ic.connection_params, cat.selected_model_id
              FROM instrument_connections AS ic
              JOIN instrument_categories AS cat ON cat.id = ic.category_id
             WHERE cat.category_key = 'baseStation'
               AND cat.selected_model_id IS NOT NULL
               AND ic.endpoint IS NOT NULL
               AND TRIM(ic.endpoint) <> ''
               AND ic.base_station_model_presets IS NULL
            """
        )
    ).mappings()
    table = sa.table(
        "instrument_connections",
        sa.column("id"),
        sa.column("base_station_model_presets", sa.JSON()),
    )
    for row in rows:
        raw_params = row["connection_params"]
        if isinstance(raw_params, str):
            import json

            raw_params = json.loads(raw_params)
        params = dict(raw_params or {})
        profile = params.pop("base_station_adapter_profile", None)
        params.pop("detected_test_app", None)
        model_id = str(row["selected_model_id"])
        preset = {
            "schema_version": 1,
            "model_id": model_id,
            "endpoint": str(row["endpoint"]).strip(),
            "controller": str(row["protocol"] or "").strip(),
            "notes": str(row["notes"] or "").strip(),
            "connection_params": params,
            "base_station_adapter_profile": profile,
        }
        bind.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(base_station_model_presets={model_id: preset})
        )


def downgrade() -> None:
    if table_exists("instrument_connections") and column_exists(
        "instrument_connections", "base_station_model_presets"
    ):
        op.drop_column("instrument_connections", "base_station_model_presets")
