"""P2-8 实时日志面板 /system-logs/tail 过滤语义 — 行为锁定。

核心契约 (2026-07-31 P2-11 现场实证的修复):
  ① 带过滤条件时窗口 = "最新 N 条匹配行", 不是"最新 N 行原始行" —
     低频 WARNING/ERROR 不允许被高频轮询 INFO 冲出窗口
     (P2-11 频率一致性失败三次落盘但面板不可见的根因);
  ② 无过滤条件时行为不变: 最新 N 行原始行;
  ③ 反向扫描同时以 _TAIL_SCAN_LIMIT 行和单请求字节预算封顶
     (3s 轮询下最坏开销有界), total_lines_read 如实报实扫行数。

变异自验对应表 (⓪-④):
- 过滤挪回截尾之后 (旧实现) → test_level_filter_reaches_beyond_raw_window 红
- keyword 谓词不进扫描循环 → test_keyword_filter_reaches_beyond_raw_window 红
- 砍扫描上限 (无界扫全文件) → test_scan_limit_bounds_reverse_scan 红
- 砍字节上限 (无换行巨行整读) → test_byte_limit_rejects_unbounded_line 红
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
HISTORY_URL = f"{settings.api_v1_prefix}/system-logs/history"


def _json_line(
    level: str,
    msg: str,
    logger: str = "app.services.instrument_hal_service",
    session_id: str = "-",
    execution_id: str = "-",
) -> str:
    return json.dumps({
        "ts": "2026-07-31T10:00:00.000+08:00",
        "level": level,
        "logger": logger,
        "hal_mode": "mock",
        "session_id": session_id,
        "execution_id": execution_id,
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

    @pytest.mark.parametrize("params", [
        {},                                                   # 无过滤
        {"level": "WARNING,ERROR,CRITICAL"},                  # 「仅异常」
        {"level": "ERROR"},                                   # 单值
        {"session_id": "aaaa1111bbbb2222"},                   # 只看这一次请求
        {"level": "WARNING,ERROR,CRITICAL", "session_id": "aaaa1111bbbb2222"},
        {"keyword": "needle"},
        {"hal_mode": "real"},                                 # 仅 export 支持的维度
        {"level": "WARNING,ERROR", "keyword": "needle", "hal_mode": "mock"},
        {"execution_id": "exec-aaaa-1111"},                    # P1-36
        {"execution_id": "exec-aaaa-1111", "level": "ERROR"},  # P1-36 组合
    ])
    def test_tail_and_export_return_the_same_rows(self, client, log_dir, params):
        """**行为门**：同一组条件下，`/tail` 看到什么，`/export` 就该导出什么。

        内审 F1：本片把 `/export` 改成复用 `_entry_matches` 之后，守它的只有
        一道存在性门（"源码里有没有 `_entry_matches(`"）—— 内审造的变异把
        `session_id` 实参换成 `None`，屏幕剩 5 条、导出全量，而门**全绿**。
        那正是 P1-34 内审 F3 原样复发。存在性门只能当粗筛，**旁边必须配
        行为门**（CLAUDE.md ⓪④）。

        变异：`/export` 的 `_entry_matches(...)` 少传 / 错传任一实参 → 本门红。
        """
        lines = [
            _json_line("ERROR", "needle 错误", session_id="aaaa1111bbbb2222",
                       execution_id="exec-aaaa-1111"),
            _json_line("WARNING", "needle 告警", session_id="aaaa1111bbbb2222",
                       execution_id="exec-aaaa-1111"),
            _json_line("CRITICAL", "致命", session_id="ffff9999ffff9999"),
            _json_line("ERROR", "另一次请求的错误", session_id="ffff9999ffff9999"),
            _json_line("INFO", "needle 普通信息"),
            _json_line("DEBUG", "心跳"),
        ]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        tail = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, **params})
        assert tail.status_code == 200
        # /tail 不支持 hal_mode，它那侧的该维度恒不过滤 —— 只在 export 生效，
        # 所以对比时把 hal_mode 从 tail 的条件里剔除、改为在本地施加同样谓词。
        tail_rows = [e["raw"] for e in tail.json()["entries"]]
        hm = params.get("hal_mode")
        if hm:
            tail_rows = [
                r for r in tail_rows if json.loads(r).get("hal_mode", "").lower() == hm.lower()
            ]

        exp = client.get(
            f"{settings.api_v1_prefix}/system-logs/export/app.log", params=params)
        assert exp.status_code == 200
        export_rows = [l for l in exp.text.splitlines() if l.strip()]

        # /tail 是倒序（最新在前），/export 是文件顺序 —— 比**集合**与条数
        assert sorted(export_rows) == sorted(tail_rows), (
            f"条件 {params} 下 /tail 与 /export 结果不一致：\n"
            f"  tail   {len(tail_rows)} 条\n  export {len(export_rows)} 条"
        )

    def test_level_accepts_a_comma_separated_set(self, client, log_dir):
        """P1-35「仅异常」：`level=WARNING,ERROR,CRITICAL` 一次拿全。

        后端是**精确相等**不是门槛，所以没有任何单值能表达「WARNING 及以上」
        —— 选 ERROR 漏 WARNING、选 WARNING 漏 ERROR，故障分诊两边看不全。

        ⚠ 仍是**集合成员**判断，不是序数比较：`ZoneLogsAlerts`（P2-19）的
        跨流去重依赖「不同 level 的流天然不相交」。
        """
        lines = [
            _json_line("ERROR", "错误一条"),
            _json_line("WARNING", "告警一条"),
            _json_line("CRITICAL", "致命一条"),
        ]
        lines += [_json_line("INFO", f"噪音 {i}") for i in range(50)]
        lines += [_json_line("DEBUG", f"心跳 {i}") for i in range(50)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        body = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200,
            "level": "WARNING,ERROR,CRITICAL"}).json()
        assert body["filtered_count"] == 3, "三个级别没一次拿全"
        assert {e["level"] for e in body["entries"]} == {"ERROR", "WARNING", "CRITICAL"}

        # 单值行为不能被破坏（ZoneLogsAlerts 还在用）
        one = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "level": "ERROR"}).json()
        assert one["filtered_count"] == 1
        assert one["entries"][0]["level"] == "ERROR"

        # 不是门槛：要 INFO 就只给 INFO，不带上更高的级别
        info = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "level": "INFO"}).json()
        assert {e["level"] for e in info["entries"]} == {"INFO"}, (
            "level 变成序数门槛了 —— ZoneLogsAlerts 的跨流去重会出错"
        )

    def test_level_filter_keeps_matching_parent_traceback_group(self, client, log_dir):
        lines = [
            _json_line("ERROR", "boom", execution_id="exec-trace"),
            "Traceback (most recent call last):",
            "ValueError: broken",
            _json_line("INFO", "later noise"),
        ]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        tail = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "level": "ERROR",
        })
        assert tail.status_code == 200
        entries = tail.json()["entries"]
        assert [entry["level"] for entry in entries] == ["ERROR", "RAW", "RAW"]
        assert [entry["msg"] for entry in entries[1:]] == lines[1:3]
        assert {entry["execution_id"] for entry in entries} == {"exec-trace"}

        exported = client.get(
            f"{settings.api_v1_prefix}/system-logs/export/app.log",
            params={"level": "ERROR"},
        )
        assert exported.status_code == 200
        assert exported.text.splitlines() == lines[:3]

    def test_execution_id_filter_pulls_one_test_run(self, client, log_dir):
        """P1-36「只看这次执行」——**过滤真的起作用**，不只是"两端一致"。

        变异 M9 实证：把谓词里 execution_id 那两行删掉，`/tail` 与 `/export`
        会**一起**不过滤 → 等价性门照绿。等价 ≠ 正确，必须单独验它真的筛掉了。

        场景：一次执行的 3 条日志（跨 2 个不同请求）+ 另一次执行的 2 条 +
        200 行无关噪音 —— 按执行 id 必须**完整**捞回 3 条、不夹带另一次。
        """
        mine, other = "exec-1111-aaaa", "exec-2222-bbbb"
        lines = [
            _json_line("INFO", "发起", logger="app.audit", session_id="req-a", execution_id=mine),
            _json_line("INFO", "相位 CONFIGURE", session_id="req-a", execution_id=mine),
            # 同一次执行、**另一个请求**（查询进度）—— 两个 id 的关系全在这
            _json_line("INFO", "查进度", logger="app.audit", session_id="req-b", execution_id=mine),
            _json_line("INFO", "别的执行 1", session_id="req-c", execution_id=other),
            _json_line("ERROR", "别的执行 2", session_id="req-c", execution_id=other),
        ]
        lines += [_json_line("INFO", f"无关噪音 {i}") for i in range(200)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        body = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "execution_id": mine}).json()
        assert body["filtered_count"] == 3, "这次执行的链没被完整捞回来"
        assert {e["execution_id"] for e in body["entries"]} == {mine}, "夹带了别的执行"
        # 关键：同一次执行**跨了两个请求** —— 这正是两个 id 必须分开的理由
        assert {e["session_id"] for e in body["entries"]} == {"req-a", "req-b"}

    def test_execution_id_filter_is_exact_not_substring(self, client, log_dir):
        """前缀相同的两次执行不能互相夹带。"""
        lines = [
            _json_line("INFO", "我的", execution_id="exec-1111"),
            _json_line("INFO", "别人的", execution_id="exec-11110000"),
        ]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
        body = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "execution_id": "exec-1111"}).json()
        assert body["filtered_count"] == 1
        assert body["entries"][0]["msg"] == "我的"

    def test_session_id_filter_pulls_one_request_chain(self, client, log_dir):
        """P1-34「只看这一次请求」依赖的就是这条路径（内审 F9：此前零覆盖）。

        这个参数在 P1-34 之前**从未被真正使用过** —— 全仓没有任何地方
        `current_session_id.set()`，日志里 `session_id` 100% 是 `-`，
        所以"过滤得对不对"从来没被验证过。现在 GUI 接上了它。

        场景：一次操作产生 3 条日志（HTTP 审计 + runner + HAL），被 300 行
        别的请求冲出原始窗口 —— 按 id 过滤必须把这 3 条**完整**捞回来，
        且不夹带别人的行。
        """
        mine, other = "a1b2c3d4", "ffff0000"
        lines = [
            _json_line("INFO", "POST /api/v1/x → 200", logger="app.audit", session_id=mine),
            _json_line("INFO", "[case-runner] 相位 CONFIGURE 开始", session_id=mine),
            _json_line("INFO", "[HAL] 下发 SCPI", session_id=mine),
        ]
        lines += [_json_line("INFO", f"别人的请求 {i}", session_id=other) for i in range(300)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        resp = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "session_id": mine})
        assert resp.status_code == 200
        body = resp.json()
        assert body["filtered_count"] == 3, "链条没被完整捞回来"
        assert {e["session_id"] for e in body["entries"]} == {mine}, "夹带了别的请求的行"
        assert body["total_lines_read"] == 303

    def test_session_id_filter_is_exact_not_substring(self, client, log_dir):
        """id 是 8 位 hex，前缀相同的两个请求不能互相夹带。"""
        lines = [
            _json_line("INFO", "我的", session_id="a1b2c3d4"),
            _json_line("INFO", "别人的", session_id="a1b2c3d4ff"),
            _json_line("INFO", "也是别人的", session_id="a1b2"),
        ]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        body = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "session_id": "a1b2c3d4"}).json()
        assert body["filtered_count"] == 1
        assert body["entries"][0]["msg"] == "我的"

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

    def test_byte_limit_rejects_unbounded_line(self, client, log_dir, monkeypatch):
        """损坏的无换行巨行不得让 3s 轮询端点把整文件读进内存。"""
        monkeypatch.setattr(
            system_logs, "_REVERSE_SCAN_BYTE_LIMIT", 128, raising=False,
        )
        (log_dir / "app.log").write_bytes(b"x" * 4096)

        response = client.get(TAIL_URL, params={"filename": "app.log", "lines": 1})

        assert response.status_code == 422
        assert "128" in response.json()["detail"]

    def test_byte_limit_rejects_split_traceback_group(
        self, client, log_dir, monkeypatch,
    ):
        """超大 traceback 逻辑组不能跨页拆开后静默丢掉前半段续行。"""
        monkeypatch.setattr(
            system_logs, "_REVERSE_SCAN_BYTE_LIMIT", 256, raising=False,
        )
        lines = [_json_line("ERROR", "parent boom", execution_id="exec-trace")]
        lines += [f"  File trace_{index}.py, line {index}" for index in range(80)]
        (log_dir / "app.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8",
        )

        response = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 1, "level": "ERROR",
        })

        assert response.status_code == 422
        assert "256" in response.json()["detail"]
        assert "日志组" in response.json()["detail"]


class TestHistoryPagination:
    def test_tail_cursor_loads_older_rows_without_overlap(self, client, log_dir):
        """最新 200 条之后还能继续读到前 50 条，且不重不漏。"""
        lines = [_json_line("INFO", f"seq-{i}") for i in range(250)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        tail = client.get(TAIL_URL, params={"filename": "app.log", "lines": 200})
        assert tail.status_code == 200
        tail_body = tail.json()
        assert tail_body["has_older"] is True
        assert tail_body["older_cursor"]

        history = client.get(HISTORY_URL, params={
            "filename": "app.log",
            "lines": 200,
            "cursor": tail_body["older_cursor"],
        })
        assert history.status_code == 200
        history_body = history.json()
        assert [e["msg"] for e in history_body["entries"]] == [
            f"seq-{i}" for i in range(50)
        ]
        assert history_body["has_older"] is False
        assert history_body["older_cursor"] is None

        combined = history_body["entries"] + tail_body["entries"]
        assert [e["msg"] for e in combined] == [f"seq-{i}" for i in range(250)]

    def test_empty_filtered_page_still_advances_cursor(
        self, client, log_dir, monkeypatch,
    ):
        """稀疏过滤不得卡死在同一扫描窗口；空页也要能继续向前。"""
        monkeypatch.setattr(system_logs, "_TAIL_SCAN_LIMIT", 3)
        monkeypatch.setattr(system_logs, "_HISTORY_SCAN_LIMIT", 4)
        lines = [_json_line("ERROR", "old-target")]
        lines += [_json_line("INFO", f"noise-{i}") for i in range(12)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        page = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 2, "level": "ERROR",
        }).json()
        assert page["entries"] == []
        cursors = [page["older_cursor"]]

        first_history_page = True
        while page["has_older"]:
            response = client.get(HISTORY_URL, params={
                "filename": "app.log",
                "lines": 2,
                "level": "ERROR",
                "cursor": page["older_cursor"],
            })
            assert response.status_code == 200
            page = response.json()
            if first_history_page:
                assert page["total_lines_read"] == 4, (
                    "历史端点误用了实时 tail 的较小扫描预算"
                )
                first_history_page = False
            if page["older_cursor"]:
                assert page["older_cursor"] not in cursors, "空页没有推进游标"
                cursors.append(page["older_cursor"])

        assert [e["msg"] for e in page["entries"]] == ["old-target"]

    def test_chunk_boundary_and_missing_final_newline_do_not_break_pages(
        self, client, log_dir,
    ):
        long_msg = "x" * 9000
        lines = [_json_line("INFO", "first"), _json_line("INFO", long_msg),
                 _json_line("INFO", "last")]
        (log_dir / "app.log").write_text("\n".join(lines), encoding="utf-8")

        tail = client.get(TAIL_URL, params={"filename": "app.log", "lines": 1}).json()
        assert [e["msg"] for e in tail["entries"]] == ["last"]
        middle = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": tail["older_cursor"], "lines": 1,
        }).json()
        assert [e["msg"] for e in middle["entries"]] == [long_msg]
        first = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": middle["older_cursor"], "lines": 1,
        }).json()
        assert [e["msg"] for e in first["entries"]] == ["first"]
        assert first["has_older"] is False

    def test_same_filter_contract_applies_to_history(self, client, log_dir):
        mine = "exec-history"
        lines = [
            _json_line("ERROR", "mine-old", session_id="req-a", execution_id=mine),
            _json_line("ERROR", "other", session_id="req-b", execution_id="other"),
        ]
        lines += [_json_line("INFO", f"noise-{i}") for i in range(210)]
        (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

        tail = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200,
        }).json()
        history = client.get(HISTORY_URL, params={
            "filename": "app.log",
            "cursor": tail["older_cursor"],
            "lines": 200,
            "level": "ERROR",
            "session_id": "req-a",
            "execution_id": mine,
        })
        assert history.status_code == 200
        assert [e["msg"] for e in history.json()["entries"]] == ["mine-old"]

    def test_cursor_survives_append_but_rejects_rewrite(self, client, log_dir):
        path = log_dir / "app.log"
        path.write_text("\n".join(_json_line("INFO", f"seq-{i}") for i in range(3)) + "\n",
                        encoding="utf-8")
        tail = client.get(TAIL_URL, params={"filename": "app.log", "lines": 1}).json()
        cursor = tail["older_cursor"]

        with path.open("a", encoding="utf-8") as stream:
            stream.write(_json_line("INFO", "new-append") + "\n")
        appended = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": cursor, "lines": 10,
        })
        assert appended.status_code == 200
        assert [e["msg"] for e in appended.json()["entries"]] == ["seq-0", "seq-1"]

        original = path.read_text(encoding="utf-8")
        # 等长改写已经返回给 GUI 的尾页：偏移、inode、大小与换行边界都不变，
        # 只能由游标携带的可见区间指纹检出。
        path.write_text(original.replace("seq-2", "bad-2"), encoding="utf-8")
        stale = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": cursor, "lines": 10,
        })
        assert stale.status_code == 409
        assert "刷新" in stale.json()["detail"]

    def test_cursor_survives_append_immediately_after_boundary(self, client, log_dir):
        """游标离旧文件尾不足锚点宽度时，正常追加也不能让游标失效。"""
        path = log_dir / "app.log"
        path.write_text(
            _json_line("INFO", "old") + "\n" + _json_line("INFO", "latest") + "\n",
            encoding="utf-8",
        )
        tail = client.get(TAIL_URL, params={"filename": "app.log", "lines": 1}).json()

        with path.open("a", encoding="utf-8") as stream:
            stream.write(_json_line("INFO", "appended") + "\n")

        history = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": tail["older_cursor"], "lines": 10,
        })
        assert history.status_code == 200
        assert [entry["msg"] for entry in history.json()["entries"]] == ["old"]

    def test_rotation_between_cursor_validation_and_scan_keeps_one_file_instance(
        self, client, log_dir, monkeypatch,
    ):
        """游标校验后发生轮转，也只能继续读已打开的旧文件，不能混进新一代。"""
        path = log_dir / "app.log"
        path.write_text(
            "\n".join(_json_line("INFO", f"old-{i}") for i in range(3)) + "\n",
            encoding="utf-8",
        )
        cursor = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 1,
        }).json()["older_cursor"]

        original_scan = system_logs._scan_reverse_entries
        rotated = False

        def rotate_then_scan(*args, **kwargs):
            nonlocal rotated
            if not rotated:
                path.rename(log_dir / "app.log.1")
                path.write_text(
                    "\n".join(_json_line("INFO", f"new-{i}") for i in range(3)) + "\n",
                    encoding="utf-8",
                )
                rotated = True
            return original_scan(*args, **kwargs)

        monkeypatch.setattr(system_logs, "_scan_reverse_entries", rotate_then_scan)
        history = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": cursor, "lines": 10,
        })
        assert history.status_code == 200
        assert [entry["msg"] for entry in history.json()["entries"]] == ["old-0", "old-1"]

    def test_visible_boundary_rewrite_during_final_page_is_rejected(
        self, client, log_dir, monkeypatch,
    ):
        """decode 后才发生的等长改写也要在返回前被二次校验拦住，包括最终页。"""
        path = log_dir / "app.log"
        path.write_text(
            "\n".join(_json_line("INFO", f"seq-{i}") for i in range(3)) + "\n",
            encoding="utf-8",
        )
        cursor = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 1,
        }).json()["older_cursor"]

        original_scan = system_logs._scan_reverse_entries

        def rewrite_after_scan(*args, **kwargs):
            result = original_scan(*args, **kwargs)
            original = path.read_text(encoding="utf-8")
            path.write_text(original.replace("seq-2", "bad-2"), encoding="utf-8")
            return result

        monkeypatch.setattr(system_logs, "_scan_reverse_entries", rewrite_after_scan)
        history = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": cursor, "lines": 10,
        })
        assert history.status_code == 409
        assert "变化" in history.json()["detail"]

    def test_cursor_guard_io_is_fixed_size_not_cumulative(
        self, client, log_dir, monkeypatch,
    ):
        """翻页游标只能读固定锚点，不能从当前 offset 一路重哈希到快照 EOF。"""
        path = log_dir / "app.log"
        path.write_text(
            "\n".join(_json_line("INFO", f"seq-{i}") for i in range(500)) + "\n",
            encoding="utf-8",
        )
        cursor = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 1,
        }).json()["older_cursor"]

        real_pread = system_logs.os.pread
        requested_sizes = []

        def recording_pread(fd, size, offset):
            requested_sizes.append(size)
            return real_pread(fd, size, offset)

        monkeypatch.setattr(system_logs.os, "pread", recording_pread)
        history = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": cursor, "lines": 1,
        })
        assert history.status_code == 200
        assert requested_sizes
        assert max(requested_sizes) <= system_logs._CURSOR_ANCHOR_BYTES * 2
        assert len(requested_sizes) <= 6, "游标校验次数随累计历史增长"

    def test_malformed_or_cross_file_cursor_is_rejected(self, client, log_dir):
        (log_dir / "app.log").write_text(
            "\n".join(_json_line("INFO", f"app-{i}") for i in range(3)) + "\n",
            encoding="utf-8",
        )
        (log_dir / "scpi.log").write_text(
            "\n".join(_json_line("INFO", f"scpi-{i}") for i in range(3)) + "\n",
            encoding="utf-8",
        )
        cursor = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 1,
        }).json()["older_cursor"]

        malformed = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": "not-a-cursor", "lines": 10,
        })
        assert malformed.status_code == 400

        cross_file = client.get(HISTORY_URL, params={
            "filename": "scpi.log", "cursor": cursor, "lines": 10,
        })
        assert cross_file.status_code == 409

    def test_rotated_log_files_are_listed(self, client, log_dir):
        for filename in ("app.log", "app.log.2026-08-05", "scpi.log.1", "ignore.txt"):
            (log_dir / filename).write_text("x\n", encoding="utf-8")

        response = client.get(f"{settings.api_v1_prefix}/system-logs/files")
        assert response.status_code == 200
        files = {item["filename"]: item for item in response.json()["files"]}
        assert set(files) == {"app.log", "app.log.2026-08-05", "scpi.log.1"}
        assert files["app.log"]["is_current"] is True
        assert files["app.log.2026-08-05"]["is_current"] is False
        assert files["scpi.log.1"]["is_current"] is False
