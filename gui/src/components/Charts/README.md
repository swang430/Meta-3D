# Advanced Charts Components - Plotly.js Integration

这个目录包含使用 Plotly.js 实现的高级图表组件，专为 MIMO OTA 测试系统的数据可视化设计。

## 已实现的图表组件

### 1. TimeSeriesChart - 时间序列图表

用于展示测试指标随时间的变化，包括趋势分析和异常检测。

**功能特性**:
- 时间序列数据可视化
- 滚动平均线（Rolling Mean）
- 异常值检测和高亮显示（Z-score 方法）
- 趋势线和 R² 统计
- 置信区间阈值线（±Nσ）
- 交互式缩放和平移

**使用示例**:
```tsx
import { TimeSeriesChart } from '@/components/Charts'

<TimeSeriesChart
  title="Throughput Over Time"
  metricName="Throughput (Mbps)"
  dataPoints={[
    {
      timestamp: "2025-01-01T00:00:00Z",
      value: 520.5,
      execution_id: "exec-1",
      is_anomaly: false,
      z_score: 0.5
    },
    // ... more points
  ]}
  trend={{
    direction: 'increasing',
    slope: 2.0,
    r_squared: 0.85,
    strength: 'strong'
  }}
  rollingMean={[500, 505, 510, ...]}
  rollingStd={[15, 16, 14, ...]}
  anomalyThreshold={3.0}
  height={500}
/>
```

### 2. StatisticsComparisonChart - 统计对比图表

用于多个报告的指标统计对比分析。

**功能特性**:
- 箱线图（Box Plot）显示分布
- 柱状图（Bar Chart）显示均值和标准差
- 多指标并排对比
- 置信区间可视化
- 变异系数（CV）计算和展示
- 子图布局支持

**使用示例**:
```tsx
import { StatisticsComparisonChart } from '@/components/Charts'

<StatisticsComparisonChart
  title="Multi-Report Comparison"
  comparisonResults={[
    {
      metric_name: "throughput_mbps",
      report_statistics: {
        "report-1": {
          metric_name: "throughput_mbps",
          mean: 520,
          median: 515,
          std: 45,
          min: 450,
          max: 600,
          range: 150,
          count: 100,
          percentiles: { "25": 490, "50": 515, "75": 550 },
          confidence_interval: { lower: 510, upper: 530 }
        },
        // ... more reports
      },
      overall_mean: 515,
      overall_std: 48,
      coefficient_of_variation: 9.3
    },
    // ... more metrics
  ]}
  reportIds={["report-1", "report-2", "report-3"]}
  reportNames={{
    "report-1": "Baseline",
    "report-2": "Optimized",
    "report-3": "Field Test"
  }}
  chartType="box"  // or "bar"
  height={600}
/>
```

### 3. PerformanceBenchmarkChart - 性能基准图表

用于展示报告的性能评级和百分位排名。

**功能特性**:
- 水平条形图显示百分位排名
- 性能阈值参考线（Excellent/Good/Average）
- 性能等级标识（excellent/good/average/below_average/poor）
- Z-score 统计
- 详细的指标分解展示
- 进度条可视化

**使用示例**:
```tsx
import { PerformanceBenchmarkChart } from '@/components/Charts'

<PerformanceBenchmarkChart
  title="Performance Benchmark"
  benchmarkMetrics={[
    {
      metric_name: "throughput_mbps",
      value: 520,
      percentile_rank: 85.5,
      performance_rating: "good",
      reference_mean: 500,
      reference_std: 50,
      z_score: 0.4
    },
    // ... more metrics
  ]}
  overallPercentile={87.6}
  overallRating="good"
  summary="Report performs at 87.6th percentile across 5 metrics"
  height={500}
/>
```

## 数据类型定义

### TimeSeriesDataPoint
```typescript
interface TimeSeriesDataPoint {
  timestamp: string          // ISO 8601 格式
  value: number              // 指标值
  execution_id: string       // 测试执行 ID
  is_anomaly?: boolean       // 是否为异常点
  z_score?: number          // Z-score 值
}
```

### TrendData
```typescript
interface TrendData {
  direction: 'increasing' | 'decreasing' | 'stable'
  slope: number             // 趋势斜率
  r_squared: number         // 决定系数
  strength: 'strong' | 'moderate' | 'weak'
}
```

### MetricStatistics
```typescript
interface MetricStatistics {
  metric_name: string
  mean: number
  median: number
  std: number
  min: number
  max: number
  range: number
  count: number
  percentiles?: Record<string, number>
  confidence_interval?: { lower: number; upper: number }
}
```

### BenchmarkMetric
```typescript
interface BenchmarkMetric {
  metric_name: string
  value: number
  percentile_rank: number
  performance_rating: 'excellent' | 'good' | 'average' | 'below_average' | 'poor'
  reference_mean: number
  reference_std: number
  z_score: number
}
```

## 技术栈

- **Plotly.js** (plotly.js-dist-min): 核心图表库
- **react-plotly.js**: React 封装
- **@mantine/core**: UI 组件库
- **@tabler/icons-react**: 图标库

## 性能优化

1. **Memoization**: 所有图表数据使用 `useMemo` 进行缓存，避免不必要的重新计算
2. **最小化包**: 使用 plotly.js-dist-min 而非完整版本
3. **惰性加载**: 图表组件可以按需导入
4. **响应式设计**: 图表自动适应容器大小

## 主题和样式

所有图表组件已集成 Mantine 主题系统：
- 使用 Mantine 颜色调色板
- 支持亮色/暗色模式（通过 Plotly layout 配置）
- 统一的间距和排版

## 演示页面

查看 `ChartsDemoPage.tsx` 获取完整的使用示例和模拟数据生成方法。

## 与后端 API 集成

这些图表组件设计为直接与统计服务 API 配合使用：

- **TimeSeriesChart** ← `/api/v1/reports/statistics/time-series`
- **StatisticsComparisonChart** ← `/api/v1/reports/statistics/compare`
- **PerformanceBenchmarkChart** ← `/api/v1/reports/statistics/benchmark`

## 下一步扩展

可能的功能增强：
- [ ] 添加热图（Heatmap）用于信号强度空间分布
- [ ] 添加 3D 散点图用于多维度分析
- [ ] 添加实时更新能力（WebSocket 支持）
- [ ] 添加图表导出功能（PNG, SVG, PDF）
- [ ] 添加自定义主题配置
