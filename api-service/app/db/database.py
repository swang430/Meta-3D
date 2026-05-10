"""Database configuration and session management"""
import logging
import time
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.config import settings

logger = logging.getLogger("app.db")

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    echo=False,  # 由 logging_config 的 sqlalchemy.engine handler 接管
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20
)

# ── SQLAlchemy 事件监听：慢查询告警 ────────────────────────────

@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """记录 SQL 执行开始时间，用于慢查询检测"""
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """检测慢查询 (>500ms) 并记录告警"""
    total = time.perf_counter() - conn.info["query_start_time"].pop(-1)
    total_ms = total * 1000

    if total_ms > 500:
        # 慢查询告警
        logger.warning(
            f"SLOW QUERY ({total_ms:.0f}ms): {statement}",
            extra={"duration_ms": round(total_ms, 1), "query": statement},
        )
    elif total_ms > 100:
        # 中等耗时提醒
        logger.info(
            f"DB query ({total_ms:.0f}ms): {statement}",
            extra={"duration_ms": round(total_ms, 1)},
        )


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection, connection_record):
    """数据库连接建立"""
    logger.info("DB connection established (pool)")


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_connection, connection_record, connection_proxy):
    """从连接池取出连接"""
    logger.debug("DB connection checked out from pool")


@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_connection, connection_record):
    """连接归还到连接池"""
    logger.debug("DB connection returned to pool")


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
        logger.debug("DB session committed")
    except Exception as e:
        # Rollback on any exception
        db.rollback()
        logger.warning(f"DB session rollback: {e}")
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize the database schema.

    Behavior depends on whether the DB is managed by alembic:

    * **Production Postgres** — has an ``alembic_version`` table. We
      skip ``Base.metadata.create_all()`` because it can only create
      missing tables; it never adds new columns to existing ones, which
      caused months of silent schema drift before alembic was wired up.
      Run ``alembic upgrade head`` from the deployment script to apply
      pending migrations.

    * **Test SQLite (no alembic state)** — falls back to
      ``create_all()`` so unit tests can bootstrap an empty in-memory
      or file-backed DB without running migrations.
    """
    import importlib
    import pkgutil

    import app.models as _models_pkg
    from sqlalchemy import inspect

    # Walk the package so Base.metadata sees every model, regardless of
    # whether the model is re-exported from app/models/__init__.py.
    for mod_info in pkgutil.iter_modules(_models_pkg.__path__):
        importlib.import_module(f"app.models.{mod_info.name}")

    inspector = inspect(engine)
    if "alembic_version" in inspector.get_table_names():
        logger.info(
            "Database is alembic-managed; skipping create_all(). "
            "Run 'alembic upgrade head' to apply pending migrations."
        )
        return

    logger.info(
        "No alembic_version table found — bootstrapping schema with "
        "create_all() (expected for test SQLite DBs)."
    )
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully")
