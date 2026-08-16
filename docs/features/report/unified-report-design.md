# 统一报告系统设计

## 概述

> ⚠️ **ARCH-1 S5（2026-07-30）读前须知**：本文里的 `source: 'test_plan'` 一支
> **已无写入方** —— 计划链随 ARCH-1 S4 拆除。
> ⚠️ **别按单一字段过滤报告** —— `TestReport` 的关联字段有三种落法：
> ① **自动归档 · 正式测试**（TestCase 执行）→ `test_execution_ids`；
> ② **自动归档 · 虚拟路测** → `road_test_execution_id`（`_archive_execution_report()`
>    仅由 VRT 停止/完成的唯一终态 winner 首次创建；既有归档不会被自动重开或更新，
>    **`test_execution_ids` 是空的**，见 `app/api/road_test.py`）；
> ③ **通用创建** `POST /api/v1/reports` → `ReportCreate` 的 `test_execution_ids`
>    与 `road_test_execution_id` **都可以为空**（`app/schemas/report.py:27/62`），
>    所以 custom / summary / 甚至 single_execution 型报告可能**两个关联字段都没有**。
>
> 按 `test_execution_ids` 过滤会同时漏掉 ② 和 ③。要全量就别加关联字段条件。
> `TestReport.test_plan_id` 字段与报告采集器的读取分支**保留**，因为 ARCH-1 之前
> 生成的老报告那个字段有值，重新生成时还要读（只读历史，见
> `app/services/report_data_collector.py`）。
> 报告架构本身（单次执行 / 汇总 / 对比三类、统一组件）不受影响。

---

本文档定义统一的测试报告架构，整合测试计划模块和虚拟路测模块的报告功能。

## 设计原则

1. **统一数据模型**：所有报告使用相同的数据库模型和 API
2. **模块化内容**：不同模块可以扩展报告内容，但使用统一结构
3. **通用展示组件**：前端使用统一的 ReportViewer 组件
4. **自动报告生成**：执行完成时自动创建报告记录

## 报告类型

| 类型 | 描述 | 来源 |
|------|------|------|
| `single_execution` | 单次执行报告 | 测试计划执行、虚拟路测执行 |
| `road_test` | 虚拟路测报告 | 虚拟路测模块（single_execution 的子类型） |
| `comparison` | 对比分析报告 | 多次执行对比 |
| `summary` | 汇总报告 | 测试计划汇总 |
| `compliance` | 合规性报告 | 标准符合性检查 |

## 统一报告内容结构 (content_data)

```typescript
interface ReportContentData {
  // === 基本信息 ===
  source: 'test_plan' | 'road_test';
  execution_id: string;
  title: string;
  description?: string;

  // === 执行信息 ===
  execution: {
    mode?: string;           // 测试模式（digital_twin/conducted/ota）
    status: string;
    start_time?: string;
    end_time?: string;
    duration_s?: number;
    notes?: string;
  };

  // === 场景配置（虚拟路测特有） ===
  scenario?: {
    id: string;
    name: string;
    category: string;
    description?: string;
    tags: string[];
  };

  // === 网络配置 ===
  network?: {
    type: string;           // 5G NR, LTE, etc.
    band: string;
    bandwidth_mhz: number;
    duplex_mode: string;
    scs_khz?: number;
  };

  // === 环境配置 ===
  environment?: {
    type: string;
    channel_model: string;
    weather: string;
    traffic_density: string;
  };

  // === 路径信息 ===
  route?: {
    duration_s: number;
    distance_m: number;
    waypoint_count: number;
    avg_speed_kmh?: number;
  };

  // === 基站配置 ===
  base_stations?: Array<{
    bs_id: string;
    name: string;
    tx_power_dbm: number;
    antenna_config: string;
    antenna_height_m: number;
  }>;

  // === 步骤配置 ===
  step_configs?: Array<{
    step_name: string;
    enabled: boolean;
    parameters: Record<string, any>;
  }>;

  // === 执行阶段结果 ===
  phases: Array<{
    name: string;
    status: 'completed' | 'failed' | 'skipped';
    duration_s: number;
    start_time: string;
    end_time: string;
    notes?: string;
  }>;

  // === KPI 汇总 ===
  kpi_summary: Array<{
    name: string;
    unit: string;
    mean: number;
    min: number;
    max: number;
    std?: number;
    target?: number;
    passed?: boolean;
  }>;

  // === 总体结果 ===
  // P1-48: 四态，别只记 passed/failed。
  //   passed / failed  —— 有可信判决（failed 也包括执行本身失败）
  //   undetermined     —— 跑完了，但没有一条可信判决（例如全部来自浏览器模拟）
  //   incomplete       —— 没跑完（还在跑 / 被中止）
  // ⚠️ undetermined 与 incomplete 不是一回事：前者是「测了但结果不可信」，
  //    后者是「压根没测完」。混用会让操作员以为测试中断了。
  overall_result: 'passed' | 'failed' | 'incomplete' | 'undetermined';
  // P1-48: 可空。没有可信判决时是 null，不是 0 ——
  // 写 0 会把「没有证据」变成「0% 通过」这个假的量化失败结论。
  // 消费方（PDF、界面）必须显式处理 null，别直接 round() / f"{x:.1f}"。
  pass_rate: number | null;

  // === 事件日志 ===
  events: Array<{
    time: string;
    type: string;
    description: string;
  }>;
}
```

## 数据库模型扩展

在 `TestReport` 模型中添加：

```python
# 报告内容数据（JSON格式，包含完整的报告内容）
content_data = Column(JSON, comment="Report content data (structured JSON)")

# 虚拟路测执行关联（可选）
road_test_execution_id = Column(String(100), comment="Road test execution ID (if applicable)")
```

## API 设计

### 创建通用报告

```
POST /api/v1/reports
{
  "title": "3GPP UMa Handover 测试报告",
  "report_type": "road_test",
  "format": "json",
  "generated_by": "system",
  "content_data": { ... }
}
```

通用创建入口不得携带 `road_test_execution_id`。VRT 报告的唯一归档槽与内容只由
服务端终态归档拥有；completed/stopped 执行的手工恢复使用：

```
POST /api/v1/road-test/executions/{execution_id}/archive-report
```

该入口从权威执行记录重建内容，不接受客户端 KPI/content_data。只有最终
`completed` 报告返回成功；`pending`、`failed`、以及无法证明 writer 仍存活的
`generating` 均返回 409 与可操作说明。服务端生成的 VRT 内容以精确整数
`vrt_archive_trust_schema_version: 1` 证明所有权；升级前旧 GUI 创建且没有该标记的
同 execution 行不能直接复用或下载，而是保留原 report id 并由上述入口从终态执行重建。
重建以旧 `content_data` 快照作为原子 writer claim 的一部分，迟到请求不能在首个 writer
完成后再次覆盖。claim winner 会先清除旧 HTML/Excel、模板、标题/生成者与文件元数据，
再以服务端权威 PDF envelope 发布；trust 标记不能只证明 payload 而继续放行客户端外壳。
列表以 `vrt_archive_trusted` 暴露这项真值，使旧行不会隐藏对应的待归档执行。

### 获取报告内容

```
GET /api/v1/reports/{report_id}
```

返回完整的报告数据，包括 `content_data`。

### 虚拟路测执行完成时自动创建报告

当虚拟路测执行状态变为 `completed` 时，自动：
1. 收集执行数据和场景配置
2. 创建报告记录
3. 返回报告 ID 供前端使用

## 前端组件设计

### 统一 ReportViewer 组件

```
gui/src/components/Report/
├── ReportViewer.tsx          # 统一报告查看组件
├── ReportOverview.tsx        # 概览标签页
├── ReportConfiguration.tsx   # 配置标签页（场景/网络/环境）
├── ReportSteps.tsx           # 步骤参数标签页
├── ReportResults.tsx         # 执行结果标签页
├── ReportKPIs.tsx            # KPI 汇总组件
├── ReportTimeline.tsx        # 阶段时间线组件
└── index.ts
```

### 使用方式

```tsx
// 测试计划模块
<ReportViewer reportId={reportId} />

// 虚拟路测模块
<ReportViewer reportId={reportId} />
// 或者通过执行ID加载
<ReportViewer roadTestExecutionId={executionId} />
```

## 迁移计划

1. **Phase 1: 数据库扩展**
   - 添加 `content_data` 和 `road_test_execution_id` 字段
   - 创建数据库迁移脚本

2. **Phase 2: API 更新**
   - 扩展报告创建 API 支持 content_data
   - 添加虚拟路测完成时自动创建报告的逻辑

3. **Phase 3: 前端统一**
   - 创建统一的 ReportViewer 组件
   - 迁移虚拟路测使用统一组件
   - 测试计划模块集成统一组件

## 向后兼容

- 现有的报告 API 保持不变
- `content_data` 为可选字段，不影响现有报告
- 旧报告可以通过 `test_plan_id` 和 `test_execution_ids` 引用数据
