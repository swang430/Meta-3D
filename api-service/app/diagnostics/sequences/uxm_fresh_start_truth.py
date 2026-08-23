"""P1-17 现场载体: UXM fresh-start / 状态导入机制真值 (P1-65)。

要回答的问题 (roadmap「Blocked on hardware」P1-17): 现场想把 UXM 拉回一个已知的
干净状态, 手册给的机制是什么、本机到底可不可用 —— 而**不是**驱动里那两条
手册查无的命令。本序列默认只读, 把机制可用性采齐; 导入动作只在显式确认
+ 先查小区状态后才发, 发完读导入状态 + 错误队列 + 复核 TAP 名。

命令清单 (全部出自本地手册原件 `Instrument_API_Doc/Keysight UXM NR SCPI/`
`UXM5G_SCPI_06_General_Examples_Shared.md`, 设计稿 §2):

- `SYSTem:APPLication[:NAME]` —— `Test Application Mode`, 06_General.md:232,
  Range `NRSI | NRNS| NSA | NRCW | NRSA | NREL1 | LTE_NR_IRAT | LTEV2X`。
  查询形式 `SYSTem:APPLication:NAME?` 是生产驱动 connect() 已在用的 (既有)。
- `SYSTem:LICense:AVAilable:ALL?` —— `ALL License List`, 06_General.md:1817,
  Query only, RUI only, Application Mode `ALL`; Notes 原文 "These are not validated"。
- `SYSTem:SCPI:FOLDer` —— `Change SCPI Import folder`, 06_General.md:1179, String。
  ⚠ 查询形式 `...:FOLDer?` 是**推断** (String 设置项, 无 No-query 标记)。
- `SYSTem:SCPI:IMPort:INCLude:PRESet` —— `Preset Before Import`, 06_General.md:1217,
  Boolean; 原文 "Presets the instrument before importing the SCPI file" ——
  这个值决定导入会不会先复位, 所以导入前必须读出来并在结论里点名。
  ⚠ 查询形式 `...:PRESet?` 同为**推断**。
- `SYSTem:SCPI:IMPort:STATus?` —— `Query SCPI Import Status`, 06_General.md:1244,
  **Query only** (手册原文), Boolean, 原文 "Queries the success or failure of an import"。
  ⚠ "1 = 成功" 是按 Boolean 型 + Default `0 (i.e. OFF)` 的**推断**, 手册没写哪个值是成功。
- `SYSTem:SCPI:IMPort "<file>"` —— `Import SCPI File`, 06_General.md:1203, String,
  原文 "Import (i.e. load) a SCPI file, recovering a previously exported application state"。
- `CELL_STATUS_QUERY` (`BSE:STATus:NR5G:<cell>?`) —— 既有 profile 常量 (P0-2 D1)。
- `SYSTem:ERRor?` —— 每条命令后读一次。

**本序列不发**:
- `SYSTem:PRESet:FULL` / `FACTory` / `API` (06_General.md:9568-9570 命令总表) ——
  破坏性复位, 只记进 `extra["preset_commands_available_not_sent"]` 作手册可用命令;
- 驱动 5G profile 的 `STATE_LOAD` (`SYSTem:CONFiguration:LOAD "<file>"`) 与
  `STATE_LIST` (`MMEMory:CATalog? "D:\\User Files"`) —— 六份手册 md **0 命中**
  (设计稿 §5 Discovered 2), 只如实记进 `extra["driver_state_load_discrepancy"]`。

方言门: 手册是 Test Application Framework (LTE_NR_IRAT / NSA / NRSA …) 的 SCPI
参考, `SYSTem:SCPI:*` 标 `NSA | SA`; 5G_NR_Test 方言 (无前缀 `CONFig:` 根, CELL0)
是另一套应用, 这些命令在它上面的形式未查证 → 不发, UNDETERMINED。
(IRAT 下 `NSA | SA` 命令可不可用手册同样未说明 —— 发出去、原样记, 不下结论。)

导入路径安全 (「先查状态再决定发不发」):
- 只在 `import_file` 非空 **且** `confirm_action=True` 时考虑;
- 文件名含引号 / 换行 / 全空白在本地拒绝, 不发;
- 小区状态显示有 UE 在网 (CONNected / IDLE / AGGRegated / ACTivated) 时拒绝 ——
  导入恢复整机应用状态, 会把正在进行的会话直接拆掉; OFF / ON 允许;
- 导入后: `IMPort:STATus?` → `SYSTem:ERRor?` → `SYSTem:APPLication:NAME?` 复核。

四态 `extra["verdict"]`: SUCCESS (导入状态为成功且队列干净) / UNDETERMINED (只读已
采集, 或导入未发生) / BLOCKER (导入状态非成功或队列有错) / ABORTED (传输异常)。
`safe_during_test=False`。
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
# 复用不复制: 同意门布尔解析 (内审 F2) 与小区白名单 (内审 F5) 跟兄弟序列同源。
from app.diagnostics.sequences.propsim_f64_local_handback_check import _as_bool
from app.diagnostics.sequences.uxm_offset_to_carrier_probe import (
    _is_bse_dialect,
    _validate_cell,
)
# 复用不复制: 错误码解析与方言解析跟兄弟序列同源。
from app.diagnostics.sequences.uxm_scpi_compatibility import (
    _parse_err,
    _profile_for_driver,
)
from app.hal.uxm_command_profiles import Uxm5GNRTestAppProfile
from app.services.diagnostic_context import DiagnosticContext

# 手册条目 (06_General.md 行号见模块 docstring)。
_APP_NAME_Q = "SYSTem:APPLication:NAME?"          # :232 (查询形式驱动已在用)
_LICENSE_ALL_Q = "SYSTem:LICense:AVAilable:ALL?"  # :1817 Query only
_SCPI_FOLDER_Q = "SYSTem:SCPI:FOLDer?"            # :1179 (查询形式为推断)
_IMPORT_INCLUDE_PRESET_Q = "SYSTem:SCPI:IMPort:INCLude:PRESet?"  # :1217 (推断)
_IMPORT_STATUS_Q = "SYSTem:SCPI:IMPort:STATus?"   # :1244 Query only
_IMPORT_HEADER = "SYSTem:SCPI:IMPort"             # :1203
# 06_General.md:9568-9570 命令总表; 破坏性, 本序列不发。
_PRESET_COMMANDS_NOT_SENT = [
    "SYSTem:PRESet:API", "SYSTem:PRESet:FACTory", "SYSTem:PRESet:FULL",
]
# 小区状态里"有 UE 在网"的取值 (手册 `NR Connection Status` Range 的后四个)。
_UE_PRESENT_STATES = {"CONNECTED", "IDLE", "AGGREGATED", "ACTIVATED"}


metadata = SequenceMetadata(
    name="UXM fresh-start 机制真值 (P1-17)",
    description=(
        "只读采集手册给的状态导入机制: APPLication:NAME? / LICense:AVAilable:ALL? / "
        "SCPI:FOLDer? / SCPI:IMPort:INCLude:PRESet? / SCPI:IMPort:STATus? / 小区状态; "
        "如实记录驱动 STATE_LOAD/STATE_LIST 手册查无 (不发)。给了 import_file 且 "
        "confirm_action=True 时发 SYSTem:SCPI:IMPort 并读导入状态 + 错误队列 + 复核 TAP; "
        "有 UE 在网时拒绝导入。不发 SYSTem:PRESet:*。只在 LTE_NR_IRAT (BSE:) 方言发命令。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "小区 (留空=方言主小区)", "type": "string", "default": ""},
        {"name": "import_file",
         "label": "要导入的 SCPI 文件 (留空=只读; 相对 SCPI:FOLDer 或绝对路径)",
         "type": "string", "default": ""},
        {"name": "confirm_action", "label": "确认执行导入 (有 UE 在网时仍会拒绝)",
         "type": "boolean", "default": False},
    ],
    safe_during_test=False,
)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


def _validate_import_file(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """返回 (规整后的文件名, 拒绝原因)。引号 / 换行 / 全空白 在本地拒绝。"""
    if value is None:
        return None, None
    s = str(value)
    if not s.strip():
        return None, None
    if '"' in s or "\n" in s or "\r" in s:
        return None, f"import_file={s!r} 含引号或换行, 本地拒绝, 未发到仪器"
    return s.strip(), None


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
    extra: Dict[str, Any] = {
        "profile": profile_name,
        "cell": None,
        "preset_commands_available_not_sent": list(_PRESET_COMMANDS_NOT_SENT),
        # 设计稿 §5 Discovered 2: 驱动 5G profile 现用的两条状态命令手册查无。
        # 只记录, 不发; 本条不是"仪器不支持", 是"手册里没有这条命令"。
        "driver_state_load_discrepancy": {
            "STATE_LOAD": Uxm5GNRTestAppProfile.STATE_LOAD,
            "STATE_LIST": Uxm5GNRTestAppProfile.STATE_LIST,
            "manual_hits": 0,
            "manual_mechanism": f'{_IMPORT_HEADER} "<file>" + {_IMPORT_STATUS_Q}',
            "sent": False,
        },
    }

    if not _is_bse_dialect(profile):
        extra["verdict"] = "UNDETERMINED"
        return SequenceRunResult(
            success=False, extra=extra,
            summary=(
                f"UNDETERMINED: 当前方言 {profile_name} 的命令根不是 BSE:; 本序列的 "
                f"SYSTem:SCPI:* 系列出自 Test Application Framework 手册 (06_General.md), "
                f"{profile_name} 方言下命令形式未查证, 不发 (未探测 ≠ 不支持)。"
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

    steps: List[SequenceStepResult] = []
    readback_errors: Dict[str, str] = {}

    async def _q(cmd: str) -> Optional[str]:
        raw = await _maybe_await(bs._query(cmd))  # noqa: SLF001
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    async def _w(cmd: str) -> None:
        await _maybe_await(bs._write(cmd))  # noqa: SLF001

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

    import_file, file_reject = _validate_import_file(params.get("import_file"))
    # 同意门 fail-closed (内审 F2): 只有 True / "true" / "1" / "yes" 算确认。
    confirm_action = _as_bool(params.get("confirm_action")) is True
    import_info: Dict[str, Any] = {
        "attempted": False, "file": import_file, "status_after": None,
        "application_after": None, "error_after_import": None, "reason": None,
    }
    extra["import"] = import_info

    # ── 只读采集 ──
    try:
        raw_app = await _read(
            "TAP 名 SYSTem:APPLication:NAME?", _APP_NAME_Q,
            "手册 `Test Application Mode` 06_General.md:232",
        )
        raw_lic = await _read(
            "许可 SYSTem:LICense:AVAilable:ALL?", _LICENSE_ALL_Q,
            "手册 `ALL License List` 06_General.md:1817 (Query only; 原文: not validated)",
        )
        raw_folder = await _read(
            "导入目录 SYSTem:SCPI:FOLDer?", _SCPI_FOLDER_Q,
            "手册 `Change SCPI Import folder` 06_General.md:1179; 查询形式为推断",
        )
        raw_incl = await _read(
            "导入前复位 SYSTem:SCPI:IMPort:INCLude:PRESet?", _IMPORT_INCLUDE_PRESET_Q,
            "手册 `Preset Before Import` 06_General.md:1217 (1=导入前先复位); 查询形式为推断",
        )
        raw_imp_status = await _read(
            "导入状态 SYSTem:SCPI:IMPort:STATus?", _IMPORT_STATUS_Q,
            "手册 `Query SCPI Import Status` 06_General.md:1244 (Query only); 上一次导入的成败",
        )
        raw_status = await _read(
            "小区状态 BSE:STATus?", status_q,
            "协议栈真话 (手册 Range OFF|ON|CONNected|IDLE|AGGRegated|ACTivated)",
        )
    except Exception as e:  # noqa: BLE001
        return _finish(
            "ABORTED",
            f"ABORTED: 只读采集阶段异常 {type(e).__name__}: {e} — 未执行导入; "
            f"已采集步骤见 steps。",
        )

    extra["readback"] = {
        "application_name": raw_app,
        "licenses_available_all": raw_lic,
        "scpi_folder": raw_folder,
        "import_include_preset": raw_incl,
        "import_status": raw_imp_status,
        "cell_status": raw_status,
    }
    incl_on = (raw_incl or "").strip().strip('"').upper() in {"1", "ON"}
    readonly_summary = (
        f"已采集: TAP={raw_app!r} 许可={raw_lic!r} 导入目录={raw_folder!r} "
        f"导入前复位(INCLude:PRESet)={raw_incl!r}{' ⚠ 导入会先复位' if incl_on else ''} "
        f"上次导入状态={raw_imp_status!r} 小区状态={raw_status!r}"
        + (f" | 回读报错 {len(readback_errors)} 条 (见 readback_errors; 推断的查询形式被拒 "
           f"≠ 命令不存在)" if readback_errors else "")
        + f" | 手册复位命令 {_PRESET_COMMANDS_NOT_SENT} 本序列不发"
        + " | 驱动 STATE_LOAD/STATE_LIST 手册查无, 未发"
    )

    # ── 导入路径判定 ──
    if file_reject:
        import_info["reason"] = file_reject
        return _finish("UNDETERMINED", f"UNDETERMINED: {file_reject}; 未执行导入。{readonly_summary}")
    if import_file is None:
        import_info["reason"] = "import_file 留空 → 只读"
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED (机制可用性已采集; 未执行导入): {readonly_summary}",
        )
    if not confirm_action:
        import_info["reason"] = "confirm_action=False → 不导入"
        return _finish(
            "UNDETERMINED",
            f"UNDETERMINED: 给了 import_file={import_file!r} 但 confirm_action=False, "
            f"未执行导入。{readonly_summary}",
        )
    st = (raw_status or "").strip().strip('"').upper()
    if st in _UE_PRESENT_STATES:
        import_info["reason"] = (
            f"小区状态={raw_status!r} 显示有 UE 在网 → 拒绝导入 (导入恢复整机应用状态, "
            f"会拆掉进行中的会话)。先用正常流程把 UE 放掉 / 小区关掉再跑。"
        )
        return _finish("UNDETERMINED", f"UNDETERMINED: {import_info['reason']} {readonly_summary}")

    # ── 导入 → ERR → STATus? → ERR → APPLication:NAME? → ERR ──
    import_cmd = f'{_IMPORT_HEADER} "{import_file}"'
    import_info["attempted"] = True
    try:
        t0 = time.monotonic()
        await _w(import_cmd)
        steps.append(SequenceStepResult(
            label="导入 SYSTem:SCPI:IMPort", success=True,
            detail=(f"下发 {import_cmd}; 手册 06_General.md:1203"
                    + (" ⚠ INCLude:PRESet=1, 导入前先复位" if incl_on else "")),
            duration_ms=int((time.monotonic() - t0) * 1000),
        ))
        code_i, raw_ei = await _err_after("导入", import_cmd)
        import_info["error_after_import"] = raw_ei
        raw_st2 = await _read(
            "导入后状态 SYSTem:SCPI:IMPort:STATus?", _IMPORT_STATUS_Q,
            "手册: success or failure of an import; 1=成功为按 Boolean 型的推断",
        )
        raw_app2 = await _read(
            "导入后复核 SYSTem:APPLication:NAME?", _APP_NAME_Q,
            f"导入前 {raw_app!r}",
        )
    except Exception as e:  # noqa: BLE001
        return _finish(
            "ABORTED",
            f"ABORTED: 导入路径异常 {type(e).__name__}: {e} — 导入命令 {import_cmd} "
            f"已发出, 状态未读到; 人工读 {_IMPORT_STATUS_Q} 与 SYSTem:ERRor? 核对。",
        )

    import_info["status_after"] = raw_st2
    import_info["application_after"] = raw_app2
    status_ok = (raw_st2 or "").strip().strip('"').upper() in {"1", "ON"}
    if status_ok and code_i == 0:
        return _finish(
            "SUCCESS",
            f"SUCCESS: 已导入 {import_file!r}, IMPort:STATus?={raw_st2!r} (成功), 错误队列干净; "
            f"TAP 导入前 {raw_app!r} → 导入后 {raw_app2!r}。{readonly_summary}",
            success=True,
        )
    problems = []
    if not status_ok:
        problems.append(f"IMPort:STATus?={raw_st2!r} 非成功")
    if code_i != 0:
        problems.append(f"导入后错误队列={raw_ei!r}")
    return _finish(
        "BLOCKER",
        f"BLOCKER: 导入 {import_file!r} 未确认成功 — {'; '.join(problems)}; "
        f"TAP 导入前 {raw_app!r} → 导入后 {raw_app2!r}。{readonly_summary}",
    )
