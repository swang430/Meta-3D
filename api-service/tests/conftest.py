"""
Pytest Configuration and Fixtures

Shared test fixtures for integration tests
"""

import pytest
from fastapi.testclient import TestClient
from typing import Generator, Dict, Any

from app.main import app
from tests.test_data import get_correct_scenario_data


# ===== FastAPI Test Client =====

@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """
    Create a TestClient for the FastAPI application

    Scope: module - one client per test module for efficiency
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def client_func() -> Generator[TestClient, None, None]:
    """
    Create a fresh TestClient for each test function

    Use this when you need isolated state per test
    """
    with TestClient(app) as test_client:
        yield test_client


# ===== Sample Test Data =====

@pytest.fixture
def sample_scenario_data() -> Dict[str, Any]:
    """Sample road test scenario data for testing - uses correct schema"""
    return get_correct_scenario_data()


@pytest.fixture
def sample_execution_data() -> Dict[str, Any]:
    """Sample test execution data"""
    return {
        "mode": "digital_twin",
        "scenario_id": "test-scenario-001",
        "config": {
            "acceleration_factor": 10.0,
            "enable_metrics_streaming": True
        },
        "notes": "Integration test execution"
    }


@pytest.fixture
def sample_topology_data() -> Dict[str, Any]:
    """Sample network topology data for conducted mode"""
    return {
        "name": "Test Topology - 2x2 MIMO",
        "description": "Test topology for integration testing",
        "topology_type": "MIMO_2x2",
        "base_station": {
            "device_id": "bs-001",
            "device_type": "base_station",
            "name": "Test gNB",
            "model": "Keysight E7515B",
            "tx_ports": 2,
            "max_bandwidth_mhz": 100.0,
            "ip_address": "192.168.1.100",
            "control_port": 5025
        },
        "channel_emulator": {
            "device_id": "ce-001",
            "device_type": "channel_emulator",
            "name": "Test Fading Emulator",
            "model": "Keysight PROPSIM F64",
            "input_ports": 2,
            "output_ports": 2,
            "max_taps": 500,
            "max_doppler_hz": 10000.0,
            "ip_address": "192.168.1.101",
            "control_port": 5026
        },
        "dut": {
            "device_id": "dut-001",
            "device_type": "dut",
            "name": "Test UE",
            "model": "Generic 5G Device",
            "antenna_ports": 2,
            "platform": "Qualcomm SDM865",
            "control_interface": "adb"
        },
        "connections": [
            {
                "connection_id": "conn-bs-ce-1",
                "source_device_id": "bs-001",
                "source_port": 1,
                "target_device_id": "ce-001",
                "target_port": 1,
                "cable_type": "LMR-400",
                "cable_length_m": 2.0,
                "loss_db": 0.5
            },
            {
                "connection_id": "conn-bs-ce-2",
                "source_device_id": "bs-001",
                "source_port": 2,
                "target_device_id": "ce-001",
                "target_port": 2,
                "cable_type": "LMR-400",
                "cable_length_m": 2.0,
                "loss_db": 0.5
            },
            {
                "connection_id": "conn-ce-dut-1",
                "source_device_id": "ce-001",
                "source_port": 1,
                "target_device_id": "dut-001",
                "target_port": 1,
                "cable_type": "LMR-400",
                "cable_length_m": 1.0,
                "loss_db": 0.3
            },
            {
                "connection_id": "conn-ce-dut-2",
                "source_device_id": "ce-001",
                "source_port": 2,
                "target_device_id": "dut-001",
                "target_port": 2,
                "cable_type": "LMR-400",
                "cable_length_m": 1.0,
                "loss_db": 0.3
            }
        ]
    }


# ===== Cleanup Fixtures =====

@pytest.fixture(autouse=True)
def reset_in_memory_storage():
    """
    Reset in-memory storage before each test

    This fixture runs automatically before each test function
    """
    # Import the in-memory storage from road_test API
    import app.api.road_test as road_test_module

    # Clear all data
    road_test_module._custom_scenarios.clear()
    road_test_module._executions.clear()
    road_test_module._topologies.clear()
    road_test_module._execution_status.clear()
    road_test_module._execution_metrics.clear()

    # Note: Standard scenarios are loaded from scenario_library.py on demand
    # No need to repopulate here

    yield

    # Cleanup after test (optional)
    pass
