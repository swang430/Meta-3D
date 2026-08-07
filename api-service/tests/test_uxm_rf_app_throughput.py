"""RF App IRAT_LITE BTPut/TMONitor driver contract tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmRfAppIratLiteProfile,
)


def _rf_driver() -> RealUxmDriver:
    driver = RealUxmDriver(
        "uxm-rf-app",
        {"ip": "201.20.2.1", "uxm_app_mode": "rf_app"},
    )
    driver._cmds = UxmRfAppIratLiteProfile()
    driver._cell_id = "CELL1"
    return driver


def test_rf_app_profile_uses_live_verified_btput_commands():
    profile = UxmRfAppIratLiteProfile()
    assert profile.RF_DL_PADDING == "BSE:CONFig:NR5G:{cell}:SCHeduling:DL:PADDing:STATe"
    assert profile.RF_BTPUT_STATE == "BSE:MEASure:NR5G:BTPut:STATe"
    assert profile.RF_BTPUT_CONTINUOUS_ALL == "BSE:MEASure:NR5G:BTPut:CONTinuous:ALL"
    assert profile.RF_BTPUT_LENGTH_ALL == "BSE:MEASure:NR5G:BTPut:LENGth:ALL"
    assert profile.RF_BTPUT_RESET == "BSE:MEASure:NR5G:BTPut:RESet"
    assert profile.RF_BTPUT_DL_QUERY == "BSE:MEASure:NR5G:{cell}:BTPut:DL?"
    assert profile.RF_TMONITOR_DL_NR_QUERY == "BSE:METRics:TMONitor:OTA:DL:NR?"
    # The unsupported old RF-App query remains disabled.
    assert profile.MEAS_BTHROUGHPUT_DL_JSON is None


@pytest.mark.asyncio
async def test_read_btput_parses_real_fields():
    driver = _rf_driver()
    driver._rf_app_dl_restore = {"cell": "CELL1"}
    responses = {
        driver._cmds.RF_BTPUT_DL_QUERY.format(cell="CELL1"):
            '"160,82,78,0,78,78,0.4875,5.88104,0.5125"',
        driver._cmds.RF_TMONITOR_DL_NR_QUERY: '"5.88,12.14,8.54,895510752"',
    }

    def query(command: str) -> str:
        if command == "SYSTem:ERRor?":
            return '0,"No error"'
        return responses[command]

    driver._query = MagicMock(side_effect=query)
    sample = await driver.read_rf_app_max_dl_throughput("CELL1")

    assert sample["valid"] is True
    assert sample["source"] == "btput"
    assert sample["dl_throughput_mbps"] == pytest.approx(5.88104)
    assert sample["dl_bler"] == pytest.approx(0.4875)
    assert sample["progress_count"] == 160
    assert sample["tmonitor_peak_mbps"] == pytest.approx(12.14)
    assert sample["raw_btput"].startswith('"160,')


@pytest.mark.asyncio
async def test_read_btput_nan_falls_back_to_real_tmonitor_current():
    driver = _rf_driver()
    driver._rf_app_dl_restore = {"cell": "CELL1"}

    def query(command: str) -> str:
        if command == "SYSTem:ERRor?":
            return '0,"No error"'
        if command.endswith("BTPut:DL?"):
            return '"0,0,0,0,0,0,NaN,NaN,NaN"'
        if command == driver._cmds.RF_TMONITOR_DL_NR_QUERY:
            return '"8.18,12.14,8.57,889916592"'
        raise AssertionError(command)

    driver._query = MagicMock(side_effect=query)
    sample = await driver.read_rf_app_max_dl_throughput("CELL1")

    assert sample["valid"] is True
    assert sample["source"] == "tmonitor"
    assert sample["dl_throughput_mbps"] == pytest.approx(8.18)
    assert sample["dl_bler"] is None


@pytest.mark.asyncio
async def test_non_rf_profile_refuses_before_any_scpi():
    driver = _rf_driver()
    driver._cmds = Uxm5GNRTestAppProfile()
    driver._query = MagicMock(side_effect=AssertionError("SCPI must not be sent"))
    driver._write = MagicMock(side_effect=AssertionError("SCPI must not be sent"))

    with pytest.raises(RuntimeError, match="IRAT_LITE"):
        await driver.start_rf_app_max_dl_throughput("CELL1", 200)
    driver._query.assert_not_called()
    driver._write.assert_not_called()


@pytest.mark.asyncio
async def test_start_stop_restores_original_measurement_settings():
    driver = _rf_driver()
    state = {"padding": 0, "btput": 0, "continuous": 1, "length": 360000}
    writes: list[str] = []

    def write(command: str) -> None:
        writes.append(command)
        if command == f"{driver._cmds.RF_BTPUT_STATE} ON":
            state["btput"] = 1
        elif command == f"{driver._cmds.RF_BTPUT_STATE} OFF":
            state["btput"] = 0
        elif command.endswith("PADDing:STATe ON"):
            state["padding"] = 1
        elif command.endswith("PADDing:STATe OFF"):
            state["padding"] = 0
        elif command.startswith(driver._cmds.RF_BTPUT_CONTINUOUS_ALL + " "):
            state["continuous"] = 1 if command.endswith(" ON") else 0
        elif command.startswith(driver._cmds.RF_BTPUT_LENGTH_ALL + " "):
            state["length"] = int(command.rsplit(" ", 1)[1])

    def query(command: str) -> str:
        if command == "SYSTem:ERRor?":
            return '0,"No error"'
        if command == "BSE:STATus:NR5G:CELL1?":
            return "CONN"
        if command.endswith("PADDing:STATe?"):
            return str(state["padding"])
        if command == driver._cmds.RF_BTPUT_STATE + "?":
            return str(state["btput"])
        if command == driver._cmds.RF_BTPUT_CONTINUOUS_ALL + "?":
            return str(state["continuous"])
        if command == driver._cmds.RF_BTPUT_LENGTH_ALL + "?":
            return str(state["length"])
        raise AssertionError(command)

    driver._write = MagicMock(side_effect=write)
    driver._query = MagicMock(side_effect=query)

    started = await driver.start_rf_app_max_dl_throughput("CELL1", 200)
    assert started["dl_padding_enabled_by_diagnostic"] is True
    assert state == {"padding": 1, "btput": 1, "continuous": 1, "length": 200}
    assert driver.rf_app_dl_throughput_cleanup_required is True

    stopped = await driver.stop_rf_app_max_dl_throughput()
    assert stopped["stopped"] is True
    assert state == {"padding": 0, "btput": 0, "continuous": 1, "length": 360000}
    assert driver.rf_app_dl_throughput_cleanup_required is False
    assert "BSE:MEASure:NR5G:BTPut:RESet" in writes
    assert "BSE:METRics:RESet" in writes


def test_checked_write_raises_on_scpi_error():
    driver = _rf_driver()
    driver._write = MagicMock()
    driver._query = MagicMock(return_value='-113,"Undefined header"')

    with pytest.raises(RuntimeError, match="Undefined header"):
        driver._rf_app_write_checked("BAD:HEADER")
    driver._write.assert_called_once_with("BAD:HEADER")
