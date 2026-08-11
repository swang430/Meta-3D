#!/bin/bash
# port-guard.sh — 端口占用者的取数与"能不能杀"判定。
#
# 被 safe-start.sh 与 cleanup-ports.sh 共同 source。**别把这两个函数复制回调用方** ——
# 上一版就是两边各一份逐字副本, 内审当场抓到它们已经在两处行为分叉 (混合监听场景的
# 处置、kill 后复不复验)。同源才不会漂。
#
# ── 为什么需要这层守门 (2026-08-02 实测事故) ────────────────────────────────
# ⓐ 取数只认 **TCP LISTEN**:
#    `lsof -i:PORT` 一次选中 TCP+UDP, 而且把**连到**该端口的客户端也算成"占用者"。
#    实测: 开着 GUI 的 Chrome tab 连着 127.0.0.1:8000, 它的 PID 就在名单里 →
#    kill -9 顺手打死浏览器; 只 bind 了同号 UDP 口的无关进程同理 (`-s` 的状态过滤
#    只作用于 TCP, 滤不掉 UDP 条目)。要清的是**监听者**, 不是访客。
#    写法跟 scripts/db-up.sh 的 host_port_bound 对齐。
#
# ⛔ⓑ 未明确属于本项目开发服务的 PID 绝不 kill:
#    在 macOS host 一侧监听容器发布端口的**不是容器**, 而是 Docker Desktop 的转发
#    进程 com.docker.backend, 也就是 **Docker 引擎本体**。kill -9 打上去 = 整个
#    daemon 当场死亡, 紧接着 db-up.sh 报 "Cannot connect to the Docker daemon"
#    启动失败 —— 而那时端口上已经没人了, 现象看起来跟端口毫无关系。
#    实测时间线: 22:12:56 meta3d-api 容器把 8000 绑到 host → safe-start 杀 8000
#    → 22:13:09 com.docker.backend.log 出现 "monitor exited: signal: killed"。
#
#    容器转发进程是最贵的误杀实例，但不是唯一需要保护的进程。判据采用 allowlist：
#    只有 python / node / uvicorn / vite 这四类本项目开发服务进程可以自动终止；
#    Docker、ssh、未知 helper 及取不到命令名的 PID 一律保护。未知进程未清掉的代价只是
#    本次启动 fail-closed，远小于误杀用户进程或容器网络栈。
#
# ⓒ 杀不杀**按 PID 判, 不按端口判**:
#    同一个端口上可以同时有两个监听者 —— host 进程占 IPv4、容器转发占 IPv6
#    (实测 8000 正是这样)。按端口整体拒杀会连该清的 host 残留一起放过。

# 监听指定端口的 PID (每行一个)。只认 TCP LISTEN, 见 ⓐ。
PORT_GUARD_REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)

listening_pids() {
    lsof -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null
}

# 这个 PID 是否明确属于本项目可自动终止的开发服务 —— 只有返回 0 才能 kill。
# `ps -o comm=` 在不同平台可能返回 basename 或完整路径，因此先取 basename、再转小写；
# Python 允许常见版本后缀，其他三类必须精确命中。进程类型只是第一层，cwd 还必须位于
# 当前仓库根目录内；同名的其他 Python/Node 项目也必须受保护。lsof 取不到 cwd 时一律
# fail-closed。不要把 shell/ssh/npm 等启动器加进来：它们不是实际监听服务的权威身份，
# 放宽只会扩大误杀面。
is_project_dev_pid() {
    [ -n "$1" ] || return 1
    case "$1" in
        *[!0-9]*) return 1 ;;
    esac

    local command_name
    command_name=$(ps -p "$1" -o comm= 2>/dev/null) || return 1
    command_name=${command_name##*/}
    command_name=$(printf '%s' "$command_name" | tr '[:upper:]' '[:lower:]')

    case "$command_name" in
        python|python[0-9]|python[0-9].[0-9]|python[0-9].[0-9][0-9]|node|uvicorn|vite)
            ;;
        *) return 1 ;;
    esac

    local process_cwd
    process_cwd=$(lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)
    [ -n "$process_cwd" ] || return 1
    case "$process_cwd/" in
        "$PORT_GUARD_REPO_ROOT/"*) return 0 ;;
    esac
    return 1
}
