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
        instrument_connection_id=conn_id, band="N78", arfcn=640000,
        bandwidth_mhz=100, model="CDLC", scenario="UMa", mimo="4x4",
        polarization="DP", version=3,
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

    def test_associate_freq_mismatch_fails(self, db, ce_binding):
        # 厂商文件名解析出 3500M (ARFCN 633333) ≠ 声明 640000 → fail-loud
        scd = _create(db, ce_binding)
        with pytest.raises(svc.StandardChannelError):
            svc.associate_file(
                db, scd.id, file_path="legacy_3500M.smu",
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
