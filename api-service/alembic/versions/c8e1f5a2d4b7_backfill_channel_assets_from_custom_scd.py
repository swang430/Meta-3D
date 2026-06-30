"""backfill channel_assets from custom_cdl_profiles + standard_channel_definitions (P2-16 S2)

Revision ID: c8e1f5a2d4b7
Revises: b7d2f4a9e1c3
Create Date: 2026-06-29

S2 激进收口: 把现有 CustomCDLProfile → ChannelAsset(custom_static), SCD →
ChannelAsset(vendor_file), **复用源 id** (旧 cdl_profile_id/scd_id 直接当 channel_asset_id,
零映射表)。幂等 (复用 id, 重跑跳已存在) + 跨方言 (sa.table 读 + bulk_insert 写, 不 import
model 锁历史 schema) + name 唯一冲突确定性去重。搬历史数据宽容 (不调命名校验; vendor
canonical 直接搬 standard_name —— SCD.standard_name 本就是 format_standard_channel_filename
输出, 跟 service 新建派生天然一致)。旧表保留 (backward-compat 双保险, S4 GUI 收口才 deprecate)。

注: pytest 用 create_all 不跑迁移 → 本迁移逻辑由专门的 alembic runner 测试覆盖 (R1)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.migration_helpers import table_exists

revision: str = 'c8e1f5a2d4b7'
down_revision: Union[str, Sequence[str], None] = 'b7d2f4a9e1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')

# 历史 schema 轻量表 (只列读/写要用的列; 不 import model)
_custom = sa.table(
    "custom_cdl_profiles",
    sa.column("id"), sa.column("name"), sa.column("description"),
    sa.column("center_frequency_hz"), sa.column("pathloss_db"),
    sa.column("is_los"), sa.column("k_factor_db"),
    sa.column("ue_velocity_mps", _JSON), sa.column("clusters", _JSON),
    sa.column("is_active"), sa.column("created_by"),
)
_scd = sa.table(
    "standard_channel_definitions",
    sa.column("id"), sa.column("band"), sa.column("arfcn"),
    sa.column("bandwidth_mhz"), sa.column("model"), sa.column("scenario"),
    sa.column("mimo"), sa.column("polarization"), sa.column("version"),
    sa.column("standard_name"), sa.column("instrument_connection_id"),
    sa.column("associated_file_path"), sa.column("description"),
)
_assets = sa.table(
    "channel_assets",
    sa.column("id"), sa.column("name"), sa.column("description"),
    sa.column("source_type"), sa.column("canonical_name"), sa.column("derived_from"),
    sa.column("allowed_targets", _JSON),
    sa.column("center_frequency_hz"), sa.column("bandwidth_mhz"),
    sa.column("is_los"), sa.column("k_factor_db"), sa.column("ue_velocity_mps", _JSON),
    sa.column("payload", _JSON),
    sa.column("instrument_connection_id"), sa.column("associated_file_path"),
    sa.column("is_active"), sa.column("created_by"),
)


def _dedup_name(base: str, taken: set) -> str:
    """name 唯一冲突 → 确定性后缀 (非随机, 重跑同结果)。不静默覆盖。"""
    if base not in taken:
        return base
    for cand in (f"{base} (migrated)", *(f"{base} ({i})" for i in range(2, 1000))):
        if cand not in taken:
            return cand
    raise RuntimeError(f"无法为 {base!r} 去重 name (已占用 1000 个候选)")


def upgrade() -> None:
    if not table_exists("channel_assets"):
        return  # S1 表必须先在
    bind = op.get_bind()
    existing_ids = {r[0] for r in bind.execute(sa.select(_assets.c.id))}
    taken_names = {r[0] for r in bind.execute(sa.select(_assets.c.name))}
    taken_canon = {
        r[0] for r in bind.execute(sa.select(_assets.c.canonical_name)) if r[0] is not None
    }

    rows = []
    # ---- custom_cdl_profiles → custom_static (复用 id) ----
    if table_exists("custom_cdl_profiles"):
        for p in bind.execute(sa.select(_custom)):
            if p.id in existing_ids:
                continue  # 幂等
            name = _dedup_name(p.name, taken_names)
            taken_names.add(name)
            rows.append({
                "id": p.id, "name": name, "description": p.description,
                "source_type": "custom_static",
                "canonical_name": None,  # 族 C: custom 无规范名 (§3.2)
                "derived_from": None,
                "allowed_targets": ["asc_baked", "b2_parametric"],
                "center_frequency_hz": p.center_frequency_hz, "bandwidth_mhz": None,
                "is_los": p.is_los, "k_factor_db": p.k_factor_db,
                "ue_velocity_mps": p.ue_velocity_mps,
                # pathloss_db: ChannelAsset 顶层无此字段, 搬进 payload (custom_static 特有)
                "payload": {"snapshots": [{"clusters": p.clusters or []}],
                            "pathloss_db": p.pathloss_db},
                "instrument_connection_id": None, "associated_file_path": None,
                "is_active": p.is_active if p.is_active is not None else True,
                "created_by": p.created_by,
            })
    # ---- standard_channel_definitions → vendor_file (复用 id) ----
    if table_exists("standard_channel_definitions"):
        for s in bind.execute(sa.select(_scd)):
            if s.id in existing_ids:
                continue
            name = _dedup_name(s.standard_name, taken_names)
            taken_names.add(name)
            canon = s.standard_name if s.standard_name not in taken_canon else None
            if canon:
                taken_canon.add(canon)
            rows.append({
                "id": s.id, "name": name, "description": s.description,
                "source_type": "vendor_file",
                "canonical_name": canon,  # 族 A: SCD standard_name 即 MF_ canonical
                "derived_from": None,
                "allowed_targets": ["gcm_native"],
                "center_frequency_hz": None,  # SCD 用 ARFCN (在 scd_config), 不存 Hz
                "bandwidth_mhz": float(s.bandwidth_mhz) if s.bandwidth_mhz is not None else None,
                "is_los": None, "k_factor_db": None, "ue_velocity_mps": None,
                "payload": {"scd_config": {
                    "band": s.band, "arfcn": s.arfcn, "bandwidth_mhz": s.bandwidth_mhz,
                    "model": s.model, "scenario": s.scenario, "mimo": s.mimo,
                    "polarization": s.polarization, "version": s.version,
                }},
                "instrument_connection_id": s.instrument_connection_id,
                "associated_file_path": s.associated_file_path,
                "is_active": True, "created_by": None,
            })
    if rows:
        op.bulk_insert(_assets, rows)


def downgrade() -> None:
    # 精确反演: 只删 id 同时存在于旧表的资产 (S2 后 operator 新建的 ChannelAsset 不误删)
    if not table_exists("channel_assets"):
        return
    bind = op.get_bind()
    old_ids = set()
    if table_exists("custom_cdl_profiles"):
        old_ids |= {r[0] for r in bind.execute(sa.select(_custom.c.id))}
    if table_exists("standard_channel_definitions"):
        old_ids |= {r[0] for r in bind.execute(sa.select(_scd.c.id))}
    if old_ids:
        bind.execute(_assets.delete().where(_assets.c.id.in_(old_ids)))
