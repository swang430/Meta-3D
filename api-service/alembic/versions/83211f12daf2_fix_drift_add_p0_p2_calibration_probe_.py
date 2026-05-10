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

Autogenerate also flagged two unrelated diff classes that we deliberately
DO NOT include here:

  1. Comment/docstring drift on instrument_categories, test_cases,
     test_executions — cosmetic only.
  2. test_executions JSONB → JSON "downgrades": the DB is correctly
     JSONB (PG-native, indexable); the model file declares generic
     ``JSON``. Applying the autogenerate suggestion would lose binary
     storage + GIN indexability. Real fix is on the model side
     (declare ``JSONB``); a separate revision can take that on once the
     model is corrected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '83211f12daf2'
down_revision: Union[str, Sequence[str], None] = '40fd1c51ff40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # chamber_configurations: SGH→SA cable loss for CE+SA path-loss main path
    op.add_column(
        'chamber_configurations',
        sa.Column(
            'cable_sgh_to_sa_loss_db', sa.Float(), nullable=True,
            comment='SGH→SA 电缆损耗 (dB), commissioning 时一次性 SOLT 测好. '
                    '为空时 fallback 到 legacy VNA 路径; 设值后路损校准走 CE+SA 主路径.',
        ),
    )

    # probe_path_loss_calibrations: P1/P2 calibration + LabProfile binding
    op.add_column(
        'probe_path_loss_calibrations',
        sa.Column(
            'path_loss_db_by_rf_chain', sa.JSON(), nullable=True,
            comment='Per-RFChain path-loss breakdown keyed by SwitchTopology connection id',
        ),
    )
    op.add_column(
        'probe_path_loss_calibrations',
        sa.Column(
            'lab_profile_id', sa.UUID(), nullable=True,
            comment='LabProfile this cert was calibrated against',
        ),
    )
    op.add_column(
        'probe_path_loss_calibrations',
        sa.Column(
            'operating_mode', sa.String(length=50), nullable=True,
            comment="SwitchTopology operating mode at calibration time, e.g. 'mimo_ota'",
        ),
    )
    op.add_column(
        'probe_path_loss_calibrations',
        sa.Column(
            'topology_id', sa.UUID(), nullable=True,
            comment='Resolved SwitchTopology id at calibration time',
        ),
    )
    op.create_index(
        op.f('ix_probe_path_loss_calibrations_lab_profile_id'),
        'probe_path_loss_calibrations', ['lab_profile_id'], unique=False,
    )

    # probe_patterns: Phase 2f vendor pattern import provenance fields.
    # `source` is declared NOT NULL on the model. Existing rows (if any)
    # need a value, so we add the column with a server_default first,
    # backfill happens implicitly, then drop the default so future
    # inserts must be explicit.
    op.add_column(
        'probe_patterns',
        sa.Column(
            'source', sa.String(length=30), nullable=False,
            server_default='vendor_datasheet',
            comment="数据来源: 'vendor_datasheet' | 'in_chamber_measured'",
        ),
    )
    op.alter_column('probe_patterns', 'source', server_default=None)
    op.add_column(
        'probe_patterns',
        sa.Column('probe_model', sa.String(length=100), nullable=True,
                  comment="探头型号 e.g. 'SGA-3500'"),
    )
    op.add_column(
        'probe_patterns',
        sa.Column('probe_vendor', sa.String(length=100), nullable=True,
                  comment="探头厂商 e.g. 'MVG' / 'Satimo' / 'Keysight'"),
    )
    op.add_column(
        'probe_patterns',
        sa.Column('probe_serial', sa.String(length=100), nullable=True,
                  comment='探头序列号 (同型号不同实例)'),
    )
    op.add_column(
        'probe_patterns',
        sa.Column('imported_file_format', sa.String(length=20), nullable=True,
                  comment="导入文件格式: 'ticra_cut' | 'csv' | 'json'; 实测路径为 None"),
    )
    op.add_column(
        'probe_patterns',
        sa.Column(
            'coordinate_system', sa.String(length=20), nullable=True,
            comment="角度坐标系: 'az_el' (我们的标准, az 0-360 / el 0-180) | "
                    "'theta_phi' (TICRA 标准, theta 0-180 / phi 0-360); 导入时若是 "
                    "theta_phi 应转换为 az_el 后存储, 此字段记原始格式",
        ),
    )
    op.create_index(
        op.f('ix_probe_patterns_source'),
        'probe_patterns', ['source'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_probe_patterns_source'), table_name='probe_patterns')
    op.drop_column('probe_patterns', 'coordinate_system')
    op.drop_column('probe_patterns', 'imported_file_format')
    op.drop_column('probe_patterns', 'probe_serial')
    op.drop_column('probe_patterns', 'probe_vendor')
    op.drop_column('probe_patterns', 'probe_model')
    op.drop_column('probe_patterns', 'source')

    op.drop_index(
        op.f('ix_probe_path_loss_calibrations_lab_profile_id'),
        table_name='probe_path_loss_calibrations',
    )
    op.drop_column('probe_path_loss_calibrations', 'topology_id')
    op.drop_column('probe_path_loss_calibrations', 'operating_mode')
    op.drop_column('probe_path_loss_calibrations', 'lab_profile_id')
    op.drop_column('probe_path_loss_calibrations', 'path_loss_db_by_rf_chain')

    op.drop_column('chamber_configurations', 'cable_sgh_to_sa_loss_db')
