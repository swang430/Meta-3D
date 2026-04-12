"""
Path Loss Calibration API Endpoints

探头路损校准和 RF 链路校准 API

CAL-10: 新校准流程 API 端点
CAL-02: RF Switch Matrix 校准 (2026-01-26 新增)
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.database import get_db
from app.models.chamber import ChamberConfiguration
from app.models.probe_calibration import (
    ProbePathLossCalibration,
    RFChainCalibration,
    MultiFrequencyPathLoss,
)
from app.schemas.probe_calibration import (
    StartProbePathLossCalibrationRequest,
    ProbePathLossCalibrationResponse,
    StartRFChainCalibrationRequest,
    RFChainCalibrationResponse,
    StartMultiFrequencyPathLossRequest,
    MultiFrequencyPathLossResponse,
    ChamberCalibrationSummary,
    ChainTypeEnum,
    PolarizationType,
    CalibrationJobResponse,
    CalibrationJobStatus,
)
from app.services.path_loss_calibration_service import (
    ProbePathLossCalibrationService,
    RFChainCalibrationService,
    MultiFrequencyPathLossService,
)
from app.services.calibration_orchestrator import (
    CalibrationOrchestrator,
    CalibrationItem,
)
from app.services.measurement_compensation import (
    MeasurementCompensator,
    get_system_compensation_summary,
)
from app.services.rf_switch_calibration_service import (
    RFSwitchCalibrationService,
)
from app.services.e2e_calibration_service import (
    E2ECalibrationService,
)
from app.services.phase_calibration_service import (
    PhaseCalibrationService,
)
from app.services.ce_internal_calibration_service import (
    CEInternalCalibrationService,
    CECalibrationType,
)
from app.services.relative_calibration_service import (
    RelativeCalibrationService,
    CalibrationType as RelativeCalibrationType,
)

router = APIRouter(prefix="/calibration/path-loss", tags=["Path Loss Calibration"])
switch_router = APIRouter(prefix="/calibration/rf-switch", tags=["RF Switch Calibration"])
e2e_router = APIRouter(prefix="/calibration/e2e", tags=["E2E Calibration"])
phase_router = APIRouter(prefix="/calibration/phase", tags=["Phase Calibration"])
ce_router = APIRouter(prefix="/calibration/ce", tags=["CE Calibration"])
baseline_router = APIRouter(prefix="/calibration/baseline", tags=["Relative Calibration"])


# ==================== 探头路损校准 ====================

@router.post("/start", response_model=CalibrationJobResponse)
async def start_path_loss_calibration(
    request: StartProbePathLossCalibrationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    启动探头路损校准

    使用 SGH 测量每个探头的空间路径损耗。

    注意:
    - 确保 SGH 已放置在静区中心
    - 校准前需要完成 VNA 预热和校准
    """
    # 验证暗室配置
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == request.chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    # 启动校准
    service = ProbePathLossCalibrationService(db, use_mock=True)

    result = await service.start_calibration(
        chamber_id=request.chamber_id,
        frequency_mhz=request.frequency_mhz,
        sgh_model=request.sgh_model,
        sgh_gain_dbi=request.sgh_gain_dbi,
        sgh_serial=request.sgh_serial,
        vna_id=request.vna_id,
        cable_loss_db=request.cable_loss_db,
        probe_ids=request.probe_ids,
        polarizations=request.polarizations,
        calibrated_by=request.calibrated_by
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return CalibrationJobResponse(
        calibration_job_id=UUID(result.data["calibration_id"]),
        status=CalibrationJobStatus.COMPLETED,
        message=result.message
    )


@router.get("/latest/{chamber_id}", response_model=ProbePathLossCalibrationResponse)
def get_latest_path_loss_calibration(
    chamber_id: UUID,
    frequency_mhz: Optional[float] = Query(None, description="目标频率 (MHz)"),
    db: Session = Depends(get_db)
):
    """
    获取最新的路损校准数据

    Args:
        chamber_id: 暗室配置 ID
        frequency_mhz: 目标频率，用于查找最接近的校准
    """
    service = ProbePathLossCalibrationService(db, use_mock=True)
    calibration = service.get_latest_calibration(chamber_id, frequency_mhz)

    if not calibration:
        raise HTTPException(status_code=404, detail="No path loss calibration found")

    return calibration


@router.get("/probe/{chamber_id}/{probe_id}")
def get_probe_path_loss(
    chamber_id: UUID,
    probe_id: int,
    polarization: str = Query("V", description="极化类型: V 或 H"),
    frequency_mhz: Optional[float] = Query(None, description="目标频率"),
    db: Session = Depends(get_db)
):
    """
    获取特定探头的路损值

    用于测量补偿。
    """
    service = ProbePathLossCalibrationService(db, use_mock=True)
    path_loss = service.get_path_loss_for_probe(
        chamber_id, probe_id, polarization, frequency_mhz
    )

    if path_loss is None:
        raise HTTPException(status_code=404, detail="No path loss data found for this probe")

    return {
        "probe_id": probe_id,
        "polarization": polarization,
        "path_loss_db": path_loss,
        "frequency_mhz": frequency_mhz
    }


# ==================== RF 链路校准 ====================

@router.post("/rf-chain/uplink", response_model=CalibrationJobResponse)
async def calibrate_uplink_chain(
    request: StartRFChainCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    校准上行链路 (LNA)

    测量探头 → LNA → 信道仿真器的总增益。
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == request.chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    if not chamber.has_lna:
        return CalibrationJobResponse(
            calibration_job_id=UUID(int=0),
            status=CalibrationJobStatus.COMPLETED,
            message="Chamber does not have LNA, no calibration needed"
        )

    service = RFChainCalibrationService(db, use_mock=True)
    result = await service.calibrate_uplink(
        chamber_id=request.chamber_id,
        frequency_mhz=request.frequency_mhz,
        vna_id=request.vna_id,
        power_meter_id=request.power_meter_id,
        calibrated_by=request.calibrated_by
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return CalibrationJobResponse(
        calibration_job_id=UUID(result.data["calibration_id"]),
        status=CalibrationJobStatus.COMPLETED,
        message=result.message
    )


@router.post("/rf-chain/downlink", response_model=CalibrationJobResponse)
async def calibrate_downlink_chain(
    request: StartRFChainCalibrationRequest,
    db: Session = Depends(get_db)
):
    """
    校准下行链路 (PA)

    测量信道仿真器 → PA → 探头的总增益。
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == request.chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    if not chamber.has_pa:
        return CalibrationJobResponse(
            calibration_job_id=UUID(int=0),
            status=CalibrationJobStatus.COMPLETED,
            message="Chamber does not have PA, no calibration needed"
        )

    service = RFChainCalibrationService(db, use_mock=True)
    result = await service.calibrate_downlink(
        chamber_id=request.chamber_id,
        frequency_mhz=request.frequency_mhz,
        vna_id=request.vna_id,
        power_meter_id=request.power_meter_id,
        calibrated_by=request.calibrated_by
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return CalibrationJobResponse(
        calibration_job_id=UUID(result.data["calibration_id"]),
        status=CalibrationJobStatus.COMPLETED,
        message=result.message
    )


@router.get("/rf-chain/uplink/{chamber_id}", response_model=RFChainCalibrationResponse)
def get_uplink_calibration(
    chamber_id: UUID,
    frequency_mhz: Optional[float] = Query(None),
    db: Session = Depends(get_db)
):
    """获取上行链路校准数据"""
    service = RFChainCalibrationService(db, use_mock=True)
    calibration = service.get_latest_uplink_calibration(chamber_id, frequency_mhz)

    if not calibration:
        raise HTTPException(status_code=404, detail="No uplink calibration found")

    return calibration


@router.get("/rf-chain/downlink/{chamber_id}", response_model=RFChainCalibrationResponse)
def get_downlink_calibration(
    chamber_id: UUID,
    frequency_mhz: Optional[float] = Query(None),
    db: Session = Depends(get_db)
):
    """获取下行链路校准数据"""
    service = RFChainCalibrationService(db, use_mock=True)
    calibration = service.get_latest_downlink_calibration(chamber_id, frequency_mhz)

    if not calibration:
        raise HTTPException(status_code=404, detail="No downlink calibration found")

    return calibration


# ==================== 多频点校准 ====================

@router.post("/multi-frequency/start", response_model=CalibrationJobResponse)
async def start_multi_frequency_calibration(
    request: StartMultiFrequencyPathLossRequest,
    db: Session = Depends(get_db)
):
    """
    启动多频点路损校准

    扫频测量路损，支持后续频率插值。
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == request.chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    service = MultiFrequencyPathLossService(db, use_mock=True)
    result = await service.calibrate_frequency_sweep(
        chamber_id=request.chamber_id,
        probe_ids=request.probe_ids,
        polarization=request.polarization,
        freq_start_mhz=request.freq_start_mhz,
        freq_stop_mhz=request.freq_stop_mhz,
        freq_step_mhz=request.freq_step_mhz,
        sgh_model=request.sgh_model,
        sgh_gain_dbi=request.sgh_gain_dbi,
        vna_id=request.vna_id,
        calibrated_by=request.calibrated_by
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return CalibrationJobResponse(
        calibration_job_id=UUID(result.data["calibration_ids"][0]) if result.data.get("calibration_ids") else UUID(int=0),
        status=CalibrationJobStatus.COMPLETED,
        message=result.message
    )


@router.get("/multi-frequency/{chamber_id}/{probe_id}")
def get_path_loss_at_frequency(
    chamber_id: UUID,
    probe_id: int,
    frequency_mhz: float = Query(..., description="目标频率 (MHz)"),
    polarization: str = Query("V", description="极化类型"),
    db: Session = Depends(get_db)
):
    """
    获取指定频率的路损值 (支持插值)
    """
    service = MultiFrequencyPathLossService(db, use_mock=True)
    path_loss = service.get_path_loss_at_frequency(
        chamber_id, probe_id, polarization, frequency_mhz
    )

    if path_loss is None:
        raise HTTPException(status_code=404, detail="No multi-frequency calibration found")

    return {
        "probe_id": probe_id,
        "polarization": polarization,
        "frequency_mhz": frequency_mhz,
        "path_loss_db": path_loss,
        "interpolated": True
    }


# ==================== 校准编排 ====================

orchestrator_router = APIRouter(prefix="/calibration/orchestrator", tags=["Calibration Orchestrator"])


@orchestrator_router.get("/required/{chamber_id}")
def get_required_calibrations(
    chamber_id: UUID,
    db: Session = Depends(get_db)
):
    """
    获取暗室配置所需的校准项目

    根据暗室硬件配置自动推断需要的校准项目。
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    orchestrator = CalibrationOrchestrator(db, use_mock=True)
    required = orchestrator.get_required_calibrations(chamber)
    optional = orchestrator.get_optional_calibrations(chamber)

    return {
        "chamber_id": str(chamber_id),
        "chamber_name": chamber.name,
        "required_calibrations": [item.value for item in required],
        "optional_calibrations": [item.value for item in optional]
    }


@orchestrator_router.get("/status/{chamber_id}")
def get_calibration_status(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0, description="参考频率 (MHz)"),
    db: Session = Depends(get_db)
):
    """
    检查暗室的校准状态

    返回每个校准项的当前状态和有效期。
    """
    orchestrator = CalibrationOrchestrator(db, use_mock=True)
    statuses = orchestrator.check_calibration_status(chamber_id, frequency_mhz)

    if not statuses:
        raise HTTPException(status_code=404, detail="Chamber not found")

    return {
        "chamber_id": str(chamber_id),
        "frequency_mhz": frequency_mhz,
        "calibrations": {
            item.value: status.to_dict()
            for item, status in statuses.items()
        }
    }


@orchestrator_router.get("/plan/{chamber_id}")
def get_calibration_plan(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0),
    force_recalibrate: bool = Query(False, description="是否强制重新校准所有项目"),
    db: Session = Depends(get_db)
):
    """
    生成校准计划

    确定需要执行的校准项目和执行顺序。
    """
    orchestrator = CalibrationOrchestrator(db, use_mock=True)
    plan = orchestrator.get_calibration_plan(chamber_id, frequency_mhz, force_recalibrate)

    if "chamber_id" not in plan:
        raise HTTPException(status_code=404, detail="Failed to generate calibration plan")

    return plan


@orchestrator_router.post("/execute/{chamber_id}")
async def execute_calibration_plan(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0),
    calibrated_by: str = Query(..., description="校准人员"),
    sgh_model: str = Query("Generic SGH", description="SGH 型号"),
    sgh_gain_dbi: float = Query(10.0, description="SGH 增益 (dBi)"),
    items: Optional[List[str]] = Query(None, description="要执行的校准项目，None 表示按计划执行"),
    db: Session = Depends(get_db)
):
    """
    执行校准计划

    按顺序执行所有需要的校准项目。
    """
    orchestrator = CalibrationOrchestrator(db, use_mock=True)

    # 确定要执行的项目
    if items:
        calibration_items = [CalibrationItem(item) for item in items]
    else:
        plan = orchestrator.get_calibration_plan(chamber_id, frequency_mhz)
        calibration_items = [
            CalibrationItem(item)
            for item in plan.get("items_to_calibrate", [])
        ]

    if not calibration_items:
        return {
            "message": "No calibration items to execute",
            "chamber_id": str(chamber_id)
        }

    result = await orchestrator.execute_calibration_plan(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        items=calibration_items,
        calibrated_by=calibrated_by,
        sgh_model=sgh_model,
        sgh_gain_dbi=sgh_gain_dbi
    )

    return result


# ==================== 测量补偿 ====================

compensation_router = APIRouter(prefix="/calibration/compensation", tags=["Measurement Compensation"])


@compensation_router.get("/trp/{chamber_id}/{probe_id}")
def get_trp_compensation(
    chamber_id: UUID,
    probe_id: int,
    polarization: str = Query("V"),
    frequency_mhz: float = Query(3500.0),
    db: Session = Depends(get_db)
):
    """
    获取 TRP 测量补偿值

    用于测量前查询补偿参数。
    """
    compensator = MeasurementCompensator(db, use_mock=True)
    compensation = compensator.get_trp_compensation(
        chamber_id, probe_id, polarization, frequency_mhz
    )

    return {
        "probe_id": probe_id,
        "polarization": polarization,
        "frequency_mhz": frequency_mhz,
        **compensation
    }


@compensation_router.get("/tis/{chamber_id}/{probe_id}")
def get_tis_compensation(
    chamber_id: UUID,
    probe_id: int,
    polarization: str = Query("V"),
    frequency_mhz: float = Query(3500.0),
    db: Session = Depends(get_db)
):
    """
    获取 TIS 测量补偿值
    """
    compensator = MeasurementCompensator(db, use_mock=True)
    compensation = compensator.get_tis_compensation(
        chamber_id, probe_id, polarization, frequency_mhz
    )

    return {
        "probe_id": probe_id,
        "polarization": polarization,
        "frequency_mhz": frequency_mhz,
        **compensation
    }


@compensation_router.get("/summary/{chamber_id}")
def get_compensation_summary(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0),
    db: Session = Depends(get_db)
):
    """
    获取系统补偿汇总

    用于测试前检查系统状态。
    """
    summary = get_system_compensation_summary(db, chamber_id, frequency_mhz)

    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])

    return summary


@compensation_router.post("/apply-trp")
def apply_trp_compensation(
    chamber_id: UUID,
    probe_id: int,
    raw_power_dbm: float,
    polarization: str = Query("V"),
    frequency_mhz: float = Query(3500.0),
    db: Session = Depends(get_db)
):
    """
    对 TRP 测量值应用补偿

    输入原始测量值，返回补偿后的值。
    """
    compensator = MeasurementCompensator(db, use_mock=True)
    compensated, details = compensator.compensate_trp_measurement(
        raw_power_dbm, chamber_id, probe_id, polarization, frequency_mhz
    )

    return {
        "raw_power_dbm": raw_power_dbm,
        "compensated_power_dbm": compensated,
        "compensation_applied_db": details["total_compensation_db"],
        "details": details
    }


@compensation_router.post("/apply-tis")
def apply_tis_compensation(
    chamber_id: UUID,
    probe_id: int,
    delivered_power_dbm: float,
    polarization: str = Query("V"),
    frequency_mhz: float = Query(3500.0),
    db: Session = Depends(get_db)
):
    """
    对 TIS 测量值应用补偿

    输入信道仿真器发射功率，返回 DUT 接收功率。
    """
    compensator = MeasurementCompensator(db, use_mock=True)
    power_at_dut, details = compensator.compensate_tis_measurement(
        delivered_power_dbm, chamber_id, probe_id, polarization, frequency_mhz
    )

    return {
        "delivered_power_dbm": delivered_power_dbm,
        "power_at_dut_dbm": power_at_dut,
        "compensation_applied_db": details["total_compensation_db"],
        "details": details
    }


# ==================== RF Switch 校准 (CAL-02) ====================

@switch_router.post("/calibrate")
async def calibrate_rf_switch_matrix(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0, description="测量频率 (MHz)"),
    num_input_ports: int = Query(4, description="输入端口数量"),
    num_output_ports: int = Query(32, description="输出端口数量"),
    vna_id: Optional[str] = Query(None, description="VNA 设备 ID"),
    calibrated_by: str = Query("System", description="校准人员"),
    db: Session = Depends(get_db)
):
    """
    校准 RF 开关矩阵

    测量开关矩阵的插入损耗和隔离度。

    Path: Path B' (旁路 CE)
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    service = RFSwitchCalibrationService(db, use_mock=True)
    result = await service.calibrate_switch_matrix(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        num_input_ports=num_input_ports,
        num_output_ports=num_output_ports,
        vna_id=vna_id,
        calibrated_by=calibrated_by
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return {
        "success": True,
        "message": result.message,
        "data": result.data,
        "warnings": result.warnings
    }


@switch_router.post("/repeatability")
async def measure_switch_repeatability(
    input_port: int = Query(..., description="输入端口"),
    output_port: int = Query(..., description="输出端口"),
    frequency_mhz: float = Query(3500.0, description="测量频率 (MHz)"),
    num_cycles: int = Query(10, description="切换次数"),
    vna_id: Optional[str] = Query(None, description="VNA 设备 ID"),
    db: Session = Depends(get_db)
):
    """
    测量开关切换一致性

    多次切换开关，测量插入损耗变化。
    """
    service = RFSwitchCalibrationService(db, use_mock=True)
    result = await service.measure_repeatability(
        input_port=input_port,
        output_port=output_port,
        frequency_mhz=frequency_mhz,
        num_cycles=num_cycles,
        vna_id=vna_id
    )

    return {
        "success": True,
        "message": result.message,
        "data": result.data,
        "warnings": result.warnings
    }


@switch_router.get("/insertion-loss")
def get_switch_insertion_loss(
    input_port: int = Query(..., description="输入端口"),
    output_port: int = Query(..., description="输出端口"),
    db: Session = Depends(get_db)
):
    """
    获取特定路径的开关插入损耗

    用于测量补偿。
    """
    # TODO: 从数据库获取最新的校准数据
    # 目前返回典型值
    return {
        "input_port": input_port,
        "output_port": output_port,
        "insertion_loss_db": 1.2,  # 典型值
        "source": "default",
        "note": "使用默认值，请执行校准获取实际数据"
    }


# ==================== E2E 校准 (CAL-03) ====================

@e2e_router.post("/generate-matrix")
async def generate_compensation_matrix(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0, description="目标频率 (MHz)"),
    num_probes: int = Query(32, description="探头数量"),
    calibrated_by: str = Query("System", description="校准人员"),
    db: Session = Depends(get_db)
):
    """
    生成端到端综合补偿矩阵

    整合探头路损、RF Switch、UL/DL 链路校准数据。

    Path: Path A (经 CE 全链路)
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    service = E2ECalibrationService(db, use_mock=True)
    result = await service.generate_compensation_matrix(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        num_probes=num_probes,
        calibrated_by=calibrated_by
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return {
        "success": True,
        "message": result.message,
        "compensation_matrix": result.compensation_matrix.to_dict() if result.compensation_matrix else None,
        "validation": result.validation_results,
        "warnings": result.warnings
    }


@e2e_router.get("/compensation/{chamber_id}/{probe_id}")
async def get_probe_compensation(
    chamber_id: UUID,
    probe_id: int,
    polarization: str = Query("V", description="极化类型: V 或 H"),
    frequency_mhz: float = Query(3500.0, description="频率 (MHz)"),
    db: Session = Depends(get_db)
):
    """
    获取特定探头的综合补偿值

    用于测量时应用补偿。
    """
    service = E2ECalibrationService(db, use_mock=True)

    # 生成补偿矩阵 (实际应用中应从缓存/数据库获取)
    result = await service.generate_compensation_matrix(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        num_probes=32
    )

    if not result.success or not result.compensation_matrix:
        raise HTTPException(status_code=500, detail="Failed to generate compensation matrix")

    compensation = result.compensation_matrix.get_compensation(probe_id, polarization)
    if not compensation:
        raise HTTPException(status_code=404, detail=f"No compensation found for probe {probe_id}")

    return {
        "probe_id": probe_id,
        "polarization": polarization,
        "frequency_mhz": frequency_mhz,
        "compensation": compensation.to_dict()
    }


@e2e_router.post("/apply-dl")
async def apply_downlink_compensation(
    chamber_id: UUID,
    probe_id: int,
    ce_output_power_dbm: float = Query(..., description="信道仿真器输出功率 (dBm)"),
    polarization: str = Query("V", description="极化类型"),
    frequency_mhz: float = Query(3500.0, description="频率 (MHz)"),
    db: Session = Depends(get_db)
):
    """
    应用下行链路补偿

    计算到达 DUT 的功率。
    """
    service = E2ECalibrationService(db, use_mock=True)

    result = await service.generate_compensation_matrix(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        num_probes=32
    )

    if not result.success or not result.compensation_matrix:
        raise HTTPException(status_code=500, detail="Failed to generate compensation matrix")

    power_at_dut = service.apply_dl_compensation(
        result.compensation_matrix,
        probe_id,
        polarization,
        ce_output_power_dbm
    )

    compensation = result.compensation_matrix.get_compensation(probe_id, polarization)

    return {
        "ce_output_power_dbm": ce_output_power_dbm,
        "power_at_dut_dbm": power_at_dut,
        "compensation_applied_db": compensation.total_dl_compensation_db if compensation else 0,
        "probe_id": probe_id,
        "polarization": polarization
    }


@e2e_router.post("/apply-ul")
async def apply_uplink_compensation(
    chamber_id: UUID,
    probe_id: int,
    ce_input_power_dbm: float = Query(..., description="信道仿真器接收功率 (dBm)"),
    polarization: str = Query("V", description="极化类型"),
    frequency_mhz: float = Query(3500.0, description="频率 (MHz)"),
    db: Session = Depends(get_db)
):
    """
    应用上行链路补偿

    计算 DUT 实际发射功率。
    """
    service = E2ECalibrationService(db, use_mock=True)

    result = await service.generate_compensation_matrix(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        num_probes=32
    )

    if not result.success or not result.compensation_matrix:
        raise HTTPException(status_code=500, detail="Failed to generate compensation matrix")

    dut_power = service.apply_ul_compensation(
        result.compensation_matrix,
        probe_id,
        polarization,
        ce_input_power_dbm
    )

    compensation = result.compensation_matrix.get_compensation(probe_id, polarization)

    return {
        "ce_input_power_dbm": ce_input_power_dbm,
        "dut_tx_power_dbm": dut_power,
        "compensation_applied_db": compensation.total_ul_compensation_db if compensation else 0,
        "probe_id": probe_id,
        "polarization": polarization
    }


# ==================== 相位校准 (CAL-04) ====================

@phase_router.post("/calibrate")
async def calibrate_phases(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0, description="校准频率 (MHz)"),
    num_channels: int = Query(32, description="通道数量"),
    calibrated_by: str = Query("system", description="校准人员"),
    db: Session = Depends(get_db)
):
    """
    执行相位校准
    
    测量各通道间的相位偏移并生成补偿值。
    """
    service = PhaseCalibrationService(db, use_mock=True)
    
    result = await service.calibrate_phases(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        num_channels=num_channels,
        calibrated_by=calibrated_by
    )
    
    return result.to_dict()


@phase_router.get("/coherence/{chamber_id}")
async def get_phase_coherence(
    chamber_id: UUID,
    db: Session = Depends(get_db)
):
    """
    获取相位一致性状态
    
    返回当前暗室的相位校准状态和一致性评分。
    """
    service = PhaseCalibrationService(db, use_mock=True)
    status = service.get_phase_coherence_status(chamber_id)
    return status.to_dict()


@phase_router.get("/compensation/{chamber_id}")
async def get_phase_compensation(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0, description="目标频率 (MHz)"),
    db: Session = Depends(get_db)
):
    """
    获取相位补偿值
    
    返回各通道需要应用的相位补偿值。
    """
    service = PhaseCalibrationService(db, use_mock=True)
    compensations = service.calculate_phase_compensation(chamber_id, frequency_mhz)
    
    return {
        "chamber_id": str(chamber_id),
        "frequency_mhz": frequency_mhz,
        "compensations": [c.to_dict() for c in compensations]
    }


@phase_router.post("/verify")
async def verify_phase_coherence(
    chamber_id: UUID,
    frequency_mhz: float = Query(3500.0, description="验证频率 (MHz)"),
    db: Session = Depends(get_db)
):
    """
    验证相位一致性
    
    应用补偿后重新测量，验证补偿效果。
    """
    service = PhaseCalibrationService(db, use_mock=True)
    result = await service.verify_phase_coherence(chamber_id, frequency_mhz)
    return result


# ==================== 信道仿真器校准 (CAL-06) ====================

@ce_router.get("/status/{ce_id}")
async def get_ce_status(
    ce_id: str,
    db: Session = Depends(get_db)
):
    """
    获取信道仿真器状态
    
    返回 CE 的连接状态、校准状态和基本信息。
    """
    service = CEInternalCalibrationService(db, use_mock=True)
    status = await service.get_ce_status(ce_id)
    return status.to_dict()


@ce_router.post("/run")
async def run_ce_calibration(
    ce_id: str,
    calibration_type: str = Query("full", description="校准类型: full, power, phase, delay, frequency"),
    frequency_mhz: float = Query(3500.0, description="校准频率 (MHz)"),
    calibrated_by: str = Query("system", description="校准人员"),
    db: Session = Depends(get_db)
):
    """
    执行 CE 内部校准
    
    调用厂商校准程序执行设备校准。
    """
    service = CEInternalCalibrationService(db, use_mock=True)
    
    try:
        cal_type = CECalibrationType(calibration_type)
    except ValueError:
        cal_type = CECalibrationType.FULL
    
    result = await service.run_vendor_calibration(
        ce_id=ce_id,
        calibration_type=cal_type,
        frequency_mhz=frequency_mhz,
        calibrated_by=calibrated_by
    )
    
    return result.to_dict()


@ce_router.post("/verify")
async def verify_ce_output(
    ce_id: str,
    frequency_mhz: float = Query(3500.0, description="测试频率 (MHz)"),
    test_power_dbm: float = Query(-30.0, description="测试功率 (dBm)"),
    db: Session = Depends(get_db)
):
    """
    验证 CE 输出精度
    
    通过发送测试信号验证 CE 输出功率和相位精度。
    """
    service = CEInternalCalibrationService(db, use_mock=True)
    result = await service.verify_ce_output(
        ce_id=ce_id,
        frequency_mhz=frequency_mhz,
        test_power_dbm=test_power_dbm
    )
    return result


@ce_router.post("/import")
async def import_ce_calibration_data(
    ce_id: str,
    file_path: str = Query(..., description="校准数据文件路径"),
    file_format: str = Query("json", description="文件格式: json, csv, xml"),
    db: Session = Depends(get_db)
):
    """
    导入厂商校准数据
    
    从文件导入厂商提供的校准数据。
    """
    service = CEInternalCalibrationService(db, use_mock=True)
    result = await service.import_calibration_data(
        ce_id=ce_id,
        file_path=file_path,
        file_format=file_format
    )
    return result


# ==================== 相对校准 (Relative Calibration) ====================

@baseline_router.post("/create")
async def create_calibration_baseline(
    chamber_id: str,
    calibration_type: str,
    frequency_mhz: float,
    reference_channel_id: int = 0,
    calibrated_by: str = "system",
    db: Session = Depends(get_db)
):
    """
    建立校准基线
    
    执行全量校准，测量所有通道，计算相对于参考通道的 Delta 矩阵。
    """
    from uuid import UUID
    service = RelativeCalibrationService(db, use_mock=True)
    result = service.create_baseline(
        chamber_id=UUID(chamber_id),
        calibration_type=RelativeCalibrationType(calibration_type),
        frequency_mhz=frequency_mhz,
        reference_channel_id=reference_channel_id,
        calibrated_by=calibrated_by,
    )
    return result


@baseline_router.post("/quick")
async def quick_calibration(
    chamber_id: str,
    calibration_type: str,
    frequency_mhz: float,
    db: Session = Depends(get_db)
):
    """
    快速校准
    
    仅测量参考通道，基于 Delta 基线推导其他通道数值。
    """
    from uuid import UUID
    from dataclasses import asdict
    service = RelativeCalibrationService(db, use_mock=True)
    result = service.quick_calibrate(
        chamber_id=UUID(chamber_id),
        calibration_type=RelativeCalibrationType(calibration_type),
        frequency_mhz=frequency_mhz,
    )
    return {
        "success": result.success,
        "calibration_type": result.calibration_type,
        "frequency_mhz": result.frequency_mhz,
        "reference_channel_id": result.reference_channel_id,
        "reference_value_db": result.reference_value_db,
        "derived_channels": result.derived_channels,
        "drift_detected": result.drift_detected,
        "max_drift_db": result.max_drift_db,
        "max_drift_deg": result.max_drift_deg,
        "calibrated_at": result.calibrated_at.isoformat(),
    }


@baseline_router.post("/drift-check")
async def check_calibration_drift(
    chamber_id: str,
    calibration_type: str,
    frequency_mhz: float,
    db: Session = Depends(get_db)
):
    """
    漂移检测
    
    对比当前测量值与基线，检测是否存在超阈值漂移。
    """
    from uuid import UUID
    service = RelativeCalibrationService(db, use_mock=True)
    result = service.check_drift(
        chamber_id=UUID(chamber_id),
        calibration_type=RelativeCalibrationType(calibration_type),
        frequency_mhz=frequency_mhz,
    )
    return {
        "baseline_id": result.baseline_id,
        "within_threshold": result.within_threshold,
        "max_drift_db": result.max_drift_db,
        "max_drift_deg": result.max_drift_deg,
        "channels_exceeding_threshold": result.channels_exceeding_threshold,
        "recommendation": result.recommendation,
    }


@baseline_router.get("/status/{chamber_id}")
async def get_baseline_status(
    chamber_id: str,
    db: Session = Depends(get_db)
):
    """
    获取暗室所有基线的状态
    """
    from uuid import UUID
    service = RelativeCalibrationService(db, use_mock=True)
    statuses = service.get_baseline_status(UUID(chamber_id))
    return {
        "chamber_id": chamber_id,
        "baselines": [
            {
                "calibration_type": s.calibration_type,
                "frequency_mhz": s.frequency_mhz,
                "status": s.status,
                "baseline_date": s.baseline_date.isoformat() if s.baseline_date else None,
                "valid_until": s.valid_until.isoformat() if s.valid_until else None,
                "days_remaining": s.days_remaining,
                "total_channels": s.total_channels,
                "reference_channel_id": s.reference_channel_id,
                "drift_within_threshold": s.drift_within_threshold,
            }
            for s in statuses
        ]
    }
