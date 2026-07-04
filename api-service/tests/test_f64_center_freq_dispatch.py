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


def _make_driver(config=None, channels=4):
    drv = RealPropsimF64Driver("propsim-test", config or {})
    drv._channel_count = channels
    visa = MagicMock()

    def _router(cmd):
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            return '0,"No error"'
        if cmd.startswith("ROUT:PATH:CONN?"):
            return "B1.1"
        return '0,"No error"'

    visa.query.side_effect = _router
    visa.write.return_value = None
    drv._visa_resource = visa

    async def _async_write(cmd, timeout=None):
        visa.write(cmd)

    async def _async_query(cmd, timeout=None):
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

    async def test_explicit_freq_writes_all_channels_and_marks_programmed(self):
        drv, visa = _make_driver(channels=4)
        ok = await drv.set_channel_model(
            "CDL-C", "UMa", {"center_frequency_mhz": 3549.99}
        )
        assert ok is True
        writes = _cent_writes(visa)
        assert len(writes) == 4
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
        assert len(writes) == 2
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

        async def _q(cmd, timeout=None):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return queue.pop(0) if queue else '0,"No error"'
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

        async def _q(cmd, timeout=None):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return queue.pop(0) if queue else '0,"No error"'
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
