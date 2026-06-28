"""ChannelAsset (信道资产多态化) 服务层 — CRUD + 多态 payload 校验 + 路径亲和性派生 (P2-16 S1)。

四源统一实体。判别键 source_type 决定 payload 形态 (判别联合体), service 层按 source_type
dispatch 校验 payload。allowed_targets 从 source_type **派生** (§3.1 亲和性, operator 不可填),
保证"来源 → 可落地路径"单一真值。source_type 是资产本质 (建后不可改); 改来源请建新资产。

设计见 docs/design/channel-asset-polymorphism-design_V0.1.md。canonical_name 确定性派生 (§3.2,
S2 填充, S1 接受 operator 可选传入 + 唯一校验)。平行 CustomCDLProfile / DUTProfile 服务层。
"""
from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.channel_asset import ChannelAsset
# 簇校验单一真值在 custom_cdl_profile_service (custom_static = CustomCDLProfile 退化, 复用避免 drift)
from app.services.custom_cdl_profile_service import (
    CustomCDLProfileError,
    _validate_cluster,
)

# 合法 source_type (判别键)
_SOURCE_TYPES = {"standard_3gpp", "custom_static", "rt_dynamic", "vendor_file"}

# 路径亲和性 (§3.1): 从 source_type 派生; gcm_native 限 artifact-backed (仅 vendor_file)。
# rt 判决指 GCM → ESCALATE (射线→GCM 逆向拟合未建模), 故 rt 不含 gcm_native。
_ALLOWED_TARGETS_BY_SOURCE = {
    "vendor_file": ["gcm_native"],
    "standard_3gpp": ["asc_baked"],
    "custom_static": ["asc_baked", "b2_parametric"],
    "rt_dynamic": ["asc_baked", "b2_parametric"],
}

# operator 可改字段 (update 用)。**不含** source_type / allowed_targets (派生/不可变) / created_by。
_MUTABLE_FIELDS = (
    "name", "description", "canonical_name", "derived_from",
    "center_frequency_hz", "bandwidth_mhz", "is_los", "k_factor_db",
    "ue_velocity_mps", "payload", "instrument_connection_id", "associated_file_path",
    "is_active",
)

# rt_dynamic 单条射线 (MPCInput) 必填几何 + 功率
_RAY_REQUIRED = ("delay_s", "power_linear", "aoa_deg", "aod_deg")


class ChannelAssetError(ValueError):
    """业务错误 (字段非法 / 重名 / payload 结构非法), caller (API) 映射 4xx。"""


class ChannelAssetNotFound(ChannelAssetError):
    """按 id 找不到。是 ChannelAssetError 子类, caller 可映射 404。"""


def _num_or_error(label: str, v: Any) -> Any:
    """payload 是 Dict[str, Any] (Pydantic 不校验内部) → 数值比较前先校验类型, 否则坏 JSON
    (如 "delay_s": "bad") 会让 < / <= 抛裸 TypeError 绕过 ChannelAssetError → 500。
    None 透传 (optional); bool 或非 int/float → ChannelAssetError (400)。返回 v。"""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ChannelAssetError(f"{label} 须是数值 (得 {type(v).__name__}: {v!r})")
    return v


# ---- 多态 payload 校验 (按 source_type dispatch) ----

def _validate_standard_payload(payload: dict) -> None:
    name = payload.get("cdl_model_name")
    if not isinstance(name, str) or not name.strip():
        raise ChannelAssetError("standard_3gpp payload.cdl_model_name 必填 (非空字符串)")


def _validate_custom_static_payload(payload: dict) -> None:
    """custom_static = CustomCDLProfile 退化: 恰 1 个静态快照, 簇复用 CustomCDLProfile 校验。"""
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list) or len(snapshots) != 1:
        raise ChannelAssetError(
            "custom_static payload.snapshots 须恰 1 个快照 (静态单快照)")
    snap = snapshots[0]
    clusters = snap.get("clusters") if isinstance(snap, dict) else None
    if not isinstance(clusters, list) or len(clusters) == 0:
        raise ChannelAssetError("custom_static payload.snapshots[0].clusters 须非空列表 (≥1 簇)")
    for i, c in enumerate(clusters):
        try:
            _validate_cluster(i, c)
        except CustomCDLProfileError as e:
            raise ChannelAssetError(str(e))
        except TypeError as e:
            # 簇数值字段坏类型 (payload 未经 Pydantic) → _validate_cluster 范围比较抛 TypeError, 转 400
            raise ChannelAssetError(f"clusters[{i}] 数值字段类型非法: {e}")


def _validate_ray(si: int, ri: int, r: Any) -> None:
    if not isinstance(r, dict):
        raise ChannelAssetError(f"snapshots[{si}].rays[{ri}] 须对象 (得 {type(r).__name__})")
    pfx = f"snapshots[{si}].rays[{ri}]"
    for f in _RAY_REQUIRED:
        if r.get(f) is None:
            raise ChannelAssetError(f"{pfx}.{f} 必填")
    # 数值字段先校验类型 (payload 是 Dict[str,Any], 防坏 JSON → TypeError → 500)
    for f in ("aoa_deg", "aod_deg"):  # required, 仅校验类型 (无范围约束)
        _num_or_error(f"{pfx}.{f}", r.get(f))
    d = _num_or_error(f"{pfx}.delay_s", r.get("delay_s"))  # required → 非 None 数值
    if d < 0:
        raise ChannelAssetError(f"{pfx}.delay_s 须 >= 0 (得 {d})")
    p = _num_or_error(f"{pfx}.power_linear", r.get("power_linear"))
    if p <= 0:
        raise ChannelAssetError(f"{pfx}.power_linear 须 > 0 (得 {p})")
    for f in ("zoa_deg", "zod_deg"):
        v = _num_or_error(f"{pfx}.{f}", r.get(f))
        if v is not None and not (0.0 <= v <= 180.0):
            raise ChannelAssetError(f"{pfx}.{f} 须在 [0,180] (得 {v})")


def _validate_rt_dynamic_payload(payload: dict) -> None:
    """rt_dynamic 存原始 MPDB 射线 (多快照, 非聚类后 CDL)。每快照 ≥1 条 MPCInput 原始射线。"""
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list) or len(snapshots) == 0:
        raise ChannelAssetError("rt_dynamic payload.snapshots 须非空列表 (≥1 快照)")
    for si, snap in enumerate(snapshots):
        if not isinstance(snap, dict):
            raise ChannelAssetError(f"rt_dynamic payload.snapshots[{si}] 须对象")
        rays = snap.get("rays")
        if not isinstance(rays, list) or len(rays) == 0:
            raise ChannelAssetError(f"rt_dynamic payload.snapshots[{si}].rays 须非空列表 (≥1 射线)")
        for ri, r in enumerate(rays):
            _validate_ray(si, ri, r)


def _validate_vendor_file_payload(payload: dict) -> None:
    scd = payload.get("scd_config")
    if not isinstance(scd, dict) or not scd:
        raise ChannelAssetError("vendor_file payload.scd_config 须非空对象 (SCD 规范配置)")


_PAYLOAD_VALIDATORS = {
    "standard_3gpp": _validate_standard_payload,
    "custom_static": _validate_custom_static_payload,
    "rt_dynamic": _validate_rt_dynamic_payload,
    "vendor_file": _validate_vendor_file_payload,
}


def _validate_payload(source_type: str, payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ChannelAssetError(f"payload 须对象 (得 {type(payload).__name__})")
    _PAYLOAD_VALIDATORS[source_type](payload)


def _validate_top_physical(fields: dict) -> None:
    for f in ("center_frequency_hz", "bandwidth_mhz"):
        v = _num_or_error(f, fields.get(f))
        if v is not None and v <= 0:
            raise ChannelAssetError(f"{f} 必须 > 0 (得 {v})")
    vel = fields.get("ue_velocity_mps")
    if vel is not None:
        if not isinstance(vel, list) or len(vel) != 3:
            raise ChannelAssetError(f"ue_velocity_mps 须 3 元素 [x,y,z] (得 {vel!r})")
        for j, x in enumerate(vel):
            _num_or_error(f"ue_velocity_mps[{j}]", x)


# ---- CRUD ----

def create_channel_asset(
    db: Session, *, name: str, source_type: str, payload: Any,
    created_by: Optional[str] = None, **fields,
) -> ChannelAsset:
    if not name or not name.strip():
        raise ChannelAssetError("name 必填")
    if source_type not in _SOURCE_TYPES:
        raise ChannelAssetError(
            f"source_type 非法: {source_type!r} (须 {sorted(_SOURCE_TYPES)})")
    if payload is None:
        raise ChannelAssetError("payload 必填")
    if db.query(ChannelAsset).filter(ChannelAsset.name == name).first() is not None:
        raise ChannelAssetError(f"ChannelAsset 名 {name!r} 已存在")
    canonical = fields.get("canonical_name")
    if canonical is not None and db.query(ChannelAsset).filter(
            ChannelAsset.canonical_name == canonical).first() is not None:
        raise ChannelAssetError(f"canonical_name {canonical!r} 已存在")
    _validate_payload(source_type, payload)
    _validate_top_physical(fields)
    asset = ChannelAsset(
        name=name,
        source_type=source_type,
        payload=payload,
        # allowed_targets 从 source_type 派生 (operator 不可填), 保证亲和性单一真值
        allowed_targets=list(_ALLOWED_TARGETS_BY_SOURCE[source_type]),
        created_by=created_by,
        **{k: v for k, v in fields.items() if k in _MUTABLE_FIELDS},
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def list_channel_assets(
    db: Session, *, source_type: Optional[str] = None, include_inactive: bool = False,
) -> List[ChannelAsset]:
    q = db.query(ChannelAsset)
    if source_type is not None:
        if source_type not in _SOURCE_TYPES:
            raise ChannelAssetError(f"source_type 非法: {source_type!r}")
        q = q.filter(ChannelAsset.source_type == source_type)
    if not include_inactive:
        q = q.filter(ChannelAsset.is_active.is_(True))
    return q.order_by(ChannelAsset.name).all()


def get_channel_asset(db: Session, asset_id: UUID) -> ChannelAsset:
    asset = db.get(ChannelAsset, asset_id)
    if asset is None:
        raise ChannelAssetNotFound(f"ChannelAsset {asset_id} 不存在")
    return asset


def update_channel_asset(db: Session, asset_id: UUID, **fields) -> ChannelAsset:
    asset = get_channel_asset(db, asset_id)
    # source_type 是判别键, 建后不可改 (改了 payload 形态 + allowed_targets 全变)
    new_src = fields.get("source_type")
    if new_src is not None and new_src != asset.source_type:
        raise ChannelAssetError("source_type 不可变更 (判别键; 改来源请建新资产)")
    new_name = fields.get("name")
    if new_name is not None:
        if not new_name.strip():
            raise ChannelAssetError("name 不能为空")
        if new_name != asset.name and db.query(ChannelAsset).filter(
                ChannelAsset.name == new_name).first() is not None:
            raise ChannelAssetError(f"ChannelAsset 名 {new_name!r} 已存在")
    new_canon = fields.get("canonical_name")
    if (new_canon is not None and new_canon != asset.canonical_name
            and db.query(ChannelAsset).filter(
                ChannelAsset.canonical_name == new_canon).first() is not None):
        raise ChannelAssetError(f"canonical_name {new_canon!r} 已存在")
    # payload 改了 → 用现有 source_type 重新 dispatch 校验 (source_type 不可改, 形态稳定)
    if "payload" in fields:
        _validate_payload(asset.source_type, fields["payload"])
    _validate_top_physical(fields)
    for k, v in fields.items():
        if k in _MUTABLE_FIELDS:
            setattr(asset, k, v)
    db.commit()
    db.refresh(asset)
    return asset


def delete_channel_asset(db: Session, asset_id: UUID, *, soft: bool = True) -> None:
    """默认软删 (is_active=False), 历史执行引用仍有效; soft=False 物理删。"""
    asset = get_channel_asset(db, asset_id)
    if soft:
        asset.is_active = False
    else:
        db.delete(asset)
    db.commit()
