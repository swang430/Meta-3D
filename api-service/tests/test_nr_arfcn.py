"""NR-ARFCN 转换 + 频率规范标识测试 (P2-11 Phase 1).

钉死 3GPP TS 38.104 NR-ARFCN 公式的关键值, 以及 FrequencyIdentity 的精确比对
(无浮点容差) —— 这是"系统用中心 ARFCN + 带宽标识频率"架构原则的基础。
"""
from __future__ import annotations

import pytest

from app.hal.nr_arfcn import (
    FrequencyIdentity,
    freq_mhz_to_nr_arfcn,
    nr_arfcn_to_freq_mhz,
)


class TestFreqToArfcn:
    def test_known_n78_points(self):
        # P1-17 用的 3600M = 640000; N78 默认 map 值 632628 = 3489.42 MHz
        assert freq_mhz_to_nr_arfcn(3600.0) == 640000
        assert freq_mhz_to_nr_arfcn(3500.0) == 633333
        assert freq_mhz_to_nr_arfcn(3489.42) == 632628

    def test_range1_below_3000(self):
        # range1: N = F / 0.005; 2600 MHz (N41 标称) → 520000
        assert freq_mhz_to_nr_arfcn(2600.0) == 520000
        assert freq_mhz_to_nr_arfcn(1000.0) == 200000

    def test_range_boundary_3000(self):
        # 3000 MHz 是 range1/range2 分界 (用 range2: 600000 + 0)
        assert freq_mhz_to_nr_arfcn(3000.0) == 600000

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            freq_mhz_to_nr_arfcn(200000.0)


class TestArfcnToFreq:
    def test_roundtrip_n78(self):
        assert nr_arfcn_to_freq_mhz(640000) == pytest.approx(3600.0)
        assert nr_arfcn_to_freq_mhz(632628) == pytest.approx(3489.42)
        assert nr_arfcn_to_freq_mhz(633333) == pytest.approx(3499.995)

    def test_roundtrip_stability(self):
        # freq → arfcn → freq 在 raster 点上稳定
        for f in (3600.0, 3500.0, 2600.0, 700.0):
            arfcn = freq_mhz_to_nr_arfcn(f)
            back = nr_arfcn_to_freq_mhz(arfcn)
            assert abs(back - f) < 0.015  # 一个 15kHz raster step 内

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            nr_arfcn_to_freq_mhz(9999999)


class TestFrequencyIdentity:
    def test_same_freq_same_bw_equal(self):
        a = FrequencyIdentity.from_center_freq_mhz(3600.0, 100.0)
        b = FrequencyIdentity.from_center_freq_mhz(3600.0, 100.0)
        assert a == b
        assert a.center_arfcn == 640000

    def test_diff_freq_not_equal(self):
        # 核心: 3600 vs 3500 中心频率不同 → ARFCN 不同 → 不相等
        a = FrequencyIdentity.from_center_freq_mhz(3600.0, 100.0)
        b = FrequencyIdentity.from_center_freq_mhz(3500.0, 100.0)
        assert a != b
        assert a.center_arfcn != b.center_arfcn

    def test_same_freq_diff_bw_not_equal(self):
        # 带宽也是标识的一部分: 同频不同带宽 → 不相等
        a = FrequencyIdentity.from_center_freq_mhz(3600.0, 100.0)
        b = FrequencyIdentity.from_center_freq_mhz(3600.0, 40.0)
        assert a != b

    def test_no_float_tolerance_problem(self):
        # 关键: 标称 3489.42 (N78 默认) vs 3500 (人写的近似) 是不同 ARFCN,
        # 精确区分 —— 这正是 P1-17 bug (标称 3600 实际 3489) 该被抓住的。
        nominal = FrequencyIdentity.from_center_freq_mhz(3489.42, 100.0)  # 632628
        intended = FrequencyIdentity.from_center_freq_mhz(3500.0, 100.0)  # 633333
        assert nominal != intended

    def test_describe(self):
        fi = FrequencyIdentity.from_center_freq_mhz(3600.0, 100.0)
        d = fi.describe()
        assert "640000" in d and "3600" in d and "100" in d
