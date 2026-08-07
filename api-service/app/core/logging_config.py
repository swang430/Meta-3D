"""
MIMO-First 集中式日志配置模块

四路输出架构:
  1. Console  — 彩色人类可读格式 (开发/运维)
  2. app.log  — JSON 结构化按天轮转 (AI debug / 审计)
  3. scpi.log — SCPI 仪器通信专用日志 (测试可追溯性)
  4. db.log   — 数据库 SQL 查询日志 (联调/性能调优)

通过 contextvars 实现 session_id / instrument_id 的自动注入,
无需修改现有 486 个 log 调用点。

Usage:
    # main.py 启动时调用一次
    from app.core.logging_config import setup_logging
    setup_logging(debug=True)

    # Commissioning 引擎入口设置会话上下文
    from app.core.logging_config import current_session_id
    current_session_id.set("a1b2c3d4")
"""

import contextvars
import copy
import logging
import logging.config
import logging.handlers
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

# ============================================================
# 1. Context Variables — 自动注入到每条日志
# ============================================================

current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "session_id", default="-"
)
current_instrument_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "instrument_id", default="-"
)

# P1-36：一次**测试执行**的关联 id。跟 `session_id`（每请求）刻意分开成
# 两个字段 —— 它们是**两个不同的生命周期**：
#   · 一次执行跨多个请求（发起、查询、取消各是一次请求）；
#   · 也可能完全不在请求里（`_run_case` 跑在后台任务上）。
# 复用同一个键会让"这次执行"与"这次请求"互相覆盖，两条链都串不成。
current_execution_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "execution_id", default="-"
)


class ContextFilter(logging.Filter):
    """
    将 contextvars 中的 session_id / instrument_id / hal_mode
    注入到每条 LogRecord，供 Formatter 使用。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = current_session_id.get("-")  # type: ignore[attr-defined]
        record.execution_id = current_execution_id.get("-")  # type: ignore[attr-defined]
        # P1-30 收窄：contextvar 只做**兜底**，不得覆盖调用方通过 extra= 显式
        # 给出的值。原实现无条件覆盖 —— HAL 层 _log_scpi_* 明明传了
        # extra={"instrument_id": self.instrument_id}，却在这里被重写成
        # contextvar 默认值 "-"（SCPI 路径上没有任何地方 set 过它）。
        # **P1-30 修复前**实测：当时归档的全部 759,894 行 SCPI 日志里
        # instrument_id 恒为 "-"（100%），仪器身份只在 logger 名
        # (app.hal.scpi.<id>) 里侥幸留存。修复后新写入的行带真实 id ——
        # 这句话描述的是历史观测，不是现在时的不变量。
        # ⚠ session_id 保持原样：全仓无任何 extra= 传 session_id，没有冲突，
        #   不顺手改（改了也观察不到差别）。
        if not hasattr(record, "instrument_id"):
            record.instrument_id = current_instrument_id.get("-")  # type: ignore[attr-defined]
        # 注入当前 HAL 全局模式 (mock/real)
        try:
            from app.services.instrument_hal_service import get_hal_service
            record.hal_mode = get_hal_service().mode.value  # type: ignore[attr-defined]
        except Exception:
            record.hal_mode = "-"  # type: ignore[attr-defined]
        return True


class ExcludeLoggerPrefixesFilter(logging.Filter):
    """让专用高敏日志保留在自己的文件，同时仍可传播到控制台。"""

    def __init__(self, prefixes: tuple[str, ...] | list[str]) -> None:
        super().__init__()
        self._prefixes = tuple(prefix.rstrip(".") for prefix in prefixes)

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(
            record.name == prefix or record.name.startswith(f"{prefix}.")
            for prefix in self._prefixes
        )


# ============================================================
# 2. JSON Formatter (无外部依赖的轻量实现)
# ============================================================

class JsonFormatter(logging.Formatter):
    """
    每行一个 JSON 对象的日志格式化器。
    
    不依赖 python-json-logger，使用标准库的 json 模块。
    输出格式:
      {"ts": "...", "level": "...", "logger": "...", 
       "session_id": "...", "instrument_id": "...",
       "msg": "...", ...extra_fields}
    """

    def format(self, record: logging.LogRecord) -> str:
        import json

        local_dt = datetime.fromtimestamp(record.created).astimezone()
        # ISO 8601 本地时间 + 时区偏移 (e.g. 2026-04-24T17:51:21.123+08:00)
        tz_offset = local_dt.strftime("%z")  # e.g. "+0800"
        ts = local_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + tz_offset[:3] + ":" + tz_offset[3:]

        log_entry = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "hal_mode": getattr(record, "hal_mode", "-"),
            "session_id": getattr(record, "session_id", "-"),
            "execution_id": getattr(record, "execution_id", "-"),
            "instrument_id": getattr(record, "instrument_id", "-"),
            "msg": record.getMessage(),
        }

        # 保留 extra 字段 (如 direction, query 等)
        standard_keys = {
            "name", "msg", "args", "created", "relativeCreated",
            "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "pathname", "filename", "module", "levelno", "levelname",
            "message", "msecs", "processName", "process", "threadName",
            "thread", "taskName", "session_id", "instrument_id", "hal_mode",
            "execution_id",
        }
        for key, value in record.__dict__.items():
            if key not in standard_keys and not key.startswith("_"):
                log_entry[key] = value

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


@dataclass
class _RepeatBucket:
    started_at: float
    emitted: int
    suppressed: int
    sample: logging.LogRecord


class _DuplicateBurstLimiter:
    """限制短窗口内的完全相同日志，并保留可审计的抑制摘要。"""

    def __init__(
        self,
        repeat_limit: int = 100,
        repeat_window_seconds: float = 1.0,
        clock=time.monotonic,
        max_buckets: int = 2048,
    ) -> None:
        self.repeat_limit = max(1, int(repeat_limit))
        self.repeat_window_seconds = max(0.001, float(repeat_window_seconds))
        self.clock = clock
        self.max_buckets = max(1, int(max_buckets))
        self._buckets: dict[tuple[str, str, str, str], _RepeatBucket] = {}

    @staticmethod
    def _key(record: logging.LogRecord) -> tuple[str, str, str, str]:
        return (
            str(getattr(record, "execution_id", "-")),
            str(getattr(record, "instrument_id", "-")),
            record.name,
            record.getMessage(),
        )

    @staticmethod
    def _summary(bucket: _RepeatBucket) -> logging.LogRecord | None:
        if bucket.suppressed <= 0:
            return None
        record = copy.copy(bucket.sample)
        original_message = bucket.sample.getMessage()
        record.msg = f"… same message suppressed x{bucket.suppressed}"
        record.args = ()
        record.suppressed_count = bucket.suppressed  # type: ignore[attr-defined]
        record.suppressed_message = original_message  # type: ignore[attr-defined]
        return record

    def _expire(self, now: float) -> list[logging.LogRecord]:
        summaries: list[logging.LogRecord] = []
        expired = [
            key for key, bucket in self._buckets.items()
            if now - bucket.started_at >= self.repeat_window_seconds
        ]
        for key in expired:
            summary = self._summary(self._buckets.pop(key))
            if summary is not None:
                summaries.append(summary)
        return summaries

    def process(self, record: logging.LogRecord) -> list[logging.LogRecord]:
        now = self.clock()
        output = self._expire(now)
        # Raw SCPI evidence has a unique exchange identity referenced by the
        # persisted evidence model. Folding it by rendered text would make
        # those references unresolvable and copy the first ID onto a summary.
        # Noise without an evidence identity remains eligible for suppression.
        if getattr(record, "exchange_id", None):
            output.append(record)
            return output
        key = self._key(record)
        bucket = self._buckets.get(key)

        if bucket is None:
            if len(self._buckets) >= self.max_buckets:
                oldest_key = min(
                    self._buckets,
                    key=lambda item: self._buckets[item].started_at,
                )
                summary = self._summary(self._buckets.pop(oldest_key))
                if summary is not None:
                    output.append(summary)
            self._buckets[key] = _RepeatBucket(now, 1, 0, copy.copy(record))
            output.append(record)
        elif bucket.emitted < self.repeat_limit:
            bucket.emitted += 1
            output.append(record)
        else:
            bucket.suppressed += 1
        return output

    def drain(self, *, execution_id: str | None = None) -> list[logging.LogRecord]:
        summaries: list[logging.LogRecord] = []
        keys = [
            key for key in self._buckets
            if execution_id is None or key[0] == str(execution_id)
        ]
        for key in keys:
            summary = self._summary(self._buckets.pop(key))
            if summary is not None:
                summaries.append(summary)
        return summaries


class SuppressingTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """带重复突发抑制的按时轮转文件处理器。"""

    def __init__(
        self,
        *args,
        repeat_limit: int = 100,
        repeat_window_seconds: float = 1.0,
        clock=time.monotonic,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._repeat_limiter = _DuplicateBurstLimiter(
            repeat_limit=repeat_limit,
            repeat_window_seconds=repeat_window_seconds,
            clock=clock,
        )

    def emit(self, record: logging.LogRecord) -> None:
        for output_record in self._repeat_limiter.process(record):
            super().emit(output_record)

    def drain_execution(self, execution_id: str) -> None:
        """Persist pending suppression summaries for one completed execution."""
        self.acquire()
        try:
            for record in self._repeat_limiter.drain(execution_id=str(execution_id)):
                super().emit(record)
        finally:
            self.release()

    def close(self) -> None:
        self.acquire()
        try:
            for record in self._repeat_limiter.drain():
                super().emit(record)
            super().close()
        finally:
            self.release()


class ExecutionFileHandler(logging.Handler):
    """按 LogRecord.execution_id 将详细日志写入扁平执行文件。"""

    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

    def __init__(
        self,
        log_dir: str,
        encoding: str = "utf-8",
        repeat_limit: int = 100,
        repeat_window_seconds: float = 1.0,
        clock=time.monotonic,
    ) -> None:
        super().__init__(logging.DEBUG)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.encoding = encoding
        self._streams: dict[str, TextIO] = {}
        self._streams_lock = threading.RLock()
        self._repeat_limiter = _DuplicateBurstLimiter(
            repeat_limit=repeat_limit,
            repeat_window_seconds=repeat_window_seconds,
            clock=clock,
        )

    def _write_locked(self, record: logging.LogRecord) -> None:
        execution_id = str(getattr(record, "execution_id", "-"))
        stream = self._streams.get(execution_id)
        if stream is None:
            path = self.log_dir / f"exec-{execution_id}.log"
            stream = path.open("a", encoding=self.encoding, buffering=1)
            self._streams[execution_id] = stream
        stream.write(self.format(record) + "\n")
        stream.flush()

    def emit(self, record: logging.LogRecord) -> None:
        execution_id = str(getattr(record, "execution_id", "-"))
        if execution_id == "-" or not self._SAFE_ID.fullmatch(execution_id):
            return
        try:
            with self._streams_lock:
                for output_record in self._repeat_limiter.process(record):
                    self._write_locked(output_record)
        except Exception:
            self.handleError(record)

    def close_execution(self, execution_id: str) -> None:
        with self._streams_lock:
            for record in self._repeat_limiter.drain(execution_id=str(execution_id)):
                self._write_locked(record)
            stream = self._streams.pop(str(execution_id), None)
            if stream is not None:
                stream.flush()
                stream.close()

    def close(self) -> None:
        with self._streams_lock:
            for record in self._repeat_limiter.drain():
                self._write_locked(record)
            streams = list(self._streams.values())
            self._streams.clear()
            for stream in streams:
                stream.flush()
                stream.close()
        super().close()


def close_execution_log(execution_id: str) -> None:
    """关闭执行文件，并让共享 SCPI 文件立即写出该执行的抑制摘要。"""
    handlers = [
        *logging.getLogger().handlers,
        *logging.getLogger("app.hal.scpi").handlers,
    ]
    seen: set[int] = set()
    for handler in handlers:
        if id(handler) in seen:
            continue
        seen.add(id(handler))
        if isinstance(handler, ExecutionFileHandler):
            handler.close_execution(execution_id)
        elif isinstance(handler, SuppressingTimedRotatingFileHandler):
            handler.drain_execution(execution_id)


# ============================================================
# 3. 主配置函数
# ============================================================

def setup_logging(
    debug: bool = True,
    log_dir: Optional[str] = None,
    log_retention_days: int = 30,
    scpi_enabled: bool = True,
    db_log_enabled: bool = True,
) -> None:
    """
    初始化整个应用的日志系统。

    Args:
        debug: True → Console 输出 DEBUG; False → INFO
        log_dir: 日志文件目录 (默认 api-service/logs/)
        log_retention_days: 日志文件保留天数
        scpi_enabled: 是否启用 SCPI 专用日志文件
        db_log_enabled: 是否启用数据库 SQL 查询日志文件
    """

    # 确定日志目录
    if log_dir is None:
        # 默认放在 api-service/logs/
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    app_log_path = os.path.join(log_dir, "app.log")
    scpi_log_path = os.path.join(log_dir, "scpi.log")
    db_log_path = os.path.join(log_dir, "db.log")

    console_level = "DEBUG" if debug else "INFO"
    # P1-47A：原始仪器往返可能包含高敏现场信息，独立 SCPI 文件无论
    # 全局日志策略如何放宽，都不得保留超过 30 个日轮转归档。
    # TimedRotatingFileHandler 的 backupCount=0 语义是“永不删除归档”，不是
    # “保留零天”。对非正配置收窄为 1 天，避免高敏 SCPI 文件无限累积。
    scpi_retention_days = min(30, max(1, int(log_retention_days)))

    # ---- dictConfig 配置 ----
    config = {
        "version": 1,
        "disable_existing_loggers": False,  # 关键! 不禁用已有 logger
        "filters": {
            "context_filter": {
                "()": ContextFilter,
            },
            "exclude_scpi_from_app": {
                "()": ExcludeLoggerPrefixesFilter,
                "prefixes": ["app.hal.scpi"],
            },
        },
        "formatters": {
            "console": {
                "format": (
                    "%(asctime)s │ %(levelname)-8s │ "
                    "%(name)-40s │ %(message)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": JsonFormatter,
            },
        },
        "handlers": {
            # Handler 1: Console (彩色人类可读)
            "console": {
                "class": "logging.StreamHandler",
                "level": console_level,
                "formatter": "console",
                "filters": ["context_filter"],
                "stream": "ext://sys.stdout",
            },
            # Handler 2: app.log (JSON 结构化, 按天轮转)
            "file_app": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "level": "INFO",
                "formatter": "json",
                "filters": ["context_filter", "exclude_scpi_from_app"],
                "filename": app_log_path,
                "when": "midnight",
                "interval": 1,
                "backupCount": log_retention_days,
                "encoding": "utf-8",
            },
            # Handler 3: 执行期间的 DEBUG/SCPI 详情，按 execution_id 分文件。
            "file_execution": {
                "()": ExecutionFileHandler,
                "level": "DEBUG",
                "formatter": "json",
                "filters": ["context_filter"],
                "log_dir": log_dir,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # 根 logger: 所有日志的默认处理
            "": {
                "level": "DEBUG",
                "handlers": ["console", "file_app", "file_execution"],
            },
            # 抑制第三方库的过度日志
            "uvicorn": {"level": "INFO", "propagate": True},
            "uvicorn.access": {"level": "WARNING", "propagate": True},
            "httpx": {"level": "WARNING", "propagate": True},
            "httpcore": {"level": "WARNING", "propagate": True},
            "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
            # 数据库会话生命周期日志
            "app.db": {"level": "DEBUG", "propagate": True},
        },
    }

    # Handler 3 (可选): SCPI 专用日志
    if scpi_enabled:
        config["handlers"]["file_scpi"] = {
            "()": SuppressingTimedRotatingFileHandler,
            "level": "DEBUG",
            "formatter": "json",
            "filters": ["context_filter"],
            "filename": scpi_log_path,
            "when": "midnight",
            "interval": 1,
            "backupCount": scpi_retention_days,
            "encoding": "utf-8",
        }
        # app.hal.scpi 命名空间的日志 → 写入 scpi.log，并传播到控制台；
        # file_app 上的命名空间过滤器阻止同一高敏证据复制进长期 app.log。
        config["loggers"]["app.hal.scpi"] = {
            "level": "DEBUG",
            "handlers": ["file_scpi"],
            "propagate": True,
        }

    # Handler 4 (可选): 数据库 SQL 查询日志
    if db_log_enabled:
        config["handlers"]["file_db"] = {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "level": "DEBUG",
            "formatter": "json",
            "filters": ["context_filter"],
            "filename": db_log_path,
            "when": "midnight",
            "interval": 1,
            "backupCount": log_retention_days,
            "encoding": "utf-8",
        }
        # SQLAlchemy SQL 语句 → db.log
        config["loggers"]["sqlalchemy.engine"] = {
            "level": "INFO",  # INFO = SQL 语句, DEBUG = SQL + 结果集
            "handlers": ["file_db"],
            "propagate": False,  # 不传播到 console/app.log 避免刷屏
        }
        # 数据库连接池事件 → db.log
        config["loggers"]["sqlalchemy.pool"] = {
            "level": "DEBUG",
            "handlers": ["file_db"],
            "propagate": False,
        }

    # ================================================================
    # Handler 5: 校准事件日志 (ISO/IEC 17025 合规)
    # ================================================================
    # 校准数据必须独立留存，供审计和 CTIA 认证检查
    cal_log_path = os.path.join(log_dir, "calibration.log")
    config["handlers"]["file_calibration"] = {
        "class": "logging.handlers.TimedRotatingFileHandler",
        "level": "DEBUG",
        "formatter": "json",
        "filters": ["context_filter"],
        "filename": cal_log_path,
        "when": "midnight",
        "interval": 1,
        "backupCount": log_retention_days,
        "encoding": "utf-8",
    }
    # app.calibration.* → calibration.log (同时传播到 app.log)
    config["loggers"]["app.calibration"] = {
        "level": "DEBUG",
        "handlers": ["file_calibration"],
        "propagate": True,
    }

    # ================================================================
    # Handler 6: 测量数据日志 (3GPP TR 37.977 数据点归档)
    # ================================================================
    # 每次吞吐量/BLER/CQI/RI 测量的 KPI 快照独立落盘
    meas_log_path = os.path.join(log_dir, "measurement.log")
    config["handlers"]["file_measurement"] = {
        "class": "logging.handlers.TimedRotatingFileHandler",
        "level": "DEBUG",
        "formatter": "json",
        "filters": ["context_filter"],
        "filename": meas_log_path,
        "when": "midnight",
        "interval": 1,
        "backupCount": log_retention_days,
        "encoding": "utf-8",
    }
    # app.measurement.* → measurement.log (同时传播到 app.log)
    config["loggers"]["app.measurement"] = {
        "level": "DEBUG",
        "handlers": ["file_measurement"],
        "propagate": True,
    }

    # ================================================================
    # Handler 7: Channel Engine 仿真日志
    # ================================================================
    # Channel Engine 微服务 (端口 8001) 的请求/响应桥接日志
    ce_log_path = os.path.join(log_dir, "channel_engine.log")
    config["handlers"]["file_channel_engine"] = {
        "class": "logging.handlers.TimedRotatingFileHandler",
        "level": "DEBUG",
        "formatter": "json",
        "filters": ["context_filter"],
        "filename": ce_log_path,
        "when": "midnight",
        "interval": 1,
        "backupCount": log_retention_days,
        "encoding": "utf-8",
    }
    # app.channel_engine.* → channel_engine.log (同时传播到 app.log)
    config["loggers"]["app.channel_engine"] = {
        "level": "DEBUG",
        "handlers": ["file_channel_engine"],
        "propagate": True,
    }

    # ================================================================
    # Handler 8: 审计日志 (操作可追溯性)
    # ================================================================
    # 记录用户身份 + 配置变更 + 关键操作的 Before/After
    # ISO/IEC 17025 要求所有操作可追溯到具体操作人
    audit_log_path = os.path.join(log_dir, "audit.log")
    config["handlers"]["file_audit"] = {
        "class": "logging.handlers.TimedRotatingFileHandler",
        "level": "INFO",  # 审计日志只记录 INFO+，不记录 DEBUG 噪音
        "formatter": "json",
        "filters": ["context_filter"],
        "filename": audit_log_path,
        "when": "midnight",
        "interval": 1,
        "backupCount": log_retention_days * 2,  # 审计日志保留 2 倍时间
        "encoding": "utf-8",
    }
    config["loggers"]["app.audit"] = {
        "level": "INFO",
        "handlers": ["file_audit"],
        "propagate": True,
    }

    # ================================================================
    # Handler 9: 告警/异常事件日志
    # ================================================================
    # 仪器离线/校准过期/BLER 超阈值/环境异常等事件
    # 独立通道便于运维监控系统 (Grafana/ELK) 接入
    alert_log_path = os.path.join(log_dir, "alert.log")
    config["handlers"]["file_alert"] = {
        "class": "logging.handlers.TimedRotatingFileHandler",
        "level": "WARNING",  # 告警日志只记录 WARNING+
        "formatter": "json",
        "filters": ["context_filter"],
        "filename": alert_log_path,
        "when": "midnight",
        "interval": 1,
        "backupCount": log_retention_days,
        "encoding": "utf-8",
    }
    config["loggers"]["app.alert"] = {
        "level": "WARNING",
        "handlers": ["file_alert"],
        "propagate": True,
    }

    # ================================================================
    # Handler 10: 前端行为日志
    # ================================================================
    # 浏览器端通过 POST /api/v1/logs/frontend 上报
    # 记录用户操作序列、API 请求摘要、WebSocket 状态、前端异常
    frontend_log_path = os.path.join(log_dir, "frontend.log")
    config["handlers"]["file_frontend"] = {
        "class": "logging.handlers.TimedRotatingFileHandler",
        "level": "DEBUG",
        "formatter": "json",
        "filters": ["context_filter"],
        "filename": frontend_log_path,
        "when": "midnight",
        "interval": 1,
        "backupCount": log_retention_days,
        "encoding": "utf-8",
    }
    config["loggers"]["app.frontend"] = {
        "level": "DEBUG",
        "handlers": ["file_frontend"],
        "propagate": False,  # 前端日志不传播到 console/app.log，避免刷屏
    }

    logging.config.dictConfig(config)

    # 启动确认
    startup_logger = logging.getLogger("app.core.logging_config")
    startup_logger.info(
        f"Logging initialized: console={console_level}, "
        f"app={app_log_path}, "
        f"scpi={'ON' if scpi_enabled else 'OFF'}, "
        f"db={'ON' if db_log_enabled else 'OFF'}, "
        f"calibration={cal_log_path}, "
        f"measurement={meas_log_path}, "
        f"channel_engine={ce_log_path}, "
        f"audit={audit_log_path}, "
        f"alert={alert_log_path}, "
        f"frontend={frontend_log_path}, "
        f"retention={log_retention_days}d, "
        f"scpi_retention={scpi_retention_days}d"
    )
