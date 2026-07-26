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
    # ⚠ 词边界匹配, 不用子串: "precheck_strict_cal" 是 "precheck_strict_calX"
    #   的子串, `in` 判会假绿 (本门首轮变异实跑抓出的洞)。
    missing = {
        f
        for f in expected
        if not re.search(rf"\bbody\.{re.escape(f)}\b", text)
    }
    assert not missing, (
        f"GUI labSmoke (Commissioning/api.ts) 缺 `body.<flag>` 赋值: {missing} — "
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

# 2026-07-26 基线 (F64R-12, #231 Codex 独立统计一致)。
# 谓词: ExceptHandler 函数体恰为单条 `pass` — 纯静默吞。
# `except: return None` 等非 pass 形态的静默吞不在此谓词内 (扩谓词先改这里
# 的注释与函数, 再整体重扫, 别在旧清单上手工加减)。
# 修复存量 (F64R-12) 时把对应文件的数字**下调** — 棘轮只进不退。
_SILENT_SWALLOW_BASELINE = {
    "propsim_f64.py": 12,
    "uxm_base_station.py": 9,
    "cmw500_base_station.py": 8,
    "aerotech_positioner.py": 3,
    "propsim_fs16.py": 3,
    "rf_switch.py": 2,
    "keysight_ena.py": 1,
}


def _count_bare_pass_handlers(source: str) -> int:
    tree = ast.parse(source)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    )


def test_g4_counter_behavior():
    """G4 的行为自测: 计数器必须数得对 (防谓词空转)。"""
    src = (
        "try:\n    a()\nexcept Exception:\n    pass\n"
        "try:\n    b()\nexcept Exception:\n    logger.warning('x')\n"
        "try:\n    c()\nexcept Exception:\n    pass\n"
        "try:\n    d()\nexcept Exception:\n    return None\n"
    )
    # 两处裸 pass; 带日志的和 except-return 的都不算
    assert _count_bare_pass_handlers(f"def f():\n{_indent(src)}") == 2


def _indent(block: str) -> str:
    return "".join(f"    {line}\n" for line in block.splitlines())


def test_g4_silent_swallow_ratchet():
    """app/hal 逐文件裸 pass 计数必须精确等于基线 — 新增即红 (吞异常不等于
    吞信息, 见 F64R-12); 修掉存量后下调基线, 把进度锁死。"""
    actual = {}
    for py in sorted(_HAL_DIR.glob("*.py")):
        n = _count_bare_pass_handlers(py.read_text(encoding="utf-8"))
        if n:
            actual[py.name] = n

    assert actual == _SILENT_SWALLOW_BASELINE, (
        "HAL 静默吞异常计数偏离基线。\n"
        f"  新增/上升: { {k: v for k, v in actual.items() if v > _SILENT_SWALLOW_BASELINE.get(k, 0)} }\n"
        f"  下降(好事, 请同步下调基线): { {k: v for k, v in actual.items() if v < _SILENT_SWALLOW_BASELINE.get(k, 999)} }\n"
        f"  基线中已消失的文件: { set(_SILENT_SWALLOW_BASELINE) - set(actual) }\n"
        "新增吞异常时: 要么记一句 logger.debug/warning 再吞 (吞异常不吞信息), "
        "要么给出手册/协议依据后调整基线。"
    )
