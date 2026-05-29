# 数据库备份与恢复 / 持久化 runbook

> 2026-05-29 durability 改进。**本文只覆盖"数据不丢"(durability),不覆盖信息安全
> (端口暴露 / 弱密码)—— 后者是单独一轮工作,见文末「已知 deferred」。**

## 为什么需要这套机制

实测发现两个 🔴 鲁棒性问题:

1. **启动不可复现 + volume 漂移**:运行中的 `meta3d_db` 是**手动 `docker run`** 起的(无 compose label),挂 named volume `meta3d_postgres_data`(真数据)。而 `docker-compose.yml` 若直接 `docker compose up`,默认 project=目录名 `api-service` → 会连到**另一个废弃 volume `api-service_postgres_data`**(旧数据)→ 在旧库上跑测试 = 真相分裂。
2. **零备份 + Docker Desktop VM 单点**:macOS 上 named volume 实际在 Docker Desktop 的 Linux VM 虚拟磁盘镜像(`Docker.raw`)里。Docker Desktop「Troubleshoot → Reset / Purge data」一键清空;host 硬断电可能损坏 VM 磁盘 → 整库全丢。PG 自己的 WAL 只保**容器内**崩溃恢复,**保不了 VM 磁盘镜像损坏**。默认不在 Time Machine。

本套机制:
- `docker-compose.yml` 用固定 `name: meta3d_postgres_data`(**非 external**)锁定真数据 volume,消除漂移;且缺失时 compose 自动创建 —— 全新 checkout / Docker Desktop purge 后 / 灾后恢复可直接 `docker compose up`,不会因 volume 缺失报错(`external: true` 会报错,Codex on PR #102)。
- `scripts/backup_db.sh` + launchd 定时把库 `pg_dump` 导到 **host 真实文件系统**(进 Time Machine / 可拷走)—— 唯一跨 VM-磁盘-损坏的副本。

## 数据存在哪

| | 位置 |
|---|---|
| 库文件(权威副本) | named volume `meta3d_postgres_data` → Docker Desktop VM 内 `/var/lib/docker/volumes/meta3d_postgres_data/_data` |
| 备份 dump | host `api-service/db-backups/*.dump`(custom format,gitignored)|
| ~~废弃 volume~~ | `api-service_postgres_data` 已删(2026-05-29,orphan 旧数据);删前 tar 留底 `db-backups/abandoned_*.tar.gz` |

## 备份

### 手动跑一次

```bash
cd api-service
sh scripts/backup_db.sh
# → db-backups/meta3d_ota_<时间戳>.dump  (custom format, 已验证 TOC)
```

脚本行为:`pg_dump -Fc` → 验证非空 + TOC 有效 → 轮转保留最近 30 份(`META3D_BACKUP_RETENTION` 可调)。容器没在跑会非 0 退出(不静默跳过)。

### 定时(launchd,每天 03:00)

```bash
# 路径是 host 特定的, 换机器先改 plist 里的绝对路径
cp scripts/com.meta3d.db-backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.meta3d.db-backup.plist
launchctl start com.meta3d.db-backup     # 立即测一次
tail db-backups/backup.log               # 看结果
```

停用:`launchctl unload ~/Library/LaunchAgents/com.meta3d.db-backup.plist`。

> 💡 建议额外:确认 `~/Tools/MIMO-First/` 在 Time Machine 备份范围内(db-backups 在其下),这样 dump 又多一层 host 外副本。

## 恢复

### 从 dump 恢复到现有库(覆盖)

```bash
# ⚠️ 会覆盖现有数据 — 恢复前先备份当前状态 (sh scripts/backup_db.sh)
DUMP=db-backups/meta3d_ota_<时间戳>.dump
cat "$DUMP" | docker exec -i meta3d_db pg_restore -U meta3d -d meta3d_ota --clean --if-exists
```

### 恢复到全新库(灾难恢复,volume 已丢)

```bash
# 1. 起空 postgres (volume 已丢也没关系: 非 external, compose 会自动建空 volume)
docker compose up -d postgres
# 2. 建库 (POSTGRES_DB 已自动建 meta3d_ota; 若没有:)
docker exec meta3d_db createdb -U meta3d meta3d_ota 2>/dev/null || true
# 3. 灌数据
cat db-backups/meta3d_ota_<时间戳>.dump | docker exec -i meta3d_db pg_restore -U meta3d -d meta3d_ota --clean --if-exists
# 4. 验证表数
docker exec meta3d_db psql -U meta3d -d meta3d_ota -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

## 从「手动 run」切到「compose 管理」(一次性演练)

让 `docker-compose.yml` 成为唯一真相源。**数据在 named volume,stop/rm 容器不丢**;且已有 dump 兜底。

```bash
cd api-service
# 1. 验证 compose 解析到真数据 volume (不改任何状态)
docker compose config | grep -A3 'postgres_data'    # 应看到 name: meta3d_postgres_data (非 external)

# 2. 先备份 (止血)
sh scripts/backup_db.sh

# 3. 停 + 删手动容器 (named volume 不受影响)
docker stop meta3d_db && docker rm meta3d_db

# 4. 用 compose 起 (只起 postgres, 不碰 host 上的 uvicorn :8000)
docker compose up -d postgres

# 5. 验证连的是真数据 (表数应跟切换前一致, 当前 = 55)
docker exec meta3d_db psql -U meta3d -d meta3d_ota -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

切换后 `restart: unless-stopped` 生效 → host/Docker 重启自动拉起。若第 5 步表数不符,`docker compose down` 后用上面「恢复」章节从 dump 重建。

## 已知 deferred(本轮不做)

- **信息安全**:Postgres 5432 + API 8000 仍绑 `0.0.0.0`(所有接口);明文弱密码 `meta3d_password` 在 git 追踪的 compose + `config.py:15` 默认值里;macOS 防火墙关闭。这些是**网络安全**问题,与本文的 durability 正交,留单独一轮(用户 2026-05-29 明确「安全性以后再说」)。
- **废弃 volume 清理**:`api-service_postgres_data`(旧数据)确认无用后 `docker volume rm`,先留存。
