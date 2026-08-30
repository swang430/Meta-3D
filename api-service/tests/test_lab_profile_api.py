"""P2: lab-profile API + RF chain resolution endpoint.

The calibration UI calls GET /lab-profiles to populate the picker, then
GET /lab-profiles/{id}/rf-chains?operating_mode=mimo_ota to render the
preview before the operator hits Start. These tests cover both reads.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.chamber import (
    ChamberType,
    create_chamber_from_preset,
)
from app.models.lab_profile import LabProfile
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.switch_topology import SwitchTopology
from app.models.test_plan import TestExecution
from app.hal.cmw500_base_station import RealCmw500Driver
from app.services import instrument_hal_service
from app.services.base_station_adapter_profile import freeze_base_station_adapter_profile


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    # Setting the dep override inside the fixture (not at module scope) avoids
    # collisions with other test modules that also override get_db. Pytest
    # imports every test module first, so module-level overrides clobber each
    # other; per-test scope keeps each file's override pointing at its own engine.
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P2 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="P2-Test-Lab",
        description="Created by test",
        organization="Test Org",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def topology(db, chamber):
    """Active mimo_ota topology with one chain (probe 0 V)."""
    t = SwitchTopology(
        switch_category_id=uuid.uuid4(),
        chamber_id=chamber.id,
        name="P2 Topology",
        nodes=[
            {"id": "ce_b1", "type": "ce_port", "label": "B1.1", "params": {}},
            {"id": "probe_0_v", "type": "probe", "label": "Probe 0 V",
             "params": {"probe_id": 0, "polarization": "V"}},
        ],
        connections=[
            {"id": "conn_p0v", "source": "ce_b1", "target": "probe_0_v",
             "calibrated_loss_db": 0.42, "modes": ["mimo_ota"]},
        ],
        operating_modes=[
            {"id": "mimo_ota", "name": "MIMO OTA", "active_connections": ["conn_p0v"]},
        ],
        is_active=True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestListLabProfiles:
    def test_returns_active_only_by_default(self, db, lab):
        # Inactive lab shouldn't show up.
        inactive = LabProfile(name="Inactive-Lab", is_active=False)
        db.add(inactive)
        db.commit()

        resp = client.get("/api/v1/lab-profiles")
        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()]
        assert "P2-Test-Lab" in names
        assert "Inactive-Lab" not in names

    def test_includes_chamber_name(self, lab, chamber):
        resp = client.get("/api/v1/lab-profiles")
        body = resp.json()
        entry = next((it for it in body if it["id"] == str(lab.id)), None)
        assert entry is not None
        assert entry["chamber_config_id"] == str(chamber.id)
        assert entry["chamber_name"] == chamber.name


class TestGetRFChains:
    def test_resolves_active_mimo_ota_chains(self, lab, topology):
        resp = client.get(
            f"/api/v1/lab-profiles/{lab.id}/rf-chains",
            params={"operating_mode": "mimo_ota"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["lab_name"] == "P2-Test-Lab"
        assert body["topology_name"] == topology.name
        assert len(body["chains"]) == 1
        chain = body["chains"][0]
        assert chain["chain_id"] == "conn_p0v"
        assert chain["probe_id"] == 0
        assert chain["polarization"] == "V"
        assert chain["cable_loss_db"] == 0.42

    def test_unknown_mode_returns_success_false_with_warning(self, lab, topology):
        resp = client.get(
            f"/api/v1/lab-profiles/{lab.id}/rf-chains",
            params={"operating_mode": "trp_only"},
        )
        # Endpoint stays 200 but `success=False` + warnings carry actionable info
        # so the GUI can render an empty-state with "go fix the topology".
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["chains"] == []
        assert any("trp_only" in w for w in body["warnings"])

    def test_unknown_lab_returns_422(self):
        resp = client.get(
            f"/api/v1/lab-profiles/{uuid.uuid4()}/rf-chains",
            params={"operating_mode": "mimo_ota"},
        )
        assert resp.status_code == 422


class TestSyncInstrumentBinding:
    def test_syncs_current_category_configuration_into_existing_lab(
        self, db, lab, monkeypatch
    ):
        category = InstrumentCategory(
            category_key="baseStation",
            category_name="Base Station",
            selected_model_id=None,
            driver_mode="real",
            is_active=True,
        )
        db.add(category)
        db.flush()
        model = InstrumentModel(
            category_id=category.id,
            vendor="R&S",
            model="CMW500",
            capabilities={},
            is_available=True,
        )
        db.add(model)
        db.flush()
        category.selected_model_id = model.id
        db.add(InstrumentConnection(
            category_id=category.id,
            endpoint="TCPIP0::192.168.100.22::inst0::INSTR",
            connection_params={
                "base_station_adapter_profile": {
                    "schema_version": 1,
                    "adapter": "cmw500",
                    "lte_2x2_internal_route": {
                        "pcc_bb_board": "BB1",
                        "rx_connector": "RF1C",
                        "rx_converter": "RX1",
                        "tx1_connector": "RF1C",
                        "tx1_converter": "TX1",
                        "tx2_connector": "RF2C",
                        "tx2_converter": "TX2",
                    },
                },
            },
            base_station_model_presets={
                str(model.id): {
                    "schema_version": 1,
                    "model_id": str(model.id),
                    "endpoint": "TCPIP0::192.168.100.22::inst0::INSTR",
                    "controller": "",
                    "notes": "",
                    "connection_params": {},
                    "base_station_adapter_profile": {
                        "schema_version": 1,
                        "adapter": "cmw500",
                        "lte_2x2_internal_route": {
                            "pcc_bb_board": "BB1",
                            "rx_connector": "RF1C",
                            "rx_converter": "RX1",
                            "tx1_connector": "RF1C",
                            "tx1_converter": "TX1",
                            "tx2_connector": "RF2C",
                            "tx2_converter": "TX2",
                        },
                    },
                },
            },
        ))
        driver = RealCmw500Driver(
            "cmw",
            {"endpoint": "TCPIP0::192.168.100.22::inst0::INSTR"},
        )
        hal = SimpleNamespace(
            drivers={"baseStation": driver},
            last_readiness_report=None,
        )
        monkeypatch.setattr(instrument_hal_service, "_hal_service", hal)
        lab.instrument_bindings = [
            {
                "category_id": str(uuid.uuid4()),
                "instrument_model_id": str(uuid.uuid4()),
                "connection_endpoint": "keep-me",
                "driver_mode": "auto",
                "role": "other",
            },
            {
                "category_id": str(category.id),
                "instrument_model_id": None,
                "connection_endpoint": "stale-endpoint",
                "driver_mode": "auto",
                "role": "primary_baseStation",
            },
        ]
        db.commit()

        response = client.put(
            f"/api/v1/lab-profiles/{lab.id}/instrument-bindings/baseStation/sync-current"
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["binding"] == {
            "category_id": str(category.id),
            "instrument_model_id": str(model.id),
            "connection_endpoint": "TCPIP0::192.168.100.22::inst0::INSTR",
            "driver_mode": "real",
            "role": "primary_baseStation",
        }
        assert body["resolved"]["status"] == "configured"
        assert body["resolved"]["adapter_id"] == "cmw500"
        assert body["resolved"]["binding_digest"]
        db.refresh(lab)
        assert len(lab.instrument_bindings) == 2
        assert lab.instrument_bindings[0]["connection_endpoint"] == "keep-me"
        assert lab.instrument_bindings[1] == body["binding"]

        preview = client.get(
            f"/api/v1/lab-profiles/{lab.id}/instrument-bindings/baseStation/preview"
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["binding_digest"] == body["resolved"]["binding_digest"]

        execution = TestExecution(status="pending", config={})
        db.add(execution)
        db.commit()
        frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)
        assert frozen["binding_digest"] == body["resolved"]["binding_digest"]

        readiness = client.get(
            "/api/v1/instruments/hal/readiness",
            params={"lab_profile_id": str(lab.id)},
        )
        assert readiness.status_code == 200, readiness.text
        readiness_body = readiness.json()
        assert (
            readiness_body["base_station_binding"]["binding_digest"]
            == body["resolved"]["binding_digest"]
        )
        assert (
            readiness_body["cmw500_lte_2x2"]["binding_digest"]
            == body["resolved"]["binding_digest"]
        )

    def test_rejects_cmw500_sync_without_internal_route_profile(
        self, db, lab, monkeypatch
    ):
        category = InstrumentCategory(
            category_key="baseStation",
            category_name="Base Station",
            driver_mode="real",
            is_active=True,
        )
        db.add(category)
        db.flush()
        model = InstrumentModel(
            category_id=category.id,
            vendor="R&S",
            model="CMW500",
            capabilities={},
            is_available=True,
        )
        db.add(model)
        db.flush()
        category.selected_model_id = model.id
        db.add(InstrumentConnection(
            category_id=category.id,
            endpoint="TCPIP0::192.168.100.22::inst0::INSTR",
            connection_params={"detected_test_app": "LTE_NR_IRAT"},
            base_station_model_presets={
                str(model.id): {
                    "schema_version": 1,
                    "model_id": str(model.id),
                    "endpoint": "TCPIP0::192.168.100.22::inst0::INSTR",
                    "controller": "",
                    "notes": "",
                    "connection_params": {"detected_test_app": "LTE_NR_IRAT"},
                    "base_station_adapter_profile": None,
                },
            },
        ))
        monkeypatch.setattr(
            instrument_hal_service,
            "_hal_service",
            SimpleNamespace(
                drivers={
                    "baseStation": RealCmw500Driver(
                        "cmw",
                        {"endpoint": "TCPIP0::192.168.100.22::inst0::INSTR"},
                    )
                }
            ),
        )
        db.commit()

        response = client.put(
            f"/api/v1/lab-profiles/{lab.id}/instrument-bindings/baseStation/sync-current"
        )

        assert response.status_code == 422
        assert "CMW500" in response.json()["detail"]
        assert "required adapter profile is missing" in response.json()["detail"]
        assert "pcc_bb_board" in response.json()["detail"]
        db.refresh(lab)
        assert lab.instrument_bindings in (None, [])

    def test_rejects_unsaved_or_drifted_base_station_before_mutating_lab(
        self, db, lab, monkeypatch
    ):
        category = InstrumentCategory(
            category_key="baseStation",
            category_name="Base Station",
            driver_mode="real",
            is_active=True,
        )
        db.add(category)
        db.flush()
        model = InstrumentModel(
            category_id=category.id,
            vendor="Keysight",
            model="UXM 5G E7515B",
            capabilities={},
            is_available=True,
        )
        db.add(model)
        db.flush()
        category.selected_model_id = model.id
        connection = InstrumentConnection(
            category_id=category.id,
            endpoint="192.168.1.112",
            protocol="socket",
            connection_params={"timeout_ms": 30000},
        )
        db.add(connection)
        monkeypatch.setattr(
            instrument_hal_service,
            "_hal_service",
            SimpleNamespace(drivers={"baseStation": object()}),
        )
        lab.instrument_bindings = [{
            "category_id": str(category.id),
            "instrument_model_id": str(model.id),
            "connection_endpoint": "keep-existing",
            "driver_mode": "real",
            "role": "primary_baseStation",
        }]
        db.commit()

        response = client.put(
            f"/api/v1/lab-profiles/{lab.id}/instrument-bindings/baseStation/sync-current"
        )
        assert response.status_code == 422
        assert "保存配置" in response.json()["detail"]
        db.refresh(lab)
        assert lab.instrument_bindings[0]["connection_endpoint"] == "keep-existing"

        connection.base_station_model_presets = {
            str(model.id): {
                "schema_version": 1,
                "model_id": str(model.id),
                "endpoint": "192.168.1.113",
                "controller": "socket",
                "notes": "",
                "connection_params": {"timeout_ms": 30000},
                "base_station_adapter_profile": None,
            },
        }
        db.commit()
        response = client.put(
            f"/api/v1/lab-profiles/{lab.id}/instrument-bindings/baseStation/sync-current"
        )
        assert response.status_code == 422
        assert "已保存 preset 不一致" in response.json()["detail"]
        db.refresh(lab)
        assert lab.instrument_bindings[0]["connection_endpoint"] == "keep-existing"
