from unittest.mock import Mock
from tests.test_road_test_executions import _isolated_db

from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.report_service import report_has_vrt_archive_trust


def test_real_capabilities_require_both_supported_drivers(client, monkeypatch):
    from app.services.instrument_hal_service import get_hal_service

    drivers = get_hal_service().drivers
    for key, cls in (("channelEmulator", RealPropsimF64Driver), ("baseStation", RealUxmDriver)):
        monkeypatch.setitem(drivers, key, object.__new__(cls))
    url = "/api/v1/road-test/capabilities"
    value = client.get(url).json()["conducted"]
    assert value["available"] and value["real_available"] and value["requires_preparation"]
    assert not value["simulated_available"]
    monkeypatch.setitem(drivers, "baseStation", Mock(spec=RealUxmDriver))
    assert not client.get(url).json()["conducted"]["available"]


def test_one_observation_cannot_authorize_archive_verdict():
    archive = {"vrt_archive_trust_schema_version": 2, "mode": "conducted",
               "overall_result": "passed", "pass_rate": 100, "observations": [
                   {"provenance": "server_measured", "metric": "connection_state", "value": True}]}
    assert not report_has_vrt_archive_trust(archive)


def test_throughput_report_and_archive_use_calibrated_cell_readback(client, monkeypatch):
    from copy import deepcopy
    from uuid import uuid4, UUID
    from app.hal.base_station import ThroughputMetrics
    from app.models.report import TestReport
    from app.schemas.road_test.execution import TestMode
    from app.services.instrument_hal_service import get_hal_service
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service
    from tests.test_road_test_executions import _TestingSessionLocal

    scenario = client.get("/api/v1/road-test/scenarios").json()[0]["id"]
    calibration_id = str(uuid4())
    setup = {"ready": True, "asset": {}, "calibration_id": calibration_id, "binding": {
        "execution_mode": "real", "real_preflight": {"calibration": {
            "id": calibration_id, "applicable": True, "evidence_sha256": "ab" * 32}}}}
    # 仅验证来源判据；不调用两个驱动的构造、连接或仪器方法。
    station = object.__new__(RealUxmDriver)
    drivers = get_hal_service().drivers
    monkeypatch.setitem(drivers, "baseStation", station)
    monkeypatch.setitem(drivers, "channelEmulator", object.__new__(RealPropsimF64Driver))
    with _TestingSessionLocal() as db:
        row = service.create(db, mode=TestMode.CONDUCTED, scenario_id=scenario, conducted_setup=setup)
        eid = str(row.id)
        service.start(db, eid)
        for source, value, scope, valid, expected in [
            (station, 0, "pcell", True, "server_measured"),
            (station, 30, "unknown", True, "unverified"),
            (station, 40, "simulated", True, "simulated"),
            (station, 20, "pcell", False, "unverified"),
            (object.__new__(RealUxmDriver), 60, "pcell", True, "unverified"),
        ]:
            rates = ThroughputMetrics(dl_throughput_mbps=value, throughput_scope=scope,
                                      kpi_valid={"dl_throughput": valid})
            item = service.record_observation(db, eid, metric="dl_throughput_mbps", value=value,
                                              time_s=1, driver=source, throughput_readback=rates)
            assert item.provenance == expected
        service.complete(db, eid)
        root = f"/api/v1/road-test/executions/{eid}"
        report = client.get(root + "/report").json()
        assert report["kpi_summary"][0]["mean"] == 0
        assert report["pass_rate"] is None and report["overall_result"] == "undetermined"
        result = client.post(root + "/archive-report")
        assert result.status_code == 200, result.text
        from pypdf import PdfReader
        artifact = db.get(TestReport, UUID(result.json()["id"]))
        archived = artifact.content_data
        text = "".join(page.extract_text() for page in PdfReader(artifact.file_path).pages)
        assert calibration_id in text and "未提供" in text
        assert report_has_vrt_archive_trust(archived)
        for field, wrong in (("mean", 40), ("unit", "bps"), ("passed", True)):
            modified = deepcopy(archived)
            modified["kpi_summary"][0][field] = wrong
            assert not report_has_vrt_archive_trust(modified)
        modified = deepcopy(archived)
        modified["conducted_setup"]["binding"]["real_preflight"]["calibration"]["applicable"] = False
        assert not report_has_vrt_archive_trust(modified)


def test_committed_hardware_contract_matches_registered_routes():
    import json
    import re
    from pathlib import Path
    import yaml
    from app.main import app

    actual = app.openapi()
    saved = yaml.safe_load((Path(__file__).resolve().parents[2] / "api/openapi.yaml").read_text())
    pending = set()
    for path, methods in actual["paths"].items():
        if path.startswith(("/api/v1/road-test/conducted/", "/api/v1/road-test/executions")) or path == "/api/v1/road-test/capabilities":
            assert saved["paths"][path] == methods
            pending.update(re.findall(r'#/components/schemas/([^"]+)', json.dumps(methods)))
    checked = set()
    while pending:
        key = pending.pop()
        schema = actual["components"]["schemas"][key]
        assert saved["components"]["schemas"][key] == schema, key
        checked.add(key)
        pending.update(set(re.findall(r'#/components/schemas/([^"]+)', json.dumps(schema))) - checked)
