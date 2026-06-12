from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import List

import pytest

from app.hal.base import InstrumentStatus
from app.hal.channel_emulator import ChannelLoadMode
from app.hal.propsim_fs16_playback import RealPropsimFs16PlaybackDriver


class _FakeVisaResource:
    def __init__(self) -> None:
        self.writes: List[str] = []
        self.queries: List[str] = []
        self.raw_writes: List[bytes] = []
        self.timeout = 5000
        self.cwd = r"C:\Temp"

    def write(self, cmd: str) -> None:
        self.writes.append(cmd)
        if cmd.startswith("MMEM:CDIR "):
            self.cwd = cmd.split(" ", 1)[1].strip().strip('"')

    def query(self, cmd: str) -> str:
        self.queries.append(cmd)
        if cmd == "*OPC?":
            return "1\n"
        if cmd == "SYST:ERR?":
            return '0,"No error"\n'
        if cmd.startswith('MMEM:CAT? "'):
            return "\n"
        if cmd == "MMEM:CDIR?":
            return f'"{self.cwd}"\n'
        if cmd == "MMEM:CAT?":
            if self.cwd == r"D:\User Playbacks":
                return '"Emulation0609.smu",2048,"mimo0609.smu",1024\n'
            return '"DL.asc",1024\n'
        if cmd == "DIAG:SIMU:STATe?":
            return "OPEN\n"
        return "\n"

    def write_raw(self, payload: bytes) -> None:
        self.raw_writes.append(payload)


def _driver(**config) -> tuple[RealPropsimFs16PlaybackDriver, _FakeVisaResource]:
    d = RealPropsimFs16PlaybackDriver(
        "fs16-playback-test",
        {"ip": "192.168.0.100", "port": 5025, **config},
    )
    visa = _FakeVisaResource()
    d._visa_resource = visa
    d._status = InstrumentStatus.READY
    return d, visa


def test_resource_string_prefers_operator_endpoint():
    d, _visa = _driver(endpoint="TCPIP0::192.168.0.100::hislip0::INSTR")

    assert d._resource_string() == "TCPIP0::192.168.0.100::hislip0::INSTR"


def test_resource_string_falls_back_to_raw_socket():
    d, _visa = _driver()

    assert d._resource_string() == "TCPIP0::192.168.0.100::5025::SOCKET"


@pytest.mark.asyncio
async def test_public_remote_playback_visibility_helpers_use_fs16_path():
    d, _visa = _driver()

    assert d.remote_playback_path("Emulation0609.smu") == r"D:\User Playbacks\Emulation0609.smu"
    assert await d.remote_playback_file_exists("Emulation0609.smu") is True
    assert await d.remote_playback_file_exists("Missing.smu") is False


@pytest.mark.asyncio
async def test_remote_playback_file_loads_without_local_waveform_dir():
    d, visa = _driver(remote_playback_file="DL.asc")

    ok = await d.load_channel(
        ChannelLoadMode.EXTERNAL_WAVEFORM,
        model_name="UMa CDL-C NLOS",
        scenario="operator-supplied",
        parameters={},
        waveform_dir=None,
    )

    assert ok is True
    assert r"CALC:FILT:FILE D:\User Playbacks\DL.asc" in visa.writes
    assert d._loaded_playback_file == r"D:\User Playbacks\DL.asc"


@pytest.mark.asyncio
async def test_single_local_asc_maps_to_playback_dir_when_upload_disabled(tmp_path: Path):
    (tmp_path / "DL.asc").write_text("dummy asc", encoding="utf-8")
    d, visa = _driver()

    ok = await d.upload_asc_files(str(tmp_path), cdl_model_name="custom")

    assert ok is True
    assert r"CALC:FILT:FILE D:\User Playbacks\DL.asc" in visa.writes
    assert visa.raw_writes == []


@pytest.mark.asyncio
async def test_multiple_asc_files_without_entry_file_fails_loudly(tmp_path: Path):
    (tmp_path / "link0.asc").write_text("0", encoding="utf-8")
    (tmp_path / "link1.asc").write_text("1", encoding="utf-8")
    d, visa = _driver()

    ok = await d.upload_asc_files(str(tmp_path), cdl_model_name="bundle")

    assert ok is False
    assert "unambiguous local entry" in (d.last_error or "")
    assert not any(w.startswith("CALC:FILT:FILE") for w in visa.writes)


@pytest.mark.asyncio
async def test_scpi_upload_uses_mmem_data_when_explicitly_enabled(tmp_path: Path):
    (tmp_path / "DL.asc").write_bytes(b"abc123")
    d, visa = _driver(enable_scpi_file_upload=True)

    ok = await d.upload_asc_files(str(tmp_path), cdl_model_name="UMa CDL-C")

    assert ok is True
    assert visa.raw_writes, "MMEM:DATA binary write should be used"
    assert visa.raw_writes[0].startswith(
        b'MMEM:DATA "D:\\User Playbacks\\UMa_CDL-C\\DL.asc",#16abc123'
    )
    assert r"CALC:FILT:FILE D:\User Playbacks\UMa_CDL-C\DL.asc" in visa.writes


@pytest.mark.asyncio
async def test_start_and_stop_use_configurable_playback_commands():
    d, visa = _driver(remote_playback_file="DL.asc")
    assert await d.upload_asc_files("", cdl_model_name="custom")

    assert await d.start_emulation() is True
    assert d.status == InstrumentStatus.BUSY
    assert await d.stop_emulation() is True
    assert d.status == InstrumentStatus.READY
    assert "DIAG:SIMU:GO" in visa.writes
    assert "DIAG:SIMU:GOS" in visa.writes


@pytest.mark.asyncio
async def test_remote_existence_check_uses_playback_directory_listing():
    d, _visa = _driver(remote_playback_file="Missing.asc", verify_remote_file_exists=True)

    ok = await d.upload_asc_files("", cdl_model_name="custom")

    assert ok is False
    assert "remote playback file not found" in (d.last_error or "")


@pytest.mark.asyncio
async def test_remote_existence_check_uses_cdir_fallback_for_path_queries():
    d, visa = _driver(remote_playback_file="mimo0609.smu", verify_remote_file_exists=True)

    ok = await d.upload_asc_files("", cdl_model_name="custom")

    assert ok is True
    assert 'MMEM:CAT? "D:\\User Playbacks"' in visa.queries
    assert 'MMEM:CDIR "D:\\User Playbacks"' in visa.writes
    assert "MMEM:CAT?" in visa.queries
    assert r"CALC:FILT:FILE D:\User Playbacks\mimo0609.smu" in visa.writes


@pytest.mark.asyncio
async def test_load_command_template_remains_operator_configurable():
    d, visa = _driver(
        remote_playback_file="mimo0609.smu",
        load_command_template='MMEM:LOAD:STAT "{path}"',
    )

    ok = await d.upload_asc_files("", cdl_model_name="custom")

    assert ok is True
    assert 'MMEM:LOAD:STAT "D:\\User Playbacks\\mimo0609.smu"' in visa.writes


@pytest.mark.asyncio
async def test_load_ignores_stale_opc_response_when_reading_error_queue():
    d, visa = _driver(remote_playback_file="Emulation0609.smu")
    original_query = visa.query
    sys_err_responses = ["1\n", '0,"No error"\n']

    def query(cmd: str) -> str:
        if cmd == "SYST:ERR?" and sys_err_responses:
            visa.queries.append(cmd)
            return sys_err_responses.pop(0)
        return original_query(cmd)

    visa.query = query

    ok = await d.upload_asc_files("", cdl_model_name="custom")

    assert ok is True
    assert r"CALC:FILT:FILE D:\User Playbacks\Emulation0609.smu" in visa.writes
    assert d._loaded_playback_file == r"D:\User Playbacks\Emulation0609.smu"


@pytest.mark.asyncio
async def test_fs16_queries_are_serialized_on_single_visa_session():
    d, visa = _driver()
    active = 0
    max_active = 0
    guard = threading.Lock()

    def slow_query(cmd: str) -> str:
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        visa.queries.append(cmd)
        if cmd == "*OPC?":
            return "1\n"
        if cmd == "SYST:ERR?":
            return '0,"No error"\n'
        return "\n"

    visa.query = slow_query

    responses = await asyncio.gather(
        d._query("*OPC?"),
        d._query("SYST:ERR?"),
    )

    assert responses == ["1\n", '0,"No error"\n']
    assert max_active == 1
