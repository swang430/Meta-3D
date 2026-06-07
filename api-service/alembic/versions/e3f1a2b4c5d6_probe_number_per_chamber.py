"""probe_number 改为按 chamber 局部唯一 (drop 全局唯一 + 回填 1..N + 复合唯一)

把 probes.probe_number 从全局唯一 (PG 自动约束 probes_probe_number_key) 改成
按 chamber 局部编号 (每暗室 1..N), 全局唯一性靠 (chamber_config_id, probe_number)
复合唯一约束保证。回填现有数据: 每个 chamber 内按 (probe_number, id) 重排成 1..N
(例: CAICT-FS 之前被 offset 成 33..94, 回填后变 1..62)。

幂等 + 仅 PostgreSQL 做约束手术; SQLite 等的 schema 由 model create_all 直接物化
(已含复合唯一约束), 本迁移在 SQLite 上 no-op (pytest 用 create_all, 不跑本迁移)。

Revision ID: e3f1a2b4c5d6
Revises: d5b82c9f3e41
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa

revision = "e3f1a2b4c5d6"
down_revision = "d5b82c9f3e41"
branch_labels = None
depends_on = None

_OLD_GLOBAL_UNIQUE = "probes_probe_number_key"  # PG 对 Column(unique=True) 的自动命名
_NEW_COMPOSITE = "uq_probes_chamber_probe_number"


def _unique_names(bind) -> set:
    return {uc["name"] for uc in sa.inspect(bind).get_unique_constraints("probes")}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite 等: schema 由 model create_all 物化 (已含复合唯一), 无需迁移。
        return

    # 1. drop 旧全局唯一 (若存在)
    if _OLD_GLOBAL_UNIQUE in _unique_names(bind):
        op.drop_constraint(_OLD_GLOBAL_UNIQUE, "probes", type_="unique")

    # 2. 回填: 每个 chamber 内按 (probe_number, id) 重排成连续 1..N。
    #    必须在 drop 全局唯一之后、create 复合唯一之前 —— 否则跨 chamber 重号会撞约束。
    op.execute(
        """
        UPDATE probes p
        SET probe_number = sub.rn
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY chamber_config_id
                       ORDER BY probe_number, id
                   ) AS rn
            FROM probes
        ) sub
        WHERE p.id = sub.id AND p.probe_number <> sub.rn
        """
    )

    # 3. create 复合唯一 (若无)
    if _NEW_COMPOSITE not in _unique_names(bind):
        op.create_unique_constraint(
            _NEW_COMPOSITE, "probes", ["chamber_config_id", "probe_number"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if _NEW_COMPOSITE in _unique_names(bind):
        op.drop_constraint(_NEW_COMPOSITE, "probes", type_="unique")
    # 注: **不**重建全局唯一 probes_probe_number_key —— probe_number 已按 chamber
    # 局部化, 跨 chamber 普遍存在重号, 重建全局唯一会立即违反约束。如确需回退到全局
    # 唯一, 须先手动把 probe_number 全局重排成唯一序列, 再加约束。
