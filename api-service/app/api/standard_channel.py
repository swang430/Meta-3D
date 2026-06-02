"""P2-12 slice 2: Standard Channel Definition (SCD) CRUD API.

软件掌控的标准信道定义 (见架构文档 §9 / standard_channel_service)。slice 2a: 定义
(create/list/get/delete); 关联文件 + synced projection 是 slice 2b。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import standard_channel_service as svc

router = APIRouter(prefix="/standard-channels", tags=["Standard Channels"])


class SCDCreateRequest(BaseModel):
    """定义一个标准信道的规范配置 (标准名由后端从这些字段算, 不接受前端传名)。"""

    instrument_connection_id: UUID = Field(..., description="所属 F64 绑定")
    band: str = Field(..., examples=["N78"])
    arfcn: int = Field(..., gt=0, description="中心 ARFCN (频率规范真值)")
    bandwidth_mhz: int = Field(..., gt=0)
    model: str = Field(..., description="filename-safe, e.g. CDLC", examples=["CDLC"])
    scenario: str = Field(..., examples=["UMa"])
    mimo: str = Field(..., examples=["4x4"])
    polarization: str = Field(..., description="V/H/DP", examples=["DP"])
    version: int = Field(1, gt=0)
    description: Optional[str] = None


class SCDResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    band: str
    arfcn: int
    bandwidth_mhz: int
    model: str
    scenario: str
    mimo: str
    polarization: str
    version: int
    standard_name: str
    instrument_connection_id: UUID
    associated_file_path: Optional[str] = None
    association_source: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@router.post("", response_model=SCDResponse, status_code=status.HTTP_201_CREATED)
def create_standard_channel(req: SCDCreateRequest, db: Session = Depends(get_db)):
    try:
        return svc.create_scd(
            db,
            instrument_connection_id=req.instrument_connection_id,
            band=req.band, arfcn=req.arfcn, bandwidth_mhz=req.bandwidth_mhz,
            model=req.model, scenario=req.scenario, mimo=req.mimo,
            polarization=req.polarization, version=req.version,
            description=req.description,
        )
    except svc.StandardChannelError as e:
        # 字段非法 / 重复 → 400 (客户端可修)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[SCDResponse])
def list_standard_channels(
    instrument_connection_id: Optional[UUID] = Query(
        None, description="只列该 F64 绑定的标准信道"
    ),
    db: Session = Depends(get_db),
):
    return svc.list_scds(db, instrument_connection_id=instrument_connection_id)


@router.get("/{scd_id}", response_model=SCDResponse)
def get_standard_channel(scd_id: UUID, db: Session = Depends(get_db)):
    try:
        return svc.get_scd(db, scd_id)
    except svc.StandardChannelError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{scd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_standard_channel(scd_id: UUID, db: Session = Depends(get_db)):
    try:
        svc.delete_scd(db, scd_id)
    except svc.StandardChannelError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
