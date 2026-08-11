#!/bin/bash

# 端口清理脚本
# 用于清理开发服务占用的端口

echo "🧹 正在清理端口占用..."

# 定义端口列表 (API Service = 8000, ChannelEngine = 8001, Frontend GUI = 5173)
PORTS=(8000 8001 5173)

# 取数 (listening_pids) 与"能不能杀"判定 (is_project_dev_pid) 在
# scripts/lib/port-guard.sh —— 跟 safe-start.sh 同源, 为什么需要守门写在那里。
# **别在这里复制副本**: 上一版两边各一份, 立刻就漂出了两处行为分叉。
source "$(dirname "${BASH_SOURCE[0]}")/lib/port-guard.sh"

SKIPPED_PORTS=()
FAILED_PORTS=()

# 清理每个端口
for PORT in "${PORTS[@]}"; do
    # 查找监听该端口的进程
    PIDS=$(listening_pids "$PORT")

    if [ -n "$PIDS" ]; then
        PORT_HAS_PROTECTED=0
        for P in $PIDS; do
            if ! is_project_dev_pid "$P"; then
                echo "  ⛔ 端口 $PORT 的 PID $P 不在项目开发进程 allowlist — 跳过，不 kill"
                echo "     请先确认身份：ps -p $P -o pid=,command="
                PORT_HAS_PROTECTED=1
                continue
            fi

            echo "  ⚠️  端口 $PORT 被进程 $P 占用，正在终止..."
            kill -9 "$P" 2>/dev/null
        done
        [ "$PORT_HAS_PROTECTED" -eq 1 ] && SKIPPED_PORTS+=($PORT)

        # 再次检查 —— "还剩监听者"分两种, 别混成一句话:
        #   剩下的全是受保护进程 → 预期内 (本来就故意不杀), 不是假成功;
        #   剩下有 allowlist 进程 → 自动清理真的没成功, 必须报 ❌。
        sleep 0.5
        REMAIN=$(listening_pids "$PORT")
        REMAIN_KILLABLE=""
        for R in $REMAIN; do
            is_project_dev_pid "$R" && REMAIN_KILLABLE="$REMAIN_KILLABLE $R"
        done
        if [ -z "$REMAIN" ]; then
            echo "  ✅ 端口 $PORT 已清理"
        elif [ -z "$REMAIN_KILLABLE" ]; then
            echo "  ↳ 端口 $PORT 仍由受保护进程监听（请确认身份后手动处置）"
            FAILED_PORTS+=($PORT)
        else
            echo "  ❌ 端口 $PORT 清理失败，allowlist 监听者仍在:$REMAIN_KILLABLE"
            echo "     (kill 可能因权限不足失败; 请确认身份后手动处置)"
            FAILED_PORTS+=($PORT)
        fi
    else
        echo "  ✓ 端口 $PORT 未被占用"
    fi
done

echo ""
if [ ${#SKIPPED_PORTS[@]} -gt 0 ]; then
    echo "⚠️  端口 ${SKIPPED_PORTS[*]} 上有受保护进程，已跳过（见上方排查提示）。"
fi
if [ ${#FAILED_PORTS[@]} -gt 0 ]; then
    echo "❌ 端口 ${FAILED_PORTS[*]} 仍被占用，清理未完成。"
    exit 1
fi
echo "✨ 端口清理完成！"
