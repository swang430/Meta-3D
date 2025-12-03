# Phase 1 完整执行指南

## ✅ 已完成的工作（由Claude Code完成）

### 数据库模型 (100%)
- ✅ `api-service/app/models/probe.py`
- ✅ `api-service/app/models/instrument.py`

### Pydantic Schemas (100%)
- ✅ `api-service/app/schemas/probe.py`
- ✅ `api-service/app/schemas/instrument.py`
- ✅ `api-service/app/schemas/dashboard.py`

### API端点 (100%)
- ✅ `api-service/app/api/dashboard.py`
- ✅ `api-service/app/api/probe.py`
- ✅ `api-service/app/api/instrument.py`
- ✅ `api-service/app/api/monitoring.py`

---

## 🔧 需要手动完成的任务

### 任务 1: 创建初始化脚本目录
```bash
cd api-service
mkdir -p scripts
cd scripts
```

### 任务 2: 创建 `init_probes.py`
将以下内容保存为 `api-service/scripts/init_probes.py`：

```python
"""Initialize 32 dual-polarized probes"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.probe import Probe

def init_probes():
    """Initialize MPAC 32-probe array"""
    print("Initializing database...")
    init_db()

    db = SessionLocal()

    print("Clearing existing probes...")
    db.query(Probe).delete()

    probes = []
    probe_number = 1

    # Ring 1: 4 positions (0°, 90°, 180°, 270°)
    print("Creating Ring 1 probes...")
    for azimuth in [0, 90, 180, 270]:
        for pol in ["V", "H"]:
            probes.append(Probe(
                probe_number=probe_number,
                name=f"Probe {probe_number}-{pol}",
                ring=1,
                polarization=pol,
                position={"azimuth": azimuth, "elevation": 0, "radius": 1.5},
                is_active=True,
                is_connected=False,
                status="idle",
                calibration_status="unknown"
            ))
            probe_number += 1

    # Ring 2: 8 positions (45° increments)
    print("Creating Ring 2 probes...")
    for azimuth in range(0, 360, 45):
        for pol in ["V", "H"]:
            if probe_number > 32:
                break
            probes.append(Probe(
                probe_number=probe_number,
                name=f"Probe {probe_number}-{pol}",
                ring=2,
                polarization=pol,
                position={"azimuth": azimuth, "elevation": 0, "radius": 2.0},
                is_active=True,
                is_connected=False,
                status="idle",
                calibration_status="unknown"
            ))
            probe_number += 1

    db.add_all(probes[:32])  # Ensure exactly 32 probes
    db.commit()

    actual_count = db.query(Probe).count()
    print(f"✅ Successfully initialized {actual_count} probes")

    db.close()

if __name__ == "__main__":
    init_probes()
```

### 任务 3: 创建 `init_instruments.py`
将以下内容保存为 `api-service/scripts/init_instruments.py`：

```python
"""Initialize instrument categories and models"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.instrument import InstrumentCategory, InstrumentModel

def init_instruments():
    """Initialize instrument catalog"""
    print("Initializing database...")
    init_db()

    db = SessionLocal()

    print("Clearing existing instruments...")
    db.query(InstrumentModel).delete()
    db.query(InstrumentCategory).delete()

    # 1. Channel Emulator
    print("Creating Channel Emulator category...")
    channel_cat = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        category_name_en="Channel Emulator",
        description="用于模拟无线信道环境的MIMO信道仿真器",
        display_order=1
    )
    db.add(channel_cat)
    db.flush()

    db.add_all([
        InstrumentModel(
            category_id=channel_cat.id,
            vendor="Keysight",
            model="PROPSIM F64",
            full_name="Keysight PROPSIM F64 Channel Emulator",
            capabilities={
                "channels": 64,
                "bandwidth_mhz": 200,
                "frequency_range_ghz": [0.4, 6.0],
                "interfaces": ["LAN", "USB"]
            },
            display_order=1
        ),
        InstrumentModel(
            category_id=channel_cat.id,
            vendor="Spirent",
            model="VR5",
            full_name="Spirent VR5 Channel Emulator",
            capabilities={
                "channels": 32,
                "bandwidth_mhz": 100,
                "frequency_range_ghz": [0.7, 6.0],
                "interfaces": ["LAN"]
            },
            display_order=2
        )
    ])

    # 2. Base Station Emulator
    print("Creating Base Station category...")
    bs_cat = InstrumentCategory(
        category_key="baseStation",
        category_name="基站仿真器",
        category_name_en="Base Station Emulator",
        description="用于模拟5G/LTE基站的测试仪表",
        display_order=2
    )
    db.add(bs_cat)
    db.flush()

    db.add(InstrumentModel(
        category_id=bs_cat.id,
        vendor="Anritsu",
        model="MT8000A",
        full_name="Anritsu MT8000A Radio Communication Tester",
        capabilities={
            "bands": ["n77", "n78", "n79"],
            "max_bandwidth_mhz": 100,
            "technologies": ["5G NR", "LTE"]
        },
        display_order=1
    ))

    # 3. Turntable
    print("Creating Turntable category...")
    turntable_cat = InstrumentCategory(
        category_key="turntable",
        category_name="转台",
        category_name_en="Turntable/Positioner",
        description="用于旋转被测设备的转台系统",
        display_order=3
    )
    db.add(turntable_cat)
    db.flush()

    db.add(InstrumentModel(
        category_id=turntable_cat.id,
        vendor="CATR",
        model="AZ-EL Positioner",
        full_name="CATR AZ-EL Dual-Axis Positioner",
        capabilities={
            "axes": 2,
            "azimuth_range_deg": [0, 360],
            "elevation_range_deg": [-90, 90],
            "accuracy_deg": 0.1
        },
        display_order=1
    ))

    # 4. VNA
    print("Creating VNA category...")
    vna_cat = InstrumentCategory(
        category_key="vna",
        category_name="矢量网络分析仪",
        category_name_en="Vector Network Analyzer",
        description="用于S参数测量和射频分析",
        display_order=4
    )
    db.add(vna_cat)
    db.flush()

    db.add(InstrumentModel(
        category_id=vna_cat.id,
        vendor="Keysight",
        model="N5227B",
        full_name="Keysight N5227B PNA Microwave Network Analyzer",
        capabilities={
            "frequency_range_ghz": [0.01, 67],
            "ports": 4,
            "dynamic_range_db": 120
        },
        display_order=1
    ))

    db.commit()

    cat_count = db.query(InstrumentCategory).count()
    model_count = db.query(InstrumentModel).count()
    print(f"✅ Successfully initialized {cat_count} categories and {model_count} models")

    db.close()

if __name__ == "__main__":
    init_instruments()
```

### 任务 4: 更新 `main.py` 注册路由
在 `api-service/app/main.py` 中添加（在现有路由注册后）：

```python
# Import new API routers
from app.api import dashboard, probe, instrument, monitoring

# Register new routers
app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
app.include_router(probe.router, prefix="/api/v1", tags=["Probes"])
app.include_router(instrument.router, prefix="/api/v1", tags=["Instruments"])
app.include_router(monitoring.router, prefix="/api/v1", tags=["Monitoring"])
```

### 任务 5: 更新前端 API Client
修改 `gui/src/api/client.ts`，添加 baseURL：

```typescript
import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',  // 添加这一行
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ... 其余代码保持不变
export default client
```

### 任务 6: 更新数据库初始化
确保 `api-service/app/db/database.py` 中的 `init_db()` 函数导入了新模型：

在文件顶部添加：
```python
# 确保所有模型被导入，以便create_all()能找到它们
from app.models.probe import Probe, ProbeConfiguration
from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection, InstrumentLog
```

---

## 🚀 执行步骤

### Step 1: 创建初始化脚本
```bash
cd api-service
mkdir -p scripts
# 然后手动创建上述两个Python文件
```

### Step 2: 更新代码
- 更新 `main.py`（添加路由注册）
- 更新 `gui/src/api/client.ts`（添加baseURL）
- 更新 `database.py`（导入新模型）

### Step 3: 运行初始化脚本
```bash
cd api-service

# 初始化探头
python scripts/init_probes.py

# 初始化仪器
python scripts/init_instruments.py
```

### Step 4: 重启服务
```bash
# 重启后端
cd api-service
python -m app.main

# 重启前端（如果需要）
cd gui
npm run dev
```

### Step 5: 验证API
访问 `http://localhost:8001/docs` 检查新的API端点：
- ✅ GET `/api/v1/dashboard`
- ✅ GET `/api/v1/probes`
- ✅ GET `/api/v1/instruments/catalog`
- ✅ GET `/api/v1/monitoring/feeds`

### Step 6: 测试前端
访问 `http://localhost:5173`，检查：
- ✅ 主仪表盘显示真实的探头数量
- ✅ 探头配置页面显示32个探头
- ✅ 仪器配置页面显示仪器目录

---

## ✅ Phase 1 完成标志

当所有以下检查通过时，Phase 1即完成：

- [ ] 后端API文档显示所有新端点
- [ ] 探头初始化脚本成功运行（输出"✅ Successfully initialized 32 probes"）
- [ ] 仪器初始化脚本成功运行（输出"✅ Successfully initialized 4 categories and X models"）
- [ ] 前端主仪表盘不再显示空数据
- [ ] 探头配置页面可以查看和编辑32个探头
- [ ] 仪器配置页面可以选择仪器型号
- [ ] 所有API调用返回200而非404

---

## 📊 Phase 1 工作量总结

| 任务类型 | 已完成 | 待完成 | 预计时间 |
|----------|--------|--------|---------|
| 数据库模型 | 2/2 | 0 | ✅ |
| Schemas | 3/3 | 0 | ✅ |
| API端点 | 4/4 | 0 | ✅ |
| 初始化脚本 | 0/2 | 2 | 15分钟 |
| 代码集成 | 0/3 | 3 | 10分钟 |
| 测试验证 | 0/1 | 1 | 15分钟 |
| **总计** | **9/15** | **6/15** | **40分钟** |

---

## 🎯 下一步：Phase 2 预览

Phase 1完成后，我们将进入Phase 2：

**Phase 2: WebSocket 和实时监控** (预计2-3天)
- 实现WebSocket服务
- 实时数据推送
- 前端WebSocket Hook
- 仪器数据采集

**准备好后请告诉我，我们将开始Phase 2！**
