from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.hal.base_station import (
    BaseStationApplyReceipt,
    BaseStationCleanupResult,
    BaseStationFieldReceipt,
    BaseStationMeasurementWindow,
    ThroughputMetrics,
)
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    InstrumentEvidenceItem,
)
from app.models.test_plan import TestExecution
from app.services import execution_scpi_evidence as evidence_writer
from app.services.execution_scpi_evidence import (
    append_base_station_measurement_window,
    confirm_base_station_configuration_and_route,
)
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from tests.p1_73c_evidence_fixtures import POSITION, valid_cmw_evidence


class _Query:
    def __init__(self, execution):
        self.execution = execution
        self.locked = False

    def filter(self, *_args):
        return self

    def with_for_update(self):
        self.locked = True
        return self

    def one_or_none(self):
        return self.execution


class _Db:
    def __init__(self, execution):
        self.query_object = _Query(execution)
        self.flushes = 0

    def query(self, _model):
        return self.query_object

    def flush(self):
        self.flushes += 1


def _execution():
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    evidence = valid_cmw_evidence()
    evidence["execution_id"] = str(execution.id)
    evidence["config_confirmed"] = False
    evidence["route_confirmed"] = False
    evidence["applied_route"] = None
    evidence["current_measurement_attempt_id"] = "attempt-new"
    evidence["current_measurement_attempt_state"] = "running"
    evidence["measurement_windows"] = []
    evidence["control_releases"] = []
    evidence["exchange_ids"] = []
    execution.config = {"base_station_execution_evidence": evidence}
    return execution


def _route_result(*, confirmed=True):
    route = valid_cmw_evidence()["requested_route"]["payload"]
    return BaseStationApplyReceipt(
        schema_version=1,
        operation="route",
        fields=tuple(
            BaseStationFieldReceipt(
                field=name,
                requested=value,
                applied=value if confirmed else None,
                status="confirmed" if confirmed else "unknown",
                reason="confirmed" if confirmed else "rejected",
                exchange_ids=("route-1", "route-2"),
            )
            for name, value in route.items()
        ),
        reason="confirmed" if confirmed else "rejected",
        simulated=False,
    )


def _config_receipt(*, confirmed=True):
    payload = valid_cmw_evidence()["requested_config"]["payload"]
    return BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=(
            BaseStationFieldReceipt(
                field="bandwidth_mhz",
                requested=payload["bandwidth_mhz"],
                applied=payload["bandwidth_mhz"] if confirmed else None,
                status="confirmed" if confirmed else "unknown",
                reason="confirmed" if confirmed else "rejected",
                exchange_ids=("config-1",),
            ),
        ),
        reason="confirmed" if confirmed else "rejected",
        simulated=False,
    )


def _window():
    evidence = InstrumentEvidenceItem(
        instrument="cmw500",
        evidence_key="cmw500.extended_bler.window",
        requested={"window_s": 1.0},
        command_sent="INITiate:LTE:SIGN1:EBLer",
        readback={},
        exchange_ids=["life-1", "metric-1"],
        evidence_level=EvidenceLevel.OUTCOME,
        source_reference="manual §window",
        verdict=EvidenceVerdict.PASSED,
        reason="confirmed",
    )
    return BaseStationMeasurementWindow(
        window_id="window-new",
        started_at=datetime(2026, 8, 26, 8, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 26, 8, 0, 1, tzinfo=timezone.utc),
        metrics=ThroughputMetrics(
            dl_throughput_mbps=96.5,
            dl_bler=0.4,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            kpi_valid={"dl_throughput": True, "dl_bler": True},
        ),
        preclear_off_confirmed=True,
        running_confirmed=True,
        ready_confirmed=True,
        closed_off_confirmed=True,
        evidence=(evidence,),
        confirmed=True,
        reason="confirmed",
    )


def test_config_route_and_window_writer_bind_current_attempt_lease_and_token(
    monkeypatch,
):
    execution = _execution()
    db = _Db(execution)
    lease_identity = ActiveBaseStationLeaseIdentity(
        lease_id="lease-new",
        measurement_attempt_id="attempt-new",
        adapter_id="cmw500",
        session_token="session-new",
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: lease_identity,
    )

    confirm_base_station_configuration_and_route(
        db,
        execution.id,
        attempt_id="attempt-new",
        lease_identity=lease_identity,
        config_receipt=_config_receipt(),
        route_receipt=_route_result(),
    )
    append_base_station_measurement_window(
        db,
        execution.id,
        attempt_id="attempt-new",
        lease_identity=ActiveBaseStationLeaseIdentity(
            lease_id="lease-new",
            measurement_attempt_id="attempt-new",
            adapter_id="cmw500",
            session_token="session-new",
        ),
        position=POSITION,
        ue_link_state="connected",
        window=_window(),
        cleanup=BaseStationCleanupResult(
            stop_signaling_confirmed=True,
            safe_idle_confirmed=True,
            warnings=(),
        ),
    )

    value = execution.config["base_station_execution_evidence"]
    assert value["config_confirmed"] is True
    assert value["route_confirmed"] is True
    assert value["applied_route"] == value["requested_route"]
    row = value["measurement_windows"][0]
    assert row["measurement_attempt_id"] == "attempt-new"
    assert row["lease_id"] == "lease-new"
    assert row["session_token"] == "session-new"
    assert row["metrics"]["dl_throughput_mbps"]["value"] == 96.5
    assert row["metrics"]["dl_bler_percent"]["value"] == 0.4
    assert set(value["exchange_ids"]) == {
        "config-1",
        "route-1",
        "route-2",
        "life-1",
        "metric-1",
    }


def test_rejected_route_or_wrong_attempt_never_confirms_or_appends(monkeypatch):
    execution = _execution()
    db = _Db(execution)
    lease_identity = ActiveBaseStationLeaseIdentity(
        lease_id="lease-new",
        measurement_attempt_id="attempt-new",
        adapter_id="cmw500",
        session_token="session-new",
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: lease_identity,
    )

    confirm_base_station_configuration_and_route(
        db,
        execution.id,
        attempt_id="attempt-new",
        lease_identity=lease_identity,
        config_receipt=_config_receipt(),
        route_receipt=_route_result(confirmed=False),
    )
    value = execution.config["base_station_execution_evidence"]
    assert value["config_confirmed"] is True
    assert value["route_confirmed"] is False
    assert value["applied_route"] is None

    with pytest.raises(ValueError, match="current running attempt"):
        append_base_station_measurement_window(
            db,
            execution.id,
            attempt_id="attempt-old",
            lease_identity=ActiveBaseStationLeaseIdentity(
                lease_id="lease-old",
                measurement_attempt_id="attempt-old",
                adapter_id="cmw500",
                session_token="session-old",
            ),
            position=POSITION,
            ue_link_state="connected",
            window=_window(),
            cleanup=BaseStationCleanupResult(False, False, ("failed",)),
        )
    assert value["measurement_windows"] == []


def test_duplicate_window_id_is_fail_loud_not_an_overwrite():
    execution = _execution()
    db = _Db(execution)
    kwargs = {
        "attempt_id": "attempt-new",
        "lease_identity": ActiveBaseStationLeaseIdentity(
            lease_id="lease-new",
            measurement_attempt_id="attempt-new",
            adapter_id="cmw500",
            session_token="session-new",
        ),
        "position": POSITION,
        "ue_link_state": "connected",
        "window": _window(),
        "cleanup": BaseStationCleanupResult(True, True, ()),
    }

    append_base_station_measurement_window(db, execution.id, **kwargs)
    with pytest.raises(ValueError, match="duplicate measurement window"):
        append_base_station_measurement_window(db, execution.id, **kwargs)
