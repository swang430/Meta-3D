"""Best-effort instrument cleanup for MIMO_OTA executors.

Used in finally-blocks so a half-finished measurement loop doesn't leave the
chamber in a hot state (UXM still signaling, F64 still emulating, turntable
parked at some random azimuth). Each step is wrapped in its own try/except
because cleanup must be idempotent and swallow secondary failures —
re-raising here would mask the original error that triggered cleanup.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, List

from app.hal.base_station import BaseStationCleanupResult, BaseStationDriver
from app.hal.channel_emulator_manifest import (
    channel_emulator_implements,
    channel_emulator_manifest_of,
    channel_emulator_rejection,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChamberCleanupResult(Sequence[str]):
    """MEASURE cleanup truth plus the legacy warning-sequence projection."""

    warnings: list[str]
    base_station: BaseStationCleanupResult

    def __getitem__(self, index):
        return self.warnings[index]

    def __len__(self) -> int:
        return len(self.warnings)

    def __iter__(self) -> Iterator[str]:
        return iter(self.warnings)


async def cleanup_chamber_instruments(
    hal: Any,
    execution_id: Any,
    *,
    expected_operator_stop_generation: int | None = None,
) -> ChamberCleanupResult:
    """Stop signaling, confirm SAFE_IDLE, home positioner and stop emulation.

    Transport release is owned by ``instrument_test_lease`` and is deliberately
    absent here.  The result remains a warning sequence for legacy consumers.
    Never raises.

    ⚠️ `Never raises` 的边界（内审 R2 F1）：它承诺的是**仪器 / 驱动故障**不外抛
    —— 本函数在 `measure.py` 的 `finally:` 里，抛出会顶替掉触发收尾的原始异常。
    能力查询（`channel_emulator_implements`）唯一会抛的是**操作名拼错**这类编码
    笔误，那一格该穿透：它在第一次跑测试时就红，而不是在现场变成一次沉默的不停机。
    对象形态不对（没 manifest / 拿到的是 Mock 自动属性）一律回落成「不支持」
    并走下面那条 else 留痕，不抛。
    """
    warnings: List[str] = []
    stop_signaling_confirmed = False
    safe_idle_confirmed = False

    base_station = hal.drivers.get("baseStation")
    if base_station is not None:
        # Phase 2g: SCells must be removed before stop_signaling so the next
        # test starts with a clean PCell. Wrapped before the generic
        # stop/disconnect tuple so its failure doesn't skip those.
        remove_scells = getattr(base_station, "remove_all_secondary_cells", None)
        class_remove_scells = getattr(
            type(base_station), "remove_all_secondary_cells", None
        )
        if (
            callable(remove_scells)
            and (
                "remove_all_secondary_cells" in vars(base_station)
                or class_remove_scells
                is not BaseStationDriver.remove_all_secondary_cells
            )
        ):
            try:
                scells_removed = await remove_scells()
                if scells_removed is not True:
                    msg = (
                        "baseStation.remove_all_secondary_cells was not "
                        "confirmed during cleanup; residual SCells may remain"
                    )
                    warnings.append(msg)
                    logger.warning("[%s] %s", execution_id, msg)
            except Exception as e:  # noqa: BLE001
                msg = f"baseStation.remove_all_secondary_cells failed during cleanup: {e}"
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)

        for action_name, coro in (
            ("stop_signaling", lambda: base_station.stop_signaling()),
            ("ensure_safe_idle", lambda: base_station.ensure_safe_idle()),
        ):
            try:
                confirmed = await coro()
                if action_name == "stop_signaling":
                    stop_signaling_confirmed = confirmed is True
                else:
                    safe_idle_confirmed = confirmed is True
                if confirmed is not True:
                    msg = (
                        f"baseStation.{action_name} was not confirmed during cleanup"
                    )
                    warnings.append(msg)
                    logger.warning("[%s] %s", execution_id, msg)
            except Exception as e:  # noqa: BLE001
                msg = f"baseStation.{action_name} failed during cleanup: {e}"
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)

    positioner = hal.drivers.get("positioner")
    if positioner is not None:
        # Best-effort home before disconnect — operator-friendly between runs.
        safe_to_disconnect = False
        try:
            move_kwargs = (
                {
                    "expected_operator_stop_generation":
                        expected_operator_stop_generation
                }
                if expected_operator_stop_generation is not None
                else {}
            )
            home_confirmed = await positioner.move_to(0.0, 0.0, **move_kwargs)
            if home_confirmed:
                safe_to_disconnect = True
            else:
                msg = (
                    "positioner.move_to(home) 被拒；编码器未证明回零，"
                    "cleanup 改为确认急停后再决定是否断开"
                )
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)
        except Exception as e:  # noqa: BLE001
            msg = f"positioner.move_to(home) failed during cleanup: {e}"
            warnings.append(msg)
            logger.warning("[%s] %s", execution_id, msg)
        if not safe_to_disconnect:
            try:
                safe_to_disconnect = await positioner.stop()
            except Exception as e:  # noqa: BLE001
                msg = f"positioner.stop failed during cleanup: {e}"
                warnings.append(msg)
                logger.error("[%s] %s", execution_id, msg)
            if not safe_to_disconnect:
                msg = (
                    "positioner 停止未确认；为保留 ABORT/VFBK 控制通道，"
                    "cleanup 不断开转台会话，需人工核对"
                )
                warnings.append(msg)
                logger.error("[%s] %s", execution_id, msg)

        if safe_to_disconnect:
            try:
                await positioner.disconnect()
            except Exception as e:  # noqa: BLE001
                msg = f"positioner.disconnect failed during cleanup: {e}"
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)

    emulator = hal.drivers.get("channelEmulator")
    # P2-57：换源到 manifest（hasattr 在基类补桩后恒为真）
    if emulator is not None and channel_emulator_implements(
        emulator, "stop_emulation"
    ):
        try:
            # #206 后 stop_emulation 的 False 带真实语义 (GOS 被拒, 仪器可能
            # 仍在发射) — 尽力而为语境不 abort, 但要进 warnings 可见
            if not await emulator.stop_emulation():
                msg = (
                    "channelEmulator.stop_emulation 被拒 (GOS SYST:ERR?, "
                    "仪器可能仍在发射) — cleanup 继续但需人工确认"
                )
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)
        except Exception as e:  # noqa: BLE001
            msg = f"channelEmulator.stop_emulation failed during cleanup: {e}"
            warnings.append(msg)
            logger.warning("[%s] %s", execution_id, msg)
    elif emulator is not None:
        # ⚠️ 内审 F2：**跳过停机必须留痕**。此前这里没有 else，manifest 少报或
        #    操作名拼错都会让收尾**静默不发停机** —— 而同一段代码上面刚写着
        #    「仪器可能仍在发射」。两个方向的代价不对称：误判「支持」只是多一行
        #    warning，误判「不支持」是操作员零信号地把仪器留在发射态。
        # ⚠️ 风险措辞要**分两种**（内审 R3 F6）：初版对所有情况都写「仪器可能仍在
        #    发射」，而 FS16 根本没有仿真引擎、不可能在发射 —— 那句话对它是假的，
        #    却会随**每一次**执行落进 `cleanup_warnings`。恒定的假警报比没有警报更
        #    坏：它训练操作员忽略这一条，等真出事时那条 warning 已经没人看了。
        #    判据从 manifest 自己派生：连 start_emulation 都没实现的型号，
        #    本链路不会让它进入发射态。
        # ⚠️ 安静侧的条件必须是「**全部**致发射路径都未实现」（内审 R4 F2）。
        #    初版只看 `start_emulation` —— 而 CE 至少有三条把射频送出去的路：
        #    仿真播放、直通（`measure.py` 的直通态测量就靠它，注释写着直通稳态下
        #    输出功率显示冻结 = 信号在走）、校准音（`path_loss_calibration_service`
        #    自己的失败文案就是「CE 可能仍在发」）。只看一条，一个「能直通/能发
        #    校准音、但没实现 start_emulation」的驱动会被告知「不会进入发射态」——
        #    那是**假的安心**，比 R4 F6 治的假警报更坏：假警报只是噪声，假安心
        #    让人不去查。而 cleanup 本身既不停直通也不停校准音。
        #
        # ⚠️ 覆盖不对称，如实记（内审 R5 F3）：这条 warning 只在**跳过停机**时发，
        #    而会进直通的驱动（F64 与 Mock —— 两家都声明了 set_passthrough_mode，
        #    初版这里写「F64 是唯一」，经不起 grep，内审 R6 F3 抓出）都实现了
        #    stop_emulation、走的是上面那个 if，
        #    所以「直通态从来没人撤」那个既有缺口本条**管不着** ——
        #    `clear_passthrough_mode` 全仓只有 path_loss_calibration_service 一个
        #    调用方，`stop_emulation` 只发 GOS、不清 STATIC。该缺口先于本片存在，
        #    按 ⑦ 不在本片修，已在 PR 里报告待 triage。
        _TRANSMIT_PATHS = (
            "start_emulation", "set_passthrough_mode", "set_calibration_tone",
        )
        # ⚠️ 还要看 **load_modes 这条轴**（内审 R5 F2）：`load_channel` /
        #    `set_channel_model` / `load_parametric_tdl` 都**不在**那 14 个操作里，
        #    所以"能不能把射频送出去"在 op 轴上表达不完整。一个声明
        #    `load_modes=[external_waveform: implemented]`（能加载并播放波形）
        #    而三个 op 全未实现的驱动，只看 op 轴会被判进安静侧 —— 那正是 FS16
        #    从前**被声称**的形态（"只做文件回放"），也正是本片刚撕掉的那个假声明。
        _manifest = channel_emulator_manifest_of(emulator)
        if _manifest is None or _manifest.supported_load_modes() or any(
            _manifest.implements(op) for op in _TRANSMIT_PATHS
        ):
            _risk = "仪器可能仍在发射"
        else:
            _risk = "该型号未实现任何发射路径，本链路不会让它进入发射态"
        msg = (
            "channelEmulator 未声明实现 stop_emulation，cleanup **跳过了停机** "
            f"({_risk}) — "
            + channel_emulator_rejection(emulator, "stop_emulation")
        )
        warnings.append(msg)
        logger.warning("[%s] %s", execution_id, msg)

    return ChamberCleanupResult(
        warnings=warnings,
        base_station=BaseStationCleanupResult(
            stop_signaling_confirmed=stop_signaling_confirmed,
            safe_idle_confirmed=safe_idle_confirmed,
            warnings=tuple(warnings),
        ),
    )
