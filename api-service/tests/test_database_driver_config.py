"""客户新安装与旧连接配置必须选择同一已声明驱动。"""
import pytest
from sqlalchemy import create_engine

from app.config import Settings


@pytest.mark.parametrize("origin", ["default", "argument", "environment", "dotenv"])
def test_unspecified_postgres_driver_uses_installed_psycopg2(origin, monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = "postgresql://operator:p%40ss%2Fword@127.0.0.1:1/audit?connect_timeout=1"
    kwargs = {"_env_file": None}
    if origin == "argument":
        kwargs["database_url"] = url
    elif origin == "environment":
        monkeypatch.setenv("DATABASE_URL", url)
    elif origin == "dotenv":
        envfile = tmp_path / ".env"
        envfile.write_text("DATABASE_URL=" + url + "\n")
        kwargs["_env_file"] = envfile
    configured = Settings(**kwargs).database_url
    assert configured.startswith("postgresql+psycopg2://")
    if origin != "default":
        assert configured == url.replace("postgresql://", "postgresql+psycopg2://", 1)
    engine = create_engine(configured)
    try:
        assert engine.dialect.driver == "psycopg2"
    finally:
        engine.dispose()


@pytest.mark.parametrize("url", ["sqlite:///example.db", "postgresql+psycopg://u:p@localhost/db", "postgresql+psycopg2://u:p@localhost/db"])
def test_explicit_driver_is_not_silently_replaced(url):
    assert Settings(_env_file=None, database_url=url).database_url == url
