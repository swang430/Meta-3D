"""DELETE /chambers/{id} 加固: 连带删探头+拓扑, 拦预设/激活/被 lab 引用。

回归防护: 旧实现 db.delete(chamber) 直删 → 遇 switch_topologies (RESTRICT 外键) 会 500,
且把探头 orphan 成 chamber_config_id=NULL。现改为单事务内先删拓扑+探头再删暗室, 并对
预设(409)/激活(400)/被 lab 引用(409) 拦截。
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.models.chamber import ChamberConfiguration
from app.models.probe import Probe
from app.models.switch_topology import SwitchTopology
from app.models.lab_profile import LabProfile
from app.models.probe_calibration import ProbeCalibrationValidity

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


def _chamber(db, name, *, active=False, preset=False):
    c = ChamberConfiguration(
        name=name, chamber_type="custom", chamber_radius_m=4.0,
        is_active=active, is_system_preset=preset,
    )
    db.add(c)
    db.flush()
    return c


def _probe(chamber_id, n):
    return Probe(
        chamber_config_id=chamber_id, probe_number=n, name=f"P{n}", ring=1,
        polarization="V", position={"azimuth": 0.0, "elevation": 0.0, "radius": 4.0},
    )


def _topology(chamber_id, name):
    return SwitchTopology(
        switch_category_id=uuid.uuid4(), chamber_id=chamber_id, name=name,
        nodes=[], connections=[], operating_modes=[],
    )


def test_delete_cascades_probes_and_topologies():
    db = TestingSessionLocal()
    c = _chamber(db, "ToDelete")
    db.add_all([_probe(c.id, 1), _probe(c.id, 2), _topology(c.id, "topo1")])
    db.commit()
    cid = c.id
    db.close()

    resp = client.delete(f"/api/v1/chambers/{cid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted_probes"] == 2
    assert body["deleted_topologies"] == 1

    db = TestingSessionLocal()
    try:
        assert db.query(ChamberConfiguration).filter_by(id=cid).first() is None
        assert db.query(Probe).filter(Probe.chamber_config_id == cid).count() == 0
        assert db.query(SwitchTopology).filter(SwitchTopology.chamber_id == cid).count() == 0
        # 没有把探头 orphan 成 NULL
        assert db.query(Probe).filter(Probe.chamber_config_id.is_(None)).count() == 0
    finally:
        db.close()


def test_legacy_active_flag_does_not_block_delete():
    db = TestingSessionLocal()
    c = _chamber(db, "ActiveOne", active=True)
    db.commit()
    cid = c.id
    db.close()
    resp = client.delete(f"/api/v1/chambers/{cid}")
    assert resp.status_code == 200


def test_delete_preset_blocked():
    db = TestingSessionLocal()
    c = _chamber(db, "PresetOne", preset=True)
    db.commit()
    cid = c.id
    db.close()
    resp = client.delete(f"/api/v1/chambers/{cid}")
    assert resp.status_code == 409


def test_delete_lab_referenced_blocked():
    db = TestingSessionLocal()
    c = _chamber(db, "LabBound")
    db.flush()
    db.add(LabProfile(name="lab-x", chamber_config_id=c.id, is_active=False))
    db.commit()
    cid = c.id
    db.close()

    resp = client.delete(f"/api/v1/chambers/{cid}")
    assert resp.status_code == 409
    assert "lab" in resp.text.lower() or "Lab" in resp.text

    db = TestingSessionLocal()
    try:
        assert db.query(ChamberConfiguration).filter_by(id=cid).first() is not None  # 未删
    finally:
        db.close()


def test_delete_chamber_with_calibration_history_is_blocked():
    db = TestingSessionLocal()
    c = _chamber(db, "Calibrated")
    db.flush()
    db.add(ProbeCalibrationValidity(probe_id=3, chamber_id=c.id))
    db.commit()
    cid = c.id
    db.close()

    resp = client.delete(f"/api/v1/chambers/{cid}")

    assert resp.status_code == 409, resp.text
    assert "probe_calibration_validity" in resp.text
    db = TestingSessionLocal()
    try:
        assert db.get(ChamberConfiguration, cid) is not None
        assert db.query(ProbeCalibrationValidity).filter_by(chamber_id=cid).count() == 1
    finally:
        db.close()
