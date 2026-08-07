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
        clear = getattr(hal, "clear_metrics_cache", None)
        if callable(clear):
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
            raise InstrumentTestLeaseError(
                f"测试 {purpose!r} 结束后未能确认 {instrument} 控制会话释放"
                + (f": {detail}" if detail else "")
            )

    @asynccontextmanager
    async def hold(
        self,
        purpose: str,
        *,
        control_f64: bool = True,
        control_uxm: bool = True,
        enable_monitoring: bool = True,
    ) -> AsyncIterator[None]:
        """在整个测试生命周期内持有 Remote，任何退出路径都归还 Local。"""
        hal = None
        operation_error: Optional[BaseException] = None
        async with self._coordinated():
            # 锁一到手立即对外标 active，覆盖“正在连接 Remote”的窗口。
            self._active_purpose = purpose
            try:
                try:
                    hal = self._hal()
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
                self._monitoring_enabled = False
                try:
                    if hal is not None:
                        await self._clear_metrics_cache(hal)
                        release_errors: list[BaseException] = []
                        for enabled, instrument in (
                            (control_uxm, "UXM"),
                            (control_f64, "F64"),
                        ):
                            if not enabled:
                                continue
                            try:
                                await self._release_local(
                                    hal, purpose, instrument=instrument
                                )
                            except BaseException as exc:
                                release_errors.append(exc)
                        if release_errors:
                            raise release_errors[0]
                        logger.info(
                            "[instrument-lease] 测试结束，F64/UXM 控制会话已释放: %s",
                            purpose,
                        )
                except BaseException:
                    if operation_error is None:
                        raise
                    logger.exception(
                        "[instrument-lease] 取得/使用仪表异常后释放控制会话也失败: %s",
                        purpose,
                    )

    async def park_idle_instruments(self) -> bool:
        """HAL 初始化/重载完成后，关闭 F64 与 UXM 的控制会话。"""
        async with self._coordinated():
            if self.is_active:
                return False
            hal = self._hal()
            await self._clear_metrics_cache(hal)
            release_errors: list[BaseException] = []
            for instrument in ("UXM", "F64"):
                try:
                    await self._release_local(
                        hal, "idle-park", instrument=instrument
                    )
                except BaseException as exc:
                    release_errors.append(exc)
            if release_errors:
                raise release_errors[0]
            logger.info(
                "[instrument-lease] 空闲停放完成：F64/UXM 均不保持 Remote"
            )
            return True

    @asynccontextmanager
    async def hal_mutation_guard(self) -> AsyncIterator[None]:
        """让 HAL reload/mode switch 与测试取得/使用/释放完整串行。"""
        async with self._coordinated():
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
) -> AsyncIterator[None]:
    async with _LEASE.hold(
        purpose,
        control_f64=control_f64,
        control_uxm=control_uxm,
        enable_monitoring=enable_monitoring,
    ):
        yield


async def park_idle_instruments() -> bool:
    return await _LEASE.park_idle_instruments()


@asynccontextmanager
async def hal_mutation_guard() -> AsyncIterator[None]:
    async with _LEASE.hal_mutation_guard():
        yield
