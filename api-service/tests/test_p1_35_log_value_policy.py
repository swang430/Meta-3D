"""P1-35 的门 —— 无用的日志不该被写出来。

判据（2026-08-05 用户定）：一条日志留不留，看它**能不能**服务这四件事之一
—— 分析系统 / 测试分析 / 积累 AI 训练语料 / 故障排除。四件都不沾就别写。

本片据此删掉的三类，各配一道会红的门：

① **周期性无信息量心跳**：`MetricsCache` 的四条 per-event `logger.debug`
   （hit / expired / updated / cleared）。同一事实**已有更好载体** ——
   `_hits` / `_misses` 计数器 + `get_stats()` + shutdown 的统计行。
   实测占 app.log 的 90.1%（6273 / 6965 行），且监控广播器是
   `while True: if active_connections: ... sleep(1.0)` ——
   **只在 GUI 连着时以 1 Hz 刷**，恰好在操作员盯着看的时候刷得最凶。

② **逐字重复第三方已记录的事**：`app.db` 的 checkout / checkin /
   session-committed 三条 DEBUG。SQLAlchemy 自己的 `sqlalchemy.pool` /
   `sqlalchemy.engine` 已经把同样的事件记进 `db.log`（实测同时段
   checkout 272 / checkin 272 / COMMIT 266，与这三条逐一对应）。

③ **说谎的死类型**：`InstrumentLog` 模型 + `instrument_logs` 表 +
   三个 schema。类名宣称"记录仪器的重要操作和状态变更历史"，实测
   库里 0 行、全仓 0 写入方 0 读取方。

⚠ **本片没做、且不该被误读为做了**的一件事：六个专属 logger 的
   `propagate: True` 双写**原样保留**。把它们关掉看着更干净，但那样
   `app.log` 只剩 1.8%，`request_id` 的链条会从操作员默认看的那个文件里
   消失 —— 正好毁掉 P1-34 刚建立的能力。`app.log` 的定位是**总线**，
   故障排除天生跨切面（HTTP → runner → HAL → SCPI），必须有一个文件看得全。
"""

import ast
import re
from pathlib import Path

_HERE = Path(__file__).resolve()
_API_ROOT = _HERE.parent.parent
_REPO_ROOT = _API_ROOT.parent


def _src(rel: str) -> str:
    return (_API_ROOT / rel).read_text(encoding="utf-8")


# ── ① 心跳：per-event 日志不得回来 ────────────────────────────────


def _metrics_cache_body() -> str:
    """取 `MetricsCache` 类的源码（只看它，别把整个文件的日志都算进来）。"""
    tree = ast.parse(_src("app/services/instrument_hal_service.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MetricsCache":
            return ast.get_source_segment(
                _src("app/services/instrument_hal_service.py"), node
            )
    raise AssertionError("找不到 MetricsCache 类 —— 本门失效了")


def test_metrics_cache_emits_no_per_event_logs():
    """缓存的每次命中/失效/更新/清空都不得再打日志。

    变异：把 `logger.debug("Cache updated")` 加回 `set()` → 本门红。
    """
    body = _metrics_cache_body()
    hits = re.findall(r"logger\.\w+\(", body)
    assert not hits, (
        f"MetricsCache 里又出现了 {len(hits)} 处日志调用 {hits} —— "
        f"缓存事件每秒发生若干次，per-event 日志会重新淹掉操作员的窗口；"
        f"要观测缓存请用 _hits / _misses 计数器与 get_stats()"
    )


def test_metrics_cache_still_counts():
    """删日志不等于删观测 —— 计数器和它的读取口必须还在。

    变异：把 `self._hits += 1` 删掉 → 本门红。
    （只删日志不留计数 = 把观测能力一起删了，那是过度收缩。）
    """
    body = _metrics_cache_body()
    for token in ("self._hits += 1", "self._misses += 1"):
        assert token in body, f"缺 {token} —— 日志删了，计数也没了 = 观测能力归零"

    # 计数器**唯一**真正被读出的路径是 shutdown 那一行（内审 F2：
    # `get_cache_stats()` 全仓零调用方，断言 `def get_stats` 存在只是对一个
    # 死方法的存在性断言，会把"看起来有观测"锁进契约）。所以这里守的是
    # **那条路径真的在**，而不是某个方法名还在。
    full = _src("app/services/instrument_hal_service.py")
    m = re.search(r"async def shutdown\(self\):(.+?)(?=\n    async def |\n    def |\Z)", full, re.S)
    assert m, "找不到 shutdown() —— 本门失效"
    assert "get_stats()" in m.group(1) and "Cache statistics" in m.group(1), (
        "shutdown 不再读出缓存计数 —— 那是这些计数器目前唯一的读出点，"
        "断了就等于日志和计数一起没了"
    )


# ── ② 不逐字重复 SQLAlchemy 已经记过的事 ──────────────────────────


def test_db_layer_does_not_duplicate_sqlalchemy_pool_events():
    """连接池 checkout/checkin 与提交成功由 SQLAlchemy 记进 db.log，
    我们不再另记一份到 app.log。

    变异：把 `logger.debug("DB connection checked out from pool")`
    加回 `_on_checkout` → 本门红。
    """
    src = _src("app/db/database.py")
    banned = [
        "DB connection checked out from pool",
        "DB connection returned to pool",
        "DB session committed",
    ]
    # 剥注释：本片在注释里逐字引用了这几句话作为"删掉的是什么"的说明
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    found = [b for b in banned if b in code]
    assert not found, (
        f"这些日志又回来了 {found} —— sqlalchemy.pool / sqlalchemy.engine "
        f"已经把同样的事件记进 db.log，这一份只会在 app.log 里抢操作员的窗口"
    )


def test_db_layer_keeps_the_real_signals():
    """删的是重复，不是信号 —— 建连(INFO,一次性)与回滚(WARNING)必须留。

    变异：把 `DB session rollback` 那条 warning 删掉 → 本门红。
    （这条是 P1-29 那个 422 能被查到根因的唯一来源。）
    """
    src = _src("app/db/database.py")
    assert 'logger.warning(f"DB session rollback' in src, (
        "回滚告警没了 —— 事务失败会变成静默"
    )
    assert 'logger.info("DB connection established (pool)")' in src, (
        "建连日志没了 —— 重连/连接池重建将无痕"
    )


# ── ③ 说谎的死类型不得复活 ────────────────────────────────────────


def test_dead_instrument_log_type_stays_deleted():
    """`InstrumentLog` 是零写入零读取的死类型，删了就别回来。

    ⚠ 真要做"仪器操作留存"，正解是往 `diagnostic_runs`（已有：参数/成败/
    **仪器原始回复**/耗时）里加，不是另起一张空表 —— 那正是它当初变成
    谎言的原因。

    变异：把 `class InstrumentLog(Base)` 加回 models → 本门红。
    """
    models = _src("app/models/instrument.py")
    schemas = _src("app/schemas/instrument.py")

    def _top_level_classes(text: str) -> set:
        return set(re.findall(r"^class (\w+)", text, re.M))

    assert "InstrumentLog" not in _top_level_classes(models), (
        "InstrumentLog 模型又回来了 —— 它是说谎的死类型（库里 0 行、无写入方）"
    )
    revived = _top_level_classes(schemas) & {
        "InstrumentLogCreate",
        "InstrumentLogResponse",
        "InstrumentLogListResponse",
    }
    assert not revived, f"这些死 schema 又回来了: {sorted(revived)}"

    # ⓪③⁺ 的文档镜像站点：自动生成的参数手册也在替这个已删的类型说话。
    # 内审 F7 抓到 —— 这类漏改**编译过、测试绿、看 diff 也看不出**，
    # 因为问题不在 diff 里，在 diff 没覆盖到的那一处。
    gen_doc = (
        _REPO_ROOT / "docs/features/virtual-road-test/parameter-reference-generated.md"
    )
    if gen_doc.exists():
        assert "InstrumentLog" not in gen_doc.read_text(encoding="utf-8"), (
            "自动生成的参数手册里还有 InstrumentLog —— 重跑 "
            "`docs/scripts/generate_parameter_docs.py`"
        )


# ── ④ 本片明确不做的那件事：别把 app.log 的总线定位改掉 ──────────


def test_app_log_stays_the_cross_cutting_bus():
    """`app.audit` 必须继续传播到 root（= 写进 app.log）。

    这是本片**刻意不动**的一处。关掉它 app.log 会干净很多，但
    `request_id` 的链条就从操作员默认看的那个文件里消失了 ——
    P1-34 刚建立的「只看这一次请求」当场作废。故障排除天生跨切面，
    必须有一个文件看得全。

    变异：把 `app.audit` 的 `propagate` 改成 False → 本门红。
    """
    src = _src("app/core/logging_config.py")
    m = re.search(
        r'config\["loggers"\]\["app\.audit"\]\s*=\s*\{(.+?)\}', src, re.S
    )
    assert m, "找不到 app.audit 的 logger 配置 —— 本门失效"
    assert re.search(r'"propagate":\s*True', m.group(1)), (
        "app.audit 不再传播到 app.log —— request_id 的链会从操作员默认看的"
        "文件里消失，P1-34 的「只看这一次请求」当场作废"
    )


# ── ⑤ GUI：「仅异常」必须真的是并集，不是某一个 level ──────────────

_LOG_VIEWER = "gui/src/features/Reports/components/SystemLogViewer.tsx"


def test_issues_view_covers_warning_error_and_critical():
    """后端 `level` 是**精确相等**，所以「WARNING 及以上」只能靠前端并流。

    变异：把 `ISSUE_LEVELS` 砍成只剩 `['ERROR']` → 本门红
    （那样分诊时会漏掉 WARNING，正是这一档要解决的问题）。
    """
    src = (_REPO_ROOT / _LOG_VIEWER).read_text(encoding="utf-8")
    m = re.search(r"const ISSUE_LEVELS = \[(.*?)\]", src, re.S)
    assert m, "找不到 ISSUE_LEVELS —— 「仅异常」的定义没了"
    levels = set(re.findall(r"'(\w+)'", m.group(1)))
    assert levels == {"WARNING", "ERROR", "CRITICAL"}, (
        f"「仅异常」覆盖的级别是 {sorted(levels)} —— 少一个就会在故障分诊时漏行"
    )

    # ⚠ 光检查常量不够 —— 内审 F1 原话：「从不检查它的**用处**」。
    # 实证：`ISSUE_LEVELS.slice(0, 1).join(',')` 让「仅异常」静默退化成只看
    # WARNING（ERROR/CRITICAL 全漏），而只看常量的门**全绿**。
    # 所以这里钉死：这个常量只准被整体 join，不准中途被切/筛/映射。
    uses = re.findall(r"ISSUE_LEVELS\.(\w+)", src)
    assert uses == ["join"], (
        f"ISSUE_LEVELS 的用法是 {uses}（应恰好一次 `.join`）—— "
        f"中间插了 slice/filter/map 就会静默少发级别，界面看不出来"
    )


def test_tail_and_export_share_one_filter_predicate():
    """`/tail` 与 `/export` 必须用**同一份**过滤谓词。

    P1-34 内审 F3 已经吃过一次亏（屏幕 5 条、导出全量）；根因是 `/export`
    自己抄了一份判断。抄出来的两份一定会漂 —— 本片把它删了，改成调用
    `_entry_matches`。

    变异：把 `/export` 的 `_entry_matches(...)` 换回自己写的逐条 if → 本门红。
    """
    src = _src("app/api/system_logs.py")

    # 精确取 `filtered_stream` 的函数体来判 —— 别用全文 grep：
    # 同文件 424 行还有个 `entry.level.upper()`，那是前端日志的**级别映射**，
    # 跟过滤谓词无关。第一版门就是这么误报的（粗正则连它一起数了）。
    body = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "filtered_stream":
            body = ast.get_source_segment(src, node)
            break
    assert body, "找不到 filtered_stream —— 本门失效"

    assert "_entry_matches(" in body, "/export 没有复用 _entry_matches，又自己抄了一份"
    for own in ("entry.level.upper()", "entry.session_id !=", "entry.hal_mode.lower()"):
        assert own not in body, (
            f"filtered_stream 里还留着自己那份判断 {own!r} —— "
            f"两份谓词一定会漂（P1-34 内审 F3：屏幕 5 条、导出全量）"
        )


def test_level_filter_is_set_membership_not_threshold():
    """`level` 收逗号集合，但**仍是精确匹配**，不是序数门槛。

    ⚠ `ZoneLogsAlerts`（P2-19 #258）的跨流去重依赖「不同 level 的流天然
    不相交」—— 改成门槛式（`>=`）会让不同流互相包含，那里当场出错。

    变异：把集合判断改成级别序数比较 → 本门红。
    """
    src = _src("app/api/system_logs.py")
    assert 'wanted = {p.strip().upper() for p in level.split(",") if p.strip()}' in src, (
        "level 不再按逗号拆成集合 —— 「仅异常」那一档会失效"
    )
    assert "if entry.level.upper() not in wanted:" in src, (
        "level 判断不再是集合成员判断 —— 若改成序数门槛，"
        "ZoneLogsAlerts 的跨流去重会出错"
    )


def test_screen_and_export_build_their_query_from_one_place():
    """屏幕与导出必须走**同一个** `buildLogQuery()`。

    内审 F1：早前两处各写了一份逐字相同的三元表达式，于是「改一处忘另一处」
    有两个入口 —— 内审造的变异（导出侧只发 `'ERROR'`、屏幕侧发哨兵值）
    **全绿**。合成一份之后那类分叉结构上不可能，这道存在性门才算数。

    ⚠ 这条只防「又抄了一份」。真正保证行为一致的是后端那条**行为门**
    `test_tail_and_export_return_the_same_rows`（逐条比对 /tail 与 /export）。
    存在性门只能当粗筛，旁边必须配行为门（CLAUDE.md ⓪④）。

    变异：把任一处改回内联三元 → 本门红。
    """
    src = (_REPO_ROOT / _LOG_VIEWER).read_text(encoding="utf-8")

    assert "function buildLogQuery(" in src, "buildLogQuery 不见了"
    calls = len(re.findall(r"buildLogQuery\(\{", src))
    assert calls == 2, (
        f"buildLogQuery 只被调用了 {calls} 次（预期 2：屏幕 + 导出）—— "
        f"有一处又自己拼参数了"
    )

    # 归一化只该发生在一处。数全文件的哨兵判断而不是"取函数体再看外面"——
    # 后者试过，`}): Record<string, string> {` 这行开头就是 `}`，
    # 非贪婪正则会在那里截断，把整个函数体判成"函数外"。
    sentinel_checks = len(re.findall(r"=== ISSUES", src))
    assert sentinel_checks == 1, (
        f"`=== ISSUES` 哨兵判断出现 {sentinel_checks} 次（应恰好 1 次，在 "
        f"buildLogQuery 里）—— 归一化又被抄了一份，漏一处就会把 "
        f"`__ISSUES__` 发给后端（精确匹配 → 0 行）"
    )
