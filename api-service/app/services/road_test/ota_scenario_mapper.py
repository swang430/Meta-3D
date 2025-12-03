"""
OTA Scenario Mapper

Maps virtual road test scenarios to OTA test configuration.
Converts scenario parameters (route, environment, velocity) into:
- Positioner movements (azimuth, elevation)
- Channel model settings (3GPP models)
- Doppler configuration (max Doppler shift)
- Probe weight calculations (32-probe MPAC)
"""

from typing import List, Dict, Tuple, Optional
import math
import logging
import httpx
import json

from app.schemas.road_test import (
    RoadTestScenario,
    Waypoint,
    ChannelModel,
    EnvironmentType,
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


class OTAScenarioMapper:
    """
    Maps road test scenarios to OTA chamber configuration

    Handles the complex mapping from:
    - Vehicle trajectory → Positioner movements (azimuth/elevation)
    - Environment → 3GPP channel model selection
    - Velocity → Doppler configuration
    - Base station positions → Probe weight calculations
    """

    def __init__(self, mpac_radius_m: float = 5.0, num_probes: int = 32):
        """
        Initialize mapper

        Args:
            mpac_radius_m: MPAC chamber radius in meters
            num_probes: Number of OTA probes (typically 32)
        """
        self.mpac_radius_m = mpac_radius_m
        self.num_probes = num_probes

        logger.info(f"OTAScenarioMapper initialized: radius={mpac_radius_m}m, probes={num_probes}")

    def map_scenario(self, scenario: RoadTestScenario) -> OTAConfig:
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

        # 4. Calculate probe weights (simplified - full implementation requires channel matrix)
        config.probe_weights = self._calculate_probe_weights(
            scenario.base_stations[0].position if scenario.base_stations else {"lat": 0, "lon": 0, "alt": 0},
            scenario.environment.channel_model
        )

        logger.info(f"Mapping complete: {len(config.positioner_sequence)} waypoints, "
                    f"max_doppler={config.max_doppler_hz:.1f}Hz")

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

    def _calculate_probe_weights(
        self,
        bs_position: Dict[str, float],
        channel_model: ChannelModel
    ) -> List[Dict[str, any]]:
        """
        Calculate probe complex weights using ChannelEngine service

        Calls ChannelEngine microservice (http://localhost:8000) to compute
        probe weights based on 3GPP 38.901 channel models. Supports both
        OTA and Conducted testing modes.

        Args:
            bs_position: Base station position (lat, lon, alt)
            channel_model: 3GPP channel model (UMa, UMi, RMa, CDL-*, TDL-*)

        Returns:
            List of probe weights {probe_id, amplitude, phase_deg}
        """
        # Try to call ChannelEngine service
        try:
            weights = self._call_channel_engine_service(channel_model)
            if weights:
                return weights
        except Exception as e:
            logger.warning(f"ChannelEngine service unavailable: {e}. Falling back to uniform weights.")

        # Fallback: uniform weighting
        return self._uniform_weights()

    def _call_channel_engine_service(self, channel_model: ChannelModel) -> Optional[List[Dict[str, any]]]:
        """
        Call ChannelEngine service to calculate probe weights

        Makes synchronous HTTP request to ChannelEngine REST API.
        For production use, consider async implementation with aiohttp.

        Args:
            channel_model: 3GPP channel model

        Returns:
            List of probe weights or None on failure
        """
        try:
            # Map ChannelModel enum to ChannelEngine scenario type
            scenario_type_map = {
                ChannelModel.UMA: "UMa",
                ChannelModel.UMI: "UMi",
                ChannelModel.RMA: "RMa",
                ChannelModel.INH: "InH",
                ChannelModel.CDL_A: "CDL-A",
                ChannelModel.CDL_B: "CDL-B",
                ChannelModel.CDL_C: "CDL-C",
                ChannelModel.CDL_D: "CDL-D",
                ChannelModel.CDL_E: "CDL-E",
                ChannelModel.TDL_A: "TDL-A",
                ChannelModel.TDL_B: "TDL-B",
                ChannelModel.TDL_C: "TDL-C",
            }

            scenario_type = scenario_type_map.get(channel_model, "UMa")

            # Generate probe positions (uniform distribution around MPAC chamber)
            probe_positions = []
            for probe_id in range(self.num_probes):
                angle_deg = probe_id * (360 / self.num_probes)
                probe_positions.append({
                    "probe_id": probe_id,
                    "theta": 90.0,  # Zenith angle (equator of sphere)
                    "phi": angle_deg,  # Azimuth angle
                    "r": self.mpac_radius_m,
                    "polarization": "V"  # Vertical polarization
                })

            # Prepare request to ChannelEngine service
            request_data = {
                "scenario": {
                    "scenario_type": scenario_type,
                    "cluster_model": "CDL-C",  # Default cluster model
                    "frequency_mhz": 3500,  # Default 3.5 GHz
                    "use_median_lsps": False
                },
                "probe_array": {
                    "num_probes": self.num_probes,
                    "radius": self.mpac_radius_m,
                    "probe_positions": probe_positions
                },
                "mimo_config": {
                    "num_tx_antennas": 2,
                    "num_rx_antennas": 2,
                    "tx_antenna_spacing": 0.5,
                    "rx_antenna_spacing": 0.5
                }
            }

            # Call ChannelEngine service
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "http://localhost:8000/api/v1/ota/generate-probe-weights",
                    json=request_data
                )
                response.raise_for_status()

            result = response.json()

            if result.get("success"):
                # Convert ChannelEngine response to our format
                weights = []
                for probe_weight in result.get("probe_weights", []):
                    weights.append({
                        "probe_id": probe_weight.get("probe_id"),
                        "azimuth_deg": probe_weight.get("weight", {}).get("phase_deg", 0.0),
                        "amplitude": probe_weight.get("weight", {}).get("magnitude", 1.0),
                        "phase_deg": probe_weight.get("weight", {}).get("phase_deg", 0.0),
                        "polarization": probe_weight.get("polarization", "V")
                    })

                logger.info(f"Generated {len(weights)} probe weights via ChannelEngine for {scenario_type}")
                return weights
            else:
                logger.error(f"ChannelEngine returned error: {result.get('message')}")
                return None

        except httpx.ConnectError:
            logger.error("Cannot connect to ChannelEngine service at http://localhost:8000")
            return None
        except Exception as e:
            logger.error(f"ChannelEngine API call failed: {e}")
            return None

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
