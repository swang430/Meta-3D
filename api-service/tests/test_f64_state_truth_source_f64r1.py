"""F64R-1: `DIAG:SIMU:STATE?` 作运行状态**唯一真值源**。

背景 (F64 驱动 review 母题①「该问仪器的地方在猜」之运行状态维度):
驱动的"在不在跑"由本地布尔 + **猜 SYST:ERR? 的错误文字**决定。手册给了唯一真值源
`DIAG:SIMU:STATE?` (§20.4.3.14 七态), P0-3 只把**加载路**接上, 播放控制/监控/旁路
三路仍在猜。

判定原则 (本 PR 的一句话): **命令发完后成没成看 STATE? 终态, 不看错误文字像不像
benign**。手册依据 (NotebookLM 查证):
  · §20.6.1.2 原文警告: `*OPC?`=1 **只表示先前操作已执行完毕, 不表示执行过程中没有
    发生错误** —— 所以要读 SYST:ERR?;
  · 但同一个 `-200 "Wrong device state"` 既可能是"本来就已达成"(幂等), 也可能是
    "前置没生效被拒" —— 错误文字**单独不足以判定**;
  · §20.6.1.1 给的解法: **用查询命令复核真实状态** → 对播放控制就是 STATE?。

本文件钉五件事:
  1. GO 判定 = STATE?==RUNNING (取代 #221 的 `STATIC?==0` 豁免 —— STATIC? 只报旁路档,
     "STATIC=0 且 STOPPED"会被误判成"已在播放", 测量跑假数据);
  2. GOS 判定 = STATE? ∈ {STOPPED, CLOSED} (取代盲信 -200 文字);
  3. 监控面 (get_metrics / get_channel_state) 的 emulation_running 用真值, 读不到降级
     并在 query_errors 标注;
  4. 旁路进出后按 STATE? 刷新 running (手册: 进旁路暂停 / 退旁路可能恢复);
  5. 超时排水**也失败**时升级重建会话 (P0-1 遗留的业务挂死盲区)。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.hal.propsim_f64 import F64BypassMode, RealPropsimF64Driver


def _drv(*, state="RUNNING", err_on=None):
    """state: DIAG:SIMU:STATE? 的回值 (可传 list 按序回); err_on: {写命令: 错误串}。"""
    d = RealPropsimF64Driver("f64-r1", {})
    d._visa_resource = MagicMock()
    d._loaded_emulation_file = "X.smu"
    writes: list[str] = []
    states = list(state) if isinstance(state, list) else [state]
    last = {"cmd": None}

    async def _w(cmd, timeout=None):
        last["cmd"] = cmd
        writes.append(cmd)

    async def _q(cmd, timeout=None):
        if cmd == "*OPC?":
            return "1"
        if cmd == "DIAG:SIMU:STATE?":
            return states[0] if len(states) == 1 else states.pop(0)
        if cmd == "SYST:ERR?":
            e = (err_on or {}).get(last["cmd"])
            if e:
                (err_on or {}).pop(last["cmd"])   # 只报一次, 之后队列净
                return e
            return '0,"No error"'
        if cmd == "DIAG:SIMU:MODEL:STATIC?":
            return "0"
        return '0,"No error"'

    d._write = _w  # type: ignore[assignment]
    d._query = _q  # type: ignore[assignment]
    return d, writes


WRONG_STATE = '-200,"Execution error;Wrong device state for command"'


# ───────────── 1. GO 判定 = STATE?==RUNNING ─────────────

class TestGoJudgedByState:
    async def test_clean_and_running_is_success(self):
        d, _ = _drv(state="RUNNING")
        assert await d.start_emulation() is True
        assert d._emulation_running is True

    async def test_rejected_but_running_is_success(self):
        """幂等"已在跑": 有 -200 但 STATE?=RUNNING → 目标达成。"""
        d, _ = _drv(state="RUNNING", err_on={"DIAG:SIMU:GO": WRONG_STATE})
        assert await d.start_emulation() is True
        assert d._emulation_running is True

    async def test_clean_but_stopped_fails_loud(self):
        """★ `*OPC?` 骗人场景 (手册 §20.6.1.2 原文警告): 没有任何错误, 但 STATE? 没到
        RUNNING → 假启动。旧的"只看错误队列"判据在这里会放行。"""
        d, _ = _drv(state="STOPPED")
        assert await d.start_emulation() is False
        assert d._emulation_running is False
        assert "STOPPED" in (d._last_error or "")

    async def test_rejected_and_stopped_fails_loud(self):
        """★ #221 误豁免的直接回归: GO 被拒且**没在跑**。旧判据 (回查 STATIC?==0)
        在这里会判成"已在播放"放行 —— STATIC? 只报旁路档, 不报运行态。"""
        d, _ = _drv(state="STOPPED", err_on={"DIAG:SIMU:GO": WRONG_STATE})
        assert await d.start_emulation() is False
        assert d._emulation_running is False

    async def test_state_unreadable_fails_loud_and_keeps_cache(self):
        """STATE? 读不到 → 无法确认 → 保守 fail-loud; running 缓存**不动**(不猜)。"""
        d, _ = _drv(state="")
        d._emulation_running = True          # 旧缓存
        assert await d.start_emulation() is False
        assert d._emulation_running is True, "读不到就不该改缓存"


# ───────────── 2. GOS 判定 = STATE? ∈ {STOPPED, CLOSED} ─────────────

class TestStopJudgedByState:
    @pytest.mark.parametrize("st", ["STOPPED", "CLOSED"])
    async def test_stopped_or_closed_is_success(self, st):
        """CLOSED (没加载仿真) 时"确保停止"的目标同样达成。"""
        d, _ = _drv(state=st)
        d._emulation_running = True
        assert await d.stop_emulation() is True
        assert d._emulation_running is False

    async def test_rejected_but_stopped_is_success(self):
        """已停态重复 GOS 被拒 (2026-07-21 现场实证形态) → 仍算停住。"""
        d, _ = _drv(state="STOPPED", err_on={"DIAG:SIMU:GOS": WRONG_STATE})
        assert await d.stop_emulation() is True

    async def test_still_running_fails_loud(self):
        """★ 真没停住: 旧判据盲信 -200 文字会当成"本来就没在跑"放行, 于是 attach
        直通预备在**仿真还在跑**的情况下假成功。"""
        d, _ = _drv(state="RUNNING", err_on={"DIAG:SIMU:GOS": WRONG_STATE})
        assert await d.stop_emulation() is False
        assert d._emulation_running is True, "真值: 还在跑"


# ───────────── 3. 监控面用真值 ─────────────

class TestMonitoringUsesLiveState:
    async def test_metrics_reports_live_state_over_stale_cache(self):
        """★ 后端重启形态: 缓存 False 而硬件在播 → 必须报 True (旧行为谎报没在跑)。"""
        d, _ = _drv(state="RUNNING")
        d._emulation_running = False          # 冷缓存
        m = await d.get_metrics()
        assert m.metrics["emulation_running"] is True
        assert m.metrics["simulation_state"] == "RUNNING"

    async def test_metrics_degrades_visibly_when_state_unreadable(self):
        d, _ = _drv(state="")
        d._emulation_running = True
        m = await d.get_metrics()
        assert m.metrics["emulation_running"] is True      # 退回缓存
        assert m.metrics["simulation_state"] is None
        assert any("simulation_state" in e for e in m.metrics["query_errors"])

    async def test_channel_state_reports_live_state(self):
        d, _ = _drv(state="RUNNING")
        d._emulation_running = False
        st = await d.get_channel_state()
        assert st["emulation_running"] is True
        assert st["simulation_state"] == "RUNNING"


# ───────────── 4. 旁路进出按 STATE? 刷新 ─────────────

class TestBypassRefreshesRunning:
    async def test_entering_passthrough_syncs_running_from_state(self):
        """手册 §20.4.6.25: 启用静态模型时**仿真被暂停** → 驱动跟着 STATE? 走。"""
        d, _ = _drv(state="STOPPED")
        d._emulation_running = True
        assert await d.set_passthrough_mode(mode=3) is True
        assert d._emulation_running is False

    async def test_clearing_passthrough_syncs_running_from_state(self):
        """ATE AN §2.4.5: 退出旁路时若之前在跑则**继续运行** → 仪器说 RUNNING 就记 True。"""
        d, _ = _drv(state="RUNNING")
        d._emulation_running = False
        assert await d.clear_passthrough_mode() is True
        assert d._emulation_running is True

    async def test_unreadable_state_keeps_cache(self):
        """STATE? 读不到 → 保留缓存, 不猜 (旁路态下 STATE? 报什么手册未定义)。"""
        d, _ = _drv(state="")
        d._emulation_running = True
        await d.set_passthrough_mode(mode=3)
        assert d._emulation_running is True


# ───────────── 5. 确认闭环本身 ─────────────

class TestConfirmClosedLoop:
    async def test_sends_opc_err_state_in_order(self):
        """闭环三步齐全且顺序正确 (*OPC? → SYST:ERR? → STATE?)。"""
        d, _ = _drv(state="RUNNING")
        seen: list[str] = []
        _orig = d._query

        async def _q(cmd, timeout=None):
            seen.append(cmd)
            return await _orig(cmd, timeout)

        d._query = _q  # type: ignore[assignment]
        await d.start_emulation()
        tail = [c for c in seen if c in ("*OPC?", "SYST:ERR?", "DIAG:SIMU:STATE?")]
        # GO 之后的三步 (前面 drain 也发 SYST:ERR?, 取末尾三条)
        assert tail[-3:] == ["*OPC?", "SYST:ERR?", "DIAG:SIMU:STATE?"], seen


# ───────────── 6. STATE? 七态白名单 (提交前审查 F2) ─────────────

class TestStateWhitelist:
    """`STATE?` 是运行态**唯一真值源**, 所以它读回来的东西必须先验明正身。

    3334 会话错位时这条查询读到的可能是上一条命令的迟到应答 (典型 `0,"NO ERROR"`)。
    没有白名单时它会被 `!= "RUNNING"` 判成"没在跑"并**写进缓存当真值** —— GO/GOS
    假失败、监控面谎报, 而且看起来像仪器真这么说的。白名单让噪声退化成"没读到"。"""

    @pytest.mark.parametrize("st", [
        "CLOSED", "OPENING", "STOPPING", "STOPPED", "RUNNING", "EDITING", "CLOSING",
    ])
    async def test_all_seven_manual_states_accepted(self, st):
        d, _ = _drv(state=st)
        assert await d._query_simulation_state() == st

    @pytest.mark.parametrize("noise", [
        '0,"No error"',      # 错位读到 SYST:ERR? 的应答 (现场真实形态)
        "1",                 # 错位读到 *OPC? 的应答
        "1.2.3",             # 错位读到 SYST:VERS? 的应答
        "RUNNIN",            # 半截响应
        "PAUSED",            # 手册里根本没有的态
    ])
    async def test_garbage_is_not_a_state(self, noise):
        d, _ = _drv(state=noise)
        assert await d._query_simulation_state() is None

    async def test_lowercase_and_padding_normalized(self):
        """手册说全大写, 但宽进严出: 大小写/空白归一后仍是合法态就认。"""
        d, _ = _drv(state="  running \n")
        assert await d._query_simulation_state() == "RUNNING"

    async def test_garbage_does_not_poison_running_cache(self):
        """★ 噪声不能改写运行态缓存 (白名单存在的**理由**, 不只是过滤器)。"""
        d, _ = _drv(state='0,"No error"')
        d._emulation_running = True
        await d.get_metrics()
        assert d._emulation_running is True, "会话噪声被当成'没在跑'写进了缓存"


# ───────────── 7. 瞬态与不可读 (提交前审查 F8 覆盖缺口) ─────────────

class TestTransientStates:
    """手册确认 (NotebookLM): GOS + `*OPC?` 同步之后 STATE? **必然**是 STOPPED ——
    GOS 不碰文件, 状态机不经过 EDITING(只 `CALC:FILT:EDIT` 进)/OPENING/CLOSING,
    STOPPING 瞬态被 `*OPC?` 吃掉。所以停止判定收严到 {STOPPED, CLOSED} 是手册支持的:
    真读到瞬态 = 有别人在并发操作仪器, 此时**保守 fail-loud** 比放行安全 (放行会把
    别人正在加载文件的 OPENING 当成"我停住了")。"""

    @pytest.mark.parametrize("st", ["STOPPING", "OPENING", "CLOSING", "EDITING"])
    async def test_stop_fails_loud_on_transient(self, st):
        d, _ = _drv(state=st)
        assert await d.stop_emulation() is False
        assert st in (d._last_error or "")

    @pytest.mark.parametrize("st", ["STOPPING", "OPENING", "CLOSING", "EDITING"])
    async def test_start_fails_loud_on_transient(self, st):
        d, _ = _drv(state=st)
        assert await d.start_emulation() is False

    async def test_stop_failure_writes_truth_cache(self):
        """agent F7: 失败分支也要落真值 —— 原先只在 ==RUNNING 时写, 瞬态读到了却
        不写, 与 GO 失败分支不对称 (缓存停留在旧值继续骗下游)。"""
        d, _ = _drv(state="STOPPING")
        d._emulation_running = True
        assert await d.stop_emulation() is False
        assert d._emulation_running is False   # STOPPING ≠ RUNNING → 真值

    async def test_unreadable_state_keeps_cache_on_stop(self):
        d, _ = _drv(state="")
        d._emulation_running = True
        assert await d.stop_emulation() is False   # 无法确认 → 保守失败
        assert d._emulation_running is True        # 但不猜: 缓存保留


# ───────────── 8. CLOSED = 被别人卸载了 (提交前审查 F10) ─────────────

class TestClosedMeansUnloaded:
    """手册 §20.4.3.14: CLOSED = "Emulation has not been loaded"; ATE AN §1.1: F64
    **支持本地 GUI 与远程 ATE 并发**。所以"我加载过、现在读到 CLOSED" = 别人 (前面板
    / 另一条连接) 把仿真关了。这是驱动唯一能拿到的"文件没了"信号, 丢掉它 = 继续拿
    **上一个仿真**的拓扑去配端口 (stale 拓扑比没拓扑更危险)。"""

    async def test_metrics_clears_load_state_when_closed(self):
        d, _ = _drv(state="CLOSED")
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2, 3, 4]
        d._active_outputs = 4
        m = await d.get_metrics()
        assert d._loaded_emulation_file is None, "仿真已被卸载却还记着文件"
        assert d._active_output_ports is None, "stale 拓扑没清 — 会配到别的仿真的口上"
        assert d._emulation_running is False
        # ★ 还要断言**发出去的 payload** 自洽 —— 只查私有字段的话, "把 STATE? 查询挪回
        # dict 之后"(= 修复前的形态) 照样全绿 (变异实测)。而 "simulation_state=CLOSED
        # 却 loaded_file=X.smu" 这种自相矛盾的快照才是缺陷本体: 看仪表盘的人据此判断
        # "文件还在, 只是没跑"。
        assert m.metrics["simulation_state"] == "CLOSED"
        assert m.metrics["loaded_file"] is None, "快照自相矛盾: CLOSED 却报着文件名"
        assert m.metrics["active_output_ports"] is None
        assert m.metrics["emulation_running"] is False

    async def test_channel_state_clears_load_state_when_closed(self):
        """两条监控读路口径一致 (单一入口 `_apply_state_truth`)。"""
        d, _ = _drv(state="CLOSED")
        d._active_output_ports = [1, 2]
        st = await d.get_channel_state()
        assert d._loaded_emulation_file is None
        assert d._active_output_ports is None
        # 同上: 钉对外 payload 的自洽性, 不只钉私有字段
        assert st["simulation_state"] == "CLOSED"
        assert st["loaded_file"] is None, "快照自相矛盾: CLOSED 却报着文件名"
        assert st["active_output_ports"] is None

    async def test_closed_needs_confirmation_before_destroying_load_state(self):
        """★ 破坏性判定要**锁内复查**: 第一次 CLOSED 是会话错位/竞态假象 (复查报
        STOPPED) → 不清加载态。

        清加载态的代价不只是"少个文件名": identity 一并没了 → 频率一致性网把 F64 记成
        "未报告(跳过)" → `precheck_strict_frequency` 这道门对 F64 **静默失效**。"""
        d, _ = _drv(state=["CLOSED", "STOPPED"])   # 第二次 (复查) 报真值
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        m = await d.get_metrics()
        assert d._loaded_emulation_file == "X.smu", "错位读到的一次 CLOSED 就把加载态清了"
        assert d._active_output_ports == [1, 2]
        assert m.metrics["emulation_running"] is False   # 复查值 STOPPED → 没在跑

    async def test_closed_confirmed_twice_does_clear(self):
        """复查也是 CLOSED → 确实被卸载了, 照清 (别把复查做成永不生效的挡箭牌)。"""
        d, _ = _drv(state=["CLOSED", "CLOSED"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        await d.get_metrics()
        assert d._loaded_emulation_file is None
        assert d._active_output_ports is None

    async def test_loaded_state_survives_normal_states(self):
        """★ 反向: 非 CLOSED 一律不清 —— 别把"停着"当成"卸载了"。"""
        for st in ("STOPPED", "RUNNING", "EDITING", "OPENING", "STOPPING", "CLOSING"):
            d, _ = _drv(state=st)
            # 输入口也要给 —— 否则 get_metrics 的按需补读会认为拓扑不全去重读,
            # 本 fake 不供 MODEL:INFO?, 读失败照样清空 (那是另一条路, 不是本用例要测的)
            d._active_input_ports = [1, 2]
            d._active_output_ports = [1, 2]
            await d.get_metrics()
            assert d._loaded_emulation_file == "X.smu", st
            assert d._active_output_ports == [1, 2], st

    async def test_channel_state_omits_key_when_unreadable(self):
        """契约: 失败的动态查询**不出现在 state 里**, 只进 query_errors。硬塞
        `simulation_state=None` 会被读成"仪器说它没状态", 而不是"这次没查到"。"""
        d, _ = _drv(state="")
        st = await d.get_channel_state()
        assert "simulation_state" not in st
        assert any("simulation_state" in e for e in st.get("query_errors", []))


# ───────────── 9. 断开前问仪器 (提交前审查 F4) ─────────────

class TestDisconnectAsksInstrument:
    """★ 冷缓存不做 gate —— 2026-07-21 现场实证形态: 后端重启后驱动缓存 False 而 F64
    硬件仍加载着信道**在播**。旧代码于是一条停止命令都不发、还返回 True 报"干净断开",
    F64 继续发射 (暗室里没人知道)。同一条教训 start_emulation / _ensure_topology 早就
    写过, 断开路是漏网的那个。"""

    async def test_stops_when_instrument_running_despite_cold_cache(self):
        d, writes = _drv(state="RUNNING")
        d._emulation_running = False          # 冷缓存: 驱动以为没在跑
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:GOS" in writes, "仪器在播却没发停止命令 — F64 会继续发射"

    async def test_stops_when_state_unreadable(self):
        """读不到状态 = 无法确认 → 也停 (GOS 幂等, 代价远小于让仪器带功率跑)。"""
        d, writes = _drv(state="")
        d._emulation_running = False
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:GOS" in writes

    async def test_skips_stop_when_already_stopped(self):
        """已停 → 不发多余 GOS (也避免在 CLOSED 上制造无谓错误条目)。"""
        d, writes = _drv(state="STOPPED")
        d._emulation_running = True           # 缓存反过来说在跑 —— 仍以仪器为准
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:GOS" not in writes

    async def test_closes_when_instrument_has_file_despite_cold_cache(self):
        """卸载同理: 缓存 None 而仪器加载着 (STOPPED) → 仍发 CLOSE。"""
        d, writes = _drv(state="STOPPED")
        d._loaded_emulation_file = None       # 冷缓存
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:CLOSE" in writes

    async def test_no_close_when_nothing_loaded(self):
        d, writes = _drv(state="CLOSED")
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:CLOSE" not in writes


class TestStartFailureWritesTruthCache:
    """GO 失败时也要落真值 —— 与 GOS 失败分支对称 (agent F7 的另一半)。

    ⚠ 这两条是**变异实测补的**: 删掉 start 失败分支的真值写入, 原有 16 条用例全绿
    (旧用例只钉返回值 False, 而缓存默认就是 False, 写不写看不出来)。绿 ≠ 覆盖。"""

    async def test_failed_start_corrects_lying_cache(self):
        """缓存说"在跑" + GO 没成 + 仪器说 STOPPED → 缓存必须被纠正成 False。
        不纠正的话: 测量前置检查看到 running=True 就往下走, 在**没有衰落播放**的
        状态下跑出假数据 (#221 的原始事故形态)。"""
        d, _ = _drv(state="STOPPED")
        d._emulation_running = True
        assert await d.start_emulation() is False
        assert d._emulation_running is False

    async def test_failed_start_on_closed_clears_load_state(self):
        """GO 失败且仪器报 CLOSED = 仿真被别人卸载了 → 连加载态一起清 (走同一个
        真值单一入口), 否则后续端口写会拿 stale 拓扑去配。"""
        d, _ = _drv(state="CLOSED")
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        assert await d.start_emulation() is False
        assert d._loaded_emulation_file is None
        assert d._active_output_ports is None


# ───────────── 10. 断开路的传输层判定 (复审 R3/R5) ─────────────

class TestDisconnectTransportFailure:
    """链路已断时 (掉线 / ATE 服务挂死 —— 恰恰是最常按断开的场景) GOS 和 CLOSE 根本
    到不了仪器, 发了只是让 disconnect 白等 4 条命令 ×(VISA 超时 + 排水)。而
    `POST /hal/reload` 持 HAL 生命周期锁**串行**调各驱动 disconnect —— 那就是现场
    "F64 掉线后点重载, 界面卡死"。"""

    def _dead_link_driver(self):
        """STATE? 抛 **conn-lost** = 会话确实没了。

        ⚠ 本用例原先用 `VI_ERROR_TMO` 造"链路不通"—— 那是错的模型 (Codex P1):
        超时只说明**设备慢**, 会话可能还活着, 拿它当断链会让一台反应慢的 F64 带着
        还在跑的仿真被释放连接。超时的正确行为见 `test_timeout_is_not_dead_link`。"""
        import pyvisa
        d, writes = _drv(state="STOPPED")
        d._visa_resource = MagicMock()

        async def _q(cmd, timeout=None):
            raise pyvisa.errors.VisaIOError(0xBFFF00B5)   # VI_ERROR_CONN_LOST

        d._query = _q  # type: ignore[assignment]
        return d, writes

    async def test_dead_link_skips_stop_and_close(self):
        d, writes = self._dead_link_driver()
        await d.disconnect()
        assert writes == [], f"链路已断还在发命令白等超时: {writes}"

    async def test_dead_link_reports_unconfirmed_stop(self):
        """★ 跳过命令是对的, 但**不能报"干净断开"** —— 命令根本没发出去, 比"GOS 被拒"
        更没资格说已确认停止。报 True 会让 disconnect_all 结果表 / HAL 重载日志显示
        "F64 已安全停下", 而它可能还在发射。"""
        d, _ = self._dead_link_driver()
        assert await d.disconnect() is False

    async def test_unreadable_value_on_live_link_still_stops(self):
        """反向: 链路通、只是值不可用 (非法应答) → 仍按保守策略发 GOS/CLOSE。
        别把"读不到值"跟"链路断了"混成一件事。"""
        d, writes = _drv(state='0,"No error"')     # 会话错位噪声, 但链路是通的
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:GOS" in writes and "DIAG:SIMU:CLOSE" in writes


# ───────────── 11. 两个静默期的行为 (复审 R6) ─────────────

class TestCooldownBehaviour:
    async def test_closed_steady_state_keeps_topology_cooldown(self):
        """★ 连着但没加载仿真 (bring-up 常态) 时, 拓扑读路的 30s 静默期不能被清零。

        `_apply_unload()` 会经 `_clear_topology()` 重置 `_topology_retry_after` ——
        若 CLOSED 稳态下每轮都无条件调它, 静默期永远失效: 每秒重跑补读 + 每秒一条
        WARNING 灌进日志面板 (30 倍于设计值, 真错误被淹)。"""
        d, _ = _drv(state="CLOSED")
        d._loaded_emulation_file = None            # 稳态: 本来就没加载
        await d.get_metrics()
        first = d._topology_retry_after
        assert first > 0, "补读失败没有进入静默期"
        await d.get_metrics()
        assert d._topology_retry_after == first, "静默期被 CLOSED 分支清零了"

    async def test_session_reset_thaws_health_cooldowns(self):
        """会话边界 = 人显式重建了连接 → 此前"仪器没反应"的负缓存全部作废。
        不清的话, 操作员点完"重连驱动"还要看最长 30s 的"STATE? 查询失败"谎报。"""
        import time as _t
        d, _ = _drv(state="RUNNING")
        d._state_query_retry_after = _t.monotonic() + 999
        d._reconnect_retry_after = _t.monotonic() + 999
        d._apply_session_reset()
        assert d._state_query_retry_after == 0.0
        assert d._reconnect_retry_after == 0.0


# ───────────── 12. 加载态判据的边界 (复审 T2/T4) ─────────────

class TestHasLoadStateBoundary:
    """判据收的是"**仪器上有个仿真加载着**"的证据, 不是"驱动身上有非空字段"。

    `configure()` 能在**完全没加载**的情况下写 `_active_pipeline` —— 把它算进判据的
    后果实测过: 纯配置状态下跑一轮 `get_metrics` (只读!) 就会走破坏性卸载, 把 configure
    写的配置清掉, 日志还打出"驱动仍记着已加载 (**None**) — 疑似前面板关闭", 现场照这条
    去查"谁关了仿真"纯属误导。"""

    async def test_pipeline_only_config_is_not_load_state(self):
        d, _ = _drv(state="CLOSED")
        d._loaded_emulation_file = None
        await d.configure({"pipeline": "asc_runtime"})
        assert d._active_pipeline is not None
        assert d._has_load_state() is False, "纯配置被当成了加载态"

    async def test_monitoring_read_does_not_destroy_config(self):
        """★ 一次**只读**的监控不该销毁 configure 写入的配置。"""
        d, _ = _drv(state="CLOSED")
        d._loaded_emulation_file = None
        await d.configure({"pipeline": "asc_runtime"})
        m = await d.get_metrics()
        assert d._active_pipeline is not None, "只读的 get_metrics 把配置清掉了"
        assert m.metrics["pipeline"] == "asc_runtime"

    async def test_partial_topology_still_counts_as_load_state(self):
        """反向: 部分回读态 (输出口空、输入口在) 仍算有加载态 —— 否则 CLOSED 既不复查
        也不清, `_active_input_ports` 永久 stale 而 get_metrics 照着它查电平。"""
        d, _ = _drv(state="CLOSED")
        d._loaded_emulation_file = None
        d._active_output_ports = None
        d._active_input_ports = [1, 2]
        assert d._has_load_state() is True


# ───────────── 13. 复查后的上报与报错文案 (复审 T4-M4 / T5) ─────────────

class TestConfirmedStateIsReported:
    async def test_metrics_reports_confirmed_state_not_rejected_read(self):
        """★ 首读 CLOSED 被复查否决后, 上报的必须是**生效状态**。照着被否决的首读值报,
        就会出现 `simulation_state=CLOSED` 却 `loaded_file=X.smu` —— 正是本 PR 定义为
        缺陷的自相矛盾快照, 只是从另一头产生。"""
        d, _ = _drv(state=["CLOSED", "STOPPED"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        m = await d.get_metrics()
        assert m.metrics["simulation_state"] == "STOPPED", "上报了被复查否决的首读值"
        assert m.metrics["loaded_file"] == "X.smu"        # 保留, 与上一行自洽

    async def test_channel_state_reports_confirmed_state(self):
        d, _ = _drv(state=["CLOSED", "STOPPED"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        st = await d.get_channel_state()
        assert st["simulation_state"] == "STOPPED"
        assert st["loaded_file"] == "X.smu"

    async def test_last_error_uses_confirmed_state(self):
        """报错文案也用生效状态 —— 否则 `_last_error` 说"STATE?=CLOSED", 同一轮
        WARNING 却说"判为会话错位假象, 不清加载态", 排障读到两个相反结论。"""
        d, _ = _drv(state=["CLOSED", "STOPPED"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        assert await d.start_emulation() is False
        assert "STOPPED" in (d._last_error or ""), d._last_error
        assert "CLOSED" not in (d._last_error or ""), d._last_error


# ───────────── 14. 传输层异常族 (复审 T4-M7) ─────────────

class TestTransportFailureShapes:
    """"链路不通"= **会话确实没了**: 已关闭句柄的 `InvalidSession` / VISA conn-lost 族 /
    裸 socket 断连。漏判的后果是退回"白等一轮超时+排水"。"""

    @pytest.mark.parametrize("exc_factory", [
        lambda: __import__("pyvisa").errors.InvalidSession(),
        lambda: __import__("pyvisa").errors.VisaIOError(0xBFFF00B5),  # CONN_LOST
        lambda: ConnectionResetError("peer reset"),
        lambda: BrokenPipeError("broken pipe"),
        lambda: ConnectionAbortedError("aborted"),
    ])
    async def test_transport_failure_detected(self, exc_factory):
        d, writes = _drv(state="STOPPED")
        d._visa_resource = MagicMock()

        async def _q(cmd, timeout=None):
            raise exc_factory()

        d._query = _q  # type: ignore[assignment]
        assert await d.disconnect() is False
        assert writes == [], f"链路已断还在发命令: {writes}"

    @pytest.mark.parametrize("exc_factory", [
        lambda: __import__("pyvisa").errors.VisaIOError(0xBFFF0015),  # VI_ERROR_TMO
        lambda: TimeoutError("socket timeout"),        # OSError 子类, 但只是"慢"
        lambda: InterruptedError("EINTR"),             # OSError 子类, 对端没事
        lambda: BlockingIOError("EAGAIN"),             # 同上
        lambda: OSError("host unreachable"),           # 故意保守: 宁可多发命令
    ])
    async def test_timeout_is_not_dead_link(self, exc_factory):
        """★ Codex P1 (连着两轮收窄): **只有"对端确实没了"才算断链**。

        判成断链 → disconnect 同时跳过 GOS 和 CLOSE → F64 带着**还在跑的仿真**被释放
        连接, 在暗室里继续发射。所以判据宁可窄:
          · `VI_ERROR_TMO` / `TimeoutError` —— "设备太慢"不是"连接断"(这条区分本来就
            写在 `_visa_reconnect.py` 里, 是 Codex #14 的教训, 我加判定时违反了);
          · `InterruptedError`(EINTR) / `BlockingIOError`(EAGAIN) —— 都是 `OSError`
            子类却跟对端无关, 用 `isinstance(e, OSError)` 当判据会把它们一起收进去;
          · 裸 `OSError`(主机/网络不可达) —— 多半真是链路没了, 但**故意保守不收**:
            漏判只是多花几秒发命令, 误判是把带功率的仪器丢下, 两者代价不对称。
        这些一律走保守路: 照发 GOS/CLOSE。"""
        d, writes = _drv(state="STOPPED")
        d._visa_resource = MagicMock()

        async def _q(cmd, timeout=None):
            raise exc_factory()

        d._query = _q  # type: ignore[assignment]
        await d.disconnect()
        assert "DIAG:SIMU:GOS" in writes, "慢仪器被当成断链 — 仿真没停就释放了连接"
        assert "DIAG:SIMU:CLOSE" in writes


# ───────────── 15. 判定/落值/文案同源 (复审 U1) ─────────────

class TestJudgementUsesConfirmedState:
    """★ 复查引入后的新裂缝: **判定读首读值、落值用复查值**。首读 CLOSED 被锁内复查
    否决成 RUNNING 时两边结论相反 —— 判定说"已停"(CLOSED 在成功集里), 缓存说"在跑"。

    GOS 这条路最危险: `stop_emulation()` 返回 True → 下游 measure 的布尔门放行 →
    在**仿真仍在播**的状态下写 STATIC 建直通, 正是那道门存在的理由 (真没停住时 attach
    直通预备假成功)。判定 / 落值 / 文案必须同源, 一律用生效状态。"""

    async def test_stop_fails_loud_when_confirm_reveals_running(self):
        d, _ = _drv(state=["CLOSED", "RUNNING"])   # 首读假象 CLOSED, 复查真值 RUNNING
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        assert await d.stop_emulation() is False, "按被否决的首读 CLOSED 判成了'已停'"
        assert d._emulation_running is True         # 真值: 还在跑
        assert "RUNNING" in (d._last_error or ""), d._last_error

    async def test_start_succeeds_when_confirm_reveals_running(self):
        """反向对称: 首读 CLOSED 被复查否决成 RUNNING → GO 的目标其实达成了。
        照首读判会返回 False 且文案写"STATE?=RUNNING (期望 RUNNING)"自相矛盾。"""
        d, _ = _drv(state=["CLOSED", "RUNNING"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        assert await d.start_emulation() is True
        assert d._emulation_running is True

    async def test_confirmed_closed_still_counts_as_stopped(self):
        """复查也是 CLOSED → 确实没加载, "确保停止"的目标达成 (别把复查做成永远失败)。"""
        d, _ = _drv(state=["CLOSED", "CLOSED"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        assert await d.stop_emulation() is True
        assert d._loaded_emulation_file is None     # 顺带确认卸载已落


class TestDisconnectUsesConfirmedState(TestJudgementUsesConfirmedState):
    """★ Codex P1: disconnect 的两道门 (发不发 GOS / 发不发 CLOSE) 当时还在用**首读值**
    —— start/stop 那两处已经改成用复查后的生效状态, 唯独这里漏了 (同一母题第三个站点)。

    后果最直接: 首读是错位假象 CLOSED、锁内复查读到 RUNNING 时, 照首读判会**同时跳过
    GOS 和 CLOSE**, 然后报"干净断开"并释放连接 —— 而 F64 还在发射。"""

    async def test_disconnect_stops_when_confirm_reveals_running(self):
        d, writes = _drv(state=["CLOSED", "RUNNING", "STOPPED"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        d._visa_resource = MagicMock()
        ok = await d.disconnect()
        assert "DIAG:SIMU:GOS" in writes, "按被否决的首读 CLOSED 跳过了停止 — F64 仍在发射"
        assert "DIAG:SIMU:CLOSE" in writes, "同理跳过了卸载"
        assert ok is True   # GOS 后 fake 报 STOPPED → 确认停住

    async def test_disconnect_skips_when_confirmed_closed(self):
        """反向: 复查也是 CLOSED → 确实没加载, 两道门都该跳过 (别白发命令)。"""
        d, writes = _drv(state=["CLOSED", "CLOSED"])
        d._active_input_ports = [1, 2]
        d._active_output_ports = [1, 2]
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:GOS" not in writes
        assert "DIAG:SIMU:CLOSE" not in writes


class TestColdCacheStillConfirmsClosed(TestJudgementUsesConfirmedState):
    """★ Codex P1: **别拿本地缓存决定要不要验证一个安全攸关的终态**。

    复查最初只为"别误清加载态"而设, 所以用 `_has_load_state()` 当闸。但判定也吃这个
    结果之后, 这个闸就成了洞: **驱动刚重启 → 加载态缓存空 → 早退不复查** → 错位来的
    过期 `CLOSED` 直接生效 → `stop_emulation()` 当"已停"报成功、`disconnect()` 同时跳过
    GOS 和 CLOSE, 而仪器**仍在 RUNNING**。

    "冷缓存但硬件在播"正是本 PR 要支持的那个现场场景 (2026-07-21 实证), 判据绝不能
    建立在"我这边记不记得加载过"上。以下三条都**不设**任何加载态缓存。"""

    async def test_stop_confirms_closed_even_with_cold_cache(self):
        d, _ = _drv(state=["CLOSED", "RUNNING"])
        d._loaded_emulation_file = None          # 冷缓存: 后端刚重启
        assert d._has_load_state() is False, "前提: 本用例要的就是空缓存"
        assert await d.stop_emulation() is False, "冷缓存下把过期 CLOSED 当'已停'了"
        assert d._emulation_running is True       # 真值: 还在跑

    async def test_disconnect_confirms_closed_even_with_cold_cache(self):
        d, writes = _drv(state=["CLOSED", "RUNNING", "STOPPED"])
        d._loaded_emulation_file = None
        d._visa_resource = MagicMock()
        await d.disconnect()
        assert "DIAG:SIMU:GOS" in writes, "冷缓存 + 过期 CLOSED → 没停就释放了连接"
        assert "DIAG:SIMU:CLOSE" in writes

    async def test_start_confirms_closed_even_with_cold_cache(self):
        """GO 后首读 CLOSED 被复查否决成 RUNNING → 目标其实达成了。"""
        d, _ = _drv(state=["CLOSED", "RUNNING"])
        d._loaded_emulation_file = None
        assert await d.start_emulation() is True
        assert d._emulation_running is True

    async def test_monitoring_path_keeps_cache_gate(self):
        """反向: 监控路 (1 Hz) **保持**按缓存早退 —— 那里多一条 STATE? 是每秒成本,
        而误信一拍 CLOSED 只影响这一秒的上报 (下一拍自愈), 卸载另有守门。"""
        # 队列按调用顺序: ①`_ensure_topology` 冷缓存时先探一次 (既有行为) ②监控自己读
        # ③若发生复查才会取到的值。报 CLOSED = 没走 ③ = 监控路仍按缓存早退。
        d, _ = _drv(state=["CLOSED", "CLOSED", "RUNNING"])
        d._loaded_emulation_file = None
        m = await d.get_metrics()
        assert m.metrics["simulation_state"] == "CLOSED", "监控路不该为 CLOSED 多发一条复查"
