"""
Probe Calibration API Endpoints

探头校准相关的 API 端点。

TASK-P03: 幅度校准 API (3 端点 + 4 API 测试)
参考: docs/features/calibration/IMPLEMENTATION-PLAN.md
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timedelta
import numpy as np

from app.db.database import get_db
from app.schemas.probe_calibration import (
    # Enums
    CalibrationJobStatus,
    # Common
    CalibrationJobResponse,
    CalibrationProgress,
    # Amplitude
    StartAmplitudeCalibrationRequest,
    AmplitudeCalibrationResponse,
    # Phase
    StartPhaseCalibrationRequest,
    PhaseCalibrationResponse,
    # Polarization
    StartPolarizationCalibrationRequest,
    PolarizationCalibrationResponse,
    # Pattern
    StartPatternCalibrationRequest,
    PatternCalibrationResponse,
    # Link
    StartLinkCalibrationRequest,
    LinkCalibrationResponse,
    # Validity
    ProbeCalibrationStatus,
    CalibrationValidityReport,
    InvalidateCalibrationRequest,
    # History
    CalibrationHistoryResponse,
    CalibrationHistoryItem,
    # Data Query
    ProbeCalibrationDataResponse,
)
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    ProbePhaseCalibration,
    ProbePolarizationCalibration,
    ProbePattern,
    LinkCalibration,
    ProbeCalibrationValidity,
    CalibrationStatus,
    Polarization,
)

router = APIRouter(prefix="/calibration/probe", tags=["Probe Calibration"])


# ==================== Amplitude Calibration Endpoints ====================

@router.post("/amplitude/start", response_model=CalibrationJobResponse, status_code=202)
async def start_amplitude_calibration(
    request: StartAmplitudeCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动幅度校准任务

    幅度校准测量探头的发射和接收增益，确保探头间的幅度一致性。

    **校准内容**:
    - Tx Gain: 发射增益 (dBi)
    - Rx Gain: 接收增益 (dBi)
    - 互易性验证: |Tx - Rx| < 0.5 dB

    **验收标准**: 增益不确定度 < ±0.3 dB

    Returns:
        CalibrationJobResponse: 校准任务 ID 和状态
    """
    # TODO: 实际实现需要在 TASK-P04 中完成服务层
    # 当前为 mock 实现，直接创建校准记录

    job_id = uuid4()

    # 计算预估时间（每个探头约 2 分钟，每个极化约 1 分钟）
    num_probes = len(request.probe_ids)
    num_polarizations = len(request.polarizations)
    estimated_minutes = num_probes * num_polarizations * 2.0

    # 为每个探头和极化创建校准记录（mock 数据）
    for probe_id in request.probe_ids:
        for pol in request.polarizations:
            # 生成频率点
            freq_range = request.frequency_range
            freq_points = []
            freq = freq_range.start_mhz
            while freq <= freq_range.stop_mhz:
                freq_points.append(freq)
                freq += freq_range.step_mhz

            # Mock 增益数据
            num_points = len(freq_points)
            import random
            base_gain = 5.0  # dBi
            tx_gain = [base_gain + random.gauss(0, 0.1) for _ in range(num_points)]
            rx_gain = [base_gain + random.gauss(0, 0.1) for _ in range(num_points)]
            uncertainty = [0.3 for _ in range(num_points)]

            calibration = ProbeAmplitudeCalibration(
                probe_id=probe_id,
                polarization=pol.value,
                frequency_points_mhz=freq_points,
                tx_gain_dbi=tx_gain,
                rx_gain_dbi=rx_gain,
                tx_gain_uncertainty_db=uncertainty,
                rx_gain_uncertainty_db=uncertainty,
                reference_antenna=request.reference_antenna_id,
                reference_power_meter=request.power_meter_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=request.calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=90),
                status=CalibrationStatus.VALID
            )
            db.add(calibration)

    db.commit()

    return CalibrationJobResponse(
        calibration_job_id=job_id,
        status=CalibrationJobStatus.COMPLETED,  # Mock: 直接完成
        estimated_duration_minutes=estimated_minutes,
        message=f"Amplitude calibration completed for {num_probes} probes, {num_polarizations} polarizations"
    )


@router.get("/amplitude/{probe_id}", response_model=AmplitudeCalibrationResponse)
def get_amplitude_calibration(
    probe_id: int,
    polarization: Optional[str] = Query(None, description="极化类型: V, H, LHCP, RHCP"),
    db: Session = Depends(get_db)
):
    """
    获取探头的最新幅度校准数据

    Args:
        probe_id: 探头 ID (0-63)
        polarization: 可选的极化类型过滤

    Returns:
        AmplitudeCalibrationResponse: 幅度校准数据
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    query = db.query(ProbeAmplitudeCalibration).filter(
        ProbeAmplitudeCalibration.probe_id == probe_id
    )

    if polarization:
        query = query.filter(ProbeAmplitudeCalibration.polarization == polarization)

    # 获取最新的校准记录
    calibration = query.order_by(desc(ProbeAmplitudeCalibration.calibrated_at)).first()

    if not calibration:
        raise HTTPException(
            status_code=404,
            detail=f"No amplitude calibration found for probe {probe_id}"
        )

    return calibration


@router.get("/amplitude/{probe_id}/history", response_model=CalibrationHistoryResponse)
def get_amplitude_calibration_history(
    probe_id: int,
    limit: int = Query(20, ge=1, le=100, description="返回记录数量"),
    db: Session = Depends(get_db)
):
    """
    获取探头的幅度校准历史记录

    Args:
        probe_id: 探头 ID (0-63)
        limit: 返回记录数量 (默认 20, 最大 100)

    Returns:
        CalibrationHistoryResponse: 校准历史列表和趋势分析
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    calibrations = db.query(ProbeAmplitudeCalibration).filter(
        ProbeAmplitudeCalibration.probe_id == probe_id
    ).order_by(
        desc(ProbeAmplitudeCalibration.calibrated_at)
    ).limit(limit).all()

    history_items = []
    for cal in calibrations:
        # 计算平均增益作为摘要
        avg_tx_gain = sum(cal.tx_gain_dbi) / len(cal.tx_gain_dbi) if cal.tx_gain_dbi else 0
        avg_rx_gain = sum(cal.rx_gain_dbi) / len(cal.rx_gain_dbi) if cal.rx_gain_dbi else 0

        history_items.append(CalibrationHistoryItem(
            calibration_id=cal.id,
            calibration_type="amplitude",
            calibrated_at=cal.calibrated_at,
            calibrated_by=cal.calibrated_by,
            status=cal.status.value if hasattr(cal.status, 'value') else str(cal.status),
            summary={
                "polarization": cal.polarization,
                "avg_tx_gain_dbi": round(avg_tx_gain, 2),
                "avg_rx_gain_dbi": round(avg_rx_gain, 2),
                "num_freq_points": len(cal.frequency_points_mhz) if cal.frequency_points_mhz else 0
            }
        ))

    # 计算趋势（如果有足够的历史数据）
    trends = None
    if len(calibrations) >= 3:
        # 简单计算增益漂移趋势
        first_cal = calibrations[-1]  # 最早的
        last_cal = calibrations[0]    # 最新的

        if first_cal.tx_gain_dbi and last_cal.tx_gain_dbi:
            first_avg = sum(first_cal.tx_gain_dbi) / len(first_cal.tx_gain_dbi)
            last_avg = sum(last_cal.tx_gain_dbi) / len(last_cal.tx_gain_dbi)
            time_diff_days = (last_cal.calibrated_at - first_cal.calibrated_at).days
            if time_diff_days > 0:
                drift_per_month = (last_avg - first_avg) / (time_diff_days / 30.0)
                trends = {
                    "amplitude_drift_db_per_month": round(drift_per_month, 3),
                    "stability_rating": "stable" if abs(drift_per_month) < 0.1 else "drifting"
                }

    return CalibrationHistoryResponse(
        probe_id=probe_id,
        history=history_items,
        trends=trends
    )


# ==================== Phase Calibration Endpoints (TASK-P05) ====================

@router.post("/phase/start", response_model=CalibrationJobResponse, status_code=202)
async def start_phase_calibration(
    request: StartPhaseCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动相位校准任务

    相位校准测量探头相对于参考探头的相位偏移和群时延。

    **校准内容**:
    - 相位偏移: 相对参考探头的相位差 (度)
    - 群时延: 信号延迟 (ns)

    **验收标准**: 相位不确定度 < ±5°
    """
    job_id = uuid4()

    # 计算预估时间
    num_probes = len(request.probe_ids)
    num_polarizations = len(request.polarizations)
    estimated_minutes = num_probes * num_polarizations * 3.0  # 相位校准比幅度校准稍长

    # 生成频率点
    freq_range = request.frequency_range
    freq_points = []
    freq = freq_range.start_mhz
    while freq <= freq_range.stop_mhz:
        freq_points.append(freq)
        freq += freq_range.step_mhz

    # 为每个探头和极化创建校准记录（mock 数据）
    for probe_id in request.probe_ids:
        for pol in request.polarizations:
            num_points = len(freq_points)
            import random

            # Mock 相位数据
            # 相位偏移: 相对参考探头，随探头位置变化
            base_phase = (probe_id - request.reference_probe_id) * 15.0  # 每个探头约 15° 差异
            phase_offsets = [base_phase + random.gauss(0, 2) for _ in range(num_points)]

            # 群时延: 约 0.5-1.5 ns，随频率略有变化
            base_delay = 0.8 + probe_id * 0.01
            group_delays = [base_delay + random.gauss(0, 0.05) for _ in range(num_points)]

            # 相位不确定度
            phase_uncertainties = [3.0 for _ in range(num_points)]  # ±3°

            calibration = ProbePhaseCalibration(
                probe_id=probe_id,
                polarization=pol.value,
                reference_probe_id=request.reference_probe_id,
                frequency_points_mhz=freq_points,
                phase_offset_deg=phase_offsets,
                group_delay_ns=group_delays,
                phase_uncertainty_deg=phase_uncertainties,
                vna_model="Mock VNA",
                vna_serial="VNA-001",
                calibrated_at=datetime.utcnow(),
                calibrated_by=request.calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=90),
                status=CalibrationStatus.VALID
            )
            db.add(calibration)

    db.commit()

    return CalibrationJobResponse(
        calibration_job_id=job_id,
        status=CalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=estimated_minutes,
        message=f"Phase calibration completed for {num_probes} probes, {num_polarizations} polarizations"
    )


@router.get("/phase/{probe_id}", response_model=PhaseCalibrationResponse)
def get_phase_calibration(
    probe_id: int,
    polarization: Optional[str] = Query(None, description="极化类型: V, H"),
    db: Session = Depends(get_db)
):
    """
    获取探头的最新相位校准数据

    Args:
        probe_id: 探头 ID (0-63)
        polarization: 可选的极化类型过滤

    Returns:
        PhaseCalibrationResponse: 相位校准数据
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    query = db.query(ProbePhaseCalibration).filter(
        ProbePhaseCalibration.probe_id == probe_id
    )

    if polarization:
        query = query.filter(ProbePhaseCalibration.polarization == polarization)

    calibration = query.order_by(desc(ProbePhaseCalibration.calibrated_at)).first()

    if not calibration:
        raise HTTPException(
            status_code=404,
            detail=f"No phase calibration found for probe {probe_id}"
        )

    return calibration


@router.get("/phase/{probe_id}/history", response_model=CalibrationHistoryResponse)
def get_phase_calibration_history(
    probe_id: int,
    limit: int = Query(20, ge=1, le=100, description="返回记录数量"),
    db: Session = Depends(get_db)
):
    """
    获取探头的相位校准历史记录

    Args:
        probe_id: 探头 ID (0-63)
        limit: 返回记录数量

    Returns:
        CalibrationHistoryResponse: 校准历史列表
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    calibrations = db.query(ProbePhaseCalibration).filter(
        ProbePhaseCalibration.probe_id == probe_id
    ).order_by(
        desc(ProbePhaseCalibration.calibrated_at)
    ).limit(limit).all()

    history_items = []
    for cal in calibrations:
        avg_phase = sum(cal.phase_offset_deg) / len(cal.phase_offset_deg) if cal.phase_offset_deg else 0
        avg_delay = sum(cal.group_delay_ns) / len(cal.group_delay_ns) if cal.group_delay_ns else 0

        history_items.append(CalibrationHistoryItem(
            calibration_id=cal.id,
            calibration_type="phase",
            calibrated_at=cal.calibrated_at,
            calibrated_by=cal.calibrated_by,
            status=cal.status.value if hasattr(cal.status, 'value') else str(cal.status),
            summary={
                "polarization": cal.polarization,
                "reference_probe_id": cal.reference_probe_id,
                "avg_phase_offset_deg": round(avg_phase, 2),
                "avg_group_delay_ns": round(avg_delay, 3),
                "num_freq_points": len(cal.frequency_points_mhz) if cal.frequency_points_mhz else 0
            }
        ))

    # 计算相位漂移趋势
    trends = None
    if len(calibrations) >= 3:
        first_cal = calibrations[-1]
        last_cal = calibrations[0]
        if first_cal.phase_offset_deg and last_cal.phase_offset_deg:
            first_avg = sum(first_cal.phase_offset_deg) / len(first_cal.phase_offset_deg)
            last_avg = sum(last_cal.phase_offset_deg) / len(last_cal.phase_offset_deg)
            time_diff_days = (last_cal.calibrated_at - first_cal.calibrated_at).days
            if time_diff_days > 0:
                drift_per_month = (last_avg - first_avg) / (time_diff_days / 30.0)
                trends = {
                    "phase_drift_deg_per_month": round(drift_per_month, 3),
                    "stability_rating": "stable" if abs(drift_per_month) < 1.0 else "drifting"
                }

    return CalibrationHistoryResponse(
        probe_id=probe_id,
        history=history_items,
        trends=trends
    )


# ==================== Polarization Calibration Endpoints (TASK-P06) ====================

@router.post("/polarization/start", response_model=CalibrationJobResponse, status_code=202)
async def start_polarization_calibration(
    request: StartPolarizationCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动极化校准任务

    极化校准测量探头的交叉极化隔离度或圆极化轴比。

    **校准内容**:
    - 线极化: V-H 隔离度 (XPD, dB)
    - 圆极化: 轴比 (AR, dB)

    **验收标准**:
    - 线极化: XPD > 20 dB
    - 圆极化: 轴比 < 3 dB
    """
    job_id = uuid4()

    # 计算预估时间
    num_probes = len(request.probe_ids)
    estimated_minutes = num_probes * 5.0  # 极化校准约 5 分钟/探头

    # 生成频率点
    freq_range = request.frequency_range
    freq_points = []
    freq = freq_range.start_mhz
    while freq <= freq_range.stop_mhz:
        freq_points.append(freq)
        freq += freq_range.step_mhz

    # 为每个探头创建校准记录（mock 数据）
    for probe_id in request.probe_ids:
        import random

        if request.probe_type.value in ("dual_linear", "dual_slant"):
            # 线极化: 生成 XPD 数据
            base_xpd = 28.0  # 典型 XPD 约 28 dB
            probe_variation = (probe_id % 10 - 5) * 0.5

            v_to_h_isolations = [
                base_xpd + probe_variation + random.gauss(0, 1.0)
                for _ in freq_points
            ]
            h_to_v_isolations = [
                base_xpd + probe_variation + random.gauss(0, 1.0)
                for _ in freq_points
            ]

            avg_v_to_h = sum(v_to_h_isolations) / len(v_to_h_isolations)
            avg_h_to_v = sum(h_to_v_isolations) / len(h_to_v_isolations)

            calibration = ProbePolarizationCalibration(
                probe_id=probe_id,
                probe_type=request.probe_type.value,
                v_to_h_isolation_db=avg_v_to_h,
                h_to_v_isolation_db=avg_h_to_v,
                frequency_points_mhz=freq_points,
                isolation_vs_frequency_db=v_to_h_isolations,
                reference_antenna=request.reference_antenna_id,
                positioner=request.positioner_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=request.calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=180),
                status=CalibrationStatus.VALID
            )
        else:
            # 圆极化: 生成轴比数据
            base_ar = 1.5  # 典型轴比约 1.5 dB
            probe_variation = abs((probe_id % 10 - 5) * 0.1)

            axial_ratios = [
                base_ar + probe_variation + abs(random.gauss(0, 0.2))
                for _ in freq_points
            ]

            avg_ar = sum(axial_ratios) / len(axial_ratios)
            hand = "LHCP" if probe_id % 2 == 0 else "RHCP"

            calibration = ProbePolarizationCalibration(
                probe_id=probe_id,
                probe_type=request.probe_type.value,
                polarization_hand=hand,
                axial_ratio_db=avg_ar,
                frequency_points_mhz=freq_points,
                axial_ratio_vs_frequency_db=axial_ratios,
                reference_antenna=request.reference_antenna_id,
                positioner=request.positioner_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=request.calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=180),
                status=CalibrationStatus.VALID
            )

        db.add(calibration)

    db.commit()

    return CalibrationJobResponse(
        calibration_job_id=job_id,
        status=CalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=estimated_minutes,
        message=f"Polarization calibration completed for {num_probes} probes, type={request.probe_type.value}"
    )


@router.get("/polarization/{probe_id}", response_model=PolarizationCalibrationResponse)
def get_polarization_calibration(
    probe_id: int,
    db: Session = Depends(get_db)
):
    """
    获取探头的最新极化校准数据

    Args:
        probe_id: 探头 ID (0-63)

    Returns:
        PolarizationCalibrationResponse: 极化校准数据
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    calibration = db.query(ProbePolarizationCalibration).filter(
        ProbePolarizationCalibration.probe_id == probe_id
    ).order_by(desc(ProbePolarizationCalibration.calibrated_at)).first()

    if not calibration:
        raise HTTPException(
            status_code=404,
            detail=f"No polarization calibration found for probe {probe_id}"
        )

    return calibration


@router.get("/polarization/{probe_id}/history", response_model=CalibrationHistoryResponse)
def get_polarization_calibration_history(
    probe_id: int,
    limit: int = Query(20, ge=1, le=100, description="返回记录数量"),
    db: Session = Depends(get_db)
):
    """
    获取探头的极化校准历史记录

    Args:
        probe_id: 探头 ID (0-63)
        limit: 返回记录数量

    Returns:
        CalibrationHistoryResponse: 校准历史列表
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    calibrations = db.query(ProbePolarizationCalibration).filter(
        ProbePolarizationCalibration.probe_id == probe_id
    ).order_by(
        desc(ProbePolarizationCalibration.calibrated_at)
    ).limit(limit).all()

    history_items = []
    for cal in calibrations:
        if cal.probe_type in ("dual_linear", "dual_slant"):
            # 线极化
            min_xpd = min(
                cal.v_to_h_isolation_db or 0,
                cal.h_to_v_isolation_db or 0
            )
            summary = {
                "probe_type": cal.probe_type,
                "v_to_h_isolation_db": round(cal.v_to_h_isolation_db or 0, 2),
                "h_to_v_isolation_db": round(cal.h_to_v_isolation_db or 0, 2),
                "min_xpd_db": round(min_xpd, 2),
                "num_freq_points": len(cal.frequency_points_mhz) if cal.frequency_points_mhz else 0
            }
        else:
            # 圆极化
            summary = {
                "probe_type": cal.probe_type,
                "polarization_hand": cal.polarization_hand,
                "axial_ratio_db": round(cal.axial_ratio_db or 0, 2),
                "num_freq_points": len(cal.frequency_points_mhz) if cal.frequency_points_mhz else 0
            }

        history_items.append(CalibrationHistoryItem(
            calibration_id=cal.id,
            calibration_type="polarization",
            calibrated_at=cal.calibrated_at,
            calibrated_by=cal.calibrated_by,
            status=cal.status if isinstance(cal.status, str) else cal.status.value,
            summary=summary
        ))

    return CalibrationHistoryResponse(
        probe_id=probe_id,
        history=history_items,
        trends=None  # 极化校准通常稳定，无需趋势分析
    )


# ==================== Pattern Calibration Endpoints (TASK-P07) ====================

@router.post("/pattern/start", response_model=CalibrationJobResponse, status_code=202)
async def start_pattern_calibration(
    request: StartPatternCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动方向图校准任务

    方向图校准测量探头的 3D 辐射方向图。

    **校准内容**:
    - 方向图数据: 增益 vs 角度 (azimuth x elevation)
    - HPBW: 半功率波束宽度 (方位面和俯仰面)
    - 峰值增益和方向
    - 前后比

    **验收标准**:
    - 远场条件: d > 2D²/λ
    - 峰值增益 > 0 dBi
    """
    job_id = uuid4()

    # 计算预估时间
    num_probes = len(request.probe_ids)
    num_polarizations = len(request.polarizations)
    num_az = int(360 / request.azimuth_step_deg)
    num_el = int(180 / request.elevation_step_deg) + 1
    num_points = num_az * num_el

    # 约 0.5 秒/测量点
    estimated_minutes = (num_probes * num_polarizations * num_points * 0.5) / 60

    # 生成角度网格
    azimuth_deg = list(np.arange(0, 360, request.azimuth_step_deg))
    elevation_deg = list(np.arange(0, 181, request.elevation_step_deg))

    # 远场条件验证
    antenna_diameter_m = 0.1  # 假设探头口径约 0.1m
    wavelength_m = 299792458.0 / (request.frequency_mhz * 1e6)
    min_far_field_distance = 2 * (antenna_diameter_m ** 2) / wavelength_m

    warnings = []
    if request.measurement_distance_m < min_far_field_distance:
        warnings.append(
            f"Measurement distance {request.measurement_distance_m}m may not satisfy "
            f"far-field condition (min: {min_far_field_distance:.2f}m)"
        )

    # 为每个探头和极化创建校准记录 (mock 数据)
    for probe_id in request.probe_ids:
        for polarization in request.polarizations:
            import random

            # 探头间的变异
            probe_variation = (probe_id % 10 - 5) * 0.2

            # 基础增益
            base_gain = 5.0 + probe_variation

            # 方向图参数
            hpbw_target = 60.0
            sigma = hpbw_target / (2 * np.sqrt(2 * np.log(2)))

            # 生成方向图数据
            gain_pattern = []
            for elev in elevation_deg:
                for az in azimuth_deg:
                    az_diff = min(abs(az), 360 - abs(az))
                    el_diff = abs(elev - 90)

                    az_factor = np.exp(-(az_diff ** 2) / (2 * sigma ** 2))
                    el_factor = np.exp(-(el_diff ** 2) / (2 * sigma ** 2))

                    gain = base_gain + 10 * np.log10(az_factor * el_factor + 0.001)
                    gain += random.gauss(0, 0.3)
                    gain_pattern.append(round(gain, 2))

            # 计算参数
            peak_gain = max(gain_pattern)
            peak_idx = gain_pattern.index(peak_gain)
            peak_elev_idx = peak_idx // len(azimuth_deg)
            peak_az_idx = peak_idx % len(azimuth_deg)

            # HPBW 计算 (简化: 使用目标值 + 随机偏差)
            hpbw_azimuth = hpbw_target + random.gauss(0, 5)
            hpbw_elevation = hpbw_target + random.gauss(0, 5)

            # 前后比 (典型值约 15-20 dB)
            ftb_ratio = 15.0 + random.gauss(0, 2)

            calibration = ProbePattern(
                probe_id=probe_id,
                polarization=polarization.value,
                frequency_mhz=request.frequency_mhz,
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
                gain_pattern_dbi=gain_pattern,
                peak_gain_dbi=round(peak_gain, 2),
                peak_azimuth_deg=azimuth_deg[peak_az_idx],
                peak_elevation_deg=elevation_deg[peak_elev_idx],
                hpbw_azimuth_deg=round(hpbw_azimuth, 1),
                hpbw_elevation_deg=round(hpbw_elevation, 1),
                front_to_back_ratio_db=round(ftb_ratio, 1),
                reference_antenna=request.reference_antenna_id,
                turntable=request.turntable_id,
                measurement_distance_m=request.measurement_distance_m,
                measured_at=datetime.utcnow(),
                measured_by=request.calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=365),
                status=CalibrationStatus.VALID
            )

            db.add(calibration)

    db.commit()

    message = f"Pattern calibration completed for {num_probes} probes, {num_polarizations} polarizations"
    if warnings:
        message += f" (warnings: {len(warnings)})"

    return CalibrationJobResponse(
        calibration_job_id=job_id,
        status=CalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=estimated_minutes,
        message=message
    )


@router.get("/pattern/{probe_id}", response_model=List[PatternCalibrationResponse])
def get_pattern_calibration(
    probe_id: int,
    frequency_mhz: Optional[float] = Query(None, description="筛选特定频率"),
    db: Session = Depends(get_db)
):
    """
    获取探头的方向图校准数据

    Args:
        probe_id: 探头 ID (0-63)
        frequency_mhz: 可选的频率筛选

    Returns:
        List[PatternCalibrationResponse]: 方向图校准数据列表
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    query = db.query(ProbePattern).filter(
        ProbePattern.probe_id == probe_id
    )

    if frequency_mhz is not None:
        query = query.filter(ProbePattern.frequency_mhz == frequency_mhz)

    calibrations = query.order_by(desc(ProbePattern.measured_at)).all()

    if not calibrations:
        raise HTTPException(
            status_code=404,
            detail=f"No pattern calibration found for probe {probe_id}"
            + (f" at {frequency_mhz} MHz" if frequency_mhz else "")
        )

    return calibrations


# ==================== Link Calibration Endpoints (TASK-P08) ====================

@router.post("/link/start", response_model=CalibrationJobResponse, status_code=202)
async def start_link_calibration(
    request: StartLinkCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    启动链路校准任务

    链路校准验证整个测量链路的端到端性能。

    **校准内容**:
    - 使用标准 DUT (偶极子/喇叭天线/贴片天线) 验证测量精度
    - 计算测量增益与已知增益的偏差
    - 可选: 探头级链路损耗和相位偏移校准

    **验收标准**: |偏差| < 阈值 (默认 1.0 dB)

    **校准类型**:
    - weekly_check: 每周例行检查
    - pre_test: 测试前校准
    - post_maintenance: 维护后校准
    """
    import random

    job_id = uuid4()

    # 标准 DUT 信息
    known_gain_dbi = request.standard_dut.known_gain_dbi

    # 模拟测量结果
    # 系统误差 + 随机噪声
    system_offset = random.gauss(0, 0.3)
    measured_gain = known_gain_dbi + system_offset + random.gauss(0, 0.1)
    deviation = measured_gain - known_gain_dbi

    # 验证
    is_pass = abs(deviation) <= request.threshold_db

    # 探头级校准数据
    probe_calibrations = []
    target_probes = request.probe_ids if request.probe_ids else list(range(0, 32))

    for probe_id in target_probes:
        probe_variation = (probe_id % 10 - 5) * 0.05
        probe_calibrations.append({
            "probe_id": probe_id,
            "link_loss_db": round(30.0 + probe_variation + random.gauss(0, 0.2), 2),
            "phase_offset_deg": round(random.uniform(-180, 180), 1)
        })

    # 创建校准记录
    calibration = LinkCalibration(
        calibration_type=request.calibration_type.value,
        standard_dut_type=request.standard_dut.dut_type,
        standard_dut_model=request.standard_dut.model,
        standard_dut_serial=request.standard_dut.serial,
        known_gain_dbi=known_gain_dbi,
        frequency_mhz=request.frequency_mhz,
        measured_gain_dbi=round(measured_gain, 2),
        deviation_db=round(deviation, 3),
        probe_link_calibrations=probe_calibrations,
        validation_pass=is_pass,
        threshold_db=request.threshold_db,
        calibrated_at=datetime.utcnow(),
        calibrated_by=request.calibrated_by
    )

    db.add(calibration)
    db.commit()

    result_str = "PASS" if is_pass else "FAIL"
    message = f"Link calibration completed: {result_str}, deviation={deviation:.3f} dB"

    return CalibrationJobResponse(
        calibration_job_id=job_id,
        status=CalibrationJobStatus.COMPLETED,
        estimated_duration_minutes=2.0,
        message=message
    )


@router.get("/link/latest", response_model=LinkCalibrationResponse)
def get_latest_link_calibration(
    calibration_type: Optional[str] = Query(None, description="筛选校准类型"),
    db: Session = Depends(get_db)
):
    """
    获取最新的链路校准数据

    Args:
        calibration_type: 可选的校准类型筛选 (weekly_check, pre_test, post_maintenance)

    Returns:
        LinkCalibrationResponse: 链路校准数据
    """
    query = db.query(LinkCalibration)

    if calibration_type:
        query = query.filter(LinkCalibration.calibration_type == calibration_type)

    calibration = query.order_by(desc(LinkCalibration.calibrated_at)).first()

    if not calibration:
        raise HTTPException(
            status_code=404,
            detail="No link calibration found"
            + (f" for type {calibration_type}" if calibration_type else "")
        )

    return calibration


@router.get("/link/history", response_model=List[LinkCalibrationResponse])
def get_link_calibration_history(
    calibration_type: Optional[str] = Query(None, description="筛选校准类型"),
    limit: int = Query(20, ge=1, le=100, description="返回记录数量"),
    db: Session = Depends(get_db)
):
    """
    获取链路校准历史记录

    Args:
        calibration_type: 可选的校准类型筛选
        limit: 返回记录数量

    Returns:
        List[LinkCalibrationResponse]: 链路校准历史列表
    """
    query = db.query(LinkCalibration)

    if calibration_type:
        query = query.filter(LinkCalibration.calibration_type == calibration_type)

    calibrations = query.order_by(desc(LinkCalibration.calibrated_at)).limit(limit).all()

    return calibrations


@router.get("/link/validity")
def check_link_validity(
    db: Session = Depends(get_db)
):
    """
    检查链路校准有效性

    链路校准有效期为 7 天。

    Returns:
        链路校准有效性状态
    """
    latest = db.query(LinkCalibration).order_by(
        desc(LinkCalibration.calibrated_at)
    ).first()

    if not latest:
        return {
            "status": "unknown",
            "message": "No link calibration found"
        }

    now = datetime.utcnow()
    valid_until = latest.calibrated_at + timedelta(days=7)

    if now > valid_until:
        days_overdue = (now - valid_until).days
        return {
            "status": "expired",
            "calibration_id": str(latest.id),
            "calibrated_at": latest.calibrated_at.isoformat(),
            "days_overdue": days_overdue,
            "validation_pass": latest.validation_pass,
            "message": f"Link calibration expired {days_overdue} days ago"
        }

    days_remaining = (valid_until - now).days

    if days_remaining <= 2:
        return {
            "status": "expiring_soon",
            "calibration_id": str(latest.id),
            "calibrated_at": latest.calibrated_at.isoformat(),
            "valid_until": valid_until.isoformat(),
            "days_remaining": days_remaining,
            "validation_pass": latest.validation_pass,
            "message": f"Link calibration expires in {days_remaining} days"
        }

    return {
        "status": "valid",
        "calibration_id": str(latest.id),
        "calibrated_at": latest.calibrated_at.isoformat(),
        "valid_until": valid_until.isoformat(),
        "days_remaining": days_remaining,
        "validation_pass": latest.validation_pass,
        "deviation_db": latest.deviation_db
    }


# ==================== Validity Management Endpoints (TASK-P09) ====================

from app.services.probe_calibration_service import CalibrationValidityService

# 创建有效性服务实例
validity_service = CalibrationValidityService(expiring_threshold_days=7)


@router.get("/validity/report", response_model=CalibrationValidityReport)
def get_validity_report(
    probe_ids: Optional[str] = Query(None, description="探头 ID 列表 (逗号分隔)，为空表示检查前 32 个探头"),
    db: Session = Depends(get_db)
):
    """
    获取校准有效性报告

    报告所有探头的校准状态，包括已过期和即将过期的校准。

    **返回内容**:
    - 总探头数、有效/过期/即将过期的探头数
    - 已过期的校准列表
    - 即将过期的校准列表
    - 校准建议 (优先级: critical > high > medium)
    """
    # 解析探头 ID
    if probe_ids:
        try:
            ids = [int(x.strip()) for x in probe_ids.split(",")]
            for pid in ids:
                if pid < 0 or pid > 63:
                    raise HTTPException(status_code=400, detail=f"Invalid probe_id: {pid}")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid probe_ids format")
    else:
        # 默认检查前 32 个探头
        ids = list(range(32))

    report = validity_service.generate_validity_report(db, probe_ids=ids)

    return CalibrationValidityReport(**report)


@router.get("/validity/expiring")
def get_expiring_calibrations(
    days: int = Query(7, ge=1, le=30, description="过期阈值天数"),
    calibration_type: Optional[str] = Query(None, description="校准类型筛选"),
    db: Session = Depends(get_db)
):
    """
    获取即将过期的校准列表

    返回在指定天数内即将过期的所有校准记录。

    **用途**:
    - 校准计划安排
    - 提前预警
    - 维护排期
    """
    if calibration_type:
        valid_types = ["amplitude", "phase", "polarization", "pattern", "link"]
        if calibration_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid calibration_type. Must be one of: {', '.join(valid_types)}"
            )

    expiring = validity_service.get_expiring_calibrations(
        db=db,
        days_threshold=days,
        calibration_type=calibration_type
    )

    return {
        "days_threshold": days,
        "count": len(expiring),
        "calibrations": expiring
    }


@router.get("/validity/expired")
def get_expired_calibrations(
    calibration_type: Optional[str] = Query(None, description="校准类型筛选"),
    db: Session = Depends(get_db)
):
    """
    获取已过期的校准列表

    返回所有已过期但未作废的校准记录。

    **用途**:
    - 识别需要重新校准的探头
    - 合规性检查
    - 校准优先级排序
    """
    if calibration_type:
        valid_types = ["amplitude", "phase", "polarization", "pattern", "link"]
        if calibration_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid calibration_type. Must be one of: {', '.join(valid_types)}"
            )

    expired = validity_service.get_expired_calibrations(
        db=db,
        calibration_type=calibration_type
    )

    return {
        "count": len(expired),
        "calibrations": expired
    }


@router.get("/validity/{probe_id}", response_model=ProbeCalibrationStatus)
def get_probe_validity(
    probe_id: int,
    db: Session = Depends(get_db)
):
    """
    获取单个探头的校准有效性状态

    返回探头的所有校准类型的有效性状态，包括:
    - amplitude: 幅度校准 (有效期 90 天)
    - phase: 相位校准 (有效期 90 天)
    - polarization: 极化校准 (有效期 180 天)
    - pattern: 方向图校准 (有效期 365 天)
    - link: 链路校准 (有效期 7 天)

    **状态值**:
    - valid: 有效
    - expiring_soon: 即将过期 (7 天内)
    - expired: 已过期
    - unknown: 无校准数据
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    status = validity_service.check_validity(db, probe_id)

    return ProbeCalibrationStatus(
        probe_id=probe_id,
        amplitude=status.get("amplitude"),
        phase=status.get("phase"),
        polarization=status.get("polarization"),
        pattern=status.get("pattern"),
        link=status.get("link"),
        overall_status=status.get("overall_status", "unknown")
    )


@router.post("/invalidate/{calibration_type}/{calibration_id}")
def invalidate_calibration(
    calibration_type: str,
    calibration_id: UUID,
    request: InvalidateCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    作废指定的校准记录

    作废后，该校准记录将不再被纳入有效性计算。
    需要重新执行校准来恢复有效性。

    **支持的校准类型**:
    - amplitude: 幅度校准
    - phase: 相位校准
    - polarization: 极化校准
    - pattern: 方向图校准
    - link: 链路校准

    Args:
        calibration_type: 校准类型
        calibration_id: 校准记录 ID
        request: 作废原因 (min 5 chars, max 500 chars)
    """
    valid_types = ["amplitude", "phase", "polarization", "pattern", "link"]
    if calibration_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid calibration_type. Must be one of: {', '.join(valid_types)}"
        )

    result = validity_service.invalidate_calibration(
        db=db,
        calibration_type=calibration_type,
        calibration_id=str(calibration_id),
        reason=request.reason
    )

    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])

    return result


# ==================== Comprehensive Data Query ====================

@router.get("/{probe_id}/data", response_model=ProbeCalibrationDataResponse)
def get_probe_calibration_data(
    probe_id: int,
    db: Session = Depends(get_db)
):
    """
    获取探头的综合校准数据

    返回探头的所有校准数据和有效性状态。

    **包含数据**:
    - amplitude_calibration: 最新幅度校准数据
    - phase_calibration: 最新相位校准数据
    - polarization_calibration: 最新极化校准数据
    - pattern_calibrations: 所有频率的方向图校准数据
    - link_calibration: 最新链路校准数据
    - validity_status: 综合有效性状态
    """
    if probe_id < 0 or probe_id > 63:
        raise HTTPException(status_code=400, detail="probe_id must be between 0 and 63")

    # 获取幅度校准
    amplitude = db.query(ProbeAmplitudeCalibration).filter(
        ProbeAmplitudeCalibration.probe_id == probe_id
    ).order_by(desc(ProbeAmplitudeCalibration.calibrated_at)).first()

    # 获取相位校准
    phase = db.query(ProbePhaseCalibration).filter(
        ProbePhaseCalibration.probe_id == probe_id
    ).order_by(desc(ProbePhaseCalibration.calibrated_at)).first()

    # 获取极化校准
    polarization = db.query(ProbePolarizationCalibration).filter(
        ProbePolarizationCalibration.probe_id == probe_id
    ).order_by(desc(ProbePolarizationCalibration.calibrated_at)).first()

    # 获取方向图校准 (可能有多个频率)
    patterns = db.query(ProbePattern).filter(
        ProbePattern.probe_id == probe_id
    ).order_by(desc(ProbePattern.measured_at)).all()

    # 获取链路校准 (全局)
    link = db.query(LinkCalibration).order_by(
        desc(LinkCalibration.calibrated_at)
    ).first()

    # 获取有效性状态
    status = validity_service.check_validity(db, probe_id)

    validity_status = ProbeCalibrationStatus(
        probe_id=probe_id,
        amplitude=status.get("amplitude"),
        phase=status.get("phase"),
        polarization=status.get("polarization"),
        pattern=status.get("pattern"),
        link=status.get("link"),
        overall_status=status.get("overall_status", "unknown")
    )

    return ProbeCalibrationDataResponse(
        probe_id=probe_id,
        amplitude_calibration=amplitude,
        phase_calibration=phase,
        polarization_calibration=polarization,
        pattern_calibrations=patterns if patterns else None,
        link_calibration=link,
        validity_status=validity_status
    )
