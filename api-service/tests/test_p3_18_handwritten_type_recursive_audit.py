from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_dead_handwritten_live_contract_clients_are_removed() -> None:
    service_source = _read("gui/src/api/service.ts")

    for dead_client in (
        "fetchDashboard",
        "fetchTestTemplates",
        "fetchTestCases",
        "fetchRecentTests",
        "fetchAlerts",
        "fetchReportTemplates",
        "fetchMonitoringFeeds",
    ):
        assert dead_client not in service_source


def test_monitoring_demo_metric_contract_is_not_presented_as_live_response() -> None:
    app_source = _read("gui/src/App.tsx")
    api_types_source = _read("gui/src/types/api.ts")

    assert "fetchMonitoringFeeds" not in app_source
    assert "metricFeeds" not in app_source
    assert "export type MonitoringFeedsResponse =" not in api_types_source
    assert "MockMonitoringFeedsResponse" in api_types_source
