"""probe_number 按 chamber 局部唯一 (复合键) 的约束单测。

验证 model 层 UniqueConstraint(chamber_config_id, probe_number):
- 不同暗室可有相同 probe_number (局部编号);
- 同暗室同 probe_number 被拒 (IntegrityError)。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberConfiguration
from app.models.probe import Probe


@pytest.fixture
def session():
    # in-memory SQLite + StaticPool: create_all 与 session 共用同一连接/库
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


def _chamber(db, name: str) -> ChamberConfiguration:
    c = ChamberConfiguration(name=name, chamber_type="custom", chamber_radius_m=4.0)
    db.add(c)
    db.flush()
    return c


def _probe(chamber, n: int) -> Probe:
    return Probe(
        chamber_config_id=chamber.id,
        probe_number=n,
        name=f"{chamber.name} #{n}",
        ring=1,
        polarization="V",
        position={"azimuth": 0.0, "elevation": 0.0, "radius": 4.0},
    )


class TestProbeNumberPerChamber:
    def test_same_number_different_chambers_allowed(self, session):
        a = _chamber(session, "ChamberA")
        b = _chamber(session, "ChamberB")
        session.add(_probe(a, 1))
        session.add(_probe(b, 1))  # 同号 #1, 不同暗室 → 复合键放行
        session.commit()  # 不应抛
        assert session.query(Probe).filter(Probe.probe_number == 1).count() == 2

    def test_same_number_same_chamber_rejected(self, session):
        a = _chamber(session, "ChamberA")
        session.add(_probe(a, 1))
        session.commit()
        session.add(_probe(a, 1))  # 同暗室同号 → 违反复合唯一
        with pytest.raises(IntegrityError):
            session.commit()
