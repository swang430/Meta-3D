"""CustomCDLProfile (自定义 CDL 簇编辑) CRUD service + API 测试 (P2-15 S1)。

SQLite 隔离, 不需硬件。簇结构校验 (非空 / 必填 / power>0 / as>=0 / 天顶范围 / 相位 len 4)
覆盖 service 层 (绕过 Pydantic) + API 层 (Pydantic Field 约束)。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.custom_cdl_profile import CustomCDLProfile  # noqa: F401  确保表在 metadata
from app.services.custom_cdl_profile_service import (
    CustomCDLProfileError,
    CustomCDLProfileNotFound,
    create_custom_cdl_profile,
    delete_custom_cdl_profile,
    get_custom_cdl_profile,
    list_custom_cdl_profiles,
    update_custom_cdl_profile,
)

_CLUSTER = {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30.0, "aod_deg": 10.0}


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class TestCustomCDLProfileService:
    def test_create_and_get(self, db):
        p = create_custom_cdl_profile(
            db, name="UMa-改", center_frequency_hz=3.5e9, is_los=False,
            clusters=[
                {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30, "aod_deg": 10},
                {"delay_s": 1e-7, "power_linear": 0.5, "aoa_deg": 45, "aod_deg": 12,
                 "as_zoa_deg": 5.0},
            ],
        )
        assert p.id is not None and len(p.clusters) == 2
        got = get_custom_cdl_profile(db, p.id)
        assert got.clusters[0]["aoa_deg"] == 30 and got.center_frequency_hz == 3.5e9
        assert got.clusters[1]["as_zoa_deg"] == 5.0

    def test_create_requires_clusters(self, db):
        with pytest.raises(CustomCDLProfileError, match="clusters 必填"):
            create_custom_cdl_profile(db, name="no-clusters")

    def test_create_empty_clusters(self, db):
        with pytest.raises(CustomCDLProfileError, match="非空"):
            create_custom_cdl_profile(db, name="empty", clusters=[])

    def test_cluster_missing_required(self, db):
        with pytest.raises(CustomCDLProfileError, match="必填"):
            create_custom_cdl_profile(
                db, name="x", clusters=[{"delay_s": 0.0, "power_linear": 1.0}])  # 缺 aoa/aod

    def test_cluster_power_nonpositive(self, db):
        with pytest.raises(CustomCDLProfileError, match="power_linear 必须 > 0"):
            create_custom_cdl_profile(db, name="x", clusters=[{**_CLUSTER, "power_linear": 0.0}])

    def test_cluster_negative_as(self, db):
        with pytest.raises(CustomCDLProfileError, match="必须 >= 0"):
            create_custom_cdl_profile(db, name="x", clusters=[{**_CLUSTER, "as_zoa_deg": -1.0}])

    def test_cluster_bad_phases_len(self, db):
        with pytest.raises(CustomCDLProfileError, match="initial_phases_rad"):
            create_custom_cdl_profile(
                db, name="x", clusters=[{**_CLUSTER, "initial_phases_rad": [0.1, 0.2]}])

    def test_cluster_zenith_out_of_range(self, db):
        with pytest.raises(CustomCDLProfileError, match=r"\[0,180\]"):
            create_custom_cdl_profile(db, name="x", clusters=[{**_CLUSTER, "zoa_deg": 200.0}])

    def test_top_level_freq_nonpositive(self, db):
        with pytest.raises(CustomCDLProfileError, match="center_frequency_hz 必须 > 0"):
            create_custom_cdl_profile(
                db, name="x", center_frequency_hz=0.0, clusters=[_CLUSTER])

    def test_velocity_wrong_len(self, db):
        with pytest.raises(CustomCDLProfileError, match="ue_velocity_mps"):
            create_custom_cdl_profile(
                db, name="x", ue_velocity_mps=[1.0, 2.0], clusters=[_CLUSTER])

    def test_duplicate_name(self, db):
        create_custom_cdl_profile(db, name="dup", clusters=[_CLUSTER])
        with pytest.raises(CustomCDLProfileError, match="已存在"):
            create_custom_cdl_profile(db, name="dup", clusters=[_CLUSTER])

    def test_update_clusters(self, db):
        p = create_custom_cdl_profile(db, name="X", clusters=[_CLUSTER])
        update_custom_cdl_profile(db, p.id, clusters=[_CLUSTER, {**_CLUSTER, "aoa_deg": 90}])
        got = get_custom_cdl_profile(db, p.id)
        assert len(got.clusters) == 2 and got.clusters[1]["aoa_deg"] == 90

    def test_update_invalid_cluster(self, db):
        p = create_custom_cdl_profile(db, name="X", clusters=[_CLUSTER])
        with pytest.raises(CustomCDLProfileError):
            update_custom_cdl_profile(db, p.id, clusters=[{**_CLUSTER, "power_linear": -1}])

    def test_update_rename_collision(self, db):
        create_custom_cdl_profile(db, name="A", clusters=[_CLUSTER])
        b = create_custom_cdl_profile(db, name="B", clusters=[_CLUSTER])
        with pytest.raises(CustomCDLProfileError, match="已存在"):
            update_custom_cdl_profile(db, b.id, name="A")

    def test_list_excludes_inactive(self, db):
        create_custom_cdl_profile(db, name="active", clusters=[_CLUSTER])
        b = create_custom_cdl_profile(db, name="gone", clusters=[_CLUSTER])
        delete_custom_cdl_profile(db, b.id)  # soft
        names = [p.name for p in list_custom_cdl_profiles(db)]
        assert "active" in names and "gone" not in names
        assert "gone" in [p.name for p in list_custom_cdl_profiles(db, include_inactive=True)]

    def test_get_not_found(self, db):
        with pytest.raises(CustomCDLProfileNotFound):
            get_custom_cdl_profile(db, uuid.uuid4())

    def test_hard_delete(self, db):
        p = create_custom_cdl_profile(db, name="X", clusters=[_CLUSTER])
        delete_custom_cdl_profile(db, p.id, soft=False)
        with pytest.raises(CustomCDLProfileNotFound):
            get_custom_cdl_profile(db, p.id)


class TestCustomCDLProfileAPI:
    @pytest.fixture
    def client(self, db):
        app.dependency_overrides[get_db] = lambda: db
        yield TestClient(app)
        app.dependency_overrides.pop(get_db, None)

    def test_crud_http(self, client):
        body = {
            "name": "API-CDL", "center_frequency_hz": 3.5e9, "is_los": False,
            "clusters": [{"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30, "aod_deg": 10}],
        }
        r = client.post("/api/v1/custom-cdl-profiles", json=body)
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        assert r.json()["clusters"][0]["aoa_deg"] == 30
        assert r.json()["clusters"][0]["num_rays"] == 20      # Pydantic 默认填充
        assert r.json()["clusters"][0]["zoa_deg"] == 90.0     # 默认水平面
        r = client.get("/api/v1/custom-cdl-profiles")
        assert r.status_code == 200 and any(p["name"] == "API-CDL" for p in r.json())
        r = client.get(f"/api/v1/custom-cdl-profiles/{pid}")
        assert r.status_code == 200 and r.json()["center_frequency_hz"] == 3.5e9
        # 改簇 (PATCH 语义)
        r = client.put(
            f"/api/v1/custom-cdl-profiles/{pid}",
            json={"clusters": [
                {"delay_s": 0.0, "power_linear": 2.0, "aoa_deg": 90, "aod_deg": 5}]})
        assert r.status_code == 200 and r.json()["clusters"][0]["aoa_deg"] == 90
        r = client.delete(f"/api/v1/custom-cdl-profiles/{pid}")
        assert r.status_code == 204
        assert not any(p["name"] == "API-CDL"
                       for p in client.get("/api/v1/custom-cdl-profiles").json())

    def test_create_empty_clusters_422(self, client):
        # Pydantic min_length=1 → 422 (service 之前拦)
        r = client.post("/api/v1/custom-cdl-profiles", json={"name": "x", "clusters": []})
        assert r.status_code == 422

    def test_create_bad_cluster_422(self, client):
        # Pydantic power_linear gt=0 → 422
        r = client.post("/api/v1/custom-cdl-profiles", json={
            "name": "x",
            "clusters": [{"delay_s": 0, "power_linear": 0, "aoa_deg": 0, "aod_deg": 0}]})
        assert r.status_code == 422

    def test_get_404(self, client):
        r = client.get(f"/api/v1/custom-cdl-profiles/{uuid.uuid4()}")
        assert r.status_code == 404
