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
    radio_technology: str = Field(..., description="nr5g | lte")
    channel_kind: str = Field(..., description="nr_arfcn | lte_dl_earfcn")
    band: str = Field(..., examples=["N78"])
    arfcn: Optional[int] = Field(None, gt=0, description="NR-ARFCN；LTE 为空")
    lte_dl_earfcn: Optional[int] = Field(
        None, ge=0, description="LTE DL EARFCN；NR 为空"
    )
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
    radio_technology: str
    channel_kind: str
    band: str
    arfcn: Optional[int]
    lte_dl_earfcn: Optional[int]
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


class SCDAssociateRequest(BaseModel):
    """把一个实际 .smu 文件关联到 SCD (slice 2b)。"""

    file_path: str = Field(
        ..., description="实际 .smu 文件 (CALC:FILT:FILE 加载这个; 路径 c 是厂商真文件)"
    )
    association_source: str = Field(
        "vendor_associated",
        description="standard_generated (路径 a/b, 文件按标准名生成, basename 须 == 标准名) | "
        "vendor_associated (路径 c, 关联已有厂商文件, 仅频率 cross-check)",
    )


@router.post("", response_model=SCDResponse, status_code=status.HTTP_201_CREATED)
def create_standard_channel(req: SCDCreateRequest, db: Session = Depends(get_db)):
    try:
        return svc.create_scd(
            db,
            instrument_connection_id=req.instrument_connection_id,
            radio_technology=req.radio_technology,
            channel_kind=req.channel_kind,
            band=req.band, arfcn=req.arfcn,
            lte_dl_earfcn=req.lte_dl_earfcn,
            bandwidth_mhz=req.bandwidth_mhz,
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


@router.post("/{scd_id}/associate", response_model=SCDResponse)
def associate_standard_channel_file(
    scd_id: UUID, req: SCDAssociateRequest, db: Session = Depends(get_db)
):
    """关联实际 .smu 文件 + 更新 synced projection (available_channel_models)。

    cross-check 文件名频率 vs SCD 声明 ARFCN, 不符 → 400 (fail-loud)。
    """
    try:
        return svc.associate_file(
            db, scd_id,
            file_path=req.file_path,
            association_source=req.association_source,
        )
    except svc.StandardChannelNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except svc.StandardChannelError as e:
        # cross-check 不符 / source 非法 / standard 名不匹配 → 400 (客户端可修)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{scd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_standard_channel(scd_id: UUID, db: Session = Depends(get_db)):
    try:
        svc.delete_scd(db, scd_id)
    except svc.StandardChannelError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
