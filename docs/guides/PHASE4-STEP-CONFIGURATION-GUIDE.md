# Virtual Road Test - Step Configuration Guide

**实现日期**: 2025-12-04
**功能**: Scenario步骤预配置
**目的**: 允许Scenario预先配置测试步骤参数，转换为TestPlan时自动继承这些配置

---

## ✅ 已完成功能

### 1. 类型定义更新

**文件**: [gui/src/types/roadTest.ts](gui/src/types/roadTest.ts)

新增`StepConfiguration`接口，包含7个步骤的配置：

```typescript
export interface StepConfiguration {
  chamber_init?: {
    chamber_id?: string
    timeout_seconds?: number
    verify_connections?: boolean
    calibrate_position_table?: boolean
  }
  network_config?: { ... }
  base_station_setup?: { ... }
  ota_mapper?: { ... }
  route_execution?: { ... }
  kpi_validation?: { ... }
  report_generation?: { ... }
}
```

`RoadTestScenario`和`ScenarioSummary`都新增了`step_configuration?`字段。

### 2. 前端转换逻辑

**文件**: [gui/src/utils/scenarioToTestPlan.ts:59](gui/src/utils/scenarioToTestPlan.ts#L59)

```typescript
test_environment: {
  // ... 其他配置
  step_configuration: scenario.step_configuration,  // 传递步骤配置
}
```

### 3. 后端自动生成逻辑

**文件**: [api-service/app/services/test_plan_service.py:58-186](api-service/app/services/test_plan_service.py#L58-L186)

优先级顺序：
```
scenario.step_configuration > test_environment > 默认值
```

每个步骤的参数都会：
1. 首先检查`step_configuration`
2. 如果没有，使用`test_environment`
3. 最后使用默认值

---

## 📖 使用方法

### 方法1：在Mock数据中添加配置（开发/测试）

编辑`gui/src/api/mockDatabase.ts`中的场景数据：

```typescript
const scenarios: ScenarioSummary[] = [
  {
    id: 'SCENARIO-URBAN-001',
    name: 'Urban Canyon Test',
    category: 'standard',
    source: 'standard',
    tags: ['urban', '5G'],
    duration_s: 1800,
    distance_m: 5000,

    // 新增：步骤配置
    step_configuration: {
      chamber_init: {
        chamber_id: 'MPAC-2',  // 自定义chamber
        timeout_seconds: 600,  // 延长超时到10分钟
        verify_connections: true,
        calibrate_position_table: false  // 跳过校准
      },
      network_config: {
        frequency_mhz: 2600,   // 使用n41频段
        bandwidth_mhz: 50,     // 50MHz带宽
        technology: '5G NR',
        timeout_seconds: 300
      },
      route_execution: {
        monitor_kpis: true,
        log_interval_s: 0.5,  // 更高频率日志记录
        auto_screenshot: true,
        timeout_seconds: 2400  // 40分钟超时
      },
      kpi_validation: {
        kpi_thresholds: {
          min_throughput_mbps: 100,  // 更严格的吞吐量要求
          max_latency_ms: 20,        // 更严格的延迟要求
          min_rsrp_dbm: -100,
          max_packet_loss_percent: 1
        }
      }
    }
  },
  // ... 其他场景
]
```

### 方法2：程序化创建（API）

当有Scenario创建/编辑API时，在payload中包含`step_configuration`：

```json
{
  "name": "Custom Urban Test",
  "category": "custom",
  "duration_s": 3600,
  "distance_m": 10000,
  "step_configuration": {
    "chamber_init": {
      "chamber_id": "MPAC-3",
      "timeout_seconds": 400
    },
    "network_config": {
      "frequency_mhz": 3700,
      "bandwidth_mhz": 100
    }
  }
}
```

---

## 🎯 转换流程

### 无步骤配置（默认行为）

```
Scenario (无step_configuration)
  ↓ 转换
Test Plan
  └─ Step 1: Initialize Chamber (MPAC-1, 300s timeout)  ← 默认值
  └─ Step 2: Configure Network (3500MHz, 100MHz)        ← test_environment
  └─ Step 3: ...
```

### 有步骤配置（新功能）

```
Scenario (有step_configuration)
  ├─ chamber_init: { chamber_id: "MPAC-2", timeout: 600s }
  └─ network_config: { frequency: 2600MHz }
    ↓ 转换
Test Plan
  └─ Step 1: Initialize Chamber (MPAC-2, 600s timeout)  ← 使用配置
  └─ Step 2: Configure Network (2600MHz, 100MHz)        ← 优先使用配置
  └─ Step 3: ...
```

---

## 🧪 测试示例

### 创建带自定义配置的测试计划

**测试文件位置**: `/tmp/test_step_configuration.json`

该测试展示了以下自定义配置：
- 使用 **MPAC-2** chamber（而非默认的 MPAC-1）
- 使用 **2600 MHz** 频率（n41频段，而非默认的 3500 MHz）
- **延长超时**: chamber初始化 600s，路径执行 70分钟
- **更严格的KPI阈值**: 150 Mbps吞吐量，15ms延迟，-95 dBm RSRP
- **高频日志记录**: 0.5秒间隔（而非默认的 1秒）

```bash
# 1. 查看测试payload（已创建）
cat /tmp/test_step_configuration.json

# 2. 创建测试计划
curl -X POST http://localhost:8000/api/v1/test-plans \
  -H "Content-Type: application/json" \
  -d @/tmp/test_step_configuration.json \
  | python3 -m json.tool

# 3. 验证步骤配置
# 获取刚创建的测试计划ID（从上一步返回）
TEST_PLAN_ID="<返回的plan_id>"

# 查看测试计划的步骤详情
curl -X GET "http://localhost:8000/api/v1/test-plans/${TEST_PLAN_ID}" \
  | python3 -m json.tool \
  | grep -A 20 "steps"

# 4. 验证关键配置是否生效
# 应该看到:
# - Step 1 (Initialize Chamber): chamber_id = "MPAC-2", timeout = 600
# - Step 2 (Configure Network): frequency_mhz = 2600, bandwidth_mhz = 50
# - Step 5 (Execute Route): log_interval_s = 0.5, timeout = 4200
# - Step 6 (KPI Validation): min_throughput_mbps = 150, max_latency_ms = 15
```

---

## 📊 配置优先级示例

### Chamber Init步骤

| 来源 | chamber_id | timeout_seconds | 最终结果 |
|------|-----------|----------------|---------|
| step_configuration | "MPAC-2" | 600 | ✅ 使用配置 |
| test_environment | "MPAC-1" | - | ❌ 被覆盖 |
| 默认值 | "MPAC-1" | 300 | ❌ 被覆盖 |

**结果**: `chamber_id = "MPAC-2"`, `timeout = 600s`

### Network Config步骤

| 来源 | frequency_mhz | technology | 最终结果 |
|------|--------------|-----------|---------|
| step_configuration | 2600 | null | ✅ 部分使用 |
| test_environment | 3500 | "5G NR" | ✅ 补充 |
| 默认值 | 3500 | "5G NR" | ❌ 不使用 |

**结果**: `frequency = 2600MHz` (配置), `technology = "5G NR"` (环境)

---

## 🎨 UI集成（TODO - Phase 4.3）

### 计划中的UI组件

1. **ScenarioEditor组件** (新建)
   - 展开式"Advanced: Test Steps Configuration"
   - 7个Tab对应7个步骤
   - 每个Tab显示该步骤的可配置参数

2. **ScenarioCard增强**
   - 显示"⚙️ Custom Steps" badge如果有配置
   - Tooltip显示已配置的步骤数量

3. **ScenarioDetailModal增强**
   - 新增"Test Steps"标签页
   - 只读模式显示预配置的步骤

---

## 🚀 下一步优化

### 短期（Phase 4.3）
- [ ] 创建StepConfigEditor组件
- [ ] 在ScenarioDetailModal中集成
- [ ] 添加配置预览功能

### 中期（Phase 5）
- [ ] 步骤配置模板库
- [ ] 从现有TestPlan导出配置到Scenario
- [ ] 配置验证和智能提示

### 长期
- [ ] AI辅助配置推荐
- [ ] 历史配置分析和优化建议
- [ ] 配置版本管理

---

## 💡 最佳实践

1. **保持简洁**：只配置需要改变的参数，其他使用默认值
2. **命名规范**：自定义配置的Scenario应在名称中标注
3. **文档化**：在`description`中说明为什么使用自定义配置
4. **测试验证**：创建TestPlan后检查步骤参数是否符合预期

---

## 📝 变更记录

- **2025-12-04**: 初始实现
  - 添加StepConfiguration类型定义
  - 前端传递step_configuration
  - 后端优先使用step_configuration
  - 文档编写

---

## 📋 快速参考

### Step Configuration完整结构

```typescript
step_configuration: {
  chamber_init?: {
    chamber_id?: string              // Chamber ID (e.g., "MPAC-2")
    timeout_seconds?: number         // 超时时间 (默认: 300s)
    verify_connections?: boolean     // 验证连接 (默认: true)
    calibrate_position_table?: boolean // 校准转台 (默认: true)
  }
  network_config?: {
    frequency_mhz?: number           // 频率 (默认: 3500 MHz)
    bandwidth_mhz?: number           // 带宽 (默认: 100 MHz)
    technology?: string              // 技术 (默认: "5G NR")
    timeout_seconds?: number         // 超时 (默认: 240s)
    verify_signal?: boolean          // 验证信号 (默认: true)
  }
  base_station_setup?: {
    channel_model?: string           // 信道模型 (默认: "UMa")
    num_base_stations?: number       // 基站数量 (默认: 1)
    timeout_seconds?: number         // 超时 (默认: 300s)
    verify_coverage?: boolean        // 验证覆盖 (默认: true)
  }
  ota_mapper?: {
    route_type?: string              // 路径类型 (默认: "urban")
    update_rate_hz?: number          // 更新频率 (默认: 10 Hz)
    enable_handover?: boolean        // 启用切换 (默认: true)
    timeout_seconds?: number         // 超时 (默认: 180s)
  }
  route_execution?: {
    route_duration_s?: number        // 路径时长 (从环境继承)
    total_distance_m?: number        // 总距离 (从环境继承)
    monitor_kpis?: boolean           // 监控KPI (默认: true)
    log_interval_s?: number          // 日志间隔 (默认: 1.0s)
    auto_screenshot?: boolean        // 自动截图 (默认: false)
    timeout_seconds?: number         // 超时 (默认: duration + 600s)
  }
  kpi_validation?: {
    kpi_thresholds?: {
      min_throughput_mbps?: number   // 最小吞吐量 (默认: 50)
      max_latency_ms?: number        // 最大延迟 (默认: 50)
      min_rsrp_dbm?: number          // 最小RSRP (默认: -110)
      max_packet_loss_percent?: number // 最大丢包率 (默认: 5)
    }
    generate_plots?: boolean         // 生成图表 (默认: true)
    timeout_seconds?: number         // 超时 (默认: 300s)
  }
  report_generation?: {
    report_format?: string           // 格式 (默认: "PDF")
    include_raw_data?: boolean       // 包含原始数据 (默认: false)
    include_screenshots?: boolean    // 包含截图 (默认: false)
    include_recommendations?: boolean // 包含建议 (默认: true)
    timeout_seconds?: number         // 超时 (默认: 60s)
  }
}
```

### 常用配置场景

| 场景 | 推荐配置 |
|------|---------|
| **快速验证测试** | `chamber_init.timeout: 180`, `route_execution.log_interval_s: 2.0` |
| **长时间稳定性测试** | `route_execution.timeout: 7200`, `network_config.timeout: 360` |
| **高精度性能测试** | `route_execution.log_interval_s: 0.1`, `kpi_validation.generate_plots: true` |
| **严格KPI测试** | 自定义`kpi_thresholds`，降低阈值 |
| **多chamber测试** | `chamber_init.chamber_id: "MPAC-X"` |

---

**状态**: ✅ 核心功能完成，UI待实现
**测试**: ✅ 后端逻辑已验证，测试文件已提供
**文档**: ✅ 使用指南完成
