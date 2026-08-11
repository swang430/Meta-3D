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


def test_dead_live_lookalike_mock_contracts_and_handlers_are_removed() -> None:
    api_types_source = _read("gui/src/types/api.ts")
    mock_database_source = _read("gui/src/api/mockDatabase.ts")
    mock_server_source = _read("gui/src/api/mockServer.ts")

    for dead_type in (
        "DashboardResponse",
        "TestTemplatesResponse",
        "TestCasesResponse",
        "RecentTestsResponse",
        "ReportTemplatesResponse",
        "RecentTest",
        "ReportTemplate",
    ):
        assert f"export type {dead_type} =" not in api_types_source

    for dead_method in (
        "getDashboard",
        "getTestTemplates",
        "getTestCases",
        "getRecentTests",
        "getReportTemplates",
        "getDashboardAlerts",
    ):
        assert f"{dead_method}(" not in mock_database_source

    for dead_handler in (
        "mock.onGet('/dashboard')",
        "mock.onGet('/tests/cases')",
        "mock.onGet('/tests/templates')",
        "mock.onGet('/tests/recent')",
        "mock.onGet('/monitoring/feeds')",
        "mock.onGet('/dashboard/alerts')",
    ):
        assert dead_handler not in mock_server_source

    # 报告模板页仍消费该活动路由；mock 必须复用 feature 的真实响应契约，不能恢复旧的
    # {reportTemplates} 假结构，也不能因清理零消费 handler 而让页面变成 404。
    assert "TemplateListResponse" in mock_server_source
    assert "../features/Reports/types" in mock_server_source
    assert "mock.onGet('/reports/templates')" in mock_server_source
    assert "const response: TemplateListResponse" in mock_server_source
    assert "total:" in mock_server_source
    assert "page:" in mock_server_source
    assert "page_size:" in mock_server_source

    # 仍有实际 mock WebSocket 消费的演示监控帧必须保留，并明确标成 Mock。
    assert "MockMonitoringFeedsResponse" in api_types_source
    assert "getMonitoringFeeds(): MockMonitoringFeedsResponse" in mock_database_source
    assert "mock.onGet('/dashboard/alerts/summary')" in mock_server_source
