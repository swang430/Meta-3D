"""
Correct test data matching actual schema definitions
"""


def get_correct_scenario_data():
    """Get correctly formatted scenario data matching actual schema"""
    return {
        "name": "Test Scenario - Urban Handover",
        "description": "Test scenario for integration testing",
        "category": "functional",
        "tags": ["test", "urban", "handover"],
        "network": {
            "type": "5G_NR",  # NetworkType.NR_5G
            "band": "n78",
            "bandwidth_mhz": 100,
            "frequency_mhz": 3500,
            "duplex_mode": "TDD"  # Must be uppercase
        },
        "base_stations": [
            {
                "bs_id": "TEST_BS1",  # Not "cell_id"
                "name": "Test Base Station 1",  # Required field
                "position": {
                    "latitude": 31.230000,
                    "longitude": 121.470000,
                    "altitude_m": 30.0
                },
                "tx_power_dbm": 43.0,  # Not "power_dbm"
                "antenna_height_m": 25.0,
                "azimuth_deg": 0.0,
                "tilt_deg": 5.0
            },
            {
                "bs_id": "TEST_BS2",
                "name": "Test Base Station 2",
                "position": {
                    "latitude": 31.235000,
                    "longitude": 121.470000,
                    "altitude_m": 30.0
                },
                "tx_power_dbm": 43.0,
                "antenna_height_m": 25.0,
                "azimuth_deg": 180.0,
                "tilt_deg": 5.0
            }
        ],
        "route": {
            "type": "generated",
            "waypoints": [
                {
                    "time_s": 0.0,  # Not "timestamp_s"
                    "position": {
                        "latitude": 31.228000,
                        "longitude": 121.470000,
                        "altitude_m": 1.5
                    },
                    "velocity": {
                        "speed_kmh": 60.0,
                        "heading_deg": 0.0
                    }
                },
                {
                    "time_s": 33.0,
                    "position": {
                        "latitude": 31.238000,
                        "longitude": 121.470000,
                        "altitude_m": 1.5
                    },
                    "velocity": {
                        "speed_kmh": 60.0,
                        "heading_deg": 0.0
                    }
                }
            ],
            "duration_s": 33.0,
            "total_distance_m": 1111.0
        },
        "environment": {
            "type": "urban_street",  # EnvironmentType enum value
            "channel_model": "UMa",  # ChannelModel.UMA (not "3gpp_uma")
            "weather": "clear",
            "traffic_density": "medium"
        },
        "traffic": {
            "type": "ftp",  # TrafficType
            "direction": "BOTH",  # Required: "DL", "UL", or "BOTH"
            "data_rate_mbps": 100.0
        },
        "events": [
            {
                "event_type": "handover",
                "trigger_time_s": 16.5,
                "source_cell_id": "TEST_BS1",  # Direct field, not in parameters
                "target_cell_id": "TEST_BS2",  # Direct field, not in parameters
                "handover_type": "intra-freq"  # Uses hyphen, not underscore
            }
        ],
        "kpi_definitions": [
            {
                "kpi_type": "throughput",
                "name": "DL Throughput",
                "unit": "Mbps",
                "target_value": 80.0,
                "threshold_min": 50.0
            },
            {
                "kpi_type": "latency",
                "name": "Round Trip Time",
                "unit": "ms",
                "target_value": 20.0,
                "threshold_max": 50.0
            }
        ]
    }


def get_minimal_scenario_data():
    """Get minimal valid scenario data"""
    return {
        "name": "Minimal Test Scenario",
        "description": "Minimal test",
        "category": "custom",
        "tags": ["test"],
        "network": {
            "type": "5G_NR",
            "band": "n78",
            "bandwidth_mhz": 100,
            "frequency_mhz": 3500,
            "duplex_mode": "TDD"
        },
        "base_stations": [
            {
                "bs_id": "BS1",
                "name": "Test BS",
                "position": {
                    "latitude": 31.0,
                    "longitude": 121.0,
                    "altitude_m": 30.0
                },
                "tx_power_dbm": 43.0,
                "antenna_height_m": 25.0,
                "azimuth_deg": 0.0,
                "tilt_deg": 5.0
            }
        ],
        "route": {
            "type": "generated",
            "waypoints": [
                {
                    "time_s": 0.0,
                    "position": {
                        "latitude": 31.0,
                        "longitude": 121.0,
                        "altitude_m": 1.5
                    },
                    "velocity": {
                        "speed_kmh": 30.0,
                        "heading_deg": 0.0
                    }
                },
                {
                    "time_s": 10.0,
                    "position": {
                        "latitude": 31.01,
                        "longitude": 121.0,
                        "altitude_m": 1.5
                    },
                    "velocity": {
                        "speed_kmh": 30.0,
                        "heading_deg": 0.0
                    }
                }
            ],
            "duration_s": 10.0,
            "total_distance_m": 1110.0
        },
        "environment": {
            "type": "urban_street",
            "channel_model": "UMa",
            "weather": "clear",
            "traffic_density": "medium"
        },
        "traffic": {
            "type": "ftp",
            "direction": "BOTH"
        },
        "events": [],
        "kpi_definitions": []
    }
