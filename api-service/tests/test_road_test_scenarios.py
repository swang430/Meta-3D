"""
Integration Tests for Virtual Road Test - Scenario Management

Tests scenario CRUD operations and filtering

Test isolation (P3-8 follow-up): each test runs against an isolated
in-memory SQLite DB instead of the shared dev Postgres. Pre-isolation
the dev PG accumulated 50+ VRT TestCases from prior dev/test runs,
breaking assertions like ``len(scenarios) == 5`` and ``all(s["category"]
== "standard" for s in scenarios)``. Same isolation pattern as
``test_uxm_topology_profile.py`` / ``test_plan_topology_override.py``.
"""

import pytest
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


@pytest.mark.integration
@pytest.mark.road_test
@pytest.mark.api
class TestScenarioSummaryIntegrity:
    """摘要构造回归门：不丢行、不刷 ERROR、channel_model 从 channel_snapshots 取值。

    背景：Environment 重构后没有 channel_model 字段（真值挪进
    channel_snapshots[].standard_model），摘要构造曾继续读旧字段，导致每个
    带 environment 的场景抛 AttributeError → 整行退化成零时长摘要并每次
    列表加载刷一条 ERROR。
    """

    def _create_snapshot_scenario(self, client: TestClient, sample_scenario_data) -> str:
        data = {**sample_scenario_data}
        data["name"] = "Snapshot Channel Scenario"
        data["environment"] = {
            "type": "urban_street",
            "channel_snapshots": [
                {
                    "timestamp_s": 0.0,
                    "duration_s": 30.0,
                    "channel_type": "3GPP",
                    "standard_model": "CDL-C",
                }
            ],
        }
        resp = client.post("/api/v1/road-test/scenarios", json=data)
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]

    def test_channel_model_sourced_from_first_snapshot(
        self, client: TestClient, sample_scenario_data
    ):
        """行为门：带标准模型快照的场景，摘要 channel_model = 快照 standard_model，行不退化"""
        sid = self._create_snapshot_scenario(client, sample_scenario_data)

        rows = client.get("/api/v1/road-test/scenarios").json()
        row = next(x for x in rows if x["id"] == sid)
        assert row["channel_model"] == "CDL-C"
        # 行保真：时长/距离/网络字段不因摘要构造问题被清零
        assert row["duration_s"] == pytest.approx(33.0)
        assert row["distance_m"] == pytest.approx(1111.0)
        assert row["network_type"] == "5G_NR"

    def test_standard_scenarios_not_degraded(self, client: TestClient):
        """行为门：标准库 5 场景快照模型按 id 对位 (P2-20 转正后)，且行不退化（时长>0）"""
        rows = client.get("/api/v1/road-test/scenarios?source=standard").json()
        assert len(rows) == 5
        # P2-20: 标准库死 kwarg 已转正为 channel_snapshots — 按 id 对位断言
        # 具体模型值 (兑现 #253 时留下的"修好后应改为期待具体模型值"注释)
        expected_models = {
            "3gpp-uma-handover-001": "UMa",
            "3gpp-umi-beam-tracking-001": "UMi",
            "highway-high-speed-001": "RMa",
            "tunnel-entry-exit-001": "UMa",
            "urban-canyon-001": "UMi",
        }
        for row in rows:
            assert row["duration_s"] > 0, f"{row['id']} 摘要被降级成零时长行"
            assert row["channel_model"] == expected_models[row["id"]], (
                f"{row['id']} 摘要 channel_model 与快照真值不符")

    def test_summary_count_equals_scenario_count_and_no_error_logs(
        self, client: TestClient, sample_scenario_data, caplog
    ):
        """不变量门：场景数 == 摘要数（不许静默消失），且列表构造零 ERROR 日志"""
        import logging as _logging

        sid = self._create_snapshot_scenario(client, sample_scenario_data)

        # alembic fileConfig 可能已把该 logger 置 disabled，先复位，否则
        # "零 ERROR"断言会假绿；测完复原原值，别让复位泄漏成全局副作用
        _rt_logger = _logging.getLogger("app.api.road_test")
        _was_disabled = _rt_logger.disabled
        _rt_logger.disabled = False
        try:
            with caplog.at_level(_logging.ERROR, logger="app.api.road_test"):
                resp = client.get("/api/v1/road-test/scenarios")
        finally:
            _rt_logger.disabled = _was_disabled

        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 6  # 5 standard + 1 custom
        assert sid in {x["id"] for x in rows}
        errors = [r.getMessage() for r in caplog.records if r.levelno >= _logging.ERROR]
        assert errors == []

    def test_broken_scenario_still_listed_degraded(
        self, client: TestClient, monkeypatch
    ):
        """降级出行门：单行衍生字段计算爆炸 → 该行带基础字段出行，不消失、不 500"""
        from app.api import road_test as rt
        from app.schemas.road_test import ScenarioCategory, ScenarioSource

        class _BoomScenario:
            """基础字段齐全、route 一碰就爆的坏数据行替身"""
            id = "boom-1"
            name = "Broken Scenario"
            category = ScenarioCategory.FUNCTIONAL
            source = ScenarioSource.STANDARD
            tags = ["boom"]
            description = None
            created_at = None
            author = None

            @property
            def route(self):
                raise RuntimeError("boom: derived-field computation exploded")

        real_get_all = rt.get_all_scenarios
        monkeypatch.setattr(
            rt, "get_all_scenarios", lambda: real_get_all() + [_BoomScenario()]
        )

        resp = client.get("/api/v1/road-test/scenarios")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 6  # 5 standard + 1 boom：坏行降级出行，不消失
        boom = next(x for x in rows if x["id"] == "boom-1")
        assert boom["name"] == "Broken Scenario"
        assert boom["duration_s"] == 0
        assert boom["channel_model"] is None

    def test_bad_custom_row_skipped_loudly_others_survive(
        self, client: TestClient, sample_scenario_data, caplog
    ):
        """P2-20 投影层降级门 (内审 F1): 单行坏 configuration 过不了投影 →
        跳该行 + ERROR 报数, 好行与标准行照常出行, 不再 500 全列表。
        变异: _list_custom_scenarios 撤回列表推导 → 本用例 500 红。"""
        import logging as _logging
        from app.api.road_test import router  # noqa: F401 — 确保模块已载

        good_id = self._create_snapshot_scenario(client, sample_scenario_data)

        # 直接把一行 VRT TestCase 的 configuration 改坏 (route 缺失 —
        # VirtualRoadTestConfig.model_validate 必炸), 模拟旧 schema 遗留行
        data = {**sample_scenario_data}
        data["name"] = "即将变坏的行"
        bad_id = client.post("/api/v1/road-test/scenarios", json=data).json()["id"]
        from app.models.test_plan import TestCase
        db = _TestingSessionLocal()  # 用本文件的隔离测试库, 不碰生产 SessionLocal
        row = db.get(TestCase, __import__("uuid").UUID(bad_id))
        assert row is not None, "坏行没建成"
        row.configuration = {"vrt": "totally-broken-shape"}
        db.commit()
        db.close()

        with caplog.at_level(_logging.ERROR):
            resp = client.get("/api/v1/road-test/scenarios")
        assert resp.status_code == 200  # 不再 500 全列表
        ids = [x["id"] for x in resp.json()]
        assert good_id in ids, "好行被连坐"
        assert bad_id not in ids, "坏行不该出行 (投影不了, 降级=跳行)"
        # 跳行是响的: 逐行 ERROR + 汇总报数
        assert any("投影场景失败" in r.message for r in caplog.records)
        assert any("跳过 1 行坏配置" in r.message for r in caplog.records)
