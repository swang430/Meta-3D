"""Explicit model ownership for instrument-file assets; never guess legacy owners.

Revision ID: c1e3f5a7b9d2
Revises: b9d2f4a6c8e0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1e3f5a7b9d2"
down_revision = "b9d2f4a6c8e0"
branch_labels = None
depends_on = None


def upgrade():
    # Baseline 引用当前 metadata：新装库已经含本片字段/约束；已有库才需要补齐。
    # offline SQL 仅用于明确的 b9d2f4a6c8e0 → 本 revision，不能反射。
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    for table in ("standard_channel_definitions", "channel_assets"):
        if inspector is not None and "instrument_model_id" in {
            column["name"] for column in inspector.get_columns(table)
        }:
            continue
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("instrument_model_id", postgresql.UUID(as_uuid=True),
                nullable=True, comment="显式仪器型号归属；NULL=历史待确认/非仪器资产，不由当前选择回填"))
            batch.create_foreign_key(f"fk_{table}_instrument_model", "instrument_models",
                                     ["instrument_model_id"], ["id"])
            batch.create_index(f"ix_{table}_instrument_model_id", ["instrument_model_id"])
    with op.batch_alter_table("standard_channel_definitions") as batch:
        constraints = ({item["name"] for item in inspector.get_unique_constraints("standard_channel_definitions")}
                       if inspector is not None else {"uq_scd_binding_standard_name"})
        if "uq_scd_binding_standard_name" in constraints:
            batch.drop_constraint("uq_scd_binding_standard_name", type_="unique")
        if "uq_scd_binding_model_standard_name" not in constraints:
            batch.create_unique_constraint("uq_scd_binding_model_standard_name",
                ["instrument_connection_id", "instrument_model_id", "standard_name"])


def downgrade():
    # Cross-model duplicate names cannot be represented by the old schema.
    # Constraint creation fails atomically instead of deleting/renaming data.
    with op.batch_alter_table("standard_channel_definitions") as batch:
        batch.drop_constraint("uq_scd_binding_model_standard_name", type_="unique")
        batch.create_unique_constraint("uq_scd_binding_standard_name",
                                       ["instrument_connection_id", "standard_name"])
    for table in ("channel_assets", "standard_channel_definitions"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_instrument_model_id")
            batch.drop_constraint(f"fk_{table}_instrument_model", type_="foreignkey")
            batch.drop_column("instrument_model_id")
