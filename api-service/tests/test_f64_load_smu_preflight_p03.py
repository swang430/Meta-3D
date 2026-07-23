"""P0-3 (2026-07-23): F64 load .smu 手册化前置序列 + 回读 —— 驱动层回归。

治现场"load .smu 从没成功"(旧盲发 CLOSE 吞错 → CALC:FILT:FILE 超时)。手册序列
(NotebookLM「PROPSIM 资料」查证):
  drain → STATE?判态 →(RUNNING则STOP+*OPC?; 瞬态则*OPC?等稳)→ CLOSE → *OPC? →
  ★复查 STATE?==CLOSED → 抬超时 FILE → *OPC? → SYST:ERR?门 → ★CENT:CH?回读真频。

⚠ P0-3 缩范围 (用户 2026-07-23 拍板): helper 只做 **load 序列 + 频率回读**。拓扑/
端口从仪器回读 (MODEL:INFO? / CENT GROup 寻址) 留 F64R-2, 本文件不验拓扑同步 —— 默认
文件的硬编码拓扑同步保护在 test_f64_default_emulation_file.py。

覆盖:
- 加载全序列成功 + CENT:CH? 回读真频 (未 GO, pipeline=GCM)。
- RUNNING → 先 STOP 再 CLOSE; OPENING 瞬态 *OPC? 等稳。
- ★CLOSE 后 STATE?≠CLOSED → fail-loud, 不硬闯 FILE (现场超时根因的正解)。
- 加载错误 (SYST:ERR?) / 超时异常 → fail-loud + 清 stale。
- F2: 加载失败清 stale 回读频率 → get_frequency_identity 不残留旧值。
- F4: 加载失败复位 _emulation_running。
- load_local_scenario 与 set_channel_model 共用 helper。
- get_frequency_identity 回读真频 > 文件名 (治说谎)。
- F1 (pre-commit fan-out): _readback_center_freq_mhz 在**全部 6 条**"离开 GCM 加载态"
  路径清空 (connect/disconnect/reset/ASC 成功/ASC 失败/B-2 参数化 TDL) → 切场景/重连后
  identity 不谎报上一步真频 (GCM→ASC / GCM→B-2 最真实)。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.hal.propsim_f64 import F64BypassMode, F64Pipeline, RealPropsimF64Driver

SYST_FAIL = '-200,"Execution error;No simulation opened"'


def _driver(
    state_seq=("STOPPED", "CLOSED"),
    center_freq="3550",
    err_seq=None,
    raise_on=None,
):
    """state_seq: DIAG:SIMU:STATE? 依次返回 (模拟状态转移; 用尽后重复最后一个)。
    helper 查两次 STATE? (加载前 + CLOSE 后复查), 故 seq 至少 2 个。
    center_freq: CALC:FILT:CENT:CH? 回读值 (identity 真频源)。
    err_seq: {写命令(精确): [该命令后 SYST:ERR? 依次返回]}。
    raise_on: 命中子串的写命令抛 TimeoutError (模拟 VI_ERROR_TMO)。
    P0-3 缩范围: helper 不查 MODEL:INFO? (拓扑回读留 F64R-2), 故无 model_info mock。"""
    drv = RealPropsimF64Driver("f64-p03", {})
    drv._channel_count = 64
    visa = MagicMock()
    drv._visa_resource = visa
    states = list(state_seq)
    errs = {k: list(v) for k, v in (err_seq or {}).items()}
    last = {"cmd": None}

    async def _w(cmd, timeout=None):
        last["cmd"] = cmd
        visa.write(cmd)
        if raise_on and raise_on in cmd:
            raise TimeoutError("VI_ERROR_TMO")

    async def _q(cmd, timeout=None):
        if cmd == "*OPC?":
            return "1"
        if cmd == "DIAG:SIMU:STATE?":
            return states.pop(0) if len(states) > 1 else (states[0] if states else "CLOSED")
        if cmd.startswith("CALC:FILT:CENT:CH?"):
            return center_freq
        if cmd == "SYST:ERR?":
            seq = errs.get(last["cmd"])
            if seq:
                return seq.pop(0)
            return '0,"No error"'
        return '0,"No error"'

    drv._write = _w  # type: ignore[assignment]
    drv._query = _q  # type: ignore[assignment]
    return drv, visa


def _writes(visa):
    return [c.args[0] for c in visa.write.call_args_list]


# ---------------------------------------------------------------------------
# load_local_scenario — 手册化前置序列
# ---------------------------------------------------------------------------


class TestLoadLocalScenario:
    async def test_empty_path_false(self):
        drv, visa = _driver()
        assert await drv.load_local_scenario("") is False
        assert _writes(visa) == []
        assert "空文件路径" in (drv._last_error or "")

    async def test_full_sequence_success_readback_freq(self):
        """加载成功: 从停态 → CLOSE → 复查 CLOSED → FILE → CENT:CH? 回读真频(3550),
        未 GO。P0-3 缩范围: 只回读频率, 不回读拓扑 (MODEL:INFO? 留 F64R-2)。"""
        drv, visa = _driver(
            state_seq=("STOPPED", "CLOSED"), center_freq="3550"
        )
        assert await drv.load_local_scenario("D:\\UMa_3600M.smu") is True
        assert drv._loaded_emulation_file == "D:\\UMa_3600M.smu"
        assert drv._readback_center_freq_mhz == 3550.0
        assert drv._center_freq_mhz == 3550.0
        assert drv._center_freq_programmed is False  # 未显式下发, 走回读
        assert drv._emulation_running is False  # CLOSE 已停, 未 GO
        assert drv._active_pipeline == F64Pipeline.GCM_NATIVE
        w = _writes(visa)
        assert "DIAG:SIMU:CLOSE" in w
        assert w.index("DIAG:SIMU:CLOSE") < w.index("CALC:FILT:FILE D:\\UMa_3600M.smu")

    async def test_running_stops_before_close(self):
        """加载前 RUNNING → 先 DIAG:SIMU:STOP 再 CLOSE (手册: pause 语义 + *OPC?)。"""
        drv, visa = _driver(state_seq=("RUNNING", "CLOSED"))
        assert await drv.load_local_scenario("D:\\x.smu") is True
        w = _writes(visa)
        assert "DIAG:SIMU:STOP" in w
        assert w.index("DIAG:SIMU:STOP") < w.index("DIAG:SIMU:CLOSE")

    async def test_transient_opening_waits_then_closes(self):
        """加载前 OPENING 瞬态 → *OPC? 等稳后 CLOSE (不 while 轮询)。"""
        drv, visa = _driver(state_seq=("OPENING", "CLOSED"))
        assert await drv.load_local_scenario("D:\\x.smu") is True
        assert "DIAG:SIMU:CLOSE" in _writes(visa)

    async def test_close_not_confirmed_preserves_identity_no_file(self):
        """★核心 + Codex #223 复审: CLOSE 后 STATE?≠CLOSED (STOPPED = 旧场景仍加载, 只暂停,
        CLOSE 未卸载) → fail-loud + **不发 CALC:FILT:FILE** (现场'CLOSE 撞 wrong state → FILE
        超时'正解) + **保留旧 identity** (旧场景冷缓存 GO 还能起, 一致性网该核对旧频率, 别报
        None 漏掉) + 仅置 running=False (STOPPED=暂停非运行)。"""
        drv, visa = _driver(state_seq=("STOPPED", "STOPPED"), center_freq="3550")
        drv._loaded_emulation_file = "D:\\old.smu"  # 旧场景仍加载
        drv._readback_center_freq_mhz = 3550.0
        drv._emulation_running = True
        assert await drv.load_local_scenario("D:\\x.smu") is False
        w = _writes(visa)
        assert not any(c.startswith("CALC:FILT:FILE") for c in w)  # 没硬闯 FILE
        assert "STATE?=STOPPED≠CLOSED" in (drv._last_error or "")
        # 旧场景仍加载 (CLOSE 未卸载) → identity 保留、running 置 False
        assert drv._loaded_emulation_file == "D:\\old.smu"
        assert drv._readback_center_freq_mhz == 3550.0
        assert drv._emulation_running is False
        assert drv.get_frequency_identity() is not None  # 报旧频率, 非 None

    async def test_load_error_fails_clears_stale(self):
        """CLOSE 成功但 CALC:FILT:FILE 后 SYST:ERR? 有错 → fail-loud + 清 stale file。"""
        fp = "D:\\bad.smu"
        drv, _ = _driver(
            state_seq=("STOPPED", "CLOSED"),
            err_seq={f"CALC:FILT:FILE {fp}": [SYST_FAIL]},
        )
        drv._loaded_emulation_file = "old.smu"
        assert await drv.load_local_scenario(fp) is False
        assert drv._loaded_emulation_file is None
        assert "load .smu failed" in (drv._last_error or "")

    async def test_file_timeout_exception_fails_clears(self):
        """CALC:FILT:FILE 抛 VI_ERROR_TMO → fail-loud + 清 stale (异常路径)。"""
        drv, _ = _driver(state_seq=("STOPPED", "CLOSED"), raise_on="CALC:FILT:FILE")
        drv._loaded_emulation_file = "old.smu"
        assert await drv.load_local_scenario("D:\\new.smu") is False
        assert drv._loaded_emulation_file is None

    async def test_load_err_after_confirmed_close_clears_stale_readback(self):
        """F2: 加载 A 成功回读真频(3550) → 加载 B **确认卸载后 FILE 失败** (STATE?=CLOSED
        确认 CLOSE 真卸载了 A → FILE 报错) → 清 stale readback (A 已卸载、B 没加载上 →
        identity None)。对比 close≠CLOSED 保留 (A 仍加载, 见 test_close_not_confirmed)。"""
        drv, _ = _driver(
            state_seq=("STOPPED", "CLOSED", "STOPPED", "CLOSED"), center_freq="3550",
            err_seq={"CALC:FILT:FILE D:\\B.smu": [SYST_FAIL]},
        )
        assert await drv.load_local_scenario("D:\\A_3600M.smu") is True
        assert drv._readback_center_freq_mhz == 3550.0
        assert drv.get_frequency_identity() is not None  # A 加载后有真频身份
        assert await drv.load_local_scenario("D:\\B.smu") is False
        assert drv._readback_center_freq_mhz is None  # A 已确认卸载 + B 失败 → 清
        assert drv.get_frequency_identity() is None

    async def test_load_failure_resets_emulation_running(self):
        """F4: close≠CLOSED (STOPPED=暂停) 也置 _emulation_running=False。先置 True (模拟
        上一场景在播) 再触发, 证明 STOPPED 态下 running 如实标停 (identity 另测保留)。"""
        drv, _ = _driver(state_seq=("STOPPED", "STOPPED"))  # CLOSE 后≠CLOSED → 失败
        drv._emulation_running = True
        assert await drv.load_local_scenario("D:\\x.smu") is False
        assert drv._emulation_running is False


# ---------------------------------------------------------------------------
# get_frequency_identity — 回读真频优先于文件名
# ---------------------------------------------------------------------------


class TestFrequencyIdentityReadback:
    async def test_readback_freq_after_load(self):
        """加载后 CENT:CH? 回读 3550 → identity 走回读真频 (非文件名 3600)。"""
        drv, _ = _driver(state_seq=("STOPPED", "CLOSED"), center_freq="3550")
        assert await drv.load_local_scenario("D:\\UMa_3600M.smu") is True
        with patch.object(drv, "_parse_loaded_center_freq_mhz") as mock_parse:
            ident = drv.get_frequency_identity()
            mock_parse.assert_not_called()  # 回读优先, 不落文件名解析
        assert ident is not None

    def test_programmed_still_wins_over_readback(self):
        """显式下发过 (programmed) → 仍优先 programmed 频 (回读只在未下发时用)。"""
        drv, _ = _driver()
        drv._center_freq_programmed = True
        drv._center_freq_mhz = 3500.0
        drv._readback_center_freq_mhz = 3550.0
        with patch.object(drv, "_parse_loaded_center_freq_mhz") as mock_parse:
            drv.get_frequency_identity()
            mock_parse.assert_not_called()

    def test_filename_fallback_when_no_readback(self):
        """既没 programmed 也没回读 → 降级文件名解析。"""
        drv, _ = _driver()
        drv._center_freq_programmed = False
        drv._readback_center_freq_mhz = None
        drv._loaded_emulation_file = "D:\\UMa_3600M.smu"
        with patch.object(drv, "_parse_loaded_center_freq_mhz", return_value=3600.0) as mock_parse:
            drv.get_frequency_identity()
            mock_parse.assert_called_once()


# ---------------------------------------------------------------------------
# set_channel_model — 共用 helper + CENT per-group
# ---------------------------------------------------------------------------


class TestSetChannelModelPreflight:
    async def test_set_channel_model_uses_preflight(self):
        """set_channel_model 走同一 helper: STATE?/STOP/CLOSE/复查/FILE/回读。"""
        drv, visa = _driver(state_seq=("STOPPED", "CLOSED"))
        drv._default_emulation_file = "D:\\default.smu"
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\default.smu"}
        )
        assert ok is True
        w = _writes(visa)
        assert "DIAG:SIMU:CLOSE" in w
        # 默认文件加载 → 硬编码拓扑同步 4x4 (P0-3 缩范围保留旧行为; MODEL:INFO?
        # 仪器回读留 F64R-2)。构造默认文件 == driver 默认 → 触发同步。
        assert (drv._tx_antennas, drv._rx_antennas) == (4, 4)

    async def test_set_channel_model_close_not_confirmed_fails(self):
        """set_channel_model 的 CLOSE 复查也 fail-loud (helper 共享)。"""
        drv, _ = _driver(state_seq=("STOPPED", "RUNNING"))  # CLOSE 后非 CLOSED
        drv._default_emulation_file = "D:\\default.smu"
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\default.smu"}
        )
        assert ok is False
        assert drv._loaded_emulation_file is None


# ---------------------------------------------------------------------------
# F1 fan-out (pre-commit finding): _readback_center_freq_mhz 是 P0-3 新加的
# identity 源, 必须在**所有**"F64 离开有效 .smu 加载态"的复位点清掉, 否则切
# 场景 / 重连后 get_frequency_identity 谎报上一步真频 → measure 三方一致性网
# 误判 (strict 下假 FAILED; 恰好相等则假通过放行未 load 的频率)。GCM load 成功/
# 失败两处已在上面覆盖, 这里补 connect / disconnect / ASC 成功 / reset 四处。
# ---------------------------------------------------------------------------


class TestIdentityResetNetFanout:
    async def test_reset_clears_identity_chain(self):
        """*RST → 清整个 identity 链 (programmed + loaded + readback) → identity 报 None
        (否则 reset 后仍报上次 load/下发的 stale 频率)。"""
        drv, _ = _driver()
        drv._readback_center_freq_mhz = 3550.0
        drv._center_freq_programmed = True
        drv._center_freq_mhz = 3550.0
        drv._loaded_emulation_file = "D:\\old.smu"
        assert await drv.reset() is True
        assert drv._readback_center_freq_mhz is None
        assert drv._center_freq_programmed is False
        assert drv._loaded_emulation_file is None
        assert drv.get_frequency_identity() is None

    async def test_disconnect_clears_readback_freq(self):
        """断开终态清 readback → 堵"断开后 identity 仍报旧真频"窗口 (懒重连现场常态:
        断开后、下次 load 前查 identity 不该谎报上会话真频)。"""
        drv, _ = _driver()
        drv._readback_center_freq_mhz = 3550.0
        drv._loaded_emulation_file = "D:\\old.smu"
        drv._emulation_running = False  # 免走 stop_emulation 分支
        await drv.disconnect()
        assert drv._readback_center_freq_mhz is None
        assert drv.get_frequency_identity() is None

    async def test_asc_success_clears_prior_gcm_readback(self):
        """★最真实触发面 (agent 指出的 GCM→ASC 泄漏): 计划第 1 步 GCM 回读真频 3550 →
        第 2 步切 ASC 成功。ASC 频率由 channel-engine 按 TestCase 生成、不在 F64 状态 →
        identity 契约应报 None 让一致性网跳过 F64。必须清 GCM 残留 readback + programmed,
        否则 measure 三方比对拿残留 3550 误判。"""
        drv, _ = _driver(state_seq=("CLOSED",))  # ASC 复查 CLOSE 已卸载 → CLOSED
        drv._readback_center_freq_mhz = 3550.0  # 上一 GCM 步残留
        drv._center_freq_programmed = False
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["runtime_emulation.smu"]
        ):
            ok = await drv.upload_asc_files("/local/asc", "UMa CDL-C")
        assert ok is True
        assert drv._readback_center_freq_mhz is None
        assert drv._center_freq_programmed is False
        assert drv._loaded_emulation_file is not None  # ASC 文件已加载
        # ASC runtime 文件名无频率 pattern → identity 报 None (一致性网跳过 F64)
        assert drv.get_frequency_identity() is None

    async def test_connect_reset_net_clears_stale_readback(self):
        """连接起始复位网含新字段: 跨重连清 stale (无真仪器 → 连接失败, 但顶部复位网
        在 try 之前已跑, 证明懒重连后未 load 前查 identity 不谎报上会话真频)。"""
        drv, _ = _driver()
        drv._readback_center_freq_mhz = 3550.0
        drv._center_freq_programmed = True
        drv._loaded_emulation_file = "D:\\old.smu"
        with patch("pyvisa.ResourceManager", side_effect=RuntimeError("no instrument")):
            assert await drv.connect() is False
        assert drv._readback_center_freq_mhz is None
        assert drv._center_freq_programmed is False
        assert drv._loaded_emulation_file is None

    async def test_b2_success_clears_prior_gcm_readback(self):
        """★第 6 条"离开 GCM 加载态"路径 (pre-commit 复验补): B-2 参数化 TDL。计划第 1 步
        GCM 回读真频 3550 → 第 2 步切 B-2 (load_parametric_tdl 成功) → identity 契约报 None
        (B-2 载频不在 F64 GCM 状态)。清 GCM 残留 readback + programmed, 与 ASC 同构。"""
        drv, _ = _driver(state_seq=("CLOSED",))  # B-2 复查 CLOSE 已卸载 → CLOSED
        drv._readback_center_freq_mhz = 3550.0  # 上一 GCM 步残留
        drv._center_freq_programmed = False
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["b2_model.rtc"]
        ):
            ok = await drv.load_parametric_tdl("/local/b2", "UMa TDL")
        assert ok is True
        assert drv._readback_center_freq_mhz is None
        assert drv._center_freq_programmed is False
        # B-2 .rtc 文件名无频率 pattern → identity 报 None (一致性网跳过 F64)
        assert drv.get_frequency_identity() is None

    async def test_b2_load_failure_clears_stale_identity(self):
        """B-2 加载失败 (SYST:ERR?) → 清 stale loaded/programmed/readback (CLOSE 已停旧
        仿真, 与 ASC/GCM 失败对称; 修前 B-2 失败分支连 loaded 都不清 = 谎报旧 GCM 还开着)。"""
        drv, _ = _driver(
            state_seq=("CLOSED",),  # B-2 复查 CLOSE 已卸载 → 进 FILE
            err_seq={"CALC:FILT:FILE D:\\B2\\M\\b2_model.rtc": [SYST_FAIL]},
        )
        drv.waveform_dir = "D:\\B2"  # 令 remote 路径确定, 精确匹配 err_seq 键
        drv._readback_center_freq_mhz = 3550.0  # 上一 GCM 步残留
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["b2_model.rtc"]
        ):
            ok = await drv.load_parametric_tdl("/local/b2", "M")
        assert ok is False
        assert drv._loaded_emulation_file is None
        assert drv._readback_center_freq_mhz is None
        assert drv.get_frequency_identity() is None

    async def test_asc_exception_after_close_clears_identity(self):
        """Codex #223 P2: ASC 路 CLOSE 已发后 CALC:FILT:FILE 超时 (VI_ERROR_TMO, 正是现场
        load 失败模式) → 异常跳到通用 except, 绕过成功/失败分支的 identity 清理。CLOSE 已停
        旧 GCM 仿真, 必须在异常路径清 identity, 否则 get_frequency_identity 谎报旧真频。"""
        drv, _ = _driver(state_seq=("CLOSED",), raise_on="CALC:FILT:FILE")
        drv._readback_center_freq_mhz = 3550.0  # 上一 GCM 残留
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["runtime_emulation.smu"]
        ):
            ok = await drv.upload_asc_files("/local/asc", "UMa")
        assert ok is False
        assert drv._loaded_emulation_file is None
        assert drv._readback_center_freq_mhz is None
        assert drv.get_frequency_identity() is None

    async def test_b2_exception_after_close_clears_identity(self):
        """Codex #223 P2: B-2 路 CLOSE 已发后 CALC:FILT:FILE 超时 → 异常路径清 identity
        (与 ASC 同构; close_issued 标志区分 CLOSE 前后)。"""
        drv, _ = _driver(state_seq=("CLOSED",), raise_on="CALC:FILT:FILE")
        drv._readback_center_freq_mhz = 3550.0
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["b2_model.rtc"]
        ):
            ok = await drv.load_parametric_tdl("/local/b2", "M")
        assert ok is False
        assert drv._loaded_emulation_file is None
        assert drv._readback_center_freq_mhz is None
        assert drv.get_frequency_identity() is None

    async def test_exception_before_close_keeps_identity(self):
        """close_issued 语义反向验证: 异常发生在 CLOSE **之前** (FTP 抛错) → 旧仿真仍开,
        identity **不动** (不能谎报 None 让一致性网漏掉仍在跑的旧 GCM)。防"异常路径无脑清"
        的过度修正。"""
        drv, _ = _driver()
        drv._readback_center_freq_mhz = 3550.0
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        with patch.object(
            drv, "_ftp_upload_directory", side_effect=TimeoutError("FTP down")
        ):
            ok = await drv.upload_asc_files("/local/asc", "UMa")
        assert ok is False
        # CLOSE 未发 → 旧 GCM 仍开 → identity 保留 (未清)
        assert drv._readback_center_freq_mhz == 3550.0
        assert drv._loaded_emulation_file == "D:\\old_gcm.smu"

    async def test_gcm_helper_exception_before_close_keeps_identity(self):
        """Codex #223 第四条 (GCM helper 路, 与 ASC before_close 同构): 加载前 RUNNING →
        DIAG:SIMU:STOP 超时 (STOP 是 pause 语义, 不卸载) → CLOSE 未发, 旧 GCM 仍加载 →
        identity **保留旧频率** (清成 None 会让一致性网漏报仍在跑的旧 GCM)。验证清理已从
        调用方移进 helper 且受 close_issued gate 保护 (调用方不再无条件清)。"""
        drv, _ = _driver(state_seq=("RUNNING", "CLOSED"), raise_on="DIAG:SIMU:STOP")
        drv._readback_center_freq_mhz = 3550.0  # 旧 GCM 已加载, 真频 3550
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        ok = await drv.load_local_scenario("D:\\new.smu")
        assert ok is False
        # STOP 就超时 → CLOSE 未发 → 旧 GCM 仍加载 → identity 全保留
        assert drv._readback_center_freq_mhz == 3550.0
        assert drv._loaded_emulation_file == "D:\\old_gcm.smu"
        assert drv.get_frequency_identity() is not None  # 报旧 GCM 频率, 非 None

    async def test_gcm_helper_exception_after_close_clears_identity(self):
        """对照: 加载前 STOPPED (无 STOP), CLOSE 已发后 CALC:FILT:FILE 超时 → CLOSE 后
        异常, 旧仿真已停 → identity 清 (close_issued=True 分支)。锁 helper except 两侧行为。"""
        drv, _ = _driver(state_seq=("STOPPED", "CLOSED"), raise_on="CALC:FILT:FILE")
        drv._readback_center_freq_mhz = 3550.0
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        ok = await drv.load_local_scenario("D:\\new.smu")
        assert ok is False
        assert drv._readback_center_freq_mhz is None
        assert drv._loaded_emulation_file is None
        assert drv.get_frequency_identity() is None

    async def test_gcm_stop_succeeds_close_fails_pauses_but_keeps_identity(self):
        """Codex #223 复审 (running vs loaded 语义分离): RUNNING → STOP 成功 (暂停播放) →
        CLOSE 写失败 (close_issued 前) → identity **保留** (旧 GCM 仍加载, 未卸载) 但
        _emulation_running=**False** (STOP 已暂停, 不能报还在跑误导监控/拆卸)。"""
        drv, _ = _driver(state_seq=("RUNNING", "CLOSED"), raise_on="DIAG:SIMU:CLOSE")
        drv._readback_center_freq_mhz = 3550.0
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        drv._emulation_running = True
        ok = await drv.load_local_scenario("D:\\new.smu")
        assert ok is False
        # STOP 成功暂停 → running False; CLOSE 未发 → 旧 GCM 仍加载, identity 保留
        assert drv._emulation_running is False
        assert drv._readback_center_freq_mhz == 3550.0
        assert drv._loaded_emulation_file == "D:\\old_gcm.smu"
        assert drv.get_frequency_identity() is not None

    async def test_reset_opc_timeout_still_clears_identity(self):
        """Codex #223 复审 (clear-on-issue 非 on-confirm): *RST 写成功但 *OPC? 超时 →
        identity/state 仍清 (*RST 已关旧仿真, 清理已在 *OPC? 之前执行, except 不残留 stale)。"""
        drv, _ = _driver()
        drv._readback_center_freq_mhz = 3550.0
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        drv._center_freq_programmed = True
        drv._emulation_running = True

        async def _q_opc_timeout(cmd, timeout=None):
            if cmd == "*OPC?":
                raise TimeoutError("VI_ERROR_TMO")
            return '0,"No error"'

        drv._query = _q_opc_timeout  # *RST write 成功, 随后 *OPC? 超时
        ok = await drv.reset()
        assert ok is False
        # *RST 已发 → 缓存在 *OPC? 之前已清
        assert drv._loaded_emulation_file is None
        assert drv._readback_center_freq_mhz is None
        assert drv._center_freq_programmed is False
        assert drv._emulation_running is False
        assert drv.get_frequency_identity() is None


# ---------------------------------------------------------------------------
# 状态复位单一入口 (_apply_unload / _apply_session_reset) + 会话/pipeline 面
# (2026-07-23 状态机重构收敛同一 fan-out 母题, 修 F1-F4)。
# ---------------------------------------------------------------------------


class TestStateResetMethods:
    def test_apply_unload_clears_load_state_not_bypass(self):
        """_apply_unload 清 5 个加载态字段 (running/loaded/programmed/readback/pipeline),
        **不碰** _bypass_mode (bypass 是独立 config 旋钮, 仅会话边界复位)。"""
        drv, _ = _driver()
        drv._emulation_running = True
        drv._loaded_emulation_file = "x.smu"
        drv._center_freq_programmed = True
        drv._readback_center_freq_mhz = 3550.0
        drv._active_pipeline = F64Pipeline.GCM_NATIVE
        drv._bypass_mode = F64BypassMode.CALIBRATION
        drv._apply_unload()
        assert drv._emulation_running is False
        assert drv._loaded_emulation_file is None
        assert drv._center_freq_programmed is False
        assert drv._readback_center_freq_mhz is None
        assert drv._active_pipeline is None
        assert drv._bypass_mode == F64BypassMode.CALIBRATION  # unload 不动 bypass

    def test_apply_session_reset_clears_all_six_incl_bypass(self):
        """_apply_session_reset = _apply_unload + bypass 复位 → 会话边界全清 6 字段。"""
        drv, _ = _driver()
        drv._emulation_running = True
        drv._loaded_emulation_file = "x.smu"
        drv._center_freq_programmed = True
        drv._readback_center_freq_mhz = 3550.0
        drv._active_pipeline = F64Pipeline.ASC_RUNTIME
        drv._bypass_mode = F64BypassMode.CALIBRATION
        drv._apply_session_reset()
        assert drv._emulation_running is False
        assert drv._loaded_emulation_file is None
        assert drv._center_freq_programmed is False
        assert drv._readback_center_freq_mhz is None
        assert drv._active_pipeline is None
        assert drv._bypass_mode == F64BypassMode.DISABLED  # F2/F3: 会话边界清 bypass

    async def test_asc_load_failure_clears_pipeline(self):
        """F1: ASC 加载失败 (CLOSE 后 load_err) → _apply_unload 清 pipeline, 别残留
        ASC_RUNTIME 让 set_runtime_environment gate 误放行"ASC 没加载成"。"""
        drv, _ = _driver(
            state_seq=("CLOSED",),  # ASC 复查 CLOSE 已卸载 → 进 FILE
            err_seq={"CALC:FILT:FILE D:\\A\\M\\runtime_emulation.smu": [SYST_FAIL]}
        )
        drv.waveform_dir = "D:\\A"
        drv._active_pipeline = F64Pipeline.GCM_NATIVE  # 上一步残留
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["runtime_emulation.smu"]
        ):
            ok = await drv.upload_asc_files("/local", "M")
        assert ok is False
        assert drv._active_pipeline is None
        assert drv._loaded_emulation_file is None

    async def test_asc_ftp_failure_preserves_old_pipeline(self):
        """F1: ASC FTP 失败 (CLOSE 前) → pipeline **不**乐观置 ASC (成功才置), 保留旧值
        (旧仿真仍加载, 别谎报切了 ASC)。"""
        drv, _ = _driver()
        drv._active_pipeline = F64Pipeline.GCM_NATIVE
        drv._loaded_emulation_file = "old_gcm.smu"
        with patch.object(drv, "_ftp_upload_directory", return_value=[]):  # FTP 无文件
            ok = await drv.upload_asc_files("/local", "M")
        assert ok is False
        assert drv._active_pipeline == F64Pipeline.GCM_NATIVE  # 未被乐观置 ASC
        assert drv._loaded_emulation_file == "old_gcm.smu"    # 旧 GCM 保留

    async def test_disconnect_resets_bypass(self):
        """F2: disconnect 终态清 _bypass_mode (它是唯一 disconnect+connect 都曾漏的字段)。"""
        drv, _ = _driver()
        drv._bypass_mode = F64BypassMode.CALIBRATION
        drv._emulation_running = False  # 免走 stop_emulation
        drv._loaded_emulation_file = "x.smu"
        await drv.disconnect()
        assert drv._bypass_mode == F64BypassMode.DISABLED

    async def test_connect_resets_full_session_state(self):
        """F3: connect 起始全清 6 字段 (running/pipeline/bypass 不止 3 个 identity)。"""
        drv, _ = _driver()
        drv._emulation_running = True
        drv._active_pipeline = F64Pipeline.ASC_RUNTIME
        drv._bypass_mode = F64BypassMode.BUTLER
        drv._loaded_emulation_file = "x.smu"
        with patch("pyvisa.ResourceManager", side_effect=RuntimeError("no instrument")):
            assert await drv.connect() is False
        assert drv._emulation_running is False
        assert drv._active_pipeline is None
        assert drv._bypass_mode == F64BypassMode.DISABLED
        assert drv._loaded_emulation_file is None

    async def test_gcm_helper_failure_does_not_set_pipeline(self):
        """F1 对称 (GCM 路补齐): set_channel_model helper 失败 (RUNNING→STOP 前超时, CLOSE
        前) → pipeline **不**乐观置 GCM, 保留旧值 (旧仿真是别的 pipeline, 仍加载)。修前
        dispatcher/顶部乐观置会残留 GCM 而 loaded=旧 ASC 不一致。"""
        drv, _ = _driver(state_seq=("RUNNING", "CLOSED"), raise_on="DIAG:SIMU:STOP")
        drv._default_emulation_file = "D:\\default.smu"
        drv._active_pipeline = F64Pipeline.ASC_RUNTIME  # 旧 ASC
        drv._loaded_emulation_file = "old_asc.smu"
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\default.smu"}
        )
        assert ok is False
        assert drv._active_pipeline == F64Pipeline.ASC_RUNTIME  # 未乐观置 GCM
        assert drv._loaded_emulation_file == "old_asc.smu"

    async def test_gcm_success_sets_pipeline(self):
        """set_channel_model 成功 → pipeline 置 GCM_NATIVE (成功才置, 与 load_local/ASC/B-2
        全路径对称 —— 完成"成功才置 pipeline"的决定性收敛)。"""
        drv, _ = _driver(state_seq=("STOPPED", "CLOSED"))
        drv._default_emulation_file = "D:\\default.smu"
        drv._active_pipeline = None
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": "D:\\default.smu"}
        )
        assert ok is True
        assert drv._active_pipeline == F64Pipeline.GCM_NATIVE

    async def test_asc_close_not_confirmed_preserves_identity(self):
        """Codex #223 复审 (ASC 路同构): CLOSE 后 STATE?≠CLOSED (STOPPED=旧场景仍加载) →
        保留 identity + **不硬闯 FILE** (旧盲发-CLOSE-硬闯-FILE 是现场 load 从没成功根因;
        走共享 _close_and_read_state, 三路统一)。"""
        drv, visa = _driver(state_seq=("STOPPED",))  # CLOSE 后仍 STOPPED
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        drv._readback_center_freq_mhz = 3550.0
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["runtime_emulation.smu"]
        ):
            ok = await drv.upload_asc_files("/local", "M")
        assert ok is False
        assert not any(c.startswith("CALC:FILT:FILE") for c in _writes(visa))  # 没硬闯 FILE
        assert drv._loaded_emulation_file == "D:\\old_gcm.smu"  # 旧场景保留
        assert drv._readback_center_freq_mhz == 3550.0

    async def test_b2_close_not_confirmed_preserves_identity(self):
        """Codex #223 复审 (B-2 路同构): CLOSE 后 STATE?≠CLOSED → 保留 identity + 不硬闯 FILE。"""
        drv, visa = _driver(state_seq=("STOPPED",))
        drv._loaded_emulation_file = "D:\\old_gcm.smu"
        drv._readback_center_freq_mhz = 3550.0
        with patch.object(
            drv, "_ftp_upload_directory", return_value=["b2_model.rtc"]
        ):
            ok = await drv.load_parametric_tdl("/local", "M")
        assert ok is False
        assert not any(c.startswith("CALC:FILT:FILE") for c in _writes(visa))  # 没硬闯 FILE
        assert drv._loaded_emulation_file == "D:\\old_gcm.smu"
        assert drv._readback_center_freq_mhz == 3550.0
