"""fix drift: add P0-P2 calibration + probe_pattern columns

Revision ID: 83211f12daf2
Revises: 40fd1c51ff40
Create Date: 2026-05-10 22:05:37.419802

Onboarding alembic revealed 11 columns that were declared on SQLAlchemy
models (P0-P2 path-loss calibration work + Phase 2f probe-pattern
import) but never made it to Postgres because the project used
Base.metadata.create_all() — which only creates tables, never adds
columns to existing ones. That drift caused GET /chambers to 500 with
``UndefinedColumn: chamber_configurations.cable_sgh_to_sa_loss_db``.

Idempotency
-----------
Every ``add_column`` / ``create_index`` is guarded with an inspector
check (see ``alembic/_helpers.py``). On a brownfield DB stamped at the
baseline, the columns are missing and get added. On a greenfield DB
that just ran the baseline (which does ``create_all`` from current
model state), the columns are already present and the migration is a
no-op. Either way, the end state is identical.

Autogenerate also flagged two unrelated diff classes that we
deliberately DO NOT include here:

  1. Comment/docstring drift on instrument_categories, test_cases,
     test_executions — cosmetic only.
  2. test_executions JSONB → JSON "downgrades": the DB is correctly
     JSONB (PG-native, indexable); the model file declared generic
     ``JSON``. Applying the autogenerate suggestion would lose binary
     storage + GIN indexability. Real fix is on the model side
     (declare ``JSONB``); test_plan.py was updated separately.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, index_exists


revision: str = '83211f12daf2'
down_revision: Union[str, Sequence[str], None] = '40fd1c51ff40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if not column_exists(table, column.name):
        op.add_column(table, column)


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if not index_exists(table, name):
        op.create_index(op.f(name), table, columns, unique=False)


def _drop_column_if_present(table: str, column: str) -> None:
    if column_exists(table, column):
        op.drop_column(table, column)


def _drop_index_if_present(name: str, table: str) -> None:
    if index_exists(table, name):
        op.drop_index(op.f(name), table_name=table)


def upgrade() -> None:
    # chamber_configurations: SGH→SA cable loss for CE+SA path-loss main path
    _add_column_if_missing(
        'chamber_configurations',
        sa.Column(
            'cable_sgh_to_sa_loss_db', sa.Float(), nullable=True,
            comment='SGH→SA 电缆损耗 (dB), commissioning 时一次性 SOLT 测好. '
                    '为空时 fallback 到 legacy VNA 路径; 设值后路损校准走 CE+SA 主路径.',
        ),
    )

    # probe_path_loss_calibrations: P1/P2 calibration + LabProfile binding
    _add_column_if_missing(
        'probe_path_loss_calibrations',
        sa.Column(
            'path_loss_db_by_rf_chain', sa.JSON(), nullable=True,
            comment='Per-RFChain path-loss breakdown keyed by SwitchTopology connection id',
        ),
    )
    _add_column_if_missing(
        'probe_path_loss_calibrations',
        sa.Column(
            'lab_profile_id', sa.UUID(), nullable=True,
            comment='LabProfile this cert was calibrated against',
        ),
    )
    _add_column_if_missing(
        'probe_path_loss_calibrations',
        sa.Column(
            'operating_mode', sa.String(length=50), nullable=True,
            comment="SwitchTopology operating mode at calibration time, e.g. 'mimo_ota'",
        ),
    )
    _add_column_if_missing(
        'probe_path_loss_calibrations',
        sa.Column(
            'topology_id', sa.UUID(), nullable=True,
            comment='Resolved SwitchTopology id at calibration time',
        ),
    )
    _create_index_if_missing(
        'ix_probe_path_loss_calibrations_lab_profile_id',
        'probe_path_loss_calibrations', ['lab_profile_id'],
    )

    # probe_patterns: Phase 2f vendor pattern import provenance fields.
    # ``source`` is declared NOT NULL on the model. Existing rows (if any)
    # need a value, so we add with a server_default first, then drop the
    # default so future inserts must be explicit.
    if not column_exists('probe_patterns', 'source'):
        op.add_column(
            'probe_patterns',
            sa.Column(
                'source', sa.String(length=30), nullable=False,
                server_default='vendor_datasheet',
                comment="数据来源: 'vendor_datasheet' | 'in_chamber_measured'",
            ),
        )
        # After backfilling existing rows via the server_default, drop the
        # default so future inserts must specify ``source`` explicitly.
        # SQLite doesn't support ALTER COLUMN ... DROP DEFAULT; skip the
        # cleanup there — the default is harmless (NOT NULL constraint
        # still enforced by the model).
        if op.get_bind().dialect.name != 'sqlite':
            op.alter_column('probe_patterns', 'source', server_default=None)
    _add_column_if_missing(
        'probe_patterns',
        sa.Column('probe_model', sa.String(length=100), nullable=True,
                  comment="探头型号 e.g. 'SGA-3500'"),
    )
    _add_column_if_missing(
        'probe_patterns',
        sa.Column('probe_vendor', sa.String(length=100), nullable=True,
                  comment="探头厂商 e.g. 'MVG' / 'Satimo' / 'Keysight'"),
    )
    _add_column_if_missing(
        'probe_patterns',
        sa.Column('probe_serial', sa.String(length=100), nullable=True,
                  comment='探头序列号 (同型号不同实例)'),
    )
    _add_column_if_missing(
        'probe_patterns',
        sa.Column('imported_file_format', sa.String(length=20), nullable=True,
                  comment="导入文件格式: 'ticra_cut' | 'csv' | 'json'; 实测路径为 None"),
    )
    _add_column_if_missing(
        'probe_patterns',
        sa.Column(
            'coordinate_system', sa.String(length=20), nullable=True,
            comment="角度坐标系: 'az_el' (我们的标准, az 0-360 / el 0-180) | "
                    "'theta_phi' (TICRA 标准, theta 0-180 / phi 0-360); 导入时若是 "
                    "theta_phi 应转换为 az_el 后存储, 此字段记原始格式",
        ),
    )
    _create_index_if_missing(
        'ix_probe_patterns_source', 'probe_patterns', ['source'],
    )


def downgrade() -> None:
    _drop_index_if_present('ix_probe_patterns_source', 'probe_patterns')
    for col in ('coordinate_system', 'imported_file_format', 'probe_serial',
                'probe_vendor', 'probe_model', 'source'):
        _drop_column_if_present('probe_patterns', col)

    _drop_index_if_present(
        'ix_probe_path_loss_calibrations_lab_profile_id',
        'probe_path_loss_calibrations',
    )
    for col in ('topology_id', 'operating_mode', 'lab_profile_id',
                'path_loss_db_by_rf_chain'):
        _drop_column_if_present('probe_path_loss_calibrations', col)

    _drop_column_if_present('chamber_configurations', 'cable_sgh_to_sa_loss_db')
