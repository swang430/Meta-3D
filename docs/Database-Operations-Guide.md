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

## 3. 初始化向导与脚本

为方便首次部署，系统内嵌了智能的数据库初始化向导。

### 3.1 自动启动向导
当您首次通过 `npm run dev:safe:all` 启动系统时，启动脚本会自动探测数据库状态。如果发现核心表为空，系统会在终端提示您进入**全自动初始化向导**：
1. 自动生成所有所需的表结构 (Schema)
2. 注入仪器型号目录 (Seed Instruments)
3. 生成 CAICT 默认 32 探头物理布局
4. 生成基础测试报告模板
5. 加载标准通用与路测测试序列

### 3.2 手动执行初始化脚本
如果因故自动向导未能完成，或者您需要重置特定部分的数据，您可以手动在后端虚拟环境中执行这些 Python 脚本：

```bash
# 1. 切换到后端目录并激活虚拟环境
cd api-service
source .venv/bin/activate

# 2. 如果需要建表（通常 FastAPI 启动时会自动建表）
python -c "from app.db.database import init_db; init_db()"

# 3. 依次执行数据注入
python scripts/seed_instruments.py
python scripts/init_probes.py
python scripts/init_report_templates.py
python scripts/init_sequences.py
```

> [!TIP]
> 如果您是在没有连接真实物理硬件的纯离线开发环境中，强烈建议执行 `python scripts/seed_dummy_calibration.py` 来注入虚拟的路径校准损耗数据，这能防止拓扑编辑器和测试引擎因缺少校准文件而报错。

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
如果需要在开发期间彻底清空并重新开始：
```bash
docker-compose down -v
docker-compose up -d postgres
```
然后再次运行 `npm run dev:safe:all` 触发全新的初始化向导。

---

## 5. 常见问题排查 (Troubleshooting)

**问题：终端提示“⚠️ 数据库连接失败！”**
- **原因**：PostgreSQL 容器未运行，或端口被占用。
- **解决**：进入 `api-service` 目录，执行 `docker-compose up -d postgres`，然后使用 `docker ps` 确保 `meta3d_db` 容器处于 `Up` 状态。

**问题：数据未保存或修改丢失**
- **原因**：可能因为错误修改了 `.env` 文件，导致连接到了本地的 SQLite (`meta3d_ota.db`) 而非 Docker。
- **解决**：检查 `.env` 文件，确保 `DATABASE_URL` 并非 `sqlite:///...`。
