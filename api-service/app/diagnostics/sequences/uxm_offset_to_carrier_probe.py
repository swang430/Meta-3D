"""NEW-3 现场载体: UXM NR DL OffsetToCarrier 真值探针 (P1-65)。

要回答的问题 (roadmap「Blocked on hardware」NEW-3): 现场 attach 不上时, UXM 的
`OffsetToCarrier` 是不是还停在出厂默认 0、需不需要按 EMQuest 基线下发 102。
本序列**默认只读**, 把四个事实一次采齐并跟基线并排放进 extra, 由操作员看
attach 结果决定要不要下发; 下发是显式确认 + 先查小区状态的剧本, 写后立即回读。

命令清单 (全部出自本地手册原件 `Instrument_API_Doc/Keysight UXM NR SCPI/`,
设计稿 docs/plans/2026-08-23-p1-65-blocker-carrier-sequences-design.md §2):

- `BSE:CONFig:NR5G:<cell>:DL:OTCarrier` —— `NR Configure OffsetToCarrier DL`,
  01_NR_Core.md:2254-2266。Type Integer, Range `0 .. 2199`, Notes
  "number PRBs from PointA to first PRB in Bandwidth", Application Mode `NSA | SA`。
  ⚠ 查询形式 `...:OTCarrier?` 是**推断**: 条目无 `No query` 标记且为 Integer 设置项,
  手册未单列查询形式 (NotebookLM 2026-08-23 亦标明为推断)。固件若回 -113,
  如实记进 `readback_errors`, **不**据此写"不支持"。
- `BSE:CONFig:NR5G:<cell>:DL:POINta` —— `NR DL PointA`, 01_NR_Core.md:2244-2253,
  Integer `0.. 3279165`, Application Mode `NSA | SA`。查询形式同为推断。
  生产 profile 已有同一条 (`UxmLteNrIratProfile.CELL_DL_POINTA`, 2026-08-07 现场
  手工拼写探针回读成功), 优先复用 profile 常量。
- `CELL_DL_ARFCN` / `CELL_STATE_QUERY` / `CELL_STATUS_QUERY` —— 既有 profile 常量,
  手册出处见 `app/hal/uxm_command_profiles.py` 各行注释。
- `SYSTem:ERRor?` —— 每条命令后读一次。

**IRAT 下可用性手册未说明**: 以上两条新命令标 `NSA | SA`, 现场方言是 LTE_NR_IRAT;
`SYSTem:APPLication` 的 Range 里 `NSA` 与 `LTE_NR_IRAT` 并列, 标 `NSA | SA` 的命令在
IRAT 下可不可用 —— 手册没写 (CLAUDE.md「必查 NotebookLM」一节 P1-32 铁证)。
所以本序列只做一件事: 发出去, 把回复和错误队列**原样记下来**; 未探测 ≠ 不支持,
手册未说明 ≠ 支持。

方言门: 两条新命令的根是 `BSE:CONFig:NR5G:<cell>` (Test Application Framework,
小区 CELL1..CELL14)。5G_NR_Test 方言用无前缀 `CONFig:NR5G:CELL0` 根, 对应的
OTCarrier / POINta 命令形式**未经手册证实** → 不发, UNDETERMINED。

写路径安全 (CLAUDE.md 诊断序列约束「先查状态再决定发不发」):
- 只在 `offset_to_carrier` 给了值 **且** `confirm_write=True` 时考虑写;
- 手册 Range 0..2199 在本地校验, 越界一条都不发;
- **只有小区 OFF 才写** —— 手册 `Apply Configured Changes` 条目原文 (06_General.md:248):
  "any changes made while a cell is off will be automatically applied when that cell
  is turned On"; ON 态写进的是缓存、要 APPLY 才生效 (P0-2 R4 实证), 本序列**不发 APPLY**
  (留给操作员 / TestCase), 所以 ON 态一律拒绝写并说明;
- 开关回声 (`ACTive:STATe?`) 与协议栈状态 (`BSE:STATus?`) **两者都说 OFF** 才算 OFF,
  任一不是就当状态不明、不写;
- 写后立即回读 `OTCarrier?` 对账 + 读错误队列; 回读 == 下发值且两次错误队列都干净
  → SUCCESS, 否则 BLOCKER。

四态 `extra["verdict"]` (口径同 P1-58): SUCCESS (写后对账成立) / UNDETERMINED (只读
已采集, 或写未发生) / BLOCKER (写后对账不成立或队列有错) / ABORTED (传输异常)。
会改配置 (虽只在 OFF 态), `safe_during_test=False`。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
# 复用不复制: 错误码解析与方言解析跟兄弟序列同源, 免得判据漂移。
from app.diagnostics.sequences.uxm_scpi_compatibility import (
    _parse_err,
    _profile_for_driver,
)
from app.hal.nr_band_baselines import _load as _load_baselines
from app.hal.nr_band_baselines import get_band_baseline
from app.services.diagnostic_context import DiagnosticContext

# 手册 `NR Configure OffsetToCarrier DL` Range (01_NR_Core.md:2262)。
_OTC_MIN, _OTC_MAX = 0, 2199
# 手册条目 SCPI 形式 (01_NR_Core.md:2258 / :2244); 仅在 BSE 方言下使用。
_OTC_TEMPLATE = "BSE:CONFig:NR5G:{cell}:DL:OTCarrier"
_POINTA_TEMPLATE = "BSE:CONFig:NR5G:{cell}:DL:POINta"


metadata = SequenceMetadata(
    name="UXM OffsetToCarrier 真值探针 (NEW-3)",
    description=(
        "默认只读: 并排采集小区开关/状态、DL ARFCN、DL PointA、DL OffsetToCarrier, "
        "并把 nr_band_baselines.json 里当前 band 的基线 (n78: offset_to_carrier=102) "
        "作为建议值放进 extra, 不下发。给了 offset_to_carrier 且 confirm_write=True "
        "时, 只在小区 OFF 态写一次, 写后立即回读对账 + 读错误队列; 不发 APPLY。"
        "只在 LTE_NR_IRAT (BSE:) 方言发命令; 其它方言命令形式未查证, 不发。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "小区 (留空=方言主小区)", "type": "string", "default": ""},
        {"name": "band", "label": "band (留空=按 DL ARFCN 匹配基线表)",
         "type": "string", "default": ""},
        {"name": "offset_to_carrier",
         "label": "要下发的 OffsetToCarrier (留空=只读; 手册 Range 0..2199)",
         "type": "string", "default": ""},
        {"name": "confirm_write", "label": "确认下发 (只在小区 OFF 态才会写)",
         "type": "boolean", "default": False},
    ],
    safe_during_test=False,
)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


def _is_bse_dialect(profile: Any) -> bool:
    """本片新命令的根是 `BSE:CONFig:NR5G:<cell>`; 以 profile 里 DL ARFCN 命令的根判方言。

    不用 PROFILE_NAME 字符串匹配 —— 命令根才是"发出去长什么样"的真值。
    """
    arfcn_t = getattr(profile, "CELL_DL_ARFCN", None)
    return isinstance(arfcn_t, str) and arfcn_t.upper().startswith("BSE:")


def _parse_offset_param(value: Any) -> Tuple[Optional[int], Optional[str]]:
    """解析 offset_to_carrier 参数。返回 (int 或 None, 拒绝原因或 None)。

    形态空间: None / "" (= 只读) / int / 整数字符串 / 浮点 / 非数字 / 越界。
    手册 Range 0..2199 在本地守, 越界一条都不发到仪器。
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"offset_to_carrier={value!r} 不是整数"
    if isinstance(value, int):
        n = value
    else:
        s = str(value).strip()
        if not s:
            return None, None
        try:
            n = int(s)
        except ValueError:
            return None, f"offset_to_carrier={value!r} 不是整数 (手册 Type Integer)"
    if not (_OTC_MIN <= n <= _OTC_MAX):
        return None, (
            f"offset_to_carrier={n} 超出手册 Range {_OTC_MIN}..{_OTC_MAX} "
            f"(01_NR_Core.md:2262), 本地拒绝, 未发到仪器"
        )
    return n, None


def _baseline_for(band_param: str, dl_arfcn_raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """基线建议值: band 参数优先; 留空则按 DL ARFCN 精确匹配基线表的 dl_arfcn。

    不发 SCPI (BAND 查询不在设计稿 §2 清单里); 匹配不到就 None, 如实披露。
    """
    band = (band_param or "").strip()
    if band:
        row = get_band_baseline(band)
        if row is None:
            return None
        return {"band": band.upper(), "source": "param", **row}
    try:
        arfcn = int(float((dl_arfcn_raw or "").strip().strip('"')))
    except ValueError:
        return None
    for name, row in _load_baselines().items():
        if row.get("dl_arfcn") == arfcn:
            return {"band": name, "source": "arfcn_match", **row}
    return None


def _to_int(raw: Optional[str]) -> Optional[int]:
    try:
        return int(float((raw or "").strip().strip('"')))
    except ValueError:
        return None


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
    if not hasattr(bs, "_query") or not hasattr(bs, "_write"):
        return SequenceRunResult(
            success=False,
            summary=f"baseStation 驱动 {type(bs).__name__} 没有 SCPI 通道 (_query/_write)",
        )

    profile = _profile_for_driver(bs)
    profile_name = getattr(profile, "PROFILE_NAME", "?")
    cell = (params.get("cell") or "").strip() or getattr(profile, "PRIMARY_CELL", "CELL1")
    extra: Dict[str, Any] = {"profile": profile_name, "cell": cell}

    # ── 方言门: 新命令只在 BSE 根方言发; 其它方言命令形式未查证, 一条不发 ──
    if not _is_bse_dialect(profile):
        extra["verdict"] = "UNDETERMINED"
        return SequenceRunResult(
            success=False,
            extra=extra,
            summary=(
                f"UNDETERMINED: 当前方言 {profile_name} 的命令根不是 BSE:, 而本序列的 "
                f"OTCarrier / POINta 只有 `BSE:CONFig:NR5G:<cell>:DL:...` 形式有手册依据 "
                f"(01_NR_Core.md:2254/:2244); {profile_name} 方言下对应命令形式未查证, "
                f"不发 (未探测 ≠ 不支持)。现场方言 LTE_NR_IRAT 下重跑。"
            ),
        )

    err_cmd = getattr(profile, "ERR", "SYSTem:ERRor?")
    switch_t = getattr(profile, "CELL_STATE_QUERY", None)
    status_t = getattr(profile, "CELL_STATUS_QUERY", None)
    arfcn_t = getattr(profile, "CELL_DL_ARFCN", None)
    if not all(isinstance(x, str) for x in (switch_t, status_t, arfcn_t)):
        extra["verdict"] = "UNDETERMINED"
        return SequenceRunResult(
            success=False, extra=extra,
            summary=(
                f"UNDETERMINED: 方言 {profile_name} 缺 CELL_STATE_QUERY / CELL_STATUS_QUERY / "
                f"CELL_DL_ARFCN 之一, 无法先查状态, 不发。"
            ),
        )
    pointa_t = getattr(profile, "CELL_DL_POINTA", None)
    if not isinstance(pointa_t, str):
        pointa_t = _POINTA_TEMPLATE
    switch_q = switch_t.format(cell=cell)
    status_q = status_t.format(cell=cell)
    arfcn_q = arfcn_t.format(cell=cell) + "?"
    pointa_q = pointa_t.format(cell=cell) + "?"
    otc_header = _OTC_TEMPLATE.format(cell=cell)
    otc_q = otc_header + "?"

    steps: List[SequenceStepResult] = []
    readback_errors: Dict[str, str] = {}

    async def _q(cmd: str) -> Optional[str]:
        raw = await _maybe_await(bs._query(cmd))  # noqa: SLF001
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    async def _w(cmd: str) -> None:
        await _maybe_await(bs._write(cmd))  # noqa: SLF001

    async def _err_after(label: str, cmd: str) -> Tuple[Optional[int], Optional[str]]:
        """每条命令后读一次错误队列; 非 0 记进 readback_errors (原样)。"""
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

    async def _read(label: str, cmd: str, note: str) -> Optional[str]:
        t0 = time.monotonic()
        raw = await _q(cmd)
        steps.append(SequenceStepResult(
            label=label, success=raw is not None, detail=note, raw=raw,
            duration_ms=int((time.monotonic() - t0) * 1000),
        ))
        log(f"  · {label}: {raw!r}")
        await _err_after(label, cmd)
        return raw

    def _finish(verdict: str, summary: str, success: bool = False) -> SequenceRunResult:
        extra["verdict"] = verdict
        extra["readback_errors"] = readback_errors
        return SequenceRunResult(
            success=success, steps=steps, extra=extra, summary=summary,
        )

    # ── 写参数先在本地解析 (越界 / 非法一条都不发) ──
    otc_value, param_reject = _parse_offset_param(params.get("offset_to_carrier"))
    confirm_write = bool(params.get("confirm_write", False))
    write_info: Dict[str, Any] = {
        "attempted": False, "value": otc_value, "readback": None,
        "readback_matches": None, "error_after_write": None,
        "error_after_readback": None, "reason": None,
    }
    extra["write"] = write_info

    # ── 只读采集 (四项 + 每步错误队列) ──
    try:
        raw_switch = await _read(
            "小区开关 ACTive:STATe?", switch_q,
            "自己写进去的 0/1 开关回声, 不是状态 (P0-2 R2)",
        )
        raw_status = await _read(
            "小区状态 BSE:STATus?", status_q,
            "协议栈真话 (手册 Range OFF|ON|CONNected|IDLE|AGGRegated|ACTivated)",
        )
        raw_arfcn = await _read("DL ARFCN 回读", arfcn_q, "当前 DL 中心 ARFCN")
        raw_pointa = await _read(
            "DL PointA 回读 (POINta?)", pointa_q,
            "手册 `NR DL PointA` 01_NR_Core.md:2244; 查询形式为推断",
        )
        raw_otc = await _read(
            "OTCarrier 回读 (OTCarrier?)", otc_q,
            "手册 `NR Configure OffsetToCarrier DL` 01_NR_Core.md:2254, Range 0..2199, "
            "Application Mode NSA|SA (IRAT 下可用性手册未说明); 查询形式为推断",
        )
    except Exception as e:  # noqa: BLE001
        return _finish(
            "ABORTED",
            f"ABORTED: 只读采集阶段异常 {type(e).__name__}: {e} — 未做任何写动作; "
            f"已采集步骤见 steps。",
        )

    extra["readback"] = {
        "cell_switch": raw_switch,
        "cell_status": raw_status,
        "dl_arfcn": raw_arfcn,
        "dl_point_a": raw_pointa,
        "dl_offset_to_carrier": raw_otc,
    }

    # ── 基线建议 (纯本地查表, 不发 SCPI, 不下发) ──
    baseline = _baseline_for(params.get("band") or "", raw_arfcn)
    extra["baseline"] = baseline
    if baseline is None:
        extra["baseline_comparison"] = None
        baseline_txt = (
            f"基线: DL ARFCN {raw_arfcn!r} 在 nr_band_baselines.json 里无精确匹配"
            f"{'' if (params.get('band') or '').strip() else ' (可传 band 参数指定)'}, 无建议值"
        )
    else:
        cur_otc, cur_pa = _to_int(raw_otc), _to_int(raw_pointa)
        extra["baseline_comparison"] = {
            "offset_to_carrier_matches_baseline": (
                cur_otc is not None and cur_otc == baseline.get("offset_to_carrier")
            ),
            "point_a_matches_baseline": (
                cur_pa is not None and cur_pa == baseline.get("point_a_arfcn")
            ),
        }
        baseline_txt = (
            f"基线 {baseline['band']} ({baseline['source']}): offset_to_carrier="
            f"{baseline.get('offset_to_carrier')} / point_a={baseline.get('point_a_arfcn')}; "
            f"仪器当前 OTCarrier={raw_otc!r} / PointA={raw_pointa!r}"
        )
    steps.append(SequenceStepResult(
        label="基线对照 (本地查表, 不下发)", success=True, detail=baseline_txt,
    ))

    readonly_summary = (
        f"已采集: 开关={raw_switch!r} 状态={raw_status!r} ARFCN={raw_arfcn!r} "
        f"PointA={raw_pointa!r} OTCarrier={raw_otc!r} | {baseline_txt}"
        + (f" | 回读报错 {len(readback_errors)} 条 (见 readback_errors; 查询形式为推断, 被拒 ≠ 设置命令不存在)"
           if readback_errors else "")
    )

    # ── 写路径判定 (每个拒绝理由都落 write.reason, 不发) ──
    if param_reject:
        write_info["reason"] = param_reject
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED: {param_reject}; 本次未下发。{readonly_summary}",
        )
    if otc_value is None:
        write_info["reason"] = "offset_to_carrier 留空 → 只读"
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED (只读, 未下发): {readonly_summary} — 是否要下发基线值"
            f"{'' if baseline is None else ' ' + str(baseline.get('offset_to_carrier'))}"
            f"由操作员看 attach 结果决定; 下发请带 offset_to_carrier + confirm_write=True。",
        )
    if not confirm_write:
        write_info["reason"] = "confirm_write=False → 不下发"
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED: 给了 offset_to_carrier={otc_value} 但 confirm_write=False, "
            f"不下发。{readonly_summary}",
        )

    # 先查状态再决定发不发: 两个口径都 OFF 才写
    sw = (raw_switch or "").strip().strip('"')
    st = (raw_status or "").strip().strip('"').upper()
    if not (sw == "0" and st == "OFF"):
        write_info["reason"] = (
            f"小区不在 OFF (开关={raw_switch!r}, 状态={raw_status!r}) → 拒绝写。"
            f"手册: OFF 态写会在开小区时自动应用; ON 态写进缓存要 APPLY 才生效, "
            f"本序列不发 APPLY。先用正常流程把小区关掉再跑。"
        )
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED: {write_info['reason']} {readonly_summary}",
        )

    # ── 写 → ERR → 立即回读 → ERR ──
    write_cmd = f"{otc_header} {otc_value}"
    write_info["attempted"] = True
    try:
        t0 = time.monotonic()
        await _w(write_cmd)
        steps.append(SequenceStepResult(
            label="写 OTCarrier (小区 OFF 态, 不 APPLY)", success=True,
            detail=f"下发 {write_cmd}; 手册: OFF 态的改动在开小区时自动应用",
            duration_ms=int((time.monotonic() - t0) * 1000),
        ))
        code_w, raw_ew = await _err_after("写 OTCarrier", write_cmd)
        write_info["error_after_write"] = raw_ew
        raw_rb = await _q(otc_q)
        steps.append(SequenceStepResult(
            label="写后立即回读 OTCarrier?", success=raw_rb is not None,
            detail=f"期望 {otc_value}", raw=raw_rb,
        ))
        code_rb, raw_erb = await _err_after("写后回读", otc_q)
        write_info["error_after_readback"] = raw_erb
    except Exception as e:  # noqa: BLE001
        return _finish(
            "ABORTED",
            f"ABORTED: 写路径异常 {type(e).__name__}: {e} — 写命令 {write_cmd} "
            f"{'已发出' if write_info['attempted'] else '未发出'}, 回读未完成; "
            f"人工回读 {otc_q} 核对。",
        )

    write_info["readback"] = raw_rb
    matches = _to_int(raw_rb) == otc_value
    write_info["readback_matches"] = matches
    queue_clean = code_w == 0 and code_rb == 0
    if matches and queue_clean:
        return _finish(
            "SUCCESS",
            f"SUCCESS: OTCarrier 已写 {otc_value} 且回读一致, 错误队列干净 "
            f"(小区 OFF 态, 开小区时自动应用, 未发 APPLY)。{readonly_summary}",
            success=True,
        )
    problems = []
    if not matches:
        problems.append(f"回读={raw_rb!r} ≠ 下发值 {otc_value}")
    if not queue_clean:
        problems.append(
            f"错误队列: 写后={raw_ew!r}, 回读后={raw_erb!r}"
        )
    return _finish(
        "BLOCKER",
        f"BLOCKER: OTCarrier 写后对账不成立 — {'; '.join(problems)}。"
        f"仪器当前值以回读为准 ({raw_rb!r})。{readonly_summary}",
    )
