"""
Channel Emulator HAL

Provides interface and mock implementation for MIMO channel emulators.
Supports vendors like R&S, Keysight, Spirent, etc.

信道加载模式说明:
  - NATIVE_MODEL:      仪器内置信道建模引擎编译并播放（如 F64 GCM/Channel Studio）
  - EXTERNAL_WAVEFORM:  外部引擎生成波形文件（.asc）后上传到仪器播放（通用模式）

应用层统一调用 load_channel() 方法，无需关心底层使用哪种仪器。
子类通过 get_supported_load_modes() 声明支持的模式。
"""

import asyncio
import logging
import random
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics
)

logger = logging.getLogger(__name__)


# ===========================================================================
# 信道加载模式枚举（对应用层透明的抽象）
# ===========================================================================

class ChannelLoadMode(str, Enum):
    """信道仿真器的信道加载模式。

    定义了仪器无关的信道加载方式，使应用层不需要关心底层具体使用
    哪种仪器或哪种工作管线。

    Attributes:
        NATIVE_MODEL: 使用仪器内置的信道建模引擎。
            仪器自身编译信道模型参数并播放。
            例: Keysight F64 的 GCM/Channel Studio，R&S 的内置 3GPP 模型。
            并非所有仿真器都支持此模式。

        EXTERNAL_WAVEFORM: 使用外部引擎生成的波形文件。
            外部 Channel Engine 计算探头权重/TDL 时序，生成 .asc 文件，
            上传到仪器后以 ARB/Runtime 模式播放。
            这是所有信道仿真器都必须支持的通用模式。
    """
    NATIVE_MODEL = "native_model"
    EXTERNAL_WAVEFORM = "external_waveform"


class ChannelEmulatorDriver(InstrumentDriver):
    """
    Abstract interface for Channel Emulator instruments (HAL Layer 2)

    Core capabilities:
    - MIMO channel modeling (spatial correlation, fading)
    - Path loss and delay configuration
    - Doppler shift simulation
    - Real-time channel updates

    信道加载架构:
        应用层通过 load_channel() 统一入口加载信道，无需关心底层仪器。
        子类通过 get_supported_load_modes() 声明自己支持哪些加载模式。
        - 所有仿真器必须支持 EXTERNAL_WAVEFORM（.asc 文件播放）
        - 部分仿真器额外支持 NATIVE_MODEL（内置信道建模引擎）
    """

    # ==================================================================
    # 信道加载：统一入口 + 能力查询
    # ==================================================================

    def get_supported_load_modes(self) -> List[ChannelLoadMode]:
        """
        声明该仿真器支持的信道加载模式。

        默认实现: 只支持外部波形加载（EXTERNAL_WAVEFORM）。
        支持内置模型的子类（如 F64）应重写此方法，追加 NATIVE_MODEL。

        Returns:
            支持的 ChannelLoadMode 列表
        """
        return [ChannelLoadMode.EXTERNAL_WAVEFORM]

    async def load_channel(
        self,
        mode: ChannelLoadMode,
        model_name: str,
        scenario: str,
        parameters: Dict[str, Any],
        waveform_dir: Optional[str] = None,
    ) -> bool:
        """
        统一信道加载入口 —— 应用层的唯一调用点。

        根据 mode 自动分发到对应的底层方法:
        - NATIVE_MODEL     → set_channel_model()
        - EXTERNAL_WAVEFORM → upload_asc_files()

        子类可重写此方法以实现更复杂的分发逻辑（如 F64 的双管线）。
        默认实现仅处理 EXTERNAL_WAVEFORM，其他模式抛出 NotImplementedError。

        Args:
            mode: 信道加载模式
            model_name: 信道模型名称 (e.g., "CDL-A", "CDL-C")
            scenario: 场景类型 (e.g., "UMi", "UMa")
            parameters: 信道参数字典 (频率、带宽等)
            waveform_dir: 波形文件目录路径
                (EXTERNAL_WAVEFORM 模式必需, NATIVE_MODEL 可选)

        Returns:
            True if channel loaded successfully

        Raises:
            NotImplementedError: 当请求的加载模式不被该仪器支持时
            ValueError: 当必需参数缺失时
        """
        supported = self.get_supported_load_modes()
        if mode not in supported:
            raise NotImplementedError(
                f"{type(self).__name__} 不支持 {mode.value} 模式。"
                f"支持的模式: {[m.value for m in supported]}"
            )

        if mode == ChannelLoadMode.EXTERNAL_WAVEFORM:
            if not waveform_dir:
                raise ValueError(
                    "waveform_dir 是 EXTERNAL_WAVEFORM 模式的必需参数"
                )
            return await self.upload_asc_files(waveform_dir, model_name)

        elif mode == ChannelLoadMode.NATIVE_MODEL:
            return await self.set_channel_model(model_name, scenario, parameters)

        return False

    # ==================================================================
    # 底层信道操作原语（子类实现）
    # ==================================================================

    async def set_channel_model(
        self,
        model_type: str,  # e.g., "WINNER_II", "3GPP_38.901"
        scenario: str,  # e.g., "UMi", "UMa", "Indoor"
        parameters: Dict[str, Any]
    ) -> bool:
        """Set channel propagation model (NATIVE_MODEL 管线的底层实现)"""
        raise NotImplementedError

    async def set_mimo_config(
        self,
        tx_antennas: int,
        rx_antennas: int,
        correlation_matrix: Optional[list[list[float]]] = None
    ) -> bool:
        """Configure MIMO antenna array"""
        raise NotImplementedError

    async def set_path_loss(
        self,
        path_loss_db: float,
        distance_m: Optional[float] = None
    ) -> bool:
        """Set path loss value"""
        raise NotImplementedError

    async def set_doppler(
        self,
        frequency_hz: float,
        velocity_kmh: Optional[float] = None
    ) -> bool:
        """Set Doppler shift parameters"""
        raise NotImplementedError

    async def start_emulation(self) -> bool:
        """Start channel emulation"""
        raise NotImplementedError

    async def stop_emulation(self) -> bool:
        """Stop channel emulation"""
        raise NotImplementedError

    async def get_channel_state(self) -> Dict[str, Any]:
        """Get current channel state"""
        raise NotImplementedError

    async def upload_asc_files(
        self,
        asc_files_dir: str,
        cdl_model_name: str = ""
    ) -> bool:
        """
        Upload .asc waveform files to the channel emulator.
        (EXTERNAL_WAVEFORM 管线的底层实现)

        The .asc files are generated by Channel Engine and contain
        per-port TDL (Tapped Delay Line) time-series data.

        Args:
            asc_files_dir: Directory containing .asc files
            cdl_model_name: CDL model name for labeling
                (e.g. "UMa CDL-C NLOS" or "Highway_Beijing CDL Snapshot-42")

        Returns:
            True if upload successful
        """
        raise NotImplementedError

    async def set_external_attenuators(
        self,
        attenuator_values_db: list[float]
    ) -> bool:
        """
        Set external attenuator values for each TX port.

        Values are computed by Channel Engine's link budget algorithm
        and provided via control_instructions.

        Args:
            attenuator_values_db: list of attenuation values in dB, one per TX port

        Returns:
            True if set successfully
        """
        raise NotImplementedError

    async def set_baseband_power(
        self,
        power_dbm: float
    ) -> bool:
        """
        Set emulator baseband output power.

        Args:
            power_dbm: Baseband power in dBm

        Returns:
            True if set successfully
        """
        raise NotImplementedError


class MockChannelEmulator(ChannelEmulatorDriver):
    """
    Mock implementation of Channel Emulator for development/testing

    Simulates realistic behavior without requiring actual hardware.
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._emulation_running = False
        self._channel_model = "3GPP_38.901"
        self._scenario = "UMi"
        self._tx_antennas = 4
        self._rx_antennas = 4
        self._path_loss_db = 80.0
        self._doppler_hz = 100.0
        # Hardware pipeline state
        self._asc_loaded = False
        self._asc_file_count = 0
        self._cdl_model_name = ""
        self._baseband_power_dbm = 0.0
        self._attenuator_values_db: list[float] = []

    async def connect(self) -> bool:
        """Simulate connection to emulator"""
        self._set_status(InstrumentStatus.CONNECTING)
        await asyncio.sleep(0.5)  # Simulate connection time

        self._set_status(InstrumentStatus.CONNECTED)
        self._clear_error()
        return True

    async def disconnect(self) -> bool:
        """Simulate disconnection"""
        if self._emulation_running:
            await self.stop_emulation()

        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        """Apply configuration parameters"""
        if self.status != InstrumentStatus.CONNECTED:
            self._set_status(InstrumentStatus.ERROR, "Not connected")
            return False

        # Apply configuration
        if "channel_model" in config:
            self._channel_model = config["channel_model"]
        if "scenario" in config:
            self._scenario = config["scenario"]
        if "tx_antennas" in config:
            self._tx_antennas = config["tx_antennas"]
        if "rx_antennas" in config:
            self._rx_antennas = config["rx_antennas"]

        self._set_status(InstrumentStatus.READY)
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        """Return supported capabilities"""
        return [
            InstrumentCapability(
                name="mimo",
                description="MIMO channel emulation",
                supported=True,
                parameters={"max_tx": 8, "max_rx": 8}
            ),
            InstrumentCapability(
                name="channel_models",
                description="Supported channel models",
                supported=True,
                parameters={
                    "models": ["3GPP_38.901", "WINNER_II", "ITU"],
                    "scenarios": ["UMi", "UMa", "Indoor", "Rural"]
                }
            ),
            InstrumentCapability(
                name="doppler",
                description="Doppler shift simulation",
                supported=True,
                parameters={"max_frequency_hz": 1000}
            ),
            InstrumentCapability(
                name="fading",
                description="Fast/slow fading simulation",
                supported=True
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        """Generate mock metrics"""
        # Simulate realistic metrics with variation
        snr = 25.0 + random.uniform(-5, 5)
        throughput = 150.0 + random.uniform(-30, 50)
        path_loss = self._path_loss_db + random.uniform(-2, 2)

        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "channel_model": self._channel_model,
                "scenario": self._scenario,
                "emulation_running": self._emulation_running,
                "snr_db": round(snr, 2),
                "throughput_mbps": round(throughput, 2),
                "path_loss_db": round(path_loss, 2),
                "doppler_hz": self._doppler_hz,
                "tx_antennas": self._tx_antennas,
                "rx_antennas": self._rx_antennas
            },
            status="normal" if snr > 15 else "warning"
        )

    async def reset(self) -> bool:
        """Reset to default configuration"""
        if self._emulation_running:
            await self.stop_emulation()

        self._channel_model = "3GPP_38.901"
        self._scenario = "UMi"
        self._tx_antennas = 4
        self._rx_antennas = 4
        self._path_loss_db = 80.0
        self._doppler_hz = 100.0

        self._set_status(InstrumentStatus.READY)
        return True

    async def set_channel_model(
        self,
        model_type: str,
        scenario: str,
        parameters: Dict[str, Any]
    ) -> bool:
        """Set channel propagation model"""
        self._channel_model = model_type
        self._scenario = scenario
        return True

    async def set_mimo_config(
        self,
        tx_antennas: int,
        rx_antennas: int,
        correlation_matrix: Optional[list[list[float]]] = None
    ) -> bool:
        """Configure MIMO antenna array"""
        if tx_antennas > 8 or rx_antennas > 8:
            return False

        self._tx_antennas = tx_antennas
        self._rx_antennas = rx_antennas
        return True

    async def set_path_loss(
        self,
        path_loss_db: float,
        distance_m: Optional[float] = None
    ) -> bool:
        """Set path loss value"""
        if path_loss_db < 0 or path_loss_db > 200:
            return False

        self._path_loss_db = path_loss_db
        return True

    async def set_doppler(
        self,
        frequency_hz: float,
        velocity_kmh: Optional[float] = None
    ) -> bool:
        """Set Doppler shift parameters"""
        if frequency_hz < 0 or frequency_hz > 1000:
            return False

        self._doppler_hz = frequency_hz
        return True

    async def start_emulation(self) -> bool:
        """Start channel emulation"""
        if self.status != InstrumentStatus.READY:
            return False

        self._set_status(InstrumentStatus.BUSY)
        self._emulation_running = True
        await asyncio.sleep(0.2)  # Simulate startup time
        return True

    async def stop_emulation(self) -> bool:
        """Stop channel emulation"""
        self._emulation_running = False
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_channel_state(self) -> Dict[str, Any]:
        """Get current channel state"""
        return {
            "model": self._channel_model,
            "scenario": self._scenario,
            "running": self._emulation_running,
            "mimo_config": {
                "tx": self._tx_antennas,
                "rx": self._rx_antennas
            },
            "path_loss_db": self._path_loss_db,
            "doppler_hz": self._doppler_hz,
            "asc_loaded": self._asc_loaded,
            "cdl_model_name": self._cdl_model_name,
            "baseband_power_dbm": self._baseband_power_dbm,
            "attenuators_db": self._attenuator_values_db,
        }

    async def upload_asc_files(
        self,
        asc_files_dir: str,
        cdl_model_name: str = ""
    ) -> bool:
        """
        Mock upload of .asc files to emulator.

        In real implementation, this would use SCPI/VISA to transfer
        files to the instrument's internal storage.
        """
        import os
        if not os.path.isdir(asc_files_dir):
            return False

        asc_files = [f for f in os.listdir(asc_files_dir) if f.endswith('.asc')]
        if not asc_files:
            return False

        await asyncio.sleep(0.3)  # Simulate file transfer time

        self._asc_loaded = True
        self._asc_file_count = len(asc_files)
        self._cdl_model_name = cdl_model_name

        return True

    async def set_external_attenuators(
        self,
        attenuator_values_db: list[float]
    ) -> bool:
        """
        Mock set external attenuator values.

        In real implementation, this would send SCPI commands to
        programmable attenuators via the RF distribution network.
        """
        if any(v < 0 or v > 60 for v in attenuator_values_db):
            return False

        self._attenuator_values_db = list(attenuator_values_db)
        return True

    async def set_baseband_power(
        self,
        power_dbm: float
    ) -> bool:
        """
        Mock set baseband power.

        In real implementation, this would configure the F64's
        output power via SCPI.
        """
        if power_dbm < -40 or power_dbm > 20:
            return False

        self._baseband_power_dbm = power_dbm
        return True
