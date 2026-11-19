import pytest
from unittest.mock import AsyncMock
from app.api import instrument
from app.hal.aerotech_positioner import RealAerotechDriver
from app.hal.rf_switch import EtslSwitchDriver


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,reply,ok", [
    ("positioner", "0", True), ("positioner", "nan", False),
    ("positioner", "", False), ("positioner", TimeoutError(), False),
    ("rfSwitch", "ETS-Lindgren,EMCenter,123", True),
    ("rfSwitch", "ETS-Lindgren EMCenter version 4.3.4", True),
    ("rfSwitch", "Keysight,F64,123", False), ("rfSwitch", "OK", False),
    ("rfSwitch", "ETS-Lindgren,EMSwitch,123", False),
    ("rfSwitch", "ERROR 3", False), ("rfSwitch", "", False),
    ("rfSwitch", TimeoutError(), False),
])
async def test_device_reply(kind, reply, ok):
    io = AsyncMock(side_effect=reply if isinstance(reply, Exception) else None,
                   return_value=reply)
    if kind == "positioner":
        driver = object.__new__(RealAerotechDriver)
        driver.az_axis = "X"
        driver._send = io
    else:
        driver = object.__new__(EtslSwitchDriver)
        driver._send_command = io
    result = await instrument._device_connection_probe(driver)
    assert result.success is ok
    assert result.idn == (reply if ok and kind == "rfSwitch" else None)
    assert io.await_args.args == (("PFBK(X)" if kind == "positioner" else "*IDN?"),)
