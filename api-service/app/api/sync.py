"""Hardware Synchronization API endpoints

L3 (Control Layer) API for managing hardware synchronization.
Provides REST endpoints for clock, trigger, and system sync management.

Phase 1: Stub implementation with mock data
Future phases will integrate with actual HAL services.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from uuid import uuid4
import logging
import time

from app.schemas.sync import (
    # Enums
    SyncState,
    ClockSource,
    ClockSyncStatus,
    TriggerSource,
    # Clock
    ClockConfig,
    ClockStatusResponse,
    InstrumentClockStatus,
    # Trigger
    TriggerConfig,
    TriggerSequenceCreate,
    TriggerSequenceResponse,
    TriggerSequenceStep,
    # System
    SyncMetrics,
    InstrumentSyncState,
    SystemSyncStatus,
    SyncInitRequest,
    SyncInitResponse,
)

router = APIRouter(prefix="/sync", tags=["Hardware Synchronization"])
logger = logging.getLogger(__name__)

# ==================== Mock State ====================
# In production, this would be managed by actual HAL services

_sync_state = SyncState.IDLE
_sync_start_time = time.time()
_clock_config = ClockConfig()
_trigger_sequences: dict[str, TriggerSequenceResponse] = {}


def _get_mock_instruments() -> List[InstrumentSyncState]:
    """Get mock instrument states"""
    return [
        InstrumentSyncState(
            instrument_id="ch_emu_01",
            instrument_name="Channel Emulator (Keysight F8800A)",
            clock_locked=_sync_state == SyncState.SYNCHRONIZED,
            trigger_armed=False,
            last_trigger_time=None,
            status="ready" if _sync_state == SyncState.SYNCHRONIZED else "idle"
        ),
        InstrumentSyncState(
            instrument_id="bs_emu_01",
            instrument_name="Base Station Emulator (R&S CMX500)",
            clock_locked=_sync_state == SyncState.SYNCHRONIZED,
            trigger_armed=False,
            last_trigger_time=None,
            status="ready" if _sync_state == SyncState.SYNCHRONIZED else "idle"
        ),
        InstrumentSyncState(
            instrument_id="sig_ana_01",
            instrument_name="Signal Analyzer (Keysight N9040B)",
            clock_locked=_sync_state == SyncState.SYNCHRONIZED,
            trigger_armed=False,
            last_trigger_time=None,
            status="ready" if _sync_state == SyncState.SYNCHRONIZED else "idle"
        ),
    ]


# ==================== System Sync Endpoints ====================

@router.get("/status", response_model=SystemSyncStatus)
def get_sync_status():
    """
    Get system synchronization status

    Returns the current state of all synchronization layers:
    - L0: Clock synchronization status
    - L1: Trigger configuration status
    - L2: Parameter synchronization metrics

    This endpoint is polled by the frontend to display sync status.
    """
    global _sync_state, _sync_start_time

    is_synced = _sync_state == SyncState.SYNCHRONIZED

    return SystemSyncStatus(
        state=_sync_state,
        is_synchronized=is_synced,

        # L0 status
        clock_locked=is_synced,
        clock_source=_clock_config.source,
        clock_coherence_verified=is_synced,

        # L1 status
        trigger_armed=False,
        active_sequence=None,

        # L2 status
        parameter_sync_active=is_synced,
        metrics=SyncMetrics(
            latency_avg_ms=2.5 if is_synced else 0.0,
            latency_p50_ms=2.0 if is_synced else 0.0,
            latency_p95_ms=5.0 if is_synced else 0.0,
            latency_p99_ms=8.0 if is_synced else 0.0,
            latency_max_ms=12.0 if is_synced else 0.0,
            jitter_ms=0.5 if is_synced else 0.0,
            messages_per_second=100.0 if is_synced else 0.0,
        ),

        # Instruments
        instruments=_get_mock_instruments(),

        last_sync_check=datetime.utcnow(),
        uptime_seconds=time.time() - _sync_start_time if is_synced else 0.0,
    )


@router.post("/initialize", response_model=SyncInitResponse)
def initialize_sync(request: SyncInitRequest):
    """
    Initialize system synchronization

    Performs the following steps:
    1. Configure clock source on all instruments
    2. Wait for clock lock
    3. Optionally configure default triggers
    4. Verify clock coherence

    This is typically called at system startup or after configuration changes.
    """
    global _sync_state, _clock_config, _sync_start_time

    start_time = time.time()
    _sync_state = SyncState.CONFIGURING
    _clock_config.source = request.clock_source

    logger.info(f"Initializing sync with clock source: {request.clock_source}")

    # Simulate initialization delay
    # In production, this would actually configure hardware
    import asyncio
    try:
        # Simulate clock lock delay (in real impl, would be async)
        time.sleep(0.1)  # 100ms simulated delay

        _sync_state = SyncState.SYNCHRONIZED
        _sync_start_time = time.time()

        elapsed = time.time() - start_time

        logger.info(f"Sync initialization complete in {elapsed:.2f}s")

        return SyncInitResponse(
            success=True,
            state=_sync_state,
            message="System synchronized successfully",
            clock_locked=True,
            instruments_configured=3,
            elapsed_seconds=elapsed,
        )

    except Exception as e:
        _sync_state = SyncState.ERROR
        logger.error(f"Sync initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync initialization failed: {e}")


@router.post("/reset")
def reset_sync():
    """
    Reset synchronization state

    Stops all synchronization activities and returns system to idle state.
    Used for error recovery or reconfiguration.
    """
    global _sync_state

    _sync_state = SyncState.IDLE
    logger.info("Sync state reset to IDLE")

    return {"message": "Sync state reset to idle", "state": _sync_state}


# ==================== Clock Endpoints ====================

@router.get("/clock", response_model=ClockStatusResponse)
def get_clock_status():
    """
    Get master clock status

    Returns the status of the system reference clock.
    """
    is_locked = _sync_state == SyncState.SYNCHRONIZED

    return ClockStatusResponse(
        sync_status=ClockSyncStatus.LOCKED if is_locked else ClockSyncStatus.UNLOCKED,
        source=_clock_config.source,
        frequency_offset_ppb=0.5 if is_locked else 0.0,
        phase_offset_ps=25.0 if is_locked else 0.0,
        lock_time_seconds=time.time() - _sync_start_time if is_locked else 0.0,
        is_locked=is_locked,
    )


@router.post("/clock/configure")
def configure_clock(config: ClockConfig):
    """
    Configure system clock

    Sets the clock source and configuration for all instruments.
    Requires re-initialization after configuration change.
    """
    global _clock_config, _sync_state

    _clock_config = config
    _sync_state = SyncState.IDLE  # Require re-init after config change

    logger.info(f"Clock configured: source={config.source}, freq={config.reference_frequency_hz}Hz")

    return {
        "message": "Clock configured successfully",
        "config": config.model_dump(),
        "requires_init": True
    }


@router.get("/clock/instruments", response_model=List[InstrumentClockStatus])
def get_instrument_clock_status():
    """
    Get clock status for all instruments

    Returns detailed clock status for each configured instrument.
    """
    is_locked = _sync_state == SyncState.SYNCHRONIZED

    return [
        InstrumentClockStatus(
            instrument_id=inst.instrument_id,
            instrument_name=inst.instrument_name,
            status=ClockStatusResponse(
                sync_status=ClockSyncStatus.LOCKED if is_locked else ClockSyncStatus.UNLOCKED,
                source=_clock_config.source,
                frequency_offset_ppb=0.3 + i * 0.1 if is_locked else 0.0,
                phase_offset_ps=20.0 + i * 5 if is_locked else 0.0,
                lock_time_seconds=time.time() - _sync_start_time if is_locked else 0.0,
                is_locked=is_locked,
            ),
            last_updated=datetime.utcnow(),
        )
        for i, inst in enumerate(_get_mock_instruments())
    ]


# ==================== Trigger Endpoints ====================

@router.post("/trigger/sequence", response_model=TriggerSequenceResponse, status_code=201)
def create_trigger_sequence(request: TriggerSequenceCreate):
    """
    Create a trigger sequence

    Defines a sequence of trigger operations across multiple instruments.
    Sequences can be armed and executed for synchronized measurements.
    """
    seq_id = str(uuid4())

    sequence = TriggerSequenceResponse(
        id=seq_id,
        name=request.name,
        description=request.description,
        steps=request.steps,
        repeat_count=request.repeat_count,
        status="idle",
        created_at=datetime.utcnow(),
    )

    _trigger_sequences[seq_id] = sequence

    logger.info(f"Created trigger sequence: {seq_id} - {request.name}")

    return sequence


@router.get("/trigger/sequences", response_model=List[TriggerSequenceResponse])
def list_trigger_sequences():
    """
    List all trigger sequences
    """
    return list(_trigger_sequences.values())


@router.get("/trigger/sequence/{sequence_id}", response_model=TriggerSequenceResponse)
def get_trigger_sequence(sequence_id: str):
    """
    Get a specific trigger sequence
    """
    if sequence_id not in _trigger_sequences:
        raise HTTPException(status_code=404, detail="Trigger sequence not found")

    return _trigger_sequences[sequence_id]


@router.post("/trigger/sequence/{sequence_id}/arm")
def arm_trigger_sequence(sequence_id: str):
    """
    Arm a trigger sequence

    Prepares all instruments in the sequence to receive triggers.
    Must be called before executing the sequence.
    """
    if sequence_id not in _trigger_sequences:
        raise HTTPException(status_code=404, detail="Trigger sequence not found")

    if _sync_state != SyncState.SYNCHRONIZED:
        raise HTTPException(
            status_code=400,
            detail="System must be synchronized before arming triggers"
        )

    sequence = _trigger_sequences[sequence_id]
    sequence.status = "armed"

    logger.info(f"Armed trigger sequence: {sequence_id}")

    return {"message": "Trigger sequence armed", "sequence_id": sequence_id}


@router.post("/trigger/sequence/{sequence_id}/execute")
def execute_trigger_sequence(sequence_id: str):
    """
    Execute an armed trigger sequence

    Runs the sequence of trigger operations.
    Sequence must be armed first.
    """
    if sequence_id not in _trigger_sequences:
        raise HTTPException(status_code=404, detail="Trigger sequence not found")

    sequence = _trigger_sequences[sequence_id]

    if sequence.status != "armed":
        raise HTTPException(
            status_code=400,
            detail=f"Sequence must be armed before execution (current status: {sequence.status})"
        )

    sequence.status = "running"

    # Simulate execution
    # In production, this would actually execute the trigger sequence
    logger.info(f"Executing trigger sequence: {sequence_id}")

    sequence.status = "completed"

    return {
        "message": "Trigger sequence executed",
        "sequence_id": sequence_id,
        "steps_executed": len(sequence.steps),
    }


@router.delete("/trigger/sequence/{sequence_id}", status_code=204)
def delete_trigger_sequence(sequence_id: str):
    """
    Delete a trigger sequence
    """
    if sequence_id not in _trigger_sequences:
        raise HTTPException(status_code=404, detail="Trigger sequence not found")

    del _trigger_sequences[sequence_id]
    logger.info(f"Deleted trigger sequence: {sequence_id}")

    return None


# ==================== Parameter Sync Endpoints ====================

@router.get("/parameters/metrics", response_model=SyncMetrics)
def get_parameter_sync_metrics():
    """
    Get L2 parameter synchronization metrics

    Returns latency, jitter, and throughput statistics
    for the parameter synchronization channel.
    """
    is_synced = _sync_state == SyncState.SYNCHRONIZED

    return SyncMetrics(
        latency_avg_ms=2.5 if is_synced else 0.0,
        latency_p50_ms=2.0 if is_synced else 0.0,
        latency_p95_ms=5.0 if is_synced else 0.0,
        latency_p99_ms=8.0 if is_synced else 0.0,
        latency_max_ms=12.0 if is_synced else 0.0,
        jitter_ms=0.5 if is_synced else 0.0,
        messages_per_second=100.0 if is_synced else 0.0,
        dropped_count=0,
        error_count=0,
    )


# ==================== L2 Channel Parameter Endpoints ====================

from app.schemas.channel_params import (
    ParameterSyncConfig,
    ParameterSyncStatus,
    LargeScaleParams,
    SyncTimestamp,
    ParameterPublishRequest,
    ParameterHistoryRequest,
    ParameterHistoryResponse,
    ChannelModel,
)

# Mock state for L2 parameter sync
_param_sync_config = ParameterSyncConfig()
_param_sync_running = False
_param_sequence_id = 0
_param_history: list[LargeScaleParams] = []


@router.get("/parameters/config", response_model=ParameterSyncConfig)
def get_parameter_sync_config():
    """
    Get L2 parameter synchronization configuration
    """
    return _param_sync_config


@router.post("/parameters/config", response_model=ParameterSyncConfig)
def update_parameter_sync_config(config: ParameterSyncConfig):
    """
    Update L2 parameter synchronization configuration

    Changes take effect on next sync start.
    """
    global _param_sync_config
    _param_sync_config = config
    logger.info(f"Updated parameter sync config: rate={config.update_rate_hz}Hz, model={config.channel_model}")
    return _param_sync_config


@router.get("/parameters/status", response_model=ParameterSyncStatus)
def get_parameter_sync_status():
    """
    Get L2 parameter synchronization status

    Returns current state of the parameter sync subsystem including:
    - Running state
    - Performance metrics
    - Buffer status
    """
    global _param_sync_running, _param_sequence_id

    is_synced = _sync_state == SyncState.SYNCHRONIZED

    return ParameterSyncStatus(
        is_running=_param_sync_running and is_synced,
        is_connected=is_synced,
        last_update_time=datetime.utcnow() if _param_sync_running else None,
        update_count=_param_sequence_id,
        error_count=0,
        dropped_count=0,
        latency_avg_ms=2.5 if _param_sync_running else 0.0,
        latency_max_ms=8.0 if _param_sync_running else 0.0,
        update_rate_actual_hz=_param_sync_config.update_rate_hz if _param_sync_running else 0.0,
        buffer_fill_percent=min(len(_param_history) / _param_sync_config.buffer_size * 100, 100),
        current_n_paths=_param_history[-1].n_paths if _param_history else 0,
        current_sequence_id=_param_sequence_id,
    )


@router.post("/parameters/start")
def start_parameter_sync():
    """
    Start L2 parameter synchronization

    Begins publishing channel parameters at configured rate.
    Requires system to be synchronized first.
    """
    global _param_sync_running

    if _sync_state != SyncState.SYNCHRONIZED:
        raise HTTPException(
            status_code=400,
            detail="System must be synchronized before starting parameter sync"
        )

    _param_sync_running = True
    logger.info("Started L2 parameter synchronization")

    return {
        "message": "Parameter sync started",
        "config": _param_sync_config.model_dump()
    }


@router.post("/parameters/stop")
def stop_parameter_sync():
    """
    Stop L2 parameter synchronization
    """
    global _param_sync_running

    _param_sync_running = False
    logger.info("Stopped L2 parameter synchronization")

    return {"message": "Parameter sync stopped"}


@router.post("/parameters/publish", response_model=LargeScaleParams)
def publish_channel_parameters(request: ParameterPublishRequest):
    """
    Manually publish channel parameters (for testing/debugging)

    In production, parameters are published automatically by the
    channel engine service at the configured rate.
    """
    global _param_sequence_id, _param_history

    if not _param_sync_running:
        raise HTTPException(
            status_code=400,
            detail="Parameter sync is not running"
        )

    _param_sequence_id += 1

    # Update timestamp
    params = request.params.model_copy()
    params.timestamp = SyncTimestamp(
        sequence_id=_param_sequence_id,
        timestamp_ns=int(time.time() * 1_000_000_000),
        source="api"
    )

    # Add to history buffer
    _param_history.append(params)
    if len(_param_history) > _param_sync_config.buffer_size:
        _param_history = _param_history[-_param_sync_config.buffer_size:]

    logger.info(f"Published channel params: seq={_param_sequence_id}, n_paths={params.n_paths}")

    return params


@router.get("/parameters/current", response_model=Optional[LargeScaleParams])
def get_current_parameters():
    """
    Get the most recently published channel parameters
    """
    if not _param_history:
        return None
    return _param_history[-1]


@router.post("/parameters/history", response_model=ParameterHistoryResponse)
def get_parameter_history(request: ParameterHistoryRequest):
    """
    Get historical channel parameters from the ring buffer

    Useful for debugging and analysis.
    """
    if not _param_history:
        return ParameterHistoryResponse(
            items=[],
            total_available=0,
            oldest_sequence_id=0,
            newest_sequence_id=0,
        )

    # Filter by sequence ID if specified
    items = _param_history
    if request.start_sequence_id is not None:
        items = [p for p in items if p.timestamp.sequence_id >= request.start_sequence_id]
    if request.end_sequence_id is not None:
        items = [p for p in items if p.timestamp.sequence_id <= request.end_sequence_id]

    # Limit count
    items = items[-request.count:]

    return ParameterHistoryResponse(
        items=items,
        total_available=len(_param_history),
        oldest_sequence_id=_param_history[0].timestamp.sequence_id if _param_history else 0,
        newest_sequence_id=_param_history[-1].timestamp.sequence_id if _param_history else 0,
    )
