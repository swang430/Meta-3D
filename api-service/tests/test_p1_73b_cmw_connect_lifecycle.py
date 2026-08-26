"""P1-73B Task 7：CMW500 connect 只能识别，不能修改仪表。"""

from unittest.mock import patch

import pytest

from app.hal.cmw500_base_station import RealCmw500Driver


class _Session:
    def __init__(self, responses: dict[str, str | Exception]):
        self.responses = responses
        self.queries: list[str] = []
        self.writes: list[str] = []
        self.closed = False

    def query(self, command: str) -> str:
        self.queries.append(command)
        response = self.responses.get(command, "")
        if isinstance(response, Exception):
            raise response
        return response

    def write(self, command: str) -> None:
        self.writes.append(command)

    def close(self) -> None:
        self.closed = True


class _ResourceManager:
    def __init__(self, session: _Session):
        self.session = session
        self.opened: list[str] = []

    def open_resource(self, resource: str, **_kwargs) -> _Session:
        self.opened.append(resource)
        return self.session


def _responses(
    *,
    idn: str = "Rohde&Schwarz,CMW,1201.0002K50/123456,4.0.250",
) -> dict[str, str | Exception]:
    return {
        "*IDN?": idn,
        "SYSTem:BASE:OPTion:LIST? SWOPtion,VALid": "CMW-KS520,CMW-KS510",
        "SYSTem:BASE:OPTion:LIST? HWOPtion,FUNCtional": "CMW-B570B",
    }


@pytest.mark.asyncio
async def test_connect_is_read_only_and_captures_model_version_and_options():
    session = _Session(_responses())
    rm = _ResourceManager(session)
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})

    with patch("pyvisa.ResourceManager", return_value=rm):
        assert await driver.connect() is True

    assert session.writes == []
    assert session.queries == [
        "*IDN?",
        "SYSTem:BASE:OPTion:LIST? SWOPtion,VALid",
        "SYSTem:BASE:OPTion:LIST? HWOPtion,FUNCtional",
    ]
    identity = driver.get_base_station_identity()
    assert identity.adapter_id == "cmw500"
    assert identity.model == "CMW"
    assert identity.firmware_version == "4.0.250"
    assert identity.options == ("CMW-KS520", "CMW-KS510", "CMW-B570B")
    assert driver.identity_snapshot_verified is True


@pytest.mark.asyncio
async def test_connect_rejects_wrong_model_and_closes_its_session():
    session = _Session(_responses(idn="Rohde&Schwarz,FSW,123456,4.0.250"))
    rm = _ResourceManager(session)
    driver = RealCmw500Driver("wrong", {"ip_address": "192.0.2.10"})

    with patch("pyvisa.ResourceManager", return_value=rm):
        assert await driver.connect() is False

    assert session.closed is True
    assert driver.identity_snapshot_verified is False


@pytest.mark.asyncio
async def test_unparseable_firmware_keeps_identity_unverified_without_writes():
    session = _Session(_responses(idn="Rohde&Schwarz,CMW,123456,unknown"))
    rm = _ResourceManager(session)
    driver = RealCmw500Driver("unknown-version", {"ip_address": "192.0.2.10"})

    with patch("pyvisa.ResourceManager", return_value=rm):
        assert await driver.connect() is True

    assert driver.get_base_station_identity().firmware_version is None
    assert driver.identity_snapshot_verified is False
    assert session.writes == []


@pytest.mark.asyncio
async def test_option_query_failure_keeps_identity_unverified_and_empty():
    responses = _responses()
    responses["SYSTem:BASE:OPTion:LIST? HWOPtion,FUNCtional"] = RuntimeError(
        "option query failed"
    )
    session = _Session(responses)
    rm = _ResourceManager(session)
    driver = RealCmw500Driver("unknown-options", {"ip_address": "192.0.2.10"})

    with patch("pyvisa.ResourceManager", return_value=rm):
        assert await driver.connect() is True

    assert driver.get_base_station_identity().options == ()
    assert driver.identity_snapshot_verified is False
    assert session.writes == []


@pytest.mark.asyncio
async def test_connect_exception_closes_only_the_opened_session():
    session = _Session({"*IDN?": RuntimeError("read failed")})
    rm = _ResourceManager(session)
    driver = RealCmw500Driver("failed", {"ip_address": "192.0.2.10"})

    with patch("pyvisa.ResourceManager", return_value=rm):
        assert await driver.connect() is False

    assert session.closed is True
