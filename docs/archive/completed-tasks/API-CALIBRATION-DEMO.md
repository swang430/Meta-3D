# 端到端校准 API 验证指南

本文档说明如何验证端到端校准功能。

## 🚀 快速开始

### 步骤 1：启动 API 服务

```bash
# 启动所有服务（包括 API 服务）
npm run dev:safe:all

# 或只启动 API 服务
npm run dev:api
```

**验证服务已启动**：
```bash
curl http://localhost:8001/api/v1/health
```

预期输出：
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database_connected": true,
  "mock_instruments": true
}
```

---

## 📊 方式 1：使用 Swagger UI（推荐）

### 访问 API 文档

在浏览器中打开：**http://localhost:8001/api/docs**

![Swagger UI](https://via.placeholder.com/800x400?text=Swagger+UI+Screenshot)

### 可用的端到端校准接口

#### 1. TRP 校准（Total Radiated Power）

**端点**：`POST /api/v1/calibration/trp`

**功能**：验证 MPAC 系统测量发射功率的准确性

**测试步骤**：
1. 在 Swagger UI 中找到 `POST /api/v1/calibration/trp`
2. 点击 "Try it out"
3. 输入请求参数：

```json
{
  "standard_dut_model": "Standard Dipole λ/2",
  "standard_dut_serial": "DIP-2024-001",
  "reference_trp_dbm": 10.5,
  "frequency_mhz": 3500,
  "tx_power_dbm": 23,
  "tested_by": "工程师A",
  "reference_lab": "NIM (中国计量科学研究院)",
  "reference_cert_number": "NIM-CAL-2024-001"
}
```

4. 点击 "Execute"
5. 查看响应结果

**预期响应**（Mock 数据）：
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "measured_trp_dbm": 10.48,
  "trp_error_db": -0.02,
  "absolute_error_db": 0.02,
  "validation_pass": true,
  "threshold_db": 0.5,
  "num_probes_used": 336,
  "tested_at": "2025-11-17T12:00:00Z"
}
```

**验证点**：
- ✅ `validation_pass: true` - 校准通过
- ✅ `absolute_error_db: 0.02` - 误差在 ±0.5 dB 阈值内
- ✅ `num_probes_used: 336` - 使用了所有探头（32个探头 × 2极化 × 多个角度）

---

#### 2. TIS 校准（Total Isotropic Sensitivity）

**端点**：`POST /api/v1/calibration/tis`

**功能**：验证 MPAC 系统测量接收灵敏度的准确性

**测试步骤**：
在 Swagger UI 中输入：

```json
{
  "standard_dut_model": "Reference Smartphone",
  "standard_dut_serial": "REF-PHONE-001",
  "reference_tis_dbm": -90.2,
  "frequency_mhz": 3500,
  "tested_by": "工程师B"
}
```

**预期响应**：
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "measured_tis_dbm": -90.15,
  "tis_error_db": 0.05,
  "absolute_error_db": 0.05,
  "validation_pass": true,
  "threshold_db": 1.0,
  "tested_at": "2025-11-17T12:05:00Z"
}
```

---

#### 3. 重复性测试（Repeatability Test）

**端点**：`POST /api/v1/calibration/repeatability`

**功能**：验证系统测量的可重复性

**测试步骤**：
```json
{
  "test_type": "TRP",
  "dut_model": "Standard Dipole",
  "dut_serial": "DIP-2024-001",
  "num_runs": 10,
  "frequency_mhz": 3500,
  "tested_by": "工程师C"
}
```

**预期响应**：
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
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
    {"run_number": 1, "value_dbm": 10.45},
    {"run_number": 2, "value_dbm": 10.52},
    ...
  ]
}
```

**验证点**：
- ✅ `std_dev_db: 0.18` - 标准差小于 0.3 dB 阈值
- ✅ `validation_pass: true` - 重复性测试通过

---

#### 4. 生成校准证书

**端点**：`POST /api/v1/calibration/certificate`

**功能**：基于校准结果生成正式证书

**测试步骤**：
```json
{
  "trp_calibration_id": "550e8400-e29b-41d4-a716-446655440000",
  "tis_calibration_id": "660e8400-e29b-41d4-a716-446655440001",
  "repeatability_test_id": "770e8400-e29b-41d4-a716-446655440002",
  "lab_name": "Meta-3D 测试实验室",
  "lab_address": "北京市海淀区中关村大街1号",
  "lab_accreditation": "CNAS L12345 / ISO/IEC 17025:2017",
  "calibrated_by": "工程师A",
  "reviewed_by": "技术经理B",
  "validity_months": 12
}
```

**预期响应**：
```json
{
  "id": "880e8400-e29b-41d4-a716-446655440003",
  "certificate_number": "MPAC-SYS-CAL-2025-11-17-1200",
  "overall_pass": true,
  "trp_pass": true,
  "tis_pass": true,
  "repeatability_pass": true,
  "calibration_date": "2025-11-17T12:00:00Z",
  "valid_until": "2026-11-17T12:00:00Z",
  "issued_at": "2025-11-17T12:10:00Z"
}
```

---

## 📋 方式 2：使用 curl 命令行

### TRP 校准

```bash
curl -X POST http://localhost:8001/api/v1/calibration/trp \
  -H "Content-Type: application/json" \
  -d '{
    "standard_dut_model": "Standard Dipole λ/2",
    "standard_dut_serial": "DIP-2024-001",
    "reference_trp_dbm": 10.5,
    "frequency_mhz": 3500,
    "tx_power_dbm": 23,
    "tested_by": "工程师A",
    "reference_lab": "NIM",
    "reference_cert_number": "NIM-CAL-2024-001"
  }'
```

### TIS 校准

```bash
curl -X POST http://localhost:8001/api/v1/calibration/tis \
  -H "Content-Type: application/json" \
  -d '{
    "standard_dut_model": "Reference Smartphone",
    "standard_dut_serial": "REF-PHONE-001",
    "reference_tis_dbm": -90.2,
    "frequency_mhz": 3500,
    "tested_by": "工程师B"
  }'
```

### 查询校准记录

```bash
# 查询所有 TRP 校准记录
curl http://localhost:8001/api/v1/calibration/trp

# 查询所有 TIS 校准记录
curl http://localhost:8001/api/v1/calibration/tis

# 查询所有重复性测试
curl http://localhost:8001/api/v1/calibration/repeatability

# 查询所有校准证书
curl http://localhost:8001/api/v1/calibration/certificate
```

---

## 🖥️ 方式 3：前端 GUI（开发中）

### 当前状态

前端 GUI 中有校准相关的 UI 框架，但尚未连接到 api-service。

### 访问位置

1. 启动前端：`npm run dev:safe`
2. 打开浏览器：http://localhost:5173
3. 导航到：**"探头与暗室配置"** 页面
4. 查看：**"校准任务队列"** 区域

### 当前功能

目前显示的是 **Mock 数据**：
- 路径损耗校准
- 静区验证
- 功率放大器线性化

### 待开发

需要创建新的页面集成端到端校准：
- 系统级 TRP/TIS 校准界面
- 重复性测试界面
- 校准证书管理界面

---

## 🔄 完整测试流程

### 端到端校准验证流程

```bash
# 1. 启动所有服务
npm run dev:safe:all

# 等待服务启动（约 10 秒）

# 2. 验证服务健康状态
curl http://localhost:8001/api/v1/health

# 3. 执行 TRP 校准
curl -X POST http://localhost:8001/api/v1/calibration/trp \
  -H "Content-Type: application/json" \
  -d '{
    "standard_dut_model": "Standard Dipole λ/2",
    "standard_dut_serial": "DIP-2024-001",
    "reference_trp_dbm": 10.5,
    "frequency_mhz": 3500,
    "tx_power_dbm": 23,
    "tested_by": "测试工程师"
  }' | jq .

# 4. 执行 TIS 校准
curl -X POST http://localhost:8001/api/v1/calibration/tis \
  -H "Content-Type: application/json" \
  -d '{
    "standard_dut_model": "Reference Smartphone",
    "standard_dut_serial": "REF-PHONE-001",
    "reference_tis_dbm": -90.2,
    "frequency_mhz": 3500,
    "tested_by": "测试工程师"
  }' | jq .

# 5. 执行重复性测试
curl -X POST http://localhost:8001/api/v1/calibration/repeatability \
  -H "Content-Type: application/json" \
  -d '{
    "test_type": "TRP",
    "dut_model": "Standard Dipole",
    "dut_serial": "DIP-2024-001",
    "num_runs": 10,
    "frequency_mhz": 3500,
    "tested_by": "测试工程师"
  }' | jq .

# 6. 查看所有校准记录
curl http://localhost:8001/api/v1/calibration/trp | jq .
curl http://localhost:8001/api/v1/calibration/tis | jq .
```

---

## 📊 验证标准

### TRP 校准通过标准

- ✅ `|measured_trp - reference_trp| < 0.5 dB`
- ✅ `validation_pass == true`

### TIS 校准通过标准

- ✅ `|measured_tis - reference_tis| < 1.0 dB`
- ✅ `validation_pass == true`

### 重复性测试通过标准

- ✅ `std_dev_db < 0.3 dB` (for TRP)
- ✅ `std_dev_db < 0.5 dB` (for TIS/EIS)
- ✅ `validation_pass == true`

---

## 🎯 后续开发任务

### Phase 2：前端集成

需要在 GUI 中创建以下页面：

1. **系统校准管理页面**
   - TRP 校准表单和结果显示
   - TIS 校准表单和结果显示
   - 重复性测试配置和结果

2. **校准历史记录页面**
   - 校准记录列表
   - 结果趋势图表
   - 导出功能

3. **校准证书管理页面**
   - 证书生成表单
   - 证书列表和查看
   - PDF 导出

### 集成步骤

```typescript
// 1. 创建 API 服务
// gui/src/api/calibrationService.ts

// 2. 创建数据类型
// gui/src/types/calibration.ts

// 3. 创建 React 组件
// gui/src/components/SystemCalibration/

// 4. 添加路由
// gui/src/App.tsx
```

---

## 📚 相关文档

- [api-service/README.md](../api-service/README.md) - API 服务文档
- [docs/System-Calibration-Design.md](../docs/System-Calibration-Design.md) - 系统校准设计文档
- [DEV-QUICKSTART.md](../DEV-QUICKSTART.md) - 开发环境启动指南

---

## 🆘 故障排查

### 问题：API 服务未启动

```bash
# 检查服务状态
lsof -i:8001

# 启动服务
npm run dev:api
```

### 问题：数据库连接失败

```bash
# 检查 .env 配置
cd api-service
cat .env

# 确保使用 SQLite（开发环境）
echo "DATABASE_URL=sqlite:///./meta3d_ota.db" > .env
echo "USE_MOCK_INSTRUMENTS=true" >> .env
```

### 问题：Mock 仪器未启用

在 `api-service/.env` 中确认：
```env
USE_MOCK_INSTRUMENTS=true
```
