"""F64 channelEmulator 历史端口迁移测试 (instruments seeder v2, Codex on PR #92).

背景: PROPSIM F64 的 ATE/SCPI 端口硬件固定 3334; 早期 seed 误写 5025/INSTR。
仅改 seeder 默认值只影响**新装**; 已 bootstrap 过的现场库 (旧连接) 不会自动
修复 —— 旧 _seed 对已存在的 InstrumentConnection 只走 skipped, 不更新端口。
结果: 驱动实连 3334, 但仪器目录 / readiness 仍显示 5025, 两者脱节。

seeder v2 加就地迁移修这条。这些测试钉死:
  - 选中 F64 + 端口仍是 5025 → 迁移到 3334 + raw SOCKET endpoint, 保留操作员 IP
  - 幂等: 第二次跑不再改 (端口已 3334)
  - 选中 FS16 (合法用 5025) → 不迁移 (避免误伤其它 channel emulator)
  - 端口已 3334 → 不动
  - 版本已 bump 到 2 (否则 runner 不会在已 bootstrap 的库上重跑这条 seeder)

验证方式: revert _migrate_f64_channel_emulator_port / version 后这些断言应失败。
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.services.bootstrap.instruments import _seed, instruments_seeder


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _make_legacy_channel_emulator(
    db,
    *,
    model_name: str,
    port: int = 5025,
    ip: str = "192.168.0.132",
    endpoint: str | None = None,
) -> InstrumentConnection:
    """造一个"老库"状态: channelEmulator 类别 + 指定型号(选中) + 一条旧连接行。"""
    cat = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        category_name_en="Channel Emulator",
        description="x",
        icon="IconWaveSine",
        display_order=1,
        usage_phase=["test"],
        driver_mode="auto",
        is_active=True,
    )
    db.add(cat)
    db.flush()
    model = InstrumentModel(
        category_id=cat.id,
        vendor="Keysight",
        model=model_name,
        full_name=model_name,
        capabilities={},
        display_order=0,
        is_available=True,
    )
    db.add(model)
    db.flush()
    cat.selected_model_id = model.id
    conn = InstrumentConnection(
        category_id=cat.id,
        endpoint=endpoint if endpoint is not None else f"TCPIP0::{ip}::inst0::INSTR",
        controller_ip=ip,
        port=port,
        protocol="VISA/SCPI",
        status="disconnected",
        created_by="test",
    )
    db.add(conn)
    db.flush()
    return conn


def _channel_emulator_conn(db) -> InstrumentConnection:
    cat = (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.category_key == "channelEmulator")
        .first()
    )
    return (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.category_id == cat.id)
        .first()
    )


class TestF64PortMigration:
    def test_legacy_5025_f64_migrated_to_3334_socket(self, db):
        _make_legacy_channel_emulator(
            db, model_name="PROPSIM F64", port=5025, ip="192.168.0.132"
        )
        result = _seed(db)
        conn = _channel_emulator_conn(db)
        assert conn.port == 3334
        assert conn.endpoint == "TCPIP0::192.168.0.132::3334::SOCKET"
        assert "SOCKET" in conn.protocol
        assert result.updated >= 1

    def test_preserves_operator_ip(self, db):
        # 迁移只改端口/transport, 不能把操作员配的 IP 覆盖回 seed 默认 100.21
        _make_legacy_channel_emulator(
            db, model_name="PROPSIM F64", port=5025, ip="10.20.30.40"
        )
        _seed(db)
        conn = _channel_emulator_conn(db)
        assert conn.port == 3334
        assert "10.20.30.40" in conn.endpoint

    def test_idempotent_second_run(self, db):
        _make_legacy_channel_emulator(db, model_name="PROPSIM F64", port=5025)
        _seed(db)
        second = _seed(db)
        conn = _channel_emulator_conn(db)
        assert conn.port == 3334
        assert second.updated == 0  # 已是 3334, 第二次不再迁移

    def test_fs16_5025_not_migrated(self, db):
        # FS16 合法使用 5025, 不应被 F64 端口迁移误伤
        _make_legacy_channel_emulator(db, model_name="PROPSIM FS16", port=5025)
        result = _seed(db)
        conn = _channel_emulator_conn(db)
        assert conn.port == 5025
        assert result.updated == 0

    def test_already_3334_untouched(self, db):
        _make_legacy_channel_emulator(
            db,
            model_name="PROPSIM F64",
            port=3334,
            endpoint="TCPIP0::192.168.0.132::3334::SOCKET",
        )
        result = _seed(db)
        conn = _channel_emulator_conn(db)
        assert conn.port == 3334
        assert result.updated == 0


def test_seeder_version_tracks_latest_connection_contract():
    # 没 bump 版本, runner (run_all) 会因 history.seeder_version >= version 跳过,
    # 迁移在已 bootstrap 的库上永不生效 (Codex on PR #92)。
    assert instruments_seeder.version == 3
