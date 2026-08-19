"""P1-57：topology API 的暗室真值从「客户端自由提交的 chamber_id」换成
「lab_profile_id → resolve_current_chamber()」。

可观察故障：射频拓扑编辑器可以独立选中另一个暗室（CAICT-5-13），跟探头配置 /
暗室首测各说各话 —— 后端只要肯收 chamber_id，GUI 的任何一套页面状态都能把
拓扑写进错的暗室。

契约（除 /templates 外全部端点）：
- 请求真值 = lab_profile_id，服务端派生 chamber；
- 请求附带的 chamber 与派生值不一致 → 在任何写入前 422，行不变；
- 存在别的暗室下的 topology 行 → 在 lab A 上读 / 改 / 删 / 解析 / 校验一律 409；
- inactive / missing / 无绑定 / 绑定指向缺失暗室的 LabProfile → fail-closed 422；
- 旧 NULL-chamber 行不迁移、不删除、lab 作用域下不可达。
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
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.lab_profile import LabProfile
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


@pytest.fixture()
def world():
    """两个暗室、两个各自绑定的活动 lab、一个无绑定 lab、一个停用 lab。"""
    db = TestingSessionLocal()
    chamber_a = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Chamber-A")
    chamber_b = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Chamber-B")
    db.add_all([chamber_a, chamber_b])
    db.commit()
    lab_a = LabProfile(name="Lab-A", chamber_config_id=chamber_a.id, is_active=True)
    lab_b = LabProfile(name="Lab-B", chamber_config_id=chamber_b.id, is_active=True)
    lab_unbound = LabProfile(name="Lab-Unbound", chamber_config_id=None, is_active=True)
    lab_inactive = LabProfile(
        name="Lab-Inactive", chamber_config_id=chamber_a.id, is_active=False
    )
    db.add_all([lab_a, lab_b, lab_unbound, lab_inactive])
    db.commit()
    for o in (chamber_a, chamber_b, lab_a, lab_b, lab_unbound, lab_inactive):
        db.refresh(o)
    out = {
        "db": db,
        "chamber_a": chamber_a, "chamber_b": chamber_b,
        "lab_a": lab_a, "lab_b": lab_b,
        "lab_unbound": lab_unbound, "lab_inactive": lab_inactive,
        "switch_id": uuid.uuid4(),
    }
    yield out
    db.close()


def _topology_payload(switch_id, name="Topo", **extra):
    return {
        "switch_category_id": str(switch_id),
        "name": name,
        "is_active": True,
        "is_default": False,
        "nodes": [], "connections": [], "operating_modes": [],
        **extra,
    }


def _mk_row(db, switch_id, chamber_id, name="Row"):
    row = SwitchTopology(
        switch_category_id=switch_id, chamber_id=chamber_id, name=name,
        is_active=True, is_default=False,
        nodes=[], connections=[], operating_modes=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestLabScopedList:
    def test_list_requires_lab_profile_id(self, world):
        r = client.get("/api/v1/switch-topologies")
        assert r.status_code == 422

    def test_list_scopes_to_resolved_chamber(self, world):
        db = world["db"]
        a = _mk_row(db, world["switch_id"], world["chamber_a"].id, "In-A")
        _mk_row(db, world["switch_id"], world["chamber_b"].id, "In-B")
        _mk_row(db, world["switch_id"], None, "Orphan-NULL")
        r = client.get(
            "/api/v1/switch-topologies",
            params={"lab_profile_id": str(world["lab_a"].id)},
        )
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["items"]]
        assert ids == [str(a.id)], "lab A 只能看到 chamber A 的行（NULL 行也不可见）"

    def test_list_rejects_contradicting_chamber_filter(self, world):
        r = client.get(
            "/api/v1/switch-topologies",
            params={
                "lab_profile_id": str(world["lab_a"].id),
                "chamber_id": str(world["chamber_b"].id),
            },
        )
        assert r.status_code == 422

    @pytest.mark.parametrize("labkey,detail_hint", [
        ("lab_unbound", "chamber"),
        ("lab_inactive", "inactive"),
    ])
    def test_list_fails_closed_on_bad_lab(self, world, labkey, detail_hint):
        r = client.get(
            "/api/v1/switch-topologies",
            params={"lab_profile_id": str(world[labkey].id)},
        )
        assert r.status_code == 422
        assert detail_hint.lower() in str(r.json()).lower()

    def test_list_fails_closed_on_missing_lab(self, world):
        r = client.get(
            "/api/v1/switch-topologies",
            params={"lab_profile_id": str(uuid.uuid4())},
        )
        assert r.status_code == 422


class TestLabScopedCreate:
    def test_create_derives_chamber_from_lab(self, world):
        r = client.post(
            "/api/v1/switch-topologies",
            json=_topology_payload(world["switch_id"],
                                   lab_profile_id=str(world["lab_a"].id)),
        )
        assert r.status_code == 201, r.text
        assert r.json()["chamber_id"] == str(world["chamber_a"].id)

    def test_create_rejects_contradicting_chamber_before_commit(self, world):
        db = world["db"]
        before = db.query(SwitchTopology).count()
        r = client.post(
            "/api/v1/switch-topologies",
            json=_topology_payload(
                world["switch_id"],
                lab_profile_id=str(world["lab_a"].id),
                chamber_id=str(world["chamber_b"].id),
            ),
        )
        assert r.status_code == 422
        assert db.query(SwitchTopology).count() == before, "拒绝时不得留下行"

    def test_create_requires_lab_profile_id(self, world):
        r = client.post(
            "/api/v1/switch-topologies",
            json=_topology_payload(world["switch_id"],
                                   chamber_id=str(world["chamber_a"].id)),
        )
        assert r.status_code == 422


class TestCrossChamberScope:
    """存在别的暗室下的行：lab A 上读 / 改 / 删 / 解析 / 校验一律拒绝且行不变。"""

    def _row_in_b(self, world):
        return _mk_row(world["db"], world["switch_id"],
                       world["chamber_b"].id, "B-owned")

    def test_get_scoped(self, world):
        row = self._row_in_b(world)
        r = client.get(
            f"/api/v1/switch-topologies/{row.id}",
            params={"lab_profile_id": str(world["lab_a"].id)},
        )
        assert r.status_code == 409

    def test_update_scoped_and_row_unchanged(self, world):
        row = self._row_in_b(world)
        r = client.patch(
            f"/api/v1/switch-topologies/{row.id}",
            params={"lab_profile_id": str(world["lab_a"].id)},
            json={"name": "hijacked"},
        )
        assert r.status_code == 409
        world["db"].refresh(row)
        assert row.name == "B-owned"

    def test_delete_scoped_and_row_survives(self, world):
        row = self._row_in_b(world)
        r = client.delete(
            f"/api/v1/switch-topologies/{row.id}",
            params={"lab_profile_id": str(world["lab_a"].id)},
        )
        assert r.status_code == 409
        assert world["db"].query(SwitchTopology).filter_by(id=row.id).first() is not None

    @pytest.mark.parametrize("suffix", ["validate", "paths/dl", "calibration-matrix/dl"])
    def test_read_computations_scoped(self, world, suffix):
        row = self._row_in_b(world)
        r = client.get(
            f"/api/v1/switch-topologies/{row.id}/{suffix}",
            params={"lab_profile_id": str(world["lab_a"].id)},
        )
        assert r.status_code == 409

    def test_update_cannot_move_row_to_other_chamber(self, world):
        """在自己 lab 下也不能把行改绑到别的暗室 —— chamber 由 lab 派生。"""
        db = world["db"]
        row = _mk_row(db, world["switch_id"], world["chamber_a"].id, "A-owned")
        r = client.patch(
            f"/api/v1/switch-topologies/{row.id}",
            params={"lab_profile_id": str(world["lab_a"].id)},
            json={"chamber_id": str(world["chamber_b"].id)},
        )
        assert r.status_code == 422
        db.refresh(row)
        assert row.chamber_id == world["chamber_a"].id

    def test_same_lab_update_works(self, world):
        db = world["db"]
        row = _mk_row(db, world["switch_id"], world["chamber_a"].id, "A-owned")
        r = client.patch(
            f"/api/v1/switch-topologies/{row.id}",
            params={"lab_profile_id": str(world["lab_a"].id)},
            json={"name": "renamed"},
        )
        assert r.status_code == 200, r.text
        db.refresh(row)
        assert row.name == "renamed"


class TestDefaultFlagScopedToChamber:
    def test_create_default_leaves_other_chamber_default_alone(self, world):
        """默认位让位只在本暗室内 —— 不从 lab A 顺手改掉 chamber B 的默认行。"""
        db = world["db"]
        b_default = SwitchTopology(
            switch_category_id=world["switch_id"], chamber_id=world["chamber_b"].id,
            name="B-default", is_active=True, is_default=True,
            nodes=[], connections=[], operating_modes=[],
        )
        db.add(b_default); db.commit(); db.refresh(b_default)
        r = client.post(
            "/api/v1/switch-topologies",
            json=_topology_payload(
                world["switch_id"],
                lab_profile_id=str(world["lab_a"].id),
                is_default=True,
            ),
        )
        assert r.status_code == 201, r.text
        db.refresh(b_default)
        assert b_default.is_default is True, "chamber B 的默认行被 lab A 的创建动了"


class TestImportResolvesBeforeAnyDelete:
    def test_import_requires_lab_not_chamber(self, world):
        """import 的真值输入是 lab_profile_id；chamber_id 不再是必填 query。"""
        r = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(world["switch_id"]),
                "chamber_id": str(world["chamber_a"].id),
                "template_id": "nonexistent",
            },
        )
        assert r.status_code == 422, "缺 lab_profile_id 必须 422（而不是接受裸 chamber）"

    def test_bad_lab_fails_before_touching_rows(self, world):
        db = world["db"]
        keep = _mk_row(db, world["switch_id"], world["chamber_a"].id, "Keep")
        r = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(world["switch_id"]),
                "lab_profile_id": str(world["lab_unbound"].id),
                "template_id": "nonexistent",
                "replace_existing": "true",
            },
        )
        assert r.status_code == 422
        assert db.query(SwitchTopology).filter_by(id=keep.id).first() is not None, (
            "lab 解析失败必须发生在任何删除之前 —— 先删后验会把行白白删掉"
        )

    def test_bad_template_fails_before_touching_rows(self, world):
        db = world["db"]
        keep = _mk_row(db, world["switch_id"], world["chamber_a"].id, "Keep")
        r = client.post(
            "/api/v1/switch-topologies/import/from-template",
            params={
                "switch_category_id": str(world["switch_id"]),
                "lab_profile_id": str(world["lab_a"].id),
                "template_id": "no_such_template",
                "replace_existing": "true",
            },
        )
        assert r.status_code == 404
        assert db.query(SwitchTopology).filter_by(id=keep.id).first() is not None


class TestLegacyRowsUntouched:
    def test_null_chamber_rows_survive_and_stay_unreachable(self, world):
        db = world["db"]
        orphan = _mk_row(db, world["switch_id"], None, "Legacy-NULL")
        r = client.get(
            "/api/v1/switch-topologies",
            params={"lab_profile_id": str(world["lab_a"].id)},
        )
        assert str(orphan.id) not in [it["id"] for it in r.json().get("items", [])]
        assert db.query(SwitchTopology).filter_by(id=orphan.id).first() is not None
