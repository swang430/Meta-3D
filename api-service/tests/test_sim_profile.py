"""SIMProfile (SIM/eSIM 身份+鉴权声明) CRUD service + API 测试 (P2-13 阶段 1)。SQLite 隔离。

本阶段: 实体 + CRUD + 字段校验 + 凭据脱敏。后续阶段: SIM↔UXM 一致性 precheck + attach 后
实测 IMSI 核对 + (档 A) 自动 provision UXM HSS。
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
from app.models.sim_profile import SIMProfile  # noqa: F401  确保表在 metadata
from app.services.sim_profile_service import (
    SIMProfileError,
    SIMProfileNotFound,
    create_sim_profile,
    delete_sim_profile,
    get_sim_profile,
    list_sim_profiles,
    update_sim_profile,
)

_KI = "00112233445566778899aabbccddeeff"  # 32 hex


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


class TestSIMProfileService:
    def test_create_and_get(self, db):
        p = create_sim_profile(
            db, name="TestSIM-46000", imsi="460001234567890", mcc="460", mnc="00",
            ki=_KI, opc=_KI, auth_algorithm="MILENAGE", card_kind="test_sim", sim_form="usim",
        )
        assert p.id is not None and p.name == "TestSIM-46000"
        got = get_sim_profile(db, p.id)
        assert got.imsi == "460001234567890" and got.ki == _KI and got.auth_algorithm == "MILENAGE"

    def test_create_duplicate_name(self, db):
        create_sim_profile(db, name="dup")
        with pytest.raises(SIMProfileError, match="已存在"):
            create_sim_profile(db, name="dup")

    def test_invalid_imsi(self, db):
        with pytest.raises(SIMProfileError, match="imsi"):
            create_sim_profile(db, name="bad", imsi="abc123")
        with pytest.raises(SIMProfileError, match="imsi"):
            create_sim_profile(db, name="bad2", imsi="123")  # too short

    def test_invalid_mcc_mnc(self, db):
        with pytest.raises(SIMProfileError, match="mcc"):
            create_sim_profile(db, name="bad", mcc="46")  # 2 位非法 (需 3)
        with pytest.raises(SIMProfileError, match="mnc"):
            create_sim_profile(db, name="bad2", mnc="1")  # 1 位非法

    def test_mcc_mnc_imsi_prefix_mismatch(self, db):
        with pytest.raises(SIMProfileError, match="前缀"):
            create_sim_profile(
                db, name="bad", imsi="460001234567890", mcc="310", mnc="26",
            )

    def test_mcc_mnc_imsi_prefix_consistent_ok(self, db):
        p = create_sim_profile(
            db, name="ok", imsi="310260123456789", mcc="310", mnc="26",
        )
        assert p.imsi == "310260123456789"

    def test_invalid_ki_not_hex32(self, db):
        with pytest.raises(SIMProfileError, match="ki"):
            create_sim_profile(db, name="bad", ki="xyz", card_kind="test_sim")
        with pytest.raises(SIMProfileError, match="ki"):
            create_sim_profile(db, name="bad2", ki="00112233", card_kind="test_sim")  # too short

    def test_invalid_auth_algorithm(self, db):
        with pytest.raises(SIMProfileError, match="auth_algorithm"):
            create_sim_profile(db, name="bad", auth_algorithm="COMP128")  # 2G, 不支持

    def test_invalid_card_kind_and_sim_form(self, db):
        with pytest.raises(SIMProfileError, match="card_kind"):
            create_sim_profile(db, name="bad", card_kind="prepaid")
        with pytest.raises(SIMProfileError, match="sim_form"):
            create_sim_profile(db, name="bad2", sim_form="psim")

    def test_commercial_with_ki_rejected(self, db):
        # 商用卡不可带 Ki (运营商保密不可得)
        with pytest.raises(SIMProfileError, match="commercial"):
            create_sim_profile(db, name="bad", card_kind="commercial", ki=_KI)

    def test_commercial_without_ki_ok(self, db):
        p = create_sim_profile(db, name="comm", card_kind="commercial", imsi="460009999999999")
        assert p.card_kind == "commercial" and p.ki is None

    def test_list_excludes_inactive(self, db):
        create_sim_profile(db, name="active")
        b = create_sim_profile(db, name="gone")
        delete_sim_profile(db, b.id)  # soft
        names = [p.name for p in list_sim_profiles(db)]
        assert "active" in names and "gone" not in names
        assert "gone" in [p.name for p in list_sim_profiles(db, include_inactive=True)]

    def test_update(self, db):
        p = create_sim_profile(db, name="X", card_kind="test_sim")
        update_sim_profile(db, p.id, auth_algorithm="TUAK", ki=_KI)
        got = get_sim_profile(db, p.id)
        assert got.auth_algorithm == "TUAK" and got.ki == _KI

    def test_update_blank_name_rejected(self, db):
        p = create_sim_profile(db, name="X")
        with pytest.raises(SIMProfileError, match="不能为空"):
            update_sim_profile(db, p.id, name="   ")

    def test_update_rename_collision(self, db):
        create_sim_profile(db, name="A")
        b = create_sim_profile(db, name="B")
        with pytest.raises(SIMProfileError, match="已存在"):
            update_sim_profile(db, b.id, name="A")

    def test_get_not_found(self, db):
        with pytest.raises(SIMProfileNotFound):
            get_sim_profile(db, uuid.uuid4())

    def test_hard_delete(self, db):
        p = create_sim_profile(db, name="X")
        delete_sim_profile(db, p.id, soft=False)
        with pytest.raises(SIMProfileNotFound):
            get_sim_profile(db, p.id)


class TestSIMProfileAPI:
    @pytest.fixture
    def client(self, db):
        app.dependency_overrides[get_db] = lambda: db
        yield TestClient(app)
        app.dependency_overrides.pop(get_db, None)

    def test_crud_http(self, client):
        r = client.post("/api/v1/sim-profiles", json={
            "name": "API-SIM", "imsi": "460001234567890", "mcc": "460", "mnc": "00",
            "ki": _KI, "auth_algorithm": "MILENAGE", "card_kind": "test_sim",
        })
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        r = client.get("/api/v1/sim-profiles")
        assert r.status_code == 200 and any(p["name"] == "API-SIM" for p in r.json())
        r = client.get(f"/api/v1/sim-profiles/{pid}")
        assert r.status_code == 200 and r.json()["imsi"] == "460001234567890"
        r = client.put(f"/api/v1/sim-profiles/{pid}", json={"auth_algorithm": "XOR"})
        assert r.status_code == 200 and r.json()["auth_algorithm"] == "XOR"
        r = client.delete(f"/api/v1/sim-profiles/{pid}")
        assert r.status_code == 204
        assert not any(p["name"] == "API-SIM" for p in client.get("/api/v1/sim-profiles").json())

    def test_ki_masked_not_leaked_in_response(self, client):
        # ⭐ 凭据脱敏: 响应不含原始 ki/opc, 只给后 4 位 + 是否已设
        r = client.post("/api/v1/sim-profiles", json={
            "name": "Secret-SIM", "ki": _KI, "opc": _KI, "card_kind": "test_sim",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert _KI not in str(body)  # 原始 ki 不出现在响应任何处
        assert body["ki_set"] is True and body["opc_set"] is True
        assert body["ki_masked"] == "…eeff" and "ki" not in body  # 无原始 ki 字段

    def test_update_without_ki_keeps_existing(self, client):
        # 编辑不传 ki = 保持原值 (凭据不必每次回传)
        r = client.post("/api/v1/sim-profiles", json={
            "name": "Keep-Ki", "ki": _KI, "card_kind": "test_sim",
        })
        pid = r.json()["id"]
        r = client.put(f"/api/v1/sim-profiles/{pid}", json={"description": "edited"})
        assert r.status_code == 200
        assert r.json()["ki_set"] is True  # ki 仍在

    def test_commercial_with_ki_400(self, client):
        r = client.post("/api/v1/sim-profiles", json={
            "name": "comm-bad", "card_kind": "commercial", "ki": _KI,
        })
        assert r.status_code == 400

    def test_create_invalid_imsi_400(self, client):
        r = client.post("/api/v1/sim-profiles", json={"name": "bad", "imsi": "xyz"})
        assert r.status_code == 400

    def test_get_404(self, client):
        assert client.get(f"/api/v1/sim-profiles/{uuid.uuid4()}").status_code == 404
