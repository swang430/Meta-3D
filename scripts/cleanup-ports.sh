#!/bin/bash

# 端口清理脚本
# 用于清理开发服务占用的端口

echo "🧹 正在清理端口占用..."

# 定义端口列表 (API Service = 8000, ChannelEngine = 8001, Frontend GUI = 5173)
PORTS=(8000 8001 5173)

# 取数 (listening_pids) 与"能不能杀"判定 (is_docker_pid) 在
# scripts/lib/port-guard.sh —— 跟 safe-start.sh 同源, 为什么需要守门写在那里。
# **别在这里复制副本**: 上一版两边各一份, 立刻就漂出了两处行为分叉。
source "$(dirname "${BASH_SOURCE[0]}")/lib/port-guard.sh"

SKIPPED_PORTS=()

# 清理每个端口
for PORT in "${PORTS[@]}"; do
    # 查找监听该端口的进程
    PIDS=$(listening_pids "$PORT")

    if [ -n "$PIDS" ]; then
        PORT_HAS_DOCKER=0
        for P in $PIDS; do
            if is_docker_pid "$P"; then
                echo "  ⛔ 端口 $PORT 的 PID $P 是容器转发进程 — 跳过，不 kill"
                echo "     杀它 = 杀整个 Docker daemon（见 scripts/lib/port-guard.sh）"
                echo "     要腾出这个端口，先查是哪个容器再停它："
                echo "       docker ps --filter publish=$PORT --format '{{.Names}}'"
                PORT_HAS_DOCKER=1   # 端口级标记, 循环后只 append 一次 (同端口可能多个转发 PID)
                continue
            fi

            echo "  ⚠️  端口 $PORT 被进程 $P 占用，正在终止..."
            kill -9 "$P" 2>/dev/null
        done
        [ "$PORT_HAS_DOCKER" -eq 1 ] && SKIPPED_PORTS+=($PORT)

        # 再次检查 —— "还剩监听者"分两种, 别混成一句话:
        #   剩下的全是 Docker → 预期内 (本来就故意不杀), 不是失败;
        #   剩下有非 Docker 的 → 真的没清掉, 必须报 ❌ 让人看见。
        sleep 0.5
        REMAIN=$(listening_pids "$PORT")
        REMAIN_OTHER=""
        for R in $REMAIN; do
            is_docker_pid "$R" || REMAIN_OTHER="$REMAIN_OTHER $R"
        done
        if [ -z "$REMAIN" ]; then
            echo "  ✅ 端口 $PORT 已清理"
        elif [ -z "$REMAIN_OTHER" ]; then
            echo "  ↳ 端口 $PORT 仍由容器转发进程监听（预期，需 docker stop 容器才能腾出）"
        else
            echo "  ❌ 端口 $PORT 清理失败，仍有监听者:$REMAIN_OTHER"
            echo "     (kill 可能因权限不足失败; 试 sudo kill -9$REMAIN_OTHER)"
        fi
    else
        echo "  ✓ 端口 $PORT 未被占用"
    fi
done

echo ""
if [ ${#SKIPPED_PORTS[@]} -gt 0 ]; then
    echo "⚠️  端口 ${SKIPPED_PORTS[*]} 上有容器转发进程，已跳过（见上方排查提示）。"
fi
echo "✨ 端口清理完成！"
