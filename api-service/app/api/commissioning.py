"""
3GPP Static MIMO OTA Commissioning API

首次暗室验证的 REST 端点。
提供会话管理、分阶段执行和结果查询。
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.commissioning_service import CommissioningService
from app.services.commissioning_config import (
    CommissioningPhase,
    PhaseStatus,
    StaticMIMOConfig,
    CTIACriteria,
)

router = APIRouter(prefix="/commissioning", tags=["暗室首测"])

_last_error = "No error captured yet"

@router.get("/debug/error")
async def get_last_error():
    return {"error": _last_error}


# ==================== Pydantic Models ====================

class CreateSessionRequest(BaseModel):
    """创建首测会话"""
    cdl_model_name: str = "UMa CDL-C NLOS"
    frequency_hz: float = 3.5e9
    bandwidth_mhz: float = 100
    mimo_layers: int = 2
    azimuths_deg: List[float] = [0, 90, 180, 270]
    measurement_duration_s: float = 10.0
    # CTIA 门限 (可调)
    min_throughput_ratio: float = 0.70
    max_rsrp_variance_db: float = 3.0


class SessionResponse(BaseModel):
    """会话状态响应"""
    session_id: str
    phase: str
    phase_statuses: Dict[str, str]
    overall_progress: float
    config: Dict[str, Any]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # 各阶段结果摘要
    precheck: Optional[Dict[str, Any]] = None
    reference: Optional[Dict[str, Any]] = None
    mimo_test: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    report_id: Optional[str] = None


class PhaseResultResponse(BaseModel):
    """阶段执行结果"""
    phase: str
    status: str
    result: Dict[str, Any]


# ==================== 工具函数 ====================

def _state_to_response(state) -> SessionResponse:
    """将内部状态转为 API 响应"""
    return SessionResponse(
        session_id=state.session_id,
        phase=state.phase.value,
        phase_statuses={k.value: v.value for k, v in state.phase_statuses.items()},
        overall_progress=state.overall_progress,
        config={
            "cdl_model_name": state.config.cdl_model_name,
            "frequency_ghz": state.config.frequency_hz / 1e9,
            "bandwidth_mhz": state.config.bandwidth_mhz,
            "mimo_config": f"{state.config.mimo_layers}x{state.config.mimo_layers}",
            "azimuths_deg": state.config.azimuths_deg,
            "measurement_duration_s": state.config.measurement_duration_s,
            "total_estimated_time_s": state.config.total_measurement_time_s,
        },
        started_at=state.started_at,
        completed_at=state.completed_at,
        precheck=asdict(state.precheck) if state.precheck else None,
        reference=asdict(state.reference) if state.reference else None,
        mimo_test=asdict(state.mimo_test) if state.mimo_test else None,
        analysis=asdict(state.analysis) if state.analysis else None,
        report_id=state.report_id,
    )


def _mimo_summary(mimo) -> Dict[str, Any]:
    """MIMO 结果摘要 (避免传输大量采样数据)"""
    return {
        "cdl_model_name": mimo.cdl_model_name,
        "frequency_ghz": mimo.frequency_ghz,
        "mimo_config": mimo.mimo_config,
        "asc_files_loaded": mimo.asc_files_loaded,
        "total_duration_s": mimo.total_duration_s,
        "azimuth_count": len(mimo.azimuth_results),
        "azimuth_results": [
            {
                "azimuth_deg": az.azimuth_deg,
                "rsrp_dbm": round(az.rsrp_dbm, 1),
                "sinr_db": round(az.sinr_db, 1),
                "throughput_mbps": round(az.throughput_mbps, 0),
                "rank_indicator": round(az.rank_indicator, 2),
                "num_samples": az.num_samples,
            }
            for az in mimo.azimuth_results
        ],
    }


# ==================== 端点 ====================

@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest,
    db: Session = Depends(get_db)
):
    """创建新的首测会话"""
    config = StaticMIMOConfig(
        cdl_model_name=request.cdl_model_name,
        frequency_hz=request.frequency_hz,
        bandwidth_mhz=request.bandwidth_mhz,
        mimo_layers=request.mimo_layers,
        azimuths_deg=request.azimuths_deg,
        measurement_duration_s=request.measurement_duration_s,
    )
    criteria = CTIACriteria(
        min_throughput_ratio=request.min_throughput_ratio,
        max_rsrp_variance_db=request.max_rsrp_variance_db,
    )

    service = CommissioningService(db)
    state = service.create_session(config=config, criteria=criteria)
    return _state_to_response(state)


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(db: Session = Depends(get_db)):
    """列出所有首测会话"""
    service = CommissioningService(db)
    return [_state_to_response(s) for s in service.list_sessions()]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: Session = Depends(get_db)):
    """获取会话状态"""
    try:
        service = CommissioningService(db)
        state = service.get_session(session_id)
        if not state:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return _state_to_response(state)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        global _last_error
        _last_error = err
        raise HTTPException(status_code=500, detail=f"Internal Server Error in get_session: {err}")


@router.post(
    "/sessions/{session_id}/phase/{phase_name}",
    response_model=PhaseResultResponse,
)
async def run_phase(
    session_id: str, 
    phase_name: str,
    db: Session = Depends(get_db)
):
    """执行指定阶段"""
    service = CommissioningService(db)
    state = service.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    phase_map = {
        "precheck": (CommissioningPhase.PRECHECK, service.phase1_system_precheck),
        "reference_wait": (CommissioningPhase.REFERENCE, service.phase2_wait_for_antenna),
        "reference": (CommissioningPhase.REFERENCE, service.phase2_reference_measurement),
        "mimo_test": (CommissioningPhase.MIMO_TEST, service.phase3_static_mimo_test),
        "analysis": (CommissioningPhase.ANALYSIS, service.phase4_analysis),
        "report": (CommissioningPhase.REPORT, service.phase5_report),
    }

    if phase_name not in phase_map:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown phase: {phase_name}. "
                   f"Valid: {list(phase_map.keys())}"
        )

    try:
        phase_enum, handler = phase_map[phase_name]
        result = await handler(session_id)

        # 将结果序列化
        if hasattr(result, '__dataclass_fields__'):
            result_dict = asdict(result)
        elif isinstance(result, str):
            result_dict = {"report_id": result}
        else:
            result_dict = {"value": result}

        return PhaseResultResponse(
            phase=phase_name,
            status=state.phase_statuses[phase_enum].value,
            result=result_dict,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        global _last_error
        _last_error = err
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {err}")


@router.post("/sessions/{session_id}/run-all", response_model=SessionResponse)
async def run_all_phases(session_id: str, db: Session = Depends(get_db)):
    """一键执行全部阶段"""
    service = CommissioningService(db)
    state = service.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    state = await service.run_all(session_id)
    return _state_to_response(state)
