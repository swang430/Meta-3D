"""P0-2 现场探针: UXM 配置「下发 → 生效 → 核对」链路的真值验证 (R2 / R4 / R7)。

一次运行拿齐三份现场证据 (全部记 `raw` 原始回复, 归档进 DiagnosticRun 供对照):

- **R2 对照**: `ACTive:STATe?`(开关回声) vs `BSE:STATus:NR5G:<cell>?`(协议栈真话)
  并排各读一次 —— 现场 07-21 那句"ACTive=1 但 STATus 持续 OFF"的定案证据。
- **R4 判定** (设计稿标 🟡 的唯一手册没写死的问题): 小区 ON 态写一个不同的
  ARFCN、**先不 APPLY** 就回读 —— 回读=新值 ⇒ `BSE:CONFig:...?` 读的是缓存
  (APPLY 前对账=假绿, D3 二层必须); 回读=旧值 ⇒ 回读即生效值 (D3 可简化,
  APPLY 照发)。**判定结论直接写进 step detail**, 现场抄回设计稿 §7 即可。
- **R7 取证**: binding 显式 topology 选择 vs 系统默认 (纯本地读, 不发 SCPI) ——
  配合 live ARFCN 回读, 坐实/推翻"623334 是 UXM 出厂默认、当时 apply 假绿"。

安全设计 (CLAUDE.md 诊断序列约束):
- 只用手册有据 + 生产驱动在用的命令 (CELL_DL_ARFCN / CELL_STATE_QUERY /
  CELL_STATUS_QUERY / CONFIG_APPLY, 全部在 UxmLteNrIratProfile 注了手册出处);
- 带动作, 所以**先查状态再决定发不发**: 小区不在 ON (开关≠"1") 直接中止,
  不自作主张开小区;
- 每个写动作后读一次 `SYST:ERR?`;
- **任何中途异常都走 finally 恢复** (写回原 ARFCN + APPLY), 绝不把仪器留在
  改了一半的态; 恢复后终读确认, 恢复不成 = 大声失败, summary 直接给人工
  恢复命令。

只适用 LTE_NR_IRAT 方言 (CONFIG_APPLY / CELL_STATUS_QUERY 手册依据仅此方言);
其它方言直接拒绝, 不猜。会改 ARFCN (虽会恢复), `safe_during_test=False`。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

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
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="UXM 配置生效链路探针 (P0-2 R2/R4/R7)",
    description=(
        "小区 ON 态下: ①并排读开关回声 vs 协议栈状态 (R2 定案); ②写测试 ARFCN "
        "不 APPLY 就回读, 判定 CONF? 读缓存还是生效值 (R4, 结论写进 step); "
        "③记录 binding topology 选择 vs 系统默认 (R7)。写动作全部恢复原值并 "
        "APPLY 收尾, 终读确认。只适用 LTE_NR_IRAT; 小区不在 ON 直接中止。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "小区 (留空=方言主小区)", "type": "string", "default": ""},
        # 634666 = n78 内 3537.99 MHz, 与现场基线 636666 (3549.99) 明显不同且合法;
        # 若恰与仪器当前值相同, 运行时自动改用 636666。
        {"name": "test_arfcn", "label": "测试 ARFCN (与当前值不同即可)",
         "type": "number", "default": 634666},
    ],
    safe_during_test=False,
)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


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
    status_q_t = getattr(profile, "CELL_STATUS_QUERY", None)
    apply_cmd = getattr(profile, "CONFIG_APPLY", None)
    arfcn_t = getattr(profile, "CELL_DL_ARFCN", None)
    switch_t = getattr(profile, "CELL_STATE_QUERY", None)
    if not all((status_q_t, apply_cmd, arfcn_t, switch_t)):
        return SequenceRunResult(
            success=False,
            summary=(
                f"方言 {profile_name} 缺本探针依赖的命令 (CELL_STATUS_QUERY/"
                f"CONFIG_APPLY/CELL_DL_ARFCN/CELL_STATE_QUERY 有 None) — "
                f"手册依据仅覆盖 LTE_NR_IRAT, 其它方言不猜。"
            ),
        )

    cell = (params.get("cell") or "").strip() or getattr(profile, "PRIMARY_CELL", "CELL1")
    steps: List[SequenceStepResult] = []
    extra: Dict[str, Any] = {"profile": profile_name, "cell": cell}

    async def _q(cmd: str) -> Optional[str]:
        raw = await _maybe_await(bs._query(cmd))  # noqa: SLF001
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    async def _w(cmd: str) -> None:
        await _maybe_await(bs._write(cmd))  # noqa: SLF001

    async def _err_after(label: str) -> Optional[int]:
        """写动作后读一次错误队列; 返回错误码 (0=干净, None=读不出)。"""
        raw_e = await _q("SYST:ERR?")
        code, text = _parse_err(raw_e or "")
        steps.append(SequenceStepResult(
            label=f"{label} → SYST:ERR?",
            success=(code == 0),
            detail="队列干净" if code == 0 else f"错误: {text or raw_e!r}",
            raw=raw_e,
        ))
        return code

    def _step(label: str, success: bool, detail: str, raw: Optional[str] = None,
              t0: Optional[float] = None) -> None:
        steps.append(SequenceStepResult(
            label=label, success=success, detail=detail, raw=raw,
            duration_ms=int((time.monotonic() - t0) * 1000) if t0 else None,
        ))
        log(f"  {'✓' if success else '✗'} {label}: {detail}")

    # ── 0. 排空错误队列 (先读空, 判据同兄弟序列: None ≠ 干净) ──
    stale: List[str] = []
    for _ in range(100):
        raw_e = await _q("SYST:ERR?")
        code_e, _t = _parse_err(raw_e or "")
        if code_e is None:
            return SequenceRunResult(
                success=False,
                steps=steps,
                summary=(
                    "开跑前排空错误队列失败: SYST:ERR? 回复读不出错误码 — "
                    "会话状态未知, 不能带着它做写动作。先跑 uxm_scpi_compatibility 排障。"
                ),
            )
        if code_e == 0:
            break
        stale.append(raw_e or "")
    if stale:
        extra["stale_errors_cleared"] = stale
        log(f"  · 清掉 {len(stale)} 条遗留错误")

    # ── 1. R7 取证 (纯本地读, 不发 SCPI) ──
    binding_topo = None
    cfg = getattr(bs, "config", None)
    if isinstance(cfg, dict):
        binding_topo = cfg.get("topology_profile_id")
    default_topo = getattr(bs, "_default_topology_profile_id", None)
    _step(
        "R7 topology 选择取证",
        True,
        f"binding 显式选择={binding_topo!r} / 系统默认={default_topo!r} — "
        f"binding 非空时它压过系统默认 (改默认等于没改)",
    )
    extra["r7"] = {"binding": binding_topo, "default": default_topo}

    # ── 2. R2 对照: 开关回声 vs 协议栈状态 ──
    raw_switch = await _q(switch_t.format(cell=cell))
    _step("R2a 开关回读 ACTive:STATe?", raw_switch is not None,
          "自己写进去的 0/1 开关的回声, 不是状态", raw=raw_switch)
    raw_status = await _q(status_q_t.format(cell=cell))
    _step(
        "R2b 小区状态 BSE:STATus?", raw_status is not None,
        f"协议栈真话 (手册枚举 OFF|ON|CONNected|IDLE|AGGRegated|ACTivated); "
        f"对照: 开关={raw_switch!r} vs 状态={raw_status!r}",
        raw=raw_status,
    )
    extra["r2"] = {"active_state": raw_switch, "status": raw_status}

    # ── 3. 前提门: 小区必须在 ON (查了状态才决定发不发; 不在 ON 就不发) ──
    if (raw_switch or "").strip() != "1":
        return SequenceRunResult(
            success=False,
            steps=steps,
            extra=extra,
            summary=(
                f"R4 前提不成立: 小区开关={raw_switch!r} (需 '1'/ON)。本探针不自作"
                f"主张开小区 — 先用正常流程把小区配好激活, 再跑本探针。"
                f"R2/R7 证据已采集 (见 steps)。"
            ),
        )

    # ── 4. R4 剧本: 写不 APPLY → 回读判缓存/生效 → 恢复 ──
    raw_orig = await _q(arfcn_t.format(cell=cell) + "?")
    try:
        orig_arfcn = int(float((raw_orig or "").strip()))
    except ValueError:
        return SequenceRunResult(
            success=False, steps=steps, extra=extra,
            summary=f"原 ARFCN 回读不可解析: {raw_orig!r} — 不敢在未知基线上做写动作。",
        )
    _step("R4a 原 ARFCN 回读", True, f"基线 = {orig_arfcn}", raw=raw_orig)
    extra["orig_arfcn"] = orig_arfcn

    test_arfcn = int(params.get("test_arfcn", 634666))
    if test_arfcn == orig_arfcn:
        test_arfcn = 636666 if orig_arfcn != 636666 else 634666
        log(f"  · 测试值与当前值相同, 改用 {test_arfcn}")

    wrote_test_value = False
    restored_ok = False
    try:
        t0 = time.monotonic()
        await _w(f"{arfcn_t.format(cell=cell)} {test_arfcn}")
        wrote_test_value = True
        _step("R4b 写测试 ARFCN (不 APPLY)", True, f"写入 {test_arfcn}", t0=t0)
        code = await _err_after("R4b")
        if code not in (0,):
            # 写被拒 (如 ON 态 -221): 本身就是有效观测 — ON 态直写到底收不收,
            # 也是链路真相的一部分; 不再继续回读判定。
            extra["r4_verdict"] = f"写被拒 (SYST:ERR 码 {code}) — ON 态直写不被接受"
        else:
            raw_rb = await _q(arfcn_t.format(cell=cell) + "?")
            try:
                rb = int(float((raw_rb or "").strip()))
            except ValueError:
                rb = None
            if rb == test_arfcn:
                verdict = (
                    "回读=新值(缓存) ⇒ R4 坐实: BSE:CONFig:...? 在 APPLY 前读的是"
                    "上层缓存 — APPLY 前对账=假绿, 判绿必须靠二层 (STATus/一致性网)"
                )
            elif rb == orig_arfcn:
                verdict = (
                    "回读=旧值(生效值) ⇒ R4 证伪: 回读反映协议栈生效值 — D3 一层"
                    "对账即有效, APPLY 仍必须发 (R3 独立成立)"
                )
            else:
                verdict = f"回读={raw_rb!r} 既非新值也非旧值 — 形态未知, 记录待判"
            _step("R4c 不 APPLY 回读判定", True, verdict, raw=raw_rb)
            extra["r4_verdict"] = verdict

            raw_status2 = await _q(status_q_t.format(cell=cell))
            _step("R4d 扰动观察 BSE:STATus?", True,
                  f"写后未 APPLY 的小区状态 (对照写前 {raw_status!r})", raw=raw_status2)
    finally:
        # ── 5. 恢复: 无论上面走到哪一步, 只要写过测试值就必须恢复 ──
        if wrote_test_value:
            try:
                await _w(f"{arfcn_t.format(cell=cell)} {orig_arfcn}")
                code_wb = await _err_after("R5a 写回原 ARFCN")
                await _w(apply_cmd)
                code_ap = await _err_after("R5b APPLY (清挂起, 恢复干净态)")
                raw_final = await _q(arfcn_t.format(cell=cell) + "?")
                try:
                    final_matches = (
                        int(float((raw_final or "").strip())) == orig_arfcn
                    )
                except ValueError:
                    final_matches = False
                # #236 Codex P2: 终读一致**不够** — R4 本身证明回读可能是
                # 缓存回声, 写回/APPLY 被拒时回读照样回显原值。恢复确认必须
                # 三条同时成立: 终读=原值 且 两次 SYST:ERR? 都干净 (0)。
                restored_ok = (
                    final_matches and code_wb == 0 and code_ap == 0
                )
                _step(
                    "R5c 恢复终读确认",
                    restored_ok,
                    (f"终读={raw_final!r} 期望 {orig_arfcn}; 写回错误码={code_wb} "
                     f"APPLY 错误码={code_ap}")
                    + ("" if restored_ok else
                        f" — ⚠ 恢复未确认! 人工执行: "
                        f"{arfcn_t.format(cell=cell)} {orig_arfcn} 然后 "
                        f"{apply_cmd}, 再回读核对"),
                    raw=raw_final,
                )
            except Exception as e:  # noqa: BLE001
                _step(
                    "R5 恢复动作抛异常",
                    False,
                    f"{type(e).__name__}: {e} — ⚠ 仪器可能停在测试 ARFCN "
                    f"{test_arfcn}! 人工执行: {arfcn_t.format(cell=cell)} "
                    f"{orig_arfcn} 然后 {apply_cmd}",
                )

    ok = restored_ok
    return SequenceRunResult(
        success=ok,
        steps=steps,
        extra=extra,
        summary=(
            f"R4 判定: {extra.get('r4_verdict', '未获得')} | R2 对照: 开关="
            f"{raw_switch!r} vs 状态={raw_status!r} | R7: binding={binding_topo!r} "
            f"默认={default_topo!r} | 恢复{'确认 OK' if ok else '⚠ 未确认 — 见 R5 步骤'}"
            f" — 结论抄回 docs/design/p0-2-uxm-config-single-source-design.md §7"
        ),
    )
