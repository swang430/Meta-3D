"""UXM ON 态同值 BAND 写入诊断剧本（P1-46）。

本序列只回答一个现场问题：LTE_NR_IRAT 小区已连接时，把当前 band 原值写回
同一个配置项，会不会令协议状态掉线。它不尝试证明命令在 IRAT 下获得厂商手册
授权：现有手册条目的 Application Mode 只写 NSA/SA，同值副作用也未说明；
``SYSTem:ERRor?`` 在 IRAT 下同样只有现场/生产使用事实，没有匹配范围的手册佐证。
因此即使所有步骤执行成功、错误队列为 0、回读一致且连接未掉，正式 verdict 仍是
``unverified``，``SequenceRunResult.success`` 必须保持 False。

Duplex 不在本轮范围：``UxmLteNrIratProfile.CELL_DUPLEX`` 当前为 ``None``，生产
驱动没有这条写路径，禁止为了“覆盖完整”临时造一条命令。
"""
from __future__ import annotations

import asyncio
import math
import re
import time
from typing import Any, Callable, Dict, List, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
from app.diagnostics.sequences.uxm_scpi_compatibility import (
    _parse_err,
    _profile_for_driver,
)
from app.services.diagnostic_context import DiagnosticContext


# 本动作问的是“已连接的 DUT 会不会被同值写踢掉”，所以只接受手册的
# CONNected 长/短返回；AGGRegated/ACTivated 是否等同该前提没有本轮证据，不扩。
_CONNECTED_PROTOCOL_STATES = frozenset({"CONN", "CONNECTED"})

# 只容纳事件循环/传输调度的轻微抖动；不是给 ERR 长盲区开的后门。
_SCHEDULING_TOLERANCE_S = 0.05

# 只用于运行前清理遗留错误；到上限仍非 0 就拒绝，不做无界 drain。
_MAX_INITIAL_ERR_DRAIN = 5

_COMMAND_EVIDENCE = {
    "classification": "unverified",
    "provenance": ["production-driver", "onsite-observed"],
    "manual_application_modes": ["NSA", "SA"],
    "manual_nr_band_type": "Band",
    "manual_nr_band_range": "not_specified",
    "accepted_band_shape_basis": "production-driver",
    "target_application_mode": "LTE_NR_IRAT",
    "scope": "manual_scope_mismatch",
    "same_value_side_effect": "manual_not_specified",
    "error_queue_scope": "unverified_in_LTE_NR_IRAT",
}


metadata = SequenceMetadata(
    name="UXM ON 态同值 BAND 写入探针 (P1-46)",
    description=(
        "只在 LTE_NR_IRAT 小区开关为 ON 且协议状态已连接时，把当前 BAND 原值"
        "写回；写后读取当前方言 ERR、BAND，并在有界窗口内观察协议状态，保留 raw。"
        "厂商手册只明确 NSA/SA，未确认覆盖 LTE_NR_IRAT，因此本序列只产出 "
        "unverified 诊断证据，永不正式判绿；"
        "duplex 因生产 profile 未定义而不覆盖。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "小区 (留空=方言主小区)",
         "type": "string", "default": ""},
        {"name": "stability_window_s", "label": "连接稳定观察窗口 (秒)",
         "type": "number", "default": 5},
        {"name": "poll_interval_s", "label": "状态采样间隔 (秒)",
         "type": "number", "default": 1},
    ],
    safe_during_test=False,
)


def _evidence_allows_formal_green(*, classification: str, scope: str) -> bool:
    """只有手册确认且应用范围精确匹配 IRAT 的证据才有资格正式判绿。"""
    return classification == "confirmed" and scope == "LTE_NR_IRAT"


def _parse_band_token(raw: Optional[str]) -> Optional[str]:
    """只接受生产驱动使用的 N 前缀形态；三位上限只是注入防护。"""
    token = (raw or "").strip().strip('"').upper()
    return token if re.fullmatch(r"N[1-9]\d{0,2}", token) else None


def _stability_offsets(params: Dict[str, Any]) -> tuple[Optional[List[float]], str]:
    """校验窗口参数并生成固定采样时刻；不依赖墙钟 while 循环。"""
    window = params.get("stability_window_s", 5)
    interval = params.get("poll_interval_s", 1)
    if (
        isinstance(window, bool) or isinstance(interval, bool)
        or not isinstance(window, (int, float))
        or not isinstance(interval, (int, float))
    ):
        return None, "窗口和间隔必须是有限数字（不能是布尔值）"
    window = float(window)
    interval = float(interval)
    if not math.isfinite(window) or not math.isfinite(interval):
        return None, "窗口和间隔必须是有限数字"
    if not 1 <= window <= 30:
        return None, "stability_window_s 必须在 1..30 秒"
    if not 0.1 <= interval <= 5:
        return None, "poll_interval_s 必须在 0.1..5 秒"
    if interval > window:
        return None, "poll_interval_s 不能大于 stability_window_s"

    full_intervals = math.floor(window / interval)
    offsets = [i * interval for i in range(full_intervals + 1)]
    if window - offsets[-1] > 1e-9:
        offsets.append(window)
    if len(offsets) > 61:
        return None, "稳定窗口最多允许 61 个固定样本，请增大采样间隔"
    return offsets, ""


async def _maybe_await(value: Any) -> Any:
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
    if not callable(getattr(bs, "_query", None)) or not callable(
        getattr(bs, "_write", None)
    ):
        return SequenceRunResult(
            success=False,
            summary=(f"baseStation 驱动 {type(bs).__name__} 没有 SCPI 通道 "
                     "(_query/_write)"),
        )

    profile = _profile_for_driver(bs)
    profile_name = getattr(profile, "PROFILE_NAME", "?")
    if profile_name != "LTE_NR_IRAT":
        return SequenceRunResult(
            success=False,
            summary=(f"只允许 LTE_NR_IRAT；当前方言={profile_name!r}，"
                     "未发送任何 SCPI。"),
            extra={"profile": profile_name, "formal_verdict": "unverified"},
        )

    band_t = getattr(profile, "CELL_BAND", None)
    switch_q_t = getattr(profile, "CELL_STATE_QUERY", None)
    status_q_t = getattr(profile, "CELL_STATUS_QUERY", None)
    err_q = getattr(profile, "ERR", None)
    if not all(isinstance(item, str) and item for item in (
        band_t, switch_q_t, status_q_t, err_q,
    )):
        return SequenceRunResult(
            success=False,
            summary=("LTE_NR_IRAT profile 缺 CELL_BAND/CELL_STATE_QUERY/"
                     "CELL_STATUS_QUERY/ERR，未发送任何 SCPI。"),
            extra={"profile": profile_name, "formal_verdict": "unverified"},
        )

    stability_offsets, params_error = _stability_offsets(params)
    if stability_offsets is None:
        return SequenceRunResult(
            success=False,
            summary=f"稳定观察参数非法：{params_error}；未发送任何 SCPI。",
            extra={"profile": profile_name, "formal_verdict": "unverified"},
        )

    cell = str(params.get("cell") or "").strip() or getattr(
        profile, "PRIMARY_CELL", "CELL1"
    )
    cell_match = re.fullmatch(r"CELL(\d+)", cell, flags=re.IGNORECASE)
    if not cell_match or not 1 <= int(cell_match.group(1)) <= 14:
        return SequenceRunResult(
            success=False,
            summary=f"非法 cell={cell!r}，未发送任何 SCPI。",
            extra={"profile": profile_name, "formal_verdict": "unverified"},
        )
    cell = cell.upper()

    switch_q = switch_q_t.format(cell=cell)
    band_header = band_t.format(cell=cell)
    band_q = band_header + "?"
    status_q = status_q_t.format(cell=cell)
    steps: List[SequenceStepResult] = []
    observations: Dict[str, Optional[str]] = {}
    common_extra: Dict[str, Any] = {
        "profile": profile_name,
        "cell": cell,
        "formal_verdict": "unverified",
        "command_evidence": dict(_COMMAND_EVIDENCE),
        "coverage": {
            "band": {"covered": False},
            "duplex": {
                "covered": False,
                "reason": (
                    "UxmLteNrIratProfile.CELL_DUPLEX=None，生产驱动未使用；"
                    "本轮禁止新增或猜测 DUPLEX 命令。"
                ),
            },
        },
        "observations": observations,
        "initial_error_queue": {
            "max_reads": _MAX_INITIAL_ERR_DRAIN,
            "raw": [],
            "cleared": False,
        },
        "prewrite_error_baseline": None,
        "observation_window": {
            "mode": "bounded_stability",
            "window_s": float(params.get("stability_window_s", 5)),
            "poll_interval_s": float(params.get("poll_interval_s", 1)),
            "planned_offsets_s": list(stability_offsets),
            "planned_samples": len(stability_offsets),
            "completed_samples": 0,
            "samples": [],
            "stable": False,
            "disconnection_observed": False,
        },
    }

    async def _query(label: str, cmd: str) -> Optional[str]:
        started = time.monotonic()
        try:
            value = await _maybe_await(bs._query(cmd))  # noqa: SLF001
            raw = value if isinstance(value, str) else (
                None if value is None else str(value)
            )
            ok = raw is not None and bool(raw.strip())
            steps.append(SequenceStepResult(
                label=label,
                success=ok,
                detail=f"已保留原始回复；命令证据={_COMMAND_EVIDENCE['classification']}",
                raw=raw,
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            return raw
        except Exception as exc:  # noqa: BLE001
            steps.append(SequenceStepResult(
                label=label,
                success=False,
                detail=f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            return None

    # ── E0：任何业务前置查询前，有界排空遗留错误 ──
    initial_err_raw: List[Optional[str]] = []
    initial_cleared = False
    for read_index in range(_MAX_INITIAL_ERR_DRAIN):
        raw_initial_err = await _query(
            f"运行前：错误队列排空 {read_index + 1}/{_MAX_INITIAL_ERR_DRAIN}",
            err_q,
        )
        initial_err_raw.append(raw_initial_err)
        initial_code, initial_text = _parse_err(raw_initial_err or "")
        steps[-1].success = initial_code is not None
        steps[-1].detail = (
            f"错误码={initial_code!r}，文本={initial_text!r}；"
            "ERR 在 IRAT 下仍是 unverified 诊断证据。"
        )
        if initial_code is None:
            break
        if initial_code == 0:
            initial_cleared = True
            break
    common_extra["initial_error_queue"] = {
        "max_reads": _MAX_INITIAL_ERR_DRAIN,
        "raw": initial_err_raw,
        "cleared": initial_cleared,
    }
    if not initial_cleared:
        return SequenceRunResult(
            success=False,
            steps=steps,
            extra=common_extra,
            summary=(
                f"运行前错误队列在 {_MAX_INITIAL_ERR_DRAIN} 次有界读取内未归零"
                "或回复不可解析；拒绝执行任何前置查询和 BAND 写动作。"
            ),
        )

    # 先拿齐三项前提观测，再决定是否动作；不能根据其中一项提前写。
    raw_switch = await _query("动作前：小区开关回读", switch_q)
    raw_band = await _query("动作前：BAND 原值回读", band_q)
    raw_status = await _query("动作前：协议连接状态回读", status_q)
    observations.update({
        "before_switch": raw_switch,
        "before_band": raw_band,
        "before_protocol_status": raw_status,
    })

    # ── E1：三条前置查询后的单次写前基线 ──
    # 必须第一条就是 0；非 0 不继续 drain，因为它正是“前置查询产生错误”的归属证据。
    raw_prewrite_err = await _query("写前：错误队列归属基线", err_q)
    prewrite_code, prewrite_text = _parse_err(raw_prewrite_err or "")
    prewrite_clean = prewrite_code == 0
    steps[-1].success = prewrite_clean
    steps[-1].detail = (
        f"错误码={prewrite_code!r}，文本={prewrite_text!r}；"
        "必须首读为 0 才能把下一条错误归给 BAND 写动作。"
    )
    common_extra["prewrite_error_baseline"] = {
        "raw": raw_prewrite_err,
        "code": prewrite_code,
        "clean": prewrite_clean,
    }
    observations["prewrite_error_baseline"] = raw_prewrite_err
    if not prewrite_clean:
        return SequenceRunResult(
            success=False,
            steps=steps,
            extra=common_extra,
            summary=(
                f"写前 ERR 基线首读不是 0（raw={raw_prewrite_err!r}）；"
                "拒绝 BAND 写动作，避免把前置查询错误误归因给写命令。"
            ),
        )

    switch_on = (raw_switch or "").strip().upper() == "1"
    protocol_state = (raw_status or "").strip().strip('"').upper()
    connected = protocol_state in _CONNECTED_PROTOCOL_STATES
    band_value = _parse_band_token(raw_band)

    if not switch_on or not connected or not band_value:
        reasons = []
        if not switch_on:
            reasons.append(f"小区开关={raw_switch!r}（需 '1'）")
        if not connected:
            reasons.append(f"协议状态={raw_status!r}（需连接类状态）")
        if not band_value:
            reasons.append(
                f"BAND 原值不是生产路径使用的 N 前缀 token: {raw_band!r}"
            )
        return SequenceRunResult(
            success=False,
            steps=steps,
            extra=common_extra,
            summary=("前提不成立，未执行同值写：" + "；".join(reasons)
                     + "。已保留动作前三项 raw 诊断观测。"),
        )

    write_cmd = f"{band_header} {band_value}"
    started = time.monotonic()
    try:
        await _maybe_await(bs._write(write_cmd))  # noqa: SLF001
        write_completed_at = time.monotonic()
        common_extra["write_completed_at"] = write_completed_at
        steps.append(SequenceStepResult(
            label="动作：写回完全相同 BAND",
            success=True,
            detail=(f"已写回动作前原值 {band_value!r}；仅表示剧本已发出，"
                    "不表示命令获手册确认或正式通过。"),
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        steps.append(SequenceStepResult(
            label="动作：写回完全相同 BAND",
            success=False,
            detail=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
        return SequenceRunResult(
            success=False,
            steps=steps,
            extra=common_extra,
            summary="同值 BAND 写动作抛异常；未取得写后观测，正式 verdict=unverified。",
        )

    # 每个写动作后立即读当前 profile.ERR；这里故意不硬编码命令拼写。
    raw_err = await _query("动作后：错误队列原始回复", err_q)
    err_code, err_text = _parse_err(raw_err or "")
    if steps:
        err_step = steps[-1]
        err_step.success = err_code == 0
        err_step.detail = (
            f"错误码={err_code!r}，文本={err_text!r}；ERR 在 IRAT 下证据仍为 "
            "unverified，0 不能令正式 verdict 变绿。"
        )
    # 固定 offsets 决定采样次数，绝不靠墙钟 while；第一个样本是写后即时读，
    # 但 ERR 查询是动作后的硬约束，所以首样本实际时刻会包含 ERR 耗时。每个
    # 目标 offset 都减掉从写完成起已经过去的真实时间，绝不把 ERR 耗时当 0。
    # 任一查询失败或非 CONN 立即停止。
    stability_samples: List[Dict[str, Any]] = []
    for index, offset in enumerate(stability_offsets):
        elapsed_before = max(0.0, time.monotonic() - write_completed_at)
        delay = max(0.0, offset - elapsed_before)
        if delay:
            await asyncio.sleep(delay)
        raw_sample = await _query(
            f"动作后：连接稳定观察 {index + 1}/{len(stability_offsets)}",
            status_q,
        )
        actual_elapsed = max(0.0, time.monotonic() - write_completed_at)
        query_ok = raw_sample is not None and bool(raw_sample.strip())
        token = (raw_sample or "").strip().strip('"').upper()
        sample_connected = query_ok and token in _CONNECTED_PROTOCOL_STATES
        sample = {
            "sample_index": index + 1,
            "planned_offset_s": offset,
            "actual_elapsed_s": actual_elapsed,
            "raw": raw_sample,
            "query_ok": query_ok,
            "connected": sample_connected,
        }
        stability_samples.append(sample)
        # _query 只判断“有回复”；本步骤还必须反映连接语义。
        steps[-1].success = sample_connected
        steps[-1].detail = (
            f"offset={offset:g}s；状态 token={token!r}；"
            + ("保持 CONN" if sample_connected else
               "查询失败或不再是 CONN，停止稳定观察")
        )
        if not sample_connected:
            break

    # BAND 回读放在完整/提前终止的稳定观察之后，避免它占用首状态采样前的盲区。
    raw_band_after = await _query("动作后：BAND 回读", band_q)
    raw_status_after = stability_samples[0]["raw"] if stability_samples else None
    observations.update({
        "after_error_queue": raw_err,
        "after_band": raw_band_after,
        "after_protocol_status": raw_status_after,
        "stability_status_raw": [sample["raw"] for sample in stability_samples],
    })

    band_unchanged = (
        (raw_band_after or "").strip().strip('"') == band_value
    )
    actual_observation_elapsed = (
        stability_samples[-1]["actual_elapsed_s"] if stability_samples else 0.0
    )
    actual_times = [sample["actual_elapsed_s"] for sample in stability_samples]
    actual_gaps = (
        [actual_times[0]]
        + [later - earlier for earlier, later in zip(actual_times, actual_times[1:])]
        if actual_times else []
    )
    max_gap = max(actual_gaps, default=0.0)
    gap_limit = float(params.get("poll_interval_s", 1)) + _SCHEDULING_TOLERANCE_S
    blind_window_exceeded = any(
        gap > gap_limit + 1e-9 for gap in actual_gaps
    )
    window_elapsed = (
        actual_observation_elapsed + 1e-9
        >= float(params.get("stability_window_s", 5))
    )
    stability_complete = (
        len(stability_samples) == len(stability_offsets)
        and window_elapsed
        and not blind_window_exceeded
        and all(sample["query_ok"] and sample["connected"]
                for sample in stability_samples)
    )
    disconnection_observed = any(
        sample["query_ok"] and not sample["connected"]
        for sample in stability_samples
    )
    window_extra = common_extra["observation_window"]
    window_extra.update({
        "completed_samples": len(stability_samples),
        "samples": stability_samples,
        "actual_elapsed_s": actual_observation_elapsed,
        "actual_gaps_s": actual_gaps,
        "max_gap_s": max_gap,
        "gap_limit_s": gap_limit,
        "scheduling_tolerance_s": _SCHEDULING_TOLERANCE_S,
        "blind_window_exceeded": blind_window_exceeded,
        "window_elapsed": window_elapsed,
        "stable": stability_complete,
        "disconnection_observed": disconnection_observed,
        "limitation": (
            "动作后按硬约束先查询 ERR，ERR 往返期间无法观测协议状态；"
            "首个状态样本 actual_elapsed_s 已如实包含该盲区。P1-41 后续负责"
            "进一步缩短/止血该窗口。相邻采样只容许固定 0.05s 调度抖动，"
            "超限不能靠后续瞬时补采抵消。"
        ),
    })
    remained_connected = stability_complete
    execution_ok = (
        err_code == 0 and band_unchanged and stability_complete
        and all(step.success for step in steps)
    )
    # coverage 表示“完整执行并观察完稳定窗口”，不是“曾发出过写命令”。
    common_extra["coverage"]["band"]["covered"] = execution_ok
    common_extra["execution"] = {
        "completed": execution_ok,
        "error_code": err_code,
        "band_unchanged": band_unchanged,
        "remained_connected": remained_connected,
    }

    formal_green = execution_ok and _evidence_allows_formal_green(
        classification=_COMMAND_EVIDENCE["classification"],
        scope=_COMMAND_EVIDENCE["scope"],
    )
    # 当前证据常量必然令 formal_green=False；保留显式计算是为了让变异测试能守住
    # 政策边界，而不是把 SequenceRunResult.success 写成与证据无关的恒 False。
    common_extra["formal_verdict"] = "confirmed" if formal_green else "unverified"
    log(
        "  · BAND 同值写剧本%s；稳定观察 %d/%d 样本。正式 verdict=%s"
        "（手册未确认覆盖 IRAT）。"
        % (
            "执行完成" if execution_ok else "存在异常/不一致",
            len(stability_samples),
            len(stability_offsets),
            common_extra["formal_verdict"],
        )
    )
    return SequenceRunResult(
        success=formal_green,
        steps=steps,
        extra=common_extra,
        summary=(
            f"同值 BAND 剧本{'执行完成' if execution_ok else '未完整通过'}："
            f"错误码={err_code!r}，BAND 回读{'一致' if band_unchanged else '不一致'}，"
            f"稳定观察={len(stability_samples)}/{len(stability_offsets)} 样本，"
            f"协议状态{'全程保持连接' if remained_connected else '未确认全程连接'}。"
            "由于厂商手册 Application Mode 只明确 NSA/SA、未确认覆盖 IRAT，"
            "且同值副作用未说明，LTE_NR_IRAT 正式 "
            "verdict=unverified，不能用于 P0-5 判绿。"
        ),
    )
