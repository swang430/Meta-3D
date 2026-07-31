"""P2-8 实时日志面板 /system-logs/tail 过滤语义 — 行为锁定。

核心契约 (2026-07-31 P2-11 现场实证的修复):
  ① 带过滤条件时窗口 = "最新 N 条匹配行", 不是"最新 N 行原始行" —
     低频 WARNING/ERROR 不允许被高频轮询 INFO 冲出窗口
     (P2-11 频率一致性失败三次落盘但面板不可见的根因);
  ② 无过滤条件时行为不变: 最新 N 行原始行;
  ③ 反向扫描以 _TAIL_SCAN_LIMIT 行封顶 (3s 轮询下最坏开销有界),
     total_lines_read 如实报实扫行数。

变异自验对应表 (⓪-④):
- 过滤挪回截尾之后 (旧实现) → test_level_filter_reaches_beyond_raw_window 红
- keyword 谓词不进扫描循环 → test_keyword_filter_reaches_beyond_raw_window 红
- 砍扫描上限 (无界扫全文件) → test_scan_limit_bounds_reverse_scan 红
- 改坏无过滤路径的截尾语义 → test_no_filter_keeps_raw_window_semantics 红
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
import app.api.system_logs as system_logs

TAIL_URL = f"{settings.api_v1_prefix}/system-logs/tail"


def _json_line(level: str, msg: str, logger: str = "app.services.instrument_hal_service") -> str:
    return json.dumps({
        "ts": "2026-07-31T10:00:00.000+08:00",
        "level": level,
        "logger": logger,
        "hal_mode": "mock",
        "session_id": "-",
        "instrument_id": "-",
        "msg": msg,
    }, ensure_ascii=False)


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def client():
    # 不进 lifespan (本端点只读文件, 不需要 DB/bootstrap)
    return TestClient(app)


class TestFilterDuringScan:
    def test_level_filter_reaches_beyond_raw_window(self, client, log_dir):
        """P2-11 场景复刻: 1 行 ERROR 后跟 300 行 INFO (失败行早已被冲出
        200 行原始窗口) — 单选 ERROR 过滤必须仍能捞到它。"""
        lines = [_json_line("ERROR", "[case-runner] execution X 相位 CONFIGURE 失败: 频率一致性失败",
                            logger="app.services.test_case_runner")]
        lines += [_json_line("INFO", f"[HAL] metrics poll {i}") for i in range(300)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        resp = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "level": "ERROR"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["filtered_count"] == 1
        assert any("相位 CONFIGURE 失败" in e["msg"] for e in body["entries"])
        # 如实报实扫行数 (301 行全扫完才凑到 1 条 ERROR)
        assert body["total_lines_read"] == 301

    def test_keyword_filter_reaches_beyond_raw_window(self, client, log_dir):
        """keyword 谓词同样在扫描中生效, 不止 level。"""
        lines = [_json_line("INFO", "唯一关键词 needle-P211")]
        lines += [_json_line("INFO", f"noise {i}") for i in range(300)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        resp = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "keyword": "needle-P211"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["filtered_count"] == 1
        assert "needle-P211" in body["entries"][0]["msg"]

    def test_no_filter_keeps_raw_window_semantics(self, client, log_dir):
        """回归门: 无过滤条件时行为与旧实现一致 — 最新 200 行原始行,
        时间正序, 扫描恰好 200 行。"""
        lines = [_json_line("INFO", f"seq-{i}") for i in range(250)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        resp = client.get(TAIL_URL, params={"filename": "app.log", "lines": 200})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_lines_read"] == 200
        assert body["filtered_count"] == 200
        # 是"最新的 200 行" (seq-50..seq-249), 且时间正序
        assert body["entries"][0]["msg"] == "seq-50"
        assert body["entries"][-1]["msg"] == "seq-249"

    def test_scan_limit_bounds_reverse_scan(self, client, log_dir, monkeypatch):
        """扫描上限行为门: 匹配行埋在上限之外 → 不返回, 且如实报
        实扫行数 = 上限 (不假装扫全了)。"""
        monkeypatch.setattr(system_logs, "_TAIL_SCAN_LIMIT", 500)
        lines = [_json_line("ERROR", "埋在上限外的失败行")]
        lines += [_json_line("INFO", f"noise {i}") for i in range(600)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        resp = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "level": "ERROR"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["filtered_count"] == 0
        assert body["total_lines_read"] == 500
