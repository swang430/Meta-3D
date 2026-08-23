"""F64 各口输出电平窗口核对（`propsim_f64_output_level_windows`，P1-65 NEW-1）。

故障形态（2026-08-07 现场实测）：口 1 的 `OUTPut:LEVel:AMPlitude:LIMits? 1` 回
`-166.60,-51.61`，而我们下发的绝对电平是 `-50.00` —— 落在窗外。手册 §20.4.5.5 原文
"Level cannot be set outside the limits"，仪器不会报得很响，测试照跑、电平不对。
现场没有载体能在正式测试前把"每个口当前值是否在它自己的窗口里"亮出来。

本序列**只读**，每条命令旁注手册章节（Propsim User Reference Rev 10.2）：

- `*IDN?`                                  §20.4.1.5  身份门（PROPSIM / F8800 任一命中）
- `SYSTem:INFO?`                           §20.4.2.4  身份兜底 + 第 2 字段 `<Number of channels>`
- `DIAG:SIMU:STATE?`                       §20.4.3.14 前置：§20.4 开篇原文 "Most PROPSIM ATE
                                                       commands are only available when emulation
                                                       has been opened" → CLOSED 不盲发逐口查询
- `OUTPut:LEVel:AMPlitude:LIMits? <n>`     §20.4.5.5  `<lower limit>,<higher limit>` dBm
- `OUTPut:LEVel:AMPlitude:CH? <n>`         §20.4.5.4  当前平均输出电平 dBm（CH 后直接 ?，不带 GET）
- `SYSTem:ERRor?`                          §20.4.2.1  结尾读到 `0,"No error"` 为止（上限 100）

**口集来源**（`extra["port_source"]`）：① `outputs` 参数；② 驱动加载仿真时已回读的
物理输出口 `_active_output_ports`（`GROUP:OUTPUTS:GET?` 的结果，本序列不重发）；
③ 退到 `SYSTem:INFO?` 的通道数 1..N —— 那是**整机衰落通道数**（F64 = 64），不是输出口数
（驱动 `_parse_topology` 注释明说两者单位不同），只当兜底并在 extra 标明，不当真值。

四态 `extra["verdict"]`：SUCCESS（全部在窗内）/ UNDETERMINED（任一口解析不出、无已加载
仿真、或错误队列有残留）/ BLOCKER（任一口当前值落在窗外，summary 点名口号与窗口）/
ABORTED（身份不符、参数非法、三连超时）。措辞：未探测 ≠ 不支持。
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
from app.diagnostics.sequences.propsim_f64_health import (
    _IDN_MODEL_TAGS,
    _maybe_await,
    _parse_err,
)
from app.diagnostics.sequences.propsim_f64_state_machine import classify_state
from app.hal.channel_emulator import F64_STATE_QUERY
from app.hal.propsim_f64 import parse_f64_sys_info
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="PROPSIM F64 各口输出电平窗口核对",
    description=(
        "只读：先 DIAG:SIMU:STATE? 确认仿真已加载，再逐口读 "
        "OUTPut:LEVel:AMPlitude:LIMits? 与 CH?，任一口当前电平落在它自己的 "
        "<lower>,<higher> 窗外即 BLOCKER 并点名口号与窗口；结尾读 SYSTem:ERRor? 零残留。"
        "口集默认取驱动已回读的物理输出口，可用 outputs 参数指定。"
    ),
    required_categories=["channelEmulator"],
    params_schema=[
        {
            "name": "outputs",
            "label": "要核对的输出口号（逗号分隔；留空 = 驱动已回读的物理输出口）",
            "type": "string",
            "default": "",
        },
    ],
    safe_during_test=False,  # 结尾 drain SYSTem:ERRor?，会吃掉在测任务要看的错误
)

_ERR_QUERY = "SYSTem:ERRor?"          # §20.4.2.1
_INFO_QUERY = "SYSTem:INFO?"          # §20.4.2.4
_LIMITS_QUERY = "OUTPut:LEVel:AMPlitude:LIMits? {n}"   # §20.4.5.5
_LEVEL_QUERY = "OUTPut:LEVel:AMPlitude:CH? {n}"        # §20.4.5.4
_RESIDUE_CAP = 100
_CONSECUTIVE_TIMEOUT_ABORT = 3


def _result(verdict: str, summary: str, steps: List[SequenceStepResult],
            extra: Dict[str, Any]) -> SequenceRunResult:
    extra = dict(extra)
    extra["verdict"] = verdict
    return SequenceRunResult(success=(verdict == "SUCCESS"), summary=summary,
                             steps=steps, extra=extra)


def _parse_outputs_param(raw: Any) -> Tuple[Optional[List[int]], Optional[str]]:
    """`outputs` 参数 → 正整数列表（去重保序）；空 = None；非法 → (None, 原因)。"""
    text = str(raw or "").strip()
    if not text:
        return None, None
    ports: List[int] = []
    for tok in text.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if not tok.isdigit() or int(tok) <= 0:
            return None, f"outputs 参数含非法口号 {tok!r}（只接受正整数，逗号分隔）"
        n = int(tok)
        if n not in ports:
            ports.append(n)
    if not ports:
        return None, "outputs 参数解析后为空"
    return ports, None


def _parse_pair(raw: Optional[str]) -> Optional[Tuple[float, float]]:
    try:
        parts = (raw or "").strip().split(",")
        return float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return None


def _parse_float(raw: Optional[str]) -> Optional[float]:
    try:
        return float((raw or "").strip().strip('"'))
    except ValueError:
        return None


class _Recorder:
    def __init__(self, query_fn: Callable[[str], Any], log: Callable[[str], None]) -> None:
        self._query_fn = query_fn
        self._log = log
        self.steps: List[SequenceStepResult] = []

    async def query(self, cmd: str) -> Optional[str]:
        raw = await _maybe_await(self._query_fn(cmd))
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    def add(self, label: str, success: bool, detail: str,
            raw: Optional[str], started: float) -> None:
        self.steps.append(SequenceStepResult(
            label=label, success=success, detail=detail,
            duration_ms=int((time.monotonic() - started) * 1000), raw=raw,
        ))
        self._log(f"  {'✓' if success else '✗'} {label}: {detail}"
                  + (f"  raw={raw!r}" if raw is not None else ""))

    async def residue(self) -> Optional[bool]:
        """结尾 SYSTem:ERRor? 读到 `0,"No error"` 为止（FIFO，上限 100）。
        返回 True 干净 / False 有残留或读不出 / None 没读（调用方在卡死时跳过）。"""
        started = time.monotonic()
        drained: List[str] = []
        try:
            for _ in range(_RESIDUE_CAP):
                raw = await self.query(_ERR_QUERY)
                code, _text = _parse_err(raw or "")
                if code == 0:
                    break
                if code is None:
                    self.add("收尾错误队列", False,
                             f"SYSTem:ERRor? 读不出错误码 ({raw!r}) — 队列状态未知, 不能当干净",
                             raw, started)
                    return False
                drained.append((raw or "").strip())
        except Exception as e:  # noqa: BLE001
            self.add("收尾错误队列", False, f"读队列异常 {type(e).__name__}: {e}", None, started)
            return False
        if drained:
            self.add("收尾错误队列", False, f"残留 {len(drained)} 条未认领错误",
                     "; ".join(drained), started)
            return False
        self.add("收尾错误队列", True, "零残留", None, started)
        return True


async def _identity_gate(rec: _Recorder) -> Tuple[bool, str, Optional[str]]:
    """`*IDN?` 含 PROPSIM/F8800 即过；否则 `SYSTem:INFO?` 兜底（同 propsim_f64_health）。
    返回 (通过?, idn, sys_info_raw 或 None)。"""
    started = time.monotonic()
    try:
        idn = (await rec.query("*IDN?")) or ""
    except Exception as e:  # noqa: BLE001
        rec.add("*IDN?", False, f"查询异常 {type(e).__name__}: {e}", None, started)
        return False, "", None
    idn = idn.strip()
    if any(tag in idn.upper() for tag in _IDN_MODEL_TAGS):
        rec.add("*IDN?", True, "身份匹配", idn, started)
        return True, idn, None
    started = time.monotonic()
    try:
        info = (await rec.query(_INFO_QUERY)) or ""
    except Exception as e:  # noqa: BLE001
        rec.add(_INFO_QUERY, False, f"查询异常 {type(e).__name__}: {e}", None, started)
        return False, idn, None
    info = info.strip()
    ok = any(tag in info.upper() for tag in _IDN_MODEL_TAGS)
    rec.add(_INFO_QUERY, ok, "身份匹配（SYSTem:INFO? 兜底）" if ok
            else f"身份不符: IDN={idn!r}, INFO={info!r}, 期望含 {_IDN_MODEL_TAGS} 之一",
            info, started)
    return ok, idn, info


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    ce = drivers.get("channelEmulator")
    if ce is None:
        return SequenceRunResult(success=False,
                                 summary=driver_not_loaded_summary("channelEmulator"))
    refusal = mock_driver_refusal_summary("channelEmulator", ce)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    query_fn = getattr(ce, "_query", None)
    if not callable(query_fn):
        return SequenceRunResult(
            success=False,
            summary=f"channelEmulator 驱动 {type(ce).__name__} 没有 _query，无法发 SCPI 查询",
        )

    rec = _Recorder(query_fn, log)
    extra: Dict[str, Any] = {
        "idn": None, "state": None, "port_source": None, "ports": {},
        "out_of_window": [], "unknown_ports": [], "residue_clean": None,
    }

    # 参数先于任何 SCPI：非法就不碰仪器。
    param_ports, param_err = _parse_outputs_param(params.get("outputs"))
    if param_err:
        return _result("ABORTED", f"ABORTED: {param_err}；未发任何 SCPI", rec.steps, extra)

    ok, idn, info_raw = await _identity_gate(rec)
    extra["idn"] = idn
    if not ok:
        return _result("ABORTED", "ABORTED: 身份门未过（IDN / SYSTem:INFO? 都不含 PROPSIM / F8800），"
                       "未发逐口查询", rec.steps, extra)

    # 前置：§20.4 开篇 —— 多数 ATE 命令仅在仿真打开后可用；先查状态再决定发不发。
    started = time.monotonic()
    try:
        state_raw = await rec.query(F64_STATE_QUERY)
    except Exception as e:  # noqa: BLE001
        rec.add(F64_STATE_QUERY, False, f"查询异常 {type(e).__name__}: {e}", None, started)
        state_raw, state, note = None, None, "查询异常"
    else:
        state, note = classify_state(state_raw)
        rec.add(F64_STATE_QUERY, state is not None, state or note, state_raw, started)
    extra["state"] = state
    if state is None or state == "CLOSED":
        why = "无已加载仿真（STATE?=CLOSED）" if state == "CLOSED" else f"状态读不到（{note}）"
        extra["residue_clean"] = await rec.residue()
        return _result(
            "UNDETERMINED",
            f"UNDETERMINED: {why} —— §20.4 开篇“多数 ATE 命令仅在仿真打开后可用”，"
            f"逐口 LIMits?/CH? 未发。先加载场景包再跑本序列。",
            rec.steps, extra,
        )

    # 口集
    if param_ports is not None:
        ports, source = param_ports, "param"
    else:
        active = getattr(ce, "_active_output_ports", None)
        if isinstance(active, (list, tuple)) and active and all(
            isinstance(p, int) and p > 0 for p in active
        ):
            ports, source = list(active), "driver_active_output_ports"
        else:
            if info_raw is None:
                started = time.monotonic()
                try:
                    info_raw = await rec.query(_INFO_QUERY)
                except Exception as e:  # noqa: BLE001
                    rec.add(_INFO_QUERY, False, f"查询异常 {type(e).__name__}: {e}", None, started)
                    info_raw = None
                else:
                    rec.add(_INFO_QUERY, True, "读取通道数（兜底口集）", info_raw, started)
            n = parse_f64_sys_info(info_raw).channel_count if info_raw else None
            if not n or n <= 0:
                extra["residue_clean"] = await rec.residue()
                return _result(
                    "UNDETERMINED",
                    "UNDETERMINED: 口集无法确定 —— 无 outputs 参数、驱动未回读物理输出口、"
                    "SYSTem:INFO? 也解析不出通道数；逐口查询未发。",
                    rec.steps, extra,
                )
            ports, source = list(range(1, n + 1)), "syst_info_channel_count"
            log(f"  · 口集退到 SYSTem:INFO? 通道数 1..{n}（整机衰落通道数，非输出口数，只当兜底）")
    extra["port_source"] = source

    # 逐口
    port_table: Dict[str, Dict[str, Any]] = {}
    out_of_window: List[int] = []
    unknown: List[int] = []
    consecutive_timeouts = 0
    aborted = False
    for n in ports:
        entry: Dict[str, Any] = {"lower": None, "higher": None, "current": None, "in_window": None}
        port_table[str(n)] = entry
        timed_out_here = False
        for cmd, kind in ((_LIMITS_QUERY.format(n=n), "limits"), (_LEVEL_QUERY.format(n=n), "level")):
            started = time.monotonic()
            try:
                raw = await rec.query(cmd)
            except Exception as e:  # noqa: BLE001
                rec.add(cmd, False, f"查询异常 {type(e).__name__}: {e}", None, started)
                consecutive_timeouts += 1
                timed_out_here = True
                if consecutive_timeouts >= _CONSECUTIVE_TIMEOUT_ABORT:
                    aborted = True
                    break
                continue
            consecutive_timeouts = 0
            if kind == "limits":
                pair = _parse_pair(raw)
                if pair is None:
                    rec.add(cmd, False, f"回复解析不出 <lower>,<higher>: {raw!r}", raw, started)
                else:
                    entry["lower"], entry["higher"] = pair
                    rec.add(cmd, True, f"窗口 {pair[0]},{pair[1]} dBm", raw, started)
            else:
                val = _parse_float(raw)
                if val is None:
                    rec.add(cmd, False, f"回复解析不出数字: {raw!r}", raw, started)
                else:
                    entry["current"] = val
                    rec.add(cmd, True, f"当前 {val} dBm", raw, started)
        if aborted:
            unknown.append(n)
            break
        if entry["lower"] is None or entry["current"] is None or timed_out_here:
            unknown.append(n)
            continue
        inside = entry["lower"] <= entry["current"] <= entry["higher"]
        entry["in_window"] = inside
        if not inside:
            out_of_window.append(n)
            log(f"  ✗ 口 {n}: 当前 {entry['current']} dBm 落在窗口 "
                f"{entry['lower']},{entry['higher']} 之外")

    extra["ports"] = port_table
    extra["out_of_window"] = out_of_window
    extra["unknown_ports"] = unknown

    if aborted:
        # 通道已卡死，再读错误队列只会再吃一轮超时；residue_clean 留 None = 没读。
        return _result(
            "ABORTED",
            f"ABORTED: 连续 {_CONSECUTIVE_TIMEOUT_ABORT} 次查询超时（SCPI 通道疑似卡死），"
            f"剩余口未查、错误队列未读；已记录 {len(port_table)} 口。重连 F64 驱动后重跑。",
            rec.steps, extra,
        )

    extra["residue_clean"] = await rec.residue()

    if out_of_window:
        parts = []
        for n in out_of_window:
            e = port_table[str(n)]
            parts.append(f"口 {n}: 当前 {e['current']} dBm, 窗口 {e['lower']},{e['higher']}")
        return _result(
            "BLOCKER",
            f"BLOCKER: {len(out_of_window)} 口当前电平落在窗外 —— " + "; ".join(parts)
            + "。手册 §20.4.5.5: Level cannot be set outside the limits。",
            rec.steps, extra,
        )
    if unknown:
        return _result(
            "UNDETERMINED",
            f"UNDETERMINED: {len(unknown)} 口回复解析不出或无回复（口 {unknown}），"
            f"其余 {len(ports) - len(unknown)} 口在窗内；原始回复见各步 raw。",
            rec.steps, extra,
        )
    if extra["residue_clean"] is not True:
        return _result(
            "UNDETERMINED",
            f"UNDETERMINED: {len(ports)} 口都在窗内，但收尾错误队列有残留 / 读不出 —— "
            "不能当干净，见「收尾错误队列」步的 raw。",
            rec.steps, extra,
        )
    return _result(
        "SUCCESS",
        f"SUCCESS: {len(ports)} 口当前电平均在各自窗口内（口集来源 {source}），错误队列零残留。",
        rec.steps, extra,
    )
