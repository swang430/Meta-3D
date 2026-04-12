# 校准系统实施计划

## 文档信息

- **创建日期**: 2026-01-15
- **状态**: 进行中
- **关联设计**:
  - [probe-calibration.md](./probe-calibration.md)
  - [channel-calibration.md](./channel-calibration.md)
  - [system-calibration.md](./system-calibration.md)

---

## 开发流程规范

### 每个任务的完成标准

```
┌─────────────────────────────────────────────────────────┐
│                    任务完成检查清单                       │
├─────────────────────────────────────────────────────────┤
│ □ 代码实现完成                                           │
│ □ 单元测试编写并通过                                      │
│ □ 测试覆盖率 > 80%                                       │
│ □ API 文档更新 (如适用)                                  │
│ □ 本文档状态更新                                         │
└─────────────────────────────────────────────────────────┘
```

### 文件命名规范

| 类型 | 路径 | 命名 |
|-----|------|------|
| 模型 | `api-service/app/models/` | `probe_calibration.py`, `channel_calibration.py` |
| Schema | `api-service/app/schemas/` | `probe_calibration.py`, `channel_calibration.py` |
| API | `api-service/app/api/` | `probe_calibration.py`, `channel_calibration.py` |
| 服务 | `api-service/app/services/` | `probe_calibration_service.py`, `channel_calibration_service.py` |
| 测试 | `api-service/tests/` | `test_probe_calibration.py`, `test_channel_calibration.py` |
| 前端 API | `gui/src/api/` | `probeCalibrationService.ts`, `channelCalibrationService.ts` |
| 前端组件 | `gui/src/components/` | `ProbeCalibration/`, `ChannelCalibration/` |

---

## 第一部分: 探头校准实现

### TASK-P01: 数据库模型

**状态**: ✅ 完成 (2026-01-15)

**文件**: `api-service/app/models/probe_calibration.py`

**实现内容**:
```python
# 需要创建的 SQLAlchemy 模型:
- ProbeAmplitudeCalibration  # 幅度校准记录
- ProbePhaseCalibration      # 相位校准记录
- ProbePolarizationCalibration  # 极化校准记录
- ProbePattern               # 方向图数据
- LinkCalibration            # 链路校准记录
- ProbeCalibrationValidity   # 有效性状态视图
```

**验收测试**:
```python
# 文件: api-service/tests/test_probe_calibration.py

def test_amplitude_calibration_model_fields():
    """验证 AmplitudeCalibration 模型包含所有必需字段"""
    required_fields = [
        'id', 'probe_id', 'polarization',
        'frequency_points_mhz', 'tx_gain_dbi', 'rx_gain_dbi',
        'tx_gain_uncertainty_db', 'rx_gain_uncertainty_db',
        'reference_antenna', 'reference_power_meter',
        'temperature_celsius', 'humidity_percent',
        'calibrated_at', 'calibrated_by',
        'valid_until', 'status'
    ]
    # 检查模型字段...

def test_amplitude_calibration_json_fields():
    """验证 JSONB 字段正确存储数组数据"""
    calibration = ProbeAmplitudeCalibration(
        frequency_points_mhz=[3300, 3400, 3500],
        tx_gain_dbi=[5.2, 5.3, 5.1],
        ...
    )
    # 验证 JSON 序列化/反序列化...

def test_phase_calibration_model_fields():
    """验证 PhaseCalibration 模型"""
    # ...

def test_calibration_validity_default_status():
    """验证新校准记录默认状态为 'valid'"""
    # ...
```

**完成检查**:
- [ ] 6 个模型类创建完成
- [ ] 数据库迁移脚本生成 (`alembic revision`)
- [ ] 迁移执行成功 (`alembic upgrade head`)
- [ ] 4 个模型测试通过
- [ ] 更新本文档状态

---

### TASK-P02: Pydantic Schemas

**状态**: ✅ 完成 (2026-01-15)

**依赖**: TASK-P01

**文件**: `api-service/app/schemas/probe_calibration.py`

**实现内容**:
```python
# Request schemas:
- StartAmplitudeCalibrationRequest
- StartPhaseCalibrationRequest
- StartPolarizationCalibrationRequest
- StartPatternCalibrationRequest
- StartLinkCalibrationRequest

# Response schemas:
- AmplitudeCalibrationResponse
- PhaseCalibrationResponse
- PolarizationCalibrationResponse
- PatternCalibrationResponse
- LinkCalibrationResponse
- ProbeCalibrationStatusResponse
- CalibrationValidityReportResponse
```

**验收测试**:
```python
def test_amplitude_request_validation():
    """验证请求参数验证"""
    # 有效请求
    valid_request = StartAmplitudeCalibrationRequest(
        probe_ids=[1, 2, 3],
        polarizations=['V', 'H'],
        frequency_range_mhz={'start': 3300, 'stop': 3800, 'step': 100}
    )
    assert valid_request.probe_ids == [1, 2, 3]

    # 无效请求 - 空探头列表
    with pytest.raises(ValidationError):
        StartAmplitudeCalibrationRequest(probe_ids=[])

def test_amplitude_response_serialization():
    """验证响应正确序列化"""
    # ...

def test_frequency_range_validation():
    """验证频率范围参数"""
    # start < stop
    # step > 0
    # ...
```

**完成检查**:
- [ ] 12 个 schema 类创建完成
- [ ] 请求验证测试通过
- [ ] 响应序列化测试通过
- [ ] 更新本文档状态

---

### TASK-P03: 幅度校准 API

**状态**: ✅ 完成 (2026-01-15)

**依赖**: TASK-P01, TASK-P02

**文件**: `api-service/app/api/probe_calibration.py`

**实现端点**:
```
POST /api/v1/calibration/probe/amplitude/start    # ✅ 已实现
     启动幅度校准任务 (mock 实现，直接完成)

GET  /api/v1/calibration/probe/amplitude/{probe_id}    # ✅ 已实现
     获取探头的幅度校准数据

GET  /api/v1/calibration/probe/amplitude/{probe_id}/history    # ✅ 已实现
     获取校准历史

GET  /api/v1/calibration/probe/validity/{probe_id}    # ✅ 额外实现
     获取探头有效性状态

GET  /api/v1/calibration/probe/validity/report    # ✅ 额外实现
     获取整体有效性报告
```

**验收测试结果**: 17 个测试全部通过
- TestAmplitudeCalibrationStart: 3 测试
- TestAmplitudeCalibrationGet: 4 测试
- TestAmplitudeCalibrationHistory: 3 测试
- TestValidityStatus: 3 测试
- TestNotYetImplementedEndpoints: 4 测试 (返回 501)

**完成检查**:
- [x] 5 个端点实现 (超出预期)
- [x] 17 个 API 测试通过
- [x] 未实现端点返回 501 并标注后续任务
- [x] 更新本文档状态

---

### TASK-P04: 幅度校准服务层

**状态**: ✅ 完成 (2026-01-15)

**依赖**: TASK-P03

**文件**: `api-service/app/services/probe_calibration_service.py`

**实现内容**:
- `AmplitudeCalibrationService` - 幅度校准服务类
- `CalibrationValidityService` - 有效性管理服务
- 算法函数:
  - `calculate_gain_from_power()` - 增益计算
  - `calculate_path_loss()` - Friis 路径损耗计算
  - `calculate_uncertainty()` - GUM 不确定度计算
  - `verify_reciprocity()` - 互易性验证
  - `generate_frequency_points()` - 频率点生成
- 数据类:
  - `GainMeasurement` - 增益测量结果
  - `CalibrationResult` - 校准结果

**验收测试结果**: 32 个测试全部通过
- TestGainCalculation: 3 测试
- TestPathLossCalculation: 4 测试
- TestUncertaintyCalculation: 3 测试
- TestReciprocityVerification: 4 测试
- TestGainMeasurement: 4 测试
- TestFrequencyPointGeneration: 2 测试
- TestAmplitudeCalibrationService: 5 测试
- TestCalibrationValidityService: 5 测试
- TestTrendAnalysis: 2 测试

**完成检查**:
- [x] 服务类实现 (AmplitudeCalibrationService + CalibrationValidityService)
- [x] 增益计算公式测试通过 (Friis, 功率转换)
- [x] 互易性验证测试通过 (阈值 0.5 dB)
- [x] 不确定度计算测试通过 (GUM 方法)
- [x] 32 个服务层测试全部通过
- [x] 更新本文档状态

---

### TASK-P05: 相位校准 API + 服务

**状态**: ⏳ 待开始

**依赖**: TASK-P04

**文件**:
- `api-service/app/api/probe_calibration.py` (追加)
- `api-service/app/services/probe_calibration_service.py` (追加)

**实现端点**:
```
POST /api/v1/calibration/probe/phase/start
GET  /api/v1/calibration/probe/phase/{probe_id}
```

**实现服务**:
```python
class ProbePhaseCalibrationService:
    def calculate_phase_offset(
        self,
        s21_phase_deg: float,
        reference_phase_deg: float
    ) -> float:
        """计算相位偏差 (归一化到 -180° ~ 180°)"""

    def calculate_group_delay(
        self,
        frequency_hz: List[float],
        phase_deg: List[float]
    ) -> List[float]:
        """计算群时延: τ = -dφ/dω"""

    def extract_from_touchstone(
        self,
        s2p_file_path: str
    ) -> Tuple[List[float], List[float], List[float]]:
        """从 Touchstone .s2p 文件提取 S21 幅度和相位"""
```

**验收测试**:
```python
class TestPhaseCalibrationService:

    def test_phase_offset_normalization(self):
        """验证相位偏差归一化到 -180° ~ 180°"""
        service = ProbePhaseCalibrationService()

        # 正常范围
        assert service.calculate_phase_offset(45, 10) == 35

        # 跨越 180° 边界
        assert service.calculate_phase_offset(350, 10) == -20  # 350 - 10 = 340 -> -20

        # 负相位
        assert service.calculate_phase_offset(-30, 10) == -40

    def test_group_delay_calculation(self):
        """验证群时延计算"""
        service = ProbePhaseCalibrationService()

        # τ = -dφ/dω = -dφ/(2π·df)
        # 假设相位线性变化: φ = -36° @ 3.3GHz, φ = -72° @ 3.5GHz
        # dφ = -36°, df = 200MHz
        # τ = -(-36°)/(360° × 200MHz) = 0.5 ns

        freq_hz = [3.3e9, 3.5e9]
        phase_deg = [-36, -72]
        delays = service.calculate_group_delay(freq_hz, phase_deg)
        assert abs(delays[0] - 0.5e-9) < 1e-11  # 0.5 ns

    def test_touchstone_parsing(self):
        """测试 Touchstone 文件解析"""
        # 使用测试 fixture 文件
```

**完成检查**:
- [ ] 相位校准 API 实现
- [ ] 相位偏差归一化测试通过
- [ ] 群时延计算测试通过
- [ ] Touchstone 解析测试通过
- [ ] 更新本文档状态

---

### TASK-P06: 极化校准 API + 服务

**状态**: ⏳ 待开始

**依赖**: TASK-P05

**实现端点**:
```
POST /api/v1/calibration/probe/polarization/start
GET  /api/v1/calibration/probe/polarization/{probe_id}
```

**实现服务**:
```python
class ProbePolarizationCalibrationService:
    def calculate_xpd(
        self,
        co_pol_power_dbm: float,
        cross_pol_power_dbm: float
    ) -> float:
        """计算交叉极化隔离度 XPD = P_co - P_cross (dB)"""

    def calculate_axial_ratio(
        self,
        power_vs_angle: List[Tuple[float, float]]  # [(angle_deg, power_dbm), ...]
    ) -> float:
        """计算轴比 AR = 20·log10((P_max + P_min) / (P_max - P_min))"""

    def validate_polarization(
        self,
        xpd_db: float,
        min_xpd_db: float = 20.0
    ) -> bool:
        """验证极化纯度是否满足要求"""
```

**验收测试**:
```python
class TestPolarizationCalibrationService:

    def test_xpd_calculation(self):
        """验证 XPD 计算"""
        service = ProbePolarizationCalibrationService()
        # XPD = P_co - P_cross = -20 - (-45) = 25 dB
        assert service.calculate_xpd(-20, -45) == 25

    def test_axial_ratio_perfect_circular(self):
        """验证完美圆极化的轴比接近 0 dB"""
        service = ProbePolarizationCalibrationService()
        # 完美圆极化: 所有角度功率相同
        power_vs_angle = [(i, -30.0) for i in range(0, 360, 10)]
        ar = service.calculate_axial_ratio(power_vs_angle)
        assert ar < 0.1  # 接近 0 dB

    def test_axial_ratio_elliptical(self):
        """验证椭圆极化的轴比计算"""
        # P_max = -25 dBm, P_min = -30 dBm
        # AR = 20·log10((10^(-2.5) + 10^(-3)) / (10^(-2.5) - 10^(-3)))
        # ...
```

**完成检查**:
- [ ] 极化校准 API 实现
- [ ] XPD 计算测试通过
- [ ] 轴比计算测试通过
- [ ] 更新本文档状态

---

### TASK-P07: 方向图校准 API + 服务

**状态**: ⏳ 待开始

**依赖**: TASK-P06

**实现端点**:
```
POST /api/v1/calibration/probe/pattern/start
GET  /api/v1/calibration/probe/pattern/{probe_id}
GET  /api/v1/calibration/probe/pattern/{probe_id}/frequencies
```

**实现服务**:
```python
class ProbePatternCalibrationService:
    def extract_pattern_parameters(
        self,
        gain_pattern_dbi: List[List[float]],
        azimuth_deg: List[float],
        elevation_deg: List[float]
    ) -> PatternParameters:
        """提取方向图参数: 峰值增益、主瓣方向、HPBW、前后比"""

    def calculate_hpbw(
        self,
        gain_vs_angle: List[Tuple[float, float]]
    ) -> float:
        """计算半功率波束宽度"""

    def validate_far_field_distance(
        self,
        probe_size_m: float,
        frequency_hz: float,
        measurement_distance_m: float
    ) -> bool:
        """验证是否满足远场条件: R > 2D²/λ"""
```

**验收测试**:
```python
class TestPatternCalibrationService:

    def test_peak_gain_extraction(self):
        """验证峰值增益提取"""
        # 给定方向图数据，找到最大值

    def test_hpbw_calculation(self):
        """验证 HPBW 计算"""
        # 给定 [-3, -2, 0, -2, -3] dB @ [0, 10, 20, 30, 40]°
        # HPBW 应该约为 40°

    def test_far_field_validation(self):
        """验证远场条件检查"""
        service = ProbePatternCalibrationService()
        # f = 3.5 GHz, λ = 0.086 m, D = 0.1 m
        # R_min = 2 × 0.1² / 0.086 = 0.23 m

        assert service.validate_far_field_distance(0.1, 3.5e9, 1.0) == True
        assert service.validate_far_field_distance(0.1, 3.5e9, 0.1) == False
```

**完成检查**:
- [ ] 方向图校准 API 实现
- [ ] 峰值增益提取测试通过
- [ ] HPBW 计算测试通过
- [ ] 远场条件验证测试通过
- [ ] 更新本文档状态

---

### TASK-P08: 链路校准 API + 服务

**状态**: ⏳ 待开始

**依赖**: TASK-P07

**实现端点**:
```
POST /api/v1/calibration/probe/link/start
GET  /api/v1/calibration/probe/link
GET  /api/v1/calibration/probe/link/latest
```

**实现服务**:
```python
class LinkCalibrationService:
    def execute_quick_check(
        self,
        standard_dut: StandardDUT,
        probe_ids: List[int]
    ) -> LinkCalibrationResult:
        """执行快速链路校准检查"""

    def calculate_link_deviation(
        self,
        measured_gain_dbi: float,
        known_gain_dbi: float
    ) -> float:
        """计算链路偏差"""

    def validate_link_calibration(
        self,
        deviation_db: float,
        threshold_db: float = 1.0
    ) -> bool:
        """验证链路校准是否合格"""
```

**验收测试**:
```python
class TestLinkCalibrationService:

    def test_link_deviation_calculation(self):
        """验证链路偏差计算"""
        service = LinkCalibrationService()
        # 测量 5.2 dBi, 已知 5.0 dBi -> 偏差 0.2 dB
        assert service.calculate_link_deviation(5.2, 5.0) == 0.2

    def test_link_validation_pass(self):
        """验证链路校准通过"""
        service = LinkCalibrationService()
        assert service.validate_link_calibration(0.5, threshold_db=1.0) == True

    def test_link_validation_fail(self):
        """验证链路校准失败"""
        service = LinkCalibrationService()
        assert service.validate_link_calibration(1.5, threshold_db=1.0) == False
```

**完成检查**:
- [ ] 链路校准 API 实现
- [ ] 偏差计算测试通过
- [ ] 验证逻辑测试通过
- [ ] 更新本文档状态

---

### TASK-P09: 有效性管理 API

**状态**: ⏳ 待开始

**依赖**: TASK-P08

**实现端点**:
```
GET  /api/v1/calibration/validity/report
GET  /api/v1/calibration/validity/expiring?days=7
POST /api/v1/calibration/validity/invalidate/{calibration_id}
```

**验收测试**:
```python
class TestCalibrationValidityAPI:

    def test_get_validity_report(self, client, db, seed_calibrations):
        """测试获取有效性报告"""
        response = client.get("/api/v1/calibration/validity/report")
        assert response.status_code == 200
        data = response.json()
        assert "total_probes" in data
        assert "valid_probes" in data
        assert "expired_probes" in data

    def test_get_expiring_calibrations(self, client, db):
        """测试获取即将过期的校准"""
        response = client.get("/api/v1/calibration/validity/expiring?days=7")
        assert response.status_code == 200

    def test_invalidate_calibration(self, client, db, seed_calibration):
        """测试手动作废校准"""
        response = client.post(
            f"/api/v1/calibration/validity/invalidate/{seed_calibration.id}"
        )
        assert response.status_code == 200
        # 验证状态变为 'invalidated'
```

**完成检查**:
- [ ] 有效性 API 实现
- [ ] 报告查询测试通过
- [ ] 过期查询测试通过
- [ ] 作废操作测试通过
- [ ] 更新本文档状态

---

### TASK-P10: 探头校准集成测试

**状态**: ⏳ 待开始

**依赖**: TASK-P09

**文件**: `api-service/tests/integration/test_probe_calibration_flow.py`

**测试场景**:
```python
class TestProbeCalibrationIntegration:

    @pytest.mark.integration
    def test_complete_calibration_flow(self, client, db, mock_instruments):
        """测试完整校准流程: 幅度 → 相位 → 链路"""

        # Step 1: 启动幅度校准
        amp_response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={"probe_ids": [1], "polarizations": ["V"], ...}
        )
        assert amp_response.status_code == 201
        amp_job_id = amp_response.json()["calibration_job_id"]

        # Step 2: 等待幅度校准完成
        await_job_completion(client, amp_job_id, timeout=60)

        # Step 3: 验证幅度校准数据已保存
        amp_data = client.get("/api/v1/calibration/probe/amplitude/1")
        assert amp_data.status_code == 200
        assert amp_data.json()["status"] == "valid"

        # Step 4: 启动相位校准
        phase_response = client.post(
            "/api/v1/calibration/probe/phase/start",
            json={"probe_ids": [1], ...}
        )
        assert phase_response.status_code == 201

        # Step 5: 等待相位校准完成
        phase_job_id = phase_response.json()["calibration_job_id"]
        await_job_completion(client, phase_job_id, timeout=60)

        # Step 6: 执行链路校准验证
        link_response = client.post(
            "/api/v1/calibration/probe/link/start",
            json={"calibration_type": "pre_test", ...}
        )
        assert link_response.status_code == 201

        # Step 7: 验证有效性报告
        validity = client.get("/api/v1/calibration/validity/report")
        assert validity.json()["valid_probes"] >= 1

    @pytest.mark.integration
    def test_calibration_expiry_flow(self, client, db):
        """测试校准过期流程"""
        # 创建即将过期的校准记录
        # 验证出现在 expiring 列表中
        # 手动作废
        # 验证状态更新
```

**完成检查**:
- [ ] 完整流程集成测试通过
- [ ] 过期流程测试通过
- [ ] 更新本文档状态

---

### TASK-P11: 探头校准前端 API 客户端

**状态**: ⏳ 待开始

**依赖**: TASK-P10

**文件**: `gui/src/api/probeCalibrationService.ts`

**实现内容**:
```typescript
// API 客户端函数
export const probeCalibrationService = {
  // 幅度校准
  startAmplitudeCalibration: (request: StartAmplitudeCalibrationRequest) => Promise<CalibrationJobResponse>,
  getAmplitudeCalibration: (probeId: number) => Promise<AmplitudeCalibrationResponse>,

  // 相位校准
  startPhaseCalibration: (request: StartPhaseCalibrationRequest) => Promise<CalibrationJobResponse>,
  getPhaseCalibration: (probeId: number) => Promise<PhaseCalibrationResponse>,

  // 极化校准
  startPolarizationCalibration: (request) => Promise<CalibrationJobResponse>,
  getPolarizationCalibration: (probeId: number) => Promise<PolarizationCalibrationResponse>,

  // 方向图校准
  startPatternCalibration: (request) => Promise<CalibrationJobResponse>,
  getPatternCalibration: (probeId: number, frequencyMhz?: number) => Promise<PatternCalibrationResponse>,

  // 链路校准
  startLinkCalibration: (request) => Promise<CalibrationJobResponse>,
  getLatestLinkCalibration: () => Promise<LinkCalibrationResponse>,

  // 有效性管理
  getValidityReport: () => Promise<ValidityReportResponse>,
  getExpiringCalibrations: (days: number) => Promise<ExpiringCalibration[]>,
  invalidateCalibration: (calibrationId: string) => Promise<void>,
}
```

**完成检查**:
- [ ] 所有 API 函数实现
- [ ] TypeScript 类型定义完整
- [ ] 与后端 API 联调通过
- [ ] 更新本文档状态

---

### TASK-P12: 探头校准 UI 组件

**状态**: ⏳ 待开始

**依赖**: TASK-P11

**文件**:
- `gui/src/components/ProbeCalibration/ProbeCalibrationDashboard.tsx`
- `gui/src/components/ProbeCalibration/ProbeCalibrationWizard.tsx`
- `gui/src/components/ProbeCalibration/CalibrationStatusBadge.tsx`
- `gui/src/components/ProbeCalibration/CalibrationValidityTable.tsx`

**完成检查**:
- [ ] Dashboard 组件实现
- [ ] Wizard 组件实现 (多步骤向导)
- [ ] StatusBadge 组件实现
- [ ] ValidityTable 组件实现
- [ ] 与后端 API 联调通过
- [ ] 更新本文档状态

---

## 第二部分: 信道校准实现

### TASK-C01: 数据库模型

**状态**: ⏳ 待开始

**文件**: `api-service/app/models/channel_calibration.py`

**实现内容**:
```python
# 需要创建的 SQLAlchemy 模型:
- TemporalChannelCalibration  # 时域信道校准
- DopplerCalibration          # 多普勒校准
- SpatialCorrelationCalibration  # 空间相关性校准
- AngularSpreadCalibration    # 角度扩展校准
- QuietZoneCalibration        # 静区校准
- EISValidation               # EIS 验证
```

**验收测试**:
```python
def test_temporal_calibration_model_fields():
    """验证时域校准模型字段"""
    required_fields = [
        'id', 'scenario_type', 'scenario_condition', 'fc_ghz',
        'measured_pdp', 'measured_rms_delay_spread_ns',
        'reference_rms_delay_spread_ns', 'rms_error_percent',
        'validation_pass', 'calibrated_at'
    ]
    # ...

def test_spatial_correlation_model_fields():
    """验证空间相关性模型字段"""
    # ...
```

**完成检查**:
- [ ] 6 个模型类创建完成
- [ ] 数据库迁移执行成功
- [ ] 模型测试通过
- [ ] 更新本文档状态

---

### TASK-C02: Pydantic Schemas

**状态**: ⏳ 待开始

**依赖**: TASK-C01

**文件**: `api-service/app/schemas/channel_calibration.py`

**完成检查**:
- [ ] 所有 schema 类创建完成
- [ ] 验证测试通过
- [ ] 更新本文档状态

---

### TASK-C03: 时域校准 API + 算法

**状态**: ⏳ 待开始

**依赖**: TASK-C02

**实现端点**:
```
POST /api/v1/calibration/channel/temporal
GET  /api/v1/calibration/channel/temporal/{id}
GET  /api/v1/calibration/channel/temporal/scenarios
```

**实现算法**:
```python
class TemporalChannelCalibrationService:
    def extract_pdp(
        self,
        channel_impulse_response: np.ndarray,
        sampling_rate_hz: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """从信道冲激响应提取功率时延谱"""

    def calculate_rms_delay_spread(
        self,
        delays_ns: np.ndarray,
        powers_linear: np.ndarray
    ) -> float:
        """计算 RMS 时延扩展: τ_rms = sqrt(E[τ²] - E[τ]²)"""

    def detect_clusters(
        self,
        pdp: np.ndarray,
        threshold_db: float = -25.0
    ) -> List[Cluster]:
        """检测多径簇"""

    def compare_with_3gpp(
        self,
        measured_rms_delay_ns: float,
        scenario: str,
        condition: str
    ) -> Tuple[float, bool]:
        """与 3GPP TR 38.901 参考值对比"""
```

**验收测试 - 算法单元测试**:
```python
class TestTemporalCalibrationAlgorithms:

    def test_rms_delay_spread_calculation(self):
        """验证 RMS 时延扩展计算"""
        service = TemporalChannelCalibrationService()

        # 简单测试: 两个等功率路径 @ 0ns 和 100ns
        delays_ns = np.array([0, 100])
        powers_linear = np.array([1, 1])  # 等功率

        # E[τ] = (0 + 100) / 2 = 50 ns
        # E[τ²] = (0 + 10000) / 2 = 5000 ns²
        # τ_rms = sqrt(5000 - 2500) = 50 ns

        rms = service.calculate_rms_delay_spread(delays_ns, powers_linear)
        assert abs(rms - 50) < 0.1

    def test_cluster_detection(self):
        """验证簇检测算法"""
        service = TemporalChannelCalibrationService()

        # 构造有明显簇结构的 PDP
        delays = np.arange(0, 1000, 10)  # 0-990 ns
        powers = np.zeros_like(delays, dtype=float)
        powers[0:3] = [0, -3, -6]  # 第一个簇 @ 0-20 ns
        powers[50:53] = [-10, -13, -16]  # 第二个簇 @ 500-520 ns
        powers[...:] = -40  # 其他为噪声

        clusters = service.detect_clusters(powers, threshold_db=-25)
        assert len(clusters) == 2

    def test_3gpp_comparison_uma_los(self):
        """验证 3GPP UMa LOS 场景对比"""
        service = TemporalChannelCalibrationService()

        # UMa LOS 参考 τ_rms ≈ 40-100 ns (取决于距离)
        measured_rms = 65  # ns
        error, passed = service.compare_with_3gpp(measured_rms, 'UMa', 'LOS')

        assert passed == True  # 在范围内
        assert error < 10  # 误差 < 10%

    def test_3gpp_comparison_uma_nlos(self):
        """验证 3GPP UMa NLOS 场景对比"""
        # UMa NLOS 参考 τ_rms ≈ 100-400 ns
        # ...
```

**完成检查**:
- [ ] 时域校准 API 实现
- [ ] PDP 提取算法测试通过
- [ ] RMS 时延扩展计算测试通过
- [ ] 簇检测算法测试通过
- [ ] 3GPP 对比测试通过
- [ ] 更新本文档状态

---

### TASK-C04: 多普勒校准 API + 算法

**状态**: ⏳ 待开始

**依赖**: TASK-C03

**实现端点**:
```
POST /api/v1/calibration/channel/doppler
GET  /api/v1/calibration/channel/doppler/{id}
```

**实现算法**:
```python
class DopplerCalibrationService:
    def calculate_doppler_spectrum(
        self,
        received_signal: np.ndarray,
        sampling_rate_hz: float,
        fft_size: int = 1024
    ) -> Tuple[np.ndarray, np.ndarray]:
        """计算多普勒频谱"""

    def generate_classical_doppler(
        self,
        max_doppler_hz: float,
        num_points: int
    ) -> np.ndarray:
        """生成理论经典多普勒谱: S(f) = 1/(π·f_d·√(1-(f/f_d)²))"""

    def calculate_spectral_correlation(
        self,
        measured_spectrum: np.ndarray,
        reference_spectrum: np.ndarray
    ) -> float:
        """计算频谱相关性 (0-1)"""
```

**验收测试**:
```python
class TestDopplerCalibrationAlgorithms:

    def test_classical_doppler_shape(self):
        """验证经典多普勒谱形状"""
        service = DopplerCalibrationService()

        # 生成 f_d = 100 Hz 的理论谱
        spectrum = service.generate_classical_doppler(100, 201)

        # 验证边界处趋于无穷
        assert spectrum[0] > spectrum[100]  # f = -100 Hz > f = 0 Hz
        assert spectrum[200] > spectrum[100]  # f = +100 Hz > f = 0 Hz

    def test_spectral_correlation_identical(self):
        """验证相同频谱的相关性为 1"""
        service = DopplerCalibrationService()
        spectrum = np.random.rand(100)
        corr = service.calculate_spectral_correlation(spectrum, spectrum)
        assert abs(corr - 1.0) < 0.001
```

**完成检查**:
- [ ] 多普勒校准 API 实现
- [ ] 频谱计算测试通过
- [ ] 经典多普勒生成测试通过
- [ ] 频谱相关性测试通过
- [ ] 更新本文档状态

---

### TASK-C05: 空间相关性校准 API + 算法

**状态**: ⏳ 待开始

**依赖**: TASK-C04

**实现端点**:
```
POST /api/v1/calibration/channel/spatial-correlation
GET  /api/v1/calibration/channel/spatial-correlation/{id}
```

**实现算法**:
```python
class SpatialCalibrationService:
    def calculate_spatial_correlation(
        self,
        h1: np.ndarray,  # 天线1的信道系数时间序列
        h2: np.ndarray   # 天线2的信道系数时间序列
    ) -> complex:
        """计算空间相关性: ρ = E[h1·h2*] / √(E[|h1|²]·E[|h2|²])"""

    def calculate_theoretical_correlation_laplacian(
        self,
        antenna_spacing_wavelengths: float,
        angular_spread_deg: float,
        mean_aoa_deg: float = 0
    ) -> float:
        """基于 Laplacian 角度分布计算理论相关性"""

    def fit_laplacian_distribution(
        self,
        azimuth_deg: np.ndarray,
        power_db: np.ndarray
    ) -> Tuple[float, float, float]:
        """拟合 Laplacian 分布: 返回 (mean, sigma, r_squared)"""
```

**验收测试**:
```python
class TestSpatialCalibrationAlgorithms:

    def test_spatial_correlation_range(self):
        """验证相关性在 [0, 1] 范围内"""
        service = SpatialCalibrationService()

        # 随机信道系数
        h1 = np.random.randn(1000) + 1j * np.random.randn(1000)
        h2 = np.random.randn(1000) + 1j * np.random.randn(1000)

        corr = service.calculate_spatial_correlation(h1, h2)
        assert 0 <= abs(corr) <= 1

    def test_spatial_correlation_identical(self):
        """验证相同信道的相关性为 1"""
        service = SpatialCalibrationService()
        h = np.random.randn(1000) + 1j * np.random.randn(1000)
        corr = service.calculate_spatial_correlation(h, h)
        assert abs(abs(corr) - 1.0) < 0.001

    def test_theoretical_correlation_half_wavelength(self):
        """验证 0.5λ 间距的理论相关性"""
        service = SpatialCalibrationService()

        # 对于 σ_θ = 35° (典型 NLOS), d = 0.5λ
        # 理论相关性约为 0.5-0.7
        corr = service.calculate_theoretical_correlation_laplacian(
            antenna_spacing_wavelengths=0.5,
            angular_spread_deg=35
        )
        assert 0.4 < corr < 0.8

    def test_laplacian_fit(self):
        """验证 Laplacian 分布拟合"""
        service = SpatialCalibrationService()

        # 生成标准 Laplacian 分布数据
        # 验证拟合参数接近真实值
```

**完成检查**:
- [ ] 空间相关性 API 实现
- [ ] 相关性计算测试通过
- [ ] 理论相关性计算测试通过
- [ ] Laplacian 拟合测试通过
- [ ] 更新本文档状态

---

### TASK-C06: 角度扩展校准 API

**状态**: ⏳ 待开始

**依赖**: TASK-C05

**实现端点**:
```
POST /api/v1/calibration/channel/angular-spread
GET  /api/v1/calibration/channel/angular-spread/{id}
```

**完成检查**:
- [ ] 角度扩展 API 实现
- [ ] APS 测量逻辑测试通过
- [ ] 更新本文档状态

---

### TASK-C07: EIS 验证 API

**状态**: ⏳ 待开始

**依赖**: TASK-C06

**实现端点**:
```
POST /api/v1/calibration/channel/eis
GET  /api/v1/calibration/channel/eis/{id}
GET  /api/v1/calibration/channel/eis/{id}/map
```

**完成检查**:
- [ ] EIS 验证 API 实现
- [ ] EIS 计算测试通过
- [ ] 更新本文档状态

---

### TASK-C08: 信道校准集成测试

**状态**: ⏳ 待开始

**依赖**: TASK-C07

**文件**: `api-service/tests/integration/test_channel_calibration_flow.py`

**测试场景**:
```python
class TestChannelCalibrationIntegration:

    @pytest.mark.integration
    def test_complete_channel_calibration_flow(self, client, db, mock_channel_emulator):
        """测试完整信道校准流程: 时域 → 空间 → EIS"""

        # Step 1: 时域校准 (UMa LOS)
        temporal_response = client.post(
            "/api/v1/calibration/channel/temporal",
            json={
                "scenario": {"type": "UMa", "condition": "LOS", "fc_ghz": 3.5},
                ...
            }
        )
        assert temporal_response.status_code == 201
        temporal_result = temporal_response.json()
        assert temporal_result["validation"]["pass"] == True

        # Step 2: 多普勒校准
        doppler_response = client.post(
            "/api/v1/calibration/channel/doppler",
            json={"velocity_kmh": 120, "fc_ghz": 3.5}
        )
        assert doppler_response.status_code == 201

        # Step 3: 空间相关性校准
        spatial_response = client.post(
            "/api/v1/calibration/channel/spatial-correlation",
            json={
                "scenario": {"type": "UMa", "condition": "NLOS"},
                "antenna_spacing_wavelengths": 0.5
            }
        )
        assert spatial_response.status_code == 201

        # Step 4: EIS 验证
        eis_response = client.post(
            "/api/v1/calibration/channel/eis",
            json={"scenario": "UMa_NLOS", ...}
        )
        assert eis_response.status_code == 201
        assert eis_response.json()["requirements"]["pass"] == True
```

**完成检查**:
- [ ] 完整流程集成测试通过
- [ ] 各场景测试通过
- [ ] 更新本文档状态

---

### TASK-C09: 信道校准前端

**状态**: ⏳ 待开始

**依赖**: TASK-C08

**文件**:
- `gui/src/api/channelCalibrationService.ts`
- `gui/src/components/ChannelCalibration/ChannelCalibrationDashboard.tsx`
- `gui/src/components/ChannelCalibration/TemporalCalibrationDetail.tsx`
- `gui/src/components/ChannelCalibration/SpatialCalibrationDetail.tsx`

**完成检查**:
- [ ] 前端 API 客户端实现
- [ ] Dashboard 组件实现
- [ ] 时域详情组件实现 (PDP 对比图)
- [ ] 空间详情组件实现 (相关矩阵热力图)
- [ ] 与后端联调通过
- [ ] 更新本文档状态

---

## 第三部分: 集成和自动化

### TASK-I01: 校准工作流引擎

**状态**: ⏳ 待开始

**依赖**: TASK-P10, TASK-C08

**文件**: `api-service/app/services/calibration_workflow.py`

**实现内容**:
```python
class CalibrationWorkflowExecutor:
    def load_workflow(self, workflow_yaml: str) -> Workflow:
        """加载 YAML 工作流定义"""

    async def execute_workflow(
        self,
        workflow: Workflow,
        configuration: Dict
    ) -> WorkflowResult:
        """执行完整校准工作流"""

    def check_pre_conditions(self, workflow: Workflow) -> List[str]:
        """检查前置条件 (如探头校准有效性)"""
```

**完成检查**:
- [ ] 工作流引擎实现
- [ ] YAML 解析测试通过
- [ ] 端到端工作流测试通过
- [ ] 更新本文档状态

---

### TASK-I02: 综合报告生成

**状态**: ⏳ 待开始

**依赖**: TASK-I01

**文件**: `api-service/app/services/calibration_report.py`

**完成检查**:
- [ ] PDF 报告生成实现
- [ ] 报告包含探头 + 信道校准结果
- [ ] 报告样式测试通过
- [ ] 更新本文档状态

---

### TASK-I03: 端到端测试

**状态**: ⏳ 待开始

**依赖**: TASK-I02

**文件**: `api-service/tests/e2e/test_calibration_e2e.py`

**测试场景**:
```python
class TestCalibrationE2E:

    @pytest.mark.e2e
    def test_full_system_calibration(self, client, db, mock_all_instruments):
        """模拟完整系统校准流程"""

        # 1. 探头校准
        # 2. 信道校准
        # 3. 系统校准
        # 4. 生成报告
        # 5. 验证所有数据正确存储
```

**完成检查**:
- [ ] 端到端测试通过
- [ ] 所有数据流验证
- [ ] 更新本文档状态

---

## 进度跟踪

### 当前状态

| 阶段 | 任务数 | 完成数 | 状态 |
|-----|-------|-------|------|
| 探头校准 | 12 | 2 | 🔄 进行中 |
| 信道校准 | 9 | 0 | ⏳ 待开始 |
| 集成 | 3 | 0 | ⏳ 待开始 |
| **总计** | **24** | **2** | **8%** |

### 最近更新

| 日期 | 任务 | 变更 |
|-----|------|------|
| 2026-01-15 | TASK-P02 | ✅ 完成 Pydantic Schemas (20+ schemas + 32 测试通过) |
| 2026-01-15 | TASK-P01 | ✅ 完成数据库模型 (6 模型 + 18 测试通过) |
| 2026-01-15 | - | 创建实施计划文档 |

---

## 如何使用本文档

1. **开始新任务前**:
   - 查找下一个状态为 "⏳ 待开始" 的任务
   - 检查其依赖是否已完成

2. **开发过程中**:
   - 按照任务的 "实现内容" 编写代码
   - 按照 "验收测试" 编写测试用例
   - 确保测试通过

3. **任务完成后**:
   - 勾选 "完成检查" 中的所有项目
   - 更新任务状态为 "✅ 完成"
   - 更新 "进度跟踪" 表格
   - 在 "最近更新" 中添加记录

4. **上下文丢失时**:
   - 阅读本文档的 "进度跟踪" 部分
   - 找到最近完成的任务
   - 继续下一个任务

---

## 附录: 3GPP 参考参数

### 时延扩展 (TR 38.901 Table 7.5-6)

| 场景 | 条件 | τ_rms (ns) | 范围 |
|-----|------|-----------|------|
| UMa | LOS | 40-100 | 取决于距离 |
| UMa | NLOS | 100-400 | 取决于距离 |
| UMi | LOS | 20-50 | - |
| UMi | NLOS | 50-200 | - |
| InH | LOS | 10-30 | - |
| InH | NLOS | 30-80 | - |

### 角度扩展 (TR 38.901 Table 7.5-6)

| 场景 | 条件 | σ_AoA (°) | σ_AoD (°) |
|-----|------|----------|----------|
| UMa | LOS | 10-20 | 5-15 |
| UMa | NLOS | 30-50 | 10-30 |
| UMi | LOS | 15-25 | 5-15 |
| UMi | NLOS | 40-60 | 15-35 |
