# 监控组件使用指南

## Phase 2.7: 实时监控的差异化策略

本文档说明系统中两个监控组件的差异化定位和使用场景。

---

## 组件概览

### 1. RealtimeMetricsCard - 系统健康监控

**位置**: `gui/src/components/RealtimeMetricsCard.tsx`

**用途**: **Always-on系统健康监控**

**使用场景**: Dashboard主仪表板

**特性**:
- ✅ 实时WebSocket连接（ws://localhost:8001/api/v1/ws/monitoring）
- ✅ Phase 2.6性能优化（throttling 100ms, React.memo, useMemo）
- ✅ 自动重连机制
- ✅ Skeleton加载状态
- ✅ 平滑过渡动画
- ⚠️ **无测试执行上下文**

**显示内容**:
- 吞吐量 (Throughput)
- 信噪比 (SNR)
- 静区均匀度 (Quiet Zone Uniformity)
- EIRP
- 温度 (Temperature)

**数据源**: 后端HAL服务（Mock仪器驱动）

**示例**:
```tsx
import { RealtimeMetricsCard } from '@/components/RealtimeMetricsCard'

function Dashboard() {
  return (
    <RealtimeMetricsCard
      throttleMs={100}  // 100ms throttling
      debug={false}      // 不显示调试信息
    />
  )
}
```

---

### 2. ExecutionMetricsCard - 测试执行监控

**位置**: `gui/src/features/Monitoring/components/ExecutionMetricsCard.tsx`

**用途**: **测试执行期间的上下文监控**

**使用场景**: 实时监控 Tab（Monitoring）

**特性**:
- ✅ 复用RealtimeMetricsCard的所有性能优化
- ✅ **测试执行上下文**（测试计划名称、当前步骤）
- ✅ **期望值vs实际值对比**
- ✅ **指标合规率进度条**
- ✅ **超出范围可视化提示**（黄色边框 + 警告图标）
- ✅ 期望值范围显示

**差异化内容**:

1. **测试计划信息**
   - 显示当前执行的测试计划名称
   - 显示步骤进度（步骤 2/5）
   - 显示当前步骤标题

2. **期望值对比**
   ```
   ┌────────────────────────┐
   │ 吞吐量          [⚠️]   │  ← 超出范围警告
   │ 148.5 Mbps            │  ← 当前值（黄色）
   │ 🎯 期望: 140-160 Mbps │  ← 期望范围
   └────────────────────────┘
   ```

3. **指标合规率**
   - 进度条显示符合预期的指标百分比
   - 颜色编码：
     - 绿色：≥80%
     - 黄色：60-80%
     - 红色：<60%
   - 显示统计：4/5 项指标在期望范围内

4. **增强的可视化**
   - 超出范围的指标：黄色边框（2px）+ 警告图标
   - 当前值颜色变化（黄色表示超出范围）
   - 期望范围始终可见

**数据源**: 与RealtimeMetricsCard相同，但添加了本地的期望值配置

**示例**:
```tsx
import { ExecutionMetricsCard } from '@/features/Monitoring'

function MonitoringTab() {
  return (
    <ExecutionMetricsCard
      throttleMs={100}
      testPlanName="TRP校准测试 - 3500MHz"
      currentStep={{
        index: 2,
        total: 5,
        title: "方位角扫描 (0° - 360°)"
      }}
      expectedRanges={{
        throughput: { min: 140, max: 160 },
        snr: { min: 23, max: 27 },
        quiet_zone_uniformity: { min: 0.7, max: 1.0 },
        eirp: { min: 43, max: 47 },
        temperature: { min: 20, max: 25 }
      }}
      debug={false}
    />
  )
}
```

---

## 对比表格

| 特性 | RealtimeMetricsCard (Dashboard) | ExecutionMetricsCard (Monitoring) |
|------|----------------------------------|-----------------------------------|
| **用途** | 系统健康监控 | 测试执行监控 |
| **上下文** | 无 | 测试计划 + 步骤 |
| **期望值** | ❌ 无 | ✅ 显示并对比 |
| **合规率** | ❌ 无 | ✅ 进度条显示 |
| **超出范围提示** | ❌ 无 | ✅ 黄色边框 + 图标 |
| **性能优化** | ✅ Throttling + Memo | ✅ 继承所有优化 |
| **使用时机** | Always-on | 测试执行期间 |
| **显示位置** | Dashboard | Monitoring Tab |

---

## 差异化策略总结

### Dashboard（RealtimeMetricsCard）
**场景**: 用户想知道 **"系统当前状态如何？"**
- 通用系统健康监控
- 简洁的指标展示
- 无需测试上下文
- 持续运行

### Monitoring Tab（ExecutionMetricsCard）
**场景**: 用户想知道 **"我的测试进展如何？指标是否符合预期？"**
- 测试执行监控
- 期望值vs实际值对比
- 测试步骤进度
- 指标合规状态
- 仅在测试运行时使用

---

## 实现细节

### 共享的性能优化

两个组件都使用相同的`useMonitoringWebSocket` Hook，包括：

1. **Throttling（节流）**: 默认100ms，限制最大更新频率为10次/秒
2. **Backend Cache**: 后端HAL服务的0.5s TTL缓存
3. **React优化**: React.memo、useMemo、useCallback
4. **组合效果**:
   - 单客户端：~33% 减少渲染
   - 多客户端：87-97% 减少后端查询

### 数据流

```
┌─────────────────┐
│   HAL Service   │ ← Mock Drivers (Channel Emulator, Base Station, Analyzer)
│  (0.5s cache)   │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   monitoring.py │ ← FastAPI WebSocket Broadcaster (1Hz)
│  (broadcaster)  │
└────────┬────────┘
         │
         ↓
┌──────────────────────────────────┐
│  useMonitoringWebSocket Hook     │ ← Throttling (100ms)
│  (Frontend)                      │
└────────┬─────────────────┬───────┘
         │                 │
         ↓                 ↓
┌────────────────┐  ┌─────────────────┐
│ RealtimeMetrics│  │ ExecutionMetrics│
│     Card       │  │      Card       │
│  (Dashboard)   │  │   (Monitoring)  │
└────────────────┘  └─────────────────┘
```

---

## 未来增强（Phase 3+）

### RealtimeMetricsCard
- [ ] 历史趋势迷你图
- [ ] 可配置的阈值告警
- [ ] 暗黑模式优化

### ExecutionMetricsCard
- [ ] 历史对比图表（当前运行 vs 上次运行）
- [ ] 自动保存超出范围的快照
- [ ] 导出测试报告（PDF）
- [ ] 实时告警通知

---

## 开发笔记

### Phase 2.6 (已完成)
- ✅ `useMonitoringWebSocket` 性能优化
- ✅ `RealtimeMetricsCard` 组件优化

### Phase 2.7 (已完成)
- ✅ `ExecutionMetricsCard` 差异化组件
- ✅ 测试执行上下文集成
- ✅ 期望值对比功能
- ✅ 指标合规率可视化
- ✅ 组件文档

### Phase 3 (待实施)
- ⏳ 在Monitoring Tab中集成ExecutionMetricsCard（替换现有指标显示）
- ⏳ 历史对比图表
- ⏳ PDF报告生成

---

## 技术栈

- **React 18** + TypeScript
- **Mantine UI** v7+ (Card, Badge, Progress, SimpleGrid等)
- **WebSocket** (实时双向通信)
- **FastAPI** (后端WebSocket broadcaster)
- **HAL架构** (硬件抽象层 + Mock驱动)

---

## 联系与反馈

如有问题或建议，请提交Issue或参考：
- [ARCHITECTURE-REVIEW.md](./ARCHITECTURE-REVIEW.md) - 架构审查
- [AGENTS.md](./AGENTS.md) - 系统设计文档
- [CLAUDE.md](./CLAUDE.md) - 开发指南
