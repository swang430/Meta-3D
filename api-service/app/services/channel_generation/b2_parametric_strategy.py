"""B-2 参数化 TDL 注入策略 (P2-14 F6 — 路由骨架 + 能力门).

B-2 路: ChannelEgine `geometric_native_fit` / `native_fit_trajectory` 把 RT 射线聚成
native 可表示簇 → 每抽头参数 (native 谱/质心/展宽/角度) → `.tap/.rtc` → F64 硬件 FPGA
实时合成衰落 (绕开 F64 无 custom PSD, 免奈奎斯特覆盖全 f_D,max)。

本策略 (F6) 落地【路由 + 能力门】:
  - 校验 channelEmulator 支持 `PARAMETRIC_TDL` 加载模式 (否则 fail-loud)。
  - `.tap/.rtc` 生成 (RT→MPC→ChannelEgine→.tap) + F64 加载在 **F7 + 现场** 落地
    (V1.0 §9: `.tap` schema / gaussian 谱可用性 / f_upd_max 等待真机标定)。

设计: docs/design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md §6-§8。
"""

import logging
from typing import Any, Dict, List

from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode
from app.services.channel_generation.base_generator import BaseChannelGenerator

logger = logging.getLogger(__name__)


class B2ParametricTdlStrategy(BaseChannelGenerator):
    """B-2 参数化 TDL 策略: 路由 + 能力门就位; 生成/加载在 F7 + 现场。"""

    def __init__(
        self,
        emulator: ChannelEmulatorDriver,
        chamber_config: Any,
        calibration_entries: List[Dict],
    ):
        super().__init__(emulator, chamber_config, calibration_entries)

    def supports_parametric_tdl(self) -> bool:
        """channelEmulator 是否支持 PARAMETRIC_TDL (.tap/.rtc) 加载。"""
        return ChannelLoadMode.PARAMETRIC_TDL in self.emulator.get_supported_load_modes()

    async def generate_and_load(
        self,
        simulation_rules: Dict[str, Any],
        cdl_model_data: Dict[str, Any],
    ) -> bool:
        # 能力门: 仪器须支持参数化 TDL 加载
        if not self.supports_parametric_tdl():
            supported = [m.value for m in self.emulator.get_supported_load_modes()]
            logger.error(
                "[B2ParametricTdl] channelEmulator (%s) 不支持 PARAMETRIC_TDL (.tap/.rtc); "
                "engine_mode=B2_PARAMETRIC_TDL 无法执行。支持的加载模式: %s",
                type(self.emulator).__name__, supported,
            )
            return False

        # F7 + 现场: .tap/.rtc 生成 (RT→MPC→ChannelEgine geometric_native_fit→.tap) + F64 加载
        logger.error(
            "[B2ParametricTdl] B-2 路由与能力门就位, 但 .tap/.rtc 生成与 F64 加载在 F7 + 现场落地 "
            "(V1.0 §9: .tap schema / gaussian 谱可用性 / f_upd_max 待真机标定); 当前不可执行。"
            " session=%s model=%s",
            cdl_model_data.get("session_id"), cdl_model_data.get("model_name"),
        )
        return False
