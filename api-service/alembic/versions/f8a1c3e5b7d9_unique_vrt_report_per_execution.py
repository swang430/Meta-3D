"""enforce one archived VRT report per execution

Revision ID: f8a1c3e5b7d9
Revises: e7a9c1d3f5b7
Create Date: 2026-08-16

Existing duplicate non-NULL execution IDs are not guessed or deleted.  The
migration fails loudly so an operator can preserve and reconcile formal report
artifacts before installing the uniqueness invariant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import index_exists, table_exists


revision: str = "f8a1c3e5b7d9"
down_revision: Union[str, Sequence[str], None] = "e7a9c1d3f5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "test_reports"
INDEX = "uq_test_reports_road_test_execution_id_not_null"


def upgrade() -> None:
    if not table_exists(TABLE) or index_exists(TABLE, INDEX):
        return

    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT road_test_execution_id
            FROM test_reports
            WHERE road_test_execution_id IS NOT NULL
            GROUP BY road_test_execution_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot enforce one VRT report per execution: duplicate "
            "test_reports.road_test_execution_id values exist; reconcile the "
            "formal report artifacts before retrying the migration."
        )

    op.create_index(
        INDEX,
        TABLE,
        ["road_test_execution_id"],
        unique=True,
        postgresql_where=sa.text("road_test_execution_id IS NOT NULL"),
        sqlite_where=sa.text("road_test_execution_id IS NOT NULL"),
    )


def downgrade() -> None:
    if table_exists(TABLE) and index_exists(TABLE, INDEX):
        op.drop_index(INDEX, table_name=TABLE)
