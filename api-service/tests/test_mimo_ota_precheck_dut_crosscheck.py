"""DUTProfile 声明 vs 实测协商交叉核对 precheck 集成测试 (阶段 4)。

precheck section 2.5b: baseStation.query_ue_capability() 返回 source==real_ue 时, 拿实测协商
能力跟 DUTProfile **声明**双向比 —— 不一致 → audit surface (measurements.dut_capability_mismatch
+ dut_capability_observed), **不 fail, 不覆盖声明** (声明 DB row 保持原值, operator 显式反写)。

跟 dut_capability_gate (2.3 请求 vs 声明, 会 fail) 区别: 2.5b 是 attach 后 vs 实测, audit-only。
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


class _FakeRealBS:
    """最小 baseStation: query_ue_capability 返回受控的实测协商能力 (source 可配)。"""

    def __init__(self, cap: dict):
        self._cap = cap

    async def query_ue_capability(self) -> dict:
        return self._cap


@pytest.fixture
def _hal_with_bs():
    """把一个 fake baseStation 装进 HAL, 让 precheck section 2.5 跑起来; 其它 driver 清空。"""
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved = dict(hal.drivers)

    def _install(cap: dict):
        hal.drivers.clear()
        hal.drivers["baseStation"] = _FakeRealBS(cap)

    yield _install
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="DUTXC-Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    lp = LabProfile(name="DUTXC-Lab", chamber_config_id=c.id, is_active=True)
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _make_dut(db, **kw) -> DUTProfile:
    d = DUTProfile(name=f"DUT-{uuid.uuid4().hex[:8]}", **kw)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


async def _run_precheck(db, lab, *, dut_profile_id, mimo_layers, modulation):
    # 声明校验放行 (请求 ≤ 声明), 只观察 2.5b 交叉核对信号; strict 门全关。
    test_case, _ = build_mimo_ota_test_case(
        db, name=f"XCheck-{uuid.uuid4().hex[:8]}", description="dut crosscheck",
        lab_profile_id=lab.id,
        config_overrides={
            "dut_profile_id": dut_profile_id,
            "mimo_layers": mimo_layers,
            "modulation": modulation,
            "precheck_strict_dut_capability": False,
            "precheck_strict_cal": False,
            "precheck_strict_dut": False,
        },
        created_by="pytest-xcheck",
    )
    execution = TestExecution(
        test_case_id=test_case.id, status="pending", started_at=datetime.utcnow(),
        config={"step_descriptors": []}, measurements={}, executed_by="pytest-xcheck",
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


class TestDUTCapabilityCrosscheckPrecheck:
    async def test_declared_vs_observed_mismatch_surfaced_not_overwritten(
        self, db, lab, _hal_with_bs
    ):
        # 声明 max DL 4 层 / 256QAM, 但真实 UE 只协商到 2 层 / 64QAM
        dut = _make_dut(db, max_dl_layers=4, max_modulation_dl="256QAM")
        _hal_with_bs({
            "source": "real_ue", "max_dl_layers": 2, "max_ul_layers": 1,
            "max_modulation_dl": "64QAM", "max_modulation_ul": "16QAM",
        })
        # 请求 2 层 ≤ 声明 4 → section 2.3 放行; 2.5b 拿声明 4 vs 实测 2 → mismatch
        res, execution = await _run_precheck(
            db, lab, dut_profile_id=str(dut.id), mimo_layers=2, modulation="64QAM",
        )
        # 1) mismatch surface 在 measurements (不管 overall pass/fail, audit-only)
        mm = (res.measurements or {}).get("dut_capability_mismatch")
        assert mm is not None and mm["consistent"] is False
        fields = {x["field"] for x in mm["mismatches"]}
        assert "max_dl_layers" in fields and "max_modulation_dl" in fields
        # 2) observed 单独记录 (含 dut_profile_id 供 GUI 反写)
        obs = (res.measurements or {}).get("dut_capability_observed")
        assert obs["source"] == "real_ue" and obs["max_dl_layers"] == 2
        assert obs["dut_profile_id"] == str(dut.id)
        # 3) ⭐ 声明 DB row **没被覆盖** —— 仍是 4 / 256QAM (audit-only, operator 显式反写)
        db.refresh(dut)
        assert dut.max_dl_layers == 4 and dut.max_modulation_dl == "256QAM"
        # 4) DB 持久化也带 mismatch (precheck phase result)
        db.refresh(execution)
        persisted = (execution.measurements or {})["phases"]["precheck"]
        assert persisted["dut_capability_mismatch"]["consistent"] is False

    async def test_declared_matches_observed_consistent(self, db, lab, _hal_with_bs):
        dut = _make_dut(db, max_dl_layers=2, max_modulation_dl="64QAM")
        _hal_with_bs({
            "source": "real_ue", "max_dl_layers": 2, "max_ul_layers": 1,
            "max_modulation_dl": "64QAM", "max_modulation_ul": "16QAM",
        })
        res, _ = await _run_precheck(
            db, lab, dut_profile_id=str(dut.id), mimo_layers=2, modulation="64QAM",
        )
        mm = (res.measurements or {}).get("dut_capability_mismatch")
        assert mm is not None and mm["consistent"] is True and mm["mismatches"] == []

    async def test_mock_source_skips_crosscheck(self, db, lab, _hal_with_bs):
        # source != real_ue (mock) → skipped, 不拿假数据判不一致
        dut = _make_dut(db, max_dl_layers=4, max_modulation_dl="256QAM")
        _hal_with_bs({
            "source": "mock", "max_dl_layers": 2,
            "max_modulation_dl": "64QAM",
        })
        res, _ = await _run_precheck(
            db, lab, dut_profile_id=str(dut.id), mimo_layers=2, modulation="64QAM",
        )
        mm = (res.measurements or {}).get("dut_capability_mismatch")
        assert mm is not None and mm["skipped"] is True and mm["consistent"] is True

    async def test_no_dut_profile_no_crosscheck(self, db, lab, _hal_with_bs):
        _hal_with_bs({"source": "real_ue", "max_dl_layers": 2})
        res, _ = await _run_precheck(
            db, lab, dut_profile_id=None, mimo_layers=2, modulation="64QAM",
        )
        assert (res.measurements or {}).get("dut_capability_mismatch") is None
        assert (res.measurements or {}).get("dut_capability_observed") is None
