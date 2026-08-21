"""P2-33 日志体验包 — 四条各自的行为 / 不变量门。

四条（Discovered 打包，见 docs/plans/2026-08-21-p2-33-log-ux-pack-design.md）：
  ① 重复抑制桶必须按日志级别隔离 —— INFO 洪峰不得吞掉同文本的 ERROR；
  ② 关键词过滤必须能命中 traceback 续行 —— /tail、/history、/export 三入口一致；
  ③ 两个日志面板对「异常」只许有一个定义 —— 主控台不得漏 CRITICAL；
  ④ 日志查看器级别过滤是多选集合 —— 哨兵值整类消失，归一化仍只一处。

变异自验对应表（⓪-④）：
- ① `_DuplicateBurstLimiter._key` 去掉 `record.levelno`
    → test_error_survives_same_text_info_burst 红
- ② `_group_matches` 只查父记录（去掉续行扫描）
    → test_tail/history/export_keyword_matches_continuation 红
- ② 非关键词维度改成"父或续行任一满足"
    → test_parent_level_still_gates_the_group 红
- ③ ZoneLogsAlerts 的 LEVEL_FILTERS / boost 流去掉 CRITICAL
    → test_dashboard_panel_can_show_critical /
      test_both_panels_share_one_issue_definition 红
- ④ 「仅异常」快捷键改 `ISSUE_LEVELS.slice(0, 1)` 或恢复哨兵
    → test_viewer_level_filter_is_multiselect_without_sentinel 红
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core import logging_config
from app.core.logging_config import ContextFilter, JsonFormatter, current_execution_id
from app.main import app

_API_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_SERVICE_ROOT.parent
_ZONE_TSX = _REPO_ROOT / "gui" / "src" / "features" / "Dashboard" / "ZoneLogsAlerts.tsx"
_VIEWER_TSX = (
    _REPO_ROOT / "gui" / "src" / "features" / "Reports" / "components" / "SystemLogViewer.tsx"
)

TAIL_URL = f"{settings.api_v1_prefix}/system-logs/tail"
HISTORY_URL = f"{settings.api_v1_prefix}/system-logs/history"
EXPORT_URL = f"{settings.api_v1_prefix}/system-logs/export"


def _strip_ts_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", src)


# ─────────────────────────────────────────────────────────────────────
# ① 重复抑制桶按级别隔离
# ─────────────────────────────────────────────────────────────────────

def _emit_at_level(
    handler: logging.Handler,
    execution_id: str,
    message: str,
    level: int,
) -> None:
    logger = logging.Logger("app.p2_33.burst", level=logging.DEBUG)
    logger.addHandler(handler)
    token = current_execution_id.set(execution_id)
    try:
        logger.log(level, message)
    finally:
        current_execution_id.reset(token)
        logger.removeHandler(handler)


class TestSuppressionBucketLevelIsolation:
    def test_error_survives_same_text_info_burst(self, tmp_path):
        """行为门：同秒同文本的 INFO 洪峰满额后，同文本 ERROR 必须原样存活。

        修复前抑制 key 不含级别：ERROR 落进满额 INFO 桶被吞，摘要还复制
        INFO 级别 —— 级别升级在日志里完全不可见（Codex #303 R1）。
        """
        now = [10.0]
        handler = logging_config.ExecutionFileHandler(
            str(tmp_path),
            repeat_limit=2,
            repeat_window_seconds=1.0,
            clock=lambda: now[0],
        )
        handler.setFormatter(JsonFormatter())
        handler.addFilter(ContextFilter())
        execution_id = str(uuid4())

        # 同一秒：3 条同文本 INFO（第 3 条应被抑制）+ 1 条同文本 ERROR。
        for _ in range(3):
            _emit_at_level(handler, execution_id, "link flap", logging.INFO)
        _emit_at_level(handler, execution_id, "link flap", logging.ERROR)
        handler.close()

        rows = [
            json.loads(line)
            for line in (tmp_path / f"exec-{execution_id}.log")
            .read_text(encoding="utf-8").splitlines()
        ]

        error_rows = [
            row for row in rows
            if row["level"] == "ERROR" and "suppressed_count" not in row
        ]
        assert error_rows and error_rows[0]["msg"] == "link flap", (
            "同文本 ERROR 被 INFO 桶吞掉 —— 抑制 key 必须包含级别"
        )

        summaries = [row for row in rows if "suppressed_count" in row]
        assert len(summaries) == 1
        assert summaries[0]["level"] == "INFO", "摘要必须来自 INFO 桶自己的样本"
        assert summaries[0]["suppressed_count"] == 1, (
            "INFO 桶只抑制了第 3 条 INFO —— ERROR 不许被算进 INFO 桶"
        )

    def test_same_level_burst_is_still_suppressed(self, tmp_path):
        """反向：级别进 key 之后，同级别同文本的洪峰仍要被抑制（别把限流修没了）。"""
        now = [10.0]
        handler = logging_config.ExecutionFileHandler(
            str(tmp_path),
            repeat_limit=2,
            repeat_window_seconds=1.0,
            clock=lambda: now[0],
        )
        handler.setFormatter(JsonFormatter())
        handler.addFilter(ContextFilter())
        execution_id = str(uuid4())

        for _ in range(5):
            _emit_at_level(handler, execution_id, "heartbeat", logging.INFO)
        handler.close()

        rows = [
            json.loads(line)
            for line in (tmp_path / f"exec-{execution_id}.log")
            .read_text(encoding="utf-8").splitlines()
        ]
        assert [row["msg"] for row in rows] == [
            "heartbeat",
            "heartbeat",
            "… same message suppressed x3",
        ]


# ─────────────────────────────────────────────────────────────────────
# ② 关键词过滤命中 traceback 续行（/tail、/history、/export 三入口）
# ─────────────────────────────────────────────────────────────────────

def _json_line(
    level: str,
    msg: str,
    logger: str = "app.services.test_case_runner",
    session_id: str = "-",
) -> str:
    return json.dumps({
        "ts": "2026-08-21T10:00:00.000+08:00",
        "level": level,
        "logger": logger,
        "hal_mode": "mock",
        "session_id": session_id,
        "execution_id": "-",
        "instrument_id": "-",
        "msg": msg,
    }, ensure_ascii=False)


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def client():
    # 不进 lifespan（本端点只读文件，不需要 DB/bootstrap）
    return TestClient(app)


def _write_traceback_scene(log_dir: Path) -> None:
    """父 INFO + 两条 RAW 续行（关键词只在续行里）+ 一条更新的无关行。"""
    lines = [
        _json_line("INFO", "request failed", session_id="sess-aaaa"),
        "Traceback (most recent call last):",
        "ValueError: broken pipe on probe 7",
        _json_line("INFO", "unrelated newest line"),
    ]
    (log_dir / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestKeywordMatchesContinuation:
    def test_tail_keyword_matches_continuation(self, client, log_dir):
        """行为门：关键词只出现在续行时，/tail 必须返回整组（父 + 续行）。"""
        _write_traceback_scene(log_dir)

        resp = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "keyword": "broken"})
        assert resp.status_code == 200
        body = resp.json()
        msgs = [e["msg"] for e in body["entries"]]
        assert "request failed" in msgs, (
            "关键词在续行里，父记录必须命中 —— 反向扫描只对父记录调谓词的旧行为"
        )
        assert any("ValueError: broken" in m for m in msgs), "续行必须随组返回"
        assert "unrelated newest line" not in msgs

    def test_history_keyword_matches_continuation(self, client, log_dir):
        """行为门：/history 与 /tail 共用扫描器，续行关键词同样必须命中。"""
        _write_traceback_scene(log_dir)

        cursor = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 1,
        }).json()["older_cursor"]
        assert cursor

        resp = client.get(HISTORY_URL, params={
            "filename": "app.log", "cursor": cursor, "lines": 200,
            "keyword": "broken",
        })
        assert resp.status_code == 200
        msgs = [e["msg"] for e in resp.json()["entries"]]
        assert "request failed" in msgs
        assert any("ValueError: broken" in m for m in msgs)

    def test_export_keyword_matches_continuation(self, client, log_dir):
        """行为门：/export 与屏幕同一份组谓词，续行关键词也要导出整组。"""
        _write_traceback_scene(log_dir)

        resp = client.get(f"{EXPORT_URL}/app.log", params={"keyword": "broken"})
        assert resp.status_code == 200
        rows = [l for l in resp.text.splitlines() if l.strip()]
        assert any('"request failed"' in r for r in rows), "父记录原始行必须导出"
        assert any("ValueError: broken" in r for r in rows), "续行原始行必须导出"
        assert not any("unrelated newest line" in r for r in rows)

    def test_parent_level_still_gates_the_group(self, client, log_dir):
        """反向门：非关键词维度仍只看父记录 —— 父 INFO 被 level=ERROR 排除时，
        哪怕续行命中关键词也不得返回（level/session 语义保持父级）。"""
        _write_traceback_scene(log_dir)

        resp = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200,
            "level": "ERROR", "keyword": "broken",
        })
        assert resp.status_code == 200
        assert resp.json()["entries"] == []

    def test_absent_keyword_still_matches_nothing(self, client, log_dir):
        """反向门：组扫描不得把"有续行"当成"命中"。"""
        _write_traceback_scene(log_dir)

        resp = client.get(TAIL_URL, params={
            "filename": "app.log", "lines": 200, "keyword": "nonexistent-kw"})
        assert resp.status_code == 200
        assert resp.json()["entries"] == []

    def test_export_and_tail_agree_on_continuation_keyword(self, client, log_dir):
        """不变量门：同一续行关键词下，/tail 与 /export 的行集合一致
        （P1-34 内审 F3「屏幕 5 条、导出全量」的母题在组语义下不得复发）。"""
        _write_traceback_scene(log_dir)

        tail_rows = {
            e["raw"] for e in client.get(TAIL_URL, params={
                "filename": "app.log", "lines": 200, "keyword": "broken",
            }).json()["entries"]
        }
        export_rows = {
            l for l in client.get(
                f"{EXPORT_URL}/app.log", params={"keyword": "broken"},
            ).text.splitlines() if l.strip()
        }
        assert tail_rows == export_rows


# ─────────────────────────────────────────────────────────────────────
# ③ 两个面板对「异常」只许有一个定义（主控台不得漏 CRITICAL）
# ─────────────────────────────────────────────────────────────────────

def _issue_levels_from_viewer(viewer_src: str) -> set[str]:
    m = re.search(r"const ISSUE_LEVELS = \[(.*?)\]", viewer_src, re.S)
    assert m, "SystemLogViewer 的 ISSUE_LEVELS 不见了"
    return set(re.findall(r"'(\w+)'", m.group(1)))


class TestPanelsShareOneIssueDefinition:
    def test_dashboard_panel_can_show_critical(self):
        """结构门：主控台日志面板必须存在能打开 CRITICAL 的开关，且默认打开。

        修复前 LEVEL_FILTERS 只有 INFO/WARNING/ERROR —— 不是"要多点一下"，
        是那个开关不存在，CRITICAL 行恒被客户端过滤掉（P1-35 内审 F8）。
        """
        zone = _strip_ts_comments(_ZONE_TSX.read_text(encoding="utf-8"))

        m = re.search(r"const LEVEL_FILTERS[^=]*= \[(.*?)\n\]", zone, re.S)
        assert m, "找不到 LEVEL_FILTERS"
        filter_values = set(re.findall(r"value: '(\w+)'", m.group(1)))
        assert "CRITICAL" in filter_values, "主控台没有任何 chip 能打开 CRITICAL"

        m = re.search(r"useState<string\[\]>\(\[(.*?)\]\)", zone, re.S)
        assert m, "找不到 enabledLevels 默认值"
        defaults = set(re.findall(r"'(\w+)'", m.group(1)))
        assert "CRITICAL" in defaults, "CRITICAL 开关存在但默认关闭 —— 等于还是看不见"

        color_block = re.search(r"const LOG_LEVEL_COLOR[^=]*= \{(.*?)\}", zone, re.S)
        assert color_block and "CRITICAL" in color_block.group(1), (
            "CRITICAL 没有配色 —— 会以 gray 渲染，跟 DEBUG 不可分"
        )

    def test_dashboard_boost_stream_covers_critical(self):
        """结构门：CRITICAL 必须有自己的下推补充流 —— 只加 chip 不加 boost，
        INFO 刷屏时 CRITICAL 仍会被冲出主流 200 行窗口（P2-11 失效模式）。"""
        zone = _strip_ts_comments(_ZONE_TSX.read_text(encoding="utf-8"))
        m = re.search(r"const boosts = \[(.*?)\]\.filter", zone, re.S)
        assert m, "找不到 boost 流级别列表"
        boost_levels = set(re.findall(r"'(\w+)'", m.group(1)))
        assert "CRITICAL" in boost_levels

    def test_both_panels_share_one_issue_definition(self):
        """不变量门：主控台 boost 流的级别集 == 查看器 ISSUE_LEVELS 集 ——
        「异常」在两个面板里只剩一个定义（本条目的标题本身）。"""
        zone = _strip_ts_comments(_ZONE_TSX.read_text(encoding="utf-8"))
        viewer = _strip_ts_comments(_VIEWER_TSX.read_text(encoding="utf-8"))

        m = re.search(r"const boosts = \[(.*?)\]\.filter", zone, re.S)
        assert m, "找不到 boost 流级别列表"
        boost_levels = set(re.findall(r"'(\w+)'", m.group(1)))

        assert boost_levels == _issue_levels_from_viewer(viewer), (
            f"两个面板对「异常」又出现两个定义：主控台补 {sorted(boost_levels)}，"
            f"查看器「仅异常」是另一套"
        )


# ─────────────────────────────────────────────────────────────────────
# ④ 查看器级别过滤 = 多选集合，哨兵值整类消失
# ─────────────────────────────────────────────────────────────────────

class TestViewerLevelMultiselect:
    def test_viewer_level_filter_is_multiselect_without_sentinel(self):
        """结构门：级别过滤是多选（string[] 状态），`__ISSUES__` 哨兵不复存在。

        多选模型里「仅异常」是一组选中态而不是一个哨兵值 ——
        「哨兵值漏发给后端 → 精确匹配 0 行」这一类风险从源头消失。
        """
        viewer = _strip_ts_comments(_VIEWER_TSX.read_text(encoding="utf-8"))

        assert "__ISSUES__" not in viewer, "哨兵值回来了 —— 多选模型不需要哨兵"
        assert "=== ISSUES" not in viewer

        m = re.search(
            r"const \[selectedLevels, setSelectedLevels\] = useState<string\[\]>", viewer,
        )
        assert m, "级别过滤不再是多选 string[] 状态"

        chips = re.search(r"LEVEL_CHOICES[^=]*= \[(.*?)\n\]", viewer, re.S)
        assert chips, "找不到级别多选选项 LEVEL_CHOICES"
        values = set(re.findall(r"value: '(\w+)'", chips.group(1)))
        assert values == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}, (
            f"级别多选必须恰好覆盖五个真实级别，现在是 {sorted(values)}"
        )

    def test_issues_shortcut_selects_whole_set(self):
        """结构门：「仅异常」快捷键必须整体消费 ISSUE_LEVELS ——
        中途 slice/filter/map 会静默少发级别（P1-35 立门实证 `.slice(0, 1)`）。"""
        viewer = _strip_ts_comments(_VIEWER_TSX.read_text(encoding="utf-8"))

        assert _issue_levels_from_viewer(viewer) == {"WARNING", "ERROR", "CRITICAL"}
        # ⚠ 钉**完整消费形态**：Array.from 的结果必须直接成为 set 参数。
        # 只断言 `Array.from(ISSUE_LEVELS)` 存在会被
        # `Array.from(ISSUE_LEVELS).slice(0, 1)` 绕过（token 还在、级别少发）
        # —— 变异预演当场抓出的绕法。
        assert "setSelectedLevels(Array.from(ISSUE_LEVELS))" in viewer, (
            "「仅异常」快捷键必须把 ISSUE_LEVELS 整体、不加中间链式调用地选中"
        )
        mutators = re.findall(r"ISSUE_LEVELS\.(\w+)", viewer)
        assert mutators == [], f"ISSUE_LEVELS 被逐方法消费：{mutators}"

    def test_level_normalization_happens_once_in_build_log_query(self):
        """结构门：`level` 参数的归一化（join）只准出现在 buildLogQuery 一处，
        且屏幕 / 历史页 / 导出仍各走一次同一构造（恰 3 调）。"""
        viewer = _strip_ts_comments(_VIEWER_TSX.read_text(encoding="utf-8"))

        assert "function buildLogQuery(" in viewer
        assert len(re.findall(r"buildLogQuery\(\{", viewer)) == 3

        # ⚠ 不用非贪婪正则取函数体 —— 参数解构关闭行 `}): Record<…> {` 行首
        # 就是 `}`，会截断（test_p1_35 的门注释里已踩过一次）。改钉位置区间：
        # 归一化 join 恰出现 1 次，且落在函数定义之后、第一次调用之前。
        joins = [m.start() for m in re.finditer(r"\.join\(','\)", viewer)]
        assert len(joins) == 1, (
            f"level 归一化 join 出现 {len(joins)} 次（应恰 1 次，在 buildLogQuery 里）"
        )
        def_pos = viewer.index("function buildLogQuery(")
        first_call = min(m.start() for m in re.finditer(r"buildLogQuery\(\{", viewer))
        assert def_pos < joins[0] < first_call, (
            "归一化 join 不在 buildLogQuery 函数体内 —— 又在调用点自己拼参数了"
        )
        assert "levels" in viewer[def_pos:joins[0]], (
            "buildLogQuery 必须从 levels 数组归一化出逗号集合"
        )
