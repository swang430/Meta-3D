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

from app.hal.propsim_f64 import (
    F64_DEFAULT_EMULATION_FILE,
    F64_DEFAULT_EMULATION_FILE_TOPOLOGY,
    RealPropsimF64Driver,
)


def _make_driver(config=None):
    """mock 驱动: SYST:ERR? 恒 no-error → set_channel_model 走 happy path。

    P0-3: 加载走 _load_smu_with_preflight —— 需 mock DIAG:SIMU:STATE?→"CLOSED"
    (CLOSE 后复查 ==CLOSED 才继续下发 CALC:FILT:FILE) + CALC:FILT:CENT:CH?→回读真频
    (加载后回读; 本文件不验 identity, 返 "" 即"不可用"非致命)。拓扑同步仍走硬编码
    常量 _default_emulation_file_topology (P0-3 缩范围: MODEL:INFO? 仪器回读留 F64R-2)。
    """
    drv = RealPropsimF64Driver("propsim-test", config or {})
    drv._channel_count = 1  # 收敛设频循环, 测试更干净
    visa = MagicMock()

    def _router(cmd):
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            return '0,"No error"'
        if cmd == "DIAG:SIMU:STATE?":
            return "CLOSED"
        if cmd.startswith("CALC:FILT:CENT:CH?"):
            return ""  # 回读真频不可用 → 非致命 (本文件不验 identity)
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


class TestF64DefaultTopologySync:
    """加载默认文件后自动同步 _tx_antennas/_rx_antennas 缓存 (Codex on PR #97):

    否则 stale 2x2 缓存让下游 set_path_loss 等按 4 个输出配, 漏配实际 16 通道
    (4x4 = 3600M 的拓扑) → RF 失真。非默认文件由 operator 经 set_mimo_config
    预设拓扑 (现有惯例)。

    ⚠ P0-3 缩范围 (用户 2026-07-23): 拓扑同步保持**硬编码常量**语义 (默认文件同步 /
    非默认不同步)。从仪器 MODEL:INFO? 回读物理拓扑 + 消费方改用真实输出口留 F64R-2。
    """

    async def test_topology_constant_is_4x4(self):
        # 3600M = 4-input MIMO OTA, 4x4 (BS 4 TX × UE 4 RX layers)
        assert F64_DEFAULT_EMULATION_FILE_TOPOLOGY == (4, 4)

    async def test_load_default_syncs_cache_from_2x2_to_4x4(self):
        drv, _ = _make_driver()
        # 构造默认: 2x2
        assert (drv._tx_antennas, drv._rx_antennas) == (2, 2)
        await drv.set_channel_model("CDL-C", "UMa", {})  # 无 emulation_file → 走默认
        # 加载默认 (3600M) 后同步到 (4, 4)
        assert (drv._tx_antennas, drv._rx_antennas) == (4, 4)

    async def test_load_default_idempotent_when_already_matching(self):
        # 已经 (4, 4) → 加载默认 → 仍 (4, 4), 不日志噪音 (本测试只验值)
        drv, _ = _make_driver()
        drv._tx_antennas, drv._rx_antennas = 4, 4
        await drv.set_channel_model("CDL-C", "UMa", {})
        assert (drv._tx_antennas, drv._rx_antennas) == (4, 4)

    async def test_load_non_default_file_does_not_touch_cache(self):
        # 加载与默认不同的自定义文件 → 缓存保持原值 (operator 应另调 set_mimo_config)
        drv, _ = _make_driver()
        await drv.set_channel_model(
            "CDL-A", "UMi", {"emulation_file": r"D:\My\custom.smu"}
        )
        assert (drv._tx_antennas, drv._rx_antennas) == (2, 2)  # 不变

    async def test_config_topology_override_takes_effect(self):
        # operator 经 connection_params 同时 override file + topology
        custom_file = r"D:\My\custom_default.smu"
        drv, _ = _make_driver({
            "default_emulation_file": custom_file,
            "default_emulation_file_topology": (8, 2),
        })
        await drv.set_channel_model("CDL-C", "UMa", {})  # 走 driver 默认 = custom_file
        assert (drv._tx_antennas, drv._rx_antennas) == (8, 2)

    async def test_per_call_file_matching_default_path_syncs(self):
        # per-call 明确传默认路径 → 仍触发同步 (路径相等就同步, 与"怎么进来"无关)
        drv, _ = _make_driver()
        await drv.set_channel_model(
            "CDL-C", "UMa", {"emulation_file": F64_DEFAULT_EMULATION_FILE}
        )
        assert (drv._tx_antennas, drv._rx_antennas) == (4, 4)

    async def test_explicit_empty_default_no_topology_sync(self):
        # 默认显式清空 → auto-name 路径不等于默认路径 → 不同步, 缓存保持构造默认
        drv, _ = _make_driver({"default_emulation_file": ""})
        await drv.set_channel_model("CDL-A", "UMi", {})
        assert (drv._tx_antennas, drv._rx_antennas) == (2, 2)
