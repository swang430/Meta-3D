"""P2-41 清理片：孤儿表 DROP + 演示期校准数据清理

Revision ID: a3e5c7d9f1b2
Revises: b6d8f0a2c4e6
Create Date: 2026-08-24

设计稿：docs/plans/2026-08-24-system-schema-review.md（用户 2026-08-24 批准）。
执行前数据已全量归档（CSV + DDL，见本片 PR body 的归档路径）。

DROP（R1/R2/R3，全部经 FK audit：DB 层零外键指向）：
- alerts_p1_38_backup_20260811 —— P1-38 收口留下的备份表（674 行已归档）
- instrument_logs —— P1-35 已删 model 的遗留孤儿表（0 行）
- probe_configurations —— 双零死表（0 行 + 全仓零引用），model/schema 同片删除

DELETE（R5，判据两层防现场库误删）：
- 时间围栏 created_at < '2026-05-14'（roadmap 治理基线日）：`use_mock` 列系
  2026-08-11/16 才加入（c2d4e6f8a1b3 / e7a9c1d3f5b7 / b6d8f0a2c4e6），现场
  2026-07-03 的 real 路损数据在任何库里都是 use_mock=NULL 的 brownfield 行，
  **裸 `use_mock IS NULL` 会误删它们** —— 时间围栏保证只清治理基线前的演示行。
- probe_path_loss_calibrations 追加 mock 指纹条件 `vna_model = 'Mock VNA'`：
  mock 分支恒写该字面值（path_loss_calibration_service），real 分支写真实
  vna_id —— 指纹条件补上时间围栏外 2026-07-02 本地演练的 1 行。
- probe_calibration_validity：派生表（可由重算刷新），删「引用的校准行已不
  存在」的悬空行（NOT EXISTS 精确条件，应用层软引用，无 DB 外键）。

Downgrade 不恢复数据（数据在归档 CSV）；仅重建三张表结构会制造
「空表 = 曾经没数据」的假象，故 downgrade 为显式 no-op + 说明。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_helpers import column_exists, table_exists

revision: str = "a3e5c7d9f1b2"
down_revision: Union[str, None] = "b6d8f0a2c4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FENCE = "created_at < '2026-05-14'"

# use_mock 列齐备的 6 张表（时间围栏即可）
_FENCED_TABLES = [
    "probe_amplitude_calibrations",
    "probe_polarization_calibrations",
    "probe_phase_calibrations",
    "link_calibrations",
    "rf_chain_calibrations",
    "channel_phase_calibrations",
]
# 无来源列的 2 张单行表（时间围栏）
_NO_PROVENANCE_TABLES = ["calibration_baselines", "ce_internal_calibrations"]


_VALIDITY_REFS = (
    ("amplitude_calibration_id", "probe_amplitude_calibrations"),
    ("phase_calibration_id", "probe_phase_calibrations"),
    ("polarization_calibration_id", "probe_polarization_calibrations"),
    ("link_calibration_id", "link_calibrations"),
)


def fenced_delete_sql(table: str) -> str:
    """时间围栏 DELETE（6 张 use_mock 表通用）—— upgrade 与行为门共用同一构造。"""
    return f"DELETE FROM {table} WHERE use_mock IS NULL AND {_FENCE}"


def path_loss_delete_sql() -> str:
    """path_loss 表：时间围栏 + mock 指纹（'Mock VNA' 系 mock 分支恒写字面值）。"""
    return (
        "DELETE FROM probe_path_loss_calibrations "
        f"WHERE use_mock IS NULL AND ({_FENCE} OR vna_model = 'Mock VNA')"
    )


def no_provenance_delete_sql(table: str) -> str:
    return f"DELETE FROM {table} WHERE {_FENCE}"


def validity_orphan_delete_sql(refs=_VALIDITY_REFS) -> str:
    """validity 悬空行：任一软引用指向已不存在的校准行即删（NOT EXISTS 精确）。
    相关子查询用全表名引用（不用 DELETE 别名——PG 认、SQLite 不认，
    行为门要在 SQLite 上执行同一构造）。"""
    v = "probe_calibration_validity"
    conds = [
        f"({v}.{col} IS NOT NULL AND NOT EXISTS "
        f"(SELECT 1 FROM {parent} p WHERE p.id = {v}.{col}))"
        for col, parent in refs
    ]
    return f"DELETE FROM {v} WHERE " + " OR ".join(conds)


def upgrade() -> None:
    # ---- R1/R2/R3: DROP 孤儿表与死表（brownfield 安全：不存在则跳过）----
    for t in ("alerts_p1_38_backup_20260811", "instrument_logs",
              "probe_configurations"):
        if table_exists(t):
            op.drop_table(t)

    # ---- R5: 演示期校准数据清理 ----
    for t in _FENCED_TABLES:
        if table_exists(t) and column_exists(t, "use_mock"):
            op.execute(fenced_delete_sql(t))
    if table_exists("probe_path_loss_calibrations") and \
            column_exists("probe_path_loss_calibrations", "use_mock"):
        op.execute(path_loss_delete_sql())
    for t in _NO_PROVENANCE_TABLES:
        if table_exists(t) and column_exists(t, "created_at"):
            op.execute(no_provenance_delete_sql(t))

    # ---- validity 悬空行（软引用，NOT EXISTS 精确删）----
    if table_exists("probe_calibration_validity"):
        refs = [
            (col, parent) for col, parent in _VALIDITY_REFS
            if column_exists("probe_calibration_validity", col) and table_exists(parent)
        ]
        if refs:
            op.execute(validity_orphan_delete_sql(tuple(refs)))


def downgrade() -> None:
    # 显式 no-op：数据恢复走归档 CSV（见 PR body），重建空表只会制造
    # 「曾经没数据」的假象；三张被 DROP 的表也无任何代码引用可服务。
    pass
