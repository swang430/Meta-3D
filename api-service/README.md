# Meta-3D OTA Test System API Service

Python FastAPI-based backend service for the Meta-3D MPAC (Multi-Probe Anechoic Chamber) OTA test system.

> **数据架构说明**: 本后端服务是系统的主要数据源。前端可选择使用 Mock Server (开发模式) 或本服务 (生产模式)。详见 [数据架构指南](../docs/Data-Architecture-Guide.md)。

## Features

- **System-Level Calibration**
  - TRP (Total Radiated Power) calibration
  - TIS (Total Isotropic Sensitivity) calibration
  - Repeatability testing
  - Comparability testing (round-robin)
  - Automated calibration certificate generation

- **Mock Instruments**
  - Full mock implementation for development without hardware
  - Realistic simulation of base station emulator, channel emulator, signal analyzer, and probe controller

- **Database**
  - PostgreSQL with SQLAlchemy ORM
  - Comprehensive data models for calibration records
  - Migration support with Alembic

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ (or use SQLite for development)

### 2. Installation

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create `.env` file:

```env
# Application
APP_NAME=Meta-3D OTA API
APP_VERSION=1.0.0
DEBUG=true

# Database
DATABASE_URL=postgresql://meta3d:meta3d_password@localhost:5432/meta3d_ota

# For SQLite (development)
# DATABASE_URL=sqlite:///./meta3d_ota.db

# Mock instruments
USE_MOCK_INSTRUMENTS=true
```

### 4. Database Setup

数据库一律 PostgreSQL,由 `docker-compose.yml` 管理(named volume + restart +
pin `postgres:14.20`)。建表靠 Alembic,灌默认数据靠 bootstrap 框架。

> ⚠️ **不要用裸 `docker run` 起 PostgreSQL** —— 会绕过 compose 管理,且极易漏挂
> `-v` volume(数据存容器可写层,容器删即全丢)。一律走 `docker compose`。

#### Option A: Docker Compose(推荐)

```bash
# 1. 起 PostgreSQL 容器 (volume 缺失自动创建; POSTGRES_DB 自动建空库)
docker compose up -d postgres

# 2. 建表 — Alembic 迁移到 head
alembic upgrade head

# 3. 灌默认数据 — bootstrap (暗室/探头/仪器/序列/模板/拓扑; 幂等可重跑)
python -m scripts.bootstrap

# 3b. (纯离线 / 无硬件开发) 注入虚拟校准 fixture — bootstrap 不含校准数据。
#     ⚠️ fixture 硬编码 chamber ID, fresh DB 须先对齐 (查 chamber id → 改 fixture
#     顶部 CHAMBER_ID), 否则校准行挂错 chamber 查不到。详见 Database-Operations-Guide.md §3。
python scripts/dev-fixtures/seed_dummy_calibration.py
```

> **全自动**:`docker compose --profile full up -d` 会连 api 容器一起起,其
> `docker-entrypoint.sh` 自动按 `alembic upgrade head → bootstrap → uvicorn`
> 跑完,步骤 2-3 无需手动执行。
>
> ⚠️ api 容器在 compose 里挂了 `profiles: ["full"]`,**不带 `--profile full` 的
> `docker compose up -d` 不会起它** —— 它跟 host 开发流程 (`npm run dev:api`)
> 抢同一个 8000,二选一。默认不起是有意的,详见 `docker-compose.yml` 里 api
> 服务上方的注释。
>
> ⚠️ **host 开发**(host 直接跑 uvicorn)时,全新空库**必须先 `alembic upgrade
> head`** 再启动 app —— 否则 lifespan 的 `init_db()` 会 fallback 用
> `create_all()` 建表,绕过 alembic 版本跟踪。详见
> [数据库操作指南](../docs/Database-Operations-Guide.md)。

#### Option B: SQLite(仅单元测试隔离)

测试用(内存 / 文件);生产与开发一律 PostgreSQL。改 `.env`:

```env
DATABASE_URL=sqlite:///./meta3d_ota.db
```

### 5. Run the Service

```bash
# Development mode (auto-reload)
python -m app.main

# Or using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Access API Documentation

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json

## API Usage Examples

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database_connected": true,
  "mock_instruments": true
}
```

### Execute TRP Calibration

```bash
curl -X POST http://localhost:8000/api/v1/calibration/trp \
  -H "Content-Type: application/json" \
  -d '{
    "standard_dut_model": "Standard Dipole λ/2",
    "standard_dut_serial": "DIP-2024-001",
    "reference_trp_dbm": 10.5,
    "frequency_mhz": 3500,
    "tx_power_dbm": 23,
    "tested_by": "Engineer A",
    "reference_lab": "NIM (National Institute of Metrology)",
    "reference_cert_number": "NIM-CAL-2024-001"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "measured_trp_dbm": 10.48,
  "trp_error_db": -0.02,
  "absolute_error_db": 0.02,
  "validation_pass": true,
  "threshold_db": 0.5,
  "num_probes_used": 336,
  "tested_at": "2025-11-16T12:00:00Z"
}
```

### Execute TIS Calibration

```bash
curl -X POST http://localhost:8000/api/v1/calibration/tis \
  -H "Content-Type: application/json" \
  -d '{
    "standard_dut_model": "Reference Smartphone",
    "standard_dut_serial": "REF-PHONE-001",
    "reference_tis_dbm": -90.2,
    "frequency_mhz": 3500,
    "tested_by": "Engineer B"
  }'
```

### Execute Repeatability Test

```bash
curl -X POST http://localhost:8000/api/v1/calibration/repeatability \
  -H "Content-Type: application/json" \
  -d '{
    "test_type": "TRP",
    "dut_model": "Standard Dipole",
    "dut_serial": "DIP-2024-001",
    "num_runs": 10,
    "frequency_mhz": 3500,
    "tested_by": "Engineer C"
  }'
```

**Response:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "test_type": "TRP",
  "num_runs": 10,
  "mean_dbm": 10.52,
  "std_dev_db": 0.18,
  "coefficient_of_variation": 0.017,
  "min_dbm": 10.25,
  "max_dbm": 10.78,
  "range_db": 0.53,
  "validation_pass": true,
  "threshold_db": 0.3,
  "measurements": [
    {"run_number": 1, "value_dbm": 10.45, "timestamp": "2025-11-16T12:00:00Z"},
    ...
  ],
  "tested_at": "2025-11-16T12:05:00Z"
}
```

### Generate Calibration Certificate

```bash
curl -X POST http://localhost:8000/api/v1/calibration/certificate \
  -H "Content-Type: application/json" \
  -d '{
    "trp_calibration_id": "550e8400-e29b-41d4-a716-446655440000",
    "tis_calibration_id": "550e8400-e29b-41d4-a716-446655440001",
    "repeatability_test_id": "660e8400-e29b-41d4-a716-446655440001",
    "lab_name": "Meta-3D Test Laboratory",
    "lab_address": "123 Test Street, City, Country",
    "lab_accreditation": "ISO/IEC 17025:2017",
    "calibrated_by": "Engineer A",
    "reviewed_by": "Technical Manager B",
    "validity_months": 12
  }'
```

**Response:**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "certificate_number": "MPAC-SYS-CAL-2025-11-16-1200",
  "overall_pass": true,
  "trp_pass": true,
  "tis_pass": true,
  "repeatability_pass": true,
  "calibration_date": "2025-11-16T12:00:00Z",
  "valid_until": "2026-11-16T12:00:00Z",
  "issued_at": "2025-11-16T12:10:00Z"
}
```

### List Calibrations

```bash
# List TRP calibrations
curl http://localhost:8000/api/v1/calibration/trp

# List TIS calibrations
curl http://localhost:8000/api/v1/calibration/tis?skip=0&limit=10

# List repeatability tests
curl http://localhost:8000/api/v1/calibration/repeatability?test_type=TRP

# List certificates
curl http://localhost:8000/api/v1/calibration/certificate
```

## Project Structure

```
api-service/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration settings
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py           # Health check endpoint
│   │   └── calibration.py      # Calibration endpoints
│   ├── db/
│   │   ├── __init__.py
│   │   └── database.py         # Database connection
│   ├── models/
│   │   ├── __init__.py
│   │   └── calibration.py      # SQLAlchemy models
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── calibration.py      # Pydantic schemas
│   └── services/
│       ├── __init__.py
│       ├── mock_instruments.py # Mock instrument drivers
│       └── system_calibration.py # Calibration services
├── requirements.txt
└── README.md
```

## Standards Compliance

This implementation follows:

- **3GPP TS 34.114**: 5G NR UE/BS OTA performance requirements
- **CTIA OTA Test Plan Ver. 4.0**: Certification test requirements
- **FCC KDB 971168**: Guidance on OTA measurements
- **ISO/IEC 17025**: Laboratory accreditation requirements

## Validation Criteria

| Calibration Type | Validation Criterion | Threshold |
|------------------|---------------------|-----------|
| TRP | \|measured - reference\| | < ±0.5 dB |
| TIS | \|measured - reference\| | < ±1.0 dB |
| Repeatability (TRP) | σ (standard deviation) | < 0.3 dB |
| Repeatability (TIS/EIS) | σ (standard deviation) | < 0.5 dB |
| Comparability | \|Lab A - Lab B\| | < ±1.0 dB |

## Development

### Run Tests

```bash
pytest
```

### Database Migrations

```bash
# Initialize Alembic (first time)
alembic init alembic

# Create migration
alembic revision --autogenerate -m "Description"

# Apply migration
alembic upgrade head
```

### Code Style

```bash
# Format code
black app/

# Check linting
flake8 app/
```

## Deployment

### Production Setup

1. **Use PostgreSQL** (not SQLite)
2. **Set DEBUG=false** in production
3. **Configure proper CORS** origins
4. **Use production WSGI server**:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn — NOTE: --workers 1 (see below)
gunicorn app.main:app \
  --workers 1 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

> ⚠️ **单 worker 是当前的部署契约，不是随手写的示例值。**
> 容器入口 (`docker-entrypoint.sh`) 也是单进程 uvicorn。三处机制都假设
> "本进程是唯一的执行者"：
> - **启动残留复位** (`main.py` lifespan 调三个 reset)：把 `running` 的
>   执行行判成僵尸并置 failed。多 worker 下，新 worker 启动会误杀**别的
>   worker 正在跑的硬件执行** —— 行被标 failed 后，HAL reload 闸门随之
>   停止保护那条仍在跑的链（Codex #242 C1）。
> - **进程内单飞标志** (`test_case_runner`；ARCH-1 S4b 前还有一个 `test_plan_runner`，已删)：内存态，
>   跨 worker 不可见（已配 DB 行判据兜底，但复位没有）。
> - **相位执行**：commissioning 的相位同步跑在请求线程上，没有跨进程锁。
>
> 要上多 worker，得先把复位从"启动即判僵尸"改成 owner/lease 或进程代次
> 判据 —— 那是架构级改动，记在 ARCH-1 backlog（"runner 体系整体
> multi-worker 化"，见 #238 裁定）。**在那之前，改这个数字会损坏在跑的
> 硬件测试。**

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build image
docker build -t meta3d-api .

# Run container
docker run -d -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/db \
  meta3d-api
```

## Troubleshooting

### Database Connection Issues

If you see "database_connected": false:

1. Check PostgreSQL is running: `docker ps` or `systemctl status postgresql`
2. Verify DATABASE_URL in `.env`
3. Check firewall rules for port 5432

### Import Errors

If you see ModuleNotFoundError:

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

## 数据初始化

首次运行或重置数据库后，跑 bootstrap 播种：

```bash
source .venv/bin/activate
python -m scripts.bootstrap
```

详细说明见 [`docs/Database-Operations-Guide.md`](../docs/Database-Operations-Guide.md)。

> ⚠️ **ARCH-1 S5（2026-07-30）更正**：本节原先写的是
> `python scripts/init_sequences.py`，会创建"6 个通用测试序列 + 8 个虚拟路测序列"。
> **那个脚本不存在**（早已并入 bootstrap），照着跑得到 `No such file or directory`；
> 那 14 条序列的 seeder 也随 ARCH-1 S4c 删除 —— 序列库整体拆除，`test_sequences`
> 表原地封存、只读历史。

## Support

For issues and questions, refer to:
- [数据架构指南](../docs/Data-Architecture-Guide.md) - Mock vs 后端 API 架构说明
- [系统校准设计](../docs/System-Calibration-Design.md) - 校准功能设计文档

## License

Proprietary - Meta-3D Project
