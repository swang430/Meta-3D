# Meta-3D OTA 系统数据库操作与维护指南

本文档旨在为开发人员和系统管理员提供 Meta-3D OTA 系统底层数据库（PostgreSQL）的结构概览、初始化方法以及日常维护指南。

---

## 1. 架构概览

Meta-3D OTA 系统的后端服务强依赖关系型数据库来存储仪器配置、拓扑信息、校准矩阵以及测试执行的流水线记录。

### 1.1 数据存储分类
- **结构化核心数据 (PostgreSQL)**：
  - 存储仪器库 (Instruments)、探头配置 (Probes)、硬件拓扑 (Switch Topology)、标准测试序列 (Test Sequences) 以及校准证书 (Calibration)。
  - 目前推荐并默认使用 Docker 运行的 PostgreSQL。
- **临时与自定义场景数据 (JSON)**：
  - 用户在前端保存的“虚拟路测自定义场景”，因为其数据结构灵活且无需强外键校验，目前被持久化在 `api-service/data/custom_scenarios.json` 中。
- **本地过渡数据 (SQLite)**：
  - 早期开发阶段的遗留产物（如 `meta3d_ota.db`）。**在接下来的架构收敛中，将彻底弃用 SQLite，全面切向 PostgreSQL。**

---

## 2. 数据库连接配置

系统的数据库连接字符串由 `api-service/.env` 文件中的 `DATABASE_URL` 变量控制。

### 2.1 推荐配置 (PostgreSQL in Docker)
```env
# api-service/.env
DATABASE_URL=postgresql://meta3d:meta3d_password@localhost:5432/meta3d_ota
```
此配置对应于 `api-service/docker-compose.yml` 中定义的 `postgres` 容器。

### 2.2 如何使用客户端工具连接
你可以使用 [DBeaver](https://dbeaver.io/) 或 pgAdmin 等工具连接查看数据：
- **Host**: `localhost` (或宿主机 IP)
- **Port**: `5432`
- **Database**: `meta3d_ota`
- **Username**: `meta3d`
- **Password**: `meta3d_password`

---

## 3. 初始化：建表 (Alembic) + 灌默认数据 (Bootstrap)

数据库初始化 = 两步：**Alembic 建表** + **Bootstrap 灌默认数据**。两条部署路径殊途同归（都汇到同一套 `alembic upgrade head` + `run_all` / `bootstrap_history` 逻辑）。

### 3.1 自动（推荐，无需手动干预）
- **Docker 全栈**：`docker compose up -d` —— api 容器的 `docker-entrypoint.sh` 自动按顺序跑 `alembic upgrade head` → `python -m scripts.bootstrap` → uvicorn。
- **host 开发**（host 直接跑 uvicorn）：`app/main.py` 的 lifespan 启动时自动调 `init_db()`（检测到 `alembic_version` 表则跳过 `create_all`）+ `run_bootstrap_on_startup()`（受 config `bootstrap_on_startup=True` 控制）。

> [!WARNING]
> **host 开发全新空库必须先手动 `alembic upgrade head` 再启动 app**。否则 `init_db()` 检测不到 `alembic_version` 表，会 fallback 用 `create_all()` 建表 —— 表是建了，但没有 alembic 版本跟踪，后续 migration 会冲突。Docker 全栈的 entrypoint 已把顺序焊死，无此坑。

### 3.2 手动（重置 / 排查时）

```bash
cd api-service
source .venv/bin/activate

# 1. 建表 — Alembic 迁移到 head (幂等: 只跑未应用的 migration)
alembic upgrade head

# 2. 灌默认数据 — bootstrap 框架 (幂等: bootstrap_history 版本跟踪, 重跑 no-op)
python -m scripts.bootstrap
#   --dry-run          只报计划不写库
#   --force            无视 history 强制重跑
#   --only <seeder>    只跑指定 seeder
```

**7 个 seeder（依赖序）**：`chamber_presets` → `probes` → `instruments` → `sequences` → `report_templates` → `test_case_templates` → `topology_profiles`（暗室预设 / 32 探头布局 / 仪器型号目录 / 标准测试序列 / 报告模板 / TestCase 模板 / UXM 拓扑 profile）。

> [!NOTE]
> 旧的单独 seed 脚本（`seed_instruments.py` / `init_probes.py` / `init_report_templates.py` / `init_sequences.py`）已整合进 bootstrap 框架并删除。任何引用它们的旧步骤一律改用 `python -m scripts.bootstrap`。

> [!TIP]
> **纯离线 / 无真实硬件的开发环境**额外注入虚拟校准数据（`probe_*_calibrations` / RF-chain / link / CE），否则拓扑编辑器 / 测试引擎因无校准报错 —— bootstrap 的 7 个 seeder **不含校准 fixture**。
>
> ⚠️ **前置：chamber ID 必须对齐**。`seed_dummy_calibration.py` 当前**硬编码** `CHAMBER_ID`（`CATR-16-Dual`，某台机器历史 PG 里的值），而 bootstrap 建的 chamber 用**生成的 UUID**。校准行按 `chamber_id` 查询（`channel_engine_client._query_calibration_entries`），chamber 不匹配 → 注入的数据查不到，等于没注入。fresh bootstrap DB 必须先对齐：
> ```bash
> # 1. 查你要测的 chamber id
> docker exec meta3d_db psql -U meta3d -d meta3d_ota -c \
>   "SELECT id, name, is_active FROM chamber_configurations;"
> # 2. 把 scripts/dev-fixtures/seed_dummy_calibration.py 顶部 CHAMBER_ID 改成该 id
> # 3. 跑
> python scripts/dev-fixtures/seed_dummy_calibration.py
> ```
> （fixture 改为参数化 / 自动解析目标 chamber 是已知改进项，见 spawned 任务。）同目录 `scripts/dev-fixtures/` 下另有 `seed_caict_lab_profile.py` / `seed_caict_switch_topology.py` 等 dev-only fixture（同样按需手动跑，注意各自的 chamber/lab 假设）。

---

## 4. 日常维护与备份

由于所有数据都在 Docker 容器的 volume 中，可以通过标准的 PostgreSQL 工具进行备份。

### 4.1 备份数据库
```bash
docker exec -t meta3d_db pg_dump -U meta3d meta3d_ota -F c > meta3d_backup_$(date +%Y%m%d).dump
```

### 4.2 恢复数据库
```bash
# ⚠️ 警告: 这将覆盖当前数据库中的所有数据
cat your_backup_file.dump | docker exec -i meta3d_db pg_restore -U meta3d -d meta3d_ota --clean
```

### 4.3 重置/清空数据库
> [!WARNING]
> `down -v` 会**永久删除 volume 数据**（volume 现在是非 external 具名卷，`-v` 会真删）。重置前务必先备份。

```bash
sh scripts/backup_db.sh          # 1. 先备份当前数据 (止血, → db-backups/)
docker compose down -v           # 2. 删容器 + volume
docker compose up -d postgres    # 3. 起空库 (volume 自动重建)
alembic upgrade head             # 4. 重新建表
python -m scripts.bootstrap      # 5. 重新灌默认数据
```

---

## 5. 常见问题排查 (Troubleshooting)

**问题：终端提示“⚠️ 数据库连接失败！”**
- **原因**：PostgreSQL 容器未运行，或端口被占用。
- **解决**：进入 `api-service` 目录，执行 `docker-compose up -d postgres`，然后使用 `docker ps` 确保 `meta3d_db` 容器处于 `Up` 状态。

**问题：数据未保存或修改丢失**
- **原因**：可能因为错误修改了 `.env` 文件，导致连接到了本地的 SQLite (`meta3d_ota.db`) 而非 Docker。
- **解决**：检查 `.env` 文件，确保 `DATABASE_URL` 并非 `sqlite:///...`。
