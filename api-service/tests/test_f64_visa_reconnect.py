"""RealPropsimF64Driver — transparent VISA reconnect on conn-lost shapes.

Mirrors the Aerotech idle-close reconnect (PR #14) but for PyVISA
transport. F64 is the first PyVISA-backed driver to get the pattern
because calibration loops leave the resource idle for minutes between
commands, which is exactly when network NAT / instrument-side idle
timeouts surface.

Contract pinned by these tests:
  1. ``VI_ERROR_CONN_LOST`` (0xBFFF00B5) triggers ONE reconnect + retry.
  2. ``VI_ERROR_INV_OBJECT`` (0xBFFF000E) triggers ONE reconnect + retry.
  3. ``VI_ERROR_TMO`` (0xBFFF0015) does NOT *itself* trigger reconnect —
     timeouts propagate so callers can decide (same Codex-#14 lesson).
     F64R-1 refinement: a timeout first runs the lightweight drain; only
     when the drain ALSO fails (session genuinely desynced, not merely a
     slow instrument) does the driver escalate to rebuilding the session.
     "This command timed out" and "this session is broken" stay distinct;
     the in-flight command still raises either way, and is never replayed.
  4. Non-VISA exceptions don't trigger reconnect.
  5. Bounded — second consecutive conn-lost still raises (no infinite loop).
  6. Both ``_do_write`` and ``_do_query`` honour the contract.

We don't talk to a real F64; PyVISA is monkey-patched at the
``ResourceManager.open_resource`` boundary with a fake resource whose
``write`` / ``query`` can be programmed to fail-then-succeed.
"""
from __future__ import annotations

import time
from typing import Any, List
from unittest.mock import MagicMock

import pytest

# pyvisa must be importable — F64 driver imports it lazily inside
# methods, the test imports it eagerly so VisaIOError is available to
# the test.
pyvisa = pytest.importorskip("pyvisa")

from app.hal.propsim_f64 import RealPropsimF64Driver


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeVisaResource:
    """Records every write/query, can be programmed to raise specific
    VisaIOErrors on the first N calls then succeed."""

    def __init__(self, name: str = "primary") -> None:
        self.name = name
        self.writes: List[str] = []
        self.queries: List[str] = []
        self.write_fail_with: List[BaseException] = []
        self.query_fail_with: List[BaseException] = []
        self.query_response: str = "OK\n"
        # F64R-1 排水路钩子: 裸 read (排水第一步) 与"按序回复"的 query
        self.read_fail_with: List[BaseException] = []
        self.query_responses: List[str] = []
        self.timeout: int = 5000
        self.closed = False
        # 可选: 按命令分派的应答函数 (优先于 query_fail_with / query_response)
        self.query_router = None

    def _check_open(self) -> None:
        """⚠ 已 close 的 pyvisa Resource 上再发命令会抛 `InvalidSession`
        (实测 pyvisa 1.16.2: `Resource.session` property 在 `_session is None` 时先抛,
        根本走不到 VISA C 库那层去返回 INV_OBJECT)。**fake 必须复刻这个行为** ——
        原先 close() 只置个标志、之后照样按"活着的 socket"作答超时, 于是"关掉旧句柄后
        还能靠超时触发下一轮重连自愈"这条路在测试里是通的、真机上根本不存在
        (memory feedback_test_failure_may_mean_wrong_fake 同款: fake 教了个不可能的
        仪器模型, 把一个真实的永久死态缺陷盖住了)。"""
        if self.closed:
            raise pyvisa.errors.InvalidSession()

    def read(self) -> str:
        """排水第一步的**裸 read** (不发新查询)。抛超时 = 无残留应答, 会话已对齐。"""
        self._check_open()
        if self.read_fail_with:
            exc = self.read_fail_with.pop(0)
            if exc is not None:
                raise exc
        return self.query_response

    def write(self, cmd: str) -> None:
        self._check_open()
        if self.write_fail_with:
            exc = self.write_fail_with.pop(0)
            if exc is not None:
                raise exc
        self.writes.append(cmd)

    def query(self, cmd: str) -> str:
        self._check_open()
        # 按命令分派 (造"业务命令超时、但 SYST:ERR? 读得回来"的会话错位形态)
        if self.query_router is not None:
            return self.query_router(cmd)
        if self.query_fail_with:
            exc = self.query_fail_with.pop(0)
            if exc is not None:
                raise exc
        self.queries.append(cmd)
        if self.query_responses:
            return self.query_responses.pop(0)
        return self.query_response

    def close(self) -> None:
        self.closed = True


class _FakeResourceManager:
    """Hands out fake resources from a pre-built list — first call gets
    the first resource, the silent-reconnect call gets the next one.
    Test asserts which resource each command landed on."""

    def __init__(self, resources: List[_FakeVisaResource]) -> None:
        self._resources = resources
        self.open_calls: int = 0

    def open_resource(self, *_args, **_kwargs) -> _FakeVisaResource:
        self.open_calls += 1
        if not self._resources:
            raise OSError("test bug: open_resource called more times than fakes provided")
        return self._resources.pop(0)


def _mk_visa_error(code_unsigned: int) -> pyvisa.errors.VisaIOError:
    """Build a VisaIOError with the requested error_code so the driver's
    ``_is_visa_conn_lost`` sees what it expects.

    PyVISA's constructor signature varies a tiny bit by version; the
    safe path is to instantiate then poke error_code."""
    err = pyvisa.errors.VisaIOError(code_unsigned)
    return err


async def _noop_write(cmd: str, timeout: Any = None) -> None:
    """吞掉写命令的桩 (本文件的负缓存用例只关心查询次数)。"""
    return None


def _build_driver_with_fake_session(primary: _FakeVisaResource, *, post_reconnect: List[_FakeVisaResource] = None):
    """Construct a F64 driver wired to ``primary`` as its live resource
    and a fake RM that hands out ``post_reconnect`` when silent reconnect
    fires."""
    d = RealPropsimF64Driver(
        instrument_id="f64-test",
        config={"ip": "192.168.0.100", "port": 5025},
    )
    d._visa_resource = primary
    d._rm = _FakeResourceManager(list(post_reconnect or []))
    return d


# ---------------------------------------------------------------------------
# 1. Conn-lost shapes trigger reconnect
# ---------------------------------------------------------------------------

class TestConnLostTriggersReconnect:
    @pytest.mark.asyncio
    async def test_conn_lost_on_query_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF00B5)]  # VI_ERROR_CONN_LOST
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_response = "READY\n"

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        result = await d._do_query("*IDN?")
        assert result == "READY\n"
        # Old resource closed, new one used for the retry.
        assert primary.closed is True
        assert replacement.queries == ["*IDN?"]
        # Exactly one open_resource call (the silent reconnect).
        assert d._rm.open_calls == 1

    @pytest.mark.asyncio
    async def test_inv_object_on_write_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.write_fail_with = [_mk_visa_error(0xBFFF000E)]  # VI_ERROR_INV_OBJECT
        replacement = _FakeVisaResource("post-reconnect")

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        await d._do_write("INIT")
        assert replacement.writes == ["INIT"]
        assert primary.closed is True


# ---------------------------------------------------------------------------
# 2. Timeout MUST NOT trigger reconnect — Codex P2 lesson
# ---------------------------------------------------------------------------

class TestTimeoutDoesNotReconnect:
    """超时**本身**不触发重连 — 超时 ≠ 连接断 (仪器可能还在处理, 立刻重连会掩盖真问题),
    原始 VisaIOError 必须原样上抛让调用方 fail-loud。

    ⚠ F64R-1 后的边界细化: 超时会先走 `_drain_after_timeout` 轻量恢复;**只有排水也
    失败** (会话确实错位) 才升级重建会话 —— 那是"会话坏了"不是"这条超时了", 两回事。
    本类钉的是: **当次命令仍上抛原始超时、不重放**; 排水成功时更不该有任何重连。
    升级路径本身由 TestDrainFailureEscalatesToReconnect 钉。"""

    @pytest.mark.asyncio
    async def test_vi_error_tmo_on_query_propagates(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)]  # VI_ERROR_TMO

        d = _build_driver_with_fake_session(primary, post_reconnect=[])

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            await d._do_query("SYST:ERR?")
        # The exact error_code survived — caller can switch on it.
        assert (exc_info.value.error_code & 0xFFFFFFFF) == 0xBFFF0015
        # 当次命令不重放、不被重连"救活"成功: 原始超时照样上抛 (上面 raises 已钉)。
        # 本例 post_reconnect=[] → 升级重建也失败。此时**必须保留旧句柄**:
        # agent F1 —— 置 `_visa_resource=None` 是"从未连接"的语义, 会让所有入口的
        # `if not self._visa_resource: return` 把驱动短路成永久死态 (不发命令 → 不撞
        # 错 → 不再重连 → 网络恢复也不自愈)。断言写死这条契约。
        assert d._visa_resource is primary, "重建失败却把驱动打成了'未连接'死态"

    @pytest.mark.asyncio
    async def test_vi_error_tmo_on_write_propagates(self):
        primary = _FakeVisaResource("primary")
        primary.write_fail_with = [_mk_visa_error(0xBFFF0015)]

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_write("CALC:STAT ON")

    @pytest.mark.asyncio
    async def test_clean_drain_does_not_escalate_to_reconnect(self):
        """★ 排水**成功** (会话自愈) → 绝不重连。只有排水也失败才升级。"""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)]
        # 排水序列: 裸 read 立刻超时 (无残留) → SYST:ERR? 回 clean
        primary.read_fail_with = [_mk_visa_error(0xBFFF0015)]
        primary.query_responses = ['0,"No error"']

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("SYST:ERR?")
        assert d._rm.open_calls == 0, "排水已净却还是重连了"


class TestDrainFailureEscalatesToReconnect:
    """F64R-1: 排水**也失败** = 会话确实坏了 → 升级重建 (P0-1 遗留的"业务挂死不自动
    恢复"盲区: 原先只记一句"建议重载驱动", 现场就得人工重启后端)。"""

    @pytest.mark.asyncio
    async def test_drain_failure_rebuilds_session(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)]
        replacement = _FakeVisaResource("post-reconnect")

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        # 排水读不回 clean (fake 默认 "READY\n") → 判会话错位 → 升级
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("SYST:ERR?")
        assert d._rm.open_calls == 1, "排水失败后没升级重建会话"
        assert d._visa_resource is replacement, "新会话没接上"

    @pytest.mark.asyncio
    async def test_timed_out_command_is_not_replayed(self):
        """★ 重建后**不重放**当次命令 — 超时命令是否已到达仪器无从确认, 重放对
        GO/STATIC/FILE 这类有副作用的命令是危险的。当次仍上抛失败。"""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)]
        replacement = _FakeVisaResource("post-reconnect")

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("DIAG:SIMU:GO")
        assert replacement.queries == [], "在新会话上重放了超时命令 (可能双写)"


# ---------------------------------------------------------------------------
# 3. Non-VISA errors don't trigger reconnect
# ---------------------------------------------------------------------------

class TestNonVisaErrorsPropagate:
    @pytest.mark.asyncio
    async def test_plain_runtime_error_does_not_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [RuntimeError("test: not a VISA error")]

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        with pytest.raises(RuntimeError):
            await d._do_query("*IDN?")
        assert d._rm.open_calls == 0


# ---------------------------------------------------------------------------
# 4. Bounded retry — second conn-lost still raises (no infinite loop)
# ---------------------------------------------------------------------------

class TestRetryIsBounded:
    @pytest.mark.asyncio
    async def test_second_consecutive_conn_lost_raises(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF00B5)]
        # Post-reconnect resource ALSO conn-losts on the retry.
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_fail_with = [_mk_visa_error(0xBFFF00B5)]

        d = _build_driver_with_fake_session(primary, post_reconnect=[replacement])
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("*IDN?")
        # Reconnect happened exactly once — no third attempt.
        assert d._rm.open_calls == 1

    @pytest.mark.asyncio
    async def test_silent_reconnect_failure_surfaces_original(self):
        """When ``_silent_reconnect_visa`` itself can't reopen
        (e.g. rm.open_resource raises), the original conn-lost VISA
        error propagates — caller sees a meaningful exception, not a
        masked one."""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF00B5)]

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        # Empty post_reconnect list — RM.open_resource will raise OSError,
        # _silent_reconnect_visa returns False, original VisaIOError propagates.
        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            await d._do_query("*IDN?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == 0xBFFF00B5


# ---------------------------------------------------------------------------
# 5. Healthy path: no reconnect happens when nothing fails
# ---------------------------------------------------------------------------

class TestHealthyPathNoReconnect:
    @pytest.mark.asyncio
    async def test_successful_query_uses_same_session(self):
        primary = _FakeVisaResource("primary")
        primary.query_response = "PROPSIM,F64,SN12345\n"

        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        result = await d._do_query("*IDN?")
        assert result == "PROPSIM,F64,SN12345\n"
        assert d._rm.open_calls == 0  # never reconnected
        assert primary.closed is False
        assert primary.queries == ["*IDN?"]


# ---------------------------------------------------------------------------
# 6. _is_visa_conn_lost classifier unit tests
# ---------------------------------------------------------------------------

class TestIsVisaConnLostClassifier:
    def test_conn_lost_code_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(_mk_visa_error(0xBFFF00B5)) is True

    def test_inv_object_code_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(_mk_visa_error(0xBFFF000E)) is True

    def test_timeout_not_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(_mk_visa_error(0xBFFF0015)) is False

    def test_non_visa_error_not_recognised(self):
        d = RealPropsimF64Driver("t", {})
        assert d._is_visa_conn_lost(RuntimeError("not visa")) is False
        assert d._is_visa_conn_lost(ConnectionResetError("plain")) is False


# ---------------------------------------------------------------------------
# 6. F64R-1 (提交前审查 F1): 重连的速率限制与失败后的可恢复性
# ---------------------------------------------------------------------------

class TestReconnectRateLimit:
    """★ `get_metrics` 挂在 broadcaster 的 1 Hz 轮询上, 一轮要发十几条查询。仪器慢/
    挂死时**每条**都超时 → 排水失败 → 升级重连, 于是**一轮 poll 能重建 7 次 socket**
    (审查实测 open_calls=7)。重建不是免费的 (TCP 握手 + 旧句柄泄漏 + 全程持锁),
    还会掩盖"仪器需要人去看"的真相。30 s 冷却窗口, 与拓扑读路同规格。"""

    @pytest.mark.asyncio
    async def test_repeated_timeouts_rebuild_session_only_once(self):
        primary = _FakeVisaResource("primary")
        # 挂死仪器 = **每条**命令都超时 (含排水自己发的 SYST:ERR?) —— 正是本条限流
        # 要挡的场景; 只给 5 个错误的话会被排水提前吃光, 后面的查询反而"成功"了。
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)] * 500
        # 备用会话同样连不上 —— 仪器还挂着, 换根 socket 不会让它复活。备用是"好的"
        # 就变成"重建一次就恢复", 后面几轮根本不超时, 限流也就无从观察。
        spares = [_FakeVisaResource(f"spare-{i}") for i in range(5)]
        for s in spares:
            s.query_fail_with = [_mk_visa_error(0xBFFF0015)] * 500

        d = _build_driver_with_fake_session(primary, post_reconnect=spares)
        for _ in range(5):
            with pytest.raises(pyvisa.errors.VisaIOError):
                await d._do_query("DIAG:SIMU:STATE?")
        assert d._rm.open_calls == 1, (
            f"冷却窗口没生效 — 重建了 {d._rm.open_calls} 次 socket"
        )

    @pytest.mark.asyncio
    async def test_cooldown_expiry_allows_next_rebuild(self):
        """冷却是**限流**不是**熔断**: 窗口过了还坏, 就该再试一次。"""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)] * 500
        # 换上的会话同样是坏的 (仪器还没恢复), 才能观察到第二次重建
        spares = [_FakeVisaResource("spare-1"), _FakeVisaResource("spare-2")]
        for s in spares:
            s.query_fail_with = [_mk_visa_error(0xBFFF0015)] * 500

        d = _build_driver_with_fake_session(primary, post_reconnect=spares)
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("DIAG:SIMU:STATE?")
        assert d._rm.open_calls == 1
        d._reconnect_retry_after = 0.0          # 模拟 30 s 已过
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("DIAG:SIMU:STATE?")
        assert d._rm.open_calls == 2

    @pytest.mark.asyncio
    async def test_failed_rebuild_keeps_old_handle_and_can_recover(self):
        """★ 重建失败 → 保留旧句柄 → 网络恢复后**下一次**重建能成功自愈。
        (置 None 的旧写法在这里就永久卡死了: 后续命令根本不会再发出去。)"""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)] * 500
        d = _build_driver_with_fake_session(primary, post_reconnect=[])  # 开新的必失败

        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("DIAG:SIMU:STATE?")
        assert d._visa_resource is primary, "重建失败后驱动被打成'未连接'"
        # 旧句柄**已被关闭**是对的 (手册 §1.1.2.3 要求重连前先 viClose, 且 3334 只容
        # 一条远程 socket, 不关就开不出新的)。关键契约是"引用还在" —— 后续命令在已关
        # 句柄上抛 INV_OBJECT, 走 conn-lost 白名单触发下一轮重连, 网络恢复即自愈。
        assert primary.closed is True, "重连前没先关旧 socket (手册 §1.1.2.3)"

        # 网络恢复: 冷却窗口过后再来一次, 这次 RM 能给出新 resource
        recovered = _FakeVisaResource("recovered")
        recovered.query_fail_with = [_mk_visa_error(0xBFFF0015)] * 500
        d._rm._resources.append(recovered)
        d._reconnect_retry_after = 0.0
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("DIAG:SIMU:STATE?")
        assert d._visa_resource is recovered, "网络恢复后没能自愈"
        assert primary.closed is True, "换上新句柄后旧的没关 (句柄泄漏)"


class TestStateQueryNegativeCache:
    """STATE? 也在 1 Hz 路上。挂死仪器每轮吃满超时 + 排水 (最坏十几秒) 全程持锁 ——
    监控把 SCPI 通道占死, 测量步骤发不出命令 (现场"打开仪表盘 = 命令卡住"的形态)。
    读失败后 30 s 静默期, 期间退回缓存并标注降级; 读到真值立刻解除。"""

    @pytest.mark.asyncio
    async def test_metrics_stops_requerying_state_after_failure(self):
        d = RealPropsimF64Driver("f64-neg-cache", {})
        d._visa_resource = MagicMock()
        calls: list[str] = []

        async def _q(cmd, timeout=None):
            calls.append(cmd)
            if cmd == "DIAG:SIMU:STATE?":
                raise RuntimeError("instrument hung")
            return '0,"No error"'

        d._query = _q  # type: ignore[assignment]
        d._write = _noop_write  # type: ignore[assignment]

        await d.get_metrics()
        first = calls.count("DIAG:SIMU:STATE?")
        assert first >= 1
        await d.get_metrics()
        await d.get_metrics()
        assert calls.count("DIAG:SIMU:STATE?") == first, "失败负缓存没生效, 每轮都在重查"

    @pytest.mark.asyncio
    async def test_human_initiated_path_is_never_throttled(self):
        """★ 只有 1 Hz 轮询节流。人点一次 (GO/GOS/加载/旁路) 就该真去问一次仪器 ——
        操作员完全可能在静默期内从**前面板**改了状态, 那时驱动无从知情。"""
        d = RealPropsimF64Driver("f64-neg-cache-2", {})
        d._visa_resource = MagicMock()
        d._state_query_retry_after = time.monotonic() + 999   # 静默期正当中
        calls: list[str] = []

        async def _q(cmd, timeout=None):
            calls.append(cmd)
            return "RUNNING" if cmd == "DIAG:SIMU:STATE?" else '0,"No error"'

        d._query = _q  # type: ignore[assignment]
        # 静默期正当中: 节流路 (1 Hz 轮询) 早退, 人发起的路照样问仪器
        assert await d._query_simulation_state(throttle=True) is None
        assert calls == [], "节流路不该真发查询"
        assert await d._query_simulation_state() == "RUNNING"
        assert calls == ["DIAG:SIMU:STATE?"]
        # 而且读到真值就**解除**静默期 —— 静默是"仪器没反应"的负缓存, 不是熔断
        assert d._state_query_retry_after == 0.0
        assert await d._query_simulation_state(throttle=True) == "RUNNING"


class TestClosedHandleStillTriggersRecovery:
    """★ 复审 R1 (本轮最重的一条, 我自己引入的): 重连失败时保留的是一个**已 close**
    的句柄, 而 pyvisa 在已关闭 Resource 上抛的是 `InvalidSession` —— 它**不是**
    `VisaIOError` 的子类 (实测 pyvisa 1.16.2: `Resource.session` property 在
    `_session is None` 时先抛, 走不到 VISA C 库那层去返回 INV_OBJECT)。

    分类器漏了它 = 后续命令既不算 conn-lost 也不算 timeout → 既不排水也不重连 →
    **驱动永久死态**, 网络恢复也不自愈。我原注释断言"会抛 INV_OBJECT 所以能自愈"是
    错的, 而当时 fake 的 close() 只置个标志、照样按活 socket 作答, 正好把它盖住。"""

    @pytest.mark.asyncio
    async def test_invalid_session_classified_as_conn_lost(self):
        from app.hal._visa_reconnect import is_visa_conn_lost
        assert is_visa_conn_lost(pyvisa.errors.InvalidSession()) is True

    @pytest.mark.asyncio
    async def test_closed_handle_recovers_when_network_returns(self):
        """端到端: 重建失败留下已关句柄 → 下一条命令仍能触发重连 → 网络回来即自愈。"""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF00B5)]      # conn-lost
        d = _build_driver_with_fake_session(primary, post_reconnect=[])  # 开新必失败

        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("*IDN?")
        assert primary.closed is True and d._visa_resource is primary

        # 网络恢复: 冷却过后再发一条 —— 已关句柄抛 InvalidSession, 必须被识别成
        # conn-lost 才会走重连 (漏了它这里就永远发不出去)
        recovered = _FakeVisaResource("recovered")
        recovered.query_response = "PROPSIM,F64\n"
        d._rm._resources.append(recovered)
        d._reconnect_retry_after = 0.0
        assert await d._do_query("*IDN?") == "PROPSIM,F64\n", "已关句柄没能触发重连自愈"
        assert d._visa_resource is recovered

    @pytest.mark.asyncio
    async def test_successful_io_thaws_reconnect_cooldown(self):
        """真恢复的判据是"新会话上命令跑通"(不是"socket 开成功")—— 跑通即解冻,
        否则"断→恢复→30 s 内又断"的第二次会被冷却挡掉。"""
        primary = _FakeVisaResource("primary")
        primary.query_response = "OK\n"
        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        d._reconnect_retry_after = time.monotonic() + 999
        await d._do_query("*IDN?")
        assert d._reconnect_retry_after == 0.0

    @pytest.mark.asyncio
    async def test_teardown_skips_session_rebuild(self):
        """断开路撞超时不再重建 socket (给要关掉的连接续命纯属白等, 而 /hal/reload
        是串行调 disconnect 的)。"""
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(0xBFFF0015)] * 500
        d = _build_driver_with_fake_session(primary, post_reconnect=[_FakeVisaResource("s")])
        d._tearing_down = True
        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("DIAG:SIMU:STATE?")
        assert d._rm.open_calls == 0, "断开途中还去重建会话"


class TestDesyncFormAlsoRateLimited:
    """★ 复审 T1 (第三轮引入的回归, 实测 5 次重建 vs 1 次): 限流不能被**排水自己**解冻。

    会话错位形态 = 业务命令超时, 但排水的 `SYST:ERR?` **读得回来**且永远不 clean ——
    这正是 `_drain_after_timeout` 存在的理由, 也是**唯一**会升级重建会话的路径。
    若解冻挂在"任何一次 IO 成功"上, 排水那几条 SYST:ERR? 每条成功都把冷却清零, 紧跟着
    的升级检查自然放行 → 第一轮辛苦修掉的"每条超时重建一次 socket"在**最主要的触发
    路径**上原样回来。解冻只认**业务 IO**。

    ⚠ 原有的限流用例 (`query_fail_with=[TMO]*500`) 覆盖不到这一形态: 那里排水自己也抛,
    压根不会解冻。绿 ≠ 覆盖 —— 这条是变异实测补的。"""

    @staticmethod
    def _desync_router(cmd: str) -> str:
        if "SYST:ERR" in cmd:
            return '-200,"Execution error;Wrong device state"'   # 读得回来, 但不 clean
        raise _mk_visa_error(0xBFFF0015)                          # 业务命令超时

    @pytest.mark.asyncio
    async def test_desync_rebuilds_session_only_once(self):
        primary = _FakeVisaResource("primary")
        primary.query_router = self._desync_router
        primary.read_fail_with = [_mk_visa_error(0xBFFF0015)] * 50   # 裸 read 立刻超时
        spares = []
        for i in range(5):
            s = _FakeVisaResource(f"spare-{i}")
            s.query_router = self._desync_router
            s.read_fail_with = [_mk_visa_error(0xBFFF0015)] * 50
            spares.append(s)

        d = _build_driver_with_fake_session(primary, post_reconnect=spares)
        for _ in range(5):
            with pytest.raises(pyvisa.errors.VisaIOError):
                await d._do_query("DIAG:SIMU:STATE?")
        assert d._rm.open_calls == 1, (
            f"排水的 SYST:ERR? 把重连冷却解冻了 — 重建了 {d._rm.open_calls} 次 socket"
        )


class TestTearingDownFlagLifecycle:
    """`_tearing_down` 卡在 True 会**静默**关掉懒重连 + 超时升级 (只留一条 INFO)。
    复位必须在 `finally` 覆盖得到的地方 —— 两个 `except Exception` 挡不住
    `CancelledError`(BaseException), 而 /hal/reload 卡死后关标签页就会取消任务。"""

    @pytest.mark.asyncio
    async def test_session_reset_does_not_clear_flag_midway(self):
        """⚠ 复位**不能**放在 `_apply_session_reset()` 里 (agent U2): 它在 disconnect
        的**中途**(SCPI 段的 finally) 就被调到, 而后面还有释放 VISA 资源的尾段 —— 那里
        的 await 撞超时同样会去给一个正在关闭的连接重开 socket。保护窗口必须覆盖整个
        拆卸, 所以复位在 disconnect 最外层 finally + connect() 起始兜底。"""
        d = RealPropsimF64Driver("f64-td", {})
        d._tearing_down = True
        d._apply_session_reset()
        assert d._tearing_down is True, "会话复位提前关掉了拆卸保护窗口"

    @pytest.mark.asyncio
    async def test_connect_clears_stale_flag(self):
        """connect 是"要活过来了"的时点 —— 兜底清标志, 防极端路径 (CancelledError 把
        最外层 finally 也跳过) 让实例永久失去懒重连能力。

        用打桩让 RM 立刻抛错: 复位在 try **之前**, 连不连得上都该生效 (而真去连一个
        不可达地址会在 TCP 握手上挂几十秒)。"""
        from unittest.mock import patch

        d = RealPropsimF64Driver("f64-td2", {"ip": "192.0.2.1", "port": 3334})
        d._tearing_down = True
        with patch("pyvisa.ResourceManager", side_effect=OSError("no visa backend")):
            assert await d.connect() is False
        assert d._tearing_down is False

    @pytest.mark.asyncio
    async def test_flag_cleared_even_when_teardown_raises(self):
        """★ 断开途中抛异常 (含被取消) 也要复位 —— 否则该实例此后永久失去自愈能力。"""
        primary = _FakeVisaResource("primary")
        d = _build_driver_with_fake_session(primary, post_reconnect=[])

        async def _boom(cmd, timeout=None):
            raise RuntimeError("teardown blew up")

        d._query = _boom  # type: ignore[assignment]
        d._write = _boom  # type: ignore[assignment]
        await d.disconnect()
        assert d._tearing_down is False, "断开异常后拆卸标志卡住了, 懒重连被静默关闭"


class TestTearingDownCoversWholeTeardown:
    """保护窗口要覆盖**整个**拆卸 —— 释放 VISA 资源的尾段同样有 await, 撞超时一样会
    去重开 socket (给正在关闭的连接续命), 而 /hal/reload 是串行调 disconnect 的。"""

    @pytest.mark.asyncio
    async def test_flag_still_set_during_resource_release(self):
        primary = _FakeVisaResource("primary")
        d = _build_driver_with_fake_session(primary, post_reconnect=[])
        seen: list[bool] = []

        def _close_probe():
            seen.append(d._tearing_down)   # 尾段释放资源的那一刻, 标志还在吗

        primary.close = _close_probe  # type: ignore[assignment]

        async def _noop(cmd, timeout=None):
            return '0,"No error"' if "?" in cmd else None

        d._query = _noop  # type: ignore[assignment]
        d._write = _noop  # type: ignore[assignment]
        await d.disconnect()
        assert seen == [True], f"尾段释放资源时保护窗口已提前关闭: {seen}"
        assert d._tearing_down is False, "拆卸结束后标志没复位"
