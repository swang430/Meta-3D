"""P2-32A 多频路损真实入口闭环回归。"""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.probe_calibration import MultiFrequencyPathLoss


def _multi_frequency_row(*, warnings=None) -> MultiFrequencyPathLoss:
    now = datetime.utcnow()
    return MultiFrequencyPathLoss(
        chamber_id=uuid4(),
        use_mock=False,
        probe_id=1,
        polarization="V",
        freq_start_mhz=3400.0,
        freq_stop_mhz=3500.0,
        freq_step_mhz=100.0,
        num_points=2,
        frequency_points_mhz=[3400.0, 3500.0],
        path_loss_db=[42.1, 42.4],
        uncertainty_db=[0.3, 0.3],
        calibrated_at=now,
        calibrated_by="p2-32a",
        valid_until=now + timedelta(days=30),
        status="valid",
        warnings=warnings,
    )


def test_multi_frequency_warnings_round_trip_and_preserve_historical_null():
    """删除 warnings 列或把历史 NULL 默认为 [] 时必须失败。"""
    engine = create_engine("sqlite:///:memory:")
    MultiFrequencyPathLoss.__table__.create(engine)

    with Session(engine) as db:
        current = _multi_frequency_row(warnings=["SA cleanup failed"])
        historical = _multi_frequency_row(warnings=None)
        historical.probe_id = 2
        db.add_all([current, historical])
        db.commit()
        db.expire_all()

        rows = {
            row.probe_id: row
            for row in db.query(MultiFrequencyPathLoss).order_by(
                MultiFrequencyPathLoss.probe_id
            )
        }

        assert rows[1].warnings == ["SA cleanup failed"]
        assert rows[2].warnings is None

