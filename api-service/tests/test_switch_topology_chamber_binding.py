"""P1: chamber_id is required when importing or saving a SwitchTopology.

Before P1, importing /switch-topologies/import/from-template left chamber_id
NULL, and PATCH could clear it again — the topology row existed but had no
chamber to point at, so calibration / measure couldn't resolve it. P1 makes
chamber_id required at the API layer for new imports + active saves.

(Endpoint was renamed from /import/caict-default to /import/from-template as
part of moving site-specific topology code out of the commercial codebase.)

P1-57 起：请求真值换成 lab_profile_id（暗室由 LabProfile 派生），chamber_id
只剩一致性断言；legacy NULL-chamber 行在 lab 作用域下不可达（不迁移不删除）。
本文件里被取代的两条旧契约（PATCH 绑定孤儿行）改写为「409 且行不变」。
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
from app.models.chamber import (
    ChamberType,
    create_chamber_from_preset,
)
from app.models.switch_topology import SwitchTopology


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
def setup_database():
    # Per-test dep override (see test_lab_profile_api for why module-scoped
    # overrides collide between test modules).
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P1 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    from app.models.lab_profile import LabProfile
    l = LabProfile(name="P1 Lab", chamber_config_id=chamber.id, is_active=True)
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


class TestImportFromTemplateRequiresChamber:
    def test_import_without_chamber_id_returns_422(self):
        # FastAPI returns 422 for missing required query param.
        resp = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(uuid.uuid4()),
                "template_id": "caict_v4",
            },
        )
        assert resp.status_code == 422

    def test_import_with_contradicting_chamber_id_returns_422(self, lab):
        # P1-57：chamber_id 只是一致性断言输入 —— 跟 lab 派生的暗室不一致就 422
        resp = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(uuid.uuid4()),
                "lab_profile_id": str(lab.id),
                "chamber_id": str(uuid.uuid4()),
                "template_id": "caict_v4",
            },
        )
        assert resp.status_code == 422
        assert "不一致" in resp.json()["detail"]

    def test_import_with_unknown_template_returns_404(self, lab):
        resp = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(uuid.uuid4()),
                "lab_profile_id": str(lab.id),
                "template_id": "no_such_template",
            },
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_import_with_valid_chamber_and_template_succeeds(self, chamber, lab):
        resp = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(uuid.uuid4()),
                "lab_profile_id": str(lab.id),
                "template_id": "caict_v4",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chamber_id"] == str(chamber.id)

    def test_templates_endpoint_lists_caict_v4(self):
        resp = client.get("/api/v1/switch-topologies/templates")
        assert resp.status_code == 200
        assert "caict_v4" in resp.json()

    def test_templates_endpoint_empty_when_dev_fixtures_absent(self, monkeypatch, tmp_path, lab):
        # Simulates the commercial-deploy invariant: .dockerignore strips
        # scripts/dev-fixtures/ out of the production image, so _TEMPLATES_DIR
        # resolves to a non-existent directory. The registry must report empty
        # and /import/from-template must 404 — without this the PR's stated
        # "commercial code ships zero templates" goal silently regresses
        # (Codex review on aa29a7969e flagged this).
        import app.api.switch_topology as topology_api

        missing_dir = tmp_path / "no-such-dir"
        assert not missing_dir.exists()
        monkeypatch.setattr(topology_api, "_TEMPLATES_DIR", missing_dir)

        list_resp = client.get("/api/v1/switch-topologies/templates")
        assert list_resp.status_code == 200
        assert list_resp.json() == []

        import_resp = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(uuid.uuid4()),
                "lab_profile_id": str(lab.id),
                "template_id": "caict_v4",
            },
        )
        assert import_resp.status_code == 404
        assert "not found" in import_resp.json()["detail"].lower()


class TestActiveTopologyRequiresChamber:
    def test_patch_active_topology_to_null_chamber_returns_422(self, db, chamber, lab):
        topo = SwitchTopology(
            switch_category_id=uuid.uuid4(),
            chamber_id=chamber.id,
            name="P1 patch test",
            nodes=[],
            connections=[],
            operating_modes=[],
            is_active=True,
        )
        db.add(topo)
        db.commit()
        db.refresh(topo)

        # P1-57：chamber 由 LabProfile 派生 —— 清空 = 改绑，一律 422
        resp = client.patch(
            f"/api/v1/switch-topologies/{topo.id}",
            params={"lab_profile_id": str(lab.id)},
            json={"chamber_id": None},
        )
        assert resp.status_code == 422
        assert "chamber_id" in resp.json()["detail"]

    def test_patch_legacy_null_chamber_row_is_unreachable(self, db, lab):
        # P1-57 取代旧契约「inactive legacy 行可改名」：legacy NULL-chamber 行
        # 在任何 lab 作用域下不可达（409），也不被改动 —— 不迁移、不删除。
        topo = SwitchTopology(
            switch_category_id=uuid.uuid4(),
            chamber_id=None,
            name="legacy",
            nodes=[],
            connections=[],
            operating_modes=[],
            is_active=False,
        )
        db.add(topo)
        db.commit()
        db.refresh(topo)

        resp = client.patch(
            f"/api/v1/switch-topologies/{topo.id}",
            params={"lab_profile_id": str(lab.id)},
            json={"name": "renamed"},
        )
        assert resp.status_code == 409
        db.refresh(topo)
        assert topo.name == "legacy"

    def test_patch_cannot_adopt_legacy_topology_into_lab(self, db, chamber, lab):
        # P1-57 取代旧契约「PATCH 可给孤儿行绑 chamber」：作用域检查在先，
        # 改绑之路整个关掉 —— chamber 只能来自 LabProfile 派生。
        topo = SwitchTopology(
            switch_category_id=uuid.uuid4(),
            chamber_id=None,
            name="legacy-fixme",
            nodes=[],
            connections=[],
            operating_modes=[],
            is_active=True,  # would normally fail save, but stored directly
        )
        db.add(topo)
        db.commit()
        db.refresh(topo)

        resp = client.patch(
            f"/api/v1/switch-topologies/{topo.id}",
            params={"lab_profile_id": str(lab.id)},
            json={"chamber_id": str(chamber.id)},
        )
        assert resp.status_code == 409
        db.refresh(topo)
        assert topo.chamber_id is None


class TestListFilterByChamber:
    """P1-57 起列表按 lab 作用域：每个 lab 只看到自己暗室的行；
    无 lab_profile_id 的「全量列表」不复存在（旧契约已被取代）。"""

    def test_lab_scope_narrows_to_own_chamber(self, db, chamber, lab):
        from app.models.lab_profile import LabProfile
        chamber_b = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Chamber-B")
        db.add(chamber_b)
        db.commit()
        db.refresh(chamber_b)
        lab_b = LabProfile(name="Lab-B", chamber_config_id=chamber_b.id, is_active=True)
        db.add(lab_b)
        db.commit()
        db.refresh(lab_b)

        switch_cat_id = uuid.uuid4()
        for name, cid in (("topo-for-A", chamber.id), ("topo-for-B", chamber_b.id)):
            db.add(SwitchTopology(
                switch_category_id=switch_cat_id, chamber_id=cid, name=name,
                nodes=[], connections=[], operating_modes=[], is_active=True,
            ))
        db.commit()

        a = client.get("/api/v1/switch-topologies", params={
            "switch_category_id": str(switch_cat_id),
            "lab_profile_id": str(lab.id),
        }).json()
        assert a["total"] == 1 and a["items"][0]["name"] == "topo-for-A"

        b = client.get("/api/v1/switch-topologies", params={
            "switch_category_id": str(switch_cat_id),
            "lab_profile_id": str(lab_b.id),
        }).json()
        assert b["total"] == 1 and b["items"][0]["name"] == "topo-for-B"

        # 兼容参数与派生暗室一致时照常工作
        compat = client.get("/api/v1/switch-topologies", params={
            "switch_category_id": str(switch_cat_id),
            "lab_profile_id": str(lab.id),
            "chamber_id": str(chamber.id),
        })
        assert compat.status_code == 200 and compat.json()["total"] == 1

    def test_lab_scope_excludes_legacy_null_chamber_rows(self, db, chamber, lab):
        switch_cat_id = uuid.uuid4()
        for name, cid in (("legacy-null", None), ("bound", chamber.id)):
            db.add(SwitchTopology(
                switch_category_id=switch_cat_id, chamber_id=cid, name=name,
                nodes=[], connections=[], operating_modes=[], is_active=True,
            ))
        db.commit()

        scoped = client.get("/api/v1/switch-topologies", params={
            "switch_category_id": str(switch_cat_id),
            "lab_profile_id": str(lab.id),
        }).json()
        assert scoped["total"] == 1
        assert scoped["items"][0]["name"] == "bound"
