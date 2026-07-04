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

        PARAMETRIC_TDL: P2-14 B-2 —— 参数化 TDL (.tap/.rtc) 由仪器硬件实时合成衰落。
            外部引擎 (ChannelEgine geometric_native_fit) 只给每抽头参数 (native 谱/
            质心/展宽/角度), 仪器 FPGA 实时生成多普勒衰落, 对外更新率仅几何骨架级。
            并非所有仿真器都支持 (F64 需 Channel Studio TDL Tool + gaussian 谱可用性,
            V1.0 §9 待真机验证)。
    """
    NATIVE_MODEL = "native_model"
    EXTERNAL_WAVEFORM = "external_waveform"
    PARAMETRIC_TDL = "parametric_tdl"


class CalibrationToneCapability(str, Enum):
    """CE 在 CE+SA 路损校准链路里能扮演什么角色。

    决定服务层走 D 路径还是 B 路径:

    - **INTERNAL_CW_GENERATOR (D 路径)**: CE 自身能在指定 OTA 输出口生成
      已知频率 + 已知功率的 CW tone, 不需要任何上游信号源。
      实现示例:
        - PROPSIM F64 + Internal Interference Generator option
          (`OUTPut:INTERFerence:ADD <out>, <id>, 2` type=2 = CW)
      service 调 `set_calibration_tone(freq, power)` 即可。

    - **PASSTHROUGH_ONLY (B 路径)**: CE 不会自己产 tone, 但可以把上游
      BSE/SG 输入的信号原样透传到指定 OTA 输出口 (零增益 / 已知 fixed
      attenuation). 此时校准链路是 SG.set_cw → CE 透传 → switch → PA →
      probe → SGH → SA。需要 LabProfile 上额外绑一个 SG 或 BSE driver。
      实现示例:
        - 没买 PROPSIM Interference Generator license 的部署
        - 第三方 CE (R&S, Spirent) 没有内置 CW gen 的型号
      service 调 `set_passthrough_mode(...)` + 上游 `set_cw(...)`。

    Mock CE 同时声明两个 (BOTH), 让单元测试可以无硬件覆盖两条路径。
    """
    INTERNAL_CW_GENERATOR = "internal_cw_generator"
    PASSTHROUGH_ONLY = "passthrough_only"


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

    async def list_channel_models(self) -> list[Dict[str, Any]]:
        """List channel-model files the operator can pick from the GUI.

        Each entry: ``{filename, label, description, type}``.

        Implementation note — *not* runtime file discovery on the
        instrument: the F64's ATE Server doesn't expose MMEM SCPI for
        directory listing, and FTP isn't always running on chamber-side
        units (verified at CAICT 2026-05-13 — F64 0.132 has FTP closed).
        So the default behaviour is to surface a user-curated list from
        ``connection_params['available_channel_models']`` instead of
        scraping the device. Drivers with a usable file-listing channel
        (SMB, working FTP, vendor REST API) may override this to do
        dynamic discovery.

        Returns the empty list when nothing is configured.
        """
        return []


def normalize_channel_model_entries(entries: Any) -> list[Dict[str, Any]]:
    """Normalise raw ``connection_params['available_channel_models']`` to
    the API contract: ``[{filename, label, description, type}, ...]``.

    Single source of truth for shape coercion, shared by every concrete
    ``list_channel_models`` implementation AND by the API endpoint's
    DB-fallback path (operators planning before HAL is up / the F64 is
    online). Without this shared helper we'd duplicate the rules and
    risk drift between "what the driver returns when connected" and
    "what the GUI sees when offline".

    Coercion rules:
    - Bare strings expand to ``{"filename": "<str>"}``.
    - Non-dict / non-string entries are silently dropped.
    - Entries missing ``filename`` (or with non-string filename) dropped.
    - ``label`` defaults to ``filename``.
    - ``type`` is the lowercased file extension (``smu``/``rtc``/``asc``
      etc.), or ``"unknown"`` if no extension.
    - ``center_frequency_mhz`` + ``nr_arfcn`` (P2-10 Step 1): 资产盘点元数据 —— 优先用
      entry 里 operator 显式给的 ``center_frequency_mhz``, 否则从文件名频率 token 解析
      (``_3600M.smu`` → 3600), 让 inventory 从"名字清单"变"带频率的资产盘点", 直接服务
      emulation_file 选择 (P2-11 Phase 2: .smu↔TestCase 频率匹配)。无频率 token → None。
      ⚠ P1-18: 文件名频率是场景族标称, 会系统性说谎 (实录 UMa_3600M 工程实为
      3549.99) —— fallback 值只作 loose 提示; 登记真值走显式字段 (工程解析
      ``smu_project.parse_smu_project_primary_freq_mhz`` 或实测, 见 #193 资产修正)。
    """
    if not entries:
        return []
    from app.hal.nr_arfcn import freq_mhz_to_nr_arfcn, parse_smu_center_freq_mhz

    out: list[Dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, str):
            entry = {"filename": entry}
        if not isinstance(entry, dict):
            continue
        filename = entry.get("filename")
        if not filename or not isinstance(filename, str):
            continue
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"
        raw_center = entry.get("center_frequency_mhz")
        center_mhz = (
            float(raw_center)
            if isinstance(raw_center, (int, float))
            else parse_smu_center_freq_mhz(filename)
        )
        nr_arfcn_val: Optional[int] = None
        if center_mhz is not None:
            try:
                nr_arfcn_val = freq_mhz_to_nr_arfcn(center_mhz)
            except ValueError:  # 频率超出 NR-ARFCN 范围 (异常命名) → 不强标 ARFCN
                nr_arfcn_val = None
        out.append({
            "filename": filename,
            "label": entry.get("label") or filename,
            "description": entry.get("description"),
            "type": ext,
            "center_frequency_mhz": center_mhz,
            "nr_arfcn": nr_arfcn_val,
            # P2-12 slice 4: SCD 派生 entry 带 scd_id (手敲条目为 None) —— 让 GUI 的
            # emulation_file 下拉选 SCD 派生项时存 scd_id (measure 查 SCD + 频率 cross-check)
            # 而非裸 filename。projection entry 由 _scd_to_projection_entry 打上 scd_id。
            "scd_id": entry.get("scd_id"),
        })
    return out

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

    # ==================================================================
    # 路损校准 tone 链路 (CE+SA 校准的 CE 端)
    #
    # 两条物理可行路径都用 HAL 抽象出来, service 层按 capability 自动选:
    #   D 路径 = INTERNAL_CW_GENERATOR → set_calibration_tone(...)
    #   B 路径 = PASSTHROUGH_ONLY      → set_passthrough_mode(...)
    #
    # 详见 CalibrationToneCapability docstring.
    # ==================================================================

    def get_calibration_tone_capabilities(self) -> List[CalibrationToneCapability]:
        """声明该 CE 在 CE+SA 路损校准链路里支持哪些角色。

        默认返回 [] —— 子类必须显式声明, 服务层会拒绝在没声明能力的 CE
        上跑校准 (避免 silent 走错路径).

        Mock CE 通常声明两个都支持 (BOTH), 真实驱动按硬件 / license 决定。
        """
        return []

    async def set_calibration_tone(
        self,
        frequency_hz: float,
        power_dbm: float,
        ce_port: Optional[str] = None,
    ) -> bool:
        """[D 路径] CE 自己出已知 CW tone (需 INTERNAL_CW_GENERATOR 能力)。

        实现示例 — PROPSIM Internal Interference Generator (option):
            OUTPut:INTERFerence:ADD <ce_port>, cal_tone, 2     # type=2=CW
            OUTPut:INTERFerence:STRATegy:SET cal_tone, 1       # 恒定功率
            OUTPut:INTERFerence:FREQuency:SET cal_tone, <MHz>
            OUTPut:INTERFerence:POWer:SET cal_tone, <dBm>
            OUTPut:INTERFerence:STatus cal_tone, 1             # enable

        Args:
            frequency_hz: tone 中心频率 (Hz)
            power_dbm: tone 输出功率 (dBm), CE OTA 端口标称值
            ce_port: 可选, 指定从哪个 OTA 端口出 (如 "B1.1"); None = 主端口

        Returns:
            True if CE tone on at requested freq/power; 必须跟
            stop_calibration_tone 配对避免长时间发射。
        """
        raise NotImplementedError

    async def stop_calibration_tone(self) -> bool:
        """[D 路径] 停 CW tone, 回 idle. finally 块里调用。"""
        raise NotImplementedError

    async def set_passthrough_mode(
        self,
        ce_port: Optional[str] = None,
        ce_input_port: Optional[str] = None,
    ) -> bool:
        """[B 路径] 把 CE 切到透传模式 (需 PASSTHROUGH_ONLY 能力)。

        透传模式下: 上游 SG/BSE 注入 CW → CE 不加 fading / 不加增益, 原样
        从指定 OTA 输出口出来。配合 SG.set_cw + SG.start_tx, 实现 CE+SA
        路损校准的 tone 源。

        实现示例 — PROPSIM 透传 (无 fading 的 baseline emulation):
            // 假设一个 zero-fading 的 1×1 CDL emulation 已 open, in_port → out_port
            // 调用方负责确保 emulation 已 build/load (一次性, 不是每次校准都重做)
            EMUlation:GAIN:CH <out_port>, 0          # 0 dB pass-through
            // 或具体厂商相关的 "calibration mode"

        Args:
            ce_port: 可选, 走哪个 OTA 输出 (如 "B1.1"); None = 主端口
            ce_input_port: 可选, 上游 SG 接到 CE 哪个 input (如 "A1");
                None = 默认 input. 真实驱动需要 input port 知道做信号路由.

        Returns:
            True if CE 已切到透传 + 输出端就绪。必须跟
            clear_passthrough_mode 配对调用。
        """
        raise NotImplementedError

    async def clear_passthrough_mode(self) -> bool:
        """[B 路径] 退出透传模式, 恢复正常 fading 配置。finally 块里调用。"""
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
        # Calibration tone state (CE-as-source for CE+SA path-loss calibration)
        self._cal_tone_active = False
        self._cal_tone_freq_hz: float = 0.0
        self._cal_tone_power_dbm: float = 0.0
        self._cal_tone_port: str = "MAIN"
        # Passthrough mode state (B path: SG/BSE upstream → CE passthrough → SA)
        self._passthrough_active = False
        self._passthrough_in_port: str = "A1"
        self._passthrough_out_port: str = "MAIN"

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

    def get_supported_load_modes(self) -> List[ChannelLoadMode]:
        """Mock 支持所有加载模式，以便在无硬件时完整测试两条流水线"""
        return [ChannelLoadMode.EXTERNAL_WAVEFORM, ChannelLoadMode.NATIVE_MODEL]

    def get_calibration_tone_capabilities(self) -> List[CalibrationToneCapability]:
        """Mock 默认两条路径都支持, 让单元测试无硬件覆盖 D / B 两条 dispatch.

        测试要单独验证某一条路径时, 子类化 Mock 并 override 这个方法。
        """
        return [
            CalibrationToneCapability.INTERNAL_CW_GENERATOR,
            CalibrationToneCapability.PASSTHROUGH_ONLY,
        ]

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
        # 对齐真驱动契约 (P2-17, Codex #201 R3): 加载成功 = 可启动 —
        # connect 后仅 CONNECTED, 不置 READY 则 start_emulation 的
        # status 门恒拒, measure 链的显式启动在 mock 下假失败。
        self._set_status(InstrumentStatus.READY)
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
        # 对齐真驱动契约 (Codex #201 R4 P2): ASC 路加载成功同样 = 可启动 —
        # 只改 NATIVE_MODEL 路会让 mock 下 external_asc/mimo_first_asc 引擎
        # 的显式启动假失败 (对称路径 fan-out, 同 set_channel_model)。
        self._set_status(InstrumentStatus.READY)

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

    async def set_calibration_tone(
        self,
        frequency_hz: float,
        power_dbm: float,
        ce_port: Optional[str] = None,
    ) -> bool:
        """Mock CE calibration tone — record state, return True.

        Production drivers (PROPSIM etc.) need vendor SCPI; the mock just
        captures the request so unit tests + dev environments can exercise
        the CE+SA path-loss flow without hardware.
        """
        if power_dbm < -50 or power_dbm > 20:
            return False
        self._cal_tone_active = True
        self._cal_tone_freq_hz = frequency_hz
        self._cal_tone_power_dbm = power_dbm
        self._cal_tone_port = ce_port or "MAIN"
        return True

    async def stop_calibration_tone(self) -> bool:
        """Mock stop — clear state, return True."""
        self._cal_tone_active = False
        return True

    async def set_passthrough_mode(
        self,
        ce_port: Optional[str] = None,
        ce_input_port: Optional[str] = None,
    ) -> bool:
        """Mock B path — record passthrough state, return True."""
        self._passthrough_active = True
        self._passthrough_out_port = ce_port or "MAIN"
        self._passthrough_in_port = ce_input_port or "A1"
        return True

    async def clear_passthrough_mode(self) -> bool:
        """Mock clear — reset state, return True."""
        self._passthrough_active = False
        return True
