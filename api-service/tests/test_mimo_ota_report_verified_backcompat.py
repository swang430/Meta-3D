"""Codex on PR #80: report must NOT default an absent verified flag to True —
historical/migrated executions carry provenance (measurement_source /
quiet_zone_ripple_source) but no quiet_zone_verified / trp_verified key, and
defaulting True would silently present an old fallback run as a real measurement.
Pins that the report derives verification from provenance instead.

P2-21 迁移: 三标志的生效端从 step 顶层键挪到 parameters 下的可读标注
("已验证 (…)"/"未验证 (…)"/"未知 (…)") —— 本文件钉的是**推导逻辑**不变,
断言跟着打在新生效端 (标注前缀), 渲染可达性另由 test_p2_21_* 行为门钉。
"""
from datetime import datetime
from types import SimpleNamespace

from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data


def _exec(phases):
    return SimpleNamespace(
        measurements={"phases": phases},
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1),
        # no `test_plan` attribute → getattr(..., None) inside the builder
    )


def _step(content, phase):
    return next(s for s in content["step_results"] if s["phase"] == phase)


def test_historical_fallback_not_marked_verified():
    """Legacy payloads: provenance present, verified flag ABSENT → must NOT
    be reported as verified."""
    phases = {
        "precheck": {
            "overall_pass": True,
            "quiet_zone_ripple_db": 0.7,
            "quiet_zone_ripple_source": "fallback_default",  # no quiet_zone_verified key
        },
        "reference": {
            "measured_trp_dbm": 23.5,
            "compensation_factor_db": 8.0,
            "measurement_source": "mock",  # no trp_verified key
        },
        "measure": {},
        "analysis": {"overall_pass": True},
    }
    content = _build_mimo_ota_content_data(_exec(phases), datetime(2026, 1, 1))
    assert not _step(content, "precheck")["parameters"]["静区验证"].startswith("已验证")
    assert not _step(content, "reference")["parameters"]["TRP 验证"].startswith("已验证")


def test_measure_path_loss_verified_derived_from_cert_id():
    """measure: absent path_loss_verified flag → derive from
    path_loss_certificate_id (None → not verified, present → verified)."""
    base = {
        "precheck": {"overall_pass": True, "quiet_zone_ripple_source": "probe_pattern_peak_spread"},
        "reference": {"measured_trp_dbm": 23.0, "compensation_factor_db": 8.0, "trp_verified": True},
        "analysis": {"overall_pass": True},
    }
    no_cert = dict(base, measure={"path_loss_certificate_id": None})
    c1 = _build_mimo_ota_content_data(_exec(no_cert), datetime(2026, 1, 1))
    assert _step(c1, "measure")["parameters"]["路损验证"].startswith("未验证")
    with_cert = dict(base, measure={"path_loss_certificate_id": "cert-123"})
    c2 = _build_mimo_ota_content_data(_exec(with_cert), datetime(2026, 1, 1))
    assert _step(c2, "measure")["parameters"]["路损验证"].startswith("已验证")


def test_historical_real_provenance_derives_verified():
    """Legacy real-source payload (no flag) → derived verified=True for QZ
    (source unambiguously recovers it)."""
    phases = {
        "precheck": {
            "overall_pass": True,
            "quiet_zone_ripple_db": 0.5,
            "quiet_zone_ripple_source": "probe_pattern_peak_spread",
        },
        "reference": {"measured_trp_dbm": 23.0, "compensation_factor_db": 8.0,
                      "measurement_source": "hal_signal_analyzer", "trp_verified": True},
        "measure": {},
        "analysis": {"overall_pass": True},
    }
    content = _build_mimo_ota_content_data(_exec(phases), datetime(2026, 1, 1))
    assert _step(content, "precheck")["parameters"]["静区验证"].startswith("已验证")
    assert _step(content, "reference")["parameters"]["TRP 验证"].startswith("已验证")


def test_fresh_explicit_flags_passthrough():
    """Fresh executions set the flags explicitly — used verbatim."""
    phases = {
        "precheck": {"overall_pass": True, "quiet_zone_ripple_db": 0.7,
                     "quiet_zone_ripple_source": "fallback_default",
                     "quiet_zone_verified": False},
        "reference": {"measured_trp_dbm": 23.5, "compensation_factor_db": 8.0,
                      "measurement_source": "mock", "trp_verified": False},
        "measure": {},
        "analysis": {"overall_pass": True},
    }
    content = _build_mimo_ota_content_data(_exec(phases), datetime(2026, 1, 1))
    assert _step(content, "precheck")["parameters"]["静区验证"].startswith("未验证")
    assert _step(content, "reference")["parameters"]["TRP 验证"].startswith("未验证")
