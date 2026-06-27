"""CustomCDLProfile (自定义 CDL 簇编辑) 服务层 — CRUD + 簇校验 (P2-15)。

operator 编辑自定义 CDL 的簇级参数, 持久化可复用。簇映射 ChannelEgine CDLClusterSpec
(cdl_schema.py)。建/改时 fail-loud 校验簇结构 (非空 / delay>=0 / power>0 / as>=0 /
天顶角 [0,180] / 相位 len 4 / num_rays>0)。平行 DUTProfile/SIMProfile 服务层。
"""
from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.custom_cdl_profile import CustomCDLProfile

# 每簇必填几何 + 功率 (映射 CDLClusterSpec 必填项)
_CLUSTER_REQUIRED = ("delay_s", "power_linear", "aoa_deg", "aod_deg")
# 每簇 >= 0 约束字段
_CLUSTER_NONNEG = ("delay_s", "as_aoa_deg", "as_aod_deg", "as_zoa_deg", "as_zod_deg")

# operator 可写字段 (id / 时间戳 / created_by 不在内)
_MUTABLE_FIELDS = (
    "name", "description", "center_frequency_hz", "pathloss_db", "is_los",
    "k_factor_db", "ue_velocity_mps", "clusters", "is_active",
)


class CustomCDLProfileError(ValueError):
    """业务错误 (字段非法 / 重名 / 簇结构非法), caller (API) 映射 4xx。"""


class CustomCDLProfileNotFound(CustomCDLProfileError):
    """按 id 找不到。是 CustomCDLProfileError 子类, caller 可映射 404。"""


def _validate_cluster(idx: int, c: Any) -> None:
    """单簇结构校验 (映射 CDLClusterSpec 约束)。"""
    if not isinstance(c, dict):
        raise CustomCDLProfileError(f"clusters[{idx}] 必须是对象 (得 {type(c).__name__})")
    for f in _CLUSTER_REQUIRED:
        if c.get(f) is None:
            raise CustomCDLProfileError(f"clusters[{idx}].{f} 必填")
    p = c.get("power_linear")
    if p is not None and p <= 0:
        raise CustomCDLProfileError(f"clusters[{idx}].power_linear 必须 > 0 (得 {p})")
    for f in _CLUSTER_NONNEG:
        v = c.get(f)
        if v is not None and v < 0:
            raise CustomCDLProfileError(f"clusters[{idx}].{f} 必须 >= 0 (得 {v})")
    for f in ("zoa_deg", "zod_deg"):
        v = c.get(f)
        if v is not None and not (0.0 <= v <= 180.0):
            raise CustomCDLProfileError(f"clusters[{idx}].{f} 须在 [0,180] (得 {v})")
    ph = c.get("initial_phases_rad")
    if ph is not None and (not isinstance(ph, list) or len(ph) != 4):
        raise CustomCDLProfileError(
            f"clusters[{idx}].initial_phases_rad 须 4 元素 [θθ,θφ,φθ,φφ] (得 {ph!r})")
    nr = c.get("num_rays")
    if nr is not None and nr <= 0:
        raise CustomCDLProfileError(f"clusters[{idx}].num_rays 必须 > 0 (得 {nr})")


def _validate(fields: dict) -> None:
    """簇结构 + 顶层物理校验。clusters 提供时必非空; 顶层物理 None = 未定 (测试时绑)。"""
    if "clusters" in fields:
        clusters = fields.get("clusters")
        if not isinstance(clusters, list) or len(clusters) == 0:
            raise CustomCDLProfileError("clusters 必须是非空列表 (至少 1 簇)")
        for i, c in enumerate(clusters):
            _validate_cluster(i, c)
    fc = fields.get("center_frequency_hz")
    if fc is not None and fc <= 0:
        raise CustomCDLProfileError(f"center_frequency_hz 必须 > 0 (得 {fc})")
    vel = fields.get("ue_velocity_mps")
    if vel is not None and (not isinstance(vel, list) or len(vel) != 3):
        raise CustomCDLProfileError(f"ue_velocity_mps 须 3 元素 [x,y,z] (得 {vel!r})")


def create_custom_cdl_profile(
    db: Session, *, name: str, created_by: Optional[str] = None, **fields,
) -> CustomCDLProfile:
    if not name or not name.strip():
        raise CustomCDLProfileError("name 必填")
    if db.query(CustomCDLProfile).filter(CustomCDLProfile.name == name).first() is not None:
        raise CustomCDLProfileError(f"CustomCDLProfile 名 {name!r} 已存在")
    # create 必带 clusters (确保走簇校验, 不建空 profile)
    if fields.get("clusters") is None:
        raise CustomCDLProfileError("clusters 必填 (至少 1 簇)")
    _validate(fields)
    profile = CustomCDLProfile(
        name=name, created_by=created_by,
        **{k: v for k, v in fields.items() if k in _MUTABLE_FIELDS},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def list_custom_cdl_profiles(
    db: Session, *, include_inactive: bool = False,
) -> List[CustomCDLProfile]:
    q = db.query(CustomCDLProfile)
    if not include_inactive:
        q = q.filter(CustomCDLProfile.is_active.is_(True))
    return q.order_by(CustomCDLProfile.name).all()


def get_custom_cdl_profile(db: Session, profile_id: UUID) -> CustomCDLProfile:
    profile = db.get(CustomCDLProfile, profile_id)
    if profile is None:
        raise CustomCDLProfileNotFound(f"CustomCDLProfile {profile_id} 不存在")
    return profile


def update_custom_cdl_profile(db: Session, profile_id: UUID, **fields) -> CustomCDLProfile:
    profile = get_custom_cdl_profile(db, profile_id)
    new_name = fields.get("name")
    if new_name is not None:
        if not new_name.strip():
            raise CustomCDLProfileError("name 不能为空")
        if new_name != profile.name and (
            db.query(CustomCDLProfile).filter(CustomCDLProfile.name == new_name).first()
            is not None
        ):
            raise CustomCDLProfileError(f"CustomCDLProfile 名 {new_name!r} 已存在")
    _validate(fields)
    for k, v in fields.items():
        if k in _MUTABLE_FIELDS:
            setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return profile


def delete_custom_cdl_profile(db: Session, profile_id: UUID, *, soft: bool = True) -> None:
    """默认软删 (is_active=False), 历史执行引用仍有效; soft=False 物理删。"""
    profile = get_custom_cdl_profile(db, profile_id)
    if soft:
        profile.is_active = False
    else:
        db.delete(profile)
    db.commit()
