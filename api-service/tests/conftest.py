"""
Pytest Configuration and Fixtures

Shared test fixtures for integration tests
"""

import os
import tempfile

# ⭐ 必须在 `from app.main import app` **之前** —— `settings` 是模块级单例，
#    导入那一刻就把 `.env` 读定了，之后再改环境变量没用。
#
# 为什么要这条：`.env` 里 `USE_MOCK_INSTRUMENTS=false`（生产就该这样），
# 而 conftest 此前不做任何隔离，于是 `TestClient(app)` 触发 lifespan →
# HAL 以 **REAL 模式**初始化 → 真去连驱动默认 IP（`propsim_f64.py` 的
# `192.168.100.21`、`uxm_base_station.py` 的 `192.168.100.10`、
# `bootstrap/instruments.py` 的 `TCPIP0::192.168.100.26::inst0::INSTR` 等）。
#
# 两个后果，2026-08-07 都真的发生了：
#   ① 平时这些地址不通、连接秒失败，测试照过；本机 Clash TUN 接管该网段后
#      连接不再快速失败而是挂住等超时 —— 全量测试跑不完（实测挂死 11m47s，
#      CPU 0.3%，lsof 抓到 198.18.0.1:57661->192.168.100.27:sunrpc）。
#      内审硬门要全量输出，那道门也跟着落空。
#   ② **在现场机上跑 pytest 会真的把 F64 拽进 Remote**（F64 收到第一条 ATE
#      命令即进 Remote），测试本身变成一次未经批准的仪器操作。
#
# 用 setdefault 不覆盖调用方已经给的值：要在测试里跑 real，
# 显式 `USE_MOCK_INSTRUMENTS=false pytest ...` 即可。
# G17 门（test_rule_gates.py）盯着这行的存在与**位置**。
os.environ.setdefault("USE_MOCK_INSTRUMENTS", "true")

# P2-39：pytest 不能继承调用方的运行日志目录。app.main 在导入时就初始化全部
# TimedRotatingFileHandler，所以必须在导入前无条件换源；setdefault 会允许测试进程
# 继续打开并轮转用户的历史仪器证据。模块级引用让目录覆盖完整 pytest 进程生命周期。
_PYTEST_LOG_ROOT = tempfile.TemporaryDirectory(prefix="meta3d-pytest-logs-")
os.environ["LOG_DIR"] = _PYTEST_LOG_ROOT.name

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
def _suite_isolate_execution_contextvar():
    """P2-35：套件级隔离 —— 每条测试结束后把 ``current_execution_id``
    恢复到该测试进入时的值。

    为什么必须有：它是**进程级** ContextVar，主线程同步代码里任何
    ``set(...)`` 不还原就永久泄漏给之后收集到的所有测试。生产路径不漏
    （AuditMiddleware 最外层 token finally reset；后台任务在 context 副本里），
    但测试**直调**带 set 的生产函数时没有那层兜底 —— 实证：
    ``test_mimo_ota_report_verified_backcompat`` 主线程直调
    ``VrtExecutionService.stop/complete`` → ``get()`` 内 set，泄漏的 UUID
    让字母序更靠后的 ``test_p1_36_execution_id::
    test_no_execution_means_default_not_empty``（"无关日志行应为 -"）
    在全量顺序下必失败；47C 的 ``_execution`` 帮手同形态。

    做法：进入时 ``set(get("-"))`` 拿 token，teardown ``reset(token)`` ——
    语义 = 恢复进入时的值，不硬写 "-"，不改变任何测试进入时看到的世界。
    conftest 的 autouse 在最外层包住各文件自己的 fixture（如 p2_29 的
    文件级自净），嵌套 set/reset 严格配对，无冲突；async 测试的 set 落在
    Task 的 context 副本里，本 fixture 对其无感也无害。

    行为门在 ``tests/test_p2_35_contextvar_isolation.py``：把本 fixture
    摘掉/改坏，那对 a/b 测试当场红（变异已实跑）。
    """
    from app.core.logging_config import current_execution_id

    token = current_execution_id.set(current_execution_id.get("-"))
    try:
        yield
    finally:
        current_execution_id.reset(token)


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
