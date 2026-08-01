# GEMINI 项目审查与记忆库

## 项目概览
- **名称:** MIMO-First
- **日期:** 2026-01-04
- **目标:** 从底层进行代码审查，发现问题并收敛公共逻辑（DRY原则），并修复关键 Bug 和用户体验问题。

## 0. 核心原则 (Core Rules)
- **语言:** 所有的交流、文档和输出必须使用 **简体中文 (Simplified Chinese)**。


## 1. 审查与修复日志 (Audit & Fix Log)

### 已解决的关键问题 (Resolved Critical Issues)
- [x] **路由冲突 (Routing Conflict):**
    - **问题:** 前端无法访问 Channel Engine (`/api/v1/ota`)，因为 Vite 代理错误地将其路由到了 API Service (8000)。
    - **修复:** 在 `gui/vite.config.ts` 中添加了针对 `/api/v1/ota` 到端口 8001 的专用代理规则。
- [x] **WebSocket 连接失败:**
    - **问题:** 浏览器受系统代理影响或 Vite 代理 WebSocket 不稳定，导致 `ws://localhost:5173` 连接失败。
    - **修复:** 修改前端 (`useMonitoringWebSocket.ts`, `App.tsx`) 在开发模式下绕过代理，直接连接 `ws://localhost:8000` (或 `127.0.0.1`)。
- [x] **报告生成 500 错误:**
    - **问题:** 报告生成逻辑在处理 Route Waypoints 时，错误地将字典 (`dict`) 当作对象属性 (`obj.lat`) 访问，导致 `AttributeError`。
    - **修复:** 在 `api-service/app/api/road_test.py` 中引入 `get_attr_or_item` 辅助函数，并全量重构 `_generate_execution_report` 以安全处理数据访问。
- [x] **数据/物理模型不匹配 (Data Mismatch):**
    - **问题:** `init_probes.py` 生成的探头数量 (24) 与仿真需求 (32) 不符。
    - **修复:** 重写初始化脚本，生成正确的 32 探头 3D 布局。

### 优化与增强 (Optimizations & Enhancements)
- [x] **场景数据准确性:**
    - **速度计算:** 修复前端场景创建时的距离计算公式 (缺少 `/ 3.6`)，解决了报告中速度显示错误 (5 vs 18 km/h) 的问题。
    - **基站数量:** 前端 `CreateScenarioDialog` 不再硬编码 1 个基站，而是添加了“基站数量”输入框，支持动态生成指定数量的基站。
- [x] **报告展示体验:**
    - **Tab 重命名:** 将“执行结果”标签重命名为“执行过程”，消除歧义。
    - **参数可视化:** 将测试步骤参数展示从原始 JSON 代码块 (`JSON.stringify`) 优化为用户友好的 Key-Value 列表。
- [x] **数据持久化 (Persistence):**
    - **场景保存:** 为自定义场景实现了 JSON 文件持久化 (`data/custom_scenarios.json`)，解决了重启服务后测试例丢失的问题。
    - **Schema 收敛基础设施:**
    - 添加了 `scripts/export_channel_engine_schema.py` 和 npm 脚本，用于从 Channel Engine 自动生成 OpenAPI 规范，为未来前后端类型同步打下基础。
- [x] **VRT 数据归档 (VRT Archiving):**
    - **问题:** 虚拟路测 (VRT) 报告仅存在于内存中，并未持久化到数据库，导致“数据归档”列表看不到 VRT 记录。
    - **修复:** 实施“Option B+”方案。在 `api-service/app/api/road_test.py` 中挂载生命周期钩子，当测试停止或完成时，自动将 JSON 报告存入 `test_reports` 表。

## 2. 共享知识 (Facts)
- **技术栈:** Python 3.9+ (FastAPI), React 18 (Vite), PostgreSQL。
- **端口:** API(8000), Engine(8001), GUI(5173)。
- **依赖:** Channel Engine 依赖本地路径 `/Users/Simon/Tools/ChannelEgine`。
- **数据存储:**
    - 结构化数据 (Topology, Users): PostgreSQL (Docker: `meta3d_db`, Database: `meta3d_ota`).
    - 临时/自定义场景: JSON 文件 (`api-service/data/custom_scenarios.json`).

## 3. 待办事项与未来计划 (Backlog & Future Plans)

### Phase 1.5: 校准系统增强 (2026-01-26 完成)
- [x] **CAL-01 校准链路拓扑文档:** 创建 `calibration-topology.md`，定义 Path A/B/C 三种校准路径。
- [x] **CAL-02 RF Switch Matrix 校准:** 创建 `rf_switch_calibration_service.py`，实现插入损耗/隔离度/一致性测量。
- [x] **CAL-03 端到端校准 (E2E):** 创建 `e2e_calibration_service.py`，实现综合补偿矩阵生成和应用。
- [x] **CAL-04 相位校准:** 创建 `phase_calibration_service.py`，实现通道间相位一致性校准和补偿。
- [x] **CAL-05 依赖管理:** 扩展 `calibration_orchestrator.py`，添加依赖检查、级联失效和自动重校准触发。
- [x] **CAL-06 CE 内部校准:** 创建 `ce_internal_calibration_service.py`，集成厂商校准程序接口。
- [x] **CAL-07 工作流模板:** 扩展 `workflow_engine.py`，新增全系统校准、频率切换和路损校准工作流模板。
- [x] **CAL-08 数据可视化:** 创建 `CalibrationTimeline.tsx` 和 `CalibrationDependencyGraph.tsx` 并集成到 Dashboard。
- [x] **CAL-09 校准报告:** 扩展 `calibration_report_generator.py`，添加 ISO 证书、审计报告和数据导出功能。

### Phase 2: 硬件驱动与深度集成 (2026-04-27 完成)
- [x] **HAL 真实驱动:** 所有设备类别已实现真实 SCPI/VISA 驱动:
    - F64 信道仿真器 (`propsim_f64.py`, 1245行)
    - UXM 5G 综测仪 (`uxm_base_station.py`, 628行)
    - CMW500 LTE 综测仪 (`cmw500_base_station.py`, 724行)
    - Aerotech / ETS 转台 (`aerotech_positioner.py`, `ets_positioner.py`)
    - Keysight ENA / R&S ZNA VNA
    - Keysight MXG / R&S SMW200A 信号发生器
    - R&S FSW/FSVA / Keysight X-Series 频谱仪
    - ETS-Lindgren EMCenter RF 开关
- [x] **HAL 驱动注册工厂 (`driver_registry.py`):** 支持 `HAL_MODE` 环境变量 (mock/real/auto), 20 个驱动类注册映射, 批量连接/断开/健康检查。
- [x] **GCM 合规性:** 实现 Automatic PAS Rotation (`pas_rotation.py`), 等价于 GCM Tool 内置功能。
- [x] **相位补偿闭环:** 创建 `PhaseCompensationExecutor`, 通过 F64 SCPI (`OUTP:PHA:DEG:CH`) 将校准补偿值下发到硬件。打通 `phase_calibration_service → channel_engine_client → F64` 完整数据链路。
- [ ] **Auth 强化:** 完善 JWT 验证逻辑，增加数据库用户状态检查。

### Phase 3: 数据库迁移与架构收敛
- [ ] **配置专属 PostgreSQL (Docker):** 建立和配置 `meta3d_db` 专属 Docker 容器环境，以支撑高并发写入、海量结果矩阵存储以及强一致性的多模块外键校验。并将 `DATABASE_URL` 环境变量从目前的过渡期 SQLite 文件正式切回目标部署 PostgreSQL，通过 Alembic 维护 Schema。
- [ ] **场景数据入库:** 将目前的 JSON 文件持久化迁移到 PostgreSQL 数据库，设计完整的 `scenarios` 表结构。
- [ ] **Schema 自动同步:** 配置 CI/CD 或 pre-commit hook，自动运行 `openapi-typescript`，确保前端类型定义与后端 Pydantic 模型始终保持一致。
- [ ] **统一错误处理:** 在前后端建立统一的错误码规范，前端实现全局错误拦截与友好的 Toast 提示。

### 体验优化
- [ ] **高级场景配置:** 在前端提供更丰富的基站配置 UI（不仅仅是数量，还可以配置位置、功率等）。
- [ ] **实时波形图:** 优化 WebSocket 数据流，支持更高频率的波形数据推送与前端 Canvas/WebGL 渲染。

## 4. 日志编码规范 (Logging Standard)

> **核心原则:** 所有执行必须留痕。日志是过程记录（谁/何时/做了什么/结果如何），数据库是结果存储（补偿矩阵/校准值/测试报告）。两者互补，不可替代。

### 4.1 日志 vs 数据库的边界

| 维度 | 日志 (Log) | 数据库 (DB) |
|:---|:---|:---|
| **用途** | 过程审计、排错、回溯 | 结果存储、计算输入、报告生成 |
| **生命周期** | 按天轮转，保留 30~60 天 | 永久保留 |
| **写入时机** | 每一步操作 (包括失败) | 操作成功后 |
| **查询方式** | 文本搜索、时间范围过滤 | SQL 结构化查询 |
| **示例(校准)** | "用户 Simon 于 20:30 发起 Path Loss 校准，执行了 120 个频点，耗时 45s" | `path_loss_matrix[freq][port] = -2.3 dB` |
| **示例(测量)** | "角度 30° 时 DL=456.7Mbps BLER=0.0012 CQI=14 RI=2" | `test_reports.throughput_data = {...}` |

### 4.2 十路日志通道定义

所有日志统一由 `app/core/logging_config.py` 管理，使用 `TimedRotatingFileHandler` 按天轮转。

| # | 文件 | 命名空间 | 级别 | propagate | 内容 |
|:--|:-----|:---------|:-----|:----------|:-----|
| 1 | Console | root | INFO+ | — | 彩色人类可读摘要 |
| 2 | `app.log` | root | DEBUG+ | — | 全量 JSON 结构化日志 |
| 3 | `scpi.log` | `app.hal.scpi.*` | DEBUG | ✅ | 每条 SCPI TX/RX 原文 |
| 4 | `db.log` | `sqlalchemy.*` | INFO+ | ❌ | SQL 语句+连接池 |
| 5 | `calibration.log` | `app.calibration.*` | DEBUG | ✅ | 校准事件+中间数据 |
| 6 | `measurement.log` | `app.measurement.*` | DEBUG | ✅ | KPI 数据点快照 |
| 7 | `channel_engine.log` | `app.channel_engine` | DEBUG | ✅ | CE 仿真请求/响应 |
| 8 | `audit.log` | `app.audit` | INFO+ | ✅ | 用户操作审计 (保留 60 天) |
| 9 | `alert.log` | `app.alert` | WARNING+ | ✅ | 告警/异常事件 |
| 10 | `frontend.log` | `app.frontend` | DEBUG | ❌ | 浏览器行为日志 (POST 上报) |

### 4.3 Logger 命名规则

```python
# ✅ 正确: 使用专用命名空间
logger = logging.getLogger("app.calibration.path_loss")
logger = logging.getLogger("app.measurement.throughput")
logger = logging.getLogger("app.channel_engine")
logger = logging.getLogger("app.audit")
logger = logging.getLogger("app.alert")

# ✅ 正确: 非专用通道的一般业务代码
logger = logging.getLogger(__name__)  # → app.log + Console

# ❌ 错误: 校准服务使用 __name__
# 会导致日志不进入 calibration.log
logger = logging.getLogger(__name__)  # 在 calibration 服务中不要这样写
```

### 4.4 对应关系 (服务 → 命名空间)

| 服务文件 | Logger 命名空间 |
|:---|:---|
| `path_loss_calibration_service.py` | `app.calibration.path_loss` |
| `phase_calibration_service.py` | `app.calibration.phase` |
| `rf_switch_calibration_service.py` | `app.calibration.rf_switch` |
| `e2e_calibration_service.py` | `app.calibration.e2e` |
| `calibration_orchestrator.py` | `app.calibration.orchestrator` |
| `ce_internal_calibration_service.py` | `app.calibration.ce_internal` |
| `channel_calibration_service.py` | `app.calibration.channel` |
| `probe_calibration_service.py` | `app.calibration.probe` |
| `channel_engine_client.py` | `app.channel_engine` |
| UXM 驱动内 KPI 记录 | `app.measurement.throughput` |

### 4.5 结构化 extra 字段规范

所有日志通过 `extra={}` 传递结构化数据，由 `JsonFormatter` 自动序列化：

```python
# 校准日志必须包含
logger.info("校准完成", extra={
    "cal_type": "path_loss",          # 必须
    "freq_mhz": 3500,                 # 必须
    "port": "RF1",                    # 必须
    "before_db": -2.5,                # 推荐
    "after_db": -0.1,                 # 推荐
    "pass": True,                     # 必须
})

# 测量日志必须包含
meas_logger.info("[KPI]", extra={
    "dl_throughput_mbps": 456.7,      # 必须
    "dl_bler": 0.0012,                # 必须
    "cqi": 14,                        # 必须
    "rank_indicator": 2,              # 必须
    "band": "N78",                    # 推荐
    "bandwidth_mhz": 100,             # 推荐
})

# 审计日志必须包含
audit_logger.info("配置变更", extra={
    "user_id": "simon",               # 必须
    "action": "update_profile",       # 必须
    "target": "caict_n78_2x2",        # 必须
    "before": {...},                  # 推荐
    "after": {...},                   # 推荐
})

# 告警日志
alert_logger.warning("仪器离线", extra={
    "instrument_id": "uxm_e7515b",    # 必须
    "alert_type": "instrument_offline", # 必须
    "severity": "warning",            # 必须
})
```

### 4.6 前端日志 SDK 规范

前端通过 `POST /api/v1/system-logs/frontend` 批量上报：

```typescript
// gui/src/utils/logger.ts
const logger = new FrontendLogger();

// 页面导航
logger.info("page_nav", { page: "/calibration" });

// API 请求
logger.info("api_request", {
    url: "/api/v1/instruments/catalog",
    status_code: 200,
    elapsed_ms: 45,
});

// 用户操作
logger.info("btn_click", {
    component: "CalibrationWizard",
    message: "用户点击了开始校准",
});

// 错误
logger.error("unhandled_error", {
    error: "TypeError: Cannot read property 'id'",
    component: "ProbeLayoutView",
});
```
