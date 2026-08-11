"""破坏性诊断与正式 TestCase 执行的进程内互斥门。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import diagnostic_sequence as diagnostic_api
from app.db.database import Base
from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
)
from app.models.test_plan import TestCase, TestExecution
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.diagnostic_run import DiagnosticRun
from app.models.lab_profile import LabProfile
from app.services import test_case_runner as tcr


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _db_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def lab_with_bs(db):
    chamber = create_chamber_from_preset(
        ChamberType.TYPE_C.value,
        name="Diagnostic exclusion chamber",
    )
    db.add(chamber)
    db.commit()
    lab = LabProfile(
        name="Diagnostic exclusion lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[],
        is_active=True,
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def _sequence(*, safe: bool, run):
    return SimpleNamespace(
        metadata=SequenceMetadata(
            name="互斥门测试序列",
            description="test only",
            required_categories=[],
            safe_during_test=safe,
        ),
        run=run,
    )


def _request(lab_profile_id):
    return diagnostic_api.RunSequenceRequest(lab_profile_id=lab_profile_id)


def _patch_sequence(monkeypatch, sequence):
    monkeypatch.setattr(diagnostic_api.loader, "get_sequence", lambda _key: sequence)
    fake_hal = MagicMock()
    fake_hal.drivers = {}
    monkeypatch.setattr(diagnostic_api, "get_hal_service", lambda: fake_hal)


@pytest.fixture(autouse=True)
def _clear_process_local_state():
    yield
    tcr._RUNNING_TASKS.clear()
    try:
        from app.services import execution_exclusion_guard as guard
    except ImportError:
        return
    guard.reset_unsafe_diagnostic_guard_for_tests()


@pytest.mark.asyncio
async def test_active_formal_execution_rejects_unsafe_diagnostic_before_scpi(
    db, lab_with_bs, monkeypatch,
):
    called = 0

    async def _run(*_args, **_kwargs):
        nonlocal called
        called += 1
        return SequenceRunResult(success=True, summary="should not run")

    _patch_sequence(monkeypatch, _sequence(safe=False, run=_run))
    gate = asyncio.Event()
    formal_task = asyncio.create_task(gate.wait())
    tcr._RUNNING_TASKS["formal-active"] = formal_task
    try:
        with pytest.raises(HTTPException) as caught:
            await diagnostic_api.run_diagnostic_sequence(
                "unsafe", _request(lab_with_bs.id), db,
            )
        assert caught.value.status_code == 409
        assert called == 0, "互斥拒绝必须发生在 sequence/SCPI I/O 之前"
    finally:
        gate.set()
        await formal_task


@pytest.mark.asyncio
async def test_db_running_case_runner_row_rejects_unsafe_diagnostic(
    db, lab_with_bs, monkeypatch,
):
    source = TestCase(
        name="DB running sentinel",
        test_type="MIMO_OTA",
        configuration={},
        created_by="pytest",
        lab_profile_id=lab_with_bs.id,
    )
    db.add(source)
    db.commit()
    db.add(TestExecution(
        test_case_id=source.id,
        status="running",
        started_at=datetime.utcnow(),
        executed_by=tcr.RUNNER_MARKER,
        config={},
    ))
    db.commit()
    called = 0

    async def _run(*_args, **_kwargs):
        nonlocal called
        called += 1
        return SequenceRunResult(success=True, summary="should not run")

    _patch_sequence(monkeypatch, _sequence(safe=False, run=_run))

    with pytest.raises(HTTPException) as caught:
        await diagnostic_api.run_diagnostic_sequence(
            "unsafe", _request(lab_with_bs.id), db,
        )
    assert caught.value.status_code == 409
    assert called == 0


@pytest.mark.asyncio
async def test_second_concurrent_unsafe_diagnostic_is_rejected(
    db, lab_with_bs, monkeypatch,
):
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    calls = 0

    async def _run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            await release_first.wait()
        return SequenceRunResult(
            success=False,
            summary="test complete",
            steps=[SequenceStepResult(label="probe", success=True)],
        )

    _patch_sequence(monkeypatch, _sequence(safe=False, run=_run))
    first = asyncio.create_task(diagnostic_api.run_diagnostic_sequence(
        "unsafe", _request(lab_with_bs.id), db,
    ))
    await first_started.wait()
    try:
        with pytest.raises(HTTPException) as caught:
            await diagnostic_api.run_diagnostic_sequence(
                "unsafe", _request(lab_with_bs.id), db,
            )
        assert caught.value.status_code == 409
        assert calls == 1
    finally:
        release_first.set()
        await first


@pytest.mark.asyncio
async def test_unsafe_sequence_does_not_interleave_with_f64_standalone_operation(
    db, lab_with_bs, monkeypatch,
):
    """序列级租约覆盖整个 run；F64 手工操作只能在序列退出后开始。

    P3-18 回查发现，原始 Discovered 所要求的 run-endpoint 串行化已由
    P1-46 / PR #296 的 exclusion token 与后续 PR #304 的全局
    ``InstrumentTestLease`` 共同落地：破坏性诊断之间直接拒绝，诊断与其它
    F64 端点则串行等待。本条补上此前缺少的跨入口行为证据，避免日后退回
    “每条 SCPI 原子各自加锁、序列仍可交错”。
    """
    from contextlib import asynccontextmanager

    from app.api import instrument as instrument_api
    from app.services import instrument_test_lease as lease_service
    from app.services.instrument_test_lease import InstrumentTestLease

    sequence_started = asyncio.Event()
    release_sequence = asyncio.Event()
    f64_waiting_for_lease = asyncio.Event()
    events = []

    class _F64:
        async def acquire_remote_control(self):
            events.append("f64-acquire")
            return True

        async def release_to_local_control(self):
            events.append("f64-release")
            return True

        async def start_emulation(self):
            events.append("f64-start")
            return True

    driver = _F64()
    fake_hal = SimpleNamespace(drivers={"channelEmulator": driver})

    async def _run(*_args, **_kwargs):
        events.append("sequence-enter")
        sequence_started.set()
        await release_sequence.wait()
        events.append("sequence-exit")
        return SequenceRunResult(success=True, summary="sequence complete")

    _patch_sequence(monkeypatch, _sequence(safe=False, run=_run))
    monkeypatch.setattr(diagnostic_api, "get_hal_service", lambda: fake_hal)
    monkeypatch.setattr(
        instrument_api, "_get_loaded_hal_driver", lambda _category: driver,
    )
    monkeypatch.setattr(
        lease_service, "_LEASE", InstrumentTestLease(lambda: fake_hal),
    )

    @asynccontextmanager
    async def _observable_f64_lease(purpose, **kwargs):
        f64_waiting_for_lease.set()
        async with lease_service.instrument_test_lease(purpose, **kwargs):
            yield

    monkeypatch.setattr(
        instrument_api, "instrument_test_lease", _observable_f64_lease,
    )

    sequence_task = asyncio.create_task(diagnostic_api.run_diagnostic_sequence(
        "unsafe", _request(lab_with_bs.id), db,
    ))
    await sequence_started.wait()
    f64_task = asyncio.create_task(instrument_api.emulation_control(
        "channelEmulator",
        instrument_api.EmulationControlRequest(action="start"),
    ))
    interleaved = False
    try:
        # 第二个 task 已进入租约入口；此后必须停在共享锁，而不是进入 F64 驱动。
        await asyncio.wait_for(f64_waiting_for_lease.wait(), timeout=1.0)
        await asyncio.sleep(0)
        interleaved = "f64-start" in events
    finally:
        release_sequence.set()
        await asyncio.wait_for(
            asyncio.gather(sequence_task, f64_task), timeout=1.0,
        )
    assert not interleaved, (
        "F64 手工操作插进了诊断序列中间；load/GO/AUTOSET 等步骤会互相污染"
    )
    assert events.index("sequence-exit") < events.index("f64-start"), events


@pytest.mark.asyncio
async def test_unsafe_sequence_exception_releases_guard(
    db, lab_with_bs, monkeypatch,
):
    async def _raise(*_args, **_kwargs):
        raise RuntimeError("diagnostic exploded")

    _patch_sequence(monkeypatch, _sequence(safe=False, run=_raise))
    response = await diagnostic_api.run_diagnostic_sequence(
        "unsafe", _request(lab_with_bs.id), db,
    )

    from app.services import execution_exclusion_guard as guard

    assert response.success is False
    assert "diagnostic exploded" in response.summary
    assert guard.active_unsafe_diagnostic() is None


@pytest.mark.asyncio
async def test_unsafe_sequence_cancellation_propagates_and_releases_guard(
    db, lab_with_bs, monkeypatch,
):
    async def _cancel(*_args, **_kwargs):
        raise asyncio.CancelledError()

    _patch_sequence(monkeypatch, _sequence(safe=False, run=_cancel))
    with pytest.raises(asyncio.CancelledError):
        await diagnostic_api.run_diagnostic_sequence(
            "unsafe", _request(lab_with_bs.id), db,
        )

    from app.services import execution_exclusion_guard as guard

    assert guard.active_unsafe_diagnostic() is None
    audit = db.query(DiagnosticRun).one()
    assert audit.success is False
    assert audit.error_message == "Sequence cancelled"
    assert audit.result_extra == {
        "cancelled": True,
        "partial_result_available": False,
    }
    assert "cancelled" in (audit.output_excerpt or "").lower()


@pytest.mark.asyncio
async def test_safe_sequence_is_unaffected_by_active_formal_execution(
    db, lab_with_bs, monkeypatch,
):
    async def _run(*_args, **_kwargs):
        return SequenceRunResult(success=True, summary="safe ran")

    _patch_sequence(monkeypatch, _sequence(safe=True, run=_run))
    gate = asyncio.Event()
    formal_task = asyncio.create_task(gate.wait())
    tcr._RUNNING_TASKS["formal-active"] = formal_task
    try:
        response = await diagnostic_api.run_diagnostic_sequence(
            "safe", _request(lab_with_bs.id), db,
        )
        assert response.success is True
        assert response.summary == "safe ran"
    finally:
        gate.set()
        await formal_task
