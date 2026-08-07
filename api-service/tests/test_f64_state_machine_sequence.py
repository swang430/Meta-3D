"""F64 状态机语义探测剧本 (`propsim_f64_state_machine`) 的回归。

剧本的使命是**记录仪器说了什么**, 不是断言仪器该说什么 —— 所以这里的 fake 是一台
按手册行为建模的、可参数化的 F64, 测试断言的是:

  ① 该问的问了、不该发的没发 (先查状态再决定发不发, 手册 §20.5.2 + 现场实证);
  ② 仪器吐出来的字面值被**原样**记进 ``step.raw`` 与 ``extra``;
  ③ 拒绝在状态未知 / 未加载 / 瞬态时动手。

fake 的行为都能在真机上出现 (见 memory feedback_test_failure_may_mean_wrong_fake:
造不出的场景不该拿来逼生产代码放宽约束)。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from app.diagnostics.sequences.propsim_f64_state_machine import (
    classify_state,
    run as run_state_machine,
)


# ---------------------------------------------------------------------------
# 按手册建模的 F64 假仪表
# ---------------------------------------------------------------------------

class _FakeF64:
    """行为参照 PROPSIM ATE 手册:

    - ``DIAG:SIMU:GO`` 在 RUNNING 下被拒并压入 ``-200``(§20.5.2), 状态不变。
    - ``DIAG:SIMU:GOS`` 停止并倒回起点 → STOPPED(§20.4.3.11)。
    - ``DIAG:SIMU:MODEL:STATIC n`` 在 RUNNING/STOPPED 下都合法(ATE AN §2.4.5);
      退旁路(0)后若进旁路前在跑则继续跑。
    - ``STATE?`` 在旁路下报什么是**手册未定义**的 —— 故用 ``state_in_bypass``
      参数化, 剧本只负责如实记录。
    """

    SUPPORTS_STATIC_PASSTHROUGH = True

    def __init__(
        self,
        *,
        state: str = "STOPPED",
        bypass: str = "0",
        state_in_bypass: Optional[str] = None,
        state_after_gos: str = "STOPPED",
        state_raw_override: Optional[str] = None,
        bypass_raw_override: Optional[str] = None,
        go_rejected_in_bypass: bool = True,
        reject_cmds: Optional[set] = None,
    ) -> None:
        # 写这些命令时压一条 -200 (仪器**因为这条命令**报错, 区别于队列里的遗留错误)
        self._reject_cmds = reject_cmds or set()
        self.state = state
        self.bypass = bypass
        self._state_in_bypass = state_in_bypass
        self._state_after_gos = state_after_gos
        self._state_raw_override = state_raw_override
        self._bypass_raw_override = bypass_raw_override
        self._go_rejected_in_bypass = go_rejected_in_bypass
        self._was_running_before_bypass = False
        self.writes: List[str] = []
        self.errors: List[str] = []

    # -- SCPI ------------------------------------------------------------
    async def _write(self, cmd: str) -> None:
        self.writes.append(cmd)
        if cmd in self._reject_cmds:
            self.errors.append('-200,"Execution error;Wrong device state for command"')
            return
        if cmd == "*CLS":
            # 手册 §20.4.1.1: 只清队列/状态寄存器, 不碰仿真状态机。
            self.errors.clear()
        elif cmd == "DIAG:SIMU:GO":
            if self.state == "RUNNING":
                self.errors.append('-200,"Execution error;Wrong device state for command"')
            elif self.bypass != "0" and self._go_rejected_in_bypass:
                # 手册未定义"旁路态下 GO", 有 -200 风险 —— 建模成被拒, 用来钉住
                # "剧本必须先退旁路再 GO"这条 (现场收工稳态就是 STOPPED+STATIC3)。
                self.errors.append('-200,"Execution error;Wrong device state for command"')
            else:
                self.state = "RUNNING"
        elif cmd == "DIAG:SIMU:STOP":
            # §20.4.3.10 暂停, 不倒回。
            self.state = "STOPPED"
        elif cmd == "DIAG:SIMU:GOS":
            self.state = self._state_after_gos
        elif cmd.startswith("DIAG:SIMU:MODEL:STATIC "):
            mode = cmd.rsplit(" ", 1)[1]
            if mode == "0":
                self.bypass = "0"
                if self._was_running_before_bypass:
                    self.state = "RUNNING"
            else:
                self._was_running_before_bypass = self.state == "RUNNING"
                self.bypass = mode

    async def _query(self, cmd: str) -> str:
        if cmd == "DIAG:SIMU:STATE?":
            if self._state_raw_override is not None:
                return self._state_raw_override
            if self.bypass != "0" and self._state_in_bypass is not None:
                return self._state_in_bypass
            return self.state
        if cmd == "DIAG:SIMU:MODEL:STATIC?":
            if self._bypass_raw_override is not None:
                return self._bypass_raw_override
            return self.bypass
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            return self.errors.pop(0) if self.errors else '0,"No error"'
        raise AssertionError(f"剧本发了预期外的查询: {cmd!r}")


class _FakeHal:
    def __init__(self, ce: Any) -> None:
        self.drivers = {"channelEmulator": ce}


def _run(ce: Any, params: Optional[Dict[str, Any]] = None):
    # 用 asyncio.run 起一个自带的事件循环 —— `get_event_loop()` 会捡当前线程
    # 的循环, 全量顺序下别的测试早把它关了/换了, 单文件绿、全量红
    # (本文件初版实测 31 红)。同 memory feedback_test_logger_emit_alembic_pollution:
    # 顺序污染只有跑全量才暴露。
    logs: List[str] = []
    result = asyncio.run(
        run_state_machine(
            ctx=object(), hal=_FakeHal(ce), params=params or {}, log=logs.append,
        )
    )
    return result, logs


def _step(result, needle: str):
    matches = [s for s in result.steps if needle in s.label]
    assert matches, f"没有标签含 {needle!r} 的步骤; 实际: {[s.label for s in result.steps]}"
    return matches[0]


# ---------------------------------------------------------------------------


class TestClassifyState:
    """七态白名单 —— 判定必须与驱动同源, 否则剧本和驱动对同一台仪器结论不同。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("RUNNING", "RUNNING"),
            (" stopped ", "STOPPED"),
            ('"CLOSED"', "CLOSED"),
            ("OPENING", "OPENING"),
            ("STOPPING", "STOPPING"),
            ("EDITING", "EDITING"),
            ("CLOSING", "CLOSING"),
        ],
    )
    def test_seven_states_normalised(self, raw, expected):
        assert classify_state(raw)[0] == expected

    @pytest.mark.parametrize(
        "raw", ['0,"NO ERROR"', "BYPASS", "1", "", None, "RUNNING,EXTRA"],
    )
    def test_off_whitelist_is_none(self, raw):
        """会话错位的迟到应答绝不能被当成一个状态 —— F64R-1 加白名单的理由。"""
        state, note = classify_state(raw)
        assert state is None
        assert note, "白名单外必须给出说明, 否则操作员看不出为什么判不了"


class TestGuards:
    """状态未知 / 未加载 / 瞬态 → 一律不动手。"""

    def test_closed_aborts_without_writing(self):
        """CLOSED 要给**它自己的**指引: "去加载一个 .smu", 不是瞬态那句"等它稳定"。

        ⚠ 断言必须钉住这句指引 —— 只断言 "不写命令" + "summary 含 CLOSED" 会被
        下面那道更宽的 `not in _ACTIONABLE_STATES` 闸短路成空转 (变异实测: 去掉
        本分支测试照样绿)。这是 memory feedback_test_failure_may_mean_wrong_fake
        的姊妹坑: 绿≠覆盖, 被更晚的闸兜住的分支最容易假绿。
        """
        ce = _FakeF64(state="CLOSED")
        result, _ = _run(ce)
        assert result.success is False
        assert ce.writes == [], "CLOSED 下发任何控制命令都只会拿到 -200"
        assert ".smu" in result.summary, (
            "CLOSED = 未加载仿真, 指引应是'先加载一个 .smu', "
            f"不是瞬态态那套说辞; 实际: {result.summary}"
        )
        assert "瞬态" not in result.summary, "CLOSED 不是瞬态, 别给错指引"

    def test_closed_does_not_require_bypass_readback(self):
        """现场 F8800A 在 CLOSED 下不返回 MODEL:STATIC 档位。

        STATE? 已可靠返回 CLOSED 就证明 SCPI 通道正常；此时应直接提示加载
        仿真，而不是继续查询一个依赖已加载仿真的档位并误报“通道异常”。
        """
        class _ClosedF64(_FakeF64):
            def __init__(self):
                super().__init__(state="CLOSED")
                self.queries: List[str] = []

            async def _query(self, cmd: str) -> str:
                self.queries.append(cmd)
                if cmd == "DIAG:SIMU:MODEL:STATIC?":
                    return ""
                return await super()._query(cmd)

        ce = _ClosedF64()
        result, _ = _run(ce)

        assert result.success is False
        assert "SCPI 通道正常" in result.summary
        assert ".smu" in result.summary
        assert ce.queries == ["DIAG:SIMU:STATE?"], (
            "CLOSED 下 MODEL:STATIC? 没有有效语义，不应让它遮住已确认的 CLOSED"
        )
        assert ce.writes == []

    @pytest.mark.parametrize("state", ["OPENING", "STOPPING", "CLOSING", "EDITING"])
    def test_transient_states_abort_without_writing(self, state):
        ce = _FakeF64(state=state)
        result, _ = _run(ce)
        assert result.success is False
        assert ce.writes == [], f"{state} 是瞬态/占用态, 手册未定义此时下发的行为"

    def test_unreadable_state_aborts_without_writing(self):
        """会话错位时读到 `0,"NO ERROR"` —— 状态未知就动手是这条线一直在删的病。"""
        ce = _FakeF64(state_raw_override='0,"NO ERROR"')
        result, _ = _run(ce)
        assert result.success is False
        assert ce.writes == []
        assert result.extra["initial_state"] is None

    def test_missing_scpi_channel_refuses(self):
        class _NoScpi:
            pass

        result, _ = _run(_NoScpi())
        assert result.success is False
        assert "_query" in result.summary

    def test_mock_driver_refused(self):
        class MockChannelEmulator:
            pass

        result, _ = _run(MockChannelEmulator())
        assert result.success is False


class TestBypassModeValidation:
    @pytest.mark.parametrize("mode", [True, False, 0, 4, -1, "3", None, 1.5])
    def test_illegal_mode_refused_before_touching_instrument(self, mode):
        """JSON 的 true 会被 int() 静默变成 1 (开关 2 在 #216 踩过) —— bool 必须先拦。"""
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {"bypass_mode": mode})
        assert result.success is False
        assert "bypass_mode" in result.summary
        assert ce.writes == []

    @pytest.mark.parametrize("mode", [1, 2, 3])
    def test_legal_modes_accepted(self, mode):
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {"bypass_mode": mode, "probe_gos": False})
        assert f"DIAG:SIMU:MODEL:STATIC {mode}" in ce.writes


class TestGoDiscipline:
    def test_running_does_not_resend_go(self):
        """手册 §20.5.2: RUNNING 态再发 GO → -200 并累积, 极端会堵死通信。

        变异自验: 把剧本里 `if state == "STOPPED"` 的守卫去掉, 本条必红。
        """
        ce = _FakeF64(state="RUNNING")
        _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert "DIAG:SIMU:GO" not in ce.writes
        assert ce.errors == [], "不该产生 -200"

    def test_stopped_sends_go_once(self):
        ce = _FakeF64(state="STOPPED")
        _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert ce.writes.count("DIAG:SIMU:GO") == 1


class TestRawRecording:
    def test_raw_is_verbatim_not_normalised(self):
        """raw 的价值就在于保留仪器原样 —— 归一化是驱动的事, 不是归档的事。"""
        ce = _FakeF64(state="RUNNING", state_raw_override='  "RunNing"  ')
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        step = _step(result, "初始 STATE?")
        assert step.raw == '  "RunNing"  '
        assert step.detail == "RUNNING", "detail 给人读(归一化), raw 给对照(原样)"

    def test_bypass_state_literal_is_captured(self):
        """F64R-7② 的答案就是这个字面值 —— 手册七态里没有 BYPASS, 报什么全靠记。"""
        ce = _FakeF64(state="RUNNING", state_in_bypass="STOPPED")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert result.extra["state_in_bypass"] == "STOPPED"
        assert _step(result, "F64R-7②").raw == "STOPPED"

    def test_gos_state_literal_is_captured(self):
        ce = _FakeF64(state="RUNNING", state_after_gos="STOPPED")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.extra["state_after_gos"] == "STOPPED"
        assert _step(result, "F64R-7①").raw == "STOPPED"

    def test_gos_not_stopping_is_reported_not_masked(self):
        """现场注释记着"GOS 未观察到真停" —— 若真如此, 剧本要如实记 RUNNING,
        **不许**把它当成停住了 (那正是这一系列删掉的假成功)。"""
        ce = _FakeF64(state="RUNNING", state_after_gos="RUNNING")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.extra["state_after_gos"] == "RUNNING"

    def test_write_step_records_error_queue_raw(self):
        ce = _FakeF64(state="STOPPED")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert _step(result, "GO (STOPPED").raw == '0,"No error"'


class TestErrorQueueGate:
    def test_nonzero_error_fails_the_step(self):
        """`*OPC?` 只表示"执行过了"不表示"没出错"(§20.6.1.2) —— 错误队列必读。

        ⚠ 错误必须是**这条命令自己引发的**, 不能拿开跑前队列里的遗留错误当素材 ——
        那种现在会在开跑时被清掉 (见 TestErrorQueueHygiene), 拿它做素材的话这条
        用例会因为"清干净了"而失去意义。

        变异自验: 把 write_and_check 里的 `ok = code in (0, None)` 改成恒 True,
        本条必红。
        """
        ce = _FakeF64(state="STOPPED", reject_cmds={"DIAG:SIMU:GO"})
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert result.success is False
        assert _step(result, "GO (STOPPED").success is False


class TestRestore:
    def test_running_initial_is_resumed_after_gos(self):
        ce = _FakeF64(state="RUNNING", state_after_gos="STOPPED")
        result, _ = _run(ce, {"restore_initial_state": True})
        assert ce.state == "RUNNING"
        assert result.extra["state_after_restore"] == "RUNNING"

    def test_stopped_initial_is_not_resumed(self):
        """初始就是 STOPPED 的机器不该被剧本留在 RUNNING —— 剧本不改变操作员的意图。"""
        ce = _FakeF64(state="STOPPED", state_after_gos="STOPPED")
        _run(ce, {"restore_initial_state": True})
        assert ce.state == "STOPPED"

    def test_probe_gos_false_skips_gos(self):
        ce = _FakeF64(state="RUNNING")
        _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert "DIAG:SIMU:GOS" not in ce.writes


class TestBypassCapabilityGate:
    def test_driver_without_flag_skips_bypass(self):
        ce = _FakeF64(state="RUNNING")
        ce.SUPPORTS_STATIC_PASSTHROUGH = False
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert not any(w.startswith("DIAG:SIMU:MODEL:STATIC") for w in ce.writes)
        assert _step(result, "旁路探测 (跳过)").success is True


# ===========================================================================
# 以下用例来自 2026-07-26 提交前审查 agent 的变异实测: 它做了 10 处变异, 其中
# **8 处我的测试全绿没抓到**。每一条对应一个当时空转的点 —— 注释里写清"改哪行会红"。
# 教训: 我自己那轮只做了 6 处变异, 覆盖的是我"想到要防"的; 空转的恰恰是我没想到的。
# ===========================================================================


class TestMutationGapsFromReview:

    def test_mock_refusal_names_the_driver(self):
        """M1: 删掉 mock 拒绝门 → 会落到"没有 SCPI 通道"那条, success 同样是 False,
        所以只断言 success 会空转。必须钉住**拒绝理由**。"""
        class MockChannelEmulator:
            async def _query(self, cmd): return "RUNNING"
            async def _write(self, cmd): return None

        result, _ = _run(MockChannelEmulator())
        assert result.success is False
        assert "mock" in result.summary.lower(), (
            f"应说明是 mock 驱动而非缺 SCPI 通道; 实际: {result.summary}"
        )

    def test_failing_step_makes_overall_verdict_false(self):
        """M2: 最终判定 `ok = all(...)` 改成恒 True 时全绿 —— 没有用例让"流程跑完
        但中间有步骤失败"。这里造一个: 旁路回读返回空串 → 该步失败, 总判定必须 False。"""
        ce = _FakeF64(state="RUNNING", bypass_raw_override="")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert any(not s.success for s in result.steps), "应有失败步骤"
        assert result.success is False, "有步骤失败时总判定不能报成功"

    def test_initial_bypass_is_read_and_recorded(self):
        """M3: 删掉初始 MODEL:STATIC? 读 → 全绿。它不是可有可无的:
        开跑时的旁路档决定了要不要先退旁路, 也决定收工恢复成什么。"""
        ce = _FakeF64(state="RUNNING", bypass="2", go_rejected_in_bypass=False)
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert result.extra["initial_bypass"] == "2"
        assert _step(result, "初始 MODEL:STATIC?").raw == "2"

    def test_bypass_exit_readbacks_are_recorded(self):
        """M4: 删掉退旁路后的两条回读 → 全绿。而"退旁路后是否自动恢复播放"正是
        手册承诺、需要在真机上验证的一条。"""
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert result.extra["state_after_bypass_exit"] == "RUNNING", "手册: 进旁路前在跑 → 退旁路后继续跑"
        assert result.extra["bypass_after_exit"] == "0"

    def test_bypass_is_actually_exited(self):
        """M5: 退旁路命令根本不发 → 全绿。最严重的一条 —— 剧本会把仪器**留在旁路里**
        (衰落被旁路掉), 下一个测试步骤全是错的还没人知道。"""
        ce = _FakeF64(state="RUNNING")
        _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert "DIAG:SIMU:MODEL:STATIC 0" in ce.writes
        assert ce.bypass == "0", "剧本跑完不能把仪器留在旁路里"

    def test_unreadable_bypass_fails_its_step(self):
        """M6: read_bypass 成功判据恒 True → 全绿。空回复必须判失败,
        否则"读不到旁路档"会被当成"读到了"。"""
        ce = _FakeF64(state="RUNNING", bypass_raw_override="")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert _step(result, "初始 MODEL:STATIC?").success is False

    def test_query_exception_leaves_raw_none_not_empty(self):
        """M8: 异常分支把 raw 填成空串 → 全绿。但 None(没拿到回复) 与 ""(仪器回了空)
        是**两个不同的结论**, 归档时混了就再也分不出来。"""
        class _Boom(_FakeF64):
            async def _query(self, cmd):
                if cmd == "DIAG:SIMU:STATE?":
                    raise TimeoutError("VI_ERROR_TMO")
                return await super()._query(cmd)

        result, _ = _run(_Boom(state="RUNNING"))
        step = _step(result, "初始 STATE?")
        assert step.success is False
        assert step.raw is None, "查询压根没拿到回复时 raw 必须是 None, 不是空串"

    def test_giving_up_restore_is_recorded_as_failure(self):
        """M9: 恢复分支的"放弃"记成成功 → 全绿。放弃恢复意味着**仪器被留在了
        跟接手时不一样的状态**, 这必须让操作员看见, 不能算成功收工。"""
        ce = _FakeF64(state="RUNNING", state_after_gos="EDITING")
        result, _ = _run(ce, {"restore_initial_state": True})
        give_up = _step(result, "恢复 (放弃)")
        assert give_up.success is False
        assert result.success is False
        # 放弃时必须把"接手时是什么 / 现在是什么"都写清楚, 否则人没法手动收拾
        assert "接手时" in give_up.detail and "EDITING" in give_up.detail


class TestOnSiteSteadyState:
    """现场收工稳态 = 「STOPPED + STATIC 3」, 下次开机第一件事就是在这个状态下跑本剧本。
    审查实测: 改之前剧本会在这里直接失败 (旁路态下盲发 GO)。"""

    def test_exits_bypass_before_go(self):
        ce = _FakeF64(state="STOPPED", bypass="3")
        result, _ = _run(ce, {"probe_gos": False})
        assert result.success is True, f"现场最常见的初始态不该失败: {result.summary}"
        exit_idx = ce.writes.index("DIAG:SIMU:MODEL:STATIC 0")
        go_idx = ce.writes.index("DIAG:SIMU:GO")
        assert exit_idx < go_idx, "必须先退旁路再 GO — 手册未定义旁路态下 GO 的行为"

    def test_bypass_mode_restored_at_end(self):
        """审查实测 E: 初始 STATIC 3 跑完变成 0 —— 衰落被放回来了, 已 attach 的手机
        可能当场掉线。收工必须还原成接手时的档位。"""
        ce = _FakeF64(state="STOPPED", bypass="3")
        _run(ce, {"probe_gos": False, "restore_initial_state": True})
        assert ce.bypass == "3", "跑完必须把旁路档还原成接手时的值"

    def test_restore_order_is_state_then_bypass(self):
        """手册纠正过我的顺序: 设 STATIC≠0 本身会暂停仿真, 所以必须**先恢复运行态,
        再恢复旁路档**, 反过来会让底层状态机跟物理状态打架。

        用 probe_gos=False 造场景: 初始 STOPPED 被剧本 GO 起来后没有 GOS 把它停回去,
        收工时"当前 RUNNING vs 初始 STOPPED"→ 必须补一条 STOP, 才有顺序可验。
        """
        ce = _FakeF64(state="STOPPED", bypass="3")
        _run(ce, {"probe_gos": False, "restore_initial_state": True})
        restore_bypass = len(ce.writes) - 1 - ce.writes[::-1].index("DIAG:SIMU:MODEL:STATIC 3")
        stop_idx = ce.writes.index("DIAG:SIMU:STOP")
        assert stop_idx < restore_bypass, "恢复顺序必须是先运行态、后旁路档"
        assert ce.state == "STOPPED" and ce.bypass == "3", "收工要跟接手时严丝合缝"

    def test_restore_uses_stop_not_gos(self):
        """复位运行态用 STOP(暂停不倒回, §20.4.3.10), 不用 GOS —— 剧本自己不该
        多倒一次带, 那会额外破坏仿真进度。"""
        ce = _FakeF64(state="STOPPED", bypass="0")
        _run(ce, {"probe_gos": False, "restore_initial_state": True})
        assert "DIAG:SIMU:STOP" in ce.writes
        assert "DIAG:SIMU:GOS" not in ce.writes


class TestErrorQueueHygiene:
    def test_stale_error_does_not_fail_this_run(self):
        """审查实测 C: 队列里有一条别人留下的旧错误时, 剧本第一条 GO 之后读到的是
        **那条旧的**, 一次成功的 GO 被判成失败。开跑前必须清干净。"""
        ce = _FakeF64(state="STOPPED")
        ce.errors.append('-200,"Execution error;Wrong device state for command"')
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert "*CLS" in ce.writes
        assert _step(result, "GO (STOPPED").success is True, (
            "开跑前的遗留错误不该算到本次 GO 头上"
        )
        assert _step(result, "排空错误队列").raw is not None, "清掉的旧错误要留痕"

    def test_clean_queue_records_no_raw(self):
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert _step(result, "排空错误队列").raw is None


class TestSummaryCarriesAnswers:
    def test_literal_answers_are_in_summary(self):
        """归档在 2048 字节处截断且保头部, 一轮完整探测已 ~1959 字节 —— 关键字面值
        必须放进 summary(永远排最前), 否则下次现场拿归档对照时答案已经被切掉了。"""
        ce = _FakeF64(state="RUNNING", state_in_bypass="STOPPED", state_after_gos="RUNNING")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert "GOS后='RUNNING'" in result.summary
        assert "旁路下='STOPPED'" in result.summary

    def test_summary_keeps_raw_not_normalised(self):
        """⭐ 摘要里必须是**仪器原样**, 不是归一化值 —— 下次现场做的是字面比对,
        `RUNNING` 和 `  "RunNing"  ` 对这件事是两回事 (Codex #229 P2)。"""
        ce = _FakeF64(state="RUNNING", state_raw_override='  "RunNing"  ')
        result, _ = _run(ce, {"restore_initial_state": False})
        assert '  "RunNing"  ' in result.summary, (
            f"摘要丢了原始字面值: {result.summary}"
        )


class TestBypassModeTypeStrictness:
    def test_float_is_rejected(self):
        """审查实测 B: `3.0 in (1,2,3)` 为真 → 会发出 `DIAG:SIMU:MODEL:STATIC 3.0`
        这条畸形命令。JSON 数字没有整型/浮点之分, 得连类型一起卡。"""
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {"bypass_mode": 3.0})
        assert result.success is False
        assert ce.writes == []


# ===========================================================================
# UXM 手册写法探针 —— 验"我们没在用的拼法"
# ===========================================================================

class TestUxmManualSpellingProbe:
    """兄弟序列 uxm_scpi_compatibility 枚举的是驱动表里已有的命令, 标 None 的会跳过
    → 结构上验不出"我们当年拼错了"。本探针专治这个 (P0-2 S4)。"""

    class _FakeUxm:
        """⚠ `_cmds` 必须是**真的命令方言实例** —— 真驱动就是这样
        (`RealUxmDriver._cmds` 自 PR #44 起是 `UxmTestApp` 子类的实例)。
        拿个同名字段的普通类冒充, `_profile_for_driver` 会合理地回退到 5G_NR_Test
        方言(主小区 CELL0), 于是测试测的是另一套方言 —— 造不出的 fake 会把结论带偏
        (memory feedback_test_failure_may_mean_wrong_fake)。现场那台跑的是 IRAT。"""

        def __init__(self, *, supported: Optional[set] = None):
            from app.hal.uxm_command_profiles import UxmLteNrIratProfile
            # supported = 认得的命令头集合; 其余回 -113 (固件里没这条)
            self._supported = supported if supported is not None else set()
            self.queries: List[str] = []
            self._pending_err = '0,"No error"'
            self._cmds = UxmLteNrIratProfile()

        async def _query(self, cmd: str) -> str:
            if cmd == "SYST:ERR?":
                err, self._pending_err = self._pending_err, '0,"No error"'
                return err
            self.queries.append(cmd)
            head = cmd.split("?")[0]
            if head in self._supported:
                return "42"
            self._pending_err = '-113,"Undefined header"'
            return ""

    def _run_probe(self, bs, params=None):
        from app.diagnostics.sequences.uxm_manual_spelling_probe import run as run_probe
        logs: List[str] = []
        result = asyncio.run(
            run_probe(ctx=object(), hal=_FakeHal2(bs), params=params or {}, log=logs.append)
        )
        return result, logs

    def test_probes_the_manual_spelling_not_ours(self):
        """核心: 探针发的必须是**手册写法**, 而不是驱动表里那条。
        我们查小区状态用的是 `...ACTive:STATe?` (自己写的开关), 手册是
        `BSE:STATus:NR5G:CELL1?` —— 探针必须发后者。"""
        bs = self._FakeUxm()
        _r, _ = self._run_probe(bs)
        assert "BSE:STATus:NR5G:CELL1?" in bs.queries
        assert not any("ACTive:STATe" in q for q in bs.queries), (
            "探针不该去发驱动已经在用的那条 —— 那是兄弟序列的活"
        )

    def test_unsupported_is_a_finding_not_a_failure(self):
        """非关键项回 -113 是**有效结论**('固件真没这条'), 不该让整轮报失败。"""
        bs = self._FakeUxm(supported={
            "BSE:STATus:NR5G:CELL1", "BSE:CONFig:NR5G:APPLY",
        })
        result, _ = self._run_probe(bs)
        assert result.success is True
        assert result.extra["critical_unsupported"] == []
        assert any(not s.success for s in result.steps), "应有 -113 的步骤"

    def test_critical_unsupported_fails_the_run(self):
        """小区状态查询若真不支持, P0-2 D1 就落不了地 —— 必须当场亮红。"""
        bs = self._FakeUxm(supported=set())
        result, _ = self._run_probe(bs)
        assert result.success is False
        assert "CELL_STATUS" in result.extra["critical_unsupported"]

    def test_reply_recorded_verbatim(self):
        """能用只是第一步 —— "它返回什么"决定能不能拿它当真值源。"""
        class _WithState(self._FakeUxm):
            async def _query(self, cmd):
                if cmd == "BSE:STATus:NR5G:CELL1?":
                    self.queries.append(cmd)
                    return "CONNected"
                return await super()._query(cmd)

        bs = _WithState(supported={"BSE:CONFig:NR5G:APPLY"})
        result, _ = self._run_probe(bs)
        cell_step = [s for s in result.steps if s.label.startswith("CELL_STATUS")][0]
        assert cell_step.raw == "CONNected"

    def test_cell_param_overrides_profile_default(self):
        bs = self._FakeUxm()
        _r, _ = self._run_probe(bs, {"cell": "CELL2"})
        assert any("NR5G:CELL2" in q for q in bs.queries)
        assert not any("NR5G:CELL1?" in q for q in bs.queries)

    def test_mock_driver_refused(self):
        class MockBaseStation:
            async def _query(self, cmd): return "x"

        result, _ = self._run_probe(MockBaseStation())
        assert result.success is False
        assert "mock" in result.summary.lower()


class _FakeHal2:
    def __init__(self, bs: Any) -> None:
        self.drivers = {"baseStation": bs}


# ===========================================================================
# 第二轮审查 findings 的回归 (F1-F8)。⚠ F1-F4 全部是**上一轮修复引入的** ——
# 修复本身也会带缺陷, 这就是为什么"修完必须钉住", 不能靠"改动很小"放行。
# ===========================================================================

class TestReviewRound2:

    def test_f1_mid_failure_still_restores_bypass(self):
        """F1 [P1]: 现场收工稳态 STOPPED+STATIC3 → 先退旁路(成功, 衰落已放回)
        → GO 被拒(现场常见) → 旧写法裸 return, 把仪器留在 STATIC 0,
        已 attach 的手机当场掉线, 而 summary 只字不提旁路档被改过。"""
        ce = _FakeF64(state="STOPPED", bypass="3", reject_cmds={"DIAG:SIMU:GO"})
        result, _ = _run(ce, {"restore_initial_state": True})
        assert result.success is False
        assert ce.bypass == "3", "中途失败也必须把旁路档还原 —— 否则衰落被放回来"
        assert "GO 被拒" in result.summary, "中止原因要排在 summary 最前"
        assert any("恢复旁路档" in s.label for s in result.steps)

    def test_f1_exception_path_also_restores(self):
        """外层异常路径同理 —— 恢复段必须在 try 之外。"""
        class _BoomOnGos(_FakeF64):
            async def _write(self, cmd):
                if cmd == "DIAG:SIMU:GOS":
                    raise RuntimeError("VISA 断了")
                return await super()._write(cmd)

        ce = _BoomOnGos(state="STOPPED", bypass="2")
        result, _ = _run(ce, {"restore_initial_state": True})
        assert result.success is False
        assert ce.bypass == "2", "异常路径也要还原旁路档"

    def test_f2_unreadable_bypass_aborts_like_state(self):
        """F2 [P2]: 旁路档读不到跟状态读不到同等严重 —— 之前只有状态那条会中止,
        旁路那条放行 → 仪器实际在 STATIC 3 却被当成 0, 不退旁路就 GO, 收工也不还原。"""
        ce = _FakeF64(state="RUNNING", bypass_raw_override="")
        result, _ = _run(ce)
        assert result.success is False
        assert ce.writes == [], "旁路档未知就不该动手"
        assert "MODEL:STATIC?" in result.summary

    def test_f3_bypass_readback_offwhitelist_never_reaches_a_write(self):
        """F3 [P2]: 会话错位的迟到应答被原样拼回 `MODEL:STATIC {值}` → 畸形命令。
        入参已经严到卡类型, 仪器回读值没道理免检。"""
        ce = _FakeF64(state="RUNNING", bypass_raw_override='0,"NO ERROR"')
        result, _ = _run(ce)
        assert result.success is False
        assert not any("NO ERROR" in w for w in ce.writes), "白名单外的值绝不能进写命令"

    def test_f4_transient_after_bypass_exit_aborts(self):
        """F4 [P2]: 入口闸只守了第一次读。退旁路可能触发状态迁移, 重读若得到瞬态
        (或期间有人卸了仿真), 旧写法会继续往瞬态里发 STATIC/GOS —— 正是 docstring
        声明"不碰"的态; 而且 else 分支还会谎报"已是 RUNNING"。"""
        class _TransientAfterExit(_FakeF64):
            async def _write(self, cmd):
                await super()._write(cmd)
                if cmd == "DIAG:SIMU:MODEL:STATIC 0" and self.state == "STOPPED":
                    self.state = "STOPPING"   # 退旁路触发的过渡态

        ce = _TransientAfterExit(state="STOPPED", bypass="3")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.success is False
        assert "STOPPING" in result.summary
        assert "DIAG:SIMU:GO" not in ce.writes, "瞬态下不该继续发控制命令"

    def test_f4_go_skip_message_prints_real_state(self):
        """同 F4: "已是 RUNNING" 曾是硬编码, 闸一旦失效就变成谎报。"""
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert "已是 RUNNING" in _step(result, "GO (跳过)").detail


class TestUxmProbeRound2:

    def _probe(self, bs, params=None):
        from app.diagnostics.sequences.uxm_manual_spelling_probe import run as run_probe
        logs: List[str] = []
        return asyncio.run(
            run_probe(ctx=object(), hal=_FakeHal2(bs), params=params or {}, log=logs.append)
        ), logs

    def _make(self, **kw):
        return TestUxmManualSpellingProbe._FakeUxm(**kw)

    def test_f5_stale_error_cleared_before_probing(self):
        """F5 [P2]: 队列里的遗留 -113 会被算到第一条候选头上 —— 而第一条恰是
        _CRITICAL 的 CELL_STATUS → 整轮误报"关键项不可用"。同轮刚在 F64 上修过
        的坑, 新文件没继承。"""
        bs = self._make(supported={"BSE:STATus:NR5G:CELL1"})
        bs._pending_err = '-113,"Undefined header"'   # 别人留下的
        bs.writes = []
        result, _ = self._probe(bs)
        assert result.extra["critical_unsupported"] == [], (
            "开跑前的遗留错误不该让关键项误判"
        )
        assert result.extra["stale_errors_cleared"], "清掉的遗留错误要留痕"

    def test_f6_non_bse_dialect_refuses(self):
        """F6 [P2]: 12 条写法的根硬编码 BSE:, 且手册里 BSE:STATus 的 banding
        没有 CELL0。在 5G_NR_Test 方言上跑会 12 条全 -113 → 得出"手册写法也不支持"
        的错结论 —— 而这正是本序列要治的病, 自己踩上去就荒唐了。"""
        from app.hal.uxm_command_profiles import Uxm5GNRTestAppProfile

        bs = self._make()
        bs._cmds = Uxm5GNRTestAppProfile()
        result, _ = self._probe(bs)
        assert result.success is False
        assert "LTE_NR_IRAT" in result.summary
        assert bs.queries == [], "方言不对就不该发任何候选"

    def test_f6_illegal_cell_token_refused(self):
        bs = self._make()
        result, _ = self._probe(bs, {"cell": "CELL0"})
        assert result.success is False
        assert bs.queries == []

    def test_f7_channel_abort_is_not_success(self):
        """F7 [P2]: 通道断在第一条时 critical_unsupported 还是空 → 旧写法报**成功**,
        summary 却说"0/12 条可用" —— 归档里看起来像"跑过了, 结论是都不支持"。"""
        class _DiesAfterFirst(TestUxmManualSpellingProbe._FakeUxm):
            def __init__(self):
                super().__init__()
                self._n = 0

            async def _query(self, cmd):
                if cmd == "SYST:ERR?":
                    self._n += 1
                    if self._n > 1:      # 第 1 次是开跑前清队列, 之后就断
                        raise TimeoutError("VI_ERROR_TMO")
                return await super()._query(cmd)

        result, _ = self._probe(_DiesAfterFirst())
        assert result.success is False, "通道中断没跑完不能报成功"
        assert result.extra["aborted"] is True
        assert "中断" in result.summary

    def test_f8_apply_candidate_removed(self):
        """F8 [P2]: `BSE:CONFig:NR5G:APPLY` 手册标 `Immediate Action / No query`,
        查询节点本就不存在 —— 回 -113 是正确行为却会被判 UNSUPPORTED, 得出
        "这台机器不能 apply"的错结论; 若固件真执行了, "全部只读"当场破产。"""
        from app.diagnostics.sequences.uxm_manual_spelling_probe import (
            _CANDIDATES, _CRITICAL,
        )
        names = {c[0] for c in _CANDIDATES}
        assert "APPLY_HEADER" not in names
        assert _CRITICAL == {"CELL_STATUS"}
        assert not any("APPLY" in c[1] for c in _CANDIDATES)


class TestCodexRound229:
    """PR #229 Codex 的 6 条 (3×P1 + 3×P2)。其中 3 条**又是我上一轮修复引入的** ——
    同一块恢复逻辑连续三轮出问题, 所以这轮把它从"打补丁"改成"对着目标态收敛"。"""

    def test_p1_restores_bypass_zero_when_exit_failed(self):
        """P1: 初始就是 STATIC 0 → 进探测旁路 → **退旁路那步失败** → 旧写法的恢复段
        只在 `initial_bypass != "0"` 时才动, 于是仪器被留在 1/2/3 档没人管。
        根因是"假设主流程已经成功退过旁路"。"""
        # ⚠ 退旁路只失败**一次**(瞬时被拒), 否则谁也救不回来 —— 造一个"永远拒绝"的
        # 仪表去逼生产代码, 属于 memory feedback_test_failure_may_mean_wrong_fake
        # 说的那种造不出的场景。这里要验的是"恢复段会不会去管初始档为 0 的情况"。
        class _RejectExitOnce(_FakeF64):
            _rejected = False

            async def _write(self, cmd):
                if cmd == "DIAG:SIMU:MODEL:STATIC 0" and not self._rejected:
                    self._rejected = True
                    self.writes.append(cmd)
                    self.errors.append('-200,"Execution error;Wrong device state for command"')
                    return
                return await super()._write(cmd)

        ce = _RejectExitOnce(state="RUNNING", bypass="0")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": True})
        assert ce.bypass == "0", "初始档是 0 也必须恢复到 0"
        assert result.success is False, "中间那步失败要如实报出来"
        assert any("恢复旁路档" in s.label for s in result.steps)

    def test_p1_unstable_state_touches_nothing_but_reports_both(self):
        """P1: 恢复前状态不稳(瞬态/读不到)时, 旧写法仍会去写 `MODEL:STATIC` ——
        而那条命令按本剧本采用的手册约束只在 RUNNING/STOPPED 下有定义。
        现在两样都不动, 但要把"接手时 vs 现在"都报出来让人手动收拾。"""
        ce = _FakeF64(state="RUNNING", bypass="3", state_after_gos="OPENING")
        result, _ = _run(ce, {"restore_initial_state": True})
        step = _step(result, "恢复 (放弃)")
        assert step.success is False
        assert "接手时" in step.detail and "旁路档=3" in step.detail
        # 关键: 状态不稳时不许**再**发旁路写命令。探测段自己那一次 STATIC 3 是它的
        # 本职工作, 算进来就把断言写歪了 —— 要数的是"恢复阶段有没有多发一次"。
        assert ce.writes.count("DIAG:SIMU:MODEL:STATIC 3") == 1, (
            f"探测写 1 次是正常的, 恢复阶段不该再写; 实际 writes={ce.writes}"
        )

    def test_p1_unparseable_error_reply_is_failure(self):
        """P1: `SYST:ERR?` 回空串/畸形 → `_parse_err` 给 code=None, 旧写法跟"明确的 0"
        一样判成功 → 这条写命令**根本没经过错误队列确认**就往下走了。"""
        class _GarbledErr(_FakeF64):
            async def _query(self, cmd):
                if cmd == "SYST:ERR?" and self.writes.count("DIAG:SIMU:GO"):
                    return ""      # 超时后的空回复
                return await super()._query(cmd)

        ce = _GarbledErr(state="STOPPED")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert _step(result, "GO (STOPPED").success is False
        assert result.success is False

    def test_p2_go_must_actually_reach_running(self):
        """P2: 错误队列干净 ≠ 真起来了。若 GO 后状态仍是 STOPPED, 后面记的
        "旁路下/GOS 之后"就不是运行态语义, 结论作废还不自知。"""
        class _GoDoesNothing(_FakeF64):
            async def _write(self, cmd):
                if cmd == "DIAG:SIMU:GO":
                    self.writes.append(cmd)   # 收下但状态不变, 也不报错
                    return
                return await super()._write(cmd)

        ce = _GoDoesNothing(state="STOPPED")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.success is False
        assert "而不是 RUNNING" in result.summary
        assert "DIAG:SIMU:GOS" not in ce.writes, "没真起来就不该继续探测"


class TestUxmProbeCodex229:
    def test_p2_no_reply_with_clean_queue_is_not_supported(self):
        """P2: 查询没回话 + 错误队列却干净 = 两头都没结论(典型是瞬时 VISA 超时,
        命令可能压根没送到)。判成 SUPPORTED 的后果特别坏 —— 关键的 CELL_STATUS
        会让整轮报成功, 而我们**从没拿到过一个能当状态真值源的值**。"""
        class _SilentButClean(TestUxmManualSpellingProbe._FakeUxm):
            async def _query(self, cmd):
                if cmd == "SYST:ERR?":
                    return '0,"No error"'      # 队列永远干净
                self.queries.append(cmd)
                raise TimeoutError("VI_ERROR_TMO")   # 查询永远不回话

        from app.diagnostics.sequences.uxm_manual_spelling_probe import run as run_probe
        logs: List[str] = []
        result = asyncio.run(
            run_probe(ctx=object(), hal=_FakeHal2(_SilentButClean()),
                      params={}, log=logs.append)
        )
        assert result.success is False, "关键项没拿到回复不能报成功"
        assert "CELL_STATUS" in result.extra["critical_unsupported"]
        assert result.extra["supported"] == []


class TestCodexRound229B:
    """Codex 第二轮 4 条。两条 P1 跟第一轮是**同一个母题的不同站点** ——
    "错误队列干净 ≠ 命令真生效"。我第一轮只在 GO 后加了校验, 没加到对称的
    退旁路后 / 三个恢复写。这轮把校验折进回读本身 (`expect=`), 不再逐点补。

    ⚠ 关键设计: 传 `expect` = 目标已知(该核); 不传 = **待测未知量**(旁路下 /
    GOS 之后报什么)。给待测量传期望值 = 预设答案, 本剧本就白写了。
    """

    def test_p1_bypass_exit_must_reach_running(self):
        """退旁路后手册承诺应恢复 RUNNING —— 那是**已知目标**。核不上就不能继续发
        GOS: GOS 观测的前提是"从 RUNNING 出发", 前提不成立结论作废。"""
        class _ExitLeavesStopped(_FakeF64):
            async def _write(self, cmd):
                await super()._write(cmd)
                if cmd == "DIAG:SIMU:MODEL:STATIC 0":
                    self.state = "STOPPED"      # 没按手册恢复播放

        ce = _ExitLeavesStopped(state="RUNNING")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.success is False
        assert "DIAG:SIMU:GOS" not in ce.writes, "前提不成立就不该继续观测 GOS"
        assert "而不是手册承诺的 RUNNING" in result.summary

    def test_p1_recovery_writes_are_verified(self):
        """恢复的 GO/STOP/旁路档 若"错误队列干净但状态没变", 旧写法照样记绿,
        整轮报成功而仪器还停在错的态。"""
        class _RestoreGoDoesNothing(_FakeF64):
            async def _write(self, cmd):
                if cmd == "DIAG:SIMU:GO" and self.writes.count("DIAG:SIMU:GOS"):
                    self.writes.append(cmd)     # 恢复阶段那次 GO: 收下但不生效
                    return
                return await super()._write(cmd)

        ce = _RestoreGoDoesNothing(state="RUNNING", state_after_gos="STOPPED")
        result, _ = _run(ce, {"restore_initial_state": True})
        assert result.success is False, "恢复没真生效不能报成功"
        assert any("期望 RUNNING" in s.detail for s in result.steps)

    def test_probe_values_must_not_be_gated_on_expectation(self):
        """⭐ 反向保护: 两个**待测量**绝不能被拿期望值卡掉。
        真机若真的在旁路下报 STOPPED、GOS 之后报 RUNNING(正是我们怀疑的那个固件
        行为), 剧本必须**如实记录**而不是判失败 —— 否则等于预设了答案。"""
        ce = _FakeF64(state="RUNNING", state_in_bypass="STOPPED", state_after_gos="RUNNING")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert _step(result, "F64R-7②").success is True, "旁路下报什么都该记, 不判错"
        assert _step(result, "F64R-7①").success is True, "GOS 后报什么都该记, 不判错"
        assert result.extra["state_in_bypass"] == "STOPPED"
        assert result.extra["state_after_gos"] == "RUNNING"

    def test_p2_clear_queue_failure_aborts(self):
        """清队列失败却继续发 GO/STATIC = 带着没清干净的队列跑, 后面每步的
        SYST:ERR? 判据都可能读到别人的旧错误。"""
        class _DrainBoom(_FakeF64):
            async def _query(self, cmd):
                if cmd == "SYST:ERR?":
                    raise TimeoutError("VI_ERROR_TMO")
                return await super()._query(cmd)

        ce = _DrainBoom(state="STOPPED")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.success is False
        assert "清错误队列失败" in result.summary
        assert "DIAG:SIMU:GO" not in ce.writes


class TestUxmProbeCodex229B:
    def test_p2_blank_reply_is_unknown(self):
        """空串/纯空白回复跟"没回复"是同一件事 —— 只判 is None 会漏掉固件回空行。
        ⚠ 归一化只用于判定, raw 仍要存原样(那是本序列的产出)。"""
        class _BlankReply(TestUxmManualSpellingProbe._FakeUxm):
            async def _query(self, cmd):
                if cmd == "SYST:ERR?":
                    return '0,"No error"'
                self.queries.append(cmd)
                return "   "          # 回了空白

        from app.diagnostics.sequences.uxm_manual_spelling_probe import run as run_probe
        logs: List[str] = []
        result = asyncio.run(
            run_probe(ctx=object(), hal=_FakeHal2(_BlankReply()), params={}, log=logs.append)
        )
        assert result.success is False
        assert "CELL_STATUS" in result.extra["critical_unsupported"]
        cell_step = [s for s in result.steps if s.label.startswith("CELL_STATUS")][0]
        assert cell_step.raw == "   ", "判定归一化了, raw 仍要存原样"


class TestCodexRound229C:
    """Codex 第三轮 3 条。P1-1 正是我上一轮**主动请它裁决**的那个判断 —— 我以为
    "排空循环的终止条件"跟"判队列干净"语义不同可以留 None, 它判我错: 那是两件事,
    我把它们混成了同一个分支。"""

    def test_p1_indeterminate_drain_reply_is_failure(self):
        """`SYST:ERR?` 读不出错误码 ≠ 队列干净。会话没验证过就去发 GO/STATIC/GOS,
        而且后面步骤的判据会把迟到的错误算到自己头上。"""
        class _GarbledDrain(_FakeF64):
            async def _query(self, cmd):
                if cmd == "SYST:ERR?":
                    return "???"          # 畸形回复, _parse_err 给 None
                return await super()._query(cmd)

        ce = _GarbledDrain(state="STOPPED")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.success is False
        assert "清错误队列失败" in result.summary
        assert "DIAG:SIMU:GO" not in ce.writes, "队列状态未知就不该动手"

    def test_p1_bypass_precondition_before_observation(self):
        """先建立前提, 再采集依赖该前提的观测。若 STATIC 写入队列干净但档位没真变,
        旧顺序会先把一个"根本不在旁路里测到的"值记成 F64R-7② 的答案 —— 整轮虽然
        最终失败, 但归档里已经躺着一个**贴错标签的观测值**。"""
        class _BypassSilentlyIgnored(_FakeF64):
            async def _write(self, cmd):
                if cmd.startswith("DIAG:SIMU:MODEL:STATIC ") and cmd.endswith(" 3"):
                    self.writes.append(cmd)   # 收下, 队列干净, 但档位不变
                    return
                return await super()._write(cmd)

        ce = _BypassSilentlyIgnored(state="RUNNING", state_in_bypass="STOPPED")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert result.success is False
        assert "state_in_bypass" not in result.extra, (
            "前提没建立就不该记观测值, 否则归档里是贴错标签的数据"
        )
        assert _step(result, "旁路下 STATE? (跳过)").success is False

    def test_p2_unrecognised_literal_still_reaches_summary(self):
        """⭐ 七态之外的字面值(比如固件自有的 `BYPASS`)恰恰是本剧本**最想收集**的东西。
        按归一化值真假判会把它从摘要里漏掉, 而步骤列表超 2048 字节会被截掉。"""
        ce = _FakeF64(state="RUNNING", state_in_bypass="BYPASS", state_after_gos="RUNNING")
        result, _ = _run(ce, {"restore_initial_state": False})
        assert "'BYPASS'" in result.summary, f"意料之外的字面值丢了: {result.summary}"
        assert "七态之外" in result.summary, "要标出来这是个未识别值"
        assert result.extra["state_in_bypass_raw"] == "BYPASS"


class TestCodexRound229D:
    """Codex 第四轮 2×P1。第二条是"同一条规则存两份、只改一份" —— 上一轮我在 F64
    剧本改了排空判据, **没 grep 同族站点**, UXM 探针那份原封不动 (memory
    feedback_clear_stale_state_enumerate_all_sources 说的正是这个坑)。"""

    def test_p1_bypass_restore_gated_on_post_state_recheck(self):
        """④-1 写完 GO/STOP 后, 错误队列干净不代表真到了目标态。若复核读到瞬态/
        读不到, ④-2 继续写 MODEL:STATIC 就是在自己声明"不可操作"的态里改仪器 ——
        把一次恢复失败升级成可能的卡死。"""
        class _RestoreLandsInTransient(_FakeF64):
            async def _write(self, cmd):
                await super()._write(cmd)
                if cmd == "DIAG:SIMU:GO" and self.state == "RUNNING":
                    self.state = "OPENING"   # 队列干净, 但落在瞬态

        ce = _RestoreLandsInTransient(state="RUNNING", bypass="3")
        result, _ = _run(ce, {"restore_initial_state": True})
        step = _step(result, "恢复旁路档 (放弃)")
        assert step.success is False
        assert "不是可操作的稳态" in step.detail
        assert "接手时旁路档=3" in step.detail
        # 关键: 复核不过就不许再写旁路 —— 探测段那一次不算
        assert ce.writes.count("DIAG:SIMU:MODEL:STATIC 3") == 1, (
            f"复核未通过仍写了旁路; writes={ce.writes}"
        )
        assert result.success is False


class TestUxmProbeCodex229D:
    def test_p1_indeterminate_drain_aborts(self):
        """UXM 探针开跑前排空: `None` 是"读不出错误码"不是"队列干净"。带着未验证
        的会话跑 12 条探测, 旧错误/迟到应答会跟首条关键的 CELL_STATUS 回复错配 →
        把可用命令误判成不支持, 而本序列的产出正是"哪个拼法可用"。"""
        class _GarbledDrain(TestUxmManualSpellingProbe._FakeUxm):
            async def _query(self, cmd):
                if cmd == "SYST:ERR?":
                    return "???"
                return await super()._query(cmd)

        from app.diagnostics.sequences.uxm_manual_spelling_probe import run as run_probe
        logs: List[str] = []
        result = asyncio.run(
            run_probe(ctx=object(), hal=_FakeHal2(_GarbledDrain()),
                      params={}, log=logs.append)
        )
        assert result.success is False
        assert "排空错误队列失败" in result.summary
        assert "结论不可信" in result.summary

    def test_drain_judgement_is_same_across_sequences(self):
        """⭐ 反回归: 两个序列的"判队列干净"判据必须同源。这条钉的是**规则本身**,
        不是某一处实现 —— 上一轮就是只改了一处才漏的。"""
        import ast
        import inspect
        from app.diagnostics.sequences import (
            propsim_f64_state_machine as f64,
            uxm_manual_spelling_probe as uxm,
        )

        # ⚠ 必须**剥掉注释和 docstring** 再扫。两个模块的注释里都写着"我原来写的是
        # `code in (0, None)`"这句解释 —— 直接扫原文会匹配到自己的注释而误报。
        # 这跟 #227 那个守门测试被自己刚写的注释文本骗**绿**是同一个坑, 只是这次
        # 方向反过来是骗**红**: 判据一旦包含自然语言, 就会被文档本身污染。
        def _code_only(mod) -> str:
            tree = ast.parse(inspect.getsource(mod))
            for node in ast.walk(tree):          # 去 docstring
                if isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)):
                        node.body.pop(0)
            return ast.unparse(tree)             # unparse 天然丢掉 # 注释

        for mod in (f64, uxm):
            src = _code_only(mod)
            assert "in (0, None)" not in src, (
                f"{mod.__name__} 的**代码里**还有 `in (0, None)` —— "
                "读不出错误码不能当队列干净"
            )


class TestCodexRound229E:
    """Codex 第五轮 1×P1 + 1×P2。P1 是"前提没建立就采观测"这个母题的**第三个站点**
    —— 第三轮我给"进旁路"补了核对, 没给"退旁路→GOS"补。"""

    def test_p1_exit_bypass_rejected_aborts_before_gos(self):
        """退旁路被拒时旧写法整块跳过, 直接落到破坏性的 GOS —— 而 F64 可能还在旁路里。
        那样记下的"GOS 之后 STATE?"不是从正常 RUNNING 出发的观测, 结论作废。"""
        ce = _FakeF64(state="RUNNING", state_in_bypass="STOPPED",
                      reject_cmds={"DIAG:SIMU:MODEL:STATIC 0"})
        result, _ = _run(ce, {"probe_gos": True, "restore_initial_state": False})
        assert "DIAG:SIMU:GOS" not in ce.writes, (
            f"退旁路没成功就发了 GOS; writes={ce.writes}"
        )
        assert "state_after_gos" not in result.extra
        assert "仍在旁路" in result.summary or "退旁路被拒" in result.summary
        assert result.success is False

    def test_p1_exit_bypass_readback_nonzero_aborts_before_gos(self):
        """写成功、队列干净, 但回读旁路档仍非 0 —— 同样不能发 GOS。
        旧写法只核了运行态那一条, 漏了旁路档这条。"""
        class _ExitAcceptedButStuck(_FakeF64):
            async def _write(self, cmd):
                if cmd == "DIAG:SIMU:MODEL:STATIC 0":
                    self.writes.append(cmd)      # 收下, 队列干净, 但档位不变
                    self.state = "RUNNING"       # 运行态那条能核过
                    return
                return await super()._write(cmd)

        # state_in_bypass=None → 旁路下 STATE? 仍报 RUNNING。手册**没定义**旁路下
        # STATE? 报什么(七态里没有 BYPASS), 所以"照样报 RUNNING"是真机可能的形态
        # —— 正是这种固件下, 只核运行态那一条会漏掉"其实还在旁路里"。
        ce = _ExitAcceptedButStuck(state="RUNNING", state_in_bypass=None)
        result, _ = _run(ce, {"probe_gos": True, "restore_initial_state": False})
        assert "DIAG:SIMU:GOS" not in ce.writes
        assert "旁路档是 3" in result.summary, f"没走到旁路档那道闸: {result.summary}"
        assert result.success is False

    @pytest.mark.parametrize("flag", ["probe_gos", "restore_initial_state"])
    @pytest.mark.parametrize("bad", ["false", "true", 0, 1, "no"])
    def test_p2_non_boolean_flags_rejected(self, flag, bad):
        """`bool("false")` 是 True —— 直接调 API 的人传字符串 "false" 想关掉 GOS,
        真值强转反而把破坏性动作打开了。破坏性开关不做强转。"""
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {flag: bad})
        assert result.success is False
        assert "必须是 JSON 布尔" in result.summary
        assert ce.writes == [], "参数非法时一条命令都不该发"

    def test_p2_real_booleans_still_work(self):
        """反向: 真布尔要照常工作, 别把闸修成谁都过不去。"""
        ce = _FakeF64(state="RUNNING")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": False})
        assert result.success is True
        assert "DIAG:SIMU:GOS" not in ce.writes


class TestBypassWriteVerificationIsStructural:
    """⭐ 把「写完旁路必须核回读」钉成**规则**, 而不是逐个站点的用例。

    本 PR 六轮审查里, 「前提没建立就采集依赖它的观测」这个母题在**四个不同站点**
    各被抓一次 (进旁路观测 / 恢复段旁路写 / GOS 前提 / 开跑前退旁路)。每次我都只
    修被点到的那一处 —— 逐点修永远慢审查一步。这条测试改成扫**结构**: 只要有人
    再加一个写旁路的站点却忘了核回读, 它直接红。

    判据用 AST 不用文本: 注释里写着命令字面量, 扫原文会被自己的注释污染
    (#227 守门测试被自己注释骗绿、本文件反回归断言被注释骗红, 已经踩过两次)。
    """

    @staticmethod
    def _run_fn_ast():
        import ast
        import inspect
        from app.diagnostics.sequences import propsim_f64_state_machine as mod
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
                return node
        raise AssertionError("找不到 run()")

    @staticmethod
    def _is_static_write(call) -> bool:
        """`p.write_and_check(label, "DIAG:SIMU:MODEL:STATIC ...")` —— 认第二个实参。"""
        import ast
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == "write_and_check"):
            return False
        if len(call.args) < 2:
            return False
        cmd = call.args[1]
        if isinstance(cmd, ast.Constant) and isinstance(cmd.value, str):
            return cmd.value.startswith("DIAG:SIMU:MODEL:STATIC")
        if isinstance(cmd, ast.JoinedStr):          # f-string
            head = cmd.values[0]
            return (isinstance(head, ast.Constant)
                    and str(head.value).startswith("DIAG:SIMU:MODEL:STATIC"))
        return False

    def test_every_bypass_write_is_verified(self):
        import ast
        run_fn = self._run_fn_ast()
        writes, verified_reads = 0, 0
        for node in ast.walk(run_fn):
            if not isinstance(node, ast.Call):
                continue
            if self._is_static_write(node):
                writes += 1
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "read_bypass"
                    and any(kw.arg == "expect" for kw in node.keywords)):
                verified_reads += 1

        assert writes == 4, (
            f"写旁路的站点数变了 ({writes} 个) —— 本测试是按'每个写站点都要有一次带 "
            "expect 的 read_bypass'来钉的。加/删站点时请一并更新本断言, 并确认新站点"
            "确实核了回读。"
        )
        assert verified_reads >= writes, (
            f"写旁路 {writes} 次, 但带 expect= 的 read_bypass 只有 {verified_reads} 次 —— "
            "有写站点没核回读。错误队列干净**不代表**档位真切过去了: 固件可能照样报一个"
            "'可操作'的 STOPPED/RUNNING(手册七态里没有 BYPASS), 于是后续的 GO/GOS 就"
            "发在了语义未定义的旁路态里, 记下来的观测作废。"
        )

    def test_initial_bypass_exit_verified_before_any_control(self):
        """行为侧对照: 开跑前退旁路'队列干净但档位没变'时, 一条控制命令都不许发。"""
        class _ExitIgnoredAtStart(_FakeF64):
            async def _write(self, cmd):
                if cmd == "DIAG:SIMU:MODEL:STATIC 0":
                    self.writes.append(cmd)      # 收下, 队列干净, 档位不变
                    return
                return await super()._write(cmd)

        ce = _ExitIgnoredAtStart(state="STOPPED", bypass="3", state_in_bypass=None)
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.success is False
        assert "仍在旁路中" in result.summary
        for forbidden in ("DIAG:SIMU:GO", "DIAG:SIMU:GOS"):
            assert forbidden not in ce.writes, (
                f"旁路没真退出就发了 {forbidden}; writes={ce.writes}"
            )


class TestMutationSweepGaps:
    """系统性变异扫描 (45 个 if 逐个改成 False) 暴露的 6 处空转。

    ⚠ 这批用例的来历值得记: 它们**不是** Codex 或 agent 指出来的, 是把"全量绿"换成
    "逐个分支变异"之后自己掉出来的。其中 L454 那道闸是前几轮**为了满足审查意见加的**
    —— 加完从来没被测过, 拿掉照样全绿。**加闸不写用例 = 加了个装饰。**
    """

    def test_driver_not_loaded(self):
        """L316: 没有 channelEmulator 驱动 —— 整条分支此前零覆盖。"""
        logs: List[str] = []
        result = asyncio.run(run_state_machine(
            ctx=object(), hal=_FakeHal(None), params={}, log=logs.append))
        assert result.success is False
        assert "channelEmulator" in result.summary
        assert result.steps == []

    def test_unreadable_initial_state_message_is_specific(self):
        """L378: 初始状态读不到, 要给**它自己**的指引(先跑健康探针查通道), 不是
        瞬态那句"等它稳定"。此前被下面更宽的 `not in _ACTIONABLE_STATES` 闸短路成
        空转 —— 跟 CLOSED 那条同一个坑: 被更晚的闸兜住的分支最容易假绿。"""
        ce = _FakeF64(state_raw_override='0,"NO ERROR"')
        result, _ = _run(ce)
        assert result.success is False
        assert "健康探针" in result.summary, f"指引不对: {result.summary}"
        assert "瞬态" not in result.summary

    def test_empty_state_reply_note_is_specific(self):
        """L114: 空回复要说"空回复", 不是笼统的"白名单外"。判不了的**原因**不同,
        现场排查方向就不同 (通道哑了 vs 固件报了个没见过的值)。"""
        state, note = classify_state("")
        assert state is None
        assert "空回复" in note, f"空回复被归成了别的原因: {note}"

    def test_transient_after_initial_bypass_exit_aborts(self):
        """L454: 开跑前退旁路后状态变成瞬态 —— 这道闸是前几轮应审查意见加的,
        **从没被测过**。退旁路本身会触发状态迁移, 落到 STOPPING/OPENING 完全可能。"""
        class _ExitLandsInTransient(_FakeF64):
            async def _write(self, cmd):
                await super()._write(cmd)
                if cmd == "DIAG:SIMU:MODEL:STATIC 0" and self.bypass == "0":
                    self.state = "STOPPING"

        ce = _ExitLandsInTransient(state="STOPPED", bypass="3", state_in_bypass=None)
        result, _ = _run(ce, {"restore_initial_state": False})
        assert result.success is False
        # ⚠ 断言必须钉住**这道闸独有的后果**。初版我断言的是 success=False /
        # summary 含 STOPPING / 没发 GO —— 这三条在闸拿掉后**依然成立**(后面退旁路
        # 那道 expect=RUNNING 的闸会兜住), 于是变异空转。这是今天第三次踩"被更晚的
        # 闸短路"(CLOSED 分支 / 初始状态读不到 / 本条)。
        # 本闸独有的后果 = **一步旁路探测都不许开始**, 且给出它自己的措辞。
        assert "退旁路后状态变成" in result.summary, f"不是本闸的措辞: {result.summary}"
        assert "DIAG:SIMU:MODEL:STATIC 3" not in ce.writes, (
            f"瞬态下不该开始旁路探测; writes={ce.writes}")
        assert "DIAG:SIMU:GO" not in ce.writes, "瞬态下不许发控制命令"

    def test_restore_noop_when_state_already_matches(self):
        """L583: 恢复时运行态已经等于初始态 → 记"无需"而不是走"放弃"报红。
        探测把状态原样还回来时(旁路进出自动恢复), 走的正是这条。"""
        ce = _FakeF64(state="RUNNING", bypass="0")
        result, _ = _run(ce, {"probe_gos": False, "restore_initial_state": True})
        step = _step(result, "恢复运行态 (无需)")
        assert step.success is True
        assert "RUNNING" in step.detail
        assert result.success is True

    def test_restore_bypass_readback_unreadable_gives_up_loudly(self):
        """L622: 恢复阶段旁路档读不到 —— 不猜, 但要把接手时的值报出来让人工核对。"""
        class _BypassUnreadableAtRestore(_FakeF64):
            _probe_done = False

            async def _query(self, cmd):
                if cmd == "DIAG:SIMU:MODEL:STATIC?" and self._probe_done:
                    return '0,"NO ERROR"'      # 会话错位, 读回非法值
                return await super()._query(cmd)

            async def _write(self, cmd):
                await super()._write(cmd)
                if cmd == "DIAG:SIMU:GOS":
                    self._probe_done = True

        ce = _BypassUnreadableAtRestore(state="RUNNING", bypass="0")
        result, _ = _run(ce, {"probe_gos": True, "restore_initial_state": True})
        step = _step(result, "恢复旁路档 (放弃)")
        assert step.success is False
        assert "接手时是 STATIC 0" in step.detail


class TestUxmProbeCodex229F:
    """第七轮 P1: 关键项必须拿到**非空回复**才算通过, 与错误码无关。

    ⚠ 上一轮我只堵了审查举例的那一种 (`code == 0`), 没堵规则本身 —— 这次按规则改。
    """

    @pytest.mark.parametrize("err", ['-113,"Undefined header"', '-108,"Parameter not allowed"',
                                     '-221,"Settings conflict"', '0,"No error"'])
    def test_critical_without_reply_never_passes(self, err):
        """CELL_STATUS 没回话时, 无论错误队列报什么, 都不许算可用。
        -108 / -221 这两档旧写法会归 SUPPORTED / SUPPORTED_BUT_STATE 而放行。"""
        class _CriticalSilent(TestUxmManualSpellingProbe._FakeUxm):
            def __init__(self):
                super().__init__()
                self._n = 0

            async def _query(self, cmd):
                if cmd == "SYST:ERR?":
                    self._n += 1
                    return '0,"No error"' if self._n <= 1 else err
                if "BSE:STATus:NR5G" in cmd:
                    self.queries.append(cmd)
                    return ""              # 认得命令但不给值
                return await super()._query(cmd)

        from app.diagnostics.sequences.uxm_manual_spelling_probe import run as run_probe
        logs: List[str] = []
        result = asyncio.run(run_probe(ctx=object(), hal=_FakeHal2(_CriticalSilent()),
                                       params={}, log=logs.append))
        assert "CELL_STATUS" not in result.extra["supported"], (
            f"错误码 {err} 下关键项没拿到值却被判可用")
        assert result.success is False

    def test_non_critical_state_rejection_still_counts_as_valid(self):
        """⭐ 反向: 这道闸**只**收紧 _CRITICAL。非关键项"命令头存在但当前状态不给值"
        是**有效结论**(那正是 SUPPORTED_BUT_STATE 的意义), 不该被误伤成不可用。
        没有这条, 我可能把闸修成"谁都过不去"还自以为更严格了。"""
        # ⚠ 关键项要真给出值 —— 基类 fake 默认"什么都不支持", 直接用它的话前提就
        # 不成立(测的是另一件事)。head = 去掉 "?" 的部分。
        crit_head = "BSE:STATus:NR5G:CELL1"

        class _NonCriticalStateBusy(TestUxmManualSpellingProbe._FakeUxm):
            def __init__(self):
                super().__init__(supported={crit_head})

            async def _query(self, cmd):
                # 非关键项 SCS_COMMON: 认得命令头, 但当前状态拒绝给值 (-221)
                if "SUBCarrier:SPACing:COMMon" in cmd:
                    self.queries.append(cmd)
                    self._pending_err = '-221,"Settings conflict"'
                    return ""
                return await super()._query(cmd)

        from app.diagnostics.sequences.uxm_manual_spelling_probe import run as run_probe
        logs: List[str] = []
        result = asyncio.run(run_probe(ctx=object(), hal=_FakeHal2(_NonCriticalStateBusy()),
                                       params={}, log=logs.append))
        assert "CELL_STATUS" in result.extra["supported"], (
            f"关键项拿到值了却被误伤; supported={result.extra['supported']}")
        # 非关键项被归成"命令头在、状态不给值", 这是有效结论 —— 不该进 critical_unsupported
        assert "SCS_COMMON" not in result.extra["critical_unsupported"]
