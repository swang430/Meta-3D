"""C 组「会红的门」— 把反复靠记忆兜底的规则下沉成结构断言 (2026-07-26 用户批准)。

背景: memory 整理 C 组的原则是"少依赖记忆、多依赖会红的门" —— 凡是能机械判定的
规则, 变成一条新增即红的测试, 然后对应 memory 条目归档。本文件四道门, 每道注明
它替代的规则与实跑过的变异 (CLAUDE.md ⓪-④: 门不过变异 = 门不算数):

G1 单一 alembic head    ← memory feedback_find_alembic_head_with_command
   (双 head 会让 `upgrade head` 报错; 曾因 grep 误判把中间节点当 head)
   变异实跑: 临时放一个 down_revision 指向旧节点的迁移文件 → 红。
G2 路由无连续重复段     ← memory feedback_fastapi_router_prefix_no_double
   (#133: router prefix + 端点路径重写前缀 → /commissioning/commissioning/...
    → 调用方 404 静默失败; 单测调函数测不到路由)
   变异: 自测函数造 '/a/a' 必须被检出 (checker 自身有行为覆盖)。
G3 strict 门 bypass 开关四站点对齐 ← memory feedback_strict_gate_extend_bypass_toggle
   (#112 + #133 两次踩: 新加 precheck_strict_* 漏接 bypass fan-out →
    真硬件 bring-up 撞门无法绕过, mock 测不出)
   变异实跑: 注释掉 _request_overrides 里 cell_config 一行 → 红。
G4 HAL 静默吞异常棘轮   ← todo F64R-12 的"防新增"半边
   (谓词 = ExceptHandler 函数体恰为单条 pass; 2026-07-26 基线 38 处,
    #231 Codex 独立统计一致。修复存量时手动下调基线, 锁住进度)
   变异: 自测函数对合成源码计数 2/2; 实跑给驱动加一处裸 pass → 红。

⚠ 本文件的判定全部走 AST / live import / model_fields, 不 grep 源码文本
  (例外: G3 的 GUI 站点是 .ts 文件, 剥注释后做 token 存在性检查 —— 存在性门
  只当粗筛, 后端三个站点有行为/集合门兜底)。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_API_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_SERVICE_ROOT.parent
_HAL_DIR = _API_SERVICE_ROOT / "app" / "hal"


# ─────────────────────────────────────────────────────────────────────
# G1 单一 alembic head
# ─────────────────────────────────────────────────────────────────────

def test_g1_single_alembic_head():
    """alembic 必须恰好一个 head — 多 head 时 `upgrade head` 直接报错。

    新迁移的 down_revision 必须指向**当前唯一 head** (用 `alembic heads` 查,
    别 grep — grep 会漏无注解/双引号写法, 把中间节点误当 head)。
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_API_SERVICE_ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, (
        f"alembic 出现 {len(heads)} 个 head: {heads} — 新迁移的 down_revision "
        f"没指向当前 head。用 `alembic heads` 定位, 合并成单链后再提交。"
    )


# ─────────────────────────────────────────────────────────────────────
# G2 路由无连续重复段
# ─────────────────────────────────────────────────────────────────────

def _doubled_segments(paths):
    """返回 [(path, 重复段)] — 连续两段相同 (参数段 {x} 除外) 视为双前缀事故。"""
    bad = []
    for p in paths:
        segs = [s for s in p.split("/") if s]
        for i in range(len(segs) - 1):
            if segs[i] == segs[i + 1] and not segs[i].startswith("{"):
                bad.append((p, segs[i]))
    return bad


def test_g2_checker_detects_doubled_segment():
    """G2 的行为自测: checker 必须能抓出坏路径 (防 checker 本身空转)。"""
    assert _doubled_segments(["/commissioning/commissioning/device-selfcheck"]) == [
        ("/commissioning/commissioning/device-selfcheck", "commissioning")
    ]
    assert _doubled_segments(["/a/{id}/{id2}", "/a/b/a"]) == []


def test_g2_no_doubled_route_segments():
    """全部注册路由无连续重复段 — router prefix 与端点路径重写前缀会撞出
    /commissioning/commissioning/... 这类 404 静默失败 (#133 实例)。
    端点路径只写 prefix 之后的部分。"""
    from app.main import app

    bad = _doubled_segments(getattr(r, "path", "") for r in app.routes)
    assert not bad, (
        f"路由出现连续重复段 (router prefix 又写进了端点路径?): {bad}"
    )


# ─────────────────────────────────────────────────────────────────────
# G3 strict 门 bypass 开关四站点对齐
# ─────────────────────────────────────────────────────────────────────

# 显式豁免表: 豁免必须带理由; 若豁免的 flag 从权威定义消失, 下面的
# test_g3_exceptions_not_stale 会红 (豁免表自清洁)。
_STRICT_FLAG_EXCEPTIONS = {
    # input_level 不是 precheck 门: 它在 measure phase 内部跑输入电平闭环,
    # 自带 opt-out 语义 (False = 不收敛降级 warning) 且 CE/BS 缺 capability
    # 时自动跳过; 其 opt-in 路径是 TestCase 配置 (schemas 注释: "GUI 不暴露,
    # fixture/config 级别 opt-in")。该 flag 早于 #112 规则确立 (2026-05-28),
    # #112 用户审计时亦未纳入。是否补 session 旁路 = 语义决策, 记 backlog
    # (onsite-20260721-todo.md), 不由本门裁决。
    "precheck_strict_input_level",
}


def _authority_strict_flags():
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration

    return {
        name
        for name in MIMOOTAConfiguration.model_fields
        if name.startswith("precheck_strict_")
    }


def test_g3_exceptions_not_stale():
    """豁免表里的 flag 必须仍存在于权威定义 — 否则豁免是死条目, 当场清。"""
    stale = _STRICT_FLAG_EXCEPTIONS - _authority_strict_flags()
    assert not stale, f"豁免表引用了已不存在的 flag: {stale} — 从豁免表删除"


def test_g3_create_session_request_covers_all_flags():
    """站点①: CreateSessionRequest 必须为每个 (非豁免) strict flag 提供
    Optional[bool] 旁路字段; 反向: 不得出现权威没有的孤儿旁路。"""
    from app.api.commissioning import CreateSessionRequest

    expected = _authority_strict_flags() - _STRICT_FLAG_EXCEPTIONS
    request_flags = {
        name
        for name in CreateSessionRequest.model_fields
        if name.startswith("precheck_strict_")
    }
    missing = expected - request_flags
    orphan = request_flags - _authority_strict_flags()
    assert not missing, (
        f"新加的 strict 门没接 CreateSessionRequest 旁路 (bring-up 将无法绕过): {missing}"
    )
    assert not orphan, f"CreateSessionRequest 有权威定义之外的孤儿旁路: {orphan}"


def test_g3_request_overrides_carry_every_flag():
    """站点②(行为门): 每个旁路字段显式 False 必须真被 _request_overrides 带出,
    None 必须一个都不漏进 (None 漏进会把门对所有人放空, PR #75 教训)。"""
    from app.api.commissioning import CreateSessionRequest, _request_overrides

    expected = _authority_strict_flags() - _STRICT_FLAG_EXCEPTIONS

    none_overrides = _request_overrides(CreateSessionRequest())
    leaked = {f for f in expected if f in none_overrides}
    assert not leaked, f"None 值泄漏进 overrides (会 falsy 放空门): {leaked}"

    for flag in sorted(expected):
        overrides = _request_overrides(CreateSessionRequest(**{flag: False}))
        assert overrides.get(flag) is False, (
            f"{flag}=False 没被 _request_overrides 带出 — 旁路字段声明了但没接线"
        )


def _strip_ts_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", src)


def test_g3_gui_labsmoke_covers_all_flags():
    """站点③: GUI 主控台 labSmoke 必须对每个 (非豁免) flag 有 `body.<flag>` **赋值**。

    ⚠ 查的是赋值不是裸 token (#232 Codex P2): flag 在类型声明 (`precheck_strict_x?:
    boolean`) 和赋值 (`body.precheck_strict_x = false`) 各出现一次 —— 只查裸 token
    会被"删了赋值、类型声明还在"绕过, 而那正是 #112 的原始形态 (GUI 没接线)。
    `body.` 前缀把检查钉在生效端; 类型声明那一侧删漏由 `npm run build` (tsc) 兜底。
    """
    api_ts = _REPO_ROOT / "gui" / "src" / "components" / "Commissioning" / "api.ts"
    assert api_ts.is_file(), f"GUI labSmoke 文件不在预期路径: {api_ts}"
    text = _strip_ts_comments(api_ts.read_text(encoding="utf-8"))

    expected = _authority_strict_flags() - _STRICT_FLAG_EXCEPTIONS
    # ⚠ 两轮变异/审查逐步收紧到"赋值形态":
    #   ① 裸 token `in` 判 → 被子串 (calX) 假绿 (首轮变异抓出);
    #   ② `\bbody\.<flag>\b` → 被"删赋值、别处留读取/插值"假绿 (#232 R2 P2);
    #   ③ 现钉 `body.<flag> = false` 赋值本身 — labSmoke 分支的真实写法
    #     (api.ts:82-89)。若将来合法改写成别的赋值形态, 门会红一次, 改这条
    #     正则时请保持"钉赋值不钉出现"的原则。
    missing = {
        f
        for f in expected
        if not re.search(rf"\bbody\.{re.escape(f)}\s*=\s*false\b", text)
    }
    assert not missing, (
        f"GUI labSmoke (Commissioning/api.ts) 缺 `body.<flag> = false` 赋值: {missing} — "
        f"真硬件 bring-up 在 GUI 上将无法跳过该门 (#112/#133 母题)"
    )


def test_g3_override_test_table_covers_all_flags():
    """站点④: test_commissioning_strict_gate_overrides 的 flag 表必须与权威
    (非豁免) 集合完全一致 — 表漏一个, 那个 flag 的 null/False/value 组合就没人测。"""
    from tests.test_commissioning_strict_gate_overrides import _ALL_STRICT_FLAGS

    expected = _authority_strict_flags() - _STRICT_FLAG_EXCEPTIONS
    assert set(_ALL_STRICT_FLAGS) == expected, (
        f"覆盖测试的 flag 表与权威定义不一致: 缺 {expected - set(_ALL_STRICT_FLAGS)}, "
        f"多 {set(_ALL_STRICT_FLAGS) - expected}"
    )


# ─────────────────────────────────────────────────────────────────────
# G4 HAL 静默吞异常棘轮
# ─────────────────────────────────────────────────────────────────────

# 2026-07-26 基线 (F64R-12; 总数 38 与 #231 Codex 独立统计一致)。
# 谓词: ExceptHandler 函数体恰为单条 `pass` — 纯静默吞。
# `except: return None` 等非 pass 形态的静默吞不在此谓词内 (扩谓词先改这里
# 的注释与函数, 再整体重扫, 别在旧清单上手工加减)。
# ⚠ 按「文件 × 所在函数」锁, 不按净计数 (#232 R2 P2): 净计数会放过
#   "删一处旧的、同文件别处加一处新的"的换位; 按函数锁能抓跨函数换位。
#   **同一函数内**的换位仍不可见 — 行号做键会在任何无关编辑上误红, 不值;
#   这是本门的已知边界, F64R-12 修存量时会自然消解。
# 修复存量时把对应条目**下调/删除** — 棘轮只进不退。
_SILENT_SWALLOW_BASELINE = {
    "aerotech_positioner.py": {"_silent_reconnect": 2, "disconnect": 1},
    "cmw500_base_station.py": {
        "get_throughput_metrics": 6, "get_ue_info": 1, "start_signaling": 1,
    },
    "keysight_ena.py": {"_silent_reconnect_visa": 1},
    "propsim_f64.py": {
        "_clear_error_queue": 1, "_do_ftp": 1, "_do_query_unlocked": 1,
        "_do_write_unlocked": 1, "_first_error": 1, "_silent_reconnect_visa": 1,
        "disconnect": 1, "parse_f64_sys_info": 2, "set_calibration_tone": 3,
    },
    "propsim_fs16.py": {"_parse_sys_info": 2, "_silent_reconnect_visa": 1},
    "rf_switch.py": {"disconnect": 2},
    "uxm_base_station.py": {
        "_silent_reconnect_visa": 1, "get_throughput_metrics": 8,
    },
}


def _bare_pass_sites_by_function(source: str) -> dict:
    """{所在函数名: 裸 pass handler 数}; 模块级记 '<module>', 嵌套取最内层函数。"""
    tree = ast.parse(source)
    counts: dict = {}

    def _walk(node, func):
        for child in ast.iter_child_nodes(node):
            child_func = (
                child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                else func
            )
            if (
                isinstance(child, ast.ExceptHandler)
                and len(child.body) == 1
                and isinstance(child.body[0], ast.Pass)
            ):
                counts[func] = counts.get(func, 0) + 1
            _walk(child, child_func)

    _walk(tree, "<module>")
    return counts


def test_g4_counter_behavior():
    """G4 的行为自测: 计数器按函数归属数得对 (含嵌套/async/模块级),
    带日志的和 except-return 的都不算 (防谓词空转)。"""
    src = (
        "def outer():\n"
        "    try:\n        a()\n    except Exception:\n        pass\n"
        "    def inner():\n"
        "        try:\n            b()\n        except Exception:\n            pass\n"
        "    try:\n        c()\n    except Exception:\n        logger.warning('x')\n"
        "async def aio():\n"
        "    try:\n        d()\n    except Exception:\n        pass\n"
        "def ret():\n"
        "    try:\n        e()\n    except Exception:\n        return None\n"
        "try:\n    f()\nexcept Exception:\n    pass\n"
    )
    assert _bare_pass_sites_by_function(src) == {
        "outer": 1, "inner": 1, "aio": 1, "<module>": 1,
    }


def test_g4_silent_swallow_ratchet():
    """app/hal 逐「文件 × 函数」裸 pass 计数必须精确等于基线 — 新增即红,
    跨函数换位也红 (吞异常不等于吞信息, 见 F64R-12); 修掉存量后同步下调
    基线, 把进度锁死。"""
    actual = {}
    for py in sorted(_HAL_DIR.glob("*.py")):
        sites = _bare_pass_sites_by_function(py.read_text(encoding="utf-8"))
        if sites:
            actual[py.name] = sites

    if actual != _SILENT_SWALLOW_BASELINE:
        diff_lines = []
        for fname in sorted(set(actual) | set(_SILENT_SWALLOW_BASELINE)):
            a = actual.get(fname, {})
            b = _SILENT_SWALLOW_BASELINE.get(fname, {})
            for func in sorted(set(a) | set(b)):
                if a.get(func, 0) != b.get(func, 0):
                    diff_lines.append(
                        f"  {fname}::{func}: 基线 {b.get(func, 0)} → 现在 {a.get(func, 0)}"
                    )
        raise AssertionError(
            "HAL 静默吞异常分布偏离基线 (逐文件×函数):\n"
            + "\n".join(diff_lines)
            + "\n新增吞异常时: 要么记一句 logger.debug/warning 再吞 (吞异常不吞信息), "
            "要么给出手册/协议依据后调整基线; 修掉存量则下调基线锁进度。"
        )


# ============================================================================
# G5 GUI 不再调用计划路由 (ARCH-1 S4a, 设计稿 §4 门 D-h)
# ============================================================================

# `/test-plans` 这个前缀下**同时**挂着两条链:
#   ① 计划链 (S4 拆除): /test-plans, /test-plans/{id}, /queue, /steps, /start …
#   ② 用例链 (**保留**): /test-plans/cases* —— 用例库 CRUD + ARCH-1 S1 的执行正门
# 所以判据必须带 /cases 例外。写成"全 GUI 不许出现 /test-plans"会**误杀**
# 用例链 —— 那种门红在正确的代码上, 比漏判更难查 (设计稿 §5.6)。
_PLAN_ROUTE_KEEP_PREFIX = "/test-plans/cases"

# axios 调用里 URL 的三种字面量写法 (单引号 / 反引号模板 / 双引号)。
_PLAN_ROUTE_CALL = re.compile(r"""["'`](/test-plans[^"'`]*)["'`]""")


def _gui_ts_sources():
    gui_src = _REPO_ROOT / "gui" / "src"
    if not gui_src.is_dir():
        return []
    return [
        p
        for p in gui_src.rglob("*")
        if p.suffix in {".ts", ".tsx"} and "node_modules" not in p.parts
    ]


def _gui_plan_route_calls(sources=None):
    """返回 [(相对路径, URL)] —— GUI 里打到**计划链**路由的调用点。

    剥注释后再匹配: 注释里提"原先读 /test-plans/{id}/executions"是文档不是调用,
    不该让门红 (换源后的 ExecutionSelector 就有这么一句)。
    """
    hits = []
    for path in sources if sources is not None else _gui_ts_sources():
        text = _strip_ts_comments(path.read_text(encoding="utf-8", errors="ignore"))
        for url in _PLAN_ROUTE_CALL.findall(text):
            if url.startswith(_PLAN_ROUTE_KEEP_PREFIX):
                continue
            try:
                shown = str(path.relative_to(_REPO_ROOT))
            except ValueError:  # 自覆盖测试喂的是 tmp_path, 不在仓库下
                shown = str(path)
            hits.append((shown, url))
    return hits


def test_g5_gui_has_no_test_plan_route_calls():
    """站点⑤: GUI 里不得再有打到计划链路由的调用 (用例链 /test-plans/cases* 除外)。

    替代的规则: 设计稿 §4 的 D-h —— 此前只是作者手跑一次 grep。不落成门的代价:
    S4b 删后端路由时, 若 GUI 还剩一处调用, **什么都不会红** —— 编译门是语法层,
    happy-path 浏览器走查不会去点一个"本来就该没有的按钮"。#243 round-2 外审
    抓到的报告向导两个选择器 (读方向) 正是这么漏的: 当时的判据只查了 createTestPlan
    这个**写**入口。

    变异实跑 (CLAUDE.md ⓪-④):
      ① 给 gui/src/api/service.ts 插一行 `client.get('/test-plans')` → 本门红 ✓
      ② 插一行 `client.get('/test-plans/cases')` → 本门**保持绿** ✓ (防误杀,
         由 test_g5_keep_prefix_not_flagged 常驻覆盖)
    """
    hits = _gui_plan_route_calls()
    assert not hits, (
        "GUI 仍在调用计划链路由 (ARCH-1 S4 已拆除, S4b 删掉后端后这些调用会 404):\n"
        + "\n".join(f"  {p} → {u}" for p, u in hits)
    )


def test_g5_checker_catches_plan_call_and_spares_cases(tmp_path):
    """G5 判定器自身的行为覆盖 — 两个方向都要对。

    这是 G5 的"变异常驻化": 光有上面那条空集断言, 判定器写错 (比如例外前缀写成
    `/test-plans` 把全部放行) 也一样绿。
    """
    f = tmp_path / "probe.ts"

    f.write_text("const r = await client.get('/test-plans')\n", encoding="utf-8")
    assert _gui_plan_route_calls([f]), "判定器漏判: 计划链调用没被抓出"

    f.write_text("const r = await client.get(`/test-plans/${id}/steps`)\n", encoding="utf-8")
    assert _gui_plan_route_calls([f]), "判定器漏判: 模板字面量形式的计划链调用"

    f.write_text("const r = await client.get('/test-plans/cases/x/execute')\n", encoding="utf-8")
    assert not _gui_plan_route_calls([f]), (
        "判定器误杀: /test-plans/cases* 是保留集 (S1 执行正门), 不得被判违例"
    )

    f.write_text("// 原先读 '/test-plans/{id}/executions', 已换源\n", encoding="utf-8")
    assert not _gui_plan_route_calls([f]), "判定器误杀: 注释里提到的旧路由不是调用"


# ============================================================================
# G6 计划链路由全部消失 (ARCH-1 S4b, 设计稿 §3 门 D-f)
# ============================================================================

# 逐条列, 不写 "少了几条" —— 设计稿 v1 的 D-f 写的是 34 条, 漏了后来查出的两条
# 读旧表的孤儿路由 (§1.7), 那两条本可以完好幸存而所有门全绿 (Codex #245 C-2)。
# 教训: 数字型断言必须跟删除集同源, 否则集合一变门就悄悄失效。
_DELETED_PLAN_ROUTES = [
    # ── plan CRUD (7) ──
    ("POST",   "/api/v1/test-plans"),
    ("GET",    "/api/v1/test-plans"),
    ("GET",    "/api/v1/test-plans/{id}"),
    ("PATCH",  "/api/v1/test-plans/{id}"),
    ("DELETE", "/api/v1/test-plans/{id}"),
    ("POST",   "/api/v1/test-plans/{id}/duplicate"),
    ("POST",   "/api/v1/test-plans/{id}/mark-ready"),
    # ── queue (7) ──
    ("POST",   "/api/v1/test-plans/queue"),
    ("GET",    "/api/v1/test-plans/queue"),
    ("POST",   "/api/v1/test-plans/queue/reorder"),
    ("DELETE", "/api/v1/test-plans/queue/{id}"),
    ("POST",   "/api/v1/test-plans/queue/{id}/move-up"),
    ("POST",   "/api/v1/test-plans/queue/{id}/move-down"),
    ("PATCH",  "/api/v1/test-plans/queue/{id}"),
    # ── steps (6) ──
    ("GET",    "/api/v1/test-plans/{id}/steps"),
    ("POST",   "/api/v1/test-plans/{id}/steps"),
    ("PATCH",  "/api/v1/test-plans/{id}/steps/{sid}"),
    ("DELETE", "/api/v1/test-plans/{id}/steps/{sid}"),
    ("POST",   "/api/v1/test-plans/{id}/steps/reorder"),
    ("POST",   "/api/v1/test-plans/{id}/steps/{sid}/duplicate"),
    # ── 生命周期 (5) ──
    ("POST",   "/api/v1/test-plans/{id}/start"),
    ("POST",   "/api/v1/test-plans/{id}/pause"),
    ("POST",   "/api/v1/test-plans/{id}/resume"),
    ("POST",   "/api/v1/test-plans/{id}/cancel"),
    ("POST",   "/api/v1/test-plans/{id}/complete"),
    # ── 单挂 (3) ──
    ("POST",   "/api/v1/test-plans/{id}/preflight"),
    ("PUT",    "/api/v1/test-plans/{id}/topology-profile"),
    ("GET",    "/api/v1/test-plans/{id}/executions"),
    # ── scenario→计划桥 (2) ──
    ("POST",   "/api/v1/scenarios/{id}/create-test-plan"),
    ("GET",    "/api/v1/scenarios/{id}/test-plans"),
    # ── test_sequence 组 (4) ──
    ("GET",    "/api/v1/test-sequences"),
    ("GET",    "/api/v1/test-sequences/categories"),
    ("GET",    "/api/v1/test-sequences/popular"),
    ("GET",    "/api/v1/test-sequences/{id}"),
    # ── §1.7 读旧表 test_plan_executions 的孤儿 (2) ──
    ("GET",    "/api/v1/test-executions/{id}"),
    ("DELETE", "/api/v1/test-executions/{id}"),
]

# ARCH-1 S1 的执行正门 + 用例库 CRUD —— **必须活着**。
# 这一半跟上面同等重要: 判据只查"计划路由没了"而不查"用例路由还在",
# 会让一次误删悄悄通过 (G5 那条的 /cases 例外是同一个道理)。
# ⚠️ 带 method —— 与 _DELETED_PLAN_ROUTES 同构 (内审 F2)。
# 只比路径会让"误删 POST /cases 但 GET /cases 还在"这类形态全绿:
# 路径形状仍命中, 而建用例/改用例/删用例三条在后端**零 HTTP 测试覆盖**,
# 被误删时没有任何别的门会红。
_SURVIVING_CASE_ROUTES = [
    ("POST",   "/api/v1/test-plans/cases"),
    ("GET",    "/api/v1/test-plans/cases"),
    ("GET",    "/api/v1/test-plans/cases/grouped"),
    ("GET",    "/api/v1/test-plans/cases/{test_case_id}"),
    ("PATCH",  "/api/v1/test-plans/cases/{test_case_id}"),
    ("DELETE", "/api/v1/test-plans/cases/{test_case_id}"),
    ("POST",   "/api/v1/test-plans/cases/{test_case_id}/execute"),
    ("GET",    "/api/v1/test-plans/cases/executions/{execution_id}"),
]


def _live_route_table():
    """(method, path) 集合 —— 从真实 app 读, 不 grep 源码。"""
    from app.main import app
    table = set()
    for r in app.routes:
        for m in getattr(r, "methods", None) or ():
            table.add((m, r.path))
    return table


def test_g6_deleted_plan_routes_are_gone():
    """站点⑥: 36 条计划链路由逐条不在路由表里 (设计稿 §3 D-f)。

    判据打在**真实 app 的路由表**上, 不 grep 源码 —— 源码里删干净了但 router
    没摘掉注册(或反之)都会被这条抓住。

    变异实跑 (⓪-④):
      - 把 api/test_plan.py 的 `POST ""` 恢复回去 → 红
      - 把 scenario.router 的注册加回 main.py → 红
    """
    live = _live_route_table()
    # 路径参数名不参与比较 —— 只比结构 (段数 + 字面段)。
    def shape(path):
        return tuple("{}" if s.startswith("{") else s for s in path.split("/"))

    live_shapes = {(m, shape(p)) for m, p in live}
    survivors = [
        f"{m} {p}" for m, p in _DELETED_PLAN_ROUTES
        if (m, shape(p)) in live_shapes
    ]
    assert not survivors, (
        "计划链路由仍在路由表里 (ARCH-1 S4b 应已全删):\n  "
        + "\n  ".join(survivors)
    )


def test_g6_case_routes_survive():
    """站点⑥的另一半: 用例链必须**还在** —— 防"删过头"。

    S4 反复踩的坑是判据过宽 (设计稿 §5.6): 一条只查"计划路由没了"的门,
    在有人把 /cases 一起删掉时照样绿。
    """
    def shape(path):
        return tuple("{}" if seg.startswith("{") else seg for seg in path.split("/"))
    live_shapes = {(m, shape(p)) for m, p in _live_route_table()}
    missing = [
        f"{m} {p}" for m, p in _SURVIVING_CASE_ROUTES
        if (m, shape(p)) not in live_shapes
    ]
    assert not missing, (
        "用例链路由被误删 (S1 的执行正门 / 用例库 CRUD 必须活着):\n  "
        + "\n  ".join(missing)
    )


# ============================================================================
# G7 / G8 文档与实况一致 (ARCH-1 S5, 设计稿 §3 门 D-1 / D-2)
# ============================================================================
#
# 为什么需要门, 而不是改一遍文档了事:
#   CLAUDE.md 写着「4个主要 Tab: 计划管理、步骤编排、执行队列、执行历史」,
#   而 S4a 是把 **6** 个 Tab 砍成 3 个 —— 也就是说这行在 S4 动手**之前**就已经错了。
#   文档和代码之间没有任何东西把它们绑在一起, 手改一次, 下次照样漂, 而且可能
#   几个月后才被发现。这两道门是那根绳子。
#
# 分档 (CLAUDE.md ⓪-④, 至少要到"不变量"档):
#   G7 = 集合相等 (文档声明的 Tab 标签集 == 从 JSX 派生的标签集), **不变量档**
#   G8 = 集合成员 (文档提到的计划链路径 ⊆ 真实路由表), **不变量档**
#   设计稿原列的 D-3「禁词存在性门」**已撤销**, 理由见 G7 docstring 末尾。

# §1.1 的路径规则: 这些位置是**历史留档**, 记的是当时的事实, 门不该管它们。
# 改历史记录不是修文档, 是伪造 —— 一份 2026-05-13 的现场日志写着"跑了测试计划",
# 那天确实跑了。
_DOC_ARCHIVE_DIRS = ("docs/archive/", "docs/site-debug/", "docs/design/")
_DOC_ARCHIVE_FILES = ("docs/roadmap-archive.md", "docs/project-retrospective.md")
# 文件名里带日期的 = 某天的记录 (onsite-20260721-todo.md / caict-2026-05-13.md …)
_DOC_DATED_NAME = re.compile(r"\d{4}-?\d{2}-?\d{2}")
# 厂商手册, 不是我们的文档
_DOC_FOREIGN_DIRS = ("Instrument_API_Doc/", "node_modules/", "gui/node_modules/")


def _live_doc_paths():
    """仓库里**描述当下实况**的 markdown —— 历史留档按 §1.1 路径规则排除。

    判定全靠路径, 不读内容: 新增文档自动进网, 不需要维护一张 A 类清单
    (手工清单正是 S4 反复漏枚举的那个失败形态)。
    """
    out = []
    for path in _REPO_ROOT.rglob("*.md"):
        rel = path.relative_to(_REPO_ROOT).as_posix()
        if any(rel.startswith(d) for d in _DOC_FOREIGN_DIRS):
            continue
        if any(rel.startswith(d) for d in _DOC_ARCHIVE_DIRS):
            continue
        if rel in _DOC_ARCHIVE_FILES:
            continue
        if _DOC_DATED_NAME.search(path.name):
            continue
        out.append(path)
    return out


# ── G7: Tab 标签集合 ────────────────────────────────────────────────────
#
# marker 形态 (与散文写在**同一行**, 渲染后不可见):
#     - 3 个主要 Tab: 测试用例库、执行历史、虚拟路测 <!-- gate:tabs=测试用例库,执行历史,虚拟路测 -->
#
# 看着冗余, 是**故意**的: 散文的分隔符 / 措辞 / 语言随时会变, 让门去散文里抠标签
# 就是把门建在流沙上。marker 把契约外化成机器可读的一行, 门再额外断言"同一行的
# 散文里逐字含这几个标签" —— 这样"改了散文没改 marker"和"改了 marker 没改散文"
# 两个方向都会红。
_TAB_MARKER = re.compile(r"<!--\s*gate:tabs=([^>]*?)\s*-->")
# ⚠️ 属性段不能写成 `[^>]*` —— `leftSection={<IconChecklist size={16} />}` 里**有 `>`**,
# 那样会在 `/>` 处提前收尾, 把 `}>\n  测试用例库` 整段当成标签 (写这道门时实际踩到)。
# 用非贪婪 `.*?` + 标签字符类排除 `<>{}`: 第一次尝试停在 IconChecklist 的 `>` 上时,
# 后面紧跟的 `}` 不在标签字符类里 → 回溯到真正的开标签 `>`。
_TAB_JSX = re.compile(
    r"<Tabs\.Tab\b.*?>\s*(?P<label>[^<>{}]+?)\s*</Tabs\.Tab>",
    re.S,
)
_TAB_SOURCE = "gui/src/features/TestManagement/TestManagement.tsx"


def _live_tab_labels():
    """真值: 从 TestManagement.tsx 的 JSX 派生的 Tab 中文标签, **按渲染顺序**。"""
    src = (_REPO_ROOT / _TAB_SOURCE).read_text(encoding="utf-8")
    return [m.group("label") for m in _TAB_JSX.finditer(src)]


def test_g7_checker_parses_tab_labels():
    """判定器自身的行为覆盖 —— 光有下面那条集合断言, 正则写错(比如永远返回空)
    也一样绿 (空集 == 空集)。这条钉住真值抽取本身。
    """
    labels = _live_tab_labels()
    assert len(labels) >= 2, f"Tab 标签抽取失败, 只拿到 {labels!r} —— 正则跟 JSX 漂了"
    assert all(lbl.strip() and "<" not in lbl for lbl in labels), labels


def test_g7_docs_declare_actual_tab_labels():
    """站点⑦: 文档声明的 Tab 标签集 == 代码里的 Tab 标签集 (设计稿 §3 D-1)。

    替代的规则: 无 —— 此前没有任何东西守着"文档说的 Tab 和代码里的 Tab 一致"。
    不落成门的代价有实证: CLAUDE.md 那行在 S4 **之前**就已经错了 (写 4 个,
    当时实际 6 个), 一直到 ARCH-1 S5 才被发现。

    三条断言, 缺一个都能被绕过:
      ① marker 至少存在一处 —— 否则"把 marker 删掉"就能让门永远绿;
      ② 每处 marker 声明的标签**列表**(有序) == 从 JSX 派生的列表 —— 增删改序全红;
      ③ marker 所在行的散文里逐字含每个标签 —— 堵住"只改 marker 不改散文"。

    变异实跑 (CLAUDE.md ⓪-④, 双向):
      - 代码侧: 给 TestManagement.tsx 加第 4 个 <Tabs.Tab> 不改文档 → 红 (②)
      - 文档侧: 把 CLAUDE.md 的 marker 改成旧的四个名字 → 红 (②)
      - 散文侧: 只把散文改成"计划管理、步骤编排、执行队列"留 marker 不动 → 红 (③)
      - 删除侧: 把所有 marker 删光 → 红 (①)

    ⚠️ 设计稿原本还列了一道 D-3「禁词存在性门」(整仓文档不许出现 计划管理 /
    步骤编排 / 执行队列)。**实现时撤销**: 本片要往文档里加的封存 banner 本身就写着
    "计划管理 / 步骤编排 / 执行队列三个 Tab 已随 ARCH-1 S4a 删除" —— 那是**正确**
    的文字, 却会让那道门红。门红在正确的文字上比漏判更难查 (G5 的注释同此教训)。
    它要防的东西已被本门断言③ 精确覆盖: 旧 Tab 名若出现在"当前 Tab 列表"那一行,
    ③ 就会红; 出现在别处则本来就合法。
    """
    truth = _live_tab_labels()
    found = []
    for path in _live_doc_paths():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            m = _TAB_MARKER.search(line)
            if not m:
                continue
            declared = [s.strip() for s in m.group(1).split(",") if s.strip()]
            prose = line[: m.start()]
            found.append((rel, lineno, declared, prose))

    assert found, (
        f"没有任何文档带 <!-- gate:tabs=... --> marker —— 本门被架空了。\n"
        f"当前真值: {truth}。至少 CLAUDE.md 的「主要 Tab」那行要带上 marker。"
    )

    problems = []
    for rel, lineno, declared, prose in found:
        if declared != truth:
            problems.append(
                f"  {rel}:{lineno} marker 声明 {declared} ≠ 代码实况 {truth}"
            )
            continue
        missing = [lbl for lbl in truth if lbl not in prose]
        if missing:
            problems.append(
                f"  {rel}:{lineno} marker 对, 但同一行散文里缺 {missing}"
                f" —— 散文: {prose.strip()!r}"
            )
    assert not problems, (
        "文档声明的 Tab 与代码不一致 (ARCH-1 S5 D-1):\n" + "\n".join(problems)
    )


# ── G8: 文档提到的计划链路径必须真实存在 ────────────────────────────────
#
# 比设计稿 v1 的"不许出现那 36 条已删路由"强一档: 判据换成**集合成员** ——
# 文档里提到的每一条计划链路径, 都必须在真实路由表里。这样:
#   ① 36 条已删的 → 抓住;
#   ② **从来没实现过的**也抓住 (文档里躺着 /test-plans/batch、/{id}/versions、
#      /{id}/validate 这类从没建过的端点 —— v1 的清单式判据对它们完全无感);
#   ③ 共享前缀陷阱**结构性消失**: /test-plans/cases 在路由表里, 天然绿,
#      不需要像 G5 那样特判例外前缀 (S4a 踩过: 判据写成"不许出现 /test-plans"
#      会误杀保留下来的用例链)。
_DOC_PLAN_PATH = re.compile(
    r"(?:/api/v\d+)?(/(?:test-plans|test-sequences)(?:/[A-Za-z0-9_{}-]+)*)"
)


def _path_shape(path: str):
    """段序列, 路径参数名归一 —— 文档写 {id} 代码写 {test_case_id} 不算差异。"""
    return tuple("{}" if s.startswith("{") else s for s in path.split("/"))


def _is_absolute_url(line: str, start: int) -> bool:
    """匹配点是不是某个 http(s):// 绝对地址的一部分?

    实跑本门时抓到的自身 bug: README 里 `https://api.ctia.org/test-plans`
    (CTIA 行业标准的外链) 被当成了我们的路由。**门红在正确的文字上比漏判更难查**
    (G5 注释同此教训), 所以这里往回扫到最近的分隔符, 看那个 token 里有没有 `://`。
    """
    token_start = start
    while token_start > 0 and line[token_start - 1] not in " \t`([|<\"'":
        token_start -= 1
    return "://" in line[token_start:start]


def _live_path_shapes():
    return {_path_shape(p.replace("/api/v1", "", 1)) for _, p in _live_route_table()}


def test_g8_checker_normalises_paths():
    """判定器行为覆盖: 归一 + 前缀边界两件事都要对。"""
    assert _path_shape("/test-plans/{id}") == _path_shape("/test-plans/{plan_id}")
    assert _path_shape("/test-plans") != _path_shape("/test-plans/cases")
    hits = _DOC_PLAN_PATH.findall("见 `/api/v1/test-plans/cases/{id}/execute` 与 /test-plans")
    assert hits == ["/test-plans/cases/{id}/execute", "/test-plans"], hits
    # 外链豁免 —— 实跑抓到的自身 bug (README 的 CTIA 链接)
    ext = "- [CTIA Test Plan](https://api.ctia.org/test-plans) - 行业标准"
    assert _is_absolute_url(ext, ext.index("/test-plans", ext.index("://")))
    ours = "调 `/api/v1/test-plans` 建计划"
    assert not _is_absolute_url(ours, ours.index("/api/v1"))


def test_g8_docs_only_cite_live_plan_routes():
    """站点⑧: 现状文档里提到的计划链路径, 必须在真实路由表里 (设计稿 §3 D-2)。

    替代的规则: 无。S4b 删了 36 条路由, 文档里对它们的引用**一条都不会红** ——
    编译门管不到 markdown, G5 只扫 GUI 的 .ts/.tsx, G6 只查路由表自身。
    照文档去调一条已删路由的人 (或 agent) 拿到的是 404。

    历史留档不在网内 (§1.1): archive / site-debug / 设计稿 / 文件名带日期的现场记录
    —— 那些记的是当时的事实, 改它们是伪造。

    变异实跑 (⓪-④):
      - 往 CLAUDE.md 插一行 `POST /api/v1/test-plans/{id}/start` → 红
      - 往 CLAUDE.md 插一行 `POST /api/v1/test-plans/cases/{id}/execute` → **保持绿**
        (防误杀, 由 test_g8_checker_normalises_paths + 本门在真库上的绿共同覆盖)
    """
    live = _live_path_shapes()
    dead = []
    for path in _live_doc_paths():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for m in _DOC_PLAN_PATH.finditer(line):
                if _is_absolute_url(line, m.start()):
                    continue  # 外部站点的 URL, 不是我们的路由
                cited = m.group(1)
                if _path_shape(cited) not in live:
                    dead.append(f"  {rel}:{lineno} → {cited}")
    assert not dead, (
        "现状文档引用了**不存在**的计划链路由 (ARCH-1 S4 已拆除, 或从未实现):\n"
        + "\n".join(sorted(set(dead)))
    )
