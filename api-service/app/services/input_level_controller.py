"""F64 输入信号参考操作点闭环控制 (P0-8 Step 2 Phase 2).

跨 driver 操作点子系统: 协调 BS (设 DL 功率) + CE (F64, autoset/校验), 跑
设计文档 §4 的 A-F 闭环, 输出收敛的下行静态参考 + 遥测。

设计依据: docs/architecture/f64-input-level-and-dynamic-range.md
- §3.3 当前决策: **下行静态 AUTOSET** (输入稳, path loss 保真)。
- §3.4 AGC keep pathloss 适用场景 (上行/WiFi/双向) **不实现**, 仅留 mode 接口。
- §4 闭环流程 A-F: 粗设基站功率 → F64 设 burst+trigger → autoset → 校验 (窗口 +
  clipping + cut-off) → 调基站功率重试 → 收敛 → 锁静态参考。
- §5 落点: 跨 driver 操作点服务, 不埋 commissioning 一个 phase。

本期范围 (Phase 2, offline 可写可测):
- 独立服务 + 单测 (mock BaseStation+F64), **不接 commissioning measure phase** (留 Phase 2b)。
- 默认参数提供; 真值现场标定 (roadmap U-6)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

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
    base_station_dl_power_dbm: Optional[float] = None
    clipping_per_mille: Optional[float] = None
    system_warnings: List[str] = field(default_factory=list)
    iterations: int = 0
    failure_reason: Optional[str] = None
    # #2001(1): 多端口 input 不平衡 = max(avg) - min(avg) 跨 input。status: ok/marginal/
    # excessive/None(单 input)。收敛时填; surface 不阻断 (容忍带见 _classify_imbalance)。
    imbalance_db: Optional[float] = None
    imbalance_status: Optional[str] = None

    @property
    def uxm_dl_power_dbm(self) -> Optional[float]:
        """旧 UXM 字段的只读同源镜像；新消费方使用公共字段。"""

        return self.base_station_dl_power_dbm


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
        initial_base_station_dl_power_dbm: float = -10.0,
        target_avg_offset_below_upper_db: float = 15.0,  # 目标 avg ≤ upper - 15
        autoset_measurement_time_s: float = 3.0,
        burst_trigger_dbm: float = -30.0,
        clipping_threshold_per_mille: float = 1.0,
        base_station_power_step_db: float = 3.0,
        max_iterations: int = 5,
        # —— 多端口 imbalance 容忍带 (#2001(1)): 4x4 各 input avg 间距 ±1-2.5dB 物理必然
        #    (cable 长度/质量/接头/ADC 增益), surface 不阻断; per-port cable cal 补偿是 (2)(3) ——
        imbalance_marginal_db: float = 1.0,    # ≤ 此 = ok
        imbalance_excessive_db: float = 2.5,   # marginal..excessive ≤ 此; 之上 = excessive
        # —— 通用 ——
        active_inputs: Tuple[int, ...] = (1, 2, 3, 4),
        group_num: int = 1,
        mode: str = MODE_DL_STATIC,
        channel_operation_recorder: Any | None = None,
    ):
        if mode != self.MODE_DL_STATIC:
            raise NotImplementedError(
                f"mode={mode!r} 暂不支持 (AGC keep pathloss 留 WiFi/双向, 见设计 §3.4)"
            )
        self._ce = ce_driver
        self._bs = bs_driver
        self._initial_base_station = initial_base_station_dl_power_dbm
        self._target_offset = target_avg_offset_below_upper_db
        self._autoset_t = autoset_measurement_time_s
        self._burst_trigger = burst_trigger_dbm
        self._clip_thresh = clipping_threshold_per_mille
        self._base_station_step = base_station_power_step_db
        self._max_iter = max_iterations
        self._imbalance_marginal = imbalance_marginal_db
        self._imbalance_excessive = imbalance_excessive_db
        self._inputs = tuple(active_inputs)
        self._group = group_num
        self._channel_operation_recorder = channel_operation_recorder

    async def _invoke_channel_operation(
        self,
        *,
        operation: str,
        requested: dict[str, Any],
        invoke: Any,
    ) -> bool:
        if self._channel_operation_recorder is None:
            return await invoke()
        return await self._channel_operation_recorder(
            phase="configure",
            operation=operation,
            requested=requested,
            invoke=invoke,
        )

    async def establish(self) -> InputLevelResult:
        """跑下行静态闭环, 返回收敛结果或失败原因。"""
        base_station_power = self._initial_base_station

        for iteration in range(1, self._max_iter + 1):
            logger.info(
                "[InputLevelController] 第 %d/%d 轮: 试 BaseStation DL=%.1f dBm",
                iteration, self._max_iter, base_station_power,
            )

            # A: 粗设基站 DL 功率
            if not await self._bs.set_downlink_power(base_station_power):
                return InputLevelResult(
                    success=False, iterations=iteration,
                    base_station_dl_power_dbm=base_station_power,
                    failure_reason=f"bs.set_downlink_power({base_station_power}) 失败",
                )

            # C: F64 设 burst 模式 + 触发电平 (TDD 5G DL 必须, 见设计 §1.1)
            mode_err = await self._configure_burst_mode()
            if mode_err is not None:
                return InputLevelResult(
                    success=False, iterations=iteration,
                    base_station_dl_power_dbm=base_station_power,
                    failure_reason=mode_err,
                )

            # D: AUTOSET 仅 active_inputs (子集 — 避免 INP:LEV:AUTOSET 0 对未连接输入
            #    触发 no-signal 错误, Codex on PR #96)。fail-loud: device error → False。
            if not await self._invoke_channel_operation(
                operation="autoset_inputs",
                requested={
                    "input_ports": list(self._inputs),
                    "measurement_time_s": self._autoset_t,
                },
                invoke=lambda: self._ce.autoset_inputs(
                    self._inputs, self._autoset_t
                ),
            ):
                # autoset 失败 (无信号/过强) → 调基站功率重试。
                # heuristic: 第一轮多半是信号弱/未到 → 升; 后续可能是过强 → 降。
                if iteration == 1:
                    base_station_power += self._base_station_step
                else:
                    base_station_power -= self._base_station_step
                logger.warning(
                    "[InputLevelController] autoset 失败, 调 BaseStation → %.1f dBm 重试",
                    base_station_power,
                )
                continue

            # E: 测每输入 avg + crest + 校验窗口
            (op_point, out_lo, out_hi, meas_err) = await self._measure_and_check_window()
            if meas_err is not None:
                return InputLevelResult(
                    success=False, iterations=iteration,
                    base_station_dl_power_dbm=base_station_power,
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
                imb_db, imb_status = self._classify_imbalance(op_point)
                if imb_status in ("marginal", "excessive"):
                    warnings = warnings + [
                        f"input imbalance {imb_db} dB ({imb_status}): 各 input avg 间距偏大 "
                        f"(> {self._imbalance_marginal} dB) — 检查 cable 长度/接头/per-port cal "
                        "(audit, 不阻断收敛; CTIA MPAC 容忍带, per-port 补偿见 #2001 (2)(3))"
                    ]
                logger.info(
                    "[InputLevelController] 收敛 (iter=%d, BaseStation=%.1f dBm, clipping=%s‰, "
                    "imbalance=%s dB %s)",
                    iteration, base_station_power, clipping, imb_db, imb_status,
                )
                return InputLevelResult(
                    success=True,
                    operating_point=op_point,
                    base_station_dl_power_dbm=base_station_power,
                    clipping_per_mille=clipping,
                    system_warnings=warnings,
                    iterations=iteration,
                    imbalance_db=imb_db,
                    imbalance_status=imb_status,
                )

            # 调整基站功率重试
            if clip_bad or cut_off or out_hi:
                base_station_power -= self._base_station_step  # 过高
            elif out_lo:
                base_station_power += self._base_station_step  # 过低
            logger.info(
                "[InputLevelController] 未收敛 (clip=%s‰, cut_off=%s, oow_lo=%s, oow_hi=%s) "
                "→ BaseStation→%.1f",
                clipping, cut_off, out_lo, out_hi, base_station_power,
            )

        return InputLevelResult(
            success=False, iterations=self._max_iter,
            base_station_dl_power_dbm=base_station_power,
            failure_reason=f"{self._max_iter} 轮未收敛",
        )

    # —— 内部辅助 ——

    def _classify_imbalance(
        self, op_point: List[InputOperatingPoint]
    ) -> Tuple[Optional[float], Optional[str]]:
        """多端口 input 不平衡 = max(avg) - min(avg) 跨 input。<2 input → (None, None)。

        容忍带 (#2001): 4x4 各 input avg ±1-2.5 dB 间距是物理必然 (cable 长度/质量 ±0.5-1dB +
        BS TX port ±0.3dB + F64 ADC 增益 ±0.5dB + 接头老化)。ok ≤ marginal < marginal..
        excessive ≤ excessive < excessive。surface 不阻断收敛 (per-port cable cal 补偿是 (2)(3))。
        """
        avgs = [op.avg_dbm for op in op_point]
        if len(avgs) < 2:
            return None, None
        imbalance = round(max(avgs) - min(avgs), 2)
        if imbalance <= self._imbalance_marginal:
            status = "ok"
        elif imbalance <= self._imbalance_excessive:
            status = "marginal"
        else:
            status = "excessive"
        return imbalance, status

    async def _configure_burst_mode(self) -> Optional[str]:
        """对每个 active input 设 BURST 模式 + burst 触发电平; 失败返回原因字符串。"""
        for in_num in self._inputs:
            if not await self._invoke_channel_operation(
                operation="set_input_measurement_mode",
                requested={
                    "input_port": in_num,
                    "mode": F64InputMeasMode.BURST.value,
                },
                invoke=lambda in_num=in_num: self._ce.set_input_measurement_mode(
                    in_num, F64InputMeasMode.BURST
                ),
            ):
                return f"set BURST mode failed on input {in_num}"
            if not await self._invoke_channel_operation(
                operation="set_burst_trigger_level",
                requested={
                    "input_port": in_num,
                    "trigger_dbm": self._burst_trigger,
                },
                invoke=lambda in_num=in_num: self._ce.set_burst_trigger_level(
                    in_num, self._burst_trigger
                ),
            ):
                return f"set burst trigger failed on input {in_num}"
        return None

    async def _measure_and_check_window(
        self,
    ) -> Tuple[List[InputOperatingPoint], bool, bool, Optional[str]]:
        """测每输入 avg+crest + 校验窗口。

        返回 (操作点列表, out_of_window_low, out_of_window_high, 失败原因)。
        out_lo = avg < hard_lower; out_hi = avg > (upper - target_offset) (软目标,
        留 crest headroom)。**limits 查询失败 → fail-fast** (Codex on PR #96: 无窗口
        就无法证明 avg 在限内, 不能默认通过)。
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
                # 无窗口 → 无法证明 avg 在限内, 不能默认通过 (Codex on PR #96)。
                return op_point, out_lo, out_hi, (
                    f"get_input_level_limits({in_num}) 失败: 无法验证操作点是否在窗口内"
                )
            lo, hi = limits
            target_max = hi - self._target_offset
            if avg < lo:
                out_lo = True
            elif avg > target_max:
                out_hi = True
        return op_point, out_lo, out_hi, None
