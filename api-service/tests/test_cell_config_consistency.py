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
    _modulation_order,
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

    # --- Phase 6 延伸: DL 调制阶数核对 (跟 layers 同机制) ---

    def test_modulation_within_capability_ok(self):
        # 请求 256QAM, UE 协商 256QAM → 阶数相等 → 一致
        r = check_cell_config_consistency(
            requested_mimo_layers=2,
            requested_modulation="256QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl="256QAM"),
        )
        assert r.consistent and not r.skipped

    def test_modulation_below_capability_ok(self):
        # 请求 64QAM, UE 支持 256QAM → 6 <= 8 → 一致
        r = check_cell_config_consistency(
            requested_mimo_layers=2,
            requested_modulation="64QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl="256QAM"),
        )
        assert r.consistent

    def test_modulation_exceeds_capability_fails(self):
        # 核心: 请求 256QAM 但 UE 只到 64QAM → 8 > 6 → 不一致 (UE clamp 到 64QAM)
        r = check_cell_config_consistency(
            requested_mimo_layers=2,
            requested_modulation="256QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl="64QAM"),
        )
        assert not r.consistent
        assert len(r.mismatches) == 1
        assert r.mismatches[0].field == "modulation"
        assert r.mismatches[0].requested == "256QAM"
        assert r.mismatches[0].applied == "64QAM"
        assert "clamp" in (r.failure_reason() or "")

    def test_modulation_format_variants_normalized(self):
        # UXM SCPI 返回格式不保证: 请求 "256QAM" vs UE "QAM256" → 同阶数 → 一致
        r = check_cell_config_consistency(
            requested_mimo_layers=2,
            requested_modulation="256QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl="QAM256"),
        )
        assert r.consistent
        # 请求 "256-QAM" vs UE "64 qam" → 8 > 6 → 归一化后仍抓到不一致
        r2 = check_cell_config_consistency(
            requested_mimo_layers=2,
            requested_modulation="256-QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl="64 qam"),
        )
        assert not r2.consistent and r2.mismatches[0].field == "modulation"

    def test_modulation_none_requested_skipped(self):
        # requested_modulation=None (默认) → 不校验 modulation, 只看 layers
        r = check_cell_config_consistency(
            requested_mimo_layers=2,
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl="64QAM"),
        )
        assert r.consistent

    def test_modulation_ue_capability_none_skipped(self):
        # UE max_modulation_dl 不可核对 (firmware 不报) → 跳过 modulation, 不算不一致
        r = check_cell_config_consistency(
            requested_mimo_layers=2,
            requested_modulation="256QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl=None),
        )
        assert r.consistent

    def test_modulation_unrecognized_skipped(self):
        # UE 返回无法识别的调制字符串 → 跳过该项 (不误判)
        r = check_cell_config_consistency(
            requested_mimo_layers=2,
            requested_modulation="256QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=4, ue_max_modulation_dl="WEIRD"),
        )
        assert r.consistent

    def test_layers_and_modulation_both_fail(self):
        # 两条线同时不一致 → 2 个 mismatch (layers + modulation)
        r = check_cell_config_consistency(
            requested_mimo_layers=4,
            requested_modulation="256QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=2, ue_max_modulation_dl="64QAM"),
        )
        assert not r.consistent
        assert {m.field for m in r.mismatches} == {"mimo_layers", "modulation"}

    def test_qpsk_is_lowest_order(self):
        # QPSK (2 bits) 最低阶: 请求 QPSK vs UE 64QAM → 一致
        ok = check_cell_config_consistency(
            requested_mimo_layers=2, requested_modulation="QPSK",
            applied=AppliedCellConfig(ue_max_dl_layers=2, ue_max_modulation_dl="64QAM"),
        )
        assert ok.consistent
        # 请求 256QAM vs UE 仅 QPSK → 不一致
        bad = check_cell_config_consistency(
            requested_mimo_layers=2, requested_modulation="256QAM",
            applied=AppliedCellConfig(ue_max_dl_layers=2, ue_max_modulation_dl="QPSK"),
        )
        assert not bad.consistent


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

    async def test_reads_modulation_capability(self):
        # Phase 6 延伸: get_applied 一并读 UE 协商的 DL 调制能力上限
        drv = self._drv()
        drv.query_ue_capability = _async_ret(
            {"max_dl_layers": 4, "max_modulation_dl": "256QAM", "source": "real_ue"}
        )
        applied = await drv.get_applied_cell_config()
        assert applied is not None
        assert applied.ue_max_dl_layers == 4
        assert applied.ue_max_modulation_dl == "256QAM"

    async def test_modulation_none_when_firmware_omits(self):
        # firmware 不报 modulation 能力 → ue_max_modulation_dl None (该项后续跳过)
        drv = self._drv()
        drv.query_ue_capability = _async_ret(
            {"max_dl_layers": 4, "source": "real_ue"}  # 无 max_modulation_dl
        )
        applied = await drv.get_applied_cell_config()
        assert applied is not None and applied.ue_max_modulation_dl is None


class TestModulationOrder:
    """_modulation_order 归一化: 容忍 UXM SCPI 格式差异 (feedback_normalize_identifier_compare)。"""

    def test_standard_format(self):
        assert _modulation_order("256QAM") == 8
        assert _modulation_order("64QAM") == 6
        assert _modulation_order("16QAM") == 4
        assert _modulation_order("1024QAM") == 10

    def test_qpsk(self):
        assert _modulation_order("QPSK") == 2

    def test_format_variants(self):
        # 大小写 / 分隔符 / QAM 前后缀 都归一到同阶数
        assert _modulation_order("qam256") == 8
        assert _modulation_order("256-QAM") == 8
        assert _modulation_order("256 QAM") == 8
        assert _modulation_order("QAM_256") == 8

    def test_none_and_unrecognized(self):
        assert _modulation_order(None) is None
        assert _modulation_order("") is None
        assert _modulation_order("WEIRD") is None
        assert _modulation_order("32QAM") is None  # 非标准 QAM 点数 → 不在表里
