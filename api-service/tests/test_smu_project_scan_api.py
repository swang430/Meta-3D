"""P2-31 static API routes for read-only preview and server-side re-scan/sync."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.channel_asset import ChannelAsset
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.services.channel_asset_service import create_channel_asset


_SCD = {
    "band": "N78",
    "arfcn": 640000,
    "bandwidth_mhz": 100,
    "model": "CDLC",
    "scenario": "UMa",
    "mimo": "4x4",
    "polarization": "DP",
    "version": 9123,
}


@pytest.fixture
def scan_api(tmp_path: Path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
    )
    db.add(category)
    db.flush()
    connection = InstrumentConnection(
        category_id=category.id,
        connection_params={
            "smu_project_scan": {
                "local_mount_root": str(tmp_path),
                "instrument_root": r"D:\Scenario Packs",
            },
            "available_channel_models": [],
        },
    )
    db.add(connection)
    db.commit()

    def override_db():
        yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app), db, connection, tmp_path
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        db.close()
        Base.metadata.drop_all(engine)


def _seed_syncable(db, root: Path) -> ChannelAsset:
    (root / "pack").mkdir()
    (root / "pack" / "truth.smu").write_text(
        "[Channel Group 0]\nCenterFrequency=3549990000 Hz\n",
        encoding="utf-8",
    )
    return create_channel_asset(
        db,
        name="api-truth",
        source_type="vendor_file",
        payload={"scd_config": dict(_SCD)},
        associated_file_path=r"D:\Scenario Packs\pack\truth.smu",
        center_frequency_hz=3_600_000_000,
        bandwidth_mhz=100,
    )


def test_preview_static_route_is_read_only_and_exposes_no_mount_or_credentials(scan_api):
    client, db, connection, root = scan_api
    asset = _seed_syncable(db, root)

    response = client.post("/api/v1/channel-assets/vendor-files/smu-scan")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["connection_id"] == str(connection.id)
    assert body["items"][0]["sync_status"] == "syncable"
    assert body["items"][0]["primary_center_frequency_hz"] == 3_549_990_000
    assert body["items"][0]["target_arfcn"] == 636666
    assert body["items"][0]["sha256"]
    assert str(root) not in response.text
    assert "password" not in response.text.casefold()
    db.refresh(asset)
    assert asset.center_frequency_hz == 3_600_000_000
    assert connection.connection_params["available_channel_models"] == []


def test_sync_static_route_re_scans_and_ignores_client_frequency(scan_api):
    client, db, connection, root = scan_api
    asset = _seed_syncable(db, root)

    response = client.post(
        "/api/v1/channel-assets/vendor-files/smu-sync",
        json={"primary_center_frequency_hz": 1, "target_arfcn": 1},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated_count"] == 1
    assert body["preview"]["items"][0]["sync_status"] == "already_synced"
    db.expire_all()
    stored = db.get(ChannelAsset, asset.id)
    assert stored.center_frequency_hz == 3_549_990_000
    assert stored.payload["scd_config"]["arfcn"] == 636666
    db.refresh(connection)
    assert connection.connection_params["available_channel_models"][0][
        "center_frequency_mhz"
    ] == 3549.99


def test_missing_scan_config_is_actionable_409_and_does_not_write(scan_api):
    client, db, connection, root = scan_api
    asset = _seed_syncable(db, root)
    connection.connection_params = {"available_channel_models": []}
    db.commit()

    for suffix in ("smu-scan", "smu-sync"):
        response = client.post(f"/api/v1/channel-assets/vendor-files/{suffix}")
        assert response.status_code == 409, response.text
        assert "smu_project_scan" in response.json()["detail"]

    db.refresh(asset)
    assert asset.center_frequency_hz == 3_600_000_000
    db.refresh(connection)
    assert connection.connection_params["available_channel_models"] == []


def test_static_routes_are_not_captured_by_uuid_asset_route(scan_api):
    client, _, _, _ = scan_api

    scan = client.post("/api/v1/channel-assets/vendor-files/smu-scan")
    sync = client.post("/api/v1/channel-assets/vendor-files/smu-sync")

    # Empty configured root is a valid preview/sync, proving FastAPI did not try to parse
    # "vendor-files" as the dynamic UUID asset_id.
    assert scan.status_code == 200, scan.text
    assert sync.status_code == 200, sync.text
    assert scan.json()["items"] == []
    assert sync.json()["updated_count"] == 0
