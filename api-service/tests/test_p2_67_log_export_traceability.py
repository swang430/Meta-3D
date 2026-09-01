"""P2-67：BaseStation 公共租约日志与执行导出的独立可追溯性。"""

from __future__ import annotations

import logging

import pytest

from app.core.logging_config import current_execution_id
from app.hal.base_station import (
    BaseStationControlReleaseResult,
    BaseStationRemoteSessionResult,
)


class _BaseStation:
    adapter_id = "cmw500"

    async def acquire_remote_control(self) -> BaseStationRemoteSessionResult:
        return BaseStationRemoteSessionResult(
            adapter_id=self.adapter_id,
            session_token="cmw-session",
            acquired_confirmed=True,
            warnings=(),
        )

    async def release_remote_session(
        self,
        expected_session_token: str,
        *,
        measurement_attempt_id: str | None = None,
        lease_id: str = "",
    ) -> BaseStationControlReleaseResult:
        return BaseStationControlReleaseResult(
            measurement_attempt_id=measurement_attempt_id,
            lease_id=lease_id,
            adapter_id=self.adapter_id,
            session_token=expected_session_token,
            remote_session_acquired_confirmed=True,
            transport_session_released_confirmed=True,
            front_panel_local_confirmed=None,
            warnings=(),
        )

    async def release_to_local_control(self) -> bool:
        return True


class _HAL:
    def __init__(self):
        self.drivers = {"baseStation": _BaseStation()}

    async def clear_metrics_cache(self) -> None:
        return None


def test_frozen_validator_projects_minimal_lease_audit_context():
    from app.services.base_station_adapter_profile import (
        build_frozen_base_station_validator,
    )
    from app.services.instrument_test_lease import BaseStationLeaseAuditContext

    validator = build_frozen_base_station_validator(
        {
            "digest": "freeze-digest",
            "binding_digest": "binding-digest",
            "resolution": {
                "adapter": "cmw500",
                "status": "configured",
                "execution_mode": "real",
                "profile": {},
            },
        }
    )

    assert validator.validation_identity == "freeze-digest"
    assert validator.lease_audit_context == BaseStationLeaseAuditContext(
        adapter_id="cmw500",
        binding_digest="binding-digest",
    )


@pytest.mark.asyncio
async def test_public_lease_logs_are_vendor_neutral_and_structurally_identified(
    caplog,
):
    from app.services.instrument_test_lease import (
        BaseStationLeaseAuditContext,
        InstrumentTestLease,
    )

    class _Validator:
        validation_identity = "freeze-digest"
        lease_audit_context = BaseStationLeaseAuditContext(
            adapter_id="cmw500",
            binding_digest="binding-digest",
        )

        def __call__(self, _hal):
            return None

    lease = InstrumentTestLease(_HAL)
    token = current_execution_id.set(
        "31d3e29d-3b0f-4e5c-b391-0b629824e72d"
    )
    try:
        with caplog.at_level(
            logging.INFO,
            logger="app.services.instrument_test_lease",
        ):
            async with lease.hold(
                "formal-case",
                control_f64=False,
                control_uxm=True,
                validate_before_remote=_Validator(),
            ):
                pass
    finally:
        current_execution_id.reset(token)

    public = [
        record
        for record in caplog.records
        if "instrument-lease" in record.getMessage()
    ]
    assert len(public) == 2
    assert all("F64/UXM" not in record.getMessage() for record in public)
    assert all("UXM" not in record.getMessage() for record in public)
    assert [record.lease_event for record in public] == [
        "control_acquired",
        "control_released",
    ]
    assert all(
        record.controlled_instruments == ("baseStation",)
        for record in public
    )
    assert all(record.base_station_adapter_id == "cmw500" for record in public)
    assert all(
        record.base_station_binding_digest == "binding-digest"
        for record in public
    )
    assert all(
        record.execution_id == "31d3e29d-3b0f-4e5c-b391-0b629824e72d"
        for record in public
    )


@pytest.mark.asyncio
async def test_idle_park_log_does_not_claim_specific_vendor(caplog):
    from app.services.instrument_test_lease import InstrumentTestLease

    lease = InstrumentTestLease(_HAL)
    with caplog.at_level(
        logging.INFO,
        logger="app.services.instrument_test_lease",
    ):
        assert await lease.park_idle_instruments() is True

    message = caplog.records[-1].getMessage()
    assert "F64/UXM" not in message
    assert "UXM" not in message
    assert caplog.records[-1].lease_event == "idle_parked"
