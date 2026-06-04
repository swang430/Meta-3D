"""DUTProfile 声明 vs 实测协商交叉核对 (阶段 4) 单测。

声明 ≠ 实测 (双向) = mismatch; 任一字段 None → 跳过该字段; observed 不可用 (mock/未 attach)
→ 整体 skipped。调制按阶数比 (容忍格式差异)。不一致是 audit 发现, 不 fail 不覆盖声明。
"""
from __future__ import annotations

from app.services.mimo_ota.dut_capability_crosscheck import (
    canonical_modulation,
    check_dut_capability_mismatch,
)


def _check(**kw):
    base = dict(
        declared_max_dl_layers=None,
        declared_max_ul_layers=None,
        declared_max_modulation_dl=None,
        declared_max_modulation_ul=None,
        observed_max_dl_layers=None,
        observed_max_ul_layers=None,
        observed_max_modulation_dl=None,
        observed_max_modulation_ul=None,
        observed_available=True,
    )
    base.update(kw)
    return check_dut_capability_mismatch(**base)


class TestDUTCapabilityCrosscheck:
    def test_declared_equals_observed_consistent(self):
        res = _check(
            declared_max_dl_layers=4, observed_max_dl_layers=4,
            declared_max_modulation_dl="256QAM", observed_max_modulation_dl="256QAM",
        )
        assert res.consistent is True
        assert res.skipped is False
        assert res.mismatches == []

    def test_layers_declared_over_observed_mismatch(self):
        # 声明 4 层但实测只协商到 2 (声明高估)
        res = _check(declared_max_dl_layers=4, observed_max_dl_layers=2)
        assert res.consistent is False
        assert len(res.mismatches) == 1
        m = res.mismatches[0]
        assert m.field == "max_dl_layers" and m.declared == 4 and m.observed == 2

    def test_layers_observed_over_declared_mismatch(self):
        # 反向: 声明 2 但实测 4 (声明低估) —— 也是不一致 (双向)
        res = _check(declared_max_dl_layers=2, observed_max_dl_layers=4)
        assert res.consistent is False
        assert res.mismatches[0].observed == 4

    def test_modulation_mismatch_by_order(self):
        res = _check(
            declared_max_modulation_dl="256QAM", observed_max_modulation_dl="64QAM",
        )
        assert res.consistent is False
        assert res.mismatches[0].field == "max_modulation_dl"

    def test_modulation_format_tolerance_no_false_positive(self):
        # 256QAM vs QAM256 是同一个 (阶数都 8), 不应判不一致
        res = _check(
            declared_max_modulation_dl="256QAM", observed_max_modulation_dl="QAM256",
        )
        assert res.consistent is True

    def test_ul_fields_checked(self):
        res = _check(
            declared_max_ul_layers=2, observed_max_ul_layers=1,
            declared_max_modulation_ul="64QAM", observed_max_modulation_ul="16QAM",
        )
        fields = {m.field for m in res.mismatches}
        assert fields == {"max_ul_layers", "max_modulation_ul"}

    def test_none_fields_skipped(self):
        # 声明只填了 DL 层, 其它 None → 只可能在 DL 层上判不一致, 其它字段跳过
        res = _check(
            declared_max_dl_layers=4, observed_max_dl_layers=4,
            observed_max_modulation_dl="64QAM",  # 声明 modulation None → 跳过
        )
        assert res.consistent is True

    def test_observed_unavailable_skipped(self):
        # mock / 未 attach → skipped, 即便声明跟 (假) observed 不等也不判不一致
        res = _check(
            declared_max_dl_layers=4, observed_max_dl_layers=2,
            observed_available=False,
        )
        assert res.skipped is True
        assert res.consistent is True
        assert res.mismatches == []

    def test_to_payload_shape(self):
        res = _check(declared_max_dl_layers=4, observed_max_dl_layers=2)
        payload = res.to_payload()
        assert payload["consistent"] is False
        assert payload["skipped"] is False
        assert payload["mismatches"] == [
            {"field": "max_dl_layers", "declared": 4, "observed": 2}
        ]

    def test_failure_reason_human_readable(self):
        res = _check(declared_max_dl_layers=4, observed_max_dl_layers=2)
        reason = res.failure_reason()
        assert reason is not None
        assert "声明 4" in reason and "实测协商 2" in reason


class TestCanonicalModulation:
    """Codex P2 (#137): 实测上报格式不保证, 归一化到 DUTProfile 接受的 canonical 供采纳反写。"""

    def test_non_canonical_normalized(self):
        assert canonical_modulation("QAM64") == "64QAM"
        assert canonical_modulation("64 qam") == "64QAM"
        assert canonical_modulation("256-QAM") == "256QAM"
        assert canonical_modulation("qpsk") == "QPSK"

    def test_already_canonical_unchanged(self):
        assert canonical_modulation("64QAM") == "64QAM"
        assert canonical_modulation("1024QAM") == "1024QAM"

    def test_none_and_unrecognized_passthrough(self):
        assert canonical_modulation(None) is None
        assert canonical_modulation("") == ""
        # 识别不出阶数 → 原样 (不臆造; 后端会拒非法值)
        assert canonical_modulation("WeirdMod") == "WeirdMod"
