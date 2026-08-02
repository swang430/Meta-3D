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

这将强制终止占用以下端口的进程：
- 8000 (API Service)
- 8001 (ChannelEngine)
- 5173 (Frontend GUI)

> ⚠️ **端口若是 Docker 容器发布的，脚本会跳过而不是 kill**。原因：在 macOS host
> 一侧监听容器端口的不是容器，而是 Docker Desktop 的转发进程
> `com.docker.backend` —— 也就是 Docker 引擎本体，`kill -9` 打上去整个 daemon
> 当场死亡。这时按脚本提示跑 `docker stop <容器名>` 腾端口。

#### 手动清理特定端口

```bash
# ⚠️ 手敲 kill 前先确认这个端口不是容器发布的, 否则杀掉的是容器转发进程
#    (macOS: com.docker.backend / Linux: docker-proxy) = 整个 Docker daemon:
#    docker ps --filter publish=8000 --format '{{.Names}}'   # 有输出 = 不要 kill
# macOS/Linux
# -t -iTCP -sTCP:LISTEN: 只杀**监听者**。裸 `lsof -ti:8000` 会连"连到"该端口的
# 客户端 (浏览器 tab) 和同号 UDP 一起选中, 那些进程跟端口占用毫无关系。
lsof -t -iTCP:8000 -sTCP:LISTEN | xargs kill -9  # 清理 API Service 端口
lsof -t -iTCP:8001 -sTCP:LISTEN | xargs kill -9  # 清理 ChannelEngine 端口
lsof -t -iTCP:5173 -sTCP:LISTEN | xargs kill -9  # 清理 Frontend 端口
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
# ⚠️ 先确认该端口不是 Docker 容器发布的 —— 有输出就**别** kill, 那个 PID 是容器
#    转发进程 (com.docker.backend / docker-proxy), 杀它 = 杀整个 daemon;
#    改用 docker stop <容器名>
docker ps --filter publish=8000 --format '{{.Names}}'

# 查找并终止占用端口的进程 (-t -iTCP -sTCP:LISTEN = 只要监听者)
lsof -t -iTCP:8000 -sTCP:LISTEN | xargs kill -9  # API Service
lsof -t -iTCP:8001 -sTCP:LISTEN | xargs kill -9  # ChannelEngine
lsof -t -iTCP:5173 -sTCP:LISTEN | xargs kill -9  # Frontend
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
