from copy import deepcopy
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import report as report_api
from app.models.report import TestReport
from app.models.test_plan import TestExecution
from app.services.mimo_ota.base_station_execution_evidence import canonical_snapshot_digest
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.report_service import (
    _base_station_projection_is_sanitized,
    report_has_provenance_trust,
)
from tests.test_mimo_ota_report_verified_backcompat import report_db  # noqa: F401
from tests.test_p2_45_diagnostic_formal_consumers import _execution
from tests.test_p2_49_metric_registry_consumers import _current_registry_evidence


def _diagnostic_execution(metric_keys):
    execution = _execution()
    execution.test_case_id = None
    execution.completed_at = datetime(2026, 10, 8)
    evidence = _current_registry_evidence()
    registry = evidence["metric_registry"]
    registry["metrics"] = [
        metric for metric in registry["metrics"] if metric["key"] in metric_keys
    ]
    registry["digest"] = canonical_snapshot_digest({
        key: value for key, value in registry.items() if key != "digest"
    })
    window = evidence["measurement_windows"][0]
    window["metrics"] = {
        key: {**metric, "registry_digest": registry["digest"]}
        for key, metric in window["metrics"].items() if key in metric_keys
    }
    window["metric_registry_digest"] = registry["digest"]
    execution.config["base_station_execution_evidence"] = evidence
    execution.measurements = {"phases": {"measure": {
        "simulated_sources": ["baseStation"],
        "azimuth_results": [{"azimuth_deg": 0.0, "throughput_mbps": 999.0}],
    }, "analysis": {"verdict": "PASS", "avg_throughput_mbps": 999.0}}}
    return execution


@pytest.mark.parametrize("metric_keys", [
    {"cqi_index"},
    {"cqi_index", "dl_throughput_mbps"},
    {"cqi_index", "dl_bler_percent"},
    {"cqi_index", "dl_throughput_mbps", "dl_bler_percent"},
])
def test_diagnostic_writer_preserves_missing_mirrors_and_is_readable(metric_keys):
    """Reverting the writer's absent-mirror handling rejects its own report."""
    execution = _diagnostic_execution(metric_keys)
    content = _build_mimo_ota_content_data(execution, datetime(2026, 10, 8))
    assert report_has_provenance_trust(content) is True
    assert content["overall_result"] == "undetermined"
    assert content["statistics"] == {}
    row = content["base_station_metric_projection"][0]
    assert set(row["metrics"]) == metric_keys
    for metric in row["metrics"].values():
        assert metric["status"] == "diagnostic"
        assert metric["formal_value"] is None
    for key in ("dl_throughput_mbps", "dl_bler_percent"):
        if key in metric_keys:
            assert row[key] == row["metrics"][key]
        else:
            assert row[key]["status"] == "unknown"
            assert row[key]["formal_value"] is None
            assert row[key]["diagnostic_value"] is None
            assert row[key]["unit"] is None
            assert row[key]["exchange_ids"] == []


def test_diagnostic_public_rebuild_detail_download_and_list_agree(report_db, tmp_path, monkeypatch):
    """Exercise real PDF rebuilding and the API's post-generation trust gate."""
    monkeypatch.chdir(tmp_path)
    source = _diagnostic_execution({"cqi_index"})
    execution = TestExecution(
        id=source.id, status="completed", config=source.config,
        measurements=source.measurements, duration_sec=source.duration_sec,
        completed_at=source.completed_at,
    )
    report = TestReport(
        id=uuid4(), title="CQI-only Mock diagnostic", report_type="single_execution",
        format="pdf", status="completed", generated_by="user",
        test_execution_ids=[str(execution.id)],
        content_data={"report_family": "mimo_ota"},
    )
    report_db.add_all([execution, report])
    report_db.commit()

    generated = report_api.generate_report(report.id, db=report_db)
    assert generated.status == "completed"
    assert generated.execution_evidence_outcome.formal_eligible is False
    assert report_api.get_report(report.id, db=report_db).id == report.id
    download = report_api.download_report(report.id, db=report_db)
    assert download.path.endswith(".pdf")
    assert report_api._report_summary(report_db, report).requires_regeneration is False

    # Recomputed digest must not authorize a fake absent compatibility metric.
    poisoned = deepcopy(report.content_data)
    poisoned["base_station_metric_projection"][0]["dl_throughput_mbps"].update(
        status="diagnostic", diagnostic_value=999.0,
    )
    attestation = poisoned["base_station_metric_projection_attestation"]
    attestation["projection_digest"] = canonical_snapshot_digest({
        "evidence_digest": attestation["evidence_digest"],
        "metric_registry_digest": attestation["metric_registry_digest"],
        "projection": poisoned["base_station_metric_projection"],
    })
    assert _base_station_projection_is_sanitized(
        poisoned["base_station_metric_projection"], attestation,
    ) is False
    report.content_data = poisoned
    report_db.commit()
    with pytest.raises(HTTPException) as rejection:
        report_api.download_report(report.id, db=report_db)
    assert rejection.value.status_code == 409
