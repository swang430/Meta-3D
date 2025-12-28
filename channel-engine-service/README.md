# Channel Engine Service

基于 3GPP TR 38.901 的 OTA 探头权重计算微服务

## 功能

- **3GPP 信道模型**: 支持 UMa, UMi, RMa, InH 场景
- **混合模型**: 支持 CDL-A/B/C/D/E 和 TDL-A/B/C 簇模型
- **探头权重计算**: 基于信道 AoA/AoD 计算探头复数权重
- **灵活配置**: 支持 8-64 个探头，多种极化方式

## 安装

### 1. 克隆并安装 ChannelEngine

```bash
# 克隆 ChannelEngine 仓库
git clone https://github.com/swang430/ChannelEgine.git
cd ChannelEgine

# 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
pip install -e ./mimo_ota_simulator
```

### 2. 配置环境变量

```bash
# 设置 ChannelEngine 路径（必需）
export CHANNEL_ENGINE_PATH=/path/to/your/ChannelEgine

# 或者创建 .env 文件
cp .env.example .env
# 编辑 .env 文件设置 CHANNEL_ENGINE_PATH
```

### 3. 安装服务依赖

```bash
cd ../channel-engine-service
# 使用与ChannelEgine相同的虚拟环境
source ../ChannelEgine/.venv/bin/activate
pip install -r requirements.txt
```

## 配置

| 环境变量 | 必需 | 说明 | 示例 |
|---------|-----|------|------|
| `CHANNEL_ENGINE_PATH` | 是 | ChannelEngine 仓库路径 | `/home/user/ChannelEgine` |
| `HOST` | 否 | 服务监听地址 | `0.0.0.0` |
| `PORT` | 否 | 服务监听端口 | `8001` |

## 运行

### 开发模式（自动重载）

```bash
# 确保设置了环境变量
export CHANNEL_ENGINE_PATH=/path/to/your/ChannelEgine

source ../ChannelEgine/.venv/bin/activate
python -m app.main
```

或使用 uvicorn:

```bash
CHANNEL_ENGINE_PATH=/path/to/ChannelEgine uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 生产模式

```bash
CHANNEL_ENGINE_PATH=/path/to/ChannelEgine uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API 文档

启动服务后访问:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

## API 端点

### 1. 健康检查

```http
GET /api/v1/health
```

**响应示例**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "channel_engine_available": true
}
```

### 2. 生成探头权重

```http
POST /api/v1/ota/generate-probe-weights
```

**请求示例**:
```json
{
  "scenario": {
    "scenario_type": "UMa",
    "cluster_model": "CDL-C",
    "frequency_mhz": 3500,
    "use_median_lsps": false
  },
  "probe_array": {
    "num_probes": 8,
    "radius": 3.0,
    "probe_positions": [
      {
        "probe_id": 1,
        "theta": 90,
        "phi": 0,
        "r": 3.0,
        "polarization": "V"
      },
      {
        "probe_id": 2,
        "theta": 90,
        "phi": 45,
        "r": 3.0,
        "polarization": "V"
      }
      // ... 更多探头
    ]
  },
  "mimo_config": {
    "num_tx_antennas": 2,
    "num_rx_antennas": 2,
    "tx_antenna_spacing": 0.5,
    "rx_antenna_spacing": 0.5
  }
}
```

**响应示例**:
```json
{
  "probe_weights": [
    {
      "probe_id": 1,
      "polarization": "V",
      "weight": {
        "magnitude": 0.85,
        "phase_deg": 45.2
      },
      "enabled": true
    }
    // ... 更多探头权重
  ],
  "channel_statistics": {
    "pathloss_db": 103.5,
    "rms_delay_spread_ns": 123.4,
    "angular_spread_deg": 15.2,
    "condition": "NLOS",
    "num_clusters": 20
  },
  "success": true,
  "message": "成功生成 8 个探头权重"
}
```

## 开发

### 项目结构

```
channel-engine-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── api/
│   │   ├── __init__.py
│   │   └── endpoints/
│   │       ├── __init__.py
│   │       ├── health.py    # 健康检查端点
│   │       └── ota.py       # OTA 权重计算端点
│   ├── models/
│   │   ├── __init__.py
│   │   └── ota_models.py    # Pydantic 数据模型
│   └── services/
│       ├── __init__.py
│       └── channel_engine.py  # ChannelEngine 封装
├── requirements.txt
└── README.md
```

### 测试

```bash
# 运行测试（待实现）
pytest
```

## 集成到 Meta-3D

在 Meta-3D 前端中调用此服务:

```typescript
// gui/src/services/channelEngine.ts
const response = await fetch('http://localhost:8000/api/v1/ota/generate-probe-weights', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(requestData)
})
const result = await response.json()
```

## 路线图

- [x] Phase 1.1: 基础服务框架
- [x] Phase 1.2: ChannelEngine 封装
- [x] Phase 1.3: 探头权重计算算法
- [ ] Phase 1.4: TypeScript 客户端
- [ ] Phase 2: 权重可视化增强
- [ ] Phase 3: Docker 部署（可选）

## 许可

与 Meta-3D 项目保持一致
