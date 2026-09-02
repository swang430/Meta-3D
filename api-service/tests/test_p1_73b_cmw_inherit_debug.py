"""P1-73B Task 11: CMW capability admission and inherit stay fail-closed."""

from app.hal.cmw500_base_station import RealCmw500Driver


def _frozen(enabled: bool):
    return {
        "instrument_connection_id": "5cf9dcb7-fc1a-4287-aa6e-6e10b15b99ce",
        "resolution": {
            "adapter": "cmw500",
            "status": "configured",
            "execution_mode": "real",
        },
        "cmw500_lte_2x2_formal_capability": {
            "schema_version": 1,
            "instrument_connection_id": "5cf9dcb7-fc1a-4287-aa6e-6e10b15b99ce",
            "enabled": enabled,
            "updated_at": "2026-08-26T08:00:00",
        },
    }


def _identified_driver(options):
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    driver._identity_model = "CMW"
    driver._identity_model_verified = True
    driver._firmware_version = "3.5.40"
    driver._installed_options = list(options)
    driver._options_snapshot_verified = True
    return driver


def test_formal_admission_requires_frozen_approval_and_duplex_specific_options():
    # P2-56 ②：TDD 侧多一个 KS510 —— 一次正式 TDD 执行必然要发
    # `CELL[:PCC]:ULDL`，其 Options 原文是「KS550 **and** KS510」（pp.687-688）。
    # 选件集现由 `cmw500_lte_formal_options` 唯一提供（内审 F3）。
    fdd = _identified_driver(["CMW-KS500", "CMW-KS520"])
    tdd = _identified_driver(["CMW-KS550", "CMW-KS520", "CMW-KS510"])

    assert fdd.evaluate_lte_2x2_formal_capability(_frozen(False), duplex="fdd").ready is False
    assert fdd.evaluate_lte_2x2_formal_capability(_frozen(True), duplex="fdd").ready is True
    assert fdd.evaluate_lte_2x2_formal_capability(_frozen(True), duplex="tdd").ready is False
    assert tdd.evaluate_lte_2x2_formal_capability(_frozen(True), duplex="tdd").ready is True
    assert tdd.evaluate_lte_2x2_formal_capability(_frozen(True), duplex="fdd").ready is False


def test_formal_admission_accepts_option_tokens_exactly_as_cmw500_reports_them():
    # 本条测的是**裸 token（不带 CMW- 前缀）也要认**，duplex 只是载体。
    driver = _identified_driver(["KS550", "KS520", "KS510"])

    decision = driver.evaluate_lte_2x2_formal_capability(
        _frozen(True), duplex="tdd"
    )

    assert decision.ready is True


def test_unknown_identity_or_options_never_claim_ready():
    driver = _identified_driver(["CMW-KS500", "CMW-KS520"])
    driver._options_snapshot_verified = False
    decision = driver.evaluate_lte_2x2_formal_capability(_frozen(True), duplex="fdd")
    assert decision.ready is False
    assert decision.status == "unknown"


def test_approval_from_a_different_connection_never_claims_ready():
    driver = _identified_driver(["CMW-KS500", "CMW-KS520"])
    frozen = _frozen(True)
    frozen["cmw500_lte_2x2_formal_capability"]["instrument_connection_id"] = (
        "a8ec9c6b-2984-49d6-9ce0-ec10edc01339"
    )
    decision = driver.evaluate_lte_2x2_formal_capability(frozen, duplex="fdd")
    assert decision.ready is False
    assert decision.status == "unknown"


def test_inherit_is_always_diagnostic_even_when_capability_is_enabled():
    driver = _identified_driver(["CMW-KS500", "CMW-KS520"])
    decision = driver.evaluate_lte_2x2_formal_capability(
        _frozen(True), duplex="fdd", config_mode="inherit"
    )
    assert decision.ready is False
    assert decision.status == "diagnostic"
    assert "inherit" in decision.reason
