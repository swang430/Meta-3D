"""Quick base-station attach + UE info probe.

Sets a minimal cell config on the bound baseStation, kicks signaling, waits
for a DUT to attach, and reports UE capability + RRC info if it does.

Use this when commissioning or path-loss looks fine but throughput is zero
— it isolates "is the DUT actually camping on our cell?" from the rest of
the chain.

Does mutate state (start_signaling), so `safe_during_test=False`.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
    SequenceStepResult,
)
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="Base station attach probe",
    description=(
        "Configures one cell, starts signaling, waits up to N seconds for "
        "DUT attach, queries UE capability + RRC info. Strictly a debug "
        "probe — leaves the BS in a signaling state, run the cleanup "
        "sequence or stop the BS yourself when done."
    ),
    required_categories=["baseStation"],
    # CE 是**可选依赖**：线缆直连场景（lab 无 CE binding）本序列跳过直通继续跑，
    # 所以不能写进 required（那会把该场景 422 拦掉）。但 CE 在场时序列体确实调它
    # （下方 `drivers.get("channelEmulator")` → `stop_emulation` /
    # `set_passthrough_mode`），必须取租约让它进 Remote —— 否则它停在 park 后的
    # Local 态，一调就返 False，整条 attach 失败还把人指向 F64 状态机（内审 F3）。
    optional_categories=["channelEmulator"],
    # agent R6 复核 F3: schema default 与 run() 默认同源 — GUI 表单按 schema
    # 预填并全量显式提交, 只改 run() 默认会被 GUI 主路径击穿
    params_schema=[
        {"name": "frequency_mhz", "label": "频率 (MHz)", "type": "number", "default": 3549.99},
        {"name": "bandwidth_mhz", "label": "带宽 (MHz)", "type": "number", "default": 40},
        {"name": "scs_khz", "label": "SCS (kHz)", "type": "number", "default": 30},
        {"name": "band", "label": "Band", "type": "string", "default": "n78"},
        {"name": "dl_power_dbm", "label": "RS EPRE (dBm)", "type": "number", "default": -46},
        {"name": "attach_timeout_s", "label": "Attach 等待 (秒)", "type": "number", "default": 15},
        {"name": "establish_f64_passthrough", "label": "F64 直通预备 (attach 默认态)",
         "type": "boolean", "default": True},
        # 开关 2: 3=Calibration (默认, -10dB 零相位, 07-03 -96 RSRP 实证) /
        # 2=Butler (官方为建 MIMO 链设计, 4 层配置起不来时切) / 1=模型旁路
        {"name": "f64_bypass_mode", "label": "F64 直通模式 (3=校准/2=Butler/1=模型)",
         "type": "number", "default": 3},
    ],
    safe_during_test=False,
)


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
            success=False,
            summary=driver_not_loaded_summary("baseStation"),
        )

    # P1-14: hardware probe is meaningless against a mock driver —
    # refuse with an actionable summary instead of running the
    # identity/SCPI checks against canned/empty mock values.
    refusal = mock_driver_refusal_summary("baseStation", bs)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)

    # agent R6 F2: 默认对齐 2026-07-03 现场实证 attach 基线 (EMQuest n78:
    # ARFCN 636666 = 3549.99 MHz / BW40 / RS EPRE -46) — 本序列的使命是复刻
    # 已实证的 attach 直通编排, 不是任意频率探索
    freq_mhz = float(params.get("frequency_mhz", 3549.99))
    bw_mhz = float(params.get("bandwidth_mhz", 40))
    scs_khz = int(params.get("scs_khz", 30))
    band = str(params.get("band", "n78"))
    dl_power_dbm = float(params.get("dl_power_dbm", -46))
    timeout_s = float(params.get("attach_timeout_s", 15))

    steps: list[SequenceStepResult] = []

    class _StepReturnedFalse(RuntimeError):
        """哨兵: False 分支已记录失败 step, except 不得二次 append (Codex #199 P3)。"""

    async def _step(label: str, coro):
        started = time.monotonic()
        try:
            result = await coro
            # Codex #195 R5 P1 同族: HAL 布尔契约 (connect/set_cell_config/
            # start_signaling) False = 失败不抛 — 不拦会记成 success 继续跑。
            if result is False:
                steps.append(SequenceStepResult(
                    label=label,
                    success=False,
                    detail="returned False (HAL 布尔契约失败, 明细见驱动日志)",
                    duration_ms=int((time.monotonic() - started) * 1000),
                ))
                log(f"  ✗ {label}: returned False")
                raise _StepReturnedFalse(f"{label} returned False")
            steps.append(SequenceStepResult(
                label=label,
                success=True,
                detail=str(result) if result is not None else "ok",
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            log(f"  ✓ {label}")
            return result
        except _StepReturnedFalse:
            raise  # 已记录, 只中止序列 (外层 except 收敛成 success=False)
        except Exception as e:  # noqa: BLE001
            steps.append(SequenceStepResult(
                label=label,
                success=False,
                detail=f"{type(e).__name__}: {e}",
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            log(f"  ✗ {label}: {e}")
            raise

    try:
        await _step("connect", bs.connect())

        # P2-17 ②: attach 默认直通态 — DUT 好接入 (2026-07-03 -96 RSRP 直通
        # 实证); 直通稳态 = STOPPED + STATIC 3。run/measure 的衰落恢复由驱动
        # start_emulation 内建 GO 前清直通 (P2-17 ①), 本序列只建立不负责恢复。
        # CE 不在 required_categories: 无真实 CE (线缆直连场景) 跳过继续;
        # CE 在场但直通失败 = fail-loud (衰落在跑 attach 大概率失败, 不硬闯)。
        if bool(params.get("establish_f64_passthrough", True)):
            # Codex #201 R2 P2: lab binding 是第一道门 — HAL drivers 是全局的,
            # 线缆直连 lab (无 CE binding) 撞上别的 setup 残留的 F64 驱动时,
            # 不得去停/切不属于本 lab 的 CE。
            ce_configured = (
                ctx.find_binding_by_category_key("channelEmulator") is not None
            )
            ce = drivers.get("channelEmulator") if ce_configured else None
            if not ce_configured:
                steps.append(SequenceStepResult(
                    label="F64 passthrough (skipped)",
                    success=True,
                    detail="本 lab 未配置 channelEmulator — 线缆直连场景, 跳过",
                ))
                log("  · F64 passthrough skipped (no CE binding)")
            elif ce is None:
                # Codex #201 P2: lab 配置了 CE 但驱动没加载 — 不是线缆直连,
                # F64 停在任意模式会让 attach 失败被误诊成 DUT/RF 问题。
                return SequenceRunResult(
                    success=False,
                    summary=driver_not_loaded_summary("channelEmulator"),
                    steps=steps,
                )
            elif not getattr(ce, "SUPPORTS_STATIC_PASSTHROUGH", False):
                # Codex #201 P2: 能力标志 gate (hasattr 对 FS16/mock 误开 —
                # set_passthrough_mode 在基类, FS16 高层 NotImplementedError);
                # attach 探针不是 F64 专属, 非 F64 CE 跳过不硬闯。
                steps.append(SequenceStepResult(
                    label="F64 passthrough (skipped)",
                    success=True,
                    detail=(
                        f"CE 驱动 {type(ce).__name__} 无 STATIC 直通能力标志 "
                        f"(SUPPORTS_STATIC_PASSTHROUGH) — 跳过"
                    ),
                ))
                log("  · F64 passthrough skipped (CE lacks static-passthrough capability)")
            else:
                # 开关 2: 直通模式参数化 (3=Calibration 默认 / 2=Butler / 1=模型)。
                # Codex #216 P2: 不在此层 int() 强转 — JSON true 会被转成 1 绕过
                # 驱动的 bool 拒绝 (静默切到 STATIC 1)。原始值透传, 守门单点在
                # 驱动 set_passthrough_mode (bool/0/非法 → False 布尔契约)。
                bypass_mode = params.get("f64_bypass_mode", 3)
                await _step("F64 stop_emulation (直通稳态前置)", ce.stop_emulation())
                await _step(
                    f"F64 passthrough (STATIC {bypass_mode})",
                    ce.set_passthrough_mode(mode=bypass_mode),
                )

        # agent R6 F2: 频率显式换算 ARFCN (与 measure 链同模式) — driver 的
        # frequency_mhz 只用于 band 推断不换算频点, 不传 arfcn 会落到 band
        # fallback (基线值), 用户自定义频率就静默错频; 默认 3549.99 → 636666
        # 命中 n78 基线 → 5b 自动补 SSB/PointA 三件套
        from app.hal.nr_arfcn import freq_mhz_to_nr_arfcn

        arfcn = freq_mhz_to_nr_arfcn(freq_mhz)
        await _step(
            f"set_cell_config {freq_mhz}MHz (ARFCN {arfcn}) / {bw_mhz}MHz / "
            f"{scs_khz}kHz / {band} / {dl_power_dbm}dBm",
            bs.set_cell_config({
                "frequency_mhz": freq_mhz,
                "arfcn": arfcn,
                "bandwidth_mhz": bw_mhz,
                "scs_khz": scs_khz,
                "band": band,
                "mimo_layers": 2,
                "dl_power_dbm": dl_power_dbm,
            }),
        )
        await _step("start_signaling", bs.start_signaling())

        # Wait for attach
        log(f"  · waiting up to {timeout_s:.0f}s for DUT attach...")
        attached = False
        ue_info: Dict[str, Any] | None = None
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if hasattr(bs, "get_ue_info"):
                try:
                    info = await bs.get_ue_info()
                    if info and info.get("connected"):
                        attached = True
                        ue_info = info
                        break
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.sleep(1.0)

        if not attached:
            steps.append(SequenceStepResult(
                label=f"DUT attach (timeout {timeout_s:.0f}s)",
                success=False,
                detail="No UE attached within timeout — DUT off, wrong band, or RF path broken",
            ))
            return SequenceRunResult(
                success=False,
                summary="DUT did not attach within timeout",
                steps=steps,
                extra={"attached": False},
            )

        steps.append(SequenceStepResult(
            label="DUT attach",
            success=True,
            detail=f"connected: {ue_info}",
        ))
        log(f"  ✓ DUT attached: {ue_info}")

        # Capability + RRC if the driver exposes them
        cap = None
        if hasattr(bs, "query_ue_capability"):
            cap = await _step("query_ue_capability", bs.query_ue_capability())

        return SequenceRunResult(
            success=True,
            summary="DUT attached and reported capability",
            steps=steps,
            extra={"ue_info": ue_info, "ue_capability": cap},
        )
    except Exception as e:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"Sequence aborted: {e}",
            steps=steps,
        )
