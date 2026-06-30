"""P2-16 S2: ChannelAsset 前置解析层 (channel_asset_resolver) 测试。

resolve_channel_asset: channel_asset_id → engine_mode + 现有信道字段 (静态 source_type→engine
查表)。方案 A: 仅 channel_asset_id 显式给时介入。SQLite 隔离。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.channel_asset import ChannelAsset  # noqa: F401  确保表在 metadata
from app.services.channel_asset_service import create_channel_asset
from app.services.mimo_ota.channel_asset_resolver import (
    ChannelAssetResolveError,
    resolve_channel_asset,
)

_CLUSTER = {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 33.0, "aod_deg": 10.0}
_RAY = {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 1.0, "aod_deg": 1.0}
_SCD = {"band": "N78", "arfcn": 640000, "bandwidth_mhz": 100, "model": "CDLC",
        "scenario": "UMa", "mimo": "4x4", "polarization": "DP", "version": 1}


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


def _cfg(**kw):
    # mock config (MIMOOTAConfiguration 的相关字段子集)
    base = dict(channel_asset_id=None, cdl_profile_id=None, scd_id=None,
                cdl_model_name="UMa CDL-C NLOS", engine_mode="mimo_first_asc")
    base.update(kw)
    return SimpleNamespace(**base)


class TestResolver:
    def test_no_channel_asset_id_returns_none(self, db):
        # 方案 A: channel_asset_id 没给 → None (走旧字段路, 下游不变)
        assert resolve_channel_asset(db, _cfg()) is None
        # 即使旧 cdl_profile_id/scd_id 给了, 解析层也不介入 (方案 A 最小侵入)
        assert resolve_channel_asset(db, _cfg(cdl_profile_id=str(uuid.uuid4()))) is None
        assert resolve_channel_asset(db, _cfg(scd_id=str(uuid.uuid4()))) is None

    def test_custom_static(self, db):
        a = create_channel_asset(db, name="c", source_type="custom_static",
                                 payload={"snapshots": [{"clusters": [_CLUSTER]}]})
        r = resolve_channel_asset(db, _cfg(channel_asset_id=str(a.id)))
        assert r.engine_mode == "mimo_first_asc"
        assert r.clusters_payload[0]["aoa_deg"] == 33.0
        assert r.cdl_model_name is None and r.emulation_file is None

    def test_vendor_file(self, db):
        # vendor_file 直接给 .smu (associated_file_path), 不依赖 SCD twin (Codex #174 P2:
        # 新建的 vendor_file 没同 id SCD 行)
        a = create_channel_asset(db, name="v", source_type="vendor_file",
                                 payload={"scd_config": _SCD},
                                 associated_file_path="/smu/x.smu")
        r = resolve_channel_asset(db, _cfg(channel_asset_id=str(a.id)))
        assert r.engine_mode == "keysight_gcm"
        assert r.emulation_file == "/smu/x.smu"
        assert r.clusters_payload is None
        # scd_config 声明频率喂一致性网 (Codex #174 复查 P2: 防选错频率 .smu)
        assert r.scd_freq_identity is not None
        assert r.scd_freq_identity.center_arfcn == 640000

    def test_vendor_declared_only_no_file(self, db):
        # declared_only (无 associated_file_path) → emulation_file None (GCM gate fail-loud),
        # 不查 SCD 表 (resolver 纯从 ChannelAsset)
        a = create_channel_asset(db, name="vd", source_type="vendor_file",
                                 payload={"scd_config": _SCD})
        r = resolve_channel_asset(db, _cfg(channel_asset_id=str(a.id)))
        assert r.engine_mode == "keysight_gcm" and r.emulation_file is None

    def test_standard_3gpp(self, db):
        a = create_channel_asset(db, name="s", source_type="standard_3gpp",
                                 payload={"cdl_model_name": "UMa CDL-C NLOS"})
        r = resolve_channel_asset(db, _cfg(channel_asset_id=str(a.id)))
        assert r.engine_mode == "mimo_first_asc"
        assert r.cdl_model_name == "UMa CDL-C NLOS"

    def test_rt_dynamic(self, db):
        a = create_channel_asset(db, name="r", source_type="rt_dynamic",
                                 payload={"snapshots": [{"rays": [_RAY]}]})
        r = resolve_channel_asset(db, _cfg(channel_asset_id=str(a.id)))
        assert r.engine_mode == "b2_parametric_tdl"
        # 透传单快照 rays 到 B2 (Codex #174 复查 P2; 多快照轨迹/ACP 装配是 S3)
        assert r.rt_rays_payload[0]["aoa_deg"] == 1.0
        assert r.clusters_payload is None and r.emulation_file is None

    def test_rt_dynamic_multi_snapshot_fails_loud(self, db):
        # 多快照轨迹 RT 执行装配是 P2-16 S5; resolver 当前只透传单快照 → 多快照必须 fail-loud,
        # 否则静默取 snapshots[0], 用户 (S4-4 编辑器) 建轨迹信道却只按首快照测量 (Codex #184 P1)。
        a = create_channel_asset(db, name="rmulti", source_type="rt_dynamic",
                                 payload={"snapshots": [{"rays": [_RAY]}, {"rays": [_RAY]}]})
        with pytest.raises(ChannelAssetResolveError, match="多快照"):
            resolve_channel_asset(db, _cfg(channel_asset_id=str(a.id)))

    def test_invalid_id_fails_loud(self, db):
        with pytest.raises(ChannelAssetResolveError, match="无效/不存在"):
            resolve_channel_asset(db, _cfg(channel_asset_id=str(uuid.uuid4())))

    def test_bad_uuid_fails_loud(self, db):
        with pytest.raises(ChannelAssetResolveError):
            resolve_channel_asset(db, _cfg(channel_asset_id="not-a-uuid"))

    def test_inactive_asset_still_resolves(self, db):
        # 软删资产仍可解析 (历史执行引用有效); get_channel_asset 不过滤 is_active
        a = create_channel_asset(db, name="c2", source_type="custom_static",
                                 payload={"snapshots": [{"clusters": [_CLUSTER]}]})
        from app.services.channel_asset_service import delete_channel_asset
        delete_channel_asset(db, a.id)  # 软删
        r = resolve_channel_asset(db, _cfg(channel_asset_id=str(a.id)))
        assert r is not None and r.engine_mode == "mimo_first_asc"
