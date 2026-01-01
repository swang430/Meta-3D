# 设计-实现差距报告

> 自动生成时间: 2026-01-01 14:21:35
>
> 此报告由 `scripts/check-design-implementation.py` 自动生成

---

## 摘要

| 指标 | 数量 | 百分比 |
|------|------|--------|
| 设计组件总数 | 65 | 100% |
| ✅ 已实现 | 27 | 41.5% |
| ⚠️ 部分实现 | 4 | 6.2% |
| ❌ 未实现 | 34 | 52.3% |

---

## 详细列表

### ❌ 未实现组件

| 名称 | 类型 | 设计文档位置 |
|------|------|-------------|
| `createTopology` | api_function | implementation.md:L1118 |
| `fetchExecutionMetrics` | api_function | implementation.md:L1161 |
| `fetchTopologies` | api_function | implementation.md:L1108 |
| `fetchTopologyDetail` | api_function | implementation.md:L1113 |
| `stopExecution` | api_function | implementation.md:L1166 |
| `validateTopology` | api_function | implementation.md:L1125 |
| `BSEditor` | component | architecture.md:L979 |
| `MapEditor` | component | implementation.md:L122 |
| `NetworkEditor` | component | implementation.md:L123 |
| `ObstEditor` | component | architecture.md:L987 |
| `ScenarioEditor` | component | implementation.md:L120 |
| `TopologyConfigurator` | component | implementation.md:L125 |
| `场景编辑器` | component | implementation.md:L120 |
| `已有` | component | implementation.md:L87 |
| `执行监控` | component | implementation.md:L130 |
| `拓扑配置器` | component | implementation.md:L125 |
| `🆕 新增` | component | implementation.md:L93 |
| `CableSpec` | interface | implementation.md:L437 |
| `ConductedConfig` | interface | implementation.md:L511 |
| `DUTConfig` | interface | implementation.md:L481 |
| `DUTInterface` | interface | implementation.md:L413 |
| `DigitalTwinConfig` | interface | implementation.md:L490 |
| `ITestExecutor` | interface | implementation.md:L674 |
| `LatencyMetrics` | interface | implementation.md:L595 |
| `LinkQualityMetrics` | interface | implementation.md:L608 |
| `OTAConfig` | interface | implementation.md:L530 |
| `Obstruction` | interface | implementation.md:L316 |
| `PortMapping` | interface | implementation.md:L402 |
| `SignalQualityMetrics` | interface | implementation.md:L602 |
| `TestEvent` | interface | implementation.md:L658 |
| `TestResult` | interface | implementation.md:L544 |
| `ThroughputMetrics` | interface | implementation.md:L590 |
| `EventCallback` | type | implementation.md:L656 |
| `SpeedProfile` | type | implementation.md:L301 |

### ⚠️ 部分实现组件

| 名称 | 类型 | 设计文档位置 | 备注 |
|------|------|-------------|------|
| `createScenario` | api_function | implementation.md:L1087 | gui/src/components (similar: CreateScenarioDialog) |
| `fetchExecutionStatus` | api_function | implementation.md:L1144 | gui/src/types (similar: ExecutionStatus) |
| `Subscription` | interface | implementation.md:L667 | api-service/app/schemas (similar: StreamSubscription) |
| `ValidationResult` | interface | implementation.md:L637 | api-service/app/schemas (similar: TopologyValidationResult) |

### ✅ 已实现组件

| 名称 | 类型 | 实现位置 |
|------|------|---------|
| `controlExecution` | api_function | gui/src/api |
| `createExecution` | api_function | gui/src/api |
| `deleteScenario` | api_function | gui/src/api |
| `fetchScenarioDetail` | api_function | gui/src/api |
| `fetchScenarios` | api_function | gui/src/api |
| `updateScenario` | api_function | gui/src/api |
| `ScenarioCategory` | enum | gui/src/types |
| `TestMode` | enum | gui/src/types |
| `TestStatus` | enum | gui/src/types |
| `BaseStationConfig` | interface | gui/src/types |
| `BaseStationDevice` | interface | api-service/app/schemas |
| `ChannelEmulatorDevice` | interface | api-service/app/schemas |
| `DUTDevice` | interface | api-service/app/schemas |
| `Environment` | interface | gui/src/types |
| `ExecutionHandle` | interface | gui/src/types |
| `KPIDefinition` | interface | gui/src/types |
| `NetworkConfig` | interface | gui/src/types |
| `NetworkTopology` | interface | gui/src/types |
| `RFConnection` | interface | api-service/app/schemas |
| `RoadTestScenario` | interface | gui/src/types |
| `Route` | interface | gui/src/types |
| `ScenarioEvent` | interface | api-service/app/schemas |
| `TestCapabilities` | interface | api-service/app/schemas |
| `TestConfig` | interface | gui/src/types |
| `TestMetrics` | interface | api-service/app/schemas |
| `TrafficConfig` | interface | api-service/app/schemas |
| `Waypoint` | interface | gui/src/types |

---

## 优先修复建议

基于组件类型的修复优先级:

1. **TypeScript 类型定义** (interface/type/enum) - 影响类型安全
2. **React 组件** - 影响用户界面功能
3. **API 函数** - 影响数据交互

---

## 如何使用此报告

1. 查看"未实现组件"列表
2. 在 `Master-Progress-Tracker.md` 中添加跟踪项
3. 按优先级实现缺失组件
4. 重新运行此脚本验证进度

```bash
# 运行检查脚本
python scripts/check-design-implementation.py
```
