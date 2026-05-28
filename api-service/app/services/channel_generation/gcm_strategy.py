"""
GCM 原生信道合成策略 (Native Model Pipeline)

使用信道仿真器内置的信道建模引擎编译并播放信道模型。
例如 Keysight F64 的 Channel Studio GCM, R&S 的内置 3GPP 模型等。

本策略通过 ChannelEmulatorDriver.load_channel(NATIVE_MODEL) 调用,
不直接依赖任何具体仪器型号的驱动或控制器。

Pipeline A 完整流程:
    1. 从 simulation_rules 中获取 .smu 文件路径 (或使用标准命名约定自动构造)
    2. 调用 emulator.load_channel(NATIVE_MODEL) 加载信道模型
    3. 可选: 生成 .oop (OTA Orientation Profile) 用于转台同步
    4. 可选: 启动仿真播放

.smu 文件命名约定:
    标准格式: {model_type}_{scenario}_{TxAntennas}x{RxAntennas}.smu
    示例: CDL-C_UMi_2x2.smu

    若在 simulation_rules 中显式指定了 emulation_file，则使用指定路径。
    否则使用上述命名约定自动构造路径。

GCM 攻略对齐:
    - Step 4: 信道模型选择 → model_name / scenario 参数
    - Step 7: .smu 文件加载 → CALC:FILT:FILE SCPI
    - Step 8: .oop 文件生成 → OOPProfile 导出
    - Step 9: PAS Rotation → 由上游 channel_engine_client 的
              _apply_pas_rotation() 预处理 (已对齐)
"""

import logging
import os
from typing import Dict, Any, List, Optional

from app.services.channel_generation.base_generator import BaseChannelGenerator
from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode
from app.services.channel_generation.oop_parser import (
    generate_oop_file,
    OOPProfile,
)

logger = logging.getLogger(__name__)


# .oop 文件输出目录
OOP_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "oop_profiles"
)


class NativeModelStrategy(BaseChannelGenerator):
    """
    使用仿真器内置信道建模引擎的策略 (Benchmarking Target)

    利用仪器内置的信道建模能力 (如 F64 的 Channel Studio GCM),
    直接在仪器内部编译 3GPP 参数并生成信道衰落数据。

    适用场景:
      - 基准对比测试 (与 MIMO-First 自研引擎进行 A/B 对照)
      - 标准信道模型快速加载 (无需外部计算)
      - GCM 合规性验证 (使用 F64 原生 GCM 管线)

    注意: 并非所有信道仿真器都支持此模式。
    策略初始化前应检查 emulator.get_supported_load_modes()。
    """

    def __init__(
        self,
        emulator: ChannelEmulatorDriver,
        chamber_config: Any,
        calibration_entries: List[Dict],
        generate_oop: bool = True,
        azimuth_step_deg: float = 15.0,
    ):
        """
        Args:
            emulator: 信道仿真器 HAL 驱动实例
            chamber_config: 暗室配置
            calibration_entries: 校准数据条目
            generate_oop: 是否自动生成 .oop 文件
            azimuth_step_deg: 空间采样步长 (度, 用于 .oop 生成)
        """
        super().__init__(emulator, chamber_config, calibration_entries)
        self.generate_oop = generate_oop
        self.azimuth_step_deg = azimuth_step_deg
        self._last_oop_profile: Optional[OOPProfile] = None

    async def generate_and_load(
        self,
        simulation_rules: Dict[str, Any],
        cdl_model_data: Dict[str, Any],
    ) -> bool:
        """
        加载 GCM 原生信道模型。

        完整流程:
        1. 验证仿真器支持 NATIVE_MODEL 模式
        2. 构造 .smu 文件路径 (或从 simulation_rules 获取)
        3. 调用 HAL 统一接口加载
        4. 可选: 生成 .oop 文件用于转台同步

        Args:
            simulation_rules: 仿真规则参数, 支持:
                - emulation_file: .smu 文件路径 (覆盖自动命名)
                - center_frequency_mhz: 中心频率 (MHz)
                - bandwidth_mhz: 带宽 (MHz)
                - mimo_tx: 发射天线数
                - mimo_rx: 接收天线数
                - azimuth_start: 方位角扫描起始 (度, 用于 .oop)
                - azimuth_stop: 方位角扫描结束 (度)
                - azimuth_step: 方位角步长 (度)
                - pas_rotation_deg: PAS 旋转偏移 (度)

            cdl_model_data: CDL 模型参数:
                - model_name: 模型名称 (e.g., "CDL-A", "CDL-C")
                - scenario: 场景类型 (e.g., "UMi", "UMa")
                - session_id: 会话 ID

        Returns:
            True if channel model loaded successfully
        """
        logger.info("[NativeModel Strategy] Starting native channel generation")

        model_name = cdl_model_data.get("model_name", "3GPP_CDL-C")
        scenario = cdl_model_data.get("scenario", "UMi")

        # ----- Step 1: 验证仿真器能力 -----
        supported_modes = self.emulator.get_supported_load_modes()
        if ChannelLoadMode.NATIVE_MODEL not in supported_modes:
            logger.error(
                f"[NativeModel Strategy] Emulator {type(self.emulator).__name__} "
                f"does not support NATIVE_MODEL mode. "
                f"Supported: {[m.value for m in supported_modes]}"
            )
            return False

        # ----- Step 2: 构建 .smu 文件路径 -----
        # 优先使用显式指定的路径, 否则使用标准命名约定
        emulation_file = simulation_rules.get("emulation_file")
        if emulation_file:
            # 用户显式指定了 .smu 路径
            simulation_rules_with_file = {
                **simulation_rules,
                "emulation_file": emulation_file,
            }
            logger.info(
                f"[NativeModel Strategy] Using explicit .smu: {emulation_file}"
            )
        else:
            # 不指定 emulation_file → 委托驱动选默认 (P0-8 Step 4):
            # F64 驱动优先级 = connection_params["default_emulation_file"] >
            # F64_DEFAULT_EMULATION_FILE (3600M) > auto-name (legacy)。
            simulation_rules_with_file = dict(simulation_rules)
            logger.info(
                "[NativeModel Strategy] No explicit .smu in simulation_rules; "
                "delegating to driver default (F64: connection_params or code default)."
            )

        # ----- Step 3: 通过 HAL 统一接口加载 -----
        logger.info(
            f"[NativeModel Strategy] Loading model: {model_name} "
            f"scenario={scenario}"
        )

        success = await self.emulator.load_channel(
            mode=ChannelLoadMode.NATIVE_MODEL,
            model_name=model_name,
            scenario=scenario,
            parameters=simulation_rules_with_file,
        )

        if not success:
            logger.error(
                "[NativeModel Strategy] Failed to load native channel model"
            )
            return False

        logger.info(
            "[NativeModel Strategy] Channel model successfully loaded "
            "via native engine"
        )

        # ----- Step 4: 可选 — 生成 .oop 文件 -----
        if self.generate_oop:
            self._generate_oop_profile(
                model_name=model_name,
                scenario=scenario,
                simulation_rules=simulation_rules,
                session_id=cdl_model_data.get("session_id", "default"),
            )

        return True

    def get_last_oop_profile(self) -> Optional[OOPProfile]:
        """
        获取最近一次生成的 OOP Profile。

        供 CommissioningService 用于转台控制序列。
        """
        return self._last_oop_profile

    # ===================================================================
    # 内部方法
    # ===================================================================

    def _generate_oop_profile(
        self,
        model_name: str,
        scenario: str,
        simulation_rules: Dict[str, Any],
        session_id: str,
    ) -> None:
        """
        生成 .oop (OTA Orientation Profile) 文件。

        方位角扫描序列:
        - 默认: 0° → 360°, 步长 15°
        - 可通过 simulation_rules 中的 azimuth_start/stop/step 覆盖

        PAS Rotation 补偿:
        - 若 simulation_rules 中包含 pas_rotation_deg,
          .oop 文件会自动应用反向旋转补偿
        """
        az_start = simulation_rules.get("azimuth_start", 0.0)
        az_stop = simulation_rules.get("azimuth_stop", 360.0)
        az_step = simulation_rules.get(
            "azimuth_step", self.azimuth_step_deg
        )
        pas_rotation = simulation_rules.get("pas_rotation_deg", 0.0)

        # 生成方位角序列
        azimuth_steps = []
        current = az_start
        while current < az_stop:
            azimuth_steps.append(current)
            current += az_step

        if not azimuth_steps:
            azimuth_steps = [0.0]

        full_model_name = f"{scenario} {model_name}"

        profile = generate_oop_file(
            model_name=full_model_name,
            azimuth_steps=azimuth_steps,
            pas_rotation_deg=pas_rotation,
            dwell_time_s=simulation_rules.get("dwell_time_s", 1.2),
            speed_deg_s=simulation_rules.get("turntable_speed_deg_s", 5.0),
            source="mimo_first",
        )

        # 保存到文件
        os.makedirs(OOP_OUTPUT_DIR, exist_ok=True)
        oop_filename = f"{session_id}_{model_name}_{scenario}.oop"
        oop_path = os.path.join(OOP_OUTPUT_DIR, oop_filename)
        profile.save(oop_path)

        self._last_oop_profile = profile
        logger.info(
            f"[NativeModel Strategy] OOP profile saved: {oop_path} "
            f"({profile.num_steps} steps)"
        )
