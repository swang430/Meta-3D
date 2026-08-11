# 开发环境快速启动指南

## 一键启动所有服务 🚀

现在支持使用一个命令自动启动所有必需的服务！

### 🌟 推荐：安全启动（自动处理端口占用）

```bash
# 基础启动 (ChannelEngine + GUI)
npm run dev:safe

# 完整启动 (所有服务)
npm run dev:safe:all
```

**特性**：
- ✅ 自动检测端口占用 (8000, 8001, 5173)
- ⚠️  如果端口被占用，询问是否清理
- 🚀 自动启动所有服务

### ⚡ 快速启动（不检查端口）

```bash
# 基础启动（ChannelEngine + GUI）
npm run dev

# 完整启动（所有服务）
npm run dev:all
```

这将自动启动：
- **ChannelEngine 服务** (http://localhost:8001) - 探头权重计算
- **API 服务** (http://localhost:8000) - 系统校准后端 (仅 dev:all)
- **前端 GUI** (http://localhost:5173) - React 应用

**注意**：如果端口被占用，启动会失败。需要先运行 `npm run cleanup`。

### 🔧 单独启动特定服务

如果只需要启动某个服务：

```bash
# 只启动 ChannelEngine
npm run dev:channel-engine

# 只启动 API 服务
npm run dev:api

# 只启动前端
npm run dev:gui
```

### 🧹 端口清理与进程管理

#### 清理所有端口

```bash
npm run cleanup
# 或
npm run kill-ports
```

这会检查以下端口，但只自动终止“进程类型在 allowlist 且 cwd 位于本仓”的开发服务：
- 8000 (API Service)
- 8001 (ChannelEngine)
- 5173 (Frontend GUI)

> ⚠️ **Docker、SSH、其他项目和身份不可确认的进程都会被保护**。脚本会保留监听者、
> 返回非零状态并提示只读检查命令；确认是容器后应停止容器，确认是其他应用后应在该
> 应用中正常停止。不要把监听 PID 直接拼进强制终止命令。

#### 只读检查特定端口

```bash
# 只显示 TCP 监听者，不执行终止动作
lsof -nP -iTCP:8000 -sTCP:LISTEN  # API Service
lsof -nP -iTCP:8001 -sTCP:LISTEN  # ChannelEngine
lsof -nP -iTCP:5173 -sTCP:LISTEN  # Frontend

# 实际清理统一走共享 allowlist
npm run cleanup
```

## 初次设置 🔧

### 1. 安装根目录依赖

```bash
npm install
```

### 2. 设置 Python 虚拟环境（首次）

```bash
# 方式1：一键设置所有服务
npm run setup:all

# 方式2：分别设置
npm run setup:channel-engine  # 设置 ChannelEngine 虚拟环境
npm run setup:api             # 设置 API 服务虚拟环境
npm run install:all           # 安装前端依赖
```

### 3. 启动开发环境

```bash
npm run dev
```

## 服务端口

> 端口↔服务以实现为准：`api-service/app/main.py` 用 8000，
> `channel-engine-service/app/main.py` 用 8001。（这张表原先把两者标反了。）

| 服务 | 端口 | 用途 |
|------|------|------|
| API Service | 8000 | 系统校准 API |
| ChannelEngine | 8001 | 探头权重计算 API |
| Frontend GUI | 5173 | React 前端应用 |

## 服务状态检查

### API 服务健康检查
```bash
curl http://localhost:8000/api/v1/health
```

### ChannelEngine 健康检查
```bash
curl http://localhost:8001/api/v1/health
```

### 前端应用
浏览器访问: http://localhost:5173

## API 文档

### API Service Swagger UI
http://localhost:8000/api/docs

### ChannelEngine Swagger UI
http://localhost:8001/api/docs

## 日志输出

所有服务的日志会在同一个终端窗口中显示，使用不同颜色区分：
- 🔵 **蓝色** - ChannelEngine 服务
- 🟡 **黄色** - API 服务（仅 dev:all）
- 🟢 **绿色** - GUI 前端

## 停止服务

在终端中按 `Ctrl+C` 即可同时停止所有服务。

## 故障排查

### 问题：虚拟环境未找到

**错误信息**：
```
channel-engine-service/.venv/bin/python: No such file or directory
```

**解决方案**：
```bash
npm run setup:channel-engine
# 或
npm run setup:all
```

### 问题：端口被占用

**错误信息**：
```
OSError: [Errno 48] Address already in use
```

**解决方案**：
```bash
# 统一使用共享 allowlist；受保护进程不会被终止，脚本会返回非零并给出排查提示
npm run cleanup
```

### 问题：Python 依赖缺失

**解决方案**：
```bash
cd channel-engine-service
.venv/bin/pip install -r requirements.txt
```

## 开发工作流建议

### 推荐：日常开发
```bash
npm run dev  # 启动 ChannelEngine + GUI
```

### 完整测试：端到端校准
```bash
npm run dev:all  # 启动所有服务
```

### 前端开发（不需要后端）
```bash
npm run dev:gui  # 只启动前端，使用 Mock 数据
```

## 项目结构

```
MIMO-First/
├── package.json              ← 根目录配置（新增）
├── channel-engine-service/   ← ChannelEngine 微服务
│   ├── .venv/               ← Python 虚拟环境
│   └── app/
├── api-service/              ← 系统校准 API 服务
│   ├── .venv/               ← Python 虚拟环境
│   └── app/
└── gui/                      ← React 前端
    └── node_modules/
```

## 环境变量

### ChannelEngine (.env)
```env
PORT=8000
DEBUG=true
```

### API Service (.env)
```env
PORT=8001
DATABASE_URL=sqlite:///./meta3d_ota.db
USE_MOCK_INSTRUMENTS=true
```

## 下一步

- 🎯 访问 http://localhost:5173 开始使用 OTA Mapper
- 📖 查看 [CLAUDE.md](./CLAUDE.md) 了解项目详情
- 📚 查看 [docs/](./docs/) 了解系统设计
