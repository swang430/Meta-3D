"""F64 输入信号参考操作点闭环控制 (P0-8 Step 2 Phase 2).

跨 driver 操作点子系统: 协调 BS (UXM, 设 DL 功率) + CE (F64, autoset/校验), 跑
设计文档 §4 的 A-F 闭环, 输出收敛的下行静态参考 + 遥测。

设计依据: docs/architecture/f64-input-level-and-dynamic-range.md
- §3.3 当前决策: **下行静态 AUTOSET** (输入稳, path loss 保真)。
- §3.4 AGC keep pathloss 适用场景 (上行/WiFi/双向) **不实现**, 仅留 mode 接口。
- §4 闭环流程 A-F: 粗设 UXM 功率 → F64 设 burst+trigger → autoset → 校验 (窗口 +
  clipping + cut-off) → 调 UXM 功率重试 → 收敛 → 锁静态参考。
- §5 落点: 跨 driver 操作点服务, 不埋 commissioning 一个 phase。

本期范围 (Phase 2, offline 可写可测):
- 独立服务 + 单测 (mock UXM+F64), **不接 commissioning measure phase** (留 Phase 2b)。
- 默认参数提供; 真值现场标定 (roadmap U-6)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.hal.propsim_f64 import F64InputMeasMode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InputOperatingPoint:
    """F64 单输入的操作点 (autoset 收敛后的 avg + crest)。"""
    input_num: int
    avg_dbm: float
    crest_db: float


@dataclass(frozen=True)
class InputLevelResult:
    """闭环收敛结果 (success=True) 或失败 (success=False + failure_reason)。

    遥测字段 (operating_point / clipping / warnings / iterations) 始终填, 便于
    诊断和后续上送 readiness/cockpit。
    """
    success: bool
    operating_point: List[InputOperatingPoint] = field(default_factory=list)
    uxm_dl_power_dbm: Optional[float] = None
    clipping_per_mille: Optional[float] = None
    system_warnings: List[str] = field(default_factory=list)
    iterations: int = 0
    failure_reason: Optional[str] = None


class InputLevelController:
    """跨 driver 下行静态操作点闭环 (CE↔BS)。

    用法::

        ctrl = InputLevelController(ce_driver, bs_driver)
        result = await ctrl.establish()
        if result.success:
            ...  # 锁定的操作点 result.operating_point
        else:
            ...  # result.failure_reason

    依赖的 driver 方法:
        BS: ``set_downlink_power(dbm) -> bool``
        CE: ``set_input_measurement_mode(in, mode)`` / ``set_burst_trigger_level`` /
            ``autoset_all_inputs`` (fail-loud) / ``measure_input`` /
            ``get_input_level_limits`` / ``get_group_clipping`` / ``get_system_status``

    AGC keep pathloss (上行/WiFi/双向) **不实现**, 设计 §3.4 记录, 仅留 mode 形参。
    """

    # 模式 (当前只支持下行静态; AGC keep pathloss 留接口、不实现)
    MODE_DL_STATIC = "dl_static"

    def __init__(
        self,
        ce_driver,
        bs_driver,
        *,
        # —— 收敛参数 (现场真值标定见 roadmap U-6) ——
        initial_uxm_dl_power_dbm: float = -10.0,
        target_avg_offset_below_upper_db: float = 15.0,  # 目标 avg ≤ upper - 15
        autoset_measurement_time_s: float = 3.0,
        burst_trigger_dbm: float = -30.0,
        clipping_threshold_per_mille: float = 1.0,
        uxm_power_step_db: float = 3.0,
        max_iterations: int = 5,
        # —— 通用 ——
        active_inputs: Tuple[int, ...] = (1, 2, 3, 4),
        group_num: int = 1,
        mode: str = MODE_DL_STATIC,
    ):
        if mode != self.MODE_DL_STATIC:
            raise NotImplementedError(
                f"mode={mode!r} 暂不支持 (AGC keep pathloss 留 WiFi/双向, 见设计 §3.4)"
            )
        self._ce = ce_driver
        self._bs = bs_driver
        self._initial_uxm = initial_uxm_dl_power_dbm
        self._target_offset = target_avg_offset_below_upper_db
        self._autoset_t = autoset_measurement_time_s
        self._burst_trigger = burst_trigger_dbm
        self._clip_thresh = clipping_threshold_per_mille
        self._uxm_step = uxm_power_step_db
        self._max_iter = max_iterations
        self._inputs = tuple(active_inputs)
        self._group = group_num

    async def establish(self) -> InputLevelResult:
        """跑下行静态闭环, 返回收敛结果或失败原因。"""
        uxm_power = self._initial_uxm

        for iteration in range(1, self._max_iter + 1):
            logger.info(
                "[InputLevelController] 第 %d/%d 轮: 试 UXM DL=%.1f dBm",
                iteration, self._max_iter, uxm_power,
            )

            # A: 粗设 UXM DL 功率
            if not await self._bs.set_downlink_power(uxm_power):
                return InputLevelResult(
                    success=False, iterations=iteration, uxm_dl_power_dbm=uxm_power,
                    failure_reason=f"bs.set_downlink_power({uxm_power}) 失败",
                )

            # C: F64 设 burst 模式 + 触发电平 (TDD 5G DL 必须, 见设计 §1.1)
            mode_err = await self._configure_burst_mode()
            if mode_err is not None:
                return InputLevelResult(
                    success=False, iterations=iteration, uxm_dl_power_dbm=uxm_power,
                    failure_reason=mode_err,
                )

            # D: AUTOSET 所有输入 (Phase 1 fail-loud: device error → False)
            if not await self._ce.autoset_all_inputs(self._autoset_t):
                # autoset 失败 (无信号/过强) → 调 UXM 功率重试。
                # heuristic: 第一轮多半是信号弱/未到 → 升; 后续可能是过强 → 降。
                if iteration == 1:
                    uxm_power += self._uxm_step
                else:
                    uxm_power -= self._uxm_step
                logger.warning(
                    "[InputLevelController] autoset 失败, 调 UXM → %.1f dBm 重试",
                    uxm_power,
                )
                continue

            # E: 测每输入 avg + crest + 校验窗口
            (op_point, out_lo, out_hi, meas_err) = await self._measure_and_check_window()
            if meas_err is not None:
                return InputLevelResult(
                    success=False, iterations=iteration, uxm_dl_power_dbm=uxm_power,
                    operating_point=op_point, failure_reason=meas_err,
                )

            # F: clipping + 系统警告 (cut-off)
            clipping = await self._ce.get_group_clipping(self._group, reset=True)
            status = await self._ce.get_system_status()
            warnings: List[str] = list(status[1]) if status else []
            cut_off = any(
                "cut-off" in w.lower() or "cut_off" in w.lower() or "cutoff" in w.lower()
                for w in warnings
            )
            clip_bad = clipping is not None and clipping > self._clip_thresh

            converged = (
                not out_lo and not out_hi and not clip_bad and not cut_off
            )
            if converged:
                logger.info(
                    "[InputLevelController] 收敛 (iter=%d, UXM=%.1f dBm, clipping=%s‰)",
                    iteration, uxm_power, clipping,
                )
                return InputLevelResult(
                    success=True,
                    operating_point=op_point,
                    uxm_dl_power_dbm=uxm_power,
                    clipping_per_mille=clipping,
                    system_warnings=warnings,
                    iterations=iteration,
                )

            # 调整 UXM 功率重试
            if clip_bad or cut_off or out_hi:
                uxm_power -= self._uxm_step  # 过高
            elif out_lo:
                uxm_power += self._uxm_step  # 过低
            logger.info(
                "[InputLevelController] 未收敛 (clip=%s‰, cut_off=%s, oow_lo=%s, oow_hi=%s) → UXM→%.1f",
                clipping, cut_off, out_lo, out_hi, uxm_power,
            )

        return InputLevelResult(
            success=False, iterations=self._max_iter, uxm_dl_power_dbm=uxm_power,
            failure_reason=f"{self._max_iter} 轮未收敛",
        )

    # —— 内部辅助 ——

    async def _configure_burst_mode(self) -> Optional[str]:
        """对每个 active input 设 BURST 模式 + burst 触发电平; 失败返回原因字符串。"""
        for in_num in self._inputs:
            if not await self._ce.set_input_measurement_mode(in_num, F64InputMeasMode.BURST):
                return f"set BURST mode failed on input {in_num}"
            if not await self._ce.set_burst_trigger_level(in_num, self._burst_trigger):
                return f"set burst trigger failed on input {in_num}"
        return None

    async def _measure_and_check_window(
        self,
    ) -> Tuple[List[InputOperatingPoint], bool, bool, Optional[str]]:
        """测每输入 avg+crest + 校验窗口。

        返回 (操作点列表, out_of_window_low, out_of_window_high, 失败原因)。
        out_lo = avg < hard_lower; out_hi = avg > (upper - target_offset) (软目标,
        留 crest headroom)。limits 查询失败的输入只记 avg/crest, 不参与窗口判定。
        """
        op_point: List[InputOperatingPoint] = []
        out_lo = False
        out_hi = False
        for in_num in self._inputs:
            meas = await self._ce.measure_input(in_num, 1.0)
            if meas is None:
                return op_point, out_lo, out_hi, f"measure_input({in_num}) 失败 (无信号)"
            avg, crest = meas
            op_point.append(InputOperatingPoint(in_num, avg, crest))
            limits = await self._ce.get_input_level_limits(in_num)
            if limits is None:
                continue
            lo, hi = limits
            target_max = hi - self._target_offset
            if avg < lo:
                out_lo = True
            elif avg > target_max:
                out_hi = True
        return op_point, out_lo, out_hi, None
