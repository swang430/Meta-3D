# 数据架构指南 (Data Architecture Guide)

**文档版本**: v1.0
**创建日期**: 2025-12-29
**状态**: 生产环境

---

## 概述

本项目采用**前后端分离**架构，有两种数据源模式可供选择：

```
┌─────────────────────────────────────────────────────────────┐
│                    前端 (React + Vite)                       │
│                    gui/src/                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   Mock Server (开发)     │     │   后端 API (生产)        │
│   axios-mock-adapter    │     │   FastAPI + SQLite      │
│   gui/src/api/          │     │   api-service/          │
│   mockServer.ts         │     │   app/                  │
│   mockDatabase.ts       │     │                         │
└─────────────────────────┘     └─────────────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────────┐
                              │   SQLite 数据库          │
                              │   meta3d_ota.db         │
                              └─────────────────────────┘
```

---

## 当前配置状态

| 组件 | 状态 | 说明 |
|------|------|------|
| **Mock Server** | **已禁用** | `setupMockServer()` 在 main.tsx 中被注释 |
| **后端 API** | **启用** | FastAPI 服务运行在 http://localhost:8000 |
| **SQLite 数据库** | **启用** | 位于 api-service/meta3d_ota.db |

**重要**: 系统设计为**二选一**模式，不支持并行运行。当前使用后端 API 模式。

---

## 模式一：Mock Server (前端开发模式)

### 适用场景
- 前端独立开发
- 无需启动后端服务
- 快速原型验证
- 单元测试

### 启用方法

编辑 `gui/src/main.tsx`：

```typescript
// 取消注释以下两行
import { setupMockServer } from './api/mockServer.ts'
setupMockServer()
```

### 数据来源

| 文件 | 用途 |
|------|------|
| `gui/src/api/mockDatabase.ts` | Mock 数据存储 |
| `gui/src/api/mockServer.ts` | API 路由拦截 |

### Mock 数据结构

```typescript
// mockDatabase.ts 中的 sequenceLibrary
const sequenceLibrary = [
  // 通用测试步骤 (lib-* 前缀)
  { id: 'lib-setup-frequency', title: '设置频率', ... },
  { id: 'lib-load-channel', title: '加载信道模型', ... },
  // ...

  // 虚拟路测步骤 (vrt-* 前缀)
  { id: 'vrt-chamber-init', title: '步骤1: 初始化OTA暗室', ... },
  { id: 'vrt-network-config', title: '步骤2: 配置网络', ... },
  // ...
]
```

### 注意事项
- Mock 数据仅存在于浏览器内存中
- 刷新页面会重置所有状态
- 需要手动同步 Mock 数据与后端数据结构

---

## 模式二：后端 API (生产模式) ✅ 当前使用

### 适用场景
- 集成测试
- 生产环境
- 数据持久化
- 多用户协作

### 架构组件

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI 后端                             │
│                     api-service/app/                         │
├─────────────────────────────────────────────────────────────┤
│  API Layer          api/test_sequence.py                    │
│                     api/test_plans.py                        │
│                     api/calibration.py                       │
├─────────────────────────────────────────────────────────────┤
│  Service Layer      services/test_plan_service.py           │
│                     services/system_calibration.py           │
├─────────────────────────────────────────────────────────────┤
│  Model Layer        models/test_plan.py                      │
│                     models/calibration.py                    │
├─────────────────────────────────────────────────────────────┤
│  Database           db/database.py  →  SQLite               │
└─────────────────────────────────────────────────────────────┘
```

### 启动后端

```bash
cd api-service
source .venv/bin/activate
python -m app.main
# 或
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 数据初始化

首次运行时需要初始化数据库：

```bash
cd api-service
source .venv/bin/activate
python scripts/init_sequences.py
```

初始化脚本 `init_sequences.py` 会创建：
- 6 个通用测试序列 (Instrument Setup, Measurement, etc.)
- 8 个虚拟路测序列 (Road Test - Step 0 到 Step 7)

### API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/test-sequences` | GET | 获取测试序列列表 |
| `/api/v1/test-sequences/categories` | GET | 获取序列分类 |
| `/api/v1/test-sequences/popular` | GET | 获取热门序列 |
| `/api/v1/test-sequences/{id}` | GET | 获取单个序列详情 |
| `/api/v1/test-plans` | GET/POST | 测试计划 CRUD |
| `/api/v1/health` | GET | 健康检查 |

### 数据库位置

```
api-service/
├── meta3d_ota.db        # SQLite 数据库文件
├── scripts/
│   └── init_sequences.py # 数据初始化脚本
```

---

## 前端 API 客户端配置

### 基础配置

`gui/src/api/client.ts`:
```typescript
import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',  // 通过 Vite proxy 转发到后端
  timeout: 30000,
})

export default client
```

### Vite Proxy 配置

`gui/vite.config.ts`:
```typescript
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

---

## 虚拟路测 8 步流程

后端存储的测试序列按 `category` 字段分类：

| Step | Category | 序列名称 |
|------|----------|----------|
| 0 | Road Test - Step 0 | Configure Digital Twin Environment |
| 1 | Road Test - Step 1 | Initialize OTA Chamber (MPAC) |
| 2 | Road Test - Step 2 | Configure Network |
| 3 | Road Test - Step 3 | Setup Base Stations and Channel Model |
| 4 | Road Test - Step 4 | Configure OTA Mapper |
| 5 | Road Test - Step 5 | Execute Route Test |
| 6 | Road Test - Step 6 | Validate KPIs and Performance Metrics |
| 7 | Road Test - Step 7 | Generate Test Report |

### 查询虚拟路测序列

服务层通过 category 前缀匹配：
```python
# test_plan_service.py
sequences = db.query(TestSequence).filter(
    TestSequence.category.like("Road Test%")
).order_by(TestSequence.category).all()
```

---

## 常见问题排查

### Q: 前端显示数据不正确
1. **确认数据源**：检查 `main.tsx` 中 `setupMockServer()` 是否被注释
2. **检查后端是否运行**：`curl http://localhost:8000/api/v1/health`
3. **检查数据库数据**：
   ```bash
   cd api-service
   sqlite3 meta3d_ota.db "SELECT name, category FROM test_sequences"
   ```

### Q: 数据库缺少某些序列
1. 检查 `init_sequences.py` 是否包含所需序列
2. 如果数据库已有数据，脚本会跳过初始化
3. 删除数据库重新初始化：
   ```bash
   rm meta3d_ota.db
   python scripts/init_sequences.py
   ```

### Q: Mock 和后端数据不同步
- Mock 数据在 `mockDatabase.ts` 中定义
- 后端数据在 `init_sequences.py` 中定义
- 两者需要**手动保持同步**
- 生产环境应只使用后端 API

---

## 开发建议

### 添加新的测试序列

1. **后端 (生产)**:
   - 修改 `api-service/scripts/init_sequences.py`
   - 删除数据库并重新运行初始化脚本

2. **Mock (开发)**:
   - 修改 `gui/src/api/mockDatabase.ts` 中的 `sequenceLibrary`
   - 修改 `gui/src/api/mockServer.ts` 中的路由处理

### 切换模式检查清单

从 Mock 切换到后端：
- [ ] 确保后端服务已启动
- [ ] 确保数据库已初始化
- [ ] 注释 `main.tsx` 中的 `setupMockServer()`

从后端切换到 Mock：
- [ ] 取消注释 `setupMockServer()`
- [ ] 确保 Mock 数据与当前需求一致

---

## 相关文件索引

| 路径 | 用途 |
|------|------|
| `gui/src/main.tsx` | 数据源切换开关 |
| `gui/src/api/mockServer.ts` | Mock API 路由 |
| `gui/src/api/mockDatabase.ts` | Mock 数据存储 |
| `gui/src/api/client.ts` | Axios 客户端配置 |
| `api-service/app/main.py` | FastAPI 入口 |
| `api-service/app/api/test_sequence.py` | 序列 API 端点 |
| `api-service/app/services/test_plan_service.py` | 测试计划服务 |
| `api-service/scripts/init_sequences.py` | 数据初始化脚本 |
| `api-service/meta3d_ota.db` | SQLite 数据库 |

---

**最后更新**: 2025-12-29
**文档所有者**: 开发团队
