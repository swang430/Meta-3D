"""P2-11 #1974: UXM 端口路由 / 调度 TestCase 驱动 (path B 显式驱动, 堵残留 profile)。

config 加 mimo_port_preset/sched_algo/csi_rs_ports; measure path B 经
_build_pcell_cell_config 显式传给 set_cell_config —— 避免残留 HAL-init 默认 topology
profile 的值 (如 2x2 TestCase 跑在残留 4x4 端口路由)。csi_rs_ports=None **不放进 dict**
(缺省哨兵, 避免 set_cell_config SCPI 写字面 "None")。用户 2026-06-04 选方案 b。
"""
from __future__ import annotations

from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.mimo_ota.executors.measure import _build_pcell_cell_config


class TestPortRoutingSchemaFields:
    def test_defaults_align_builtin_profile(self):
        cfg = MIMOOTAConfiguration()
        assert cfg.mimo_port_preset == "2x2"
        assert cfg.sched_algo == "FULLBUFFER"
        assert cfg.csi_rs_ports is None  # None → set_cell_config 按 mimo_layers 推断
        assert cfg.tdd_pattern == "DDDSU"  # 已有 (Phase 3)

    def test_override(self):
        cfg = MIMOOTAConfiguration(
            mimo_port_preset="4x4", sched_algo="ROUNDROBIN", csi_rs_ports=8,
        )
        assert cfg.mimo_port_preset == "4x4"
        assert cfg.sched_algo == "ROUNDROBIN"
        assert cfg.csi_rs_ports == 8


def _build(**cfg_kw):
    return _build_pcell_cell_config(
        MIMOOTAConfiguration(**cfg_kw),
        frequency_mhz=3500.0,
        arfcn=633333,  # 3500 MHz 的 NR ARFCN
        bandwidth_mhz=100.0,
        scs_khz=30,
        band="N78",
    )


class TestBuildPcellCellConfig:
    def test_port_routing_fields_explicitly_driven(self):
        # #1974 核心: path B 显式传端口路由/TDD/调度, 覆盖残留 profile
        d = _build(mimo_port_preset="4x4", tdd_pattern="DSUUU", sched_algo="ROUNDROBIN")
        assert d["mimo_port_preset"] == "4x4"
        assert d["tdd_pattern"] == "DSUUU"
        assert d["sched_algo"] == "ROUNDROBIN"
        assert d["tdd_period"] == "5MS"  # 默认也带上

    def test_base_fields_carried(self):
        d = _build(mimo_layers=4, target_tx_power_dbm=-10.0)
        assert d["frequency_mhz"] == 3500.0 and d["arfcn"] == 633333
        assert d["bandwidth_mhz"] == 100.0 and d["scs_khz"] == 30 and d["band"] == "N78"
        assert d["mimo_layers"] == 4 and d["dl_power_dbm"] == -10.0

    def test_csi_rs_ports_none_omitted(self):
        # 关键边缘 (缺省哨兵): csi_rs_ports=None 不放进 dict —— set_cell_config 的
        # `if "csi_rs_ports" in config` 会对 None 写字面 "None" 崩真 UXM。
        d = _build()  # csi_rs_ports 默认 None
        assert "csi_rs_ports" not in d

    def test_csi_rs_ports_value_included(self):
        d = _build(csi_rs_ports=8)
        assert d["csi_rs_ports"] == 8

    def test_defaults_match_builtin_profile_backward_compat(self):
        # 默认值对齐内置 profile (2x2/FULLBUFFER/DDDSU): 不改变现有 2x2 测试行为
        d = _build()
        assert d["mimo_port_preset"] == "2x2"
        assert d["sched_algo"] == "FULLBUFFER"
        assert d["tdd_pattern"] == "DDDSU"
