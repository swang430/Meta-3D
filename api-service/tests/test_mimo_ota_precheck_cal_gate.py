"""Cartesian tests for the P1-8 commissioning precheck cal-missing gate.

Why this file exists: PR #59 (P1-7) + Codex P2 review on PR #60 surfaced that
[`PrecheckExecutor`](../app/services/mimo_ota/executors/precheck.py) was
computing `overall_pass = critical_online and qz_pass and ue_cap_pass` —
calibration state was written into `result_payload` but **never entered the
gate**. An uncalibrated chamber could pass precheck and silently fall back to
`typical_cable_loss_db + duplexer - pa_gain` in the measure phase, producing
.asc files based on typical values rather than measured path-loss.

P1-8 fix（P2-45 后由审计 policy 选择 Diagnostic）：
  - Default `precheck_strict_cal=True`: cal missing/broken → precheck FAIL
  - Explicit Diagnostic policy: effective `precheck_strict_cal=False`, but
    `cal_pass_reason` records "bypassed via precheck_strict_cal=False
    (would-fail-under-strict: ...)" so audit trails know

These tests pin the 12-cell cartesian:
  (path_loss_cal: present / missing)
    × (cal_cert: None / overall_pass=True / overall_pass=False)
    × (precheck_strict_cal: True / False)
  = 2 × 3 × 2 = 12 cases

Each case asserts:
  - `result.status` (SUCCESS / FAILED)
  - `result.measurements["overall_pass"]`
  - `result.measurements["cal_pass"]`
  - `result.measurements["cal_pass_reason"]` (substring match)
  - `result.error_message` contains the failure cause when FAILED
"""
from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

import uuid
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.base_station import BaseStationDriver
from app.hal.base_station_compatibility import (
    build_compatibility_payload,
    build_measure_execution_requirements_from_configuration,
    canonical_payload_digest,
)
from app.models.calibration import CalibrationCertificate
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile
from app.models.channel_asset import ChannelAsset
from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePathLossCalibration,
)
from app.models.test_plan import TestCase, TestExecution
from app.services.channel_engine_client import ChannelEngineClient
from app.services import instrument_test_lease
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota import build_mimo_ota_test_case
from app.services.mimo_ota.executors.measure import (
    MeasureExecutor,
    _evaluate_path_loss_provenance_for_measure,
    _is_path_loss_certificate_verified,
)
from app.services.mimo_ota.executors.precheck import PrecheckExecutor
from app.services.test_execution import (
    StepDescriptor,
    StepExecutionContext,
    StepExecutionStatus,
)
from app.schemas.mimo_ota.config import canonicalize_mimo_ota_configuration_payload


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _bind_unbound_mock_measurement(
    monkeypatch,
    context: StepExecutionContext,
    base_station,
) -> None:
    """Give direct MEASURE tests the same diagnostic lease truth as production."""

    adapter_id = base_station.adapter_id
    execution_config = dict(context.test_execution.config or {})
    test_case = context.db.get(TestCase, context.test_execution.test_case_id)
    requirements = build_measure_execution_requirements_from_configuration(
        test_case.configuration
    )
    compatibility = build_compatibility_payload(requirements, None)
    legacy_freeze = {
        "resolution": {
            "schema_version": 1,
            "adapter": None,
            "status": "diagnostic_unbound",
            "execution_mode": "simulated",
            "profile": None,
        },
        "compatibility": compatibility,
        "mimo_ota_configuration": canonicalize_mimo_ota_configuration_payload(
            dict(test_case.configuration or {})
        ),
    }
    legacy_freeze["digest"] = canonical_payload_digest(legacy_freeze)
    execution_config["base_station_adapter_profile_freeze"] = legacy_freeze
    context.test_execution.config = execution_config
    context.db.add(context.test_execution)
    context.db.commit()
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="legacy-measure-test",
        measurement_attempt_id=None,
        adapter_id=adapter_id,
        session_token="legacy-measure-session",
    )
    monkeypatch.setattr(
        instrument_test_lease,
        "active_base_station_lease_identity",
        lambda: lease,
    )


# ---------------------------------------------------------------------------
# Fixtures — minimal scaffold to exercise PrecheckExecutor in isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Cal-Gate-Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="Cal-Gate-Lab",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def instrument_categories(db):
    """Seed the critical InstrumentCategory rows so precheck's
    `critical_online` gate isn't the blocker we're testing."""
    rows = [
        InstrumentCategory(
            category_key="channelEmulator",
            category_name="信道仿真器",
            driver_mode="mock",
            is_active=True,
            display_order=1,
        ),
        InstrumentCategory(
            category_key="baseStation",
            category_name="基站仿真器",
            driver_mode="mock",
            is_active=True,
            display_order=2,
        ),
    ]
    for r in rows:
        db.add(r)
    db.commit()
    return rows


class _RealLikeChannelEmulator:
    """Non-mock channelEmulator stand-in. P1-9 runtime mock-awareness (Codex on
    PR #75): the strict CAL gate only engages against a real channelEmulator
    (a mock CE = simulated measurement → cal moot → auto-skip). These tests are
    about the cal gate's logic, so CE must read as real. precheck only
    hasattr-guard-calls get_user_alignment_status / list_external_units, so a
    bare instance is enough (they're skipped).

    P2-59 ①：MEASURE 在首次 CE I/O 前按驱动 manifest 冻结 / 对账执行计划，没有 manifest
    的驱动不宣称任何加载模式（P2-57 fail-closed）→ 会在启动期被拒。这个替身要读成
    「真实但什么都能装」，所以借 mock 的 manifest 声明、换个 adapter_id。"""

    from app.hal.channel_emulator import MockChannelEmulator as _M

    adapter_manifest = _M.adapter_manifest.model_copy(
        update={"adapter_id": "real_like_channel_emulator", "model_name": "Real-like CE"}
    )


@pytest.fixture
def hal_with_mocks(instrument_categories):
    """Inject drivers so precheck's `_CRITICAL_INSTRUMENT_CATEGORIES` check
    passes. channelEmulator is a *real-like* (non-mock) stub so the strict CAL
    gate engages — see `_RealLikeChannelEmulator`. baseStation stays mock
    (these tests set precheck_strict_dut=False, so BS mock-ness is irrelevant
    to the CAL-gate signal). Cleared after the test."""
    from app.hal import MockBaseStation
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["channelEmulator"] = _RealLikeChannelEmulator()
    hal.drivers["baseStation"] = registered_mock_base_station("mock-bs", {"model": "UXM 5G E7515B"})
    yield hal
    hal.drivers.clear()
    hal.drivers.update(saved)


# ---------------------------------------------------------------------------
# Helpers — seed cal data + build StepExecutionContext
# ---------------------------------------------------------------------------

def _seed_path_loss_cal(
    db,
    chamber_id,
    frequency_mhz: float = 3500.0,
    *,
    use_mock: Optional[bool] = False,
    valid_until: Optional[datetime] = None,
) -> ProbePathLossCalibration:
    """Write a minimal VALID ProbePathLossCalibration so
    `latest_pl is not None` and `result_payload["path_loss_calibration_valid"]
    = True`."""
    now = datetime.utcnow()
    cal = ProbePathLossCalibration(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        probe_path_losses={"0": {"path_loss_db": 5.0}, "1": {"path_loss_db": 5.2}},
        sgh_model="ETS-Lindgren 3164-06",
        sgh_gain_dbi=8.0,
        status=CalibrationStatus.VALID.value,
        calibrated_at=now,
        valid_until=valid_until or now.replace(year=now.year + 1),
    )
    # P1-27: pre-existing tests are about certificate existence/frequency,
    # so they explicitly represent a real calibration. ``setattr`` keeps the
    # RED test importable before the model column exists; the producer tests
    # separately prove the value survives a database round-trip.
    setattr(cal, "use_mock", use_mock)
    db.add(cal)
    db.commit()
    db.refresh(cal)
    return cal


def _seed_complete_legacy_path_loss_cal(db, chamber) -> ProbePathLossCalibration:
    """复现现场遗留证书：完整参与补偿，但来源列仍为 NULL。"""
    now = datetime.utcnow()
    cal = ProbePathLossCalibration(
        chamber_id=chamber.id,
        frequency_mhz=3500.0,
        operating_mode="mimo_ota",
        use_mock=None,
        probe_path_losses={
            str(probe_id): {
                "path_loss_db": 56.77,
                "pol_v_db": 56.77,
                "pol_h_db": 56.77,
            }
            for probe_id in range(1, chamber.num_probes + 1)
        },
        sgh_model="legacy-sgh",
        sgh_gain_dbi=8.0,
        avg_path_loss_db=56.77,
        status=CalibrationStatus.VALID.value,
        calibrated_at=now,
        valid_until=now + timedelta(days=1),
    )
    db.add(cal)
    db.commit()
    db.refresh(cal)
    return cal


def _make_cal_cert(overall_pass: bool) -> CalibrationCertificate:
    """Build a CalibrationCertificate row with a chosen `overall_pass`.

    Caller is responsible for db.add / commit if persistence is needed —
    `context.calibration_certificate` is set directly on StepExecutionContext
    so we don't even have to attach it to a TestCase. Keeping it detached
    avoids the LabProfile.active_calibration_certificate_id machinery that
    would otherwise interfere with the cert-state parametrization.
    """
    return CalibrationCertificate(
        certificate_number=f"CAL-GATE-TEST-{uuid.uuid4().hex[:8]}",
        calibration_date=datetime.utcnow(),
        valid_until=datetime.utcnow(),
        overall_pass=overall_pass,
    )


def _refreeze_ce_plan(db, ctx):
    """用例在 _build_context 之后改了 TestCase 配置：按真实写方形态重冻 CE 执行计划。
    不重冻的话对账会把用例自己造的 engine_mode 变化判成漂移 —— 那正是它该判的（P2-59 ①）。"""
    from sqlalchemy.orm.attributes import flag_modified

    from app.services.channel_emulator_execution_plan import (
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
        freeze_channel_emulator_execution_plan,
    )
    from app.services.instrument_hal_service import get_hal_service

    execution = ctx.test_execution
    execution.config = {
        key: value
        for key, value in execution.config.items()
        if key not in {CE_LOAD_REQUEST_FREEZE_CONFIG_KEY, CE_PLAN_FREEZE_CONFIG_KEY}
    }
    flag_modified(execution, "config")
    freeze_channel_emulator_execution_plan(db, get_hal_service(), execution)
    db.commit()


async def _execute_direct_measure_in_receipt_scope(ctx):
    """Run a direct MEASURE fixture inside the execution-owned CE scope.

    Production reaches MEASURE through the joint BaseStation/CE session.  The
    two tests below intentionally call the executor directly, so they must
    provide the same task-local receipt owner instead of weakening the
    production fail-closed owner check.
    """

    from app.services.channel_emulator_binding import CE_FREEZE_CONFIG_KEY
    from app.core.logging_config import current_execution_id
    from app.services.channel_emulator_execution_plan import (
        CE_PLAN_FREEZE_CONFIG_KEY,
        plan_from_frozen_payload,
    )
    from app.services.channel_emulator_operation_receipt import (
        ChannelEmulatorOperationRecorderOwner,
        channel_emulator_operation_recorder_scope,
    )
    from app.services.instrument_hal_service import get_hal_service

    execution = ctx.test_execution
    config = execution.config
    binding = config[CE_FREEZE_CONFIG_KEY]
    plan = plan_from_frozen_payload(config[CE_PLAN_FREEZE_CONFIG_KEY])
    emulator = get_hal_service().drivers["channelEmulator"]
    owner = ChannelEmulatorOperationRecorderOwner(
        db=ctx.db,
        execution_pk=execution.id,
        execution_id=str(execution.id),
        session_id="direct-measure-receipt-session",
        operation_scope="direct-measure-fixture",
        measurement_attempt_id=None,
        binding_digest=str(binding["binding_digest"]),
        binding_freeze_digest=str(
            binding.get("digest") or canonical_payload_digest(binding)
        ),
        plan_digest=plan.digest,
        asset_digest=None,
        lease_id="direct-measure-receipt-lease",
        instrument_id=str(
            getattr(emulator, "instrument_id", "direct-measure-channel-emulator")
        ),
        adapter_id=plan.adapter_id,
        execution_mode="simulated",
        plan=plan,
        driver=emulator,
    )
    execution_token = current_execution_id.set(str(execution.id))
    try:
        with channel_emulator_operation_recorder_scope(owner):
            return await MeasureExecutor().execute(ctx)
    finally:
        current_execution_id.reset(execution_token)


def _build_context(
    db,
    lab,
    *,
    cal_cert: Optional[CalibrationCertificate],
    strict_mode: bool,
    frequency_hz: Optional[float] = None,
    channel_asset_id: Optional[str] = None,
) -> StepExecutionContext:
    """Build a TestCase + TestExecution + StepExecutionContext pinned to the
    given strict mode and (detached) cal cert.

    ``frequency_hz``: 显式钉住目标频率。**±5% 窗口的边界测试必须给它** ——
    否则窗口跟着 ``MIMOOTAConfiguration.frequency_hz`` 的默认值漂，改一次默认
    就红一次（2026-08-07 实证：默认从 3.5e9 换成 3.54999e9 时，三条边界测试
    同时红，而它们测的契约根本没变）。留 None = 沿用 schema 默认（对不关心
    频率的用例是对的）。"""
    test_case, _descriptors = build_mimo_ota_test_case(
        db,
        name=f"CalGateCase-{uuid.uuid4().hex[:8]}",
        description="P1-8 cartesian",
        lab_profile_id=lab.id,
        config_overrides={
            **({"frequency_hz": frequency_hz} if frequency_hz is not None else {}),
            **({"channel_asset_id": channel_asset_id} if channel_asset_id is not None else {}),
            # P1-9 (2026-05-19): dut gate disabled so it doesn't fight the
            # cal_pass test signal — dut gate is covered by
            # test_mimo_ota_precheck_dut_gate.py. Without this, the cartesian's
            # no-dut default would fail at dut_pass first and we couldn't
            # observe cal_pass behavior in isolation.
            "precheck_strict_dut": False,
            # Keep config defaults; pass_criteria.max_quiet_zone_ripple_db=1.0
            # so the precheck QZ ripple gate (default fallback 0.7 dB) passes.
        },
        created_by="pytest-cal-gate",
        execution_policy=(
            None
            if strict_mode
            else {
                "schema_version": 1,
                "mode": "diagnostic",
                "reason": "calibration gate diagnostic fixture",
                "updated_by": "pytest-cal-gate",
                "updated_at": "2026-08-29T00:00:00Z",
            }
        ),
    )
    execution = TestExecution(
        test_case_id=test_case.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={"step_descriptors": []},
        executed_by="pytest-cal-gate",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    # P2-59 ①：MEASURE 在首次 CE I/O 前对账启动期冻结的执行计划（它引用 binding 冻结件的
    # binding_digest）。真实写方（runner / commissioning）在 binding 之后用同一个服务函数冻，
    # 端到端夹具照同一形态冻，走不到 CE 加载的用例不受影响。
    from app.services.channel_emulator_binding import CE_FREEZE_CONFIG_KEY as _CE_BINDING_KEY
    from app.services.channel_emulator_execution_plan import (
        freeze_channel_emulator_execution_plan as _freeze_ce_plan,
    )
    from app.services.instrument_hal_service import get_hal_service as _hal_service

    hal = _hal_service()
    ce_driver = hal.drivers["channelEmulator"]
    execution.config = {
        **execution.config,
        _CE_BINDING_KEY: {
            "binding_digest": "cal-gate-fixture-" + "0" * 47,
            "resolved_binding": {
                "status": "configured",
                "manifest": ce_driver.adapter_manifest.model_dump(mode="json"),
            },
        },
    }
    try:
        _freeze_ce_plan(db, hal, execution)
    except ValueError:
        # 用例故意给了冻不出计划的配置（如退役资产）：真实路径会在启动期拒绝（P2-59 门守），
        # 这里不冻，让用例观察 MEASURE 自己那道更早的门。
        pass
    db.commit()
    db.refresh(execution)

    step = StepDescriptor(
        id="precheck-step", type="MIMO_OTA_PRECHECK", parameters={},
    )
    return StepExecutionContext(
        db=db,
        step=step,
        test_execution=execution,
        lab_profile=lab,
        calibration_certificate=cal_cert,
    )


@pytest.mark.asyncio
async def test_direct_measure_rejects_inactive_asset_before_hardware_connect(
    db,
    lab,
    hal_with_mocks,
):
    """已有用例在资产退役后重跑，也必须在任何仪表连接前 fail-loud。"""

    class _MustNotConnect:
        async def connect(self):
            raise AssertionError("inactive asset gate ran after hardware connect")

    asset = ChannelAsset(
        name=f"retired-{uuid.uuid4().hex[:8]}",
        source_type="standard_3gpp",
        allowed_targets=["asc_baked"],
        payload={"cdl_model_name": "UMa CDL-C NLOS"},
        is_active=False,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    hal_with_mocks.drivers["positioner"] = _MustNotConnect()
    hal_with_mocks.drivers["baseStation"] = _MustNotConnect()
    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=False,
        channel_asset_id=str(asset.id),
    )

    result = await MeasureExecutor().execute(ctx)

    assert result.status == StepExecutionStatus.FAILED
    assert "已退役" in (result.error_message or "")


@pytest.mark.asyncio
async def test_ca_partial_add_surfaces_cleanup_failure_in_failed_result(
    db,
    lab,
    hal_with_mocks,
    monkeypatch,
):
    from app.hal import MockPositioner

    class _Positioner(MockPositioner):
        async def connect(self):
            return True

        async def move_to(self, *_args, **_kwargs):
            return True

        async def disconnect(self):
            return True

    class _PartialCaBaseStation:
        MIMO_PORT_PRESETS = {}
        SCELL_ACTIVATION_READBACK_AUTHORITATIVE = True
        adapter_id = "uxm"
        simulated = True

        def __init__(self) -> None:
            self.add_calls = 0

        async def connect(self):
            return True

        async def set_cell_config(self, _config):
            return True

        async def apply_requested_config(self, _requested):
            return True

        async def apply_config(self, requested):
            return await BaseStationDriver.apply_config(self, requested)

        async def apply_route(self, frozen_adapter):
            return await BaseStationDriver.apply_route(self, frozen_adapter)

        def route_allows_diagnostic_execution(self, receipt):
            return BaseStationDriver.route_allows_diagnostic_execution(
                self,
                receipt,
            )

        async def add_secondary_cell(self, _index, _config):
            self.add_calls += 1
            return self.add_calls == 1

        async def activate_secondary_cells(self, **_kwargs):
            raise AssertionError("partial add must block activation")

        async def remove_all_secondary_cells(self):
            return False

        async def stop_signaling(self):
            return True

        async def disconnect(self):
            return True

    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=False,
        frequency_hz=3.5e9,
    )
    test_case = db.get(TestCase, ctx.test_execution.test_case_id)
    test_case.configuration = {
        **test_case.configuration,
        "component_carriers": [
            {
                "frequency_hz": 3.5e9,
                "bandwidth_mhz": 100.0,
                "subcarrier_spacing_khz": 30,
                "band": "n78",
            },
            {
                "frequency_hz": 3.7e9,
                "bandwidth_mhz": 100.0,
                "subcarrier_spacing_khz": 30,
                "band": "n78",
            },
            {
                "frequency_hz": 3.8e9,
                "bandwidth_mhz": 100.0,
                "subcarrier_spacing_khz": 30,
                "band": "n78",
            },
        ],
    }
    db.commit()
    hal_with_mocks.drivers["positioner"] = _Positioner("mock-pos", {})
    hal_with_mocks.drivers["baseStation"] = _PartialCaBaseStation()
    _bind_unbound_mock_measurement(
        monkeypatch,
        ctx,
        hal_with_mocks.drivers["baseStation"],
    )

    result = await MeasureExecutor().execute(ctx)

    assert result.status == StepExecutionStatus.FAILED
    assert "SCell 2 添加失败" in (result.error_message or "")
    assert "remove_all_secondary_cells" in (result.error_message or "")
    assert any(
        "remove_all_secondary_cells" in warning
        for warning in result.warnings
    )


# ---------------------------------------------------------------------------
# 12-cell cartesian
# ---------------------------------------------------------------------------

# (path_loss_present, cal_cert_state, strict_mode)
#   - path_loss_present: bool — seed a VALID ProbePathLossCalibration or not
#   - cal_cert_state: "none" / "pass" / "fail" — None / overall_pass=True/False
#   - strict_mode: bool — config.precheck_strict_cal
# Expected (overall_pass, cal_pass, reason_keywords)
PARAMS = [
    # === STRICT (default) — gate active ===
    # path_loss present
    (True,  "none", True, True,  True,  ["ok"]),
    (True,  "pass", True, True,  True,  ["ok"]),
    (True,  "fail", True, False, False, ["not passed"]),
    # path_loss missing
    (False, "none", True, False, False, ["missing or invalid"]),
    (False, "pass", True, False, False, ["missing or invalid"]),
    (False, "fail", True, False, False, ["missing or invalid", "not passed"]),
    # === BYPASS — gate inert, audit trail records would-fail ===
    (True,  "none", False, True, True, ["bypassed"]),
    (True,  "pass", False, True, True, ["bypassed"]),
    (True,  "fail", False, True, True, ["bypassed", "cal_cert.overall_pass=False"]),
    (False, "none", False, True, True, ["bypassed", "path-loss calibration missing", "cal_cert is None"]),
    (False, "pass", False, True, True, ["bypassed", "path-loss calibration missing"]),
    (False, "fail", False, True, True, ["bypassed", "path-loss calibration missing", "cal_cert.overall_pass=False"]),
]


@pytest.mark.parametrize(
    "path_loss_present, cal_cert_state, strict_mode, "
    "expect_overall_pass, expect_cal_pass, expect_reason_keywords",
    PARAMS,
    ids=[
        f"{'pl_yes' if p else 'pl_no'}-cert_{c}-{'strict' if s else 'bypass'}"
        for (p, c, s, _o, _cp, _r) in PARAMS
    ],
)
@pytest.mark.asyncio
async def test_precheck_cal_gate_cartesian(
    db, lab, chamber, hal_with_mocks,
    path_loss_present: bool,
    cal_cert_state: str,
    strict_mode: bool,
    expect_overall_pass: bool,
    expect_cal_pass: bool,
    expect_reason_keywords: list[str],
):
    # Seed path-loss calibration if this case wants it
    if path_loss_present:
        _seed_path_loss_cal(db, chamber.id)

    # Build the cal_cert per state
    cal_cert: Optional[CalibrationCertificate]
    if cal_cert_state == "none":
        cal_cert = None
    elif cal_cert_state == "pass":
        cal_cert = _make_cal_cert(overall_pass=True)
    elif cal_cert_state == "fail":
        cal_cert = _make_cal_cert(overall_pass=False)
    else:  # pragma: no cover - parametrize bug guard
        raise AssertionError(f"unknown cal_cert_state {cal_cert_state!r}")

    ctx = _build_context(db, lab, cal_cert=cal_cert, strict_mode=strict_mode)
    result = await PrecheckExecutor().execute(ctx)

    measurements = result.measurements or {}

    expected_overall = None if expect_overall_pass else False
    assert measurements.get("overall_pass") is expected_overall, (
        f"overall_pass mismatch: got {measurements.get('overall_pass')}, "
        f"expected {expected_overall}; cal_pass_reason="
        f"{measurements.get('cal_pass_reason')!r}"
    )
    assert measurements.get("operational_ready") is expect_overall_pass
    assert measurements.get("cal_pass") == expect_cal_pass, (
        f"cal_pass mismatch: got {measurements.get('cal_pass')}, "
        f"expected {expect_cal_pass}"
    )

    reason = measurements.get("cal_pass_reason", "") or ""
    for keyword in expect_reason_keywords:
        assert keyword in reason, (
            f"cal_pass_reason missing keyword {keyword!r}; got {reason!r}"
        )

    # Status correlates with overall_pass
    if expect_overall_pass:
        assert result.status == StepExecutionStatus.SUCCESS, (
            f"expected SUCCESS, got {result.status}: {result.error_message}"
        )
    else:
        assert result.status == StepExecutionStatus.FAILED, (
            f"expected FAILED, got {result.status}"
        )
        # error_message must mention the cal failure so on-site operator knows why
        assert result.error_message and "Pre-check failed:" in result.error_message
        # At least one of the cal-related keywords appears in the error
        cal_keywords = [k for k in expect_reason_keywords if k not in ("bypassed",)]
        assert any(k in result.error_message for k in cal_keywords), (
            f"error_message {result.error_message!r} missing cal keywords {cal_keywords}"
        )


# ---------------------------------------------------------------------------
# Frequency-window boundary tests (P1-8 Codex P1 follow-up on 42af8ca)
#
# Codex flagged that the initial P1-8 implementation just checked
# `path_loss_calibration_valid` set by a chamber-only query — an old/
# different-band VALID cert (e.g. 700 MHz cert for a 3500 MHz test) would
# pass precheck silently and then leave Phase 3 with no usable cert.
#
# Fix: precheck now goes through ProbePathLossCalibrationService.
# get_latest_calibration(chamber_id, freq_mhz), which applies the same ±5%
# frequency window measure.py uses. These tests pin that window contract:
#   - 3500 MHz target accepts certs in 3325-3675 MHz
#   - 700 MHz cert at 3500 MHz target → strict FAIL with audit trail showing
#     "frequency_mismatch"
#   - bypass: same setup PASSes but cal_pass_reason still records would-fail
# ---------------------------------------------------------------------------


class TestFrequencyWindow:
    """Pin the ±5% frequency-matching contract between precheck and measure."""

    @pytest.mark.asyncio
    async def test_mismatched_frequency_strict_fails(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Cert at 700 MHz can't satisfy a 3500 MHz commissioning run."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=700.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True,
                             frequency_hz=3500e6)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.FAILED
        assert measurements["overall_pass"] is False
        assert measurements["cal_pass"] is False
        assert measurements["path_loss_calibration_valid"] is False
        # The cert exists for the chamber, just out of window — the audit
        # field disambiguates from "no cert at all" for operator UX
        assert measurements["path_loss_calibration_reason"] == "frequency_mismatch"
        assert "missing or invalid" in measurements["cal_pass_reason"]
        warning_text = "\n".join(result.warnings or [])
        assert "strict calibration gate will block Phase 3" in warning_text
        assert "fall back to default cable loss" not in warning_text

    @pytest.mark.asyncio
    async def test_mismatched_frequency_bypass_passes_with_audit(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Bypass lets the run continue but audit trail flags the mismatch."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=700.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=False)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["operational_ready"] is True
        assert measurements["overall_pass"] is None
        assert measurements["cal_pass"] is True
        # path_loss_calibration_valid still reflects reality (mismatched)
        assert measurements["path_loss_calibration_valid"] is False
        assert measurements["path_loss_calibration_reason"] == "frequency_mismatch"
        # Audit trail proves "this run happened despite the mismatch"
        assert "bypassed" in measurements["cal_pass_reason"]
        assert "path-loss calibration missing" in measurements["cal_pass_reason"]
        warning_text = "\n".join(result.warnings or [])
        assert "operator bypass permits Phase 3 without path-loss compensation" in warning_text
        assert "fall back to default cable loss" not in warning_text

    @pytest.mark.asyncio
    async def test_upper_boundary_within_window_passes(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """3500 × 1.05 = 3675 MHz cert ↔ 3500 MHz target: at-window edge,
        must pass strict."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3675.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True,
                             frequency_hz=3500e6)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["operational_ready"] is True
        assert measurements["overall_pass"] is None
        assert measurements["cal_pass"] is True
        assert measurements["path_loss_calibration_valid"] is True
        assert measurements["path_loss_calibration_frequency_mhz"] == 3675.0

    @pytest.mark.asyncio
    async def test_lower_boundary_within_window_passes(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """3500 × 0.95 = 3325 MHz cert ↔ 3500 MHz target: at-window edge,
        must pass strict."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3325.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True,
                             frequency_hz=3500e6)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["operational_ready"] is True
        assert measurements["overall_pass"] is None
        assert measurements["cal_pass"] is True
        assert measurements["path_loss_calibration_valid"] is True

    @pytest.mark.asyncio
    async def test_just_outside_upper_boundary_fails_strict(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Just above the +5% window: 3676 MHz cert vs 3500 MHz target →
        out of window → FAIL strict."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3676.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True,
                             frequency_hz=3500e6)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.FAILED
        assert measurements["path_loss_calibration_reason"] == "frequency_mismatch"

    @pytest.mark.asyncio
    async def test_target_frequency_recorded_in_audit_trail(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """`path_loss_calibration_target_frequency_mhz` always written so
        operator / audit can correlate the cert window with the test config."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3500.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True,
                             frequency_hz=3500e6)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert measurements["path_loss_calibration_target_frequency_mhz"] == 3500.0
        assert measurements["path_loss_calibration_frequency_mhz"] == 3500.0


# ---------------------------------------------------------------------------
# P1-27: path-loss calibration provenance is a strict allowlist.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "use_mock, strict_mode, expect_pass, reason_keywords",
    [
        (False, True, True, ["ok"]),
        (True, True, False, ["simulated", "provenance"]),
        (None, True, False, ["unknown", "provenance"]),
        (True, False, True, ["bypassed", "simulated", "provenance"]),
        (None, False, True, ["bypassed", "unknown", "provenance"]),
    ],
    ids=[
        "real-strict",
        "mock-strict",
        "unknown-strict",
        "mock-bypass",
        "unknown-bypass",
    ],
)
@pytest.mark.asyncio
async def test_path_loss_provenance_gate(
    db,
    lab,
    chamber,
    hal_with_mocks,
    use_mock: Optional[bool],
    strict_mode: bool,
    expect_pass: bool,
    reason_keywords: list[str],
):
    """A real run may trust only an explicitly real path-loss record.

    Historical rows are ``None`` rather than silently backfilled to real.
    Explicit strict bypass remains available for rehearsal, but its audit
    reason must still say exactly what strict mode would have rejected.
    """
    _seed_path_loss_cal(db, chamber.id, use_mock=use_mock)
    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=strict_mode,
        frequency_hz=3500e6,
    )

    result = await PrecheckExecutor().execute(ctx)
    measurements = result.measurements or {}

    assert measurements.get("path_loss_calibration_use_mock") is use_mock
    assert measurements.get("cal_pass") is expect_pass
    assert measurements.get("operational_ready") is expect_pass
    assert measurements.get("overall_pass") is (None if expect_pass else False)
    assert result.status == (
        StepExecutionStatus.SUCCESS if expect_pass else StepExecutionStatus.FAILED
    )

    reason = measurements.get("cal_pass_reason", "") or ""
    for keyword in reason_keywords:
        assert keyword in reason, f"missing {keyword!r} in {reason!r}"


@pytest.mark.parametrize(
    "use_mock, reason_keywords",
    [
        (True, ["simulated", "provenance"]),
        (None, ["unknown", "provenance"]),
    ],
    ids=["mock", "legacy-unknown"],
)
@pytest.mark.asyncio
async def test_direct_measure_rejects_untrusted_path_loss_before_hardware_touch(
    db,
    lab,
    chamber,
    hal_with_mocks,
    use_mock: Optional[bool],
    reason_keywords: list[str],
):
    """单阶段 MEASURE 不能绕过 PRECHECK 的 provenance 门。

    失败必须发生在 connect / SCPI 下发之前；否则即使最终返回失败，也已经
    改动了现场仪表状态。
    """

    class _MustNotConnect:
        async def connect(self):
            raise AssertionError("provenance gate ran after hardware connect")

    certificate = _seed_path_loss_cal(db, chamber.id, use_mock=use_mock)
    hal_with_mocks.drivers["positioner"] = _MustNotConnect()
    hal_with_mocks.drivers["baseStation"] = _MustNotConnect()
    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=True,
        frequency_hz=3500e6,
    )

    result = await MeasureExecutor().execute(ctx)

    assert result.status == StepExecutionStatus.FAILED
    application = (result.measurements or {})["path_loss_application"]
    assert application["status"] == "not_applied"
    assert application["provenance"] == (
        "simulated" if use_mock is True else "unknown"
    )
    assert application["reason"] == "rejected_untrusted"
    assert application["certificate_id"] == str(certificate.id)
    reason = result.error_message or ""
    for keyword in reason_keywords:
        assert keyword in reason, f"missing {keyword!r} in {reason!r}"


@pytest.mark.parametrize("cert_state", ["missing", "expired"])
@pytest.mark.asyncio
async def test_direct_measure_strict_rejects_missing_or_expired_cert_before_connect(
    db,
    lab,
    chamber,
    hal_with_mocks,
    cert_state: str,
):
    class _MustNotConnect:
        async def connect(self):
            raise AssertionError("calibration gate ran after hardware connect")

    if cert_state == "expired":
        _seed_path_loss_cal(
            db,
            chamber.id,
            use_mock=False,
            valid_until=datetime.utcnow() - timedelta(days=1),
        )
    hal_with_mocks.drivers["positioner"] = _MustNotConnect()
    hal_with_mocks.drivers["baseStation"] = _MustNotConnect()
    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=True,
        frequency_hz=3500e6,
    )

    result = await MeasureExecutor().execute(ctx)

    assert result.status == StepExecutionStatus.FAILED
    application = (result.measurements or {})["path_loss_application"]
    assert application["status"] == "not_applied"
    assert application["reason"] == cert_state
    assert application["certificate_id"] is None
    assert "missing or expired" in (result.error_message or "")


@pytest.mark.parametrize(
    "use_mock, ce_is_real, strict, expect_usable, expect_blocked",
    [
        (False, True, True, True, False),
        (True, True, True, False, True),
        (None, True, True, False, True),
        (True, True, False, False, False),
        (None, True, False, False, False),
        (True, False, True, True, False),
    ],
    ids=[
        "real-cert-real-run",
        "mock-cert-real-strict",
        "unknown-cert-real-strict",
        "mock-cert-real-bypass-not-applied",
        "unknown-cert-real-bypass-not-applied",
        "mock-cert-mock-run",
    ],
)
def test_measure_path_loss_provenance_policy(
    use_mock: Optional[bool],
    ce_is_real: bool,
    strict: bool,
    expect_usable: bool,
    expect_blocked: bool,
):
    """Opt-out may continue, but it must never apply simulated calibration
    values to a real measurement or let them influence formal KPIs."""
    usable, blocker = _evaluate_path_loss_provenance_for_measure(
        use_mock,
        channel_emulator_is_real=ce_is_real,
        strict=strict,
    )

    assert usable is expect_usable
    assert (blocker is not None) is expect_blocked


@pytest.mark.parametrize(
    "use_mock, expected",
    [(False, True), (True, False), (None, False)],
    ids=["real", "mock", "unknown"],
)
def test_path_loss_verified_flag_is_an_explicit_real_allowlist(
    use_mock: Optional[bool], expected: bool,
):
    """报告中的“已验证”不能只等于“证书存在”。"""
    assert _is_path_loss_certificate_verified(use_mock) is expected


def test_channel_generation_cannot_requery_a_rejected_mock_certificate(
    db, chamber,
):
    """MEASURE 已拒绝 cert 后，ASC/GCM calibration entries 必须消费同一个
    过滤结果；不能自己再查数据库把 mock 数值捞回来。"""
    _seed_path_loss_cal(db, chamber.id, use_mock=True)
    entries = ChannelEngineClient(db)._query_calibration_entries(
        chamber.id,
        3500e6,
        chamber,
        path_loss_calibration=None,
    )

    fallback_loss = chamber.typical_cable_loss_db
    if chamber.has_pa and chamber.pa_gain_db:
        fallback_loss -= chamber.pa_gain_db
    if chamber.has_duplexer and chamber.duplexer_insertion_loss_db:
        fallback_loss += chamber.duplexer_insertion_loss_db

    assert entries
    assert all(
        entry["cable_loss_db"] == pytest.approx(float(fallback_loss))
        for entry in entries
    )
    assert all(entry["cable_loss_db"] != 5.0 for entry in entries)


@pytest.mark.asyncio
async def test_asc_strategy_forwards_the_already_filtered_calibration_entries(chamber):
    """ASC strategy must not discard MEASURE's provenance-filtered entries and
    let the client auto-select a second, potentially simulated certificate."""
    from types import SimpleNamespace

    from app.services.channel_generation.asc_strategy import ExternalWaveformStrategy

    class CapturingChannelEngineClient:
        def __init__(self):
            self.kwargs = None

        async def synthesize_hardware_pipeline(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(success=False, message="stop after capture")

    client = CapturingChannelEngineClient()
    filtered_entries = [{"port": 1, "cable_loss_db": 1.25}]
    strategy = ExternalWaveformStrategy(
        emulator=object(),
        ce_client=client,
        chamber_config=chamber,
        calibration_entries=filtered_entries,
    )

    assert await strategy.generate_and_load(
        {"frequency_hz": 3.5e9},
        {"model_name": "UMa NLOS CDL-C"},
    ) is False
    assert client.kwargs["calibration_entries"] is filtered_entries


# ---------------------------------------------------------------------------
# Runtime mock-awareness (Codex on PR #75): mock/absent CE auto-skips cal gate
# ---------------------------------------------------------------------------

@pytest.fixture
def hal_with_mock_ce(instrument_categories):
    """channelEmulator is a real **mock** driver — used to verify the runtime
    auto-skip: strict CAL gate must be N/A when the measurement is simulated."""
    from app.hal import MockBaseStation, MockChannelEmulator
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["channelEmulator"] = MockChannelEmulator("mock-ce", {"model": "UXM 5G E7515B"})
    hal.drivers["baseStation"] = registered_mock_base_station("mock-bs", {"model": "UXM 5G E7515B"})
    yield hal
    hal.drivers.clear()
    hal.drivers.update(saved)


@pytest.fixture
def hal_with_full_mock_chain(instrument_categories):
    from app.hal import (
        MockBaseStation,
        MockChannelEmulator,
        MockPositioner,
        MockSignalAnalyzer,
    )
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["channelEmulator"] = MockChannelEmulator(
        "mock-ce", {"model": "UXM 5G E7515B"}
    )
    hal.drivers["baseStation"] = registered_mock_base_station("mock-bs", {"model": "UXM 5G E7515B"})
    positioner = MockPositioner("mock-pos", {"model": "UXM 5G E7515B"})

    async def instant_move_to(azimuth, elevation, **_kwargs):
        positioner._azimuth = azimuth
        positioner._elevation = elevation
        return True

    positioner.move_to = instant_move_to
    hal.drivers["positioner"] = positioner
    hal.drivers["signalAnalyzer"] = MockSignalAnalyzer(
        "mock-sa", {"model": "UXM 5G E7515B"}
    )
    yield hal
    hal.drivers.clear()
    hal.drivers.update(saved)


@pytest.mark.asyncio
async def test_ce_plan_drift_rejects_before_any_instrument_connection_or_write(
    db,
    lab,
    hal_with_full_mock_chain,
    monkeypatch,
):
    """冻结后 engine_mode 漂移必须在任何仪器连接/配置写入前 fail-loud。"""

    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=False,
        frequency_hz=3500e6,
    )
    test_case = db.get(TestCase, ctx.test_execution.test_case_id)
    frozen_load_mode = ctx.test_execution.config[
        "channel_emulator_execution_plan_freeze"
    ]["requested_load_mode"]
    drifted_engine_mode = (
        "mimo_first_asc"
        if frozen_load_mode == "native_model"
        else "keysight_gcm"
    )
    test_case.configuration = canonicalize_mimo_ota_configuration_payload(
        {
            **dict(test_case.configuration or {}),
            "engine_mode": drifted_engine_mode,
        }
    )
    db.commit()
    base_station = hal_with_full_mock_chain.drivers["baseStation"]
    _bind_unbound_mock_measurement(monkeypatch, ctx, base_station)

    positioner = hal_with_full_mock_chain.drivers["positioner"]
    channel_emulator = hal_with_full_mock_chain.drivers["channelEmulator"]
    io_spies = {
        "positioner.connect": (positioner, "connect"),
        "base_station.connect": (base_station, "connect"),
        "base_station.apply_config": (base_station, "apply_config"),
        "base_station.apply_route": (base_station, "apply_route"),
        "base_station.configure_mac_throughput_test": (
            base_station,
            "configure_mac_throughput_test",
        ),
        "channel_emulator.connect": (channel_emulator, "connect"),
    }
    installed_spies = []
    for label, (driver, method_name) in io_spies.items():
        spy = AsyncMock(side_effect=AssertionError(f"CE plan drift gate ran after {label}"))
        setattr(driver, method_name, spy)
        installed_spies.append(spy)

    with pytest.raises(RuntimeError, match="frozen execution plan does not match"):
        await MeasureExecutor().execute(ctx)

    for spy in installed_spies:
        spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_testcase_stat_count_drives_the_frozen_statistical_basis(
    db,
    lab,
    chamber,
    hal_with_full_mock_chain,
    monkeypatch,
):
    """P1-74: TestCase 的 stat_count 必须真的驱动窗口请求的统计基。

    行为门，不是存在性门：断言值取自 TestCase 而非任何字面量。用 3000 这个
    既非 schema 默认(5000)、也非本文件其它用例所用(1)的值 —— 把
    ``statistical_basis_subframes=config.stat_count`` 改成任何常量都会红。

    这一跳此前零覆盖：内审实测把它换成字面量 5000 后 176 个相关用例全绿。
    """

    _seed_complete_legacy_path_loss_cal(db, chamber)
    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=False,
        frequency_hz=3500e6,
    )
    test_case = db.get(TestCase, ctx.test_execution.test_case_id)
    legacy_configuration = dict(test_case.configuration)
    legacy_configuration.pop("mac_profile", None)
    test_case.configuration = {
        **legacy_configuration,
        "engine_mode": "keysight_gcm",
        "switch_mode_id": "mimo_ota",
        "azimuths_deg": [0.0],
        "stat_count": 3000,
        "settling_time_s": 0.0,
        "num_samples_per_azimuth": 1,
        "precheck_strict_dut": False,
    }
    db.commit()
    _refreeze_ce_plan(db, ctx)
    _bind_unbound_mock_measurement(
        monkeypatch,
        ctx,
        hal_with_full_mock_chain.drivers["baseStation"],
    )

    captured: dict = {}
    original = MeasureExecutor._measure_base_station_samples

    async def _spy(base_station, **kwargs):
        captured.update(kwargs)
        return await original(base_station, **kwargs)

    monkeypatch.setattr(
        MeasureExecutor,
        "_measure_base_station_samples",
        staticmethod(_spy),
    )

    result = await _execute_direct_measure_in_receipt_scope(ctx)

    assert result.status == StepExecutionStatus.SUCCESS, result.error_message
    assert captured, "measure 从未走到 BaseStation 窗口采样"
    assert captured["statistical_basis_subframes"] == 3000


@pytest.mark.asyncio
async def test_diagnostic_measure_rejects_legacy_unverified_certificate(
    db,
    lab,
    chamber,
    hal_with_full_mock_chain,
    monkeypatch,
):
    certificate = _seed_complete_legacy_path_loss_cal(db, chamber)
    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=True,
        frequency_hz=3500e6,
    )
    test_case = db.get(TestCase, ctx.test_execution.test_case_id)
    configuration = {
        **test_case.configuration,
        "engine_mode": "keysight_gcm",
        "switch_mode_id": "mimo_ota",
        "azimuths_deg": [0.0],
        "stat_count": 1,
        "settling_time_s": 0.0,
        "num_samples_per_azimuth": 1,
        "precheck_strict_dut": False,
    }
    configuration.pop("mac_profile")
    test_case.configuration = canonicalize_mimo_ota_configuration_payload(
        configuration
    )
    db.commit()
    _refreeze_ce_plan(db, ctx)
    _bind_unbound_mock_measurement(
        monkeypatch,
        ctx,
        hal_with_full_mock_chain.drivers["baseStation"],
    )

    result = await _execute_direct_measure_in_receipt_scope(ctx)

    assert result.status == StepExecutionStatus.SUCCESS, result.error_message
    measurements = result.measurements or {}
    application = measurements["path_loss_application"]
    assert application["status"] == "not_applied"
    assert application["provenance"] == "unknown"
    assert application["reason"] == "rejected_untrusted"
    assert application["certificate_id"] == str(certificate.id)
    assert measurements["path_loss_verified"] is False
    assert measurements["measurement_verified"] is False
    warning_text = "\n".join(result.warnings or [])
    assert "补偿数值不展示" in warning_text
    assert "无 path-loss certificate" not in warning_text
    assert "56.77" not in warning_text


@pytest.mark.asyncio
async def test_mock_channelEmulator_auto_skips_strict_cal_gate(
    db, lab, chamber, hal_with_mock_ce,
):
    """precheck_strict_cal=True + NO path-loss cal, but channelEmulator is a
    mock driver → simulated measurement → cal gate N/A, cal_pass True. Local
    rehearsal isn't blocked by a missing calibration."""
    # Deliberately seed NO path-loss cal.
    ctx = _build_context(db, lab, cal_cert=None, strict_mode=True,
                             frequency_hz=3500e6)
    result = await PrecheckExecutor().execute(ctx)
    measurements = result.measurements or {}

    assert measurements.get("cal_pass") is True, (
        f"mock CE should auto-skip the cal gate; cal_pass="
        f"{measurements.get('cal_pass')}, reason={measurements.get('cal_pass_reason')!r}"
    )
    reason = measurements.get("cal_pass_reason", "") or ""
    assert "gate N/A" in reason and "mock" in reason, f"got {reason!r}"


@pytest.mark.asyncio
async def test_mock_channelEmulator_rehearsal_keeps_mock_calibration_chain(
    db, lab, chamber, hal_with_mock_ce,
):
    """模拟仪表链应演练校准选择，而不是悄悄退回默认线损。"""
    _seed_path_loss_cal(db, chamber.id, use_mock=True)
    ctx = _build_context(
        db,
        lab,
        cal_cert=None,
        strict_mode=True,
        frequency_hz=3500e6,
    )

    result = await PrecheckExecutor().execute(ctx)
    measurements = result.measurements or {}

    assert measurements["path_loss_calibration_valid"] is True
    assert measurements["path_loss_calibration_use_mock"] is True
    assert measurements["path_loss_calibration_frequency_mhz"] == 3500.0
    assert measurements["cal_pass"] is True
    assert "gate N/A" in measurements["cal_pass_reason"]
