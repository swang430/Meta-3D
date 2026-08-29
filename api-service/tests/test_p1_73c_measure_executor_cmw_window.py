from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.hal.base_station import (
    BASE_STATION_MEASUREMENT_WINDOW_STAGES,
    BaseStationApplyReceipt,
    BaseStationFieldReceipt,
    BaseStationMeasurementStageReceipt,
    BaseStationMeasurementWindow,
    BaseStationMeasurementWindowRequest,
    BaseStationMeasurementWindowTrust,
    MockBaseStation,
    ThroughputMetrics,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.models.test_plan import TestExecution
from app.services.execution_scpi_evidence import (
    begin_base_station_measurement_attempt,
    initialize_base_station_execution_evidence,
)
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota.executors.measure import MeasureExecutor
from tests.test_p1_73c_base_station_evidence_writer import (
    _CmwDriver,
    _frozen,
    _request,
)


def _window_trust(
    request: BaseStationMeasurementWindowRequest,
    *,
    confirmed: bool,
    simulated: bool = False,
) -> BaseStationMeasurementWindowTrust:
    exchange_ids = () if simulated or not confirmed else ("window-proof",)
    if request.lifecycle in {"clear_read_only", "unavailable"} and not simulated:
        exchange_ids = ("diagnostic-observation",)
    return BaseStationMeasurementWindowTrust(
        schema_version=1,
        request=request,
        request_digest=request.digest,
        stages=tuple(
            BaseStationMeasurementStageReceipt(
                stage=stage,
                status="confirmed" if confirmed else (
                    "unavailable" if request.lifecycle == "unavailable" else "unknown"
                ),
                reason="test window truth",
                exchange_ids=exchange_ids if confirmed else (),
            )
            for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
        ),
        simulated=simulated,
        exchange_ids=exchange_ids,
        reason="test window truth",
    )


@dataclass
class _Cmw:
    adapter_id: str = "cmw500"
    native_calls: int = 0
    legacy_calls: int = 0

    def measurement_window_count(self, _requested: int) -> int:
        return 1

    async def measure_base_station_window(self, window_s, *, request):
        self.native_calls += 1
        started = datetime.now(timezone.utc)
        trust = _window_trust(request, confirmed=True)
        return BaseStationMeasurementWindow(
            window_id="cmw-window",
            started_at=started,
            completed_at=started + timedelta(seconds=1),
            metrics=ThroughputMetrics(
                dl_throughput_mbps=98.0,
                dl_bler=0.2,
                throughput_scope=ThroughputMetrics.SCOPE_PCELL,
                kpi_valid={"dl_throughput": True, "dl_bler": True},
            ),
            preclear_off_confirmed=True,
            running_confirmed=True,
            ready_confirmed=True,
            closed_off_confirmed=True,
            evidence=(),
            confirmed=True,
            reason="confirmed",
            trust=trust,
        )

    async def measure_throughput_window(self, *_args, **_kwargs):
        self.legacy_calls += 1
        raise AssertionError("CMW500 must not use the legacy polling window")


@dataclass
class _Uxm:
    adapter_id: str = "uxm"
    native_calls: int = 0

    async def measure_base_station_window(self, _window_s, *, request):
        self.native_calls += 1
        started = datetime.now(timezone.utc)
        trust = _window_trust(request, confirmed=False)
        return BaseStationMeasurementWindow(
            window_id=f"uxm-window-{self.native_calls}",
            started_at=started,
            completed_at=started + timedelta(seconds=1),
            metrics=ThroughputMetrics(
                dl_throughput_mbps=float(self.native_calls),
                throughput_scope=(
                    ThroughputMetrics.SCOPE_PCELL
                    if request.scope == "pcell"
                    else ThroughputMetrics.SCOPE_NR_ALL_CELLS
                ),
                kpi_valid={"dl_throughput": True},
            ),
            preclear_off_confirmed=False,
            running_confirmed=False,
            ready_confirmed=False,
            closed_off_confirmed=False,
            evidence=(),
            confirmed=False,
            reason="diagnostic observation without sourced lifecycle",
            trust=trust,
        )


def test_cmw_diagnostic_route_requires_all_six_authoritative_physical_fields():
    requested = {
        "pcc_bb_board": "BB1",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    def receipt(*, bad_field: str | None = None, all_unknown: bool = False):
        return BaseStationApplyReceipt(
            schema_version=1,
            operation="route",
            fields=tuple(
                BaseStationFieldReceipt(
                    field=name,
                    requested=value,
                    applied=(
                        None
                        if all_unknown or name == "pcc_bb_board" or name == bad_field
                        else value
                    ),
                    status=(
                        "unknown"
                        if all_unknown or name == "pcc_bb_board" or name == bad_field
                        else "confirmed"
                    ),
                    reason="test route truth",
                )
                for name, value in requested.items()
            ),
            reason="test route truth",
            simulated=False,
        )

    driver = object.__new__(RealCmw500Driver)
    assert driver.route_allows_diagnostic_execution(receipt()) is True
    assert driver.route_allows_diagnostic_execution(
        receipt(bad_field="tx2_connector")
    ) is False
    assert driver.route_allows_diagnostic_execution(receipt(all_unknown=True)) is False


@pytest.mark.asyncio
async def test_cmw_measure_scan_uses_one_driver_native_extended_bler_window():
    driver = _Cmw()

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=1.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=3,
        manifest=RealCmw500Driver.adapter_manifest,
        simulated_diagnostic=False,
    )

    assert driver.native_calls == 1
    assert driver.legacy_calls == 0
    assert len(samples) == 1
    assert samples[0].window is not None
    assert samples[0].metrics.dl_throughput_mbps == 98.0
    assert samples[0].metrics.dl_bler == 0.2


@pytest.mark.asyncio
async def test_uxm_measure_scan_preserves_requested_common_window_count():
    driver = _Uxm()

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=1.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=3,
        manifest=RealUxmDriver.adapter_manifest,
        simulated_diagnostic=False,
    )

    assert driver.native_calls == 3
    assert [item.metrics.dl_throughput_mbps for item in samples] == [1.0, 2.0, 3.0]
    assert all(item.window is not None for item in samples)


@pytest.mark.asyncio
async def test_rejected_cmw_lifecycle_stops_before_any_legacy_or_extra_window():
    driver = _Cmw()
    original = driver.measure_base_station_window

    async def rejected(*args, **kwargs):
        window = await original(*args, **kwargs)
        trust = _window_trust(kwargs["request"], confirmed=False)
        return BaseStationMeasurementWindow(
            **{
                **window.__dict__,
                "preclear_off_confirmed": False,
                "running_confirmed": False,
                "ready_confirmed": False,
                "closed_off_confirmed": False,
                "confirmed": False,
                "reason": "final OFF unconfirmed",
                "trust": trust,
            }
        )

    driver.measure_base_station_window = rejected

    with pytest.raises(RuntimeError, match="final OFF unconfirmed"):
        await MeasureExecutor._measure_base_station_samples(
            driver,
            window_s=1.0,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            requested_sample_count=3,
            manifest=RealCmw500Driver.adapter_manifest,
            simulated_diagnostic=False,
        )

    assert driver.native_calls == 1
    assert driver.legacy_calls == 0


class _Db:
    def __init__(self, execution):
        self.execution = execution

    class _Query:
        def __init__(self, execution):
            self.execution = execution

        def filter(self, *_args):
            return self

        def with_for_update(self):
            return self

        def one_or_none(self):
            return self.execution

    def query(self, _model):
        return self._Query(self.execution)

    def flush(self):
        return None


class _FormalCmw(_CmwDriver):
    def evaluate_lte_2x2_formal_capability(self, *_args, **_kwargs):
        return SimpleNamespace(ready=True, reason="ready")


class _DiagnosticCmw(_CmwDriver):
    def __init__(self, status: str):
        self.status = status

    def evaluate_lte_2x2_formal_capability(self, *_args, **_kwargs):
        return SimpleNamespace(
            ready=False,
            status=self.status,
            reason=f"{self.status} diagnostic",
        )


def _simulated_frozen() -> dict:
    frozen = _frozen(enabled=False)
    frozen["resolution"]["execution_mode"] = "simulated"
    payload = {key: value for key, value in frozen.items() if key != "digest"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**payload, "digest": hashlib.sha256(encoded).hexdigest()}


def test_cmw_formal_attempt_requires_the_server_current_attempt_and_active_lease(
    monkeypatch,
):
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    frozen = _frozen()
    execution.config = {"base_station_adapter_profile_freeze": frozen}
    initialize_base_station_execution_evidence(
        execution,
        frozen_adapter=frozen,
        requested_config=_request(),
        requested_positions=[{"azimuth_deg": 0.0, "elevation_deg": 0.0}],
        driver=_CmwDriver(),
    )
    db = _Db(execution)
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-current",
        measurement_attempt_id=attempt_id,
        adapter_id="cmw500",
        session_token="session-current",
    )
    monkeypatch.setattr(
        "app.services.instrument_test_lease.active_base_station_lease_identity",
        lambda: lease,
    )
    context = SimpleNamespace(test_execution=execution, db=db)

    resolved = MeasureExecutor._base_station_attempt_context(
        context,
        _FormalCmw(),
    )

    assert resolved.attempt_id == attempt_id
    assert resolved.lease_identity == lease
    assert resolved.frozen_adapter == frozen


def test_cmw_formal_attempt_rejects_a_lease_from_an_old_attempt(monkeypatch):
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    frozen = _frozen()
    execution.config = {"base_station_adapter_profile_freeze": frozen}
    initialize_base_station_execution_evidence(
        execution,
        frozen_adapter=frozen,
        requested_config=_request(),
        requested_positions=[{"azimuth_deg": 0.0, "elevation_deg": 0.0}],
        driver=_CmwDriver(),
    )
    db = _Db(execution)
    begin_base_station_measurement_attempt(db, execution.id)
    monkeypatch.setattr(
        "app.services.instrument_test_lease.active_base_station_lease_identity",
        lambda: ActiveBaseStationLeaseIdentity(
            lease_id="lease-old",
            measurement_attempt_id="attempt-old",
            adapter_id="cmw500",
            session_token="session-old",
        ),
    )

    with pytest.raises(RuntimeError, match="not bound to the current attempt"):
        MeasureExecutor._base_station_attempt_context(
            SimpleNamespace(test_execution=execution, db=db),
            _FormalCmw(),
        )


@pytest.mark.parametrize(
    ("status", "config_mode"),
    [("disabled", "dispatch"), ("diagnostic", "inherit")],
)
def test_cmw_disabled_or_inherit_keeps_the_measurement_attempt_diagnostic(
    monkeypatch,
    status,
    config_mode,
):
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    frozen = _frozen(enabled=status != "disabled")
    execution.config = {"base_station_adapter_profile_freeze": frozen}
    driver = _DiagnosticCmw(status)
    initialize_base_station_execution_evidence(
        execution,
        frozen_adapter=frozen,
        requested_config=_request(),
        requested_positions=[{"azimuth_deg": 0.0, "elevation_deg": 0.0}],
        driver=driver,
    )
    db = _Db(execution)
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-diagnostic",
        measurement_attempt_id=attempt_id,
        adapter_id="cmw500",
        session_token="session-diagnostic",
    )
    monkeypatch.setattr(
        "app.services.instrument_test_lease.active_base_station_lease_identity",
        lambda: lease,
    )

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=db),
        driver,
    )

    assert resolved.attempt_id == attempt_id
    assert resolved.simulated_diagnostic is False


def test_explicit_cmw_mock_can_enter_a_simulated_diagnostic_attempt(monkeypatch):
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    frozen = _simulated_frozen()
    execution.config = {"base_station_adapter_profile_freeze": frozen}
    driver = MockBaseStation("mock-cmw", {"model": "CMW500"})
    initialize_base_station_execution_evidence(
        execution,
        frozen_adapter=frozen,
        requested_config=_request(),
        requested_positions=[{"azimuth_deg": 0.0, "elevation_deg": 0.0}],
        driver=driver,
    )
    db = _Db(execution)
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-mock",
        measurement_attempt_id=attempt_id,
        adapter_id="cmw500",
        session_token="session-mock",
    )
    monkeypatch.setattr(
        "app.services.instrument_test_lease.active_base_station_lease_identity",
        lambda: lease,
    )

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=db),
        driver,
    )

    assert resolved.attempt_id == attempt_id
    assert resolved.simulated_diagnostic is True


@pytest.mark.asyncio
async def test_explicit_cmw_mock_uses_the_existing_simulated_diagnostic_window():
    driver = MockBaseStation("mock-cmw", {"model": "CMW500"})
    await driver.start_signaling()

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=2,
        manifest=None,
        simulated_diagnostic=True,
    )

    assert len(samples) == 2
    assert all(sample.window is not None for sample in samples)
    assert all(sample.metrics.throughput_scope == "simulated" for sample in samples)
