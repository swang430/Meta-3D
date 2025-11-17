#!/bin/bash

# 端口清理脚本
# 用于清理开发服务占用的端口

echo "🧹 正在清理端口占用..."

# 定义端口列表
PORTS=(8000 8001 5173)

# 清理每个端口
for PORT in "${PORTS[@]}"; do
    # 查找占用端口的进程
    PID=$(lsof -ti:$PORT 2>/dev/null)

    if [ -n "$PID" ]; then
        echo "  ⚠️  端口 $PORT 被进程 $PID 占用，正在终止..."
        kill -9 $PID 2>/dev/null

        # 再次检查
        sleep 0.5
        if lsof -ti:$PORT >/dev/null 2>&1; then
            echo "  ❌ 端口 $PORT 清理失败"
        else
            echo "  ✅ 端口 $PORT 已清理"
        fi
    else
        echo "  ✓ 端口 $PORT 未被占用"
    fi
done

echo ""
echo "✨ 端口清理完成！"
