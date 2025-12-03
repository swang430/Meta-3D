"""
Standard Scenario Library

Pre-defined road test scenarios based on 3GPP, CTIA, and 5GAA standards
"""

from app.schemas.road_test import (
    RoadTestScenario,
    NetworkConfig,
    BaseStationConfig,
    Route,
    Waypoint,
    Environment,
    TrafficConfig,
    HandoverEvent,
    BeamSwitchEvent,
    KPIDefinition,
    NetworkType,
    ScenarioCategory,
    ScenarioSource,
    ChannelModel,
    RouteType,
    EnvironmentType,
    WeatherCondition,
    TrafficDensity,
    TrafficType,
    KPIType,
)
import math
from datetime import datetime


def generate_linear_route(
    start_pos: tuple[float, float, float],
    end_pos: tuple[float, float, float],
    speed_kmh: float,
    num_waypoints: int = 20
) -> Route:
    """Generate a linear route between two points"""
    waypoints = []

    lat1, lon1, alt1 = start_pos
    lat2, lon2, alt2 = end_pos

    # Calculate distance (simplified)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    dalt = alt2 - alt1
    distance_m = math.sqrt((dlat * 111000)**2 + (dlon * 111000 * math.cos(math.radians(lat1)))**2)

    duration_s = (distance_m / 1000) / speed_kmh * 3600
    heading_deg = math.degrees(math.atan2(dlon, dlat))

    for i in range(num_waypoints):
        t = i / (num_waypoints - 1)
        time_s = t * duration_s

        lat = lat1 + t * dlat
        lon = lon1 + t * dlon
        alt = alt1 + t * dalt

        waypoints.append(Waypoint(
            time_s=time_s,
            position={"lat": lat, "lon": lon, "alt": alt},
            velocity={"speed_kmh": speed_kmh, "heading_deg": heading_deg}
        ))

    return Route(
        type=RouteType.GENERATED,
        waypoints=waypoints,
        duration_s=duration_s,
        total_distance_m=distance_m
    )


# ===== Standard Scenarios =====

def create_3gpp_uma_handover_scenario() -> RoadTestScenario:
    """
    3GPP UMa Handover Scenario

    Urban Macro cell scenario with inter-cell handover at cell edge.
    Based on 3GPP TR 38.901.
    """
    return RoadTestScenario(
        id="3gpp-uma-handover-001",
        name="3GPP UMa Handover",
        category=ScenarioCategory.STANDARD,
        source=ScenarioSource.STANDARD,
        tags=["3GPP", "UMa", "handover", "5G NR", "urban"],
        description="Urban Macro cell scenario with single handover event. Vehicle drives from BS1 coverage to BS2 coverage at 60 km/h.",

        network=NetworkConfig(
            type=NetworkType.NR_5G,
            band="n78",
            bandwidth_mhz=100,
            duplex_mode="TDD",
            scs_khz=30
        ),

        base_stations=[
            BaseStationConfig(
                bs_id="BS1",
                name="Base Station 1",
                position={"lat": 31.230390, "lon": 121.473702, "alt": 30.0},
                tx_power_dbm=46.0,
                antenna_height_m=25.0,
                antenna_config="4T4R",
                azimuth_deg=0.0,
                tilt_deg=10.0
            ),
            BaseStationConfig(
                bs_id="BS2",
                name="Base Station 2",
                position={"lat": 31.235390, "lon": 121.473702, "alt": 30.0},
                tx_power_dbm=46.0,
                antenna_height_m=25.0,
                antenna_config="4T4R",
                azimuth_deg=180.0,
                tilt_deg=10.0
            )
        ],

        route=generate_linear_route(
            start_pos=(31.228390, 121.473702, 1.5),
            end_pos=(31.237390, 121.473702, 1.5),
            speed_kmh=60,
            num_waypoints=30
        ),

        environment=Environment(
            type=EnvironmentType.URBAN_STREET,
            channel_model=ChannelModel.UMA,
            weather=WeatherCondition.CLEAR,
            traffic_density=TrafficDensity.MEDIUM
        ),

        traffic=TrafficConfig(
            type=TrafficType.FTP,
            direction="DL",
            data_rate_mbps=50.0
        ),

        events=[
            HandoverEvent(
                trigger_time_s=27.0,
                source_cell_id="BS1",
                target_cell_id="BS2",
                handover_type="intra-freq",
                description="Handover at cell edge"
            )
        ],

        kpi_definitions=[
            KPIDefinition(
                kpi_type=KPIType.THROUGHPUT,
                target_value=45.0,
                unit="Mbps",
                percentile=50,
                threshold_min=30.0
            ),
            KPIDefinition(
                kpi_type=KPIType.LATENCY,
                target_value=20.0,
                unit="ms",
                percentile=95,
                threshold_max=50.0
            ),
            KPIDefinition(
                kpi_type=KPIType.HANDOVER_SUCCESS_RATE,
                target_value=99.0,
                unit="%",
                threshold_min=95.0
            )
        ],

        created_at=datetime.now(),
        author="Meta-3D Team",
        version="1.0"
    )


def create_3gpp_umi_beam_tracking_scenario() -> RoadTestScenario:
    """
    3GPP UMi Beam Tracking Scenario

    Urban Micro cell scenario with beam switching events.
    Tests mmWave beam management algorithms.
    """
    return RoadTestScenario(
        id="3gpp-umi-beam-tracking-001",
        name="3GPP UMi Beam Tracking",
        category=ScenarioCategory.FUNCTIONAL,
        source=ScenarioSource.STANDARD,
        tags=["3GPP", "UMi", "beam-tracking", "5G NR", "mmWave"],
        description="Urban Micro cell scenario testing mmWave beam tracking. Vehicle makes 90-degree turn requiring beam switches.",

        network=NetworkConfig(
            type=NetworkType.NR_5G,
            band="n257",  # 28 GHz mmWave
            bandwidth_mhz=100,
            duplex_mode="TDD",
            scs_khz=120
        ),

        base_stations=[
            BaseStationConfig(
                bs_id="BS1",
                name="mmWave Base Station",
                position={"lat": 31.230390, "lon": 121.473702, "alt": 10.0},
                tx_power_dbm=40.0,
                antenna_height_m=10.0,
                antenna_config="64T64R",  # Massive MIMO
                azimuth_deg=45.0,
                tilt_deg=5.0
            )
        ],

        route=generate_linear_route(
            start_pos=(31.229390, 121.472702, 1.5),
            end_pos=(31.231390, 121.474702, 1.5),
            speed_kmh=30,
            num_waypoints=25
        ),

        environment=Environment(
            type=EnvironmentType.URBAN_STREET,
            channel_model=ChannelModel.UMI,
            weather=WeatherCondition.CLEAR,
            traffic_density=TrafficDensity.HIGH
        ),

        traffic=TrafficConfig(
            type=TrafficType.VIDEO,
            direction="DL",
            data_rate_mbps=100.0
        ),

        events=[
            BeamSwitchEvent(
                trigger_time_s=8.0,
                source_beam_id=0,
                target_beam_id=1,
                reason="RSRP dropped below threshold",
                description="First beam switch"
            ),
            BeamSwitchEvent(
                trigger_time_s=16.0,
                source_beam_id=1,
                target_beam_id=2,
                reason="Vehicle rotation, beam alignment changed",
                description="Second beam switch"
            )
        ],

        kpi_definitions=[
            KPIDefinition(
                kpi_type=KPIType.THROUGHPUT,
                target_value=90.0,
                unit="Mbps",
                percentile=50,
                threshold_min=70.0
            ),
            KPIDefinition(
                kpi_type=KPIType.RSRP,
                target_value=-80.0,
                unit="dBm",
                percentile=50,
                threshold_min=-100.0
            ),
            KPIDefinition(
                kpi_type=KPIType.BLER,
                target_value=1.0,
                unit="%",
                percentile=95,
                threshold_max=5.0
            )
        ],

        created_at=datetime.now(),
        author="Meta-3D Team",
        version="1.0"
    )


def create_highway_high_speed_scenario() -> RoadTestScenario:
    """
    Highway High Speed Scenario

    High-speed highway scenario at 120 km/h with multiple handovers.
    Tests performance under high Doppler and frequent cell changes.
    """
    return RoadTestScenario(
        id="highway-high-speed-001",
        name="Highway High Speed",
        category=ScenarioCategory.ENVIRONMENT,
        source=ScenarioSource.STANDARD,
        tags=["highway", "high-speed", "5G NR", "rural"],
        description="Highway scenario at 120 km/h with 3 handovers. Tests high Doppler and cell edge performance.",

        network=NetworkConfig(
            type=NetworkType.NR_5G,
            band="n78",
            bandwidth_mhz=100,
            duplex_mode="TDD",
            scs_khz=30
        ),

        base_stations=[
            BaseStationConfig(
                bs_id=f"BS{i+1}",
                name=f"Highway Base Station {i+1}",
                position={"lat": 31.230390 + i * 0.005, "lon": 121.473702, "alt": 35.0},
                tx_power_dbm=46.0,
                antenna_height_m=35.0,
                antenna_config="4T4R",
                azimuth_deg=0.0 if i % 2 == 0 else 180.0,
                tilt_deg=8.0
            )
            for i in range(4)
        ],

        route=generate_linear_route(
            start_pos=(31.228390, 121.473702, 1.5),
            end_pos=(31.248390, 121.473702, 1.5),
            speed_kmh=120,
            num_waypoints=40
        ),

        environment=Environment(
            type=EnvironmentType.HIGHWAY,
            channel_model=ChannelModel.RMA,  # Rural Macro
            weather=WeatherCondition.CLEAR,
            traffic_density=TrafficDensity.LOW
        ),

        traffic=TrafficConfig(
            type=TrafficType.FTP,
            direction="BOTH",
            data_rate_mbps=80.0
        ),

        events=[
            HandoverEvent(
                trigger_time_s=20.0,
                source_cell_id="BS1",
                target_cell_id="BS2",
                handover_type="intra-freq",
                description="First handover"
            ),
            HandoverEvent(
                trigger_time_s=40.0,
                source_cell_id="BS2",
                target_cell_id="BS3",
                handover_type="intra-freq",
                description="Second handover"
            ),
            HandoverEvent(
                trigger_time_s=60.0,
                source_cell_id="BS3",
                target_cell_id="BS4",
                handover_type="intra-freq",
                description="Third handover"
            )
        ],

        kpi_definitions=[
            KPIDefinition(
                kpi_type=KPIType.THROUGHPUT,
                target_value=70.0,
                unit="Mbps",
                percentile=50,
                threshold_min=50.0
            ),
            KPIDefinition(
                kpi_type=KPIType.HANDOVER_SUCCESS_RATE,
                target_value=98.0,
                unit="%",
                threshold_min=95.0
            ),
            KPIDefinition(
                kpi_type=KPIType.LATENCY,
                target_value=30.0,
                unit="ms",
                percentile=95,
                threshold_max=60.0
            )
        ],

        created_at=datetime.now(),
        author="Meta-3D Team",
        version="1.0"
    )


def create_tunnel_scenario() -> RoadTestScenario:
    """
    Tunnel Scenario

    Tunnel entry/exit scenario with signal loss and recovery.
    Tests link adaptation and recovery mechanisms.
    """
    from app.schemas.road_test import RFImpairmentEvent

    return RoadTestScenario(
        id="tunnel-entry-exit-001",
        name="Tunnel Entry/Exit",
        category=ScenarioCategory.EXTREME,
        source=ScenarioSource.STANDARD,
        tags=["tunnel", "signal-loss", "LTE", "extreme"],
        description="Tunnel scenario with signal blockage and recovery. Vehicle enters tunnel at 80 km/h with 5s signal loss.",

        network=NetworkConfig(
            type=NetworkType.LTE,
            band="B7",
            bandwidth_mhz=20,
            duplex_mode="FDD"
        ),

        base_stations=[
            BaseStationConfig(
                bs_id="BS1",
                name="Tunnel Entrance BS",
                position={"lat": 31.230390, "lon": 121.473702, "alt": 20.0},
                tx_power_dbm=43.0,
                antenna_height_m=20.0,
                antenna_config="2T2R",
                azimuth_deg=0.0,
                tilt_deg=12.0
            ),
            BaseStationConfig(
                bs_id="BS2",
                name="Tunnel Exit BS",
                position={"lat": 31.235390, "lon": 121.473702, "alt": 20.0},
                tx_power_dbm=43.0,
                antenna_height_m=20.0,
                antenna_config="2T2R",
                azimuth_deg=180.0,
                tilt_deg=12.0
            )
        ],

        route=generate_linear_route(
            start_pos=(31.228390, 121.473702, 1.5),
            end_pos=(31.237390, 121.473702, 1.5),
            speed_kmh=80,
            num_waypoints=30
        ),

        environment=Environment(
            type=EnvironmentType.TUNNEL,
            channel_model=ChannelModel.UMA,  # Custom tunnel model in practice
            weather=WeatherCondition.CLEAR,
            traffic_density=TrafficDensity.MEDIUM
        ),

        traffic=TrafficConfig(
            type=TrafficType.VIDEO,
            direction="DL",
            data_rate_mbps=10.0
        ),

        events=[
            RFImpairmentEvent(
                trigger_time_s=18.0,
                impairment_type="signal_loss",
                duration_s=5.0,
                severity_db=-20.0,
                description="Signal blockage inside tunnel"
            )
        ],

        kpi_definitions=[
            KPIDefinition(
                kpi_type=KPIType.THROUGHPUT,
                target_value=8.0,
                unit="Mbps",
                percentile=50,
                threshold_min=5.0
            ),
            KPIDefinition(
                kpi_type=KPIType.BLER,
                target_value=5.0,
                unit="%",
                percentile=95,
                threshold_max=10.0
            )
        ],

        created_at=datetime.now(),
        author="Meta-3D Team",
        version="1.0"
    )


def create_urban_canyon_scenario() -> RoadTestScenario:
    """
    Urban Canyon Scenario

    Dense urban environment with buildings causing multipath and shadowing.
    Tests NLOS performance and interference handling.
    """
    return RoadTestScenario(
        id="urban-canyon-001",
        name="Urban Canyon",
        category=ScenarioCategory.ENVIRONMENT,
        source=ScenarioSource.STANDARD,
        tags=["urban", "NLOS", "multipath", "5G NR"],
        description="Dense urban canyon with high-rise buildings. Tests NLOS propagation and multipath handling.",

        network=NetworkConfig(
            type=NetworkType.NR_5G,
            band="n78",
            bandwidth_mhz=100,
            duplex_mode="TDD",
            scs_khz=30
        ),

        base_stations=[
            BaseStationConfig(
                bs_id="BS1",
                name="Urban Micro BS",
                position={"lat": 31.230390, "lon": 121.473702, "alt": 10.0},
                tx_power_dbm=40.0,
                antenna_height_m=10.0,
                antenna_config="4T4R",
                azimuth_deg=45.0,
                tilt_deg=8.0
            )
        ],

        route=generate_linear_route(
            start_pos=(31.229390, 121.472702, 1.5),
            end_pos=(31.231390, 121.474702, 1.5),
            speed_kmh=40,
            num_waypoints=20
        ),

        environment=Environment(
            type=EnvironmentType.URBAN_CANYON,
            channel_model=ChannelModel.UMI,
            weather=WeatherCondition.CLEAR,
            traffic_density=TrafficDensity.HIGH,
            obstructions=[
                {"type": "building", "height_m": 80, "position": {"lat": 31.230000, "lon": 121.473000}},
                {"type": "building", "height_m": 100, "position": {"lat": 31.230500, "lon": 121.473500}},
                {"type": "building", "height_m": 90, "position": {"lat": 31.230000, "lon": 121.474000}}
            ]
        ),

        traffic=TrafficConfig(
            type=TrafficType.WEB,
            direction="BOTH",
            data_rate_mbps=20.0
        ),

        events=[],

        kpi_definitions=[
            KPIDefinition(
                kpi_type=KPIType.THROUGHPUT,
                target_value=18.0,
                unit="Mbps",
                percentile=50,
                threshold_min=10.0
            ),
            KPIDefinition(
                kpi_type=KPIType.RSRP,
                target_value=-90.0,
                unit="dBm",
                percentile=50,
                threshold_min=-110.0
            ),
            KPIDefinition(
                kpi_type=KPIType.SINR,
                target_value=10.0,
                unit="dB",
                percentile=50,
                threshold_min=0.0
            )
        ],

        created_at=datetime.now(),
        author="Meta-3D Team",
        version="1.0"
    )


# ===== Scenario Library =====

STANDARD_SCENARIOS = [
    create_3gpp_uma_handover_scenario(),
    create_3gpp_umi_beam_tracking_scenario(),
    create_highway_high_speed_scenario(),
    create_tunnel_scenario(),
    create_urban_canyon_scenario(),
]


def get_scenario_by_id(scenario_id: str) -> RoadTestScenario | None:
    """Get scenario by ID"""
    for scenario in STANDARD_SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    return None


def get_scenarios_by_category(category: ScenarioCategory) -> list[RoadTestScenario]:
    """Get scenarios by category"""
    return [s for s in STANDARD_SCENARIOS if s.category == category]


def get_all_scenarios() -> list[RoadTestScenario]:
    """Get all standard scenarios"""
    return STANDARD_SCENARIOS.copy()
