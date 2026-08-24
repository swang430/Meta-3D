# -*- coding: utf-8 -*-
"""P1-72 对比换源：report_comparisons / repeatability_tests 增 execution 级列

Revision ID: b7c9e1f3a5d7
Revises: a3e5c7d9f1b2
Create Date: 2026-08-25

两段：
0. 迁移只加裸列不带 FK（仓库先例 d8b412ca9f15：SQLite ALTER 不支持
   FK，downgrade DROP COLUMN 也会因 FK 定义失败——alembic 链测试抓出）；
   FK 关系由模型层承载，测试库 create_all 直建时生效。
1. add-column（方言无关，column_exists 守门）——report_comparisons 增
   baseline_execution_id / comparison_execution_ids；repeatability_tests 增
   test_case_id / execution_ids / metric_deltas。
2. 约束手术（PG-only）——repeatability_tests 的 mean_dbm / std_dev_db /
   validation_pass / threshold_db 放开 NOT NULL：execution_metrics 行不填
   dBm 语义列、无判据不造判决（P1-71 外审同母题：列名语义不许错配）。
   SQLite 测试库由模型 DDL 直建（已 nullable），无需手术。

两表生产库均为 0 行（2026-08-25 实查），无数据迁移动作。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import column_exists, table_exists


revision: str = "b7c9e1f3a5d7"
down_revision: Union[str, Sequence[str], None] = "a3e5c7d9f1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ADD_COLUMNS = {
    "report_comparisons": (
        sa.Column(
            "baseline_execution_id",
            postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
            nullable=True,
            comment="Baseline test execution（P1-72 对比换源）",
        ),
        sa.Column(
            "comparison_execution_ids",
            sa.JSON(),
            nullable=True,
            comment="Array of test execution UUIDs to compare（P1-72 对比换源）",
        ),
    ),
    "repeatability_tests": (
        sa.Column(
            "test_case_id",
            postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
            nullable=True,
            comment="同 TestCase 对齐记录的 case（execution_metrics 行必填）",
        ),
        sa.Column(
            "execution_ids",
            sa.JSON(),
            nullable=True,
            comment="参与对齐的 test_execution UUID 数组",
        ),
        sa.Column(
            "metric_deltas",
            sa.JSON(),
            nullable=True,
            comment="相对 baseline 的指标差分（吞吐/RSRP 方差/SINR），"
                    "含各 execution 的 provenance 标志",
        ),
    ),
}

_RELAX_NOT_NULL = (
    ("mean_dbm", sa.Float()),
    ("std_dev_db", sa.Float()),
    ("validation_pass", sa.Boolean()),
    ("threshold_db", sa.Float()),
)


def upgrade() -> None:
    for table, columns in _ADD_COLUMNS.items():
        if not table_exists(table):
            continue
        for col in columns:
            if not column_exists(table, col.name):
                op.add_column(table, col)

    # 约束手术只在 PG 上做（SQLite 测试库按模型 DDL 直建已是 nullable）
    if op.get_bind().dialect.name == "postgresql" and table_exists("repeatability_tests"):
        for name, coltype in _RELAX_NOT_NULL:
            if column_exists("repeatability_tests", name):
                op.alter_column(
                    "repeatability_tests", name,
                    existing_type=coltype, nullable=True,
                )


def downgrade() -> None:
    # 不回收紧 NOT NULL（execution_metrics 行一旦存在，回收紧会毁数据）；
    # 只撤新增列。用 batch_alter_table：链首迁移按模型元数据建表时这些列
    # 带模型层 FK，SQLite 直接 DROP COLUMN 会撞 FK 定义（链测试抓出）——
    # batch 模式在 SQLite 上重建表、在 PG 上退化为普通 ALTER。
    for table, columns in _ADD_COLUMNS.items():
        if not table_exists(table):
            continue
        names = [c.name for c in reversed(columns) if column_exists(table, c.name)]
        if not names:
            continue
        with op.batch_alter_table(table) as batch:
            for name in names:
                batch.drop_column(name)
