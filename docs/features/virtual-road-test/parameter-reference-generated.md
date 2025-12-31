# Parameter Reference (Auto-Generated)

> Generated at: 2025-12-31 15:23:53
> Source: `api-service/app/schemas/`

This document is auto-generated from Pydantic schema definitions.
Run `python docs/scripts/generate_parameter_docs.py` to regenerate.

---

## Table of Contents

- [Virtual Road Test - Scenario](#virtual-road-test---scenario)
- [Test Management](#test-management)
- [Calibration](#calibration)
- [Instrument](#instrument)
- [Channel Parameters](#channel-parameters)
- [Probe](#probe)
- [Synchronization](#synchronization)

---

## Virtual Road Test - Scenario

Source: `road_test/scenario.py`

### NetworkConfig

Network configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | NetworkType | Yes | - | Network type (5G NR/LTE/C-V2X) |
| `band` | str | Yes | - | Frequency band (e.g., 'n78', 'B7') |
| `bandwidth_mhz` | float | Yes | - | Channel bandwidth in MHz |
| `duplex_mode` | Literal['TDD', 'FDD' | Yes | - | Duplex mode |
| `scs_khz` | float | No | - | Subcarrier spacing in kHz (5G NR) |

### BaseStationConfig

Base station configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `bs_id` | str | Yes | - | Base station ID |
| `name` | str | Yes | - | Base station name |
| `position` | dict[str, float | Yes | - | Position {lat, lon, alt} |
| `tx_power_dbm` | float | Yes | - | Transmit power in dBm |
| `antenna_height_m` | float | No | 30.0 | Antenna height in meters |
| `antenna_config` | str | No | 4T4R | Antenna configuration |
| `azimuth_deg` | float | No | 0.0 | Antenna azimuth in degrees |
| `tilt_deg` | float | No | 0.0 | Antenna tilt in degrees |

### Waypoint

Route waypoint


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `time_s` | float | Yes | - | Time in seconds from start |
| `position` | dict[str, float | Yes | - | Position {lat, lon, alt} |
| `velocity` | dict[str, float | Yes | - | Velocity {speed_kmh, heading_deg} |

### Route

Vehicle route


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | RouteType | Yes | - | Route type |
| `waypoints` | list[Waypoint | Yes | - | List of waypoints |
| `duration_s` | float | Yes | - | Total duration in seconds |
| `total_distance_m` | float | Yes | - | Total distance in meters |
| `description` | str | No | - | Route description |

### Environment

Environment configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | EnvironmentType | Yes | - | Environment type |
| `channel_model` | ChannelModel | Yes | - | 3GPP channel model |
| `weather` | WeatherCondition | No | - | - |
| `traffic_density` | TrafficDensity | No | - | - |
| `obstructions` | list[Dict | No | - | Buildings, trees, etc. |

### TrafficConfig

Traffic configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | TrafficType | Yes | - | Traffic type |
| `direction` | Literal['DL', 'UL', 'BOTH' | Yes | - | Traffic direction |
| `data_rate_mbps` | float | No | - | Target data rate in Mbps |
| `packet_size_bytes` | int | No | - | Packet size in bytes |
| `inter_arrival_ms` | float | No | - | Inter-arrival time in ms |

### ScenarioEvent

Base scenario event


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `event_type` | EventType | Yes | - | Event type |
| `trigger_time_s` | float | Yes | - | Trigger time in seconds |
| `description` | str | No | - | Event description |

### KPIDefinition

KPI definition with target


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `kpi_type` | KPIType | Yes | - | KPI type |
| `target_value` | float | Yes | - | Target value |
| `unit` | str | Yes | - | Unit (Mbps, ms, %, dBm) |
| `percentile` | float | No | - | Percentile (50, 95, etc.) |
| `threshold_min` | float | No | - | Minimum threshold |
| `threshold_max` | float | No | - | Maximum threshold |

### ChamberInitConfig

Chamber initialization step configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `chamber_id` | str | No | - | Chamber ID |
| `timeout_seconds` | int | No | - | Timeout in seconds |
| `verify_connections` | bool | No | - | Verify connections |
| `calibrate_position_table` | bool | No | - | Calibrate position table |

### NetworkConfigStep

Network configuration step


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `frequency_mhz` | float | No | - | Frequency in MHz |
| `bandwidth_mhz` | float | No | - | Bandwidth in MHz |
| `technology` | str | No | - | Technology (5G NR, LTE, etc.) |
| `timeout_seconds` | int | No | - | Timeout in seconds |
| `verify_signal` | bool | No | - | Verify signal |

### BaseStationSetupConfig

Base station setup step configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `channel_model` | str | No | - | Channel model |
| `num_base_stations` | int | No | - | Number of base stations |
| `bs_positions` | list[Dict | No | - | Base station positions |
| `timeout_seconds` | int | No | - | Timeout in seconds |
| `verify_coverage` | bool | No | - | Verify coverage |

### OTAMapperConfig

OTA mapper step configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `route_file` | str | No | - | Route file path |
| `route_type` | str | No | - | Route type |
| `update_rate_hz` | float | No | - | Update rate in Hz |
| `enable_handover` | bool | No | - | Enable handover |
| `position_tolerance_m` | float | No | - | Position tolerance in meters |
| `timeout_seconds` | int | No | - | Timeout in seconds |

### RouteExecutionConfig

Route execution step configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `route_duration_s` | float | No | - | Route duration in seconds |
| `total_distance_m` | float | No | - | Total distance in meters |
| `environment_type` | str | No | - | Environment type |
| `monitor_kpis` | bool | No | - | Monitor KPIs |
| `log_interval_s` | float | No | - | Log interval in seconds |
| `auto_screenshot` | bool | No | - | Auto screenshot |
| `timeout_seconds` | int | No | - | Timeout in seconds |

### KPIValidationConfig

KPI validation step configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `kpi_thresholds` | KPIThresholds | No | - | KPI threshold values |
| `generate_plots` | bool | No | - | Generate plots |
| `timeout_seconds` | int | No | - | Timeout in seconds |

### ReportGenerationConfig

Report generation step configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `report_format` | str | No | - | Report format (PDF, HTML, etc.) |
| `include_raw_data` | bool | No | - | Include raw data |
| `include_screenshots` | bool | No | - | Include screenshots |
| `include_recommendations` | bool | No | - | Include recommendations |
| `timeout_seconds` | int | No | - | Timeout in seconds |

### StepConfiguration

Test step configuration for scenario


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `chamber_init` | ChamberInitConfig | No | - | Chamber initialization config |
| `network_config` | NetworkConfigStep | No | - | Network configuration |
| `base_station_setup` | BaseStationSetupConfig | No | - | Base station setup |
| `ota_mapper` | OTAMapperConfig | No | - | OTA mapper configuration |
| `route_execution` | RouteExecutionConfig | No | - | Route execution |
| `kpi_validation` | KPIValidationConfig | No | - | KPI validation |
| `report_generation` | ReportGenerationConfig | No | - | Report generation |

### RoadTestScenario

Complete road test scenario


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `id` | str | Yes | - | Scenario ID |
| `name` | str | Yes | - | Scenario name |
| `category` | ScenarioCategory | Yes | - | Scenario category |
| `source` | ScenarioSource | Yes | - | Scenario source |
| `tags` | list[str | Yes | - | Search tags |
| `description` | str | No | - | Detailed description |
| `network` | NetworkConfig | Yes | - | Network configuration |
| `base_stations` | list[BaseStationConfig | Yes | - | Base station configurations |
| `route` | Route | Yes | - | Vehicle route |
| `environment` | Environment | Yes | - | Environment configuration |
| `traffic` | TrafficConfig | Yes | - | Traffic configuration |
| `events` | list[Union[HandoverEvent, BeamSwitchEvent, RFImpairmentEvent, TrafficBurstEvent | Yes | - | Scenario events |
| `kpi_definitions` | list[KPIDefinition | Yes | - | KPI definitions |
| `step_configuration` | StepConfiguration | No | - | Pre-configured test step parameters |
| `created_at` | datetime | No | - | Creation timestamp |
| `updated_at` | datetime | No | - | Last update timestamp |
| `author` | str | No | - | Author |
| `version` | str | No | 1.0 | Scenario version |

### ScenarioCreate

Create scenario request


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | Scenario name |
| `category` | ScenarioCategory | Yes | - | Scenario category |
| `tags` | list[str | Yes | - | - |
| `description` | str | No | - | - |
| `network` | NetworkConfig | Yes | - | - |
| `base_stations` | list[BaseStationConfig | Yes | - | - |
| `route` | Route | Yes | - | - |
| `environment` | Environment | Yes | - | - |
| `traffic` | TrafficConfig | Yes | - | - |
| `events` | list[Union[HandoverEvent, BeamSwitchEvent, RFImpairmentEvent, TrafficBurstEvent | Yes | - | - |
| `kpi_definitions` | list[KPIDefinition | Yes | - | - |

### ScenarioUpdate

Update scenario request


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | No | - | - |
| `category` | ScenarioCategory | No | - | - |
| `tags` | list[str | No | - | - |
| `description` | str | No | - | - |
| `network` | NetworkConfig | No | - | - |
| `base_stations` | list[BaseStationConfig | No | - | - |
| `route` | Route | No | - | - |
| `environment` | Environment | No | - | - |
| `traffic` | TrafficConfig | No | - | - |
| `events` | list[Union[HandoverEvent, BeamSwitchEvent, RFImpairmentEvent, TrafficBurstEvent | No | - | - |
| `kpi_definitions` | list[KPIDefinition | No | - | - |

### KPIThresholds

KPI threshold values


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `min_throughput_mbps` | float | No | - | Minimum throughput in Mbps |
| `max_latency_ms` | float | No | - | Maximum latency in ms |
| `min_rsrp_dbm` | float | No | - | Minimum RSRP in dBm |
| `max_packet_loss_percent` | float | No | - | Maximum packet loss percentage |

---

## Test Management

Source: `test_plan.py`

### TestPlanCreate

Request to create a test plan


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | Test plan name |
| `description` | str | No | - | Detailed description |
| `version` | str | No | 1.0 | Version number |
| `dut_info` | dict[str, Any | No | - | Device Under Test info |
| `test_environment` | dict[str, Any | No | - | Test environment info |
| `scenario_id` | str | No | - | Linked road test scenario ID |
| `test_case_ids` | list[str | Yes | - | Array of test case UUIDs |
| `priority` | int | No | 5 | Priority (1=highest, 10=lowest) |
| `created_by` | str | No | - | User who created the plan (derived from auth if not provided) |
| `notes` | str | No | - | - |
| `tags` | list[str | No | - | Tags for categorization |

### TestPlanUpdate

Request to update a test plan


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | No | - | - |
| `description` | str | No | - | - |
| `status` | str | No | - | Test plan status (draft, ready, queued, running, etc.) |
| `dut_info` | dict[str, Any | No | - | - |
| `test_environment` | dict[str, Any | No | - | - |
| `scenario_id` | str | No | - | Linked road test scenario ID |
| `test_case_ids` | list[str | No | - | - |
| `priority` | int | No | - | - |
| `notes` | str | No | - | - |
| `tags` | list[str | No | - | - |

### TestCaseCreate

Request to create a test case


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | Test case name |
| `description` | str | No | - | - |
| `test_type` | str | Yes | - | TRP | TIS | Throughput | Handover | MIMO | ChannelModel | Custom |
| `configuration` | dict[str, Any | Yes | - | Test-specific configuration |
| `pass_criteria` | dict[str, Any | No | - | - |
| `expected_results` | dict[str, Any | No | - | - |
| `probe_selection` | dict[str, Any | No | - | - |
| `instrument_config` | dict[str, Any | No | - | - |
| `channel_model` | str | No | - | - |
| `channel_parameters` | dict[str, Any | No | - | - |
| `frequency_mhz` | float | No | - | - |
| `tx_power_dbm` | float | No | - | - |
| `bandwidth_mhz` | float | No | - | - |
| `test_duration_sec` | float | No | - | - |
| `is_template` | bool | No | False | - |
| `template_category` | str | No | - | - |
| `created_by` | str | Yes | - | User who created the test case |
| `tags` | list[str | No | - | - |

### TestCaseUpdate

Request to update a test case


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | No | - | - |
| `description` | str | No | - | - |
| `configuration` | dict[str, Any | No | - | - |
| `pass_criteria` | dict[str, Any | No | - | - |
| `expected_results` | dict[str, Any | No | - | - |
| `probe_selection` | dict[str, Any | No | - | - |
| `instrument_config` | dict[str, Any | No | - | - |
| `channel_model` | str | No | - | - |
| `channel_parameters` | dict[str, Any | No | - | - |
| `frequency_mhz` | float | No | - | - |
| `tx_power_dbm` | float | No | - | - |
| `bandwidth_mhz` | float | No | - | - |
| `test_duration_sec` | float | No | - | - |
| `tags` | list[str | No | - | - |

### TestExecutionCreate

Request to create a test execution record


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `test_plan_id` | UUID | Yes | - | - |
| `test_case_id` | UUID | Yes | - | - |
| `execution_order` | int | Yes | - | - |
| `executed_by` | str | Yes | - | - |

### TestExecutionUpdate

Request to update a test execution record


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `status` | str | No | - | - |
| `test_results` | dict[str, Any | No | - | - |
| `measurements` | dict[str, Any | No | - | - |
| `validation_pass` | bool | No | - | - |
| `validation_details` | dict[str, Any | No | - | - |
| `error_message` | str | No | - | - |
| `error_details` | dict[str, Any | No | - | - |

### QueueTestPlanRequest

Request to queue a test plan


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `test_plan_id` | UUID | Yes | - | - |
| `priority` | int | No | 5 | - |
| `scheduled_start_time` | datetime | No | - | - |
| `dependencies` | list[UUID | No | - | - |
| `queued_by` | str | Yes | - | - |
| `notes` | str | No | - | - |

### QueueItemUpdateRequest

Request to update a queue item (priority, position, etc.)


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `priority` | int | No | - | New priority (1=highest) |
| `position` | int | No | - | New position in queue |

### StartTestPlanRequest

Request to start executing a test plan


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `started_by` | str | Yes | - | - |
| `override_config` | dict[str, Any | No | - | - |

### PauseTestPlanRequest

Request to pause a running test plan


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `paused_by` | str | Yes | - | - |
| `reason` | str | No | - | - |

### ResumeTestPlanRequest

Request to resume a paused test plan


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `resumed_by` | str | Yes | - | - |

### CancelTestPlanRequest

Request to cancel a test plan


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cancelled_by` | str | Yes | - | - |
| `reason` | str | No | - | - |

### TestStepCreate

Request to create a test step


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `test_plan_id` | UUID | Yes | - | - |
| `step_number` | int | Yes | - | Step number in sequence |
| `name` | str | Yes | - | Step name |
| `description` | str | No | - | - |
| `type` | str | Yes | - | Step type: configure_instrument, run_measurement, etc. |
| `parameters` | dict[str, Any | Yes | - | Step parameters |
| `order` | int | Yes | - | Execution order |
| `expected_duration_minutes` | float | No | - | - |
| `validation_criteria` | dict[str, Any | No | - | - |
| `notes` | str | No | - | - |
| `tags` | list[str | No | - | - |

### TestStepCreateFromSequence

Request to create a test step from sequence library


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sequence_library_id` | UUID | Yes | - | ID of sequence from library |
| `order` | int | Yes | - | Execution order |
| `parameters` | dict[str, Any | No | - | Override parameters |
| `timeout_seconds` | int | No | 300 | Step timeout |
| `retry_count` | int | No | 0 | Number of retries |
| `continue_on_failure` | bool | No | False | Continue if step fails |

### TestStepUpdate

Request to update a test step


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | No | - | - |
| `description` | str | No | - | - |
| `type` | str | No | - | - |
| `parameters` | dict[str, Any | No | - | - |
| `order` | int | No | - | - |
| `expected_duration_minutes` | float | No | - | - |
| `validation_criteria` | dict[str, Any | No | - | - |
| `notes` | str | No | - | - |
| `tags` | list[str | No | - | - |
| `timeout_seconds` | int | No | - | Step timeout in seconds |
| `retry_count` | int | No | - | Number of retries on failure |
| `continue_on_failure` | bool | No | - | Whether to continue execution if this step fails |

### ReorderStepsRequest

Request to reorder steps


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `step_ids` | list[UUID | Yes | - | Ordered list of step IDs |

### TestSequenceCreate

Request to create a test sequence


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | - |
| `description` | str | No | - | - |
| `category` | str | No | - | - |
| `steps` | list[dict[str, Any | Yes | - | Array of step objects |
| `parameters` | dict[str, Any | No | - | - |
| `default_values` | dict[str, Any | No | - | - |
| `validation_rules` | dict[str, Any | No | - | - |
| `is_public` | bool | No | True | - |
| `created_by` | str | Yes | - | - |
| `tags` | list[str | No | - | - |

---

## Calibration

Source: `calibration.py`

### TRPCalibrationRequest

Request to execute TRP calibration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `standard_dut_model` | str | Yes | - | Model of standard DUT |
| `standard_dut_serial` | str | Yes | - | Serial number of standard DUT |
| `reference_trp_dbm` | float | Yes | - | Known TRP from reference lab (dBm) |
| `frequency_mhz` | float | Yes | - | Test frequency (MHz) |
| `tx_power_dbm` | float | Yes | - | Transmit power (dBm) |
| `tested_by` | str | Yes | - | Name of test engineer |
| `reference_lab` | str | No | - | Reference laboratory name |
| `reference_cert_number` | str | No | - | Reference certificate number |
| `probe_selection_mode` | str | No | all | Probe selection mode: all | ring | custom | polarization |
| `selected_rings` | list[str | No | - | Selected rings: ['upper', 'middle', 'lower'] |
| `selected_probes` | list[int | No | - | Selected probe IDs: [1, 5, 9, ...] |
| `selected_polarizations` | list[str | No | - | Selected polarizations: ['V', 'H'] |
| `theta_step_deg` | float | No | 15.0 | Theta step in degrees |
| `phi_step_deg` | float | No | 15.0 | Phi step in degrees |

### TISCalibrationRequest

Request to execute TIS calibration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `standard_dut_model` | str | Yes | - | - |
| `standard_dut_serial` | str | Yes | - | - |
| `reference_tis_dbm` | float | Yes | - | Known TIS from reference lab (dBm) |
| `frequency_mhz` | float | Yes | - | - |
| `tested_by` | str | Yes | - | - |
| `reference_lab` | str | No | - | - |
| `reference_cert_number` | str | No | - | - |
| `probe_selection_mode` | str | No | all | Probe selection mode: all | ring | custom | polarization |
| `selected_rings` | list[str | No | - | Selected rings: ['upper', 'middle', 'lower'] |
| `selected_probes` | list[int | No | - | Selected probe IDs: [1, 5, 9, ...] |
| `selected_polarizations` | list[str | No | - | Selected polarizations: ['V', 'H'] |
| `theta_step_deg` | float | No | 15.0 | Theta step in degrees |
| `phi_step_deg` | float | No | 15.0 | Phi step in degrees |

### RepeatabilityTestRequest

Request to execute repeatability test


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `test_type` | str | Yes | - | Type: TRP, TIS, or EIS |
| `dut_model` | str | Yes | - | - |
| `dut_serial` | str | Yes | - | - |
| `num_runs` | int | Yes | - | Number of repeated measurements |
| `frequency_mhz` | float | Yes | - | - |
| `tested_by` | str | Yes | - | - |

### GenerateCertificateRequest

Request to generate calibration certificate


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `trp_calibration_id` | UUID | Yes | - | - |
| `tis_calibration_id` | UUID | Yes | - | - |
| `repeatability_test_id` | UUID | Yes | - | - |
| `lab_name` | str | Yes | - | Laboratory name |
| `lab_address` | str | Yes | - | Laboratory address |
| `lab_accreditation` | str | No | ISO/IEC 17025:2017 | Accreditation standard |
| `calibrated_by` | str | Yes | - | Calibration engineer name |
| `reviewed_by` | str | Yes | - | Technical reviewer name |
| `validity_months` | int | No | 12 | Certificate validity (months) |

### CertificateDetail

Detailed certificate information


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `id` | UUID | Yes | - | - |
| `certificate_number` | str | Yes | - | - |
| `system_name` | str | Yes | - | - |
| `system_serial_number` | str | No | - | - |
| `system_configuration` | dict[str, Any | No | - | - |
| `lab_name` | str | No | - | - |
| `lab_address` | str | No | - | - |
| `lab_accreditation` | str | No | - | - |
| `calibration_date` | datetime | Yes | - | - |
| `valid_until` | datetime | Yes | - | - |
| `standards` | list[str | No | - | - |
| `trp_error_db` | float | No | - | - |
| `trp_pass` | bool | No | - | - |
| `tis_error_db` | float | No | - | - |
| `tis_pass` | bool | No | - | - |
| `repeatability_std_dev_db` | float | No | - | - |
| `repeatability_pass` | bool | No | - | - |
| `overall_pass` | bool | Yes | - | - |
| `calibrated_by` | str | No | - | - |
| `reviewed_by` | str | No | - | - |
| `digital_signature` | str | No | - | - |
| `issued_at` | datetime | Yes | - | - |

### ComparabilityTestRequest

Request to execute comparability test


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `round_robin_id` | UUID | No | - | Round-robin test ID (shared across labs) |
| `lab_name` | str | Yes | - | This laboratory's name |
| `lab_id` | str | Yes | - | This laboratory's ID |
| `lab_accreditation` | str | No | ISO/IEC 17025:2017 | Accreditation standard |
| `dut_model` | str | Yes | - | - |
| `dut_serial` | str | Yes | - | - |
| `local_trp_dbm` | float | Yes | - | TRP measured by this lab |
| `local_tis_dbm` | float | Yes | - | TIS measured by this lab |
| `local_eis_dbm` | float | No | - | EIS measured by this lab |
| `reference_measurements` | list[dict[str, Any | Yes | - | Measurements from other labs |
| `tested_by` | str | Yes | - | - |

### QuietZoneCalibrationRequest

Request to execute quiet zone validation


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `validation_type` | str | Yes | - | field_uniformity | spatial_correlation | probe_coupling | phase_stability |
| `frequency_mhz` | float | Yes | - | - |
| `tested_by` | str | Yes | - | - |
| `grid_points` | int | No | 25 | - |
| `num_antennas` | int | No | 4 | - |
| `target_channel_model` | str | No | 3GPP_UMa | - |
| `probe_ids` | list[int | No | - | - |
| `duration_sec` | float | No | 60.0 | - |

### MultiFrequencyCalibrationRequest

Multi-frequency calibration request


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `calibration_type` | str | Yes | - | Type: TRP | TIS |
| `frequency_list_mhz` | list[float | Yes | - | List of frequencies (MHz) |
| `dut_model` | str | Yes | - | - |
| `dut_serial` | str | Yes | - | - |
| `reference_trp_dbm` | float | No | - | Reference TRP for TRP calibration |
| `reference_tis_dbm` | float | No | - | Reference TIS for TIS calibration |
| `tested_by` | str | Yes | - | - |

### FrequencyCalibrationResult

Single frequency result


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `frequency_mhz` | float | Yes | - | - |
| `measured_value_dbm` | float | Yes | - | - |
| `error_db` | float | Yes | - | - |
| `validation_pass` | bool | Yes | - | - |

---

## Instrument

Source: `instrument.py`

### InstrumentModelBase

Base instrument model schema


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `vendor` | str | Yes | - | - |
| `model` | str | Yes | - | - |
| `full_name` | str | No | - | - |
| `capabilities` | dict[str, Any | Yes | - | - |
| `datasheet_url` | str | No | - | - |
| `manual_url` | str | No | - | - |
| `display_order` | int | No | 0 | - |
| `is_available` | bool | No | True | - |
| `notes` | str | No | - | - |

### InstrumentModelUpdate

Request to update an instrument model


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `vendor` | str | No | - | - |
| `model` | str | No | - | - |
| `full_name` | str | No | - | - |
| `capabilities` | dict[str, Any | No | - | - |
| `datasheet_url` | str | No | - | - |
| `manual_url` | str | No | - | - |
| `display_order` | int | No | - | - |
| `is_available` | bool | No | - | - |
| `notes` | str | No | - | - |

### InstrumentConnectionBase

Base instrument connection schema


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `endpoint` | str | No | - | - |
| `controller_ip` | str | No | - | - |
| `port` | int | No | - | - |
| `protocol` | str | No | - | - |
| `username` | str | No | - | - |
| `connection_params` | dict[str, Any | No | - | - |
| `notes` | str | No | - | - |

### InstrumentCategoryBase

Base instrument category schema


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `category_key` | str | Yes | - | - |
| `category_name` | str | Yes | - | - |
| `category_name_en` | str | No | - | - |
| `description` | str | No | - | - |
| `icon` | str | No | - | - |
| `display_order` | int | No | 0 | - |
| `is_active` | bool | No | True | - |

### InstrumentCategoryUpdate

Request to update an instrument category


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `category_name` | str | No | - | - |
| `category_name_en` | str | No | - | - |
| `selected_model_id` | UUID | No | - | - |
| `description` | str | No | - | - |
| `icon` | str | No | - | - |
| `display_order` | int | No | - | - |
| `is_active` | bool | No | - | - |

### InstrumentCatalogItem

Single item in the instrument catalog


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `category` | InstrumentCategoryResponse | Yes | - | - |
| `available_models` | list[InstrumentModelResponse | Yes | - | - |
| `selected_model` | InstrumentModelResponse | No | - | - |
| `connection` | InstrumentConnectionResponse | No | - | - |

### UpdateInstrumentCategoryRequest

Request to update an instrument category's selection and connection


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `selected_model_id` | UUID | No | - | 选择的仪器型号ID |
| `connection` | InstrumentConnectionUpdate | No | - | 连接配置 |

### InstrumentLogCreate

Request to create an instrument log


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `category_id` | UUID | Yes | - | - |
| `event_type` | str | Yes | - | - |
| `message` | str | Yes | - | - |
| `level` | str | No | info | - |
| `details` | dict[str, Any | No | - | - |
| `performed_by` | str | No | - | - |

### InstrumentStatistics

Instrument system statistics


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `total_categories` | int | Yes | - | - |
| `total_models` | int | Yes | - | - |
| `connected_instruments` | int | Yes | - | - |
| `disconnected_instruments` | int | Yes | - | - |
| `error_instruments` | int | Yes | - | - |
| `by_category` | dict[str, dict[str, Any | Yes | - | - |

---

## Channel Parameters

Source: `channel_params.py`

### SyncTimestamp

High-precision timestamp for synchronization


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sequence_id` | int | Yes | - | Monotonic sequence number |
| `timestamp_ns` | int | Yes | - | Nanosecond timestamp |
| `source` | str | No | api | Timestamp source |

### LargeScaleParams

Large-scale channel parameters (L2 sync - small data)

Updated at ~100Hz for dynamic scenarios.


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timestamp` | SyncTimestamp | Yes | - | - |
| `scenario_id` | UUID | No | - | - |
| `position_index` | int | No | 0 | Position index in trajectory |
| `n_paths` | int | No | 1 | Number of multipath components |
| `path_loss_db` | list[float | Yes | - | Path loss per path (dB) |
| `aod_azimuth` | list[float | Yes | - | AoD azimuth per path (degrees) |
| `aod_elevation` | list[float | Yes | - | AoD elevation per path (degrees) |
| `aoa_azimuth` | list[float | Yes | - | AoA azimuth per path (degrees) |
| `aoa_elevation` | list[float | Yes | - | AoA elevation per path (degrees) |
| `delay_ns` | list[float | Yes | - | Delay per path (ns) |
| `doppler_hz` | list[float | Yes | - | Doppler shift per path (Hz) |
| `xpr_db` | list[float | Yes | - | Cross-polarization ratio per path (dB) |
| `cluster_powers` | list[float | No | - | - |
| `cluster_delays` | list[float | No | - | - |

### ChannelMatrixMetadata

Metadata for channel matrix (actual matrix in SharedMemory)


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timestamp` | SyncTimestamp | Yes | - | - |
| `n_rx` | int | Yes | - | Number of RX antennas |
| `n_tx` | int | Yes | - | Number of TX antennas |
| `n_subcarriers` | int | Yes | - | Number of subcarriers |
| `n_ofdm_symbols` | int | Yes | - | Number of OFDM symbols |
| `subcarrier_spacing_khz` | float | No | 15.0 | Subcarrier spacing (kHz) |
| `shm_name` | str | Yes | - | Shared memory segment name |
| `shm_offset` | int | No | 0 | Offset in shared memory |
| `shm_size` | int | Yes | - | Size in bytes |
| `dtype` | str | No | complex64 | NumPy dtype string |

### ParameterSyncConfig

Configuration for parameter synchronization


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enabled` | bool | No | True | Enable parameter sync |
| `update_rate_hz` | float | No | 100.0 | Target update rate |
| `channel_model` | ChannelModel | Yes | - | - |
| `use_shared_memory` | bool | No | True | Use shared memory for large data |
| `zmq_endpoint` | str | No | ipc:///tmp/mimo_large_scale_params | ZeroMQ endpoint |
| `buffer_size` | int | No | 100 | Ring buffer size |

### ParameterSyncStatus

Status of parameter synchronization subsystem


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `is_running` | bool | No | False | - |
| `is_connected` | bool | No | False | - |
| `last_update_time` | datetime | No | - | - |
| `update_count` | int | No | 0 | - |
| `error_count` | int | No | 0 | - |
| `dropped_count` | int | No | 0 | - |
| `latency_avg_ms` | float | No | 0.0 | - |
| `latency_max_ms` | float | No | 0.0 | - |
| `update_rate_actual_hz` | float | No | 0.0 | - |
| `buffer_fill_percent` | float | No | 0.0 | - |
| `current_n_paths` | int | No | 0 | - |
| `current_sequence_id` | int | No | 0 | - |

### ParameterPublishRequest

Request to publish channel parameters


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `params` | LargeScaleParams | Yes | - | - |
| `priority` | int | No | 5 | Publishing priority |

### ParameterHistoryRequest

Request for parameter history


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_sequence_id` | int | No | - | - |
| `end_sequence_id` | int | No | - | - |
| `count` | int | No | 10 | Number of records |

---

## Probe

Source: `probe.py`

### ProbePosition

Probe 3D position


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `azimuth` | float | Yes | - | 方位角（度）0-360 |
| `elevation` | float | Yes | - | 仰角（度）-90-90 |
| `radius` | float | Yes | - | 半径（米） |

### ProbeCreateRequest

Request to create a new probe


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `probe_number` | int | Yes | - | 探头编号 1-32 |
| `name` | str | No | - | - |
| `ring` | int | Yes | - | 环编号 1-5 (基于仰角: 1=顶层>60°, 2=上层30-60°, 3=中层±30°, 4=下层-60~-30°, 5=底层<-60°) |
| `polarization` | str | Yes | - | 极化: V | H |
| `position` | ProbePosition | Yes | - | - |
| `is_active` | bool | No | True | 是否启用 |
| `hardware_id` | str | No | - | - |
| `channel_port` | int | No | - | - |
| `frequency_range_mhz` | dict[str, float | No | - | 频率范围 {min, max} |
| `max_power_dbm` | float | No | - | - |
| `gain_db` | float | No | - | - |
| `notes` | str | No | - | - |
| `created_by` | str | No | - | - |

### ProbeUpdateRequest

Request to update a probe


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | No | - | - |
| `ring` | int | No | - | 环编号 1-5 (基于仰角自动计算) |
| `polarization` | str | No | - | - |
| `position` | ProbePosition | No | - | - |
| `is_active` | bool | No | - | - |
| `is_connected` | bool | No | - | - |
| `status` | str | No | - | - |
| `hardware_id` | str | No | - | - |
| `channel_port` | int | No | - | - |
| `last_calibration_date` | datetime | No | - | - |
| `calibration_status` | str | No | - | - |
| `calibration_data` | dict[str, Any | No | - | - |
| `frequency_range_mhz` | dict[str, float | No | - | - |
| `max_power_dbm` | float | No | - | - |
| `gain_db` | float | No | - | - |
| `notes` | str | No | - | - |

### BulkProbeRequest

Request to replace all probes in bulk


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `probes` | list[ProbeCreateRequest | Yes | - | - |

### ProbeConfigurationCreate

Request to create a probe configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | - |
| `description` | str | No | - | - |
| `version` | str | No | 1.0 | - |
| `probe_data` | list[ProbeResponse | Yes | - | - |
| `created_by` | str | Yes | - | - |
| `imported_from` | str | No | - | - |

### ProbeConfigurationUpdate

Request to update a probe configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | No | - | - |
| `description` | str | No | - | - |
| `version` | str | No | - | - |
| `probe_data` | list[ProbeResponse | No | - | - |
| `is_active` | bool | No | - | - |

### ProbeStatistics

Probe system statistics


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `total_probes` | int | Yes | - | - |
| `active_probes` | int | Yes | - | - |
| `connected_probes` | int | Yes | - | - |
| `calibrated_probes` | int | Yes | - | - |
| `by_ring` | dict[int, int | Yes | - | - |
| `by_polarization` | dict[str, int | Yes | - | - |
| `by_status` | dict[str, int | Yes | - | - |

---

## Synchronization

Source: `sync.py`

### ClockConfig

Clock configuration request


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | ClockSource | Yes | - | Clock source |
| `reference_frequency_hz` | float | No | 10000000 | Reference frequency in Hz |
| `output_enabled` | bool | No | True | Enable clock output |

### InstrumentClockStatus

Individual instrument clock status


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `instrument_id` | str | Yes | - | - |
| `instrument_name` | str | Yes | - | - |
| `status` | ClockStatusResponse | Yes | - | - |
| `last_updated` | datetime | Yes | - | - |

### TriggerConfig

Trigger configuration


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source` | TriggerSource | Yes | - | Trigger source |
| `edge` | TriggerEdge | Yes | - | Trigger edge |
| `mode` | TriggerMode | Yes | - | Trigger mode |
| `delay_ns` | float | No | 0.0 | Trigger delay in nanoseconds |
| `level_v` | float | No | 1.5 | Trigger level in volts |
| `holdoff_ns` | float | No | 0.0 | Trigger holdoff in nanoseconds |

### TriggerSequenceStep

Single step in trigger sequence


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `order` | int | Yes | - | Step order |
| `action` | str | Yes | - | Action: arm | trigger | wait | configure |
| `instrument_id` | str | Yes | - | Target instrument |
| `delay_after_us` | float | No | 0.0 | Delay after step in microseconds |
| `parameters` | dict[str, Any | No | - | Action-specific parameters |

### TriggerSequenceCreate

Create trigger sequence request


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | Yes | - | Sequence name |
| `description` | str | No | - | - |
| `steps` | list[TriggerSequenceStep | Yes | - | - |
| `repeat_count` | int | No | 1 | Number of times to repeat sequence |

### SyncMetrics

Synchronization performance metrics


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `latency_avg_ms` | float | No | 0.0 | Average latency in ms |
| `latency_p50_ms` | float | No | 0.0 | P50 latency in ms |
| `latency_p95_ms` | float | No | 0.0 | P95 latency in ms |
| `latency_p99_ms` | float | No | 0.0 | P99 latency in ms |
| `latency_max_ms` | float | No | 0.0 | Max latency in ms |
| `jitter_ms` | float | No | 0.0 | Jitter in ms |
| `messages_per_second` | float | No | 0.0 | Message throughput |
| `dropped_count` | int | No | 0 | Number of dropped messages |
| `error_count` | int | No | 0 | Number of errors |

### InstrumentSyncState

Individual instrument sync state


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `instrument_id` | str | Yes | - | - |
| `instrument_name` | str | Yes | - | - |
| `clock_locked` | bool | Yes | - | - |
| `trigger_armed` | bool | Yes | - | - |
| `last_trigger_time` | datetime | No | - | - |
| `status` | str | Yes | - | - |

### SystemSyncStatus

Complete system synchronization status


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | SyncState | Yes | - | - |
| `is_synchronized` | bool | No | False | Whether system is fully synchronized |
| `clock_locked` | bool | No | False | All clocks locked to reference |
| `clock_source` | ClockSource | Yes | - | - |
| `clock_coherence_verified` | bool | No | False | Clock coherence verified |
| `trigger_armed` | bool | No | False | Trigger system armed |
| `active_sequence` | str | No | - | Active trigger sequence name |
| `parameter_sync_active` | bool | No | False | Parameter synchronization active |
| `metrics` | SyncMetrics | Yes | - | - |
| `instruments` | list[InstrumentSyncState | Yes | - | - |
| `last_sync_check` | datetime | No | - | - |
| `uptime_seconds` | float | No | 0.0 | - |

### SyncInitRequest

Initialize synchronization request


| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `clock_source` | ClockSource | Yes | - | - |
| `auto_configure_triggers` | bool | No | True | Auto-configure default triggers |
| `verify_coherence` | bool | No | True | Verify clock coherence after init |
| `timeout_seconds` | float | No | 30.0 | Initialization timeout |

---
