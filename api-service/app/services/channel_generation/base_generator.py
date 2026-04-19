"""
信道波形合成策略 — 接口基类

定义了向硬件装载信道波形的标准化抽象。
策略层通过 ChannelEmulatorDriver 统一接口与硬件交互,
不直接依赖任何具体仪器型号的驱动。
"""

from enum import Enum
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from app.hal.channel_emulator import ChannelEmulatorDriver


class EngineMode(str, Enum):
    GCM_NATIVE = "keysight_gcm"       # Keysight native Channel Studio GCM
    ASC_SYNTHESIS = "mimo_first_asc"  # MIMO-First Custom ASC Synthesis Engine


class BaseChannelGenerator(ABC):
    """
    信道波形合成策略的接口基类。

    所有策略通过 ChannelEmulatorDriver 抽象接口与硬件交互,
    实现硬件无关性 —— 无论底层是 F64、R&S 还是 Spirent,
    策略代码都不需要修改。
    """

    def __init__(
        self,
        emulator: ChannelEmulatorDriver,
        chamber_config: Any,
        calibration_entries: List[Dict],
    ):
        """
        Args:
            emulator: 信道仿真器 HAL 驱动实例 (从 HAL 管理器获取)
            chamber_config: 暗室配置
            calibration_entries: 校准数据条目
        """
        self.emulator = emulator
        self.chamber_config = chamber_config
        self.calibration_entries = calibration_entries

    @abstractmethod
    async def generate_and_load(
        self,
        simulation_rules: Dict[str, Any],
        cdl_model_data: Dict[str, Any],
    ) -> bool:
        """
        生成信道文件并将其装载入物理硬件。

        Args:
            simulation_rules: 仿真规则参数 (频率、目标功率等)
            cdl_model_data: CDL 模型描述 (模型名、会话 ID 等)

        Returns:
            成功则为 True
        """
        pass
