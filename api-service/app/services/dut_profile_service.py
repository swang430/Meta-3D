"""DUTProfile (DUT 自声明能力) 服务层 — CRUD + 轻量字段校验。

平行 LabProfile: operator 规划期建/管 DUT 能力档案。校验请求 vs 声明 (规划期提前 fail)
+ attach 后跟 UXM 协商交叉核对 在后续 PR (本 PR 只做实体 + CRUD)。
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dut_profile import DUTProfile

# 调制集 (跟 cell_config_consistency._MODULATION_BITS 对齐, 校验声明值)
_MODULATIONS = {"QPSK", "16QAM", "64QAM", "256QAM", "1024QAM"}
_DUPLEX = {"TDD", "FDD", "BOTH"}

# operator 可写字段 (id / 时间戳 / created_by 不在内)
_MUTABLE_FIELDS = (
    "name", "description", "manufacturer", "model_name",
    "max_dl_layers", "max_ul_layers", "max_modulation_dl", "max_modulation_ul",
    "ue_category", "duplex_mode", "supported_bands", "extra_metadata", "is_active",
)


class DUTProfileError(ValueError):
    """DUTProfile 业务错误 (字段非法 / 重名), caller (API) 映射 4xx。"""


class DUTProfileNotFound(DUTProfileError):
    """按 id 找不到。是 DUTProfileError 子类 (既有 except 仍捕获), caller 可映射 404。"""


def _validate(fields: dict) -> None:
    """轻量校验。None / 缺省 = 该项未声明, 跳过 (不是所有 DUT 都填全)。"""
    for f in ("max_dl_layers", "max_ul_layers"):
        v = fields.get(f)
        if v is not None and v <= 0:
            raise DUTProfileError(f"{f} 必须 > 0 (得 {v})")
    for f in ("max_modulation_dl", "max_modulation_ul"):
        v = fields.get(f)
        if v is not None and str(v).upper() not in _MODULATIONS:
            raise DUTProfileError(f"{f} 非法调制 {v!r} (合法: {sorted(_MODULATIONS)})")
    dup = fields.get("duplex_mode")
    if dup is not None and str(dup).upper() not in _DUPLEX:
        raise DUTProfileError(f"duplex_mode 非法 {dup!r} (合法: TDD/FDD/both)")
    bands = fields.get("supported_bands")
    if bands is not None and not isinstance(bands, list):
        raise DUTProfileError(f"supported_bands 必须是列表 (得 {type(bands).__name__})")


def create_dut_profile(
    db: Session, *, name: str, created_by: Optional[str] = None, **fields,
) -> DUTProfile:
    if not name or not name.strip():
        raise DUTProfileError("name 必填")
    if db.query(DUTProfile).filter(DUTProfile.name == name).first() is not None:
        raise DUTProfileError(f"DUTProfile 名 {name!r} 已存在")
    _validate(fields)
    profile = DUTProfile(
        name=name, created_by=created_by,
        **{k: v for k, v in fields.items() if k in _MUTABLE_FIELDS},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def list_dut_profiles(db: Session, *, include_inactive: bool = False) -> List[DUTProfile]:
    q = db.query(DUTProfile)
    if not include_inactive:
        q = q.filter(DUTProfile.is_active.is_(True))
    return q.order_by(DUTProfile.name).all()


def get_dut_profile(db: Session, profile_id: UUID) -> DUTProfile:
    profile = db.get(DUTProfile, profile_id)
    if profile is None:
        raise DUTProfileNotFound(f"DUTProfile {profile_id} 不存在")
    return profile


def update_dut_profile(db: Session, profile_id: UUID, **fields) -> DUTProfile:
    profile = get_dut_profile(db, profile_id)
    new_name = fields.get("name")
    if new_name is not None and new_name != profile.name:
        if db.query(DUTProfile).filter(DUTProfile.name == new_name).first() is not None:
            raise DUTProfileError(f"DUTProfile 名 {new_name!r} 已存在")
    _validate(fields)
    for k, v in fields.items():
        if k in _MUTABLE_FIELDS:
            setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return profile


def delete_dut_profile(db: Session, profile_id: UUID, *, soft: bool = True) -> None:
    """默认软删 (is_active=False), 历史执行引用仍有效; soft=False 物理删。"""
    profile = get_dut_profile(db, profile_id)
    if soft:
        profile.is_active = False
    else:
        db.delete(profile)
    db.commit()
