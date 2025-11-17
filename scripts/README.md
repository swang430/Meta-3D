# 开发脚本说明

本目录包含开发环境管理脚本。

## 脚本列表

### 1. cleanup-ports.sh

**用途**: 清理开发服务占用的端口

**使用方法**:
```bash
npm run cleanup
# 或直接运行
bash scripts/cleanup-ports.sh
```

**功能**:
- 自动检测端口 8000, 8001, 5173 是否被占用
- 强制终止占用端口的进程
- 显示清理结果

**适用场景**:
- 服务启动失败，提示"Address already in use"
- IDE 崩溃或异常退出后，进程未正常关闭
- 需要重启所有服务

### 2. safe-start.sh

**用途**: 安全启动开发环境，自动处理端口占用

**使用方法**:
```bash
# 启动基础服务 (ChannelEngine + GUI)
npm run dev:safe

# 启动所有服务 (ChannelEngine + API + GUI)
npm run dev:safe:all
```

**功能**:
1. 启动前检查端口占用情况
2. 如果端口被占用，询问用户是否清理
3. 用户确认后自动清理端口
4. 启动相应的服务

**适用场景**:
- 日常开发启动（推荐使用）
- 不确定端口是否被占用时
- 需要可靠启动的场景

## 端口分配

| 端口 | 服务 | 用途 |
|------|------|------|
| 8000 | ChannelEngine | 探头权重计算 API |
| 8001 | API Service | 系统校准 API |
| 5173 | Frontend GUI | React 前端应用 |

## 故障排查

### 问题：脚本没有执行权限

**错误信息**:
```
Permission denied: scripts/cleanup-ports.sh
```

**解决方案**:
```bash
chmod +x scripts/cleanup-ports.sh
chmod +x scripts/safe-start.sh
```

### 问题：lsof 命令未找到

**错误信息**:
```
lsof: command not found
```

**解决方案**:
- macOS: `lsof` 是系统内置命令，应该已经存在
- Linux: `sudo apt-get install lsof` (Debian/Ubuntu) 或 `sudo yum install lsof` (CentOS/RHEL)

### 问题：无法终止进程

**错误信息**:
```
Operation not permitted
```

**可能原因**:
- 进程属于其他用户或系统进程
- 需要管理员权限

**解决方案**:
```bash
# 查看进程信息
lsof -i:8000

# 使用 sudo 强制终止
sudo kill -9 <PID>
```

## 开发工作流建议

### 日常开发流程

```bash
# 1. 启动开发环境（推荐使用安全启动）
npm run dev:safe

# 2. 开发工作...

# 3. 停止服务（Ctrl+C）

# 4. 如果需要重启
npm run dev:safe  # 会自动检查和清理端口
```

### 如果遇到端口占用

```bash
# 方法1：使用安全启动（自动处理）
npm run dev:safe

# 方法2：手动清理后启动
npm run cleanup
npm run dev

# 方法3：直接清理特定端口
lsof -ti:8000 | xargs kill -9
```

### IDE 崩溃后恢复

```bash
# IDE 崩溃可能导致进程未正常关闭
# 运行清理脚本后重新启动
npm run cleanup
npm run dev:safe
```

## 进程管理最佳实践

1. **优先使用安全启动**: `npm run dev:safe` 可以避免大部分端口占用问题

2. **正常关闭服务**: 使用 `Ctrl+C` 而不是直接关闭终端，确保进程正常退出

3. **定期清理**: 如果经常遇到端口占用问题，可以在启动前习惯性运行 `npm run cleanup`

4. **监控端口**: 如果不确定端口状态，可以运行：
   ```bash
   lsof -i:8000  # 查看 8000 端口占用情况
   lsof -i:8001  # 查看 8001 端口占用情况
   lsof -i:5173  # 查看 5173 端口占用情况
   ```

5. **避免冲突**: 不要在不同终端窗口重复启动同一服务

## 脚本维护

### 添加新端口

如果需要添加新的服务端口，需要修改：

1. **cleanup-ports.sh**:
   ```bash
   PORTS=(8000 8001 5173 <新端口>)
   ```

2. **safe-start.sh**:
   ```bash
   PORT_SERVICE[<新端口>]="<服务名称>"
   ```

3. **文档**: 更新 DEV-QUICKSTART.md 和本文档

### 修改端口检查逻辑

如果需要修改端口检查或清理逻辑，编辑对应脚本文件即可。脚本使用 bash 编写，逻辑简单易懂。

## 相关文档

- [DEV-QUICKSTART.md](../DEV-QUICKSTART.md) - 开发环境快速启动指南
- [CLAUDE.md](../CLAUDE.md) - 项目总体说明
