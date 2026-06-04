"""DUTProfile 声明能力校验 (规划期, attach 前) 单测。

请求 vs DUT 声明: 请求 > 声明 → violation (提前 fail); 声明项 None = 未声明跳过。
"""
from app.services.mimo_ota.dut_capability_check import check_dut_capability


class TestCheckDUTCapability:
    def test_request_within_declared(self):
        r = check_dut_capability(
            requested_layers=2, requested_modulation="64QAM",
            declared_max_dl_layers=4, declared_max_modulation_dl="256QAM",
        )
        assert r.consistent and r.violations == []

    def test_layers_exceed_declared(self):
        r = check_dut_capability(
            requested_layers=4, requested_modulation="64QAM",
            declared_max_dl_layers=2, declared_max_modulation_dl="256QAM",
        )
        assert not r.consistent
        assert any("层" in v for v in r.violations)

    def test_modulation_exceed_declared(self):
        r = check_dut_capability(
            requested_layers=2, requested_modulation="256QAM",
            declared_max_dl_layers=4, declared_max_modulation_dl="64QAM",
        )
        assert not r.consistent
        assert any("调制" in v for v in r.violations)

    def test_both_exceed(self):
        r = check_dut_capability(
            requested_layers=4, requested_modulation="256QAM",
            declared_max_dl_layers=2, declared_max_modulation_dl="64QAM",
        )
        assert not r.consistent and len(r.violations) == 2

    def test_unspecified_declared_skips(self):
        # 声明项 None = 未声明 (不是所有 DUT 都填全) → 跳过, 不 fail
        r = check_dut_capability(
            requested_layers=8, requested_modulation="1024QAM",
            declared_max_dl_layers=None, declared_max_modulation_dl=None,
        )
        assert r.consistent

    def test_equal_is_ok(self):
        # 等于声明上限 = 满足 (不算超)
        r = check_dut_capability(
            requested_layers=4, requested_modulation="256QAM",
            declared_max_dl_layers=4, declared_max_modulation_dl="256QAM",
        )
        assert r.consistent
