#!/bin/bash
# db-up.sh — 确保 meta3d Postgres 容器在运行, 且 host:5432 端口"真的"绑上。
#
# 背景: macOS Docker Desktop 重启后, postgres 容器会被 restart 策略自启, 但已声明的
#   发布端口 (5432:5432) 可能没被重新绑定到 host (HostConfig.PortBindings 写着 5432,
#   但 NetworkSettings.Ports 为空 / host 上没人 listen)。host 后端 (.env localhost:5432)
#   于是连不到 DB → 所有 DB 端点 500, GUI 满屏"未就绪"。
#   普通 `docker compose up -d` 在容器配置未变时是 no-op, 修不好; 必须 force-recreate。
#
# 本脚本: up -d → 等 healthy → 验证 host:5432 真可达 → 不可达则 force-recreate 自愈 → 复验。
# 命名卷 meta3d_postgres_data 不动, 数据安全。任意目录可调用。
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${PROJECT_ROOT}/api-service"
DB_CONTAINER="meta3d_db"
DB_USER="meta3d"
DB_PORT=5432

wait_ready() {
  local i
  for i in $(seq 1 30); do
    if docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

host_port_bound() {
  nc -z localhost "$DB_PORT" >/dev/null 2>&1
}

echo "🗄  [db-up] 确保 Postgres 容器在运行..."
( cd "$COMPOSE_DIR" && docker compose up -d postgres )

echo "⏳ [db-up] 等待容器内 Postgres ready..."
if ! wait_ready; then
  echo "❌ [db-up] 30s 内容器未 ready —— 看 'docker logs ${DB_CONTAINER}'"
  exit 1
fi
echo "✅ [db-up] 容器内 Postgres ready"

echo "🔌 [db-up] 验证 host:${DB_PORT} 端口是否真的绑上..."
if host_port_bound; then
  echo "✅ [db-up] host:${DB_PORT} 可达 —— 一切正常"
  exit 0
fi

echo "⚠️  [db-up] host:${DB_PORT} 连不上 (典型: Docker Desktop 重启后端口转发未重建)"
echo "🔧 [db-up] force-recreate 容器以重挂端口 (命名卷数据不动)..."
( cd "$COMPOSE_DIR" && docker compose up -d --force-recreate postgres )

if ! wait_ready; then
  echo "❌ [db-up] force-recreate 后容器未 ready"
  exit 1
fi

if host_port_bound; then
  echo "✅ [db-up] 已自愈 —— host:${DB_PORT} 现在可达"
  exit 0
fi

echo "❌ [db-up] force-recreate 后 host:${DB_PORT} 仍连不上。可能原因:"
echo "   - 别的进程占用了 ${DB_PORT}:  lsof -nP -iTCP:${DB_PORT} -sTCP:LISTEN"
echo "   - Docker Desktop 端口转发层卡死:  重启 Docker Desktop 后再跑本脚本"
echo "   现状:  docker compose -f ${COMPOSE_DIR}/docker-compose.yml ps"
exit 1
