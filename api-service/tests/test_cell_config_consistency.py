"""P2-11 Phase 6: UXM cell config 下发后回读一致性 + getter 测试.

钉死:
1. check_cell_config_consistency 比对逻辑 (一致 / clamp 不一致 / None 跳过 / 字段 None 跳过)。
2. RealUxmDriver.get_applied_cell_config 回读: 连接时查 MIMO:LAY? 返回实际 layers;
   未连接 / 查询失败 / 命令不支持 → None (跳过, 同 Phase 1 mock-skip)。
"""
from __future__ import annotations

from app.hal.uxm_base_station import AppliedCellConfig, RealUxmDriver
from app.services.mimo_ota.cell_config_consistency import (
    check_cell_config_consistency,
)


class TestConsistencyLogic:
    def test_consistent(self):
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(mimo_layers=4)
        )
        assert r.consistent and not r.skipped
        assert r.failure_reason() is None

    def test_clamp_mismatch_fails(self):
        # 核心: 请求 4 层但 UXM 实际生效 2 (UE 能力/端口路由 clamp) → 不一致
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(mimo_layers=2)
        )
        assert not r.consistent
        assert len(r.mismatches) == 1
        assert r.mismatches[0].field == "mimo_layers"
        assert r.mismatches[0].requested == 4 and r.mismatches[0].applied == 2
        assert "mimo_layers" in (r.failure_reason() or "")

    def test_none_applied_skipped(self):
        # 回读不到 (mock / 未连接) → skipped, 不算不一致
        r = check_cell_config_consistency(requested_mimo_layers=4, applied=None)
        assert r.consistent and r.skipped

    def test_field_none_skipped(self):
        # applied 有但 mimo_layers 那项没回读到 → 跳过该项, 不算不一致
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(mimo_layers=None)
        )
        assert r.consistent and not r.skipped

    def test_payload_shape(self):
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(mimo_layers=2)
        )
        p = r.to_payload()
        assert p["consistent"] is False and p["skipped"] is False
        assert p["mismatches"][0]["field"] == "mimo_layers"


class TestUxmGetApplied:
    def _drv(self):
        return RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})

    def test_reads_actual_layers(self):
        drv = self._drv()
        drv._visa_session = object()  # 模拟已连接
        drv._query = lambda cmd: "2"  # UXM 回读实际生效 2 层
        applied = drv.get_applied_cell_config()
        assert applied is not None and applied.mimo_layers == 2

    def test_none_when_not_connected(self):
        drv = self._drv()
        # _visa_session 默认 None (未 connect)
        assert drv.get_applied_cell_config() is None

    def test_none_when_query_empty(self):
        drv = self._drv()
        drv._visa_session = object()
        drv._query = lambda cmd: ""  # 空回读
        assert drv.get_applied_cell_config() is None

    def test_none_when_query_raises(self):
        drv = self._drv()
        drv._visa_session = object()

        def _boom(cmd):
            raise RuntimeError("UXM 不支持该查询 / 超时")

        drv._query = _boom
        assert drv.get_applied_cell_config() is None  # 不崩, 优雅跳过
