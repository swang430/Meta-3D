"""
Base classes for Hardware Abstraction Layer (HAL)

Defines abstract interfaces that all instrument drivers must implement.

SCPI 日志架构:
  base 类提供 _write() / _query() 模板方法，自动记录到 scpi.log。
  子类只需覆盖 _do_write() / _do_query() 实现具体的 I/O 操作。
"""

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
import logging
from typing import Any, ClassVar, Dict, FrozenSet, List, Optional
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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
        """记录 SCPI 写命令到 scpi.log"""
        self._scpi_logger.debug(
            f"TX: {cmd}",
            extra={"instrument_id": self.instrument_id, "direction": "TX"},
        )

    def _log_scpi_response(self, cmd: str, response: str) -> None:
        """记录 SCPI 查询及其响应到 scpi.log"""
        self._scpi_logger.debug(
            f"RX: {response.strip()[:200]}",
            extra={
                "instrument_id": self.instrument_id,
                "direction": "RX",
                "query": cmd,
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
        result = self._do_write(cmd, **kwargs)
        # _do_write 可能是同步或异步实现 — 异步时返回 coroutine,
        # 直接交给调用方 await。
        return result

    def _query(self, cmd: str, **kwargs):
        """
        发送 SCPI 查询命令并返回响应（模板方法）。

        Sync _do_query: 返回 str。
        Async _do_query: 返回 coroutine，调用方需 await。

        子类应覆盖 _do_query() 而非本方法。
        """
        self._log_scpi_write(cmd)
        result = self._do_query(cmd, **kwargs)
        if asyncio.iscoroutine(result):
            # 异步路径：包装一层 coroutine，让 RX 日志在真正拿到字符串
            # 之后再写。直接 ``return result`` 会让 _log_scpi_response
            # 永远拿不到 RX，scpi.log 里只有 TX 没有 RX。
            return self._log_response_after_await(cmd, result)
        # 同步路径：直接写日志 + 返回。
        self._log_scpi_response(cmd, result)
        return result

    async def _log_response_after_await(self, cmd: str, coro):
        """Helper: await an async _do_query result, log RX, return string."""
        response = await coro
        self._log_scpi_response(cmd, response)
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
