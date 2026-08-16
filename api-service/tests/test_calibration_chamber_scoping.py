"""校准链路 chamber-scoping foundation 单测。

覆盖两部分:
A. 测量路径活跃消费方 (probe_pattern.consumer): probe_id 在多暗室下不再全局唯一,
   consumer 给定 chamber_id 时必须只取 exact-chamber，**绝不**回退 NULL/legacy 或
   取其它暗室的方向图; chamber_id=None 时维持历史审计行为。
B. service writer/getter: execute_*_calibration 持久化 chamber_id; get_latest_calibration
   给定 chamber_id 时按暗室作用域过滤。

均用 in-memory SQLite + StaticPool (create_all 物化 model schema, 含新 chamber_id 列)。
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    ProbePattern,
    CalibrationStatus,
)
from app.schemas.probe_calibration import FrequencyRange, PolarizationType
from app.services.probe_calibration_service import AmplitudeCalibrationService
from app.services.probe_pattern.consumer import (
    _query_valid_pattern,
    estimate_quiet_zone_ripple_db,
    get_probe_gain_at_azimuth,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def _pattern(
    db,
    *,
    probe_id: int,
    chamber_id,
    peak_gain_dbi: float,
    freq: float = 3500.0,
    pol: str = "V",
    measured_at: datetime | None = None,
) -> ProbePattern:
    p = ProbePattern(
        probe_id=probe_id,
        chamber_id=chamber_id,
        use_mock=False,
        polarization=pol,
        frequency_mhz=freq,
        azimuth_deg=[0.0],
        elevation_deg=[90.0],
        gain_pattern_dbi=[peak_gain_dbi],
        peak_gain_dbi=peak_gain_dbi,
        valid_until=datetime.utcnow() + timedelta(days=365),
        status=CalibrationStatus.VALID.value,
    )
    if measured_at is not None:
        p.measured_at = measured_at
    db.add(p)
    db.flush()
    return p


# ==================== A. consumer (测量路径) ====================

class TestPatternConsumerChamberScoping:
    def test_prefers_exact_chamber_even_when_null_is_newer(self, session):
        """exact-chamber 优先级高于 measured_at: 即使 NULL 行更新, 也取本暗室的。"""
        cid = uuid.uuid4()
        now = datetime.utcnow()
        # NULL/legacy 行更新 (now), 本暗室行更旧 (now-10d)
        _pattern(session, probe_id=0, chamber_id=None, peak_gain_dbi=10.0, measured_at=now)
        _pattern(
            session, probe_id=0, chamber_id=cid, peak_gain_dbi=20.0,
            measured_at=now - timedelta(days=10),
        )
        hit = _query_valid_pattern(session, 0, "V", 3500.0, chamber_id=cid)
        assert hit is not None
        assert hit.peak_gain_dbi == 20.0  # 本暗室, 非更新的 NULL 行

    def test_does_not_fall_back_to_null_when_no_exact(self, session):
        """多暗室正式消费不能把来源未知的 NULL/legacy 当成本暗室校准。"""
        cid = uuid.uuid4()
        _pattern(session, probe_id=0, chamber_id=None, peak_gain_dbi=11.0)
        hit = _query_valid_pattern(session, 0, "V", 3500.0, chamber_id=cid)
        assert hit is None

    def test_never_returns_other_chamber(self, session):
        """只有**其它**暗室的数据时, chamber-scoped 查询必须返回 None (核心防错)。"""
        other = uuid.uuid4()
        target = uuid.uuid4()
        _pattern(session, probe_id=0, chamber_id=other, peak_gain_dbi=99.0)
        hit = _query_valid_pattern(session, 0, "V", 3500.0, chamber_id=target)
        assert hit is None

    def test_chamber_none_is_rejected_for_formal_consumption(self, session):
        """正式消费不得用 None 恢复跨暗室/legacy 查询。"""
        other = uuid.uuid4()
        _pattern(session, probe_id=0, chamber_id=other, peak_gain_dbi=42.0)
        with pytest.raises(ValueError, match="chamber_id is required"):
            _query_valid_pattern(session, 0, "V", 3500.0, chamber_id=None)

    def test_get_probe_gain_at_azimuth_is_chamber_scoped(self, session):
        """同一 probe 在两暗室有不同 peak gain, 取值随 chamber_id 切换。"""
        a, b = uuid.uuid4(), uuid.uuid4()
        _pattern(session, probe_id=0, chamber_id=a, peak_gain_dbi=15.0)
        _pattern(session, probe_id=0, chamber_id=b, peak_gain_dbi=99.0)
        assert get_probe_gain_at_azimuth(
            session, 4, 0.0, 3500.0, "V", chamber_id=a
        ) == 15.0
        assert get_probe_gain_at_azimuth(
            session, 4, 0.0, 3500.0, "V", chamber_id=b
        ) == 99.0

    def test_quiet_zone_ripple_excludes_other_chamber(self, session):
        """ripple 估计只统计本暗室探头, 不被其它暗室的宽 spread 污染。"""
        a, b = uuid.uuid4(), uuid.uuid4()
        # 本暗室 A: probe0=10, probe1=12 → ripple 2.0
        _pattern(session, probe_id=0, chamber_id=a, peak_gain_dbi=10.0)
        _pattern(session, probe_id=1, chamber_id=a, peak_gain_dbi=12.0)
        # 其它暗室 B: 宽 spread, 必须被排除
        _pattern(session, probe_id=0, chamber_id=b, peak_gain_dbi=50.0)
        _pattern(session, probe_id=1, chamber_id=b, peak_gain_dbi=99.0)
        ripple = estimate_quiet_zone_ripple_db(session, 4, 3500.0, "V", chamber_id=a)
        assert ripple == pytest.approx(2.0)


# ==================== B. service writer/getter ====================

class TestServiceWriterGetterChamberScoping:
    @pytest.mark.asyncio
    async def test_writer_persists_chamber_id_and_getter_filters(self, session):
        cid = uuid.uuid4()
        other = uuid.uuid4()
        svc = AmplitudeCalibrationService()

        result = await svc.execute_amplitude_calibration(
            db=session,
            probe_ids=[1],
            polarizations=[PolarizationType.V],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            calibrated_by="Test Engineer",
            use_mock=True,
            chamber_id=cid,
        )
        assert result.success is True

        # writer 持久化了 chamber_id
        rec = (
            session.query(ProbeAmplitudeCalibration)
            .filter(ProbeAmplitudeCalibration.probe_id == 1)
            .first()
        )
        assert rec is not None
        assert rec.chamber_id == cid

        # getter: 本暗室命中
        assert svc.get_latest_calibration(session, probe_id=1, chamber_id=cid) is not None
        # getter: 其它暗室不命中
        assert svc.get_latest_calibration(session, probe_id=1, chamber_id=other) is None
        # getter: 不传 chamber_id → 维持历史行为 (命中)
        assert svc.get_latest_calibration(session, probe_id=1) is not None
