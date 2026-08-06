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
import subprocess
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

    # ⚠️ 取数走 _live_route_table (内审 F2): 原先直接遍历 `app.routes` 取 path,
    # 在 FastAPI 0.141 懒加载下 `_IncludedRouter` 没有 `.path`, getattr 兜成 ""
    # → 本门只看到 5 条非空路径 (真实 320), **已空转**。而它的失效方向是
    # "失败开"(不会红), 所以那次三门假红的排查没暴露它 —— 这正是"按红了哪几个门
    # 做域枚举"的漏洞: 同一个取数源的读点必须一起换, 不管它红不红。
    bad = _doubled_segments(p for _, p in _live_route_table())
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
        # get_throughput_metrics 原有 8 处裸 pass —— 每个 KPI 字段一处
        # "解析失败就静默用默认值"。2026-08-03 那批解析全部按手册重写
        # (命令、下标、单位、NaN 哨兵都是错的), 8 处静默吞异常一并消除:
        # 现在读不到就记 warning + 在 measurement.log 里标 kpi_valid=false,
        # 不再让"没读到"冒充"测出来是 0"。基线 8 → 0 锁住进度。
        "_silent_reconnect_visa": 1,
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


def _expand_app_routes(routes, prefix=""):
    """递归展开路由树 → [(method, full_path)]。

    FastAPI 0.141 起 `include_router` **不再**把子路由展平进 `app.routes`,
    而是留一个 `_IncludedRouter` 懒加载对象 (子路由在 `.original_router.routes`,
    前缀在 `.include_context.prefix`), 可嵌套多层。WebSocket 路由无 `methods`,
    单列成 "WS" 动词 (openapi 里没有它们, 但文档会如实引用 —— G11 散文半要用)。
    """
    out = []
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            sub = getattr(r, "original_router", None)
            ctx = getattr(r, "include_context", None)
            sub_prefix = getattr(ctx, "prefix", "") or "" if ctx is not None else ""
            if sub is not None:
                out += _expand_app_routes(sub.routes, prefix + sub_prefix)
            continue
        methods = getattr(r, "methods", None)
        if methods:
            out += [(m, prefix + r.path) for m in methods]
        elif type(r).__name__ == "APIWebSocketRoute":
            out.append(("WS", prefix + r.path))
    return out


def _live_route_table():
    """(method, path) 集合 —— 从真实 app 读, 不 grep 源码。

    ⚠️ 2026-08-02 事故教训 (本函数为什么带自检): FastAPI 从 0.141 起改懒加载
    路由 (见 `_expand_app_routes`), 旧实现"遍历 app.routes 找 methods"当场只
    拿到 **9 条** (真实 320 条) —— 而三个消费门 (G6/G8/G11) 收到空表后喊的是
    **"用例链路由被误删" / "文档引用了 44 条死路由"**, 全是假红且**归因完全
    错误**。取数源坏掉必须**自己喊出来**, 不能静默交一张残表让上层门瞎判。
    所以下面这道自检不是冗余: 它把"我瞎了"和"路由真丢了"分开。
    判据 = `app.openapi()` 的 **(动词, shape) 集合 ⊆ 展开结果**的同款集合。
    openapi 是公开 API, 独立于路由树内部结构, 拿它当交叉源。
    ⚠️ **必须是集合包含, 不能是数量比较** (内审 F1 实证): 计数判据下
    ① 丢掉整个 `test-plans` router 仍有 252 ≥ 251 → 自检放行, G6 照样喊
    "用例链路由被误删"(与本次事故一字不差的错误归因); 37 个顶层 router 里
    **25 个**整丢都不到余量。② `include_context.prefix` 拿不到时路径全退化成
    `/health`, 数量一条不少 —— 而**路径内容错正是展开器唯一的风险面**。
    ⚠️ 比 shape 不比原串: live 的 `{report_path:path}` (Starlette converter 语法)
    与 openapi 的 `{report_path}` 字面不等, 归一后才可比。
    """
    from app.main import app

    table = set(_expand_app_routes(app.routes))

    def _shape(path):
        return tuple("{}" if seg.startswith("{") else seg
                     for seg in path.strip("/").split("/"))

    live_pairs = {(m, _shape(p)) for m, p in table}
    spec_pairs = {
        (m.upper(), _shape(p))
        for p, ops in app.openapi().get("paths", {}).items()
        for m in ops
        if m.lower() in ("get", "post", "put", "patch", "delete", "head", "options")
    }
    missing = spec_pairs - live_pairs
    assert not missing, (
        f"路由取数源失效: openapi 声明的 {len(missing)} 个 (动词,路径) 展开不出来, 例如 "
        + ", ".join(f"{m} /{'/'.join(sh)}" for m, sh in sorted(missing)[:5])
        + "。这**不是**路由被删 —— 是 _expand_app_routes 跟不上 FastAPI 的路由树结构了 "
        "(0.141 那次改懒加载就是先例)。先修展开器, 别改被它喂假数据的门。"
    )
    return table


def test_expand_app_routes_behavior():
    """展开器自测 (内审 F3) —— 同文件每个判定器都配的那种"防自己空转"的门。

    为什么非要独立自测: 展开器的 6 个分支此前全靠 G6/G8/G11 的整体绿"借"覆盖,
    而 F1 已证明整体绿对**部分失效**是瞎的; WS 分支更是只被
    `docs/guides/monitoring-components.md` 的一行散文覆盖 —— 删掉那行文档,
    分支就零覆盖且 G11 照绿。借来的覆盖随时会被别人的编辑拿走。

    合成 app 覆盖两种前缀来源混用 + 多层嵌套 + websocket。
    """
    from fastapi import APIRouter, FastAPI

    inner = APIRouter(prefix="/inner")          # ① router 自带 prefix

    @inner.get("/leaf")
    def _leaf():  # pragma: no cover - 仅供路由表
        return {}

    @inner.websocket("/stream")
    async def _stream(ws):  # pragma: no cover - 仅供路由表
        ...

    mid = APIRouter()
    mid.include_router(inner, prefix="/i")      # ② include_router 的 prefix
    outer = APIRouter(prefix="/m")
    outer.include_router(mid, prefix="/mid")    # ③ 三层嵌套

    tmp = FastAPI()
    tmp.include_router(outer, prefix="/api/v1")

    table = set(_expand_app_routes(tmp.routes))
    assert ("GET", "/api/v1/m/mid/i/inner/leaf") in table, table
    # WS 单列伪动词 —— 删掉展开器的 websocket 分支这条就红 (不再依赖某行文档)
    assert ("WS", "/api/v1/m/mid/i/inner/stream") in table, table
    # 与 openapi 交叉: 声明的 (动词,路径) 一条不能少 (前缀漏拼/双拼都会破这条)
    spec = {(m.upper(), p) for p, ops in tmp.openapi().get("paths", {}).items()
            for m in ops}
    assert spec <= {(m, p) for m, p in table}, spec - {(m, p) for m, p in table}


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
# 以"完成记录"为主体的文件 —— 见 _live_doc_paths() 的 roadmap 说明。
_DOC_ARCHIVE_FILES = (
    "docs/roadmap-archive.md",
    "docs/roadmap-first-call.md",
    "docs/project-retrospective.md",
)
# 文件名里带日期的 = 某天的记录 (onsite-20260721-todo.md / caict-2026-05-13.md …)
_DOC_DATED_NAME = re.compile(r"\d{4}-?\d{2}-?\d{2}")
# 厂商手册, 不是我们的文档
_DOC_FOREIGN_DIRS = ("Instrument_API_Doc/",)


def _live_doc_paths():
    """仓库里**描述当下实况**的 markdown —— 历史留档按 §1.1 路径规则排除。

    判定全靠路径, 不读内容: 新增文档自动进网, 不需要维护一张 A 类清单
    (手工清单正是 S4 反复漏枚举的那个失败形态)。

    ⚠️ **只认 git 跟踪的文件** (内审 F13): 原先用 ``rglob("*.md")``, 结果把
    ``api-service/.venv`` / ``channel-engine-service/.venv`` 里 site-packages 的
    40+ 个 markdown (playwright 的 skill 文档、各 LICENSE.md) 和 ``.pytest_cache``
    一起扫进了网 —— 门的结论会取决于**本机装了哪些 pip 包**、工作树里有什么草稿,
    换台机器装个新包就可能红在一个不在版本控制里的文件上。那不是门, 是骰子。

    ⚠️ **``docs/roadmap-first-call.md`` 在网外** (内审 F9): 它虽然是活路线图,
    但正文主体是 "✅ Done" 完成记录与 ``[discovered YYYY-MM-DD]`` 当日 backlog ——
    内审把 G8 跑在 main 上, 该文件 5 条命中**真阳性率 0/5**, 全落在历史记录里。
    这跟已经在网外的 ``docs/roadmap-archive.md`` 是同一种文本, 同事同待遇。
    (撤销 D-3 禁词门的理由 —— "门红在正确的文字上比漏判更难查" —— 对这里一字不改
    地成立: 漏判一条 stale path = 读者一次 404; 误红在正确记录上 = 有人去改记录,
    而那已经发生过 4 次, 其中一次还在代码块里造了个不存在的符号。)
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
    )
    out = []
    for rel in proc.stdout.split("\0"):
        if not rel:
            continue
        if any(rel.startswith(d) for d in _DOC_FOREIGN_DIRS):
            continue
        if any(rel.startswith(d) for d in _DOC_ARCHIVE_DIRS):
            continue
        if rel in _DOC_ARCHIVE_FILES:
            continue
        path = _REPO_ROOT / rel
        if _DOC_DATED_NAME.search(path.name) or not path.is_file():
            continue
        out.append(path)
    return out


def test_g7_g8_doc_net_is_deterministic():
    """网必须只含 git 跟踪的仓库文档 —— 不含 .venv / 缓存 / 未跟踪草稿。

    内审 F13 的常驻化: 光有下面两道门, 网悄悄扩到 site-packages 也一样绿
    (只是结论开始取决于本机 pip 状态)。
    """
    rels = [p.relative_to(_REPO_ROOT).as_posix() for p in _live_doc_paths()]
    assert rels, "文档网为空 —— 两道门被架空了"
    bad = [r for r in rels if ".venv" in r or "node_modules" in r or "cache" in r]
    assert not bad, f"网里混进了非仓库文档: {bad[:5]}"


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
# 必须带 marker 的文件 —— 少一个就红 (内审 F2)。CLAUDE.md 是 agent 必读的那份,
# GUI README 是模块现状说明; 两处都漂回去过的风险最高。
_TAB_MARKER_REQUIRED_FILES = (
    "CLAUDE.md",
    "gui/src/features/TestManagement/README.md",
)
_TAB_SOURCE = "gui/src/features/TestManagement/TestManagement.tsx"
_TAB_OPEN = re.compile(r"<Tabs\.Tab\b")


def _parse_tab_entries(src: str):
    """扫 `<Tabs.Tab>` 开标签, 逐个抽 (value, label)。label=None 表示**抽不出来**。

    ⚠️ **不用单条正则** (内审 F1)。原先写的是
    ``<Tabs\.Tab\b.*?>\s*(?P<label>[^<>{}]+?)\s*</Tabs\.Tab>`` 配 ``re.S``,
    内审实跑用三种**常规** JSX 写法把它绕过去了, 每种都让门保持绿:

      | 变异 | 为什么绿 |
      |---|---|
      | 标签写 `{t('reports')}` | 标签字符类排除 `{}`, 该 Tab 抽不出来 |
      | 标签包 `<Text>报告中心</Text>` | 排除 `<>`, 同上 |
      | 自闭合 `<Tabs.Tab value="x" />` | 没有 `</Tabs.Tab>` 可配对 |

    根因是 ``.*?`` + ``re.S`` **允许跨越 ``</Tabs.Tab>``**: 遇到抽不出的标签就回溯到
    **下一个** Tab 的开标签, 那个 Tab 于是凭空消失 —— 真值集从 3 变不成 4,
    ``declared == truth`` 照样成立。这就是"门看起来是不变量档, 其实是某一种写法的
    存在性门"。

    现在改成: 逐个开标签手扫, 抽不出来就记 ``None`` 让上层**喊出来**, 且开标签总数
    与抽出条数必须相等 —— 静默漏抽变成显式失败。
    """
    entries = []
    for m in _TAB_OPEN.finditer(src):
        # 找开标签的收尾 `>` —— 必须跳过 `{...}` 里的 `>`
        # (`leftSection={<IconChecklist size={16} />}` 里就有一个)
        depth, i, end = 0, m.end(), None
        while i < len(src):
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0:
                end = i
                break
            i += 1
        if end is None:
            entries.append((None, None))
            continue
        head = src[m.start():end]
        vm = re.search(r'value="([^"]*)"', head)
        value = vm.group(1) if vm else None
        if src[end - 1] == "/":          # 自闭合 → 没有标签文本
            entries.append((value, None))
            continue
        nxt = src.find("<Tabs.Tab", end)
        close = src.find("</Tabs.Tab>", end)
        if close == -1 or (nxt != -1 and nxt < close):
            entries.append((value, None))   # 闭合标签缺失或错配
            continue
        body = src[end + 1:close].strip()
        # 纯文本才算抽到; 含 `<`(嵌套组件) 或 `{`(i18n / 表达式) 一律记 None
        label = body if body and "<" not in body and "{" not in body else None
        entries.append((value, label))
    return entries


def _live_tab_labels():
    """真值: Tab 的中文标签, **按渲染顺序**。抽不干净就抛 —— 不静默降级。"""
    src = _strip_ts_comments((_REPO_ROOT / _TAB_SOURCE).read_text(encoding="utf-8"))
    entries = _parse_tab_entries(src)
    unresolved = [v for v, lbl in entries if lbl is None]
    assert not unresolved, (
        f"{_TAB_SOURCE} 里有 {len(unresolved)} 个 Tab 抽不出纯文本标签"
        f" (value={unresolved}) —— 可能改成了 i18n / 嵌套组件 / 自闭合。\n"
        "G7 门无法在这种形态下判定, 请要么让标签保持纯文本, 要么改本判定器"
        "(不要放任它静默漏抽, 那会让门恒绿 —— 内审 F1)。"
    )
    return [lbl for _, lbl in entries]


def test_g7_checker_parses_every_tab():
    """判定器自身的行为覆盖: **开标签数 == 抽出标签数**, 且顺序稳定。

    内审 F1 的常驻化。原来这条只断言 ``len(labels) >= 2``, 而真实失效形态是
    "**新增一个** Tab 用了别的写法" —— 那时还剩 3 个标签, `>= 2` 照样过。
    现在把"抽不出来"钉成硬失败。
    """
    src = _strip_ts_comments((_REPO_ROOT / _TAB_SOURCE).read_text(encoding="utf-8"))
    opens = len(_TAB_OPEN.findall(src))
    labels = _live_tab_labels()      # 抽不干净会在这里就炸
    assert opens == len(labels), f"开标签 {opens} 个, 抽出标签 {len(labels)} 个"
    assert opens >= 2, f"只找到 {opens} 个 <Tabs.Tab> —— 判定器跟 JSX 漂了"


def test_g7_checker_catches_evasive_jsx():
    """判定器对三种绕过写法必须**喊出来**, 不许静默漏抽 (内审 F1 实跑的那三种)。"""
    base = (
        '<Tabs.Tab value="a" leftSection={<Icon size={16} />}>\n  甲\n</Tabs.Tab>\n'
        '<Tabs.Tab value="b">\n  乙\n</Tabs.Tab>\n'
    )
    assert [lbl for _, lbl in _parse_tab_entries(base)] == ["甲", "乙"]
    for name, extra in [
        ("i18n",      '<Tabs.Tab value="c">{t(\'rep\')}</Tabs.Tab>\n'),
        ("嵌套组件",  '<Tabs.Tab value="c"><Text>报告</Text></Tabs.Tab>\n'),
        ("自闭合",    '<Tabs.Tab value="c" />\n'),
    ]:
        entries = _parse_tab_entries(base + extra)
        assert len(entries) == 3, (name, entries)
        assert entries[2][1] is None, f"{name} 应被记为抽不出来, 实得 {entries[2]!r}"


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

    # ⚠️ 不能只断言 "found 非空" (内审 F2): 那样单独删掉 CLAUDE.md 那一行门照样绿,
    # 而 CLAUDE.md 正是原始 bug 的发生地、也是 agent 唯一必读的那份文档 —— 断言②③
    # 会对它彻底失效, 那行可以自由漂回去。所以锚定到具体文件。
    carriers = {rel for rel, _, _, _ in found}
    missing_carriers = [f for f in _TAB_MARKER_REQUIRED_FILES if f not in carriers]
    assert not missing_carriers, (
        f"这些文件必须带 <!-- gate:tabs=... --> marker, 现在没带: {missing_carriers}\n"
        f"当前真值: {truth}。没有 marker 的文件, 本门的另两条断言对它完全失效。"
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


# 自家地址 —— 这些 host 下的路径是我们的路由, 不享受外链豁免 (内审 F3)。
_OWN_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "::", "host.docker.internal"}


def _is_absolute_url(line: str, start: int) -> bool:
    """匹配点是不是某个 http(s):// 绝对地址的一部分?

    实跑本门时抓到的自身 bug: README 里 `https://api.ctia.org/test-plans`
    (CTIA 行业标准的外链) 被当成了我们的路由。**门红在正确的文字上比漏判更难查**
    (G5 注释同此教训), 所以这里往回扫到最近的分隔符, 看那个 token 里有没有 `://`。
    """
    token_start = start
    while token_start > 0 and line[token_start - 1] not in " \t`([|<\"'":
        token_start -= 1
    prefix = line[token_start:start]
    if "://" not in prefix:
        return False
    # ⚠️ 只豁免**外部站点** (内审 F3)。原先"token 里有 `://` 就豁免"太宽:
    # `curl -X POST http://localhost:8000/api/v1/test-plans/{id}/start` 会被整条放过,
    # 而仓库里 quickstart.md / implementation-roadmap.md / data-architecture.md 全是
    # 这个写法 —— 下一份文档照着写就漏判。自家地址一律照查。
    authority = prefix.split("://", 1)[1].split("/")[0].split("@")[-1]
    # IPv6 字面量是 `[::1]:8000` —— 直接按 `:` 切会得到 `[` (Codex #248 C3)。
    if authority.startswith("["):
        host = authority[1:].split("]")[0]
    else:
        host = authority.split(":")[0]
    return host.lower() not in _OWN_HOSTS


# 文档里路径前面那个动词 —— `POST /api/v1/test-plans/cases/{id}/execute` 里的 POST。
# 允许中间夹反引号 / 空白: "**POST** `/api/v1/...`" 也认。
_DOC_VERB = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b[\s`*]*$")


def _live_path_shapes():
    return {_path_shape(p.replace("/api/v1", "", 1)) for _, p in _live_route_table()}


def _live_method_shapes():
    """(method, shape) 集合 —— 与 G6 同构 (Codex #248 C2)。

    只比路径会放过"对路径错动词": 文档把执行正门写成
    ``GET /api/v1/test-plans/cases/{id}/execute`` 时路径形状仍命中, 门绿,
    而照它调的人拿到 **405** —— 跟 404 一样是死引用, 只是死法不同。
    """
    return {(m, _path_shape(p.replace("/api/v1", "", 1))) for m, p in _live_route_table()}


def _doc_verb_before(line: str, start: int):
    """路径前面紧挨着的 HTTP 动词; 没有就返回 None (那时只比路径)。"""
    m = _DOC_VERB.search(line[:start])
    return m.group(1) if m else None


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
    # 自家 localhost 不豁免 (内审 F3 实跑抓到的绕过)
    lh = "curl -X POST http://localhost:8000/api/v1/test-plans/{id}/start"
    assert not _is_absolute_url(lh, lh.index("/api/v1"))
    # IPv6 方括号 loopback 同样不豁免 (Codex #248 C3)
    v6 = "curl http://[::1]:8000/api/v1/test-plans/{id}/start"
    assert not _is_absolute_url(v6, v6.index("/api/v1"))
    # 动词抽取 (Codex #248 C2)
    for line, want in [
        ("执行走 `POST /api/v1/test-plans/cases/{id}/execute`", "POST"),
        ("**DELETE** `/test-plans/queue/{id}`", "DELETE"),
        ("见 /test-plans/cases 列表", None),
    ]:
        i = line.index("/test-plans") if "/api/v1" not in line else line.index("/api/v1")
        assert _doc_verb_before(line, i) == want, (line, _doc_verb_before(line, i))


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
    live_methods = _live_method_shapes()
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
                shape = _path_shape(cited)
                if shape not in live:
                    dead.append(f"  {rel}:{lineno} → {cited}")
                    continue
                # 路径在, 再看动词 —— 写错动词是 405, 跟 404 一样是死引用
                verb = _doc_verb_before(line, m.start())
                if verb and (verb, shape) not in live_methods:
                    allowed = sorted(v for v, sh in live_methods if sh == shape)
                    dead.append(
                        f"  {rel}:{lineno} → {verb} {cited} (路径在, 但该动词不存在;"
                        f" 实际支持 {allowed} —— 照文档调会拿 405)"
                    )
    assert not dead, (
        "现状文档引用了**不存在**的计划链路由 (ARCH-1 S4 已拆除, 或从未实现):\n"
        + "\n".join(sorted(set(dead)))
    )

# ─────────────────────────────────────────────────────────────────────
# G9 schema 描述 ⊇ 枚举 (P3-14 拍板的门 G-A)
# ─────────────────────────────────────────────────────────────────────
# TestCaseCreate.test_type 的 description 是外部调用方唯一会读的契约文本 (进
# OpenAPI), 曾漏 MIMO_OTA。字段类型是 str 不是 Enum (历史决定), 描述与枚举的
# 对齐没有任何结构强制 —— 站点表锁死: 枚举加成员、描述漏更新 → 红。
# 判定是**集合包含**不是子串 (不变量档): desc 按 "|" 切 token 集, 枚举成员
# value 必须逐个是 token —— 子串匹配会被 "MIMO" ⊂ "MIMO_OTA" 这种前缀骗过。
# 变异实跑: 描述里删 " MIMO_OTA |" → 红。

_G9_ENUM_DESCRIPTION_SITES = [
    # (schema 模块, schema 类, 字段, 枚举模块, 枚举类)
    ("app.schemas.test_plan", "TestCaseCreate", "test_type",
     "app.models.test_plan", "TestCaseType"),
]


def test_g9_schema_description_superset_of_enum():
    import importlib

    problems = []
    for schema_mod, schema_cls, field_name, enum_mod, enum_cls in _G9_ENUM_DESCRIPTION_SITES:
        schema = getattr(importlib.import_module(schema_mod), schema_cls)
        enum = getattr(importlib.import_module(enum_mod), enum_cls)
        desc = schema.model_fields[field_name].description or ""
        tokens = {t.strip() for t in desc.split("|")}
        missing = [f"{enum_cls}.{m.name} ({m.value!r})" for m in enum
                   if m.value not in tokens]
        if missing:
            problems.append(
                f"{schema_cls}.{field_name} 的 description 漏列: {', '.join(missing)}\n"
                f"  当前描述: {desc!r}"
            )
    assert not problems, (
        "schema 描述与权威枚举脱节 (外部调用方只读描述, 漏列 = 契约说谎):\n"
        + "\n".join(problems)
    )

# ─────────────────────────────────────────────────────────────────────
# G10 状态列注释 ⊇ TestExecution 状态字面量写点 (P3-16 拍板的门 G-B)
# ─────────────────────────────────────────────────────────────────────
# TestExecution.status 的列注释是状态取值的**唯一真值源** (CLAUDE.md 指向它,
# ARCH-1 曾漏 `pending`、#248 C4 曾漏 `cancelled` — 漏枚举是这条线反复踩的坑)。
# 本门反向锁: 全仓写进 TestExecution.status 的**字面量**必须都在注释里 ——
# 新代码写一个注释没列的状态 → 红, 逼着同步真值源。
# 写点识别 (2026-08-01 全仓 AST 普查定的双判据):
#   ① 构造调用 TestExecution(status="...")
#   ② 属性赋值 <var>.status = "...", var ∈ {execution, ex, test_execution}
#      (test_case_runner / commissioning / executors 的既有命名惯例;
#      conn/session/sequence/step 等别的 status 域不进判定 — 宁漏报不误伤,
#      动态值写点本来就不归字面量门管)
# 真值源提取 = live import 列对象 comment (不 grep 源文本)。
# 变异实跑: test_case_runner 临时加 execution.status = "exploded" → 红。

# "row" 为 VRT 服务惯例 (vrt_execution_service, Codex #264 R1 — 该域经
# TestExecutionORM 别名构造 + row.status 赋值, 原判据两头都漏)。
# 全仓 `row.status = "字面量"` 现存零命中 → 加入零误伤。
_G10_EXEC_VAR_NAMES = {"execution", "ex", "test_execution", "row"}


def _g10_collect_status_literals(tree: "ast.AST"):
    lits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Attribute) and t.attr == "status"
                        and isinstance(t.value, ast.Name)
                        and t.value.id in _G10_EXEC_VAR_NAMES
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)):
                    lits.append((t.value.id, node.lineno, node.value.value))
        if isinstance(node, ast.Call):
            fn = node.func
            fn_name = fn.attr if isinstance(fn, ast.Attribute) else (
                fn.id if isinstance(fn, ast.Name) else "")
            # startswith: 覆盖 import 别名 (TestExecutionORM, Codex #264 R1)
            if fn_name.startswith("TestExecution"):
                for kw in node.keywords:
                    if (kw.arg == "status" and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)):
                        lits.append(("TestExecution()", node.lineno, kw.value.value))
    return lits


def test_g10_checker_detects_bad_literal():
    """G10 判定器行为自测 — 两个方向都要对 (防 checker 空转)。"""
    src = (
        "def f(execution, conn):\n"
        "    execution.status = 'exploded'\n"
        "    conn.status = 'connected'\n"
        "    row = TestExecution(status='pending')\n"
    )
    lits = _g10_collect_status_literals(ast.parse(src))
    vals = {v for _, _, v in lits}
    assert "exploded" in vals          # execution 域写点抓到
    assert "connected" not in vals     # 别的 status 域不误伤
    assert "pending" in vals           # 构造调用抓到
    src2 = (
        "def g(row):\n"
        "    row.status = 'kaboom'\n"
        "    x = TestExecutionORM(status='boom')\n"
    )
    vals2 = {v for _, _, v in _g10_collect_status_literals(ast.parse(src2))}
    assert {"kaboom", "boom"} <= vals2  # VRT 惯例: row 变量 + ORM 别名 (Codex #264 R1)


def test_g10_status_comment_superset_of_write_sites():
    from app.models.test_plan import TestExecution

    comment = TestExecution.__table__.columns["status"].comment or ""
    truth = {t.strip().split(" ")[0] for t in comment.split("|") if t.strip()}
    assert truth, "TestExecution.status 列注释为空 — 真值源没了"

    # 列自身的 default 也是一个写点 (Codex #264 R2): default 改成注释没列的值,
    # 所有缺省构造都写野值而 AST 判据看不见 — live 断言直接锁列对象。
    col_default = TestExecution.__table__.columns["status"].default
    if col_default is not None and isinstance(getattr(col_default, "arg", None), str):
        assert col_default.arg in truth, (
            f"TestExecution.status 列 default={col_default.arg!r} 不在列注释真值源里")

    offenders = []
    for py in sorted((_API_SERVICE_ROOT / "app").rglob("*.py")):
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for base, lineno, lit in _g10_collect_status_literals(tree):
            if lit not in truth:
                offenders.append(
                    f"{py.relative_to(_API_SERVICE_ROOT)}:{lineno} "
                    f"{base}.status = {lit!r}")
    assert not offenders, (
        "TestExecution.status 写点用了列注释 (唯一真值源) 没列的状态字面量 —\n"
        "要么是拼错, 要么先把注释真值源更新了再写代码:\n" + "\n".join(offenders)
        + f"\n当前真值源: {sorted(truth)}"
    )


def test_g10_vrt_enum_subset_of_comment():
    """VRT 域写点全走 ExecutionStatus 枚举 (动态值, 字面量门看不见) — 源头锁:
    枚举成员值 ⊆ 列注释。枚举加成员、注释不更新 → 红 (Codex #264 R1 顺藤补强:
    字面量判据扩到 VRT 别名/row 只堵将来的字面量写法, 现存动态面在这条锁)。"""
    from app.models.test_plan import TestExecution
    from app.schemas.road_test.execution import ExecutionStatus

    comment = TestExecution.__table__.columns["status"].comment or ""
    truth = {t.strip().split(" ")[0] for t in comment.split("|") if t.strip()}
    extra = {m.value for m in ExecutionStatus} - truth
    assert not extra, (
        f"ExecutionStatus 枚举成员 {sorted(extra)} 不在 TestExecution.status "
        f"列注释 (唯一真值源) 里 — 先更新注释再加枚举。当前真值源: {sorted(truth)}"
    )

# ─────────────────────────────────────────────────────────────────────
# G11 文档 (动词,路径,参数,响应键) ⊇ 真实实现 (P3-17 拍板的门 G-C, G8 加强版)
# ─────────────────────────────────────────────────────────────────────
# 两半:
#   ①散文半 — 现状文档引用的**任何** /api/v1 路径 (G8 只锁计划链域) 必须是
#     活路由, 动词也要对。设计愿景类文档 (docs/features / docs/hardware /
#     docs/architecture / AGENTS.md / implementation-roadmap) 记录的是设计意图
#     不是现状声明, 豁免 (同 G8 对历史留档的理由); 跨服务路由 (/ota =
#     channel-engine, /ws = websocket 不进 REST 路由表) 豁免并申报。
#     实值段通配: 文档常写 `/instruments/baseStation/...` 实值示例, 与 live 的
#     `{category_key}` 参数位按段通配匹配, 否则示例全误杀。
#   ②契约半 — checked-in api/openapi.yaml 声明的 (路径,动词,参数名,2xx 响应键)
#     ⊆ live app.openapi()。参数/响应键维度的机械落点在这里 (散文书写形态
#     不可机械解析, P3-17 实施时定的收窄); 路径参数名形态差异 ({categoryKey}
#     vs {category_key}) 按 shape 归一。
# 变异实跑: CLAUDE.md 插死路径 → ①红; yaml 加不存在参数 → ②红。

_G11_DESIGN_DOCS = ("docs/features/", "docs/hardware/", "docs/architecture/",
                    "AGENTS.md", "IMPLEMENTATION-PLAN",
                    "docs/guides/implementation-roadmap.md")
# /ota = channel-engine 服务路由, 本地路由表无从验证 — 唯一剩余豁免。
# (websocket 路由不豁免: 其 shape 并进 live_shapes, 见散文半 — 内审 F3)
_G11_CROSS_SERVICE_PREFIXES = ("/ota",)
_G11_API_PATH = re.compile(r"/api/v1(/[A-Za-z0-9_{}\-./]+)")


def _g11_shape_segs(path: str):
    return tuple("{}" if seg.startswith("{") else seg
                 for seg in path.strip("/").split("/"))


def _g11_matches(cited: str, live_shapes) -> bool:
    # 通配只有一个方向: 文档实值段 ↔ live 参数位 (s == "{}")。反向
    # (文档参数段配 live 实值段) 是内审 F1 删掉的宽松洞: 它让
    # `/instruments/{category_key}/status` 这种参数化书写的死路径匹配上
    # live 的 `/instruments/hal/status` 而穿透 — 全语料实测零引用依赖它。
    segs = tuple(cited.strip("/").split("/"))
    for shape in live_shapes:
        if len(shape) == len(segs) and all(
                s == "{}" or s == c
                for s, c in zip(shape, segs)):
            return True
    return False


def test_g11_matcher_behavior():
    """通配匹配器行为自测 — 实值段命中参数位 / 段数不齐不命中。"""
    shapes = [("instruments", "{}", "topology-profiles"), ("dashboard",)]
    assert _g11_matches("/instruments/baseStation/topology-profiles", shapes)
    assert _g11_matches("/instruments/{cat}/topology-profiles", shapes)
    assert not _g11_matches("/instruments/topology-profiles", shapes)
    assert not _g11_matches("/dashboard/extra", shapes)
    # 内审 F1 锁死: 文档参数段**不许**匹配 live 实值段 — 参数化书写的死路径
    # 曾经此洞穿透 (变异实证: /instruments/{x}/status 配上 hal 实值段)。
    assert not _g11_matches("/instruments/{x}/status",
                            [("instruments", "hal", "status")])


def test_g11_docs_cite_live_api_routes_full_domain():
    """散文半: 现状文档全 API 面 (动词,路径) ⊆ 路由表 — G8 域扩展。
    2026-08-02 落地时基线: 116 条死引用全部来自设计愿景文档 (豁免类),
    豁免后真死引用 2 条已修 (GEMINI 示例值 / implementation-roadmap 入豁免)。"""
    live_routes = [(m, p.replace("/api/v1", "", 1)) for m, p in _live_route_table()]
    # websocket 路由已由 _expand_app_routes 以 "WS" 动词并进表 (内审 F3 的
    # 两向洞在取数层一次消掉) —— 这里不再单独兜一遍: 原先那段从 app.routes
    # 找 APIWebSocketRoute, 在 FastAPI 0.141 懒加载下**同样失效**, 留着就是
    # 第二个会瞎的取数点 (2026-08-02)。
    live_shapes = [_g11_shape_segs(p) for _, p in live_routes]
    live_verb_shapes = {(m, _g11_shape_segs(p)) for m, p in live_routes}
    dead = []
    for path in _live_doc_paths():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        if any(d in rel for d in _G11_DESIGN_DOCS):
            continue
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for m in _G11_API_PATH.finditer(line):
                if _is_absolute_url(line, m.start()):
                    continue
                cited = m.group(1).rstrip(".,;:/")
                if any(cited == c or cited.startswith(c + "/")
                       for c in _G11_CROSS_SERVICE_PREFIXES):
                    continue
                if not _g11_matches(cited, live_shapes):
                    dead.append(f"  {rel}:{lineno} → /api/v1{cited}")
                    continue
                verb = _doc_verb_before(line, m.start())
                if verb:
                    segs = tuple(cited.strip("/").split("/"))
                    ok = any(v == verb and len(sh) == len(segs) and all(
                        s == "{}" or s == c
                        for s, c in zip(sh, segs)) for v, sh in live_verb_shapes)
                    if not ok:
                        dead.append(f"  {rel}:{lineno} → {verb} /api/v1{cited} (动词不存在, 405)")
    assert not dead, (
        "现状文档引用了不存在的 API 路由/动词 (照文档调会 404/405):\n"
        + "\n".join(sorted(set(dead))))


def test_g11_openapi_yaml_subset_of_live_schema():
    """契约半: checked-in openapi.yaml (路径,动词,参数名,2xx 响应键) ⊆ live。
    yaml 是 checked-in 契约与类型生成源 (api.generated.ts) — 如实申报 (内审 F2):
    当前 GUI 零 import generated 类型 (api.ts:195 自记录消费约定), 本门锁的是
    契约文本自身 + 未来消费方; 同一谎言的**生效端副本** (gui/src/types/api.ts
    手写 camel 三键 → App.tsx 系统状态面板恒空态) 已记 roadmap Discovered。
    required 维度不比对 (实扫 6 处差异全为 "live 字段有默认值故不 required 但
    序列化恒出现" 的良性形态, 硬比误报)。

    已知收窄面 (Codex #265 R2 枚举, 转 backlog 独立精化 — 声明与覆盖对齐):
    ① 参数比对只按名不分 in= location (query 重名 path 参数会穿透);
    ② 散文半动词抽取不识别 curl 形态 (`curl -X POST http://host/api/v1/...`
       动词与路径隔着 host, 抽不出 → 只比路径);
    ③ 响应比对只在双侧都是 object properties 时进行 (yaml 改成 type: array
       等不兼容形态时 y_props 空 → 跳过)。"""
    import yaml as _yaml

    from app.main import app

    spec = _yaml.safe_load((_REPO_ROOT / "api" / "openapi.yaml").read_text())
    live = app.openapi()
    live_paths = live.get("paths", {})
    live_by_shape = {}
    for p, ops in live_paths.items():
        live_by_shape.setdefault(_g11_shape_segs(p), {}).update(ops)

    def _resolve(doc, node):
        # hop 上限: 循环 $ref (A→B→A) 该红不该挂死 (内审 F4)。
        # 已知漏比 (申报): allOf/anyOf 组合形态解出的 properties 为空 → 跳过
        # 比对 — 漏报方向, 当前 yaml 无此形态 (grep 证实), 出现时再精化。
        for _ in range(20):
            if not (isinstance(node, dict) and "$ref" in node):
                return node
            ref = node["$ref"]
            assert ref.startswith("#/"), ref
            cur = doc
            for part in ref[2:].split("/"):
                cur = cur[part]
            node = cur
        raise AssertionError(f"$ref 链过深/成环: {node}")

    problems = []
    for p, methods in (spec.get("paths") or {}).items():
        shape = _g11_shape_segs(p)
        lp = live_by_shape.get(shape)
        if lp is None:
            problems.append(f"yaml 声明的路径不在实现: {p}")
            continue
        for m, op in methods.items():
            if m in ("parameters", "description", "summary"):
                continue
            lop = lp.get(m)
            if lop is None:
                problems.append(f"yaml 声明的动词不在实现: {m.upper()} {p}")
                continue
            want = {pr["name"] for pr in (op.get("parameters") or [])
                    if isinstance(pr, dict) and "name" in pr and pr.get("in") != "path"}
            have = {pr["name"] for pr in (lop.get("parameters") or [])}
            extra = want - have
            if extra:
                problems.append(f"yaml 参数不在实现: {m.upper()} {p} → {sorted(extra)}")
            # 2xx 响应键: yaml 声明的顶层 properties ⊆ live (双侧都解 $ref;
            # live 未声明 response_model 时无 schema — 跳过, 契约弱侧不硬比)
            for code, resp in (op.get("responses") or {}).items():
                if not str(code).startswith("2"):
                    continue
                y_schema = _resolve(spec, ((resp.get("content") or {})
                                           .get("application/json") or {}).get("schema") or {})
                l_resp = (lop.get("responses") or {}).get(str(code))
                if l_resp is None:
                    # Codex #265 R1: 声明的响应码 live 根本没有 — 这是 mismatch,
                    # 静默跳过会让 "改 200 成 201 + 编键" 照绿。
                    problems.append(
                        f"yaml 声明的响应码不在实现: {m.upper()} {p} {code}")
                    continue
                l_schema = _resolve(live, ((l_resp.get("content") or {})
                                           .get("application/json") or {}).get("schema") or {})
                y_props = set((y_schema.get("properties") or {}).keys())
                l_props = set((l_schema.get("properties") or {}).keys())
                if y_props and l_props:
                    missing = y_props - l_props
                    if missing:
                        problems.append(
                            f"yaml 响应键不在实现: {m.upper()} {p} {code} → {sorted(missing)}")
                # y_props 有而 l_props 空 = live 响应无 schema (未声明
                # response_model) — 契约弱侧, 跳过 (已在 docstring 申报)
    assert not problems, (
        "openapi.yaml (GUI 类型生成源) 声明了实现没有的契约元素:\n  "
        + "\n  ".join(problems))



# ── G9: .gitignore 的规则不得遮住已跟踪的源文件 ────────────────────
#
# 起因（Codex #284 R1）：往 .gitignore 加了一条**没锚定**的 `data/`，
# 它匹配**任何**叫 data 的目录 —— 实测命中 `gui/src/data/` 与
# `api-service/app/data/`，共 **23 个已跟踪源文件**
# （`scenario_library.py` / `nr_band_baselines.json` / uxm_configs/…）。
#
# 为什么必须落成门：这个失效是**静默**的。已跟踪的文件不受影响，所以
# 测试全绿、构建全过、`git status` 干净；只有当某人往那两个目录**新加**
# 文件时才会发现"加不进去"，而那时早已没人记得是哪条规则干的。
# 本轮除了外审，没有任何东西会抓到它。
#
# ⚠ 判据必须用 `--no-index`：`git check-ignore` **默认跳过已跟踪文件**，
#    不加这个参数得到的永远是 0 —— 一道恒真断言。（我第一版就是这么写的。）

# 本门开出来时就已经存在的 6 处，**不由本门管**：
#   · api-service/data/reports/*.pdf ×5 —— 早于 `api-service/data/` 规则
#     （.gitignore:57）就提交的历史产物
#   · logs/services.info —— 同理，`logs/` 规则（.gitignore:69）
# 它们是"该不该继续跟踪"的问题，跟"规则写宽了误伤源码"不是一回事。
_IGNORED_TRACKED_KNOWN = {
    "logs/services.info",
}


def test_gitignore_does_not_shadow_tracked_sources():
    """.gitignore 里的规则不得命中已跟踪的文件。

    变异：把 `/data/` 的开头斜杠去掉 → 本门红（23 个源文件被遮住）。
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO_ROOT, capture_output=True, check=True,
    ).stdout
    res = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin", "-z"],
        cwd=_REPO_ROOT, input=tracked, capture_output=True,
    )
    shadowed = {p for p in res.stdout.decode().split("\0") if p}

    unexpected = sorted(
        p for p in shadowed
        if p not in _IGNORED_TRACKED_KNOWN
        and not p.startswith("api-service/data/reports/")
    )
    assert not unexpected, (
        "这些**已跟踪**的文件被 .gitignore 命中了 —— 规则写宽了：\n  "
        + "\n  ".join(unexpected)
        + "\n已跟踪的不受影响，但往同一目录**新加**的文件会被静默忽略。"
        "\n多半是漏了开头的 `/`（`data/` 匹配任何叫 data 的目录，`/data/` 只匹配根下那个）。"
    )


# ─────────────────────────────────────────────────────────────────────────────
# G12 (P1-39) — 系统日志面板的两条**会静默失效**的不变量
#
# 背景: P1-39 把日志表默认改成降序 (新在最上)。这个改动本身很小, 但它让两件
# 原本"恰好没事"的写法变成真 bug, 而**两者都不会报错、不会崩、看起来还正常**:
#
#   ① 排序若就地 reverse (`entries.reverse()`) 会**改掉 state 数组本身** ——
#      React state 被原地改动, 下一次渲染/轮询的比较基准就错了, 表现为条目
#      顺序间歇性跳动。写成 `[...entries].reverse()` 才安全。
#   ② 展开态若按**下标**记 (`Set<number>` + `expandedRows.has(idx)`), 在降序 +
#      自动刷新下每来一条新日志所有下标都移位 —— 用户展开的那行会跳到别的
#      日志上。升序+追加时下标恰好稳定, 所以旧写法一直没暴露。
#
# 这两条 GUI 侧没有单测基建可守 (gui/ 无 vitest/jest), 所以下沉成结构断言。
# ⚠️ 存在性档不够: 只查 "有没有 sortDesc" 会被"保留 token 的错写法"绕过,
#    所以这里查的是**具体的错写法不存在** + **正确写法存在**。
# ─────────────────────────────────────────────────────────────────────────────

_SLV_SOURCE = "gui/src/features/Reports/components/SystemLogViewer.tsx"


def test_g12_log_sort_does_not_mutate_state_and_expand_is_keyed():
    raw = (_REPO_ROOT / _SLV_SOURCE).read_text(encoding="utf-8")
    # ⚠ 先剥注释再扫代码 —— 否则注释里**引用**别处代码(例如解释后端那句
    #   `matched.reverse()`)会被当成本文件的就地调用, 门假红。
    src = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)

    # ① 任何**裸的**就地 reverse/sort 都不允许 —— 断的是"有没有先复制", 不是变量叫什么。
    #    内审 F4 实证: 早前写死 `entries.reverse()`, 一行别名
    #    `const rows = entries; rows.reverse()` 就绕过去了。
    for m in re.finditer(r"(\w+)\.(reverse|sort)\(", src):
        head = src[max(0, m.start() - 12):m.start()]
        assert head.rstrip().endswith("]"), (
            f"{_SLV_SOURCE} 出现就地 {m.group(1)}.{m.group(2)}() —— "
            f"若 {m.group(1)} 来自 React state 会被原地改动。"
            f"必须先复制: [...{m.group(1)}].{m.group(2)}()"
        )

    # ② 展开态必须按条目身份, 不能按下标
    assert "useState<Set<number>>" not in src, (
        f"{_SLV_SOURCE} 的 expandedRows 退回了 Set<number>(按下标) —— "
        f"降序+自动刷新下下标会移位, 展开的行会跳到别的日志上。"
    )
    assert "useState<Set<string>>" in src, (
        f"{_SLV_SOURCE} 找不到 Set<string> 形态的 expandedRows。"
    )

    # ③ **身份的性质**, 不是标识符的名字 (内审 F4: 早前断言实参必须叫 `rk`/`rowKey(`,
    #    于是把 rowKey 函数体换成 `String(entries.indexOf(e))` 照样绿, 而正当写法
    #    `expandedRows.has(rowKeys[i])` 反被假红)。改断 key 的**构成**:
    #    必须由条目自身的字段拼出, 且不得掺入下标类来源。
    key_src = re.search(r"const base = ([^\n]+)", src)
    assert key_src, f"{_SLV_SOURCE} 找不到条目 key 的构造 (const base = ...)"
    expr = key_src.group(1)
    for field in ("e.ts", "e.logger", "e.msg"):
        assert field in expr, (
            f"{_SLV_SOURCE} 的条目 key 不含 {field} —— key 必须由条目自身字段构成。"
            f"当前: {expr}"
        )
    # ③b 补上"实参不得是下标"（G12 换判据时一度把这条丢了, 变异 M4 当场变绿 ——
    #     构成检查与实参检查是**互补**的两个洞, 缺一个就能绕: 前者防"改 rowKey
    #     函数体", 后者防"绕过 key 直接传下标"）。用**否定式**而不是白名单,
    #     以免正当写法 (如 has(keys[i])) 被假红。
    for arg in re.findall(r"expandedRows\.has\(([^)]*)\)", src):
        a = arg.strip()
        assert not re.fullmatch(r"\d+|idx|index|i", a), (
            f"{_SLV_SOURCE} 的 expandedRows.has({a}) 传的是下标/常量 —— "
            f"降序+自动刷新下下标会移位, 展开的行会跳到别的日志上。"
        )

    for banned in ("indexOf", "index", "idx"):
        assert banned not in expr, (
            f"{_SLV_SOURCE} 的条目 key 掺入了下标来源 {banned!r} —— "
            f"那正是本门要防的那个 bug。当前: {expr}"
        )
