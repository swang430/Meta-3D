"""P2-11 Phase 1: 多方频率一致性校验 + driver 频率自报 测试.

钉死:
1. check_frequency_consistency 的比对逻辑 (一致 / 不一致 / None 跳过 / 多 mismatch)。
2. driver get_frequency_identity 自报的是**实际下发频率**: UXM 用实际 _arfcn (抓
   fallback 坑), F64 解析 .smu 文件名 (抓默认 .smu 不联动)。
"""
from __future__ import annotations

from app.hal.nr_arfcn import FrequencyIdentity, freq_mhz_to_nr_arfcn
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.mimo_ota.frequency_consistency import (
    CenterFrequencyObservation,
    check_frequency_consistency,
)


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
        # UXM 实际下发 ARFCN ≠ TestCase 标称 (632628=3489.42 只是任一偏离值,
        # 一致性网只看整数相等) → 不一致
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

    def test_center_only_observation_checks_center_without_inventing_bandwidth(self):
        center = CenterFrequencyObservation.from_center_freq_mhz(
            3600.0, source="F64 CALC:FILT:CENT:CH?"
        )
        r = check_frequency_consistency(_fi(3600, 40.0), {"F64": center})
        assert r.consistent
        assert not r.fully_verified
        assert r.unverified == ["F64"]
        assert "BW unknown" in r.per_instrument["F64"]

        mismatch = check_frequency_consistency(
            _fi(3550, 40.0), {"F64": center}
        )
        assert not mismatch.consistent
        assert mismatch.mismatches[0].instrument == "F64"

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
    def test_reports_center_but_not_a_fabricated_bandwidth(self):
        """F64 运行时只能证明中心频率；系统能力 100 MHz 不是当前 .smu 带宽。"""
        drv = RealPropsimF64Driver("test", {})
        drv._loaded_emulation_file = (
            r"D:\Scenario Packs\...\3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
        )
        assert drv.get_center_frequency_mhz() == 3600.0
        assert drv.get_frequency_identity() is None

        fi = drv.get_frequency_identity(declared_bandwidth_mhz=40.0)
        assert fi is not None
        assert fi.center_arfcn == 640000   # 3600 MHz
        assert fi.bandwidth_mhz == 40.0

    def test_none_when_no_file_loaded(self):
        drv = RealPropsimF64Driver("test", {})
        # _loaded_emulation_file 默认 None (ASC 路径 / 没加载)
        assert drv.get_frequency_identity() is None

    def test_none_when_filename_has_no_freq_token(self):
        drv = RealPropsimF64Driver("test", {})
        drv._loaded_emulation_file = r"D:\some\arbitrary_channel.smu"
        assert drv.get_frequency_identity() is None

    def test_programmed_center_overrides_filename(self):
        # Codex on PR #109 P2: 复用 ".._3600M.smu" 但显式下发中心频到 3500 → 自报
        # **实际下发的 3500**, 不是 stale 的文件名 3600 (否则校验门会误判已正确调谐
        # 的 run, 或放过错调的 run)。
        drv = RealPropsimF64Driver("test", {})
        drv._loaded_emulation_file = (
            r"D:\Scenario Packs\...\3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
        )
        drv._center_freq_mhz = 3500.0
        drv._center_freq_programmed = True
        assert drv.get_center_frequency_mhz() == 3500.0
        fi = drv.get_frequency_identity(declared_bandwidth_mhz=40.0)
        assert fi == FrequencyIdentity.from_center_freq_mhz(3500.0, 40.0)
        assert fi != FrequencyIdentity.from_center_freq_mhz(3600.0, 40.0)  # 非文件名

    async def test_configure_marks_programmed_and_reports_it(self):
        # configure(center_frequency_mhz=...) 显式下发 → 标记 programmed → 自报该频率,
        # 即使文件名 token 是别的。
        drv = RealPropsimF64Driver("test", {})
        drv._loaded_emulation_file = (
            r"D:\Scenario Packs\...\3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
        )
        assert drv._center_freq_programmed is False  # 默认未下发
        await drv.configure({"center_frequency_mhz": 3500.0})
        assert drv._center_freq_programmed is True
        assert drv.get_frequency_identity(
            declared_bandwidth_mhz=40.0
        ) == FrequencyIdentity.from_center_freq_mhz(
            3500.0, 40.0
        )


class TestUxmSetCellConfigArfcn:
    """P1 (Codex on PR #109): measure 必须把从 TestCase 中心频推导的规范 ARFCN 显式
    传给 set_cell_config; 否则 RealUxmDriver fallback 到 NR_BAND_ARFCN_MAP[band], UXM
    实际下发频率 ≠ TestCase → 频率一致性门把任何 (频率 ≠ band fallback) 的真实 run 误杀。
    这里测**真实下发的 SCPI / _arfcn**, 不停在 frequency_mhz 标称层。
    """

    async def test_explicit_arfcn_dispatched_aligns_to_testcase(self):
        drv = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        sent: list = []
        drv._write = lambda s: sent.append(s)   # 捕获真实下发的 SCPI
        drv._query = lambda *a, **k: "1"
        arfcn = freq_mhz_to_nr_arfcn(3500.0)
        assert arfcn != 632628  # 跟 N78 fallback 不同, 测试才有意义
        await drv.set_cell_config(
            {
                "frequency_mhz": 3500.0,
                "arfcn": arfcn,
                "bandwidth_mhz": 100.0,
                "band": "N78",
                "scs_khz": 30,
            }
        )
        # 实际下发的 ARFCN (state + SCPI wire body) 是 TestCase 的, 不是 band fallback
        assert drv._arfcn == arfcn
        assert any("ARFCN" in s.upper() and str(arfcn) in s for s in sent)
        # 频率自报 round-trip 跟 TestCase 精确一致
        assert drv.get_frequency_identity() == FrequencyIdentity.from_center_freq_mhz(
            3500.0, 100.0
        )

    async def test_missing_arfcn_falls_back_and_mismatches_testcase(self):
        # 文档化 fallback 语义: 不传 arfcn → band fallback (agent R6 F3 起接
        # EMQuest 基线, N78=636666=3549.99 MHz), 依然 ≠ TestCase 3500 —
        # 一致性网必须抓到"标称频率没变成下发 ARFCN"这类错配。
        drv = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        drv._write = lambda s: None
        drv._query = lambda *a, **k: "1"
        await drv.set_cell_config(
            {
                "frequency_mhz": 3500.0,
                "bandwidth_mhz": 100.0,
                "band": "N78",
                "scs_khz": 30,
            }
        )
        assert drv._arfcn == 636666  # band fallback → EMQuest 基线, 不是 3500 的 ARFCN
        assert drv.get_frequency_identity() != FrequencyIdentity.from_center_freq_mhz(
            3500.0, 100.0
        )
