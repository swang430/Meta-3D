"""UXM 手册写法探针 —— 专门验证**我们没在用的那些命令拼法**。

为什么要单独一个序列(而不是塞进 `uxm_scpi_compatibility`)
--------------------------------------------------------
两者的契约**方向相反**:

- `uxm_scpi_compatibility` 枚举的是**驱动命令表里已有的**命令, 验"我们在用的这些
  这台固件认不认"。它按设计**跳过**表里标成 ``None`` 的项 —— 而 ``None`` 的语义正是
  "我们判定这台 Test App 不支持这条"。
- 于是它有一个结构性盲点: **它只能验证我们已经相信的东西, 验证不了我们相信错了的东西。**
  我们当年判"不支持"的那几条, 它永远不会再试一次。

而本项目有**明确的反例先例**: DL 功率与 SSB 功率当初也实测 ``-113`` 被判"不支持",
后来发现是**拼写不对** —— `:PHY:DL:POWer` 正确是 `:DL:POWer`, `:SSB:POWer` 正确是
`:SSB:POWer:ADVertised`(见 `uxm_command_profiles.py` 里那段注释)。
也就是说 **"这台机器不支持" 很可能一直是 "我们发的命令名不对"**。

本序列就是那个反例的系统化: 拿**手册的确切写法**逐条试, 记原始回复, 让
「我们拼错了」和「固件真没有」分得开。这是 P0-2 S4 的载体
(见 `docs/design/p0-2-uxm-config-single-source-design.md` R5)。

写法来源
--------
NotebookLM「Keysight UXM5G 网络测试 SCPI 编程指南」
`236d9621-e3ce-4ed1-a8e1-7819b674dbcd`, 2026-07-26 逐条查证, 附出处。
**禁盲试**: 这里每一条都能在手册里指到, 不是我们自己编的变体。

安全性
------
**全部只读**(纯 query, 不写任何值), 不改小区配置、不动信令。但会往错误队列灌
``-113``, 跟 `uxm_scpi_compatibility` 同理, 不与真实测试并行 → `safe_during_test=False`。
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
# 复用不复制: 错误码解析/分类与方言解析都跟兄弟序列同源, 免得两份判据漂移。
from app.diagnostics.sequences.uxm_scpi_compatibility import (
    _categorize_status,
    _parse_err,
    _profile_for_driver,
)
from app.services.diagnostic_context import DiagnosticContext


# (名字, 手册确切写法(带 {cell} 占位), 我们驱动里对应的常量名, 为什么要验)
#
# "驱动常量名" 是为了在结果里直接给出**对照结论**: 我们那条是什么写法、
# 是不是标成了"不支持"。没有对应常量的填 None。
_CANDIDATES: List[Tuple[str, str, Optional[str], str]] = [
    # ── ⭐ P0-2 R1/R2: 小区**真实状态**。当前驱动判 attach 用的是
    #    `BSE:CONFig:NR5G:{cell}:ACTive:STATe?` —— 那是我们自己写进去的 0/1 开关,
    #    不是小区状态。手册的状态查询是这条, 返回 OFF|ON|CONNected|IDLE|... ——
    #    正好是驱动注释里期望的那种值。这条通不通决定 P0-2 D1 能不能落地。
    ("CELL_STATUS", "BSE:STATus:NR5G:{cell}?", "BSE_STATUS(不带小区)",
     "⭐小区真实状态 (OFF|ON|CONNected|IDLE|AGGRegated|ACTivated)"),

    # ── P0-2 R5: 被我们标成"本机不支持"的, 逐条用手册写法重试
    ("SCS_COMMON", "BSE:CONFig:NR5G:{cell}:SUBCarrier:SPACing:COMMon?", "CELL_SCS(None)",
     "子载波间隔 — 我们的常量是 None(判不支持), 手册写法完全不同"),
    ("DUPLEX_MODE", "BSE:CONFig:NR5G:{cell}:DUPLEX:MODe?", "CELL_DUPLEX(None)",
     "双工模式 — 手册带 :MODe 后缀"),
    ("DL_POINTA", "BSE:CONFig:NR5G:{cell}:DL:POINta?", "CELL_DL_POINTA(None)",
     "PointA 频点 (16 步推荐序第 10 步)"),
    ("SSB_ARFCN", "BSE:CONFig:NR5G:{cell}:SSB:ARFCN?", "SSB_ARFCN(None)",
     "SSB 频点 (推荐序第 13 步)"),
    ("MIMO_LAYERS", "BSE:CONFig:NR5G:{cell}:PHY:PDSCh:MMIMolayers?", "MIMO_DL_LAYERS(None)",
     "DL MIMO 层数 — 手册名 MMIMolayers, 跟我们试过的完全不同"),

    # ── P0-2 R5: 手册 16 步推荐配置序里我们**根本没设**的几步。
    #    没设不等于不需要 —— 手册说乱序/缺步会让中间频率计算越界。
    ("FREQ_RANGE", "BSE:CONFig:NR5G:{cell}:FREQuency:RANGe?", None,
     "FR1/FR2 (推荐序第 3 步, 我们不设)"),
    ("SSB_SCS", "BSE:CONFig:NR5G:{cell}:SSB:SUBCarrier:SPACing?", None,
     "SSB 子载波间隔 (推荐序第 12 步, 我们不设)"),
    ("CORESET0", "BSE:CONFig:NR5G:{cell}:SSB:COReset0?", None,
     "CORESET#0 索引 (推荐序第 14 步, 我们不设)"),

    # ── 路径 A/B 泄漏相关 (架构文档 §6.1 记的 leak): 这些参数 HAL-init 会写进硬件,
    #    但正式测试不覆盖 → 残留。要治先得能读回来核对。
    ("DL_MIMO_CONFIG", "BSE:CONFig:NR5G:{cell}:DL:MIMO:CONFig?", "无",
     "MIMO 端口预设 (HAL-init 会写, 正式测试不覆盖 → 残留)"),
    ("HARQ_PROCESSES", "BSE:CONFig:NR5G:{cell}:PHY:DL:HARQ:PROCesses?", "HARQ_*(None)",
     "DL HARQ 进程数"),
    ("SCHED_SCENARIO", "BSE:CONFig:NR5G:SCHeduling:QCONFig:SCENario?", "PDSCH_SCHED_ALGO(None)",
     "调度场景 (整机级, 不带小区)"),

    # ⚠ **不探 `BSE:CONFig:NR5G:APPLY`** (P0-2 R3 那条"小区 ON 时改配置必须发它才
    # 进协议栈", 全驱动零调用)。原因两头都不划算, 审查逐条驳倒了我原来的设计:
    #   ① 手册白纸黑字标它 `Immediate Action / No query: True`、`Type: Imm Action`
    #      —— **查询节点本就不存在**, 回 -113 是正确行为, 却会被分类成 UNSUPPORTED,
    #      得出"这台机器不能 apply"的错结论。我原注释里"固件认头但拒 ? 会回
    #      -100..-109"是**没有依据的猜测**, 跟手册的 "No query" 声明正相反。
    #   ② 反过来若固件真把它执行了, 它的语义是"把**所有小区**的暂存配置推进协议栈"
    #      —— 本序列 docstring 那句"全部只读"当场破产。
    #   存在性手册已经权威回答, 探测收益近零、代价两头都有 → 不探。
]

# 这条通不通直接决定 P0-2 D1(小区状态换源)能不能落地 → 不通就该在现场当场升级。
# 其余候选"不支持"都是**有效结论**, 不该让整轮报红。
_CRITICAL = frozenset({"CELL_STATUS"})

# 手册 banding: CELL1..CELL14 | SELected (**没有 CELL0**)。入参也照这个卡。
_CELL_TOKEN = re.compile(r"(?:CELL(?:[1-9]|1[0-4])|SELected)", re.IGNORECASE)


metadata = SequenceMetadata(
    name="UXM 手册写法探针 (验我们没在用的拼法)",
    description=(
        "拿手册的确切写法逐条试那些我们**标成不支持**或**根本没设**的命令, 记原始回复。"
        "兄弟序列 uxm_scpi_compatibility 只验驱动表里已有的命令(标 None 的会跳过), "
        "结构上验不出'我们当年拼错了'——本序列专治这个。全部只读。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "小区 (留空=用当前方言的主小区)", "type": "string", "default": ""},
    ],
    safe_during_test=False,  # 会往错误队列灌 -113
)


async def _maybe_await(value: Any) -> Any:
    import asyncio
    if asyncio.iscoroutine(value):
        return await value
    return value


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(
            success=False, summary=driver_not_loaded_summary("baseStation"),
        )
    refusal = mock_driver_refusal_summary("baseStation", bs)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    if not hasattr(bs, "_query"):
        return SequenceRunResult(
            success=False,
            summary=f"baseStation 驱动 {type(bs).__name__} 没有 SCPI 查询通道 (_query)",
        )

    profile = _profile_for_driver(bs)
    profile_name = getattr(profile, "PROFILE_NAME", "?")

    # ⚠ 12 条候选的**根**硬编码成 `BSE:` —— 那是 Test App Framework(LTE_NR_IRAT)
    # 的命令树。另一套方言 5G_NR_Test 用的是裸 `CONFig:` / `CALL:` 根, 且主小区是
    # CELL0, 而手册里 `BSE:STATus:NR5G:<cell>?` 的 banding 只有 CELL1..CELL14|SELected
    # (**没有 CELL0**)。在非 BSE 方言上跑, 12 条会全回 -113, 于是得出"手册写法也不
    # 支持"的**错结论** —— 而"把自己发错当成机器不支持"正是本序列存在要治的病,
    # 自己踩上去就荒唐了。所以不匹配直接拒跑, 不猜。
    if getattr(profile, "PRIMARY_CELL", None) == "CELL0" or not getattr(
        profile, "BSE_STATUS", None
    ):
        return SequenceRunResult(
            success=False,
            summary=(
                f"当前方言是 {profile_name} —— 本探针的 12 条写法取自 Test App Framework "
                f"(BSE: 命令树, LTE_NR_IRAT), 在别的方言上跑会全回 -113 并给出错误结论。"
                "先确认 UXM 跑在 LTE_NR_IRAT 上再跑本序列。"
            ),
        )

    cell = (params.get("cell") or "").strip() or getattr(profile, "PRIMARY_CELL", "CELL1")
    if not _CELL_TOKEN.fullmatch(cell):
        return SequenceRunResult(
            success=False,
            summary=f"小区标识 {cell!r} 形态非法 —— 手册 banding 是 CELL1..CELL14 或 SELected。",
        )
    log(f"  · 方言 {profile_name} / 小区 {cell}")

    async def _q(cmd: str) -> Optional[str]:
        raw = await _maybe_await(bs._query(cmd))  # noqa: SLF001
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    # 开跑前把队列清干净 —— 否则上一次操作(或兄弟探针)留下的 -113 会被算到第一条
    # 候选头上, 而第一条恰恰是 _CRITICAL 的 CELL_STATUS → 整轮误报"关键项不可用"。
    # 这就是同轮在 F64 剧本上刚修的那个坑, 换台仪器重演 (审查 P2)。顺序同样是
    # **先读空再 `*CLS`**: 先清会把"开跑前有什么遗留"这条线索冲掉。
    stale: List[str] = []
    try:
        for _ in range(100):
            raw_e = await _q("SYST:ERR?")
            code_e, _t = _parse_err(raw_e or "")
            # ⚠ `None` = 读不出错误码(空/畸形/会话错位), **不是**"队列干净"。
            # 带着未验证的会话开始 12 条探测, 旧错误或迟到应答会跟首条关键的
            # CELL_STATUS 回复错配 → 把可用命令误判成不支持, 或归档错误的字面值,
            # 而本序列的产出正是"哪个拼法可用 + 它返回什么"。判据与 F64 剧本同源
            # (Codex #229 第四轮 P1: F64 那边上一轮已改, 这里是**漏掉的同族站点** ——
            # 同一条规则存两份, 改的时候只改了一份, 正是 memory
            # feedback_clear_stale_state_enumerate_all_sources 说的那个坑)。
            if code_e is None:
                return SequenceRunResult(
                    success=False,
                    steps=[SequenceStepResult(
                        label="开跑前排空错误队列", success=False,
                        detail=f"SYST:ERR? 读不出错误码 ({raw_e!r}) — 队列状态未知, 不能当干净",
                        raw=raw_e,
                    )],
                    summary=("开跑前排空错误队列失败: SYST:ERR? 回复读不出错误码 — "
                             "SCPI 会话未经验证, 此时探测出的'支持/不支持'结论不可信。"
                             "先确认通道正常再跑。"),
                )
            if code_e == 0:
                break
            stale.append((raw_e or "").strip())
        wfn = getattr(bs, "_write", None)
        if callable(wfn):
            await _maybe_await(wfn("*CLS"))
    except Exception as e:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"开跑前清错误队列失败: {type(e).__name__}: {e} — SCPI 通道可能已经卡死",
        )
    if stale:
        log(f"  · 清掉 {len(stale)} 条开跑前的遗留错误")

    steps: List[SequenceStepResult] = []
    counts: Dict[str, int] = {}
    supported_now: List[str] = []
    critical_unsupported: List[str] = []
    aborted = False

    for name, template, ours, why in _CANDIDATES:
        cmd = template.format(cell=cell)
        started = time.monotonic()
        reply: Optional[str] = None
        try:
            try:
                reply = await _q(cmd)
            except Exception:  # noqa: BLE001
                # 不支持的命令常常是"不回话 + 往队列压 -113" —— 真正的判据在错误队列,
                # 这里超时不算失败。
                reply = None
            raw_err = await _q("SYST:ERR?")
        except Exception as e:  # noqa: BLE001
            steps.append(SequenceStepResult(
                label=f"{name} → {cmd}", success=False,
                detail=f"错误队列读取异常: {type(e).__name__}: {e} — SCPI 通道可能卡死",
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            # ⚠ 必须记下"没跑完" —— 只 break 不标记的话, 通道断在第一条时
            # critical_unsupported 还是空, 总判定报**成功**、summary 写"0/12 条可用",
            # 归档里看起来像"跑过了, 结论是都不支持"。兄弟序列早有 aborted_early
            # 进总判定的写法, 新文件没继承 (审查 P2)。
            aborted = True
            break

        code, text = _parse_err(raw_err or "")
        status = _categorize_status(code)
        # ⚠ "查询没回话" + "错误队列却是干净的" = **两头都没结论**, 不能算支持。
        # 典型成因是一次瞬时 VISA 超时: 命令可能压根没送到, 队列自然也没有 -113。
        # 判成 SUPPORTED 的后果特别坏 —— 对关键的 CELL_STATUS 而言, 整轮会报成功,
        # 而我们**从没拿到过一个可以当状态真值源的值**(raw 是 None)。
        # 这正是本序列要产出的东西: "能用"的第一步是"它真回了话"。(Codex #229 P2)
        # 空串 / 纯空白跟"没回复"是同一件事: 都没拿到能用的值。只判 `is None` 会漏掉
        # 固件回了个空行的情形 (Codex #229 第二轮)。⚠ 归一化只用于**判定**,
        # `raw` 仍存原样 —— 那是本序列的产出, 不能被判定逻辑顺手抹掉。
        if (reply is None or not reply.strip()) and code == 0:
            status = "UNKNOWN"
        # ⚠ 上面那条只堵了"队列干净"这一种。⚠⚠ 判据要按**规则**不按上一条 finding
        # 举的**例子** —— 同样没拿到值的情形还有: 错误码是 -100..-112 / -200..-299
        # (固件认得命令头, 却拒绝当前查询形态或当前状态), 那几种 `_categorize_status`
        # 会给 SUPPORTED / SUPPORTED_BUT_STATE, 于是关键项被列为可用、整轮报成功,
        # 而 raw 里**根本没有一个能当小区状态真值源的值** → 现场据此假绿去做状态换源。
        # 本序列的产出是"哪个拼法可用 **且它返回什么**": 对 _CRITICAL 项,
        # "拿到非空回复"是通过的**必要条件**, 与错误码无关 (Codex #229 第七轮 P1)。
        #
        # 只对 _CRITICAL 收紧 —— 非关键项"命令头存在但当前状态不给值"是**有效结论**,
        # 不该判红。兄弟序列 propsim_f64_health 的 is_critical 语义不同 (问的是"这条
        # 命令在不在固件里", 空回复也可能是合法答案) → 不做同样收紧, 这是判断不是遗漏。
        if name in _CRITICAL and not (reply or "").strip():
            status = "UNKNOWN"
        counts[status] = counts.get(status, 0) + 1
        ok = status in ("SUPPORTED", "SUPPORTED_BUT_STATE")
        if ok:
            supported_now.append(name)
        elif name in _CRITICAL:
            critical_unsupported.append(name)

        steps.append(SequenceStepResult(
            label=f"{name} → {cmd}",
            success=ok,
            detail=(
                f"{status}{' ★' if name in _CRITICAL else ''}"
                f" [{code if code is not None else '?'}: {text or 'NO ERROR'}]"
                f" | 我们现在: {ours or '没有这条'} | {why}"
            ),
            # 命令**本身的回复**才是这个序列的产出 —— 通不通看错误码, 但"它到底
            # 返回什么"决定了我们能不能拿它当真值源 (例如小区状态那条)。
            raw=reply,
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
        log(f"  {'✓' if ok else '✗'} {name}: {status}" + (f" raw={reply!r}" if reply else ""))

    n_ok = len(supported_now)
    n_probed = len(steps)
    return SequenceRunResult(
        # 有 critical 不支持、或通道中断没跑完 → 失败。
        # 其余"不支持"是**有效结论**不是故障, 不该报红。
        success=(not critical_unsupported) and (not aborted),
        summary=(
            (f"⚠ SCPI 通道中断, 只探了 {n_probed}/{len(_CANDIDATES)} 条 — "
             if aborted else "手册写法探针: ")
            + f"{n_ok}/{n_probed if aborted else len(_CANDIDATES)} 条可用"
            + (f" — 可用的: {', '.join(supported_now)}" if supported_now else "")
            + (f" ⚠ 关键项不可用: {', '.join(critical_unsupported)}" if critical_unsupported else "")
        ),
        steps=steps,
        extra={
            "cell": cell,
            "profile": profile_name,
            "supported": supported_now,
            "critical_unsupported": critical_unsupported,
            "counts": counts,
            "aborted": aborted,
            "stale_errors_cleared": stale,
        },
    )
