"""
channel_generation - 并行信道生成策略包

提供基于 Strategy 模式的多引擎信道波形合成能力：
- NativeModelStrategy: 使用仿真器内置信道建模引擎 (如 F64 GCM)
- ExternalWaveformStrategy: 使用 MIMO-First 自研 C++ 引擎生成 ASC 波形

所有策略通过 ChannelEmulatorDriver 抽象接口与硬件交互,
实现硬件无关性。
"""

from app.services.channel_generation.base_generator import BaseChannelGenerator, EngineMode
from app.services.channel_generation.gcm_strategy import NativeModelStrategy
from app.services.channel_generation.asc_strategy import ExternalWaveformStrategy

__all__ = [
    "BaseChannelGenerator",
    "EngineMode",
    "NativeModelStrategy",
    "ExternalWaveformStrategy",
]
