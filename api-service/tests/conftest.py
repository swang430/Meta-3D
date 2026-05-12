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
def _isolate_dependency_overrides():
    """Per-test snapshot+restore of ``app.dependency_overrides``.

    Several test modules install FastAPI dependency overrides (typically
    to swap ``get_db`` with a SQLite test session). Historically some did
    this at module level, which meant pytest's collection order
    determined which override was "active" — the last imported module
    won, and earlier modules ran their tests against the wrong DB,
    surfacing as confusing ``no such table`` errors.

    This fixture is the safety net: every test starts with whatever
    overrides are currently installed, runs, then we restore that exact
    state on teardown. Combined with each polluting test module
    converting its module-level mutation into a module-scoped autouse
    fixture (which installs/uninstalls its own override correctly), this
    eliminates cross-module bleeding.

    The fixture is intentionally cheap: a single dict copy. It's safe
    even for tests that don't touch overrides.
    """
    saved = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


@pytest.fixture(autouse=True)
def reset_in_memory_storage():
    """
    Reset in-memory storage before each test

    This fixture runs automatically before each test function
    """
    # Import the in-memory storage from road_test API. After the road_test
    # refactor moved scenarios to the DB, several of these attrs no longer
    # exist; clear them defensively so unrelated test files still run.
    import app.api.road_test as road_test_module

    for attr in (
        "_custom_scenarios", "_executions", "_topologies",
        "_execution_status", "_execution_metrics",
    ):
        store = getattr(road_test_module, attr, None)
        if store is not None and hasattr(store, "clear"):
            store.clear()

    # Note: Standard scenarios are loaded from scenario_library.py on demand
    # No need to repopulate here

    yield

    # Cleanup after test (optional)
    pass
