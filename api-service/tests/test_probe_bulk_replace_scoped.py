"""PUT /probes/bulk 按**单个暗室作用域**替换 (不再全局清空) + 缺 chamber 时 fail-loud。

回归防护: 之前 bulk replace 无条件 `db.query(Probe).delete()` 删光所有暗室的探头
(GUI「加载默认布局」误触 → CAICT-FS/3GPP 等暗室探头全没)。现要求 chamber_config_id,
只作用于该暗室。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.models.chamber import ChamberConfiguration
from app.models.probe import Probe

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _setup():
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(engine)


client = TestClient(app)


def _chamber(db, name: str) -> ChamberConfiguration:
    c = ChamberConfiguration(name=name, chamber_type="custom", chamber_radius_m=4.0)
    db.add(c)
    db.flush()
    return c


def _probe(chamber_id, n: int) -> Probe:
    return Probe(
        chamber_config_id=chamber_id, probe_number=n, name=f"P{n}", ring=1,
        polarization="V", position={"azimuth": 0.0, "elevation": 0.0, "radius": 4.0},
    )


def _payload(n: int) -> dict:
    return {
        "probe_number": n, "name": f"New{n}", "ring": 1, "polarization": "V",
        "position": {"azimuth": 0.0, "elevation": 0.0, "radius": 4.0},
    }


def test_bulk_replace_is_chamber_scoped():
    db = TestingSessionLocal()
    a, b = _chamber(db, "A"), _chamber(db, "B")
    db.add_all([_probe(a.id, 1), _probe(a.id, 2), _probe(b.id, 1), _probe(b.id, 2)])
    db.commit()
    a_id, b_id = a.id, b.id  # session 仍开, 读取触发 refresh
    db.close()

    resp = client.put(
        "/api/v1/probes/bulk",
        json={"chamber_config_id": str(a_id), "probes": [_payload(1), _payload(2), _payload(3)]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] == 2   # 只删 A 原有 2 个
    assert body["created"] == 3

    db = TestingSessionLocal()
    try:
        assert db.query(Probe).filter(Probe.chamber_config_id == a_id).count() == 3  # A 被替换
        assert db.query(Probe).filter(Probe.chamber_config_id == b_id).count() == 2  # B 不受影响
        # 新探头确实归属 A
        assert all(p.chamber_config_id == a_id for p in db.query(Probe).filter(Probe.chamber_config_id == a_id))
    finally:
        db.close()


def test_bulk_replace_without_chamber_rejected():
    """缺 chamber_config_id → 422 (schema 必填), 拒绝全局替换 (防数据丢失炸弹)。"""
    db = TestingSessionLocal()
    a = _chamber(db, "A")
    db.add_all([_probe(a.id, 1), _probe(a.id, 2)])
    db.commit()
    a_id = a.id
    db.close()

    resp = client.put("/api/v1/probes/bulk", json={"probes": [_payload(1)]})
    assert resp.status_code == 422  # Pydantic 必填校验, 在进 handler 前就拦下
    assert "chamber_config_id" in resp.text

    # 原有探头未被动 (没有发生全局删除)
    db = TestingSessionLocal()
    try:
        assert db.query(Probe).filter(Probe.chamber_config_id == a_id).count() == 2
    finally:
        db.close()
