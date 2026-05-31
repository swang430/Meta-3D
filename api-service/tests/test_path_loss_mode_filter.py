"""P2-11 Phase 3 (Codex on PR #111): 路损 cert 按 switch operating_mode 过滤 测试.

钉死核心 bug: 多 operating mode 同频校准的 lab 里, 一个 '2x2' run 不能静默拿到最新的
'mimo_ota' / 'cal_power_sweep' cert (per-chain 线损会来自错的 RF 通路)。精确匹配优先,
退回 legacy 未标记 (NULL), 绝不返回 tagged-不同-mode 的 cert。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePathLossCalibration,
)
from app.services.path_loss_calibration_service import (
    ProbePathLossCalibrationService,
)

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


def _seed(db, chamber_id, *, mode, age_min: int = 1, freq_mhz: float = 3500.0):
    """Seed a VALID cert with given operating_mode; smaller age_min = newer."""
    now = datetime.utcnow()
    cal = ProbePathLossCalibration(
        chamber_id=chamber_id,
        frequency_mhz=freq_mhz,
        operating_mode=mode,
        probe_path_losses={"0": {"path_loss_db": 5.0}},
        sgh_model="ETS-Lindgren 3164-06",
        sgh_gain_dbi=8.0,
        status=CalibrationStatus.VALID.value,
        calibrated_at=now - timedelta(minutes=age_min),
        valid_until=now.replace(year=now.year + 1),
    )
    db.add(cal)
    db.commit()


def _svc(db):
    return ProbePathLossCalibrationService(db, use_mock=False)


class TestModeFilteredLookup:
    def test_exact_mode_match(self, db):
        cid = uuid4()
        _seed(db, cid, mode="2x2")
        cert = _svc(db).get_latest_calibration(cid, 3500.0, operating_mode="2x2")
        assert cert is not None and cert.operating_mode == "2x2"

    def test_tagged_different_mode_excluded(self, db):
        # 核心 Codex bug: 请求 2x2 但只有 mimo_ota cert → 不返回 (绝不静默用错 RF 通路)
        cid = uuid4()
        _seed(db, cid, mode="mimo_ota")
        cert = _svc(db).get_latest_calibration(cid, 3500.0, operating_mode="2x2")
        assert cert is None

    def test_exact_preferred_over_newer_different_mode(self, db):
        # 核心修复: 新 mimo_ota + 老 2x2, 请求 2x2 → 返回 2x2 (不被更新的 mimo_ota 抢走)
        cid = uuid4()
        _seed(db, cid, mode="2x2", age_min=60)        # 老
        _seed(db, cid, mode="mimo_ota", age_min=1)    # 新
        cert = _svc(db).get_latest_calibration(cid, 3500.0, operating_mode="2x2")
        assert cert is not None and cert.operating_mode == "2x2"

    def test_legacy_null_fallback(self, db):
        # legacy 未标记 cert (operating_mode IS NULL) → 找不到精确时退回 (向后兼容)
        cid = uuid4()
        _seed(db, cid, mode=None)
        cert = _svc(db).get_latest_calibration(cid, 3500.0, operating_mode="mimo_ota")
        assert cert is not None and cert.operating_mode is None

    def test_exact_preferred_over_newer_null(self, db):
        # 精确匹配优先于更新的 legacy NULL cert
        cid = uuid4()
        _seed(db, cid, mode="mimo_ota", age_min=60)   # 老 exact
        _seed(db, cid, mode=None, age_min=1)          # 新 NULL
        cert = _svc(db).get_latest_calibration(cid, 3500.0, operating_mode="mimo_ota")
        assert cert is not None and cert.operating_mode == "mimo_ota"

    def test_none_operating_mode_no_filter(self, db):
        # operating_mode=None → 不过滤, 返回最新 (任意 mode, 保持旧行为/向后兼容)
        cid = uuid4()
        _seed(db, cid, mode="cal_power_sweep")
        cert = _svc(db).get_latest_calibration(cid, 3500.0, operating_mode=None)
        assert cert is not None and cert.operating_mode == "cal_power_sweep"
