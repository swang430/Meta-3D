"""P2-45: one server-owned execution qualification boundary."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "api-service" / "app"


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text()


def test_all_five_entry_paths_use_the_shared_qualification_wrapper():
    runner = _read("api-service/app/services/test_case_runner.py")
    commissioning = _read("api-service/app/api/commissioning.py")
    assert runner.count("freeze_execution_base_station_adapter_profile(") == 1
    assert commissioning.count("_freeze_instrument_lease(") == 5


def test_classification_decision_does_not_read_legacy_or_vendor_authorizers():
    source = _read("api-service/app/services/execution_qualification.py")
    freezer = source.split("def freeze_execution_qualification(", 1)[1]
    decision = freezer.split("payload: dict[str, Any]", 1)[0]

    for forbidden in (
        "precheck_strict_cal",
        "connection_params",
        "cmw500_lte_2x2_formal",
        "base_station_config_mode",
        "inherit",
        "os.environ",
        "UXM",
        "CMW",
    ):
        assert forbidden not in decision


def test_all_formal_consumers_use_the_frozen_evidence_outcome_boundary():
    required = (
        "api-service/app/services/mimo_ota/executors/analysis.py",
        "api-service/app/services/mimo_ota/executors/report.py",
        "api-service/app/services/report_service.py",
        "api-service/app/services/report_data_collector.py",
        "api-service/app/api/test_execution.py",
        "api-service/app/api/commissioning.py",
    )
    for relative in required:
        source = _read(relative)
        assert "execution_evidence_blocks_formal_outputs" in source, relative
        assert "execution_is_diagnostic" not in source, relative


def test_gui_has_no_legacy_client_side_formal_or_calibration_authority():
    service = _read("gui/src/api/service.ts")
    commissioning = _read("gui/src/components/Commissioning/index.tsx")
    session_body = _read("gui/src/components/Commissioning/sessionBody.ts")

    assert "updateCmw500Lte2x2FormalCapability" not in service
    assert "calBypass" not in commissioning
    assert "precheck_strict_cal" not in session_body
