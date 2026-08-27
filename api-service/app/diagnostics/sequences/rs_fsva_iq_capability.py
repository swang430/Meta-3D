"""R&S FSVA IQ 采集能力探针（`rs_fsva_iq_capability`，P1-70 出发前载体）。

背景：信道验证第一激活批（P1-69 §1，temporal + doppler）的真驱动
`RealRsFsvaDriver.measure_pdp / measure_doppler_spectrum` 走 TRACe:IQ 采集。
现场 FSVA3044 的权威手册 R&S FSV/A3000 I/Q Analyzer User Manual
1178.8536.02─16 §10.3（印刷页 150）明确：I/Q 专属配置只有在 I/Q Analyzer
channel 或 `TRACe:IQ:STATe ON` 快速采集模式下才可用。因此本序列在仪器空闲时
暂时启用快速 I/Q 模式，逐条实测查询形式，并在 finally 中恢复原始 OFF 状态。

**会临时切换 I/Q 模式**（仅允许 STATe ON/OFF），每条命令旁注手册出处：

- `*IDN?`               通用命令（手册 p612 命令清单）—— FSVA/FSV/FSW 身份门
- `TRACe:IQ:STATe?`     现场已实测；ON/OFF 据 1178.8536.02─16 §10.3 p150、p155
- `TRACe:IQ:SRATe?`     p252 载设置形，查询形待真机核验
- `TRACe:IQ:BWIDth?`    p251 明写 "Defines or queries"
- `TRACe:IQ:RLENgth?`   p251 载设置形，查询形待真机核验
- `SYST:ERR?`           SYSTem:ERRor[:NEXT]? p969（每读一条删一条，空队列回
                        `0,"No error"`）—— 每条能力查询后读一轮，结尾再排水一轮

判读约定：能力查询**有回复且错误队列干净** = 该查询形式真机支持（SUPPORTED）；
有回复但错误队列报错（如 -113 Undefined header）= 查询形式被拒（REJECTED，
这是探针要的答案，不算故障）；查询超时但错误队列明确归属到该命令，也记为
REJECTED 并先排空队列再测下一条；无可归属错误的超时 / 异常 / 无回复 = BLOCKER。

四态 `extra["verdict"]`（照 P1-65 序列形态）：SUCCESS（所有查询都可判定，无论
支持与否；REJECTED 计数进 summary）/ BLOCKER（存在无法归属的查询超时 / 异常 /
无回复）/ UNDETERMINED（查询均可判但收尾错误队列有残留 / 读不出）/
ABORTED（身份门未过或初始状态不可判）。
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
from app.hal.rs_fsva import FsvaScpi

metadata = SequenceMetadata(
    name="R&S FSVA IQ 采集能力探针",
    description=(
        "空闲时临时启用 TRACe:IQ 快速采集模式，逐条实测 SRATe?/BWIDth?/RLENgth?"
        "查询形式并立即归属错误队列；最后恢复原始 OFF 状态。仅允许写 STATe ON/OFF，"
        "不改采样参数、不采集数据。P1-70 真驱动的 PDP/Doppler 采集依赖这些能力。"
    ),
    required_categories=["signalAnalyzer"],
    params_schema=[],
    safe_during_test=False,  # 临时切换 I/Q mode 且 drain SYST:ERR?
)

# 身份门：驱动面向 FSVA（现场 FSVA3000）；手册为 FSVA/FSV 双机型；FSW 与 FSVA
# 共核心 SCPI（rs_fsva.py 文件头既有说明）。
_IDN_MODEL_TAGS = ("FSVA", "FSV", "FSW")

# STATe? 在激活前读取并作为 capability 归档；其余命令必须在 I/Q mode 内查询。
# (命令, 手册证据档位) —— evidence="manual" 查询形有手册原文；"inferred" 推断。
_CAPABILITY_QUERIES: Tuple[Tuple[str, str], ...] = (
    (FsvaScpi.IQ_SRATE_QUERY, "inferred"),    # 1178.8536.02-16 p252 载设置形
    (FsvaScpi.IQ_BWIDTH_QUERY, "manual"),     # 同手册 p251 "Defines or queries"
    (FsvaScpi.IQ_RLENGTH_QUERY, "inferred"),  # 同手册 p251 载设置形
)

_ERR_DRAIN_CAP = 50


def _result(verdict: str, summary: str, steps: List[SequenceStepResult],
            extra: Dict[str, Any]) -> SequenceRunResult:
    extra = dict(extra)
    extra["verdict"] = verdict
    return SequenceRunResult(success=(verdict == "SUCCESS"), summary=summary,
                             steps=steps, extra=extra)


def _parse_err_code(raw: Optional[str]) -> Optional[int]:
    """`<code>,"<text>"`（p969）→ code；解析不出 → None（队列状态未知）。"""
    if not isinstance(raw, str):
        return None
    head = raw.strip().split(",", 1)[0].strip()
    try:
        return int(float(head))
    except ValueError:
        return None


class _Recorder:
    def __init__(self, query_fn: Callable[[str], Any], write_fn: Callable[[str], Any],
                 log: Callable[[str], None]) -> None:
        self._query_fn = query_fn
        self._write_fn = write_fn
        self._log = log
        self.steps: List[SequenceStepResult] = []
        self.blockers: List[str] = []

    async def query(self, cmd: str) -> Optional[str]:
        raw = self._query_fn(cmd)
        if hasattr(raw, "__await__"):
            raw = await raw
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    async def write(self, cmd: str) -> None:
        result = self._write_fn(cmd)
        if hasattr(result, "__await__"):
            await result

    def add(self, label: str, success: bool, detail: str,
            raw: Optional[str], started: float) -> None:
        self.steps.append(SequenceStepResult(
            label=label, success=success, detail=detail,
            duration_ms=int((time.monotonic() - started) * 1000), raw=raw,
        ))
        self._log(f"  {'✓' if success else '✗'} {label}: {detail}"
                  + (f"  raw={raw!r}" if raw is not None else ""))

    async def drain_errors(self, label: str) -> Tuple[Optional[List[str]], bool]:
        """读 SYST:ERR? 到 0 为止（cap 内）。返回 (非零条目列表|None, 是否可判)。
        None + False = 读队列本身异常 / 读不出码 —— 状态未知。"""
        started = time.monotonic()
        drained: List[str] = []
        try:
            for _ in range(_ERR_DRAIN_CAP):
                raw = await self.query(FsvaScpi.ERR)
                code = _parse_err_code(raw)
                if code is None:
                    self.add(label, False,
                             f"SYST:ERR? 读不出错误码 ({raw!r}) —— 队列状态未知",
                             raw, started)
                    return None, False
                if code == 0:
                    return drained, True
                drained.append((raw or "").strip())
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"读错误队列异常 {type(e).__name__}: {e}",
                     None, started)
            return None, False
        drained.append(f"...(超过排水上限 {_ERR_DRAIN_CAP} 条未读完)")
        return drained, True


async def run(
    ctx: Any,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    sa = drivers.get("signalAnalyzer")
    if sa is None:
        return SequenceRunResult(success=False,
                                 summary=driver_not_loaded_summary("signalAnalyzer"))
    refusal = mock_driver_refusal_summary("signalAnalyzer", sa)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    query_fn = getattr(sa, "_query", None)
    write_fn = getattr(sa, "_write", None)
    if not callable(query_fn) or not callable(write_fn):
        return SequenceRunResult(
            success=False,
            summary=(f"signalAnalyzer 驱动 {type(sa).__name__} 没有 _query/_write，"
                     "无法受控激活并恢复 I/Q mode"),
        )

    rec = _Recorder(query_fn, write_fn, log)
    extra: Dict[str, Any] = {
        "idn": None,
        "capabilities": {},   # cmd -> {raw, evidence, supported, errors}
        "residue_clean": None,
        "initial_iq_state": None,
        "activated_for_probe": False,
        "restore_confirmed": None,
    }

    # ── 身份门 ──────────────────────────────────────────────────────────
    started = time.monotonic()
    try:
        idn = ((await rec.query("*IDN?")) or "").strip()
    except Exception as e:  # noqa: BLE001
        rec.add("*IDN?", False, f"查询异常 {type(e).__name__}: {e}", None, started)
        return _result("ABORTED",
                       "ABORTED: *IDN? 查询异常，身份未认，能力查询未发",
                       rec.steps, extra)
    extra["idn"] = idn
    ok = any(tag in idn.upper() for tag in _IDN_MODEL_TAGS)
    rec.add("*IDN?", ok, "身份匹配" if ok
            else f"身份不符: IDN={idn!r}, 期望含 {_IDN_MODEL_TAGS} 之一", idn, started)
    if not ok:
        return _result("ABORTED",
                       f"ABORTED: 身份门未过（IDN 不含 {_IDN_MODEL_TAGS} 之一），"
                       f"能力查询未发", rec.steps, extra)

    # ── 读取原始状态；只有明确 OFF 才允许临时激活 ──────────────────────
    state_started = time.monotonic()
    try:
        state_raw = ((await rec.query(FsvaScpi.IQ_STATE_QUERY)) or "").strip()
    except Exception as e:  # noqa: BLE001
        rec.add(FsvaScpi.IQ_STATE_QUERY, False,
                f"查询异常 {type(e).__name__}: {e}", None, state_started)
        return _result("ABORTED", "ABORTED: I/Q 初始状态不可判，未切换模式",
                       rec.steps, extra)
    state_errors, state_decidable = await rec.drain_errors(
        f"{FsvaScpi.IQ_STATE_QUERY} 后错误队列"
    )
    state_token = state_raw.upper()
    if not state_decidable or state_errors or state_token not in {"0", "1", "OFF", "ON"}:
        rec.add(FsvaScpi.IQ_STATE_QUERY, False,
                f"初始状态不可判: raw={state_raw!r}, errors={state_errors}",
                state_raw, state_started)
        return _result("ABORTED", "ABORTED: I/Q 初始状态不可判，未切换模式",
                       rec.steps, extra)

    initially_on = state_token in {"1", "ON"}
    extra["initial_iq_state"] = "ON" if initially_on else "OFF"
    extra["capabilities"][FsvaScpi.IQ_STATE_QUERY] = {
        "raw": state_raw,
        "evidence": "onsite",
        "supported": True,
        "errors": [],
    }
    rec.add(FsvaScpi.IQ_STATE_QUERY, True,
            f"支持；初始 I/Q mode={'ON' if initially_on else 'OFF'}",
            state_raw, state_started)

    # ── 临时激活后逐条能力查询；finally 恢复原始 OFF ───────────────────
    supported: List[str] = [FsvaScpi.IQ_STATE_QUERY]
    rejected: List[str] = []
    activation_attempted = False
    try:
        if not initially_on:
            activation_attempted = True
            started = time.monotonic()
            try:
                await rec.write(FsvaScpi.IQ_STATE_ON)
                extra["activated_for_probe"] = True
                confirmed = ((await rec.query(FsvaScpi.IQ_STATE_QUERY)) or "").strip().upper()
                errors, decidable = await rec.drain_errors("TRACe:IQ:STATe ON 后错误队列")
                activation_ok = decidable and not errors and confirmed in {"1", "ON"}
                rec.add("临时激活 I/Q mode", activation_ok,
                        "已确认 ON" if activation_ok
                        else f"未确认 ON: state={confirmed!r}, errors={errors}",
                        confirmed or None, started)
                if not activation_ok:
                    rec.blockers.append("TRACe:IQ:STATe ON")
            except Exception as e:  # noqa: BLE001
                rec.add("临时激活 I/Q mode", False,
                        f"异常 {type(e).__name__}: {e}", None, started)
                rec.blockers.append("TRACe:IQ:STATe ON")

        if not rec.blockers:
            for cmd, evidence in _CAPABILITY_QUERIES:
                started = time.monotonic()
                entry: Dict[str, Any] = {"raw": None, "evidence": evidence,
                                         "supported": None, "errors": []}
                extra["capabilities"][cmd] = entry
                try:
                    raw = await rec.query(cmd)
                except Exception as e:  # noqa: BLE001
                    # VISA query 超时本身拿不到回复，但仪器通常会把真正原因写进
                    # SYST:ERR?。必须在发送下一条查询前立即归属并排空，避免 -400
                    # 级联污染后续能力项。
                    errors, decidable = await rec.drain_errors(f"{cmd} 异常后错误队列")
                    entry["errors"] = errors or []
                    if decidable and errors:
                        entry["supported"] = False
                        rejected.append(cmd)
                        rec.add(cmd, True,
                                f"查询未回复但错误队列明确拒绝: {errors} "
                                f"({type(e).__name__}: {e})",
                                None, started)
                    else:
                        rec.add(cmd, False,
                                f"查询异常 {type(e).__name__}: {e}; errors={errors}",
                                None, started)
                        rec.blockers.append(cmd)
                        if not decidable:
                            break
                    continue
                if raw is None:
                    errors, decidable = await rec.drain_errors(f"{cmd} 无回复后错误队列")
                    entry["errors"] = errors or []
                    if decidable and errors:
                        entry["supported"] = False
                        rejected.append(cmd)
                        rec.add(cmd, True,
                                f"无回复但错误队列明确拒绝: {errors}", None, started)
                    else:
                        rec.add(cmd, False, f"无回复；errors={errors}", None, started)
                        rec.blockers.append(cmd)
                        if not decidable:
                            break
                    continue
                entry["raw"] = raw
                errors, decidable = await rec.drain_errors(f"{cmd} 后错误队列")
                if not decidable:
                    rec.blockers.append(cmd)
                    entry["supported"] = None
                    break
                entry["errors"] = errors
                if errors:
                    entry["supported"] = False
                    rejected.append(cmd)
                    rec.add(cmd, True,
                            f"查询形式被拒（错误队列: {errors}）——"
                            + ("推断的查询形在真机不成立" if evidence == "inferred"
                               else "手册有据却被拒，字面值已归档"),
                            raw, started)
                else:
                    entry["supported"] = True
                    supported.append(cmd)
                    rec.add(cmd, True,
                            "支持，回复已归档"
                            + ("（推断查询形得到证实）" if evidence == "inferred" else ""),
                            raw, started)
    finally:
        if activation_attempted:
            started = time.monotonic()
            try:
                await rec.write(FsvaScpi.IQ_STATE_OFF)
                confirmed = ((await rec.query(FsvaScpi.IQ_STATE_QUERY)) or "").strip().upper()
                errors, decidable = await rec.drain_errors("TRACe:IQ:STATe OFF 后错误队列")
                restored = decidable and not errors and confirmed in {"0", "OFF"}
                extra["restore_confirmed"] = restored
                rec.add("恢复 I/Q mode", restored,
                        "已确认恢复 OFF" if restored
                        else f"未确认 OFF: state={confirmed!r}, errors={errors}",
                        confirmed or None, started)
                if not restored:
                    rec.blockers.append("TRACe:IQ:STATe OFF restore")
            except Exception as e:  # noqa: BLE001
                extra["restore_confirmed"] = False
                rec.add("恢复 I/Q mode", False,
                        f"异常 {type(e).__name__}: {e}", None, started)
                rec.blockers.append("TRACe:IQ:STATe OFF restore")
        else:
            extra["restore_confirmed"] = True

    # ── 收尾错误队列排水 ────────────────────────────────────────────────
    residue_started = time.monotonic()
    residue, decidable = await rec.drain_errors("收尾错误队列")
    if decidable and residue is not None:
        extra["residue_clean"] = residue == []
        rec.add("收尾错误队列", residue == [],
                "零残留" if residue == [] else f"残留 {len(residue)} 条未认领错误",
                "; ".join(residue) if residue else None, residue_started)
    else:
        extra["residue_clean"] = None

    suffix = (f"；支持 {len(supported)} 条 {supported}，被拒 {len(rejected)} 条 "
              f"{rejected}（被拒 = 查询形式不被真机接受，字面错误已归档，"
              f"驱动侧靠错误队列 fail-loud 兜底）")
    if rec.blockers:
        return _result(
            "BLOCKER",
            f"BLOCKER: {len(rec.blockers)} 条查询超时 / 异常 / 无回复 / 队列不可判："
            f"{rec.blockers}" + suffix,
            rec.steps, extra,
        )
    if extra["residue_clean"] is not True:
        return _result(
            "UNDETERMINED",
            "UNDETERMINED: 能力查询均可判，但收尾错误队列有残留 / 读不出，"
            "见「收尾错误队列」步" + suffix,
            rec.steps, extra,
        )
    return _result(
        "SUCCESS",
        "SUCCESS: 能力查询全部可判，错误队列零残留" + suffix,
        rec.steps, extra,
    )
