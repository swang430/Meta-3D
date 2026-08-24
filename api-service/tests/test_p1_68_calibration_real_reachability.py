"""P1-68 行为门：校准 API real 可达性 + phase mock 口 fail-loud（Schema Review B-1/B-2）。

守什么：
1. rf-chain uplink/downlink 与 multi-frequency 三个 POST 端点必须把
   `request.use_mock` 透传给 service 构造 —— 原硬编码 True 使 real 分支
   API 不可达（变异「换回 use_mock=True」在门 1/2 红）；
2. 缺省行为向后兼容：不带 use_mock 字段 → True（现有调用方行为不变）；
3. 两个 phase mock 生成口（/calibration/phase/calibrate 与
   /calibration/probe/phase/start）409 fail-loud 且**零落库**；
4. rf-chain GET 读路径回归不受影响。

真实生效端：FastAPI TestClient 走真实路由 + monkeypatch service 构造捕获
实参 —— 不测「schema 里有字段」，测「字段真的到了 service」。
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app

# 照 test_path_loss_calibration.py 骨架：module 级 SQLite override，
# 防止绕过隔离直连生产 PG。
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(bind=_engine)


def _override_get_db():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True, scope="module")
def _install_get_db_override():
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _tables():
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


client = TestClient(app)


def _capture_service(monkeypatch, module_path, cls_name, captured):
    """替换 service 类为构造参数捕获桩（calibrate_* 返回最小假结果）。"""
    import importlib
    api_mod = importlib.import_module("app.api.path_loss_calibration")

    class _Stub:
        def __init__(self, db, use_mock=True):
            captured.append(use_mock)
            self.use_mock = use_mock

        async def calibrate_uplink(self, **kw):
            return _FakeResult()

        async def calibrate_downlink(self, **kw):
            return _FakeResult()

        async def calibrate_multi_frequency(self, **kw):
            return _FakeResult()

        async def calibrate_frequency_sweep(self, **kw):
            return _FakeResult()

        def get_latest_uplink_calibration(self, *a, **kw):
            return None

        def get_latest_downlink_calibration(self, *a, **kw):
            return None

    monkeypatch.setattr(api_mod, cls_name, _Stub)
    return _Stub


class _FakeResult:
    id = uuid.uuid4()
    warnings = []
    success = True
    error_message = None
    message = 'stub result' 
    data = {
        "calibration_id": str(uuid.uuid4()),
        "calibration_ids": [str(uuid.uuid4())],
    }

    def to_response(self):
        from app.schemas.probe_calibration import (
            CalibrationJobResponse, CalibrationJobStatus,
        )
        return CalibrationJobResponse(
            calibration_job_id=self.id,
            status=CalibrationJobStatus.COMPLETED,
        )


def _chamber():
    """建一个 Type D 暗室（有 LNA）供 rf-chain 端点通过前置校验。"""
    from app.models.chamber import ChamberType, create_chamber_from_preset
    db = _TestingSessionLocal()
    try:
        ch = create_chamber_from_preset(
            ChamberType.TYPE_D.value, name=f"p1-68-{uuid.uuid4().hex[:8]}")
        db.add(ch)
        db.commit()
        db.refresh(ch)
        return str(ch.id)
    finally:
        db.close()


def _chain_payload(chamber_id, chain_type="uplink", **extra):
    body = {
        "chamber_id": chamber_id, "chain_type": chain_type,
        "frequency_mhz": 3500.0, "calibrated_by": "p1-68-gate",
    }
    body.update(extra)
    return body


class TestUseMockReachesService:
    """门 1/2：use_mock 从请求真的到达 service 构造。"""

    @pytest.mark.parametrize("endpoint,chain", [
        ("/api/v1/calibration/path-loss/rf-chain/uplink", "uplink"),
        ("/api/v1/calibration/path-loss/rf-chain/downlink", "downlink"),
    ])
    def test_rf_chain_passes_explicit_false(self, monkeypatch,
                                            endpoint, chain):
        captured = []
        _capture_service(monkeypatch, "app.api.path_loss_calibration",
                         "RFChainCalibrationService", captured)
        chamber_id = _chamber()
        r = client.post(endpoint, json=_chain_payload(
            chamber_id, chain, use_mock=False))
        assert r.status_code == 200, r.text
        assert captured == [False], "request.use_mock=False 未到达 service 构造"

    def test_rf_chain_defaults_to_mock_for_backward_compat(self, monkeypatch):
        captured = []
        _capture_service(monkeypatch, "app.api.path_loss_calibration",
                         "RFChainCalibrationService", captured)
        chamber_id = _chamber()
        r = client.post("/api/v1/calibration/path-loss/rf-chain/uplink",
                        json=_chain_payload(chamber_id))
        assert r.status_code == 200, r.text
        assert captured == [True], "缺省必须是 True（向后兼容）"

    def test_multi_frequency_passes_explicit_false(self, monkeypatch):
        captured = []
        _capture_service(monkeypatch, "app.api.path_loss_calibration",
                         "MultiFrequencyPathLossService", captured)
        chamber_id = _chamber()
        r = client.post(
            "/api/v1/calibration/path-loss/multi-frequency/start",
            json={
                "chamber_id": chamber_id, "probe_ids": [0],
                "polarization": "V",
                "freq_start_mhz": 3400.0, "freq_stop_mhz": 3500.0,
                "freq_step_mhz": 100.0,
                "sgh_model": "SGH-01", "sgh_gain_dbi": 10.0,
                "calibrated_by": "p1-68-gate", "use_mock": False,
            },
        )
        # 桩未实现 calibrate_frequency_sweep 时端点 500——判据只看构造实参
        assert captured == [False], "multi-frequency 未透传 use_mock"

    def test_multi_frequency_defaults_to_mock_for_backward_compat(self, monkeypatch):
        """内审 F2：缺省兼容承诺三端点都要有门 —— schema default 改 False 在这红。"""
        captured = []
        _capture_service(monkeypatch, "app.api.path_loss_calibration",
                         "MultiFrequencyPathLossService", captured)
        chamber_id = _chamber()
        client.post(
            "/api/v1/calibration/path-loss/multi-frequency/start",
            json={
                "chamber_id": chamber_id, "probe_ids": [0],
                "polarization": "V",
                "freq_start_mhz": 3400.0, "freq_stop_mhz": 3500.0,
                "freq_step_mhz": 100.0,
                "sgh_model": "SGH-01", "sgh_gain_dbi": 10.0,
                "calibrated_by": "p1-68-gate",
            },
        )
        assert captured == [True], "multi-frequency 缺省必须 True（向后兼容）"


class TestPhaseEntriesFailLoud:
    """门 3：两个 phase mock 生成口 409 且零落库。"""

    def _phase_row_count(self):
        from app.models.probe_calibration import ProbePhaseCalibration
        db = _TestingSessionLocal()
        try:
            return db.query(ProbePhaseCalibration).count()
        finally:
            db.close()

    def test_probe_phase_start_409_and_no_rows(self):
        before = self._phase_row_count()
        r = client.post("/api/v1/calibration/probe/phase/start", json={
            "chamber_id": str(uuid.uuid4()),
            "probe_ids": [0, 1], "reference_probe_id": 0,
            "frequency_range": {"start_mhz": 3400, "stop_mhz": 3500,
                                "step_mhz": 50},
            "polarizations": ["V"], "calibrated_by": "p1-68-gate",
        })
        assert r.status_code == 409, r.text
        assert "PFS 不需要相位校准" in r.json()["detail"]
        assert "import-csv" in r.json()["detail"], "409 必须指路合法导入口"
        assert self._phase_row_count() == before, "409 口不得落库"

    def test_phase_calibrate_endpoint_409(self):
        r = client.post(
            "/api/v1/calibration/phase/calibrate",
            params={"chamber_id": str(uuid.uuid4())},
        )
        assert r.status_code == 409, r.text
        assert "PFS 不需要相位校准" in r.json()["detail"]


class TestGetPathsRegression:
    """门 4：rf-chain GET 读路径回归（404 于空库而非 500）。"""

    def test_get_uplink_calibration_still_works(self):
        r = client.get(
            f"/api/v1/calibration/path-loss/rf-chain/uplink/{uuid.uuid4()}")
        assert r.status_code == 404, r.text
