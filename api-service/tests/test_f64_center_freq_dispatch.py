"""P1-18: F64 中心频率下发正修 — 缺省不写 CENT + 工程真值解析。

2026-07-03 现场 ⭐⭐⭐ bug: set_channel_model Step 4 原先参数缺省也无条件把
self._center_freq_mhz (默认 3500 或上次遗留) 写满全部通道, 冲掉 .smu 工程
频率 (3550 工程被写成 3500), 输入测量 / AUTOSET / 吞吐全链错位。

正修语义 (本文件钉死):
- 缺省 → 一条 CENT 都不写 (尊重工程), programmed 复位 (identity 退文件名 loose);
- 显式 → 全通道写 + programmed 置位 + identity 用下发值;
- None 视同缺省 (边缘值枚举, feedback_endpoint_null_field_cartesian);
- configure 顶层频率并进 parameters 直通 (不再依赖"缺省写内存值"旧机制);
- .smu 工程 INI 的 CenterFrequency 是登记真值源 (smu_project 解析器)。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.smu_project import (
    parse_smu_project_center_freqs_hz,
    parse_smu_project_primary_freq_mhz,
)


def _make_driver(config=None, channels=4, *, groups=None):
    """groups: {组号: [该组通道...]}。F64R-2 后 CENT 按**组**下发 (每组一条, 用该组
    代表通道), 故 fake 要能应答 GROUP:*。

    默认 = **全部通道同 1 组**: 本 fake 造的是 1 输入 × N 输出, 所有通道共用那 1 个
    输入口, 按手册 §20.4.6.1 (同输入或同输出即同组) **必然同组** —— 所以 CENT 只发
    1 条。多组形态见 test_f64_topology_readback_f64r2.py 的互不重叠拓扑用例。"""
    drv = RealPropsimF64Driver("propsim-test", config or {})
    drv._channel_count = channels
    # ⚠ 手册 §20.4.6.1: 同输入**或**同输出即同组 (有传递性)。本 fake 是 1 输入 × N 输出,
    # 所有通道共用那 1 个输入 ⇒ **必然同属 1 组**。旧的"每通道自成一组"物理上不可能。
    group_map = groups if groups is not None else {1: list(range(1, channels + 1))}
    visa = MagicMock()

    def _router(cmd):
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            return '0,"No error"'
        # 加载走 _load_smu_with_preflight — STATE? 判态 + CLOSE 后复查 ==CLOSED 才继续;
        # CENT:CH? 回读真频; F64R-2 起再回读拓扑 (MODEL:INFO? + GROUP:*)。CENT 设频
        # 循环按**回读的组**走, 不再看 _channel_count。这些查询均不碰 SYST:ERR?, 故
        # CENT 被拒 / 加载失败的判定语义不变。
        if cmd == "DIAG:SIMU:STATE?":
            return "CLOSED"
        if cmd.startswith("CALC:FILT:CENT:CH?"):
            return ""  # 回读真频不可用 → 非致命 (本文件不验 identity)
        if cmd == "DIAG:SIMU:MODEL:INFO?":
            # <inputs>,<channels>,<outputs> — 取 1 输入 × N 输出 使 1×N=N 自洽
            return f"1,{channels},{channels}"
        if cmd == "GROUP:GET?":
            return str(len(group_map))
        if cmd.startswith("GROUP:CHANNELS:GET?"):
            g = int(cmd.split("?", 1)[1].strip())
            return ",".join(str(c) for c in group_map[g])
        if cmd.startswith("GROUP:INPUTS:GET?"):
            return "1"                                # 1 个输入口 (与 INFO? 的 inputs=1 一致)
        if cmd.startswith("GROUP:OUTPUTS:GET?"):
            # 与"全部通道 1 组"自洽: 该组占用全部输出口
            return ",".join(str(o) for o in range(1, channels + 1))
        if cmd.startswith("ROUT:PATH:CONN?"):
            return "B1.1"
        return '0,"No error"'

    visa.query.side_effect = _router
    visa.write.return_value = None
    drv._visa_resource = visa

    async def _async_write(cmd, timeout=None):
        visa.write(cmd)

    async def _async_query(cmd, timeout=None, **_kw):
        return visa.query(cmd)

    drv._write = _async_write  # type: ignore[assignment]
    drv._query = _async_query  # type: ignore[assignment]
    return drv, visa


def _cent_writes(visa):
    return [
        c.args[0] for c in visa.write.call_args_list
        if c.args[0].startswith("CALC:FILT:CENT:CH")
    ]


class TestCentDispatchOnlyWhenExplicit:
    async def test_default_load_writes_no_cent(self):
        """缺省加载 → 零 CENT 写 (工程频率不被冲), programmed 保持 False。"""
        drv, visa = _make_driver()
        assert await drv.set_channel_model("CDL-C", "UMa", {}) is True
        assert _cent_writes(visa) == []
        assert drv._center_freq_programmed is False

    async def test_explicit_freq_dispatched_per_group_and_marks_programmed(self):
        """显式给频 → 按**组**下发 (F64R-2)。本 fake 是 1 输入 × 4 输出, 4 条通道共用
        那个输入 ⇒ 同 1 组 ⇒ 只发 1 条 (旧行为是写满 4 条通道)。"""
        drv, visa = _make_driver(channels=4)
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"center_frequency_mhz": 3549.99}
        )
        assert ok is True
        writes = _cent_writes(visa)
        assert len(writes) == 1
        assert all(w.endswith(",3549.99") for w in writes), writes
        assert drv._center_freq_programmed is True
        assert drv._center_freq_mhz == 3549.99

    async def test_none_freq_treated_as_absent(self):
        """显式 null 不能变成字面 'CENT:CH 1,None' 下发 (边缘值枚举)。"""
        drv, visa = _make_driver()
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"center_frequency_mhz": None}
        )
        assert ok is True
        assert _cent_writes(visa) == []
        assert drv._center_freq_programmed is False

    async def test_default_reload_resets_programmed_flag(self):
        """显式下发后再缺省加载 → programmed 复位 (identity 不残留旧显式值)。"""
        drv, visa = _make_driver()
        assert await drv.set_channel_model(
            "CDL-C", "UMa", {"center_frequency_mhz": 3600.0}
        ) is True
        assert drv._center_freq_programmed is True
        visa.write.reset_mock()
        assert await drv.set_channel_model("CDL-C", "UMa", {}) is True
        assert _cent_writes(visa) == []  # 遗留 3600 不冲新工程
        assert drv._center_freq_programmed is False

    async def test_configure_top_level_freq_flows_into_load(self):
        """configure 顶层频率并进 parameters 直通下发 (旧'缺省写内存值'机制已拆)。"""
        drv, visa = _make_driver(channels=2)
        ok = await drv.configure({
            "channel_model": "CDL-C",
            "center_frequency_mhz": 3600.0,
        })
        assert ok is True
        writes = _cent_writes(visa)
        assert len(writes) == 1          # 2 通道共用 1 输入 ⇒ 同组 ⇒ 1 条
        assert all(w.endswith(",3600.0") for w in writes), writes
        assert drv._center_freq_programmed is True

    async def test_configure_none_freq_not_programmed(self):
        """configure 显式 null 视同缺省 (不置 programmed, 不污染 identity)。"""
        drv, _ = _make_driver()
        assert await drv.configure({"center_frequency_mhz": None}) is True
        assert drv._center_freq_programmed is False

    async def test_configure_no_model_still_programs_cache(self):
        """agent 门审 F2 边界: configure 无 channel_model → 只更内存缓存不发
        SCPI, programmed 仍置 (缓存即真值, 无下发可拒; 旧语义保持)。"""
        drv, _ = _make_driver()
        assert await drv.configure({"center_frequency_mhz": 3600.0}) is True
        assert drv._center_freq_mhz == 3600.0
        assert drv._center_freq_programmed is True

    async def test_configure_with_model_cent_rejected_no_programmed(self):
        """agent 门审 F2: configure 有 model + CENT 被拒 → programmed 不残留
        (原 configure 抢先置 True, CENT 门后被拒会留'标称已下发但没发')。"""
        drv = RealPropsimF64Driver("propsim-cfg-rej", {})
        drv._channel_count = 2
        visa = MagicMock()
        queue: list = []

        async def _w(cmd, timeout=None):
            visa.write(cmd)
            if cmd.startswith("CALC:FILT:CENT:CH"):
                queue.append('-222,"Data out of range"')

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return queue.pop(0) if queue else '0,"No error"'
            # 加载前置 STATE? 判态 + CLOSE 后复查 ==CLOSED; CENT:CH? 回读真频;
            # F64R-2 起再回读拓扑 (MODEL:INFO? + GROUP:*) —— CENT 改按**组**下发,
            # 1 输入 × 2 输出 = 2 通道, 共用那 1 个输入 ⇒ 按手册 §20.4.6.1 **同 1 组**
            # (同输入或同输出即同组) → CENT 只发 1 条。
            # 均**不碰** SYST:ERR? 注入队列 → CENT 被拒 / 加载失败判定语义不变。
            if cmd == "DIAG:SIMU:STATE?":
                return "CLOSED"
            if cmd.startswith("CALC:FILT:CENT:CH?"):
                return ""  # 回读 None → identity 走文件名兜底 (test_cent_rejected 需要)
            if cmd == "DIAG:SIMU:MODEL:INFO?":
                return "1,2,2"
            if cmd == "GROUP:GET?":
                return "1"                            # 2 通道共用 1 输入 ⇒ 同 1 组
            if cmd.startswith("GROUP:CHANNELS:GET?"):
                return "1,2"
            if cmd.startswith("GROUP:INPUTS:GET?"):
                return "1"
            if cmd.startswith("GROUP:OUTPUTS:GET?"):
                return "1,2"
            if cmd.startswith("ROUT:PATH:CONN?"):
                return "B1.1"
            return '0,"No error"'

        drv._visa_resource = visa
        drv._write = _w  # type: ignore[assignment]
        drv._query = _q  # type: ignore[assignment]
        ok = await drv.configure({
            "channel_model": "CDL-C", "center_frequency_mhz": 9999.0,
        })
        assert ok is False
        assert drv._center_freq_programmed is False  # 抢先置已移除

    async def test_cent_write_rejected_fails_loud_no_programmed(self):
        """R10 平行族: CENT 写序列被拒 (队列有 -222 越界) → set_channel_model
        return False + programmed 不置 (R8 被拒状态不动) — 频率没设进去不许
        假成功让下游按错频跑。"""
        drv = RealPropsimF64Driver("propsim-cent-rej", {})
        drv._channel_count = 2
        visa = MagicMock()
        # 写后注入模型 (比固定队列稳): CENT 写命令后往队列压 -222; drain 循环
        # 读到 clean 才停, 所以只有"写序列产生"的错误留给门。
        queue: list = []

        async def _w(cmd, timeout=None):
            visa.write(cmd)
            if cmd.startswith("CALC:FILT:CENT:CH"):
                queue.append('-222,"Data out of range"')

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return queue.pop(0) if queue else '0,"No error"'
            # 加载前置 STATE? 判态 + CLOSE 后复查 ==CLOSED; CENT:CH? 回读真频;
            # F64R-2 起再回读拓扑 (MODEL:INFO? + GROUP:*) —— CENT 改按**组**下发,
            # 1 输入 × 2 输出 = 2 通道, 共用那 1 个输入 ⇒ 按手册 §20.4.6.1 **同 1 组**
            # (同输入或同输出即同组) → CENT 只发 1 条。
            # 均**不碰** SYST:ERR? 注入队列 → CENT 被拒 / 加载失败判定语义不变。
            if cmd == "DIAG:SIMU:STATE?":
                return "CLOSED"
            if cmd.startswith("CALC:FILT:CENT:CH?"):
                return ""  # 回读 None → identity 走文件名兜底 (test_cent_rejected 需要)
            if cmd == "DIAG:SIMU:MODEL:INFO?":
                return "1,2,2"
            if cmd == "GROUP:GET?":
                return "1"                            # 2 通道共用 1 输入 ⇒ 同 1 组
            if cmd.startswith("GROUP:CHANNELS:GET?"):
                return "1,2"
            if cmd.startswith("GROUP:INPUTS:GET?"):
                return "1"
            if cmd.startswith("GROUP:OUTPUTS:GET?"):
                return "1,2"
            if cmd.startswith("ROUT:PATH:CONN?"):
                return "B1.1"
            return '0,"No error"'

        drv._visa_resource = visa

        drv._write = _w  # type: ignore[assignment]
        drv._query = _q  # type: ignore[assignment]
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"center_frequency_mhz": 9999.0}
        )
        assert ok is False
        assert drv._center_freq_programmed is False  # 被拒不置
        assert "-222" in (drv._last_error or "")

    async def test_cent_rejected_resets_prior_programmed_true(self):
        """Codex #211 follow-up: 上一个 model 已置 programmed=True, 新 .smu
        load 成功但 CENT 被拒 → 复位 programmed=False (不残留旧频率谎报);
        get_frequency_identity 退回**新**文件名解析而非旧显式频率。"""
        drv = RealPropsimF64Driver("propsim-cent-dirty", {})
        drv._channel_count = 2
        # 脏态: 上一次成功 program 过 3600
        drv._center_freq_mhz = 3600.0
        drv._center_freq_programmed = True

        visa = MagicMock()
        queue: list = []

        async def _w(cmd, timeout=None):
            visa.write(cmd)
            if cmd.startswith("CALC:FILT:CENT:CH"):
                queue.append('-222,"Data out of range"')

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return queue.pop(0) if queue else '0,"No error"'
            # 加载前置 STATE? 判态 + CLOSE 后复查 ==CLOSED; CENT:CH? 回读真频;
            # F64R-2 起再回读拓扑 (MODEL:INFO? + GROUP:*) —— CENT 改按**组**下发,
            # 1 输入 × 2 输出 = 2 通道, 共用那 1 个输入 ⇒ 按手册 §20.4.6.1 **同 1 组**
            # (同输入或同输出即同组) → CENT 只发 1 条。
            # 均**不碰** SYST:ERR? 注入队列 → CENT 被拒 / 加载失败判定语义不变。
            if cmd == "DIAG:SIMU:STATE?":
                return "CLOSED"
            if cmd.startswith("CALC:FILT:CENT:CH?"):
                return ""  # 回读 None → identity 走文件名兜底 (test_cent_rejected 需要)
            if cmd == "DIAG:SIMU:MODEL:INFO?":
                return "1,2,2"
            if cmd == "GROUP:GET?":
                return "1"                            # 2 通道共用 1 输入 ⇒ 同 1 组
            if cmd.startswith("GROUP:CHANNELS:GET?"):
                return "1,2"
            if cmd.startswith("GROUP:INPUTS:GET?"):
                return "1"
            if cmd.startswith("GROUP:OUTPUTS:GET?"):
                return "1,2"
            if cmd.startswith("ROUT:PATH:CONN?"):
                return "B1.1"
            return '0,"No error"'

        drv._visa_resource = visa
        drv._write = _w  # type: ignore[assignment]
        drv._query = _q  # type: ignore[assignment]
        # 新加载文件名可解析出 3550 (区别于脏态旧显式 3600)
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {
                "center_frequency_mhz": 9999.0,
                "emulation_file": "D:\\Packs\\UMa_CDL-C_3550M.smu",
            }
        )
        assert ok is False
        assert drv._center_freq_programmed is False  # 从 True 复位
        # agent 门审 F: 钉可观测契约 (上报频率) 而非只钉内部标志 —— 复位后
        # identity 退回**新**文件名 3550, 不是脏态残留的旧显式 3600
        # (test_real_dispatch 母题: 若回归让 programmed=False 仍读 _center_
        # freq_mhz, field-only 断言会假绿, 本断言会红)。
        ident = drv.get_frequency_identity()
        assert ident is not None
        assert "3550" in ident.describe(), ident.describe()
        assert "3600" not in ident.describe(), ident.describe()

    async def test_load_rejected_clears_prior_loaded_file(self):
        """Codex #211 follow-up + #202 兜底: 上一次成功 load 过文件且 program
        过频率, 新 load 被拒 (CLOSE 已发) → 清空 _loaded_emulation_file **且**
        复位 _center_freq_programmed → get_frequency_identity 报 None (不谎报
        旧文件 / 旧 programmed 频率; #202 兜底: programmed 优先级 > 文件名,
        只清 loaded_file 仍会谎报)。"""
        drv = RealPropsimF64Driver("propsim-load-dirty", {})
        drv._channel_count = 2
        # 脏态: 上次成功加载 + 显式 program 过 3600
        drv._loaded_emulation_file = "D:\\old\\prev_3600M.smu"
        drv._center_freq_mhz = 3600.0
        drv._center_freq_programmed = True

        visa = MagicMock()
        queue: list = []

        async def _w(cmd, timeout=None):
            visa.write(cmd)
            if cmd.startswith("CALC:FILT:FILE"):
                queue.append('-200,"No simulation opened"')  # load 门被拒

        async def _q(cmd, timeout=None, **_kw):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return queue.pop(0) if queue else '0,"No error"'
            # 加载前置 STATE? 判态 + CLOSE 后复查 ==CLOSED; CENT:CH? 回读真频;
            # F64R-2 起再回读拓扑 (MODEL:INFO? + GROUP:*) —— CENT 改按**组**下发,
            # 1 输入 × 2 输出 = 2 通道, 共用那 1 个输入 ⇒ 按手册 §20.4.6.1 **同 1 组**
            # (同输入或同输出即同组) → CENT 只发 1 条。
            # 均**不碰** SYST:ERR? 注入队列 → CENT 被拒 / 加载失败判定语义不变。
            if cmd == "DIAG:SIMU:STATE?":
                return "CLOSED"
            if cmd.startswith("CALC:FILT:CENT:CH?"):
                return ""  # 回读 None → identity 走文件名兜底 (test_cent_rejected 需要)
            if cmd == "DIAG:SIMU:MODEL:INFO?":
                return "1,2,2"
            if cmd == "GROUP:GET?":
                return "1"                            # 2 通道共用 1 输入 ⇒ 同 1 组
            if cmd.startswith("GROUP:CHANNELS:GET?"):
                return "1,2"
            if cmd.startswith("GROUP:INPUTS:GET?"):
                return "1"
            if cmd.startswith("GROUP:OUTPUTS:GET?"):
                return "1,2"
            if cmd.startswith("ROUT:PATH:CONN?"):
                return "B1.1"
            return '0,"No error"'

        drv._visa_resource = visa
        drv._write = _w  # type: ignore[assignment]
        drv._query = _q  # type: ignore[assignment]
        ok = await drv.set_channel_model("CDL-C", "UMa", {})
        assert ok is False
        assert drv._loaded_emulation_file is None  # 旧文件清空 (CLOSE 已关)
        assert drv._center_freq_programmed is False  # 旧 programmed 复位
        # 可观测契约: 两个 stale 源 (programmed + 文件名) 都清 → identity 报
        # None (无加载), 不谎报旧 3600 (回归下若漏清 programmed 会报 3600)
        assert drv.get_frequency_identity() is None

    async def test_disconnect_resets_programmed_even_without_loaded_file(self):
        """Codex #202 兜底门审 F1: configure(freq) 不带 model → programmed=True
        + loaded_file=None; disconnect 无条件复位 programmed (原嵌 if loaded_
        file 块内会跳过 → 断开后 identity 谎报 stale 频率)。"""
        drv = RealPropsimF64Driver("propsim-disc", {})
        drv._channel_count = 2
        # freq-only-configure 态: programmed 但无加载文件
        drv._center_freq_mhz = 3600.0
        drv._center_freq_programmed = True
        assert drv._loaded_emulation_file is None

        visa = MagicMock()
        visa.close = MagicMock()
        visa.query = MagicMock(return_value='0,"No error"')

        async def _w(cmd, timeout=None):
            visa.write(cmd)

        async def _q(cmd, timeout=None, **_kw):
            return "1" if cmd == "*OPC?" else '0,"No error"'

        drv._visa_resource = visa
        drv._write = _w  # type: ignore[assignment]
        drv._query = _q  # type: ignore[assignment]
        await drv.disconnect()
        assert drv._center_freq_programmed is False  # 无条件复位 (不受 loaded_file 门控)
        assert drv.get_frequency_identity() is None  # 断开后不谎报旧 3600

    async def test_disconnect_resets_freq_even_when_close_raises(self):
        """门审复核: DIAG:SIMU:CLOSE 抛异常 (VISA I/O 失败) 走 except 也不
        残留 stale — 三态复位在 finally, failed-CLOSE→不重连→跑一致性网 窗口
        彻底堵住。"""
        drv = RealPropsimF64Driver("propsim-disc-raise", {})
        drv._channel_count = 2
        drv._loaded_emulation_file = "D:\\old\\prev_3600M.smu"  # 有加载 → 走 CLOSE
        drv._center_freq_mhz = 3600.0
        drv._center_freq_programmed = True

        visa = MagicMock()
        visa.close = MagicMock()

        async def _w(cmd, timeout=None):
            if cmd == "DIAG:SIMU:CLOSE":
                raise RuntimeError("VISA session dropped on CLOSE")

        async def _q(cmd, timeout=None, **_kw):
            return "1" if cmd == "*OPC?" else '0,"No error"'

        drv._visa_resource = visa
        drv._write = _w  # type: ignore[assignment]
        drv._query = _q  # type: ignore[assignment]
        await drv.disconnect()  # CLOSE 抛 → except → finally 仍复位
        assert drv._loaded_emulation_file is None
        assert drv._center_freq_programmed is False
        assert drv.get_frequency_identity() is None


class TestSmuProjectTruthParser:
    """P1-18 ③: .smu 工程 INI CenterFrequency 真值解析 (实录格式)。"""

    RECORDED = (
        "[Project]\n"
        "Name = 3GPP_FR1_OTA_CDLC_UMa\n"
        "\n"
        "[Channel Group 0]\n"
        "CenterFrequency = 3549990000 Hz\n"
        "Bandwidth = 100000000 Hz\n"
        "\n"
        "[Link_BS1_1_MS1_32x4_DL]\n"
        "CenterFrequency = 9999999999 Hz\n"
    )

    def test_recorded_project_parses_group0(self):
        """现场实录: UMa_3600M 工程实为 3549.99 MHz (文件名说谎的金标准样本)。"""
        freqs = parse_smu_project_center_freqs_hz(self.RECORDED)
        assert freqs == {0: 3549990000}  # Link 节的同名键不收
        assert parse_smu_project_primary_freq_mhz(self.RECORDED) == 3549.99

    def test_multi_group_and_missing_group0(self):
        text = (
            "[Channel Group 1]\nCenterFrequency = 1842500000 Hz\n"
            "[Channel Group 2]\nCenterFrequency = 2592990000\n"  # 单位可省
        )
        freqs = parse_smu_project_center_freqs_hz(text)
        assert freqs == {1: 1842500000, 2: 2592990000}
        # 缺组 0 → 取最小组号
        assert parse_smu_project_primary_freq_mhz(text) == 1842.5

    def test_empty_and_unparseable(self):
        assert parse_smu_project_center_freqs_hz(None) == {}
        assert parse_smu_project_center_freqs_hz("") == {}
        assert parse_smu_project_primary_freq_mhz("no ini here") is None
        # 畸形值不收
        bad = "[Channel Group 0]\nCenterFrequency = about3.5G\n"
        assert parse_smu_project_center_freqs_hz(bad) == {}

    def test_duplicate_key_takes_first(self):
        text = (
            "[Channel Group 0]\n"
            "CenterFrequency = 3549990000 Hz\n"
            "CenterFrequency = 1000000000 Hz\n"
        )
        assert parse_smu_project_center_freqs_hz(text) == {0: 3549990000}
