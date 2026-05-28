"""F64 默认 .smu 文件优先级测试 (P0-8 Step 4).

设计: 现场 2026-05-27 把 3GPP FR1 OTA CDL-C UMa 3600M.smu 真机加载/运行通过,
用户指定为系统默认。本测试钉死优先级链 (高→低):

  1) per-call:  set_channel_model(parameters={"emulation_file": <path>})
  2) per-binding: config["default_emulation_file"]
                  (InstrumentConnection.connection_params 经 HAL service merge 进 config)
  3) 系统默认: F64_DEFAULT_EMULATION_FILE 常量 (= 3600M)
  4) 兜底 auto-name: 仅当操作员显式清空默认 (config 设 "" / None) 时

验证方式: 看 driver 实际写出的 CALC:FILT:FILE <path>。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.hal.propsim_f64 import F64_DEFAULT_EMULATION_FILE, RealPropsimF64Driver


def _make_driver(config=None):
    """mock 驱动: SYST:ERR? 恒 no-error → set_channel_model 走 happy path。"""
    drv = RealPropsimF64Driver("propsim-test", config or {})
    drv._channel_count = 1  # 收敛设频循环, 测试更干净
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


def _filt_file_path(visa):
    """提取实际写出的 CALC:FILT:FILE <path> 的 path 参数。"""
    prefix = "CALC:FILT:FILE "
    for c in visa.write.call_args_list:
        cmd = c.args[0]
        if cmd.startswith(prefix):
            return cmd[len(prefix):]
    return None


class TestF64DefaultEmulationFile:
    async def test_constant_is_3600m_smu(self):
        # 钉死常量本身的形状 (路径含 3600M + 以 .smu 结尾)
        assert "3600M" in F64_DEFAULT_EMULATION_FILE
        assert F64_DEFAULT_EMULATION_FILE.endswith(".smu")

    async def test_no_config_no_per_call_uses_3600m_default(self):
        # 优先级 #3: 无 config 默认 + 无 per-call → 走系统常量 (3600M)
        drv, visa = _make_driver()
        assert await drv.set_channel_model("CDL-C", "UMa", {}) is True
        assert _filt_file_path(visa) == F64_DEFAULT_EMULATION_FILE

    async def test_connection_params_default_overrides_constant(self):
        # 优先级 #2: 操作员经 connection_params 设的默认 > 系统常量
        custom = r"D:\My\Custom_default.smu"
        drv, visa = _make_driver({"default_emulation_file": custom})
        await drv.set_channel_model("CDL-C", "UMa", {})
        assert _filt_file_path(visa) == custom

    async def test_per_call_emulation_file_beats_all(self):
        # 优先级 #1: per-call > per-binding 默认 > 常量
        per_call = r"D:\Call\override.smu"
        drv, visa = _make_driver({"default_emulation_file": r"D:\Config\config.smu"})
        await drv.set_channel_model("CDL-C", "UMa", {"emulation_file": per_call})
        assert _filt_file_path(visa) == per_call

    async def test_explicit_empty_default_falls_back_to_auto_name(self):
        # 优先级 #4: operator 显式清空默认 ("") → legacy auto-name 兜底
        drv, visa = _make_driver({"default_emulation_file": ""})
        await drv.set_channel_model("CDL-A", "UMi", {})
        path = _filt_file_path(visa)
        assert path is not None
        # 默认 _tx_antennas=_rx_antennas=2 → "CDL-A_UMi_2x2.smu"
        assert path.endswith("CDL-A_UMi_2x2.smu")
