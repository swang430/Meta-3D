"""P2-11 #1974: UXM 端口路由 / 调度 TestCase 驱动 (path B 显式驱动, 堵残留 profile)。

端口 preset 仍是独立的可选配置；调度与 CSI-RS 则由 P2-54 execution-frozen
MAC profile 唯一驱动。typo preset 经 _validate_port_preset 前置 fail-loud。
"""
from __future__ import annotations

from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.mimo_ota.executors.measure import (
    _build_pcell_cell_config,
    _validate_port_preset,
)


class TestPortRoutingSchemaFields:
    def test_defaults_are_none_distinguishable(self):
        # Codex P1 #127: 默认 None = "未指定" (不是 "2x2") → 旧 saved case 不被默认值覆盖
        cfg = MIMOOTAConfiguration()
        assert cfg.mimo_port_preset is None
        assert cfg.sched_algo is None
        assert cfg.csi_rs_ports is None
        # 旧字段跟上面三个**语义不同**: 它不是 None-可区分的 opt-in 旋钮,
        # 而是有真实默认、由 configure_mac 驱动下发的必填项。
        # ⚠ 2026-08-07: 原来这里写死 `== "DDDSU"`, 现场把默认改成
        #   `DDDSUDDSUU`(30kHz 下配 5ms 周期) 时它就红了 —— 而本测试测的
        #   契约("新字段 None 可区分")根本没变。钉字面值 ≠ 钉契约。
        assert cfg.tdd_pattern is not None and cfg.tdd_pattern != ""

    def test_supported_legacy_override_is_migrated_into_profile(self):
        cfg = MIMOOTAConfiguration(
            mimo_port_preset="4x4", sched_algo="FULLBUFFER", csi_rs_ports=8,
        )
        assert cfg.mimo_port_preset == "4x4"
        assert cfg.mac_profile.profile.kind == "nr_throughput"
        assert cfg.mac_profile.profile.scheduler_algorithm == "full_throughput"
        assert cfg.mac_profile.profile.csi_rs_ports == 8


def _build(**cfg_kw):
    config = MIMOOTAConfiguration(**cfg_kw)
    return _build_pcell_cell_config(
        config,
        mac_profile=config.mac_profile,
        frequency_mhz=3500.0,
        arfcn=633333,  # 3500 MHz 的 NR ARFCN
        bandwidth_mhz=100.0,
        scs_khz=30,
        band="N78",
    )


class TestBuildPcellCellConfig:
    def test_optional_fields_omitted_when_none(self):
        # 端口 preset 仍按显式 opt-in；调度/CSI-RS 来自冻结 profile。
        d = _build()  # 全默认 (None)
        assert "mimo_port_preset" not in d
        assert d["sched_algo"] == "full_throughput"
        assert d["csi_rs_ports"] == 4
        assert d["frequency_mhz"] == 3500.0 and d["mimo_layers"] == 2

    def test_tdd_not_in_helper(self):
        # tdd_pattern/tdd_period 由 configure_mac_throughput_test 驱动, 不在 helper (避免冗余)
        d = _build()
        assert "tdd_pattern" not in d and "tdd_period" not in d

    def test_profile_fields_driven(self):
        d = _build(mimo_port_preset="4x4", sched_algo="FULLBUFFER", csi_rs_ports=8)
        assert d["mimo_port_preset"] == "4x4"
        assert d["sched_algo"] == "full_throughput"
        assert d["csi_rs_ports"] == 8

    def test_partial_explicit_others_omitted(self):
        # 只给 mimo_port_preset, 其它仍 omit
        d = _build(mimo_port_preset="siso")
        assert d["mimo_port_preset"] == "siso"
        assert d["sched_algo"] == "full_throughput"
        assert d["csi_rs_ports"] == 4

    def test_base_fields_carried(self):
        d = _build(mimo_layers=4, target_tx_power_dbm=-10.0)
        assert d["frequency_mhz"] == 3500.0 and d["arfcn"] == 633333
        assert d["bandwidth_mhz"] == 100.0 and d["scs_khz"] == 30 and d["band"] == "N78"
        assert d["mimo_layers"] == 4 and d["dl_power_dbm"] == -10.0


class TestValidatePortPreset:
    """Codex P2 #127: typo preset 前置 fail-loud (set_cell_config 对 unknown preset 不 abort
    会静默保留旧路由)。"""

    _VALID = {"siso": {}, "2x2": {}, "4x4": {}, "2x2_alt": {}}  # 模拟 MIMO_PORT_PRESETS

    def test_none_preset_skips(self):
        # TestCase 未指定 → 不校验 (走 backward-compat 不传)
        assert _validate_port_preset(None, self._VALID) is None

    def test_mock_driver_no_presets_skips(self):
        # mock driver 没 MIMO_PORT_PRESETS → mock-aware skip
        assert _validate_port_preset("4x4", None) is None

    def test_valid_preset_passes(self):
        assert _validate_port_preset("4x4", self._VALID) is None
        assert _validate_port_preset("SISO", self._VALID) is None  # 大小写不敏感

    def test_typo_preset_returns_error(self):
        err = _validate_port_preset("4X4_typo", self._VALID)
        assert err is not None and "非法" in err and "4X4_typo" in err
