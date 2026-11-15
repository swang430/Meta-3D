# Channel Engine Service

基于 3GPP TR 38.901 的 OTA 探头权重计算微服务

## 功能

- **3GPP 信道模型**: 支持 UMa, UMi, RMa, InH 场景
- **混合模型**: 支持 CDL-A/B/C/D/E 和 TDL-A/B/C 簇模型
- **探头权重计算**: 基于信道 AoA/AoD 计算探头复数权重
- **灵活配置**: 支持 8-64 个探头，多种极化方式

## 安装

以下命令用于 macOS / Linux 本地开发，不是生产部署方案。从 `MIMO-First` 仓库根目录开始执行。完整系统还需要 API、前端和数据库，见[根目录安装说明](../README.md#-快速开始)。

### 1. 克隆外部引擎并导出路径

```bash
# 当前目录：MIMO-First 根目录；已有同级克隆时跳过 git clone
git clone https://github.com/swang430/ChannelEgine.git ../ChannelEgine
export CHANNEL_ENGINE_PATH="$(cd ../ChannelEgine && pwd)"
```

`CHANNEL_ENGINE_PATH` 是外部引擎克隆目录的绝对路径。请在启动服务的终端中导出，换终端后重新设置。服务通过该路径导入源码，不要求执行 `pip install -e`。

### 2. 安装服务和引擎依赖

```bash
# 仍在 MIMO-First 根目录，两个 requirements 使用同一个解释器安装
python3 -m venv channel-engine-service/.venv
channel-engine-service/.venv/bin/python -m pip install \
  -r channel-engine-service/requirements.txt \
  -r "$CHANNEL_ENGINE_PATH/requirements.txt"
```

虚拟环境必须位于 `channel-engine-service/.venv`，根目录的 `npm run dev:channel-engine` 使用的就是这个解释器。若已按根目录安装说明完成这一步，无需重复安装。

### 3. 扩展支持第三方射线跟踪 (Ray Tracing) 自定义 CDL
如果你希望引擎能够接受来自外部射线跟踪工具输出的任意 CDL 路况模型（非 3GPP 标准局限的簇参数），请遵循以下扩展步骤：

1. **引擎算法层扩展**：修改你本地克隆的 `ChannelEgine` 仓库中的模拟器代码（如追加 `CustomChannelSimulator`），直接对接接收形如 `[Delay, Power, AoA, ZoA, AoD, ZoD, XPR]` 阵列字典的底层实例化。修改完毕后，保持 `CHANNEL_ENGINE_PATH` 指向该克隆目录，并重启服务以重新加载源码。
2. **API 接口扩展**：在本仓库的 `app/models/ota_models.py` 中，为 `ScenarioConfig` 补充字典/列表类型，用以直接接收 JSON 格式的自定义射线矩阵数据；并在 `app/services/channel_engine.py` 内实现分支判断处理，如果是 `dict` 结构，则透传给原厂改写后的自定义算法计算器，完成自定义环境到探头的映射 (Spatial Mapping)。

## 配置

| 配置项 | 设置方式 | 说明 |
|---------|-----|------|
| `CHANNEL_ENGINE_PATH` | 在终端中 `export` | 外部 `ChannelEgine` 仓库的绝对路径 |
| 监听地址 | `uvicorn --host` | 下例使用 `127.0.0.1` |
| 监听端口 | `uvicorn --port` | 信道引擎服务标准端口为 `8001` |

当前服务入口未加载 `.env` 文件，也未读取 `HOST`、`PORT` 环境变量来设置监听地址。仅复制 `.env.example` 或设置这两个变量不会自动改变监听配置；请使用下面的显式启动参数。

## 运行

### 单独启动开发服务（自动重载）

在已导出 `CHANNEL_ENGINE_PATH` 的终端、`MIMO-First` 根目录执行：

```bash
(cd channel-engine-service && .venv/bin/python -m uvicorn app.main:app \
  --reload --host 127.0.0.1 --port 8001)
```

也可在根目录安装 npm 依赖后运行 `npm run dev:channel-engine`。该命令继承终端中的引擎路径，使用服务自己的虚拟环境；当前模块入口固定监听 `0.0.0.0:8001`，并开启自动重载。

同时启动完整开发系统，请先完成[根目录安装说明](../README.md#-快速开始)，然后在同一终端的根目录执行：

```bash
export USE_MOCK_INSTRUMENTS=true
npm run dev:all
```

完整开发系统使用 API `8000`、信道引擎服务 `8001`、前端 `5173`。这组命令用于开发，不是生产部署入口。

## API 文档

启动服务后访问:

- **Swagger UI**: http://localhost:8001/api/docs
- **ReDoc**: http://localhost:8001/api/redoc

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
const response = await fetch('http://localhost:8001/api/v1/ota/generate-probe-weights', {
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
