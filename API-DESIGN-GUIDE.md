# API 设计规范

**版本**: 1.0.0
**生效日期**: 2025-11-23

---

## 1. 设计原则

### 1.1 RESTful 风格

所有 API 遵循 REST 架构风格：

- **资源导向**: URL 表示资源，而非操作
- **HTTP 方法语义化**: GET（查询）、POST（创建）、PUT/PATCH（更新）、DELETE（删除）
- **无状态**: 每个请求包含完整信息，不依赖服务端会话
- **可缓存**: 适当使用 HTTP 缓存头

### 1.2 一致性优先

- **命名一致**: 相同概念在所有端点使用相同名称
- **格式一致**: 响应结构在所有端点保持一致
- **错误一致**: 错误响应格式统一
- **分页一致**: 所有列表查询使用相同的分页参数

### 1.3 向后兼容

- **版本控制**: URL 包含 API 版本号 (`/v1/`, `/v2/`)
- **字段添加**: 新增字段不影响旧客户端
- **弃用流程**: 提前通知 → 标记弃用 → 最终移除（至少保留 3 个月）

---

## 2. URL 设计

### 2.1 路径命名规范

```
格式: /v{version}/{resource-collection}/{resource-id}/{sub-resource}

示例:
  /v1/test-plans                    # 资源集合
  /v1/test-plans/{id}               # 单个资源
  /v1/test-plans/{id}/steps         # 子资源集合
  /v1/test-plans/{id}/steps/{step_id}  # 单个子资源
```

**规则**:
1. 使用小写字母
2. 单词之间用连字符（-）分隔，不用下划线（_）
3. 资源名称用复数形式（`test-plans` 而非 `test-plan`）
4. 避免在 URL 中使用动词（`GET /users` 而非 `GET /getUsers`）

### 2.2 查询参数规范

```
格式: ?param1=value1&param2=value2

常用参数:
  ?skip=0&limit=20         # 分页
  ?sort_by=created_at      # 排序字段
  ?sort_order=desc         # 排序顺序 (asc/desc)
  ?filter_field=value      # 过滤条件
  ?search=keyword          # 全文搜索
```

**规则**:
1. 使用 snake_case（下划线分隔）
2. 布尔参数使用 `true`/`false` 字符串
3. 日期使用 ISO 8601 格式（`2025-11-23T10:30:00Z`）

---

## 3. HTTP 方法

### 3.1 方法使用规范

| 方法 | 用途 | 幂等性 | 请求体 | 响应体 |
|------|-----|--------|-------|--------|
| GET | 查询资源 | ✅ | ❌ | ✅ |
| POST | 创建资源 | ❌ | ✅ | ✅ |
| PUT | 完全替换资源 | ✅ | ✅ | ✅ |
| PATCH | 部分更新资源 | ❌ | ✅ | ✅ |
| DELETE | 删除资源 | ✅ | ❌ | ✅/❌ |

### 3.2 方法选择指南

```
# 创建资源
POST /v1/test-plans
{
  "name": "新测试计划",
  ...
}

# 完全替换（所有字段必填）
PUT /v1/test-plans/{id}
{
  "name": "更新的名称",
  "description": "...",
  ...所有字段...
}

# 部分更新（只更新提供的字段）✅ 推荐
PATCH /v1/test-plans/{id}
{
  "name": "只更新名称"
}

# 删除资源
DELETE /v1/test-plans/{id}
```

---

## 4. 请求格式

### 4.1 请求头

**必需头**:
```http
Content-Type: application/json
Accept: application/json
```

**可选头**:
```http
Authorization: Bearer <token>
X-Request-ID: <uuid>          # 用于追踪请求
Accept-Language: zh-CN        # 国际化
```

### 4.2 请求体

**JSON 格式**:
```json
{
  "field_name": "value",       // 使用 snake_case
  "nested_object": {
    "nested_field": "value"
  },
  "array_field": [1, 2, 3]
}
```

**规则**:
1. 使用 JSON 格式（除非上传文件）
2. 字段名使用 snake_case
3. 日期使用 ISO 8601 字符串
4. UUID 使用字符串格式（带连字符）

---

## 5. 响应格式

### 5.1 成功响应

#### 单一资源

```json
// GET /v1/test-plans/{id}
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "测试计划名称",
  "status": "ready",
  "created_at": "2025-11-23T10:30:00Z",
  ...
}
```

#### 资源集合（带分页）

```json
// GET /v1/test-plans?skip=0&limit=20
{
  "total": 100,              // 总数
  "items": [                 // 资源数组
    {
      "id": "...",
      "name": "...",
      ...
    }
  ],
  "page": 1,                 // 当前页（可选）
  "page_size": 20            // 每页大小（可选）
}
```

#### 资源集合（不带分页）

```json
// GET /v1/test-sequences/categories
{
  "items": ["Calibration", "Measurement", "5G NR"]
}
```

#### 创建/更新成功

```json
// POST /v1/test-plans
// 返回创建的资源
{
  "id": "...",
  "name": "...",
  ...
}

// PATCH /v1/test-plans/{id}
// 返回更新后的资源
{
  "id": "...",
  "name": "...",
  ...
}
```

#### 删除成功

```
// 选项 1: 返回 204 No Content（无响应体）
DELETE /v1/test-plans/{id}
204 No Content

// 选项 2: 返回 200 + 确认消息
200 OK
{
  "message": "Test plan deleted successfully"
}
```

### 5.2 错误响应

#### 标准错误格式

```json
{
  "message": "简短的错误描述",
  "detail": "详细的错误信息（可选）",
  "errors": {              // 字段级别的错误（可选）
    "name": ["名称不能为空"],
    "priority": ["优先级必须在 1-10 之间"]
  }
}
```

#### 常见错误示例

```json
// 400 Bad Request - 请求参数错误
{
  "message": "Invalid request",
  "detail": "Missing required field: name",
  "errors": {
    "name": ["This field is required"]
  }
}

// 401 Unauthorized - 未认证
{
  "message": "Authentication required",
  "detail": "Please provide a valid token"
}

// 403 Forbidden - 无权限
{
  "message": "Permission denied",
  "detail": "You don't have permission to delete this resource"
}

// 404 Not Found - 资源不存在
{
  "message": "Resource not found",
  "detail": "Test plan with id '123' does not exist"
}

// 409 Conflict - 冲突
{
  "message": "Cannot delete running test plan",
  "detail": "Please stop the test plan before deleting"
}

// 422 Unprocessable Entity - 验证失败
{
  "message": "Validation failed",
  "errors": {
    "email": ["Invalid email format"],
    "age": ["Must be at least 18"]
  }
}

// 500 Internal Server Error - 服务器错误
{
  "message": "Internal server error",
  "detail": "An unexpected error occurred. Please contact support."
}
```

---

## 6. HTTP 状态码

### 6.1 成功状态码

| 状态码 | 含义 | 使用场景 |
|-------|------|---------|
| 200 OK | 成功 | GET, PATCH, DELETE（返回内容） |
| 201 Created | 已创建 | POST（创建资源） |
| 204 No Content | 成功但无内容 | DELETE（无返回） |

### 6.2 客户端错误

| 状态码 | 含义 | 使用场景 |
|-------|------|---------|
| 400 Bad Request | 请求格式错误 | JSON 格式错误、缺少必需参数 |
| 401 Unauthorized | 未认证 | 缺少或无效的认证令牌 |
| 403 Forbidden | 无权限 | 认证成功但无操作权限 |
| 404 Not Found | 资源不存在 | 查询不存在的资源 |
| 409 Conflict | 冲突 | 资源状态不允许操作 |
| 422 Unprocessable Entity | 验证失败 | 字段验证失败 |
| 429 Too Many Requests | 请求过多 | 触发限流 |

### 6.3 服务器错误

| 状态码 | 含义 | 使用场景 |
|-------|------|---------|
| 500 Internal Server Error | 服务器错误 | 未预期的错误 |
| 503 Service Unavailable | 服务不可用 | 维护、过载 |

---

## 7. 分页

### 7.1 基于偏移量的分页（推荐）

**请求**:
```
GET /v1/test-plans?skip=20&limit=10
```

**响应**:
```json
{
  "total": 100,
  "items": [...],
  "skip": 20,
  "limit": 10
}
```

**特点**:
- ✅ 简单直观
- ✅ 可以跳转到任意页
- ❌ 数据插入/删除时可能重复/遗漏

### 7.2 基于游标的分页（高级）

**请求**:
```
GET /v1/test-plans?cursor=eyJpZCI6MTIzfQ&limit=10
```

**响应**:
```json
{
  "items": [...],
  "next_cursor": "eyJpZCI6MTMzfQ",
  "has_more": true
}
```

**特点**:
- ✅ 数据一致性好
- ✅ 性能好（大数据集）
- ❌ 不能跳页

---

## 8. 过滤和搜索

### 8.1 简单过滤

```
GET /v1/test-plans?status=ready&created_by=admin
```

### 8.2 高级过滤（可选）

```
GET /v1/test-plans?filter=status:eq:ready,priority:gte:5
```

### 8.3 全文搜索

```
GET /v1/test-plans?search=MIMO测试
```

### 8.4 排序

```
GET /v1/test-plans?sort_by=created_at&sort_order=desc
```

---

## 9. 批量操作

### 9.1 批量创建

```http
POST /v1/test-plans/batch
{
  "items": [
    { "name": "计划1", ... },
    { "name": "计划2", ... }
  ]
}

Response:
{
  "created": 2,
  "items": [
    { "id": "...", "name": "计划1", ... },
    { "id": "...", "name": "计划2", ... }
  ]
}
```

### 9.2 批量更新

```http
PATCH /v1/test-plans/batch
{
  "ids": ["id1", "id2", "id3"],
  "updates": {
    "status": "ready"
  }
}

Response:
{
  "updated": 3,
  "message": "3 test plans updated successfully"
}
```

### 9.3 批量删除

```http
POST /v1/test-plans/batch-delete
{
  "ids": ["id1", "id2", "id3"]
}

Response:
{
  "deleted": 3,
  "message": "3 test plans deleted successfully"
}
```

---

## 10. 版本控制

### 10.1 URL 版本控制（推荐）

```
/v1/test-plans    # 版本 1
/v2/test-plans    # 版本 2
```

### 10.2 版本升级策略

1. **向后兼容更改**（无需升级版本）:
   - 添加新端点
   - 添加可选字段
   - 添加新的查询参数

2. **破坏性更改**（需要升级版本）:
   - 删除端点
   - 删除字段
   - 修改字段类型
   - 修改响应结构

3. **弃用流程**:
   ```
   1. 在响应头添加弃用警告
      Deprecation: true
      Sunset: 2026-03-01

   2. 在文档中标记弃用

   3. 至少保留 3 个月后移除
   ```

---

## 11. 安全性

### 11.1 认证

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 11.2 CORS

```python
# FastAPI 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 开发环境
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 11.3 限流

```
# 响应头
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1700000000
```

---

## 12. 文档和测试

### 12.1 OpenAPI 文档

- 所有端点必须有 OpenAPI 文档
- 包含请求/响应示例
- 包含参数说明

### 12.2 API 测试

- 每个端点至少有一个集成测试
- 测试成功和失败场景
- 测试边界条件

---

## 13. 示例：完整 API 端点

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

router = APIRouter(prefix="/v1/test-plans", tags=["Test Plans"])

@router.get("", response_model=TestPlanListResponse)
def list_test_plans(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum records to return"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search in name/description"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    """
    List test plans with filtering, searching, and pagination.

    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return
    - **status**: Filter by status (draft, ready, running, etc.)
    - **search**: Search keyword in name and description
    - **sort_by**: Field to sort by
    - **sort_order**: Sort order (asc or desc)
    """
    service = TestPlanService()
    plans, total = service.list_plans(
        db=db,
        skip=skip,
        limit=limit,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order
    )

    return {
        "total": total,
        "items": plans,
        "skip": skip,
        "limit": limit
    }

@router.post("", response_model=TestPlanResponse, status_code=201)
def create_test_plan(
    request: CreateTestPlanRequest,
    db: Session = Depends(get_db)
):
    """Create a new test plan."""
    service = TestPlanService()

    try:
        plan = service.create_plan(db, request)
        return plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{plan_id}", response_model=TestPlanResponse)
def get_test_plan(
    plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a test plan by ID."""
    service = TestPlanService()
    plan = service.get_plan(db, plan_id)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"Test plan {plan_id} not found"
        )

    return plan

@router.patch("/{plan_id}", response_model=TestPlanResponse)
def update_test_plan(
    plan_id: UUID,
    request: UpdateTestPlanRequest,
    db: Session = Depends(get_db)
):
    """Partially update a test plan."""
    service = TestPlanService()

    plan = service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")

    # Check if plan can be updated
    if plan.status in ["running", "completed"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update test plan in '{plan.status}' status"
        )

    updated_plan = service.update_plan(db, plan_id, request)
    return updated_plan

@router.delete("/{plan_id}", status_code=204)
def delete_test_plan(
    plan_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a test plan."""
    service = TestPlanService()

    plan = service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")

    # Check if plan can be deleted
    if plan.status == "running":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete running test plan"
        )

    service.delete_plan(db, plan_id)
    # 204 No Content - no response body
```

---

## 14. 检查清单

在实现新 API 端点时，检查以下项目：

- [ ] URL 使用 kebab-case（`test-plans` 而非 `test_plans`）
- [ ] 使用合适的 HTTP 方法（GET, POST, PATCH, DELETE）
- [ ] 响应格式统一（`{ total, items }` 或 `{ items }` 或单一资源）
- [ ] 字段名使用 snake_case（后端）
- [ ] 错误响应包含 `message` 字段
- [ ] 添加 OpenAPI 文档（docstring）
- [ ] 添加请求参数验证（使用 Pydantic）
- [ ] 添加业务逻辑验证（状态检查等）
- [ ] 返回合适的 HTTP 状态码
- [ ] 编写集成测试

---

## 15. 参考资源

- [REST API Tutorial](https://restfulapi.net/)
- [HTTP Status Codes](https://httpstatuses.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenAPI Specification](https://swagger.io/specification/)

