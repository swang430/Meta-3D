#!/bin/bash

# 安全启动脚本
# 启动前检查端口，如果被占用则询问是否清理

echo "🚀 准备启动开发环境..."
echo ""

# 定义端口列表和对应服务名称
# ⚠️ 端口↔服务对应以实现为准, 别照抄记忆: API Service = 8000
#    (api-service/app/main.py), ChannelEngine = 8001
#    (channel-engine-service/app/main.py)。这两个标签原先是反的。
PORTS=(8000 8001 5173)
SERVICE_NAMES=("API Service" "ChannelEngine" "Frontend GUI")

# 端口占用者的取数 (listening_pids) 与"能不能杀"判定 (is_docker_pid) 在
# scripts/lib/port-guard.sh —— 跟 cleanup-ports.sh 同源。为什么需要这层守门、
# 覆盖了哪些容器运行时、哪些没覆盖, 全写在那个文件的头注释里。
# **别在这里复制副本**: 上一版两边各一份, 立刻就漂出了两处行为分叉。
source "$(dirname "${BASH_SOURCE[0]}")/lib/port-guard.sh"

# 检查端口占用
OCCUPIED_PORTS=()
OCCUPIED_SERVICES=()

for i in "${!PORTS[@]}"; do
    PORT=${PORTS[$i]}
    SERVICE=${SERVICE_NAMES[$i]}

    PIDS=$(listening_pids "$PORT")
    [ -n "$PIDS" ] || continue

    KILLABLE=""
    DOCKER_PIDS=""
    for P in $PIDS; do
        if is_docker_pid "$P"; then
            DOCKER_PIDS="$DOCKER_PIDS $P"
        else
            KILLABLE="$KILLABLE $P"
        fi
    done

    if [ -n "$DOCKER_PIDS" ]; then
        echo "⛔ 端口 $PORT ($SERVICE) 上有容器转发进程在监听 (PID${DOCKER_PIDS}) — 不 kill"
        echo "   杀它 = 杀整个 Docker daemon（见 scripts/lib/port-guard.sh）。"
        echo "   要腾出这个端口，先查是哪个容器再停它："
        echo "     docker ps --filter publish=$PORT --format '{{.Names}}'"
        # 这里**不记标记** —— 最终提示的分类在收尾判定处当场重算 (原因见那里)
    fi

    if [ -n "$KILLABLE" ]; then
        echo "⚠️  端口 $PORT ($SERVICE) 被进程${KILLABLE} 占用"
        OCCUPIED_PORTS+=($PORT)
        OCCUPIED_SERVICES+=("$SERVICE")
    fi
done

# 注意: 这里**不 exit** —— "不杀容器转发进程"跟"不许启动"是两件事, 别绑一起,
# 先把能清的 host 残留清掉。真正的放行判定挪到清理**之后**(见下方"收尾判定")。

# 如果有端口被占用，询问是否清理
if [ ${#OCCUPIED_PORTS[@]} -gt 0 ]; then
    echo ""
    echo "发现 ${#OCCUPIED_PORTS[@]} 个端口被占用。"
    read -p "是否清理这些端口？(y/n) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在清理端口..."
        for PORT in "${OCCUPIED_PORTS[@]}"; do
            # 重新取数 + 重新守门 —— 上面的检查到这里隔着一个 read 等用户输入的窗口,
            # 期间 Docker Desktop 完全可能刚好把容器拉起来占上这个端口 (本次事故正是
            # Docker 刚启动、容器陆续 up 的场景)。守门必须打在真正执行 kill 的这一端,
            # 不能只打在检查那一端。
            for P in $(listening_pids "$PORT"); do
                if is_docker_pid "$P"; then
                    echo "  ⛔ 端口 $PORT 的 PID $P 是容器转发进程 — 跳过不 kill"
                    continue
                fi
                kill -9 "$P" 2>/dev/null
            done

            # kill 完必须复验再下结论 —— kill 的返回码被 2>/dev/null 吞了, 监听者
            # 属于别的用户/root 时它会 EPERM 失败。不复验就报 ✅ 是假成功: 脚本
            # 一路往下走, 最后 npm run dev 撞 EADDRINUSE 才炸, 且看不出跟这里有关。
            sleep 0.5
            REMAIN_OTHER=""; REMAIN_DOCKER=""
            for R in $(listening_pids "$PORT"); do
                if is_docker_pid "$R"; then
                    REMAIN_DOCKER="$REMAIN_DOCKER $R"
                else
                    REMAIN_OTHER="$REMAIN_OTHER $R"
                fi
            done
            # 三态, 别把"只剩容器"混进"已清理" —— 只剩容器时端口照样用不了
            # (Docker 是双栈 socket), 报"已清理"是谎报, 下面收尾判定会立刻打脸。
            if [ -n "$REMAIN_OTHER" ]; then
                echo "  ❌ 端口 $PORT 清理失败，仍有监听者:$REMAIN_OTHER"
                echo "     (kill 可能因权限不足失败; 试 sudo kill -9$REMAIN_OTHER)"
            elif [ -n "$REMAIN_DOCKER" ]; then
                echo "  ↳ 端口 $PORT 的 host 进程已清，但容器转发进程仍占着（需 docker stop）"
            else
                echo "  ✅ 端口 $PORT 已清理"
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

# ── 收尾判定: 清理完之后, 端口到底还能不能用 ──────────────────────────────
#
# 判据放在清理**之后**, 且只问一件事: **还有没有人在听**。不猜是谁占的、不猜地址族。
#
# 为什么不排在清理之前 (内审 F1): 上一版把"这端口上有容器"当硬退条件排在清理前,
#   结果同端口的 host 残留一次都清不掉 —— 按端口整体拒杀, 连该杀的一起放过。
# 为什么不能只打印提示就放行 (Codex #268 P1): 容器**先**拿到端口时, Docker 发布的
#   是**双栈** socket。实测 (空闲端口 45222): `lsof` 只显示一条 `IPv6 *:45222
#   (LISTEN)`, 但 host 侧 bind `0.0.0.0` 和 `::` **双双 Address already in use**。
#   我先前"容器占 IPv6 / host 占 IPv4 可共存"的观察是**特例**: 那次是 host 进程
#   抢先占了 IPv4, Docker 才退化成 IPv6-only。真实事故顺序恰好相反 —— Docker
#   Desktop 先自启容器、用户后跑本脚本 —— 这时 host 服务是真起不来的。
# 所以: 让它在这里带着修复命令停下, 而不是放行后由 uvicorn/vite 抛 EADDRINUSE、
#   埋在 concurrently 的交错日志里。**故障现象离原因十万八千里正是本脚本要治的病。**
# ⚠️ 提示分类**在这里当场重新算**，不读初次扫描留下的标记 (Codex #268 R2)。
#   竞态复现: 初次扫描时端口上只有普通进程 → 标记为空 → 用户答 y 的那几秒里
#   Docker 接管了端口 → 清理循环认出并跳过它 → 但若最终提示读的是那个**旧标记**,
#   就会走进"非容器占用……试 sudo"分支, **叫用户 sudo kill -9 掉 Docker 引擎的
#   PID** —— 手动重演本 PR 要修的事故。判据必须跟被判定的对象同一时刻取。
STILL_HELD=()
STILL_DOCKER_PORTS=()
for i in "${!PORTS[@]}"; do
    PORT=${PORTS[$i]}
    PIDS=$(listening_pids "$PORT")
    [ -n "$PIDS" ] || continue
    STILL_HELD+=("$PORT (${SERVICE_NAMES[$i]})")
    for P in $PIDS; do
        if is_docker_pid "$P"; then
            STILL_DOCKER_PORTS+=($PORT)
            break            # 一个端口只登记一次
        fi
    done
done

if [ ${#STILL_HELD[@]} -gt 0 ]; then
    echo ""
    echo "❌ 清理后这些端口仍有人监听，本次启动会撞 EADDRINUSE，先停下："
    for HELD in "${STILL_HELD[@]}"; do echo "     - $HELD"; done
    echo ""
    if [ ${#STILL_DOCKER_PORTS[@]} -gt 0 ]; then
        echo "   其中 ${STILL_DOCKER_PORTS[*]} 是容器发布的（本脚本故意不 kill —— 杀它 = 杀 Docker 引擎）。"
        echo "   查出容器并停掉："
        for P in "${STILL_DOCKER_PORTS[@]}"; do
            echo "     docker ps --filter publish=$P --format '{{.Names}}'   # → docker stop <容器名>"
        done
        echo "   注：compose 的 api 服务已挪进 'full' profile，默认不再随 up 自启；"
        echo "       若它还在跑：cd api-service && docker compose stop api"
    fi
    if [ ${#STILL_DOCKER_PORTS[@]} -lt ${#STILL_HELD[@]} ]; then
        echo "   非容器占用的那些：kill 可能因权限不足失败，试 sudo，或手动停掉占用进程。"
    fi
    exit 1
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
