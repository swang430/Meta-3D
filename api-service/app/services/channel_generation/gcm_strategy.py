"""
GCM 原生信道合成策略 (Native Model Pipeline)

使用信道仿真器内置的信道建模引擎编译并播放信道模型。
例如 Keysight F64 的 Channel Studio GCM, R&S 的内置 3GPP 模型等。

本策略通过 ChannelEmulatorDriver.load_channel(NATIVE_MODEL) 调用,
不直接依赖任何具体仪器型号的驱动或控制器。
"""

import logging
from typing import Dict, Any

from app.services.channel_generation.base_generator import BaseChannelGenerator
from app.hal.channel_emulator import ChannelLoadMode

logger = logging.getLogger(__name__)


class NativeModelStrategy(BaseChannelGenerator):
    """
    使用仿真器内置信道建模引擎的策略 (Benchmarking Target)

    利用仪器内置的信道建模能力 (如 F64 的 Channel Studio GCM),
    直接在仪器内部编译 3GPP 参数并生成信道衰落数据。

    适用场景:
      - 基准对比测试 (与 MIMO-First 自研引擎进行 A/B 对照)
      - 标准信道模型快速加载 (无需外部计算)

    注意: 并非所有信道仿真器都支持此模式。
    策略初始化前应检查 emulator.get_supported_load_modes()。
    """

    async def generate_and_load(
        self,
        simulation_rules: Dict[str, Any],
        cdl_model_data: Dict[str, Any],
    ) -> bool:
        logger.info("[NativeModel Strategy] Starting native channel generation")

        model_name = cdl_model_data.get("model_name", "3GPP_CDL-C")
        scenario = cdl_model_data.get("scenario", "UMi")

        # 通过 HAL 统一接口加载, 不关心底层是 F64 还是 R&S
        logger.info(
            f"Commanding emulator to native-compile channel model: {model_name}"
        )

        success = await self.emulator.load_channel(
            mode=ChannelLoadMode.NATIVE_MODEL,
            model_name=model_name,
            scenario=scenario,
            parameters=simulation_rules,
        )

        if success:
            logger.info(
                "[NativeModel Strategy] Channel model successfully loaded via native engine"
            )
        else:
            logger.error("[NativeModel Strategy] Failed to load native channel model")

        return success
