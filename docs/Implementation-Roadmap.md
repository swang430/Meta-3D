# ChannelEngine 集成实施路线图

## 📋 需求确认

根据讨论确认的技术方案：

✅ **技术方案**: Python 微服务架构
✅ **部署方式**:
  - 开发环境：本地运行
  - 生产环境：Docker 可选
✅ **优先级**: 先实现基础功能，再实现权重可视化

---

## 🎯 实施策略

### 分阶段交付原则

```
Phase 1: 核心功能 MVP (最小可行产品)
  ↓ 验证可行性，建立基础架构
Phase 2: 权重可视化增强
  ↓ 提升用户体验
Phase 3: 生产部署优化
  ↓ 性能优化、容器化
```

---

## 📅 Phase 1: 核心功能 MVP (2-3周)

### 目标
建立端到端的基础流程：场景 → ChannelEngine → OTA配置

### 里程碑

#### Week 1: Python 服务基础架构

**任务 1.1: ChannelEngine 环境搭建** (1-2天)
```bash
# 目标：验证 ChannelEngine 可运行
□ 克隆 ChannelEngine 仓库
□ 创建 Python 虚拟环境
□ 安装依赖
□ 运行 ChannelEngine 基础测试
□ 验证 3GPP 信道模型生成功能
```

**验收标准**:
```python
# 测试代码
from channel_model_38901.simulator import ChannelSimulator

simulator = ChannelSimulator(
    scenario_name='UMa',
    center_frequency_hz=3.5e9
)
results = simulator.run()
assert 'channel_matrix' in results
assert 'pathloss_db' in results
```

**任务 1.2: FastAPI 服务框架** (1-2天)
```bash
# 目标：搭建 REST API 基础框架
□ 创建 channel-engine-service 项目结构
□ 安装 FastAPI + Uvicorn
□ 实现健康检查端点 GET /api/v1/health
□ 配置 CORS（允许 Meta-3D 前端访问）
□ 添加基础错误处理
```

**交付物**:
```
channel-engine-service/
├── app/
│   ├── __init__.py
│   ├── main.py              ✅ FastAPI 应用入口
│   └── api/
│       ├── __init__.py
│       └── health.py        ✅ 健康检查路由
├── requirements.txt         ✅ 依赖清单
└── README.md               ✅ 启动文档
```

**验收标准**:
```bash
# 启动服务
uvicorn app.main:app --reload --port 8000

# 测试健康检查
curl http://localhost:8000/api/v1/health
# 预期返回: {"status": "healthy", "version": "1.0.0"}
```

**任务 1.3: ChannelEngine 封装服务** (2-3天)
```bash
# 目标：封装 ChannelEngine 为 Python 服务
□ 创建 ChannelEngineService 类
□ 实现 generate_channel() 方法
□ 实现 LSP 参数提取
□ 实现簇参数提取
□ 添加错误处理和日志
□ 单元测试
```

**交付物**:
```python
# app/services/channel_service.py
class ChannelEngineService:
    def generate_channel(
        self,
        scenario: str,          # 'UMa', 'UMi', 'RMa', 'InH'
        cluster_model: str,     # 'CDL-A', 'CDL-B', etc.
        frequency_hz: float,
        use_median_lsps: bool = False
    ) -> Dict:
        """生成3GPP信道模型"""
        # 返回: channel_matrix, pathloss_db, lsp, clusters
```

**验收标准**:
```python
service = ChannelEngineService()
result = service.generate_channel(
    scenario='UMa',
    cluster_model='CDL-C',
    frequency_hz=3.5e9,
    use_median_lsps=True
)
assert result['pathloss_db'] > 0
assert 'lsp' in result
assert 'clusters' in result
```

#### Week 2: 探头权重计算核心算法

**任务 2.1: 探头权重计算器** (3-4天)
```bash
# 目标：实现核心算法
□ 创建 ProbeWeightCalculator 类
□ 实现簇到探头方向匹配算法
□ 实现天线方向图模型（简化余弦模型）
□ 实现功率分配算法
□ 实现相位计算（基于时延）
□ V/H 极化权重分离
□ 单元测试（验证物理合理性）
```

**交付物**:
```python
# app/services/probe_calculator.py
class ProbeWeightCalculator:
    def calculate_weights(
        self,
        channel_matrix: np.ndarray,
        clusters: List[Dict],
        probe_positions: List[Dict],
        frequency_hz: float
    ) -> List[Dict]:
        """
        计算探头复数权重

        返回格式:
        [
          {"probeId": 1, "polarization": "V", "weight": {"magnitude": 0.85, "phase": 45.2}},
          {"probeId": 1, "polarization": "H", "weight": {"magnitude": 0.62, "phase": -12.8}},
          ...
        ]
        """
```

**验收标准**:
```python
calculator = ProbeWeightCalculator()
weights = calculator.calculate_weights(
    channel_matrix=channel_data['channel_matrix'],
    clusters=channel_data['clusters'],
    probe_positions=[...],  # 32探头位置
    frequency_hz=3.5e9
)
# 验证：
assert len(weights) == 64  # 32探头 × 2极化
assert all(0 <= w['weight']['magnitude'] <= 1 for w in weights)
assert all(-180 <= w['weight']['phase'] <= 180 for w in weights)
```

**任务 2.2: REST API 端点实现** (1-2天)
```bash
# 目标：完整的探头权重生成 API
□ 定义 Pydantic 数据模型（请求/响应）
□ 实现 POST /api/v1/ota/generate-probe-weights
□ 集成 ChannelEngineService
□ 集成 ProbeWeightCalculator
□ 错误处理和验证
□ API 文档（FastAPI 自动生成）
```

**交付物**:
```python
# app/api/routes.py
@router.post("/ota/generate-probe-weights")
def generate_probe_weights(request: ProbeWeightRequest):
    # 1. 生成信道模型
    # 2. 计算探头权重
    # 3. 返回结果
```

**验收标准**:
```bash
# 测试API
curl -X POST http://localhost:8000/api/v1/ota/generate-probe-weights \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": {"type": "UMa", "clusterModel": "CDL-C", "frequency": 3500},
    "probeArray": {"numProbes": 32, "radius": 3.0, "probePositions": [...]},
    "mimoConfig": {"numTxAntennas": 2, "numRxAntennas": 2}
  }'

# 预期返回: 64个探头权重（32 × 2极化）
```

#### Week 3: TypeScript 客户端集成

**任务 3.1: ChannelEngine 客户端** (1-2天)
```bash
# 目标：TypeScript HTTP 客户端
□ 创建 gui/src/services/roadTest/ChannelEngineClient.ts
□ 实现 generateProbeWeights() 方法
□ 实现 healthCheck() 方法
□ 错误处理和重试逻辑
□ TypeScript 类型定义
```

**交付物**:
```typescript
// gui/src/services/roadTest/ChannelEngineClient.ts
export class ChannelEngineClient {
  async generateProbeWeights(
    request: ProbeWeightRequest
  ): Promise<ProbeWeightResponse> {
    // HTTP POST 调用
  }

  async healthCheck(): Promise<boolean> {
    // 健康检查
  }
}
```

**验收标准**:
```typescript
const client = new ChannelEngineClient()
const isHealthy = await client.healthCheck()
assert(isHealthy === true)

const response = await client.generateProbeWeights({...})
assert(response.success === true)
assert(response.data.probeWeights.length === 64)
```

**任务 3.2: OTA 映射器基础集成** (2-3天)
```bash
# 目标：最简化的端到端流程
□ 修改 OTAScenarioMapper 集成 ChannelEngineClient
□ 实现基础的探头位置生成（32探头球形阵列）
□ 实现 ChannelEngine 调用
□ 实现权重数据接收和处理
□ 基础错误处理
□ 端到端测试
```

**交付物**:
```typescript
// gui/src/services/roadTest/OTAScenarioMapper.ts
export class OTAScenarioMapper {
  private channelEngine: ChannelEngineClient

  async map(scenario: RoadTestScenarioDetail): Promise<OTATestConfiguration> {
    // 1. 验证服务可用
    // 2. 生成探头位置
    // 3. 调用 ChannelEngine
    // 4. 处理权重数据
    // 5. 生成 OTA 配置
  }
}
```

**任务 3.3: 简单测试界面** (1天)
```bash
# 目标：验证端到端流程的最小 UI
□ 在 VirtualRoadTest 组件中添加测试按钮
□ 选择一个场景（如场景001）
□ 调用 OTA 映射器
□ 显示结果（成功/失败）
□ 显示基础信息（探头数量、权重范围）
```

**交付物**:
```typescript
// 简化的测试 UI
<Button onClick={async () => {
  const mapper = new OTAScenarioMapper()
  const config = await mapper.map(scenario001)
  console.log('OTA配置生成成功:', config)
  alert(`成功生成${config.probeArray.probes.length}个探头的权重`)
}}>
  测试 OTA 映射器
</Button>
```

### Phase 1 验收标准

**功能性验收**:
- [ ] Python 服务可独立运行（`uvicorn app.main:app`）
- [ ] 健康检查 API 响应正常
- [ ] 可成功调用 ChannelEngine 生成信道模型
- [ ] 可为32探头计算权重（64个数值）
- [ ] TypeScript 客户端可成功调用 Python 服务
- [ ] OTA 映射器可生成完整配置
- [ ] 端到端测试通过（场景 → OTA配置）

**性能验收**:
- [ ] 单次权重计算 < 5秒
- [ ] API 响应时间 < 10秒（含计算时间）

**文档验收**:
- [ ] Python 服务 README（如何启动）
- [ ] API 文档（FastAPI 自动生成）
- [ ] TypeScript 客户端使用示例
- [ ] 故障排除指南

---

## 🎨 Phase 2: 权重可视化增强 (1-2周)

### 目标
提升用户体验，直观展示探头权重分布

### 任务清单

**任务 2.1: 坐标转换工具** (1天)
```bash
□ 创建 gui/src/utils/coordinateConverter.ts
□ 实现球坐标 → 笛卡尔转换
□ 实现笛卡尔 → 球坐标转换
□ 实现位置字符串解析/格式化
□ 单元测试（精度验证）
```

**任务 2.2: 数据模型扩展** (1天)
```bash
□ 扩展 Probe 类型为 ProbeWithOTA
□ 添加 weight 可选字段
□ 添加 sphericalPosition 可选字段
□ 创建转换函数 convertOTAProbeToLegacyProbe()
```

**任务 2.3: ProbeLayoutView 增强** (2-3天)
```bash
□ 添加 showWeights 可选参数
□ 实现权重透明度可视化（magnitude → opacity）
□ 实现权重相位颜色编码（phase → hue）
□ 添加权重图例组件
□ 权重数值标签显示
□ 过渡动画效果
```

**任务 2.4: ProbeDetailPanel 组件** (2天)
```bash
□ 创建详情面板组件
□ 显示笛卡尔 + 球坐标
□ 显示权重幅度和相位
□ 显示复数形式
□ 添加极化信息
□ 添加使能状态指示
```

**任务 2.5: OTA 测试流程 UI** (2-3天)
```bash
□ 创建 OTATestFlow 组件
□ 步骤1: 场景选择
□ 步骤2: OTA 配置生成
□ 步骤3: 探头权重可视化（集成 ProbeLayoutView）
□ 步骤4: 配置导出（JSON）
□ 进度指示器
□ 错误处理和提示
```

### Phase 2 验收标准

**功能性验收**:
- [ ] 探头权重在可视化中以透明度表示
- [ ] 相位以颜色（色相）表示
- [ ] 点击探头显示详细参数
- [ ] 可导出带权重的 OTA 配置文件
- [ ] 支持多场景测试

**用户体验验收**:
- [ ] 可视化直观易懂
- [ ] 操作流程顺畅
- [ ] 错误信息清晰
- [ ] 响应速度快（< 1秒加载可视化）

---

## 🐳 Phase 3: 生产部署优化 (可选，1周)

### 目标
支持 Docker 容器化部署，适用于生产环境

### 任务清单

**任务 3.1: Python 服务 Docker 化** (1-2天)
```bash
□ 创建 Dockerfile（多阶段构建）
□ 优化镜像大小（使用 alpine 基础镜像）
□ 创建 .dockerignore
□ 配置环境变量
□ 健康检查配置
```

**任务 3.2: Docker Compose 编排** (1天)
```bash
□ 创建 docker-compose.yml
□ 配置 channel-engine 服务
□ 配置 meta-3d-frontend 服务
□ 配置网络和卷
□ 环境变量管理
```

**任务 3.3: 性能优化** (2-3天)
```bash
□ 实现结果缓存（相同参数复用结果）
□ 添加异步任务队列（长时间计算）
□ 批量处理优化
□ 数据库集成（可选，缓存持久化）
□ 性能监控和日志
```

**任务 3.4: 生产部署文档** (1天)
```bash
□ Docker 部署指南
□ 环境变量配置说明
□ 性能调优建议
□ 监控和日志配置
□ 故障排除
```

---

## 📊 总体时间规划

| 阶段 | 时长 | 关键交付物 | 优先级 |
|------|------|-----------|--------|
| **Phase 1** | 2-3周 | 端到端基础流程 | 🔴 必须 |
| **Phase 2** | 1-2周 | 权重可视化 UI | 🟡 推荐 |
| **Phase 3** | 1周 | Docker 部署 | 🟢 可选 |
| **总计** | 4-6周 | 完整功能系统 | |

---

## 🚀 立即行动计划（本周）

### Day 1-2: 环境准备
```bash
# 任务清单
□ 克隆 ChannelEngine 仓库
□ 安装 Python 3.10+ 环境
□ 安装 ChannelEngine 依赖
□ 运行 ChannelEngine 测试示例
□ 验证 3GPP 模型生成功能

# 验收
能够成功运行以下代码：
python
from channel_model_38901.simulator import ChannelSimulator
simulator = ChannelSimulator(scenario_name='UMa', center_frequency_hz=3.5e9)
results = simulator.run()
print(f"Pathloss: {results['pathloss_db']:.2f} dB")
```

### Day 3-4: FastAPI 服务框架
```bash
# 任务清单
□ 创建 channel-engine-service 项目
□ 安装 FastAPI, Uvicorn
□ 实现健康检查端点
□ 配置 CORS
□ 编写启动文档

# 验收
能够启动服务并访问：
http://localhost:8000/docs (FastAPI 自动文档)
http://localhost:8000/api/v1/health (健康检查)
```

### Day 5: 基础集成测试
```bash
# 任务清单
□ 封装 ChannelEngine 为服务类
□ 实现简单的测试端点
□ 验证端到端调用

# 验收
能够通过 API 调用 ChannelEngine：
curl -X POST http://localhost:8000/api/v1/test/generate-channel \
  -d '{"scenario": "UMa", "frequency": 3500000000}'
```

---

## 📋 检查清单

### 开发环境就绪检查
- [ ] Python 3.10+ 已安装
- [ ] Node.js 18+ 已安装
- [ ] Git 已配置
- [ ] ChannelEngine 仓库可访问
- [ ] Meta-3D 仓库已克隆

### 工具和库检查
- [ ] FastAPI 已安装
- [ ] Uvicorn 已安装
- [ ] NumPy/SciPy 已安装
- [ ] TypeScript 编译器工作正常
- [ ] Vite 开发服务器可启动

### 知识和技能检查
- [ ] 理解 3GPP 信道模型基础
- [ ] 熟悉 FastAPI 框架
- [ ] 熟悉 TypeScript/React
- [ ] 理解球坐标系统
- [ ] 理解 MIMO OTA 测试原理

---

## 🎯 成功标准

### Phase 1 成功标准（核心目标）
```
✅ 能够从虚拟路测场景生成 OTA 配置
✅ 能够为 32 探头计算权重
✅ TypeScript 前端可调用 Python 服务
✅ 端到端流程可演示
✅ 基础错误处理完善
```

### Phase 2 成功标准（增强目标）
```
✅ 探头权重可视化直观
✅ 用户可交互查看探头详情
✅ 配置可导出为文件
✅ UI/UX 流畅专业
```

### Phase 3 成功标准（生产目标）
```
✅ Docker 一键部署
✅ 性能满足生产需求（< 5秒响应）
✅ 生产部署文档完整
✅ 监控和日志完善
```

---

## 🔗 相关文档

- [ChannelEgine-Integration-Plan.md](./ChannelEgine-Integration-Plan.md) - 完整技术方案
- [ProbeLayoutView-Integration-Analysis.md](./ProbeLayoutView-Integration-Analysis.md) - UI 集成方案
- [Flexible-Probe-Array-Design.md](./Flexible-Probe-Array-Design.md) - 灵活探头配置设计

---

## 📞 支持和协作

### 需要帮助时
1. 查阅相关文档
2. 检查 ChannelEngine 仓库 Issues
3. 参考 FastAPI 官方文档
4. 回顾设计方案文档

### 进度同步
- 每周一次进度回顾
- 关键里程碑验收
- 及时沟通阻塞问题

---

**开始时间**: 当前周
**Phase 1 目标完成**: 2-3周后
**完整系统交付**: 4-6周后

准备好了就开始吧！🚀
