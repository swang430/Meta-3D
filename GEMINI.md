# GEMINI 项目审查与记忆库

## 项目概览
- **名称:** MIMO-First
- **日期:** 2026-01-04
- **目标:** 从底层进行代码审查，发现问题并收敛公共逻辑（DRY原则）。

## 1. 审查日志 (代码发现)

### 架构分析
- **双头后端架构 (Dual-Head Backend):**
    - `api-service` (Port 8000): 负责硬件管理、用户、拓扑存储。使用 PostgreSQL。
    - `channel-engine-service` (Port 8001): 负责物理计算（探头权重、信道模型）。无数据库，纯计算。
    - **前端 (GUI):** 直接分别与两个服务通信（意图上）。

### 关键发现与风险

1.  **路由冲突 (Critical Routing Conflict):**
    - **问题:** `channel-engine-service` 使用 `/api/v1/ota` 前缀。`api-service` 使用 `/api/v1/...`。
    - **Vite 代理:** `vite.config.ts` 只有一条规则 `/api` -> `http://localhost:8000`。
    - **后果:** 前端对 Channel Engine (`/api/v1/ota/...`) 的调用会被错误地路由到 API Service (8000)，导致 404 错误。Channel Engine 实际上是不可达的。

2.  **数据模型重复 (Model Duplication):**
    - `channel-engine-service` (Python) 与 `gui` (TS) 之间的模型是手动同步的。

3.  **数据/物理模型不匹配 (Severe Data Mismatch):**
    - **DB (`init_probes.py`):** 生成 2D 平面阵列（24个探头，尽管声称32个）。
    - **Sim (`channelEngine.ts`):** 生成 3D 球面阵列（32个探头）。
    - **后果:** 虚拟仿真无法直接映射到物理配置。

4.  **HAL (硬件层) 缺失:**
    - `api-service/app/hal` 仅包含抽象基类 (ABC) 和 Mock 实现。
    - **没有真实仪器的驱动程序**。系统目前完全运行在模拟模式下。

5.  **Auth 弱点:**
    - JWT 验证仅基于签名，不检查数据库中用户是否存在或已被禁用。

### 缺陷 (Bugs)
- **`api-service/scripts/init_probes.py`**: 循环逻辑错误，生成 24 个而不是 32 个探头。
- **`gui/vite.config.ts`**: 缺少转发到端口 8001 的代理规则。

## 2. 共享知识 (事实)
- **端口:** API(8000), Engine(8001), GUI(5173).
- **依赖:** Engine 依赖本地 `~/ChannelEgine`。

## 3. 收敛与改进建议 (Action Items)
1.  **修复路由**: 更新 `vite.config.ts`，添加 `/api/v1/ota` -> `localhost:8001` 的代理规则。
2.  **修复初始化脚本**: 修正 `init_probes.py`。
3.  **Schema 同步**: 引入 OpenAPI 生成 TS 客户端。
4.  **HAL 实现**: 实际上还需要编写硬件驱动程序（这是 Phase 2 的工作）。
