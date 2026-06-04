"""DUTProfile (DUT 自声明能力) CRUD API。

operator 规划期建/管 DUT 能力档案 (max layers/调制/频段/UE category/双工)。后续 PR 接
precheck 早期校验 (TestCase 请求 vs 声明, attach 前提前 fail) + attach 后跟 UXM 协商交叉核对。

注: router prefix="/dut-profiles", main.py include 时加 /api/v1 → /api/v1/dut-profiles。
端点路径只写 prefix 之后部分 (feedback_fastapi_router_prefix_no_double)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.dut_profile import DUTProfile
from app.services.dut_profile_service import (
    DUTProfileError,
    DUTProfileNotFound,
    create_dut_profile,
    delete_dut_profile,
    get_dut_profile,
    list_dut_profiles,
    update_dut_profile,
)

router = APIRouter(prefix="/dut-profiles", tags=["DUT Profile"])


class DUTProfileBase(BaseModel):
    description: Optional[str] = None
    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    max_dl_layers: Optional[int] = None
    max_ul_layers: Optional[int] = None
    max_modulation_dl: Optional[str] = None
    max_modulation_ul: Optional[str] = None
    ue_category: Optional[str] = None
    duplex_mode: Optional[str] = None
    supported_bands: Optional[List[str]] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class DUTProfileCreate(DUTProfileBase):
    name: str
    created_by: Optional[str] = None


class DUTProfileUpdate(DUTProfileBase):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class DUTProfileResponse(DUTProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool


@router.get("", response_model=List[DUTProfileResponse])
def list_profiles(include_inactive: bool = False, db: Session = Depends(get_db)):
    return [
        DUTProfileResponse.model_validate(p)
        for p in list_dut_profiles(db, include_inactive=include_inactive)
    ]


@router.post("", response_model=DUTProfileResponse, status_code=201)
def create_profile(req: DUTProfileCreate, db: Session = Depends(get_db)):
    try:
        p = create_dut_profile(db, **req.model_dump())
    except DUTProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DUTProfileResponse.model_validate(p)


@router.get("/{profile_id}", response_model=DUTProfileResponse)
def get_profile(profile_id: UUID, db: Session = Depends(get_db)):
    try:
        return DUTProfileResponse.model_validate(get_dut_profile(db, profile_id))
    except DUTProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{profile_id}", response_model=DUTProfileResponse)
def update_profile(profile_id: UUID, req: DUTProfileUpdate, db: Session = Depends(get_db)):
    try:
        # exclude_unset: 只改 operator 显式设的字段 (PATCH 语义); 显式 None = 清空该声明
        p = update_dut_profile(db, profile_id, **req.model_dump(exclude_unset=True))
    except DUTProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DUTProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DUTProfileResponse.model_validate(p)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: UUID, hard: bool = False, db: Session = Depends(get_db)):
    try:
        delete_dut_profile(db, profile_id, soft=not hard)
    except DUTProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
