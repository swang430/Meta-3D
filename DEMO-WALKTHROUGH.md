# 自动启动与端口管理演示

本文档演示新增的自动启动和端口管理功能。

## 🎬 演示场景

### 场景 1：正常启动（无端口占用）

```bash
$ npm run dev:safe
```

**输出**：
```
🚀 准备启动开发环境...

✨ 端口检查完成，开始启动服务...

[ChannelEngine] INFO:     Started server process [12345]
[ChannelEngine] INFO:     Waiting for application startup.
[ChannelEngine] INFO:     Application startup complete.
[ChannelEngine] INFO:     Uvicorn running on http://0.0.0.0:8000
[GUI]           VITE v5.0.0  ready in 1234 ms
[GUI]           ➜  Local:   http://localhost:5173/
[GUI]           ➜  Network: http://192.168.1.100:5173/
```

**结果**：✅ 两个服务成功启动

---

### 场景 2：端口被占用（自动检测并清理）

假设端口 8000 被其他进程占用：

```bash
$ npm run dev:safe
```

**输出**：
```
🚀 准备启动开发环境...

⚠️  端口 8000 (ChannelEngine) 被进程 54321 占用

发现 1 个端口被占用。
是否清理这些端口？(y/n) y
正在清理端口...
  ✅ 已清理端口 8000

✨ 端口检查完成，开始启动服务...

[ChannelEngine] INFO:     Started server process [67890]
[ChannelEngine] INFO:     Uvicorn running on http://0.0.0.0:8000
[GUI]           VITE ready in 1000 ms
[GUI]           ➜  Local:   http://localhost:5173/
```

**结果**：✅ 自动清理端口后成功启动

---

### 场景 3：用户拒绝清理端口

```bash
$ npm run dev:safe
```

**输出**：
```
🚀 准备启动开发环境...

⚠️  端口 8000 (ChannelEngine) 被进程 54321 占用
⚠️  端口 5173 (Frontend GUI) 被进程 54322 占用

发现 2 个端口被占用。
是否清理这些端口？(y/n) n
❌ 取消启动。请手动清理端口后重试。
   提示：运行 'npm run cleanup' 清理所有端口
```

**结果**：❌ 启动被取消，需要手动处理

---

### 场景 4：手动清理端口

```bash
$ npm run cleanup
```

**输出**：
```
🧹 正在清理端口占用...
  ⚠️  端口 8000 被进程 12345 占用，正在终止...
  ✅ 端口 8000 已清理
  ⚠️  端口 8001 被进程 12346 占用，正在终止...
  ✅ 端口 8001 已清理
  ⚠️  端口 5173 被进程 12347 占用，正在终止...
  ✅ 端口 5173 已清理

✨ 端口清理完成！
```

**结果**：✅ 所有端口已清理

---

### 场景 5：IDE 崩溃后恢复

IDE 崩溃后，服务进程可能仍在运行，占用端口。

```bash
$ npm run dev
```

**错误**：
```
[ChannelEngine] ERROR: [Errno 48] error while attempting to bind on address ('0.0.0.0', 8000): address already in use
```

**解决方案**：

```bash
# 方法 1：使用安全启动（推荐）
$ npm run dev:safe
# 会自动检测并询问是否清理

# 方法 2：手动清理
$ npm run cleanup
$ npm run dev
```

---

## 📊 完整命令对比

| 命令 | 端口检查 | 自动清理 | 用户确认 | 适用场景 |
|------|---------|---------|---------|----------|
| `npm run dev` | ❌ | ❌ | ❌ | 确定端口空闲时 |
| `npm run dev:safe` | ✅ | ✅ | ✅ | **日常使用（推荐）** |
| `npm run cleanup` | ✅ | ✅ | ❌ | 强制清理所有端口 |
| `npm run dev:all` | ❌ | ❌ | ❌ | 启动所有服务（快速） |
| `npm run dev:safe:all` | ✅ | ✅ | ✅ | **启动所有服务（安全）** |

---

## 🔍 实时监控端口状态

### 查看单个端口

```bash
# 查看 ChannelEngine 端口 (8000)
$ lsof -i:8000

# 示例输出：
COMMAND   PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
Python  12345 Simon   3u  IPv4 0x1234  0t0  TCP *:8000 (LISTEN)
```

### 查看所有服务端口

```bash
$ lsof -i:8000 -i:8001 -i:5173

# 或使用我们的清理脚本（仅查看，不清理）
$ bash scripts/cleanup-ports.sh
```

---

## ⚙️ 高级用法

### 启动特定服务组合

```bash
# 只启动后端服务
$ concurrently -n "ChannelEngine,API" -c "blue,yellow" \
  "npm run dev:channel-engine" "npm run dev:api"

# 只启动 ChannelEngine + GUI
$ npm run dev:safe

# 启动所有服务（包括 API）
$ npm run dev:safe:all
```

### 自定义端口清理

```bash
# 只清理特定端口
$ lsof -ti:8000 | xargs kill -9  # ChannelEngine
$ lsof -ti:8001 | xargs kill -9  # API Service
$ lsof -ti:5173 | xargs kill -9  # Frontend

# 清理所有开发端口
$ npm run cleanup
```

### 后台运行服务

```bash
# 启动服务并放到后台（不推荐，难以管理）
$ npm run dev > /dev/null 2>&1 &

# 查看后台进程
$ jobs

# 停止后台进程
$ npm run cleanup
```

---

## 🎯 实际使用示例

### 示例 1：开始一天的开发工作

```bash
# 早上打开电脑，启动开发环境
$ cd /path/to/MIMO-First
$ npm run dev:safe

# 输出：
🚀 准备启动开发环境...
✨ 端口检查完成，开始启动服务...
[ChannelEngine] 服务启动成功 ✅
[GUI] 前端启动成功 ✅

# 开始开发...
```

### 示例 2：IDE 崩溃恢复

```bash
# IDE 崩溃了，重新打开
$ npm run dev
[ChannelEngine] ERROR: address already in use ❌

# 使用安全启动自动处理
$ npm run dev:safe
⚠️  端口 8000 被进程 54321 占用
是否清理？(y/n) y
✅ 已清理，重新启动成功
```

### 示例 3：测试端到端校准

```bash
# 需要测试完整的系统校准功能
$ npm run dev:safe:all

# 输出：启动3个服务
[ChannelEngine] http://localhost:8000 ✅
[API] http://localhost:8001 ✅
[GUI] http://localhost:5173 ✅

# 在浏览器中访问：http://localhost:5173
# 测试 OTA Mapper 和 系统校准功能
```

### 示例 4：结束一天的工作

```bash
# 在终端中按 Ctrl+C 停止所有服务
^C
[ChannelEngine] 服务已关闭
[GUI] 前端已关闭

# 如果担心有残留进程
$ npm run cleanup
✨ 端口清理完成！

# 关闭电脑
```

---

## 📝 故障排查

### 问题：安全启动检测不到端口占用

**可能原因**：`lsof` 命令权限不足或不存在

**解决方案**：
```bash
# 检查 lsof 是否可用
$ which lsof
/usr/sbin/lsof

# 手动测试
$ lsof -i:8000
```

### 问题：清理端口后仍然无法启动

**可能原因**：进程需要时间完全释放端口

**解决方案**：
```bash
# 等待几秒后重试
$ npm run cleanup
$ sleep 2
$ npm run dev:safe
```

### 问题：脚本在 Windows 上无法运行

**原因**：Bash 脚本不兼容 Windows

**解决方案**：
```bash
# 使用 Git Bash 或 WSL
$ bash scripts/safe-start.sh

# 或使用基础启动命令
$ npm run dev
```

---

## 🎓 最佳实践

1. **日常开发**：优先使用 `npm run dev:safe`
2. **快速测试**：如果确定端口空闲，使用 `npm run dev`
3. **端到端测试**：使用 `npm run dev:safe:all`
4. **遇到问题**：先运行 `npm run cleanup` 清理端口
5. **正常退出**：使用 `Ctrl+C` 而不是直接关闭终端

---

## 📚 相关文档

- [DEV-QUICKSTART.md](./DEV-QUICKSTART.md) - 快速启动指南
- [scripts/README.md](./scripts/README.md) - 脚本详细说明
- [CLAUDE.md](./CLAUDE.md) - 项目总体介绍
