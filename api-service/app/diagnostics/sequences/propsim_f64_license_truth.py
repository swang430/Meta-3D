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

P1-80（2026-09-16 现场反例）：不能把主回复与错误队列拆开判。序列先归档并排空开场
residue；此后每条业务查询都在同一独占租约中立即排水，把非零错误归属到该查询。空回复
只有在该查询错误队列为零、且符合命令自身值域时才成立。许可、校准、用户对齐各自输出
`CONFIRMED / UNKNOWN`，许可成立绝不补真另两类状态。
`CONFIRMED` 只表示该子域的现场回复可归属、可解析，不表示校准本身有效或用户对齐已启用。

四态 `extra["verdict"]`：SUCCESS（所有已发查询均有可判值、逐查询与收尾错误队列为零；
对账差异只进 extra 与 summary 后缀）/ BLOCKER（任一查询异常 / 无回复 / 值域非法 / 有可
归属错误 / 查询后队列不可判）/ UNDETERMINED（查询都已判定但收尾错误队列有异步残留）/
ABORTED（开场队列不可判或身份门未过）。措辞：驱动探针命令**手册查无** ≠ 仪器不支持。
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
        "开场先归档旧错误；每条查询后立即读取 SYSTem:ERRor? 做错误归属，结尾再确认零残留。"
        "CONFIRMED 仅表示状态可信，不等于校准有效或用户对齐已启用。"
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
    if len(parts) != 2 or any(p not in ("0", "1") for p in parts):
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
        self.query_errors: Dict[str, List[str]] = {}
        self.error_queue_failures: List[str] = []
        self.opening_residue: Optional[List[str]] = None

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

    def _fail(self, cmd: str) -> None:
        if cmd not in self.failed:
            self.failed.append(cmd)

    async def _drain_queue(self) -> Tuple[Optional[List[str]], Optional[str]]:
        """排到零；返回 (非零错误, None) 或 (None, 不可判原因)。"""
        drained: List[str] = []
        try:
            for _ in range(_RESIDUE_CAP):
                raw = await self.query(_ERR_QUERY)
                code, _text = _parse_err(raw or "")
                if code == 0:
                    return drained, None
                if code is None:
                    return None, f"SYSTem:ERRor? 读不出错误码 ({raw!r})"
                drained.append((raw or "").strip())
        except Exception as e:  # noqa: BLE001
            return None, f"读队列异常 {type(e).__name__}: {e}"
        return None, f"排水撞上限（{_RESIDUE_CAP} 条仍未见 0）"

    async def read(
        self,
        cmd: str,
        describe: Callable[[str], str],
        *,
        validate: Optional[Callable[[str], Optional[str]]] = None,
    ) -> Optional[str]:
        """查询后立即排水；回复、归属错误和值域共同决定该步是否成立。"""
        started = time.monotonic()
        raw: Optional[str] = None
        query_error: Optional[BaseException] = None
        try:
            raw = await self.query(cmd)
        except Exception as e:  # noqa: BLE001
            query_error = e

        errors, drain_failure = await self._drain_queue()
        query_failure = (
            f"查询异常 {type(query_error).__name__}: {query_error}；"
            if query_error is not None else ""
        )
        if drain_failure is not None:
            self.add(
                cmd,
                False,
                f"{query_failure}查询后错误队列不可判：{drain_failure}",
                raw,
                started,
            )
            self._fail(cmd)
            self.error_queue_failures.append(cmd)
            return None
        if errors:
            self.query_errors[cmd] = errors
            self.add(
                cmd,
                False,
                f"{query_failure}查询产生 {len(errors)} 条可归属错误：{errors}",
                raw,
                started,
            )
            self._fail(cmd)
            return None
        if query_error is not None:
            self.add(
                cmd,
                False,
                f"查询异常 {type(query_error).__name__}: {query_error}",
                None,
                started,
            )
            self._fail(cmd)
            return None
        if raw is None:
            self.add(cmd, False, "无回复（驱动返回 None）", None, started)
            self._fail(cmd)
            return None
        code = _error_payload_code(raw)
        if code is not None:
            # 错误元组当响应串回来了 —— 不是值。命令手册有据；固件 / 许可 / 状态未认，
            # 原样归档，不据此断言"仪器不支持"。
            self.add(cmd, False, f"仪器回错误 payload（code {code}），不解析成值", raw, started)
            self._fail(cmd)
            self.error_payloads[cmd] = raw
            return None
        invalid_reason = validate(raw) if validate is not None else None
        if invalid_reason is not None:
            self.add(cmd, False, invalid_reason, raw, started)
            self._fail(cmd)
            return None
        self.add(cmd, True, describe(raw), raw, started)
        return raw

    def skip(self, cmd: str, reason: str) -> None:
        self.add(cmd, True, reason, None, time.monotonic())

    async def archive_opening_residue(self) -> bool:
        started = time.monotonic()
        drained, failure = await self._drain_queue()
        if failure is not None:
            self.add("开场错误队列", False, failure, None, started)
            self.opening_residue = None
            return False
        self.opening_residue = list(drained or [])
        if drained:
            self.add(
                "开场错误队列",
                True,
                f"归档并排出 {len(drained)} 条历史残留；不归属本次任何查询",
                "; ".join(drained),
                started,
            )
        else:
            self.add("开场错误队列", True, "零残留", None, started)
        return True

    async def residue(self) -> Optional[bool]:
        started = time.monotonic()
        drained, failure = await self._drain_queue()
        if failure is not None:
            self.add("收尾错误队列", False, f"{failure}；队列状态未知", None, started)
            return False
        if drained:
            self.add("收尾错误队列", False, f"残留 {len(drained)} 条未认领错误",
                     "; ".join(drained), started)
            return False
        self.add("收尾错误队列", True, "零残留", None, started)
        return True

    def evidence(self) -> Dict[str, Any]:
        return {
            "opening_residue": self.opening_residue,
            "failed_queries": list(self.failed),
            "error_payloads": dict(self.error_payloads),
            "query_errors": {key: list(value) for key, value in self.query_errors.items()},
            "error_queue_failures": list(self.error_queue_failures),
        }


def _nonempty_value(name: str) -> Callable[[str], Optional[str]]:
    def _validate(raw: str) -> Optional[str]:
        return None if raw.strip() else f"{name} 空回复，不符合手册值域"

    return _validate


def _valid_sys_info(raw: str) -> Optional[str]:
    parsed = parse_f64_sys_info(raw)
    if not any(tag in raw.upper() for tag in _IDN_MODEL_TAGS):
        return f"SYSTem:INFO? 产品身份不匹配：{raw!r}"
    if (
        parsed.product_family is None
        or parsed.channel_count is None
        or parsed.channel_count <= 0
        or parsed.signal_type is None
    ):
        return f"SYSTem:INFO? 结构不完整，不能作为许可真值：{raw!r}"
    return None


def _valid_calibration_status(raw: str) -> Optional[str]:
    in_use, valid = _parse_valid(raw)
    if in_use is None or valid is None:
        return f"解析不出手册值域 <in use 0/1>,<valid 0/1>：{raw!r}"
    return None


def _valid_state(raw: str) -> Optional[str]:
    state, note = classify_state(raw)
    return None if state is not None else f"状态不在权威白名单：{note}（raw={raw!r}）"


def _valid_interference(raw: str) -> Optional[str]:
    return None if _parse_interference(raw) is not None else f"解析不出手册三元组：{raw!r}"


async def _identity_gate(rec: _Recorder) -> Tuple[bool, str, Optional[str]]:
    idn_raw = await rec.read(
        "*IDN?",
        lambda r: "身份匹配" if any(tag in r.upper() for tag in _IDN_MODEL_TAGS)
        else "身份回复有效；型号未匹配，继续用 SYSTem:INFO? 兜底",
        validate=_nonempty_value("*IDN?"),
    )
    if idn_raw is None:
        return False, "", None
    idn = idn_raw.strip()
    if any(tag in idn.upper() for tag in _IDN_MODEL_TAGS):
        return True, idn, None
    info = await rec.read(
        _INFO_QUERY,
        lambda _r: "身份匹配（SYSTem:INFO? 兜底）",
        validate=_valid_sys_info,
    )
    return info is not None, idn, info


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
        "idn": None, "sys_info": None, "licenses": [],
        "license": {"verdict": "UNKNOWN", "sys_info": None, "licenses": []},
        "calibration": {"verdict": "UNKNOWN"},
        "user_alignment": {"verdict": "UNKNOWN"},
        "state": None, "interference": {},
        "driver_probe_discrepancy": {}, "failed_queries": [], "error_payloads": {},
        "opening_residue": None, "query_errors": {}, "error_queue_failures": [],
        "residue_clean": None,
    }

    if not await rec.archive_opening_residue():
        extra.update(rec.evidence())
        return _result(
            "ABORTED",
            "ABORTED: 开场错误队列不可判，无法建立逐查询错误归属；业务查询未发",
            rec.steps,
            extra,
        )

    ok, idn, info_raw = await _identity_gate(rec)
    extra["idn"] = idn
    if not ok:
        extra.update(rec.evidence())
        return _result("ABORTED", "ABORTED: 身份门未过（IDN / SYSTem:INFO? 都不含 PROPSIM / F8800），"
                       "许可 / 校准查询未发", rec.steps, extra)

    # 许可列表 —— §20.4.2.4 尾部 <License#1>,…（身份兜底已读过就复用，不重发）
    if info_raw is None:
        info_raw = await rec.read(
            _INFO_QUERY,
            lambda r: f"{len(parse_f64_sys_info(r).extra_tokens)} 条许可字段",
            validate=_valid_sys_info,
        )
    licenses = parse_f64_sys_info(info_raw).extra_tokens if info_raw is not None else []
    extra["sys_info"] = info_raw
    extra["licenses"] = licenses
    extra["license"] = {
        "verdict": "CONFIRMED" if info_raw is not None else "UNKNOWN",
        "sys_info": info_raw,
        "licenses": licenses,
    }

    # 校准 —— §20.4.2.11 / 12 / 13
    cal_list_raw = await rec.read(_CAL_LIST, lambda r: f"{len(_csv(r))} 个有效校准")
    cal_valid_raw = await rec.read(
        _CAL_VALID,
        lambda r: (lambda iu, v: f"in_use={iu} valid={v}")(*_parse_valid(r)),
        validate=_valid_calibration_status,
    )
    in_use, valid = _parse_valid(cal_valid_raw)
    # §20.4.2.11 GET? 只在 VALid? 说 in_use=1 时发（未使用时的应答形态手册未说明，不盲发）
    if in_use is True:
        cal_get_raw = await rec.read(
            _CAL_GET,
            lambda r: f"当前校准 {r.strip()}",
            validate=_nonempty_value("当前校准名"),
        )
    else:
        cal_get_raw = None
        rec.skip(_CAL_GET, "未发：VALid? 未给出 in_use=1"
                 + ("（解析不出 / 无回复）" if in_use is None else "（in_use=0）"))
    calibration_confirmed = (
        cal_list_raw is not None
        and cal_valid_raw is not None
        and (in_use is not True or cal_get_raw is not None)
    )
    extra["calibration"] = {
        "verdict": "CONFIRMED" if calibration_confirmed else "UNKNOWN",
        "list": _csv(cal_list_raw),
        "in_use": in_use,
        "valid": valid,
        "current": (cal_get_raw or "").strip() or None,
        "current_query_sent": in_use is True,
    }

    # 用户对齐 —— §20.4.2.19 / 21（空串 = 未启用，手册原文）
    user_get_raw = await rec.read(
        _USER_GET, lambda r: f"用户对齐 {r.strip()!r}" if r.strip() else "未启用用户对齐（空串）")
    user_enabled = bool(user_get_raw.strip()) if user_get_raw is not None else None
    # §20.4.2.21 INFO? 只在 USER:GET? 非空（已启用）时发（未启用时的应答形态手册未说明，不盲发）
    if user_enabled is True:
        user_info_raw = await rec.read(
            _USER_INFO, lambda r: f"附加信息 {r.strip()!r}" if r.strip() else "(空)")
    else:
        user_info_raw = None
        rec.skip(_USER_INFO, "未发：USER:GET? 未给出已启用的对齐名"
                 + ("（空串 = 未启用）" if user_get_raw is not None else "（无回复 / 错误 payload）"))
    extra["user_alignment"] = {
        "verdict": (
            "CONFIRMED"
            if user_get_raw is not None and (user_enabled is not True or user_info_raw is not None)
            else "UNKNOWN"
        ),
        "enabled": user_enabled,
        "name": (user_get_raw or "").strip() or None,
        "info": (user_info_raw or "").strip() or None,
        "info_query_sent": user_enabled is True,
    }

    # 干扰源 —— 先 STATE?（§20.4.3.14），非 CLOSED 才发 INTERFerence:GET?（§20.4.9.5）
    state_raw = await rec.read(
        F64_STATE_QUERY,
        lambda r: classify_state(r)[0] or "状态不可判",
        validate=_valid_state,
    )
    state, note = classify_state(state_raw)
    extra["state"] = state
    if state is not None and state != "CLOSED":
        interf_raw = await rec.read(
            _INTERF_GET,
            lambda r: (lambda s: "无干扰源（0）" if s == [] else f"{len(s or [])} 个干扰源")
            (_parse_interference(r)),
            validate=_valid_interference,
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
    extra.update(rec.evidence())

    extra["residue_clean"] = await rec.residue()
    extra.update(rec.evidence())

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
            f"BLOCKER: {len(rec.failed)} 条查询异常 / 无回复 / 值域非法 / 回错误 payload / "
            f"产生错误队列条目：{rec.failed}"
            + (f"（其中 {n_payload} 条是仪器把错误元组当响应回来：{rec.error_payloads}；"
               f"命令手册有据，固件 / 许可 / 状态未认，原样归档）" if n_payload else "")
            + suffix,
            rec.steps, extra,
        )
    unknown_domains = [
        name
        for name in ("license", "calibration", "user_alignment")
        if extra[name]["verdict"] != "CONFIRMED"
    ]
    if unknown_domains:
        return _result(
            "BLOCKER",
            f"BLOCKER: 子判决仍未知：{unknown_domains}；许可成立不得补真校准 / 用户对齐"
            + suffix,
            rec.steps,
            extra,
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
