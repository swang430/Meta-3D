"""Regression: commissioning CreateSessionRequest → config override mapping for
the strict precheck gates (P1-8 cal / P1-9 DUT).

The Lab-smoke fix added optional `precheck_strict_dut` / `precheck_strict_cal`
fields to CreateSessionRequest. The correctness hazard is the explicit-null vs
omitted vs value cartesian (cf. feedback_endpoint_null_field_cartesian):

  - omitted (None)  → MUST NOT appear in the override dict, so the config schema
                      default (True / strict) is preserved. Leaking None into the
                      config would falsy-bypass `if config.precheck_strict_dut:`
                      for EVERY session — silently disabling the on-site gate.
  - explicit False  → appears as False (Lab-smoke opt-out).
  - explicit True   → appears as True.

NOTE: the mock/real auto-skip is NOT applied at session-create — it's evaluated
live at precheck time (`strict = config_flag AND hardware_real`, see
test_mimo_ota_precheck_{dut,cal}_gate.py). So here we only pin the request →
override translation: omitted leaves the schema default, explicit value carries.
"""
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.commissioning import CreateSessionRequest, _request_overrides


# P2-11: Phase 1/2/3 加了 3 道新 strict 门 + Phase 6 (#114/#124/#126) 加 cell_config 门;
# 暗室首测 "强制跳过严格门" 必须一并降级它们, 否则真仪表 bring-up 撞上新门无法绕过
# (cal/dut 之外的捷径缺口)。cell_config 门此前漏接三层 bypass (GUI labSmoke + CreateSessionRequest
# + _request_overrides), feedback_strict_gate_extend_bypass_toggle 母题又踩, 本测试一并钉死。
# 新门同样走 null/False/value cartesian。
_P2_11_FLAGS = (
    "precheck_strict_frequency",
    "precheck_strict_emulation_file",
    "precheck_strict_switch_mode",
    "precheck_strict_cell_config",
    "precheck_strict_dut_capability",
    "precheck_strict_sim_identity",
)
_ALL_STRICT_FLAGS = ("precheck_strict_dut", "precheck_strict_cal", *_P2_11_FLAGS)


def test_strict_flags_omitted_are_absent_from_overrides():
    """Default request → flags not in overrides → config keeps strict default."""
    overrides = _request_overrides(CreateSessionRequest())
    for flag in _ALL_STRICT_FLAGS:
        assert flag not in overrides, f"{flag} leaked into overrides as None"


def test_strict_flags_false_pass_through():
    """Lab-smoke toggle → explicit False is carried into overrides (全 7 道门)。"""
    overrides = _request_overrides(
        CreateSessionRequest(
            precheck_strict_dut=False,
            precheck_strict_cal=False,
            precheck_strict_frequency=False,
            precheck_strict_emulation_file=False,
            precheck_strict_switch_mode=False,
            precheck_strict_cell_config=False,
            precheck_strict_dut_capability=False,
            precheck_strict_sim_identity=False,
        )
    )
    for flag in _ALL_STRICT_FLAGS:
        assert overrides[flag] is False, f"{flag} not carried as False"


def test_strict_flags_true_pass_through():
    """Explicit True is carried (distinct from omitted, though same effect)."""
    overrides = _request_overrides(
        CreateSessionRequest(precheck_strict_dut=True, precheck_strict_cal=True)
    )
    assert overrides["precheck_strict_dut"] is True
    assert overrides["precheck_strict_cal"] is True


def test_one_flag_set_other_omitted():
    """Setting only one flag must not drag the other in as None."""
    overrides = _request_overrides(CreateSessionRequest(precheck_strict_dut=False))
    assert overrides["precheck_strict_dut"] is False
    assert "precheck_strict_cal" not in overrides


def test_p2_11_flag_set_others_omitted():
    """P2-11: 只设 frequency 门, 其余 (含另两道新门) 不能被拖成 None 静默绕过。"""
    overrides = _request_overrides(
        CreateSessionRequest(precheck_strict_frequency=False)
    )
    assert overrides["precheck_strict_frequency"] is False
    for flag in ("precheck_strict_emulation_file", "precheck_strict_switch_mode",
                 "precheck_strict_cell_config", "precheck_strict_dut_capability",
                 "precheck_strict_sim_identity",
                 "precheck_strict_cal", "precheck_strict_dut"):
        assert flag not in overrides


def test_p2_11_flags_true_pass_through():
    """显式 True 也透传 (跟 omitted 区分, 虽同效)。"""
    overrides = _request_overrides(
        CreateSessionRequest(
            precheck_strict_frequency=True,
            precheck_strict_emulation_file=True,
            precheck_strict_switch_mode=True,
            precheck_strict_cell_config=True,
            precheck_strict_dut_capability=True,
            precheck_strict_sim_identity=True,
        )
    )
    for flag in _P2_11_FLAGS:
        assert overrides[flag] is True


def test_gcm_session_requires_current_model_source_in_strict_mode():
    """GCM 冷启动不能创建一个依赖 F64 遗留 .smu 的正式会话。"""
    with pytest.raises(ValidationError, match="emulation_file|channel_asset_id"):
        CreateSessionRequest(engine_mode="keysight_gcm")

    assert CreateSessionRequest(
        engine_mode="keysight_gcm",
        emulation_file=r"D:\Scenario Packs\onsite.smu",
    ).emulation_file
    assert CreateSessionRequest(
        engine_mode="keysight_gcm",
        precheck_strict_emulation_file=False,
    ).precheck_strict_emulation_file is False


def test_onsite_rf_workpoint_is_saved_in_session_overrides():
    """本次首测的 UXM/F64 工作点必须完整进入会话，不能只停留在界面。"""
    asset_id = UUID("12345678-1234-5678-1234-567812345678")
    overrides = _request_overrides(
        CreateSessionRequest(
            engine_mode="keysight_gcm",
            channel_asset_id=asset_id,
            frequency_hz=3_549_990_000.0,
            bandwidth_mhz=40.0,
            uxm_dl_power_dbm_per_bw=-15.0,
            f64_input_ref_dbm=-17.0,
            f64_crest_db=15.0,
            f64_output_level_dbm=-52.0,
            f64_bypass_mode=2,
        )
    )

    assert overrides["channel_asset_id"] == str(asset_id)
    assert overrides["frequency_hz"] == 3_549_990_000.0
    assert overrides["bandwidth_mhz"] == 40.0
    assert overrides["uxm_dl_power_dbm_per_bw"] == -15.0
    assert overrides["f64_input_ref_dbm"] == -17.0
    assert overrides["f64_crest_db"] == 15.0
    assert overrides["f64_output_level_dbm"] == -52.0
    assert overrides["f64_bypass_mode"] == 2

# NOTE: the mock/real auto-skip is verified at the precheck gate level (live
# HAL), see test_mimo_ota_precheck_{dut,cal}_gate.py
# (test_mock_baseStation_auto_skips_strict_dut_gate /
# test_mock_channelEmulator_auto_skips_strict_cal_gate). It is intentionally
# NOT a session-create concern anymore (Codex on PR #75).
