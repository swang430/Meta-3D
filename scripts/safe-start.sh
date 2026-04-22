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

echo "✨ 端口检查完成，开始检查数据库状态..."
echo ""

cd api-service
DB_STATE=$(.venv/bin/python scripts/check_db_state.py)
cd ..

if [ "$DB_STATE" == "ERROR" ]; then
    echo "⚠️ 数据库连接失败！"
    echo "请检查 PostgreSQL 服务是否已启动，例如执行: docker-compose up -d postgres"
    echo "或检查 api-service/.env 中的 DATABASE_URL 配置是否正确。"
    read -p "是否强行继续启动服务？(y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 取消启动。"
        exit 1
    fi
elif [ "$DB_STATE" == "EMPTY" ]; then
    echo "==================================================="
    echo "🌟 欢迎使用 Meta-3D OTA 系统！检测到初次运行 🌟"
    echo "==================================================="
    echo "系统检测到您的数据库为空。为了保证测试系统正常运行，我们需要初始化以下内容："
    echo " - 自动创建所有关系型数据表结构"
    echo " - 注入仪器设备型号名录 (Seed Instruments)"
    echo " - 建立标准 32 探头暗室 3D 布局 (Init Probes)"
    echo " - 加载基础测试报告模板 (Report Templates)"
    echo " - 配置标准测试及路测序列 (Init Sequences)"
    echo ""
    read -p "是否现在自动为您完成全自动初始化？(Y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        echo "⏳ 正在初始化表结构与种子数据..."
        cd api-service
        
        # 1. 创建表结构
        .venv/bin/python -c "from app.db.database import init_db; init_db()"
        echo "  ✅ 表结构创建成功"
        
        # 2. 注入种子数据
        .venv/bin/python scripts/seed_instruments.py > /dev/null
        echo "  ✅ 仪器名录加载成功"
        
        .venv/bin/python scripts/init_probes.py > /dev/null
        echo "  ✅ 暗室探头布局初始化成功"
        
        .venv/bin/python scripts/init_report_templates.py > /dev/null
        echo "  ✅ 报告模板初始化成功"
        
        .venv/bin/python scripts/init_sequences.py > /dev/null
        echo "  ✅ 标准测试序列初始化成功"
        
        cd ..
        echo ""
        echo "🎉 数据库初始化完美完成！"
    else
        echo "⚠️ 跳过数据库初始化，系统可能无法正常运行所有功能。"
    fi
    echo ""
fi

echo "🚀 开始启动服务..."
echo ""

# 根据参数选择启动模式
if [ "$1" == "all" ]; then
    npm run dev:all
else
    npm run dev
fi
