"""
Channel Calibration API Endpoints

信道校准相关的 API 端点。

包含:
- 校准会话管理
- 时域校准 (PDP, RMS 时延扩展)
- 多普勒校准
- 空间相关性校准
- 角度扩展校准
- 静区校准
- EIS 验证
- 校准历史和有效性查询

参考: docs/features/calibration/channel-calibration.md
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.db.database import get_db
from app.schemas.channel_calibration import (
    # Enums
    ChannelCalibrationJobStatus,
    # Common
    CalibrationJobResponse,
    CalibrationProgress,
    ScenarioConfig,
    # Temporal
    StartTemporalCalibrationRequest,
    TemporalCalibrationResponse,
    # Doppler
    StartDopplerCalibrationRequest,
    DopplerCalibrationResponse,
    # Spatial Correlation
    StartSpatialCorrelationCalibrationRequest,
    SpatialCorrelationCalibrationResponse,
    # Angular Spread
    StartAngularSpreadCalibrationRequest,
    AngularSpreadCalibrationResponse,
    # Quiet Zone
    StartQuietZoneCalibrationRequest,
    QuietZoneCalibrationResponse,
    # EIS
    StartEISValidationRequest,
    EISValidationResponse,
    # Session
    StartCalibrationSessionRequest,
    CalibrationSessionResponse,
    UpdateSessionProgressRequest,
    CompleteSessionRequest,
    # History & Validity
    ChannelCalibrationHistoryQuery,
    ChannelCalibrationHistoryResponse,
    ChannelCalibrationHistoryItem,
    ChannelCalibrationValidityReport,
    ChannelCalibrationStatusSummary,
    InvalidateCalibrationRequest,
    InvalidateCalibrationResponse,
)
from app.services.channel_calibration_service import ChannelCalibrationService

router = APIRouter(prefix="/calibration/channel", tags=["Channel Calibration"])


# ==================== Session Management ====================

@router.post("/sessions", response_model=CalibrationSessionResponse, status_code=201)
async def create_calibration_session(
    request: StartCalibrationSessionRequest,
    db: Session = Depends(get_db)
):
    """
    创建新的校准会话

    校准会话用于组织一次完整的信道校准流程，
    可以包含多个不同类型的校准（时域、空间、EIS 等）。
    """
    service = ChannelCalibrationService(db)
    session = service.create_session(
        name=request.name,
        description=request.description,
        workflow_id=request.workflow_id,
        configuration=request.configuration,
        created_by=request.created_by
    )
    return session


@router.get("/sessions/{session_id}", response_model=CalibrationSessionResponse)
async def get_calibration_session(
    session_id: UUID,
    db: Session = Depends(get_db)
):
    """获取校准会话详情"""
    service = ChannelCalibrationService(db)
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/sessions/{session_id}/progress", response_model=CalibrationSessionResponse)
async def update_session_progress(
    session_id: UUID,
    request: UpdateSessionProgressRequest,
    db: Session = Depends(get_db)
):
    """更新校准会话进度"""
    service = ChannelCalibrationService(db)
    session = service.update_session_progress(
        session_id=session_id,
        progress_percent=request.progress_percent,
        current_stage=request.current_stage,
        status=request.status.value if request.status else None
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/{session_id}/complete", response_model=CalibrationSessionResponse)
async def complete_calibration_session(
    session_id: UUID,
    request: CompleteSessionRequest,
    db: Session = Depends(get_db)
):
    """完成校准会话"""
    service = ChannelCalibrationService(db)
    session = service.complete_session(
        session_id=session_id,
        overall_pass=request.overall_pass,
        total_calibrations=request.total_calibrations,
        passed_calibrations=request.passed_calibrations,
        failed_calibrations=request.failed_calibrations
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ==================== Temporal Channel Calibration ====================

@router.post("/temporal/start", response_model=CalibrationJobResponse, status_code=202)
async def start_temporal_calibration(
    request: StartTemporalCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动时域信道校准

    时域校准验证信道仿真器能否正确生成 3GPP 定义的功率时延谱 (PDP)。

    **校准内容**:
    - 功率时延谱 (PDP) 测量
    - RMS 时延扩展计算
    - 簇检测和参数提取
    - 与 3GPP TR 38.901 参考值对比

    **验收标准**: RMS 时延扩展误差 < 10%

    **支持场景**:
    - UMa (Urban Macro): LOS/NLOS
    - UMi (Urban Micro): LOS/NLOS
    - RMa (Rural Macro): LOS/NLOS
    - InH (Indoor Hotspot): LOS/NLOS
    """
    service = ChannelCalibrationService(db)

    # 执行校准
    calibration = service.run_temporal_calibration(
        scenario_type=request.scenario.type.value,
        scenario_condition=request.scenario.condition.value,
        fc_ghz=request.scenario.fc_ghz,
        distance_2d_m=request.scenario.distance_2d_m,
        session_id=request.session_id,
        channel_emulator=request.channel_emulator_id,
        calibrated_by=request.calibrated_by
    )

    return CalibrationJobResponse(
        calibration_job_id=calibration.id,
        status=ChannelCalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=5.0,
        message=f"Temporal calibration completed for {request.scenario.type.value} {request.scenario.condition.value}"
    )


@router.get("/temporal/{calibration_id}", response_model=TemporalCalibrationResponse)
async def get_temporal_calibration(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """获取时域校准详情"""
    service = ChannelCalibrationService(db)
    calibration = service.get_temporal_calibration(calibration_id)
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


@router.get("/temporal/latest", response_model=TemporalCalibrationResponse)
async def get_latest_temporal_calibration(
    scenario_type: Optional[str] = Query(None, description="场景类型: UMa, UMi, RMa, InH"),
    scenario_condition: Optional[str] = Query(None, description="信道条件: LOS, NLOS"),
    db: Session = Depends(get_db)
):
    """获取最新的时域校准记录"""
    service = ChannelCalibrationService(db)
    calibration = service.get_latest_temporal_calibration(
        scenario_type=scenario_type,
        scenario_condition=scenario_condition
    )
    if not calibration:
        raise HTTPException(status_code=404, detail="No temporal calibration found")
    return calibration


# ==================== Doppler Calibration ====================

@router.post("/doppler/start", response_model=CalibrationJobResponse, status_code=202)
async def start_doppler_calibration(
    request: StartDopplerCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动多普勒校准

    多普勒校准验证信道仿真器能否正确生成多普勒频谱。

    **校准内容**:
    - 发射 CW 信号
    - FFT 分析接收信号
    - 提取多普勒频谱
    - 与经典 Jakes 频谱对比

    **验收标准**: 频谱相关性 > 0.9

    **典型速度配置**:
    - 3 km/h (步行)
    - 30 km/h (城市)
    - 120 km/h (高速)
    - 350 km/h (高铁)
    """
    service = ChannelCalibrationService(db)

    calibration = service.run_doppler_calibration(
        velocity_kmh=request.velocity_kmh,
        fc_ghz=request.fc_ghz,
        session_id=request.session_id,
        channel_emulator=request.channel_emulator_id,
        calibrated_by=request.calibrated_by
    )

    return CalibrationJobResponse(
        calibration_job_id=calibration.id,
        status=ChannelCalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=3.0,
        message=f"Doppler calibration completed for {request.velocity_kmh} km/h"
    )


@router.get("/doppler/{calibration_id}", response_model=DopplerCalibrationResponse)
async def get_doppler_calibration(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """获取多普勒校准详情"""
    service = ChannelCalibrationService(db)
    calibration = service.get_doppler_calibration(calibration_id)
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


# ==================== Spatial Correlation Calibration ====================

@router.post("/spatial-correlation/start", response_model=CalibrationJobResponse, status_code=202)
async def start_spatial_correlation_calibration(
    request: StartSpatialCorrelationCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动空间相关性校准

    空间相关性校准验证 MPAC 系统能否正确重现 MIMO 天线间的空间相关性。

    **校准内容**:
    - 使用双天线 DUT
    - 测量两天线信道系数的相关性
    - 与 3GPP Laplacian 模型理论值对比

    **验收标准**:
    - 相关系数幅度误差 < 0.1
    - 相关系数相位误差 < 10°

    **典型天线间距配置**:
    - 0.5λ (强相关)
    - 1λ (中等相关)
    - 2λ (弱相关)
    """
    service = ChannelCalibrationService(db)

    calibration = service.run_spatial_correlation_calibration(
        scenario_type=request.scenario.type.value,
        scenario_condition=request.scenario.condition.value,
        fc_ghz=request.scenario.fc_ghz,
        antenna_spacing_wavelengths=request.test_dut.antenna_spacing_wavelengths,
        antenna_spacing_m=request.test_dut.antenna_spacing_m,
        antenna_type=request.test_dut.antenna_type,
        session_id=request.session_id,
        calibrated_by=request.calibrated_by
    )

    return CalibrationJobResponse(
        calibration_job_id=calibration.id,
        status=ChannelCalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=10.0,
        message=f"Spatial correlation calibration completed for {request.test_dut.antenna_spacing_wavelengths}λ spacing"
    )


@router.get("/spatial-correlation/{calibration_id}", response_model=SpatialCorrelationCalibrationResponse)
async def get_spatial_correlation_calibration(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """获取空间相关性校准详情"""
    service = ChannelCalibrationService(db)
    calibration = service.get_spatial_correlation_calibration(calibration_id)
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


# ==================== Angular Spread Calibration ====================

@router.post("/angular-spread/start", response_model=CalibrationJobResponse, status_code=202)
async def start_angular_spread_calibration(
    request: StartAngularSpreadCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动角度扩展校准

    角度扩展校准验证 MPAC 系统的角度功率谱 (APS) 与 3GPP 模型一致。

    **校准内容**:
    - 旋转 DUT，扫描方位角 (0°-360°)
    - 测量每个角度的接收功率
    - 拟合 Laplacian/Gaussian 分布
    - 提取 RMS 角度扩展

    **验收标准**: RMS 角度扩展误差 < 5°
    """
    service = ChannelCalibrationService(db)

    calibration = service.run_angular_spread_calibration(
        scenario_type=request.scenario.type.value,
        scenario_condition=request.scenario.condition.value,
        fc_ghz=request.scenario.fc_ghz,
        azimuth_step_deg=request.azimuth_step_deg or 5.0,
        session_id=request.session_id,
        positioner=request.positioner,
        calibrated_by=request.calibrated_by
    )

    return CalibrationJobResponse(
        calibration_job_id=calibration.id,
        status=ChannelCalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=30.0,
        message=f"Angular spread calibration completed for {request.scenario.type.value} {request.scenario.condition.value}"
    )


@router.get("/angular-spread/{calibration_id}", response_model=AngularSpreadCalibrationResponse)
async def get_angular_spread_calibration(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """获取角度扩展校准详情"""
    service = ChannelCalibrationService(db)
    calibration = service.get_angular_spread_calibration(calibration_id)
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


# ==================== Quiet Zone Calibration ====================

@router.post("/quiet-zone/start", response_model=CalibrationJobResponse, status_code=202)
async def start_quiet_zone_calibration(
    request: StartQuietZoneCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动静区均匀性校准

    静区校准验证静区 (Quiet Zone) 内的电磁场幅度和相位均匀性。

    **校准内容**:
    - 使用场探头在静区内多点扫描
    - 计算幅度和相位的统计特性
    - 验证均匀性要求

    **验收标准** (CTIA):
    - 幅度均匀性: ±1 dB
    - 相位均匀性: ±30° (mmWave 可放宽至 ±45°)
    """
    service = ChannelCalibrationService(db)

    calibration = service.run_quiet_zone_calibration(
        quiet_zone_shape=request.quiet_zone.shape.value,
        quiet_zone_diameter_m=request.quiet_zone.diameter_m,
        fc_ghz=request.fc_ghz,
        num_points=request.num_points or 100,
        quiet_zone_height_m=request.quiet_zone.height_m,
        field_probe_type=request.field_probe.type.value if request.field_probe else "dipole",
        field_probe_size_mm=request.field_probe.size_mm if request.field_probe else 10.0,
        session_id=request.session_id,
        calibrated_by=request.calibrated_by
    )

    return CalibrationJobResponse(
        calibration_job_id=calibration.id,
        status=ChannelCalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=60.0,
        message=f"Quiet zone calibration completed for {request.quiet_zone.shape.value} zone ({request.quiet_zone.diameter_m}m)"
    )


@router.get("/quiet-zone/{calibration_id}", response_model=QuietZoneCalibrationResponse)
async def get_quiet_zone_calibration(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """获取静区校准详情"""
    service = ChannelCalibrationService(db)
    calibration = service.get_quiet_zone_calibration(calibration_id)
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return calibration


# ==================== EIS Validation ====================

@router.post("/eis/start", response_model=CalibrationJobResponse, status_code=202)
async def start_eis_validation(
    request: StartEISValidationRequest,
    db: Session = Depends(get_db)
):
    """
    启动 EIS 验证

    EIS (等效全向灵敏度) 验证是端到端性能验证，
    确保系统能正确测量 DUT 的 EIS。

    **验证内容**:
    - 使用参考 DUT
    - 3D 空间扫描 (θ, φ)
    - 测量灵敏度分布
    - 与已知参考值对比

    **验收标准**: EIS 测量误差 < ±1 dB
    """
    service = ChannelCalibrationService(db)

    calibration = service.run_eis_validation(
        fc_ghz=request.test_config.fc_ghz,
        dut_model=request.dut.model,
        dut_type=request.dut.type.value if request.dut.type else "vehicle",
        scenario=request.test_config.scenario,
        bandwidth_mhz=request.test_config.bandwidth_mhz,
        modulation=request.test_config.modulation,
        target_throughput_percent=request.test_config.target_throughput_percent or 95.0,
        num_rx_antennas=request.dut.num_rx_antennas,
        min_eis_dbm=request.test_config.min_eis_dbm,
        session_id=request.session_id,
        measured_by=request.measured_by
    )

    return CalibrationJobResponse(
        calibration_job_id=calibration.id,
        status=ChannelCalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=120.0,
        message=f"EIS validation completed for {request.dut.model}"
    )


@router.get("/eis/{calibration_id}", response_model=EISValidationResponse)
async def get_eis_validation(
    calibration_id: UUID,
    db: Session = Depends(get_db)
):
    """获取 EIS 验证详情"""
    service = ChannelCalibrationService(db)
    calibration = service.get_eis_validation(calibration_id)
    if not calibration:
        raise HTTPException(status_code=404, detail="Validation not found")
    return calibration


# ==================== History & Validity ====================

@router.get("/history", response_model=ChannelCalibrationHistoryResponse)
async def get_calibration_history(
    calibration_type: Optional[str] = Query(
        None,
        description="校准类型: temporal, doppler, spatial_correlation, angular_spread, quiet_zone, eis"
    ),
    validation_pass: Optional[bool] = Query(None, description="筛选通过/失败"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """获取校准历史"""
    service = ChannelCalibrationService(db)
    results = service.list_calibrations(
        calibration_type=calibration_type,
        validation_pass=validation_pass,
        limit=limit,
        offset=offset
    )

    items = [
        ChannelCalibrationHistoryItem(
            calibration_id=r["calibration_id"],
            calibration_type=r["calibration_type"],
            calibrated_at=r["calibrated_at"],
            calibrated_by=r["calibrated_by"],
            status=r["status"],
            validation_pass=r["validation_pass"],
            summary=r["summary"]
        )
        for r in results
    ]

    return ChannelCalibrationHistoryResponse(
        total=len(items),
        items=items
    )


@router.get("/status", response_model=ChannelCalibrationStatusSummary)
async def get_channel_calibration_status(
    db: Session = Depends(get_db)
):
    """
    获取信道校准状态摘要

    返回各类校准的当前状态、最后校准时间和下次到期时间。
    """
    service = ChannelCalibrationService(db)

    # 获取各类校准的最新记录
    temporal = service.get_latest_temporal_calibration()

    # 构建状态摘要
    def get_status_info(calibration, validity_days):
        if not calibration:
            return {
                "status": "unknown",
                "last_calibrated": None,
                "next_due": None
            }

        valid_until = calibration.valid_until or calibration.calibrated_at
        now = datetime.utcnow()

        if now > valid_until:
            status = "expired"
        elif (valid_until - now).days <= 7:
            status = "expiring_soon"
        else:
            status = "valid"

        return {
            "status": status,
            "last_calibrated": calibration.calibrated_at,
            "next_due": valid_until
        }

    temporal_info = get_status_info(temporal, 30)

    # TODO: 获取其他类型的校准状态
    default_info = {
        "status": "unknown",
        "last_calibrated": None,
        "next_due": None
    }

    # 计算总体状态
    statuses = [temporal_info["status"]]
    if "expired" in statuses:
        overall_status = "expired"
    elif "expiring_soon" in statuses:
        overall_status = "expiring_soon"
    elif all(s == "valid" for s in statuses):
        overall_status = "valid"
    else:
        overall_status = "unknown"

    # 获取最近校准历史
    recent = service.list_calibrations(limit=5)
    recent_items = [
        ChannelCalibrationHistoryItem(
            calibration_id=r["calibration_id"],
            calibration_type=r["calibration_type"],
            calibrated_at=r["calibrated_at"],
            calibrated_by=r["calibrated_by"],
            status=r["status"],
            validation_pass=r["validation_pass"],
            summary=r["summary"]
        )
        for r in recent
    ]

    return ChannelCalibrationStatusSummary(
        temporal_status=temporal_info["status"],
        temporal_last_calibrated=temporal_info["last_calibrated"],
        temporal_next_due=temporal_info["next_due"],

        doppler_status=default_info["status"],
        doppler_last_calibrated=default_info["last_calibrated"],
        doppler_next_due=default_info["next_due"],

        spatial_correlation_status=default_info["status"],
        spatial_correlation_last_calibrated=default_info["last_calibrated"],
        spatial_correlation_next_due=default_info["next_due"],

        angular_spread_status=default_info["status"],
        angular_spread_last_calibrated=default_info["last_calibrated"],
        angular_spread_next_due=default_info["next_due"],

        quiet_zone_status=default_info["status"],
        quiet_zone_last_calibrated=default_info["last_calibrated"],
        quiet_zone_next_due=default_info["next_due"],

        eis_status=default_info["status"],
        eis_last_calibrated=default_info["last_calibrated"],
        eis_next_due=default_info["next_due"],

        overall_status=overall_status,
        recent_calibrations=recent_items
    )


@router.post("/{calibration_type}/{calibration_id}/invalidate", response_model=InvalidateCalibrationResponse)
async def invalidate_calibration(
    calibration_type: str,
    calibration_id: UUID,
    request: InvalidateCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    作废校准记录

    将指定的校准记录标记为无效。

    **支持的校准类型**:
    - temporal
    - doppler
    - spatial_correlation
    - angular_spread
    - quiet_zone
    - eis
    """
    from app.models.channel_calibration import (
        TemporalChannelCalibration,
        DopplerCalibration,
        SpatialCorrelationCalibration,
        AngularSpreadCalibration,
        ChannelQuietZoneCalibration,
        EISValidation,
        ChannelCalibrationStatus,
    )

    # 根据类型获取校准记录
    model_map = {
        "temporal": TemporalChannelCalibration,
        "doppler": DopplerCalibration,
        "spatial_correlation": SpatialCorrelationCalibration,
        "angular_spread": AngularSpreadCalibration,
        "quiet_zone": ChannelQuietZoneCalibration,
        "eis": EISValidation,
    }

    model = model_map.get(calibration_type)
    if not model:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported calibration type: {calibration_type}"
        )

    calibration = db.query(model).filter(model.id == calibration_id).first()
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration not found")

    previous_status = calibration.status
    calibration.status = ChannelCalibrationStatus.INVALIDATED.value
    db.commit()

    return InvalidateCalibrationResponse(
        calibration_id=calibration_id,
        calibration_type=calibration_type,
        invalidated_at=datetime.utcnow(),
        reason=request.reason,
        previous_status=previous_status
    )
