"""R&S FSVA IQ 采集能力探针（`rs_fsva_iq_capability`，P1-70 出发前载体）。

背景：信道验证第一激活批（P1-69 §1，temporal + doppler）的真驱动
`RealRsFsvaDriver.measure_pdp / measure_doppler_spectrum` 走 TRACe:IQ 采集
（手册 R&S FSVA/FSV Operating Manual 1176.7510.02─13，TRACe:IQ Subsystem
p894-907）。其中三条**查询形式**手册只载设置形（`STATe?` / `SRATe?` /
`RLENgth?`），驱动按 SCPI 标准派生并靠错误队列 fail-loud —— 本序列在出发前
把这几条查询形式对真机逐条实测：通不通、返回什么字面值、错误队列报什么。

**只读**（禁发任何设置命令），每条命令旁注手册出处：

- `*IDN?`               通用命令（手册 p612 命令清单）—— FSVA/FSV/FSW 身份门
- `TRACe:IQ:STATe?`     ⚠ 推断：p895 只载设置形（ON|OFF，*RST: OFF），查询形系
                        SCPI 标准派生（该条未标 setting-only）—— 本序列就是来验它
- `TRACe:IQ:SRATe?`     ⚠ 推断：p906 只载设置形（*RST: 32 MHz），同上
- `TRACe:IQ:BWIDth?`    p896 例原文 "TRAC:IQ:BWID?"（查询形有据）
- `TRACe:IQ:RLENgth?`   ⚠ 推断：p903 只载设置形（*RST: 691），同上
- `SYST:ERR?`           SYSTem:ERRor[:NEXT]? p969（每读一条删一条，空队列回
                        `0,"No error"`）—— 每条能力查询后读一轮，结尾再排水一轮

判读约定：能力查询**有回复且错误队列干净** = 该查询形式真机支持（SUPPORTED）；
有回复但错误队列报错（如 -113 Undefined header）= 查询形式被拒（REJECTED，
这是探针要的答案，不算故障）；超时 / 异常 / 无回复 = BLOCKER。

四态 `extra["verdict"]`（照 P1-65 序列形态）：SUCCESS（所有查询有回复，无论
支持与否；REJECTED 计数进 summary）/ BLOCKER（任一查询超时 / 异常 / 无回复）/
UNDETERMINED（查询都有回复但收尾错误队列有残留 / 读不出）/ ABORTED（身份门未过）。
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
        "只读：逐条实测 TRACe:IQ 子系统查询形式（STATe?/SRATe?/BWIDth?/RLENgth?）"
        "在真机上的支持情况与字面回复 —— 其中 STATe?/SRATe?/RLENgth? 手册只载"
        "设置形、查询形系 SCPI 标准推断，P1-70 真驱动的 PDP/Doppler 采集依赖它们。"
        "每条查询后读一轮 SYST:ERR?，结尾排水零残留。禁发任何设置命令。"
    ),
    required_categories=["signalAnalyzer"],
    params_schema=[],
    safe_during_test=False,  # 结尾 drain SYST:ERR?，会清掉别人排队的错误
)

# 身份门：驱动面向 FSVA（现场 FSVA3000）；手册为 FSVA/FSV 双机型；FSW 与 FSVA
# 共核心 SCPI（rs_fsva.py 文件头既有说明）。
_IDN_MODEL_TAGS = ("FSVA", "FSV", "FSW")

# (命令, 手册证据档位) —— evidence="manual" 查询形有手册原文例；"inferred" 推断。
_CAPABILITY_QUERIES: Tuple[Tuple[str, str], ...] = (
    (FsvaScpi.IQ_STATE_QUERY, "inferred"),    # p895 只载设置形
    (FsvaScpi.IQ_SRATE_QUERY, "inferred"),    # p906 只载设置形
    (FsvaScpi.IQ_BWIDTH_QUERY, "manual"),     # p896 例 "TRAC:IQ:BWID?"
    (FsvaScpi.IQ_RLENGTH_QUERY, "inferred"),  # p903 只载设置形
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
    def __init__(self, query_fn: Callable[[str], Any], log: Callable[[str], None]) -> None:
        self._query_fn = query_fn
        self._log = log
        self.steps: List[SequenceStepResult] = []
        self.blockers: List[str] = []

    async def query(self, cmd: str) -> Optional[str]:
        raw = self._query_fn(cmd)
        if hasattr(raw, "__await__"):
            raw = await raw
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

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
    if not callable(query_fn):
        return SequenceRunResult(
            success=False,
            summary=f"signalAnalyzer 驱动 {type(sa).__name__} 没有 _query，无法发 SCPI 查询",
        )

    rec = _Recorder(query_fn, log)
    extra: Dict[str, Any] = {
        "idn": None,
        "capabilities": {},   # cmd -> {raw, evidence, supported, errors}
        "residue_clean": None,
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

    # ── 逐条能力查询（只读；每条后读一轮错误队列归属到该条） ────────────
    supported: List[str] = []
    rejected: List[str] = []
    for cmd, evidence in _CAPABILITY_QUERIES:
        started = time.monotonic()
        entry: Dict[str, Any] = {"raw": None, "evidence": evidence,
                                 "supported": None, "errors": []}
        extra["capabilities"][cmd] = entry
        try:
            raw = await rec.query(cmd)
        except Exception as e:  # noqa: BLE001
            rec.add(cmd, False, f"查询异常 {type(e).__name__}: {e}", None, started)
            rec.blockers.append(cmd)
            continue
        if raw is None:
            rec.add(cmd, False, "无回复（驱动返回 None）", None, started)
            rec.blockers.append(cmd)
            continue
        entry["raw"] = raw
        errors, decidable = await rec.drain_errors(f"{cmd} 后错误队列")
        if not decidable:
            rec.blockers.append(cmd)
            entry["supported"] = None
            continue
        entry["errors"] = errors
        if errors:
            # 有回复但队列报错 = 该查询形式被真机拒绝 —— 这是探针要的答案，
            # 不算故障。措辞：查询形式被拒 ≠ 子系统不存在。
            entry["supported"] = False
            rejected.append(cmd)
            rec.add(cmd, True,
                    f"查询形式被拒（错误队列: {errors}）——"
                    + ("推断的查询形在真机不成立" if evidence == "inferred"
                       else "手册有例却被拒，异常，字面值已归档"),
                    raw, started)
        else:
            entry["supported"] = True
            supported.append(cmd)
            rec.add(cmd, True,
                    "支持，回复已归档" + ("（推断查询形得到证实）" if evidence == "inferred" else ""),
                    raw, started)

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
            "UNDETERMINED: 查询都有回复，但收尾错误队列有残留 / 读不出，"
            "见「收尾错误队列」步" + suffix,
            rec.steps, extra,
        )
    return _result(
        "SUCCESS",
        "SUCCESS: 能力查询全部有回复，错误队列零残留" + suffix,
        rec.steps, extra,
    )
