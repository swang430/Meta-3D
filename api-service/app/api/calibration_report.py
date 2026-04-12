"""
Calibration Report API Endpoints

REST API for generating calibration reports.
"""

from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.services.calibration_report_generator import CalibrationReportGenerator

router = APIRouter(prefix="/calibration-reports", tags=["calibration-reports"])


# ==================== Request/Response Schemas ====================

class GenerateReportRequest(BaseModel):
    """Request to generate a calibration report"""
    session_id: Optional[str] = Field(
        None,
        description="Optional session ID to filter calibrations"
    )
    include_probe: bool = Field(
        True,
        description="Include probe calibration data"
    )
    include_channel: bool = Field(
        True,
        description="Include channel calibration data"
    )
    title: Optional[str] = Field(
        None,
        description="Custom report title"
    )


class GenerateProbeReportRequest(BaseModel):
    """Request to generate a probe calibration report"""
    probe_ids: Optional[List[int]] = Field(
        None,
        description="Filter by probe IDs"
    )
    calibration_type: Optional[str] = Field(
        None,
        description="Filter by calibration type: amplitude, phase, polarization, pattern, link"
    )


class GenerateChannelReportRequest(BaseModel):
    """Request to generate a channel calibration report"""
    session_id: Optional[str] = Field(
        None,
        description="Filter by session ID"
    )
    calibration_type: Optional[str] = Field(
        None,
        description="Filter by type: temporal, doppler, spatial_correlation, angular_spread, quiet_zone, eis"
    )


class ReportGeneratedResponse(BaseModel):
    """Response after report generation"""
    success: bool
    report_path: str
    message: str


# ==================== API Endpoints ====================

@router.post("/comprehensive", response_model=ReportGeneratedResponse)
async def generate_comprehensive_report(
    request: GenerateReportRequest,
    db: Session = Depends(get_db)
):
    """
    生成综合校准报告

    生成包含探头校准和信道校准数据的完整 PDF 报告。

    **包含内容**:
    - 封面和摘要
    - 探头校准结果（幅度、相位、极化、方向图、链路）
    - 信道校准结果（时域、多普勒、空间相关性、角度扩展、静区、EIS）
    - 验证状态和通过率统计
    """
    try:
        generator = CalibrationReportGenerator(db)

        session_id = UUID(request.session_id) if request.session_id else None

        report_path = generator.generate_comprehensive_report(
            session_id=session_id,
            include_probe=request.include_probe,
            include_channel=request.include_channel,
            title=request.title,
        )

        return ReportGeneratedResponse(
            success=True,
            report_path=report_path,
            message="Comprehensive calibration report generated successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(e)}"
        )


@router.post("/probe", response_model=ReportGeneratedResponse)
async def generate_probe_report(
    request: GenerateProbeReportRequest,
    db: Session = Depends(get_db)
):
    """
    生成探头校准报告

    生成仅包含探头校准数据的 PDF 报告。

    **支持过滤**:
    - 按探头 ID 列表过滤
    - 按校准类型过滤（amplitude, phase, polarization, pattern, link）
    """
    try:
        generator = CalibrationReportGenerator(db)

        report_path = generator.generate_probe_calibration_report(
            probe_ids=request.probe_ids,
            calibration_type=request.calibration_type,
        )

        return ReportGeneratedResponse(
            success=True,
            report_path=report_path,
            message="Probe calibration report generated successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(e)}"
        )


@router.post("/channel", response_model=ReportGeneratedResponse)
async def generate_channel_report(
    request: GenerateChannelReportRequest,
    db: Session = Depends(get_db)
):
    """
    生成信道校准报告

    生成仅包含信道校准数据的 PDF 报告。

    **支持过滤**:
    - 按校准会话 ID 过滤
    - 按校准类型过滤（temporal, doppler, spatial_correlation, angular_spread, quiet_zone, eis）
    """
    try:
        generator = CalibrationReportGenerator(db)

        session_id = UUID(request.session_id) if request.session_id else None

        report_path = generator.generate_channel_calibration_report(
            session_id=session_id,
            calibration_type=request.calibration_type,
        )

        return ReportGeneratedResponse(
            success=True,
            report_path=report_path,
            message="Channel calibration report generated successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report: {str(e)}"
        )


@router.get("/download/{report_path:path}")
async def download_report(report_path: str):
    """
    下载校准报告

    通过路径下载生成的 PDF 报告文件。
    """
    import os

    # Validate path is within allowed directory
    if not report_path.startswith("data/reports/calibration/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid report path"
        )

    full_path = report_path
    if not os.path.exists(full_path):
        raise HTTPException(
            status_code=404,
            detail="Report file not found"
        )

    return FileResponse(
        path=full_path,
        filename=os.path.basename(full_path),
        media_type="application/pdf"
    )
