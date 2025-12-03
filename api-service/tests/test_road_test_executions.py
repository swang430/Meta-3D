"""
Integration Tests for Virtual Road Test - Test Execution

Tests execution lifecycle: create → start → monitor → stop
"""

import pytest
import time
from fastapi.testclient import TestClient


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
