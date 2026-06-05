"""SIM 身份核对 precheck 门集成测试 (P2-13 Phase 2, sibling of dut_capability gate)。

config.sim_profile_id 指向声明卡时, precheck section 2.4b 拿 attach 记录 IMSI 跟 SIMProfile.imsi
比 —— 不一致 (插错卡): strict → FAILED, opt-out → 降级 warning。无 sim_profile_id / 卡无 imsi /
无 dut_attach → skip。
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
from app.models.lab_profile import LabProfile
from app.models.sim_profile import SIMProfile
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
    """空 drivers — SIM 身份核对 (section 2.4b) 拿 attach 记录 + DB 声明比, 不依赖 driver。"""
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="SIMId-Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    lp = LabProfile(name="SIMId-Lab", chamber_config_id=c.id, is_active=True)
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _make_sim(db, *, imsi=None) -> SIMProfile:
    s = SIMProfile(name=f"SIM-{uuid.uuid4().hex[:8]}", imsi=imsi, card_kind="test_sim")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


async def _run_precheck(db, lab, *, sim_profile_id, attach_imsi, strict):
    test_case, _ = build_mimo_ota_test_case(
        db, name=f"SIMIdCase-{uuid.uuid4().hex[:8]}", description="sim identity gate",
        lab_profile_id=lab.id,
        config_overrides={
            "sim_profile_id": sim_profile_id,
            "precheck_strict_sim_identity": strict,
            # 隔离其它门, 只观察 sim_identity 信号
            "precheck_strict_cal": False,
            "precheck_strict_dut": False,
            "precheck_strict_dut_capability": False,
        },
        created_by="pytest-simid",
    )
    measurements = {}
    if attach_imsi is not None:
        measurements["dut_attach"] = {"imsi": attach_imsi, "rrc_connected": True}
    execution = TestExecution(
        test_case_id=test_case.id, status="pending", started_at=datetime.utcnow(),
        config={"step_descriptors": []}, measurements=measurements, executed_by="pytest-simid",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    ctx = StepExecutionContext(
        db=db, step=StepDescriptor(id="pc", type="MIMO_OTA_PRECHECK", parameters={}),
        test_execution=execution, lab_profile=lab, calibration_certificate=None,
    )
    return await PrecheckExecutor().execute(ctx), execution


class TestSIMIdentityPrecheckGate:
    async def test_mismatch_strict_fails(self, db, lab):
        sim = _make_sim(db, imsi="460001234567890")
        res, _ = await _run_precheck(
            db, lab, sim_profile_id=str(sim.id), attach_imsi="310260000000001", strict=True,
        )
        assert res.status == StepExecutionStatus.FAILED
        assert "SIM 身份不符" in (res.error_message or "")
        # 脱敏: 完整订户号不出现在 error
        assert "4567890" not in (res.error_message or "")

    async def test_mismatch_optout_no_sim_fail(self, db, lab):
        sim = _make_sim(db, imsi="460001234567890")
        res, _ = await _run_precheck(
            db, lab, sim_profile_id=str(sim.id), attach_imsi="310260000000001", strict=False,
        )
        assert "SIM 身份不符" not in (res.error_message or "")
        mm = (res.measurements or {}).get("sim_identity_check")
        assert mm is not None and mm["consistent"] is False

    async def test_match_no_fail(self, db, lab):
        sim = _make_sim(db, imsi="460001234567890")
        res, _ = await _run_precheck(
            db, lab, sim_profile_id=str(sim.id), attach_imsi="460001234567890", strict=True,
        )
        assert "SIM 身份不符" not in (res.error_message or "")
        assert (res.measurements or {})["sim_identity_check"]["consistent"] is True

    async def test_no_dut_attach_skips(self, db, lab):
        # 没 attach 记录 → 无可比, 跳过 (不 fail)
        sim = _make_sim(db, imsi="460001234567890")
        res, _ = await _run_precheck(
            db, lab, sim_profile_id=str(sim.id), attach_imsi=None, strict=True,
        )
        assert "SIM 身份不符" not in (res.error_message or "")
        assert (res.measurements or {}).get("sim_identity_check") is None

    async def test_no_sim_profile_id_skips(self, db, lab):
        res, _ = await _run_precheck(
            db, lab, sim_profile_id=None, attach_imsi="460001234567890", strict=True,
        )
        assert (res.measurements or {}).get("sim_identity_check") is None

    async def test_sim_without_declared_imsi_skips(self, db, lab):
        # 卡没声明 imsi → 无可比, 跳过
        sim = _make_sim(db, imsi=None)
        res, _ = await _run_precheck(
            db, lab, sim_profile_id=str(sim.id), attach_imsi="460001234567890", strict=True,
        )
        assert (res.measurements or {}).get("sim_identity_check") is None
