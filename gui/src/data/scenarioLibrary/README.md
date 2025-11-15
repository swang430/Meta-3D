# 虚拟路测场景库

## 文件结构

```
scenarioLibrary/
├── index.ts                # 统一导出，包含场景列表和辅助函数
├── scenarios_2to5.ts       # 场景2-5的完整定义
├── scenarios_6to10.ts      # 场景6-10的完整定义
└── README.md              # 本文件
```

另外：
- `../scenarioLibrary.ts` - 场景1的完整定义（向后兼容）

## 10个场景概览

| ID | 名称 | 来源 | 地理类型 | 测试目的 | 复杂度 | 网络 |
|----|------|------|----------|---------|--------|------|
| scenario-001 | 北京CBD早高峰通勤 | real-world | urban | throughput | advanced | 5G NR FR1 |
| scenario-002 | 京沪高速G2巡航 | real-world | highway | handover | intermediate | 5G NR FR1 |
| scenario-003 | 上海南京路隧道穿越 | real-world | tunnel | reliability | advanced | LTE |
| scenario-004 | 深圳科技园区覆盖验证 | real-world | urban | coverage | intermediate | 5G NR FR1 |
| scenario-005 | 郊区低速移动场景 | synthetic | suburban | coverage | basic | 5G NR FR1 |
| scenario-006 | 室内停车场穿透测试 | synthetic | indoor | coverage | intermediate | LTE |
| scenario-007 | 高速极限移动测试 | synthetic | highway | mobility | extreme | 5G NR FR1 |
| scenario-008 | 密集干扰城区场景 | synthetic | urban | interference | advanced | 5G NR FR1 |
| scenario-009 | V2X十字路口碰撞预警 | real-world | urban | latency | intermediate | C-V2X |
| scenario-010 | 连续切换压力测试 | synthetic | highway | handover | advanced | 5G NR FR1 |

## 统计信息

- **总场景数**: 10
- **真实场景**: 4个 (scenario-001, 002, 003, 004, 009)
- **合成场景**: 6个 (scenario-005, 006, 007, 008, 010)
- **复杂度分布**:
  - basic: 1个
  - intermediate: 5个
  - advanced: 3个
  - extreme: 3个

## 使用方法

```typescript
import { scenarioList, getScenarioById, filterScenarios } from './data/scenarioLibrary'

// 获取所有场景列表
const allScenarios = scenarioList

// 根据ID获取详情
const scenario = getScenarioById('scenario-001')

// 筛选场景
const urbanScenarios = filterScenarios({ geographyType: 'urban' })
const highSpeedScenarios = filterScenarios({ tags: ['高速'] })
```

## 数据完整性

所有场景均包含：
- ✅ 完整的网络配置（基站、频率、带宽）
- ✅ 详细的车辆轨迹（路点、速度）
- ✅ 环境条件定义（信道模型、传播特性）
- ✅ 业务流量模型
- ✅ KPI目标定义
- ✅ 完整性验证标记

真实场景（4个）额外包含：
- ✅ 地理坐标
- ✅ 射线跟踪工具信息
- ✅ 射线跟踪输出结果

## 下一步

- [ ] 实现场景到测试例的映射器（OTAScenarioMapper）
- [ ] 开发场景库UI组件
- [ ] 集成到虚拟路测主流程
