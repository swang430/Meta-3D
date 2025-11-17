#!/bin/bash

# 安全启动脚本
# 启动前检查端口，如果被占用则询问是否清理

echo "🚀 准备启动开发环境..."
echo ""

# 定义端口列表和对应服务名称
PORTS=(8000 8001 5173)
SERVICE_NAMES=("ChannelEngine" "API Service" "Frontend GUI")

# 检查端口占用
OCCUPIED_PORTS=()
OCCUPIED_SERVICES=()

for i in "${!PORTS[@]}"; do
    PORT=${PORTS[$i]}
    SERVICE=${SERVICE_NAMES[$i]}

    if lsof -ti:$PORT >/dev/null 2>&1; then
        OCCUPIED_PORTS+=($PORT)
        OCCUPIED_SERVICES+=("$SERVICE")
        PID=$(lsof -ti:$PORT)
        echo "⚠️  端口 $PORT ($SERVICE) 被进程 $PID 占用"
    fi
done

# 如果有端口被占用，询问是否清理
if [ ${#OCCUPIED_PORTS[@]} -gt 0 ]; then
    echo ""
    echo "发现 ${#OCCUPIED_PORTS[@]} 个端口被占用。"
    read -p "是否清理这些端口？(y/n) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在清理端口..."
        for PORT in "${OCCUPIED_PORTS[@]}"; do
            PID=$(lsof -ti:$PORT 2>/dev/null)
            if [ -n "$PID" ]; then
                kill -9 $PID 2>/dev/null
                echo "  ✅ 已清理端口 $PORT"
            fi
        done
        echo ""
        sleep 1
    else
        echo "❌ 取消启动。请手动清理端口后重试。"
        echo "   提示：运行 'npm run cleanup' 清理所有端口"
        exit 1
    fi
fi

echo "✨ 端口检查完成，开始启动服务..."
echo ""

# 根据参数选择启动模式
if [ "$1" == "all" ]; then
    npm run dev:all
else
    npm run dev
fi
