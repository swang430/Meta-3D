"""SIM 身份核对 (P2-13 Phase 2) 单测: 声明 IMSI vs attach IMSI 比 + 脱敏。"""
from __future__ import annotations

from app.services.mimo_ota.sim_identity_check import check_sim_identity


class TestCheckSIMIdentity:
    def test_match(self):
        r = check_sim_identity(declared_imsi="460001234567890", attached_imsi="460001234567890")
        assert r.consistent is True

    def test_mismatch(self):
        r = check_sim_identity(declared_imsi="460001234567890", attached_imsi="310260000000001")
        assert r.consistent is False

    def test_strip_normalization(self):
        r = check_sim_identity(declared_imsi=" 460001234567890 ", attached_imsi="460001234567890")
        assert r.consistent is True

    def test_imsi_masked_prefix_only(self):
        r = check_sim_identity(declared_imsi="460001234567890", attached_imsi="310260000000001")
        # 前 8 位 + …, 不暴露完整订户号
        assert r.declared_imsi_masked == "46000123…"
        assert r.attached_imsi_masked == "31026000…"
        assert "4567890" not in (r.declared_imsi_masked or "")
