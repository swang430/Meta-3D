"""ChannelAsset (信道资产多态化) CRUD API (P2-16 S1)。

四源 (GCM/B-1/B-2/RT) 统一实体。判别键 source_type 决定 payload 形态; payload 用 dict
(多态), service 层按 source_type dispatch 校验。allowed_targets 派生只读 (operator 不填)。
source_type 建后不可改 (update 不暴露)。

router prefix="/channel-assets", main.py include 时加 /api/v1 → /api/v1/channel-assets。
端点路径只写 prefix 之后部分 (feedback_fastapi_router_prefix_no_double)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.channel_asset_service import (
    ChannelAssetError,
    ChannelAssetNotFound,
    create_channel_asset,
    delete_channel_asset,
    get_channel_asset,
    list_channel_assets,
    update_channel_asset,
)

router = APIRouter(prefix="/channel-assets", tags=["Channel Asset"])

SourceType = Literal["standard_3gpp", "custom_static", "rt_dynamic", "vendor_file"]


class ChannelAssetBase(BaseModel):
    description: Optional[str] = None
    canonical_name: Optional[str] = None
    derived_from: Optional[str] = None
    center_frequency_hz: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    is_los: Optional[bool] = None
    k_factor_db: Optional[float] = None
    ue_velocity_mps: Optional[List[float]] = None
    instrument_connection_id: Optional[UUID] = None
    associated_file_path: Optional[str] = None


class ChannelAssetCreate(ChannelAssetBase):
    name: str
    source_type: SourceType
    payload: Dict[str, Any] = Field(
        ..., description="多态 payload, 按 source_type (见设计 §3 / 模型 docstring)")
    created_by: Optional[str] = None


class ChannelAssetUpdate(ChannelAssetBase):
    name: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    # source_type / allowed_targets 不可改 (判别键 / 派生), 不暴露


class ChannelAssetResponse(ChannelAssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    source_type: SourceType
    payload: Dict[str, Any]
    allowed_targets: List[str]  # 派生只读 (源自 source_type)
    is_active: bool


@router.get("", response_model=List[ChannelAssetResponse])
def list_assets(
    source_type: Optional[SourceType] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    try:
        assets = list_channel_assets(
            db, source_type=source_type, include_inactive=include_inactive)
    except ChannelAssetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [ChannelAssetResponse.model_validate(a) for a in assets]


@router.post("", response_model=ChannelAssetResponse, status_code=201)
def create_asset(req: ChannelAssetCreate, db: Session = Depends(get_db)):
    try:
        a = create_channel_asset(db, **req.model_dump())
    except ChannelAssetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ChannelAssetResponse.model_validate(a)


@router.get("/{asset_id}", response_model=ChannelAssetResponse)
def get_asset(asset_id: UUID, db: Session = Depends(get_db)):
    try:
        return ChannelAssetResponse.model_validate(get_channel_asset(db, asset_id))
    except ChannelAssetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{asset_id}", response_model=ChannelAssetResponse)
def update_asset(asset_id: UUID, req: ChannelAssetUpdate, db: Session = Depends(get_db)):
    try:
        # exclude_unset: 只改 operator 显式设的字段 (PATCH 语义)
        a = update_channel_asset(db, asset_id, **req.model_dump(exclude_unset=True))
    except ChannelAssetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ChannelAssetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ChannelAssetResponse.model_validate(a)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: UUID, hard: bool = False, db: Session = Depends(get_db)):
    try:
        delete_channel_asset(db, asset_id, soft=not hard)
    except ChannelAssetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
