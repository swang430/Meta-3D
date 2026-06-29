"""P2-16 S2 data migration (c8e1f5a2d4b7) 测试 — backfill channel_assets from custom/SCD。

R1 (最大盲区): pytest create_all 不跑迁移, 本迁移的数据搬运逻辑必须专门用 alembic runner +
预置数据覆盖。SQLite FK 默认 off → 可插 SCD 带任意 instrument_connection_id (不建真连接)。
"""
import json
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _cfg(db_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture
def migrated_to_s1(tmp_path):
    """upgrade 到 b7d2f4a9e1c3 (S1: channel_assets 表 + 旧表都在), 返回 (engine, cfg)。"""
    db_url = f"sqlite:///{tmp_path}/m.db"
    cfg = _cfg(db_url)
    command.upgrade(cfg, "b7d2f4a9e1c3")
    eng = create_engine(db_url)
    yield eng, cfg
    eng.dispose()


def _insert_custom(eng, cid, name):
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO custom_cdl_profiles (id, name, clusters, is_active, "
            "center_frequency_hz, is_los) VALUES (:id, :n, :cl, 1, :f, 0)"),
            {"id": cid, "n": name,
             "cl": json.dumps([{"delay_s": 0, "power_linear": 1, "aoa_deg": 1, "aod_deg": 1}]),
             "f": 3.5e9})


def _insert_scd(eng, sid, std_name):
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO standard_channel_definitions "
            "(id, band, arfcn, bandwidth_mhz, model, scenario, mimo, polarization, version, "
            "standard_name, instrument_connection_id, association_source, associated_file_path) "
            "VALUES (:id,'N78',640000,100,'CDLC','UMa','4x4','DP',1,:sn,:ic,'declared_only',:afp)"),
            {"id": sid, "sn": std_name, "ic": str(uuid.uuid4()), "afp": "/smu/x.smu"})


class TestBackfillMigration:
    def test_custom_and_scd_backfill(self, migrated_to_s1):
        eng, cfg = migrated_to_s1
        cid, sid = str(uuid.uuid4()), str(uuid.uuid4())
        _insert_custom(eng, cid, "MyCustom")
        _insert_scd(eng, sid, "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v1.smu")

        command.upgrade(cfg, "c8e1f5a2d4b7")  # backfill

        with eng.connect() as c:
            rows = {str(r[0]): r for r in c.execute(text(
                "SELECT id, source_type, name, canonical_name, payload, allowed_targets, "
                "associated_file_path FROM channel_assets")).fetchall()}
        # 复用 id: cid/sid 直接是 channel_asset id (零映射表 backward-compat 的基石)
        assert cid in rows and sid in rows
        cust = rows[cid]
        assert cust[1] == "custom_static" and cust[3] is None  # canonical null (族 C)
        assert json.loads(cust[4])["snapshots"][0]["clusters"][0]["aoa_deg"] == 1
        assert json.loads(cust[5]) == ["asc_baked", "b2_parametric"]
        ven = rows[sid]
        assert ven[1] == "vendor_file"
        assert ven[3] == "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v1.smu"  # canonical = standard_name
        assert json.loads(ven[4])["scd_config"]["arfcn"] == 640000
        assert json.loads(ven[5]) == ["gcm_native"]
        assert ven[6] == "/smu/x.smu"  # associated_file_path carry

    def test_idempotent(self, migrated_to_s1):
        eng, cfg = migrated_to_s1
        _insert_custom(eng, str(uuid.uuid4()), "C1")
        command.upgrade(cfg, "c8e1f5a2d4b7")
        with eng.connect() as c:
            n1 = c.execute(text("SELECT count(*) FROM channel_assets")).scalar()
        # downgrade + re-upgrade 不重复插 (复用 id 让幂等天然成立)
        command.downgrade(cfg, "b7d2f4a9e1c3")
        command.upgrade(cfg, "c8e1f5a2d4b7")
        with eng.connect() as c:
            n2 = c.execute(text("SELECT count(*) FROM channel_assets")).scalar()
        assert n1 == 1 and n2 == 1

    def test_name_dedup(self, migrated_to_s1):
        eng, cfg = migrated_to_s1
        _insert_custom(eng, str(uuid.uuid4()), "SameName")
        _insert_scd(eng, str(uuid.uuid4()), "SameName")
        command.upgrade(cfg, "c8e1f5a2d4b7")
        with eng.connect() as c:
            names = [r[0] for r in c.execute(text("SELECT name FROM channel_assets")).fetchall()]
        assert len(names) == 2 and len(set(names)) == 2  # 去重后唯一 (name unique 不炸)
        assert "SameName" in names and "SameName (migrated)" in names

    def test_downgrade_keeps_new_assets(self, migrated_to_s1):
        eng, cfg = migrated_to_s1
        _insert_custom(eng, str(uuid.uuid4()), "Old")
        command.upgrade(cfg, "c8e1f5a2d4b7")
        # 模拟 S2 后 operator 新建的 ChannelAsset (id 不在旧表)
        new_id = str(uuid.uuid4())
        with eng.begin() as c:
            c.execute(text(
                "INSERT INTO channel_assets (id, name, source_type, allowed_targets, payload, "
                "is_active) VALUES (:id, 'NewAsset', 'standard_3gpp', :at, :pl, 1)"),
                {"id": new_id, "at": json.dumps(["asc_baked"]),
                 "pl": json.dumps({"cdl_model_name": "CDL-A"})})
        command.downgrade(cfg, "b7d2f4a9e1c3")
        with eng.connect() as c:
            remaining = [str(r[0]) for r in c.execute(
                text("SELECT id FROM channel_assets")).fetchall()]
        assert new_id in remaining  # 精确反演: 新建的不被 downgrade 误删
