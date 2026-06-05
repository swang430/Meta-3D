"""SIMProfile (SIM/eSIM 身份 + 鉴权声明) 服务层 — CRUD + 字段校验 (P2-13 阶段 1)。

平行 dut_profile_service: operator 规划期建/管测试卡池。SIM↔UXM 一致性校验 + attach 后
实测 IMSI 核对在后续阶段 (本阶段只做实体 + CRUD)。

校验要点:
- IMSI 数字 14-15 位; MCC 3 位 / MNC 2-3 位; 若 IMSI+MCC+MNC 都有, IMSI 必须以 MCC+MNC 起头。
- Ki/OPc 32 hex; auth_algorithm ∈ {MILENAGE,TUAK,XOR}; card_kind/sim_form 枚举。
- card_kind=commercial **不允许带 Ki** (商用卡 Ki 不可得; 标"不可鉴权用测试卡")。
"""
from __future__ import annotations

import re
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.sim_profile import SIMProfile

_AUTH_ALGORITHMS = {"MILENAGE", "TUAK", "XOR"}
_CARD_KINDS = {"test_sim", "operator_test", "commercial"}
_SIM_FORMS = {"usim", "esim"}

_HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_DIGITS_RE = re.compile(r"^\d+$")

# operator 可写字段 (id / 时间戳 / created_by 不在内)
_MUTABLE_FIELDS = (
    "name", "description", "imsi", "iccid", "mcc", "mnc",
    "ki", "opc", "auth_algorithm", "card_kind", "sim_form",
    "eid", "esim_profile_id", "extra_metadata", "is_active",
)


class SIMProfileError(ValueError):
    """SIMProfile 业务错误 (字段非法 / 重名), caller (API) 映射 4xx。"""


class SIMProfileNotFound(SIMProfileError):
    """按 id 找不到。是 SIMProfileError 子类, caller 可映射 404。"""


def _digits(v) -> str:
    return str(v).strip()


def _validate(fields: dict) -> None:
    """轻量校验。None / 缺省 = 该项未声明, 跳过 (不是所有卡都填全)。"""
    imsi = fields.get("imsi")
    if imsi is not None:
        s = _digits(imsi)
        if not _DIGITS_RE.match(s) or not (14 <= len(s) <= 15):
            raise SIMProfileError(f"imsi 必须是 14-15 位数字 (得 {imsi!r})")
    for f, lo, hi in (("mcc", 3, 3), ("mnc", 2, 3)):
        v = fields.get(f)
        if v is not None:
            s = _digits(v)
            if not _DIGITS_RE.match(s) or not (lo <= len(s) <= hi):
                raise SIMProfileError(f"{f} 必须是 {lo}-{hi} 位数字 (得 {v!r})")
    # MCC/MNC 跟 IMSI 前缀一致性 (三者都有时)
    mcc, mnc = fields.get("mcc"), fields.get("mnc")
    if imsi is not None and mcc is not None and mnc is not None:
        prefix = _digits(mcc) + _digits(mnc)
        if not _digits(imsi).startswith(prefix):
            raise SIMProfileError(
                f"imsi {imsi!r} 前缀跟 MCC+MNC ({prefix}) 不一致 —— 同一张卡的 PLMN 应一致"
            )
    for f in ("ki", "opc"):
        v = fields.get(f)
        if v is not None and v != "" and not _HEX32_RE.match(str(v).strip()):
            # ⚠️ Codex P1 (#142): 不回显凭据原值 —— 错误 detail 会进 GUI 通知 + 前端日志,
            # echo 输错的 Ki/OPc 会泄漏 (可能是真值的笔误)。只报长度 (非密) 辅助排查。
            raise SIMProfileError(
                f"{f} 格式非法: 必须是 32 位十六进制 (128-bit, 32 字符); "
                f"收到 {len(str(v).strip())} 字符 (凭据值已隐去)"
            )
    alg = fields.get("auth_algorithm")
    if alg is not None and str(alg).upper() not in _AUTH_ALGORITHMS:
        raise SIMProfileError(
            f"auth_algorithm 非法 {alg!r} (合法: {sorted(_AUTH_ALGORITHMS)}; 2G COMP128 不支持)"
        )
    ck = fields.get("card_kind")
    if ck is not None and ck not in _CARD_KINDS:
        raise SIMProfileError(f"card_kind 非法 {ck!r} (合法: {sorted(_CARD_KINDS)})")
    sf = fields.get("sim_form")
    if sf is not None and sf not in _SIM_FORMS:
        raise SIMProfileError(f"sim_form 非法 {sf!r} (合法: {sorted(_SIM_FORMS)})")
    # 商用卡不存 Ki (Ki 运营商保密不可得)
    if ck == "commercial" and fields.get("ki"):
        raise SIMProfileError(
            "card_kind=commercial 不可带 Ki —— 商用卡 Ki 运营商保密不可得, "
            "真鉴权测试请用可编程测试卡 (test_sim) 或运营商测试卡 (operator_test)"
        )


def create_sim_profile(
    db: Session, *, name: str, created_by: Optional[str] = None, **fields,
) -> SIMProfile:
    if not name or not name.strip():
        raise SIMProfileError("name 必填")
    if db.query(SIMProfile).filter(SIMProfile.name == name).first() is not None:
        raise SIMProfileError(f"SIMProfile 名 {name!r} 已存在")
    _validate(fields)
    profile = SIMProfile(
        name=name, created_by=created_by,
        **{k: v for k, v in fields.items() if k in _MUTABLE_FIELDS},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def list_sim_profiles(db: Session, *, include_inactive: bool = False) -> List[SIMProfile]:
    q = db.query(SIMProfile)
    if not include_inactive:
        q = q.filter(SIMProfile.is_active.is_(True))
    return q.order_by(SIMProfile.name).all()


def get_sim_profile(db: Session, profile_id: UUID) -> SIMProfile:
    profile = db.get(SIMProfile, profile_id)
    if profile is None:
        raise SIMProfileNotFound(f"SIMProfile {profile_id} 不存在")
    return profile


def update_sim_profile(db: Session, profile_id: UUID, **fields) -> SIMProfile:
    profile = get_sim_profile(db, profile_id)
    new_name = fields.get("name")
    if new_name is not None:
        if not new_name.strip():
            raise SIMProfileError("name 不能为空")
        if new_name != profile.name and (
            db.query(SIMProfile).filter(SIMProfile.name == new_name).first() is not None
        ):
            raise SIMProfileError(f"SIMProfile 名 {new_name!r} 已存在")
    # 校验**合并后**状态 (现有值 + 本次 delta), 不只 delta —— PATCH 半量提交不能绕过跨字段
    # 不变量 (Codex P2 #140: 已有 ki 的卡只提交 card_kind=commercial / 只改 mcc 让 IMSI 前缀
    # 不一致, 都因 _validate 只看 delta 漏过)。同 feedback_runtime_gate_not_frozen_snapshot
    # 母题: 校验对最终生效状态, 不是孤立增量。
    merged = {f: getattr(profile, f) for f in _MUTABLE_FIELDS}
    merged.update({k: v for k, v in fields.items() if k in _MUTABLE_FIELDS})
    _validate(merged)
    for k, v in fields.items():
        if k in _MUTABLE_FIELDS:
            setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return profile


def delete_sim_profile(db: Session, profile_id: UUID, *, soft: bool = True) -> None:
    profile = get_sim_profile(db, profile_id)
    if soft:
        profile.is_active = False
        db.commit()
    else:
        db.delete(profile)
        db.commit()
