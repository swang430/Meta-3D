"""
Integration Tests for Virtual Road Test - Scenario Management

Tests scenario CRUD operations and filtering
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestScenarioList:
    """Test scenario listing and filtering"""

    def test_list_all_scenarios(self, client: TestClient):
        """Test listing all scenarios"""
        response = client.get("/api/v1/road-test/scenarios")

        assert response.status_code == 200
        scenarios = response.json()
        assert isinstance(scenarios, list)
        assert len(scenarios) == 5  # 5 standard scenarios from library

        # Verify scenario structure
        scenario = scenarios[0]
        assert "id" in scenario
        assert "name" in scenario
        assert "category" in scenario
        assert "source" in scenario
        assert "tags" in scenario
        assert "duration_s" in scenario
        assert "distance_m" in scenario

    def test_filter_by_category(self, client: TestClient):
        """Test filtering scenarios by category"""
        response = client.get("/api/v1/road-test/scenarios?category=standard")

        assert response.status_code == 200
        scenarios = response.json()
        assert all(s["category"] == "standard" for s in scenarios)

    def test_filter_by_source(self, client: TestClient):
        """Test filtering scenarios by source"""
        response = client.get("/api/v1/road-test/scenarios?source=standard")

        assert response.status_code == 200
        scenarios = response.json()
        assert all(s["source"] == "standard" for s in scenarios)

    def test_filter_by_tags(self, client: TestClient):
        """Test filtering scenarios by tags"""
        response = client.get("/api/v1/road-test/scenarios?tags=3GPP")  # Tags are case-sensitive

        assert response.status_code == 200
        scenarios = response.json()
        # Should find at least the 3GPP standard scenarios
        assert len(scenarios) >= 2

    def test_filter_multiple_criteria(self, client: TestClient):
        """Test filtering with multiple criteria"""
        response = client.get(
            "/api/v1/road-test/scenarios?category=standard&source=standard"
        )

        assert response.status_code == 200
        scenarios = response.json()
        assert all(
            s["category"] == "standard" and s["source"] == "standard"
            for s in scenarios
        )


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestScenarioDetail:
    """Test scenario detail retrieval"""

    def test_get_scenario_by_id(self, client: TestClient):
        """Test retrieving scenario by ID"""
        # First get list to find a valid ID
        list_response = client.get("/api/v1/road-test/scenarios")
        scenarios = list_response.json()
        scenario_id = scenarios[0]["id"]

        # Get detailed scenario
        response = client.get(f"/api/v1/road-test/scenarios/{scenario_id}")

        assert response.status_code == 200
        scenario = response.json()

        # Verify complete scenario structure
        assert scenario["id"] == scenario_id
        assert "name" in scenario
        assert "network" in scenario
        assert "base_stations" in scenario
        assert "route" in scenario
        assert "environment" in scenario
        assert "traffic" in scenario
        assert "events" in scenario
        assert "kpi_definitions" in scenario

        # Verify network config
        assert "type" in scenario["network"]
        assert "band" in scenario["network"]
        assert "bandwidth_mhz" in scenario["network"]

        # Verify route structure
        assert "type" in scenario["route"]  # Field is 'type', not 'route_type'
        assert "waypoints" in scenario["route"]
        assert len(scenario["route"]["waypoints"]) >= 2

    def test_get_nonexistent_scenario(self, client: TestClient):
        """Test retrieving non-existent scenario"""
        response = client.get("/api/v1/road-test/scenarios/invalid-id-999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestScenarioCreate:
    """Test scenario creation"""

    def test_create_scenario(self, client: TestClient, sample_scenario_data):
        """Test creating a new scenario"""
        response = client.post(
            "/api/v1/road-test/scenarios",
            json=sample_scenario_data
        )

        assert response.status_code == 201
        created_scenario = response.json()

        # Verify created scenario
        assert "id" in created_scenario
        assert created_scenario["name"] == sample_scenario_data["name"]
        assert created_scenario["category"] == sample_scenario_data["category"]
        assert created_scenario["source"] == "custom"  # Should be set to custom

        # Verify it appears in list
        list_response = client.get("/api/v1/road-test/scenarios")
        scenarios = list_response.json()
        assert any(s["id"] == created_scenario["id"] for s in scenarios)

    def test_create_scenario_invalid_data(self, client: TestClient):
        """Test creating scenario with invalid data"""
        invalid_data = {
            "name": "Invalid Scenario",
            # Missing required fields
        }

        response = client.post(
            "/api/v1/road-test/scenarios",
            json=invalid_data
        )

        assert response.status_code == 422  # Validation error

    def test_create_scenario_with_minimal_data(self, client: TestClient):
        """Test creating scenario with minimal required data"""
        from tests.test_data import get_minimal_scenario_data

        minimal_data = get_minimal_scenario_data()

        response = client.post(
            "/api/v1/road-test/scenarios",
            json=minimal_data
        )

        assert response.status_code == 201


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestScenarioUpdate:
    """Test scenario update operations"""

    def test_update_scenario(self, client: TestClient, sample_scenario_data):
        """Test updating an existing scenario"""
        # Create a scenario first
        create_response = client.post(
            "/api/v1/road-test/scenarios",
            json=sample_scenario_data
        )
        scenario_id = create_response.json()["id"]

        # Update the scenario
        update_data = {
            "name": "Updated Test Scenario",
            "tags": ["test", "updated"]
        }

        response = client.put(
            f"/api/v1/road-test/scenarios/{scenario_id}",
            json=update_data
        )

        assert response.status_code == 200
        updated_scenario = response.json()
        assert updated_scenario["name"] == "Updated Test Scenario"
        assert "updated" in updated_scenario["tags"]

    def test_update_nonexistent_scenario(self, client: TestClient):
        """Test updating non-existent scenario"""
        update_data = {"name": "Should Fail"}

        response = client.put(
            "/api/v1/road-test/scenarios/invalid-id-999",
            json=update_data
        )

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestScenarioDelete:
    """Test scenario deletion"""

    def test_delete_scenario(self, client: TestClient, sample_scenario_data):
        """Test deleting a scenario"""
        # Create a scenario first
        create_response = client.post(
            "/api/v1/road-test/scenarios",
            json=sample_scenario_data
        )
        scenario_id = create_response.json()["id"]

        # Delete the scenario
        response = client.delete(f"/api/v1/road-test/scenarios/{scenario_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/api/v1/road-test/scenarios/{scenario_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_scenario(self, client: TestClient):
        """Test deleting non-existent scenario"""
        response = client.delete("/api/v1/road-test/scenarios/invalid-id-999")

        assert response.status_code == 404

    def test_delete_standard_scenario(self, client: TestClient):
        """Test deleting a standard scenario (should fail)"""
        # Get a standard scenario ID
        list_response = client.get("/api/v1/road-test/scenarios?source=standard")
        scenarios = list_response.json()

        if scenarios:
            scenario_id = scenarios[0]["id"]
            response = client.delete(f"/api/v1/road-test/scenarios/{scenario_id}")

            # Standard scenarios cannot be deleted - should return 404, 400, or 403
            assert response.status_code in [404, 400, 403]
