# API 设计规范

**版本**: 1.0.0
**生效日期**: 2025-11-23

---

> ⚠️ **本文是「约定规范」，不是「API 参考手册」。**
>
> 示例里的资源与参数是用来**示范形状**的，**不保证每一个都已实现**。
> 例如 `/v1/chambers` 的列表端点今天只接受 `skip` / `limit` / `active_only`，
> 响应只有 `{items, total}` —— 本文 §5.1 的 `page` / `page_size`、§7.1 响应里的
> `skip` / `limit`、§7.2 的游标分页（`cursor` / `next_cursor` / `has_more`）、
> §8 的 `chamber_type` / `created_by` / `filter` / `search` / `sort_by` / `sort_order`
> **一个都没实现**；照着发过去不会报错，会**静默返回未过滤的普通列表**。
>
> **要看真实端点，去 Swagger（`/docs`）或读 `app/api/` 的路由定义。**
>
> （2026-07-30 ARCH-1 S5 补注：本文原来的贯穿示例是**计划链的资源集合**，随 S4b 删除后
> 换成了还活着的 `/chambers`。换源过程中连着被审查抓到三次同一个毛病 ——
> **换了主语没换谓词**：先是给暗室安上了计划的 `status` 状态机（字段不存在），
> 再是 `PATCH`（只注册了 PUT），最后是这一整片查询参数。
> 根因是"示范" 与 "现状描述" 在这份文档里一直没分开，所以在顶上一次性说清，
> 而不是逐处打补丁。§9 批量操作另有更强的单独声明。）

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
  /v1/chambers                    # 资源集合
  /v1/chambers/{id}               # 单个资源
  /v1/chambers/{id}/probes         # 子资源集合
  （单个子资源形如 /v1/{coll}/{id}/{sub}/{sub-id}；暗室的探头子资源目前只做了集合级读取）
```

**规则**:
1. 使用小写字母
2. 单词之间用连字符（-）分隔，不用下划线（_）
3. 资源名称用复数形式（`chambers` 而非 `chamber`）
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
POST /v1/chambers
{
  "name": "3D-MPAC 暗室 A",
  ...
}

# 完全替换（所有字段必填）
PUT /v1/chambers/{id}
{
  "name": "更新的名称",
  "description": "...",
  ...所有字段...
}

# 部分更新（只更新提供的字段）✅ 推荐
# ⚠️ 这是本规范推荐的**语义**。暗室路由今天只注册了 PUT（没有 PATCH handler），
#    照这里发 PATCH 会拿 405；PUT 的 schema 用 exclude_unset 已支持部分更新。
PATCH /v1/chambers/{id}
{
  "name": "只更新名称"
}

# 删除资源
DELETE /v1/chambers/{id}
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
// GET /v1/chambers/{id}
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "3D-MPAC 暗室 A",
  "chamber_type": "custom",
  "is_active": true,
  "created_at": "2025-11-23T10:30:00Z",
  ...
}
```

#### 资源集合（带分页）

```json
// GET /v1/chambers?skip=0&limit=20
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
// GET /v1/chambers/presets —— 注意本端点的键名是 `presets` 而非 `items`,
//   属既有不一致 (本规范建议统一用 `items`, 存量端点未改)
{
  "presets": [{ "key": "caict_fs", "name": "CAICT-FS", ... }]
}
```

#### 创建/更新成功

```json
// POST /v1/chambers
// 返回创建的资源
{
  "id": "...",
  "name": "...",
  ...
}

// PATCH /v1/chambers/{id}  ← 语义示范；暗室今天只有 PUT，见 §3.2 的说明
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
DELETE /v1/chambers/{id}
204 No Content

// 选项 2: 返回 200 + 确认消息
200 OK
{
  "message": "Chamber deleted successfully"
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
  "detail": "Chamber with id '123' does not exist"
}

// 409 Conflict - 冲突 (暗室的真实 409 场景: 被活跃 lab profile 引用, 或系统预设不可改删)
{
  "message": "Cannot delete chamber in use",
  "detail": "Chamber is referenced by the active lab profile"
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
GET /v1/chambers?skip=20&limit=10
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
GET /v1/chambers?cursor=eyJpZCI6MTIzfQ&limit=10
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
GET /v1/chambers?chamber_type=custom&created_by=admin
```

### 8.2 高级过滤（可选）

```
GET /v1/chambers?filter=chamber_type:eq:custom,num_probes:gte:16
```

### 8.3 全文搜索

```
GET /v1/chambers?search=MPAC
```

### 8.4 排序

```
GET /v1/chambers?sort_by=created_at&sort_order=desc
```

---

## 9. 批量操作

> ⚠️ **本节是约定，不是现状描述。** 仓库里目前**没有任何** `/batch` / `/batch-delete`
> 端点 —— 下面写的是"将来要做批量时按这个形状做"，别照着去调。
> （2026-07-30 ARCH-1 S5 补注：本节原本拿计划链的批量端点举例 —— 那条路由既已随
> S4b 删除、此前也从未实现过。换成 `/v1/chambers` 只是换了个还活着的资源当范例，
> **批量端点本身仍然不存在** —— 这句话就是防止换源把假话洗白。）

### 9.1 批量创建

```http
POST /v1/chambers/batch
{
  "items": [
    { "name": "暗室1", ... },
    { "name": "暗室2", ... }
  ]
}

Response:
{
  "created": 2,
  "items": [
    { "id": "...", "name": "暗室1", ... },
    { "id": "...", "name": "暗室2", ... }
  ]
}
```

### 9.2 批量更新

```http
PATCH /v1/chambers/batch
{
  "ids": ["id1", "id2", "id3"],
  "updates": {
    "chamber_type": "caict_fs"
  }
}

Response:
{
  "updated": 3,
  "message": "3 chambers updated successfully"
}
```

### 9.3 批量删除

```http
POST /v1/chambers/batch-delete
{
  "ids": ["id1", "id2", "id3"]
}

Response:
{
  "deleted": 3,
  "message": "3 chambers deleted successfully"
}
```

---

## 10. 版本控制

### 10.1 URL 版本控制（推荐）

```
/v1/chambers    # 版本 1
/v2/chambers    # 版本 2
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

> ⚠️ **示范代码，不是 `app/api/chamber.py` 的抄本。** 这里演示的是本指南推荐的
> 分层写法（路由 → Service → 模型），真实的暗室路由目前**没有** Service 层、
> 直接操作模型，`ChamberService` 这个类并不存在。
> （2026-07-30 ARCH-1 S5 补注：本节原本示范的是 `TestPlanService`，那个类已随
> S4b 删除 —— 照抄会 ImportError。Schema 名 `ChamberConfigurationResponse` /
> `ChamberListResponse` / `ChamberConfigurationCreate` / `ChamberConfigurationUpdate`
> 是真的，可以照着看。）

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

router = APIRouter(prefix="/v1/chambers", tags=["Chambers"])

@router.get("", response_model=ChamberListResponse)
def list_chambers(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum records to return"),
    chamber_type: Optional[str] = Query(None, description="Filter by chamber type"),
    search: Optional[str] = Query(None, description="Search in name/description"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    """
    List chambers with filtering, searching, and pagination.

    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return
    - **chamber_type**: Filter by chamber type (caict_fs, custom, …)
    - **search**: Search keyword in name and description
    - **sort_by**: Field to sort by
    - **sort_order**: Sort order (asc or desc)
    """
    service = ChamberService()
    chambers, total = service.list_chambers(
        db=db,
        skip=skip,
        limit=limit,
        chamber_type=chamber_type,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order
    )

    return {
        "total": total,
        "items": chambers,
        "skip": skip,
        "limit": limit
    }

@router.post("", response_model=ChamberConfigurationResponse, status_code=201)
def create_chamber(
    request: ChamberConfigurationCreate,
    db: Session = Depends(get_db)
):
    """Create a new chamber."""
    service = ChamberService()

    try:
        chamber = service.create_chamber(db, request)
        return chamber
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{chamber_id}", response_model=ChamberConfigurationResponse)
def get_chamber(
    chamber_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a chamber by ID."""
    service = ChamberService()
    chamber = service.get_chamber(db, chamber_id)

    if not chamber:
        raise HTTPException(
            status_code=404,
            detail=f"Chamber {chamber_id} not found"
        )

    return chamber

@router.patch("/{chamber_id}", response_model=ChamberConfigurationResponse)
def update_chamber(
    chamber_id: UUID,
    request: ChamberConfigurationUpdate,
    db: Session = Depends(get_db)
):
    """Partially update a chamber."""
    service = ChamberService()

    chamber = service.get_chamber(db, chamber_id)
    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber not found")

    # Check if chamber can be updated (暗室的真实约束: 系统预设只读)
    if chamber.is_system_preset:
        raise HTTPException(
            status_code=409,
            detail="Cannot modify a system preset; duplicate it first"
        )

    updated_chamber = service.update_chamber(db, chamber_id, request)
    return updated_chamber

@router.delete("/{chamber_id}", status_code=204)
def delete_chamber(
    chamber_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a chamber."""
    service = ChamberService()

    chamber = service.get_chamber(db, chamber_id)
    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber not found")

    # Check if chamber can be deleted (暗室的真实约束: 被活跃 lab profile 引用)
    if service.is_referenced_by_active_lab(db, chamber_id):
        raise HTTPException(
            status_code=409,
            detail="Chamber is referenced by the active lab profile"
        )

    service.delete_chamber(db, chamber_id)
    # 204 No Content - no response body
```

---

## 14. 检查清单

在实现新 API 端点时，检查以下项目：

- [ ] URL 使用 kebab-case（`chambers` 而非 `chamber_configs`）
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

