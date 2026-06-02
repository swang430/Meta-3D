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
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.services import standard_channel_service as svc

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
