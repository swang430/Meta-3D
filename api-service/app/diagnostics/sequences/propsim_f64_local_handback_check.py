"""F64 面板 Local 交还的两段式人工确认（`propsim_f64_local_handback_check`，P1-65 NEW-2）。

**手册事实**（Propsim User Reference Rev 10.2 §20.1 原文）：
"When you open a remote connection to PROPSIM and issue an ATE command, PROPSIM goes
automatically into remote mode. In remote mode, the background of PROPSIM GUI shows the text
“Remote mode”, … and the Local Mode button in the top right corner button is activated (turns
blue). … To return to local mode, click the Local Mode button in the top right corner of the GUI."
⚠ 按钮**亮蓝 / 被激活是 Remote 态**的标志（内审 F4 纠正：初版 label 写成"按钮可点 = 已回
Local"，方向反了）。给操作员的判据只留手册有据的两条：Remote mode 水印消失、按钮不再亮蓝。
—— 没有任何 SCPI 能切回或查询 Local / Remote（§20.4 指令集无此类命令；NotebookLM
2026-08-23 核对：这是手册**无记载**，不是推断出的"支持"或"不支持"）。ATE AN 全文也没有
"socket 关闭即回 Local"。驱动 `release_to_local_control` 做的只是关 socket、
停后台轮询；仪器面板到底回没回 Local，**只有人眼能看**。

所以本序列不能用 SCPI 判定这件事，只做**证据记录器**，两段式：

- `phase=release`：`*IDN?`（§20.4.1.5）身份门 + 收尾 `SYSTem:ERRor?`（§20.4.2.1），然后在
  summary 里给操作员明确指令。**不自己调 `release_to_local_control`** —— 租约 runner 在序列
  结束时会做；序列自己调等于把交接做两遍，结果无法归因。verdict 恒 UNDETERMINED（等待人工确认）。
- `phase=confirm`：**不发任何 SCPI**（面板观察与 SCPI 无关；而且下一次取租约本身就会再发
  ATE 命令把仪器重新置 Remote —— 所以观察必须在**开始 confirm 之前**做完）。把操作员在面板
  看到的原文 + 是否已回 Local 记进 extra（`evidence_kind: "onsite-observed"`），verdict 按布尔
  SUCCESS / BLOCKER，summary 写明"来源 = 人工面板观察，非 SCPI 证据"。缺观察原文或缺布尔 →
  UNDETERMINED 并说明缺什么。

⚠ GUI 对 boolean 参数不给默认时会填 false（`SequenceRunnerPanel` 的初始化），所以
`operator_confirmed_local` 在 GUI 路径上永远"有值"；真正守住"操作员看过了"的是
`operator_observation` 必填 —— 没有观察原文就不收布尔。
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
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="PROPSIM F64 面板 Local 交还人工确认",
    description=(
        "两段式证据记录器（手册 §20.1：回 Local 只有 GUI 右上角按钮，无 SCPI 可切回或查询）。"
        "phase=release：*IDN? 身份门后给操作员指令，租约释放后到前面板看 Local Mode 按钮 / "
        "Remote mode 水印；phase=confirm：不发任何 SCPI，把操作员的面板观察原文与是否已回 "
        "Local 记为 onsite-observed 证据。"
    ),
    required_categories=["channelEmulator"],
    params_schema=[
        {
            "name": "phase",
            "label": "阶段：release（释放前登记）/ confirm（记回面板观察）",
            "type": "string",
            "default": "release",
        },
        {
            "name": "operator_observation",
            "label": "confirm 必填：操作员在 F64 前面板看到的原文（按钮状态 / 水印是否消失）",
            "type": "string",
            "default": "",
        },
        {
            "name": "operator_confirmed_local",
            "label": "confirm 必填：面板已回到 Local（背景 Remote mode 水印消失、右上角 Local Mode 按钮不再亮蓝）",
            "type": "boolean",
            "default": False,
        },
    ],
    safe_during_test=False,
)

_ERR_QUERY = "SYSTem:ERRor?"   # §20.4.2.1
_INFO_QUERY = "SYSTem:INFO?"   # §20.4.2.4（仅身份兜底）
_RESIDUE_CAP = 100
_PHASES = ("release", "confirm")

_RELEASE_INSTRUCTIONS = (
    "UNDETERMINED（等待人工确认）：本序列结束、租约释放（驱动关闭 ATE socket）后，"
    "到 F64 前面板看背景是否仍显示 Remote mode 水印 / 右上角 Local Mode 按钮是否仍亮蓝"
    "（手册 §20.1 原文：Remote 态下该按钮 is activated (turns blue) —— 按钮亮蓝是 Remote 的标志，"
    "不是已回 Local）；回 Local 只能点 GUI 的 Local Mode 按钮，没有 SCPI 能切回或查询。"
    "看完后用 phase=confirm 再跑一次，把观察原文填进 operator_observation、"
    "结论填进 operator_confirmed_local（⚠ 先看面板再开始 confirm —— 取租约本身会再发 ATE 命令，"
    "仪器会重新进 Remote）。"
)


def _result(verdict: str, summary: str, steps: List[SequenceStepResult],
            extra: Dict[str, Any]) -> SequenceRunResult:
    extra = dict(extra)
    extra["verdict"] = verdict
    return SequenceRunResult(success=(verdict == "SUCCESS"), summary=summary,
                             steps=steps, extra=extra)


def _as_bool(value: Any) -> Optional[bool]:
    """bool 原样；API 调用方可能传字符串 "true"/"false"；其余 = 缺。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes"):
            return True
        if v in ("false", "0", "no"):
            return False
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


async def _identity_gate(rec: _Recorder) -> Tuple[bool, str]:
    started = time.monotonic()
    try:
        idn = (await rec.query("*IDN?")) or ""
    except Exception as e:  # noqa: BLE001
        rec.add("*IDN?", False, f"查询异常 {type(e).__name__}: {e}", None, started)
        return False, ""
    idn = idn.strip()
    if any(tag in idn.upper() for tag in _IDN_MODEL_TAGS):
        rec.add("*IDN?", True, "身份匹配", idn, started)
        return True, idn
    started = time.monotonic()
    try:
        info = (await rec.query(_INFO_QUERY)) or ""
    except Exception as e:  # noqa: BLE001
        rec.add(_INFO_QUERY, False, f"查询异常 {type(e).__name__}: {e}", None, started)
        return False, idn
    info = info.strip()
    ok = any(tag in info.upper() for tag in _IDN_MODEL_TAGS)
    rec.add(_INFO_QUERY, ok, "身份匹配（SYSTem:INFO? 兜底）" if ok
            else f"身份不符: IDN={idn!r}, INFO={info!r}, 期望含 {_IDN_MODEL_TAGS} 之一",
            info, started)
    return ok, idn


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

    phase = str(params.get("phase") or "release").strip().lower()
    extra: Dict[str, Any] = {"phase": phase}
    if phase not in _PHASES:
        return _result("ABORTED", f"ABORTED: phase={phase!r} 非法，只能是 release / confirm；未发任何 SCPI",
                       [], extra)

    if phase == "confirm":
        # 零 SCPI：面板观察与 SCPI 无关。
        observation = str(params.get("operator_observation") or "").strip()
        confirmed = _as_bool(params.get("operator_confirmed_local"))
        missing: List[str] = []
        if not observation:
            missing.append("operator_observation")
        if confirmed is None:
            missing.append("operator_confirmed_local")
        extra.update({
            "evidence_kind": "onsite-observed",
            "operator_observation": observation or None,
            "operator_confirmed_local": confirmed,
            "missing": missing,
            "scpi_sent": False,
        })
        if missing:
            return _result(
                "UNDETERMINED",
                f"UNDETERMINED: confirm 段缺 {missing} —— 面板观察原文与是否已回 Local 都必须由"
                f"操作员填写（来源 = 人工面板观察，非 SCPI 证据）；本段未发任何 SCPI。",
                [], extra,
            )
        step = SequenceStepResult(
            label="操作员面板观察",
            success=bool(confirmed),
            detail=f"已回 Local = {confirmed}；观察原文：{observation}",
            duration_ms=0, raw=None,
        )
        log(f"  {'✓' if confirmed else '✗'} 操作员面板观察: {step.detail}")
        if confirmed:
            return _result(
                "SUCCESS",
                f"SUCCESS: 操作员确认 F64 面板已回 Local —— 观察原文「{observation}」"
                "（来源 = 人工面板观察，非 SCPI 证据；手册 §20.1 无 SCPI 可查询此状态）。",
                [step], extra,
            )
        return _result(
            "BLOCKER",
            f"BLOCKER: 操作员确认 F64 面板**未**回 Local —— 观察原文「{observation}」"
            "（来源 = 人工面板观察，非 SCPI 证据）。租约释放后仪器仍在 Remote，面板不可操作；"
            "按手册 §20.1 需在 GUI 右上角点 Local Mode 按钮。",
            [step], extra,
        )

    # phase == release
    query_fn = getattr(ce, "_query", None)
    if not callable(query_fn):
        return _result("ABORTED", f"ABORTED: channelEmulator 驱动 {type(ce).__name__} 没有 _query，"
                       "无法做身份门", [], extra)
    rec = _Recorder(query_fn, log)
    ok, idn = await _identity_gate(rec)
    extra["idn"] = idn
    if not ok:
        return _result("ABORTED", "ABORTED: 身份门未过（IDN / SYSTem:INFO? 都不含 PROPSIM / F8800）",
                       rec.steps, extra)
    extra["residue_clean"] = await rec.residue()
    extra["awaiting"] = "operator_panel_observation"
    extra["instructions"] = _RELEASE_INSTRUCTIONS
    extra["scpi_sent"] = True
    return _result("UNDETERMINED", _RELEASE_INSTRUCTIONS, rec.steps, extra)
