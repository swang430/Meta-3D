# Parameter Reference - Virtual Road Test

All configurable parameters at a glance.

---

## Step Sources Overview

测试管理中的测试步骤来自两部分：

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Plan Steps                          │
├─────────────────────────┬───────────────────────────────────┤
│  Virtual Road Test      │  Generic Test Steps               │
│  (Section 2)            │  (Section 2B)                     │
├─────────────────────────┼───────────────────────────────────┤
│  8 predefined steps:    │  Flexible custom steps:           │
│  • chamber_init         │  • configure_instrument           │
│  • network_config       │  • run_measurement                │
│  • base_station_setup   │  • validate_result                │
│  • ota_mapper           │  • generate_report                │
│  • route_execution      │  • wait                           │
│  • kpi_validation       │  • custom                         │
│  • report_generation    │                                   │
│  • environment_setup    │  Parameters: JSON (flexible)      │
├─────────────────────────┴───────────────────────────────────┤
│  Source: scenario.step_configuration                        │
│  Source: Test Management module                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Navigation

| Section | Description |
|---------|-------------|
| [1. Scenario Parameters](#1-scenario-parameters) | 场景配置参数 |
| [2. Step Configuration (Virtual Road Test)](#2-step-configuration-virtual-road-test) | 虚拟路测步骤参数 |
| [2B. Test Step (Generic)](#2b-test-step-generic) | 通用测试步骤参数 |
| [3. Test Plan Parameters](#3-test-plan-parameters) | 测试计划参数 |
| [4. Priority Rules](#4-priority-rules) | 参数优先级 |

---

## 1. Scenario Parameters

### 1.1 Basic Info

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | 场景名称 |
| `description` | string | No | 场景描述 |
| `category` | enum | Yes | `standard` / `functional` / `performance` / `environment` / `extreme` / `custom` |
| `tags` | string[] | No | 搜索标签 |

### 1.2 Network Config (`network`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | enum | - | `5G_NR` / `LTE` / `C-V2X` |
| `band` | string | - | 频段 (e.g., `n78`, `B7`) |
| `bandwidth_mhz` | number | - | 带宽 (MHz) |
| `duplex_mode` | enum | - | `TDD` / `FDD` |
| `scs_khz` | number | - | 子载波间隔 (kHz), 5G NR only |

### 1.3 Base Station Config (`base_stations[]`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bs_id` | string | - | 基站ID |
| `name` | string | - | 基站名称 |
| `position` | object | - | `{lat, lon, alt}` |
| `tx_power_dbm` | number | - | 发射功率 (dBm) |
| `antenna_height_m` | number | 30.0 | 天线高度 (m) |
| `antenna_config` | string | "4T4R" | 天线配置 |
| `azimuth_deg` | number | 0.0 | 方位角 |
| `tilt_deg` | number | 0.0 | 下倾角 |

### 1.4 Route Config (`route`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | enum | - | `predefined` / `recorded` / `generated` |
| `waypoints` | array | - | 路径点列表 |
| `duration_s` | number | - | 总时长 (秒) |
| `total_distance_m` | number | - | 总距离 (米) |

### 1.5 Environment Config (`environment`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | enum | - | `urban_canyon` / `urban_street` / `highway` / `tunnel` / `parking_lot` / `rural` |
| `channel_model` | enum | - | `UMa` / `UMi` / `RMa` / `InH` / `CDL-A` ~ `CDL-E` / `TDL-A` ~ `TDL-C` |
| `weather` | enum | clear | `clear` / `rain` / `fog` / `snow` |
| `traffic_density` | enum | medium | `low` / `medium` / `high` |

### 1.6 Traffic Config (`traffic`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | enum | - | `ftp` / `video` / `voip` / `web` / `gaming` |
| `direction` | enum | - | `DL` / `UL` / `BOTH` |
| `data_rate_mbps` | number | - | 目标数据速率 |

### 1.7 KPI Definition (`kpi_definitions[]`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kpi_type` | enum | - | `throughput` / `latency` / `bler` / `rsrp` / `sinr` / `handover_success_rate` |
| `target_value` | number | - | 目标值 |
| `unit` | string | - | 单位 |
| `percentile` | number | - | 百分位 (50, 95, etc.) |
| `threshold_min` | number | - | 最小阈值 |
| `threshold_max` | number | - | 最大阈值 |

---

## 2. Step Configuration (Virtual Road Test)

Pre-configure test step parameters in scenario. Available in `step_configuration` field.
These are the **8 predefined steps** for virtual road test scenarios.

### 2.1 Chamber Init (`chamber_init`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `chamber_id` | string | "MPAC-1" | 暗室ID |
| `timeout_seconds` | number | 300 | 超时时间 (秒) |
| `verify_connections` | boolean | true | 验证连接 |
| `calibrate_position_table` | boolean | true | 校准转台 |

### 2.2 Network Config (`network_config`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `frequency_mhz` | number | 3500 | 频率 (MHz) |
| `bandwidth_mhz` | number | 100 | 带宽 (MHz) |
| `technology` | string | "5G NR" | 技术标准 |
| `timeout_seconds` | number | 240 | 超时时间 (秒) |
| `verify_signal` | boolean | true | 验证信号 |

### 2.3 Base Station Setup (`base_station_setup`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel_model` | string | "UMa" | 信道模型 |
| `num_base_stations` | number | 1 | 基站数量 |
| `timeout_seconds` | number | 300 | 超时时间 (秒) |
| `verify_coverage` | boolean | true | 验证覆盖 |

### 2.4 OTA Mapper (`ota_mapper`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `route_type` | string | "urban" | 路径类型 |
| `update_rate_hz` | number | 10 | 更新频率 (Hz) |
| `enable_handover` | boolean | true | 启用切换 |
| `timeout_seconds` | number | 180 | 超时时间 (秒) |

### 2.5 Route Execution (`route_execution`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `route_duration_s` | number | (from env) | 路径时长 |
| `total_distance_m` | number | (from env) | 总距离 |
| `monitor_kpis` | boolean | true | 监控KPI |
| `log_interval_s` | number | 1.0 | 日志间隔 (秒) |
| `auto_screenshot` | boolean | false | 自动截图 |
| `timeout_seconds` | number | duration+600 | 超时时间 |

### 2.6 KPI Validation (`kpi_validation`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kpi_thresholds.min_throughput_mbps` | number | 50 | 最小吞吐量 |
| `kpi_thresholds.max_latency_ms` | number | 50 | 最大延迟 |
| `kpi_thresholds.min_rsrp_dbm` | number | -110 | 最小RSRP |
| `kpi_thresholds.max_packet_loss_percent` | number | 5 | 最大丢包率 |
| `generate_plots` | boolean | true | 生成图表 |
| `timeout_seconds` | number | 300 | 超时时间 |

### 2.7 Report Generation (`report_generation`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `report_format` | string | "PDF" | 格式 (`PDF`/`HTML`) |
| `include_raw_data` | boolean | false | 包含原始数据 |
| `include_screenshots` | boolean | false | 包含截图 |
| `include_recommendations` | boolean | true | 包含建议 |
| `timeout_seconds` | number | 60 | 超时时间 |

---

## 2B. Test Step (Generic)

测试管理模块的通用测试步骤，可独立于虚拟路测使用。支持灵活的自定义配置。

### 2B.1 Basic Info

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | 步骤名称 |
| `description` | string | No | 步骤描述 |
| `type` | string | Yes | 步骤类型 (见下表) |
| `step_number` | number | Yes | 步骤序号 |
| `order` | number | Yes | 执行顺序 |

### 2B.2 Step Types

| Type | Description |
|------|-------------|
| `configure_instrument` | 配置仪器 |
| `run_measurement` | 执行测量 |
| `validate_result` | 验证结果 |
| `generate_report` | 生成报告 |
| `wait` | 等待 |
| `custom` | 自定义 |

### 2B.3 Parameters (`parameters`)

灵活的JSON结构，根据step type不同而变化。

```json
{
  "instrument_id": "channel_emulator_1",
  "measurement_type": "throughput",
  "frequency_mhz": 3700,
  "power_dbm": -10,
  "custom_key": "custom_value"
}
```

### 2B.4 Execution Config

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout_seconds` | number | 300 | 超时时间 (秒) |
| `retry_count` | number | 0 | 失败重试次数 |
| `continue_on_failure` | boolean | false | 失败后继续执行 |
| `expected_duration_minutes` | number | - | 预期时长 (分钟) |

### 2B.5 Validation (`validation_criteria`)

```json
{
  "min_value": 50,
  "max_value": 100,
  "unit": "Mbps",
  "pass_condition": ">=",
  "tolerance_percent": 5
}
```

### 2B.6 Status Values

| Status | Description |
|--------|-------------|
| `pending` | 待执行 |
| `running` | 执行中 |
| `completed` | 已完成 |
| `failed` | 失败 |
| `skipped` | 已跳过 |

---

## 3. Test Plan Parameters

### 3.1 Basic Info

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | 测试计划名称 |
| `description` | string | No | 描述 |
| `version` | string | No | 版本号 (default: "1.0") |
| `priority` | number | No | 优先级 1-10 (1=最高) |
| `created_by` | string | No | 创建者 |
| `tags` | string[] | No | 标签 |

### 3.2 DUT Info (`dut_info`)

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | 设备型号 |
| `manufacturer` | string | 制造商 |
| `firmware_version` | string | 固件版本 |
| `serial_number` | string | 序列号 |

### 3.3 Test Environment (`test_environment`)

| Parameter | Type | Description |
|-----------|------|-------------|
| `chamber_id` | string | 暗室ID |
| `temperature_c` | number | 温度 |
| `humidity_percent` | number | 湿度 |
| `step_configuration` | object | 步骤配置 (同上 Section 2) |

### 3.4 Associations

| Parameter | Type | Description |
|-----------|------|-------------|
| `scenario_id` | string | 关联的场景ID |
| `test_case_ids` | string[] | 测试用例ID列表 |

---

## 4. Priority Rules

When converting Scenario to TestPlan, parameters are resolved in this order:

```
┌─────────────────────────────────┐
│  1. step_configuration          │  ← Highest priority
│     (Scenario预设)              │
├─────────────────────────────────┤
│  2. test_environment            │
│     (TestPlan环境配置)          │
├─────────────────────────────────┤
│  3. Default Values              │  ← Lowest priority
│     (系统默认值)                │
└─────────────────────────────────┘
```

**Example:**
```
Scenario.step_configuration.chamber_init.chamber_id = "MPAC-2"
TestPlan.test_environment.chamber_id = "MPAC-1"
Default = "MPAC-1"

Result: "MPAC-2" (from step_configuration)
```

---

## Quick Copy Templates

### Minimal Step Configuration
```json
{
  "step_configuration": {
    "chamber_init": { "chamber_id": "MPAC-1" },
    "network_config": { "frequency_mhz": 3700, "bandwidth_mhz": 100 }
  }
}
```

### Strict KPI Configuration
```json
{
  "step_configuration": {
    "kpi_validation": {
      "kpi_thresholds": {
        "min_throughput_mbps": 100,
        "max_latency_ms": 20,
        "min_rsrp_dbm": -95,
        "max_packet_loss_percent": 1
      }
    }
  }
}
```

### High-Precision Logging
```json
{
  "step_configuration": {
    "route_execution": {
      "log_interval_s": 0.1,
      "auto_screenshot": true,
      "monitor_kpis": true
    }
  }
}
```
