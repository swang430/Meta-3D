"""EMCenter 开关机箱只读体检 —— P2-9 的首个 checked-in 载体（P1-65 A 组）。

为什么有这条
------------
P2-9「EMCenter switch bring-up」的现场半（端口通不通 / 每槽插的是什么卡 /
继电器现在拨在哪 / 互锁有没有被锁）到 2026-08-23 还没有任何 checked-in 载体 ——
到了现场只能临时敲命令，而临时脚本不查源码、错误一次性重犯（P1-45 立的规矩）。
本序列把这几问做成「点一下、看数、抄回来」。

做什么（**全部只读**，每条命令旁标手册出处）
--------------------------------------------
手册 = `Instrument_API_Doc/ETS-L EMCenter/EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf`
（Rev A 2025-08；行号为本机 `pdftotext` 抽取结果），二次出处 =
`docs/site-debug/2026-06-04-emcenter-switch-protocol.md` 命令表。

1. ``*IDN?``                  机箱身份（手册 :136-155 "Request the identification of the
                              EMCenter"；不带槽位前缀 = 系统版本）
2. ``VERSION_SW?``            系统软件版本（手册 :287-298，回 ``x.y.z``）
3. ``<slot>:*IDN?``           每个配置里出现的槽位 → 卡型号（手册 :158-185 示例
                              ``1:*IDN?`` → ``ETS-Lindgren, EMSwitch 7001-003, 4.3.3``）
4. ``<slot>:INT_RELAY_<R>?``  每槽每个继电器的当前位（手册 :305-330 SPDT → ``NO``|``NC``；
                              :508-532 SP6T → ``1-6``，``0`` = 无线圈励磁、六路全开）
5. ``INTLK? SAFETYRELAY``     互锁（手册 :492-500 "0: No interlock / 1: Interlock active"；
                              06-04 文档：1 = Relay A 被硬件锁，软件无法覆盖）。
                              手册把它列在 "Relay SP6T Card Commands" 下且无示例；这里发的
                              裸形式与生产驱动 ``connect()`` 已在用的完全一致，不另造带槽位的形式。
                              2026-08-27 CAICT 现场记录：系统软件 2.5.1 对这条精确查询回
                              ``ERROR 3;(INTLK? SAFETYRELAY);``；该单一组合只标为已知不支持，
                              不推广为其他固件 / 命令的语义，也不声称互锁为 0。

⚠ 同名 ``INT_RELAY_<R>?`` 对 SPDT 卡（值域 NC/NO）和 SP6T 卡（值域 0-6）语义不同，
  **从命令名无法区分卡类型**（06-04 文档明示）—— 值域判定只认驱动 ``port_maps`` 配置里
  的 ``relay_type``；没标就只记值、不判值域（UNDETERMINED），不猜。

槽位与继电器集合**从驱动配置派生**（``EtslSwitchDriver._mappings`` = binding 的
``port_maps``，item 形如 ``{"switch_id": "4:INT_RELAY_A", "relay_type": "spdt"}``）；
没有配置就只做机箱级三条，并在 summary 如实写「未配置槽位」。
设计稿 §2 没列 ``EXT_RELAY`` 的只读形式 → 映射里的外部继电器**不探测**，登记到
``extra["skipped_mappings"]``（禁盲试）。

不做什么
--------
不发任何会改状态的命令：继电器置位、复位 / 清错 / 重启类命令一律不出现在本文件
（`tests/test_p1_65_emcenter_switch_health.py` 有源码级 + 行为级两道门守着）。
也不发 ``STATUS?`` —— 设计稿 §2 没列它。

判定四态（照 `uxm_scpi_compatibility` 的 ``extra["verdict"]`` 口径）
----------------------------------------------------------------
* BLOCKER      任一查询超时 / 无响应（驱动 ``_send_command`` 回 None）；互锁 = 1；
               回读值不在合法值域。机箱 ``*IDN?`` 就不应答时立即停，不再往下敲。
* UNDETERMINED 没有槽位配置；某继电器没标 ``relay_type``；或精确命中 2026-08-27
               现场观察到的系统软件 2.5.1 已知不支持回复（安全状态仍未知）。
* SUCCESS      机箱 + 每槽 + 每继电器全部在值域内，且互锁权威回读为 0。
* ABORTED      序列自身异常（由 runner 记）。
措辞：除上述现场精确白名单外，未探测 ≠ 不支持；不从近似回复推断仪器能力。

``raw`` = 驱动 ``_send_command`` 返回的字符串（驱动已去终止符与 ``\\x00``，这是
它唯一的原语，不再二次归一化）；None = 这步没有仪器回复。

``safe_during_test=False``：会占用 rfSwitch 驱动的会话（虽只读），不与正式测试并行。
"""
from __future__ import annotations

import re
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

_CATEGORY = "rfSwitch"

# 手册 :305-330 / :508-532 的合法回读值域；键 = port_maps item 的 relay_type（小写）。
_RELAY_DOMAIN: Dict[str, frozenset] = {
    "spdt": frozenset({"NC", "NO"}),
    "sp6t": frozenset({"0", "1", "2", "3", "4", "5", "6"}),
}
_INTERLOCK_DOMAIN = frozenset({"0", "1"})

# 完整字面量来自 2026-08-27 操作员粘贴的诊断结果，并固化在本片设计文档；当日现场摘要
# 只保留了缩写 ``ERROR 3``。这不是厂商手册对 ERROR 3 的通用定义，只允许精确的软件
# 版本 + 完整原始回复组合。
_KNOWN_UNSUPPORTED_INTERLOCK_VERSION = "2.5.1"
_KNOWN_UNSUPPORTED_INTERLOCK_REPLY = "ERROR 3;(INTLK? SAFETYRELAY);"

# port_maps 的 switch_id 形态（驱动 switch_path 直接拿它拼命令）：``<slot>:INT_RELAY_<R>``
_INT_RELAY_ID = re.compile(r"^(?P<slot>\d+):INT_RELAY_(?P<relay>[A-D])$")

# 连续无响应几次就停止往下走（照 uxm_scpi_compatibility 的 3 strikes：
# VISA 每次超时 5 s，半死会话会把只读普查拖成几分钟）。
_MAX_CONSECUTIVE_TIMEOUTS = 3


metadata = SequenceMetadata(
    name="EMCenter 开关机箱只读体检 (P2-9)",
    description=(
        "只读：*IDN? → VERSION_SW? → 每个配置槽位 <slot>:*IDN? → 每槽每继电器 "
        "<slot>:INT_RELAY_<R>? → INTLK? SAFETYRELAY。槽位 / 继电器 / relay_type 从驱动 "
        "port_maps 派生；没配置就只做机箱级三条。互锁=1 / 超时 / 回读值不在值域 → BLOCKER；"
        "系统软件 2.5.1 的现场精确 ERROR 3 回复标为已知不支持且安全状态未知；无槽位配置或缺 "
        "relay_type → UNDETERMINED。不发任何写命令。"
    ),
    required_categories=["rfSwitch"],
    params_schema=[],
    safe_during_test=False,  # 占用开关会话（只读）；不与正式测试并行
)


def _relay_targets(mappings: Any) -> "tuple[Dict[str, Dict[str, Optional[str]]], List[str]]":
    """从驱动 port_maps 派生 ``{slot: {relay: relay_type|None}}``（去重、按槽位 / 继电器排序），
    以及无法按 ``<slot>:INT_RELAY_<R>`` 解析、因此**不探测**的 switch_id 列表。"""
    targets: Dict[str, Dict[str, Optional[str]]] = {}
    skipped: List[str] = []
    if not isinstance(mappings, dict):
        return targets, skipped
    for item in mappings.values():
        if not isinstance(item, dict):
            continue
        switch_id = item.get("switch_id", item.get("relay"))
        if switch_id is None:
            continue
        switch_id = str(switch_id)
        m = _INT_RELAY_ID.match(switch_id)
        if not m:
            if switch_id not in skipped:
                skipped.append(switch_id)
            continue
        relay_type_raw = item.get("relay_type")
        relay_type = str(relay_type_raw).strip().lower() if relay_type_raw else None
        slot_relays = targets.setdefault(m.group("slot"), {})
        # 同一继电器被多条路径引用：只要有一条标了 relay_type 就用它
        if slot_relays.get(m.group("relay")) is None:
            slot_relays[m.group("relay")] = relay_type
    ordered = {
        slot: dict(sorted(relays.items()))
        for slot, relays in sorted(targets.items(), key=lambda kv: int(kv[0]))
    }
    return ordered, skipped


def _classify_interlock(version: Optional[str], reply: Optional[str]) -> str:
    """按手册值域和单一现场白名单分类互锁回复，不从近似字符串推断。"""
    if reply is None:
        return "no_response"
    value = reply.strip()
    if value == "0":
        return "inactive"
    if value == "1":
        return "active"
    if (
        (version or "").strip() == _KNOWN_UNSUPPORTED_INTERLOCK_VERSION
        and value == _KNOWN_UNSUPPORTED_INTERLOCK_REPLY
    ):
        return "known_unsupported"
    return "invalid"


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    drv = drivers.get("rfSwitch")
    if drv is None:
        return SequenceRunResult(success=False, summary=driver_not_loaded_summary(_CATEGORY))
    refusal = mock_driver_refusal_summary(_CATEGORY, drv)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    send = getattr(drv, "_send_command", None)
    if not callable(send):
        return SequenceRunResult(
            success=False,
            summary=(
                f"rfSwitch 驱动 {type(drv).__name__} 不暴露 _send_command 原语；"
                "本序列需要 EtslSwitchDriver 的裸命令 + CR 发送原语。"
            ),
        )

    steps: List[SequenceStepResult] = []
    blockers: List[str] = []
    undetermined: List[str] = []
    consecutive_timeouts = 0
    walk_aborted = False

    async def _ask(cmd: str) -> Optional[str]:
        """发一条只读查询；返回驱动原样回复（None = 无响应 / 超时）。"""
        nonlocal consecutive_timeouts
        started = time.monotonic()
        try:
            resp = await send(cmd)
        except Exception as exc:  # noqa: BLE001 — 驱动原语本应吞异常回 None；兜底不让序列 ABORTED
            resp = None
            log(f"  ✗ {cmd}: 驱动原语抛出 {exc!r}")
        duration_ms = int((time.monotonic() - started) * 1000)
        if resp is None:
            consecutive_timeouts += 1
            steps.append(SequenceStepResult(
                label=cmd, success=False,
                detail="无响应 / 超时（驱动 _send_command 返回 None）",
                duration_ms=duration_ms, raw=None,
            ))
            blockers.append(f"{cmd} 无响应")
            log(f"  ✗ {cmd}: 无响应 / 超时")
            return None
        consecutive_timeouts = 0
        # 成功与否由调用方按值域再判；先占位，调用方可改 success/detail
        steps.append(SequenceStepResult(
            label=cmd, success=True, detail=resp, duration_ms=duration_ms, raw=resp,
        ))
        log(f"  · {cmd} → {resp!r}")
        return resp

    def _mark_last(success: bool, detail: str) -> None:
        steps[-1].success = success
        steps[-1].detail = detail

    # ── 1. 机箱身份（手册 :136-155）────────────────────────────────
    chassis_idn = await _ask("*IDN?")
    if chassis_idn is None:
        walk_aborted = True
    elif not chassis_idn.strip():
        _mark_last(False, "机箱 *IDN? 回了空串")
        blockers.append("*IDN? 回空串")

    version: Optional[str] = None
    targets: Dict[str, Dict[str, Optional[str]]] = {}
    skipped: List[str] = []
    slots_out: List[Dict[str, Any]] = []
    interlock: Optional[str] = None
    interlock_classification: Optional[str] = None

    if not walk_aborted:
        # ── 2. 系统软件版本（手册 :287-298）──────────────────────────
        version = await _ask("VERSION_SW?")

        # ── 3/4. 逐槽卡识别 + 继电器位回读（槽位集合从驱动配置派生）──
        targets, skipped = _relay_targets(getattr(drv, "_mappings", None))
        if skipped:
            log(f"  · 未探测（设计稿未列只读形式或无法按 <slot>:INT_RELAY_<R> 解析）: {skipped}")
        for slot, relays in targets.items():
            if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                walk_aborted = True
                break
            # 手册 :158-185：``<slot>:*IDN?`` → 卡型号
            slot_idn = await _ask(f"{slot}:*IDN?")
            relay_values: Dict[str, Optional[str]] = {}
            for relay, relay_type in relays.items():
                if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                    walk_aborted = True
                    break
                # 手册 :305-330（SPDT）/ :508-532（SP6T）：``<slot>:INT_RELAY_<R>?``
                cmd = f"{slot}:INT_RELAY_{relay}?"
                value = await _ask(cmd)
                relay_values[relay] = value
                if value is None:
                    continue
                domain = _RELAY_DOMAIN.get(relay_type or "")
                if domain is None:
                    why = (
                        "未标 relay_type" if relay_type is None
                        else f"relay_type={relay_type!r} 不是 spdt/sp6t"
                    )
                    _mark_last(True, f"{value!r}（port_maps {why}，SPDT/SP6T 值域无法判定，只记值）")
                    undetermined.append(f"{cmd} {why}")
                elif value.strip() in domain:
                    _mark_last(True, f"{value!r} ∈ {relay_type.upper()} 值域")
                else:
                    _mark_last(
                        False,
                        f"{value!r} 不在 {relay_type.upper()} 合法值域 {sorted(domain)} 内",
                    )
                    blockers.append(f"{cmd} 回读 {value!r} 不在 {relay_type.upper()} 值域")
            slots_out.append({"slot": slot, "idn": slot_idn, "relays": relay_values})
            if walk_aborted:
                break

        # ── 5. 互锁（手册 :492-500；形式与驱动 connect() 一致）───────
        if not walk_aborted:
            interlock = await _ask("INTLK? SAFETYRELAY")
            interlock_classification = _classify_interlock(version, interlock)
            if interlock is not None:
                if interlock_classification == "active":
                    _mark_last(False, "互锁激活：Relay A 被硬件锁，软件无法覆盖（供电继电器断开）")
                    blockers.append("互锁=1：Relay A 被硬件锁，软件无法覆盖")
                elif interlock_classification == "known_unsupported":
                    _mark_last(
                        False,
                        "系统软件 2.5.1 的现场精确回复：该互锁查询已知不支持；安全状态未知",
                    )
                    undetermined.append(
                        "INTLK? SAFETYRELAY 已知不支持：未取得 0/1 权威值，安全状态未知"
                    )
                elif interlock_classification == "invalid":
                    _mark_last(False, f"{interlock!r} 不在互锁合法值域 {sorted(_INTERLOCK_DOMAIN)} 内")
                    blockers.append(f"INTLK? SAFETYRELAY 回读 {interlock!r} 不在 0/1 值域")
                else:
                    _mark_last(True, "0：互锁未激活，继电器工作正常")

    if walk_aborted:
        blockers.append(
            "连续无响应，已停止余下只读步骤"
            if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS and chassis_idn is not None
            else "机箱 *IDN? 无响应，未继续探测槽位"
        )
    if not targets and not walk_aborted:
        undetermined.append("驱动 port_maps 未配置槽位：只做了机箱级三条，卡型号 / 继电器位未探测")

    # ── 判定 ─────────────────────────────────────────────────────────
    if blockers:
        verdict = "BLOCKER"
        summary = "BLOCKER：" + "；".join(blockers)
    elif undetermined:
        verdict = "UNDETERMINED"
        summary = "UNDETERMINED（未探测 ≠ 不支持）：" + "；".join(undetermined)
    else:
        verdict = "SUCCESS"
        relay_count = sum(len(s["relays"]) for s in slots_out)
        summary = (
            f"SUCCESS：机箱 {chassis_idn!r} / 软件 {version!r}；"
            f"{len(slots_out)} 个槽位 {relay_count} 个继电器回读全部在值域内；"
            "互锁 0"
        )
    if skipped:
        summary += f"；未探测的映射（非 <slot>:INT_RELAY_<R> 形式）: {skipped}"

    return SequenceRunResult(
        success=verdict == "SUCCESS",
        summary=summary,
        steps=steps,
        extra={
            "chassis_idn": chassis_idn,
            "version": version,
            "slots": slots_out,
            "interlock": interlock,
            "interlock_classification": interlock_classification,
            "verdict": verdict,
            "blockers": blockers,
            "undetermined": undetermined,
            "skipped_mappings": skipped,
            "walk_aborted": walk_aborted,
        },
    )
