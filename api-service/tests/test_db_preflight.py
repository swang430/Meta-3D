"""#3 — DB 连通性启动预检 (fail-loud) 单测。

preflight_database 在 lifespan 里 init_db 之前跑: 连不上 DB 时打一条含可操作修复
命令的显著 banner, 把"满屏静默 500"变成一眼可见的根因。不 raise (续跑降级, 不破坏
34 个跑 lifespan 的测试 + GUI 仍可加载)。
"""
import logging

from sqlalchemy import create_engine

from app.db.database import preflight_database, _mask_db_url


def _reachable_engine():
    # SQLite 内存库永远可达 → 模拟"DB 正常"
    return create_engine("sqlite:///:memory:")


def _unreachable_engine():
    # 指向没人监听的端口 → connect 立即 refused (retries=0 不 sleep, 跑得快)
    return create_engine("postgresql://u:p@127.0.0.1:1/nodb")


class TestPreflightDatabase:
    def test_reachable_returns_true(self):
        assert preflight_database(eng=_reachable_engine(), retries=0) is True

    def test_unreachable_returns_false(self):
        assert (
            preflight_database(eng=_unreachable_engine(), retries=0, emit_fatal_log=False)
            is False
        )

    def test_unreachable_emits_actionable_banner(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.db"):
            ok = preflight_database(
                eng=_unreachable_engine(), retries=0, emit_fatal_log=True
            )
        assert ok is False
        txt = caplog.text
        # banner 必须可操作: 点明根因 + 给出修复命令
        assert "数据库不可达" in txt
        assert "db-up.sh" in txt
        assert "force-recreate" in txt

    def test_no_banner_when_emit_disabled(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.db"):
            preflight_database(eng=_unreachable_engine(), retries=0, emit_fatal_log=False)
        assert "数据库不可达" not in caplog.text

    def test_mask_db_url_hides_password(self):
        masked = _mask_db_url("postgresql://meta3d:secretpass@localhost:5432/meta3d_ota")
        assert "secretpass" not in masked
        assert "meta3d:***@localhost:5432" in masked
