"""P1-36 的门 —— 一次**测试执行**的日志要能串成一条链。

用户原话：「如何能将测试例标注在 log 中」。

修法跟 P1-34 的 `request_id` 是同一套（ContextVar + `ContextFilter` 自动注入 +
入口 set 一次 + 后端精确过滤），所以本文件只守**这次新增**的那几件事：

① **四种**执行入口都设了 id —— ⓪③ 的枚举纪律在这片当场救过场：
   roadmap 立项时只写了 `_run_case()`，实际枚举出**四种**执行
   （`test_case_runner` 后台任务 / `commissioning_api` 同步 /
   `commissioning_adhoc` 同步 / VRT），照原样做出来 4 种里只有 1 种带 id，
   而暗室首测恰恰是现场调试的主力。
   **VRT 也做了**（2026-08-05 用户当场纠正我先前的"不做"判断）：它确实没有
   可包住的运行作用域（`start`/`pause`/`stop` 各是一次独立请求），但用户指出
   ——「如果现在还不能定义 VRT 的所有细节，**至少开始和结束需要标记**」。
   成本几乎为零，且等 VRT 以后长出内部逻辑，标记已经在了。
   落点选 `VrtExecutionService.get()` —— 它是**唯一的解析点**
   （`_transition` 与 `fail` 都走它），比分散到 7 个跃迁方法里更不容易漏。

② `execution_id` 与 `session_id` 是**两个独立字段**，不许合并、不许互相覆盖 ——
   两个生命周期：一次执行跨多个请求、也可能完全不在请求里。

③ 后台任务**继承**发起它的请求的 `session_id`（溯源用），刻意保留。
"""

import ast
import logging
import re
from pathlib import Path

import pytest

from app.core.logging_config import (
    ContextFilter,
    current_execution_id,
    current_session_id,
)

_API_ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (_API_ROOT / rel).read_text(encoding="utf-8")


class _Capture(logging.Handler):
    """带 ContextFilter 的捕获 handler —— 必须带，否则 record 上根本没有
    `execution_id` 属性（注入是 filter 干的），门会变成恒真断言。"""

    def __init__(self):
        super().__init__()
        self.addFilter(ContextFilter())
        self.seen: list[tuple[str, str, str]] = []  # (msg, execution_id, session_id)

    def emit(self, record):
        self.filter(record)
        self.seen.append((
            record.getMessage(),
            getattr(record, "execution_id", "<缺>"),
            getattr(record, "session_id", "<缺>"),
        ))


@pytest.fixture
def cap():
    lg = logging.getLogger("app.test.p1_36")
    h = _Capture()
    # ⚠ 复位 `.disabled`：全量里别的用例会 in-process 跑 alembic，
    #   `fileConfig(disable_existing_loggers=True)` 把已导入的 logger 永久禁掉
    #   （memory feedback_test_logger_emit_alembic_pollution；P1-34 实测栽过一次）。
    prev = (lg.propagate, lg.disabled, lg.level)
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    lg.disabled = False
    lg.propagate = False
    try:
        yield lg, h
    finally:
        lg.removeHandler(h)
        lg.propagate, lg.disabled, lg.level = prev


# ── ① 行为门：注入链路真的通 ──────────────────────────────────────


def test_execution_id_reaches_the_log_record(cap):
    """set 一次 → 之后每条日志都带上，**零调用点改动**。

    变异：删掉 `ContextFilter` 里注入 execution_id 那行 → 本门红。
    """
    lg, h = cap
    token = current_execution_id.set("exec-1111")
    try:
        lg.info("执行期间干了点活")
    finally:
        current_execution_id.reset(token)

    ids = [e for m, e, _ in h.seen if "执行期间" in m]
    assert ids, "日志没被捕获，门本身失效"
    assert ids == ["exec-1111"], f"execution_id 没注入到日志: {ids}"


def test_execution_id_and_session_id_are_independent(cap):
    """两个 id 必须**同时**在，且互不覆盖。

    它们是两个生命周期：一次执行跨多请求、也可能不在请求里。
    合并成一个字段会让两条链都串不成。

    变异：把 `current_execution_id` 换成复用 `current_session_id` → 本门红。
    """
    lg, h = cap
    t1 = current_session_id.set("req-aaaa")
    t2 = current_execution_id.set("exec-bbbb")
    try:
        lg.info("一次执行里的一次请求")
    finally:
        current_execution_id.reset(t2)
        current_session_id.reset(t1)

    rows = [(e, s) for m, e, s in h.seen if "一次执行里" in m]
    assert rows == [("exec-bbbb", "req-aaaa")], (
        f"两个 id 没有各自独立地出现: {rows}"
    )


def test_no_execution_means_default_not_empty(cap):
    """不在执行里的日志（启动 / 后台心跳）如实是 `-`，不是空串。

    空串会让「按执行过滤」把这些行也捞进来。
    """
    lg, h = cap
    lg.info("跟任何执行都无关的一行")
    ids = [e for m, e, _ in h.seen if "无关的一行" in m]
    assert ids == ["-"], f"无执行上下文时 execution_id={ids}，应为 '-'"


def test_vrt_state_transitions_carry_the_execution_id(cap, monkeypatch):
    """**行为门**：VRT 的每次状态跃迁都必须带上执行身份。

    上面那道枚举门只证明"源码里写了 set"，证明不了"跃迁时真的带上了" ——
    存在性门旁边必须配行为门（CLAUDE.md ⓪④）。

    用户原话：「至少开始和结束需要标记」。这里就按开始（start）和
    结束（complete）各验一次。

    变异：把 `VrtExecutionService.get()` 里那行 set 删掉 → 本门红。
    """
    from app.services.road_test.vrt_execution_service import VrtExecutionService

    lg, h = cap
    svc = VrtExecutionService()

    class _Row:
        id = "exec-vrt-9999"

    # get() 是唯一解析点；用假 db 让它返回一行，只验 contextvar 有没有被设上
    class _Q:
        def filter(self, *a, **k): return self
        def first(self): return _Row()

    class _DB:
        def query(self, *a, **k): return _Q()

    # ⚠ 必须 reset（内审 F5）：不还原的话 `exec-vrt-9999` 会留在**进程级**
    #    上下文里，泄漏给同一进程内后续所有测试 —— 同文件的
    #    `test_no_execution_means_default_not_empty` 现在只是**侥幸排在它前面**，
    #    换个收集顺序就变顺序 flaky（同 feedback_test_logger_emit_alembic_pollution）。
    token = current_execution_id.set("-")
    try:
        row = svc.get(_DB(), "00000000-0000-0000-0000-000000009999")
        assert row is not None, "假 db 没返回行，门本身失效"

        lg.info("VRT 跃迁期间的一行日志")
        ids = [e for m, e, _ in h.seen if "VRT 跃迁期间" in m]
        assert ids == ["exec-vrt-9999"], (
            f"VRT 解析出执行之后，日志的 execution_id 是 {ids} —— "
            f"start / complete 这些跃迁的日志将归不了属"
        )
    finally:
        current_execution_id.reset(token)


def test_vrt_get_does_not_set_id_when_not_found(cap):
    """查不到就不该动 contextvar —— 否则会把上一次执行的 id 留在链上。"""
    from app.services.road_test.vrt_execution_service import VrtExecutionService

    class _Q:
        def filter(self, *a, **k): return self
        def first(self): return None

    class _DB:
        def query(self, *a, **k): return _Q()

    token = current_execution_id.set("exec-上一次")
    try:
        assert VrtExecutionService().get(_DB(), "00000000-0000-0000-0000-000000000001") is None
        assert current_execution_id.get() == "exec-上一次", (
            "查不到执行时 contextvar 被改了 —— 会把日志错误归属"
        )
    finally:
        current_execution_id.reset(token)


# ── ② 不变量门：三个入口都设了，一个都不能漏 ──────────────────────

# ⓪③ 的枚举结果 —— **四种执行全在列**（VRT 是用户 2026-08-05 当场纠正
# 我先前"不做"判断后补的）。
#
# ⚠ 这里**不数 `set(` 的出现次数**（内审 F2）：原来写的是 `n == expected`
#    的相等式，于是按 F1 的正确修法给 `run_phase` 补上 set 时，**门当场变红**
#    —— 它把 bug 锁成了契约，报错文案还反过来教育修复者"漏一处就串不成链"，
#    而真正漏掉的正是跑相位那处。数量门天然有这个毛病：它把"现在是几处"
#    当成了"应该是几处"。
#    改成：**每个真正 dispatch 的入口，其解析点都必须设过 id**（下方行为门）。
_MUST_INSTRUMENT = {
    "app/services/test_case_runner.py",
    "app/api/commissioning.py",
    "app/services/road_test/vrt_execution_service.py",
}


def test_every_execution_entry_point_sets_the_id():
    """四种执行**全部**都要设 —— 但判据是"设了没"，不是"设了几处"。"""
    for rel in _MUST_INSTRUMENT:
        assert "current_execution_id.set(" in _src(rel), (
            f"{rel} 里没有任何 current_execution_id.set() —— 这一类执行的日志永远串不成链"
        )


def test_commissioning_resolve_sets_the_resolved_execution_id(cap):
    """**行为门（内审 F1 的直接对策）**：暗室首测跑相位时必须带上执行身份。

    F1 实证：早前 set 在 `create_session` 里 —— 而那个端点**根本不跑相位**。
    真正 dispatch 的 `run_phase` / `run_all_phases` 一处都没有，内审探针实测
    `run-all` **51 条日志 0 条带 id**。而我拿来当证据的那一行
    （`Created MIMO_OTA session: execution_id=...`）**自己早就把 id 写进了消息
    文本** —— 验证打在了看起来的那一端（`feedback_effective_end_not_nominal`）。

    `_resolve_execution` 是 run_phase / run_all_phases / get_session 的唯一解析点。

    变异：把 `_resolve_execution` 里那行 set 删掉 → 本门红。
    """
    import app.api.commissioning as comm

    class _Exec:
        id = "e5555555-0000-0000-0000-000000000001"
        executed_by = sorted(comm.COMMISSIONING_CHAINS)[0]
        config = {}

    class _Q:
        def filter(self, *a, **k): return self
        def first(self): return _Exec()

    class _DB:
        def query(self, *a, **k): return _Q()

    token = current_execution_id.set("-")
    try:
        try:
            comm._resolve_execution(_DB(), "e5555555-0000-0000-0000-000000000001")
        except Exception:
            pass   # 解析之后的重建步骤可能因假对象失败 —— 只验 set 发生了

        assert current_execution_id.get() == "e5555555-0000-0000-0000-000000000001", (
            "解析出执行之后 contextvar 没被设上 —— run_phase / run_all_phases 的"
            "全部日志（含 HAL / SCPI）都会归不了属"
        )
    finally:
        current_execution_id.reset(token)   # 内审 F5：别把值泄漏给后续测试


def test_set_values_are_the_real_execution_id_not_a_constant():
    """**行为门（内审 F4）**：设的必须是**这次**执行的 id，不是常量。

    F4 实证：把三处 set 的值换成 `"-"` 或写死的 `"deadbeef"`，30~33 条测试
    **全绿** —— 原来的门只验"调了 set("，设的是什么无人过问。

    ⚠ 判据必须从**捕获的日志**里看，不能事后读 contextvar：
      `asyncio.run()` 新建上下文，任务里 set 的值**传不回调用方**
      （第一版就这么写的，恒为 '-'）。

    变异：把 `_run_case` 里 set 的值换成常量 → 本门红。
    """
    import asyncio
    import logging as _logging
    from uuid import uuid4
    from app.services.test_case_runner import _run_case

    eid = uuid4()
    runner_log = _logging.getLogger("app.services.test_case_runner")
    h = _Capture()
    prev = (runner_log.propagate, runner_log.disabled, runner_log.level)
    runner_log.addHandler(h)
    runner_log.setLevel(_logging.DEBUG)
    runner_log.disabled = False
    runner_log.propagate = False
    try:
        try:
            asyncio.run(_run_case(eid))
        except Exception:
            pass   # 没有真 DB / 真用例，跑不完；只验入口那一刻设的值
    finally:
        runner_log.removeHandler(h)
        runner_log.propagate, runner_log.disabled, runner_log.level = prev

    ids = {e for _, e, _ in h.seen}
    assert ids, "_run_case 一条日志都没产生，门本身失效"
    assert ids == {str(eid)}, (
        f"_run_case 期间日志的 execution_id 是 {ids}，应全是本次执行的 {eid} —— "
        f"设成常量的话所有执行共用一个 id，串出来的是一锅粥"
    )


def test_runner_sets_the_id_before_doing_any_work():
    """`_run_case` 必须在**干活之前**设 id，否则前面那几行日志归不了属。

    变异：把 set 挪到 `_run_case` 末尾 → 本门红。
    """
    src = _src("app/services/test_case_runner.py")
    fn = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_run_case":
            fn = ast.get_source_segment(src, node)
            break
    assert fn, "找不到 _run_case —— 本门失效"

    lines = [l.strip() for l in fn.splitlines() if l.strip()]
    body = [l for l in lines if not l.startswith(("#", '"""', "async def", "'''"))]
    # 跳过 docstring 后的第一条**可执行**语句就该是它
    first_exec = next((l for l in body if not l.startswith(('"', "'"))), "")
    assert "current_execution_id.set(" in first_exec, (
        f"_run_case 的第一条可执行语句是 {first_exec!r}，不是 set execution_id —— "
        f"在它之前产生的日志会归不了属"
    )


# ── ③ 不变量门：两个 id 不许被合并回一个 ──────────────────────────


def test_the_two_context_vars_stay_separate():
    """`execution_id` 不得改成复用 `session_id` 的那个 ContextVar。

    变异：把 `current_execution_id` 定义删掉、改成 `= current_session_id` → 本门红。
    """
    src = _src("app/core/logging_config.py")
    assert re.search(
        r"current_execution_id:\s*contextvars\.ContextVar\[str\]\s*=\s*contextvars\.ContextVar\(",
        src,
    ), "current_execution_id 不再是独立的 ContextVar —— 两条链会互相覆盖"
    # formatter 必须把两个都吐出来
    for field in ('"session_id":', '"execution_id":'):
        assert field in src, f"JsonFormatter 不再输出 {field}"


def test_filter_injects_execution_id():
    """注入必须发生在 `ContextFilter` 里 —— 那是唯一对**每条** record 生效的地方。

    变异：删掉 filter 里那行注入 → 本门红（连带上面三条行为门一起红）。
    """
    src = _src("app/core/logging_config.py")
    assert "record.execution_id = current_execution_id.get(" in src, (
        "ContextFilter 不再注入 execution_id —— 只有显式传 extra= 的调用点才会带，"
        "等于回到 P1-36 之前"
    )


# ── ④ GUI / 契约：两条链要并排看得见，且别再手写镜像 ────────────────

_REPO_ROOT = _API_ROOT.parent
_LOG_VIEWER = "gui/src/features/Reports/components/SystemLogViewer.tsx"


def _viewer_src() -> str:
    return (_REPO_ROOT / _LOG_VIEWER).read_text(encoding="utf-8")


def test_execution_column_is_visible_in_the_table():
    """执行链必须**在表格里直接看得见**，跟请求链并排。

    P1-34 的教训：把 id 只放在展开详情里，用户的反馈是「没看到 request_id
    真的落进日志了」—— 做了但看不见 = 没做。

    变异：删掉 `<Table.Th w={86}>执行</Table.Th>` → 本门红。
    """
    src = _viewer_src()
    for col in (">请求</Table.Th>", ">执行</Table.Th>"):
        assert col in src, f"日志表里缺 {col} —— 两条链没并排，看不出「这次执行里的这一个请求」"


def test_execution_filter_goes_through_the_shared_query_builder():
    """`execution_id` 必须由 `buildLogQuery()` 统一产出。

    P1-35 内审 F1 的教训：屏幕与导出各写一份归一化 → 必然分叉。
    新增维度若绕过它，导出就会漏掉这个过滤（屏幕 5 条、导出全量的复发）。

    变异：把 `q.execution_id = ...` 从 buildLogQuery 里删掉 → 本门红。
    """
    src = _viewer_src()
    assert "q.execution_id = opts.executionFilter" in src, (
        "buildLogQuery 不产出 execution_id —— 导出会跟屏幕分叉"
    )
    calls = len(re.findall(r"buildLogQuery\(\{", src))
    assert calls == 3, (
        f"buildLogQuery 被调用 {calls} 次（应为 3：实时屏幕 + 历史页 + 导出）"
    )
    # 归一化只该在一处：别处不得再拼 execution_id 参数
    outside = len(re.findall(r"params\.set\('execution_id'", src))
    assert outside == 0, "有地方绕过 buildLogQuery 自己拼 execution_id 参数"


def test_viewer_does_not_hand_write_the_log_entry_shape():
    """日志条目的形状只有一处真值源（`types/api.ts`），组件不得手写副本。

    本片实证：组件原先有一份逐字副本，加 `execution_id` 时它当场漂了
    （共享类型有、副本没有，编译直接红）。这是 P1-25「手写类型审计」的
    同一个母题 —— 手写镜像迟早跟真值源分家。

    变异：把 `interface LogEntry {...}` 写回组件 → 本门红。
    """
    src = _viewer_src()
    assert "interface LogEntry" not in src, (
        "组件里又手写了一份 LogEntry —— 用 types/api.ts 的 SystemLogEntry"
    )
    assert "SystemLogEntry as LogEntry" in src, "没有从共享类型导入"


def test_contract_carries_execution_id_end_to_end():
    """契约四步：yaml / 生成类型 / service.ts / mock 一处都不能少。

    少任一处的后果各不相同但都难查：yaml 少 → 外部调用方不知道有这个参数；
    生成类型少 → GUI 编译不过（这个会自己暴露）；service.ts 少 → 调用点
    传不了；**mock 少 → mock 下过滤不出来，而真后端能** —— 最后这种最坏，
    因为它让 mock 说谎。
    """
    # ⚠ 用**行级精确**匹配，别用子串：变异 M14 把它改成
    #   `name: execution_id_MUTANT`，子串检查照过（它确实"包含"那段文字）。
    #   P1-34 那轮也栽过同一形态（保留 token 的错写法绕过存在性门）。
    yaml_lines = {l.strip() for l in (_REPO_ROOT / "api/openapi.yaml").read_text(encoding="utf-8").splitlines()}
    assert "- name: execution_id" in yaml_lines, (
        "openapi.yaml 里没有精确的 `- name: execution_id` 查询参数 —— "
        "外部调用方（含 AI 训练语料的消费方）不会知道有这个过滤"
    )
    assert "execution_id:" in yaml_lines, "LogEntry schema 里没有 execution_id 字段"

    checks = {
        "gui/src/types/api.generated.ts": ["execution_id"],
        "gui/src/types/api.ts": ["execution_id: string"],
        "gui/src/api/service.ts": ["execution_id?: string"],
        "gui/src/api/mockServer.ts": ["params.execution_id"],
        "gui/src/api/mockDatabase.ts": ["e.execution_id !== executionId"],
    }
    for rel, tokens in checks.items():
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        for t in tokens:
            assert t in text, f"契约链断在 {rel}：缺 {t!r}"


# ── ⑤ 端到端行为门：真实链路（内审 F3） ──────────────────────────


def test_execution_id_survives_the_whole_pipeline(tmp_path):
    """**端到端**：真 logger → `JsonFormatter` → 落盘 → `_parse_log_line`。

    内审 F3 实证：把 `JsonFormatter` 里 `"execution_id"` 的取值源换成
    `getattr(record, "instrument_id", "-")`，**71 条测试全绿** ——
    因为所有行为门都停在 `LogRecord` 属性上，而文件侧的门喂的是**手写的
    JSON 行**。`emit → JsonFormatter → app.log → _parse_log_line` 这条真实
    链路，此前全仓没有一条测试走完。

    我原来的 M2 只是**存在性**变异（`'"execution_id":' in src`），
    保留 token 的错写法照样绕过 —— CLAUDE.md ⓪④ 明写：存在性门旁边必须配行为门。

    变异：把 formatter 的取值源接到别的字段 → 本门红。
    """
    import json
    import logging as _logging
    from app.core.logging_config import ContextFilter, JsonFormatter
    from app.api.system_logs import _parse_log_line

    log_file = tmp_path / "e2e.log"
    lg = _logging.getLogger("app.test.p1_36.e2e")
    fh = _logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    fh.addFilter(ContextFilter())
    prev = (lg.propagate, lg.disabled, lg.level)
    lg.addHandler(fh)
    lg.setLevel(_logging.INFO)
    lg.disabled = False
    lg.propagate = False

    token = current_execution_id.set("e2e-exec-7777")
    try:
        lg.info("走完整条链路的一行")
    finally:
        current_execution_id.reset(token)
        lg.removeHandler(fh)
        fh.close()
        lg.propagate, lg.disabled, lg.level = prev

    raw = log_file.read_text(encoding="utf-8").strip()
    assert raw, "什么都没落盘，门本身失效"

    # ① 落盘的 JSON 里字段值对
    obj = json.loads(raw)
    assert obj.get("execution_id") == "e2e-exec-7777", (
        f"落盘的 execution_id 是 {obj.get('execution_id')!r} —— "
        f"JsonFormatter 的取值源接错了（内审 F3 的变异形态）"
    )
    # ② 后端解析器读回来也对（tail / export 都走它）
    entry = _parse_log_line(raw)
    assert entry is not None and entry.execution_id == "e2e-exec-7777", (
        "_parse_log_line 没把 execution_id 读回来 —— 过滤会永远筛不到"
    )


def test_the_two_isolate_actions_are_symmetric():
    """两个「只看 X」必须**策略一致**：都只清 level / keyword，不清对方那条链。

    内审 F8：早前 `isolateExecution` 会清掉 `sessionFilter` 而
    `isolateRequest` 不清 `executionFilter` —— 于是"执行 A ∩ 请求 B"这个组合
    只能沿一个方向到达，而两个徽章都显示着，用户没法预期哪个会被清。
    两条链本就可以叠加（后端支持同时传）。

    变异：给任一个 isolate 加回 `setXxxFilter(null)` → 本门红。
    """
    src = _viewer_src()
    for name in ("isolateExecution", "isolateRequest"):
        m = re.search(rf"const {name} = \([^)]*\) => \{{(.*?)\n  \}}", src, re.S)
        assert m, f"找不到 {name} —— 本门失效"
        body = m.group(1)
        assert "clearTextFilters()" in body, f"{name} 没清 level/keyword —— 会返回交集而不是整条链"
        for other in ("setSessionFilter(null)", "setExecutionFilter(null)"):
            assert other not in body, (
                f"{name} 里出现了 {other} —— 两个 isolate 策略不对称，"
                f"「执行 A ∩ 请求 B」只能沿一个方向到达，而两个徽章都显示着"
            )


def test_request_side_lifecycle_logs_are_on_the_chain():
    """**行为门（Codex #286 R1）**：执行的**起点**和**取消**也得在链上。

    早前只在后台任务 `_run_case` 里设 —— 而 `launch_test_case_execution`
    的「开始执行」和 `request_cancel` 的「被请求取消」都打在**请求上下文**
    里，`execution_id` 为 `-`。于是按返回的 id 过滤日志，**恰恰漏掉这次
    执行的生命周期记录**。

    ⚠ `launch_...` 那处必须在 `create_task` **之前** —— 子任务继承的是
      创建那一刻的上下文（先 create 再 set，子任务拿不到）。

    变异：把任一处 set 删掉、或把 launch 那处挪到 create_task 之后 → 本门红。
    """
    src = _src("app/services/test_case_runner.py")

    # ⚠ 用 ast 精确取函数体，别用全文 rindex：`current_execution_id.set(
    #   str(execution_id))` 这个字符串在 `_run_case` 里**也有一份**，
    #   rindex 会找到那处（第一版就是这么错的：断言 12993 < 7362）。
    fns = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fns[node.name] = ast.get_source_segment(src, node)

    # ① 取消侧：set 必须在那条日志之前
    body = fns.get("request_cancel")
    assert body, "找不到 request_cancel —— 本门失效"
    i_set = body.index("current_execution_id.set(")
    i_log = body.index('"[case-runner] execution %s 被请求取消')
    assert i_set < i_log, "取消的 set 排在那条日志之后 —— 这行仍会归不了属"

    # ② 请求侧：set 必须在 create_task 之前（子任务继承创建那一刻的上下文）
    body2 = fns.get("launch_test_case_execution")
    assert body2, "找不到 launch_test_case_execution —— 本门失效"
    i_set2 = body2.index("current_execution_id.set(")
    assert i_set2 < body2.index("create_task(_run_case("), (
        "请求侧的 set 排在 create_task 之后 —— 子任务继承的是创建那一刻的"
        "上下文，设晚了后台那条链会拿不到"
    )
    assert i_set2 < body2.index('"[case-runner] 用例 %s (%s) 开始执行'), (
        "「开始执行」这条日志在 set 之前 —— 执行的起点不在链上"
    )
