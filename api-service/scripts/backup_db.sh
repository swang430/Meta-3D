#!/bin/sh
# PostgreSQL 备份脚本 (2026-05-29 durability 改进 — out-of-roadmap)。
#
# 把运行中的 meta3d-postgres 容器里的库 pg_dump (custom format) 导到
# host 的 db-backups/ 目录, 轮转保留最近 N 份。custom format (-Fc) 压缩 +
# 支持 pg_restore 选择性恢复。
#
# 为什么需要: macOS Docker Desktop 的 named volume 实际在 Linux VM 的虚拟
# 磁盘镜像 (Docker.raw) 里 — "Reset to factory defaults" / host 硬断电 →
# VM 磁盘损坏 = 整库全丢 (PG 自己的 WAL 只保容器内崩溃恢复, 保不了 VM 磁盘)。
# 本脚本导出到 host 真实文件系统 (进 Time Machine 范围 / 可拷走), 是唯一
# 跨 VM-磁盘-损坏 的副本。
#
# 用法:
#   scripts/backup_db.sh                 # 手动跑一次
#   (或 launchd 定时, 见 scripts/com.meta3d.db-backup.plist)
#
# 可调环境变量 (都有默认):
#   META3D_PG_CONTAINER  (meta3d-postgres)
#   META3D_PG_DB         (meta3d_ota)
#   META3D_PG_USER       (meta3d)
#   META3D_BACKUP_DIR    (脚本同级 ../db-backups)
#   META3D_BACKUP_RETENTION (30 — 保留最近 30 份)
set -e

# launchd 环境 PATH 不含 docker — 显式补全 (Docker Desktop / Homebrew 常见位置)。
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"

CONTAINER="${META3D_PG_CONTAINER:-meta3d-postgres}"
DB="${META3D_PG_DB:-meta3d_ota}"
PGUSER_="${META3D_PG_USER:-meta3d}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BACKUP_DIR="${META3D_BACKUP_DIR:-$SCRIPT_DIR/../db-backups}"
RETENTION="${META3D_BACKUP_RETENTION:-30}"

mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d_%H%M%S)
OUT="$BACKUP_DIR/${DB}_${TS}.dump"

# 容器没在跑 → 非 0 退出 (launchd 记失败, 不静默跳过)。
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "[backup] ERROR: 容器 ${CONTAINER} 没在运行 — 跳过备份" >&2
    exit 1
fi

echo "[backup] $(date '+%Y-%m-%d %H:%M:%S') pg_dump ${DB} → ${OUT}"
docker exec "$CONTAINER" pg_dump -U "$PGUSER_" -Fc "$DB" > "$OUT"

# 验证: dump 非空 + pg_restore -l 能列出 TOC (确认不是半截 / 损坏)。
if [ ! -s "$OUT" ]; then
    echo "[backup] ERROR: dump 为空, 删除 ${OUT}" >&2
    rm -f "$OUT"
    exit 1
fi
TOC=$(docker run --rm -i "$(docker inspect "$CONTAINER" --format '{{.Config.Image}}')" \
        pg_restore -l < "$OUT" 2>/dev/null | grep -cE "^[0-9;]" || true)
if [ "${TOC:-0}" -lt 1 ]; then
    echo "[backup] ERROR: dump 无有效 TOC 对象 (可能损坏), 删除 ${OUT}" >&2
    rm -f "$OUT"
    exit 1
fi

SIZE=$(du -h "$OUT" | cut -f1)
echo "[backup] OK: ${OUT} (${SIZE}, ${TOC} 对象)"

# 轮转: 超过 RETENTION 份就删最旧的。
COUNT=$(ls -1t "$BACKUP_DIR"/${DB}_*.dump 2>/dev/null | wc -l | tr -d ' ')
if [ "$COUNT" -gt "$RETENTION" ]; then
    ls -1t "$BACKUP_DIR"/${DB}_*.dump | tail -n +$((RETENTION + 1)) | while read -r old; do
        echo "[backup] 轮转删除旧备份: $old"
        rm -f "$old"
    done
fi
