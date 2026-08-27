from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.hal.base_station import (
    BaseStationControlReleaseResult,
    BaseStationRemoteSessionResult,
    MockBaseStation,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.services.instrument_test_lease import (
    ActiveBaseStationLeaseIdentity,
    InstrumentTestLease,
    InstrumentTestLeaseError,
)


class _F64:
    async def acquire_remote_control(self):
        return True

    async def release_to_local_control(self):
        return True


class _BaseStation:
    adapter_id = "cmw500"

    def __init__(self, *, release_confirmed=True):
        self.release_confirmed = release_confirmed
        self.calls: list[tuple] = []

    async def acquire_remote_control(self):
        self.calls.append(("acquire",))
        return BaseStationRemoteSessionResult(
            adapter_id="cmw500",
            session_token="session-1",
            acquired_confirmed=True,
            warnings=("front-panel Remote unknown",),
        )

    async def release_remote_session(
        self, expected_session_token, *, measurement_attempt_id=None, lease_id=""
    ):
        self.calls.append(
            ("release", expected_session_token, measurement_attempt_id, lease_id)
        )
        return BaseStationControlReleaseResult(
            measurement_attempt_id=measurement_attempt_id,
            lease_id=lease_id,
            adapter_id="cmw500",
            session_token=expected_session_token,
            remote_session_acquired_confirmed=True,
            transport_session_released_confirmed=self.release_confirmed,
            front_panel_local_confirmed=None,
            warnings=("front-panel Local unknown",),
        )


def _hal(base_station):
    async def clear_metrics_cache():
        return None

    return SimpleNamespace(
        drivers={"channelEmulator": _F64(), "baseStation": base_station},
        clear_metrics_cache=clear_metrics_cache,
    )


@pytest.mark.asyncio
async def test_lease_outcome_binds_attempt_lease_and_driver_session_token():
    driver = _BaseStation()
    lease = InstrumentTestLease(lambda: _hal(driver))

    async with lease.hold(
        "measure", measurement_attempt_id="attempt-1"
    ) as outcome:
        assert lease.active_base_station_identity() == ActiveBaseStationLeaseIdentity(
            lease_id=outcome.lease_id,
            measurement_attempt_id="attempt-1",
            adapter_id="cmw500",
            session_token="session-1",
        )
        assert outcome.measurement_attempt_id == "attempt-1"
        assert outcome.base_station_release is None
        lease_id = outcome.lease_id

    assert outcome.base_station_release == BaseStationControlReleaseResult(
        measurement_attempt_id="attempt-1",
        lease_id=lease_id,
        adapter_id="cmw500",
        session_token="session-1",
        remote_session_acquired_confirmed=True,
        transport_session_released_confirmed=True,
        front_panel_local_confirmed=None,
        warnings=("front-panel Local unknown",),
    )
    assert driver.calls == [
        ("acquire",),
        ("release", "session-1", "attempt-1", lease_id),
    ]
    assert lease.active_base_station_identity() is None


@pytest.mark.asyncio
async def test_unconfirmed_transport_release_is_exposed_before_fail_loud():
    driver = _BaseStation(release_confirmed=False)
    lease = InstrumentTestLease(lambda: _hal(driver))
    outcome = None

    with pytest.raises(InstrumentTestLeaseError, match="transport"):
        async with lease.hold(
            "measure", measurement_attempt_id="attempt-1"
        ) as outcome:
            pass

    assert outcome is not None
    assert outcome.base_station_release is not None
    assert outcome.base_station_release.transport_session_released_confirmed is False


@pytest.mark.asyncio
async def test_present_base_station_without_common_release_contract_fails_loud():
    class MissingRelease:
        async def acquire_remote_control(self):
            return True

    lease = InstrumentTestLease(lambda: _hal(MissingRelease()))

    with pytest.raises(InstrumentTestLeaseError, match="baseStation.*contract"):
        async with lease.hold("measure", measurement_attempt_id="attempt-1"):
            pytest.fail("missing release contract must block instrument I/O")


@pytest.mark.asyncio
async def test_authoritative_mock_uses_the_same_control_contract_but_stays_simulated():
    driver = MockBaseStation("mock", {"model": "CMW500"})

    acquired = await driver.acquire_remote_control()
    released = await driver.release_remote_session(
        acquired.session_token,
        measurement_attempt_id="attempt-1",
        lease_id="lease-1",
    )

    assert driver.simulated is True
    assert acquired.adapter_id == "cmw500"
    assert acquired.acquired_confirmed is True
    assert released == BaseStationControlReleaseResult(
        measurement_attempt_id="attempt-1",
        lease_id="lease-1",
        adapter_id="cmw500",
        session_token=acquired.session_token,
        remote_session_acquired_confirmed=True,
        transport_session_released_confirmed=True,
        front_panel_local_confirmed=None,
        warnings=("simulated transport; front-panel Local not applicable",),
    )


@pytest.mark.asyncio
async def test_cmw_release_keeps_transport_open_when_safe_idle_is_unconfirmed():
    class _Session:
        closed = False

        def close(self):
            self.closed = True

    class _UnsafeCmw(RealCmw500Driver):
        async def ensure_safe_idle(self) -> bool:
            return False

    driver = _UnsafeCmw("cmw", {"ip_address": "192.0.2.10"})
    session = _Session()
    driver._visa_session = session
    driver._session_token = "session-1"

    released = await driver.release_remote_session(
        "session-1",
        measurement_attempt_id="attempt-1",
        lease_id="lease-1",
    )

    assert released.transport_session_released_confirmed is False
    assert driver._visa_session is session
    assert driver._session_token == "session-1"
    assert session.closed is False
    assert any("SAFE_IDLE" in warning for warning in released.warnings)


@pytest.mark.asyncio
async def test_idle_park_uses_the_real_cmw_safe_idle_release_path():
    class _Session:
        closed = False

        def close(self):
            self.closed = True

    class _SafeCmw(RealCmw500Driver):
        async def ensure_safe_idle(self) -> bool:
            return True

    driver = _SafeCmw("cmw", {"ip_address": "192.0.2.10"})
    session = _Session()
    driver._visa_session = session
    driver._session_token = "session-idle"
    lease = InstrumentTestLease(lambda: _hal(driver))

    assert await lease.park_idle_instruments() is True
    assert session.closed is True
    assert driver._visa_session is None
    assert driver._session_token is None


@pytest.mark.asyncio
async def test_idle_park_accepts_a_real_cmw_with_no_transport_to_release():
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    lease = InstrumentTestLease(lambda: _hal(driver))

    assert await lease.park_idle_instruments() is True


@pytest.mark.asyncio
async def test_hal_shutdown_retains_a_cmw_that_cannot_confirm_safe_idle():
    from app.services.instrument_hal_service import DriverMode, InstrumentHALService

    class _UnsafeCmw:
        adapter_id = "cmw500"

        async def disconnect(self):
            return False

    driver = _UnsafeCmw()
    service = InstrumentHALService(mode=DriverMode.REAL)
    service.drivers = {"baseStation": driver}
    service._initialized = True

    with pytest.raises(RuntimeError, match="baseStation.*安全断开"):
        await service.shutdown()

    assert service.drivers == {"baseStation": driver}
    assert service._initialized is True


@pytest.mark.asyncio
async def test_hal_reconnect_refuses_to_reopen_after_unsafe_cmw_disconnect():
    from app.services.instrument_hal_service import DriverMode, InstrumentHALService

    class _UnsafeCmw:
        adapter_id = "cmw500"

        def __init__(self):
            self.connect_calls = 0

        async def disconnect(self):
            return False

        async def connect(self):
            self.connect_calls += 1
            return True

    driver = _UnsafeCmw()
    service = InstrumentHALService(mode=DriverMode.REAL)
    service.drivers = {"baseStation": driver}

    assert await service.reconnect_driver("baseStation") is False
    assert driver.connect_calls == 0
