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
from app.services.smu_project_inventory import (
    SMUProjectInventoryError,
    SMUProjectSyncError,
    preview_smu_project_sync,
    sync_smu_project_truth,
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


class SMUProjectSyncItemResponse(BaseModel):
    """One read-only project observation plus its exact-match synchronization decision."""

    model_config = ConfigDict(from_attributes=True)

    relative_path: str
    instrument_path: str
    size_bytes: int
    sha256: str
    center_frequencies_hz: Dict[int, int]
    primary_center_frequency_hz: Optional[int] = None
    scan_status: str
    scan_detail: Optional[str] = None
    sync_status: str
    sync_detail: str
    connection_id: UUID
    asset_id: Optional[UUID] = None
    asset_name: Optional[str] = None
    target_arfcn: Optional[int] = None
    target_lte_dl_earfcn: Optional[int] = None


class SMUProjectSyncPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connection_id: UUID
    items: List[SMUProjectSyncItemResponse]
    protected_paths: List[str]
    total_files: int
    total_bytes: int


class SMUProjectSyncResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    updated_count: int
    already_synced_count: int
    preview: SMUProjectSyncPreviewResponse


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


# Static routes must be registered before /{asset_id}; otherwise FastAPI/Starlette can route
# "vendor-files" into the dynamic UUID sibling and return a misleading 422/404.
@router.post(
    "/vendor-files/smu-scan",
    response_model=SMUProjectSyncPreviewResponse,
)
def scan_vendor_smu_projects(db: Session = Depends(get_db)):
    """Development/debug scan of an SMB copy; never a formal execution prerequisite."""
    try:
        return preview_smu_project_sync(db)
    except SMUProjectInventoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/vendor-files/smu-sync",
    response_model=SMUProjectSyncResultResponse,
)
def sync_vendor_smu_projects(db: Session = Depends(get_db)):
    """Development/debug sync of provable exact-path matches from an SMB copy.

    There is intentionally no request body: clients cannot submit a frequency, ARFCN, mount root,
    or cached preview as truth.  This offline authoring operation is never consulted by Readiness,
    execution freeze, or MEASURE.
    """
    try:
        return sync_smu_project_truth(db)
    except (SMUProjectInventoryError, SMUProjectSyncError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
