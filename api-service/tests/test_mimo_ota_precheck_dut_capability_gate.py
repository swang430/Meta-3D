"""DUTProfile 声明能力 precheck 门集成测试 (sibling of dut_gate / cal_gate)。

config.dut_profile_id 指向 DUTProfile 时, precheck section 2.3 拿请求 (mimo_layers/modulation)
跟 DUT **声明**比 —— 请求 > 声明: strict → FAILED (规划期提前 fail), opt-out → 降级 warning。
跟 attach 后协商核对 (cell_config) 互补: 这个最早, 查 DB 声明不需硬件。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.dut_profile import DUTProfile
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services.mimo_ota import build_mimo_ota_test_case
from app.services.mimo_ota.executors.precheck import PrecheckExecutor
from app.services.test_execution import (
    StepDescriptor,
    StepExecutionContext,
    StepExecutionStatus,
)

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _hal():
    """空 drivers 的 HAL — precheck section 2 (instrument connectivity) 不 crash;
    DUT 声明校验 (section 2.3) 是规划期查 DB, 不依赖 driver。"""
    from app.services.instrument_hal_service import get_hal_service
    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers.clear()
    yield
    hal.drivers.clear()
    hal.drivers.update(saved)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def lab(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="DUTCap-Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    lp = LabProfile(name="DUTCap-Lab", chamber_config_id=c.id, is_active=True)
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _make_dut(db, *, max_dl_layers=None, max_modulation_dl=None) -> DUTProfile:
    d = DUTProfile(
        name=f"DUT-{uuid.uuid4().hex[:8]}",
        max_dl_layers=max_dl_layers, max_modulation_dl=max_modulation_dl,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


async def _run_precheck(db, lab, *, dut_profile_id, mimo_layers, modulation, strict):
    test_case, _ = build_mimo_ota_test_case(
        db, name=f"DUTCapCase-{uuid.uuid4().hex[:8]}", description="dut cap gate",
        lab_profile_id=lab.id,
        config_overrides={
            "dut_profile_id": dut_profile_id,
            "mimo_layers": mimo_layers,
            "modulation": modulation,
            "precheck_strict_dut_capability": strict,
            # 隔离其它门, 只观察 dut_capability gate 信号
            "precheck_strict_cal": False,
            "precheck_strict_dut": False,
        },
        created_by="pytest-dutcap",
    )
    execution = TestExecution(
        test_case_id=test_case.id, status="pending", started_at=datetime.utcnow(),
        config={"step_descriptors": []}, measurements={}, executed_by="pytest-dutcap",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    ctx = StepExecutionContext(
        db=db, step=StepDescriptor(id="pc", type="MIMO_OTA_PRECHECK", parameters={}),
        test_execution=execution, lab_profile=lab, calibration_certificate=None,
    )
    result = await PrecheckExecutor().execute(ctx)
    return result, execution


class TestDUTCapabilityPrecheckGate:
    async def test_layers_exceed_strict_fails(self, db, lab):
        dut = _make_dut(db, max_dl_layers=2)
        res, execution = await _run_precheck(
            db, lab, dut_profile_id=str(dut.id), mimo_layers=4, modulation="256QAM", strict=True,
        )
        assert res.status == StepExecutionStatus.FAILED
        assert "声明能力不满足" in (res.error_message or "")
        # Codex P2 (3083096): 早期 strict fail 也必须持久化 precheck phase result —
        # 否则 session 读出来是 pending, UI 看不到 violation。验返回值 + DB 两侧。
        assert res.measurements is not None
        assert res.measurements["dut_capability_check"]["violations"]
        assert res.measurements["overall_pass"] is False
        assert res.measurements["operational_ready"] is False
        db.refresh(execution)
        persisted = (execution.measurements or {})["phases"]["precheck"]
        assert persisted["operational_ready"] is False
        assert persisted["dut_capability_check"]["consistent"] is False
        assert persisted["dut_capability_check"]["violations"]

    async def test_layers_exceed_optout_no_dutcap_fail(self, db, lab):
        dut = _make_dut(db, max_dl_layers=2)
        res, _ = await _run_precheck(
            db, lab, dut_profile_id=str(dut.id), mimo_layers=4, modulation="256QAM", strict=False,
        )
        # opt-out: section 2.3 降级 warning, 不因 dut_capability FAILED
        assert "声明能力不满足" not in (res.error_message or "")

    async def test_within_declared_no_dutcap_fail(self, db, lab):
        dut = _make_dut(db, max_dl_layers=4, max_modulation_dl="256QAM")
        res, _ = await _run_precheck(
            db, lab, dut_profile_id=str(dut.id), mimo_layers=2, modulation="64QAM", strict=True,
        )
        assert "声明能力不满足" not in (res.error_message or "")

    async def test_no_dut_profile_id_skips(self, db, lab):
        res, _ = await _run_precheck(
            db, lab, dut_profile_id=None, mimo_layers=4, modulation="256QAM", strict=True,
        )
        assert "声明能力" not in (res.error_message or "")
