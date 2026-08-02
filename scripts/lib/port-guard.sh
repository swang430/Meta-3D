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
# ⛔ⓑ 容器转发进程的 PID 绝不 kill:
#    在 macOS host 一侧监听容器发布端口的**不是容器**, 而是 Docker Desktop 的转发
#    进程 com.docker.backend, 也就是 **Docker 引擎本体**。kill -9 打上去 = 整个
#    daemon 当场死亡, 紧接着 db-up.sh 报 "Cannot connect to the Docker daemon"
#    启动失败 —— 而那时端口上已经没人了, 现象看起来跟端口毫无关系。
#    实测时间线: 22:12:56 meta3d-api 容器把 8000 绑到 host → safe-start 杀 8000
#    → 22:13:09 com.docker.backend.log 出现 "monitor exited: signal: killed"。
#
# ⓒ 杀不杀**按 PID 判, 不按端口判**:
#    同一个端口上可以同时有两个监听者 —— host 进程占 IPv4、容器转发占 IPv6
#    (实测 8000 正是这样)。按端口整体拒杀会连该清的 host 残留一起放过。

# 监听指定端口的 PID (每行一个)。只认 TCP LISTEN, 见 ⓐ。
listening_pids() {
    lsof -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null
}

# 这个 PID 是不是容器运行时的端口转发进程 —— 是则绝不能 kill, 见 ⓑ。
#
# ⚠️ 这是 **denylist**, 判据是进程名, 默认动作是"杀"。所以新形态一旦没被列进来,
#    失效是**静默**的 (直接回到"杀") —— 加新形态时务必带上实证, 别照着印象写。
#    已覆盖三条, **各自的实证强度不同, 别当成一样硬**:
#      com.docker.backend  macOS Docker Desktop 的转发进程 —— 本条**本机实测**:
#                          lsof 显示它监听 5432/8000/8501, ps -o comm= 给出完整
#                          路径, 且它就是本次事故的死因。
#      docker-proxy        Linux 原生 docker 的 per-port 转发进程 —— **二进制实证**
#                          (Docker Desktop 的 Linux VM 里 /usr/bin/docker-proxy
#                          确实存在), 但**没见过它的活进程**: Desktop 关了
#                          userland-proxy, 转发走 macOS 侧的 gvisor。native Linux
#                          默认 userland-proxy=true 时它才是发布端口的监听者;
#                          设成 false 时是纯 iptables DNAT, **没有任何进程监听** ——
#                          那种情况下 listening_pids 本来就取不到东西, 不会误杀。
#      rootlesskit         rootless docker 的网络栈 —— ⚠️ **未实证**, 按该项目的
#                          组件名写的, 手上没有 rootless 环境可验。
#    **未覆盖, 如实申报**: colima/lima 用 host 上的 `ssh -L` master 做转发, 进程名
#    就是 ssh —— 拿 ssh 当判据会误杀用户自己的 ssh, 宁可漏判也不加; OrbStack /
#    Rancher Desktop 的 helper 进程名我没有环境实证, 不猜。这些环境下本守门等于
#    不存在, 走的还是"杀"那条路。彻底的解法是反过来做 allowlist (只杀
#    python/node/uvicorn/vite 这类自家 dev 进程), 已记 backlog。
is_docker_pid() {
    [ -n "$1" ] || return 1
    case "$(ps -p "$1" -o comm= 2>/dev/null)" in
        *com.docker*|*docker-proxy*|*rootlesskit*) return 0 ;;
    esac
    return 1
}
