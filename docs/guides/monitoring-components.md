# 监控组件使用指南

## 实时监控组件与当前界面位置

本文档说明系统中两个实时指标组件的差异化定位，以及它们在当前界面中的实际挂载位置。
主控台不再常驻显示实时指标；其操作视图由顶部就绪状态、最近执行和实时日志组成。

---

## 组件概览

### 1. RealtimeMetricsCard - 可复用的系统健康监控

**位置**: `gui/src/components/RealtimeMetricsCard.tsx`

**用途**: 可按需嵌入的系统健康监控

**当前界面位置**: 当前导航没有直接挂载；2026-09-05 起不再作为主控台常驻区域

**特性**:
- ✅ 实时 WebSocket 连接（同源路径 `/api/v1/ws/monitoring`；本地开发默认
  `ws://localhost:8000/api/v1/ws/monitoring`）
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

**数据源**: 后端监控 WebSocket 投影；组件本身不提供测试执行上下文

**观测契约**: 每项均携带 `value|null`、`status`、`provenance`、`reason` 与 `timestamp`。
只有真实 BaseStation 明确验证且口径为 `pcell` / `nr_all_cells` 的当前下行吞吐可以显示数值；
SNR、EIRP、温度没有权威实时来源时显示 N/A，模拟值只作黄色诊断，不能解释为正式通过。

**示例**:
```tsx
import { RealtimeMetricsCard } from '@/components/RealtimeMetricsCard'

function StandaloneMetricsView() {
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

**当前界面位置**: 调试维护 → 演示回放

**特性**:
- ✅ 复用RealtimeMetricsCard的所有性能优化
- ✅ **测试执行上下文**（测试用例名称、当前相位；ARCH-1 前这里显示的是计划名）
- ✅ **逐指标观测状态与来源**
- ✅ 缺测显示 N/A，模拟值显示黄色诊断状态
- ✅ 不在监控组件内产生 pass/fail 或“合规率”

**差异化内容**:

1. **测试执行信息**
   - 显示当前执行的测试用例名称（ARCH-1 前是计划名，计划链已拆除）
   - 显示步骤进度（步骤 2/5）
   - 显示当前步骤标题

2. **观测真值**
   ```
   ┌────────────────────────┐
   │ 吞吐量      [observed] │  ← 真实权威观测
   │ 148.5 Mbps            │
   ├────────────────────────┤
   │ EIRP      [unavailable]│  ← 尚无权威实时来源
   │ N/A                   │
   └────────────────────────┘
   ```

3. **状态颜色**
   - 蓝色：`observed`，表示有真实权威观测，不表示通过
   - 黄色：`simulated`，只作诊断
   - 灰色：`unavailable`，显示 N/A 与具体原因

**数据源**: 与 RealtimeMetricsCard 共用服务器权威监控 WebSocket 投影，不叠加客户端阈值或第二判据

**示例**:
```tsx
import { ExecutionMetricsCard } from '@/features/Monitoring'

function DiagnosticsDemoPlayback() {
  return (
    <ExecutionMetricsCard
      throttleMs={100}
      testPlanName="TRP校准测试 - 3500MHz"
      currentStep={{
        index: 2,
        total: 5,
        title: "方位角扫描 (0° - 360°)"
      }}
      debug={false}
    />
  )
}
```

---

## 对比表格

| 特性 | RealtimeMetricsCard（可复用） | ExecutionMetricsCard（调试维护） |
|------|----------------------------------|-----------------------------------|
| **用途** | 系统健康监控 | 测试执行监控 |
| **上下文** | 无 | 测试用例 + 相位 |
| **判定** | 不产生 pass/fail | 不产生 pass/fail |
| **来源状态** | ✅ | ✅ |
| **缺测/模拟** | N/A / 黄色诊断 | N/A / 黄色诊断 |
| **性能优化** | ✅ Throttling + Memo | ✅ 继承所有优化 |
| **使用时机** | 按需挂载 | 调试演示回放期间 |
| **显示位置** | 当前无直接导航入口 | 调试维护 → 演示回放 |

---

## 差异化策略总结

### 主控台（当前不挂载实时指标）

**场景**: 用户要快速判断 **“能不能开测、刚刚发生了什么？”**

- 顶部显示服务器权威的就绪状态与阻塞原因
- 左侧显示最近执行
- 右侧显示实时日志与紧凑告警计数
- 不建立实时指标 WebSocket；需要开发调试时进入“调试维护”

### 调试维护 → 演示回放（ExecutionMetricsCard）

**场景**: 开发或调试人员查看 **“演示执行进展如何、当前有哪些可信观测？”**

- 演示执行监控
- 测试步骤进度
- 观测来源与缺测原因
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
│   HAL Service   │ ← 当前只消费 BaseStation 权威实时吞吐
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
│ 当前未直接挂载 │  │ 调试维护/演示回放│
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
- ✅ 组件文档

### P1-76（已实现，Ready PR）
- ✅ 删除固定/随机 fallback 与无依据 EIRP/温度
- ✅ 统一 nullable + provenance 观测契约
- ✅ 删除客户端硬编码期望范围与合规率

### 当前界面状态
- ✅ `ExecutionMetricsCard` 已挂载到“调试维护 → 演示回放”
- ✅ 主控台已移除无操作价值的实时指标区，保留就绪、最近执行和实时日志
- ⏳ 通用实时指标卡是否重新提供独立入口，需由后续明确的用户场景决定

### Phase 3 (待实施)
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
- [AGENTS.md](../../AGENTS.md) - 系统设计文档
- [CLAUDE.md](../../CLAUDE.md) - 开发指南
