"""P1-40: 常驻 INFO 基线与按 execution_id 分文件。"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import pytest

from app.core import logging_config
from app.core.logging_config import ContextFilter, JsonFormatter, current_execution_id


def _emit(
    handler: logging.Handler,
    execution_id: str,
    message: str,
    *,
    logger_name: str | None = None,
) -> None:
    logger = logging.Logger(
        logger_name or f"test.execution.{execution_id}",
        level=logging.DEBUG,
    )
    logger.addHandler(handler)
    token = current_execution_id.set(execution_id)
    try:
        logger.debug(message)
    finally:
        current_execution_id.reset(token)
        logger.removeHandler(handler)


def test_setup_uses_info_baseline_and_execution_handler(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(logging_config.logging.config, "dictConfig", captured.update)

    logging_config.setup_logging(
        log_dir=str(tmp_path),
        scpi_enabled=False,
        db_log_enabled=False,
    )

    assert captured["handlers"]["file_app"]["level"] == "INFO"
    assert captured["handlers"]["file_execution"]["level"] == "DEBUG"
    assert captured["loggers"][""]["handlers"] == [
        "console", "file_app", "file_execution",
    ]


def test_execution_handler_routes_debug_to_separate_flat_files(tmp_path):
    handler = logging_config.ExecutionFileHandler(str(tmp_path))
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    first = str(uuid4())
    second = str(uuid4())

    _emit(handler, first, "first-debug")
    _emit(handler, second, "second-debug")
    _emit(handler, "-", "idle-debug")
    handler.close()

    first_path = tmp_path / f"exec-{first}.log"
    second_path = tmp_path / f"exec-{second}.log"
    assert first_path.is_file()
    assert second_path.is_file()
    assert not (tmp_path / "exec--.log").exists()
    assert json.loads(first_path.read_text(encoding="utf-8"))["msg"] == "first-debug"
    assert json.loads(second_path.read_text(encoding="utf-8"))["msg"] == "second-debug"


def test_execution_handler_rejects_unsafe_identity(tmp_path):
    handler = logging_config.ExecutionFileHandler(str(tmp_path))
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())

    _emit(handler, "../../escape", "must-not-write")
    handler.close()

    assert list(tmp_path.iterdir()) == []


def test_close_execution_releases_only_target_stream(tmp_path):
    handler = logging_config.ExecutionFileHandler(str(tmp_path))
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    first = str(uuid4())
    second = str(uuid4())
    _emit(handler, first, "one")
    _emit(handler, second, "two")

    handler.close_execution(first)

    assert first not in handler._streams
    assert second in handler._streams
    handler.close()


def test_duplicate_burst_is_suppressed_then_summarized(tmp_path):
    now = [10.0]
    handler = logging_config.ExecutionFileHandler(
        str(tmp_path),
        repeat_limit=2,
        repeat_window_seconds=1.0,
        clock=lambda: now[0],
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    execution_id = str(uuid4())

    for _ in range(5):
        _emit(handler, execution_id, "same-message", logger_name="app.repeat")
    now[0] = 12.0
    _emit(handler, execution_id, "same-message", logger_name="app.repeat")
    handler.close()

    rows = [
        json.loads(line)
        for line in (tmp_path / f"exec-{execution_id}.log").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["msg"] for row in rows] == [
        "same-message",
        "same-message",
        "… same message suppressed x3",
        "same-message",
    ]
    assert rows[2]["suppressed_count"] == 3
    assert rows[2]["suppressed_message"] == "same-message"


def test_suppression_buckets_do_not_cross_execution_or_message(tmp_path):
    handler = logging_config.ExecutionFileHandler(
        str(tmp_path), repeat_limit=1, repeat_window_seconds=60,
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    first = str(uuid4())
    second = str(uuid4())

    _emit(handler, first, "same", logger_name="app.repeat")
    _emit(handler, first, "different", logger_name="app.repeat")
    _emit(handler, second, "same", logger_name="app.repeat")
    handler.close()

    first_rows = (tmp_path / f"exec-{first}.log").read_text(encoding="utf-8")
    second_rows = (tmp_path / f"exec-{second}.log").read_text(encoding="utf-8")
    assert "same" in first_rows and "different" in first_rows
    assert "same" in second_rows


def test_scpi_exchange_identity_is_never_suppressed(tmp_path):
    handler = logging_config.ExecutionFileHandler(
        str(tmp_path), repeat_limit=1, repeat_window_seconds=60,
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    execution_id = str(uuid4())
    logger = logging.Logger("app.hal.scpi.identity", level=logging.DEBUG)
    logger.addHandler(handler)
    token = current_execution_id.set(execution_id)
    try:
        for exchange_id in ("exchange-a", "exchange-b"):
            logger.debug(
                "TX: *OPC?",
                extra={"exchange_id": exchange_id, "instrument_id": "uxm"},
            )
    finally:
        current_execution_id.reset(token)
        logger.removeHandler(handler)
        handler.close()

    rows = [
        json.loads(line)
        for line in (tmp_path / f"exec-{execution_id}.log").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["exchange_id"] for row in rows] == ["exchange-a", "exchange-b"]
    assert all("suppressed_count" not in row for row in rows)


def test_scpi_file_uses_same_suppression_handler(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(logging_config.logging.config, "dictConfig", captured.update)

    logging_config.setup_logging(
        log_dir=str(tmp_path), scpi_enabled=True, db_log_enabled=False,
    )

    assert captured["handlers"]["file_scpi"]["()"] is logging_config.SuppressingTimedRotatingFileHandler


def test_close_execution_drains_idle_scpi_suppression_summary(tmp_path):
    path = tmp_path / "scpi.log"
    handler = logging_config.SuppressingTimedRotatingFileHandler(
        path,
        when="midnight",
        repeat_limit=1,
        repeat_window_seconds=60,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    logger = logging.getLogger("app.hal.scpi")
    old_level = logger.level
    old_disabled = logger.disabled
    old_propagate = logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.disabled = False
    logger.propagate = False
    logger.addHandler(handler)
    execution_id = str(uuid4())
    token = current_execution_id.set(execution_id)
    try:
        for _ in range(4):
            logger.debug("TX: repeated")
        # No later record and no process shutdown: execution close itself must
        # make the suppressed-count evidence visible in the global SCPI file.
        logging_config.close_execution_log(execution_id)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert [row["msg"] for row in rows] == [
            "TX: repeated",
            "… same message suppressed x3",
        ]
    finally:
        current_execution_id.reset(token)
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.disabled = old_disabled
        logger.propagate = old_propagate
        handler.close()


@pytest.mark.asyncio
async def test_case_runner_closes_execution_log(monkeypatch):
    from app.services import test_case_runner

    execution_id = uuid4()
    closed: list[str] = []

    class _Db:
        def close(self):
            return None

    monkeypatch.setattr(test_case_runner, "SessionLocal", _Db)
    monkeypatch.setattr(test_case_runner, "_run_case_loop", lambda db, eid: _done())
    monkeypatch.setattr(test_case_runner, "close_execution_log", closed.append)

    await test_case_runner._run_case(execution_id)

    assert closed == [str(execution_id)]


@pytest.mark.asyncio
async def test_case_runner_log_close_failure_does_not_leak_db(monkeypatch):
    from app.services import test_case_runner

    execution_id = uuid4()
    state = {"db_closed": False}

    class _Db:
        def close(self):
            state["db_closed"] = True

    monkeypatch.setattr(test_case_runner, "SessionLocal", _Db)
    monkeypatch.setattr(test_case_runner, "_run_case_loop", lambda db, eid: _done())
    monkeypatch.setattr(
        test_case_runner,
        "close_execution_log",
        lambda _execution_id: (_ for _ in ()).throw(OSError("disk unavailable")),
    )

    await test_case_runner._run_case(execution_id)

    assert state["db_closed"] is True


async def _done():
    return None
