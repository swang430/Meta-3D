# Meta-3D MIMO OTA 测试系统

面向全尺寸汽车的 3D MIMO OTA 测试暗室控制软件

## 📋 项目简介

Meta-3D 是一个专为汽车无线通信系统设计的 MIMO OTA（Over-The-Air）测试平台。系统采用多探头暗室（Multi-Probe Anechoic Chamber, MPAC）技术，能够在可控的电磁环境中对全尺寸车辆的 C-V2X、5G 等无线通信系统进行精确测试。

### 核心理念：软件定义静区

本系统的独特之处在于采用**"软件定义静区"（Software-Defined Quiet Zone）**架构：

- 测试区域的质量由**软件算法和校准**决定，而非暗室的物理尺寸
- 通过精确的波场合成（Wavefield Synthesis）在有限空间内创造等效的远场测试环境
- 使用 32 个双极化探头天线配合信道仿真器实时计算复杂激励信号
- 系统性能取决于算法精度和校准质量，而非土木工程规模

## ✨ 主要功能

- 🔧 **仪器管理**：信道仿真器、基站仿真器、信号分析仪的统一控制
- 📊 **探头配置**：32 探头阵列的可视化配置和参数管理
- 🧪 **测试用例**：配置仪表参数、保存、直接执行（ARCH-1 起以 TestCase 为根）
  ⚠️ GUI 目前**没有新建用例的入口** —— 用例来自 bootstrap 种子，可改可执行不可新建（backlog）
- 🕘 **执行历史**：每次执行落一条记录，历史与报告同源
- 📈 **实时监控**：系统状态、告警和关键指标的实时展示
- 💾 **测试例管理**：测试配置的持久化、另存和删除
- 🎨 **专业 UI**：基于 Mantine 的现代化界面设计（支持暗黑模式）

## 🛠️ 技术栈

### 前端
- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **UI 组件库**: Mantine UI (@mantine/core, @mantine/hooks, @mantine/notifications)
- **状态管理**: TanStack Query (React Query)
- **HTTP 客户端**: Axios (配合 Mock Adapter)
- **代码规范**: ESLint + TypeScript ESLint

### API
- **规范**: OpenAPI 3.0
- **架构**: RESTful API
- **类型生成**: openapi-typescript

## 🚀 快速开始

以下是 macOS / Linux 的本地开发入口，不是生产部署方案。命令从已经克隆的 `MIMO-First` 仓库根目录开始，按顺序在同一个终端执行；括号中的切换目录只影响该条命令。

### 环境要求

- Node.js 20 系列中的 20.19.0 及以上版本，或 Node.js 22.12.0 及以上版本（`^20.19.0 || >=22.12.0`）；npm >= 9
- Python >= 3.11
- 已运行的 PostgreSQL，以及可用于本项目的数据库和账号
- 能访问 `ChannelEgine` 仓库（仓库名称中的拼写如此）

### 安装依赖

```bash
# 当前目录：MIMO-First 根目录
# 将信道引擎克隆到与 MIMO-First 同级的目录；已有克隆时跳过 git clone
git clone https://github.com/swang430/ChannelEgine.git ../ChannelEgine
export CHANNEL_ENGINE_PATH="$(cd ../ChannelEgine && pwd)"

# 根目录启动工具和前端分别安装锁定的依赖
npm ci
(cd gui && npm ci)

# API 服务使用自己的 Python 环境
python3 -m venv api-service/.venv
api-service/.venv/bin/python -m pip install -r api-service/requirements.txt

# 信道引擎服务及外部引擎的依赖安装到同一个服务环境
python3 -m venv channel-engine-service/.venv
channel-engine-service/.venv/bin/python -m pip install \
  -r channel-engine-service/requirements.txt \
  -r "$CHANNEL_ENGINE_PATH/requirements.txt"
```

`CHANNEL_ENGINE_PATH` 必须是 `ChannelEgine` 克隆目录的绝对路径。服务通过此路径导入外部引擎源码，以上步骤不要求可编辑安装。由根目录启动的子进程会继承已导出的环境变量；换终端后需重新导出。

### 配置数据库并初始化

如果尚无配置文件，在根目录执行：

```bash
cp api-service/.env.example api-service/.env
```

已有 `.env` 时直接编辑，不要覆盖。按示例将 `DATABASE_URL` 配置为实际可连接的 PostgreSQL 数据库，使用 `postgresql+psycopg2://` 驱动格式，并填写实际账号、密码、主机、端口和数据库名。数据库与账号需提前准备好。

```bash
# 开发期间使用模拟仪器；此变量也会传给后续启动的 API 服务
export USE_MOCK_INSTRUMENTS=true

# 先迁移表结构，再初始化默认数据；bootstrap 本身不执行迁移
(cd api-service && .venv/bin/python -m alembic upgrade head && \
  .venv/bin/python -m scripts.bootstrap)
```

### 启动开发服务

在已导出上述变量的同一终端、仓库根目录执行：

```bash
npm run dev:all
```

该命令启动 API、信道引擎服务和前端。请确保标准端口未被其他程序占用：

| 服务 | 地址 | 接口文档 |
|---|---|---|
| 前端 | http://localhost:5173 | — |
| API 服务 | http://localhost:8000 | http://localhost:8000/api/docs |
| 信道引擎服务 | http://localhost:8001 | http://localhost:8001/api/docs |

也可在分别导出 `CHANNEL_ENGINE_PATH` 和 `USE_MOCK_INSTRUMENTS=true` 的三个终端中，从根目录各运行一条命令：

```bash
# 终端 1：API 服务
(cd api-service && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)
# 终端 2：信道引擎服务
(cd channel-engine-service && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001)
# 终端 3：前端
npm run dev --prefix gui
```

模拟仪器开关不会替代数据库或信道引擎服务，模拟结果也不代表真实硬件验收。

### 生成接口描述和构建前端

以下命令均从根目录执行：

```bash
npm run generate:schema
npm run build --prefix gui
```

`generate:schema` 使用 `channel-engine-service/.venv/bin/python` 运行 `scripts/export_channel_engine_schema.py`，输出 `gui/src/types/channel-engine-schema.json`。该导出脚本只读取路由定义，不启动服务或运行引擎计算，不能用来验证真实引擎计算。

前端构建产物位于 `gui/dist/`。生成这些文件不等于完成生产部署。

## 📁 项目结构

```
MIMO-First/
├── gui/                        # 前端应用 (React + TypeScript + Vite)
│   ├── src/
│   │   ├── api/               # API 客户端
│   │   ├── features/          # 功能模块 (TestManagement, Reports, etc.)
│   │   ├── components/        # 共享组件
│   │   └── types/             # TypeScript 类型
│   └── package.json
│
├── api-service/               # 后端 API 服务 (FastAPI + SQLAlchemy)
│   ├── app/
│   │   ├── api/              # REST API 端点
│   │   ├── models/           # 数据库模型
│   │   ├── schemas/          # Pydantic schemas
│   │   └── services/         # 业务逻辑
│   └── requirements.txt
│
├── channel-engine-service/    # 信道引擎服务 (Python)
│
├── docs/                      # 文档
│   ├── design/               # 架构设计文档
│   ├── guides/               # 开发指南
│   └── archive/              # 归档文档
│
├── AGENTS.md                  # 系统架构参考文档
├── CLAUDE.md                  # Claude Code 工作指南
├── Hardware.md                # 硬件规格说明
└── README.md                  # 本文件
```

## 📖 开发指南

### 架构层次

前端采用分层架构：

```
┌─────────────────────────────┐
│      组件层 (Components)     │  ← UI 组件、页面
├─────────────────────────────┤
│      服务层 (Services)       │  ← 业务逻辑、HAL
├─────────────────────────────┤
│        API 层 (API)         │  ← HTTP 客户端、Mock
└─────────────────────────────┘
```

### Mock 数据开发

当前前端入口未启用 Mock 服务器；上述开发入口连接 API 和信道引擎服务。`USE_MOCK_INSTRUMENTS=true` 控制后端使用模拟仪器，不会启用前端 Mock 服务器。前端保留的 Mock 文件位于：

- Mock 服务器配置：`gui/src/api/mockServer.ts`
- Mock 数据存储：`gui/src/api/mockDatabase.ts`

### 添加新 API 端点

1. 在 `api/openapi.yaml` 中定义端点和 schema
2. 生成 TypeScript 类型：
   ```bash
   cd gui
   npm run openapi:generate
   ```
3. 在 `gui/src/api/service.ts` 中添加服务函数
4. 在 `gui/src/api/mockServer.ts` 中添加 mock 处理器
5. 在 `gui/src/api/mockDatabase.ts` 中更新 mock 数据

### 代码规范

```bash
cd gui
npm run lint        # 运行 ESLint 检查
```

### UI 开发规范

- 优先使用 **Mantine 组件**而非自定义 CSS
- 封装业务组件以保持一致性
- 遵循 8px 基准网格系统
- 支持浅色/暗黑模式

## 🧪 测试层级

系统支持三级测试组织结构：

```
测试用例 (Test Case)           ← 单一真值源, 自带仪表参数与相位描述符
    ↓ 执行
执行记录 (Test Execution)      ← 每次执行一行, 状态/结果/耗时都在这
    ↓ 汇总
测试报告 (Test Report)
```

> ⚠️ 原来中间还有「序列库 → 测试例 → 测试计划」三层，**计划链与序列库已随 ARCH-1 S4（2026-07）整体拆除**，层级拍平成上面两层。

## 🔬 核心硬件组件

- **探头阵列**：32 个双极化天线，分布在三个环层
- **信道仿真器**：实时生成多径衰落和时延扩展
- **基站仿真器**：模拟 5G NR/LTE 基站信号
- **被测设备（DUT）**：全尺寸车辆及其无线通信系统

## 📚 文档

**根目录**:
- [CLAUDE.md](CLAUDE.md) - Claude Code 工作指南
- [AGENTS.md](AGENTS.md) - 系统架构参考文档

**docs/design/** - 架构设计:
- [SYSTEM-INTEGRATION-DESIGN.md](docs/design/SYSTEM-INTEGRATION-DESIGN.md) - 系统集成设计
- [TestManagement-Unified-Architecture.md](docs/design/TestManagement-Unified-Architecture.md) - 测试管理架构
- [VirtualRoadTest-Architecture.md](docs/design/VirtualRoadTest-Architecture.md) - 虚拟路测架构
- [HARDWARE-SYNC-ARCHITECTURE.md](docs/design/HARDWARE-SYNC-ARCHITECTURE.md) - 硬件同步架构 (L0-L3)

**docs/guides/** - 开发指南:
- [DEV-QUICKSTART.md](docs/guides/DEV-QUICKSTART.md) - 开发快速入门
- [API-DESIGN-GUIDE.md](docs/guides/API-DESIGN-GUIDE.md) - API 设计规范
- [DATA-MODEL-GUIDE.md](docs/guides/DATA-MODEL-GUIDE.md) - 数据模型指南

**硬件规格**:
- [Hardware.md](Hardware.md) - 硬件总览
- [MPAC.md](MPAC.md) - MPAC 暗室技术细节

## 🚧 当前状态

项目处于**活跃开发阶段** (2025-12)：

**已完成功能**:
- ✅ 前后端架构完整 (React + FastAPI + SQLite)
- ✅ 测试用例管理：编辑、配置仪表参数、直接执行（**新建入口待补**，见 backlog）
- ⚠️ ~~测试计划管理 / 步骤编排 / 执行队列 / 序列库~~ —— 已随 ARCH-1 S4 拆除
- ✅ 虚拟路测：场景库、ChannelEngine 集成
- ✅ 报告系统：PDF 生成、模板管理
- ✅ 执行历史记录和统计

**进行中**:
- 🔄 GUI 功能完善 (Phase 4 - 70%)
- 🔄 硬件抽象层设计完成，驱动待实现

**待实现**:
- ⏳ 硬件驱动集成 (信道仿真器、基站仿真器)
- ⏳ 用户认证系统
- ⏳ Docker 部署

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发流程

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: add some amazing feature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### Commit 规范

使用语义化提交信息：

- `feat:` 新功能
- `fix:` 问题修复
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具链更新

## 📄 许可证

[待添加许可证信息]

## 👥 作者

Simon - 乾径团队

## 🔗 相关资源

- [3GPP TS 38.521-4](https://www.3gpp.org/DynaReport/38521-4.htm) - 5G MIMO OTA 测试规范
- [CTIA Test Plan](https://api.ctia.org/test-plans) - 行业标准测试计划
- [Mantine UI](https://mantine.dev/) - 组件库文档
- [TanStack Query](https://tanstack.com/query) - 数据获取库文档
