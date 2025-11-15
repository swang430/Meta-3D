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
- 🧪 **测试计划**：支持测试例的创建、保存、预览和执行队列管理
- 📚 **序列库**：可重用的测试步骤构建块
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

### 环境要求

- Node.js >= 18
- npm >= 9

### 安装依赖

```bash
# 进入前端目录
cd gui

# 安装依赖
npm install
```

### 开发模式

```bash
cd gui
npm run dev
```

访问 http://localhost:5173 查看应用（默认端口）

### 生产构建

```bash
cd gui
npm run build
```

构建产物位于 `gui/dist/` 目录

### 预览生产构建

```bash
cd gui
npm run preview
```

## 📁 项目结构

```
Meta-3D/
├── gui/                    # 前端应用
│   ├── src/
│   │   ├── api/           # API 层（client, service, mock）
│   │   ├── components/    # React 组件
│   │   ├── services/      # 业务逻辑层
│   │   ├── types/         # TypeScript 类型定义
│   │   ├── App.tsx        # 主应用组件
│   │   └── main.tsx       # 入口文件
│   ├── package.json
│   └── vite.config.ts
│
├── api/                    # API 规范
│   └── openapi.yaml       # OpenAPI 3.0 定义
│
├── AGENTS.md              # 详细的系统架构文档
├── CLAUDE.md              # Claude Code 工作指南
├── Hardware.md            # 硬件规格说明
├── MPAC.md                # MPAC 技术文档
└── README.md              # 本文件
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

当前应用完全基于 Mock 数据运行，无需后端即可开发：

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
序列库 (Sequence Library)
    ↓ 组合
测试例 (Test Cases)
    ↓ 收集
测试计划 (Test Plans)
    ↓ 执行
测试报告 (Test Reports)
```

## 🔬 核心硬件组件

- **探头阵列**：32 个双极化天线，分布在三个环层
- **信道仿真器**：实时生成多径衰落和时延扩展
- **基站仿真器**：模拟 5G NR/LTE 基站信号
- **被测设备（DUT）**：全尺寸车辆及其无线通信系统

## 📚 文档

- [CLAUDE.md](CLAUDE.md) - Claude Code 使用指南
- [AGENTS.md](AGENTS.md) - 完整的系统架构和设计文档（35K+ tokens）
- [Hardware.md](Hardware.md) - 硬件规格说明
- [MPAC.md](MPAC.md) - MPAC 暗室技术细节

## 🚧 当前状态

项目处于**早期开发阶段**：

- ✅ 前端架构已建立
- ✅ API 规范已定义
- ✅ Mock 数据开发环境就绪
- ✅ 测试计划和测试例管理功能基本完成
- 🚧 正在从自定义 CSS 迁移到 Mantine UI（Phase 1）
- ⏳ 硬件控制层为桩代码，待后端开发
- ⏳ 探头 3D 可视化待增强（计划集成 D3.js/Three.js）

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
