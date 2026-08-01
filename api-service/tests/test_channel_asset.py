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

    def test_vendor_top_freq_mismatch_rejected(self, db):
        """P3-15: 顶层声明 vs scd_config 漂移 fail-loud — 2026-07-02 现场形态
        (顶层 3.5 GHz vs arfcn=640000=3600 MHz): 显示读顶层、一致性网读 arfcn,
        两边不同 = 显示误导现场。顶层给了就必须与 SCD 一致。"""
        from app.services.channel_asset_service import update_channel_asset
        with pytest.raises(ChannelAssetError, match="center_frequency_hz.*不一致"):
            create_channel_asset(db, name="ven-drift", source_type="vendor_file",
                                 payload=_VENDOR_PAYLOAD,
                                 center_frequency_hz=3.5e9, bandwidth_mhz=100)
        with pytest.raises(ChannelAssetError, match="bandwidth_mhz.*不一致"):
            create_channel_asset(db, name="ven-drift2", source_type="vendor_file",
                                 payload=_VENDOR_PAYLOAD,
                                 center_frequency_hz=3600.0e6, bandwidth_mhz=40)
        # 一致 / 顶层留空 → 放行
        ok = create_channel_asset(db, name="ven-ok", source_type="vendor_file",
                                  payload=_VENDOR_PAYLOAD,
                                  center_frequency_hz=3600.0e6, bandwidth_mhz=100)
        create_channel_asset(db, name="ven-blank", source_type="vendor_file",
                             payload={"scd_config": {**_SCD, "version": 2}})
        # update 只改顶层也撞 scd 现值 (最终状态判, 不然 PATCH 绕过)
        with pytest.raises(ChannelAssetError, match="center_frequency_hz.*不一致"):
            update_channel_asset(db, ok.id, center_frequency_hz=3.5e9)

    def test_vendor_incomplete_scd_config(self, db):
        # S2: vendor scd_config 须完整 SCD schema (缺 mimo → 400, Codex #173 第5轮纳入 S2)
        incomplete = {k: v for k, v in _SCD.items() if k != "mimo"}
        with pytest.raises(ChannelAssetError, match=r"scd_config\.mimo 必填"):
            create_channel_asset(db, name="x", source_type="vendor_file",
                                 payload={"scd_config": incomplete})

    def test_vendor_scd_fractional_arfcn(self, db):
        # arfcn 是整数 (Dict payload 绕过 Pydantic int → 拒 fractional, Codex #174 复查 P2; int()
        # 否则静默 coerce 640000.7→640000)
        bad_scd = dict(_SCD, arfcn=640000.7)
        with pytest.raises(ChannelAssetError, match="arfcn 须整数"):
            create_channel_asset(db, name="x", source_type="vendor_file",
                                 payload={"scd_config": bad_scd})

    def test_vendor_invalid_scd_naming(self, db):
        # model 含连字符 → 命名契约 (alnum) 拒 (format_standard_channel_filename ValueError)
        bad_scd = dict(_SCD, model="CDL-C")
        with pytest.raises(ChannelAssetError, match="命名契约非法"):
            create_channel_asset(db, name="x", source_type="vendor_file",
                                 payload={"scd_config": bad_scd})

    def test_vendor_canonical_derived(self, db):
        # S2: vendor 不传 canonical → 从 scd_config 确定性派生 MF_ 名 (§3.2 族 A)
        a = create_channel_asset(db, name="vc", source_type="vendor_file",
                                 payload=_VENDOR_PAYLOAD)
        assert a.canonical_name == "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v1.smu"

    def test_standard_invalid_cdl_name(self, db):
        # 任意非空名不够, 须合法 3GPP CDL 名 (Codex #173 复查 P2; 复用 parse_cdl_model_name)
        with pytest.raises(ChannelAssetError, match="非法 CDL 名"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload={"cdl_model_name": "not-a-model"})

    def test_vendor_non_smu_path(self, db):
        # 给了 associated_file_path 须 .smu 后缀 (Codex #173 复查 P2)
        with pytest.raises(ChannelAssetError, match="smu 后缀"):
            create_channel_asset(db, name="x", source_type="vendor_file",
                                 payload=_VENDOR_PAYLOAD, associated_file_path="/x/chan.asc")

    def test_vendor_declared_only_ok(self, db):
        # vendor_file 无 associated_file_path = declared_only (SCD 合法中间态), 允许建
        a = create_channel_asset(db, name="vd", source_type="vendor_file", payload=_VENDOR_PAYLOAD)
        assert a.associated_file_path is None and a.allowed_targets == ["gcm_native"]


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

    def test_update_name_explicit_null_rejected(self, db):
        # 显式 PUT name=null → 400 不是 NOT NULL 500 (Codex #173 第四轮 P2;
        # exclude_unset 不排除显式 null, feedback_endpoint_null_field_cartesian)
        a = create_channel_asset(db, name="u-null", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD)
        with pytest.raises(ChannelAssetError, match="不能为空或 null"):
            update_channel_asset(db, a.id, name=None)

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

    def test_custom_cluster_bad_compared_field(self, db):
        # power_linear 被比较, 坏类型显式校验拦
        bad = {"snapshots": [{"clusters": [
            {"delay_s": 0.0, "power_linear": "x", "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="power_linear 须是数值"):
            create_channel_asset(db, name="x", source_type="custom_static", payload=bad)

    def test_custom_cluster_unchecked_field_bad_type(self, db):
        # aoa_deg 不被 _validate_cluster 比较 (只查存在) → 显式枚举校验才能拦坏类型静默持久化
        # (Codex #173 复查 P2: except TypeError 兜底漏掉不被比较的字段)
        bad = {"snapshots": [{"clusters": [
            {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": "bad", "aod_deg": 10}]}]}
        with pytest.raises(ChannelAssetError, match="aoa_deg 须是数值"):
            create_channel_asset(db, name="x", source_type="custom_static", payload=bad)

    def test_rt_ray_phase_rad_bad_type(self, db):
        # phase_rad optional 不被比较 → 显式枚举校验才能拦
        bad = {"snapshots": [{"rays": [
            {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 1, "aod_deg": 1, "phase_rad": "x"}]}]}
        with pytest.raises(ChannelAssetError, match="phase_rad 须是数值"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_custom_num_rays_fractional(self, db):
        # num_rays 整数计数, Dict payload 绕过 Pydantic int → 拒 1.5 (Codex #173 第三轮 P2)
        bad = {"snapshots": [{"clusters": [
            {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 1, "aod_deg": 1, "num_rays": 1.5}]}]}
        with pytest.raises(ChannelAssetError, match="num_rays 须整数"):
            create_channel_asset(db, name="x", source_type="custom_static", payload=bad)

    def test_custom_num_rays_integer_float_ok(self, db):
        # 20.0 (整数值 float) 接受, 跟 Pydantic int lax 一致
        a = create_channel_asset(db, name="nr", source_type="custom_static",
                                 payload={"snapshots": [{"clusters": [
                                     {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 1,
                                      "aod_deg": 1, "num_rays": 20.0}]}]})
        assert a.id is not None

    def test_payload_nan_rejected(self, db):
        # NaN 是合法 float 但非有限 → 拒 (Codex #173 第四轮 P2; JSON 允许 NaN literal)
        bad = {"snapshots": [{"clusters": [
            {"delay_s": 0.0, "power_linear": float("nan"), "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="有限数值"):
            create_channel_asset(db, name="x", source_type="custom_static", payload=bad)

    def test_payload_infinity_rejected(self, db):
        bad = {"snapshots": [{"rays": [
            {"delay_s": float("inf"), "power_linear": 1.0, "aoa_deg": 1, "aod_deg": 1}]}]}
        with pytest.raises(ChannelAssetError, match="有限数值"):
            create_channel_asset(db, name="x", source_type="rt_dynamic", payload=bad)

    def test_top_physical_bad_type(self, db):
        with pytest.raises(ChannelAssetError, match="center_frequency_hz 须是数值"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD, center_frequency_hz="bad")

    def test_k_factor_db_bad_type(self, db):
        # 主动 audit 补齐: k_factor_db 也须类型校验 (之前 _validate_top_physical 漏)
        with pytest.raises(ChannelAssetError, match="k_factor_db 须是数值"):
            create_channel_asset(db, name="x", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD, k_factor_db="bad")

    def test_k_factor_db_negative_ok(self, db):
        # k_factor_db 是 dB, 可负 (无 >0 约束)
        a = create_channel_asset(db, name="kf", source_type="standard_3gpp",
                                 payload=_STD_PAYLOAD, k_factor_db=-3.0)
        assert a.k_factor_db == -3.0

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
