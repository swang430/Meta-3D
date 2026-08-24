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
G19 静态路由不被参数兄弟遮蔽 ← P1-29 `/alerts/{alert_id}` 抢先吃掉 `/alerts/summary`
   变异: 自测 router 先注册 `/{id}` 再注册 `/summary` → 必须检出；倒序必须放行。
G20 test_suite 告警写入必须有模块级 SQLite 隔离 ← P1-38 测试污染开发库
   变异: 任意新测试模块写 source=test_suite 但没接 SQLite/get_db/drop_all → 必须检出。

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
# G19 字面量路由不得被更早的同方法 path 参数路由遮蔽
# ─────────────────────────────────────────────────────────────────────

def _ordered_route_objects(routes, prefix=""):
    """按真实声明顺序展开 FastAPI 0.141 的懒加载路由树。"""
    out = []
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            sub = getattr(route, "original_router", None)
            ctx = getattr(route, "include_context", None)
            sub_prefix = getattr(ctx, "prefix", "") or "" if ctx is not None else ""
            if sub is not None:
                out.extend(_ordered_route_objects(sub.routes, prefix + sub_prefix))
            continue
        methods = getattr(route, "methods", None)
        if methods:
            out.append((set(methods), prefix + route.path))
    return out


def _literal_route_shadows(routes):
    """返回更早参数路由会吞掉的后续静态路由。"""
    from starlette.routing import compile_path

    ordered = _ordered_route_objects(routes)
    bad = []
    for index, (earlier_methods, earlier_path) in enumerate(ordered):
        if "{" not in earlier_path:
            continue
        earlier_regex, _, _ = compile_path(earlier_path)
        for later_methods, later_path in ordered[index + 1:]:
            shared_methods = earlier_methods & later_methods
            if "{" in later_path or not shared_methods:
                continue
            if earlier_regex.fullmatch(later_path):
                bad.append(
                    (earlier_path, later_path, tuple(sorted(shared_methods)))
                )
    return bad


def test_g19_checker_detects_shadow_and_accepts_safe_order():
    """判定器自测：必须会红，也不能把正确顺序误杀。"""
    from fastapi import APIRouter

    bad_router = APIRouter(prefix="/items")
    bad_router.get("/{item_id}")(lambda item_id: item_id)
    bad_router.get("/summary")(lambda: {})
    assert _literal_route_shadows(bad_router.routes) == [
        ("/items/{item_id}", "/items/summary", ("GET",))
    ]

    safe_router = APIRouter(prefix="/items")
    safe_router.get("/summary")(lambda: {})
    safe_router.get("/{item_id}")(lambda item_id: item_id)
    assert _literal_route_shadows(safe_router.routes) == []


def test_g19_live_static_routes_precede_shadowing_parameters():
    from app.main import app

    # P1-49 已清零首次落门时记录的两个存量；后续不得新增精确例外。
    known_existing = set()
    bad = set(_literal_route_shadows(app.routes))
    unexpected = bad - known_existing
    stale_exceptions = known_existing - bad
    assert not unexpected, (
        "以下静态路由声明在会吞掉它的 path 参数路由之后，真实请求会先命中参数路由: "
        f"{sorted(unexpected)}"
    )
    assert not stale_exceptions, (
        "G19 存量例外已经不再命中；请删除对应例外并同步关闭 Discovered 条目: "
        f"{sorted(stale_exceptions)}"
    )


# ─────────────────────────────────────────────────────────────────────
# G20 test_suite 告警写入必须隔离在模块自己的 SQLite DB
# ─────────────────────────────────────────────────────────────────────

def _literal_string(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _test_suite_source_write_lines(tree: ast.AST) -> list[int]:
    """定位真正构造 ``source=test_suite`` 数据的 AST 站点，不查注释/说明文本。"""
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _literal_string(key) == "source" and _literal_string(value) == "test_suite":
                    lines.add(node.lineno)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "source" and _literal_string(keyword.value) == "test_suite":
                    lines.add(node.lineno)
    return sorted(lines)


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _is_get_db_override_target(node: ast.AST) -> bool:
    if not isinstance(node, ast.Subscript):
        return False
    owner = node.value
    if not (
        isinstance(owner, ast.Attribute)
        and owner.attr == "dependency_overrides"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "app"
    ):
        return False
    return isinstance(node.slice, ast.Name) and node.slice.id == "get_db"


def _is_base_metadata_drop_all(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "drop_all"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "metadata"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "Base"
    )


def _test_suite_alert_isolation_gaps(tests_dir: Path | None = None):
    """返回每个写测试告警但隔离契约不完整的模块及缺项。"""
    tests_dir = tests_dir or (_API_SERVICE_ROOT / "tests")
    gaps = []
    # 与 pytest.ini 的 python_files 保持一致；集合并集避免 test_*_test.py 重复扫描。
    test_paths = {
        path
        for pattern in ("test_*.py", "*_test.py")
        for path in tests_dir.rglob(pattern)
    }
    for path in sorted(test_paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        write_lines = _test_suite_source_write_lines(tree)
        if not write_lines:
            continue

        has_sqlite_engine = False
        has_get_db_override = False
        has_drop_all = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    _call_name(node) == "create_engine"
                    and node.args
                    and (_literal_string(node.args[0]) or "").startswith("sqlite")
                ):
                    has_sqlite_engine = True
                if _is_base_metadata_drop_all(node):
                    has_drop_all = True
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(_is_get_db_override_target(target) for target in targets):
                    has_get_db_override = True

        missing = []
        if not has_sqlite_engine:
            missing.append("independent SQLite create_engine")
        if not has_get_db_override:
            missing.append("app.dependency_overrides[get_db]")
        if not has_drop_all:
            missing.append("Base.metadata.drop_all teardown")
        if missing:
            try:
                shown = str(path.relative_to(_API_SERVICE_ROOT))
            except ValueError:
                shown = str(path)
            gaps.append((shown, tuple(write_lines), tuple(missing)))
    return gaps


def test_g20_checker_detects_any_writer_module_and_accepts_isolation(tmp_path):
    """判定器自测：pytest 两种文件名的坏写点必须报，完整隔离模块必须放行。"""
    bad = tmp_path / "test_unexpected_alert_writer.py"
    bad.write_text(
        'payload = {"source": "test_suite", "message": "Test alert"}\n',
        encoding="utf-8",
    )
    suffix_bad = tmp_path / "alert_writer_test.py"
    suffix_bad.write_text(
        'payload = build_alert(source="test_suite")\n',
        encoding="utf-8",
    )
    overlap_bad = tmp_path / "test_overlap_test.py"
    overlap_bad.write_text(
        'payload = build_alert(source="test_suite")\n',
        encoding="utf-8",
    )
    gaps = _test_suite_alert_isolation_gaps(tmp_path)
    assert len(gaps) == 3, "同时命中两种 pytest 文件模式的模块不得重复报告"
    assert {gap[0] for gap in gaps} == {str(bad), str(suffix_bad), str(overlap_bad)}
    for _path, lines, missing in gaps:
        assert lines == (1,)
        assert set(missing) == {
            "independent SQLite create_engine",
            "app.dependency_overrides[get_db]",
            "Base.metadata.drop_all teardown",
        }

    bad.unlink()
    suffix_bad.unlink()
    overlap_bad.unlink()
    good = tmp_path / "test_another_alert_writer.py"
    good.write_text(
        '_engine = create_engine("sqlite://")\n'
        'app.dependency_overrides[get_db] = override\n'
        'payload = build_alert(source="test_suite")\n'
        'Base.metadata.drop_all(bind=_engine)\n',
        encoding="utf-8",
    )
    assert _test_suite_alert_isolation_gaps(tmp_path) == []


def test_g20_test_suite_alert_writers_are_sqlite_isolated():
    gaps = _test_suite_alert_isolation_gaps()
    assert not gaps, (
        "以下测试模块会写 source=test_suite 告警，却没把 HTTP DB 会话完整隔离到"
        "独立 SQLite（新站点不得污染开发/现场库）:\n"
        + "\n".join(
            f"  {path}:{lines} 缺 {missing}" for path, lines, missing in gaps
        )
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
    "aerotech_positioner.py": {"_silent_reconnect": 1},
    "cmw500_base_station.py": {
        "get_throughput_metrics": 4, "get_ue_info": 1, "start_signaling": 1,
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
_DOC_CURL_REQUEST = re.compile(
    r"\bcurl\b.*?(?:-X\s+|--request(?:=|\s+))"
    r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b",
    re.IGNORECASE,
)


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
    prefix = line[:start]
    m = _DOC_VERB.search(prefix)
    if m:
        return m.group(1)
    # curl 的动词与路径之间隔着 URL authority，不能靠“紧邻路径”抽取。
    curl = _DOC_CURL_REQUEST.search(prefix)
    return curl.group(1).upper() if curl else None


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


def _g11_non_path_parameter_pairs(parameters):
    """契约参数的 (name, in)；path 名由路径 shape 负责，避免参数名差异误报。"""
    return {
        (parameter["name"], parameter.get("in", ""))
        for parameter in (parameters or [])
        if isinstance(parameter, dict)
        and "name" in parameter
        and parameter.get("in") != "path"
    }


def _g11_schema_type(schema):
    """提取响应容器类型；无显式 type 时由 properties/items 作保守推导。"""
    if not isinstance(schema, dict):
        return None
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return schema_type
    if "properties" in schema:
        return "object"
    if "items" in schema:
        return "array"
    return None


def _g11_resolve(doc, node):
    """解析本地 $ref；循环/异常深链必须明确失败，不能让门挂死。"""
    for _ in range(20):
        if not (isinstance(node, dict) and "$ref" in node):
            return node
        ref = node["$ref"]
        assert ref.startswith("#/"), ref
        current = doc
        for part in ref[2:].split("/"):
            current = current[part]
        node = current
    raise AssertionError(f"$ref 链过深/成环: {node}")


def _g11_contract_problems(spec, live):
    """返回 checked-in OpenAPI 相对 live OpenAPI 的全部不兼容声明。"""
    live_by_shape = {}
    for path, operations in (live.get("paths") or {}).items():
        live_by_shape.setdefault(_g11_shape_segs(path), {}).update(operations)

    problems = []
    for path, methods in (spec.get("paths") or {}).items():
        live_methods = live_by_shape.get(_g11_shape_segs(path))
        if live_methods is None:
            problems.append(f"yaml 声明的路径不在实现: {path}")
            continue
        for method, operation in methods.items():
            if method in ("parameters", "description", "summary"):
                continue
            live_operation = live_methods.get(method)
            if live_operation is None:
                problems.append(f"yaml 声明的动词不在实现: {method.upper()} {path}")
                continue
            want = _g11_non_path_parameter_pairs(operation.get("parameters"))
            have = _g11_non_path_parameter_pairs(live_operation.get("parameters"))
            extra = want - have
            if extra:
                problems.append(
                    f"yaml 参数不在实现: {method.upper()} {path} → {sorted(extra)}")

            for code, response in (operation.get("responses") or {}).items():
                if not str(code).startswith("2"):
                    continue
                yaml_schema = _g11_resolve(
                    spec,
                    ((response.get("content") or {}).get("application/json") or {})
                    .get("schema") or {},
                )
                live_response = (live_operation.get("responses") or {}).get(str(code))
                if live_response is None:
                    problems.append(
                        f"yaml 声明的响应码不在实现: {method.upper()} {path} {code}")
                    continue
                live_schema = _g11_resolve(
                    live,
                    ((live_response.get("content") or {}).get("application/json") or {})
                    .get("schema") or {},
                )
                yaml_type = _g11_schema_type(yaml_schema)
                live_type = _g11_schema_type(live_schema)
                if yaml_type and live_type and yaml_type != live_type:
                    problems.append(
                        f"yaml 响应类型与实现不兼容: {method.upper()} {path} {code} "
                        f"→ yaml={yaml_type}, live={live_type}")
                    continue
                yaml_properties = set((yaml_schema.get("properties") or {}).keys())
                live_properties = set((live_schema.get("properties") or {}).keys())
                if yaml_properties and live_properties:
                    missing = yaml_properties - live_properties
                    if missing:
                        problems.append(
                            f"yaml 响应键不在实现: {method.upper()} {path} {code} "
                            f"→ {sorted(missing)}")
                # yaml 有 properties 而 live 没有 schema = live 没声明 response_model；
                # 契约弱侧不硬比，维持既有收窄语义。
    return problems


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


def test_g11_parameter_comparison_includes_location():
    """同名 path 参数不能替 query/header 参数顶账。"""
    yaml_params = [{"name": "execution_id", "in": "query"}]
    live_params = [{"name": "execution_id", "in": "path"}]
    assert (
        _g11_non_path_parameter_pairs(yaml_params)
        - _g11_non_path_parameter_pairs(live_params)
    ) == {("execution_id", "query")}


def test_g11_curl_request_verb_is_extracted_before_absolute_url():
    line = "curl -X POST http://localhost:8000/api/v1/dashboard/alerts"
    assert _doc_verb_before(line, line.index("/api/v1")) == "POST"
    long_form = "curl --request=PATCH http://localhost/api/v1/test-plans/cases/abc"
    assert _doc_verb_before(long_form, long_form.index("/api/v1")) == "PATCH"


def test_g11_response_schema_type_mismatch_is_visible():
    assert _g11_schema_type({"type": "array"}) == "array"
    assert _g11_schema_type({"type": "object", "properties": {}}) == "object"
    assert _g11_schema_type({"properties": {"id": {"type": "string"}}}) == "object"


def test_g11_contract_checker_catches_location_and_schema_mutations():
    response_object = {
        "content": {
            "application/json": {
                "schema": {"type": "object", "properties": {"id": {"type": "string"}}}
            }
        }
    }
    live = {
        "paths": {
            "/items/{live_id}": {
                "get": {
                    "parameters": [{"name": "execution_id", "in": "path"}],
                    "responses": {"200": response_object},
                }
            }
        }
    }
    mutated_spec = {
        "paths": {
            "/items/{doc_id}": {
                "get": {
                    "parameters": [{"name": "execution_id", "in": "query"}],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"type": "array", "items": {}}}
                            }
                        }
                    },
                }
            }
        }
    }
    problems = _g11_contract_problems(mutated_spec, live)
    assert any("('execution_id', 'query')" in problem for problem in problems)
    assert any("yaml=array, live=object" in problem for problem in problems)


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

    P3-18 已收口三处覆盖面：非 path 参数按 (name, in) 比对；curl -X/--request
    动词由散文半识别；响应 schema 在 properties 比对前先拒绝 object/array 等
    明确容器类型不兼容。"""
    import yaml as _yaml

    from app.main import app

    spec = _yaml.safe_load((_REPO_ROOT / "api" / "openapi.yaml").read_text())
    problems = _g11_contract_problems(spec, app.openapi())
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


# ── G12: P0-5 SCPI 手册证据范围不得被现场观察/配置声明放宽 ───────

def test_g12_p0_5_scpi_evidence_catalog_is_strict_and_complete():
    """关键命令有来源；IRAT 未证错误队列与 APPLY 范围必须保持 fail-closed。"""
    from app.hal.scpi_evidence import (
        EvidenceStatus,
        InstrumentEnvironment,
        evaluate_catalog_scope,
        load_p0_5_catalog,
    )

    path = _API_SERVICE_ROOT / "app/data/scpi_evidence/p0_5_commands.json"
    catalog = load_p0_5_catalog(path)
    mandatory = {entry.id for entry in catalog.entries.values() if entry.mandatory}
    expected = {
        "f64.model_load", "f64.operation_complete", "f64.error_queue",
        "f64.simulation_state", "f64.model_state", "f64.center_frequency",
        "f64.input_reference", "f64.crest_factor", "f64.output_gain",
        "f64.output_loss", "f64.bypass_mode", "uxm.config_readback",
        "uxm.config_apply", "uxm.cell_status", "uxm.error_queue",
        "uxm.dl_throughput", "positioner.move_absolute",
        "positioner.position_feedback",
    }
    assert mandatory == expected
    source_ids = {
        "f64": "982222b7-4953-46cd-9949-00fa97882353",
        "uxm": "236d9621-e3ce-4ed1-a8e1-7819b674dbcd",
        "positioner": "aerotech-ensemble-ascii-v1.0",
    }
    source_kinds = {
        "f64": "notebooklm",
        "uxm": "notebooklm",
        "positioner": "vendor-integration",
    }
    assert all(
        (
            entry.source.kind,
            entry.source.source_id,
        )
        == (
            source_kinds[entry.instrument],
            source_ids[entry.instrument],
        )
        for entry in catalog.entries.values()
    )

    irat = InstrumentEnvironment(
        instrument_id="gate",
        instrument="uxm",
        model="E7515B",
        firmware_version="28.21.0.32",
        test_application="LTE_NR_IRAT",
        captured_from_live_connection=True,
    )
    err = catalog.entries["uxm.error_queue"]
    assert err.status is EvidenceStatus.UNVERIFIED
    assert not evaluate_catalog_scope(err, irat).eligible
    # BSE APPLY 的现有手册来源只声明 NSA|SA；不得凭现场能发就扩到 IRAT。
    assert not evaluate_catalog_scope(catalog.entries["uxm.config_apply"], irat).eligible
    assert not evaluate_catalog_scope(catalog.entries["uxm.cell_status"], irat).eligible
    assert not evaluate_catalog_scope(catalog.entries["uxm.dl_throughput"], irat).eligible


# ── G13: P1-28 当前暗室只能来自 LabProfile 绑定 ──────────────────

def test_g13_current_chamber_consumers_use_single_resolver():
    """旧列可留作迁移兼容，但不能再被生产路径当作当前暗室选择器。"""
    chamber_api = (
        _API_SERVICE_ROOT / "app/api/chamber.py"
    ).read_text(encoding="utf-8")
    workflow = (
        _API_SERVICE_ROOT / "app/services/workflow_engine.py"
    ).read_text(encoding="utf-8")

    assert "ChamberConfiguration.is_active" not in chamber_api
    assert "ChamberConfiguration.is_active" not in workflow
    assert "chamber.is_active" not in chamber_api
    assert "resolve_current_chamber" in chamber_api
    assert "resolve_current_chamber" in workflow

    from app.schemas.chamber import ChamberConfigurationUpdate

    assert "is_active" not in ChamberConfigurationUpdate.model_fields

    offenders = []
    for path in (_API_SERVICE_ROOT / "app").rglob("*.py"):
        if path == _API_SERVICE_ROOT / "app/models/chamber.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "ChamberConfiguration.is_active" in source and path.name != "chamber_resolution.py":
            offenders.append(str(path.relative_to(_API_SERVICE_ROOT)))
    assert offenders == [], f"生产代码重新读取了废弃暗室选择器: {offenders}"

    supported_seed_scripts = (
        _API_SERVICE_ROOT / "scripts/dev-fixtures/seed_caict_lab_profile.py",
        _API_SERVICE_ROOT / "scripts/dev-fixtures/seed_caict_switch_topology.py",
    )
    script_offenders = [
        str(path.relative_to(_API_SERVICE_ROOT))
        for path in supported_seed_scripts
        if "ChamberConfiguration.is_active" in path.read_text(encoding="utf-8")
    ]
    assert script_offenders == [], f"受支持的初始化脚本仍读取废弃选择器: {script_offenders}"


def test_g13_gui_chamber_consumers_fail_closed_and_track_source_provenance():
    app_source = (_REPO_ROOT / "gui/src/App.tsx").read_text(encoding="utf-8")
    chamber_card_source = (
        _REPO_ROOT / "gui/src/components/ChamberConfigCard.tsx"
    ).read_text(encoding="utf-8")
    ota_source = (
        _REPO_ROOT / "gui/src/components/OTAMapper/ProbeArraySelector.tsx"
    ).read_text(encoding="utf-8")

    assert ": probes),\n    [probes, activeChamberId]" not in app_source
    assert "loadedChamberSource" in ota_source
    assert "loadedChamberSource.labProfileId" in ota_source
    assert "loadedChamberSource.chamberId" in ota_source
    for source in (app_source, ota_source):
        assert "isFetching: isActiveChamberLoading" not in source
        assert "isLoading: isActiveChamberLoading" in source
    assert "isFetching: isActiveLoading" not in chamber_card_source
    assert "isLoading: isActiveLoading" in chamber_card_source
    assert (
        "queryClient.setQueryData(['chamber', 'active', labProfileId], newChamber)"
        in chamber_card_source
    )
    assert "onSuccess: (newChamber, { labProfileId })" in chamber_card_source
    assert "onSuccess: (cloned, { labProfileId })" in chamber_card_source


def test_g13_integrity_audit_catalog_covers_every_direct_calibration_reference():
    """新增带 chamber_id 的校准表时，必须进入 orphan 巡检而非静默漏掉。"""
    from app.db.database import Base
    from app.services.chamber_resolution import _CALIBRATION_CHAMBER_TABLES

    direct_chamber_tables = {
        name
        for name, table in Base.metadata.tables.items()
        if "chamber_id" in table.c and name != "switch_topologies"
    }
    assert set(_CALIBRATION_CHAMBER_TABLES) == direct_chamber_tables


def test_g13_checker_self_test_detects_legacy_selector_shape():
    """防止 G13 退化成永远为绿的存在性检查。"""
    bad = (
        "db.query(ChamberConfiguration).filter("
        "ChamberConfiguration.is_active == True).first()"
    )
    assert "ChamberConfiguration.is_active" in bad


# ── G14: P1-43 历史分页不得混进实时轮询 ────────────────────────

def test_g14_log_history_is_explicit_and_freezes_the_live_snapshot():
    """GUI 的历史取数必须走独立端点，并在前插旧页前退出自动刷新。

    后端不重不漏、空页推进及游标失效由 test_system_logs_tail_filter.py 的
    行为门兜底；本门只守前端接线不把重历史路径挂进 interval。

    变异：interval 回调改为 loadOlder、删掉 historyModeRef 短路、删掉同步
    clearInterval，或把前插改成覆盖 → 本门红。
    """
    source = _strip_ts_comments((
        _REPO_ROOT / "gui/src/features/Reports/components/SystemLogViewer.tsx"
    ).read_text(encoding="utf-8"))

    assert "if (!historyModeRef.current) fetchLogs()" in source
    assert "setInterval(loadOlder" not in source
    history_start = source.index("const loadOlder = useCallback")
    history_end = source.index("const handleDownload", history_start)
    history = source[history_start:history_end]
    assert "'/system-logs/history'" in history
    assert "historyModeRef.current = true" in history
    assert "clearInterval(intervalRef.current)" in history
    assert "setRefreshInterval('0')" in history
    assert "setEntries(current => [...olderEntries, ...current])" in history
    assert "cursor," in history

    mock_db = (
        _REPO_ROOT / "gui/src/api/mockDatabase.ts"
    ).read_text(encoding="utf-8")
    mock_server = (
        _REPO_ROOT / "gui/src/api/mockServer.ts"
    ).read_text(encoding="utf-8")
    assert "MOCK_HISTORY_SCAN_LIMIT" in mock_db
    mock_db_history_start = mock_db.index("getSystemLogsHistory(")
    mock_db_history_end = mock_db.index("getSystemLogFiles()", mock_db_history_start)
    mock_db_history = mock_db[mock_db_history_start:mock_db_history_end]
    assert "scanMockLogPage" in mock_db_history
    assert "decodeMockLogCursor" in mock_db_history
    assert "status: 400" in mock_db_history and "status: 409" in mock_db_history
    mock_history_start = mock_server.index("mock.onGet('/system-logs/history')")
    mock_history_end = mock_server.index("mock.onGet('/system-logs/files')", mock_history_start)
    mock_history = mock_server[mock_history_start:mock_history_end]
    for forwarded in (
        "params.cursor", "params.lines", "params.level", "params.keyword",
        "params.session_id", "params.execution_id",
    ):
        assert forwarded in mock_history, f"mock history 未转发 {forwarded}"


# ── G15: P1-44 日志降序必须先归组，展开态不得按下标 ─────────────

def test_g15_log_sort_groups_continuations_and_uses_stable_identity():
    """恢复 #292 拆出的原 G12，并补上 traceback 先归组后翻转的不变量。"""
    viewer_path = "gui/src/features/Reports/components/SystemLogViewer.tsx"
    zone_path = "gui/src/features/Dashboard/ZoneLogsAlerts.tsx"
    util_path = "gui/src/utils/logEntries.ts"
    viewer = _strip_ts_comments((_REPO_ROOT / viewer_path).read_text(encoding="utf-8"))
    zone = _strip_ts_comments((_REPO_ROOT / zone_path).read_text(encoding="utf-8"))
    util = (_REPO_ROOT / util_path).read_text(encoding="utf-8")

    assert "useState<Set<number>>" not in viewer
    assert "useState<Set<string>>" in viewer
    assert "groupLogContinuations(entries)" in viewer
    assert "filterGroupedLogEntries(data?.entries ?? []," in zone
    assert "[...keyedEntries].reverse()" in viewer
    assert "[...groupedEntries].reverse()" in zone
    assert "top: sortDesc ? 0 : viewportRef.current.scrollHeight" in zone

    key_src = re.search(r"const base = (.*?)\n\s*const n = ", viewer, re.S)
    assert key_src, "找不到稳定日志身份构造"
    expr = key_src.group(1)
    for field in (
        "e.ts", "e.level", "e.logger", "e.hal_mode", "e.session_id",
        "e.execution_id", "e.instrument_id", "e.msg", "e.raw",
        "e.continuation_lines",
    ):
        assert field in expr, f"日志身份缺 {field}"
    assert "JSON.stringify([" in expr
    for banned in ("indexOf", "idx"):
        assert banned not in expr
    for arg in re.findall(r"expandedRows\.has\(([^)]*)\)", viewer):
        assert not re.fullmatch(r"\s*(?:\d+|idx|index|i)\s*", arg)

    assert "entry.level.toUpperCase() === 'RAW'" in util
    assert "previous.continuation_lines.push" in util
    assert "grouped.push" in util
    assert viewer.index("groupLogContinuations(entries)") < viewer.index(".reverse()")
    assert zone.index("filterGroupedLogEntries(data?.entries ?? [],") < zone.index(".reverse()")

    tbody_start = viewer.index("<Table.Tbody>")
    tbody_end = viewer.index("</Table.Tbody>", tbody_start)
    tbody = viewer[tbody_start:tbody_end]
    assert "renderLogDetail(entry)" in tbody


def test_p2_25_log_file_picker_separates_current_and_searchable_history():
    """当前日志不得再与两类历史文件混成一份平铺下拉。"""
    viewer = _strip_ts_comments((
        _REPO_ROOT / "gui/src/features/Reports/components/SystemLogViewer.tsx"
    ).read_text(encoding="utf-8"))

    assert "buildLogFileCatalog(files)" in viewer
    assert "'current' | 'history'" in viewer
    assert "'category' | 'execution'" in viewer
    for label in ("当前日志", "历史日志", "分类日志", "执行日志"):
        assert label in viewer
    assert "searchable" in viewer

    refresh_helper = viewer[viewer.index("const stopAutoRefreshForHistory"):]
    refresh_helper = refresh_helper[:refresh_helper.index("const handleLogModeChange")]
    assert "setRefreshInterval('0')" in refresh_helper
    assert "clearInterval(intervalRef.current)" in refresh_helper
    mode_handler = viewer[viewer.index("const handleLogModeChange"):]
    mode_handler = mode_handler[:mode_handler.index("return (")]
    assert "stopAutoRefreshForHistory()" in mode_handler
    assert "setSelectedFile" in mode_handler
    assert "disabled={logMode === 'history'}" in viewer
    assert "const fileActionsDisabled = !selectedFile" in viewer
    assert viewer.count("disabled={fileActionsDisabled}") >= 3

    fetch_logs = viewer[viewer.index("const fetchLogs = useCallback"):]
    fetch_logs = fetch_logs[:fetch_logs.index("const loadOlder")]
    empty_guard = fetch_logs.index("if (!selectedFile)")
    assert fetch_logs.index("++requestGenerationRef.current") < empty_guard
    empty_branch = fetch_logs[empty_guard:fetch_logs.index("historyModeRef.current = false")]
    assert "setLoading(false)" in empty_branch


def test_p2_25_mock_catalog_and_roadmap_status_match_live_ui():
    """Mock 开发必须能看到三类目录，Roadmap 必须保留 P2-25 完成事实与批准队列。"""
    mock_db = (
        _REPO_ROOT / "gui/src/api/mockDatabase.ts"
    ).read_text(encoding="utf-8")
    files_start = mock_db.index("getSystemLogFiles()")
    files_end = mock_db.index("getDashboardAlertSummary()", files_start)
    files_source = mock_db[files_start:files_end]
    assert "app.log" in files_source
    assert "app.log.2026-08-11" in files_source
    assert "exec-848a0000-dead-beef.log" in files_source
    assert files_source.count("is_current: false") >= 2

    roadmap = (
        _REPO_ROOT / "docs/roadmap-first-call.md"
    ).read_text(encoding="utf-8")
    current_focus = roadmap[:roadmap.index("> **~~P1-48~~")]
    assert "| **P2-25** |" in current_focus
    assert "| ✅ PR #340 |" in current_focus
    for item_id in (
        *(f"P1-{number}" for number in range(49, 54)),
        *(f"P2-{number}" for number in range(25, 35)),
        "P3-20", "P3-21",
    ):
        assert item_id in current_focus, f"批准队列缺少 {item_id}"


# ─────────────────────────────────────────────────────────────────────
# G16 建会话请求的默认值不得跟配置 schema 打架
# ─────────────────────────────────────────────────────────────────────
#
# 母题: **同一个默认值活在两个地方**。`CreateSessionRequest` 与
# `MIMOOTAConfiguration` 有一批同名字段, 而 `_request_overrides()` 把请求侧的值
# **无条件**塞进 overrides —— 于是改了 schema 默认根本不生效, 被请求侧的旧值盖掉,
# 而且**没有任何测试会红**(两边各自的单测都过)。
#
# 2026-08-07 现场实证: 把 schema 的 frequency_hz/bandwidth_mhz 改成现场基线
# (3549.99 MHz / 40 MHz) 后, 建出来的会话仍然是 3500 MHz / 100 MHz —— 靠端到端
# 建一次真会话读回配置才发现。**单测全绿, 默认值全错。**
#
# 不变量: 请求侧任一跟配置 schema 同名的字段, 要么默认值**相等**,
#         要么请求侧默认是 **None**(= 不覆盖, 用 schema 默认)。
# 这条门是**不变量档**(从代码派生恒成立的关系), 不是存在性档 ——
# 新加字段、改任一侧默认值, 只要两处漂开就红。

def _session_request_vs_config_conflicts():
    """返回 [(字段名, 请求侧默认, schema 默认)] —— 两处打架的字段。"""
    from app.api.commissioning import CreateSessionRequest
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration

    cfg = MIMOOTAConfiguration()
    out = []
    for name, field in CreateSessionRequest.model_fields.items():
        if not hasattr(cfg, name):
            continue
        req_default = field.default
        # None = "不覆盖, 用 schema 默认" —— 这是本仓已确立的语义
        # (见 _request_overrides 里 8 个 precheck_strict_* 的 is-not-None 写法)。
        if req_default is None:
            continue
        cfg_default = getattr(cfg, name)
        if req_default != cfg_default:
            out.append((name, req_default, cfg_default))
    return out


def test_g16_session_request_defaults_match_config_schema():
    """站点: CreateSessionRequest 的默认值不得静默盖掉 MIMOOTAConfiguration。"""
    conflicts = _session_request_vs_config_conflicts()
    assert not conflicts, (
        "CreateSessionRequest 与 MIMOOTAConfiguration 的默认值打架 —— "
        "请求侧会**无条件**覆盖 schema 默认, 改 schema 不生效且无测试会红。\n"
        + "\n".join(
            f"  {n}: 请求侧={r!r} vs schema={c!r}" for n, r, c in conflicts
        )
        + "\n修法二选一: ① 两处改成同值; ② 请求侧改成 Optional=None "
        "(不覆盖, 跟 precheck_strict_* 同语义) 并在 _request_overrides 里加 "
        "`if req.x is not None` 守卫。**优先 ②** —— 去掉重复胜过同步重复。"
    )


def test_g16_checker_detects_a_planted_conflict():
    """G16 判定器的行为自测: 造一个假冲突, 判定器必须抓到。

    ⓪④ 要求「每加一道门, 附上让它红的变异并实跑」。没有这条自测, 上面那条
    在判定器写错(比如把 `!=` 写成 `==`, 或者 hasattr 恒 False)时会**恒绿** ——
    那正是本文件反复在治的"存在性门被绕过"形态。
    """
    from app.api.commissioning import CreateSessionRequest
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration

    cfg = MIMOOTAConfiguration()
    # 挑一个两侧同名、且请求侧默认不是 None 的真实字段来做变异。
    victim = next(
        (n for n, f in CreateSessionRequest.model_fields.items()
         if hasattr(cfg, n) and f.default is not None),
        None,
    )
    assert victim is not None, (
        "找不到可用于变异的同名字段 —— G16 已失去意义(两侧不再有重叠), "
        "该删门或改写本自测, 别让它假绿。"
    )
    field = CreateSessionRequest.model_fields[victim]
    saved = field.default
    try:
        # 种一个绝不可能等于 schema 默认的值
        field.default = object()
        conflicts = _session_request_vs_config_conflicts()
        assert any(n == victim for n, _r, _c in conflicts), (
            f"判定器没抓到植入的冲突 (字段 {victim}) —— G16 是恒绿的假门"
        )
    finally:
        field.default = saved
    # 复位后必须回到干净态, 否则本自测会污染同进程的其它测试
    assert not any(n == victim for n, _r, _c in _session_request_vs_config_conflicts())


# ─────────────────────────────────────────────────────────────────────
# G18 诊断序列声明的品类必须覆盖它真正碰的驱动
# ─────────────────────────────────────────────────────────────────────
#
# 母题: **声明与事实脱钩**。序列的 `required_categories` / `optional_categories`
# 决定跑之前取哪些仪表租约; 序列体里 `drivers.get("X")` 才是它真正会碰的。
# 两者不一致时, 没声明的那个驱动停在 park 后的 Local 态 —— 一调就返 False。
#
# 2026-08-07 实证 (内审 F3): `baseStation_attach_check` 只声明 baseStation,
# 序列体却实打实调 channelEmulator 的 `stop_emulation` / `set_passthrough_mode`
# → F64 不在 Remote → 整条 attach 主力序列失败, 报错还指向 F64 状态机 (错方向)。
# 同文件里那句 `if key == "instrument_idn_sweep"` 的硬编码特判, 就是这个洞
# 已经咬过一次的物证。
#
# ⚠ 本门是**不变量门**: 从代码派生"声明集 ⊇ 实碰集"这个恒成立的关系,
#   不是"某个 token 在不在"的存在性门。新加序列漏声明会直接红。

def _sequence_declaration_gaps(seq_dir=None):
    """返回 [(模块名, 碰了但没声明的品类集合)]，空列表 = 全部对得上。

    `seq_dir` 可传：自测用它指向 `tmp_path`，避免往**源码包目录**写探针文件
    （G18 自测此前真往 `app/diagnostics/sequences/` 写，`finally` 兜不住
    Ctrl-C / 进程被杀，残留文件会被 `loader.py` 尝试导入，还会混进 git add）。
    """
    import re

    seq_dir = seq_dir or (_REPO_ROOT / "api-service/app/diagnostics/sequences")
    gaps = []
    for path in sorted(seq_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        src = path.read_text(encoding="utf-8")
        declared = set()
        for field in ("required_categories", "optional_categories"):
            m = re.search(rf"{field}=\[([^\]]*)\]", src)
            if m:
                declared |= set(re.findall(r'"([^"]+)"', m.group(1)))
        touched = (
            set(re.findall(r'drivers\.get\(\s*"([^"]+)"', src))
            | set(re.findall(r'drivers\[\s*"([^"]+)"\s*\]', src))
        )
        missing = touched - declared
        if missing:
            gaps.append((path.name, sorted(missing)))
    return gaps


def test_g18_sequence_declares_every_driver_it_touches():
    """⭐ 不变量门：每个序列声明的品类必须覆盖它源码里真正取用的驱动。"""
    gaps = _sequence_declaration_gaps()
    assert not gaps, (
        "以下诊断序列碰了没声明的驱动 —— 跑的时候那个驱动会停在 Local 态, "
        "一调就返 False, 而错误会指向被调的驱动而不是这里:\n"
        + "\n".join(f"  {name}: 碰了 {cats} 但 required/optional 里没有" for name, cats in gaps)
        + "\n修法: 跑不了就得有 → required_categories; 在场才碰、缺了能跳过 → optional_categories。"
    )


def test_g18_checker_catches_a_planted_gap(tmp_path):
    """判定器自测：种一个"碰了没声明"的假序列，判定器必须抓到。

    没有这条，上面那个门在**判定器抽不出东西**时会恒绿（比如正则写错、
    目录挪了），而恒绿的门比没有门更坏。
    """
    import re

    seq_dir = tmp_path
    planted = seq_dir / "zz_g18_planted_probe.py"
    planted.write_text(
        'METADATA = SequenceMetadata(\n'
        '    name="planted", description="g17 self-test",\n'
        '    required_categories=["baseStation"],\n'
        ')\n'
        'async def run(ctx, hal, params, log):\n'
        '    ce = drivers.get("channelEmulator")\n',
        encoding="utf-8",
    )
    try:
        gaps = dict(_sequence_declaration_gaps(seq_dir))
        assert "zz_g18_planted_probe.py" in gaps, (
            "判定器没抓到植入的脱钩序列 —— G18 是恒绿的假门"
        )
        assert gaps["zz_g18_planted_probe.py"] == ["channelEmulator"]
    finally:
        planted.unlink()
    # 复位后必须回到干净态
    assert "zz_g18_planted_probe.py" not in dict(_sequence_declaration_gaps(seq_dir))


# ── G17: 测试不得以 REAL 模式拉起 HAL（不会去连真仪器）──────────────

def test_g17_tests_never_bring_up_hal_in_real_mode():
    """⭐ **行为门** —— 在当前测试进程里，HAL 模式必须是 mock。

    2026-08-07 实证：`.env` 有 `USE_MOCK_INSTRUMENTS=false`（生产就该这样），
    而 `conftest.py` 此前不隔离，于是 `TestClient(app)` 的 lifespan 把 HAL 拉成
    REAL、真去连驱动默认 IP `192.168.100.x`。两个后果：本机 TUN 接管该网段后
    全量测试挂死 11m47s（内审硬门跟着落空）；**在现场机上跑 pytest 会把 F64
    拽进 Remote**，测试本身变成一次未经批准的仪器操作。

    变异：注释掉 `conftest.py` 顶部那行 `os.environ.setdefault(...)` → 本条红。
    """
    from app.config import settings

    assert settings.use_mock_instruments is True, (
        "测试进程的 HAL 模式是 REAL —— lifespan 会真去连 192.168.100.x 系列"
        "生产默认 IP。检查 tests/conftest.py 顶部的环境隔离是否还在、"
        "以及它是否仍排在 `from app.main import app` 之前。"
    )


def test_g17_isolation_precedes_app_import_in_conftest():
    """⭐ 顺序不变量 —— HAL 与日志换源都必须早于应用导入。

    `settings` 是模块级单例，导入 `app.main` 那一刻就把 `.env` 读定了。
    隔离必须排在它**之前**，否则设了也白设。

    上面那条断言的是"结果对"，这条锁的是"为什么对" —— 只有结果门时，
    把隔离挪到 app 导入之后，结果门在**单跑本文件**时可能仍绿（别的模块
    先导入过 app），这条能直接抓住。

    变异：把 `os.environ.setdefault` 挪到 `from app.main import app` 之后 → 本条红。
    """
    import pathlib

    src = pathlib.Path(__file__).parent.joinpath("conftest.py").read_text(
        encoding="utf-8"
    )
    # ⚠ 必须**行首锚定**：这两句话在文件顶部的注释里也逐字出现过
    #   （"必须在 `from app.main import app` 之前"），裸 `str.index` 会命中
    #   注释里那个、拿到比真导入更早的位置 —— 门当场给出假信号（本条第一版
    #   就这么红的）。同 memory「不去注释的文本门会被注释里的同一个词喂绿」。
    lines = src.splitlines()

    def _lineno(prefix: str) -> int:
        hits = [i for i, ln in enumerate(lines) if ln.startswith(prefix)]
        assert hits, f"conftest.py 里找不到行首以 {prefix!r} 开头的语句"
        return hits[0]

    isolation = _lineno('os.environ.setdefault("USE_MOCK_INSTRUMENTS"')
    log_isolation = _lineno('os.environ["LOG_DIR"] = ')
    app_import = _lineno("from app.main import app")
    assert isolation < app_import, (
        "conftest.py 里 HAL 模式隔离排在 `from app.main import app` 之后 —— "
        "settings 单例那时已经把 .env 读定了，设了也白设"
    )
    assert log_isolation < app_import, (
        "conftest.py 里 pytest 日志换源排在 `from app.main import app` 之后 —— "
        "测试进程会先打开并轮转用户的运行日志"
    )
    assert 'os.environ.setdefault("LOG_DIR"' not in src, (
        "pytest 日志隔离使用了 setdefault —— 调用方预置运行日志目录时仍会被放行；"
        "必须无条件覆盖为进程级临时目录"
    )


# ─────────────────────────────────────────────────────────────────────
# G21 多暗室探头校准入口必须显式消费 chamber_id
# ─────────────────────────────────────────────────────────────────────

_P1_53_CHAMBER_SCOPE_INVENTORY = (
    # REST writers and readers
    ("api-service/app/api/probe_calibration.py", "start_amplitude_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_amplitude_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_amplitude_calibration_history"),
    # start_phase_calibration 已随 P1-68 fail-loud 关闭（B-2：PFS power-only，
    # mock 生成口不再写库），不再是活动写点，移出 chamber-scope 名单。
    # REST 直接口仅剩 import_phase_calibration_csv_endpoint（仍在名单）；
    # workflow 引擎的 phase 步骤是仍活着的间接落库口（归 P1-69），其
    # service 写点 execute_phase_calibration 的 chamber-scope 由名单内
    # service 行覆盖。
    ("api-service/app/api/probe_calibration.py", "import_phase_calibration_csv_endpoint"),
    ("api-service/app/api/probe_calibration.py", "get_phase_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_phase_calibration_history"),
    ("api-service/app/api/probe_calibration.py", "start_polarization_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_polarization_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_polarization_calibration_history"),
    ("api-service/app/api/probe_calibration.py", "import_probe_pattern_endpoint"),
    ("api-service/app/api/probe_calibration.py", "start_pattern_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_pattern_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_validity_report"),
    ("api-service/app/api/probe_calibration.py", "get_expiring_calibrations"),
    ("api-service/app/api/probe_calibration.py", "get_expired_calibrations"),
    ("api-service/app/api/probe_calibration.py", "get_probe_validity"),
    ("api-service/app/api/probe_calibration.py", "invalidate_calibration"),
    ("api-service/app/api/probe_calibration.py", "get_probe_calibration_data"),
    # Service writers/imports and formal consumers
    ("api-service/app/services/probe_calibration_service.py", "AmplitudeCalibrationService.execute_amplitude_calibration"),
    ("api-service/app/services/probe_calibration_service.py", "PhaseCalibrationService.execute_phase_calibration"),
    ("api-service/app/services/probe_calibration_service.py", "PolarizationCalibrationService.execute_polarization_calibration"),
    ("api-service/app/services/probe_calibration_service.py", "PatternCalibrationService.execute_pattern_calibration"),
    ("api-service/app/services/probe_calibration_service.py", "CalibrationValidityService.check_validity"),
    ("api-service/app/services/probe_calibration_service.py", "CalibrationValidityService.generate_validity_report"),
    ("api-service/app/services/probe_calibration_service.py", "CalibrationValidityService.get_expiring_calibrations"),
    ("api-service/app/services/probe_calibration_service.py", "CalibrationValidityService.get_expired_calibrations"),
    ("api-service/app/services/probe_calibration_service.py", "CalibrationValidityService.invalidate_calibration"),
    ("api-service/app/services/probe_phase_calibration_import.py", "import_phase_calibration_from_csv"),
    ("api-service/app/services/probe_pattern/import_service.py", "import_probe_pattern"),
    ("api-service/app/services/probe_pattern/consumer.py", "_query_valid_pattern"),
    ("api-service/app/services/calibration_report_generator.py", "CalibrationReportGenerator._collect_probe_data"),
)


def _p1_53_qualified_function_source(relative_path: str, qualified_name: str) -> str:
    """Return one inventoried function body, including class qualification."""
    import ast

    path = _REPO_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    parts = qualified_name.split(".")
    nodes = tree.body
    target = None
    for index, part in enumerate(parts):
        expected = ast.ClassDef if index < len(parts) - 1 else (ast.FunctionDef, ast.AsyncFunctionDef)
        target = next(
            (node for node in nodes if isinstance(node, expected) and node.name == part),
            None,
        )
        assert target is not None, f"P1-53 入口清单已漂移：{relative_path}:{qualified_name} 不存在"
        nodes = getattr(target, "body", [])
    lines = source.splitlines()
    return "\n".join(lines[target.lineno - 1:target.end_lineno])


def test_g21_probe_calibration_active_sites_consume_chamber_scope():
    """P1-53 入口全集：四类探头校准的活动写读判定不得退回全局 probe_id。"""
    missing = []
    for relative_path, qualified_name in _P1_53_CHAMBER_SCOPE_INVENTORY:
        body = _p1_53_qualified_function_source(relative_path, qualified_name)
        if "chamber_id" not in body:
            missing.append(f"{relative_path}:{qualified_name}")
    assert not missing, (
        "以下多暗室探头校准入口未显式消费 chamber_id，可能按全局 probe_id "
        "混入其他暗室或 legacy NULL：\n  " + "\n  ".join(missing)
    )
