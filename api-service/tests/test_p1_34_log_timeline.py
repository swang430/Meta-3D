"""P1-34 的门 —— 让操作员能顺着时间线还原一次操作。

三件事各配一道会红的门（⓪④：门不过变异 = 门不算数）：

① **行为门** `request_id` 串联：一次请求内的日志带同一个 id，跨请求不同，
   且**被审计排除的路径**（心跳轮询）其下游日志同样带 id。
   变异：删掉 `current_session_id.set(...)` / 把它挪到排除判断之后 → 红。

② **不变量门** `EXCLUDED_PATHS` 里每条 `/api/v1/` 路径都必须真的存在于路由表。
   变异：把 `/api/v1/system-logs/tail` 少写一个 `s` → 红。
   （存在性写法拼错 = 排除静默失效，噪音照旧、而且没人会发现。）

③ **不变量门** GUI 不得再"切时间戳字符串"取时分秒，必须走
   `utils/datetime.ts` 的共享函数。
   变异：把任一面板改回 `ts.split('T')[1]` → 红。

为什么 ③ 是不变量门而不是行为门：GUI 侧没有单测 runner（`gui/package.json`
无 test 脚本），本轮不为一条格式化函数引入一整套 vitest（⑤ 一轮只删不加）。
渲染结果由**浏览器实测**这道既定的门覆盖，本门只守"同一个母题不许在第三处
复活"——它防的是**新站点漏做**，正是不变量门该干的事。
"""

import ast
import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.audit_middleware import (
    EXCLUDED_PATHS,
    REQUEST_ID_HEX_LEN,
    AuditMiddleware,
)
from app.core.logging_config import ContextFilter

from .test_rule_gates import _REPO_ROOT, _gui_ts_sources, _strip_ts_comments


# ── ① 行为门：request_id 把一次请求的日志串成一条链 ────────────────


class _Capture(logging.Handler):
    """带 ContextFilter 的捕获 handler —— 必须带，否则 record 上根本没有
    `session_id` 属性（注入是 filter 干的），门会变成恒真断言。"""

    def __init__(self):
        super().__init__()
        self.addFilter(ContextFilter())
        self.seen: list[tuple[str, str]] = []  # (msg, session_id)

    def emit(self, record):
        self.filter(record)
        self.seen.append((record.getMessage(), getattr(record, "session_id", "<缺>")))


@pytest.fixture
def logged_app():
    """最小 app：只装 AuditMiddleware + 两个会写日志的路由。

    不用真 app：那样得跑 lifespan（连 DB、起 HAL），而本门要问的只有一件事
    —— **中间件设的 contextvar 传不传得到 endpoint 里**。
    （这不是想当然：`BaseHTTPMiddleware` 的 `call_next` 会另起一个任务，
    contextvar 能不能穿过去正是这道门要证的。）
    """
    app = FastAPI()
    app.add_middleware(AuditMiddleware)
    logger = logging.getLogger("app.test.p1_34")

    @app.get("/api/v1/probes")
    def _audited():
        logger.info("端点内部干了点活")
        return {"ok": True}

    # 走排除名单的路径：成功时审计那一行不写，但下游日志照样要能串。
    @app.get("/api/v1/system-logs/tail")
    def _excluded():
        logger.info("被排除路径的下游日志")
        return {"ok": True}

    # 同样走排除名单，但**失败** —— 这一行必须记（内审 F1）。
    @app.post("/api/v1/system-logs/frontend")
    def _excluded_but_failing():
        return JSONResponse({"detail": "schema 对不上"}, status_code=422)

    handler = _Capture()
    audit_logger = logging.getLogger("app.audit")
    # ⚠ 必须复位 `.disabled`：全量里别的用例会 in-process 跑 alembic，
    #   `fileConfig(disable_existing_loggers=True)` 把**已导入**的 logger
    #   永久禁掉。单跑本文件绿、跑全量红，就是这个（memory
    #   `feedback_test_logger_emit_alembic_pollution`，实测本片又踩一次：
    #   单文件 18 passed，全量 `test_excluded_path_failure_is_still_audited` 红）。
    prev = {lg: (lg.propagate, lg.disabled, lg.level) for lg in (logger, audit_logger)}
    for lg in (logger, audit_logger):
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
        lg.disabled = False
        lg.propagate = False
    try:
        yield TestClient(app), handler
    finally:
        for lg, (propagate, disabled, level) in prev.items():
            lg.removeHandler(handler)
            lg.propagate, lg.disabled, lg.level = propagate, disabled, level


def _ids_for(handler, needle):
    return [sid for msg, sid in handler.seen if needle in msg]


def test_request_id_is_populated_and_stable_within_one_request(logged_app):
    """修之前实测：24372 行日志的 session_id 100% 是 '-'，字段纯装饰。"""
    client, handler = logged_app
    assert client.get("/api/v1/probes").status_code == 200

    ids = _ids_for(handler, "端点内部干了点活")
    assert ids, "端点的日志没被捕获到，门本身失效了"
    for sid in ids:
        assert sid not in ("-", "", "<缺>"), (
            f"请求内的日志 session_id={sid!r} —— AuditMiddleware 没把 id 传进 "
            f"endpoint（BaseHTTPMiddleware 的 call_next 换了任务）"
        )
    assert len(set(ids)) == 1, f"同一次请求里 id 不一致: {set(ids)}"


def test_request_id_has_enough_entropy_to_avoid_collisions(logged_app):
    """id 短了会**静默合并两条不相干的链** —— 比没有这个功能更坏。

    Codex #282 R1 P2：`hex[:8]` = 32 bit，一天的日志量级上碰撞是必然
    （GUI 光轮询约 1 万请求/小时；十万条时 69%、五十万条 ~100%）。
    而「只看这一次请求」是精确匹配，碰撞 = 把别人的行混进你的链。

    ⚠ 别拿"扫描窗口只有 20000 行"当理由：`/system-logs/export` 是**全文件**
    流式过滤，不受那个上限约束。

    变异：把 `REQUEST_ID_HEX_LEN` 改回 8 → 本门红。
    """
    assert REQUEST_ID_HEX_LEN >= 16, (
        f"request id 只有 {REQUEST_ID_HEX_LEN} 位 hex = {REQUEST_ID_HEX_LEN * 4} bit，"
        f"碰撞会把两条不相干的链合并显示"
    )

    client, handler = logged_app
    client.get("/api/v1/probes")
    ids = _ids_for(handler, "端点内部干了点活")
    assert ids, "端点的日志没被捕获到，门本身失效了"
    for sid in ids:
        assert len(sid) == REQUEST_ID_HEX_LEN, (
            f"实际发出的 id 是 {len(sid)} 位（{sid!r}），跟声明的 "
            f"{REQUEST_ID_HEX_LEN} 位对不上"
        )


def test_request_id_differs_across_requests(logged_app):
    """不同请求必须能分开 —— 否则"只看这一次请求"会把别人的日志也捞进来。"""
    client, handler = logged_app
    client.get("/api/v1/probes")
    client.get("/api/v1/probes")

    ids = _ids_for(handler, "端点内部干了点活")
    assert len(ids) == 2, f"预期两条，实得 {len(ids)}"
    assert ids[0] != ids[1], f"两次请求拿到同一个 id {ids[0]!r} —— 串不成链"


def test_excluded_paths_still_get_a_request_id(logged_app):
    """排除的是"审计那一行"，不是"这个请求的全部日志"。

    变异：把 `current_session_id.set(...)` 挪到排除判断**之后** → 本门红。
    """
    client, handler = logged_app
    assert client.get("/api/v1/system-logs/tail").status_code == 200

    ids = _ids_for(handler, "被排除路径的下游日志")
    assert ids, "被排除路径的下游日志没捕获到"
    for sid in ids:
        assert sid not in ("-", "", "<缺>"), (
            f"被排除路径的下游日志 session_id={sid!r} —— id 设晚了，"
            f"心跳请求引发的问题将无法归属"
        )


# ── ①' 行为门：排除名单只吞"成功那一行"（内审 F1） ──────────────────


def test_excluded_path_success_is_not_audited(logged_app):
    """成功的心跳请求不该进审计 —— 这是排除名单存在的理由。"""
    client, handler = logged_app
    client.get("/api/v1/system-logs/tail")
    audited = [m for m, _ in handler.seen if "system-logs/tail" in m and "→" in m]
    assert not audited, f"成功的心跳被记进审计了: {audited}"


def test_excluded_path_failure_is_still_audited(logged_app):
    """**失败的**心跳请求必须留痕。

    内审 F1 的场景：`/system-logs/frontend` 返 422 时，前端 `frontendLogger`
    自己 catch 后静默丢批、`api/client.ts` 又显式跳过该 URL 防回环 ——
    审计这一行是最后一处痕迹。排掉它 = 整条前端日志通道死了没人知道。

    变异：把 dispatch 改回「命中排除就 `return await call_next(request)`」→ 红。
    """
    client, handler = logged_app
    r = client.post("/api/v1/system-logs/frontend")
    assert r.status_code == 422

    audited = [m for m, _ in handler.seen if "system-logs/frontend" in m and "422" in m]
    assert audited, (
        "被排除路径返回 422 却没留下任何审计痕迹 —— 排除的粒度错了："
        "该排的是「成功那一行」，不是整个请求的痕迹"
    )


# ── ② 不变量门：排除名单里的路径必须真的存在 ──────────────────────


# 本门开出来时就已经是死条目的排除项 —— **不是本片造成的，也不由本片修**。
#
# 实况（2026-08-05 查证）：`app/api/monitoring.py` 里只有
# `GET /monitoring/feeds` 和 `WS /ws/monitoring`，下面这两个路径**不存在**，
# 是旧路由布局的残留，各自排除了个寂寞。
#
# 为什么不顺手删（⑦ 的判据在动手前问）：「不改它，P1-34 那个可观察故障
# ——操作员看不出自己刚做的操作——还在吗？」**还在**。它们匹配不到任何请求，
# 一行噪音都不贡献。所以是越界，撤回 Discovered backlog。
# 放这里而不是悄悄跳过：让它在代码里留个名，别变成隐形债。
_EXCLUDED_KNOWN_STALE = {
    "/api/v1/monitoring/metrics",
    "/api/v1/monitoring/instrument-status",
}


def test_excluded_api_paths_exist_in_the_route_table():
    """`EXCLUDED_PATHS` 是**字符串前缀匹配**，拼错不会报错，只会静默失效。

    变异：把 `/api/v1/system-logs/tail` 写成 `/api/v1/system-log/tail` → 红。

    真值源取 **OpenAPI schema**（`app.openapi()["paths"]`）而不是 `app.routes`：
    后者在当前 FastAPI 里是一层 `_IncludedRouter` 包装，没有公开的 `.routes`，
    照着它的内部结构写门等于把实现细节当契约。

    只校 `/api/v1/` 开头的：`/health`、`/favicon.ico`、`/api/docs` 等要么是
    FastAPI 自带、要么根本不是路由。
    """
    from app.main import app

    known = set(app.openapi().get("paths", {}))
    assert len(known) > 100, f"OpenAPI 只给出 {len(known)} 条路径，真值源本身可疑"

    checked = 0
    for p in EXCLUDED_PATHS:
        if not p.startswith("/api/v1/") or p in _EXCLUDED_KNOWN_STALE:
            continue
        checked += 1
        assert any(k == p or k.startswith(p) for k in known), (
            f"排除名单里的 {p!r} 在 OpenAPI 路径里找不到 —— 拼错了，"
            f"这条排除是空转的：噪音照旧，而且没人会发现"
        )
    assert checked >= 2, "该门没实际校到东西（可校的排除项少于 2 条）"


def test_exclusion_prefixes_do_not_swallow_real_operations():
    """排除是**前缀匹配**，写宽了会顺手吞掉真实操作 —— 这是另一个方向的失效。

    内审 F7 的变异实证：把两条新排除项合并成 `/api/v1/system-logs` → 原来
    那道门 9 条全绿，而下载 / 导出 / 文件列表的审计**一起没了**，正好推翻
    `audit_middleware.py` 注释里「下载 / 导出属真实操作，不排除」那句承诺。

    上一道门只防「写窄了」（路径拼错），这道防「写宽了」。
    """
    must_stay_audited = (
        "/api/v1/system-logs/files",
        "/api/v1/system-logs/download/app.log",
        "/api/v1/system-logs/export/app.log",
    )
    for path in must_stay_audited:
        swallowed = [p for p in EXCLUDED_PATHS if path.startswith(p)]
        assert not swallowed, (
            f"{path} 被排除前缀 {swallowed} 吞掉了 —— 它是操作员的真实动作，"
            f"不是心跳轮询，必须留审计痕迹"
        )


def _handler_dicts_from_logging_config():
    """静态取出 `logging_config.py` 里所有**写文件**的 handler 字典字面量。

    用 ast 而不是正则：正则会被换行 / 键序 / 注释晃到。
    **不 import 后调用 `setup_logging()`** —— 那会真的接管全局 logging，
    正是 memory `feedback_test_logger_emit_alembic_pollution` 记的那个
    「全量顺序 flaky」的坑。
    """
    src = (_REPO_ROOT / "api-service" / "app" / "core" / "logging_config.py").read_text(
        encoding="utf-8"
    )
    out = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Dict):
            continue
        pairs = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                pairs[k.value] = v
        if "filename" in pairs and "class" in pairs:
            out.append(pairs)
    return out


def test_every_file_handler_is_wired_to_context_filter():
    """`session_id` 是 `ContextFilter` 注入的 —— 哪个 handler 没接它，
    落到那个文件里的 `session_id` 就恒为 `-`。

    内审 F4 的变异实证：把 `file_app` 的 `"filters": ["context_filter"],`
    删掉 → P1-34 功能对 app.log **整体归零**，而 `test_p1_34` +
    `test_scpi_log_evidence` + `test_f64_check_errors_family` **57 条全绿**。
    原来的门只锁了测试自己 `addFilter` 挂上去的那个 filter，
    **没锁真实生效端的接线** —— 典型的「验证打在看起来的那一端」。

    变异：删任一 file handler 的 filters 行 → 本门红。
    """
    handlers = _handler_dicts_from_logging_config()
    assert len(handlers) >= 8, (
        f"只解析出 {len(handlers)} 个写文件的 handler，真值源可疑（门可能空转）"
    )

    missing = []
    for h in handlers:
        filters = h.get("filters")
        names = (
            [e.value for e in filters.elts if isinstance(e, ast.Constant)]
            if isinstance(filters, ast.List)
            else []
        )
        if "context_filter" not in names:
            fn = h["filename"]
            label = ast.unparse(fn) if hasattr(ast, "unparse") else "<handler>"
            missing.append(label)

    assert not missing, (
        "这些写文件的 handler 没接 context_filter，落进去的 session_id 会恒为 '-'：\n  "
        + "\n  ".join(missing)
    )


def test_known_stale_exclusions_are_still_stale():
    """守住上面那份豁免名单**只减不增**的方向。

    哪天有人把 `/api/v1/monitoring/metrics` 真加成路由（或修了这两条），
    这个门会红，提醒把它从豁免名单里摘掉 —— 豁免不许无限期挂着。
    """
    from app.main import app

    known = set(app.openapi().get("paths", {}))
    revived = [p for p in _EXCLUDED_KNOWN_STALE if any(k.startswith(p) for k in known)]
    assert not revived, (
        f"{revived} 现在已经是真路由了 —— 把它从 _EXCLUDED_KNOWN_STALE 里删掉，"
        f"让主门去管"
    )


# ── ③ 不变量门：GUI 不得再切时间戳字符串 ──────────────────────────

# 从 ISO 时刻里"切"出时分秒的几种写法。共同毛病：把 `+08:00` / `Z`
# 这个偏移量丢掉，于是 UTC 的时刻被当本地时刻显示（差 8 小时）。
_TS_SLICING = (
    re.compile(r"\.split\(\s*['\"]T['\"]\s*\)"),
    re.compile(r"\.match\(\s*/\^?\\?d?.*?T\("),
    # ⚠ 末尾不能要求逗号：内审 F8 的变异 MUT-E 用 `.substring(11)`（无第二参）
    #   就把原来那条 `\(\s*11\s*,` 整个绕过去了。11 是 ISO 串里 'T' 后一位的
    #   下标，出现这个数字本身就是在按下标切时刻。
    re.compile(r"\.(?:slice|substring)\(\s*11\b"),
)
# ⚠ 别再加一条"凡 `toISOString().slice/split` 都算"——试过，太宽：
#   `App.tsx:2849` 的 `toISOString().slice(0, 10)` 是给下载文件名盖**日期**戳，
#   取的是日期不是时刻，跟本片这个病不是一回事。而 MUT-E 那种真正的绕法
#   （`toISOString().substring(11)`，取**时刻**）上面第三条已经抓得到 ——
#   下标 11 正是 ISO 串里 'T' 后第一位。宽一格就开始误伤，收着写。

_TS_SLICING_ALLOWED: set[str] = set()  # 目前没有豁免；要加必须写清理由


def test_gui_does_not_slice_timestamp_strings():
    """时间戳是"带时区的时刻"，不是可以按下标切的文本。

    修之前全仓正好 2 处这么写（`ZoneLogsAlerts` / `SystemLogViewer`），
    而另有 34 处已经正确用 `toLocale*`。本门守的是：别在第三处复活。

    变异：把任一面板改回 `e.ts.split('T')[1]?.slice(0, 8)` → 红。
    """
    hits = []
    for path in _gui_ts_sources():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        # ⚠ `utils/datetime.ts` **不豁免**。第一轮变异我豁免过它，结果
        #   「往 formatLogTime 里塞一句 `return ts.slice(11, 19)`」这条变异
        #   照样绿 —— 共享函数自己丢时区，是这个母题最坏的形态（一处坏，
        #   两个面板一起坏），恰恰最该守。
        if rel in _TS_SLICING_ALLOWED:
            continue
        text = _strip_ts_comments(path.read_text(encoding="utf-8", errors="ignore"))
        for pat in _TS_SLICING:
            if pat.search(text):
                hits.append(f"{rel} —— 命中 {pat.pattern}")

    assert not hits, (
        "GUI 里又出现了「切时间戳字符串」的写法，会丢掉时区偏移：\n  "
        + "\n  ".join(hits)
        + "\n改用 gui/src/utils/datetime.ts 的 formatLogTime / formatLogDate。"
    )


_LOG_VIEWER = "gui/src/features/Reports/components/SystemLogViewer.tsx"


def test_request_id_is_visible_in_the_table_not_only_on_expand():
    """做了但看不见 = 没做。

    用户反馈原话：「没看到 request_id 真的落进日志了」—— 而实测那 200 行里
    **47% 是带 id 的**。真因是我把它只放在展开详情里，表格 5 列一个字都不提，
    随手点一行还大概率点到没 id 的心跳行。

    变异：把 `<Table.Th w={86}>请求</Table.Th>` 删掉 → 本门红。
    """
    src = _strip_ts_comments((_REPO_ROOT / _LOG_VIEWER).read_text(encoding="utf-8"))
    assert ">请求</Table.Th>" in src, (
        "日志表格里没有「请求」列 —— request_id 又被藏回展开详情里了"
    )


def test_isolating_a_request_clears_the_other_filters():
    """「只看这一次请求」必须给出**整条链**，不是「这次请求 ∩ 当前过滤」。

    Codex #282 R2：操作员先用 ERROR/keyword 找到失败行，再点这个按钮 ——
    若不清掉那些过滤，后端返回交集，按钮承诺的 INFO/HAL/SCPI 上下文全没了。
    按钮名与实际行为不符，正是本片在治的母题。

    变异：把 `isolateRequest` 里的 `setLevelFilter('ALL')` 或
    `setKeyword('')` 删掉 → 本门红。
    """
    src = _strip_ts_comments((_REPO_ROOT / _LOG_VIEWER).read_text(encoding="utf-8"))
    m = re.search(r"const isolateRequest\s*=\s*\([^)]*\)\s*=>\s*\{(.+?)\n\s{2}\}", src, re.S)
    assert m, "找不到 isolateRequest —— 隔离逻辑被改名或拆散了，本门失效"
    body = m.group(1)
    assert "setSessionFilter" in body, "isolateRequest 里没设 session 过滤，按钮等于没用"

    # P1-36 把「清 level + keyword」提成了共享的 `clearTextFilters()`
    # （两个 isolate 必须策略一致，见 test_the_two_isolate_actions_are_symmetric）。
    # 所以判据从"体内直接有那两个 setter"改成"要么直接清、要么走那个 helper，
    # **且 helper 自己两个都清**" —— 意图没变，别因为重构就放松。
    if "clearTextFilters()" in body:
        helper = re.search(r"const clearTextFilters = \(\) => \{(.*?)\n  \}", src, re.S)
        assert helper, "调了 clearTextFilters 但找不到它的定义 —— 本门失效"
        body = body + helper.group(1)
    for needed, why in (
        ("setLevelFilter('ALL')", "没清 level，返回的是交集不是整条链"),
        ("setKeyword('')", "没清 keyword，返回的是交集不是整条链"),
    ):
        assert needed in body, f"「只看这一次请求」这条路上缺 {needed} —— {why}"

    # 所有触发点都得走它，不能有人绕过去直接 setSessionFilter
    direct = re.findall(r"onClick=\{[^}]*setSessionFilter\(entry", src)
    assert not direct, (
        f"有 {len(direct)} 处直接 setSessionFilter(entry…) 绕过了 isolateRequest，"
        f"那些入口不会清掉 level/keyword"
    )


def test_the_ts_slicing_gate_can_actually_fail(tmp_path):
    """自覆盖：证明上面那道门不是恒真断言。

    喂一个含旧写法的临时文件给同一组正则 —— 必须命中。
    """
    bad = tmp_path / "Bad.tsx"
    bad.write_text("const t = e.ts.split('T')[1]?.slice(0, 8)\n", encoding="utf-8")
    text = _strip_ts_comments(bad.read_text(encoding="utf-8"))
    assert any(p.search(text) for p in _TS_SLICING), "门抓不到旧写法，等于没有"


def test_shared_formatter_keeps_the_offset():
    """共享函数的契约：同一时刻的三种写法必须等价。

    这条在 Python 侧只能校"源码里声明了什么"——真正的渲染由浏览器实测。
    这里守的是那三个 `toLocale*` 选项没被人删掉（删了就退回切字符串的效果）。
    """
    src = (_REPO_ROOT / "gui" / "src" / "utils" / "datetime.ts").read_text(
        encoding="utf-8"
    )
    assert "toLocaleTimeString" in src, "formatLogTime 不再走 toLocaleTimeString"
    for token in ("formatLogTime", "formatLogDate"):
        assert f"export function {token}" in src, f"{token} 不见了"

    # ⚠ 这两条得**声明与使用都在**才算数。只查 "TIMEZONE_RE" in src 是
    #   存在性门：把声明删掉、用处留着，token 仍在，门照绿（第一轮变异 M8
    #   就这么溜过去的 —— 那种写法其实过不了 tsc，但那是另一道门的功劳，
    #   不是本门的）。
    assert re.search(r"const\s+TIMEZONE_RE\s*=", src), (
        "TIMEZONE_RE 的**声明**没了 —— 解析端不再区分带/不带偏移两种形态"
    )
    assert "TIMEZONE_RE.test(" in src, (
        "TIMEZONE_RE 声明了但没人用 —— 等于没区分"
    )

    # 内审 F8 的变异实证（MUT-A）：给 toLocaleTimeString 的选项里加一句
    # `timeZone: 'UTC'`，tsc 过、9 道门全绿，而界面立刻退回「比手表慢 8 小时」
    # —— 本片要修的那个故障原样复活。这个文件的语义就是**渲染成观看者的
    # 本地时区**，钉死任何时区都是违约。
    assert "timeZone" not in src, (
        "datetime.ts 里出现了 timeZone 选项 —— 钉死时区 = 把 P1-34 修的 bug 装回去；"
        "这里的契约是渲染成**本地**时区"
    )
