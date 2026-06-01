"""P2-11 Phase 6: UXM cell config 下发后一致性 (UE 能力核对) + getter 测试.

钉死 (Codex on PR #114 修正后):
1. check_cell_config_consistency: 请求层数 > UE 能力上限 → 不一致; <= → 一致;
   None → 跳过。
2. RealUxmDriver.get_applied_cell_config 读的是 **UE 协商能力** (query_ue_capability 的
   max_dl_layers), 不是 set_cell_config 写入的配置旋钮 (那个回读只原样返回配置值,
   抓不到 UE 把 4 层 clamp 到 2 的降级)。UE 未 attach / firmware 不支持 → None 跳过。
"""
from __future__ import annotations

from app.hal.uxm_base_station import AppliedCellConfig, RealUxmDriver
from app.services.mimo_ota.cell_config_consistency import (
    check_cell_config_consistency,
)


def _async_ret(value):
    """返回一个 await 后给出 value 的 async 函数 (mock async 方法用)。"""
    async def _coro(*args, **kwargs):
        return value
    return _coro


class TestConsistencyLogic:
    def test_request_within_ue_capability_ok(self):
        # 请求 2 层, UE 支持 4 → 2 <= 4 → 一致
        r = check_cell_config_consistency(
            requested_mimo_layers=2, applied=AppliedCellConfig(ue_max_dl_layers=4)
        )
        assert r.consistent and not r.skipped
        assert r.failure_reason() is None

    def test_request_equals_capability_ok(self):
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(ue_max_dl_layers=4)
        )
        assert r.consistent

    def test_request_exceeds_capability_fails(self):
        # 核心: 请求 4 层但 UE 只支持 2 → 4 > 2 → 不一致 (UXM 会静默 clamp)
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(ue_max_dl_layers=2)
        )
        assert not r.consistent
        assert len(r.mismatches) == 1
        assert r.mismatches[0].field == "mimo_layers"
        assert r.mismatches[0].requested == 4 and r.mismatches[0].applied == 2
        assert "clamp" in (r.failure_reason() or "")

    def test_none_applied_skipped(self):
        # UE 未 attach / mock → skipped, 不算不一致
        r = check_cell_config_consistency(requested_mimo_layers=4, applied=None)
        assert r.consistent and r.skipped

    def test_field_none_skipped(self):
        # applied 有但 ue_max_dl_layers 不可核对 → 跳过该项
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(ue_max_dl_layers=None)
        )
        assert r.consistent and not r.skipped

    def test_payload_shape(self):
        r = check_cell_config_consistency(
            requested_mimo_layers=4, applied=AppliedCellConfig(ue_max_dl_layers=2)
        )
        p = r.to_payload()
        assert p["consistent"] is False and p["skipped"] is False
        assert p["mismatches"][0]["field"] == "mimo_layers"


class TestUxmGetApplied:
    def _drv(self):
        return RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})

    async def test_reads_ue_capability_not_config_knob(self):
        # 读 UE 协商能力 max_dl_layers (不是配置旋钮回读)
        drv = self._drv()
        drv.query_ue_capability = _async_ret(
            {"max_dl_layers": 2, "source": "real_ue"}
        )
        applied = await drv.get_applied_cell_config()
        assert applied is not None and applied.ue_max_dl_layers == 2

    async def test_none_when_ue_unavailable(self):
        # UE 未 attach / firmware 不支持 → max_dl_layers None → 整体 None (跳过)
        drv = self._drv()
        drv.query_ue_capability = _async_ret(
            {"max_dl_layers": None, "source": "unavailable"}
        )
        assert await drv.get_applied_cell_config() is None

    async def test_none_when_capability_query_raises(self):
        drv = self._drv()

        async def _boom(*a, **k):
            raise RuntimeError("UXM UEINFO 不支持 / 超时")

        drv.query_ue_capability = _boom
        assert await drv.get_applied_cell_config() is None  # 不崩, 优雅跳过
