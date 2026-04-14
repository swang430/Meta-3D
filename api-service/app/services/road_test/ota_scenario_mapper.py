"""
OTA Scenario Mapper

Maps virtual road test scenarios to OTA test configuration.
Converts scenario parameters (route, environment, velocity) into:
- Positioner movements (azimuth, elevation)
- Channel model settings (3GPP models)
- Doppler configuration (max Doppler shift)
- Hardware pipeline synthesis (Spec v1.0)
"""

from typing import List, Dict, Tuple, Optional
from uuid import UUID
import math
import logging

from sqlalchemy.orm import Session

from app.schemas.road_test import (
    RoadTestScenario,
    Waypoint,
    ChannelModel,
    EnvironmentType,
)
from app.services.channel_engine_client import (
    ChannelEngineClient,
    CDLCluster,
    CDLModelSource,
    build_cdl_model_name,
    AntennaConfig,
    HardwarePipelineResult,
)

logger = logging.getLogger(__name__)


class OTAConfig:
    """OTA configuration for MPAC chamber"""

    def __init__(self):
        self.positioner_sequence: List[Dict[str, float]] = []
        self.channel_model: str = ""
        self.max_doppler_hz: float = 0.0
        self.probe_weights: List[Dict[str, any]] = []
        self.fading_enabled: bool = False
        # Hardware pipeline results (Spec v1.0)
        self.cdl_model_name: str = ""
        self.asc_files_path: Optional[str] = None
        self.f64_baseband_power_dbm: Optional[float] = None
        self.external_attenuators_db: List[float] = []
        self.target_achieved_rsrp_dbm: Optional[float] = None
        self.spatial_correlation: Optional[float] = None
        self.hardware_pipeline_success: bool = False


class OTAScenarioMapper:
    """
    Maps road test scenarios to OTA chamber configuration

    Handles the complex mapping from:
    - Vehicle trajectory → Positioner movements (azimuth/elevation)
    - Environment → 3GPP channel model selection
    - Velocity → Doppler configuration
    - Base station positions → Probe weight calculations
    """

    def __init__(
        self,
        mpac_radius_m: float = 5.0,
        num_probes: int = 32,
        db: Optional[Session] = None,
        chamber_id: Optional[UUID] = None,
    ):
        """
        Initialize mapper

        Args:
            mpac_radius_m: MPAC chamber radius in meters
            num_probes: Number of OTA probes (typically 32)
            db: SQLAlchemy session (required for hardware pipeline)
            chamber_id: Chamber configuration UUID (required for hardware pipeline)
        """
        self.mpac_radius_m = mpac_radius_m
        self.num_probes = num_probes
        self.db = db
        self.chamber_id = chamber_id

        logger.info(f"OTAScenarioMapper initialized: radius={mpac_radius_m}m, probes={num_probes}")

    async def map_scenario(self, scenario: RoadTestScenario) -> OTAConfig:
        """
        Map complete scenario to OTA configuration

        Args:
            scenario: Road test scenario

        Returns:
            OTAConfig: OTA chamber configuration
        """
        logger.info(f"Mapping scenario '{scenario.name}' to OTA configuration")

        config = OTAConfig()

        # 1. Map environment to channel model
        config.channel_model = self._map_channel_model(scenario.environment.channel_model)
        config.fading_enabled = True

        # 2. Calculate max Doppler from route
        config.max_doppler_hz = self._calculate_max_doppler(
            scenario.route.waypoints,
            scenario.network.band
        )

        # 3. Generate positioner sequence from route
        config.positioner_sequence = self._generate_positioner_sequence(
            scenario.route.waypoints,
            scenario.base_stations[0].position if scenario.base_stations else None
        )

        # 4. Hardware Pipeline: 调用 Channel Engine 合成硬件驱动文件
        await self._run_hardware_pipeline(
            config=config,
            scenario=scenario,
            carrier_freq_hz=self._get_carrier_frequency(scenario.network.band),
        )

        logger.info(
            f"Mapping complete: {len(config.positioner_sequence)} waypoints, "
            f"max_doppler={config.max_doppler_hz:.1f}Hz, "
            f"pipeline={'OK' if config.hardware_pipeline_success else 'FALLBACK'}"
        )

        return config

    def _map_channel_model(self, channel_model: ChannelModel) -> str:
        """
        Map 3GPP channel model to MPAC emulator model name

        Different channel emulators use different naming conventions.
        This maps standardized 3GPP names to emulator-specific names.
        """
        # Map 3GPP models to emulator models (e.g., PropsIM, Vertex)
        model_mapping = {
            ChannelModel.UMA: "3GPP_38.901_UMa",
            ChannelModel.UMI: "3GPP_38.901_UMi",
            ChannelModel.RMA: "3GPP_38.901_RMa",
            ChannelModel.INH: "3GPP_38.901_InH",
            ChannelModel.CDL_A: "3GPP_38.901_CDL-A",
            ChannelModel.CDL_B: "3GPP_38.901_CDL-B",
            ChannelModel.CDL_C: "3GPP_38.901_CDL-C",
            ChannelModel.CDL_D: "3GPP_38.901_CDL-D",
            ChannelModel.CDL_E: "3GPP_38.901_CDL-E",
            ChannelModel.TDL_A: "3GPP_38.901_TDL-A",
            ChannelModel.TDL_B: "3GPP_38.901_TDL-B",
            ChannelModel.TDL_C: "3GPP_38.901_TDL-C",
        }

        return model_mapping.get(channel_model, "3GPP_38.901_UMa")

    def _calculate_max_doppler(self, waypoints: List[Waypoint], frequency_band: str) -> float:
        """
        Calculate maximum Doppler frequency shift

        Doppler shift: fd = v * f / c
        where:
        - v: velocity (m/s)
        - f: carrier frequency (Hz)
        - c: speed of light (3e8 m/s)

        Args:
            waypoints: Route waypoints
            frequency_band: Frequency band (e.g., "n78", "B7")

        Returns:
            Maximum Doppler frequency in Hz
        """
        # Extract maximum velocity
        max_speed_kmh = max(wp.velocity["speed_kmh"] for wp in waypoints)
        max_speed_ms = max_speed_kmh / 3.6  # Convert km/h to m/s

        # Get carrier frequency from band
        carrier_freq_hz = self._get_carrier_frequency(frequency_band)

        # Calculate max Doppler
        speed_of_light = 3e8  # m/s
        max_doppler_hz = max_speed_ms * carrier_freq_hz / speed_of_light

        logger.debug(f"Max Doppler: {max_doppler_hz:.1f} Hz (v={max_speed_kmh} km/h, f={carrier_freq_hz/1e9:.2f} GHz)")

        return max_doppler_hz

    def _get_carrier_frequency(self, frequency_band: str) -> float:
        """
        Get carrier frequency from band designation

        Args:
            frequency_band: Band designation (e.g., "n78", "B7", "n257")

        Returns:
            Carrier frequency in Hz
        """
        # Simplified frequency mapping (use center frequency)
        band_frequencies = {
            # 5G NR bands
            "n1": 2100e6,
            "n3": 1800e6,
            "n7": 2600e6,
            "n28": 700e6,
            "n78": 3500e6,
            "n79": 4700e6,
            "n257": 28000e6,  # mmWave
            "n258": 26000e6,
            "n260": 39000e6,
            "n261": 28000e6,
            # LTE bands
            "B1": 2100e6,
            "B3": 1800e6,
            "B7": 2600e6,
            "B20": 800e6,
            "B28": 700e6,
        }

        return band_frequencies.get(frequency_band, 3500e6)  # Default: 3.5 GHz

    def _generate_positioner_sequence(
        self,
        waypoints: List[Waypoint],
        bs_position: Dict[str, float] | None
    ) -> List[Dict[str, float]]:
        """
        Generate positioner movement sequence

        Maps vehicle trajectory to positioner azimuth/elevation angles.
        Simulates the changing angle of arrival (AoA) as vehicle moves.

        Args:
            waypoints: Route waypoints
            bs_position: Base station position (lat, lon, alt)

        Returns:
            List of positioner configurations {time_s, azimuth_deg, elevation_deg}
        """
        if not bs_position:
            # Default: static positioner
            return [{
                "time_s": wp.time_s,
                "azimuth_deg": 0.0,
                "elevation_deg": 0.0
            } for wp in waypoints]

        sequence = []

        for wp in waypoints:
            # Calculate angle from BS to vehicle
            azimuth, elevation = self._calculate_angle_of_arrival(
                bs_position,
                wp.position
            )

            sequence.append({
                "time_s": wp.time_s,
                "azimuth_deg": azimuth,
                "elevation_deg": elevation
            })

        return sequence

    def _calculate_angle_of_arrival(
        self,
        bs_pos: Dict[str, float],
        vehicle_pos: Dict[str, float]
    ) -> Tuple[float, float]:
        """
        Calculate angle of arrival (AoA) from base station to vehicle

        Args:
            bs_pos: Base station position {lat, lon, alt}
            vehicle_pos: Vehicle position {lat, lon, alt}

        Returns:
            (azimuth_deg, elevation_deg): Angles in degrees
        """
        # Convert lat/lon to local Cartesian (simplified)
        dlat = vehicle_pos["lat"] - bs_pos["lat"]
        dlon = vehicle_pos["lon"] - bs_pos["lon"]
        dalt = vehicle_pos["alt"] - bs_pos["alt"]

        # Approximate conversion (1 degree lat/lon ~ 111 km)
        dx = dlon * 111000 * math.cos(math.radians(bs_pos["lat"]))  # East-West
        dy = dlat * 111000  # North-South
        dz = dalt

        # Calculate horizontal distance
        d_horizontal = math.sqrt(dx**2 + dy**2)

        # Azimuth: angle from North (clockwise)
        azimuth_rad = math.atan2(dx, dy)
        azimuth_deg = math.degrees(azimuth_rad)
        if azimuth_deg < 0:
            azimuth_deg += 360

        # Elevation: angle above horizon
        elevation_rad = math.atan2(dz, d_horizontal)
        elevation_deg = math.degrees(elevation_rad)

        return azimuth_deg, elevation_deg

    async def _run_hardware_pipeline(
        self,
        config: OTAConfig,
        scenario: RoadTestScenario,
        carrier_freq_hz: float,
    ) -> None:
        """
        调用 Channel Engine Hardware Pipeline (Spec v1.0)

        从场景中提取/生成 CDL 簇参数，通过 ChannelEngineClient 发送到 CE，
        将返回的 .asc 文件和控制指令写入 OTAConfig。

        若 CE 不可用或缺少 DB 连接，则回退到均匀权重。
        """
        if not self.db or not self.chamber_id:
            logger.warning(
                "No DB session or chamber_id provided, "
                "falling back to uniform weights"
            )
            config.probe_weights = self._uniform_weights()
            return

        # 从场景构造 CDL 簇参数
        clusters = self._extract_clusters_from_scenario(scenario)

        # 构造 CDL 模型名称
        model = scenario.environment.channel_model
        is_los = model in (ChannelModel.CDL_D, ChannelModel.CDL_E)
        cdl_model_name = self._build_cdl_name(model, is_los)

        try:
            ce_client = ChannelEngineClient(db=self.db)
            result: HardwarePipelineResult = await ce_client.synthesize_hardware_pipeline(
                chamber_id=self.chamber_id,
                frequency_hz=carrier_freq_hz,
                clusters=clusters,
                cdl_model_name=cdl_model_name,
                pathloss_db=self._estimate_pathloss(
                    scenario, carrier_freq_hz
                ),
                is_los=is_los,
                tx_antenna=AntennaConfig(
                    array_type="ULA", num_rows=1, num_cols=2, spacing_h=0.5
                ),
                rx_antenna=AntennaConfig(
                    array_type="ULA", num_rows=1, num_cols=2, spacing_h=0.5
                ),
                ue_velocity_kph=max(
                    wp.velocity["speed_kmh"]
                    for wp in scenario.route.waypoints
                ),
            )

            if result.success:
                config.hardware_pipeline_success = True
                config.cdl_model_name = result.cdl_model_name
                config.asc_files_path = result.asc_files_path
                config.f64_baseband_power_dbm = result.f64_baseband_power_dbm
                config.external_attenuators_db = result.external_attenuators_db
                config.target_achieved_rsrp_dbm = result.target_achieved_rsrp_dbm
                config.spatial_correlation = result.spatial_correlation
                logger.info(
                    f"Hardware pipeline [{result.cdl_model_name}]: "
                    f"{result.total_files} .asc files, "
                    f"RSRP={result.target_achieved_rsrp_dbm:.1f} dBm, "
                    f"compute={result.computation_time_ms:.0f}ms"
                )
            else:
                logger.warning(
                    f"Hardware pipeline failed: {result.message}. "
                    f"Falling back to uniform weights."
                )
                config.probe_weights = self._uniform_weights()

        except Exception as e:
            logger.exception(
                f"Hardware pipeline exception: {e}. "
                f"Falling back to uniform weights."
            )
            config.probe_weights = self._uniform_weights()

    def _extract_clusters_from_scenario(
        self, scenario: RoadTestScenario
    ) -> List[CDLCluster]:
        """
        从场景信道模型中提取 CDL 簇参数。

        当前：使用 3GPP CDL 标准簇参数表。
        未来：接入 Ray-Tracing 引擎后，替换为“{ScenarioName} CDL Snapshot-{N}”格式数据。
        """
        # 3GPP CDL-C 标准簇参数（简化版，取前 6 个主要簇）
        CDL_C_CLUSTERS = [
            {"delay_s": 0.0,    "power": 0.2099, "aoa": -46.6, "aod": -10.2, "as_aoa": 2.0},
            {"delay_s": 65e-9,  "power": 0.2219, "aoa": -11.2, "aod": 10.5,  "as_aoa": 3.0},
            {"delay_s": 70e-9,  "power": 0.1399, "aoa": 51.0,  "aod": -25.2, "as_aoa": 5.0},
            {"delay_s": 190e-9, "power": 0.1279, "aoa": -65.4, "aod": 38.1,  "as_aoa": 7.0},
            {"delay_s": 195e-9, "power": 0.1350, "aoa": -1.8,  "aod": -0.9,  "as_aoa": 2.5},
            {"delay_s": 430e-9, "power": 0.0500, "aoa": 78.2,  "aod": -42.1, "as_aoa": 10.0},
        ]

        model = scenario.environment.channel_model

        # 当前阶段：所有模型都使用 CDL-C 的簇参数
        # TODO: 为不同 CDL/TDL 模型提供专用参数表
        cluster_data = CDL_C_CLUSTERS

        clusters = []
        for c in cluster_data:
            clusters.append(CDLCluster(
                delay_s=c["delay_s"],
                power_relative_linear=c["power"],
                aoa_deg=c["aoa"],
                aod_deg=c.get("aod", 0.0),
                zoa_deg=90.0,
                zod_deg=90.0,
                as_aoa_deg=c.get("as_aoa", 2.0),
            ))

        is_los = model in (ChannelModel.CDL_D, ChannelModel.CDL_E)
        cdl_name = self._build_cdl_name(model, is_los)
        logger.info(
            f"Prepared {len(clusters)} clusters: [{cdl_name}]"
        )
        return clusters

    def _build_cdl_name(self, model: ChannelModel, is_los: bool) -> str:
        """
        根据场景信道模型构造标准化的 CDL 名称。

        3GPP 标准模型格式：“{Scenario} {CDL_Model} {LOS/NLOS}”
        例: UMa CDL-C NLOS, UMi CDL-D LOS
        """
        # 场景映射
        SCENARIO_MAP = {
            ChannelModel.UMA: "UMa",
            ChannelModel.UMI: "UMi",
            ChannelModel.RMA: "RMa",
            ChannelModel.INH: "InH",
        }

        # CDL 模型映射
        CDL_MAP = {
            ChannelModel.CDL_A: "CDL-A",
            ChannelModel.CDL_B: "CDL-B",
            ChannelModel.CDL_C: "CDL-C",
            ChannelModel.CDL_D: "CDL-D",
            ChannelModel.CDL_E: "CDL-E",
            ChannelModel.TDL_A: "TDL-A",
            ChannelModel.TDL_B: "TDL-B",
            ChannelModel.TDL_C: "TDL-C",
        }

        # 如果是明确的 CDL/TDL 模型
        if model in CDL_MAP:
            cdl_id = CDL_MAP[model]
            condition = "LOS" if is_los else "NLOS"
            # 从模型名推断场景（CDL-D/E 为 LOS 场景，通常对应 UMa）
            scenario = "UMa"  # 默认
            return f"{scenario} {cdl_id} {condition}"

        # 如果是场景类型（UMa/UMi/RMa/InH）
        if model in SCENARIO_MAP:
            scenario = SCENARIO_MAP[model]
            cdl_id = "CDL-C"  # 当前默认使用 CDL-C
            condition = "LOS" if is_los else "NLOS"
            return f"{scenario} {cdl_id} {condition}"

        return build_cdl_model_name(
            CDLModelSource.STANDARD_3GPP,
            scenario="UMa",
            cdl_model="CDL-C",
            is_los=is_los,
        )

    def _estimate_pathloss(
        self,
        scenario: RoadTestScenario,
        carrier_freq_hz: float,
    ) -> float:
        """
        估算路径损耗（简化的 Free-Space Path Loss）。

        TODO: 未来接入 Ray-Tracing 引擎后替换为真实计算值。
        """
        # 假设 BS-UE 距离 ~200m
        distance_m = 200.0
        if scenario.base_stations:
            # 尝试从第一个航点计算到基站的距离
            bs = scenario.base_stations[0].position
            wp = scenario.route.waypoints[0].position
            dlat = wp["lat"] - bs["lat"]
            dlon = wp["lon"] - bs["lon"]
            dx = dlon * 111000 * math.cos(math.radians(bs["lat"]))
            dy = dlat * 111000
            distance_m = max(math.sqrt(dx**2 + dy**2), 10.0)

        # FSPL = 20*log10(d) + 20*log10(f) - 147.55
        freq_hz = carrier_freq_hz
        fspl = (
            20 * math.log10(distance_m)
            + 20 * math.log10(freq_hz)
            - 147.55
        )
        return round(fspl, 2)

    def _uniform_weights(self) -> List[Dict[str, any]]:
        """
        Generate fallback uniform weights when ChannelEngine is unavailable

        Provides basic probe weighting for testing purposes.

        Returns:
            List of uniformly weighted probes
        """
        weights = []
        for probe_id in range(self.num_probes):
            angle_deg = probe_id * (360 / self.num_probes)
            amplitude = 1.0 / math.sqrt(self.num_probes)  # Normalize power

            weights.append({
                "probe_id": probe_id,
                "azimuth_deg": angle_deg,
                "amplitude": amplitude,
                "phase_deg": 0.0,
                "polarization": "V"
            })

        logger.warning(f"Using fallback uniform weights for {self.num_probes} probes")
        return weights

    def validate_scenario_compatibility(self, scenario: RoadTestScenario) -> Dict[str, any]:
        """
        Validate if scenario can be executed in OTA mode

        Checks:
        - Route duration (must fit within test time limits)
        - Velocity (OTA positioner speed limits)
        - Channel model (must be supported by emulator)
        - Base station count (OTA typically supports 1-2 BS)

        Args:
            scenario: Road test scenario

        Returns:
            Validation result with warnings/errors
        """
        errors = []
        warnings = []

        # Check duration
        if scenario.route.duration_s > 300:  # 5 minutes
            warnings.append(f"Long scenario duration ({scenario.route.duration_s:.1f}s). Consider shortening for OTA.")

        # Check max velocity
        max_speed_kmh = max(wp.velocity["speed_kmh"] for wp in scenario.route.waypoints)
        if max_speed_kmh > 150:
            errors.append(f"Velocity too high ({max_speed_kmh} km/h). OTA positioner limit: 150 km/h equivalent.")

        # Check base station count
        if len(scenario.base_stations) > 2:
            warnings.append(f"{len(scenario.base_stations)} base stations. OTA mode typically supports 1-2.")

        # Check channel model support
        supported_models = {ChannelModel.UMA, ChannelModel.UMI, ChannelModel.RMA}
        if scenario.environment.channel_model not in supported_models:
            warnings.append(f"Channel model {scenario.environment.channel_model} may have limited OTA support.")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "compatible": len(errors) == 0
        }
