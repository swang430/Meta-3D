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

# 确保 Postgres 容器在运行且 host:5432 端口真的绑上 (重启后 Docker 端口转发丢失的自愈)。
# 否则 host 后端连不到 DB → 所有 DB 端点 500 / GUI 满屏"未就绪"。见 scripts/db-up.sh。
bash "$(dirname "$0")/db-up.sh" || { echo "❌ 数据库无法就绪，取消启动。"; exit 1; }

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
else
    # ── DB 在线 → 永远先把 alembic 推到 head ─────────────────
    # 即使 DB 已经初始化过 (DB_STATE=OK)，团队成员拉到含新迁移的代码后
    # 启动时也需要自动同步 schema。alembic 迁移天然幂等；已应用过的会被
    # 跳过，不会重复执行。
    echo "📦 检查并应用 schema 迁移 (alembic upgrade head)..."
    cd api-service
    if .venv/bin/alembic upgrade head; then
        echo "  ✅ schema 已是最新"
    else
        echo "  ❌ schema 迁移失败 — 请检查 alembic 输出"
        cd ..
        exit 1
    fi
    cd ..
    echo ""

    # ── EMPTY DB greeting ─────────────────────────────────────
    # bootstrap 自己幂等，但 EMPTY 时打个欢迎信息帮新用户理解将要发生什么.
    if [ "$DB_STATE" == "EMPTY" ]; then
        echo "==================================================="
        echo "🌟 欢迎使用 Meta-3D OTA 系统！检测到初次运行 🌟"
        echo "==================================================="
        echo "即将通过 bootstrap 落入下列默认数据 (全部幂等, 后续重启不重复):"
        echo " - 4 个默认暗室预设 (Type A/B/C/D)"
        echo " - 7 类仪器目录 + 默认型号 + 默认连接配置"
        echo " - 32 探头 MPAC 三环布局 (链接到默认 Type-C 暗室)"
        echo " - 14 个标准测试序列 (TRP/TIS/MIMO/校准 + VRT 8 步)"
        echo " - 6 个标准报告模板"
        echo " - 25 个 CTIA / 3GPP 测试用例模板 (lab_profile_id=NULL)"
        echo ""
    fi

    # ── Bootstrap (always idempotent) ────────────────────────
    # 跟 alembic 同样思路: 放进 bootstrap 的 seeder 在新版本时需要让所有
    # 现有部署自动 pick up. 所以无论 EMPTY 还是 OK 都跑. 已经 up-to-date
    # 的 seeder 会被自动跳过.
    echo "🌱 检查并应用 bootstrap 默认数据..."
    cd api-service
    if .venv/bin/python -m scripts.bootstrap; then
        echo "  ✅ bootstrap 已是最新"
    else
        echo "  ⚠️ bootstrap 报错 — 详见上方日志, 启动继续"
    fi
    cd ..
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
