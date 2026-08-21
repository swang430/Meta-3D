"""P2-30 行为门：校准/方向图作业级仪表租约 —— 一次作业恰一次真取放。

可观察故障（roadmap F4）：租约只在最内层 primitive
`acquire_sa_power_via_ce_tone` 上取放，作业入口无一外层持有 → 每个测量点都
真建拆一次 F64 socket 并跑一遍 `_apply_session_reset`（清 6 个缓存字段）。
一次 32 探头 × 2 极化的 path-loss 作业 = 64 次建拆；方向图按角度点计更甚。

本文件的 5 条测试对应 5 个作业入口（三类作业）：

1. 方向图  `PatternCalibrationService._real_pattern_measurements`
2. QZ 校验 `QuietZoneValidationService.run_xpd_validation`
3. path-loss `ProbePathLossCalibrationService.start_calibration`
4. path-loss `ProbePathLossCalibrationService.start_calibration_for_lab_profile`
5. path-loss `MultiFrequencyPathLossService.calibrate_frequency_sweep`

断言是**行为**不是源码 grep：用引用计数桩替换 `instrument_test_lease`，
如实模拟 `hold()` 的嵌套语义（depth 0→1 = 真 acquire，1→0 = 真 release，
嵌套圈是 no-op），断言：

  A. 一次作业 `acquires == 1 and releases == 1`（任务级恰一次真取放）；
  B. 每次点级测量发生时 depth >= 1（所有点都在作业级租约持有期间）。

变异（摘掉任一入口的外层租约）→ 对应测试的断言 A 变红
（该入口退化回逐点取放，acquires == 点数 != 1）。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.schemas.probe_calibration import PolarizationType

# ---------------------------------------------------------------------------
# sqlite 内存库（同 tests/test_quiet_zone_validation.py 形态）
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P2-30 Lab")
    c.cable_sgh_to_sa_loss_db = 1.5  # 走 CE+SA 主路径
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ---------------------------------------------------------------------------
# 引用计数租约桩
# ---------------------------------------------------------------------------


class _CountingLease:
    """如实模拟 `hold()` 嵌套语义的计数桩。

    - `acquires` / `releases`：只数**最外层**进出（真实世界 = socket connect /
      release_to_local_control）。嵌套圈 depth>0 时进出不计 —— 这正是
      `hold()` 引用计数的行为（内层 no-op）。
    - `enters`：所有 `async with` 进入都计（含嵌套），用于确认内层那圈还在。
    - `purposes`：进入顺序的 purpose 记录（外层作业标识可核）。
    """

    def __init__(self) -> None:
        self.depth = 0
        self.acquires = 0
        self.releases = 0
        self.enters = 0
        self.purposes: list[str] = []

    @asynccontextmanager
    async def __call__(self, purpose: str, **kwargs):
        self.enters += 1
        self.purposes.append(purpose)
        if self.depth == 0:
            self.acquires += 1
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1
            if self.depth == 0:
                self.releases += 1


@pytest.fixture
def lease(monkeypatch):
    """替换租约源模块属性。

    所有站点（含最内层 wrapper）都是函数内
    `from app.services.instrument_test_lease import instrument_test_lease`
    的 lazy import —— patch 源模块一处即全覆盖。
    """
    stub = _CountingLease()
    monkeypatch.setattr(
        "app.services.instrument_test_lease.instrument_test_lease", stub
    )
    return stub


def _stub_inner_tone(monkeypatch, lease: _CountingLease) -> list[int]:
    """类级桩掉最内层 CE/SA 实测，记录每次点级测量发生时的租约 depth。

    wrapper `acquire_sa_power_via_ce_tone` 保持真跑 —— 它自己的那圈租约
    （嵌套时应为 no-op）也被计数桩如实观测。
    """
    from app.services import path_loss_calibration_service as pl_mod

    depths: list[int] = []

    async def _inner(self, **_kw):
        depths.append(lease.depth)
        return (-42.0, 0.1, "CE-D")

    monkeypatch.setattr(
        pl_mod.ProbePathLossCalibrationService,
        "_acquire_sa_power_via_ce_tone_inner",
        _inner,
    )
    return depths


def _stub_single_point_measurement(monkeypatch, lease: _CountingLease) -> list[int]:
    """类级桩掉单点测量 `_real_path_loss_measurement_via_ce_sa`。

    path-loss 三个作业入口逐点调它；桩内记录调用时的租约 depth。
    """
    from app.services import path_loss_calibration_service as pl_mod

    depths: list[int] = []

    async def _measure(self, probe_id, polarization, frequency_mhz, **_kw):
        depths.append(lease.depth)
        return pl_mod.PathLossMeasurement(
            probe_id=probe_id,
            polarization=polarization.value,
            path_loss_db=50.0,
            uncertainty_db=0.3,
        )

    monkeypatch.setattr(
        pl_mod.ProbePathLossCalibrationService,
        "_real_path_loss_measurement_via_ce_sa",
        _measure,
    )
    return depths


# ---------------------------------------------------------------------------
# 1. 方向图扫描：el × az 双重循环 = 一次作业
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pattern_scan_holds_one_task_level_lease(lease, monkeypatch):
    from app.services.probe_calibration_service import PatternCalibrationService

    depths = _stub_inner_tone(monkeypatch, lease)

    pos = MagicMock()
    pos.move_to = AsyncMock(return_value=True)
    fake_hal = MagicMock()
    fake_hal.drivers = {"positioner": pos}
    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service", lambda: fake_hal
    )

    svc = PatternCalibrationService()
    measurements = await svc._real_pattern_measurements(
        db=MagicMock(),
        probe_id=3,
        polarization=PolarizationType.V,
        azimuth_deg=[0.0, 180.0],
        elevation_deg=[45.0, 90.0, 135.0],
        frequency_mhz=3500.0,
        ce_port=None,
        ce_tx_power_dbm=-20.0,
        sgh_gain_dbi=10.0,
        chain_correction_db=0.0,
        measurement_distance_m=3.0,
        reference_antenna_id=None,
        turntable_id=None,
        warnings=[],
    )

    assert len(measurements) == 6
    assert len(depths) == 6
    assert lease.acquires == 1 and lease.releases == 1, (
        "一次方向图扫描（6 个角度点）必须只真取/放一次仪表控制权 —— "
        f"实际 acquires={lease.acquires} releases={lease.releases}，"
        "逐点建拆 F64 socket + _apply_session_reset 的故障还在"
    )
    assert all(d >= 1 for d in depths), (
        f"有角度点的测量发生在作业级租约之外: depths={depths}"
    )


# ---------------------------------------------------------------------------
# 2. QZ XPD 校验：co + cross 两次 = 一次作业
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xpd_validation_holds_one_task_level_lease(
    lease, db, chamber, monkeypatch
):
    from app.services.quiet_zone_validation_service import QuietZoneValidationService

    depths = _stub_inner_tone(monkeypatch, lease)

    svc = QuietZoneValidationService(db, use_mock=False)
    result = await svc.run_xpd_validation(
        chamber_id=chamber.id,
        frequency_mhz=3500.0,
        sgh_model="SGH-01",
        sgh_gain_dbi=10.0,
    )

    assert result.success
    assert len(depths) == 2
    assert lease.acquires == 1 and lease.releases == 1, (
        "一次 XPD 校验（co + cross 两次采集）必须只真取/放一次仪表控制权 —— "
        f"实际 acquires={lease.acquires} releases={lease.releases}"
    )
    assert all(d >= 1 for d in depths), (
        f"有采集发生在作业级租约之外: depths={depths}"
    )


# ---------------------------------------------------------------------------
# 3. path-loss 作业（chamber-keyed 旧门）：probe × pol 逐组 = 一次作业
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_loss_job_holds_one_task_level_lease(
    lease, db, chamber, monkeypatch
):
    from app.services import path_loss_calibration_service as pl_mod

    depths = _stub_single_point_measurement(monkeypatch, lease)

    svc = pl_mod.ProbePathLossCalibrationService(db, use_mock=False)
    result = await svc.start_calibration(
        chamber_id=chamber.id,
        frequency_mhz=3500.0,
        sgh_model="SGH-01",
        sgh_gain_dbi=10.0,
        probe_ids=[0, 1],
        polarizations=[PolarizationType.V, PolarizationType.H],
    )

    assert result.success
    assert len(depths) == 4  # 2 probes × 2 pols
    assert lease.acquires == 1 and lease.releases == 1, (
        "一次 path-loss 作业（2 探头 × 2 极化）必须只真取/放一次仪表控制权 —— "
        f"实际 acquires={lease.acquires} releases={lease.releases}；"
        "32×2 的真实作业就是 64 次 socket 建拆"
    )
    assert all(d >= 1 for d in depths), (
        f"有测量发生在作业级租约之外: depths={depths}"
    )


# ---------------------------------------------------------------------------
# 4. path-loss 作业（lab-profile 正门）：逐 chain = 一次作业
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lab_profile_path_loss_job_holds_one_task_level_lease(
    lease, db, chamber, monkeypatch
):
    from app.models.lab_profile import LabProfile
    from app.services import path_loss_calibration_service as pl_mod
    from app.services.calibration.rf_chain_resolver import (
        RFChainResolution,
        RFChainSpec,
    )

    depths = _stub_single_point_measurement(monkeypatch, lease)

    lab = LabProfile(name="P2-30 Lab Profile", chamber_config_id=chamber.id)
    db.add(lab)
    db.commit()
    db.refresh(lab)

    resolution = RFChainResolution(
        lab_profile_id=lab.id,
        chamber_id=chamber.id,
        topology_id=None,
        topology_name="p2-30-topo",
        operating_mode="mimo_4x4",
        chains=[
            RFChainSpec(chain_id="c0", ce_port="B1.1", probe_id=0, polarization="V"),
            RFChainSpec(chain_id="c1", ce_port="B1.2", probe_id=0, polarization="H"),
        ],
    )
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_a, **_k: resolution,
    )

    svc = pl_mod.ProbePathLossCalibrationService(db, use_mock=False)
    result = await svc.start_calibration_for_lab_profile(
        lab_profile_id=lab.id,
        operating_mode="mimo_4x4",
        frequency_mhz=3500.0,
        sgh_model="SGH-01",
        sgh_gain_dbi=10.0,
    )

    assert result.success
    assert len(depths) == 2  # 2 chains
    assert lease.acquires == 1 and lease.releases == 1, (
        "一次 lab-profile path-loss 作业（2 条 RF chain）必须只真取/放一次"
        f"仪表控制权 —— 实际 acquires={lease.acquires} releases={lease.releases}"
    )
    assert all(d >= 1 for d in depths), (
        f"有测量发生在作业级租约之外: depths={depths}"
    )


# ---------------------------------------------------------------------------
# 5. path-loss 扫频作业：probe × 频点 = 一次作业
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_frequency_sweep_holds_one_task_level_lease(
    lease, db, chamber, monkeypatch
):
    from app.services import path_loss_calibration_service as pl_mod

    depths = _stub_single_point_measurement(monkeypatch, lease)

    svc = pl_mod.MultiFrequencyPathLossService(db, use_mock=False)
    result = await svc.calibrate_frequency_sweep(
        chamber_id=chamber.id,
        probe_ids=[0, 1],
        polarization=PolarizationType.V,
        freq_start_mhz=3400.0,
        freq_stop_mhz=3600.0,
        freq_step_mhz=100.0,
        sgh_model="SGH-01",
        sgh_gain_dbi=10.0,
    )

    assert result.success
    assert len(depths) == 6  # 2 probes × 3 freq points
    assert lease.acquires == 1 and lease.releases == 1, (
        "一次扫频作业（2 探头 × 3 频点）必须只真取/放一次仪表控制权 —— "
        f"实际 acquires={lease.acquires} releases={lease.releases}"
    )
    assert all(d >= 1 for d in depths), (
        f"有频点测量发生在作业级租约之外: depths={depths}"
    )
