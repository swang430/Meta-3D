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


class TestExecutionLogRetention:
    """#303 外审 P1：`exec-<id>.log` 收的是 `app.hal.scpi.*` 传播来的原始往返，
    但它手写 `open("a")`、不走 `TimedRotatingFileHandler` 的 `backupCount`，
    于是绕过了 `setup_logging` 里那条「独立 SCPI 文件不得保留超过 30 个日轮转
    归档」的禁令 —— 高敏往返无限期留在一个能被 `GET /system-logs/files`
    列出的目录里。

    ⚠ 这三条是**行为门**：造出过期/新鲜/正在写三种文件，断言可观察后果
    （谁被删、谁留下），不是断言"代码里有 purge 这个词"。
    """

    def test_expired_execution_logs_are_purged_on_init(self, tmp_path):
        """变异：删掉 `__init__` 末尾的 `self.purge_expired()` → 本条红。"""
        import os
        import time as _time

        stale = tmp_path / "exec-0000stale.log"
        stale.write_text("SCPI: 高敏往返\n", encoding="utf-8")
        old = _time.time() - 31 * 86400
        os.utime(stale, (old, old))

        fresh = tmp_path / "exec-0000fresh.log"
        fresh.write_text("SCPI: 今天的\n", encoding="utf-8")

        logging_config.ExecutionFileHandler(str(tmp_path), retention_days=30)

        assert not stale.exists(), (
            "31 天前的执行日志没被清掉 —— 原始 SCPI 往返会无限期堆在可枚举目录里")
        assert fresh.exists(), "把没过期的执行日志也删了"

    def test_retention_follows_the_scpi_cap_not_the_global_policy(self, tmp_path):
        """留存上限必须**跟 scpi.log 同源**。

        变异：把 dictConfig 里的 `retention_days` 换成 `log_retention_days`
        （全局策略，可被放宽到 >30）→ 本条红。
        """
        import inspect

        src = inspect.getsource(logging_config.setup_logging)
        exec_block = src[src.index('"file_execution"'):]
        exec_block = exec_block[:exec_block.index("},")]
        assert "scpi_retention_days" in exec_block, (
            "执行日志的留存上限没接在 scpi_retention_days 上 —— "
            "全局策略一放宽，高敏往返就又无限期了")
        assert "log_retention_days" not in exec_block

    def test_active_execution_file_is_never_purged(self, tmp_path):
        """正在写的执行不能被删 —— 删了会留下悬空句柄。

        变异：去掉 `purge_expired` 里那个 `in self._streams` 的跳过 → 本条红。
        """
        import os
        import time as _time

        handler = logging_config.ExecutionFileHandler(str(tmp_path), retention_days=30)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(ContextFilter())
        exec_id = "activeexec1"
        _emit(handler, exec_id, "正在写")

        active = tmp_path / f"exec-{exec_id}.log"
        assert active.exists()
        old = _time.time() - 99 * 86400
        os.utime(active, (old, old))

        purged = handler.purge_expired()

        assert active.exists(), "把正在写的执行日志删了 —— 句柄会悬空"
        assert purged == 0
        handler.close()

    def test_retention_is_enforced_after_startup_not_only_at_init(self, tmp_path):
        """#303 R2 P1：常驻进程跑过 retention_days 后，启动时没过期的文件
        此后无人检查 —— 30 天上限被静默突破。

        变异：删掉 `close_execution` 末尾的 `purge_expired()` → 本条红。
        """
        import os
        import time as _time

        handler = logging_config.ExecutionFileHandler(str(tmp_path), retention_days=30)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(ContextFilter())

        # 启动时它还新鲜（没被 __init__ 那次清掉），之后才过期
        survivor = tmp_path / "exec-0000later.log"
        survivor.write_text("SCPI: 启动后才到期\n", encoding="utf-8")

        _emit(handler, "someexec99", "触发一次执行")
        old = _time.time() - 31 * 86400
        os.utime(survivor, (old, old))

        handler.close_execution("someexec99")

        assert not survivor.exists(), (
            "执行收尾时没复查留存 —— 常驻进程里到期文件永远不会被清")
        handler.close()

    def test_cleanup_failure_is_reported_outside_handleError(self, tmp_path, caplog):
        """#303 R2 P2：`handleError` 在 `raiseExceptions=False`（生产常见）下
        按标准库契约静默返回，告警根本不会出现。

        变异：把 `_module_logger.warning(...)` 换回 `self.handleError(...)`
        → 本条在 `raiseExceptions=False` 下红。
        """
        import logging as _logging
        import os
        import time as _time
        from unittest.mock import patch

        doomed = tmp_path / "exec-0000doomed.log"
        doomed.write_text("SCPI: 删不掉\n", encoding="utf-8")
        old = _time.time() - 31 * 86400
        os.utime(doomed, (old, old))

        prev = _logging.raiseExceptions
        _logging.raiseExceptions = False        # 复刻生产配置
        try:
            with patch.object(logging_config.Path, "unlink",
                              side_effect=OSError("只读文件系统")):
                with caplog.at_level(_logging.WARNING,
                                     logger="app.core.logging_config"):
                    logging_config.ExecutionFileHandler(
                        str(tmp_path), retention_days=30)
        finally:
            _logging.raiseExceptions = prev

        msgs = " | ".join(r.getMessage() for r in caplog.records)
        assert "留存清理失败" in msgs, (
            "生产配置下清理失败无声无息 —— 过期高敏日志留在盘上且运维不知道")
        assert doomed.exists(), "夹具前提错了：本例要的是删除失败"
