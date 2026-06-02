"""P2-12 slice 2a: Standard Channel Definition 服务 测试.

钉死: create 从规范配置算标准名 (slice 1 契约, 单一真值); 字段非法 / 重复 → 业务错误;
list 按绑定过滤; get/delete。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
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


def _create(db, conn_id, **over):
    base = dict(
        instrument_connection_id=conn_id, band="N78", arfcn=640000,
        bandwidth_mhz=100, model="CDLC", scenario="UMa", mimo="4x4",
        polarization="DP", version=3,
    )
    base.update(over)
    return svc.create_scd(db, **base)


class TestCreate:
    def test_standard_name_computed_from_config(self, db):
        scd = _create(db, uuid4())
        # 标准名是规范配置的派生 (单一真值), 后端算 —— 不接受前端传名
        assert scd.standard_name == "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu"
        assert scd.association_source == "declared_only"
        assert scd.associated_file_path is None

    def test_pol_and_version_in_name(self, db):
        scd = _create(db, uuid4(), polarization="V", version=12)
        assert scd.standard_name.endswith("_V_v12.smu")

    def test_invalid_field_raises(self, db):
        # 字段含下划线 (会破坏反解) → StandardChannelError (API → 400)
        with pytest.raises(svc.StandardChannelError):
            _create(db, uuid4(), model="CDL_C")

    def test_duplicate_same_binding_raises(self, db):
        conn = uuid4()
        _create(db, conn)
        with pytest.raises(svc.StandardChannelError):
            _create(db, conn)  # 同绑定同标准名

    def test_same_config_different_binding_ok(self, db):
        # 同规范配置在不同 F64 绑定上各一份 (回答"一个配置多个物理文件")
        a = _create(db, uuid4())
        b = _create(db, uuid4())
        assert a.standard_name == b.standard_name
        assert a.instrument_connection_id != b.instrument_connection_id

    def test_different_version_not_duplicate(self, db):
        conn = uuid4()
        _create(db, conn, version=1)
        _create(db, conn, version=2)  # 不同版本 = 不同标准名 = 不冲突


class TestListGetDelete:
    def test_list_filtered_by_binding(self, db):
        c1, c2 = uuid4(), uuid4()
        _create(db, c1, version=1)
        _create(db, c1, version=2)
        _create(db, c2, version=1)
        assert len(svc.list_scds(db, instrument_connection_id=c1)) == 2
        assert len(svc.list_scds(db, instrument_connection_id=c2)) == 1
        assert len(svc.list_scds(db)) == 3  # 不过滤 = 全部

    def test_get_found(self, db):
        scd = _create(db, uuid4())
        assert svc.get_scd(db, scd.id).id == scd.id

    def test_get_missing_raises(self, db):
        with pytest.raises(svc.StandardChannelError):
            svc.get_scd(db, uuid4())

    def test_delete(self, db):
        scd = _create(db, uuid4())
        svc.delete_scd(db, scd.id)
        with pytest.raises(svc.StandardChannelError):
            svc.get_scd(db, scd.id)
