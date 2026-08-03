"""
Base classes for Hardware Abstraction Layer (HAL)

Defines abstract interfaces that all instrument drivers must implement.

SCPI 日志架构:
  base 类提供 _write() / _query() 模板方法，自动记录到 scpi.log。
  子类只需覆盖 _do_write() / _do_query() 实现具体的 I/O 操作。

  每次往返产出一条 TX + 一条结果记录 (P1-30)：
    TX  → 即将下发 (只表示"程序打算发", 不表示仪器收到了)
    OK  → 写命令下发完成 (带 duration_ms)
    RX  → 查询拿到响应 (带 duration_ms + resp_len 真实长度)
    ERR → 下发/读取过程中抛异常 (带 duration_ms + error_type), 异常随后原样重抛

  ⚠ **配对要按 `query` 字段, 不能按"相邻行"** —— TX 记在 `_scpi_lock` **之外**
  且在 `_do_*` 之前, 所以两种情况下 TX 与结果行不相邻:
    · **并发** —— 多协程共用一台仪器时 (broadcaster 1 Hz × 32+ 查询与测量
      序列并行), 连续几条 TX 会先落盘, 结果行随后交错回来;
    · **嵌套** —— F64 `_do_query` 超时后在同一条命令的窗口内调
      `_drain_after_timeout` / `_drain_errors`, 那里每条 `SYST:ERR?` 各产生
      一对 TX/RX, 排完才写外层的 ERR。
  (`OK` 行目前只在 msg 文本里带命令、没有 `query` 字段 —— 给它补上属于加
   机制, 已进 backlog。)

  ⚠ **只有 TX 没有后续 ≠ 一定失败**, 它是个**多义签名**, 至少覆盖:
  被上层 `asyncio.wait_for` 超时 / 被 `task.cancel()` 取消 / coroutine 从未
  被 await / 进程中断。前两种走 `CancelledError`, 它继承 `BaseException`,
  **本文件的 `except Exception` 抓不到**, 所以不会留下 ERR 行 —— 这是当前
  已知的证据缺口, 不是本片修好了的东西 (要覆盖须改成 `except BaseException`
  + 裸 raise, 已进 backlog)。

  ⚠ **`duration_ms` 的口径包含排队等锁的时间** —— 对 async 驱动 (F64/FS16),
  t0 取在 coroutine **创建**时刻, 而 `_scpi_lock` 在 coroutine **内部**才拿;
  ERR 的 duration_ms 还额外含 `_drain_after_timeout` 的排水时间 (上界 64 次
  `SYST:ERR?`)。所以它答的是"这次调用从发起到落定花了多久", **不是**"仪器
  响应花了多久" —— 看到 8000ms 别直接判仪器慢。
"""

import asyncio
import time
from abc import ABC, abstractmethod
from enum import Enum
import logging
from typing import Any, ClassVar, Dict, FrozenSet, List, Optional
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _resolve_resp_max() -> int:
    """响应体写进日志的最大字符数 (超出截断并显式标记)。

    P1-30 之前是硬编码 200 且**无任何标记** —— 实测 31 个 scpi.log* 里
    hal_mode=real 的 RX 共 171,170 条, 其中 **22,914 条恰好 200 字符**(13.4%)
    即被截断, 且 RX 的最大长度就是 200 → 日志里**从未出现过任何一条长响应
    的全貌**。被砍最多的是 BSE:...BTHRoughput:DL:TSTatistics:JSON? (22,608 条,
    下行吞吐量统计 = 项目核心测量数据), 还砍过 SYST:INFO? / SYSTem:ERRor?。

    默认放宽到 2000；现场磁盘吃紧可用 `LOG_SCPI_RESP_MAX` 调回。
    无论是否截断, resp_len 都记**真实长度**, 读者永远知道被砍了多少。

    ⚠ 走 `app.config.settings` 而不是 `os.getenv` —— 本项目的 `.env` 由
    pydantic-settings 直接读进 Settings 对象, **不会注入 os.environ**
    (实证: import app.config 前后 os.environ 里都没有 DATABASE_URL)。
    用 os.getenv 会让 .env 里配的值被静默忽略, 旋钮形同虚设。
    """
    from app.config import settings

    try:
        return max(0, int(settings.log_scpi_resp_max))
    except (TypeError, ValueError):
        logger.warning(
            f"log_scpi_resp_max={settings.log_scpi_resp_max!r} 不是整数, "
            f"回落默认 2000"
        )
        return 2000


_SCPI_LOG_RESP_MAX = _resolve_resp_max()


class InstrumentStatus(str, Enum):
    """Instrument connection and operational status"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    UNKNOWN = "unknown"


class InstrumentCapability(BaseModel):
    """Instrument capability description"""
    name: str
    description: str
    supported: bool
    parameters: Optional[Dict[str, Any]] = None


class InstrumentMetrics(BaseModel):
    """Real-time metrics from instrument"""
    timestamp: datetime
    metrics: Dict[str, Any]
    status: str = "normal"  # normal, warning, critical


class InstrumentDriver(ABC):
    """
    Abstract base class for all instrument drivers

    Provides standard interface for:
    - Connection management
    - Configuration
    - Data acquisition
    - Status monitoring

    SCPI 日志:
      子类不要直接覆盖 _write() / _query()，
      而是覆盖 _do_write() / _do_query()。
      基类的 _write() / _query() 会自动记录 SCPI 通信到 scpi.log。
    """

    # P2-3: static "what this MODEL can expose" declaration. Read without
    # instantiating / connecting the driver, so catalog API + offline plan
    # editing can answer "does FS16 support ce.interference_generator?"
    # before HAL Reload. Subclasses override with a frozenset of canonical
    # tokens (see app/hal/capabilities.py). Default empty so a forgotten
    # override is honest about lack of declaration rather than inheriting
    # a parent's set.
    #
    # Invariant (enforced in tests): runtime ``self.capabilities`` must be
    # a subset of ``model_capabilities`` — a live driver can't expose what
    # the model doesn't declare. Adding a runtime token outside this set
    # means either the model declaration is wrong or the runtime probe is
    # reading something the vocabulary doesn't cover.
    model_capabilities: ClassVar[FrozenSet[str]] = frozenset()

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        """
        Initialize instrument driver

        Args:
            instrument_id: Unique identifier for this instrument
            config: Configuration parameters (IP, port, model, etc.)
        """
        self.instrument_id = instrument_id
        self.config = config
        self._status = InstrumentStatus.DISCONNECTED
        self._last_error: Optional[str] = None

        # 安装选件 (license) 缓存。connect() 中由 _probe_installed_options()
        # 调 *OPT? 填充。空列表 = 探测失败 / 仪表不支持 *OPT? / 尚未连接。
        self._installed_options: List[str] = []

        # P2-2: 单一 capability 出口。 子类在 connect() / probe 时把
        # canonical token 加进来 (见 app/hal/capabilities.py 词表)。新代码
        # 应当读这个 set, 旧的 has_interference_generator / is_single_axis
        # 等 bool 字段会作为过渡 alias 保留, 内部由 driver 自己同步两边。
        # Consumer 不应直接 mutate 这个 set —— 走 _add_capability().
        self.capabilities: set[str] = set()

        # SCPI 通信专用 logger — 命名空间 app.hal.scpi.{id}
        # 被 logging_config 中的 SCPI handler 独立捕获到 scpi.log
        self._scpi_logger = logging.getLogger(f"app.hal.scpi.{instrument_id}")

    # ── SCPI 日志记录 (内部使用) ───────────────────────────────

    def _log_scpi_write(self, cmd: str) -> None:
        """记录"即将下发"到 scpi.log。

        ⚠ 这行**不代表仪器收到了** —— 它记在 _do_write / _do_query 执行之前,
        语义是"程序打算发这条"。是否走完看配对的 OK / RX / ERR 行。
        """
        self._scpi_logger.debug(
            f"TX: {cmd}",
            extra={"instrument_id": self.instrument_id, "direction": "TX"},
        )

    def _log_scpi_response(
        self, cmd: str, response: str, duration_ms: Optional[float] = None
    ) -> None:
        """记录 SCPI 查询及其响应到 scpi.log。

        两个长度，别混：
          · ``resp_len`` = **原始响应的字符数, 未 strip 未截断** —— "从线上
            收到了多少"。这是给读者判断证据完整性用的唯一权威数。
          · truncated 标记的分母 = **strip 后**准备显示的字符数。

        两者可能差几个 (换行 / 前后空格)。刻意分开是因为 **whitespace-only
        响应必须与真空响应可区分** (Codex #273 P2): 仪器回 ``"   \\n"`` 与
        什么都没回, 是两件事 —— 前者 ``resp_len=4`` 且消息体为空, 后者
        ``resp_len=0``。早先版本先 strip 再量长度, 两者都成 0, 而本片正是
        拿"空回复 60,565 条"当立项证据的, 量错了长度等于把证据量废。
        """
        raw_len = len(response)
        body = response.strip()
        shown_len = len(body)
        if shown_len > _SCPI_LOG_RESP_MAX:
            body = (
                f"{body[:_SCPI_LOG_RESP_MAX]}"
                f"…[truncated {_SCPI_LOG_RESP_MAX}/{shown_len}]"
            )
        extra: Dict[str, Any] = {
            "instrument_id": self.instrument_id,
            "direction": "RX",
            "query": cmd,
            "resp_len": raw_len,
        }
        if duration_ms is not None:
            extra["duration_ms"] = round(duration_ms, 3)
        self._scpi_logger.debug(f"RX: {body}", extra=extra)

    def _log_scpi_done(self, cmd: str, duration_ms: float) -> None:
        """记录写命令下发完成 (无响应体) 到 scpi.log。

        写命令在 real 模式下只占 SCPI 流量的 ~1% (实测 2,293 条写 vs
        261,755 条查询), 所以给每条写补一条完成行的体量代价可忽略,
        换来的是"发了就一定有配对记录", 不必靠"没看到报错"去推断成功。
        """
        self._scpi_logger.debug(
            f"OK: {cmd}",
            extra={
                "instrument_id": self.instrument_id,
                "direction": "OK",
                "duration_ms": round(duration_ms, 3),
            },
        )

    def _log_scpi_error(
        self, cmd: str, exc: BaseException, duration_ms: float
    ) -> None:
        """记录往返过程中抛出的异常到 scpi.log。

        ⚠ 级别刻意用 DEBUG 而非 WARNING: app.hal.scpi.* propagate 到 root
        (console + app.log)。app.log 已经被 DEBUG 心跳刷到 78% 噪声, 再把
        SCPI 异常按 WARNING 灌进去只会让它更难读。异常的**告警**归驱动层
        决定, 本行只负责在 scpi.log 里留下可 grep 的证据 (direction=ERR)。

        ⚠ 异常消息体复用 RX 的同一上限 —— 驱动里 `ValueError(f"...{raw}...")`
        这类写法会把整段响应嵌进异常, 不设限的话被 RX 挡住的 3412 字符会从
        ERR 行原样漏出去, 与本片"给日志加边界"正相反。
        """
        detail = str(exc)
        if len(detail) > _SCPI_LOG_RESP_MAX:
            detail = (
                f"{detail[:_SCPI_LOG_RESP_MAX]}"
                f"…[truncated {_SCPI_LOG_RESP_MAX}/{len(detail)}]"
            )
        self._scpi_logger.debug(
            f"ERR: {cmd} -> {type(exc).__name__}: {detail}",
            extra={
                "instrument_id": self.instrument_id,
                "direction": "ERR",
                "query": cmd,
                "error_type": type(exc).__name__,
                "duration_ms": round(duration_ms, 3),
            },
        )

    # ── SCPI 模板方法 (子类覆盖 _do_write / _do_query) ────────
    #
    # 这两个模板方法对 sync 和 async 的 _do_query / _do_write 都透明:
    #
    #   - 如果子类的 _do_query 是 def 返回 str（pyvisa 直接调用，
    #     ENA / UXM / Keysight MXG 等），_query() 返回 str，调用方按
    #     ``idn = driver._query("*IDN?").strip()`` 用。
    #
    #   - 如果子类的 _do_query 是 async def 返回 str（pyvisa 走
    #     ``asyncio.to_thread``，PROPSIM F64 / FS16 等），_query() 返回
    #     一个 coroutine，调用方按 ``idn = await driver._query("*IDN?")``
    #     用。Coroutine 内部 await _do_query 拿到字符串再写 RX 日志，
    #     避免把 coroutine 对象丢进 _log_scpi_response 触发
    #     ``'coroutine' object has no attribute 'strip'`` 崩溃
    #     （CAICT 2026-05-13 现场实际遇到的 bug，详见
    #     docs/site-debug/2026-05-13-retrospective.md）。

    def _write(self, cmd: str, **kwargs):
        """
        发送 SCPI 写命令（模板方法）。

        Sync _do_write: 同步执行，无返回值。
        Async _do_write: 返回 coroutine，调用方需 await。

        子类应覆盖 _do_write() 而非本方法。
        """
        self._log_scpi_write(cmd)
        t0 = time.perf_counter()
        try:
            result = self._do_write(cmd, **kwargs)
        except Exception as exc:
            # 只记日志, 异常**原样重抛** —— 控制流零变化。
            self._log_scpi_error(cmd, exc, (time.perf_counter() - t0) * 1000)
            raise
        # _do_write 可能是同步或异步实现 — 异步时返回 coroutine,
        # 包一层让 OK / ERR 行在真正执行完之后才写 (与 _query 同形态)。
        if asyncio.iscoroutine(result):
            return self._log_write_done_after_await(cmd, result, t0)
        self._log_scpi_done(cmd, (time.perf_counter() - t0) * 1000)
        return result

    async def _log_write_done_after_await(self, cmd: str, coro, t0: float):
        """Helper: await 异步 _do_write, 写 OK / ERR 行, 返回原结果。"""
        try:
            result = await coro
        except Exception as exc:
            self._log_scpi_error(cmd, exc, (time.perf_counter() - t0) * 1000)
            raise
        self._log_scpi_done(cmd, (time.perf_counter() - t0) * 1000)
        return result

    def _query(self, cmd: str, **kwargs):
        """
        发送 SCPI 查询命令并返回响应（模板方法）。

        Sync _do_query: 返回 str。
        Async _do_query: 返回 coroutine，调用方需 await。

        子类应覆盖 _do_query() 而非本方法。
        """
        self._log_scpi_write(cmd)
        t0 = time.perf_counter()
        try:
            result = self._do_query(cmd, **kwargs)
        except Exception as exc:
            # 只记日志, 异常**原样重抛** —— 控制流零变化。
            self._log_scpi_error(cmd, exc, (time.perf_counter() - t0) * 1000)
            raise
        if asyncio.iscoroutine(result):
            # 异步路径：包装一层 coroutine，让 RX 日志在真正拿到字符串
            # 之后再写。直接 ``return result`` 会让 _log_scpi_response
            # 永远拿不到 RX，scpi.log 里只有 TX 没有 RX。
            return self._log_response_after_await(cmd, result, t0)
        # 同步路径：直接写日志 + 返回。
        self._log_scpi_response(cmd, result, (time.perf_counter() - t0) * 1000)
        return result

    async def _log_response_after_await(
        self, cmd: str, coro, t0: Optional[float] = None
    ):
        """Helper: await an async _do_query result, log RX, return string."""
        if t0 is None:
            t0 = time.perf_counter()
        try:
            response = await coro
        except Exception as exc:
            self._log_scpi_error(cmd, exc, (time.perf_counter() - t0) * 1000)
            raise
        self._log_scpi_response(cmd, response, (time.perf_counter() - t0) * 1000)
        return response

    def _do_write(self, cmd: str, **kwargs) -> None:
        """
        子类实现: 实际的 SCPI 写操作。
        
        默认实现为 no-op（Mock 模式安全）。
        真实驱动应覆盖此方法调用 visa_session.write()。
        """
        pass

    def _do_query(self, cmd: str, **kwargs) -> str:
        """
        子类实现: 实际的 SCPI 查询操作。
        
        默认实现返回空字符串（Mock 模式安全）。
        真实驱动应覆盖此方法调用 visa_session.query()。
        """
        return ""

    # ── 选件 / license 探测 (启动时, 不依赖 config 声明) ──────
    #
    # 设计原则: 仪表能告诉我们的事 (license / 选件 / 通道数 / 频段),
    # 启动时通过 SCPI 查询; 不要让运维去填表。connect() 在 *IDN? 验证
    # 身份后调 _probe_installed_options() 拿到 *OPT? 字符串, 解析成列表,
    # 再交给子类的 _apply_discovered_capabilities() 映射为驱动内部能力
    # 标志 (e.g. has_interference_generator on PROPSIM)。
    #
    # 子类应在 connect() 内显式触发:
    #   opts = await self._probe_installed_options()
    #   await self._apply_discovered_capabilities(opts)
    #
    # 默认 _probe_installed_options() 调标准 *OPT? — 失败时容错返回 [],
    # 子类只在仪表用非标准查询时才 override (罕见)。
    # 默认 _apply_discovered_capabilities() 是 no-op — 没有 license 类
    # 能力字段的子类不需要 override。

    async def _probe_installed_options(self) -> List[str]:
        """启动时探测安装选件 (IEEE 488.2 标准 *OPT? 查询).

        返回 list[str] 选件 token; 失败时返回 [] 并记录警告 (不抛). 容错是
        刻意的: 不是所有仪表都实现 *OPT?, 不应阻断 connect.
        """
        try:
            raw = await self._query("*OPT?")
        except Exception as e:
            logger.warning(
                f"[{self.instrument_id}] *OPT? probe failed: {e}",
                extra={"instrument_id": self.instrument_id},
            )
            self._installed_options = []
            return []
        opts = self._parse_options_response(raw)
        self._installed_options = opts
        logger.info(
            f"[{self.instrument_id}] installed options: {opts or '(none)'}",
            extra={"instrument_id": self.instrument_id},
        )
        return opts

    @staticmethod
    def _parse_options_response(raw: str) -> List[str]:
        """解析 *OPT? CSV 响应.

        典型格式:  'K01,K02,"INT-GEN", 0'  →  ['K01', 'K02', 'INT-GEN', '0']
        空 / "0" / 空字符串过滤掉, 双引号剥掉, 大小写保持原样 (子类匹配时
        自己做归一化).
        """
        if not raw:
            return []
        parts = [p.strip().strip('"').strip() for p in raw.split(",")]
        # 过滤空 token; '0' 是 Keysight 表示"无选件"的占位符, 保留交给子类
        return [p for p in parts if p]

    async def _apply_discovered_capabilities(self, options: List[str]) -> None:
        """子类钩子: 把 *OPT? 解析出的 token 映射到自己的能力字段.

        默认 no-op. PROPSIM 用 token 推 has_interference_generator;
        VNA 子类未来加 license-aware 测量时按同样方式 override.
        """
        return

    def _add_capability(self, token: str) -> None:
        """P2-2: register a canonical capability token on this driver.

        Subclasses call this from connect / probe / configure paths to
        declare what they expose at runtime. ``token`` must be a member
        of ``app.hal.capabilities.KNOWN_CAPABILITIES`` — unknown tokens
        are still added (so a typo doesn't break first-call), but a
        warning is logged so the drift is visible in scpi/hal logs.

        Idempotent: adding a token that's already in the set is a no-op
        (a probe that reruns produces the same set).
        """
        from app.hal.capabilities import KNOWN_CAPABILITIES

        if token not in KNOWN_CAPABILITIES:
            logger.warning(
                "[%s] non-canonical capability token registered: %r — add it "
                "to app/hal/capabilities.py:KNOWN_CAPABILITIES or fix the typo",
                self.instrument_id, token,
                extra={"instrument_id": self.instrument_id},
            )
        self.capabilities.add(token)

    def _remove_capability(self, token: str) -> None:
        """Mirror of ``_add_capability`` for capabilities that probe-out as
        absent on this unit. Mostly used when a driver flips an explicit
        config override at construction time and needs to clear a token
        that a default might have populated."""
        self.capabilities.discard(token)

    # ── 状态与属性 ────────────────────────────────────────────

    @property
    def status(self) -> InstrumentStatus:
        """Get current instrument status"""
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        """Get last error message"""
        return self._last_error

    # ── 抽象接口 ──────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to instrument

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close connection to instrument

        Returns:
            True if disconnection successful, False otherwise
        """
        pass

    @abstractmethod
    async def configure(self, config: Dict[str, Any]) -> bool:
        """
        Configure instrument parameters

        Args:
            config: Configuration parameters to apply

        Returns:
            True if configuration successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_capabilities(self) -> list[InstrumentCapability]:
        """
        Get instrument capabilities

        Returns:
            List of supported capabilities
        """
        pass

    @abstractmethod
    async def get_metrics(self) -> InstrumentMetrics:
        """
        Get current instrument metrics

        Returns:
            Current metrics data
        """
        pass

    @abstractmethod
    async def reset(self) -> bool:
        """
        Reset instrument to default state

        Returns:
            True if reset successful, False otherwise
        """
        pass

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on instrument

        Returns:
            Health status information
        """
        return {
            "instrument_id": self.instrument_id,
            "status": self.status.value,
            "last_error": self.last_error,
            "timestamp": datetime.utcnow().isoformat()
        }

    def readiness_metadata(self) -> Dict[str, Any]:
        """P3-5: driver-specific extras for the HAL readiness report.

        Returns a key/value dict surfaced alongside the row's core fields
        (status, endpoint, detail) in ``GET /instruments/hal/readiness`` +
        the formatted startup table. Default empty so the base contract is
        zero-cost — subclasses opt-in by overriding when they have parsed
        metadata worth exposing (e.g. PROPSIM F64 surfaces SYST:INFO?
        fields here, since P3-4 parses them onto the driver instance but
        the readiness report is the only outward-facing surface).

        Must be safe to call when the driver is not connected (return
        ``{}`` rather than raise) — the readiness builder doesn't filter
        by status before calling.
        """
        return {}

    def _set_status(self, status: InstrumentStatus, error: Optional[str] = None):
        """Internal method to update status with lifecycle logging"""
        old_status = self._status
        self._status = status
        # VISA 连接生命周期日志 — 记录每次状态变更
        if old_status != status:
            logger.info(
                f"[{self.instrument_id}] status: {old_status.value} → {status.value}",
                extra={"instrument_id": self.instrument_id},
            )
        if error:
            self._last_error = error
            logger.error(
                f"[{self.instrument_id}] error: {error}",
                extra={"instrument_id": self.instrument_id},
            )

    def _clear_error(self):
        """Internal method to clear error"""
        self._last_error = None
