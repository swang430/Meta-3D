"""ChannelEngineClient non-ring probe geometry plumbing — P1-10 (2026-05-19).

Pins the cross-repo plumbing for ChannelEgine Phase 8 (Non-Ring Chamber):

1. ``ChannelEngineClient._build_probe_positions`` 跟 ``_build_payload``:
   - ring 路径 (默认): ``probe_positions=None``, chamber_config 不带
     ``probe_positions`` 字段, ``distribution = "ring"`` — 现有 8-probe
     ring lab smoke 完全向后兼容
   - custom / multi-ring 路径: 从 DB ``Probe`` 表读 per-probe (az, el),
     按 ``probe_number`` 排序, dual-polarized chamber 按位置 dedupe, 返回
     正好 ``num_probes`` 个 dict
   - fail-loud: 非 ring 但 DB 无 probe / probe 缺 azimuth / 位置数对不上
     ``num_probes`` 都 ``ValueError``

2. ``channel-engine-service`` 微服务 schema (``ChamberConfig``):
   - 接受新枚举 ``ring / multi-ring / custom`` (替换历史无人使用的 ``sphere``)
   - 非 ring distribution 必须显式传 ``probe_positions``, schema validator
     422; 长度跟 ``num_probes`` 不一致也 422

历史链路 (P0-7 + P1-7 测试覆盖 payload shape 已经够 phase 5/6 + standard
mode); 这里只补 P1-10 新加的几何透传维度。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberConfiguration, ProbeDistribution
from app.models.probe import Probe


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=_engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def db():
    s = _TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _make_chamber(
    db,
    distribution: str = ProbeDistribution.RING.value,
    num_probes: int = 4,
    dual_polarized: bool = False,
) -> ChamberConfiguration:
    chamber = ChamberConfiguration(
        id=uuid.uuid4(),
        name=f"p1-10-test-{distribution}",
        chamber_type="type_c",
        chamber_radius_m=2.0,
        quiet_zone_diameter_m=1.0,
        num_probes=num_probes,
        num_polarizations=2 if dual_polarized else 1,
        num_rings=1,
        probe_distribution=distribution,
        is_system_preset=False,
        is_active=True,
    )
    db.add(chamber)
    db.commit()
    db.refresh(chamber)
    return chamber


def _seed_probes(
    db,
    chamber: ChamberConfiguration,
    positions_az_el: list,
    dual_polarized: bool = False,
) -> None:
    """Insert one Probe row per physical probe (single-pol) or two rows
    per probe sharing the same position (dual-pol). Probe numbers are
    1-based, monotonically increasing.
    """
    probe_number = 1
    for az, el in positions_az_el:
        pols = ("V", "H") if dual_polarized else ("V",)
        for pol in pols:
            db.add(Probe(
                probe_number=probe_number,
                name=f"P{probe_number}-{pol}",
                ring=1,
                polarization=pol,
                position={"azimuth": az, "elevation": el, "radius": 2.0},
                is_active=True,
                chamber_config_id=chamber.id,
            ))
            probe_number += 1
    db.commit()


# ---------------------------------------------------------------------------
# (1) _build_probe_positions helper — unit-level
# ---------------------------------------------------------------------------


class TestBuildProbePositionsHelper:
    """Direct unit coverage of the DB-read + dedupe + validation helper."""

    def test_ring_distribution_returns_none_no_db_query(self, db):
        """Ring 路径必须保持现有 lab 8-probe smoke 行为 — 不查 DB, 不返回
        probe_positions, ChannelEgine 走 (p × 360°/N) 等距公式。
        """
        from app.services.channel_engine_client import ChannelEngineClient

        chamber = _make_chamber(db, distribution="ring", num_probes=8)
        # 故意不 seed Probe rows — ring 路径不应该查询 DB
        client = ChannelEngineClient(db=db)
        positions = client._build_probe_positions(chamber)
        assert positions is None

    def test_custom_distribution_reads_probes_in_probe_number_order(self, db):
        from app.services.channel_engine_client import ChannelEngineClient

        chamber = _make_chamber(db, distribution="custom", num_probes=4)
        _seed_probes(db, chamber, [
            (10.0, 0.0),
            (95.0, 0.0),
            (180.0, 15.0),
            (270.0, -15.0),
        ])
        client = ChannelEngineClient(db=db)
        positions = client._build_probe_positions(chamber)

        assert positions == [
            {"azimuth_deg": 10.0, "elevation_deg": 0.0},
            {"azimuth_deg": 95.0, "elevation_deg": 0.0},
            {"azimuth_deg": 180.0, "elevation_deg": 15.0},
            {"azimuth_deg": 270.0, "elevation_deg": -15.0},
        ]

    def test_dual_polarized_dedupes_v_h_pairs_by_position(self, db):
        """Dual-pol chamber: 每个物理 probe 有 V+H 两个 Probe row 共享 position;
        helper 必须按 (az, el) dedupe, 返回 num_probes 个物理位置, 不是 num_ports
        个 row 数。
        """
        from app.services.channel_engine_client import ChannelEngineClient

        chamber = _make_chamber(
            db, distribution="custom", num_probes=4, dual_polarized=True,
        )
        _seed_probes(
            db, chamber,
            [(0.0, 0.0), (90.0, 0.0), (180.0, 0.0), (270.0, 0.0)],
            dual_polarized=True,
        )
        # DB 里有 8 行 (V+H), 但物理只有 4 个 probe
        assert db.query(Probe).filter(
            Probe.chamber_config_id == chamber.id
        ).count() == 8

        client = ChannelEngineClient(db=db)
        positions = client._build_probe_positions(chamber)

        assert len(positions) == 4  # num_probes, not num_ports
        assert {tuple(p.items()) for p in positions} == {
            (("azimuth_deg", 0.0), ("elevation_deg", 0.0)),
            (("azimuth_deg", 90.0), ("elevation_deg", 0.0)),
            (("azimuth_deg", 180.0), ("elevation_deg", 0.0)),
            (("azimuth_deg", 270.0), ("elevation_deg", 0.0)),
        }

    def test_custom_distribution_no_probes_raises_valueerror(self, db):
        from app.services.channel_engine_client import ChannelEngineClient

        chamber = _make_chamber(db, distribution="custom", num_probes=4)
        client = ChannelEngineClient(db=db)
        with pytest.raises(ValueError, match="no active probes"):
            client._build_probe_positions(chamber)

    def test_probe_missing_azimuth_raises_valueerror(self, db):
        from app.services.channel_engine_client import ChannelEngineClient

        chamber = _make_chamber(db, distribution="custom", num_probes=2)
        # 故意一个有 azimuth 一个没有
        db.add(Probe(
            probe_number=1, name="P1-V", ring=1, polarization="V",
            position={"azimuth": 0.0, "elevation": 0.0, "radius": 2.0},
            is_active=True, chamber_config_id=chamber.id,
        ))
        db.add(Probe(
            probe_number=2, name="P2-V", ring=1, polarization="V",
            position={"elevation": 0.0, "radius": 2.0},  # 缺 azimuth
            is_active=True, chamber_config_id=chamber.id,
        ))
        db.commit()
        client = ChannelEngineClient(db=db)
        with pytest.raises(ValueError, match="no azimuth"):
            client._build_probe_positions(chamber)

    def test_count_mismatch_raises_valueerror(self, db):
        """num_probes spec'd as 8 但 DB 只有 4 — 半成品配置, fail-loud."""
        from app.services.channel_engine_client import ChannelEngineClient

        chamber = _make_chamber(db, distribution="custom", num_probes=8)
        _seed_probes(db, chamber, [
            (0.0, 0.0), (90.0, 0.0), (180.0, 0.0), (270.0, 0.0),
        ])
        client = ChannelEngineClient(db=db)
        with pytest.raises(ValueError, match="num_probes"):
            client._build_probe_positions(chamber)


# ---------------------------------------------------------------------------
# (2) _build_payload — chamber_config dict carries new fields
# ---------------------------------------------------------------------------


class TestBuildPayloadChamberConfig:
    """Pin the wire-format of chamber_config dict — what MIMO-First emits to
    the microservice. End-to-end: chamber + DB probes → payload['chamber_config'].
    """

    def _call_build_payload(self, db, chamber, probe_positions):
        from app.services.channel_engine_client import (
            AntennaConfig, CDLCluster, ChannelEngineClient,
        )
        client = ChannelEngineClient(db=db)
        return client._build_payload(
            chamber=chamber,
            calibration_entries=[],
            frequency_hz=3.5e9,
            clusters=[CDLCluster()],
            cdl_model_name="UMa CDL-C NLOS",
            pathloss_db=85.0,
            is_los=False,
            tx_antenna=AntennaConfig(),
            rx_antenna=AntennaConfig(),
            target_tx_power_dbm=0.0,
            target_rsrp_dbm=-85.0,
            target_snr_db=20.0,
            ue_velocity_kph=15.0,
            probe_positions=probe_positions,
        )

    def test_ring_payload_omits_probe_positions(self, db):
        chamber = _make_chamber(db, distribution="ring", num_probes=8)
        payload = self._call_build_payload(db, chamber, probe_positions=None)
        cc = payload["chamber_config"]
        assert cc["distribution"] == "ring"
        assert "probe_positions" not in cc, (
            "ring chamber 不应该传 probe_positions; 老版 ChannelEgine 收到会拒"
        )

    def test_custom_payload_carries_probe_positions(self, db):
        chamber = _make_chamber(db, distribution="custom", num_probes=4)
        positions = [
            {"azimuth_deg": 10.0, "elevation_deg": 0.0},
            {"azimuth_deg": 95.0, "elevation_deg": 0.0},
            {"azimuth_deg": 180.0, "elevation_deg": 15.0},
            {"azimuth_deg": 270.0, "elevation_deg": -15.0},
        ]
        payload = self._call_build_payload(db, chamber, probe_positions=positions)
        cc = payload["chamber_config"]
        assert cc["distribution"] == "custom"
        assert cc["probe_positions"] == positions

    def test_distribution_value_reflects_db_column(self, db):
        """chamber.probe_distribution 列 == payload chamber_config.distribution.
        防止有人改一边忘改另一边。
        """
        chamber = _make_chamber(db, distribution="multi-ring", num_probes=4)
        positions = [
            {"azimuth_deg": 0.0, "elevation_deg": 30.0},
            {"azimuth_deg": 120.0, "elevation_deg": 30.0},
            {"azimuth_deg": 240.0, "elevation_deg": 30.0},
            {"azimuth_deg": 0.0, "elevation_deg": -30.0},
        ]
        payload = self._call_build_payload(db, chamber, probe_positions=positions)
        assert payload["chamber_config"]["distribution"] == "multi-ring"


# ---------------------------------------------------------------------------
# (3) channel-engine-service schema validator
# ---------------------------------------------------------------------------
#
# 微服务 schema 在 sibling repo (channel-engine-service/app/...) 里, 跟
# api-service 的 `app` namespace 冲突 (两边 import path 都叫 `app.models.*`).
# pytest 是从 api-service 根跑的, `app.*` 直接 import 会拿到 api-service 的
# 同名 module 而不是微服务的. 用 importlib + 文件路径直接加载, 避开 namespace
# 冲突.
# ---------------------------------------------------------------------------


def _load_ce_service_schema():
    import importlib.util
    import os

    schema_path = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "channel-engine-service", "app", "models",
        "hardware_pipeline_models.py",
    ))
    spec = importlib.util.spec_from_file_location(
        "ce_service_hardware_pipeline_models", schema_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestChannelEngineServiceChamberConfigSchema:
    """微服务侧 schema 边界 — 422 失败比 ChannelEgine 内部 500 早, 错误信息也更清楚."""

    def test_ring_no_probe_positions_ok(self):
        mod = _load_ce_service_schema()
        mod.ChamberConfig(num_probes=8, radius_m=2.0, distribution="ring")

    def test_custom_without_probe_positions_rejected(self):
        from pydantic import ValidationError
        mod = _load_ce_service_schema()
        with pytest.raises(ValidationError, match="probe_positions"):
            mod.ChamberConfig(
                num_probes=8, radius_m=2.0, distribution="custom",
            )

    def test_custom_with_length_mismatch_rejected(self):
        from pydantic import ValidationError
        mod = _load_ce_service_schema()
        with pytest.raises(ValidationError, match="num_probes"):
            mod.ChamberConfig(
                num_probes=8, radius_m=2.0, distribution="custom",
                probe_positions=[
                    mod.ProbePosition(azimuth_deg=0.0),
                    mod.ProbePosition(azimuth_deg=90.0),
                ],
            )

    def test_custom_with_matching_positions_ok(self):
        mod = _load_ce_service_schema()
        positions = [
            mod.ProbePosition(azimuth_deg=p * 360.0 / 8) for p in range(7)
        ] + [mod.ProbePosition(azimuth_deg=180.0, elevation_deg=15.0)]
        cc = mod.ChamberConfig(
            num_probes=8, radius_m=2.0, distribution="custom",
            probe_positions=positions,
        )
        assert cc.distribution == "custom"
        assert len(cc.probe_positions) == 8

    def test_sphere_no_longer_accepted_alignment_with_channelegine(self):
        """历史 schema 列了 'sphere' 但跟 ChannelEgine 实际枚举对不上;
        现已替换为 'multi-ring' 跟 ChannelEgine Phase 8 三选一保持一致。
        没人 actually 传过 'sphere' (channel_engine_client.py 只写 'ring'),
        所以替换不破已有调用。
        """
        from pydantic import ValidationError
        mod = _load_ce_service_schema()
        with pytest.raises(ValidationError):
            mod.ChamberConfig(num_probes=8, radius_m=2.0, distribution="sphere")
