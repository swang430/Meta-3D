# 数据库备份与恢复 / 持久化 runbook

> 本文说明数据库持久化、备份、恢复及本机访问范围。

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

### 升级前留存和恢复到独立实例

1. 停止本实例写入，记录正在运行的 API、计算服务、界面版本及数据库迁移号。保留旧可执行包或镜像，记录连接配置、实际挂载路径、属主和权限。
2. 用本实例的 META3D_PG_CONTAINER、META3D_PG_DB、META3D_PG_USER 和独立的 META3D_BACKUP_DIR 运行 sh scripts/backup_db.sh。确认退出成功。按数据库记录及实际配置另存外部附件、报告、证书、校准数据、站点配置及所需密钥。以相同的停写窗口生成文件清单和校验值，限制备份权限。
3. 在独立网络和新卷初始化目标数据库，为恢复使用新的空库。显式确认容器名、数据库名、目标卷及应用连接地址；默认 Compose 文件里的容器名和卷名是固定的。只改项目名仍会引用原资源。
4. 在目标实例执行以下命令。确认库名空闲后创建，任一命令失败即停止。所有恢复对象在同一事务内提交。

```sh
docker exec "$RESTORE_CONTAINER" createdb -U "$RESTORE_USER" "$RESTORE_DB" &&
docker exec -i "$RESTORE_CONTAINER" pg_restore --single-transaction --exit-on-error \
  -U "$RESTORE_USER" -d "$RESTORE_DB" < "$DUMP"
```

5. 把外部文件解包到全新目录。核对配置、权限、文件摘要，以及数据库记录引用的具体文件。权限、凭据及目标地址单独核实后，将旧应用指向恢复库和恢复目录，核对健康接口和关键业务对象。
6. 在独立副本重试新版本并核对迁移号、数据与文件。只有验证完成后才安排站点切换。迁移发生部分提交、初始化失败或版本无法识别时，使用经过核实的升级前备份与旧应用恢复；直接降低版本号不能恢复旧表结构或文件。

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

切换后 `restart: unless-stopped` 生效 → host/Docker 重启自动拉起。若第 5 步表数不符,`docker compose down --remove-orphans` 后用上面「恢复」章节从 dump 重建。(⛔ 旧版这里要求带 `--profile full` —— 那时 compose 里还有个 api 容器;**2026-08-05 已拆除**。但服务定义没了会让残留的 `meta3d-api` 容器变成 **orphan**,而 `down` 默认不动 orphan 且**退出码仍是 0** —— 所以改带 `--remove-orphans`,并先停掉 host 上的 API 进程。)

## 已知 deferred(本轮不做)

- **访问范围**：随附 Compose 将数据库端口发布在 127.0.0.1。新建数据库须提供 META3D_POSTGRES_PASSWORD，已有卷使用原角色凭据。主机启动的 API 与计算服务默认监听回环地址。API 容器内部监听所有接口，发布时显式指定 127.0.0.1 并隔离容器网络。同主机进程以及同一容器网络的成员仍可访问后端。远程接入依赖部署侧认证网关、端口隔离与实际访问测试。
- **废弃 volume 清理**:`api-service_postgres_data`(旧数据)确认无用后 `docker volume rm`,先留存。
