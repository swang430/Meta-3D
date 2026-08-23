"""连接空置保持探针 —— P2-4 / P1-6 idle-drop 的 C 类观察载体（P1-65 A 组）。

为什么有这条
------------
「会话空置 N 秒后是不是会被仪器那头掐掉 / 驱动会不会静默重连」是 P2-4（F64 idle-close）
和 P1-6 反复提到却从没被 checked-in 载体记录过的现象 —— 每次都靠临时脚本或口头回忆。
按 CLAUDE.md「仪表驱动调试走诊断序列」的分类，这是 **C 类：一串动作之后会怎样**，
载体应是剧本式序列，而它的剧本只有三步。

做什么（**只读**；命令出处）
---------------------------
1. ``*IDN?``（IEEE 488.2 通用身份查询；F64 手册 §20.4.1.5、UXM 06_General、
   EMCenter 手册 :136-155 —— 所有受支持品类都有）—— 用驱动的 ``_query`` 原语发。
2. ``asyncio.sleep(hold_seconds)`` —— **期间本序列不发任何命令**。
3. 再发一次 ``*IDN?``；并把驱动上的会话 / 重连迹象与「步骤 1 成功之后」的快照对比
   （F64 ``_visa_resource`` / UXM ``_visa_session`` 对象换了、``_identity_response``
   被清 None = 驱动静默重连过，这是两者 ``_silent_reconnect_visa`` 的可观察副作用，
   属性表见 ``_SESSION_SIGN_ATTRS``；驱动没有的属性不记）。快照取在首条 IDN 成功之后，
   否则首条 IDN 自己触发的重连（F64 常态）会被记成空置后重连。

判定（照 P1-58 四态，透出在 ``extra["verdict"]``）
-----------------------------------------------
* SUCCESS       第二次 ``*IDN?`` 成功且无重连迹象 →「空置 N 秒会话存活」。
* UNDETERMINED  第二次失败、或驱动有重连迹象 → 这是**观察结果**（正是要喂给 P2-4 的现象），
                不是序列失败；``extra["observation"] = "idle_drop"``，summary 写清
                「空置后会话断开/重连，现象已记录」。``success`` 仍为 False —— GUI 拿
                success 画绿牌，空置掉线不能报绿。
* BLOCKER       第一次 ``*IDN?`` 就失败 → 不再空置等待。

⚠ caveat（必须随结果一起落库，见 ``extra["caveat"]`` 与 summary）
-----------------------------------------------------------------
序列 runner 取租约时 ``enable_monitoring`` 默认 True（`app/api/diagnostic_sequence.py`
→ `instrument_test_lease(...)`），而 `app/api/monitoring.py` 的 1 Hz 广播在
「有 GUI WebSocket 连着 且 监控门开」时会对仪器发 ``get_metrics`` 流量 —— 所以这里的
「空置」只保证**本序列**不发命令，**不是仪器侧的真空置**。本序列把监控门的真实状态
（`is_test_monitoring_enabled()`，即广播真正看的那扇门）记进 ``extra["monitoring_state"]``
（enabled / disabled；读不到写 unknown）。要真空置需 runner 支持按序列关监控 —— 那是加机制，
已登记设计稿 §5 Discovered #3，本片不做。驱动没有命令交换计数器，期间的实际流量计数
**不可得**，如实写在 summary 里。

``hold_seconds`` 上限 900（15 分钟）—— 超限直接拒绝：租约会把 F64 / UXM 按在 Remote，
整个面板期间不可用，不让一次手误锁住半小时。

``safe_during_test=False``：把驱动按住几分钟不动，正式测试期间跑它既毫无意义又会抢会话。
"""
from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Callable, Dict, List, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
from app.services.diagnostic_context import DiagnosticContext
from app.services.instrument_test_lease import is_test_monitoring_enabled

# 白名单：只允许探这几个品类（G18：drivers.get 的键必须在 required ∪ optional 里；
# 这里键来自参数，所以白名单就是声明本身，不许传别的）。
_ALLOWED_CATEGORIES: List[str] = [
    "channelEmulator", "baseStation", "signalAnalyzer", "positioner", "rfSwitch",
]
_DEFAULT_CATEGORY = "channelEmulator"
_DEFAULT_HOLD_S = 120
_MAX_HOLD_S = 900

# 「静默重连」在两个真驱动上留下的可观察副作用 —— 表从 `_silent_reconnect_visa` 的
# 赋值点 grep 出来，不凭记忆（内审 F1：初版写的 `_visa_session` 在 F64 上 0 处，
# F64 的会话对象是 `_visa_resource`）。`tests/test_p1_65_connection_idle_hold_probe.py`
# 有不变量门：表里每个名字必须真的在某个真驱动的 `_silent_reconnect_visa` 里被赋值。
#   F64  `RealPropsimF64Driver._silent_reconnect_visa`（propsim_f64.py）：
#        换 `_visa_resource`（新 open_resource）、清 `_identity_response`
#   UXM  `RealUxmDriver._silent_reconnect_visa`（uxm_base_station.py）：
#        换 `_visa_session`、清 `_identity_response` / `_platform_identity_response`
# 不收 `_reconnect_retry_after`：重连后第一条命令跑通就被 `_note_io_success` 归零，
# 空置掉线 → 第二条 *IDN? 触发重连成功 → 它前后都是 0.0，不是迹象。
# 对象型属性记 id()（换没换），标量 / 字符串记原值；驱动没有的属性不记（getattr None）。
_SESSION_SIGN_ATTRS = (
    "_visa_resource",              # F64 会话对象
    "_visa_session",               # UXM 会话对象
    "_identity_response",          # 两者重连都清 None；裸 *IDN? 不会重新填
    "_platform_identity_response", # UXM 重连清 None
)

_CAVEAT = (
    "caveat：序列 runner 的租约默认开监控（enable_monitoring=True），GUI 有 WebSocket 连着时 "
    "1 Hz 广播会向仪器发 get_metrics 流量 —— 本序列期间不发任何命令，但这不是仪器侧的真空置；"
    "驱动无命令交换计数器，期间实际流量计数不可得。"
)


metadata = SequenceMetadata(
    name="连接空置保持探针 (P2-4 / P1-6 idle-drop 观察)",
    description=(
        "*IDN? → 空置 hold_seconds 秒（本序列不发任何命令）→ *IDN?，记录会话是否存活、"
        "驱动是否出现重连迹象。第二次失败 / 有重连迹象 = 观察结果（UNDETERMINED，现象已记录），"
        "第一次就失败 = BLOCKER。注意：runner 租约默认开监控，空置不是仪器侧真空置。"
    ),
    required_categories=[],
    optional_categories=["channelEmulator", "baseStation", "signalAnalyzer", "positioner", "rfSwitch"],
    params_schema=[
        {"name": "category", "label": "探测哪个品类的驱动",
         "type": "string", "default": _DEFAULT_CATEGORY},
        {"name": "hold_seconds", "label": "空置秒数（上限 900）",
         "type": "number", "default": _DEFAULT_HOLD_S},
    ],
    safe_during_test=False,
)


def _parse_hold_seconds(value: Any) -> Optional[float]:
    """0 < hold ≤ 900 才合法；bool / 非数 / 超限一律 None（白名单）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value <= _MAX_HOLD_S):
        return None
    return value


def _session_snapshot(drv: Any) -> Dict[str, Any]:
    """驱动上能拿到的会话 / 重连迹象快照。对象型属性记 id()（看换没换），标量记原值。"""
    snap: Dict[str, Any] = {}
    for attr in _SESSION_SIGN_ATTRS:
        value = getattr(drv, attr, None)
        if value is None:
            continue
        if isinstance(value, (int, float, str, bool)):
            snap[attr] = value
        else:
            snap[attr] = f"id={id(value)}"
    return snap


def _monitoring_state() -> str:
    """广播真正看的那扇门（app/api/monitoring.py:91 / :181）；读不到就 unknown。"""
    try:
        return "enabled" if is_test_monitoring_enabled() else "disabled"
    except Exception:  # noqa: BLE001
        return "unknown"


async def _call_query(query_fn: Callable[..., Any], cmd: str) -> Any:
    """兼容同步（UXM pyvisa）与异步（F64）两种 `_query`：同步的扔进线程，不卡事件循环。"""
    if inspect.iscoroutinefunction(query_fn):
        return await query_fn(cmd)
    result = await asyncio.to_thread(query_fn, cmd)
    if inspect.isawaitable(result):
        result = await result
    return result


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    category = str(params.get("category") or _DEFAULT_CATEGORY)
    if category not in _ALLOWED_CATEGORIES:
        return SequenceRunResult(
            success=False,
            summary=f"category={category!r} 不在本序列允许的品类 {_ALLOWED_CATEGORIES} 内",
        )
    hold_raw = params.get("hold_seconds", _DEFAULT_HOLD_S)
    hold_s = _parse_hold_seconds(hold_raw)
    if hold_s is None:
        return SequenceRunResult(
            success=False,
            summary=(
                f"hold_seconds={hold_raw!r} 非法：必须是 0 < 秒数 ≤ {_MAX_HOLD_S}"
                "（租约会把仪器按在 Remote，不允许更长）"
            ),
        )

    drivers = getattr(hal, "drivers", {}) or {}
    drv = drivers.get(category)
    if drv is None:
        return SequenceRunResult(success=False, summary=driver_not_loaded_summary(category))
    refusal = mock_driver_refusal_summary(category, drv)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    query_fn = getattr(drv, "_query", None)
    if not callable(query_fn):
        return SequenceRunResult(
            success=False,
            summary=(
                f"{category} 驱动 {type(drv).__name__} 不暴露 _query 原语；"
                "本探针只用 *IDN?，需要裸查询原语。"
            ),
        )

    monitoring_state = _monitoring_state()
    steps: List[SequenceStepResult] = []
    hold_label = f"空置 {hold_s:g} s"

    async def _idn(label: str) -> Optional[str]:
        started = time.monotonic()
        try:
            resp = await _call_query(query_fn, "*IDN?")
        except Exception as exc:  # noqa: BLE001 — 失败本身就是要记录的现象
            steps.append(SequenceStepResult(
                label=label, success=False,
                detail=f"*IDN? 失败: {type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000), raw=None,
            ))
            log(f"  ✗ {label}: {exc!r}")
            return None
        text = None if resp is None else str(resp)
        steps.append(SequenceStepResult(
            label=label, success=text is not None, detail=text if text is not None else "*IDN? 回 None",
            duration_ms=int((time.monotonic() - started) * 1000), raw=text,
        ))
        log(f"  · {label} → {text!r}")
        return text

    # ── 1. 空置前 ──────────────────────────────────────────────────
    idn_before = await _idn("*IDN? (空置前)")
    # ⚠ 快照必须取在首条 *IDN? **成功之后**：F64 常态是驱动在首条命令上就先静默重连一次，
    #   取在它之前会把"首条 IDN 自己触发的重连"记成"空置后重连"的反向假观察（内审 F1）。
    snap_before = _session_snapshot(drv)
    base_extra = {
        "category": category,
        "driver": type(drv).__name__,
        "hold_seconds": hold_s,
        "idn_before": idn_before,
        "idn_after": None,
        "session_before": snap_before,
        "session_after": None,
        "reconnect_signs": [],
        "monitoring_state": monitoring_state,
        "caveat": _CAVEAT,
    }
    if idn_before is None:
        return SequenceRunResult(
            success=False,
            summary=(
                f"BLOCKER：{category} 空置前 *IDN? 就失败，未进入空置等待；"
                f"monitoring_state={monitoring_state}。{_CAVEAT}"
            ),
            steps=steps,
            extra={**base_extra, "verdict": "BLOCKER", "observation": None},
        )

    # ── 2. 空置：期间不发任何命令 ────────────────────────────────────
    log(f"  · {hold_label}，期间本序列不发任何命令（monitoring_state={monitoring_state}）")
    started = time.monotonic()
    await asyncio.sleep(hold_s)
    steps.append(SequenceStepResult(
        label=hold_label, success=True,
        detail=f"本序列未发命令；monitoring_state={monitoring_state}",
        duration_ms=int((time.monotonic() - started) * 1000), raw=None,
    ))

    # ── 3. 空置后 ──────────────────────────────────────────────────
    idn_after = await _idn("*IDN? (空置后)")
    snap_after = _session_snapshot(drv)
    reconnect_signs = sorted(
        attr for attr in set(snap_before) | set(snap_after)
        if snap_before.get(attr) != snap_after.get(attr)
    )
    base_extra.update({
        "idn_after": idn_after,
        "session_after": snap_after,
        "reconnect_signs": reconnect_signs,
    })

    if idn_after is not None and not reconnect_signs:
        return SequenceRunResult(
            success=True,
            summary=(
                f"SUCCESS：{category} 空置 {hold_s:g} 秒会话存活（两次 *IDN? 均应答，"
                f"无重连迹象）；monitoring_state={monitoring_state}。{_CAVEAT}"
            ),
            steps=steps,
            extra={**base_extra, "verdict": "SUCCESS", "observation": None},
        )

    why = []
    if idn_after is None:
        why.append("空置后 *IDN? 失败")
    if reconnect_signs:
        why.append(f"驱动出现重连迹象 {reconnect_signs}")
    return SequenceRunResult(
        success=False,
        summary=(
            f"UNDETERMINED（观察结果，不是序列失败）：{category} 空置后会话断开/重连，现象已记录"
            f"（空置 {hold_s:g} 秒；{'；'.join(why)}）；monitoring_state={monitoring_state}。{_CAVEAT}"
        ),
        steps=steps,
        extra={**base_extra, "verdict": "UNDETERMINED", "observation": "idle_drop"},
    )
