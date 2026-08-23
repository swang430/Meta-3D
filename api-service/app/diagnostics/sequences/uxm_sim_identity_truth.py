"""P2-13 现场载体: UE 实测 IMSI vs SIMProfile 声明 IMSI 对账 (P1-65)。

要回答的问题 (roadmap「Blocked on hardware」P2-13): attach 上来的到底是不是
TestCase 选的那张卡。precheck 的 SIM 核对 (`app/services/mimo_ota/executors/precheck.py`
2.4b) 今天只拿得到操作员**手敲**的 IMSI, modem 上报的实测 IMSI 从没被读过 ——
本序列把实测值读出来, 跟声明值并排对账。

命令清单 (本地手册原件 `Instrument_API_Doc/Keysight UXM NR SCPI/UXM5G_SCPI_01_NR_Core.md`,
设计稿 §2):

- `BSE:INFO:NR5G:<cell>:UEReported:IMSI?` —— `UE IMSI`, 01_NR_Core.md:39010-39021,
  **Query only** (手册原文), Type String, Notes `Read only`, First Version v17.08,
  Section `NR UE Info > UE Reported Info > UE Information`。
  ⚠ 该条目**没有标 Application Mode** (邻条 `Request IMEI or IMSI` 的
  `BSE:FUNCtion:NR5G:<cell>:NAS:REQuest[:IMMediate] IMEI` 是 Imm Action、标 `SA`;
  它是"向 UE 发起请求"的动作, **本序列不发**)。IRAT 下可用性手册未说明 —— 发出去、原样记。
- `CELL_STATUS_QUERY` (`BSE:STATus:NR5G:<cell>?`) —— 既有 profile 常量 (P0-2 D1),
  用来解释"回空"是不是因为 UE 根本没 attach。
- `SYSTem:ERRor?` —— 每条命令后读一次。

声明值取数路径 = precheck 同一条: `SIMProfile` 表按 id (或名称) 查 `imsi`。
DiagnosticContext 不带 DB 会话、LabProfile 也不绑 SIM (SIM 绑在 TestCase 上), 所以
本序列从 `params["sim_profile"]` 拿 id / 名称, 自己开一个只读会话 (`_open_db`,
测试可替换)。拿不到 (未给 / 不存在 / 卡无声明 IMSI / DB 故障) → 如实 UNDETERMINED。

**IMSI 是 PII** —— 本序列任何输出 (summary / steps.detail / steps.raw / extra) 只出现
P1-47A 的脱敏形态 (`app/hal/base.py::redact_instrument_exchange_text`, 保留末 4 位),
完整 IMSI 不落 `DiagnosticRun`。`raw` 字段的"原样存"约定在这里让位于 PII 规则:
存的是脱敏副本, 步骤 detail 写明。比对用 `check_sim_identity` (精确比, strip 归一化)。

方言门: 命令根 `BSE:INFO:NR5G:<cell>` 属 Test Application Framework; 5G_NR_Test 方言
下对应形式未查证 → 不发, UNDETERMINED。

四态 `extra["verdict"]`: SUCCESS (两边都有且相等) / BLOCKER (两边都有且不等 —— 插错卡
或声明写错) / UNDETERMINED (UE 未上报 / 无声明值可比) / ABORTED (传输异常)。
只读, 但读的是在网 UE 的身份, 不与正式测试并行 → `safe_during_test=False`。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
from app.diagnostics.sequences.uxm_offset_to_carrier_probe import (
    _is_bse_dialect,
    _validate_cell,
)
from app.diagnostics.sequences.uxm_scpi_compatibility import (
    _parse_err,
    _profile_for_driver,
)
from app.hal.base import redact_instrument_exchange_text, redact_instrument_log_text
from app.services.diagnostic_context import DiagnosticContext
from app.services.mimo_ota.sim_identity_check import check_sim_identity

# 手册 `UE IMSI` 01_NR_Core.md:39014 (Query only)。
_IMSI_TEMPLATE = "BSE:INFO:NR5G:{cell}:UEReported:IMSI?"


metadata = SequenceMetadata(
    name="UXM SIM 身份真值 (P2-13)",
    description=(
        "读 BSE:INFO:NR5G:<cell>:UEReported:IMSI? (UE 实测上报) 与小区状态, 跟 "
        "sim_profile (SIMProfile id 或名称) 的声明 IMSI 对账: 相等=SUCCESS, 不等=BLOCKER "
        "(插错卡 / 声明写错), UE 未上报或无声明值=UNDETERMINED。输出只含脱敏 IMSI "
        "(保留末 4 位)。只读; 只在 LTE_NR_IRAT (BSE:) 方言发命令。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "小区 (留空=方言主小区)", "type": "string", "default": ""},
        {"name": "sim_profile", "label": "SIMProfile id 或名称 (留空=只采集, 不对账)",
         "type": "string", "default": ""},
    ],
    safe_during_test=False,
)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


def _open_db():
    """开一个 DB 会话 (只读用)。测试用 monkeypatch 换成 SQLite 会话。"""
    from app.db.database import SessionLocal

    return SessionLocal()


def _mask(imsi: Optional[str]) -> Optional[str]:
    """P1-47A 脱敏: 保留末 4 位 (复用 HAL 日志脱敏, 不另起一套)。"""
    if imsi is None:
        return None
    s = str(imsi).strip()
    if not s:
        return ""
    return redact_instrument_log_text(s, mask_bare_imsi=True)


def _resolve_declared_imsi(ref: str) -> Dict[str, Any]:
    """按 precheck 同一取数路径找 SIMProfile 的声明 IMSI。

    返回 {"found": bool, "name": str|None, "imsi": str|None, "note": str|None}。
    任何失败都不抛 —— 声明值拿不到是 UNDETERMINED 的一种, 不是序列崩溃。
    """
    from app.models.sim_profile import SIMProfile

    ref = (ref or "").strip()
    if not ref:
        return {"found": False, "name": None, "imsi": None,
                "note": "未给 sim_profile 参数, 无声明值可对账"}
    try:
        db = _open_db()
    except Exception as e:  # noqa: BLE001
        return {"found": False, "name": None, "imsi": None,
                "note": f"打开 DB 会话失败: {type(e).__name__}: {e}"}
    try:
        row = None
        try:
            row = db.query(SIMProfile).filter(SIMProfile.id == UUID(ref)).first()
        except (ValueError, TypeError, AttributeError):
            row = None  # 不是 UUID → 按名称找
        if row is None:
            row = db.query(SIMProfile).filter(SIMProfile.name == ref).first()
        if row is None:
            return {"found": False, "name": None, "imsi": None,
                    "note": f"sim_profile={ref!r} 在 SIMProfile 表里不存在 (按 id 与名称都找过)"}
        if not row.imsi:
            return {"found": True, "name": row.name, "imsi": None,
                    "note": f"SIMProfile {row.name!r} 没有声明 IMSI"}
        return {"found": True, "name": row.name, "imsi": str(row.imsi).strip(), "note": None}
    except Exception as e:  # noqa: BLE001
        return {"found": False, "name": None, "imsi": None,
                "note": f"查 SIMProfile 失败: {type(e).__name__}: {e}"}
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass


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
    extra: Dict[str, Any] = {"profile": profile_name, "cell": None}

    if not _is_bse_dialect(profile):
        extra["verdict"] = "UNDETERMINED"
        return SequenceRunResult(
            success=False, extra=extra,
            summary=(
                f"UNDETERMINED: 当前方言 {profile_name} 的命令根不是 BSE:; "
                f"`BSE:INFO:NR5G:<cell>:UEReported:IMSI?` (01_NR_Core.md:39014) 在 "
                f"{profile_name} 方言下对应形式未查证, 不发 (未探测 ≠ 不支持)。"
                f"现场方言 LTE_NR_IRAT 下重跑。"
            ),
        )

    # ── 小区白名单 (内审 F5): 不合法一条不发 ──
    cell, cell_reject = _validate_cell(
        params.get("cell"), getattr(profile, "PRIMARY_CELL", "CELL1"),
    )
    if cell_reject:
        extra["verdict"] = "UNDETERMINED"
        return SequenceRunResult(
            success=False, extra=extra, summary=f"UNDETERMINED: {cell_reject}",
        )
    extra["cell"] = cell

    err_cmd = getattr(profile, "ERR", "SYSTem:ERRor?")
    status_t = getattr(profile, "CELL_STATUS_QUERY", None)
    if not isinstance(status_t, str):
        extra["verdict"] = "UNDETERMINED"
        return SequenceRunResult(
            success=False, extra=extra,
            summary=f"UNDETERMINED: 方言 {profile_name} 缺 CELL_STATUS_QUERY, 无法先查状态, 不发。",
        )
    status_q = status_t.format(cell=cell)
    imsi_q = _IMSI_TEMPLATE.format(cell=cell)

    steps: List[SequenceStepResult] = []
    readback_errors: Dict[str, str] = {}

    async def _q(cmd: str) -> Optional[str]:
        raw = await _maybe_await(bs._query(cmd))  # noqa: SLF001
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    async def _err_after(label: str, cmd: str) -> Tuple[Optional[int], Optional[str]]:
        raw_e = await _q(err_cmd)
        code, text = _parse_err(raw_e or "")
        clean = code == 0
        if not clean:
            readback_errors[cmd] = raw_e if raw_e is not None else ""
        steps.append(SequenceStepResult(
            label=f"{label} → SYSTem:ERRor?",
            success=clean,
            detail="队列干净" if clean else f"错误: {text or raw_e!r} (原样记录, 不据此下结论)",
            raw=raw_e,
        ))
        return code, raw_e

    def _finish(verdict: str, summary: str, success: bool = False) -> SequenceRunResult:
        extra["verdict"] = verdict
        extra["readback_errors"] = readback_errors
        return SequenceRunResult(
            success=success, steps=steps, extra=extra, summary=summary,
        )

    # ── 1. 小区状态 (解释"回空") ──
    try:
        t0 = time.monotonic()
        raw_status = await _q(status_q)
        steps.append(SequenceStepResult(
            label="小区状态 BSE:STATus?", success=raw_status is not None,
            detail="协议栈真话 (手册 Range OFF|ON|CONNected|IDLE|AGGRegated|ACTivated)",
            raw=raw_status, duration_ms=int((time.monotonic() - t0) * 1000),
        ))
        await _err_after("小区状态", status_q)

        # ── 2. UE 上报 IMSI (raw 存脱敏副本 —— PII) ──
        t0 = time.monotonic()
        raw_imsi = await _q(imsi_q)
        masked_raw = (
            redact_instrument_exchange_text(raw_imsi, command=imsi_q)
            if raw_imsi is not None else None
        )
        steps.append(SequenceStepResult(
            label="UEReported:IMSI? (UE 实测上报)", success=raw_imsi is not None,
            detail=(
                "手册 `UE IMSI` 01_NR_Core.md:39014 (Query only, Read only); "
                "raw 为脱敏副本 (P1-47A, 保留末 4 位), 完整 IMSI 不落库"
            ),
            raw=masked_raw, duration_ms=int((time.monotonic() - t0) * 1000),
        ))
        await _err_after("UEReported:IMSI?", imsi_q)
    except Exception as e:  # noqa: BLE001
        return _finish(
            "ABORTED",
            f"ABORTED: 采集阶段异常 {type(e).__name__}: {e} — 已采集步骤见 steps。",
        )

    reported = (raw_imsi or "").strip().strip('"').strip()
    extra["cell_status"] = raw_status
    extra["reported_imsi_masked"] = _mask(reported) if reported else reported
    log(f"  · 小区状态={raw_status!r} UE IMSI={extra['reported_imsi_masked']!r}")

    # ── 3. 声明值 (precheck 同一取数路径) ──
    declared = _resolve_declared_imsi(params.get("sim_profile") or "")
    extra["sim_profile_name"] = declared["name"]
    extra["declared_imsi_masked"] = _mask(declared["imsi"]) if declared["imsi"] else None
    extra["declared_note"] = declared["note"]
    steps.append(SequenceStepResult(
        label="声明 IMSI (SIMProfile 表)", success=bool(declared["imsi"]),
        detail=(
            f"SIMProfile {declared['name']!r} 声明 IMSI={extra['declared_imsi_masked']!r}"
            if declared["imsi"] else (declared["note"] or "无声明值")
        ),
    ))

    err_txt = (
        f" | 回读报错 {len(readback_errors)} 条 (见 readback_errors; 原样记录, 不据此下结论)"
        if readback_errors else ""
    )

    # ── 4. 判定 ──
    if not reported:
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED: UE 未上报 IMSI (回复 {raw_imsi!r}), 小区状态={raw_status!r} — "
            f"UE 未 attach / 未上报时读不到身份, 无法对账; 声明侧: "
            f"{declared['note'] or ('SIMProfile ' + repr(declared['name']) + ' 已找到')}。{err_txt}",
        )
    if not declared["imsi"]:
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED: 已采到 UE IMSI={extra['reported_imsi_masked']!r} "
            f"(小区状态={raw_status!r}), 但无声明值可对账: {declared['note']}。"
            f"{'' if (params.get('sim_profile') or '').strip() else ' 传 sim_profile 参数 (SIMProfile id 或名称) 后重跑。'}"
            f"{err_txt}",
        )

    extra["consistent"] = bool(check_sim_identity(
        declared_imsi=declared["imsi"], attached_imsi=reported,
    ).consistent)
    if extra["consistent"]:
        return _finish(
            "SUCCESS",
            f"SUCCESS: UE 实测 IMSI={extra['reported_imsi_masked']!r} 与 SIMProfile "
            f"{declared['name']!r} 声明 IMSI={extra['declared_imsi_masked']!r} 一致 "
            f"(小区状态={raw_status!r}){err_txt}",
            success=True,
        )
    return _finish(
        "BLOCKER",
        f"BLOCKER: UE 实测 IMSI={extra['reported_imsi_masked']!r} ≠ SIMProfile "
        f"{declared['name']!r} 声明 IMSI={extra['declared_imsi_masked']!r} —— 插错卡或声明写错 "
        f"(小区状态={raw_status!r}){err_txt}",
    )
