"""P2-16 S2: ChannelAsset 前置解析层 — channel_asset_id → engine_mode + 现有信道字段。

**方案 A 最小侵入**: 只在 `config.channel_asset_id` 显式给时介入; 旧 cdl_profile_id/scd_id
走现状 (一行不改下游 engine dispatch / strategy)。`source_type → engine_mode` 是**静态查表**
(S2: 一对一映射, 非智能判决 —— §6 判决路由 / ACP 装配 / F4/F5 接线全是 S3)。

解析结果翻译成现有 config 字段 (cdl_model_name / scd_id) + cdl_model_data clusters, 让
measure 下游 if/elif engine dispatch 和各 strategy **原封不动**跑。vendor_file 靠"复用 id"
(asset.id == 旧 scd_id, 旧 SCD 表保留) 透传 scd_id 走老 resolve_emulation_for_measure。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.channel_asset_service import (
    ChannelAssetNotFound,
    get_channel_asset,
)
from app.services.channel_generation.base_generator import EngineMode

# source_type → engine_mode 静态查表 (一对一; 非 §6 判决, 那是 S3)
_SOURCE_TO_ENGINE = {
    "standard_3gpp": EngineMode.ASC_SYNTHESIS.value,   # → mimo_first_asc
    "custom_static": EngineMode.ASC_SYNTHESIS.value,   # → mimo_first_asc
    "vendor_file": EngineMode.GCM_NATIVE.value,        # → keysight_gcm
    "rt_dynamic": EngineMode.B2_PARAMETRIC_TDL.value,  # → b2 (现恒 fail-loud=现场半)
}


@dataclass(frozen=True)
class ResolvedChannelAsset:
    """解析结果: engine_mode 覆盖 + 翻译到现有 config/cdl_model_data 字段。"""
    engine_mode: str
    asset: Any
    cdl_model_name: Optional[str] = None      # standard_3gpp → config.cdl_model_name
    emulation_file: Optional[str] = None      # vendor_file → config.emulation_file (不依赖 SCD twin)
    clusters_payload: Optional[List[dict]] = None  # custom_static → cdl_model_data["clusters"]


class ChannelAssetResolveError(ValueError):
    """解析失败 (资产不存在 / source_type 未知); caller 映射 FAILED。"""


def resolve_channel_asset(db: Session, config: Any) -> Optional[ResolvedChannelAsset]:
    """方案 A: 仅 config.channel_asset_id 显式给时解析; 否则 None (走旧字段路, 下游不变)。"""
    aid = getattr(config, "channel_asset_id", None)
    if not aid:
        return None
    try:
        asset = get_channel_asset(db, UUID(str(aid)))
    except (ChannelAssetNotFound, ValueError) as e:
        raise ChannelAssetResolveError(f"channel_asset_id={aid} 无效/不存在: {e}")

    st = asset.source_type
    if st not in _SOURCE_TO_ENGINE:
        raise ChannelAssetResolveError(f"未知 source_type: {st!r}")
    engine = _SOURCE_TO_ENGINE[st]

    if st == "custom_static":
        snapshots = (asset.payload or {}).get("snapshots") or [{}]
        clusters = snapshots[0].get("clusters") if isinstance(snapshots[0], dict) else None
        return ResolvedChannelAsset(engine_mode=engine, asset=asset, clusters_payload=clusters)
    if st == "standard_3gpp":
        return ResolvedChannelAsset(
            engine_mode=engine, asset=asset,
            cdl_model_name=(asset.payload or {}).get("cdl_model_name"))
    if st == "vendor_file":
        # vendor_file 不依赖 SCD twin (Codex #174 P2: 新建的 vendor_file 经 ChannelAsset API
        # 没有同 id 的 SCD 行, 不能透传 scd_id 走查 SCD 表的老路): 直接从 ChannelAsset 提供
        # .smu (associated_file_path)。declared_only (None) → GCM 分支 emulation_file_gate
        # strict fail-loud (没指定 .smu 不能真跑 GCM), 与现状 (裸 emulation_file 缺失) 一致。
        return ResolvedChannelAsset(
            engine_mode=engine, asset=asset, emulation_file=asset.associated_file_path)
    # rt_dynamic: S2 只路由到 B2 (现恒 fail-loud=现场半), 不装配 payload→ACP (S3/S5)
    return ResolvedChannelAsset(engine_mode=engine, asset=asset)
