"""Database configuration and session management"""
import logging
import time
from sqlalchemy import create_engine, event, text
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


def _mask_db_url(url: str) -> str:
    """隐去 DB URL 里的密码: postgresql://user:pass@host/db → user:***@host。"""
    import re
    return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", url)


def preflight_database(
    eng=None,
    retries: int = 5,
    delay: float = 2.0,
    connect_timeout: int = 3,
    emit_fatal_log: bool = True,
) -> bool:
    """启动期 DB 连通性 fail-loud 预检（在 init_db 之前调用）。

    背景：重启后（尤其 macOS Docker Desktop）postgres 容器虽自启，host 发布端口可能
    未重新绑定 → 后端连不到 localhost:5432 → 所有 DB 端点 500、GUI 满屏"未就绪"，
    但根因被各处 try/except 吞掉，排查极慢。本预检主动连一次 DB：连不上时打一条
    **显著的、含修复命令的 ERROR banner**，把 20 分钟侦探活变 5 秒。

    设计：**不 raise**（与 init_db 一致续跑降级）—— 既不破坏 34 个跑 lifespan 的
    测试，也让 GUI 仍能加载。``retries`` 吸收重启后 DB 慢启动的 race（refused 是
    瞬时返回，retries 之间才 sleep）。

    返回 True=可达 / False=不可达。
    """
    eng = eng if eng is not None else engine
    # 用带 connect_timeout 的临时引擎探测: 黑洞网络 (丢包而非 refused) 下, eng.connect()
    # 会用驱动默认超时, 远超 delay、把启动卡死在 banner 之前 (Codex P2 #153, 对齐
    # check_db_state.py 的 connect_timeout=3)。SQLite 等本地后端无网络超时概念, 直接用 eng。
    if eng.url.get_backend_name().startswith("postgresql"):
        from sqlalchemy.pool import NullPool
        probe = create_engine(
            eng.url,
            connect_args={"connect_timeout": connect_timeout},
            poolclass=NullPool,
        )
    else:
        probe = eng
    last_err = None
    try:
        for attempt in range(retries + 1):
            try:
                with probe.connect() as conn:
                    conn.execute(text("SELECT 1"))
                if attempt:
                    logger.info(f"[db-preflight] 数据库在第 {attempt} 次重试后可达")
                return True
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < retries:
                    logger.warning(
                        f"[db-preflight] 数据库暂不可达 (尝试 {attempt + 1}/{retries + 1})，"
                        f"{delay}s 后重试…"
                    )
                    time.sleep(delay)
    finally:
        if probe is not eng:
            probe.dispose()
    if emit_fatal_log:
        masked = _mask_db_url(str(eng.url))
        bar = "=" * 72
        logger.error(bar)
        logger.error("[db-preflight] ❌ 数据库不可达 —— 后端将降级启动，所有 DB 端点会 500 / GUI 满屏未就绪")
        logger.error(f"  目标 : {masked}")
        logger.error(f"  原因 : {last_err}")
        logger.error("  常见根因: Docker Desktop / 机器重启后 postgres 容器端口转发未重建 (host:5432 未绑定)")
        logger.error("  修复 : ./scripts/db-up.sh    (确保容器起 + 端口真绑上，必要时 force-recreate 自愈)")
        logger.error("    或 : cd api-service && docker compose up -d --force-recreate postgres")
        logger.error(bar)
    return False


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
