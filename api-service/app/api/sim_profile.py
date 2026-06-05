"""SIMProfile (SIM/eSIM 身份 + 鉴权声明) CRUD API (P2-13 阶段 1)。

operator 规划期建/管测试卡池 (IMSI/PLMN/Ki/OPc/算法/卡类型)。后续阶段接 SIM↔UXM 一致性
precheck 校验 + attach 后实测 IMSI 核对 + (档 A) 自动 provision UXM HSS。

注: router prefix="/sim-profiles", main.py include 时加 /api/v1 → /api/v1/sim-profiles。
端点路径只写 prefix 之后部分 (feedback_fastapi_router_prefix_no_double)。

⚠️ Ki/OPc 脱敏: 响应**不返回原值**, 只给 `ki_masked` (后 4 位) + `ki_set` (是否已设) —— 凭据
不回显 (feedback: tolerant store ≠ leak)。编辑时不传 ki = 保持原值 (exclude_unset), 传新值才改。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.sim_profile import SIMProfile
from app.services.sim_profile_service import (
    SIMProfileError,
    SIMProfileNotFound,
    create_sim_profile,
    delete_sim_profile,
    get_sim_profile,
    list_sim_profiles,
    update_sim_profile,
)

router = APIRouter(prefix="/sim-profiles", tags=["SIM Profile"])


def _mask(secret: Optional[str]) -> Optional[str]:
    """凭据脱敏: 只显后 4 位。None/空 → None。"""
    if not secret:
        return None
    s = str(secret)
    return "…" + s[-4:] if len(s) > 4 else "****"


class SIMProfileBase(BaseModel):
    """非密字段 (create/update 输入 + response 共享)。"""
    description: Optional[str] = None
    imsi: Optional[str] = None
    iccid: Optional[str] = None
    mcc: Optional[str] = None
    mnc: Optional[str] = None
    auth_algorithm: Optional[str] = None
    card_kind: Optional[str] = None
    sim_form: Optional[str] = None
    eid: Optional[str] = None
    esim_profile_id: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class SIMProfileCreate(SIMProfileBase):
    name: str
    # 凭据 (输入); commercial 卡不可带 ki (service 校验)
    ki: Optional[str] = None
    opc: Optional[str] = None
    created_by: Optional[str] = None


class SIMProfileUpdate(SIMProfileBase):
    name: Optional[str] = None
    ki: Optional[str] = None
    opc: Optional[str] = None
    is_active: Optional[bool] = None


class SIMProfileResponse(SIMProfileBase):
    """响应: 不含原始 ki/opc, 只给脱敏后 4 位 + 是否已设。"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool
    ki_masked: Optional[str] = None
    opc_masked: Optional[str] = None
    ki_set: bool = False
    opc_set: bool = False

    @classmethod
    def from_model(cls, p: SIMProfile) -> "SIMProfileResponse":
        return cls(
            id=p.id, name=p.name, is_active=p.is_active,
            description=p.description, imsi=p.imsi, iccid=p.iccid,
            mcc=p.mcc, mnc=p.mnc, auth_algorithm=p.auth_algorithm,
            card_kind=p.card_kind, sim_form=p.sim_form,
            eid=p.eid, esim_profile_id=p.esim_profile_id,
            extra_metadata=p.extra_metadata,
            ki_masked=_mask(p.ki), opc_masked=_mask(p.opc),
            ki_set=bool(p.ki), opc_set=bool(p.opc),
        )


@router.get("", response_model=List[SIMProfileResponse])
def list_profiles(include_inactive: bool = False, db: Session = Depends(get_db)):
    return [
        SIMProfileResponse.from_model(p)
        for p in list_sim_profiles(db, include_inactive=include_inactive)
    ]


@router.post("", response_model=SIMProfileResponse, status_code=201)
def create_profile(req: SIMProfileCreate, db: Session = Depends(get_db)):
    try:
        p = create_sim_profile(db, **req.model_dump())
    except SIMProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SIMProfileResponse.from_model(p)


@router.get("/{profile_id}", response_model=SIMProfileResponse)
def get_profile(profile_id: UUID, db: Session = Depends(get_db)):
    try:
        return SIMProfileResponse.from_model(get_sim_profile(db, profile_id))
    except SIMProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{profile_id}", response_model=SIMProfileResponse)
def update_profile(profile_id: UUID, req: SIMProfileUpdate, db: Session = Depends(get_db)):
    try:
        # exclude_unset: 只改 operator 显式设的字段 (PATCH 语义); 不传 ki = 保持原值 (凭据
        # 不必每次回传)。显式 None = 清空。
        p = update_sim_profile(db, profile_id, **req.model_dump(exclude_unset=True))
    except SIMProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SIMProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SIMProfileResponse.from_model(p)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: UUID, hard: bool = False, db: Session = Depends(get_db)):
    try:
        delete_sim_profile(db, profile_id, soft=not hard)
    except SIMProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
