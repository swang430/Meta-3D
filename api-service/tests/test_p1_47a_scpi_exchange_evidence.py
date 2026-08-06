"""P1-47A：SCPI/AeroBasic 传输证据必须可配对、可分类且不泄密。"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any

import pytest
import pyvisa

from app.api.instrument import _run_command_via_hal, _send_scpi_command
from app.core import logging_config
from app.core.logging_config import ContextFilter, JsonFormatter
from app.hal.aerotech_positioner import AerotechError, RealAerotechDriver
from app.hal.base import InstrumentDriver, redact_instrument_log_text
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.propsim_fs16 import RealPropsimFs16Driver
from app.hal.uxm_base_station import RealUxmDriver


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def scpi_capture():
    logger = logging.getLogger("app.hal.scpi")
    handler = _RecordingHandler()
    previous = (logger.level, logger.disabled)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.disabled = False
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous[0])
        logger.disabled = previous[1]


def _direction(records: list[logging.LogRecord], value: str):
    return [r for r in records if getattr(r, "direction", None) == value]


class _Driver(InstrumentDriver):
    def __init__(self, *, response: str = "OK", error: BaseException | None = None):
        super().__init__("stub-evidence", {})
        self.response = response
        self.error = error
        self.seen: list[str] = []

    def _do_query(self, cmd: str, **kwargs: Any) -> str:
        self.seen.append(cmd)
        if self.error:
            raise self.error
        return self.response

    def _do_write(self, cmd: str, **kwargs: Any) -> None:
        self.seen.append(cmd)
        if self.error:
            raise self.error

    async def connect(self): return True
    async def disconnect(self): return True
    async def configure(self, config): return True
    async def get_capabilities(self): return []
    async def get_metrics(self): return None
    async def reset(self): return True


def _assert_pair(records: list[logging.LogRecord], terminal: str, operation: str) -> None:
    tx = _direction(records, "TX")
    end = _direction(records, terminal)
    assert len(tx) == len(end) == 1
    assert tx[0].exchange_id
    assert tx[0].exchange_id == end[0].exchange_id
    assert tx[0].operation == end[0].operation == operation
    assert tx[0].command == end[0].command


def test_sync_query_and_write_share_structured_exchange_ids(scpi_capture):
    driver = _Driver(response="VALUE")
    assert driver._query("READ?") == "VALUE"
    _assert_pair(scpi_capture.records, "RX", "query")
    rx = _direction(scpi_capture.records, "RX")[0]
    assert rx.result_type == "response"
    assert rx.response == "VALUE"

    scpi_capture.records.clear()
    driver._write("SET 1")
    _assert_pair(scpi_capture.records, "OK", "command")
    assert _direction(scpi_capture.records, "OK")[0].result_type == "ok"


@pytest.mark.asyncio
async def test_concurrent_and_nested_queries_pair_by_id_not_adjacency(scpi_capture):
    class _Nested(_Driver):
        def _do_query(self, cmd: str, **kwargs: Any):
            return self._run(cmd)

        async def _run(self, cmd: str) -> str:
            if cmd == "OUTER?":
                inner = await self._query("INNER?")
                await asyncio.sleep(0)
                return f"outer:{inner}"
            await asyncio.sleep(0.01 if cmd == "SLOW?" else 0)
            return cmd.lower()

    driver = _Nested()
    outer, slow, fast = await asyncio.gather(
        driver._query("OUTER?"),
        driver._query("SLOW?"),
        driver._query("FAST?"),
    )
    assert (outer, slow, fast) == ("outer:inner?", "slow?", "fast?")

    grouped: dict[str, list[logging.LogRecord]] = {}
    for record in scpi_capture.records:
        grouped.setdefault(record.exchange_id, []).append(record)
    assert len(grouped) == 4
    for pair in grouped.values():
        assert [r.direction for r in pair] == ["TX", "RX"]
        assert pair[0].command == pair[1].command


@pytest.mark.asyncio
async def test_cancelled_query_logs_terminal_and_propagates_same_cancel(scpi_capture):
    entered = asyncio.Event()

    class _Cancelled(_Driver):
        def _do_query(self, cmd: str, **kwargs: Any):
            return self._block()

        async def _block(self) -> str:
            entered.set()
            await asyncio.Event().wait()
            return "never"

    task = asyncio.create_task(_Cancelled()._query("WAIT?"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    _assert_pair(scpi_capture.records, "ERR", "query")
    err = _direction(scpi_capture.records, "ERR")[0]
    assert err.result_type == "cancelled"
    assert err.error_type == "CancelledError"


@pytest.mark.asyncio
async def test_cancelled_write_logs_terminal_and_propagates(scpi_capture):
    entered = asyncio.Event()

    class _CancelledWrite(_Driver):
        def _do_write(self, cmd: str, **kwargs: Any):
            return self._block()

        async def _block(self) -> None:
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(_CancelledWrite()._write("WAIT"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    _assert_pair(scpi_capture.records, "ERR", "command")
    assert _direction(scpi_capture.records, "ERR")[0].result_type == "cancelled"


@pytest.mark.asyncio
async def test_timeout_is_logged_and_same_exception_object_propagates(scpi_capture):
    timeout = TimeoutError("slow transport")

    class _Timeout(_Driver):
        def _do_query(self, cmd: str, **kwargs: Any):
            return self._raise_later()

        async def _raise_later(self) -> str:
            await asyncio.sleep(0)
            raise timeout

    with pytest.raises(TimeoutError) as caught:
        await _Timeout()._query("SLOW?")
    assert caught.value is timeout
    _assert_pair(scpi_capture.records, "ERR", "query")
    assert _direction(scpi_capture.records, "ERR")[0].result_type == "timeout"


def test_empty_whitespace_and_not_ready_remain_distinct(scpi_capture):
    for value in ("", "   \n", "not ready"):
        _Driver(response=value)._query("STATE?")
    assert [r.result_type for r in _direction(scpi_capture.records, "RX")] == [
        "empty_response",
        "whitespace_response",
        "not_ready",
    ]


def test_scpi_log_redacts_imsi_and_authentication_secrets_only_in_evidence(
    scpi_capture,
):
    imsi = "001010000000001"
    ki = "0123456789ABCDEF0123456789ABCDEF"
    opc = "FEDCBA9876543210FEDCBA9876543210"
    command = f"BSE:CONF:IMSI {imsi};AUTH:KI {ki};AUTH:OPC {opc}"
    response = f'{{"imsi":"{imsi}","ki":"{ki}","opc":"{opc}"}}'
    driver = _Driver(response=response)

    assert driver._query(command) == response, "脱敏不得改写真正发给仪器的值"
    assert driver.seen == [command]
    for record in scpi_capture.records:
        rendered = " ".join(
            str(getattr(record, name, ""))
            for name in ("msg", "command", "query", "response")
        )
        assert imsi not in rendered
        assert ki not in rendered
        assert opc not in rendered
        assert "0001" in rendered
        assert "[REDACTED]" in rendered


def test_bare_imsi_query_response_is_masked_but_returned_unchanged(scpi_capture):
    imsi = "001010000000001"
    driver = _Driver(response=imsi)

    assert driver._query("BSE:UE:IMSI?") == imsi
    rx = _direction(scpi_capture.records, "RX")[0]
    rendered = f"{rx.getMessage()} {rx.response}"
    assert imsi not in rendered
    assert "***********0001" in rendered


@pytest.mark.parametrize(
    "command",
    ("BSE:AUTH:KI?", "BSE:AUTH:OPC?", "BSE:AUTHENTICATION:KEY?"),
)
def test_bare_auth_secret_query_response_is_fully_redacted(
    scpi_capture, command
):
    ki = "0123456789ABCDEF0123456789ABCDEF"
    driver = _Driver(response=ki)

    assert driver._query(command) == ki
    rx = _direction(scpi_capture.records, "RX")[0]
    rendered = f"{rx.getMessage()} {rx.response}"
    assert ki not in rendered
    assert "[REDACTED]" in rendered


@pytest.mark.parametrize(
    "command",
    ("BSE:AUTH:KI?", "BSE:AUTH:OPC?", "BSE:AUTHENTICATION:KEY?"),
)
def test_bare_auth_secret_error_is_redacted_but_exception_is_unchanged(
    scpi_capture, command
):
    ki = "0123456789ABCDEF0123456789ABCDEF"
    original = ValueError(ki)

    with pytest.raises(ValueError) as caught:
        _Driver(error=original)._query(command)

    assert caught.value is original
    err = _direction(scpi_capture.records, "ERR")[0]
    assert ki not in err.getMessage()
    assert "[REDACTED]" in err.getMessage()


def test_bare_auth_secret_write_error_is_redacted_but_exception_is_unchanged(
    scpi_capture,
):
    ki = "0123456789ABCDEF0123456789ABCDEF"
    original = ValueError(ki)

    with pytest.raises(ValueError) as caught:
        _Driver(error=original)._write(f"BSE:AUTH:KI {ki}")

    assert caught.value is original
    err = _direction(scpi_capture.records, "ERR")[0]
    assert ki not in err.getMessage()
    assert "[REDACTED]" in err.getMessage()


def test_standard_opc_response_is_not_misclassified_as_authentication_secret(
    scpi_capture,
):
    assert _Driver(response="1")._query("*OPC?") == "1"
    rx = _direction(scpi_capture.records, "RX")[0]
    assert rx.response == "1"
    assert rx.getMessage() == "RX: 1"


def test_scpi_error_detail_is_redacted_but_original_exception_propagates(
    scpi_capture,
):
    secret = "0123456789ABCDEF0123456789ABCDEF"
    original = ValueError(f"AUTH:KI {secret}")
    with pytest.raises(ValueError) as caught:
        _Driver(error=original)._query("AUTH:STATUS?")

    assert caught.value is original
    err = _direction(scpi_capture.records, "ERR")[0]
    assert secret not in err.getMessage()
    assert "[REDACTED]" in err.getMessage()


@pytest.mark.asyncio
async def test_native_async_cancelled_before_start_emits_no_false_tx_intent(
    scpi_capture,
):
    started: list[str] = []

    class _NativeAsync(_Driver):
        async def _do_query(self, cmd: str, **kwargs: Any) -> str:
            started.append(cmd)
            return "never"

        async def _do_write(self, cmd: str, **kwargs: Any) -> None:
            started.append(cmd)

    driver = _NativeAsync()
    for awaitable in (driver._query("NEVER?"), driver._write("NEVER")):
        task = asyncio.create_task(awaitable)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert started == []
    assert scpi_capture.records == []


@pytest.mark.asyncio
async def test_native_async_success_forwards_kwargs_and_pairs_query_write(
    scpi_capture,
):
    seen: list[tuple[str, dict[str, Any]]] = []

    class _NativeAsync(_Driver):
        async def _do_query(self, cmd: str, **kwargs: Any) -> str:
            seen.append((cmd, kwargs))
            return "VALUE"

        async def _do_write(self, cmd: str, **kwargs: Any) -> None:
            seen.append((cmd, kwargs))

    driver = _NativeAsync()
    assert await driver._query("READ?", timeout=4321, note_success=False) == "VALUE"
    await driver._write("SET", timeout=8765)

    assert seen == [
        ("READ?", {"timeout": 4321, "note_success": False}),
        ("SET", {"timeout": 8765}),
    ]
    grouped: dict[str, list[str]] = {}
    for record in scpi_capture.records:
        grouped.setdefault(record.exchange_id, []).append(record.direction)
    assert sorted(grouped.values()) == [["TX", "OK"], ["TX", "RX"]]


@pytest.mark.asyncio
async def test_native_async_running_cancel_and_error_preserve_terminal_evidence(
    scpi_capture,
):
    entered = asyncio.Event()
    original = RuntimeError("transport failed")

    class _NativeAsync(_Driver):
        async def _do_query(self, cmd: str, **kwargs: Any) -> str:
            entered.set()
            await asyncio.Event().wait()
            return "never"

        async def _do_write(self, cmd: str, **kwargs: Any) -> None:
            raise original

    driver = _NativeAsync()
    task = asyncio.create_task(driver._query("WAIT?"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(RuntimeError) as caught:
        await driver._write("FAIL")
    assert caught.value is original

    errors = _direction(scpi_capture.records, "ERR")
    assert [record.result_type for record in errors] == ["cancelled", "exception"]
    assert all(record.exchange_id for record in errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("driver_cls", (RealPropsimF64Driver, RealPropsimFs16Driver))
async def test_real_propsim_native_async_path_pairs_and_forwards_timeout(
    scpi_capture, driver_cls
):
    class _Visa:
        timeout = 5000

        def __init__(self):
            self.calls: list[str] = []

        def query(self, cmd: str) -> str:
            self.calls.append(cmd)
            return "1"

    visa = _Visa()
    driver = driver_cls(f"{driver_cls.__name__}-evidence", {})
    driver._visa_resource = visa

    assert await driver._query("*OPC?", timeout=4321) == "1"
    assert visa.calls == ["*OPC?"]
    _assert_pair(scpi_capture.records, "RX", "query")
    assert _direction(scpi_capture.records, "RX")[0].response == "1"


@pytest.mark.asyncio
async def test_scpi_terminal_log_copies_are_redacted_but_results_remain_raw(
    scpi_capture,
):
    secret = "0123456789ABCDEF0123456789ABCDEF"
    logger = logging.getLogger("app.hal.scpi")

    class _Hal:
        def _query(self, _cmd: str) -> str:
            return secret

    hal_result = await _run_command_via_hal(
        _Hal(), "BSE:AUTH:OPC?", logger, "baseStation"
    )
    assert hal_result.response == secret
    rendered = " ".join(record.getMessage() for record in scpi_capture.records)
    assert secret not in rendered
    assert "[REDACTED]" in rendered

    scpi_capture.records.clear()

    class _Socket:
        def sendall(self, _data: bytes) -> None:
            return None

        def recv(self, _size: int) -> bytes:
            return secret.encode()

    socket_result = _send_scpi_command(
        _Socket(), "BSE:AUTH:KI?", logger, "baseStation"
    )
    assert socket_result.response == secret
    rendered = " ".join(record.getMessage() for record in scpi_capture.records)
    assert secret not in rendered
    assert "[REDACTED]" in rendered


@pytest.mark.asyncio
async def test_driver_reconnect_warnings_never_repeat_secret_commands():
    secret = "0123456789ABCDEF0123456789ABCDEF"
    command = f"BSE:AUTH:KI {secret}"
    conn_lost = pyvisa.errors.VisaIOError(
        0xBFFF00B5 - (1 << 32)
    )

    class _LostVisa:
        timeout = 5000

        def write(self, _cmd: str) -> None:
            raise conn_lost

    uxm = RealUxmDriver("uxm-secret-log", {})
    uxm._visa_session = _LostVisa()
    f64 = RealPropsimF64Driver("f64-secret-log", {})
    f64._visa_resource = _LostVisa()
    fs16 = RealPropsimFs16Driver("fs16-secret-log", {})
    fs16._visa_resource = _LostVisa()

    handler = _RecordingHandler()
    driver_loggers = [
        logging.getLogger("app.hal.uxm_base_station"),
        logging.getLogger("app.hal.propsim_f64"),
        logging.getLogger("app.hal.propsim_fs16"),
    ]
    previous = [(item.level, item.disabled) for item in driver_loggers]
    for item in driver_loggers:
        item.addHandler(handler)
        item.setLevel(logging.WARNING)
        item.disabled = False
    try:
        with pytest.raises(pyvisa.errors.VisaIOError):
            uxm._do_write(command)
        with pytest.raises(pyvisa.errors.VisaIOError):
            await f64._do_write_unlocked(command)
        with pytest.raises(pyvisa.errors.VisaIOError):
            await fs16._do_write_unlocked(command)
    finally:
        for item, (level, disabled) in zip(driver_loggers, previous):
            item.removeHandler(handler)
            item.setLevel(level)
            item.disabled = disabled

    rendered = " ".join(record.getMessage() for record in handler.records)
    assert secret not in rendered
    assert rendered.count("[REDACTED]") >= 3


@pytest.mark.parametrize(
    ("raw", "secrets", "visible_hint"),
    [
        (
            '{"ue_imsi":"001010000000001"}',
            ("001010000000001",),
            "0001",
        ),
        (
            '{"auth_ki":"0123456789ABCDEF0123456789ABCDEF"}',
            ("0123456789ABCDEF0123456789ABCDEF",),
            "[REDACTED]",
        ),
        (
            '{"password":"two words here"}',
            ("two", "words", "here"),
            "[REDACTED]",
        ),
    ],
)
def test_redactor_covers_prefixed_keys_and_complete_quoted_values(
    raw, secrets, visible_hint
):
    safe = redact_instrument_log_text(raw)
    assert all(secret not in safe for secret in secrets)
    assert visible_hint in safe


def test_json_formatter_preserves_exchange_contract_fields(scpi_capture):
    _Driver(response="READY")._query("STATE?")
    context_filter = ContextFilter()
    formatter = JsonFormatter()

    payloads = []
    for record in scpi_capture.records:
        assert context_filter.filter(record)
        payloads.append(json.loads(formatter.format(record)))

    assert [item["direction"] for item in payloads] == ["TX", "RX"]
    assert payloads[0]["exchange_id"] == payloads[1]["exchange_id"]
    for item in payloads:
        assert item["instrument_id"] == "stub-evidence"
        assert item["operation"] == "query"
        assert item["command"] == "STATE?"
        assert item["result_type"] in {"intent", "response"}


class _Writer:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.sent.append(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return False


class _Reader:
    def __init__(self, value: bytes | None = b"%12.5\n") -> None:
        self.value = value
        self.entered = asyncio.Event()

    async def readline(self) -> bytes:
        self.entered.set()
        if self.value is None:
            await asyncio.Event().wait()
        assert self.value is not None
        return self.value


def _aerotech(reader: _Reader, *, timeout_s: float = 1.0):
    driver = RealAerotechDriver(
        "aero-evidence", {"ip": "127.0.0.1", "timeout_s": timeout_s}
    )
    driver._reader = reader
    driver._writer = _Writer()
    driver._axes_present = ["X"]
    return driver


@pytest.mark.asyncio
async def test_aerotech_socket_path_uses_same_exchange_contract(scpi_capture):
    assert await _aerotech(_Reader())._send("PFBK(X)") == "12.5"
    _assert_pair(scpi_capture.records, "RX", "query")
    assert _direction(scpi_capture.records, "RX")[0].result_type == "response"


def test_aerotech_axisfault_is_classified_as_query():
    assert RealAerotechDriver._aerobasic_operation("AXISFAULT(X)") == "query"


@pytest.mark.asyncio
async def test_aerotech_device_rejection_is_distinct_from_transport_error(scpi_capture):
    with pytest.raises(AerotechError):
        await _aerotech(_Reader(b"!123\n"))._send("MOVEABS X 90")
    _assert_pair(scpi_capture.records, "RX", "command")
    assert _direction(scpi_capture.records, "RX")[0].result_type == "device_rejected"
    assert not _direction(scpi_capture.records, "ERR")


@pytest.mark.asyncio
async def test_aerotech_empty_whitespace_and_not_ready_are_not_conflated(
    scpi_capture,
):
    with pytest.raises(ConnectionResetError):
        await _aerotech(_Reader(b""))._tx_rx("PFBK(X)")
    assert _direction(scpi_capture.records, "ERR")[0].result_type == "exception"

    scpi_capture.records.clear()
    assert await _aerotech(_Reader(b"   \n"))._send("PFBK(X)") == ""
    whitespace = _direction(scpi_capture.records, "RX")[0]
    assert whitespace.result_type == "whitespace_response"
    assert whitespace.resp_len == 4

    scpi_capture.records.clear()
    assert await _aerotech(_Reader(b"not ready\n"))._send("PFBK(X)") == "not ready"
    assert _direction(scpi_capture.records, "RX")[0].result_type == "not_ready"


@pytest.mark.asyncio
async def test_aerotech_cancelled_and_timeout_leave_terminal_evidence(scpi_capture):
    reader = _Reader(None)
    task = asyncio.create_task(_aerotech(reader)._send("PFBK(X)"))
    await reader.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    _assert_pair(scpi_capture.records, "ERR", "query")
    assert _direction(scpi_capture.records, "ERR")[0].result_type == "cancelled"

    scpi_capture.records.clear()
    with pytest.raises(TimeoutError):
        await _aerotech(_Reader(None), timeout_s=0.001)._send("PFBK(X)")
    _assert_pair(scpi_capture.records, "ERR", "query")
    assert _direction(scpi_capture.records, "ERR")[0].result_type == "timeout"


@pytest.mark.asyncio
async def test_aerotech_reconnect_cancel_closes_half_initialized_transport(
    monkeypatch,
):
    entered = asyncio.Event()
    writer = _Writer()
    writer.closed = False
    writer.close = lambda: setattr(writer, "closed", True)
    driver = _aerotech(_Reader())
    driver._reader = None
    driver._writer = None

    async def fake_open_connection(_host, _port):
        return _Reader(), writer

    async def blocked_handshake(_cmd):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)
    monkeypatch.setattr(driver, "_enable_tcp_keepalive", lambda _writer: None)
    monkeypatch.setattr(driver, "_tx_rx", blocked_handshake)

    task = asyncio.create_task(driver._silent_reconnect())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert writer.closed is True
    assert driver._reader is None
    assert driver._writer is None


@pytest.mark.parametrize(
    ("configured_days", "expected_scpi_days"),
    [(0, 1), (7, 7), (30, 30), (90, 30)],
)
def test_scpi_file_retention_is_capped_at_30_days(
    monkeypatch, tmp_path, configured_days, expected_scpi_days
):
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        logging_config.logging.config,
        "dictConfig",
        lambda config: captured.update(config),
    )
    logging_config.setup_logging(
        log_dir=str(tmp_path),
        log_retention_days=configured_days,
        db_log_enabled=False,
    )
    assert (
        captured["handlers"]["file_scpi"]["backupCount"]
        == expected_scpi_days
    )


def test_scpi_file_retention_defaults_to_30_days():
    assert (
        inspect.signature(logging_config.setup_logging)
        .parameters["log_retention_days"]
        .default
        == 30
    )
