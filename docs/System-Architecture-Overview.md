# Meta-3D MIMO OTA 测试系统 - 整体架构设计

**文档版本**: v2.0
**创建日期**: 2025-11-16
**状态**: 架构设计阶段

---

## 🎯 系统愿景

构建一个**完整的、生产级别的**汽车无线通信MIMO OTA测试平台，支持：
- ✅ 虚拟测试（数字孪生 + ChannelEngine）
- ✅ 传导测试（仪表-DUT直连）
- ✅ OTA辐射测试（MPAC暗室）
- ✅ 混合测试（虚拟+实测结合）
- ✅ 日常生产测试工作流

---

## 📐 系统分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      用户界面层 (UI Layer)                        │
│  - 测试计划管理  - 实时监控  - 数据可视化  - 报告生成              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    业务逻辑层 (Business Logic)                    │
│  - 测试编排  - 工作流引擎  - 场景管理  - 数据分析                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  抽象服务层 (Service Abstraction)                 │
│  - 虚拟测试服务  - 校准服务  - 数据服务  - 配置服务                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  硬件抽象层 (Hardware Abstraction)                │
│  - 信道仿真器HAL  - 基站HAL  - 分析仪HAL  - 探头HAL  - 转台HAL     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      硬件层 (Hardware)                            │
│  信道仿真器 | 基站仿真器 | 信号分析仪 | 探头阵列 | 转台 | DUT       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ 核心子系统详解

### 1. 虚拟测试子系统 (Virtual Test Subsystem)

**目标**: 提供基于信道模型的虚拟OTA测试能力

#### 1.1 ChannelEngine集成模块 ✅ **30%完成**
- [x] **Phase 1**: Python微服务 + TypeScript客户端（已完成）
- [ ] **Phase 2**: 权重可视化增强
- [ ] **Phase 3**: Docker部署

#### 1.2 虚拟场景库 (Virtual Scenario Library) ⏸️ **0%完成**
- [ ] **设计文档**: `Virtual-Scenario-Library-Design.md`
- [ ] 3GPP标准场景库（UMa/UMi/RMa/InH + CDL/TDL）
- [ ] 自定义场景创建和编辑
- [ ] 场景参数化（频率、速度、路径损耗等）
- [ ] 场景验证和仿真
- [ ] 场景版本管理和导入/导出

**关键API**:
```typescript
interface VirtualScenario {
  id: string
  name: string
  type: 'standard' | 'custom'
  channelModel: ChannelModelConfig
  environmentParams: EnvironmentParams
  motionProfile?: MotionProfile
  validation: ValidationResult
}
```

#### 1.3 虚拟-实测混合测试 ⏸️ **0%完成**
- [ ] **设计文档**: `Hybrid-Test-Framework-Design.md`
- [ ] 虚拟信道注入到实际仪表
- [ ] 实测数据反馈到虚拟模型
- [ ] 混合测试结果对比分析
- [ ] 误差校正和模型优化

---

### 2. 校准子系统 (Calibration Subsystem) ⏸️ **0%完成**

**目标**: 保证测试系统的准确性和可重复性

#### 2.1 探头校准 (Probe Calibration)
- [ ] **设计文档**: `Probe-Calibration-Design.md`
- [ ] 探头幅度校准（增益、功率）
- [ ] 探头相位校准（相位中心、相位偏移）
- [ ] 探头极化校准（极化纯度、交叉极化）
- [ ] 探头方向图测量和校准
- [ ] 校准数据存储和管理

**校准工作流**:
```
1. 选择校准类型（幅度/相位/极化/方向图）
2. 配置校准参数（频率点、功率等级等）
3. 执行自动化校准流程
4. 采集校准数据
5. 数据分析和校准系数计算
6. 应用校准系数到测试系统
7. 校准验证和报告生成
```

#### 2.2 信道校准 (Channel Calibration)
- [ ] **设计文档**: `Channel-Calibration-Design.md`
- [ ] 信道仿真器校准（幅度、相位、时延）
- [ ] 多径信道校准
- [ ] 信道相关性校准
- [ ] 信道统计特性验证

#### 2.3 系统级校准 (System-Level Calibration)
- [ ] **设计文档**: `System-Calibration-Design.md`
- [ ] 端到端系统校准（基站→探头→DUT）
- [ ] 静区均匀性校准
- [ ] EIS (Effective Isotropic Sensitivity) 校准
- [ ] TRP (Total Radiated Power) 校准

#### 2.4 校准数据管理
- [ ] 校准数据库设计
- [ ] 校准历史记录
- [ ] 校准有效期管理
- [ ] 校准证书生成

**数据模型**:
```typescript
interface CalibrationRecord {
  id: string
  type: 'probe' | 'channel' | 'system'
  timestamp: Date
  operator: string
  equipment: EquipmentInfo[]
  calibrationData: CalibrationCoefficients
  validityPeriod: { start: Date; end: Date }
  verificationResult: VerificationResult
  certificate: CertificateInfo
}
```

---

### 3. 硬件抽象层 (HAL) ⏸️ **0%完成**

**目标**: 统一硬件接口，支持多厂商设备

#### 3.1 信道仿真器HAL
- [ ] **设计文档**: `Channel-Emulator-HAL-Design.md`
- [ ] Keysight PROPSIM
- [ ] Spirent VR5
- [ ] R&S SMW200A
- [ ] Anritsu Fading Simulator

**统一接口**:
```typescript
interface IChannelEmulator {
  // 连接管理
  connect(config: ConnectionConfig): Promise<void>
  disconnect(): Promise<void>

  // 配置管理
  setChannelModel(model: ChannelModelConfig): Promise<void>
  setFrequency(freqHz: number): Promise<void>
  setPower(powerDbm: number): Promise<void>

  // 探头权重配置
  setProbeWeights(weights: ProbeWeight[]): Promise<void>

  // 控制
  start(): Promise<void>
  stop(): Promise<void>

  // 状态监控
  getStatus(): Promise<EmulatorStatus>
  getMetrics(): Promise<EmulatorMetrics>
}
```

#### 3.2 基站仿真器HAL
- [ ] **设计文档**: `Base-Station-HAL-Design.md`
- [ ] Keysight UXM
- [ ] R&S CMW500
- [ ] Anritsu MT8000A

#### 3.3 信号分析仪HAL
- [ ] **设计文档**: `Signal-Analyzer-HAL-Design.md`
- [ ] Keysight N9040B
- [ ] R&S FSW

#### 3.4 探头控制HAL
- [ ] **设计文档**: `Probe-Control-HAL-Design.md`
- [ ] RF开关矩阵控制
- [ ] 探头选择和切换
- [ ] 探头功率控制

#### 3.5 转台控制HAL
- [ ] **设计文档**: `Positioner-HAL-Design.md`
- [ ] 方位角/俯仰角控制
- [ ] 位置预设和记忆
- [ ] 运动轨迹规划

---

### 4. 测试编排和工作流 ⏸️ **0%完成**

**目标**: 支持复杂测试流程的自动化执行

#### 4.1 测试计划管理
- [ ] **设计文档**: `Test-Plan-Management-Design.md`
- [ ] 测试计划创建和编辑
- [ ] 测试例（Test Case）库
- [ ] 测试序列（Test Sequence）设计
- [ ] 测试参数化和变量管理

**测试计划结构**:
```typescript
interface TestPlan {
  id: string
  name: string
  description: string
  testMode: 'digital_twin' | 'conducted' | 'ota' | 'hybrid'
  testCases: TestCase[]
  executionOrder: 'sequential' | 'parallel' | 'conditional'
  variables: TestVariable[]
  resources: ResourceRequirement[]
  schedule: ScheduleConfig
}

interface TestCase {
  id: string
  name: string
  category: string
  setup: SetupConfig          // 测试前配置
  execution: ExecutionSteps[] // 执行步骤
  validation: ValidationRules // 验证规则
  teardown: TeardownConfig    // 测试后清理
  expectedDuration: number
}
```

#### 4.2 测试执行引擎
- [ ] **设计文档**: `Test-Execution-Engine-Design.md`
- [ ] 测试队列管理
- [ ] 测试调度和优先级
- [ ] 并行测试支持
- [ ] 测试中断和恢复
- [ ] 错误处理和重试机制

#### 4.3 测试工作流模板
- [ ] **设计文档**: `Test-Workflow-Templates-Design.md`
- [ ] 日常验证测试（Daily Verification）
- [ ] 型式认证测试（Type Approval）
- [ ] 生产线测试（Production Line）
- [ ] 研发调试测试（R&D Debug）

**典型工作流示例**:
```yaml
# 日常OTA验证测试工作流
workflow:
  name: "Daily OTA Verification"
  trigger: "schedule:daily:09:00"

  steps:
    - name: "系统健康检查"
      action: health_check
      targets: [channel_emulator, base_station, probes]

    - name: "校准验证"
      action: verify_calibration
      max_age: 30days
      auto_recalibrate: true

    - name: "执行标准测试集"
      action: run_test_plan
      plan: "standard_ota_suite"
      scenarios: [UMa_CDL-C, UMi_CDL-A, InH_TDL-A]

    - name: "结果分析"
      action: analyze_results
      compare_baseline: true
      threshold: "±1dB"

    - name: "生成报告"
      action: generate_report
      format: [pdf, html]
      recipients: [test_team, management]
```

#### 4.4 测试状态和进度监控
- [ ] **设计文档**: `Test-Monitoring-Design.md`
- [ ] 实时测试状态展示
- [ ] 测试进度追踪
- [ ] 资源使用监控
- [ ] 异常告警和通知

---

### 5. 数据管理子系统 ⏸️ **0%完成**

**目标**: 完整的测试数据生命周期管理

#### 5.1 数据采集
- [ ] **设计文档**: `Data-Acquisition-Design.md`
- [ ] 实时数据流采集
- [ ] 高速数据采样
- [ ] 多源数据同步
- [ ] 数据预处理和过滤

#### 5.2 数据存储
- [ ] **设计文档**: `Data-Storage-Design.md`
- [ ] 时序数据库（InfluxDB/TimescaleDB）
- [ ] 对象存储（测试配置、原始数据）
- [ ] 关系数据库（元数据、测试结果）
- [ ] 数据压缩和归档

**数据模型**:
```typescript
interface TestDataRecord {
  // 元数据
  testId: string
  testPlanId: string
  testCaseId: string
  timestamp: Date
  operator: string
  dut: DUTInfo

  // 配置数据
  testConfig: TestConfiguration
  calibrationData: CalibrationReference

  // 测试数据
  measurements: {
    frequency: number[]
    power: number[]
    phase: number[]
    evm: number[]
    // ... 更多测量指标
  }

  // 结果数据
  results: {
    pass: boolean
    metrics: PerformanceMetrics
    deviations: Deviation[]
  }
}
```

#### 5.3 数据分析
- [ ] **设计文档**: `Data-Analysis-Design.md`
- [ ] 统计分析（均值、方差、分布）
- [ ] 趋势分析（性能随时间变化）
- [ ] 对比分析（虚拟vs实测、不同DUT）
- [ ] 异常检测（基于ML的异常识别）

#### 5.4 报告生成
- [ ] **设计文档**: `Report-Generation-Design.md`
- [ ] 测试报告模板管理
- [ ] 自动化报告生成
- [ ] 多格式导出（PDF、HTML、Excel）
- [ ] 报告定制和品牌化

---

### 6. 场景库和复用 ⏸️ **10%完成**

**目标**: 建立标准化、可复用的测试场景库

#### 6.1 标准场景库（已部分完成）
- [x] **Phase 2实现**: 基础场景库框架
- [ ] 完整的3GPP标准场景
- [ ] 行业标准场景（CTIA、GCF等）
- [ ] 场景参数范围定义

#### 6.2 自定义场景
- [ ] **设计文档**: `Custom-Scenario-Design.md`
- [ ] 场景编辑器（图形化配置）
- [ ] 场景参数化和模板化
- [ ] 场景验证和仿真预览
- [ ] 场景分享和社区库

#### 6.3 场景复用机制
- [ ] **设计文档**: `Scenario-Reuse-Design.md`
- [ ] 场景继承和组合
- [ ] 场景变体管理
- [ ] 场景标签和分类
- [ ] 场景搜索和推荐

---

### 7. 系统集成和部署 ⏸️ **0%完成**

#### 7.1 系统配置管理
- [ ] **设计文档**: `System-Configuration-Design.md`
- [ ] 环境配置（dev/staging/prod）
- [ ] 设备配置和发现
- [ ] 用户权限和角色管理
- [ ] 系统备份和恢复

#### 7.2 CI/CD和自动化测试
- [ ] **设计文档**: `CI-CD-Pipeline-Design.md`
- [ ] 代码自动化测试
- [ ] 集成测试
- [ ] 性能测试
- [ ] 自动化部署

#### 7.3 监控和运维
- [ ] **设计文档**: `System-Monitoring-Design.md`
- [ ] 系统健康监控
- [ ] 性能指标收集
- [ ] 日志聚合和分析
- [ ] 告警和故障诊断

---

## 📊 整体进度矩阵

### 子系统完成度汇总

| 子系统 | 设计完成度 | 实现完成度 | 优先级 | 预计工期 |
|--------|-----------|-----------|--------|---------|
| **1. 虚拟测试** | 40% | 30% | P0 | 4-6周 |
| └─ 1.1 ChannelEngine集成 | 100% | 30% | P0 | 2周 |
| └─ 1.2 虚拟场景库 | 0% | 0% | P1 | 1-2周 |
| └─ 1.3 混合测试 | 0% | 0% | P2 | 2周 |
| **2. 校准子系统** | 0% | 0% | P0 | 6-8周 |
| └─ 2.1 探头校准 | 0% | 0% | P0 | 2周 |
| └─ 2.2 信道校准 | 0% | 0% | P0 | 2周 |
| └─ 2.3 系统级校准 | 0% | 0% | P1 | 2周 |
| └─ 2.4 校准数据管理 | 0% | 0% | P1 | 2周 |
| **3. 硬件抽象层** | 0% | 0% | P0 | 8-10周 |
| └─ 3.1 信道仿真器HAL | 0% | 0% | P0 | 3周 |
| └─ 3.2 基站仿真器HAL | 0% | 0% | P0 | 2周 |
| └─ 3.3 信号分析仪HAL | 0% | 0% | P1 | 1周 |
| └─ 3.4 探头控制HAL | 0% | 0% | P0 | 1周 |
| └─ 3.5 转台控制HAL | 0% | 0% | P1 | 1周 |
| **4. 测试编排** | 0% | 0% | P0 | 4-6周 |
| └─ 4.1 测试计划管理 | 0% | 0% | P0 | 2周 |
| └─ 4.2 测试执行引擎 | 0% | 0% | P0 | 2周 |
| └─ 4.3 工作流模板 | 0% | 0% | P1 | 1周 |
| └─ 4.4 监控 | 0% | 0% | P1 | 1周 |
| **5. 数据管理** | 0% | 0% | P1 | 4-6周 |
| └─ 5.1 数据采集 | 0% | 0% | P0 | 2周 |
| └─ 5.2 数据存储 | 0% | 0% | P0 | 1周 |
| └─ 5.3 数据分析 | 0% | 0% | P1 | 2周 |
| └─ 5.4 报告生成 | 0% | 0% | P1 | 1周 |
| **6. 场景库** | 10% | 10% | P1 | 2-3周 |
| └─ 6.1 标准场景库 | 20% | 10% | P1 | 1周 |
| └─ 6.2 自定义场景 | 0% | 0% | P2 | 1周 |
| └─ 6.3 场景复用 | 0% | 0% | P2 | 1周 |
| **7. 系统集成** | 0% | 0% | P2 | 2-4周 |
| └─ 7.1 配置管理 | 0% | 0% | P1 | 1周 |
| └─ 7.2 CI/CD | 0% | 0% | P2 | 1周 |
| └─ 7.3 监控运维 | 0% | 0% | P1 | 2周 |
| **总计** | **7%** | **6%** | - | **30-45周** |

---

## 🗺️ 开发路线图（修订版）

### Stage 0: 架构设计阶段 ⏸️ **进行中**

**目标**: 完成整体架构设计和子模块规划

- [x] 整体架构设计（本文档）
- [ ] 各子系统详细设计文档（13份待创建）
- [ ] API接口规范定义
- [ ] 数据模型设计
- [ ] 技术选型和评估

**预计时间**: 2-3周

---

### Stage 1: 核心基础设施 🎯 **下一步**

**目标**: 建立可工作的基础系统

#### Sprint 1-2: 虚拟测试基础（4周）
- [ ] 完成ChannelEngine集成（Phase 1-3）
- [ ] 虚拟场景库基础框架
- [ ] 基础数据存储和查询

#### Sprint 3-4: 硬件抽象层框架（4周）
- [ ] 定义统一HAL接口
- [ ] 实现信道仿真器HAL（至少1个厂商）
- [ ] 实现基站仿真器HAL（至少1个厂商）
- [ ] HAL集成测试

#### Sprint 5-6: 基础测试编排（4周）
- [ ] 测试计划管理UI
- [ ] 简单测试执行引擎
- [ ] 测试状态监控

**里程碑**: 可以创建、执行简单的OTA测试计划

---

### Stage 2: 校准和精度保证 📐

**目标**: 实现完整的校准能力

#### Sprint 7-8: 探头校准（4周）
- [ ] 探头幅度校准流程
- [ ] 探头相位校准流程
- [ ] 校准数据管理

#### Sprint 9-10: 系统校准（4周）
- [ ] 信道校准
- [ ] 端到端系统校准
- [ ] 校准验证和报告

**里程碑**: 系统具备完整校准能力，测试结果可溯源

---

### Stage 3: 生产化和自动化 🏭

**目标**: 支持日常生产测试

#### Sprint 11-12: 工作流和自动化（4周）
- [ ] 测试工作流模板
- [ ] 自动化测试调度
- [ ] 批量测试支持

#### Sprint 13-14: 数据分析和报告（4周）
- [ ] 高级数据分析
- [ ] 自动化报告生成
- [ ] 测试结果对比

**里程碑**: 支持无人值守的日常测试

---

### Stage 4: 高级特性 🚀

**目标**: 提供差异化能力

#### Sprint 15-16: 混合测试（4周）
- [ ] 虚拟-实测混合框架
- [ ] 模型优化和校正

#### Sprint 17-18: 场景复用和社区（4周）
- [ ] 场景编辑器
- [ ] 场景分享和导入

**里程碑**: 完整功能的生产级系统

---

## 📋 设计文档清单（待创建）

### 必需文档（P0）- 13份

| # | 文档名称 | 所属子系统 | 预计页数 | 状态 |
|---|---------|-----------|---------|------|
| 1 | Virtual-Scenario-Library-Design.md | 虚拟测试 | 15-20 | ⏸️ 待创建 |
| 2 | Hybrid-Test-Framework-Design.md | 虚拟测试 | 20-25 | ⏸️ 待创建 |
| 3 | Probe-Calibration-Design.md | 校准 | 25-30 | ⏸️ 待创建 |
| 4 | Channel-Calibration-Design.md | 校准 | 20-25 | ⏸️ 待创建 |
| 5 | System-Calibration-Design.md | 校准 | 25-30 | ⏸️ 待创建 |
| 6 | Channel-Emulator-HAL-Design.md | 硬件抽象层 | 30-35 | ⏸️ 待创建 |
| 7 | Base-Station-HAL-Design.md | 硬件抽象层 | 25-30 | ⏸️ 待创建 |
| 8 | Probe-Control-HAL-Design.md | 硬件抽象层 | 15-20 | ⏸️ 待创建 |
| 9 | Test-Plan-Management-Design.md | 测试编排 | 20-25 | ⏸️ 待创建 |
| 10 | Test-Execution-Engine-Design.md | 测试编排 | 30-35 | ⏸️ 待创建 |
| 11 | Data-Acquisition-Design.md | 数据管理 | 20-25 | ⏸️ 待创建 |
| 12 | Data-Storage-Design.md | 数据管理 | 15-20 | ⏸️ 待创建 |
| 13 | System-Configuration-Design.md | 系统集成 | 15-20 | ⏸️ 待创建 |

### 可选文档（P1-P2）- 8份

| # | 文档名称 | 所属子系统 | 预计页数 | 状态 |
|---|---------|-----------|---------|------|
| 14 | Signal-Analyzer-HAL-Design.md | 硬件抽象层 | 15-20 | ⏸️ 待创建 |
| 15 | Positioner-HAL-Design.md | 硬件抽象层 | 15-20 | ⏸️ 待创建 |
| 16 | Test-Workflow-Templates-Design.md | 测试编排 | 20-25 | ⏸️ 待创建 |
| 17 | Test-Monitoring-Design.md | 测试编排 | 15-20 | ⏸️ 待创建 |
| 18 | Data-Analysis-Design.md | 数据管理 | 25-30 | ⏸️ 待创建 |
| 19 | Report-Generation-Design.md | 数据管理 | 20-25 | ⏸️ 待创建 |
| 20 | Custom-Scenario-Design.md | 场景库 | 15-20 | ⏸️ 待创建 |
| 21 | CI-CD-Pipeline-Design.md | 系统集成 | 15-20 | ⏸️ 待创建 |

**总计**: 21份设计文档，预计450-550页

---

## 🎯 关键决策点

### 决策1: 开发顺序

**选项A**: 深度优先（完成一个子系统再做下一个）
- 优点: 每个子系统完整，容易验证
- 缺点: 整体集成晚，风险后置

**选项B**: 广度优先（所有子系统并行基础功能）✅ **推荐**
- 优点: 早期集成，持续验证
- 缺点: 每个子系统初期不完整

**建议**: 采用**广度优先 + 迭代增量**方式

---

### 决策2: 硬件抽象策略

**选项A**: 完全抽象（支持所有厂商）
- 优点: 最大灵活性
- 缺点: 复杂度高，开发周期长

**选项B**: 单一厂商 + 抽象层预留 ✅ **推荐**
- 优点: 快速上线，后续扩展
- 缺点: 初期vendor lock-in

**建议**: 先支持1-2个主要厂商，接口设计保持通用性

---

### 决策3: 虚拟vs实测优先级

**选项A**: 虚拟测试优先
- 适合: 研发阶段，快速迭代

**选项B**: 实测优先 ✅ **推荐**
- 适合: 生产环境，结果可信

**建议**: **虚拟测试作为实测的补充**，而非替代

---

## 📈 成功指标

### 技术指标
- [ ] 测试准确度: ±0.5dB (vs 手动测试)
- [ ] 测试可重复性: σ < 0.2dB
- [ ] 校准有效期: > 30天
- [ ] 系统可用性: > 99%
- [ ] 测试吞吐量: > 10 tests/hour

### 业务指标
- [ ] 测试效率提升: > 80% (vs 手动)
- [ ] 人力成本降低: > 60%
- [ ] 测试周期缩短: > 70%
- [ ] 错误率降低: > 90%

---

## 📝 下一步行动

### 立即行动（本周）
1. **评审本架构文档**
2. **确定Stage 1优先级**
3. **启动P0设计文档编写**（13份）
4. **组建技术团队**
5. **准备硬件设备清单**

### 短期行动（1-2周）
1. 完成核心设计文档
2. 技术选型和PoC验证
3. 搭建开发环境
4. 启动Stage 1 Sprint 1

---

**最后更新**: 2025-11-16
**下次评审**: 待定
**文档所有者**: 架构团队
