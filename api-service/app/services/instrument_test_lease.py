"""测试期间独占仪表控制，空闲时释放 F64 与 UXM 的远程控制会话。

本模块是运行入口与具体驱动之间的唯一租约层：测试开始取得 Remote，最后一个
测试操作结束后先关闭监控门，再非破坏性关闭 F64 ATE socket 和 UXM
VISA/HiSLIP 会话。交接过程不发送停止仿真、停止小区、停止信令或复位指令。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


class InstrumentTestLeaseError(RuntimeError):
    """测试无法安全取得或归还仪表控制权。"""


class InstrumentTestLeaseReleaseError(InstrumentTestLeaseError):
    """业务操作结束后，仪表未能被确认交还 Local。"""


class InstrumentTestLease:
    """进程内单飞测试租约。

    所有会触碰真仪表的测试入口共用一个实例。等待中的第二条测试不会把第一条
    测试提前切回 Local；只有持有者退出并完成交接后，它才能取得 Remote。
    """

    def __init__(self, hal_getter: Callable[[], object]):
        self._hal_getter = hal_getter
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock_owner: Optional[asyncio.Task] = None
        self._lock_depth = 0
        self._active_purpose: Optional[str] = None
        # 最外层 hold() 实际取到的控制权 —— 嵌套时用来校验内层没有"要更宽"
        self._held_f64 = False
        self._held_uxm = False
        self._monitoring_enabled = False

    @property
    def is_active(self) -> bool:
        return self._active_purpose is not None

    @property
    def active_purpose(self) -> Optional[str]:
        return self._active_purpose

    @property
    def monitoring_enabled(self) -> bool:
        return self.is_active and self._monitoring_enabled

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            if self.is_active or self._lock_owner is not None:
                raise InstrumentTestLeaseError(
                    "仪表协调锁跨事件循环仍处于活跃状态，拒绝重建锁"
                )
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    def _hal(self):
        return self._hal_getter()

    @asynccontextmanager
    async def _coordinated(self) -> AsyncIterator[None]:
        """可重入的 HAL 生命周期锁。

        reload 初始化会在同一 task 内再次调用 idle park；普通 asyncio.Lock
        不可重入会自锁，因此显式跟踪 owner/depth。不同 task 仍严格串行。
        """
        lock = self._get_lock()
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - async 上下文必有 task
            raise InstrumentTestLeaseError("仪表协调锁必须在 asyncio task 中使用")
        if self._lock_owner is task:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return

        await lock.acquire()
        self._lock_owner = task
        self._lock_depth = 1
        try:
            yield
        finally:
            self._lock_depth -= 1
            if self._lock_depth == 0:
                self._lock_owner = None
                lock.release()

    @staticmethod
    def _f64_driver(hal):
        drivers = getattr(hal, "drivers", {}) or {}
        candidate = drivers.get("channelEmulator") or drivers.get("channel_emulator")
        if candidate is None:
            return None
        if not inspect.iscoroutinefunction(
            getattr(candidate, "acquire_remote_control", None)
        ):
            return None
        if not inspect.iscoroutinefunction(
            getattr(candidate, "release_to_local_control", None)
        ):
            return None
        return candidate

    @staticmethod
    def _uxm_driver(hal):
        drivers = getattr(hal, "drivers", {}) or {}
        candidate = drivers.get("baseStation") or drivers.get("base_station")
        if candidate is None:
            return None
        if not inspect.iscoroutinefunction(
            getattr(candidate, "acquire_remote_control", None)
        ):
            return None
        if not inspect.iscoroutinefunction(
            getattr(candidate, "release_to_local_control", None)
        ):
            return None
        return candidate

    @staticmethod
    async def _clear_metrics_cache(hal) -> None:
        # ⚠ 必须查**协程性**，不能只查 callable —— 跟同文件 `_f64_driver`
        #   对 `acquire_remote_control` / `release_to_local_control` 的做法一致。
        #   `callable()` 对 MagicMock、对同名的同步方法、对任意属性都成立，
        #   `await` 上去就是 `TypeError: object X can't be used in 'await'`，
        #   而它发生在 `hold()` 的 try 里 → 整个租约连同业务操作一起炸，
        #   错误还长得像"仪表控制出问题"（2026-08-08：给校准链加租约时撞到，
        #   4 个静区/XPD 测试的 hal 是 MagicMock）。
        clear = getattr(hal, "clear_metrics_cache", None)
        if inspect.iscoroutinefunction(clear):
            await clear()

    async def _acquire_remote(
        self, hal, purpose: str, *, instrument: str
    ) -> None:
        if instrument == "F64":
            driver = self._f64_driver(hal)
        elif instrument == "UXM":
            driver = self._uxm_driver(hal)
        else:  # pragma: no cover - 仅内部固定枚举调用
            raise ValueError(f"未知仪表控制租约: {instrument}")
        if driver is None:
            return
        if not await driver.acquire_remote_control():
            detail = getattr(driver, "get_last_error", lambda: None)()
            raise InstrumentTestLeaseError(
                f"测试 {purpose!r} 无法取得 {instrument} Remote 控制"
                + (f": {detail}" if detail else "")
            )

    async def _release_local(
        self, hal, purpose: str, *, instrument: str
    ) -> None:
        if instrument == "F64":
            driver = self._f64_driver(hal)
        elif instrument == "UXM":
            driver = self._uxm_driver(hal)
        else:  # pragma: no cover - 仅内部固定枚举调用
            raise ValueError(f"未知仪表控制租约: {instrument}")
        if driver is None:
            return
        if not await driver.release_to_local_control():
            detail = getattr(driver, "get_last_error", lambda: None)()
            raise InstrumentTestLeaseReleaseError(
                f"测试 {purpose!r} 结束后未能确认 {instrument} 控制会话释放"
                + (f": {detail}" if detail else "")
            )

    async def _settle_local_controls(
        self,
        hal,
        purpose: str,
        *,
        control_f64: bool,
        control_uxm: bool,
    ) -> None:
        """独立尝试缓存清理与全部 Local 归还，并聚合完整失败证据。"""
        failures: list[tuple[str, BaseException]] = []
        try:
            await self._clear_metrics_cache(hal)
        except BaseException as exc:
            failures.append(("指标缓存清理", exc))

        for enabled, instrument in (
            (control_uxm, "UXM"),
            (control_f64, "F64"),
        ):
            if not enabled:
                continue
            try:
                await self._release_local(hal, purpose, instrument=instrument)
            except BaseException as exc:
                failures.append((f"{instrument} Local 交接", exc))

        if failures:
            details = "；".join(
                f"{stage}: {type(exc).__name__}: {exc}"
                for stage, exc in failures
            )
            raise InstrumentTestLeaseReleaseError(
                f"测试 {purpose!r} 结束时未能完整确认仪表 Local 交接：{details}"
            ) from failures[0][1]

    @asynccontextmanager
    async def hold(
        self,
        purpose: str,
        *,
        control_f64: bool = True,
        control_uxm: bool = True,
        enable_monitoring: bool = True,
        validate_before_remote: Optional[Callable[[object], Optional[str]]] = None,
    ) -> AsyncIterator[None]:
        """在整个测试生命周期内持有 Remote，任何退出路径都归还 Local。

        ⚠ **嵌套按引用计数处理，只有最外层真正取/放控制权**（2026-08-07 内审 F5）。

        原实现的 `finally` 会**无条件**清 `_active_purpose` / `_monitoring_enabled`
        并把 F64/UXM 交还 Local —— 嵌套时内层退出就把外层的控制权拆了，而外层
        还在跑：此后外层每条 SCPI 都撞 Local 门，同时 `hal_reload_policy` 的
        blocker 消失，`POST /hal/reload` 会在正式执行进行中直接放行拆驱动。

        一度改成"嵌套直接抛"，但那跟**校准链**冲突：`acquire_sa_power_via_ce_tone`
        是三个校准服务共用的最内层 primitive，租约必须加在它上面（否则 park 之后
        校准必然撞 Local 门）；而一次探头校准要跑 32 探头 × 2 极化 = 64 次调用，
        每次进出都 connect/close 的开销不可接受。所以正解是让嵌套**安全**：
        最外层 acquire/release，内层复用同一份控制权、退出不拆。

        ⚠ 内层要的控制权**不能比外层宽** —— 外层只持了 UXM，内层却要 F64 时，
        那台 F64 根本没被 acquire，内层照跑就会在第一条 SCPI 上撞 Local 门。
        这种情况 fail-loud，不静默降级。
        """
        hal = None
        operation_error: Optional[BaseException] = None
        # 同 task 已持租约 = 嵌套。内层不重复 acquire/release，只做控制权校验。
        nested = (
            self._lock_owner is asyncio.current_task()
            and self._active_purpose is not None
        )
        if nested:
            widened = [
                name for want, have, name in (
                    (control_f64, self._held_f64, "F64"),
                    (control_uxm, self._held_uxm, "UXM"),
                ) if want and not have
            ]
            if widened:
                raise InstrumentTestLeaseError(
                    f"嵌套租约 {purpose!r} 要求 {widened} 的控制权，"
                    f"而外层 {self._active_purpose!r} 没有持有它 —— "
                    f"内层不会重复 acquire，照跑会在第一条 SCPI 上撞 Local 门。"
                    f"把外层的 control_f64/control_uxm 放宽，或把内层移到租约外。"
                )
            logger.debug(
                "[instrument-lease] 嵌套复用 %r 的控制权: %s",
                self._active_purpose, purpose,
            )
            yield
            return
        async with self._coordinated():
            # 校验必须与 HAL reload 共用同一把协调锁，并且排在 cache clear / Remote
            # acquire 之前。否则“保存了新地址、活动 driver 仍是旧地址”的窗口会先
            # 对旧仪表产生控制 I/O，随后才报配置冲突。
            hal = self._hal()
            if validate_before_remote is not None:
                validation_error = validate_before_remote(hal)
                if validation_error:
                    raise InstrumentTestLeaseError(validation_error)
            # 锁一到手立即对外标 active，覆盖“正在连接 Remote”的窗口。
            self._active_purpose = purpose
            self._held_f64 = control_f64
            self._held_uxm = control_uxm
            try:
                try:
                    await self._clear_metrics_cache(hal)
                    if control_f64:
                        await self._acquire_remote(hal, purpose, instrument="F64")
                    if control_uxm:
                        await self._acquire_remote(hal, purpose, instrument="UXM")
                    self._monitoring_enabled = enable_monitoring
                    logger.info("[instrument-lease] 测试取得仪表控制: %s", purpose)
                    yield
                except BaseException as exc:
                    operation_error = exc
                    raise
            finally:
                # 先关监控门，阻止新一轮 get_metrics 排到 SCPI 锁后面。
                self._active_purpose = None
                self._held_f64 = False
                self._held_uxm = False
                self._monitoring_enabled = False
                try:
                    if hal is not None:
                        await self._settle_local_controls(
                            hal,
                            purpose,
                            control_f64=control_f64,
                            control_uxm=control_uxm,
                        )
                        logger.info(
                            "[instrument-lease] 测试结束，F64/UXM 控制会话已释放: %s",
                            purpose,
                        )
                except BaseException as release_error:
                    if operation_error is None:
                        raise
                    logger.exception(
                        "[instrument-lease] 取得/使用仪表异常后释放控制会话也失败: %s",
                        purpose,
                    )
                    raise InstrumentTestLeaseReleaseError(
                        f"测试 {purpose!r} 的操作失败 ({operation_error})，且随后"
                        f"未能安全归还仪表控制 ({release_error})"
                    ) from operation_error

    async def park_idle_instruments(self) -> bool:
        """HAL 初始化/重载完成后，关闭 F64 与 UXM 的控制会话。"""
        async with self._coordinated():
            if self.is_active:
                return False
            hal = self._hal()
            await self._settle_local_controls(
                hal,
                "idle-park",
                control_f64=True,
                control_uxm=True,
            )
            logger.info(
                "[instrument-lease] 空闲停放完成：F64/UXM 均不保持 Remote"
            )
            return True

    @asynccontextmanager
    async def hal_mutation_guard(self) -> AsyncIterator[None]:
        """让 HAL reload/mode switch 与测试取得/使用/释放完整串行。"""
        async with self._coordinated():
            yield

    @asynccontextmanager
    async def positioner_operation_guard(
        self, purpose: str
    ) -> AsyncIterator[None]:
        """让完整转台动作与 destructive diagnostic / HAL reload 串行。

        急停不使用本 guard：ABORT 必须能在一个长时间 MOVE/HOME 仍持有操作锁时
        抢占；底层每条 AeroBasic TX/RX 自身仍由驱动通信锁串行化。
        """
        async with self._coordinated():
            logger.debug("[instrument-lease] 取得转台操作锁: %s", purpose)
            yield


def _get_hal_service():
    # 延迟导入，避免 HAL service 初始化本模块时形成循环依赖。
    from app.services.instrument_hal_service import get_hal_service

    return get_hal_service()


_LEASE = InstrumentTestLease(_get_hal_service)


def is_test_lease_active() -> bool:
    return _LEASE.is_active


def active_test_lease_purpose() -> Optional[str]:
    return _LEASE.active_purpose


def is_test_monitoring_enabled() -> bool:
    return _LEASE.monitoring_enabled


@asynccontextmanager
async def instrument_test_lease(
    purpose: str,
    *,
    control_f64: bool = True,
    control_uxm: bool = True,
    enable_monitoring: bool = True,
    validate_before_remote: Optional[Callable[[object], Optional[str]]] = None,
) -> AsyncIterator[None]:
    async with _LEASE.hold(
        purpose,
        control_f64=control_f64,
        control_uxm=control_uxm,
        enable_monitoring=enable_monitoring,
        validate_before_remote=validate_before_remote,
    ):
        yield


async def park_idle_instruments() -> bool:
    return await _LEASE.park_idle_instruments()


@asynccontextmanager
async def hal_mutation_guard() -> AsyncIterator[None]:
    async with _LEASE.hal_mutation_guard():
        yield


@asynccontextmanager
async def positioner_operation_guard(purpose: str) -> AsyncIterator[None]:
    async with _LEASE.positioner_operation_guard(purpose):
        yield
