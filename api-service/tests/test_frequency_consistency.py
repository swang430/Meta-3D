"""P2-11 Phase 1: 多方频率一致性校验 + driver 频率自报 测试.

钉死:
1. check_frequency_consistency 的比对逻辑 (一致 / 不一致 / None 跳过 / 多 mismatch)。
2. driver get_frequency_identity 自报的是**实际下发频率**: UXM 用实际 _arfcn (抓
   fallback 坑), F64 解析 .smu 文件名 (抓默认 .smu 不联动)。
"""
from __future__ import annotations

from app.hal.nr_arfcn import FrequencyIdentity
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.mimo_ota.frequency_consistency import check_frequency_consistency


def _fi(freq_mhz, bw=100.0):
    return FrequencyIdentity.from_center_freq_mhz(freq_mhz, bw)


class TestConsistencyLogic:
    def test_all_consistent(self):
        r = check_frequency_consistency(_fi(3600), {"UXM": _fi(3600), "F64": _fi(3600)})
        assert r.consistent
        assert r.failure_reason() is None
        assert not r.mismatches

    def test_f64_mismatch_fails(self):
        # 核心: TestCase 3600 但 F64 用了别的 .smu (3500) → 不一致
        r = check_frequency_consistency(_fi(3600), {"UXM": _fi(3600), "F64": _fi(3500)})
        assert not r.consistent
        assert len(r.mismatches) == 1
        assert r.mismatches[0].instrument == "F64"
        assert "F64" in (r.failure_reason() or "")

    def test_uxm_arfcn_fallback_mismatch(self):
        # UXM 实际下发 ARFCN 632628 (3489, fallback) 但 TestCase 3500 → 不一致
        tc = _fi(3500)  # ARFCN 633333
        uxm = FrequencyIdentity(center_arfcn=632628, bandwidth_mhz=100.0)  # 3489.42
        r = check_frequency_consistency(tc, {"UXM": uxm})
        assert not r.consistent
        assert r.mismatches[0].instrument == "UXM"

    def test_none_skipped_not_mismatch(self):
        # F64 None (ASC 路径无频率可报) → 跳过, 不算不一致
        r = check_frequency_consistency(_fi(3600), {"UXM": _fi(3600), "F64": None})
        assert r.consistent
        assert r.per_instrument["F64"] == "未报告(跳过)"

    def test_bandwidth_part_of_identity(self):
        # 同频不同带宽 → 不一致
        r = check_frequency_consistency(_fi(3600, 100.0), {"UXM": _fi(3600, 40.0)})
        assert not r.consistent

    def test_multiple_mismatches(self):
        r = check_frequency_consistency(_fi(3600), {"UXM": _fi(3500), "F64": _fi(3700)})
        assert not r.consistent
        assert len(r.mismatches) == 2

    def test_payload_shape(self):
        r = check_frequency_consistency(_fi(3600), {"UXM": _fi(3500), "F64": None})
        p = r.to_payload()
        assert p["consistent"] is False
        assert "testcase_identity" in p
        assert p["per_instrument"]["F64"] == "未报告(跳过)"
        assert len(p["mismatches"]) == 1


class TestUxmFrequencyIdentity:
    def test_reports_actual_arfcn_not_nominal(self):
        # UXM getter 用实际下发 _arfcn (不是 _frequency_mhz 标称) —— 这才能抓
        # "标称 3500 但没传 arfcn → 实际下发 632628=3489" 的坑。
        drv = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        drv._arfcn = 632628        # 实际下发 (fallback)
        drv._bandwidth_mhz = 100.0
        fi = drv.get_frequency_identity()
        assert fi is not None
        assert fi.center_arfcn == 632628   # 实际, 非标称

    def test_none_before_set_cell_config(self):
        drv = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        # _arfcn 默认 None (还没 set_cell_config)
        assert drv.get_frequency_identity() is None


class TestF64FrequencyIdentity:
    def test_parses_3600m_smu(self):
        drv = RealPropsimF64Driver("test", {})
        drv._loaded_emulation_file = (
            r"D:\Scenario Packs\...\3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
        )
        fi = drv.get_frequency_identity()
        assert fi is not None
        assert fi.center_arfcn == 640000   # 3600 MHz

    def test_none_when_no_file_loaded(self):
        drv = RealPropsimF64Driver("test", {})
        # _loaded_emulation_file 默认 None (ASC 路径 / 没加载)
        assert drv.get_frequency_identity() is None

    def test_none_when_filename_has_no_freq_token(self):
        drv = RealPropsimF64Driver("test", {})
        drv._loaded_emulation_file = r"D:\some\arbitrary_channel.smu"
        assert drv.get_frequency_identity() is None
