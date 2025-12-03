"""Database configuration and session management"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.config import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session.

    Usage in FastAPI endpoints:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
        # Commit any pending changes
        db.commit()
    except Exception:
        # Rollback on any exception
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize database (create all tables)"""
    # Import all models to ensure they are registered with SQLAlchemy
    from app.models.probe import Probe, ProbeConfiguration
    from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection, InstrumentLog
    from app.models.test_plan import TestPlan, TestCase, TestExecution, TestQueue, TestStep, TestSequence
    from app.models.calibration import CalibrationCertificate, QuietZoneCalibration, RepeatabilityTest, ComparabilityTest, SystemTRPCalibration, SystemTISCalibration
    from app.models.report import TestReport, ReportTemplate, ReportComparison, ReportSchedule

    Base.metadata.create_all(bind=engine)
