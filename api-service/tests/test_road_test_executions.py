"""
Integration Tests for Virtual Road Test - Test Execution

Tests execution lifecycle: create → start → monitor → stop

Test isolation (P3-8 follow-up): each test runs against an isolated
in-memory SQLite DB instead of the shared dev Postgres. See
``test_road_test_scenarios.py`` module docstring for the rationale.
"""

import pytest
import time
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app


_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _isolated_db():
    Base.metadata.create_all(bind=_engine)
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=_engine)


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestExecutionCreate:
    """Test execution creation"""

    def test_create_digital_twin_execution(self, client: TestClient):
        """Test creating digital twin execution"""
        # Get a scenario ID
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        execution_data = {
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {
                "acceleration_factor": 10.0,
                "enable_metrics_streaming": True
            },
            "notes": "Integration test - digital twin"
        }

        response = client.post(
            "/api/v1/road-test/executions",
            json=execution_data
        )

        assert response.status_code == 201
        execution = response.json()

        # Verify execution structure
        assert "execution_id" in execution
        assert execution["mode"] == "digital_twin"
        assert execution["scenario_id"] == scenario_id
        assert execution["status"] == "idle"  # Initial status is 'idle'
        # Note: API returns 'created_by' not 'created_at'

    def test_create_conducted_execution(self, client: TestClient, sample_topology_data):
        """Test creating conducted execution (requires topology)"""
        # Get a scenario ID
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        # Create topology first
        topology_response = client.post(
            "/api/v1/road-test/topologies",
            json=sample_topology_data
        )
        topology_id = topology_response.json()["id"]

        execution_data = {
            "mode": "conducted",
            "scenario_id": scenario_id,
            "topology_id": topology_id,
            "config": {},
            "notes": "Integration test - conducted"
        }

        response = client.post(
            "/api/v1/road-test/executions",
            json=execution_data
        )

        assert response.status_code == 201
        execution = response.json()
        assert execution["mode"] == "conducted"
        assert execution["topology_id"] == topology_id

    def test_create_ota_execution(self, client: TestClient):
        """Test creating OTA execution"""
        # Get a scenario ID
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        execution_data = {
            "mode": "ota",
            "scenario_id": scenario_id,
            "config": {
                "mpac_config": {
                    "num_probes": 32,
                    "chamber_size": "large"
                }
            },
            "notes": "Integration test - OTA"
        }

        response = client.post(
            "/api/v1/road-test/executions",
            json=execution_data
        )

        assert response.status_code == 201
        execution = response.json()
        assert execution["mode"] == "ota"

    def test_create_execution_invalid_scenario(self, client: TestClient):
        """Test creating execution with invalid scenario ID"""
        execution_data = {
            "mode": "digital_twin",
            "scenario_id": "invalid-scenario-id",
            "config": {},
            "notes": "Should fail"
        }

        response = client.post(
            "/api/v1/road-test/executions",
            json=execution_data
        )

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestExecutionList:
    """Test execution listing and filtering"""

    def test_list_all_executions(self, client: TestClient):
        """Test listing all executions"""
        response = client.get("/api/v1/road-test/executions")

        assert response.status_code == 200
        executions = response.json()
        assert isinstance(executions, list)

    def test_filter_by_scenario_id(self, client: TestClient):
        root = "/api/v1/road-test"
        scenes = client.get(f"{root}/scenarios").json()
        ids = []
        for scene in scenes[:2]:
            result = client.post(f"{root}/executions", json={
                "mode": "digital_twin", "scenario_id": scene["id"], "config": {}
            })
            assert result.status_code == 201, result.text
            ids.append(result.json()["execution_id"])
        assert len(ids) == 2
        response = client.get(f"{root}/executions", params={"scenario_id": scenes[0]["id"]})
        assert [row["execution_id"] for row in response.json()] == ids[:1]

    def test_filter_by_mode(self, client: TestClient):
        """Test filtering executions by mode"""
        # Create executions with different modes
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        # Create digital twin
        client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })

        # Filter by mode
        response = client.get("/api/v1/road-test/executions?mode=digital_twin")

        assert response.status_code == 200
        executions = response.json()
        assert all(e["mode"] == "digital_twin" for e in executions)

    def test_filter_by_status(self, client: TestClient):
        """Test filtering executions by status"""
        response = client.get("/api/v1/road-test/executions?status=idle")

        assert response.status_code == 200
        executions = response.json()
        # All newly created executions should be in 'idle' status
        assert all(e["status"] in ["idle", "ready"] for e in executions)


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestExecutionDetail:
    """Test execution detail retrieval"""

    def test_get_execution_detail(self, client: TestClient):
        """Test retrieving execution details"""
        # Create an execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {"acceleration_factor": 5.0}
        })
        execution_id = create_response.json()["execution_id"]

        # Get detail
        response = client.get(f"/api/v1/road-test/executions/{execution_id}")

        assert response.status_code == 200
        execution = response.json()
        assert execution["execution_id"] == execution_id
        assert "scenario_id" in execution
        assert "status" in execution
        assert "config" in execution
        assert execution["config"]["acceleration_factor"] == 5.0

    def test_get_nonexistent_execution(self, client: TestClient):
        """Test retrieving non-existent execution"""
        response = client.get("/api/v1/road-test/executions/invalid-exec-id")

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestExecutionControl:
    """Test execution control (start, pause, resume, stop)"""

    def test_start_execution(self, client: TestClient):
        """Test starting an execution"""
        # Create an execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Start execution
        response = client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "start"}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"

        # Verify status changed
        status_response = client.get(
            f"/api/v1/road-test/executions/{execution_id}/status"
        )
        status = status_response.json()
        assert status["status"] in ["running", "ready"]  # API uses 'status', not 'state'

    def test_pause_execution(self, client: TestClient):
        """Test pausing a running execution"""
        # Create and start execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Start
        client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "start"}
        )

        # Pause
        response = client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "pause"}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"

    def test_resume_execution(self, client: TestClient):
        """Test resuming a paused execution"""
        # Create, start, and pause execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Start then pause
        client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "start"}
        )
        client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "pause"}
        )

        # Resume
        response = client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "resume"}
        )

        assert response.status_code == 200

    def test_stop_execution(self, client: TestClient):
        """Test stopping an execution"""
        # Create and start execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Start
        client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "start"}
        )

        # Stop
        response = client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "stop"}
        )

        assert response.status_code == 200

        # Verify status
        status_response = client.get(
            f"/api/v1/road-test/executions/{execution_id}/status"
        )
        status = status_response.json()
        assert status["status"] in ["stopped", "completed"]  # API uses 'status', not 'state'

    def test_invalid_control_action(self, client: TestClient):
        """Test invalid control action"""
        # Create execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Try invalid action
        response = client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "invalid_action"}
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestExecutionStatus:
    """Test execution status monitoring"""

    def test_get_execution_status(self, client: TestClient):
        """Test getting execution status"""
        # Create execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Get status
        response = client.get(
            f"/api/v1/road-test/executions/{execution_id}/status"
        )

        assert response.status_code == 200
        status = response.json()

        # Verify status structure
        assert "status" in status  # API uses 'status', not 'state'
        assert "progress_percent" in status
        assert "elapsed_time_s" in status
        assert "current_position" in status or status["status"] == "idle"

    def test_status_after_start(self, client: TestClient):
        """Test status after starting execution"""
        # Create and start execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Start
        client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "start"}
        )

        # Get status
        response = client.get(
            f"/api/v1/road-test/executions/{execution_id}/status"
        )

        assert response.status_code == 200
        status = response.json()
        assert status["status"] in ["running", "ready", "completed"]  # API uses 'status', not 'state'


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestExecutionMetrics:
    """Test execution metrics retrieval"""

    def test_get_execution_metrics(self, client: TestClient):
        """Test getting execution metrics"""
        # Create and start execution
        scenarios_response = client.get("/api/v1/road-test/scenarios")
        scenario_id = scenarios_response.json()[0]["id"]

        create_response = client.post("/api/v1/road-test/executions", json={
            "mode": "digital_twin",
            "scenario_id": scenario_id,
            "config": {}
        })
        execution_id = create_response.json()["execution_id"]

        # Start execution
        client.post(
            f"/api/v1/road-test/executions/{execution_id}/control",
            json={"action": "start"}
        )

        # Get metrics
        response = client.get(
            f"/api/v1/road-test/executions/{execution_id}/metrics"
        )

        assert response.status_code == 200
        metrics = response.json()

        # Verify metrics structure (may be empty if just started)
        assert isinstance(metrics, dict)


def test_runner_samples_and_forged_client_source_stay_out_of_verdict(client):
    from app.schemas.road_test.execution import TestMode
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service

    with _TestingSessionLocal() as db:
        row = service.create(db, mode=TestMode.DIGITAL_TWIN, scenario_id="sample")
        eid = str(row.id)
        service.start(db, eid)
        service.record_observation(db, eid, metric="dl_throughput_mbps", value=999,
                                   driver=object(), time_s=1)
        service.record_observation(db, eid, metric="connection_state", value=None,
                                   driver=None, time_s=2)
        url = f"/api/v1/road-test/executions/{eid}"
        payload = {"execution_id": eid, "time_series": [{"time_s": 1, "dl_throughput_mbps": 999,
                   "provenance": "server_measured"}], "events": [], "phases": [], "kpi_summary": []}
        assert client.post(url + "/metrics", json=payload).is_success
        # 历史数据可能已有错误的真值声明，不能替同批原始样本证明来源。
        service.set_summary(db, eid, {"伪造摘要": {"mean": 999, "passed": True, "provenance": "server_measured"}})
        service.set_kpi_results(db, eid, {"伪造摘要": True})
        service.complete(db, eid)
        history = client.get(url + "/metrics").json()
        assert history["summary"]["伪造摘要"]["passed"] is None and history["kpi_results"] == {}
        report = client.get(url + "/report").json()
        assert report["observations"] == history["observations"]
        sample, missing = report["observations"]
        assert sample["provenance"] == "simulated" and sample["value"] == 999
        assert sample["source_frame_time_s"] is None and sample["device_playback_time_s"] is None
        assert missing["value"] is None
        assert report["kpi_summary"] == [] and report["pass_rate"] is None
        assert report["overall_result"] == "undetermined"


@pytest.mark.parametrize(("end_state", "verdict"), [("failed", "failed"), ("stopped", "incomplete")])
def test_conducted_archive_preserves_mock_readings_and_terminal_state(
    client, tmp_path, monkeypatch, end_state, verdict
):
    from uuid import UUID
    from pypdf import PdfReader
    from app.hal.base_station import MockBaseStation
    from app.models.report import TestReport
    from app.schemas.road_test.execution import TestMode
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service

    monkeypatch.chdir(tmp_path)
    with _TestingSessionLocal() as db:
        row = service.create(db, mode=TestMode.CONDUCTED, scenario_id="sample")
        eid = str(row.id)
        url = f"/api/v1/road-test/executions/{eid}"
        service.start(db, eid)
        service.record_observation(db, eid, metric="dl_throughput_mbps", value=92,
                                   driver=MockBaseStation.__new__(MockBaseStation), time_s=3)
        body = {"execution_id": eid, "time_series": [], "events": [{"type": "passed"}],
                "phases": [], "kpi_summary": []}
        assert client.post(url + "/metrics", json=body).status_code == 409
        if end_state == "failed":
            service.fail(db, eid, "模拟驱动拒绝继续播放")
        else:
            service.stop(db, eid)
        with pytest.raises(ValueError):
            service.record_observation(db, eid, metric="dl_throughput_mbps", value=42,
                                       driver=None, time_s=4)
        response = client.post(url + "/archive-report")
        assert response.status_code == 200, response.text
        archived = db.get(TestReport, UUID(response.json()["id"]))
        report = client.get(url + "/report").json()
        assert report["status"] == end_state and report["overall_result"] == verdict
        assert archived.content_data["observations"] == report["observations"]
        assert archived.content_data["kpi_summary"] == [] and archived.content_data["pass_rate"] is None
        text = "".join(page.extract_text() for page in PdfReader(archived.file_path).pages)
        assert "MockBaseStation" in text and "92" in text


def test_mock_only_snapshot_rejects_non_mock_observation():
    from app.schemas.road_test.execution import TestMode
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service

    with _TestingSessionLocal() as db:
        row = service.create(db, mode=TestMode.CONDUCTED, scenario_id="sample",
                             conducted_setup={"asset": {"mock_only": True}})
        eid = str(row.id)
        service.start(db, eid)
        with pytest.raises(ValueError, match="模拟专用"):
            service.record_observation(db, eid, metric="dl_throughput_mbps", value=999,
                                       driver=object(), time_s=1)
        assert service.query_kpi_samples(db, eid) == []


def test_legacy_client_setup_cannot_authorize_or_describe_a_conducted_run(client, monkeypatch):
    from app.api import road_test_conducted
    from app.schemas.road_test.execution import TestMode
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service
    from app.services.report_service import report_has_vrt_archive_trust

    forged = {"ready": True, "binding": {"execution_mode": "real"}, "asset": {"name": "伪造绑定"}}
    with _TestingSessionLocal() as db:
        row = service.create(db, mode=TestMode.CONDUCTED, scenario_id="legacy",
                             config={"conducted": forged, "operator_note": "保留"})
        eid = str(row.id)
        root = "/api/v1/road-test/executions"
        url = root + "/" + eid
        assert client.get(url).json()["config"] == {"operator_note": "保留"}
        history = client.get(root + "?mode=conducted").json()
        assert next(item for item in history if item["execution_id"] == eid)["conducted"] is None
        monkeypatch.setattr(road_test_conducted, "resolve", lambda *a, **k: pytest.fail("旧记录不能进入启动核对"))
        denied = client.post(url + "/control", json={"action": "start"})
        assert denied.status_code == 409 and "准备记录" in denied.json()["detail"]
        from app.models.road_test import VrtKpiSample
        db.add(VrtKpiSample(execution_id=row.id, time_s=1, observation={
            "time_s": 1, "metric": "dl_throughput_mbps", "value": 999, "source": "旧回读",
            "unit": "Mbps", "provenance": "server_measured", "sampled_at": "2026-11-24T00:00:00Z",
        }))
        db.commit()
        assert client.get(url + "/metrics").json()["observations"][0]["provenance"] == "unverified"
        service.fail(db, eid, "旧记录")
        assert client.get(url + "/report").json()["kpi_summary"] == []
        assert client.get(url + "/report").json()["conducted_setup"] is None
        assert not report_has_vrt_archive_trust({"vrt_archive_trust_schema_version": 1, "conducted_setup": forged})


def test_frozen_twin_replay(client, monkeypatch, tmp_path):
    from uuid import UUID
    from app.models.report import TestReport

    monkeypatch.chdir(tmp_path)
    base = "/api/v1/road-test"
    scenario = client.get(base + "/scenarios").json()[0]["id"]
    payload = {"mode": "digital_twin", "scenario_id": scenario,
               "config": {"model_parameters": {"seed": 7}}}
    timelines = []
    for _ in range(2):
        execution = client.post(base + "/executions", json=payload).json()
        assert execution["config"]["digital_twin"]["model_parameters"] == {"seed": 7}
        url = base + "/executions/" + execution["execution_id"]
        assert client.get(url + "/timeline").status_code == 409
        assert client.post(url + "/control", json={"action": "start"}).is_success
        timeline = client.get(url + "/timeline").json()
        assert timeline["formal_kpi"] is False
        assert timeline["points"] and all(p["provenance"] == "simulated" for p in timeline["points"])
        assert client.post(url + "/control", json={"action": "complete"}).is_success
        finished = client.get(url + "/timeline").json()
        assert len(finished["points"]) == len(execution["config"]["digital_twin"]["scenario_snapshot"]["route"]["waypoints"])
        receipt = client.post(url + "/archive-report")
        assert receipt.is_success, receipt.text
        with _TestingSessionLocal() as db:
            from pypdf import PdfReader
            archive = db.get(TestReport, UUID(receipt.json()["id"]))
            pages = [page.extract_text() for page in PdfReader(archive.file_path).pages]
            assert "数字孪生模拟报告" in pages[0]
            pdf_text = "".join(pages)
            for expected in ("demo-v1", "随机种子 7", "模拟下行吞吐量", "不参与正式性能判定"):
                assert expected in pdf_text
            assert str(finished["points"][-1]["dl_throughput_mbps"]) + " Mbps" in pdf_text
            archived = archive.content_data
            assert archived["simulation_timeline"] == finished
            assert archived["simulation_input"] == execution["config"]["digital_twin"]
            assert archived["kpi_summary"] == [] and archived["pass_rate"] is None
            assert archived["overall_result"] == "undetermined"
        timelines.append(finished)
        assert client.get(url + "/metrics").json()["kpi_results"] == {}
    assert timelines[0] == timelines[1]


def test_twin_stop_freezes_route_prefix(client, monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    from app.api import road_test
    from importlib import import_module

    clock = datetime(2026, 1, 1)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(road_test, "_utcnow", lambda: clock)
    service = import_module("app.services.road_test.vrt_execution_service")
    monkeypatch.setattr(service, "_utcnow", lambda: clock)
    base = "/api/v1/road-test"
    sid = client.get(base + "/scenarios").json()[0]["id"]
    row = client.post(base + "/executions", json={"scenario_id": sid, "mode": "digital_twin"}).json()
    route = row["config"]["digital_twin"]["scenario_snapshot"]["route"]
    url = base + "/executions/" + row["execution_id"]
    assert client.post(url + "/control", json={"action": "start"}).is_success
    clock += timedelta(seconds=route["waypoints"][1]["time_s"])
    prefix = client.get(url + "/timeline").json()
    assert len(prefix["points"]) == 2 < len(route["waypoints"])
    assert client.post(url + "/control", json={"action": "stop"}).is_success
    clock += timedelta(days=1)
    assert client.get(url + "/timeline").json() == prefix
    assert client.get(url + "/report").json()["simulation_timeline"] == prefix


@pytest.mark.parametrize(("digest", "source_time", "device_time", "provenance", "matched"), [
    ("identical", 5, 5, "server_measured", True),
    ("different", 5, 5, "server_measured", False),
    ("identical", None, 5, "server_measured", False),
    ("identical", 5, 9, "server_measured", False),
    ("identical", 5, None, "server_measured", False),
    ("identical", 6, 5, "server_measured", False),
    ("identical", 5, 5, "simulated", False),
])
def test_twin_comparison_requires_matching_route_evidence(digest, source_time, device_time, provenance, matched):
    from types import SimpleNamespace
    from app.services.road_test.twin_playback import compare

    observation = SimpleNamespace(metric="dl_throughput_mbps", value=50, time_s=5,
                                  provenance=provenance, source_frame_time_s=source_time,
                                  device_playback_time_s=device_time)
    result = compare({"scenario_sha256": "identical"}, {"scenario_sha256": digest},
                     [{"source_frame_time_s": 5, "dl_throughput_mbps": 60}], [observation])
    assert result["formal_kpi"] is False and result["comparable"] is matched
    assert result["differences"] == ([{"source_frame_time_s": 5, "delta_dl_throughput_mbps": 10}] if matched else [])
