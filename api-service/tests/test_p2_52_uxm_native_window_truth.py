"""P2-52/U-13：UXM 原生 Single + Length 有限窗口现场诊断合同。"""
from __future__ import annotations

import asyncio
import inspect
import math
import threading
from pathlib import Path
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest

from app.diagnostics import loader
from app.diagnostics.sequences import uxm_native_window_truth as seq
from app.diagnostics.sequences import uxm_scpi_compatibility as compatibility
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
    UxmTestApp,
)


class _SentinelProfile(UxmLteNrIratProfile):
    """用哨兵 ERR 证明序列不硬编码另一条错误队列。"""

    ERR = "SENTINEL:ERR?"


class _FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeBs:
    def __init__(
        self,
        *,
        profile: type[UxmTestApp] = _SentinelProfile,
        status: str = "CONN",
        progress: list[object] | None = None,
        errors_after: dict[str, list[str] | str] | None = None,
        raise_on: dict[tuple[str, str], BaseException] | None = None,
    ) -> None:
        self._cmds = profile
        self.status = status
        self.progress = list(progress or [0, 1000, 2000, 2000, 0, 1200, 2000, 2000])
        self.errors_after = {
            key: list(value) if isinstance(value, list) else [value]
            for key, value in (errors_after or {}).items()
        }
        self.raise_on = raise_on or {}
        self.ops: list[tuple[str, str]] = []
        self.call_threads: list[int] = []
        self._last_operation: str | None = None

    def _query(self, command: str) -> str:
        self.call_threads.append(threading.get_ident())
        self.ops.append(("Q", command))
        error = self.raise_on.get(("Q", command))
        if error is not None:
            raise error
        if command == self._cmds.ERR:
            key = self._last_operation or "<initial>"
            values = self.errors_after.get(key)
            if values:
                return values.pop(0)
            return '0,"No error"'
        self._last_operation = command
        if command == self._cmds.CELL_STATUS_QUERY.format(cell="CELL1"):
            return self.status
        if command == self._cmds.MEAS_BLER_DL.format(cell="CELL1"):
            value = self.progress.pop(0) if self.progress else 2000
            return str(value)
        return ""

    def _write(self, command: str) -> None:
        self.call_threads.append(threading.get_ident())
        self.ops.append(("W", command))
        self._last_operation = command
        error = self.raise_on.get(("W", command))
        if error is not None:
            raise error


class MockFakeBs(_FakeBs):
    pass


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    clock = _FakeClock()

    async def _advance(seconds: float) -> None:
        clock.advance(seconds)

    monkeypatch.setattr(seq.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(seq.asyncio, "sleep", _advance)
    return clock


def _run(bs, params=None):
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}
    return asyncio.run(
        seq.run(MagicMock(), hal, params or {}, log=lambda *_: None)
    )


def _writes(bs: _FakeBs) -> list[str]:
    return [command for kind, command in bs.ops if kind == "W"]


def test_loader_discovers_unsafe_operator_confirmed_sequence():
    loader.reset_cache()
    entries = {item["key"]: item for item in loader.list_sequences()}
    item = entries["uxm_native_window_truth"]
    assert item["safe_during_test"] is False
    assert item["required_categories"] == ["baseStation"]
    params = {entry["name"]: entry for entry in item["params_schema"]}
    assert params["confirm_write"]["default"] is False
    assert params["measurement_length"]["default"] == 2000


def test_new_controls_exist_only_on_irat_and_keep_manual_scope_explicit():
    assert UxmLteNrIratProfile.MEAS_BTHROUGHPUT_LENGTH_ALL == (
        "BSE:MEASure:NR5G:BTHRoughput:LENGth:ALL"
    )
    assert UxmLteNrIratProfile.MEAS_BTHROUGHPUT_CONTINUOUS_ALL == (
        "BSE:MEASure:NR5G:BTHRoughput:CONTinuous:ALL"
    )
    assert Uxm5GNRTestAppProfile.MEAS_BTHROUGHPUT_LENGTH_ALL is None
    assert Uxm5GNRTestAppProfile.MEAS_BTHROUGHPUT_CONTINUOUS_ALL is None
    source = inspect.getsource(UxmLteNrIratProfile)
    for anchor in (
        "Examples > Measuring BLER",
        "Application Mode",
        "NSA",
        "SA",
        "LTE_NR_IRAT",
        "诊断",
    ):
        assert anchor in source


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"confirm_write": False},
        {"confirm_write": "true"},
        {"confirm_write": True, "measurement_length": True},
        {"confirm_write": True, "measurement_length": 1999},
        {"confirm_write": True, "measurement_length": 2100},
        {"confirm_write": True, "measurement_length": 360200},
        {"confirm_write": True, "poll_interval_s": 0},
        {"confirm_write": True, "poll_interval_s": math.inf},
        {"confirm_write": True, "timeout_s": 0},
    ],
)
def test_invalid_or_missing_confirmation_refuses_all_scpi(params):
    bs = _FakeBs()

    result = _run(bs, params)

    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"
    assert result.extra["formal_verdict"] == "unverified"
    assert bs.ops == []


def test_mock_wrong_profile_and_missing_control_refuse_all_scpi():
    for bs in (
        MockFakeBs(),
        _FakeBs(profile=Uxm5GNRTestAppProfile),
        _FakeBs(profile=type(
            "MissingLengthProfile",
            (_SentinelProfile,),
            {"MEAS_BTHROUGHPUT_LENGTH_ALL": None},
        )),
    ):
        result = _run(bs, {"confirm_write": True})
        assert result.success is False
        assert bs.ops == []


@pytest.mark.parametrize("status", ["", "ON", "OFF", "IDLE", "AGGR", "ACT"])
def test_only_explicit_connected_protocol_state_allows_first_write(status):
    bs = _FakeBs(status=status)

    result = _run(bs, {"confirm_write": True})

    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"
    assert _writes(bs) == []


def test_two_exact_single_windows_are_observed_but_never_formally_green():
    event_loop_thread = threading.get_ident()
    bs = _FakeBs()

    result = _run(
        bs,
        {
            "confirm_write": True,
            "measurement_length": 2000,
            "poll_interval_s": 0.1,
            "timeout_s": 5,
        },
    )

    profile = _SentinelProfile
    per_window = [
        profile.MEAS_BTHROUGHPUT_CLEAR,
        f"{profile.MEAS_BTHROUGHPUT_STATE} 0",
        f"{profile.MEAS_BTHROUGHPUT_LENGTH_ALL} 2000",
        f"{profile.MEAS_BTHROUGHPUT_CONTINUOUS_ALL} 0",
        f"{profile.MEAS_BTHROUGHPUT_STATE} 1",
    ]
    assert _writes(bs) == per_window + per_window + [
        f"{profile.MEAS_BTHROUGHPUT_STATE} 0"
    ]
    assert result.success is False
    assert result.extra["verdict"] == "OBSERVED"
    assert result.extra["formal_verdict"] == "unverified"
    assert result.extra["requested_length"] == 2000
    assert result.extra["observed_boundary"] is True
    assert result.extra["single_shot_observed"] is True
    assert result.extra["repeatable_observed"] is True
    assert [window["progress"] for window in result.extra["windows"]] == [
        [0, 1000, 2000, 2000],
        [0, 1200, 2000, 2000],
    ]
    assert "applied_length" not in result.extra
    assert result.extra["cleanup"]["state_off_sent"] is True
    assert result.extra["cleanup"]["error_queue_clean"] is True
    assert bs.call_threads and all(
        thread_id != event_loop_thread for thread_id in bs.call_threads
    )


@pytest.mark.parametrize(
    ("progress", "reason"),
    [
        ([0, "bad"], "解析"),
        ([0, 1000, 900], "回退"),
        ([0, 2200], "越过"),
        ([2000], "继承"),
    ],
)
def test_invalid_progress_blocks_and_still_cleans_up(progress, reason):
    bs = _FakeBs(progress=progress)

    result = _run(bs, {"confirm_write": True, "timeout_s": 1})

    assert result.success is False
    assert result.extra["verdict"] == "BLOCKED"
    assert reason in result.summary
    assert _writes(bs)[-1] == f"{_SentinelProfile.MEAS_BTHROUGHPUT_STATE} 0"
    assert result.extra["cleanup"]["state_off_sent"] is True


def test_progress_timeout_blocks_and_still_cleans_up():
    bs = _FakeBs(progress=[0] * 100)

    result = _run(
        bs,
        {
            "confirm_write": True,
            "poll_interval_s": 0.5,
            "timeout_s": 1,
        },
    )

    assert result.extra["verdict"] == "BLOCKED"
    assert "超时" in result.summary
    assert _writes(bs)[-1].endswith("STATe 0")


def test_command_error_stops_window_and_cleanup_error_is_separately_recorded():
    rejected = f"{_SentinelProfile.MEAS_BTHROUGHPUT_LENGTH_ALL} 2000"
    cleanup = f"{_SentinelProfile.MEAS_BTHROUGHPUT_STATE} 0"
    bs = _FakeBs(
        errors_after={
            rejected: ['-222,"Data out of range"', '0,"No error"'],
            # 第一次 STATe 0 属于窗口配置；第二次才是 finally cleanup。
            cleanup: [
                '0,"No error"',
                '-200,"Cleanup rejected"',
                '0,"No error"',
            ],
        }
    )

    result = _run(bs, {"confirm_write": True})

    assert result.extra["verdict"] == "BLOCKED"
    assert rejected in result.summary
    assert cleanup == _writes(bs)[-1]
    assert result.extra["cleanup"]["state_off_sent"] is True
    assert result.extra["cleanup"]["error_queue_clean"] is False
    assert "Cleanup rejected" in result.extra["cleanup"]["errors"][0]


def test_driver_exception_after_first_write_still_sends_state_off():
    length = f"{_SentinelProfile.MEAS_BTHROUGHPUT_LENGTH_ALL} 2000"
    bs = _FakeBs(raise_on={("W", length): TimeoutError("visa timeout")})

    result = _run(bs, {"confirm_write": True})

    assert result.extra["verdict"] == "BLOCKED"
    assert "TimeoutError" in result.summary
    assert any("异常后错误队列" in step.label for step in result.steps)
    assert _writes(bs)[-1] == f"{_SentinelProfile.MEAS_BTHROUGHPUT_STATE} 0"


@pytest.mark.parametrize(
    "errors_after",
    [
        {"<initial>": ["malformed"]},
        {
            _SentinelProfile.CELL_STATUS_QUERY.format(cell="CELL1"): [
                '-200,"Status unavailable"',
                '0,"No error"',
            ]
        },
    ],
)
def test_untrusted_preflight_error_state_aborts_before_any_write(errors_after):
    bs = _FakeBs(errors_after=errors_after)

    result = _run(bs, {"confirm_write": True})

    assert result.extra["verdict"] == "ABORTED"
    assert _writes(bs) == []


def test_run_cancellation_waits_for_inflight_write_then_performs_cleanup():
    started = threading.Event()
    release = threading.Event()

    class _BlockingFirstWriteBs(_FakeBs):
        def __init__(self):
            super().__init__()
            self.write_calls = 0

        def _write(self, command: str) -> None:
            self.write_calls += 1
            super()._write(command)
            if self.write_calls == 1:
                started.set()
                release.wait(timeout=2)

    bs = _BlockingFirstWriteBs()
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}

    async def exercise():
        task = asyncio.create_task(seq.run(
            MagicMock(),
            hal,
            {"confirm_write": True},
            log=lambda *_: None,
        ))
        loop = asyncio.get_running_loop()
        assert await loop.run_in_executor(None, started.wait, 1)
        task.cancel()
        await loop.run_in_executor(None, lambda: None)
        assert task.done() is False
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert _writes(bs)[-1] == f"{_SentinelProfile.MEAS_BTHROUGHPUT_STATE} 0"
    assert bs.ops[-1] == ("Q", _SentinelProfile.ERR)


def test_manual_archive_contains_the_exact_single_length_progress_contract():
    archive = (
        Path(__file__).parents[2]
        / "Instrument_API_Doc/Keysight UXM NR SCPI"
        / "5G_NR_Test_Application_SCPI_Reference.zip"
    )
    with ZipFile(archive) as bundle:
        html_name = next(name for name in bundle.namelist() if name.endswith(".html"))
        html = bundle.read(html_name).decode("utf-8", errors="replace")
    for anchor in (
        "examples-measuring-bler",
        "BTHRoughput</span><span class=\"op\">:</span><span class=\"dt\">LENGth",
        "BTHRoughput</span><span class=\"op\">:</span><span class=\"dt\">CONTinuous",
        "progress-count is what you must compare to the configured",
        "Application Mode",
        "NSA | SA",
    ):
        assert anchor in html


def test_diagnostic_only_controls_have_no_formal_production_consumer():
    app_root = Path(__file__).parents[1] / "app"
    allowed = {
        app_root / "hal/uxm_command_profiles.py",
        app_root / "diagnostics/sequences/uxm_native_window_truth.py",
        app_root / "diagnostics/sequences/uxm_scpi_compatibility.py",
    }
    names = {
        "MEAS_BTHROUGHPUT_LENGTH_ALL",
        "MEAS_BTHROUGHPUT_CONTINUOUS_ALL",
    }
    consumers: set[Path] = set()
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(name in text for name in names):
            consumers.add(path)
    assert consumers == allowed


def test_compatibility_probe_never_invents_queries_for_write_only_controls():
    bs = _FakeBs()
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}

    asyncio.run(compatibility.run(
        MagicMock(), hal, {"include_supported": True}, log=lambda *_: None,
    ))

    forbidden = {
        f"{_SentinelProfile.MEAS_BTHROUGHPUT_LENGTH_ALL}?",
        f"{_SentinelProfile.MEAS_BTHROUGHPUT_CONTINUOUS_ALL}?",
    }
    assert not forbidden.intersection(command for _, command in bs.ops)
    assert compatibility._UNVERIFIED_QUERY_FORM_NAMES == {
        "MEAS_BTHROUGHPUT_LENGTH_ALL",
        "MEAS_BTHROUGHPUT_CONTINUOUS_ALL",
    }


def test_sync_worker_cancellation_waits_for_real_io_before_propagating():
    started = threading.Event()
    release = threading.Event()

    def blocking_call():
        started.set()
        release.wait(timeout=2)

    async def exercise():
        task = asyncio.create_task(seq._invoke_driver_method(blocking_call))
        loop = asyncio.get_running_loop()
        assert await loop.run_in_executor(None, started.wait, 1)
        task.cancel()
        await loop.run_in_executor(None, lambda: None)
        assert task.done() is False
        task.cancel()
        await loop.run_in_executor(None, lambda: None)
        assert task.done() is False
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
