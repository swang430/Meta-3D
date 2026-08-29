"""UXM 测量窗口 STATe 边界探针（`uxm_window_boundary_probe`，P2-52 现场复验载体）。

背景（P2-52 取证，2026-08-30，本地 zip HTML + NotebookLM 双源手册原文）
--------------------------------------------------------------------
NR 域 BTHRoughput 树的控制命令恰 4 条：`BSE:MEASure:NR5G:BTHRoughput[:STATe]`
（"Enables/disables BLER measurement"，Boolean，Default 0）/ `CONTinuous[:ALL]`
/ `LENGth[:ALL]` / `CLEar`（"Resets... if in-progress it will automatically be
restarted"）——其余全 Query only，**没有**独立 STARt/STOP，也没有权威
closed 边界。两处推断缺口挡住了 lifecycle 升级到 authoritative_closed：

1. `[:STATe]?` **查询形手册未列**（显式 `:STATe` 展开是方括号可选节点的
   SCPI 标准等价 —— 推断；对比 `CSI:STATe?` 手册显式带 `?` 并标 Query only）。
2. 上述条目 AppMode 全标 NSA|SA；`SYSTem:APPLication` 里 NSA 与 LTE_NR_IRAT
   并列互斥，NSA|SA 命令在 IRAT 下认不认**手册未说明**（P1-32 规矩：
   两个方向都没证据 = 未经查证）。

本探针到场后一跑即知：`STATe?` 被认 → 缺口 1 关掉一半（查询形实测成立，
可回读累积开关现状）；回 -113 → 推断查询形不成立，这**也是答案**。

剧本（照 rs_fsva_iq_capability 前例：只读优先、每步错误队列归属）
----------------------------------------------------------------
1. 方言门：当前 profile 未定义 `MEAS_BTHROUGHPUT_STATE_QUERY`（如
   5G_NR_Test —— BSE 树在该方言认不认未经查证，不猜）→ 直接拒跑。
2. 预排水 `SYSTem:ERRor?` 到 0（stale 错误不许挂到本探针的命令名下）。
3. 发 `BTHRoughput:STATe?` 读现状 → 立即归属错误队列。
4. **读到 ON 也不动**（测量在累积，本探针不干预）；**绝不发 OFF/ON** ——
   条目明令不盲试，OFF 写形复验留给现场操作员按取证文档
   `docs/plans/2026-08-30-p2-52-uxm-window-boundary-evidence.md` §现场复验
   在本探针结果指引下人工执行。
5. 收尾排水一轮。

**零写命令**：全程只有 `STATe?` / `SYSTem:ERRor?` 两种查询（连 `*CLS` 都
不发 —— 排水用查询循环完成），由 test_p2_52 的行为门守着。

四态 `extra["verdict"]`（照 P1-65 / rs_fsva 序列形态）：SUCCESS（查询可判定，
无论支持与否；`state_query_supported` 记 True/False）/ BLOCKER（无法归属的
超时 / 异常 / 无回复 / 队列不可判）/ UNDETERMINED（可判但收尾队列有残留）/
ABORTED（方言门未过或预排水失败，`STATe?` 未发）。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
from app.diagnostics.sequences.uxm_scpi_compatibility import _profile_for_driver

metadata = SequenceMetadata(
    name="UXM 测量窗口 STATe 边界探针 (只读)",
    description=(
        "P2-52 现场复验载体：只读 `BSE:MEASure:NR5G:BTHRoughput:STATe?`"
        "（⚠ 推断查询形 —— 方括号展开 + 查询形无手册原文）并立即归属错误"
        "队列，判定该推断形在真机成不成立、顺带归档累积开关现状。"
        "**零写命令**：读到 ON 也不动，绝不发 OFF/ON（条目明令不盲试；"
        "OFF 写形复验由现场操作员按取证文档人工执行）。"
    ),
    required_categories=["baseStation"],
    params_schema=[],
    safe_during_test=False,  # 排空 SYSTem:ERRor? 会吞并发操作的错误归属
)

_ERR_DRAIN_CAP = 50
_STATE_QUERY_ERR = "SYSTem:ERRor?"


def _result(verdict: str, summary: str, steps: List[SequenceStepResult],
            extra: Dict[str, Any]) -> SequenceRunResult:
    extra = dict(extra)
    extra["verdict"] = verdict
    return SequenceRunResult(success=(verdict == "SUCCESS"), summary=summary,
                             steps=steps, extra=extra)


def _parse_err_code(raw: Optional[str]) -> Optional[int]:
    """`<code>,"<text>"` → code；解析不出 → None（队列状态未知）。"""
    if not isinstance(raw, str):
        return None
    head = raw.strip().split(",", 1)[0].strip()
    try:
        return int(float(head))
    except ValueError:
        return None


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def run(
    ctx: Any,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(
            success=False, summary=driver_not_loaded_summary("baseStation"))
    refusal = mock_driver_refusal_summary("baseStation", bs)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    if not hasattr(bs, "_query"):
        return SequenceRunResult(
            success=False,
            summary=(f"baseStation 驱动 {type(bs).__name__} 没有 SCPI 查询通道 "
                     "(_query)"))

    steps: List[SequenceStepResult] = []

    def _step(label: str, success: bool, detail: str,
              raw: Optional[str] = None, started: Optional[float] = None) -> None:
        steps.append(SequenceStepResult(
            label=label, success=success, detail=detail, raw=raw,
            duration_ms=(int((time.monotonic() - started) * 1000)
                         if started is not None else None),
        ))
        log(f"  {'✓' if success else '✗'} {label}: {detail}"
            + (f"  raw={raw!r}" if raw is not None else ""))

    async def _q(cmd: str) -> Optional[str]:
        raw = await _maybe_await(bs._query(cmd))
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    async def _drain(label: str) -> Tuple[Optional[List[str]], bool]:
        """读 SYSTem:ERRor? 到 0 为止（cap 内）。返回 (非零条目列表|None, 是否可判)。"""
        started = time.monotonic()
        drained: List[str] = []
        try:
            for _ in range(_ERR_DRAIN_CAP):
                raw = await _q(_STATE_QUERY_ERR)
                code = _parse_err_code(raw)
                if code is None:
                    _step(label, False,
                          f"SYSTem:ERRor? 读不出错误码 ({raw!r}) —— 队列状态未知",
                          raw, started)
                    return None, False
                if code == 0:
                    return drained, True
                drained.append((raw or "").strip())
        except Exception as e:  # noqa: BLE001
            _step(label, False, f"读错误队列异常 {type(e).__name__}: {e}",
                  None, started)
            return None, False
        # 内审 F2：cap 内未读到 0 = 队列里还有旧错，后续任何错误归属都会
        # 被 stale 残留污染（极端场景会把「查询形被拒」的反向假结论归档）
        # —— 按不可判处理，预排水路径 ABORTED 不发 STATe?，后排水路径 BLOCKER
        _step(label, False,
              f"排水撞上限（{_ERR_DRAIN_CAP} 条仍未见 0）—— 队列未清空，"
              f"归属不可判。已排出: {drained}", None, started)
        return None, False

    profile = _profile_for_driver(bs)
    profile_name = getattr(profile, "PROFILE_NAME", "?")
    query_cmd = getattr(profile, "MEAS_BTHROUGHPUT_STATE_QUERY", None)
    extra: Dict[str, Any] = {
        "profile": profile_name,
        "query_command": query_cmd,
        "state_query_supported": None,   # True/False/None(未判定)
        "bthroughput_state": None,       # 原样 token；不解释、不写回
        "errors": [],
        "residue_clean": None,
    }

    # ── 方言门：推断查询形没定义就拒跑，不猜 ──────────────────────────
    if not query_cmd:
        return _result(
            "ABORTED",
            f"ABORTED: 方言 {profile_name} 未定义 MEAS_BTHROUGHPUT_STATE_QUERY"
            "（BSE 命令树在该方言认不认未经查证，禁盲试）—— STATe? 未发。"
            "先确认 UXM 跑在 LTE_NR_IRAT 上。",
            steps, extra,
        )

    # ── 预排水：stale 错误不许挂到本探针的命令名下 ────────────────────
    pre_errors, pre_decidable = await _drain("预排水错误队列")
    if not pre_decidable:
        return _result(
            "ABORTED",
            "ABORTED: 预排水错误队列不可判（读不出码 / 异常）—— STATe? 未发。",
            steps, extra,
        )
    if pre_errors:
        _step("预排水错误队列", True,
              f"排出 {len(pre_errors)} 条历史残留（已认领为跑前遗留，"
              f"不属于本探针）: {pre_errors}", None, None)

    # ── 唯一的能力查询：STATe?（读到 ON 也不动，绝不写） ──────────────
    started = time.monotonic()
    raw_state: Optional[str] = None
    query_exc: Optional[BaseException] = None
    try:
        raw_state = await _q(query_cmd)
    except Exception as e:  # noqa: BLE001
        query_exc = e
    errors, decidable = await _drain(f"{query_cmd} 后错误队列")
    extra["errors"] = errors or []

    if not decidable:
        _step(query_cmd, False,
              f"错误队列不可判，查询结果无法归属"
              + (f"（查询异常 {type(query_exc).__name__}: {query_exc}）"
                 if query_exc else f"（raw={raw_state!r}）"),
              raw_state, started)
        return _result(
            "BLOCKER",
            "BLOCKER: STATe? 后错误队列不可判，推断查询形成立与否无法定案。",
            steps, extra,
        )

    if errors:
        # 有可归属错误 = 推断查询形被拒 —— 这就是探针要的答案之一。
        extra["state_query_supported"] = False
        _step(query_cmd, True,
              f"推断查询形**被拒**（错误队列: {errors}"
              + (f"; 查询异常 {type(query_exc).__name__}" if query_exc else "")
              + "）—— `[:STATe]?` 在本 Test App 不成立，累积开关现状不可回读。"
              "OFF 写形复验仍待操作员按取证文档人工执行。",
              raw_state, started)
        residue, res_decidable = await _drain("收尾错误队列")
        extra["residue_clean"] = (residue == []) if res_decidable else None
        if extra["residue_clean"] is not True:
            return _result(
                "UNDETERMINED",
                "UNDETERMINED: 查询已判定（被拒），但收尾错误队列有残留 / 读不出。",
                steps, extra,
            )
        return _result(
            "SUCCESS",
            f"SUCCESS: 推断查询形 `{query_cmd}` 被真机拒绝（{errors}）——"
            "缺口定案：查询形不成立，closed/OFF 回读无路，lifecycle 保持 "
            "clear_read_only 正确。",
            steps, extra,
        )

    if query_exc is not None or raw_state is None or not raw_state.strip():
        _step(query_cmd, False,
              "查询无回复且错误队列无可归属错误 —— 无法定案"
              + (f"（{type(query_exc).__name__}: {query_exc}）" if query_exc else ""),
              raw_state, started)
        return _result(
            "BLOCKER",
            "BLOCKER: STATe? 无回复且错误队列干净，推断查询形成立与否无法定案。",
            steps, extra,
        )

    token = raw_state.strip()
    extra["state_query_supported"] = True
    extra["bthroughput_state"] = token
    on_like = token.upper() in {"1", "ON"}
    _step(query_cmd, True,
          f"推断查询形**成立**；BTHRoughput 累积开关现状 = {token!r}"
          + ("（正在累积 —— 本探针不干预，不发 OFF）" if on_like
             else "（未在白名单 {'0','OFF','1','ON'} 内则原样归档，不解释）"
             if token.upper() not in {"0", "OFF"} else "（当前 OFF）"),
          token, started)

    residue, res_decidable = await _drain("收尾错误队列")
    extra["residue_clean"] = (residue == []) if res_decidable else None
    if extra["residue_clean"] is not True:
        return _result(
            "UNDETERMINED",
            "UNDETERMINED: 查询已判定（成立），但收尾错误队列有残留 / 读不出。",
            steps, extra,
        )
    return _result(
        "SUCCESS",
        f"SUCCESS: 推断查询形 `{query_cmd}` 真机成立，现状 = {token!r}；"
        "本探针零写命令。OFF 写形复验按取证文档 §现场复验由操作员执行。",
        steps, extra,
    )
