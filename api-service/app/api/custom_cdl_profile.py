"""CustomCDLProfile (自定义 CDL 簇编辑) CRUD API (P2-15)。

operator 编辑自定义 CDL 簇级参数, 持久化可复用; 测试时选它 → input_mode=custom →
ChannelEgine 合成。簇字段映射 ChannelEgine CDLClusterSpec (cdl_schema.py)。

router prefix="/custom-cdl-profiles", main.py include 时加 /api/v1 → /api/v1/custom-cdl-profiles。
端点路径只写 prefix 之后部分 (feedback_fastapi_router_prefix_no_double)。
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.custom_cdl_profile_service import (
    CustomCDLProfileError,
    CustomCDLProfileNotFound,
    create_custom_cdl_profile,
    delete_custom_cdl_profile,
    get_custom_cdl_profile,
    list_custom_cdl_profiles,
    update_custom_cdl_profile,
)

router = APIRouter(prefix="/custom-cdl-profiles", tags=["Custom CDL Profile"])


class CDLClusterInput(BaseModel):
    """一个 CDL 簇 (映射 ChannelEgine CDLClusterSpec)。"""
    delay_s: float = Field(..., ge=0.0, description="簇延迟 s")
    power_linear: float = Field(..., gt=0.0, description="线性功率 (构建器规一化)")
    aoa_deg: float = Field(..., description="到达方位角 deg")
    aod_deg: float = Field(..., description="出发方位角 deg")
    zoa_deg: float = Field(90.0, description="到达天顶角 deg (default 水平面)")
    zod_deg: float = Field(90.0, description="出发天顶角 deg")
    as_aoa_deg: float = Field(0.0, ge=0.0, description="AoA 角度扩展 deg")
    as_aod_deg: float = Field(0.0, ge=0.0, description="AoD 角度扩展 deg")
    as_zoa_deg: float = Field(0.0, ge=0.0, description="ZoA 角度扩展 deg (也作探头权重高斯 el 宽)")
    as_zod_deg: float = Field(0.0, ge=0.0, description="ZoD 角度扩展 deg")
    xpr_db: Optional[float] = Field(None, description="交叉极化比 dB")
    initial_phases_rad: Optional[List[float]] = Field(
        None, description="[Φθθ, Φθφ, Φφθ, Φφφ] rad (4 元素)")
    num_rays: int = Field(20, gt=0, description="每簇子径数 (38.901 默认 20)")


class CustomCDLProfileBase(BaseModel):
    description: Optional[str] = None
    center_frequency_hz: Optional[float] = None
    pathloss_db: Optional[float] = None
    is_los: Optional[bool] = None
    k_factor_db: Optional[float] = None
    ue_velocity_mps: Optional[List[float]] = None


class CustomCDLProfileCreate(CustomCDLProfileBase):
    name: str
    clusters: List[CDLClusterInput] = Field(..., min_length=1)
    created_by: Optional[str] = None


class CustomCDLProfileUpdate(CustomCDLProfileBase):
    name: Optional[str] = None
    clusters: Optional[List[CDLClusterInput]] = None
    is_active: Optional[bool] = None


class CustomCDLProfileResponse(CustomCDLProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    clusters: List[CDLClusterInput]
    is_active: bool


@router.get("", response_model=List[CustomCDLProfileResponse])
def list_profiles(include_inactive: bool = False, db: Session = Depends(get_db)):
    return [
        CustomCDLProfileResponse.model_validate(p)
        for p in list_custom_cdl_profiles(db, include_inactive=include_inactive)
    ]


@router.post("", response_model=CustomCDLProfileResponse, status_code=201)
def create_profile(req: CustomCDLProfileCreate, db: Session = Depends(get_db)):
    # model_dump 递归把 clusters 转 List[dict] (存 JSONB)
    try:
        p = create_custom_cdl_profile(db, **req.model_dump())
    except CustomCDLProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CustomCDLProfileResponse.model_validate(p)


@router.get("/{profile_id}", response_model=CustomCDLProfileResponse)
def get_profile(profile_id: UUID, db: Session = Depends(get_db)):
    try:
        return CustomCDLProfileResponse.model_validate(get_custom_cdl_profile(db, profile_id))
    except CustomCDLProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{profile_id}", response_model=CustomCDLProfileResponse)
def update_profile(
    profile_id: UUID, req: CustomCDLProfileUpdate, db: Session = Depends(get_db),
):
    try:
        # exclude_unset: 只改 operator 显式设的字段 (PATCH 语义); clusters 递归转 List[dict]
        p = update_custom_cdl_profile(db, profile_id, **req.model_dump(exclude_unset=True))
    except CustomCDLProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CustomCDLProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CustomCDLProfileResponse.model_validate(p)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: UUID, hard: bool = False, db: Session = Depends(get_db)):
    try:
        delete_custom_cdl_profile(db, profile_id, soft=not hard)
    except CustomCDLProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
