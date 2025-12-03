# 五大面板集成修复计划

## 📊 当前状态总览

| 面板 | 前端状态 | 后端API | 数据源 | 集成度 | 优先级 |
|------|---------|---------|--------|--------|--------|
| **主仪表盘** | ✅ 完整 | ❌ 缺失 | Mock | 0% | 🔴 P0 |
| **仪器资源配置** | ✅ 完整 | ❌ 缺失 | Mock | 0% | 🔴 P0 |
| **探头与暗室配置** | ✅ 完整 | ❌ 缺失 | Mock | 0% | 🔴 P0 |
| **实时监控** | ✅ 完整 | ❌ 缺失 | Mock WS | 0% | 🔴 P0 |
| **数据归档与报告** | ✅ 完整 | ⚠️ 部分 | Mock | 20% | 🟡 P1 |
| **测试管理** | ✅ 完整 | ✅ 完整 | SQLite | 100% | ✅ 完成 |
| **系统校准** | ✅ 完整 | ✅ 完整 | SQLite | 100% | ✅ 完成 |

---

## 🎯 三阶段修复计划

### Phase 1：API基础设施（1-2天）
**目标**：恢复基本功能，移除对Mock数据的依赖

#### 任务1.1：创建数据库模型
- [ ] **Probe模型** (`api-service/app/models/probe.py`)
  ```python
  class Probe(Base):
      __tablename__ = "probes"
      id: UUID
      ring: int          # 1-4
      polarization: str  # "V" | "H"
      position: JSON     # {azimuth, elevation, radius}
      is_active: bool
      calibration_date: datetime
      created_at: datetime
      updated_at: datetime
  ```

- [ ] **Instrument模型** (`api-service/app/models/instrument.py`)
  ```python
  class InstrumentCategory(Base):
      __tablename__ = "instrument_categories"
      id: UUID
      category_key: str  # "channelEmulator", "baseStation", etc.
      category_name: str
      selected_model_id: UUID

  class InstrumentModel(Base):
      __tablename__ = "instrument_models"
      id: UUID
      category_id: UUID
      vendor: str
      model: str
      capabilities: JSON  # {channels, bandwidth, interfaces, ...}

  class InstrumentConnection(Base):
      __tablename__ = "instrument_connections"
      id: UUID
      category_id: UUID
      endpoint: str
      controller_ip: str
      status: str  # "connected" | "disconnected" | "error"
      notes: str
  ```

- [ ] **DashboardMetrics模型** (可选，用于缓存)
  ```python
  class DashboardMetrics(Base):
      __tablename__ = "dashboard_metrics"
      id: UUID
      timestamp: datetime
      metrics: JSON
  ```

#### 任务1.2：实现后端API端点

**A. Dashboard API** (`api-service/app/api/dashboard.py`)
```python
@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    """
    返回：
    - summary: {probeCount, activePlans, activeAlerts, comparisonsSelected}
    - runningTasks: [{label, value, trend}]
    - activeAlerts: [{id, title, severity, timestamp}]
    """
    # 从数据库聚合数据
    probe_count = db.query(Probe).count()
    active_plans = db.query(TestPlan).filter(
        TestPlan.status.in_(['running', 'queued'])
    ).count()

    # TODO: 实现告警系统
    active_alerts = []

    return DashboardResponse(
        summary={...},
        runningTasks=[...],
        activeAlerts=[...]
    )
```

**B. Probe API** (`api-service/app/api/probe.py`)
```python
@router.get("/probes", response_model=List[ProbeResponse])
def get_probes(db: Session = Depends(get_db))

@router.post("/probes", response_model=ProbeResponse)
def create_probe(request: ProbeCreateRequest, db: Session = Depends(get_db))

@router.put("/probes/{probe_id}", response_model=ProbeResponse)
def update_probe(probe_id: UUID, request: ProbeUpdateRequest, db: Session = Depends(get_db))

@router.delete("/probes/{probe_id}", status_code=204)
def delete_probe(probe_id: UUID, db: Session = Depends(get_db))

@router.put("/probes/bulk", response_model=BulkProbeResponse)
def replace_probes(request: BulkProbeRequest, db: Session = Depends(get_db))
```

**C. Instrument API** (`api-service/app/api/instrument.py`)
```python
@router.get("/instruments/catalog", response_model=InstrumentCatalogResponse)
def get_instrument_catalog(db: Session = Depends(get_db))

@router.put("/instruments/{category_key}", response_model=InstrumentCategoryResponse)
def update_instrument_category(
    category_key: str,
    request: InstrumentUpdateRequest,
    db: Session = Depends(get_db)
)
```

**D. Monitoring API** (`api-service/app/api/monitoring.py`)
```python
@router.get("/monitoring/feeds", response_model=MonitoringFeedsResponse)
def get_monitoring_feeds(db: Session = Depends(get_db))
    """返回当前监控源和最新数据快照"""
```

#### 任务1.3：数据库迁移和初始化
- [ ] 创建Alembic迁移脚本
- [ ] 添加初始化种子数据脚本 (`scripts/init_probes.py`, `scripts/init_instruments.py`)
- [ ] 从Mock数据迁移到数据库

```python
# scripts/init_probes.py
"""Initialize 32 dual-polarized probes"""
probes = []
for ring in range(1, 5):
    for azimuth in range(0, 360, 45 if ring <= 2 else 30):
        for pol in ["V", "H"]:
            probes.append(Probe(
                ring=ring,
                polarization=pol,
                position={"azimuth": azimuth, "elevation": ..., "radius": ...},
                is_active=True
            ))
db.add_all(probes[:32])  # Limit to 32
db.commit()
```

#### 任务1.4：前端API服务更新
- [ ] 更新 `gui/src/api/service.ts`：添加`/api/v1`前缀
  ```typescript
  // 修改前
  export const fetchDashboard = () => client.get('/dashboard')

  // 修改后
  export const fetchDashboard = () => client.get('/api/v1/dashboard')
  ```

- [ ] 或者修改 `gui/src/api/client.ts` 的 baseURL：
  ```typescript
  const client = axios.create({
    baseURL: '/api/v1',  // 添加全局前缀
    // ...
  })
  ```

---

### Phase 2：WebSocket和实时数据（2-3天）
**目标**：实现真实的数据流推送

#### 任务2.1：WebSocket服务实现
```python
# api-service/app/api/monitoring.py
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/monitoring")
async def monitoring_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 从仪器采集数据
            data = await collect_monitoring_data()
            await websocket.send_json({
                "type": "metrics",
                "data": data,
                "timestamp": datetime.utcnow().isoformat()
            })
            await asyncio.sleep(1)  # 1秒推送一次
    except WebSocketDisconnect:
        logger.info("Client disconnected")
```

#### 任务2.2：前端WebSocket客户端
```typescript
// gui/src/hooks/useMonitoringWebSocket.ts
export function useMonitoringWebSocket() {
  const [metrics, setMetrics] = useState<MonitoringMetrics | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8001/ws/monitoring')

    ws.onopen = () => setIsConnected(true)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'metrics') {
        setMetrics(data.data)
      }
    }
    ws.onerror = () => setIsConnected(false)
    ws.onclose = () => setIsConnected(false)

    return () => ws.close()
  }, [])

  return { metrics, isConnected }
}
```

#### 任务2.3：数据采集服务
- [ ] 实现仪器HAL抽象层
- [ ] 创建数据采集后台任务
- [ ] 实现数据缓存和聚合

---

### Phase 3：高级功能完善（3-5天）
**目标**：报告生成、对比分析、高级可视化

#### 任务3.1：报告生成服务
```python
# api-service/app/services/report_service.py
class ReportService:
    def generate_test_report(self, execution_id: UUID) -> bytes:
        """生成PDF测试报告"""
        execution = db.query(TestExecution).get(execution_id)
        # 使用reportlab或weasyprint生成PDF
        return pdf_bytes

    def get_report_templates(self) -> List[ReportTemplate]:
        """返回可用的报告模板"""
        return [
            {"id": "standard", "name": "标准测试报告"},
            {"id": "detailed", "name": "详细分析报告"},
            {"id": "comparison", "name": "对比分析报告"}
        ]
```

#### 任务3.2：数据对比功能
- [ ] 实现多次执行的对比查询
- [ ] 生成对比图表数据
- [ ] 导出对比报告

#### 任务3.3：高级可视化
- [ ] ProbeLayoutView增强（使用Three.js）
- [ ] 实时波形图表（使用recharts或plotly）
- [ ] 热图和3D静区可视化

---

## 📁 新建文件清单

### 后端文件
```
api-service/
├── app/
│   ├── models/
│   │   ├── probe.py          [新建]
│   │   └── instrument.py     [新建]
│   ├── schemas/
│   │   ├── probe.py          [新建]
│   │   ├── instrument.py     [新建]
│   │   ├── dashboard.py      [新建]
│   │   └── monitoring.py     [新建]
│   ├── services/
│   │   ├── probe_service.py  [新建]
│   │   ├── instrument_service.py  [新建]
│   │   ├── dashboard_service.py   [新建]
│   │   ├── monitoring_service.py  [新建]
│   │   └── report_service.py      [新建]
│   └── api/
│       ├── dashboard.py      [新建]
│       ├── probe.py          [新建]
│       ├── instrument.py     [新建]
│       └── monitoring.py     [新建]
└── scripts/
    ├── init_probes.py        [新建]
    └── init_instruments.py   [新建]
```

### 前端文件（可选重构）
```
gui/src/
├── features/
│   ├── Dashboard/            [新建，从App.tsx抽离]
│   │   ├── DashboardView.tsx
│   │   ├── hooks/
│   │   └── api/
│   ├── ProbeConfiguration/   [新建，从App.tsx抽离]
│   │   ├── ProbeManager.tsx
│   │   ├── ProbeLayoutView.tsx
│   │   └── hooks/
│   ├── InstrumentConfiguration/  [新建]
│   ├── Monitoring/           [新建]
│   └── Reports/              [新建]
└── hooks/
    └── useMonitoringWebSocket.ts  [新建]
```

---

## 🔧 修改文件清单

### 后端
- [ ] `api-service/app/main.py` - 注册新的路由器
  ```python
  from app.api import dashboard, probe, instrument, monitoring

  app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
  app.include_router(probe.router, prefix="/api/v1", tags=["Probes"])
  app.include_router(instrument.router, prefix="/api/v1", tags=["Instruments"])
  app.include_router(monitoring.router, prefix="/api/v1", tags=["Monitoring"])
  ```

- [ ] `api-service/app/db/database.py` - 导入新模型
- [ ] `api/openapi.yaml` - 更新API规范

### 前端
- [ ] `gui/src/api/service.ts` - 添加`/api/v1`前缀或修改baseURL
- [ ] `gui/src/api/client.ts` - 配置全局API前缀
- [ ] `gui/src/main.tsx` - 移除Mock服务器配置（已完成）
- [ ] `gui/src/App.tsx` - （可选）重构为Feature模块

---

## 📊 实施时间表

| 阶段 | 任务 | 预计时间 | 开始日期 | 完成日期 |
|------|------|---------|---------|---------|
| **Phase 1** | 数据库模型 | 0.5天 | Day 1 | Day 1 |
| | Dashboard API | 0.5天 | Day 1 | Day 1 |
| | Probe API | 0.5天 | Day 2 | Day 2 |
| | Instrument API | 0.5天 | Day 2 | Day 2 |
| | 前端API更新 | 0.5天 | Day 2 | Day 2 |
| **Phase 2** | WebSocket实现 | 1天 | Day 3 | Day 3 |
| | 数据采集服务 | 1-2天 | Day 4 | Day 5 |
| **Phase 3** | 报告生成 | 1-2天 | Day 6 | Day 7 |
| | 对比分析 | 1天 | Day 7 | Day 7 |
| | 高级可视化 | 1-2天 | Day 8 | Day 9 |
| **总计** | | **8-10天** | | |

---

## 🎯 里程碑

### Milestone 1: 基础功能恢复（Phase 1完成）
- ✅ 所有面板不再显示404错误
- ✅ Dashboard显示真实的系统状态
- ✅ 探头配置可持久化
- ✅ 仪器配置可保存

### Milestone 2: 实时监控上线（Phase 2完成）
- ✅ WebSocket连接成功
- ✅ 实时数据流正常推送
- ✅ 波形和指标实时更新

### Milestone 3: 完整功能交付（Phase 3完成）
- ✅ PDF报告生成
- ✅ 多次执行对比分析
- ✅ 高级3D可视化

---

## 🚨 风险和依赖

### 技术风险
1. **WebSocket性能** - 多客户端并发连接
   - 缓解措施：实现连接池和数据广播
2. **数据采集延迟** - 仪器响应时间
   - 缓解措施：异步采集 + 缓存
3. **前端重构影响** - App.tsx过于庞大（5000+行）
   - 缓解措施：渐进式重构，保持向后兼容

### 依赖关系
- Phase 2 依赖 Phase 1 完成（需要数据库模型）
- Phase 3 依赖 Phase 1 & 2（需要完整的执行记录）

---

## 📝 测试计划

### 单元测试
- [ ] 数据库模型测试
- [ ] API端点测试（pytest + httpx）
- [ ] 服务层业务逻辑测试

### 集成测试
- [ ] 前后端API契约测试
- [ ] WebSocket连接测试
- [ ] 数据流端到端测试

### 手动测试清单
- [ ] Dashboard加载和刷新
- [ ] 探头CRUD操作
- [ ] 仪器配置保存和恢复
- [ ] 实时监控数据流
- [ ] 报告生成和下载
- [ ] 浏览器兼容性测试

---

## 🎓 开发指南

### 遵循现有架构模式

参考 **测试管理模块** 的成功实践：

1. **API优先架构**
   ```
   OpenAPI定义 → 后端实现 → 前端生成类型 → 前端调用
   ```

2. **三层架构**
   ```
   Controller (API端点) → Service (业务逻辑) → Model (数据库)
   ```

3. **前端Feature模块**
   ```
   Feature/
   ├── components/     # UI组件
   ├── hooks/          # TanStack Query hooks
   ├── api/            # API调用
   ├── types/          # TypeScript类型
   └── utils/          # 工具函数
   ```

### 代码风格
- 后端：遵循 `DATA-MODEL-GUIDE.md` 和 `API-DESIGN-GUIDE.md`
- 前端：遵循 `TestManagement-Unified-Architecture.md` 模式
- 命名：使用 RESTful 约定（复数名词、小写连字符）

---

## 🔍 参考资料

- [ARCHITECTURE-REVIEW.md](ARCHITECTURE-REVIEW.md) - 架构审查和重构计划
- [API-DESIGN-GUIDE.md](API-DESIGN-GUIDE.md) - API设计统一规范
- [DATA-MODEL-GUIDE.md](DATA-MODEL-GUIDE.md) - 数据模型设计规范
- [TestManagement-Unified-Architecture.md](TestManagement-Unified-Architecture.md) - 测试管理统一架构
- [AGENTS.md](AGENTS.md) - 系统架构和设计文档

---

## 📞 支持和协作

如遇到问题或需要讨论：
1. 参考现有的测试管理和系统校准模块实现
2. 查阅项目根目录的架构文档
3. 检查 `BUGFIX-LOG.md` 了解已知问题

**最后更新**: 2025-11-24
**文档版本**: v1.0
**负责人**: Development Team
