"""P2-11 Phase 2: GCM .smu TestCase-驱动门 + schema 字段 测试.

钉死:
1. evaluate_emulation_file_gate 4 路决策 (mock N/A / TestCase 指定 / 真 F64 strict
   FAIL / 真 F64 opt-out warn) + 空串视作未指定。
2. MIMOOTAConfiguration 新字段 emulation_file / precheck_strict_emulation_file 默认
   与可覆盖。
"""
from __future__ import annotations

from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.mimo_ota.emulation_file_gate import (
    GATE_FAIL,
    GATE_PROCEED,
    GATE_WARN_FALLBACK,
    evaluate_emulation_file_gate,
)


class TestEmulationFileGate:
    def test_mock_emulator_na_proceeds(self):
        # mock/缺失仿真器不加载真 .smu → 门 N/A, 放行 (即使 strict + 没指定)
        d = evaluate_emulation_file_gate(
            emulator_is_real=False, emulation_file=None, strict=True
        )
        assert d.action == GATE_PROCEED
        assert not d.should_fail and not d.should_warn

    def test_testcase_specified_proceeds(self):
        # 真 F64 + TestCase 指定了 .smu → 路径 B, 放行
        d = evaluate_emulation_file_gate(
            emulator_is_real=True,
            emulation_file=r"D:\Scenario Packs\..._3600M.smu",
            strict=True,
        )
        assert d.action == GATE_PROCEED

    def test_real_no_file_strict_fails(self):
        # 真 F64 + 未指定 + strict → FAIL (不静默 fallback 驱动默认)
        d = evaluate_emulation_file_gate(
            emulator_is_real=True, emulation_file=None, strict=True
        )
        assert d.action == GATE_FAIL
        assert d.should_fail
        assert d.message and "emulation_file" in d.message

    def test_real_no_file_optout_warns(self):
        # 真 F64 + 未指定 + opt-out → 降级 warning, 用驱动默认 (路径 A bring-up)
        d = evaluate_emulation_file_gate(
            emulator_is_real=True, emulation_file=None, strict=False
        )
        assert d.action == GATE_WARN_FALLBACK
        assert d.should_warn
        assert d.message

    def test_empty_string_treated_as_unspecified(self):
        # 空串不能静默选中 fallback 却假装 TestCase 驱动 → 跟 None 同样走 strict FAIL
        d = evaluate_emulation_file_gate(
            emulator_is_real=True, emulation_file="", strict=True
        )
        assert d.action == GATE_FAIL


class TestEmulationFileSchemaFields:
    def test_defaults(self):
        cfg = MIMOOTAConfiguration()
        # 生产默认: 不指定 .smu, 但严格门开 (正式 GCM 测试必须 TestCase 驱动)
        assert cfg.emulation_file is None
        assert cfg.precheck_strict_emulation_file is True

    def test_override(self):
        cfg = MIMOOTAConfiguration(
            emulation_file=r"D:\packs\CDLC_3500M.smu",
            precheck_strict_emulation_file=False,
        )
        assert cfg.emulation_file == r"D:\packs\CDLC_3500M.smu"
        assert cfg.precheck_strict_emulation_file is False
