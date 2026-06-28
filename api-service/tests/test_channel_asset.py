"""ChannelAsset (信道资产多态化) CRUD service + API 测试 (P2-16 S1)。

SQLite 隔离, 不需硬件。覆盖: 四 source_type 多态 payload 校验 (按 source_type dispatch) +
allowed_targets 从 source_type 派生 + 边缘值 fail-loud + source_type 不可改 + CRUD + 软删 +
API 层路由/422 (feedback_fastapi_router_prefix_no_double: 加 TestClient 路径测试)。
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
from app.models.channel_asset import ChannelAsset  # noqa: F401  确保表在 metadata
from app.services.channel_asset_service import (
    ChannelAssetError,
    ChannelAssetNotFound,
    create_channel_asset,
    delete_channel_asset,
    get_channel_asset,
    list_channel_assets,
    update_channel_asset,
)

# —— 各 source_type 合法 payload 样例 ——
_CLUSTER = {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30.0, "aod_deg": 10.0}
_RAY = {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30.0, "aod_deg": 10.0, "phase_rad": 0.5}
_SCD = {"band": "N78", "arfcn": 640000, "bandwidth_mhz": 100, "model": "CDLC",
        "scenario": "UMa", "mimo": "4x4", "polarization": "DP", "version": 1}

_STD_PAYLOAD = {"cdl_model_name": "UMa CDL-C NLOS"}
_CUSTOM_PAYLOAD = {"snapshots": [{"clusters": [_CLUSTER]}]}
_RT_PAYLOAD = {"snapshots": [{"rays": [_RAY]}]}
_VENDOR_PAYLOAD = {"scd_config": _SCD}


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


@pytest.fixture
def client(db):
    def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestCreateEachSourceTypeAndAllowedTargets:
    """四 source_type 建成功 + allowed_targets 派生正确 (§3.1)。"""

    def test_standard(self, db):
        a = create_channel_asset(db, name="std-1", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD)
        assert a.source_type == "standard_3gpp"
        assert a.allowed_targets == ["asc_baked"]
        assert a.payload["cdl_model_name"] == "UMa CDL-C NLOS"

    def test_custom_static(self, db):
        a = create_channel_asset(db, name="cus-1", source_type="custom_static",
                                 payload=_CUSTOM_PAYLOAD)
        assert a.allowed_targets == ["asc_baked", "b2_parametric"]
        assert a.payload["snapshots"][0]["clusters"][0]["aoa_deg"] == 30.0

    def test_rt_dynamic(self, db):
        a = create_channel_asset(db, name="rt-1", source_type="rt_dynamic",
                                 payload=_RT_PAYLOAD)
        # rt 全开但 gcm 因无 artifact 走 ESCALATE → allowed 不含 gcm_native
        assert a.allowed_targets == ["asc_baked", "b2_parametric"]
        assert "gcm_native" not in a.allowed_targets

    def test_vendor_file(self, db):
        a = create_channel_asset(db, name="ven-1", source_type="vendor_file",
                                 payload=_VENDOR_PAYLOAD,
                                 associated_file_path="/smu/MF_N78.smu")
        assert a.allowed_targets == ["gcm_native"]
        assert a.associated_file_path == "/smu/MF_N78.smu"

    def test_allowed_targets_not_operator_writable(self, db):
        # operator 传 allowed_targets 被忽略, 仍从 source_type 派生
        a = create_channel_asset(db, name="std-2", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD,
                                 allowed_targets=["gcm_native", "b2_parametric"])
        assert a.allowed_targets == ["asc_baked"]


class TestPolymorphicPayloadValidation:
    """payload 按 source_type dispatch 校验, 缺字段/非法 fail-loud。"""

    def test_invalid_source_type(self, db):
        with pytest.raises(ChannelAssetError, match="source_type 非法"):
            create_channel_asset(db, name="x", source_type="bogus", payload={})

    def test_payload_not_dict(self, db):
        with pytest.raises(ChannelAssetError, match="payload 须对象"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload=["not", "dict"])

    def test_standard_missing_cdl_model_name(self, db):
        with pytest.raises(ChannelAssetError, match="cdl_model_name 必填"):
            create_channel_asset(db, name="x", source_type="standard_3gpp", payload={})

    def test_custom_snapshots_not_single(self, db):
        with pytest.raises(ChannelAssetError, match="恰 1 个快照"):
            create_channel_asset(db, name="x", source_type="custom_static",
                                 payload={"snapshots": [{"clusters": [_CLUSTER]},
                                                        {"clusters": [_CLUSTER]}]})

    def test_custom_empty_clusters(self, db):
        with pytest.raises(ChannelAssetError, match="clusters 须非空"):
            create_channel_asset(db, name="x", source_type="custom_static",
                                 payload={"snapshots": [{"clusters": []}]})

    def test_custom_cluster_missing_required(self, db):
        bad = {"snapshots": [{"clusters": [{"delay_s": 0.0, "power_linear": 1.0}]}]}
        with pytest.raises(ChannelAssetError, match="aoa_deg 必填"):
            create_channel_asset(db, name="x", source_type="custom_static", payload=bad)

    def test_custom_cluster_nonpos_power(self, db):
        bad = {"snapshots": [{"clusters": [
            {"delay_s": 0.0, "power_linear": 0.0, "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="power_linear 必须 > 0"):
            create_channel_asset(db, name="x", source_type="custom_static", payload=bad)

    def test_rt_empty_snapshots(self, db):
        with pytest.raises(ChannelAssetError, match="snapshots 须非空"):
            create_channel_asset(db, name="x", source_type="rt_dynamic",
                                 payload={"snapshots": []})

    def test_rt_empty_rays(self, db):
        with pytest.raises(ChannelAssetError, match="rays 须非空"):
            create_channel_asset(db, name="x", source_type="rt_dynamic",
                                 payload={"snapshots": [{"rays": []}]})

    def test_rt_ray_missing_required(self, db):
        bad = {"snapshots": [{"rays": [{"delay_s": 0.0, "power_linear": 1.0}]}]}
        with pytest.raises(ChannelAssetError, match=r"rays\[0\]\.aoa_deg 必填"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_rt_ray_negative_delay(self, db):
        bad = {"snapshots": [{"rays": [
            {"delay_s": -1e-9, "power_linear": 1.0, "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="delay_s 须 >= 0"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_rt_ray_nonpos_power(self, db):
        bad = {"snapshots": [{"rays": [
            {"delay_s": 0.0, "power_linear": -0.5, "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="power_linear 须 > 0"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_vendor_empty_scd_config(self, db):
        with pytest.raises(ChannelAssetError, match="scd_config 须非空"):
            create_channel_asset(db, name="x", source_type="vendor_file",
                                 payload={"scd_config": {}})


class TestTopPhysicalAndUniqueness:
    def test_center_freq_nonpos(self, db):
        with pytest.raises(ChannelAssetError, match="center_frequency_hz 必须 > 0"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD, center_frequency_hz=0.0)

    def test_velocity_not_three(self, db):
        with pytest.raises(ChannelAssetError, match=r"ue_velocity_mps 须 3 元素"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD, ue_velocity_mps=[1.0, 2.0])

    def test_name_unique(self, db):
        create_channel_asset(db, name="dup", source_type="standard_3gpp", payload=_STD_PAYLOAD)
        with pytest.raises(ChannelAssetError, match="已存在"):
            create_channel_asset(db, name="dup", source_type="rt_dynamic", payload=_RT_PAYLOAD)

    def test_canonical_name_unique(self, db):
        create_channel_asset(db, name="a1", source_type="vendor_file", payload=_VENDOR_PAYLOAD,
                             canonical_name="MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v1.smu")
        with pytest.raises(ChannelAssetError, match="canonical_name .* 已存在"):
            create_channel_asset(db, name="a2", source_type="vendor_file",
                                 payload=_VENDOR_PAYLOAD,
                                 canonical_name="MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v1.smu")

    def test_multiple_null_canonical_ok(self, db):
        # custom canonical_name=null, 多个 null 不冲突 (PG/SQLite 允许多 NULL unique)
        create_channel_asset(db, name="c1", source_type="custom_static", payload=_CUSTOM_PAYLOAD)
        create_channel_asset(db, name="c2", source_type="custom_static", payload=_CUSTOM_PAYLOAD)
        assert len(list_channel_assets(db)) == 2


class TestUpdateDeleteList:
    def test_update_name_and_payload(self, db):
        a = create_channel_asset(db, name="u1", source_type="custom_static",
                                 payload=_CUSTOM_PAYLOAD)
        new_payload = {"snapshots": [{"clusters": [
            {"delay_s": 1e-7, "power_linear": 0.7, "aoa_deg": 60, "aod_deg": 20}]}]}
        upd = update_channel_asset(db, a.id, name="u1-renamed", payload=new_payload)
        assert upd.name == "u1-renamed"
        assert upd.payload["snapshots"][0]["clusters"][0]["aoa_deg"] == 60

    def test_update_source_type_immutable(self, db):
        a = create_channel_asset(db, name="u2", source_type="custom_static",
                                 payload=_CUSTOM_PAYLOAD)
        with pytest.raises(ChannelAssetError, match="source_type 不可变更"):
            update_channel_asset(db, a.id, source_type="rt_dynamic")

    def test_update_payload_revalidated(self, db):
        a = create_channel_asset(db, name="u3", source_type="rt_dynamic", payload=_RT_PAYLOAD)
        with pytest.raises(ChannelAssetError, match="rays 须非空"):
            update_channel_asset(db, a.id, payload={"snapshots": [{"rays": []}]})

    def test_get_not_found(self, db):
        with pytest.raises(ChannelAssetNotFound):
            get_channel_asset(db, uuid.uuid4())

    def test_soft_delete(self, db):
        a = create_channel_asset(db, name="d1", source_type="standard_3gpp", payload=_STD_PAYLOAD)
        delete_channel_asset(db, a.id)
        assert list_channel_assets(db) == []
        assert len(list_channel_assets(db, include_inactive=True)) == 1

    def test_hard_delete(self, db):
        a = create_channel_asset(db, name="d2", source_type="standard_3gpp", payload=_STD_PAYLOAD)
        delete_channel_asset(db, a.id, soft=False)
        assert list_channel_assets(db, include_inactive=True) == []

    def test_list_by_source_type(self, db):
        create_channel_asset(db, name="s1", source_type="standard_3gpp", payload=_STD_PAYLOAD)
        create_channel_asset(db, name="r1", source_type="rt_dynamic", payload=_RT_PAYLOAD)
        rts = list_channel_assets(db, source_type="rt_dynamic")
        assert len(rts) == 1 and rts[0].name == "r1"


class TestBadNumericType:
    """payload 数值字段坏类型 → ChannelAssetError (400), 不是裸 TypeError (500) (Codex #173 P2)。

    payload 是 Dict[str, Any] (Pydantic 不校验内部), 坏 JSON 直达 service 数值比较。
    """

    def test_rt_ray_bad_delay_type(self, db):
        bad = {"snapshots": [{"rays": [
            {"delay_s": "bad", "power_linear": 1.0, "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="delay_s 须是数值"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_rt_ray_string_power(self, db):
        # Codex 明确举例: "power_linear": "1" (字符串伪装数字)
        bad = {"snapshots": [{"rays": [
            {"delay_s": 0.0, "power_linear": "1", "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="power_linear 须是数值"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_rt_ray_bool_rejected(self, db):
        # bool 是 int 子类但语义不对 → 拒
        bad = {"snapshots": [{"rays": [
            {"delay_s": 0.0, "power_linear": True, "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="power_linear 须是数值"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_custom_cluster_bad_type(self, db):
        # custom 簇复用 _validate_cluster (P2-15 假设数值), 坏类型 TypeError 被转 400
        bad = {"snapshots": [{"clusters": [
            {"delay_s": 0.0, "power_linear": "x", "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="类型非法"):
            create_channel_asset(db, name="x", source_type="custom_static", payload=bad)

    def test_top_physical_bad_type(self, db):
        with pytest.raises(ChannelAssetError, match="center_frequency_hz 须是数值"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD, center_frequency_hz="bad")

    def test_velocity_bad_element_type(self, db):
        with pytest.raises(ChannelAssetError, match=r"ue_velocity_mps\[1\] 须是数值"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD, ue_velocity_mps=[1.0, "y", 3.0])


class TestAPI:
    """API 层 (TestClient): 路由 + Pydantic + HTTP 状态码。"""

    def test_create_and_roundtrip(self, client):
        r = client.post("/api/v1/channel-assets", json={
            "name": "api-cus", "source_type": "custom_static", "payload": _CUSTOM_PAYLOAD})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["allowed_targets"] == ["asc_baked", "b2_parametric"]
        aid = body["id"]

        assert client.get(f"/api/v1/channel-assets/{aid}").status_code == 200
        assert len(client.get("/api/v1/channel-assets").json()) == 1

        r = client.put(f"/api/v1/channel-assets/{aid}", json={"description": "edited"})
        assert r.status_code == 200 and r.json()["description"] == "edited"

        assert client.delete(f"/api/v1/channel-assets/{aid}").status_code == 204
        assert client.get("/api/v1/channel-assets").json() == []

    def test_create_each_type_api(self, client):
        cases = [
            ("standard_3gpp", _STD_PAYLOAD, ["asc_baked"]),
            ("rt_dynamic", _RT_PAYLOAD, ["asc_baked", "b2_parametric"]),
            ("vendor_file", _VENDOR_PAYLOAD, ["gcm_native"]),
        ]
        for i, (st, pl, allowed) in enumerate(cases):
            r = client.post("/api/v1/channel-assets", json={
                "name": f"api-{i}", "source_type": st, "payload": pl})
            assert r.status_code == 201, r.text
            assert r.json()["allowed_targets"] == allowed

    def test_invalid_source_type_422(self, client):
        # Pydantic Literal 拦非法 source_type → 422
        r = client.post("/api/v1/channel-assets", json={
            "name": "bad", "source_type": "nope", "payload": {}})
        assert r.status_code == 422

    def test_bad_payload_400(self, client):
        # service 层 payload 校验失败 → 400
        r = client.post("/api/v1/channel-assets", json={
            "name": "bad2", "source_type": "custom_static",
            "payload": {"snapshots": [{"clusters": []}]}})
        assert r.status_code == 400
        assert "非空" in r.json()["detail"]

    def test_get_404(self, client):
        assert client.get(f"/api/v1/channel-assets/{uuid.uuid4()}").status_code == 404

    def test_bad_numeric_type_400_not_500(self, client):
        # Codex #173 P2 核心: 坏类型 payload → 400 (client-fixable), 不是 500 (裸 TypeError)
        r = client.post("/api/v1/channel-assets", json={
            "name": "badtype", "source_type": "rt_dynamic",
            "payload": {"snapshots": [{"rays": [
                {"delay_s": "bad", "power_linear": 1.0, "aoa_deg": 1, "aod_deg": 1}]}]}})
        assert r.status_code == 400, r.text
        assert "数值" in r.json()["detail"]
