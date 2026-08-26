"""P2-12 slice 2a: Standard Channel Definition 服务 测试.

钉死: create 从规范配置算标准名 (slice 1 契约, 单一真值); 字段非法 / 重复 / 绑定非法
→ 业务错误; list 按绑定过滤; get/delete。

绑定 (Codex #117): create 必须 resolve instrument_connection_id —— 缺失 / 非信道仿真器
类别都 fail-loud, 不让 stale id 在生产 PG 上变成 commit 时 IntegrityError, 也不让 SCD
挂到 available_channel_models projection 不被消费的别类连接上。
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.channel_emulator import normalize_channel_model_entries
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.services import standard_channel_service as svc

_STD_NAME = "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu"  # 默认 _create 配置的标准名

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _make_binding(db, *, category_key: str) -> UUID:
    """造一个 {category_key} 类别 + 一条连接, 返回 connection id。

    注意 category_key 生产 schema 全局 unique → 每个 key 每库只能一个 (单台信道仿真器)。
    """
    cat = InstrumentCategory(
        category_key=category_key,
        category_name=category_key,
        display_order=1,
        usage_phase=["test"],
        driver_mode="auto",
        is_active=True,
    )
    db.add(cat)
    db.flush()
    conn = InstrumentConnection(
        category_id=cat.id,
        endpoint="TCPIP0::192.168.0.132::inst0::INSTR",
        controller_ip="192.168.0.132",
        port=5025,
        protocol="VISA/SCPI",
        status="disconnected",
        created_by="test",
    )
    db.add(conn)
    db.flush()
    return conn.id


@pytest.fixture
def ce_binding(db) -> UUID:
    """唯一的 channelEmulator 连接 (生产里 category_key unique → 一台 F64)。"""
    return _make_binding(db, category_key="channelEmulator")


def _create(db, conn_id, **over):
    base = dict(
        instrument_connection_id=conn_id, radio_technology="nr5g",
        channel_kind="nr_arfcn", band="N78", arfcn=640000,
        lte_dl_earfcn=None,
        bandwidth_mhz=100, model="CDLC", scenario="UMa", mimo="4x4",
        polarization="DP", version=3,
    )
    base.update(over)
    return svc.create_scd(db, **base)


def _create_lte(db, conn_id, **over):
    base = dict(
        instrument_connection_id=conn_id, radio_technology="lte",
        channel_kind="lte_dl_earfcn", band="B3", arfcn=None,
        lte_dl_earfcn=1575, bandwidth_mhz=20, model="TDLA",
        scenario="Urban", mimo="2x2", polarization="DP", version=1,
    )
    base.update(over)
    return svc.create_scd(db, **base)


class TestCreate:
    def test_standard_name_computed_from_config(self, db, ce_binding):
        scd = _create(db, ce_binding)
        # 标准名是规范配置的派生 (单一真值), 后端算 —— 不接受前端传名
        assert scd.standard_name == "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu"
        assert scd.association_source == "declared_only"
        assert scd.associated_file_path is None

    def test_pol_and_version_in_name(self, db, ce_binding):
        scd = _create(db, ce_binding, polarization="V", version=12)
        assert scd.standard_name.endswith("_V_v12.smu")

    def test_invalid_field_raises(self, db, ce_binding):
        # 字段含下划线 (会破坏反解) → StandardChannelError (API → 400)
        with pytest.raises(svc.StandardChannelError):
            _create(db, ce_binding, model="CDL_C")

    def test_out_of_range_arfcn_raises(self, db, ce_binding):
        # Codex #118: arfcn 为正但超 NR-ARFCN 定义域 (>3279165) —— Pydantic gt=0 拦不住。
        # 必须 create 就 StandardChannelError (→ 400); 否则建出 zombie SCD, 到 associate
        # 重建 projection 时 nr_arfcn_to_freq_mhz 抛裸 ValueError → 路由不 catch → 500。
        with pytest.raises(svc.StandardChannelError):
            _create(db, ce_binding, arfcn=3279166)

    def test_max_valid_arfcn_ok(self, db, ce_binding):
        # 边界: NR-ARFCN 上界 3279165 仍合法 (守 off-by-one, 别把合法值误拒)
        scd = _create(db, ce_binding, arfcn=3279165)
        assert scd.arfcn == 3279165

    def test_duplicate_same_binding_raises(self, db, ce_binding):
        _create(db, ce_binding)
        with pytest.raises(svc.StandardChannelError):
            _create(db, ce_binding)  # 同绑定同标准名

    def test_missing_binding_raises(self, db):
        # Codex #117: stale / 填错的 id → StandardChannelError, 而非生产 PG commit 时
        # 未捕获的 IntegrityError (500)
        with pytest.raises(svc.StandardChannelError):
            _create(db, uuid4())

    def test_non_channel_emulator_binding_raises(self, db):
        # 存在但非 channelEmulator 的连接 → 拒绝 (其 available_channel_models projection
        # 不被 F64 流程消费, 挂上去是死数据)
        bs = _make_binding(db, category_key="baseStation")
        with pytest.raises(svc.StandardChannelError):
            _create(db, bs)

    def test_different_version_not_duplicate(self, db, ce_binding):
        _create(db, ce_binding, version=1)
        _create(db, ce_binding, version=2)  # 不同版本 = 不同标准名 = 不冲突

    def test_lte_identity_uses_distinct_column_and_name_family(self, db, ce_binding):
        scd = _create_lte(db, ce_binding)
        assert scd.radio_technology == "lte"
        assert scd.channel_kind == "lte_dl_earfcn"
        assert scd.arfcn is None
        assert scd.lte_dl_earfcn == 1575
        assert scd.standard_name == (
            "MF_LTE_B3_EARFCN1575_BW20_TDLA_Urban_2x2_DP_v1.smu"
        )

    def test_new_scd_requires_matching_rat_and_channel_kind(self, db, ce_binding):
        with pytest.raises(svc.StandardChannelError, match="channel_kind"):
            _create_lte(db, ce_binding, channel_kind="nr_arfcn")
        with pytest.raises(svc.StandardChannelError, match="lte_dl_earfcn"):
            _create_lte(db, ce_binding, lte_dl_earfcn=None)
        with pytest.raises(svc.StandardChannelError, match="arfcn"):
            _create_lte(db, ce_binding, arfcn=1575)


class TestListGetDelete:
    def test_list_filtered_by_binding(self, db, ce_binding):
        _create(db, ce_binding, version=1)
        _create(db, ce_binding, version=2)
        assert len(svc.list_scds(db, instrument_connection_id=ce_binding)) == 2
        # 别的 binding (无 SCD) → 空
        assert len(svc.list_scds(db, instrument_connection_id=uuid4())) == 0
        assert len(svc.list_scds(db)) == 2  # 不过滤 = 全部

    def test_get_found(self, db, ce_binding):
        scd = _create(db, ce_binding)
        assert svc.get_scd(db, scd.id).id == scd.id

    def test_get_missing_raises(self, db):
        with pytest.raises(svc.StandardChannelError):
            svc.get_scd(db, uuid4())

    def test_delete(self, db, ce_binding):
        scd = _create(db, ce_binding)
        svc.delete_scd(db, scd.id)
        with pytest.raises(svc.StandardChannelError):
            svc.get_scd(db, scd.id)


def _models(db, conn_id):
    """读 F64 绑定的 available_channel_models (原始存储形式, 带 scd_id 标记)。"""
    conn = db.get(InstrumentConnection, conn_id)
    return (conn.connection_params or {}).get("available_channel_models") or []


class TestAssociate:
    def test_associate_standard_named_file_ok(self, db, ce_binding):
        # 路径 a/b: 文件名 == 标准名, source=standard_generated
        scd = _create(db, ce_binding)
        out = svc.associate_file(
            db, scd.id, file_path=_STD_NAME, association_source="standard_generated"
        )
        assert out.associated_file_path == _STD_NAME
        assert out.association_source == "standard_generated"
        entries = _models(db, ce_binding)
        assert len(entries) == 1
        assert entries[0]["filename"] == _STD_NAME
        assert entries[0]["label"] == _STD_NAME
        assert entries[0]["scd_id"] == str(scd.id)

    def test_associate_vendor_file_matching_freq_ok(self, db, ce_binding):
        # 路径 c: 厂商文件名带匹配频率 token (3600M → ARFCN 640000 == 声明)
        scd = _create(db, ce_binding)
        out = svc.associate_file(
            db, scd.id, file_path="vendor_run_3600M.smu",
            association_source="vendor_associated",
        )
        assert out.associated_file_path == "vendor_run_3600M.smu"
        entries = _models(db, ce_binding)
        assert entries[0]["filename"] == "vendor_run_3600M.smu"
        assert entries[0]["label"] == _STD_NAME  # 标签仍是标准名

    def test_associate_vendor_file_unparseable_ok(self, db, ce_binding):
        # 厂商文件名无频率 token → cross-check 无从核对 → 放行 (声明是真值)
        scd = _create(db, ce_binding)
        out = svc.associate_file(
            db, scd.id, file_path="customer_channel.smu",
            association_source="vendor_associated",
        )
        assert out.associated_file_path == "customer_channel.smu"

    def test_projection_uses_declared_freq_not_parsed(self, db, ce_binding):
        # §9 关键: projection 频率来自声明 (权威), 非解析厂商名。
        # 厂商名无频率 token, 但归一后 entry 的频率必须是声明的 3600 / ARFCN 640000。
        scd = _create(db, ce_binding)
        svc.associate_file(
            db, scd.id, file_path="customer_channel.smu",
            association_source="vendor_associated",
        )
        normalised = normalize_channel_model_entries(_models(db, ce_binding))
        assert normalised[0]["center_frequency_mhz"] == 3600.0
        assert normalised[0]["nr_arfcn"] == 640000

    def test_lte_projection_preserves_typed_identity(self, db, ce_binding):
        scd = _create_lte(db, ce_binding)
        svc.associate_file(
            db, scd.id, file_path="customer_lte_channel.smu",
            association_source="vendor_associated",
        )
        raw = _models(db, ce_binding)[0]
        assert raw["radio_technology"] == "lte"
        assert raw["channel_kind"] == "lte_dl_earfcn"
        assert raw["lte_dl_earfcn"] == 1575
        assert "nr_arfcn" not in raw
        normalised = normalize_channel_model_entries([raw])[0]
        assert normalised["radio_technology"] == "lte"
        assert normalised["channel_kind"] == "lte_dl_earfcn"
        assert normalised["lte_dl_earfcn"] == 1575
        assert normalised["center_frequency_mhz"] == 1842.5

    def test_lte_association_rejects_software_owned_filename_with_wrong_bandwidth(
        self, db, ce_binding,
    ):
        scd = _create_lte(db, ce_binding)
        with pytest.raises(svc.StandardChannelError, match="bandwidth_mhz|BW"):
            svc.associate_file(
                db,
                scd.id,
                file_path="MF_LTE_B3_EARFCN1575_BW10_TDLA_Urban_2x2_DP_v1.smu",
                association_source="vendor_associated",
            )

    def test_lte_association_rejects_software_owned_filename_with_wrong_band(
        self, db, ce_binding,
    ):
        scd = _create_lte(db, ce_binding)
        with pytest.raises(svc.StandardChannelError, match="band"):
            svc.associate_file(
                db,
                scd.id,
                file_path="MF_LTE_B7_EARFCN1575_BW20_TDLA_Urban_2x2_DP_v1.smu",
                association_source="vendor_associated",
            )

    def test_associate_loose_freq_mismatch_passes(self, db, ce_binding):
        # 2026-07-03 现场实证: 厂商文件名频率是场景族标称会说谎 (UMa_3600M 工程实为
        # 3549.99 MHz) → source=loose 的不一致**放行** (真值=SCD 声明侧工程实测),
        # 只作 cross-check 提示不作拦截 (ChannelNameFreqCheck.must_fail 单点语义)。
        scd = _create(db, ce_binding)
        out = svc.associate_file(
            db, scd.id, file_path="legacy_3500M.smu",
            association_source="vendor_associated",
        )
        assert out.associated_file_path == "legacy_3500M.smu"

    def test_associate_standard_name_freq_mismatch_still_fails(self, db, ce_binding):
        # 软化后仍要守住的边界: MF_ 标准名 (source=standard) 与 SCD 强绑定,
        # 频率段不一致必是改名/错关联 → 仍 fail-loud (即使 source=vendor_associated)。
        scd = _create(db, ce_binding)
        wrong_freq_std = "MF_N77_650000_BW100_CDLC_UMa_4x4_DP_v1.smu"  # 650000 ≠ 声明 640000
        with pytest.raises(svc.StandardChannelError):
            svc.associate_file(
                db, scd.id, file_path=wrong_freq_std,
                association_source="vendor_associated",
            )

    def test_associate_standard_source_wrong_name_fails(self, db, ce_binding):
        # source=standard_generated 但文件名 != 标准名 (UMi vs UMa, 频率仍对) → fail-loud
        scd = _create(db, ce_binding)
        wrong = "MF_N78_640000_BW100_CDLC_UMi_4x4_DP_v3.smu"
        with pytest.raises(svc.StandardChannelError):
            svc.associate_file(
                db, scd.id, file_path=wrong, association_source="standard_generated"
            )

    def test_associate_invalid_source_fails(self, db, ce_binding):
        scd = _create(db, ce_binding)
        with pytest.raises(svc.StandardChannelError):
            svc.associate_file(
                db, scd.id, file_path=_STD_NAME, association_source="garbage"
            )

    def test_associate_missing_scd_raises(self, db):
        with pytest.raises(svc.StandardChannelNotFound):
            svc.associate_file(
                db, uuid4(), file_path=_STD_NAME,
                association_source="standard_generated",
            )

    def test_projection_preserves_legacy_entries(self, db, ce_binding):
        # §9: 存量手敲条目 (无 scd_id) 关联时保留, 逐步收敛
        conn = db.get(InstrumentConnection, ce_binding)
        conn.connection_params = {
            "available_channel_models": [
                {"filename": "legacy_handmade.smu", "label": "老条目"}
            ]
        }
        db.flush()
        scd = _create(db, ce_binding)
        svc.associate_file(
            db, scd.id, file_path=_STD_NAME, association_source="standard_generated"
        )
        entries = _models(db, ce_binding)
        names = {e["filename"] for e in entries}
        assert "legacy_handmade.smu" in names  # 存量保留
        assert _STD_NAME in names              # SCD 派生新增
        assert len(entries) == 2

    def test_reassociate_replaces_entry(self, db, ce_binding):
        # 改关联: 旧文件条目随 scd_id 丢弃重建, 不留 phantom
        scd = _create(db, ce_binding)
        svc.associate_file(
            db, scd.id, file_path=_STD_NAME, association_source="standard_generated"
        )
        svc.associate_file(
            db, scd.id, file_path="vendor_run_3600M.smu",
            association_source="vendor_associated",
        )
        entries = _models(db, ce_binding)
        scd_entries = [e for e in entries if e.get("scd_id") == str(scd.id)]
        assert len(scd_entries) == 1
        assert scd_entries[0]["filename"] == "vendor_run_3600M.smu"

    def test_delete_associated_scd_removes_projection_entry(self, db, ce_binding):
        # 删已关联 SCD → synced projection 同步移除其派生条目 (存量保留)
        conn = db.get(InstrumentConnection, ce_binding)
        conn.connection_params = {
            "available_channel_models": [{"filename": "legacy.smu", "label": "x"}]
        }
        db.flush()
        scd = _create(db, ce_binding)
        svc.associate_file(
            db, scd.id, file_path=_STD_NAME, association_source="standard_generated"
        )
        assert len(_models(db, ce_binding)) == 2
        svc.delete_scd(db, scd.id)
        entries = _models(db, ce_binding)
        assert len(entries) == 1
        assert entries[0]["filename"] == "legacy.smu"  # 存量保留, 派生移除


class TestResolveEmulationForMeasure:
    """P2-12 slice 4: resolve_emulation_for_measure — measure 用 scd_id 解析 .smu + 声明频率。"""

    def test_no_scd_id_returns_fallback(self, db):
        # scd_id 没给 → 裸 fallback emulation_file (路径 A / legacy), 无 SCD 频率
        path, freq = svc.resolve_emulation_for_measure(
            db, scd_id=None, fallback_emulation_file="D:\\legacy.smu"
        )
        assert path == "D:\\legacy.smu"
        assert freq is None

    def test_scd_unassociated_returns_none_path_with_decl_freq(self, db, ce_binding):
        # SCD 已声明未关联文件 → path None (caller GCM gate fail-loud 抓), 但有声明频率
        scd = _create(db, ce_binding)  # arfcn=640000, bw=100, declared_only
        path, freq = svc.resolve_emulation_for_measure(
            db, scd_id=str(scd.id), fallback_emulation_file="ignored.smu"
        )
        assert path is None
        assert freq is not None
        assert freq.center_arfcn == 640000 and freq.bandwidth_mhz == 100

    def test_scd_associated_returns_file_and_decl_freq(self, db, ce_binding):
        # 关联后 → path=实际 .smu, freq=SCD 声明 ARFCN (供 measure cross-check, 非文件名解析)
        scd = _create(db, ce_binding)
        svc.associate_file(
            db, scd.id, file_path="vendor_run_3600M.smu",
            association_source="vendor_associated",
        )
        path, freq = svc.resolve_emulation_for_measure(
            db, scd_id=str(scd.id), fallback_emulation_file=None
        )
        assert path == "vendor_run_3600M.smu"
        assert freq.center_arfcn == 640000  # SCD 声明值, 不是文件名 3600M 解析

    def test_lte_scd_returns_typed_earfcn_identity(self, db, ce_binding):
        scd = _create_lte(db, ce_binding)
        path, freq = svc.resolve_emulation_for_measure(
            db, scd_id=str(scd.id), fallback_emulation_file=None
        )

        assert path is None
        assert freq.radio_technology == "lte"
        assert freq.channel_kind == "lte_dl_earfcn"
        assert freq.lte_dl_earfcn == 1575
        assert freq.center_freq_mhz == 1842.5

    def test_scd_id_redirects_to_vendor_channel_asset(self, db, ce_binding):
        """P2-16 deprecate-legacy (消费收敛): scd_id 命中同 id vendor_file ChannelAsset →
        用 ChannelAsset 的 associated_file_path + scd_config 频率, **不读** legacy SCD 表。
        证 ChannelAsset 是收敛后单一真值源 (工作台编辑 .smu 关联落这里, 消除双副本 stale)。"""
        from app.models.channel_asset import ChannelAsset
        scd = _create(db, ce_binding)  # arfcn=640000, bw=100
        svc.associate_file(db, scd.id, file_path="legacy_old.smu",
                           association_source="vendor_associated")
        # 同 id vendor_file ChannelAsset (工作台编辑后的收敛真值源), 故意不同文件+频率
        db.add(ChannelAsset(
            id=scd.id, name="ca-vendor-收敛", source_type="vendor_file",
            payload={"scd_config": {
                "band": "N78", "arfcn": 620000, "bandwidth_mhz": 50,
                "model": "CDLC", "scenario": "UMa", "mimo": "4x4",
                "polarization": "DP", "version": 1,
            }},
            allowed_targets=["gcm_native"], associated_file_path="workbench_new.smu",
            is_active=True,
        ))
        db.commit()
        path, freq = svc.resolve_emulation_for_measure(
            db, scd_id=str(scd.id), fallback_emulation_file=None)
        assert path == "workbench_new.smu"       # ChannelAsset (非 legacy_old.smu)
        assert freq.center_arfcn == 620000       # ChannelAsset scd_config (非 SCD 640000)
        assert freq.bandwidth_mhz == 50

    def test_scd_id_rejects_inactive_vendor_asset_without_legacy_fallback(
        self, db, ce_binding
    ):
        """迁移后的资产一旦退役，不得回落到同 UUID 的 legacy SCD 重新执行。"""
        from app.models.channel_asset import ChannelAsset

        scd = _create(db, ce_binding)
        svc.associate_file(
            db,
            scd.id,
            file_path="legacy_old.smu",
            association_source="vendor_associated",
        )
        db.add(
            ChannelAsset(
                id=scd.id,
                name="retired-vendor",
                source_type="vendor_file",
                payload={"scd_config": {
                    "band": "N78", "arfcn": 620000, "bandwidth_mhz": 50,
                    "model": "CDLC", "scenario": "UMa", "mimo": "4x4",
                    "polarization": "DP", "version": 1,
                }},
                allowed_targets=["gcm_native"],
                associated_file_path="retired.smu",
                is_active=False,
            )
        )
        db.commit()

        with pytest.raises(svc.StandardChannelError, match="已退役"):
            svc.resolve_emulation_for_measure(
                db, scd_id=str(scd.id), fallback_emulation_file=None
            )

    def test_scd_not_found_raises(self, db):
        with pytest.raises(svc.StandardChannelNotFound):
            svc.resolve_emulation_for_measure(
                db, scd_id=str(uuid4()), fallback_emulation_file=None
            )

    def test_malformed_uuid_raises(self, db):
        with pytest.raises(ValueError):
            svc.resolve_emulation_for_measure(
                db, scd_id="not-a-uuid", fallback_emulation_file=None
            )
