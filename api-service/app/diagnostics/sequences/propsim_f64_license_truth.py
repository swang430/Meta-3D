"""F64 许可 / 校准 / 用户对齐 / 干扰源真值读取（`propsim_f64_license_truth`，P1-65 / P1-2）。

故障（P1-65 时；**P1-66 已修驱动**）：驱动连接路径曾靠两条**手册查无**的软探针猜许可 ——
`SYSTem:CALibration:USER:LIST?`（USER-ALIGN）/ `OUTPut:INTERFerence:LIST?`（INT-GEN），
当时驱动源码注释自承 "CAICT to-verify"（该探针表已随 P1-66 删除，connect 只扫
SYSTem:INFO?）；现场每次连接各留一条 -100 "ATE command not supported" 在错误队列
（2026-08-07 实测 269 次连接 = 269 条）。那个 -100 是**命令编出来的**，
不是"该机不支持"。本序列用手册有的命令把真值读出来，跟驱动自称的 `_installed_options`
对账；**绝不发那两条探针**（P1-65 设计稿 §5 Discovered 1 只建本序列；P1-66 删了驱动探针）。

**只读**，每条命令旁注手册章节（Propsim User Reference Rev 10.2）：

- `*IDN?`                              §20.4.1.5   身份门
- `SYSTem:INFO?`                       §20.4.2.4   原文 "Query returns the basic system info and
                                                   licenses"；尾部 `<License#1>,…,<License#N>`
                                                   **就是许可列表**，不需要探针
- `SYSTem:CALIBration:LIST?`           §20.4.2.12  有效校准列表（CSV）
- `SYSTem:CALIBration:VALid?`          §20.4.2.13  `<in use 0/1>,<valid 0/1>`
- `SYSTem:CALIBration:GET?`            §20.4.2.11  当前加载的校准名
- `SYSTem:CALIBration:USER:GET?`       §20.4.2.19  当前用户对齐名，原文 "empty string if no
                                                   user alignment is enabled"
- `SYSTem:CALIBration:USER:INFO?`      §20.4.2.21  用户对齐附加信息
- `DIAG:SIMU:STATE?`                   §20.4.3.14  前置（七态白名单复用驱动常量）
- `OUTPut:INTERFerence:GET?`           §20.4.9.5   原文 "List all the interferers in emulation"，
                                                   无干扰源返回 0；§20.4 开篇"多数 ATE 命令仅在
                                                   仿真打开后可用" → **只在 STATE? 非 CLOSED 时发**
- `SYSTem:ERRor?`                      §20.4.2.1   结尾读到 `0,"No error"` 为止

**先查状态再决定发不发**（内审 F6）：`USER:INFO?` 只在 `USER:GET?` 非空（已启用）时发；
`CALIBration:GET?` 只在 `VALid?` 的 in_use=1 时发 —— 手册未说明未启用 / 未使用时这两条的
应答形态，不盲发（超时会被驱动当 3334 desync 排水，把"没装用户对齐"这个很可能的现场实况
报成 BLOCKER）。

**错误 payload 不是值**（内审 F3）：驱动 `propsim_f64.py` 自承 F64 有时把
`-100,"ATE command not supported"` 当**响应串**回而不是 raise。每条回复先过驱动现成的
`_F64_SCPI_ERROR_RE`（复用不复制），非零错误元组 → 该步 success=False、不解析成值、
计入 failed 与 `extra["error_payloads"]`，原样归档。否则 `USER:GET?` 回 -100 会变成
"用户对齐已启用，名叫 -100,…"。

许可列表解析复用驱动 `parse_f64_sys_info`（索引 5 起、非 "Band:" 前缀的字段 = extra_tokens）
—— 这是按 §20.4.2.4 示例推出的切分约定，不是手册逐字保证；原始回复原样进 raw。

四态 `extra["verdict"]`：SUCCESS（所有查询有回复；对账差异只进 extra 与 summary 后缀，
不算失败）/ BLOCKER（任一查询超时 / 异常 / 无回复）/ UNDETERMINED（查询都有回复但收尾
错误队列有残留）/ ABORTED（身份门未过）。措辞：驱动探针命令**手册查无** ≠ 仪器不支持。
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
from app.hal.propsim_f64 import _F64_SCPI_ERROR_RE, parse_f64_sys_info
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="PROPSIM F64 许可与校准真值",
    description=(
        "只读：用手册有的命令读许可列表（SYSTem:INFO? 尾部）、校准列表/有效性/当前校准、"
        "用户对齐状态；仿真已加载时再读干扰源列表（OUTPut:INTERFerence:GET?）。"
        "把驱动自称的 _installed_options 与手册列表对账，并报告 P1-66 前驱动连接时"
        "曾发的两条手册查无探针命令（驱动已删除，本序列也绝不发它们，供历史记录对照）。"
        "结尾读 SYSTem:ERRor? 零残留。"
    ),
    required_categories=["channelEmulator"],
    params_schema=[],
    safe_during_test=False,  # 结尾 drain SYSTem:ERRor?
)

_ERR_QUERY = "SYSTem:ERRor?"                       # §20.4.2.1
_INFO_QUERY = "SYSTem:INFO?"                       # §20.4.2.4
_CAL_LIST = "SYSTem:CALIBration:LIST?"             # §20.4.2.12
_CAL_VALID = "SYSTem:CALIBration:VALid?"           # §20.4.2.13
_CAL_GET = "SYSTem:CALIBration:GET?"               # §20.4.2.11
_USER_GET = "SYSTem:CALIBration:USER:GET?"         # §20.4.2.19
_USER_INFO = "SYSTem:CALIBration:USER:INFO?"       # §20.4.2.21
_INTERF_GET = "OUTPut:INTERFerence:GET?"           # §20.4.9.5
_RESIDUE_CAP = 100

# P1-66 前驱动 `_F64_OPTION_PROBES` 连接时曾发的两条命令 —— Propsim User Reference
# Rev 10.2 全文 0 命中（§20.4.2.x 用户对齐子树无 USER:LIST?；§20.4.9 干扰源列表是
# GET? 不是 LIST?）。P1-66 已把探针从驱动删除（connect 只扫 SYSTem:INFO?）；本条
# 保留是为对照历史 DiagnosticRun。本序列**只报告、绝不发**。措辞恒为"手册查无"，
# 不说"仪器不支持"。
_DRIVER_PROBES_NOT_IN_MANUAL: Tuple[str, ...] = (
    "SYSTem:CALibration:USER:LIST?",
    "OUTPut:INTERFerence:LIST?",
)
_PROBE_NOTE = (
    "这两条探针命令手册查无（Rev 10.2 全文无此条目）；P1-66 前驱动连接时曾发它们，"
    "历史记录里回的 -100 是命令编出来的结果，不能据此断言仪器缺少对应许可；P1-66 起"
    "驱动已不发。许可真值看 SYSTem:INFO? 尾部，用户对齐看 USER:GET?，干扰源看 "
    "INTERFerence:GET?。本序列未发这两条。"
)


def _result(verdict: str, summary: str, steps: List[SequenceStepResult],
            extra: Dict[str, Any]) -> SequenceRunResult:
    extra = dict(extra)
    extra["verdict"] = verdict
    return SequenceRunResult(success=(verdict == "SUCCESS"), summary=summary,
                             steps=steps, extra=extra)


def _error_payload_code(raw: Optional[str]) -> Optional[int]:
    """回复是 IEEE 488.2 错误元组 `<code>,"<text>"` 且 code≠0 → 返回 code；否则 None。
    正则复用驱动 `_F64_SCPI_ERROR_RE`（要求引号包住描述，`1,1` / CSV 校准名不会误中；
    `0,"No error"` 形状命中但 code=0 不算错误）。"""
    if not isinstance(raw, str):
        return None
    m = _F64_SCPI_ERROR_RE.match(raw)
    if m is None:
        return None
    try:
        code = int(m.group(1))
    except ValueError:
        return None
    return code if code != 0 else None


def _csv(raw: Optional[str]) -> List[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def _parse_valid(raw: Optional[str]) -> Tuple[Optional[bool], Optional[bool]]:
    """§20.4.2.13 `<in use>,<valid>`，各为 0/1。"""
    parts = _csv(raw)
    if len(parts) < 2 or any(p not in ("0", "1") for p in parts[:2]):
        return None, None
    return parts[0] == "1", parts[1] == "1"


def _parse_interference(raw: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """§20.4.9.5：`0` = 无干扰源；否则 `output, id, type, output, id, type, …` 三元组。"""
    parts = _csv(raw)
    if parts == ["0"]:
        return []
    if not parts or len(parts) % 3 != 0:
        return None
    out: List[Dict[str, Any]] = []
    for i in range(0, len(parts), 3):
        try:
            output = int(parts[i])
        except ValueError:
            return None
        try:
            typ: Any = int(parts[i + 2])
        except ValueError:
            typ = parts[i + 2]
        out.append({"output": output, "id": parts[i + 1], "type": typ})
    return out


class _Recorder:
    def __init__(self, query_fn: Callable[[str], Any], log: Callable[[str], None]) -> None:
        self._query_fn = query_fn
        self._log = log
        self.steps: List[SequenceStepResult] = []
        self.failed: List[str] = []
        self.error_payloads: Dict[str, str] = {}

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

    async def read(self, cmd: str, describe: Callable[[str], str]) -> Optional[str]:
        """一条查询 → 原样归档。异常 / None（无回复）都记进 `failed`；"" 是合法回复。"""
        started = time.monotonic()
        try:
            raw = await self.query(cmd)
        except Exception as e:  # noqa: BLE001
            self.add(cmd, False, f"查询异常 {type(e).__name__}: {e}", None, started)
            self.failed.append(cmd)
            return None
        if raw is None:
            self.add(cmd, False, "无回复（驱动返回 None）", None, started)
            self.failed.append(cmd)
            return None
        code = _error_payload_code(raw)
        if code is not None:
            # 错误元组当响应串回来了 —— 不是值。命令手册有据；固件 / 许可 / 状态未认，
            # 原样归档，不据此断言"仪器不支持"。
            self.add(cmd, False, f"仪器回错误 payload（code {code}），不解析成值", raw, started)
            self.failed.append(cmd)
            self.error_payloads[cmd] = raw
            return None
        self.add(cmd, True, describe(raw), raw, started)
        return raw

    def skip(self, cmd: str, reason: str) -> None:
        self.add(cmd, True, reason, None, time.monotonic())

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


async def _identity_gate(rec: _Recorder) -> Tuple[bool, str, Optional[str]]:
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


def _reconcile(ce: Any, licenses: List[str]) -> Dict[str, Any]:
    """驱动自称 token（`_installed_options`）↔ 手册许可列表（SYSTem:INFO? 尾部）两向对账。
    关键字表从驱动实例上取（`_F64_SYSTINFO_KEYWORDS`，驱动自己的 keyword→token 映射），
    不另抄一份；驱动没有就如实标 keyword_map_available=False。"""
    raw_tokens = getattr(ce, "_installed_options", None)
    driver_tokens = [str(t) for t in raw_tokens] if isinstance(raw_tokens, (list, tuple)) else []
    keyword_map = getattr(ce, "_F64_SYSTINFO_KEYWORDS", None)
    map_ok = isinstance(keyword_map, dict) and bool(keyword_map)
    hits: Dict[str, List[str]] = {}
    if map_ok:
        for keyword, token in keyword_map.items():
            matched = [lic for lic in licenses if str(keyword).lower() in lic.lower()]
            if matched:
                hits.setdefault(str(token), [])
                for m in matched:
                    if m not in hits[str(token)]:
                        hits[str(token)].append(m)
    return {
        "driver_tokens": driver_tokens,
        "manual_license_list": list(licenses),
        "keyword_map_available": map_ok,
        "keyword_hits": hits,
        "driver_claims_without_manual_hit": [t for t in driver_tokens if t not in hits],
        "manual_hits_without_driver_token": sorted(t for t in hits if t not in driver_tokens),
        "driver_probe_commands_not_in_manual": list(_DRIVER_PROBES_NOT_IN_MANUAL),
        "note": _PROBE_NOTE,
    }


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
        "idn": None, "sys_info": None, "licenses": [], "calibration": {},
        "user_alignment": {}, "state": None, "interference": {},
        "driver_probe_discrepancy": {}, "failed_queries": [], "error_payloads": {},
        "residue_clean": None,
    }

    ok, idn, info_raw = await _identity_gate(rec)
    extra["idn"] = idn
    if not ok:
        return _result("ABORTED", "ABORTED: 身份门未过（IDN / SYSTem:INFO? 都不含 PROPSIM / F8800），"
                       "许可 / 校准查询未发", rec.steps, extra)

    # 许可列表 —— §20.4.2.4 尾部 <License#1>,…（身份兜底已读过就复用，不重发）
    if info_raw is None:
        info_raw = await rec.read(_INFO_QUERY, lambda r: f"{len(parse_f64_sys_info(r).extra_tokens)} 条许可字段")
    licenses = parse_f64_sys_info(info_raw).extra_tokens if info_raw is not None else []
    extra["sys_info"] = info_raw
    extra["licenses"] = licenses

    # 校准 —— §20.4.2.11 / 12 / 13
    cal_list_raw = await rec.read(_CAL_LIST, lambda r: f"{len(_csv(r))} 个有效校准")
    cal_valid_raw = await rec.read(
        _CAL_VALID,
        lambda r: (lambda iu, v: f"in_use={iu} valid={v}" if iu is not None
                   else f"解析不出 <in use>,<valid>: {r!r}")(*_parse_valid(r)),
    )
    in_use, valid = _parse_valid(cal_valid_raw)
    # §20.4.2.11 GET? 只在 VALid? 说 in_use=1 时发（未使用时的应答形态手册未说明，不盲发）
    if in_use is True:
        cal_get_raw = await rec.read(_CAL_GET, lambda r: f"当前校准 {r.strip() or '(空)'}")
    else:
        cal_get_raw = None
        rec.skip(_CAL_GET, "未发：VALid? 未给出 in_use=1"
                 + ("（解析不出 / 无回复）" if in_use is None else "（in_use=0）"))
    extra["calibration"] = {
        "list": _csv(cal_list_raw),
        "in_use": in_use,
        "valid": valid,
        "current": (cal_get_raw or "").strip() or None,
        "current_query_sent": in_use is True,
    }

    # 用户对齐 —— §20.4.2.19 / 21（空串 = 未启用，手册原文）
    user_get_raw = await rec.read(
        _USER_GET, lambda r: f"用户对齐 {r.strip()!r}" if r.strip() else "未启用用户对齐（空串）")
    user_enabled = bool(user_get_raw.strip()) if user_get_raw is not None else False
    # §20.4.2.21 INFO? 只在 USER:GET? 非空（已启用）时发（未启用时的应答形态手册未说明，不盲发）
    if user_enabled:
        user_info_raw = await rec.read(
            _USER_INFO, lambda r: f"附加信息 {r.strip()!r}" if r.strip() else "(空)")
    else:
        user_info_raw = None
        rec.skip(_USER_INFO, "未发：USER:GET? 未给出已启用的对齐名"
                 + ("（空串 = 未启用）" if user_get_raw is not None else "（无回复 / 错误 payload）"))
    extra["user_alignment"] = {
        "enabled": user_enabled,
        "name": (user_get_raw or "").strip() or None,
        "info": (user_info_raw or "").strip() or None,
        "info_query_sent": user_enabled,
    }

    # 干扰源 —— 先 STATE?（§20.4.3.14），非 CLOSED 才发 INTERFerence:GET?（§20.4.9.5）
    started = time.monotonic()
    try:
        state_raw = await rec.query(F64_STATE_QUERY)
    except Exception as e:  # noqa: BLE001
        rec.add(F64_STATE_QUERY, False, f"查询异常 {type(e).__name__}: {e}", None, started)
        rec.failed.append(F64_STATE_QUERY)
        state, note = None, "查询异常"
    else:
        state, note = classify_state(state_raw)
        rec.add(F64_STATE_QUERY, state is not None, state or note, state_raw, started)
    extra["state"] = state
    if state is not None and state != "CLOSED":
        interf_raw = await rec.read(
            _INTERF_GET,
            lambda r: (lambda s: "无干扰源（0）" if s == [] else
                       (f"{len(s)} 个干扰源" if s is not None else f"解析不出三元组: {r!r}"))
            (_parse_interference(r)),
        )
        extra["interference"] = {
            "sent": True,
            "sources": _parse_interference(interf_raw) if interf_raw is not None else None,
            "reason": None,
        }
    else:
        reason = ("未发：无已加载仿真（STATE?=CLOSED）" if state == "CLOSED"
                  else f"未发：状态读不到（{note}），不盲发")
        started = time.monotonic()
        rec.add(_INTERF_GET, True, reason, None, started)
        extra["interference"] = {"sent": False, "sources": None, "reason": reason}

    # 对账
    disc = _reconcile(ce, licenses)
    extra["driver_probe_discrepancy"] = disc
    extra["failed_queries"] = list(rec.failed)
    extra["error_payloads"] = dict(rec.error_payloads)

    extra["residue_clean"] = await rec.residue()

    n_diff = len(disc["driver_claims_without_manual_hit"]) + len(disc["manual_hits_without_driver_token"])
    suffix = (
        f"；对账：驱动自称 {disc['driver_tokens'] or '(无)'}，手册许可 {len(licenses)} 条，"
        f"差异 {n_diff} 项（驱动有手册无 {disc['driver_claims_without_manual_hit']}，"
        f"手册有驱动无 {disc['manual_hits_without_driver_token']}）；"
        f"历史探针命令手册查无 {list(_DRIVER_PROBES_NOT_IN_MANUAL)}（P1-66 已从驱动删除），本序列未发"
    )
    if rec.failed:
        n_payload = len(rec.error_payloads)
        return _result(
            "BLOCKER",
            f"BLOCKER: {len(rec.failed)} 条查询超时 / 无回复 / 回错误 payload：{rec.failed}"
            + (f"（其中 {n_payload} 条是仪器把错误元组当响应回来：{rec.error_payloads}；"
               f"命令手册有据，固件 / 许可 / 状态未认，原样归档）" if n_payload else "")
            + suffix,
            rec.steps, extra,
        )
    if extra["residue_clean"] is not True:
        return _result(
            "UNDETERMINED",
            "UNDETERMINED: 查询都有回复，但收尾错误队列有残留 / 读不出，见「收尾错误队列」步的 raw"
            + suffix,
            rec.steps, extra,
        )
    return _result(
        "SUCCESS",
        f"SUCCESS: 许可 {len(licenses)} 条、校准 in_use={in_use} valid={valid}、"
        f"用户对齐 {'启用' if extra['user_alignment']['enabled'] else '未启用'}、"
        f"干扰源 {'已读' if extra['interference']['sent'] else '未发'}；错误队列零残留"
        + suffix,
        rec.steps, extra,
    )
