# ChannelEgine 与 Meta-3D 集成方案

## 📋 ChannelEgine 技术分析

### 项目概述

**仓库**: `swang430/ChannelEgine`
**语言**: Python 3.10+
**标准**: 3GPP TR 38.901 V19.0.0
**核心功能**: 5G及未来无线信道模型仿真

### 架构组成

```
ChannelEgine/
├── channel_model_38901/      # 核心库（可复用Python包）
│   ├── ChannelSimulator      # 用户顶层API
│   ├── ParameterLoader        # 标准参数管理
│   ├── ParameterTables        # 3GPP参数表
│   ├── ScenarioConfig         # 场景配置
│   └── ChannelGenerator       # 12步信道生成引擎
├── mimo_ota_simulator/        # MIMO OTA测试模拟器应用
│   ├── data_models.py         # 数据模型
│   ├── parsers.py             # 解析器
│   ├── simulator.py           # 模拟器核心
│   └── INTEGRATION_GUIDE.md   # 集成指南
└── system_simulator/          # 系统级仿真（规划中）
```

### 核心能力

#### 1. **3GPP 标准信道模型**
- **场景支持**: UMa（城市宏蜂窝）、UMi（城市微蜂窝）、RMa（农村宏蜂窝）、InH（室内热点）
- **簇模型**: CDL-A/B/C/D/E, TDL-A/B/C, SCME
- **频率范围**: 0.5 - 100 GHz

#### 2. **混合信道模型**（关键创新）
```python
# 混合模型：环境参数 + 确定性簇模型
simulator = ChannelSimulator(
    scenario_name='UMa',           # 大尺度环境（路径损耗、阴影衰落、LSP）
    cluster_model_name='CDL-A',    # 小尺度簇定义（时延、功率、角度）
    center_frequency_hz=3.5e9
)
results = simulator.run()
```

**物理意义**:
- `scenario_name` → 提供真实环境的路径损耗和LSP（大尺度参数）
- `cluster_model_name` → 提供标准化的多径簇结构（小尺度参数）
- 最终信道 = 路径损耗 × 阴影衰落 × 簇衰落

#### 3. **确定性LSP模式**
```python
simulator = ChannelSimulator(
    scenario_name='RMa',
    center_frequency_hz=0.7e9,
    use_median_lsps=True  # 使用中位数，避免随机性
)
```
用途：回归测试、标准一致性测试、可重复性验证

#### 4. **输出数据格式**
```python
results = {
    'channel_matrix': np.ndarray,  # 复数信道矩阵 H
    'pathloss_db': float,           # 路径损耗（dB）
    'lsp': {                        # 大尺度参数
        'ds': float,                  # RMS时延扩展（ns）
        'asd': float,                 # 到达角扩展（°）
        'asa': float,                 # 发射角扩展（°）
        # ...
    },
    'clusters': [{                  # 多径簇参数
        'delay': float,               # 时延（ns）
        'power': float,               # 功率（dB）
        'aoa': float,                 # 到达角（°）
        'aod': float,                 # 发射角（°）
        # ...
    }],
}
```

---

## 🔗 集成方案设计

### 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **A. Python微服务** | ✅ 零代码移植<br>✅ 复用ChannelEgine全部功能<br>✅ NumPy高性能 | ⚠️ 需部署Python服务<br>⚠️ 网络调用延迟 | ⭐⭐⭐⭐⭐ |
| **B. TypeScript重写** | ✅ 单一技术栈<br>✅ 无网络延迟 | ❌ 开发工作量大（数千行代码）<br>❌ 科学计算库弱<br>❌ 维护两套代码 | ⭐⭐ |
| **C. WebAssembly桥接** | ✅ 前端直接调用<br>✅ 无后端服务 | ❌ 浏览器加载Python运行时（体积大）<br>❌ 性能损失 | ⭐⭐⭐ |

**推荐**: **方案 A - Python 微服务架构**

---

## 🎯 方案 A：Python 微服务集成（推荐）

### 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                      Meta-3D Frontend                           │
│  ┌────────────────┐           ┌──────────────────────────────┐ │
│  │ React UI       │           │ OTA Scenario Mapper          │ │
│  │ (TypeScript)   │◄──────────│ (TypeScript)                 │ │
│  └────────────────┘           └──────────────────────────────┘ │
│         │                                  │                    │
│         │                                  │                    │
│         │                                  ▼                    │
│         │                      ┌──────────────────────────────┐ │
│         │                      │ ChannelEngine Client         │ │
│         │                      │ (TypeScript HTTP Client)     │ │
│         │                      └──────────────────────────────┘ │
│         │                                  │                    │
└─────────┼──────────────────────────────────┼────────────────────┘
          │                                  │
          │                                  ▼ HTTP POST (JSON)
          │                      ╔══════════════════════════════╗
          │                      ║  ChannelEngine Service       ║
          │                      ║  (Python FastAPI/Flask)      ║
          │                      ╚══════════════════════════════╝
          │                                  │
          │                      ┌───────────┴──────────┐
          │                      │                      │
          │               ┌──────▼─────┐      ┌────────▼──────┐
          │               │ Channel    │      │ OTA Probe     │
          │               │ Simulator  │      │ Weight Calc   │
          │               │ (38901)    │      │               │
          │               └────────────┘      └───────────────┘
          │                      │
          │               ┌──────▼────────────────────┐
          │               │ NumPy/SciPy 科学计算       │
          │               └───────────────────────────┘
          │
          ▼ WebSocket/SSE (Real-time)
┌─────────────────────────────────────────────────────────────────┐
│                     Probe Layout View                           │
│              (实时探头权重可视化 - 可选)                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📡 API 接口设计

### Endpoint 1: 生成探头权重

**POST** `/api/v1/ota/generate-probe-weights`

**Request Body**:
```json
{
  "scenario": {
    "type": "UMa",                    // 3GPP场景类型
    "clusterModel": "CDL-C",          // 簇模型
    "frequency": 3500,                // MHz
    "useMedianLSPs": false            // 是否使用确定性LSP
  },
  "probeArray": {
    "geometry": "spherical",          // 探头阵列几何（球形/柱形）
    "numProbes": 32,
    "radius": 3.0,                    // 米
    "probePositions": [               // 探头位置（球坐标）
      {"id": 1, "theta": 0, "phi": 90, "r": 3.0},
      {"id": 2, "theta": 45, "phi": 90, "r": 3.0},
      // ...
    ]
  },
  "mimoConfig": {
    "numTxAntennas": 2,
    "numRxAntennas": 2,
    "numLayers": 1
  },
  "vehicleTrajectory": {              // 可选：车辆轨迹
    "speed": 40,                       // km/h
    "duration": 600                    // 秒
  }
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "probeWeights": [
      {
        "probeId": 1,
        "polarization": "V",
        "weight": {
          "magnitude": 0.85,
          "phase": 45.2              // 度
        }
      },
      {
        "probeId": 1,
        "polarization": "H",
        "weight": {
          "magnitude": 0.62,
          "phase": -12.8
        }
      },
      // ... 64个权重（32探头 × 2极化）
    ],
    "channelStatistics": {
      "pathloss": 118.5,              // dB
      "rmsDelaySpread": 186,           // ns
      "maxDopplerShift": 129.72        // Hz
    },
    "fadingProfile": {
      "timeSeries": [                 // 时间序列衰落数据（可选）
        {
          "time": 0.0,
          "pathLoss": 118.5,
          "shadowFading": 2.3
        },
        // ...
      ]
    }
  }
}
```

### Endpoint 2: 生成衰落曲线

**POST** `/api/v1/ota/generate-fading-profile`

**Request Body**:
```json
{
  "scenario": "UMa",
  "clusterModel": "CDL-C",
  "frequency": 3500,
  "trajectory": {
    "waypoints": [
      {"time": 0, "x": 0, "y": 0, "z": 1.5},
      {"time": 10, "x": 100, "y": 50, "z": 1.5},
      // ...
    ]
  },
  "samplingRate": 1000                // Hz
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "timeSeries": [...],              // 时间序列数据
    "statistics": {
      "rmsDelaySpread": 186,
      "maxDopplerShift": 129.72,
      "riceanKFactor": null
    }
  }
}
```

### Endpoint 3: 健康检查

**GET** `/api/v1/health`

**Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "channelEngine": {
    "version": "1.0.0",
    "available": true
  }
}
```

---

## 💻 Python 服务实现

### 文件结构

```
channel-engine-service/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # API 路由
│   │   └── models.py            # Pydantic 数据模型
│   ├── services/
│   │   ├── __init__.py
│   │   ├── channel_service.py   # ChannelEgine 封装
│   │   └── probe_calculator.py  # 探头权重计算
│   └── utils/
│       ├── __init__.py
│       └── coordinate_converter.py  # 坐标转换工具
├── tests/
│   └── test_api.py
├── requirements.txt
├── Dockerfile
└── README.md
```

### 核心代码示例

#### `app/main.py` - FastAPI 入口

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

app = FastAPI(
    title="ChannelEngine Service",
    description="3GPP Channel Model & MIMO OTA Simulation API",
    version="1.0.0"
)

# CORS配置（允许Meta-3D前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Meta-3D dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "ChannelEngine Service is running"}
```

#### `app/services/channel_service.py` - ChannelEgine 封装

```python
import numpy as np
from channel_model_38901.simulator import ChannelSimulator
from typing import Dict, List, Optional

class ChannelEngineService:
    """封装ChannelEgine核心功能"""

    def __init__(self):
        self.simulator: Optional[ChannelSimulator] = None

    def generate_channel(
        self,
        scenario: str,
        cluster_model: Optional[str],
        frequency_hz: float,
        use_median_lsps: bool = False
    ) -> Dict:
        """
        生成信道模型

        Args:
            scenario: 场景类型 ('UMa', 'UMi', 'RMa', 'InH')
            cluster_model: 簇模型 ('CDL-A', 'CDL-B', 'CDL-C', etc.)
            frequency_hz: 中心频率（Hz）
            use_median_lsps: 是否使用确定性LSP

        Returns:
            信道参数字典
        """
        self.simulator = ChannelSimulator(
            scenario_name=scenario,
            cluster_model_name=cluster_model,
            center_frequency_hz=frequency_hz,
            use_median_lsps=use_median_lsps
        )

        results = self.simulator.run()

        return {
            'channel_matrix': results['channel_matrix'].tolist(),
            'pathloss_db': float(results['pathloss_db']),
            'lsp': self._extract_lsp(results),
            'clusters': self._extract_clusters(results)
        }

    def _extract_lsp(self, results: Dict) -> Dict:
        """提取大尺度参数"""
        return {
            'rmsDelaySpread': float(results.get('ds', 0)),
            'azimuthSpreadDeparture': float(results.get('asd', 0)),
            'azimuthSpreadArrival': float(results.get('asa', 0)),
            'zenithSpreadDeparture': float(results.get('zsd', 0)),
            'zenithSpreadArrival': float(results.get('zsa', 0)),
            'shadowFading': float(results.get('sf', 0)),
            'riceanKFactor': results.get('k_factor', None)
        }

    def _extract_clusters(self, results: Dict) -> List[Dict]:
        """提取多径簇参数"""
        clusters = []
        # 从results中提取簇信息
        # 这部分需要根据ChannelEgine的实际输出格式调整
        return clusters
```

#### `app/services/probe_calculator.py` - 探头权重计算

```python
import numpy as np
from typing import List, Dict, Tuple

class ProbeWeightCalculator:
    """探头权重计算器"""

    def calculate_weights(
        self,
        channel_matrix: np.ndarray,
        clusters: List[Dict],
        probe_positions: List[Dict],
        frequency_hz: float
    ) -> List[Dict]:
        """
        计算探头复数权重

        Args:
            channel_matrix: 信道矩阵 H
            clusters: 多径簇参数
            probe_positions: 探头位置（球坐标）
            frequency_hz: 频率

        Returns:
            探头权重列表
        """
        wavelength = 3e8 / frequency_hz  # λ = c/f

        probe_weights = []

        for probe in probe_positions:
            # 1. 计算探头方向与簇到达角的匹配度
            weight_v, weight_h = self._calculate_probe_weight(
                probe_theta=probe['theta'],
                probe_phi=probe['phi'],
                clusters=clusters,
                wavelength=wavelength
            )

            # 2. 添加V极化权重
            probe_weights.append({
                'probeId': probe['id'],
                'polarization': 'V',
                'weight': {
                    'magnitude': float(np.abs(weight_v)),
                    'phase': float(np.angle(weight_v, deg=True))
                }
            })

            # 3. 添加H极化权重
            probe_weights.append({
                'probeId': probe['id'],
                'polarization': 'H',
                'weight': {
                    'magnitude': float(np.abs(weight_h)),
                    'phase': float(np.angle(weight_h, deg=True))
                }
            })

        return probe_weights

    def _calculate_probe_weight(
        self,
        probe_theta: float,
        probe_phi: float,
        clusters: List[Dict],
        wavelength: float
    ) -> Tuple[complex, complex]:
        """
        计算单个探头的复数权重（V和H极化）

        基于空间角度匹配和功率分配
        """
        weight_v = 0 + 0j
        weight_h = 0 + 0j

        for cluster in clusters:
            # 到达角（AoA）
            aoa_azimuth = cluster['aoa']      # 方位角
            aoa_elevation = cluster['zoa']    # 仰角

            # 计算探头方向与簇到达角的夹角
            angle_diff = self._calculate_angle_difference(
                probe_theta, probe_phi,
                aoa_azimuth, aoa_elevation
            )

            # 天线方向图（简化为余弦模型）
            antenna_gain = max(0, np.cos(np.deg2rad(angle_diff)))

            # 簇功率（线性）
            cluster_power_linear = 10 ** (cluster['power'] / 10)

            # 相位（基于时延）
            phase = 2 * np.pi * cluster['delay'] * 1e-9 / wavelength

            # 累加权重（V极化）
            weight_v += np.sqrt(cluster_power_linear * antenna_gain) * np.exp(1j * phase)

            # H极化（简化：交叉极化比-20dB）
            weight_h += 0.1 * np.sqrt(cluster_power_linear * antenna_gain) * np.exp(1j * phase)

        return weight_v, weight_h

    def _calculate_angle_difference(
        self,
        theta1: float, phi1: float,
        theta2: float, phi2: float
    ) -> float:
        """计算球坐标系中两个方向的夹角"""
        # 转换为笛卡尔坐标
        x1 = np.sin(np.deg2rad(phi1)) * np.cos(np.deg2rad(theta1))
        y1 = np.sin(np.deg2rad(phi1)) * np.sin(np.deg2rad(theta1))
        z1 = np.cos(np.deg2rad(phi1))

        x2 = np.sin(np.deg2rad(phi2)) * np.cos(np.deg2rad(theta2))
        y2 = np.sin(np.deg2rad(phi2)) * np.sin(np.deg2rad(theta2))
        z2 = np.cos(np.deg2rad(phi2))

        # 点积计算夹角
        dot_product = x1*x2 + y1*y2 + z1*z2
        angle_rad = np.arccos(np.clip(dot_product, -1, 1))

        return np.rad2deg(angle_rad)
```

#### `app/api/routes.py` - API 路由

```python
from fastapi import APIRouter, HTTPException
from app.api.models import (
    ProbeWeightRequest,
    ProbeWeightResponse,
    HealthResponse
)
from app.services.channel_service import ChannelEngineService
from app.services.probe_calculator import ProbeWeightCalculator

router = APIRouter()
channel_service = ChannelEngineService()
probe_calculator = ProbeWeightCalculator()

@router.get("/health", response_model=HealthResponse)
def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "channelEngine": {
            "version": "1.0.0",
            "available": True
        }
    }

@router.post("/ota/generate-probe-weights", response_model=ProbeWeightResponse)
def generate_probe_weights(request: ProbeWeightRequest):
    """生成探头权重"""
    try:
        # 1. 生成信道模型
        channel_data = channel_service.generate_channel(
            scenario=request.scenario.type,
            cluster_model=request.scenario.clusterModel,
            frequency_hz=request.scenario.frequency * 1e6,  # MHz → Hz
            use_median_lsps=request.scenario.useMedianLSPs
        )

        # 2. 计算探头权重
        probe_weights = probe_calculator.calculate_weights(
            channel_matrix=channel_data['channel_matrix'],
            clusters=channel_data['clusters'],
            probe_positions=request.probeArray.probePositions,
            frequency_hz=request.scenario.frequency * 1e6
        )

        # 3. 返回结果
        return {
            "success": True,
            "data": {
                "probeWeights": probe_weights,
                "channelStatistics": {
                    "pathloss": channel_data['pathloss_db'],
                    "rmsDelaySpread": channel_data['lsp']['rmsDelaySpread'],
                    "maxDopplerShift": 0  # 需要根据车速计算
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 🔧 Meta-3D 集成实现

### TypeScript 客户端

#### `gui/src/services/roadTest/ChannelEngineClient.ts`

```typescript
/**
 * ChannelEngine Python服务客户端
 */

export interface ProbeWeightRequest {
  scenario: {
    type: 'UMa' | 'UMi' | 'RMa' | 'InH'
    clusterModel?: 'CDL-A' | 'CDL-B' | 'CDL-C' | 'CDL-D' | 'CDL-E'
    frequency: number  // MHz
    useMedianLSPs: boolean
  }
  probeArray: {
    geometry: 'spherical' | 'cylindrical'
    numProbes: number
    radius: number
    probePositions: Array<{
      id: number
      theta: number
      phi: number
      r: number
    }>
  }
  mimoConfig: {
    numTxAntennas: number
    numRxAntennas: number
    numLayers: number
  }
}

export interface ProbeWeightResponse {
  success: boolean
  data: {
    probeWeights: Array<{
      probeId: number
      polarization: 'V' | 'H'
      weight: {
        magnitude: number
        phase: number
      }
    }>
    channelStatistics: {
      pathloss: number
      rmsDelaySpread: number
      maxDopplerShift: number
    }
  }
}

export class ChannelEngineClient {
  private baseURL: string

  constructor(baseURL: string = 'http://localhost:8000/api/v1') {
    this.baseURL = baseURL
  }

  async generateProbeWeights(request: ProbeWeightRequest): Promise<ProbeWeightResponse> {
    const response = await fetch(`${this.baseURL}/ota/generate-probe-weights`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`ChannelEngine API error: ${response.statusText}`)
    }

    return response.json()
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseURL}/health`)
      const data = await response.json()
      return data.status === 'healthy'
    } catch {
      return false
    }
  }
}
```

#### OTA 映射器集成

```typescript
// gui/src/services/roadTest/OTAScenarioMapper.ts

import { ChannelEngineClient } from './ChannelEngineClient'

export class OTAScenarioMapper implements IScenarioMapper {
  private channelEngine: ChannelEngineClient

  constructor() {
    this.channelEngine = new ChannelEngineClient()
  }

  async map(scenario: RoadTestScenarioDetail): OTATestConfiguration {
    // 1. 验证ChannelEngine服务可用
    const isHealthy = await this.channelEngine.healthCheck()
    if (!isHealthy) {
      throw new Error('ChannelEngine服务不可用')
    }

    // 2. 准备探头位置（32探头球形阵列）
    const probePositions = this.generateProbePositions(32, 3.0)

    // 3. 调用ChannelEngine生成探头权重
    const channelResponse = await this.channelEngine.generateProbeWeights({
      scenario: {
        type: this.mapEnvironmentToScenario(scenario.environment.type),
        clusterModel: this.selectClusterModel(scenario.environment.type),
        frequency: scenario.networkConfig.frequency.dl,
        useMedianLSPs: false,
      },
      probeArray: {
        geometry: 'spherical',
        numProbes: 32,
        radius: 3.0,
        probePositions,
      },
      mimoConfig: {
        numTxAntennas: scenario.networkConfig.mimoConfig?.numTxAntennas || 2,
        numRxAntennas: scenario.networkConfig.mimoConfig?.numRxAntennas || 2,
        numLayers: scenario.networkConfig.mimoConfig?.numLayers || 1,
      },
    })

    // 4. 转换为OTA配置
    const probeArray = this.convertToProbeArrayConfig(
      channelResponse.data.probeWeights,
      probePositions
    )

    // 5. 生成完整配置
    return {
      channelEmulator: this.mapChannelEmulator(scenario, channelResponse.data),
      baseStationEmulator: this.mapBaseStationEmulator(scenario),
      probeArray,
      testSequence: this.generateTestSequence(scenario),
      kpiTargets: scenario.kpiTargets,
      metadata: {
        scenarioId: scenario.id,
        scenarioName: scenario.name,
        generatedAt: new Date().toISOString(),
        generatedBy: 'OTAScenarioMapper + ChannelEngine',
        estimatedDuration: this.estimate(scenario).estimatedDuration,
        requiredInstruments: ['Keysight E6952A', 'Keysight UXM'],
        mappingVersion: '2.0.0',
      },
    }
  }

  private generateProbePositions(
    numProbes: number,
    radius: number
  ): Array<{ id: number; theta: number; phi: number; r: number }> {
    const positions = []
    const azimuthStep = 360 / numProbes

    for (let i = 0; i < numProbes; i++) {
      positions.push({
        id: i + 1,
        theta: i * azimuthStep,
        phi: 90, // 水平面
        r: radius,
      })
    }

    return positions
  }

  private mapEnvironmentToScenario(
    envType: EnvironmentType
  ): 'UMa' | 'UMi' | 'RMa' | 'InH' {
    const mapping: Record<EnvironmentType, 'UMa' | 'UMi' | 'RMa' | 'InH'> = {
      [EnvironmentType.URBAN_MACRO]: 'UMa',
      [EnvironmentType.URBAN_MICRO]: 'UMi',
      [EnvironmentType.SUBURBAN]: 'UMi',
      [EnvironmentType.HIGHWAY]: 'RMa',
      [EnvironmentType.RURAL]: 'RMa',
      [EnvironmentType.INDOOR]: 'InH',
      [EnvironmentType.TUNNEL]: 'UMi', // 近似为UMi
    }
    return mapping[envType] || 'UMa'
  }

  private selectClusterModel(envType: EnvironmentType): string {
    const mapping: Record<EnvironmentType, string> = {
      [EnvironmentType.URBAN_MACRO]: 'CDL-C', // NLOS
      [EnvironmentType.URBAN_MICRO]: 'CDL-B', // Mixed
      [EnvironmentType.HIGHWAY]: 'CDL-D', // LOS
      [EnvironmentType.SUBURBAN]: 'CDL-D',
      [EnvironmentType.RURAL]: 'CDL-D',
      [EnvironmentType.TUNNEL]: 'CDL-A',
      [EnvironmentType.INDOOR]: 'CDL-A',
    }
    return mapping[envType] || 'CDL-C'
  }

  private convertToProbeArrayConfig(
    probeWeights: Array<{ probeId: number; polarization: string; weight: any }>,
    positions: Array<{ id: number; theta: number; phi: number; r: number }>
  ): ProbeArrayConfig {
    const probes: ProbeConfig[] = []

    positions.forEach((pos) => {
      // 找到该探头的V和H权重
      const vWeight = probeWeights.find(
        (w) => w.probeId === pos.id && w.polarization === 'V'
      )
      const hWeight = probeWeights.find(
        (w) => w.probeId === pos.id && w.polarization === 'H'
      )

      // V极化探头
      if (vWeight) {
        probes.push({
          id: pos.id * 2 - 1,
          position: { theta: pos.theta, phi: pos.phi, r: pos.r },
          polarization: 'V',
          weight: {
            magnitude: vWeight.weight.magnitude,
            phase: vWeight.weight.phase,
          },
          enabled: true,
        })
      }

      // H极化探头
      if (hWeight) {
        probes.push({
          id: pos.id * 2,
          position: { theta: pos.theta, phi: pos.phi, r: pos.r },
          polarization: 'H',
          weight: {
            magnitude: hWeight.weight.magnitude,
            phase: hWeight.weight.phase,
          },
          enabled: true,
        })
      }
    })

    return {
      geometry: 'spherical',
      radius: 3.0,
      probes,
    }
  }
}
```

---

## 🚀 部署方案

### 开发环境

#### 1. 启动 ChannelEngine 服务

```bash
# 克隆ChannelEgine仓库
git clone https://github.com/swang430/ChannelEgine.git
cd ChannelEgine

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
pip install -e ./channel_model_38901
pip install -e ./mimo_ota_simulator

# 安装FastAPI
pip install fastapi uvicorn

# 启动服务
cd channel-engine-service
uvicorn app.main:app --reload --port 8000
```

#### 2. 启动 Meta-3D 前端

```bash
cd Meta-3D/gui
npm install
npm run dev  # http://localhost:5173
```

#### 3. 验证集成

访问 http://localhost:5173 → 虚拟路测 → OTA测试

---

### 生产环境

#### Docker Compose 部署

```yaml
# docker-compose.yml
version: '3.8'

services:
  channel-engine:
    build: ./channel-engine-service
    ports:
      - "8000:8000"
    environment:
      - PYTHONUNBUFFERED=1
    volumes:
      - ./channel-engine-service:/app
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  meta-3d-frontend:
    build: ./Meta-3D/gui
    ports:
      - "5173:5173"
    environment:
      - VITE_CHANNEL_ENGINE_URL=http://channel-engine:8000
    depends_on:
      - channel-engine

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - channel-engine
      - meta-3d-frontend
```

---

## 📊 性能优化

### 1. 缓存机制

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def generate_channel_cached(
    scenario: str,
    cluster_model: str,
    frequency: int,
    use_median: bool
):
    """缓存相同参数的信道生成结果"""
    return channel_service.generate_channel(...)
```

### 2. 异步处理

```python
from fastapi import BackgroundTasks

@router.post("/ota/generate-probe-weights-async")
async def generate_probe_weights_async(
    request: ProbeWeightRequest,
    background_tasks: BackgroundTasks
):
    """异步生成探头权重（适用于长时间计算）"""
    task_id = str(uuid.uuid4())
    background_tasks.add_task(process_probe_weights, task_id, request)
    return {"task_id": task_id, "status": "processing"}
```

### 3. 批量处理

```python
@router.post("/ota/generate-batch")
def generate_batch(scenarios: List[RoadTestScenarioDetail]):
    """批量处理多个场景"""
    results = []
    for scenario in scenarios:
        result = generate_probe_weights(scenario)
        results.append(result)
    return results
```

---

## 🧪 测试验证

### 单元测试

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_generate_probe_weights():
    request = {
        "scenario": {
            "type": "UMa",
            "clusterModel": "CDL-C",
            "frequency": 3500,
            "useMedianLSPs": True
        },
        "probeArray": {
            "geometry": "spherical",
            "numProbes": 32,
            "radius": 3.0,
            "probePositions": [...]
        },
        "mimoConfig": {
            "numTxAntennas": 2,
            "numRxAntennas": 2,
            "numLayers": 1
        }
    }

    response = client.post("/api/v1/ota/generate-probe-weights", json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert len(data["data"]["probeWeights"]) == 64  # 32 probes × 2 polarizations
```

### 集成测试

```typescript
// gui/src/test/channelEngineIntegration.test.ts
import { ChannelEngineClient } from '../services/roadTest/ChannelEngineClient'

describe('ChannelEngine Integration', () => {
  const client = new ChannelEngineClient()

  it('should connect to ChannelEngine service', async () => {
    const isHealthy = await client.healthCheck()
    expect(isHealthy).toBe(true)
  })

  it('should generate probe weights', async () => {
    const response = await client.generateProbeWeights({
      scenario: {
        type: 'UMa',
        clusterModel: 'CDL-C',
        frequency: 3500,
        useMedianLSPs: true,
      },
      // ...
    })

    expect(response.success).toBe(true)
    expect(response.data.probeWeights.length).toBe(64)
  })
})
```

---

## 📋 实施计划

### Phase 1: Python 服务开发（1-2周）
- [ ] 搭建 FastAPI 项目框架
- [ ] 封装 ChannelEgine 核心功能
- [ ] 实现探头权重计算算法
- [ ] 编写 API 路由和数据模型
- [ ] 单元测试

### Phase 2: TypeScript 客户端（1周）
- [ ] 创建 ChannelEngineClient
- [ ] 集成到 OTAScenarioMapper
- [ ] 错误处理和重试逻辑
- [ ] 集成测试

### Phase 3: UI 集成（1周）
- [ ] 连接状态指示器
- [ ] 实时探头权重可视化
- [ ] 错误提示和降级方案
- [ ] 用户文档

### Phase 4: 部署与优化（1周）
- [ ] Docker 容器化
- [ ] 性能优化（缓存、批处理）
- [ ] 监控和日志
- [ ] 生产环境部署

---

## ✅ 总结

### 关键优势

1. ✅ **零代码移植**: 完全复用ChannelEgine的Python实现
2. ✅ **物理精确**: 基于3GPP TR 38.901标准
3. ✅ **灵活性**: 混合模型支持（环境 + 簇模型）
4. ✅ **可测试性**: 确定性LSP模式支持回归测试
5. ✅ **高性能**: NumPy矩阵运算优化

### 技术栈

- **后端**: Python 3.10+ + FastAPI + ChannelEgine
- **前端**: TypeScript + React + Vite
- **通信**: REST API (JSON)
- **部署**: Docker + Docker Compose

### 下一步行动

1. **立即**: 审查本集成方案，确认技术路线
2. **本周**: 搭建Python服务框架，实现健康检查API
3. **下周**: 实现探头权重计算，集成ChannelEgine
4. **第3周**: TypeScript客户端开发和集成
5. **第4周**: 完整端到端测试和文档
