# Swagger UI 使用指南

## 🎯 重要说明

**您看到的不是普通文档，而是交互式 API 测试工具！**

Swagger UI 是 FastAPI 自动生成的，可以直接在浏览器中测试所有 API 端点。

---

## 📍 访问地址

```
http://localhost:8001/api/docs
```

**当前状态**：✅ API 服务已运行，所有端点已实现

---

## 🖱️ 如何使用 Swagger UI

### 步骤 1：查看可用端点

在 Swagger UI 页面中，您会看到分组的 API 端点：

```
📁 Health
  GET /api/v1/health - 健康检查

📁 System Calibration
  POST /api/v1/calibration/trp - TRP 校准
  GET  /api/v1/calibration/trp - 查询 TRP 记录
  GET  /api/v1/calibration/trp/{id} - 获取单条记录
  POST /api/v1/calibration/tis - TIS 校准
  GET  /api/v1/calibration/tis - 查询 TIS 记录
  POST /api/v1/calibration/repeatability - 重复性测试
  POST /api/v1/calibration/certificate - 生成证书
  ...
```

---

### 步骤 2：测试一个端点（以 TRP 校准为例）

#### 2.1 点击端点展开

找到 **`POST /api/v1/calibration/trp`**，点击展开。

您会看到：
- 📝 **Summary**: Execute Trp Calibration
- 📖 **Description**: 端点的详细说明
- 📥 **Request Body**: 需要的输入参数
- 📤 **Responses**: 可能的响应

#### 2.2 点击 "Try it out"

在展开的端点右上角，点击蓝色按钮 **"Try it out"**。

此时，Request Body 区域会变成可编辑状态。

#### 2.3 输入测试数据

您会看到一个 JSON 编辑器，预填充了示例数据：

```json
{
  "standard_dut_model": "string",
  "standard_dut_serial": "string",
  "reference_trp_dbm": 0,
  "frequency_mhz": 0,
  "tx_power_dbm": 0,
  "tested_by": "string",
  "reference_lab": "string",
  "reference_cert_number": "string"
}
```

**修改为真实测试数据**：

```json
{
  "standard_dut_model": "Standard Dipole λ/2",
  "standard_dut_serial": "DIP-2024-001",
  "reference_trp_dbm": 10.5,
  "frequency_mhz": 3500,
  "tx_power_dbm": 23,
  "tested_by": "张工",
  "reference_lab": "NIM (中国计量科学研究院)",
  "reference_cert_number": "NIM-CAL-2024-001"
}
```

#### 2.4 点击 "Execute"

点击蓝色的 **"Execute"** 按钮。

#### 2.5 查看结果

向下滚动，您会看到：

**✅ Server response**

```
Code: 201 Created
```

**Response body**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "standard_dut_model": "Standard Dipole λ/2",
  "standard_dut_serial": "DIP-2024-001",
  "reference_trp_dbm": 10.5,
  "measured_trp_dbm": 10.48,
  "trp_error_db": -0.02,
  "absolute_error_db": 0.02,
  "validation_pass": true,
  "threshold_db": 0.5,
  "num_probes_used": 336,
  "frequency_mhz": 3500.0,
  "tx_power_dbm": 23.0,
  "tested_by": "张工",
  "reference_lab": "NIM (中国计量科学研究院)",
  "reference_cert_number": "NIM-CAL-2024-001",
  "tested_at": "2025-11-17T15:30:00.123456"
}
```

**Response headers**:
```
content-type: application/json
```

**Curl command**:
```bash
curl -X 'POST' \
  'http://localhost:8001/api/v1/calibration/trp' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{ ... }'
```

---

## 🎓 Swagger UI 界面说明

### 主要区域

```
┌─────────────────────────────────────────────┐
│  Meta-3D OTA API                    v1.0.0  │  ← 标题栏
├─────────────────────────────────────────────┤
│  This API provides endpoints for...         │  ← API 描述
│                                             │
│  📁 Health                                  │  ← 端点分组
│    ▼ GET /api/v1/health                    │
│                                             │
│  📁 System Calibration                      │
│    ▼ POST /api/v1/calibration/trp          │  ← 可展开的端点
│      Execute Trp Calibration               │
│      [Try it out]  ← 点击进入交互模式        │
│                                             │
│      Request body                          │
│      { ... JSON 编辑器 ... }                │
│      [Execute]  ← 执行请求                  │
│                                             │
│      Responses                             │
│      200 OK                                │
│      { ... 响应示例 ... }                   │
│                                             │
│    ▼ GET /api/v1/calibration/trp           │
│    ▼ POST /api/v1/calibration/tis          │
│    ...                                     │
└─────────────────────────────────────────────┘
```

### 按钮说明

| 按钮 | 位置 | 功能 |
|------|------|------|
| **Try it out** | 端点展开后右上角 | 进入交互测试模式 |
| **Execute** | Request body 下方 | 发送 API 请求 |
| **Cancel** | Execute 旁边 | 取消编辑，返回只读模式 |
| **▼** | 端点左侧 | 展开/折叠端点详情 |

### 颜色标识

| 颜色 | HTTP 方法 | 说明 |
|------|----------|------|
| 🟢 **绿色** | GET | 查询数据 |
| 🔵 **蓝色** | POST | 创建数据 |
| 🟡 **黄色** | PUT | 更新数据 |
| 🔴 **红色** | DELETE | 删除数据 |

---

## 🧪 实际测试流程

### 测试 1：执行 TRP 校准

1. 访问 http://localhost:8001/api/docs
2. 找到 **POST /api/v1/calibration/trp**
3. 点击展开
4. 点击 **"Try it out"**
5. 输入测试数据（参考上面的 JSON）
6. 点击 **"Execute"**
7. 查看响应结果

**期望结果**：
- ✅ `validation_pass: true`
- ✅ `absolute_error_db < 0.5`

---

### 测试 2：查询所有 TRP 校准记录

1. 找到 **GET /api/v1/calibration/trp**
2. 点击展开
3. 点击 **"Try it out"**
4. 直接点击 **"Execute"**（无需输入参数）
5. 查看返回的记录列表

**期望结果**：
```json
[
  {
    "id": "550e8400-...",
    "measured_trp_dbm": 10.48,
    "validation_pass": true,
    ...
  },
  ...
]
```

---

### 测试 3：执行 TIS 校准

1. 找到 **POST /api/v1/calibration/tis**
2. 点击 **"Try it out"**
3. 输入：
   ```json
   {
     "standard_dut_model": "Reference Smartphone",
     "standard_dut_serial": "REF-PHONE-001",
     "reference_tis_dbm": -90.2,
     "frequency_mhz": 3500,
     "tested_by": "李工"
   }
   ```
4. 点击 **"Execute"**

---

### 测试 4：生成校准证书

1. 先执行 TRP、TIS 和重复性测试，记录返回的 ID
2. 找到 **POST /api/v1/calibration/certificate**
3. 输入三个测试的 ID：
   ```json
   {
     "trp_calibration_id": "550e8400-...",
     "tis_calibration_id": "660e8400-...",
     "repeatability_test_id": "770e8400-...",
     "lab_name": "Meta-3D 测试实验室",
     "lab_address": "北京市海淀区",
     "lab_accreditation": "CNAS L12345",
     "calibrated_by": "张工",
     "reviewed_by": "王经理",
     "validity_months": 12
   }
   ```
4. 点击 **"Execute"**

---

## 🎯 常见问题

### Q1: 为什么叫 Swagger UI？

**A**: Swagger 是 OpenAPI 规范的旧名称。Swagger UI 是一个自动生成的交互式 API 文档工具，由 FastAPI 自动创建。

### Q2: Mock 数据是什么意思？

**A**: 当前系统运行在 **Mock 模式**，这意味着：
- ✅ API 逻辑完整实现
- ✅ 可以正常调用和测试
- ⚠️ 使用模拟的仪器数据（不连接真实硬件）

**查看 Mock 状态**：
```bash
curl http://localhost:8001/api/v1/health
# "mock_instruments": true  ← Mock 模式开启
```

### Q3: 数据库连接失败正常吗？

**A**: 是的。在开发环境中，如果您看到：
```json
{
  "database_connected": false
}
```

这是正常的，因为：
1. 数据库配置是可选的
2. Mock 模式下数据存储在内存中
3. 不影响 API 测试

**如需启用数据库**：
```bash
cd api-service
echo "DATABASE_URL=sqlite:///./meta3d_ota.db" > .env
# 重启服务
```

### Q4: 可以复制生成的 curl 命令吗？

**A**: 可以！每次执行后，Swagger UI 都会显示等效的 curl 命令。您可以：
1. 复制 curl 命令
2. 在终端中执行
3. 集成到自动化脚本中

---

## 📚 Swagger UI vs 其他工具

| 特性 | Swagger UI | Postman | curl |
|------|-----------|---------|------|
| 自动生成 | ✅ | ❌ | ❌ |
| 浏览器内测试 | ✅ | ❌ | ❌ |
| 免安装 | ✅ | ❌ | ✅ |
| 可视化 | ✅ | ✅ | ❌ |
| 自动验证 | ✅ | ✅ | ❌ |

---

## 🔗 相关链接

- **Swagger UI**: http://localhost:8001/api/docs
- **ReDoc** (另一种文档格式): http://localhost:8001/api/redoc
- **OpenAPI JSON**: http://localhost:8001/api/openapi.json
- **Health Check**: http://localhost:8001/api/v1/health

---

## 🎓 下一步

1. ✅ 在 Swagger UI 中测试所有校准端点
2. ✅ 了解每个端点的输入输出格式
3. ✅ 验证 Mock 数据返回是否符合预期
4. 🔲 （未来）创建前端 GUI 集成这些 API
5. 🔲 （未来）连接真实硬件替换 Mock 仪器

---

**提示**: 如果您想查看更详细的 API 使用示例，请参考 [API-CALIBRATION-DEMO.md](./API-CALIBRATION-DEMO.md)
