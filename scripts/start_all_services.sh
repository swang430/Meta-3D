#!/bin/bash

# MIMO-First 完整系统启动脚本
# 启动所有必要的服务：API、GUI、ChannelEngine

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
mkdir -p "${LOG_DIR}"

echo "================================================"
echo "🚀 MIMO-First 系统启动"
echo "================================================"
echo "项目目录: ${PROJECT_ROOT}"
echo "日志目录: ${LOG_DIR}"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函数：启动服务
start_service() {
    local name=$1
    local dir=$2
    local cmd=$3
    local port=$4
    local log_file="${LOG_DIR}/${name}.log"

    echo -e "${BLUE}📡 启动 ${name} (端口 ${port})...${NC}"

    cd "${dir}"
    eval "${cmd}" > "${log_file}" 2>&1 &
    local pid=$!

    echo $pid > "${LOG_DIR}/${name}.pid"

    # 等待服务启动
    sleep 3

    if curl -s "http://localhost:${port}" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ ${name} 启动成功 (PID: ${pid})${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  ${name} 启动中... (检查日志: ${log_file})${NC}"
        return 0
    fi
}

# 函数：检查端口是否被占用
check_port() {
    local port=$1
    if lsof -Pi :${port} -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # 端口被占用
    else
        return 1  # 端口空闲
    fi
}

# 等待 API 服务的 HAL 完成驱动加载,最长 ${2:-30} 秒。
# HAL init 在 lifespan startup 中跑完之后会输出一行 "N/M categories loaded · X failed · Y skipped"
# 作为完成标志。
wait_for_hal_readiness() {
    local log_file=$1
    local timeout=${2:-30}
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if grep -q "categories loaded ·" "${log_file}" 2>/dev/null; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

# 把 HAL 启动汇报表 (✓/✗/○ 哪些 instrument loaded 了) 从 API.log 抽出来打到终端,
# 不要让用户在 tail -f 一堆 mixed log 里自己找。
# 抽取范围: 从 "HAL READINESS REPORT" 表头到 "categories loaded ·" tally,
# sed 把 logging 前缀 "时间戳 │ INFO │ … │ [HAL] " 削掉,只留报告本体。
print_hal_readiness() {
    local log_file=$1
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}🔌 HAL Readiness (硬件驱动加载结果):${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    awk '/HAL READINESS REPORT/,/categories loaded ·/' "${log_file}" \
      | sed -E 's/.*\[HAL\] //'
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# 检查依赖端口
echo "检查依赖端口..."
PORTS_OK=true

for port in 8000 8001 5173; do
    if check_port $port; then
        echo -e "${YELLOW}⚠️  端口 ${port} 已被占用${NC}"
        PORTS_OK=false
    fi
done

if [ "$PORTS_OK" = false ]; then
    echo ""
    read -p "继续启动？某些服务可能无法启动 (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "================================================"
echo "启动所有服务..."
echo "================================================"
echo ""

# 1. 启动 ChannelEngine (Python)
if [ -d "${PROJECT_ROOT}/channel-engine-service" ]; then
    echo -e "${BLUE}1️⃣  ChannelEngine 微服务${NC}"
    VENV_ACTIVATE="${PROJECT_ROOT}/api-service/.venv/bin/activate"
    if [ -f "${VENV_ACTIVATE}" ]; then
        start_service "ChannelEngine" \
            "${PROJECT_ROOT}/channel-engine-service" \
            "source ${VENV_ACTIVATE} && python3 -m app.main" \
            8001
    else
        start_service "ChannelEngine" \
            "${PROJECT_ROOT}/channel-engine-service" \
            "python3 -m app.main" \
            8001
    fi
    echo ""
fi

# 2. 启动 API 服务 (Python FastAPI)
if [ -d "${PROJECT_ROOT}/api-service" ]; then
    echo -e "${BLUE}2️⃣  Road Test API${NC}"
    VENV_ACTIVATE="${PROJECT_ROOT}/api-service/.venv/bin/activate"
    if [ -f "${VENV_ACTIVATE}" ]; then
        start_service "API" \
            "${PROJECT_ROOT}/api-service" \
            "source ${VENV_ACTIVATE} && python3 -m app.main" \
            8000
    else
        start_service "API" \
            "${PROJECT_ROOT}/api-service" \
            "python3 -m app.main" \
            8000
    fi

    # HAL init runs inside FastAPI lifespan startup. Block here until it
    # finishes (or 30s) so the readiness table prints in a stable place
    # — before GUI logs start flowing past in tail -f.
    if wait_for_hal_readiness "${LOG_DIR}/API.log" 30; then
        print_hal_readiness "${LOG_DIR}/API.log"
    else
        echo -e "${YELLOW}⚠️  HAL readiness report not seen within 30s — check ${LOG_DIR}/API.log${NC}"
        echo ""
    fi
fi

# 3. 启动 GUI 开发服务器 (Node.js)
if [ -d "${PROJECT_ROOT}/gui" ]; then
    echo -e "${BLUE}3️⃣  GUI 开发服务器${NC}"
    start_service "GUI" \
        "${PROJECT_ROOT}/gui" \
        "npm run dev" \
        5173
    echo ""
fi

echo "================================================"
echo "✅ 所有服务启动完成"
echo "================================================"
echo ""
echo "📋 服务状态："
echo "  • API:           http://localhost:8000"
echo "  • GUI:           http://localhost:5173"
echo "  • ChannelEngine: http://localhost:8001"
echo ""
echo "📊 日志文件位置："
echo "  ${LOG_DIR}/"
echo ""
echo "🧪 运行端到端测试："
echo "  cd ${PROJECT_ROOT}"
echo "  python3 e2e_test_suite.py --verbose"
echo ""
echo "停止所有服务:"
echo "  bash ${PROJECT_ROOT}/scripts/stop_all_services.sh"
echo ""

# 保存PID到文件以便停止
echo "服务启动于 $(date)" > "${LOG_DIR}/services.info"
echo "项目目录: ${PROJECT_ROOT}" >> "${LOG_DIR}/services.info"

# 保持脚本运行，显示日志
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "显示实时日志 (按 Ctrl+C 关闭):"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

tail -f "${LOG_DIR}"/*.log 2>/dev/null &
TAIL_PID=$!

# 处理 Ctrl+C
trap "
    echo ''
    echo '收到关闭信号，正在停止所有服务...'
    kill $TAIL_PID 2>/dev/null || true
    bash ${PROJECT_ROOT}/scripts/stop_all_services.sh
    exit 0
" SIGINT SIGTERM

wait
