# 虚拟路测场景设计文档

## 文档信息
- **版本**: 2.0
- **日期**: 2025-11-15
- **状态**: 设计确认

## 1. 场景的本质定义

### 1.1 虚拟路测场景 vs 标准测试

```
┌─────────────────────────────────────────────────────────┐
│  测试例库 (Test Case Library)                            │
│  = 标准测试例                                            │
│  - 3GPP TS 38.101 符合性测试                             │
│  - CTIA OTA认证测试                                      │
│  - 5GAA V2X协议测试                                      │
│  特点：步骤明确、参数标准化、用于认证                      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  虚拟路测场景库 (Virtual Road Test Scenario Library)     │
│  = 真实道路场景的数字孪生                                 │
│  - 北京CBD早高峰通勤路线                                  │
│  - 京沪高速G2公路段                                       │
│  - 上海南京路隧道穿越                                     │
│  特点：业务导向、真实场景、用于研发验证                    │
└─────────────────────────────────────────────────────────┘

关键区别：
  标准测试 → "验证是否符合标准"
  虚拟路测 → "验证在真实场景下的性能"
```

### 1.2 射线跟踪工具的核心作用

```
真实环境数据采集
  ├─ 地理信息 (GIS)
  ├─ 建筑模型 (3D)
  ├─ 基站位置
  └─ 道路网络
        ↓
射线跟踪仿真工具
  ├─ Remcom Wireless InSite
  ├─ Altair WinProp
  ├─ CloudRT
  └─ 其他商业/开源工具
        ↓ 输出
传播特性数据
  ├─ 路径损耗矩阵
  ├─ 多径分量 (时延/幅度/角度)
  ├─ 阴影衰落统计
  └─ 信道冲激响应
        ↓ 导入
虚拟路测场景
  ├─ 完整的环境定义
  ├─ 真实的传播特性
  └─ 可直接用于测试
```

## 2. 场景分类体系（多维度标签）

### 2.1 分类维度

```typescript
interface ScenarioTaxonomy {
  // 维度1: 来源类型
  source: 'real-world' | 'synthetic' | 'standard-derived'

  // 维度2: 地理特征
  geography: {
    region: string        // "北京CBD", "京沪高速G2"
    type: 'urban' | 'suburban' | 'highway' | 'tunnel' | 'indoor' | 'rural'
  }

  // 维度3: 测试目的
  purpose: 'coverage' | 'handover' | 'throughput' | 'latency' | 'mobility' | 'reliability'

  // 维度4: 网络类型
  network: 'LTE' | '5G NR FR1' | '5G NR FR2' | 'C-V2X' | 'Hybrid'

  // 维度5: 复杂度
  complexity: 'basic' | 'intermediate' | 'advanced' | 'extreme'

  // 自由标签
  tags: string[]
}
```

### 2.2 分类示例

| 场景名称 | source | geography | purpose | network | complexity | tags |
|---------|--------|-----------|---------|---------|------------|------|
| 北京CBD早高峰 | real-world | {北京CBD, urban} | throughput | 5G NR FR1 | advanced | ["早高峰","密集建筑","低速"] |
| 京沪高速巡航 | real-world | {G2苏州段, highway} | handover | 5G NR FR1 | intermediate | ["高速","多普勒"] |
| 隧道穿越 | real-world | {南京路隧道, tunnel} | reliability | LTE | advanced | ["遮挡","弱覆盖"] |
| 郊区覆盖验证 | synthetic | {通用郊区, suburban} | coverage | 5G NR FR1 | basic | ["大范围","稀疏基站"] |

## 3. 场景抽象层次

### 3.1 三层架构

```
┌─────────────────────────────────────────────┐
│  场景类别 (Scenario Category)                │
│  例如："城市密集区通勤场景"                   │
│  - 业务描述                                  │
│  - 适用范围                                  │
└─────────────────┬───────────────────────────┘
                  ↓ 实例化
┌─────────────────────────────────────────────┐
│  场景模板 (Scenario Template)                │
│  例如："城市密集区-参数化模板"                │
│  - 可配置参数（速度、频段等）                 │
│  - 固定参数（环境模型）                      │
│  - 射线跟踪配置                              │
└─────────────────┬───────────────────────────┘
                  ↓ 参数赋值
┌─────────────────────────────────────────────┐
│  场景实例 (Scenario Instance)                │
│  例如："北京CBD早高峰-3.5GHz-60km/h"         │
│  - 所有参数已固定                            │
│  - 射线跟踪结果文件                          │
│  - 可直接生成测试例                          │
└─────────────────────────────────────────────┘
```

### 3.2 Phase 2实现策略

- **Phase 2**: 只实现**场景实例**（10个固定场景）
  - 所有参数预定义
  - 开箱即用
  - 简化用户流程

- **Phase 3+**: 引入**场景模板**
  - 用户可基于模板创建新实例
  - 参数化配置
  - 支持射线跟踪工具集成

## 4. 场景来源与射线跟踪

### 4.1 场景来源定义

```typescript
interface ScenarioOrigin {
  type: 'real-world' | 'synthetic' | 'customer-requested'

  // 真实场景
  realWorld?: {
    location: string              // "北京市朝阳区CBD"
    coordinates?: {
      latitude: number
      longitude: number
    }
    captureDate?: string          // 场景采集日期
    dataSources: string[]         // ["GIS", "Street View", "LiDAR"]
  }

  // 射线跟踪信息
  rayTracing?: {
    tool: 'WirelessInSite' | 'WinProp' | 'CloudRT' | 'Custom'
    version: string
    environmentModel: string      // 环境文件引用
    configFile?: string           // 射线跟踪配置文件
    generatedBy?: string          // 创建人员
    generatedAt: string
  }

  // 客户定制
  customerRequest?: {
    customer: string
    project: string
    requirements: string
    deliveryDate?: string
  }
}
```

### 4.2 射线跟踪输出集成

```typescript
interface RayTracingOutput {
  tool: 'WirelessInSite' | 'WinProp' | 'CloudRT' | 'Custom'
  version: string

  // 结果文件
  resultFiles: {
    pathLossMatrix?: string       // 路径损耗矩阵
    channelCoefficients?: string  // 信道系数
    dopplerProfile?: string       // 多普勒谱
    powerDelayProfile?: string    // 功率时延谱
    angleOfArrival?: string       // 到达角
    angleOfDeparture?: string     // 离开角
  }

  // 统计信息
  statistics?: {
    averagePathLoss: number       // dB
    shadowingStdDev: number       // dB
    rmsDelaySpread: number        // ns
    dominantPathDelay: number     // ns
  }

  // 执行信息
  execution: {
    computeTime: number           // 秒
    rayCount: number              // 跟踪的射线数量
    reflectionOrder: number       // 反射阶数
    diffractionOrder: number      // 绕射阶数
  }
}
```

## 5. 场景完整性与验证

### 5.1 完整性定义

```typescript
interface ScenarioIntegrity {
  // 数据完整性
  dataCompleteness: {
    hasNetwork: boolean           // 网络配置完整
    hasTrajectory: boolean        // 轨迹定义完整
    hasEnvironment: boolean       // 环境条件完整
    hasTraffic: boolean          // 流量模型完整
    hasKPI: boolean              // KPI定义完整
  }

  // 验证状态
  validation: {
    isValidated: boolean          // 已通过验证
    validatedBy?: string          // 验证人员
    validatedAt?: string          // 验证时间
    validationNotes?: string      // 验证备注
  }

  // 可执行性
  executability: {
    canExecuteOTA: boolean        // 可在OTA模式执行
    canExecuteConducted: boolean  // 可在传导模式执行
    canExecuteDigitalTwin: boolean // 可在数字孪生执行

    blockers?: string[]           // 阻塞问题列表
  }
}
```

### 5.2 场景验证流程

```
1. 数据完整性检查
   └─ 所有必需字段已填写

2. 参数一致性检查
   └─ 网络配置、环境、轨迹参数相互匹配

3. 物理合理性检查
   └─ 速度、加速度、功率等参数在合理范围

4. 射线跟踪结果验证（如适用）
   └─ 输出文件存在且格式正确

5. 可执行性验证
   └─ 至少一种测试模式可执行
```

## 6. Phase 2场景库规划

### 6.1 10个场景实例分类

| 编号 | 场景名称 | 来源 | 地理类型 | 测试目的 | 复杂度 |
|------|---------|------|---------|---------|--------|
| 1 | 北京CBD早高峰通勤 | real-world | urban | throughput | advanced |
| 2 | 京沪高速G2巡航 | real-world | highway | handover | intermediate |
| 3 | 上海南京路隧道 | real-world | tunnel | reliability | advanced |
| 4 | 深圳科技园区覆盖 | real-world | urban | coverage | intermediate |
| 5 | 郊区低速移动 | synthetic | suburban | coverage | basic |
| 6 | 室内停车场 | synthetic | indoor | penetration | intermediate |
| 7 | 高速极限测试 | synthetic | highway | mobility | extreme |
| 8 | 密集干扰场景 | synthetic | urban | interference | advanced |
| 9 | V2X十字路口 | real-world | urban | latency | intermediate |
| 10 | 连续切换压力测试 | synthetic | highway | handover | advanced |

### 6.2 场景数据来源

- **真实场景** (4个): 基于实际城市/道路数据，使用射线跟踪工具生成
- **合成场景** (6个): 基于典型环境参数，使用标准信道模型

## 7. 未来扩展路径

### 7.1 Phase 3: 场景模板与参数化

- 引入场景模板机制
- 用户可基于模板创建新场景
- 参数验证和约束

### 7.2 Phase 4: 射线跟踪工具集成

- 集成射线跟踪工具API
- 支持在线生成场景
- 自动导入传播特性数据

### 7.3 Phase 5: 场景组合与模块化

- 积累足够场景后
- 归纳总结可复用模块
- 支持场景模块化组合

---

**本设计文档确认了虚拟路测场景的核心定位、分类体系、数据模型和实施策略。**
