"""DUTProfile (DUT 自声明能力) CRUD service + API 测试。SQLite 隔离, 不需硬件。

本 PR: 实体 + CRUD。后续 PR: precheck 早期校验 (TestCase 请求 vs 声明) + attach 后跟 UXM
协商交叉核对。
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
from app.models.dut_profile import DUTProfile  # noqa: F401  确保表在 metadata
from app.services.dut_profile_service import (
    DUTProfileError,
    DUTProfileNotFound,
    create_dut_profile,
    delete_dut_profile,
    get_dut_profile,
    list_dut_profiles,
    update_dut_profile,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # in-memory 每 connection 独立 DB; StaticPool 共享单 conn
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class TestDUTProfileService:
    def test_create_and_get(self, db):
        p = create_dut_profile(
            db, name="Model-X", max_dl_layers=4, max_modulation_dl="256QAM",
            supported_bands=["N78", "N41"], duplex_mode="TDD",
        )
        assert p.id is not None and p.name == "Model-X"
        got = get_dut_profile(db, p.id)
        assert got.max_dl_layers == 4 and got.supported_bands == ["N78", "N41"]

    def test_create_duplicate_name(self, db):
        create_dut_profile(db, name="dup")
        with pytest.raises(DUTProfileError, match="已存在"):
            create_dut_profile(db, name="dup")

    def test_create_invalid_layers(self, db):
        with pytest.raises(DUTProfileError, match="必须 > 0"):
            create_dut_profile(db, name="bad", max_dl_layers=0)

    def test_create_invalid_modulation(self, db):
        with pytest.raises(DUTProfileError, match="非法调制"):
            create_dut_profile(db, name="bad", max_modulation_dl="999QAM")

    def test_create_invalid_duplex(self, db):
        with pytest.raises(DUTProfileError, match="duplex"):
            create_dut_profile(db, name="bad", duplex_mode="XDD")

    def test_create_bands_not_list(self, db):
        with pytest.raises(DUTProfileError, match="supported_bands"):
            create_dut_profile(db, name="bad", supported_bands="N78")

    def test_list_excludes_inactive(self, db):
        create_dut_profile(db, name="active")
        b = create_dut_profile(db, name="gone")
        delete_dut_profile(db, b.id)  # soft
        names = [p.name for p in list_dut_profiles(db)]
        assert "active" in names and "gone" not in names
        all_names = [p.name for p in list_dut_profiles(db, include_inactive=True)]
        assert "gone" in all_names

    def test_update(self, db):
        p = create_dut_profile(db, name="X", max_dl_layers=2)
        update_dut_profile(db, p.id, max_dl_layers=4, max_modulation_dl="256QAM")
        got = get_dut_profile(db, p.id)
        assert got.max_dl_layers == 4 and got.max_modulation_dl == "256QAM"

    def test_update_invalid(self, db):
        p = create_dut_profile(db, name="X")
        with pytest.raises(DUTProfileError):
            update_dut_profile(db, p.id, max_dl_layers=-1)

    def test_update_rename_collision(self, db):
        create_dut_profile(db, name="A")
        b = create_dut_profile(db, name="B")
        with pytest.raises(DUTProfileError, match="已存在"):
            update_dut_profile(db, b.id, name="A")

    def test_update_blank_name_rejected(self, db):
        # Codex P2 #134: update 不能把 name 改成空白 (后续 plan/precheck 按 name 引用)
        p = create_dut_profile(db, name="X")
        with pytest.raises(DUTProfileError, match="不能为空"):
            update_dut_profile(db, p.id, name="   ")

    def test_get_not_found(self, db):
        with pytest.raises(DUTProfileNotFound):
            get_dut_profile(db, uuid.uuid4())

    def test_hard_delete(self, db):
        p = create_dut_profile(db, name="X")
        delete_dut_profile(db, p.id, soft=False)
        with pytest.raises(DUTProfileNotFound):
            get_dut_profile(db, p.id)


class TestDUTProfileAPI:
    @pytest.fixture
    def client(self, db):
        app.dependency_overrides[get_db] = lambda: db
        yield TestClient(app)
        app.dependency_overrides.pop(get_db, None)

    def test_crud_http(self, client):
        r = client.post("/api/v1/dut-profiles", json={"name": "API-DUT", "max_dl_layers": 4})
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        r = client.get("/api/v1/dut-profiles")
        assert r.status_code == 200 and any(p["name"] == "API-DUT" for p in r.json())
        r = client.get(f"/api/v1/dut-profiles/{pid}")
        assert r.status_code == 200 and r.json()["max_dl_layers"] == 4
        r = client.put(f"/api/v1/dut-profiles/{pid}", json={"max_dl_layers": 2})
        assert r.status_code == 200 and r.json()["max_dl_layers"] == 2
        r = client.delete(f"/api/v1/dut-profiles/{pid}")
        assert r.status_code == 204
        r = client.get("/api/v1/dut-profiles")
        assert not any(p["name"] == "API-DUT" for p in r.json())

    def test_create_invalid_400(self, client):
        r = client.post("/api/v1/dut-profiles", json={"name": "bad", "max_dl_layers": 0})
        assert r.status_code == 400

    def test_get_404(self, client):
        r = client.get(f"/api/v1/dut-profiles/{uuid.uuid4()}")
        assert r.status_code == 404
