"""P2-43：共同 adapter receipt 到 execution evidence 的唯一写入合同。"""

from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.hal.base_station import (
    BaseStationApplyReceipt,
    BaseStationFieldReceipt,
    MockBaseStation,
)
from app.models.test_plan import TestExecution
from app.services import execution_scpi_evidence as evidence_writer
from app.services.execution_scpi_evidence import (
    confirm_base_station_configuration_and_route,
)
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence


class _Query:
    def __init__(self, execution):
        self.execution = execution

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def one_or_none(self):
        return self.execution


class _Db:
    def __init__(self, execution):
        self.execution = execution

    def query(self, _model):
        return _Query(self.execution)

    def flush(self):
        return None


def _execution(*, adapter: str = "cmw500") -> TestExecution:
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    evidence = valid_cmw_evidence()
    evidence["execution_id"] = str(execution.id)
    evidence["config_confirmed"] = False
    evidence["route_confirmed"] = False
    evidence["applied_route"] = None
    evidence["current_measurement_attempt_id"] = "attempt-1"
    evidence["current_measurement_attempt_state"] = "running"
    evidence["measurement_windows"] = []
    evidence["control_releases"] = []
    evidence["exchange_ids"] = []
    if adapter == "uxm":
        evidence["adapter"] = "uxm"
        evidence["identity"] = {
            "adapter": "uxm",
            "model": "E7515B",
            "firmware_version": "1.0",
            "options": [],
            "instrument_connection_id": "connection-1",
            "adapter_profile_digest": None,
        }
        evidence["formal_capability_approval"] = {
            "schema_version": 1,
            "status": "not_applicable",
            "instrument_connection_id": None,
            "capability": None,
            "enabled": None,
            "updated_at": None,
        }
        evidence["route_confirmed"] = None
        evidence["requested_route"] = None
    execution.config = {"base_station_execution_evidence": evidence}
    return execution


def _field(
    name: str,
    requested,
    *,
    status: str = "confirmed",
    exchange_id: str = "config-1",
) -> BaseStationFieldReceipt:
    return BaseStationFieldReceipt(
        field=name,
        requested=requested,
        applied=requested if status == "confirmed" else None,
        status=status,
        reason=status,
        exchange_ids=(exchange_id,) if exchange_id else (),
    )


def _config_receipt(execution, *, partial: bool = False, simulated: bool = False):
    payload = execution.config["base_station_execution_evidence"][
        "requested_config"
    ]["payload"]
    fields = [
        _field(
            name,
            value,
            status=(
                "unknown"
                if partial and name == "mimo_layers"
                else "confirmed"
            ),
            exchange_id=("config-2" if name == "mimo_layers" else "config-1"),
        )
        for name, value in payload.items()
        if value is not None
    ]
    return BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=tuple(fields),
        reason="partial" if partial else "confirmed",
        simulated=simulated,
    )


def _route_receipt(execution, *, simulated: bool = False):
    evidence = execution.config["base_station_execution_evidence"]
    if evidence["adapter"] == "uxm":
        return BaseStationApplyReceipt(
            schema_version=1,
            operation="route",
            fields=(
                BaseStationFieldReceipt(
                    field="route",
                    requested=None,
                    applied=None,
                    status="not_applicable",
                    reason="not applicable",
                ),
            ),
            reason="not applicable",
            simulated=simulated,
        )
    route = evidence["requested_route"]["payload"]
    return BaseStationApplyReceipt(
        schema_version=1,
        operation="route",
        fields=tuple(
            _field(name, value, exchange_id="route-1")
            for name, value in route.items()
        ),
        reason="confirmed",
        simulated=simulated,
    )


def _lease(adapter: str = "cmw500") -> ActiveBaseStationLeaseIdentity:
    return ActiveBaseStationLeaseIdentity(
        lease_id="lease-1",
        measurement_attempt_id="attempt-1",
        adapter_id=adapter,
        session_token="session-1",
        instrument_id="uxm" if adapter == "uxm" else "cmw",
    )


@pytest.mark.asyncio
async def test_bound_cmw_mock_route_covers_frozen_request_but_stays_simulated(
    monkeypatch,
):
    execution = _execution(adapter="cmw500")
    route = execution.config["base_station_execution_evidence"][
        "requested_route"
    ]["payload"]
    frozen = {
        "resolution": {
            "profile": {"lte_2x2_internal_route": route},
        }
    }
    driver = registered_mock_base_station("mock-cmw", {"model": "CMW500"})

    receipt = await driver.apply_route(frozen)

    assert receipt.simulated is True
    assert receipt.confirmed is False
    assert {field.field: field.requested for field in receipt.fields} == route
    assert all(field.status == "unknown" for field in receipt.fields)
    assert driver.route_allows_diagnostic_execution(receipt) is True

    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("cmw500"),
    )
    confirm_base_station_configuration_and_route(
        _Db(execution),
        execution.id,
        attempt_id="attempt-1",
        lease_identity=_lease("cmw500"),
        config_receipt=_config_receipt(execution, simulated=True),
        route_receipt=receipt,
    )
    stored = execution.config["base_station_execution_evidence"]
    assert stored["route_confirmed"] is False
    assert stored["applied_route"] is None


@pytest.mark.parametrize("adapter", ["cmw500", "uxm"])
def test_writer_accepts_same_vendor_neutral_receipt_shape(adapter, monkeypatch):
    execution = _execution(adapter=adapter)
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(adapter),
    )

    confirm_base_station_configuration_and_route(
        _Db(execution),
        execution.id,
        attempt_id="attempt-1",
        lease_identity=_lease(adapter),
        config_receipt=_config_receipt(execution),
        route_receipt=_route_receipt(execution),
    )

    evidence = execution.config["base_station_execution_evidence"]
    assert evidence["config_confirmed"] is True
    assert evidence["route_confirmed"] is (True if adapter == "cmw500" else None)
    assert [row["operation"] for row in evidence["adapter_operations"]] == [
        "config",
        "route",
    ]
    assert all(row["adapter"] == adapter for row in evidence["adapter_operations"])
    assert all(row["lease_id"] == "lease-1" for row in evidence["adapter_operations"])
    route_operation = evidence["adapter_operations"][1]
    if adapter == "uxm":
        assert route_operation["frozen_request_digest"] is None
    else:
        assert isinstance(route_operation["frozen_request_digest"], str)


def test_writer_rejects_free_confirmation_boolean_and_wrong_frozen_request(
    monkeypatch,
):
    execution = _execution()
    db = _Db(execution)
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(),
    )

    with pytest.raises(TypeError):
        confirm_base_station_configuration_and_route(
            db,
            execution.id,
            attempt_id="attempt-1",
            config_confirmed=True,
            config_exchange_ids=["config-1"],
        )

    receipt = _config_receipt(execution)
    bad_fields = list(receipt.fields)
    bad_fields[0] = _field(bad_fields[0].field, "wrong frozen value")
    bad = BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=tuple(bad_fields),
        reason="wrong request",
        simulated=False,
    )
    with pytest.raises(ValueError, match="frozen request"):
        confirm_base_station_configuration_and_route(
            db,
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease(),
            config_receipt=bad,
            route_receipt=_route_receipt(execution),
        )


def test_writer_rejects_config_receipt_that_omits_frozen_non_null_fields(
    monkeypatch,
):
    execution = _execution()
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(),
    )

    complete = _config_receipt(execution)
    incomplete = BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=complete.fields[:-1],
        reason="missing frozen field",
        simulated=False,
    )

    with pytest.raises(ValueError, match="does not cover frozen request"):
        confirm_base_station_configuration_and_route(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease(),
            config_receipt=incomplete,
            route_receipt=_route_receipt(execution),
        )


def test_partial_or_simulated_receipt_is_audited_but_never_confirmed(monkeypatch):
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(),
    )
    for config_receipt, route_receipt in (
        (None, None),
        ("partial", None),
        ("simulated", None),
        (None, "simulated"),
    ):
        execution = _execution()
        config = _config_receipt(
            execution,
            partial=config_receipt == "partial",
            simulated=config_receipt == "simulated",
        )
        route = _route_receipt(
            execution,
            simulated=route_receipt == "simulated",
        )
        confirm_base_station_configuration_and_route(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease(),
            config_receipt=config,
            route_receipt=route,
        )
        evidence = execution.config["base_station_execution_evidence"]
        if config_receipt == "partial":
            assert evidence["config_confirmed"] is False
        if config_receipt == "simulated":
            assert evidence["config_confirmed"] is False
        if route_receipt == "simulated":
            assert evidence["route_confirmed"] is False
        assert len(evidence["adapter_operations"]) == 2


@pytest.mark.parametrize(
    "lease",
    [
        ActiveBaseStationLeaseIdentity("wrong", "attempt-1", "cmw500", "session-1"),
        ActiveBaseStationLeaseIdentity("lease-1", "wrong", "cmw500", "session-1"),
        ActiveBaseStationLeaseIdentity("lease-1", "attempt-1", "uxm", "session-1"),
        ActiveBaseStationLeaseIdentity("lease-1", "attempt-1", "cmw500", "wrong"),
    ],
)
def test_writer_rejects_attempt_lease_adapter_or_session_mismatch(
    lease, monkeypatch,
):
    execution = _execution()
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(),
    )

    with pytest.raises(ValueError, match="lease identity"):
        confirm_base_station_configuration_and_route(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=lease,
            config_receipt=_config_receipt(execution),
            route_receipt=_route_receipt(execution),
        )

    evidence = deepcopy(execution.config["base_station_execution_evidence"])
    assert evidence.get("adapter_operations", []) == []


def test_writer_rejects_confirmed_receipt_without_exchange_evidence(monkeypatch):
    execution = _execution()
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(),
    )
    payload = execution.config["base_station_execution_evidence"][
        "requested_config"
    ]["payload"]
    no_evidence = BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=tuple(
            _field(name, value, exchange_id="")
            for name, value in payload.items()
            if value is not None
        ),
        reason="unproven",
        simulated=False,
    )

    with pytest.raises(ValueError, match="requires exchange ids"):
        confirm_base_station_configuration_and_route(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease(),
            config_receipt=no_evidence,
            route_receipt=_route_receipt(execution),
        )


def test_writer_rejects_duplicate_operation_for_same_attempt_and_lease(monkeypatch):
    execution = _execution()
    db = _Db(execution)
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(),
    )
    kwargs = {
        "attempt_id": "attempt-1",
        "lease_identity": _lease(),
        "config_receipt": _config_receipt(execution),
        "route_receipt": _route_receipt(execution),
    }
    confirm_base_station_configuration_and_route(
        db,
        execution.id,
        **kwargs,
    )

    with pytest.raises(ValueError, match="already persisted"):
        confirm_base_station_configuration_and_route(
            db,
            execution.id,
            **kwargs,
        )

    assert len(
        execution.config["base_station_execution_evidence"]["adapter_operations"]
    ) == 2


def test_shared_writer_does_not_import_a_vendor_route_result():
    source = Path(evidence_writer.__file__).read_text(encoding="utf-8")

    assert "app.hal.cmw500_base_station" not in source
    assert "BaseStationRouteResult" not in source
