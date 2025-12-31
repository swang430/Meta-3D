# 数据模型设计规范

**版本**: 1.0.0
**生效日期**: 2025-11-23

---

## 1. 概述

本文档定义了 MIMO OTA 测试系统的数据模型设计规范，包括数据库模型、API Schema、前端类型定义的统一标准。

### 1.1 三层模型架构

```
┌─────────────────────┐
│  Frontend Types     │  TypeScript interfaces (camelCase)
│  (TypeScript)       │
└──────────┬──────────┘
           │ HTTP JSON (snake_case)
           ↓
┌─────────────────────┐
│  API Schemas        │  Pydantic models (snake_case)
│  (Pydantic)         │
└──────────┬──────────┘
           │ ORM mapping
           ↓
┌─────────────────────┐
│  Database Models    │  SQLAlchemy models (snake_case)
│  (SQLAlchemy)       │
└─────────────────────┘
```

### 1.2 数据流

```
创建流程:
Frontend → API Request (camelCase) → [转换] → API Schema (snake_case)
→ Service Layer → Database Model → Database

查询流程:
Database → Database Model → DTO (Data Transfer Object)
→ API Response (snake_case) → [转换] → Frontend (camelCase)
```

---

## 2. 命名规范

### 2.1 字段命名约定

#### 数据库和后端（Python - snake_case）

```python
# SQLAlchemy Model
class TestPlan(Base):
    id = Column(UUID, primary_key=True)
    test_plan_name = Column(String)        # ❌ 冗余
    name = Column(String)                  # ✅ 简洁
    created_at = Column(DateTime)
    dut_info = Column(JSON)

# Pydantic Schema
class TestPlanResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    dut_info: Dict[str, Any]
```

#### 前端（TypeScript - camelCase）

```typescript
interface TestPlan {
  id: string
  name: string
  createdAt: string
  dutInfo: Record<string, any>
}
```

### 2.2 统一术语表

| 概念 | 英文术语 | 数据库表 | 主要字段 | 显示字段 |
|-----|---------|---------|---------|---------|
| 测试计划 | Test Plan | test_plans | name | name |
| 测试步骤 | Test Step | test_steps | name | title (computed) |
| 测试例 | Test Case | test_cases | name | name |
| 序列库 | Sequence Library | test_sequences | name | name |
| 测试队列 | Test Queue | test_queue | - | position |
| 测试执行 | Test Execution | test_executions | - | - |
| 被测设备 | Device Under Test (DUT) | - | model, serial | - |

**规则**:
- **存储字段**: 使用 `name`（数据库实际存储）
- **显示字段**: 前端可使用 `title`（从 `name` 或关联表获取）
- **避免冗余**: 不要使用 `test_plan_name`，直接使用 `name`
- **保持一致**: 同一概念在所有地方使用相同的英文术语

### 2.3 特殊字段命名

#### 主键

```python
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
```

**规则**:
- 所有表使用 `id` 作为主键名
- 使用 UUID 类型（字符串格式，带连字符）
- 不使用整型自增 ID

#### 外键

```python
test_plan_id = Column(UUID, ForeignKey('test_plans.id'))
```

**规则**:
- 格式: `{关联表单数}_id`
- 例: `test_plan_id`, `sequence_library_id`

#### 时间戳

```python
created_at = Column(DateTime, server_default=func.now())
updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
started_at = Column(DateTime, nullable=True)
completed_at = Column(DateTime, nullable=True)
```

**规则**:
- 使用 `_at` 后缀
- 存储 UTC 时间
- 前端转换为本地时间显示

#### 状态字段

```python
status = Column(String(50), nullable=False, default="draft")
```

**规则**:
- 字段名: `status`
- 类型: 字符串枚举
- 使用小写、连字符分隔（`draft`, `in-progress`, `completed`）

---

## 3. 数据类型

### 3.1 基础类型映射

| 概念 | Python (SQLAlchemy) | Python (Pydantic) | TypeScript |
|-----|-------------------|------------------|------------|
| 唯一标识 | UUID | UUID | string |
| 字符串 | String(N) | str | string |
| 文本 | Text | str | string |
| 整数 | Integer | int | number |
| 浮点数 | Float | float | number |
| 布尔值 | Boolean | bool | boolean |
| 日期时间 | DateTime | datetime | string (ISO 8601) |
| JSON | JSON | Dict[str, Any] | Record<string, any> |
| 数组 | JSON | List[T] | T[] |

### 3.2 可选性

#### 后端可选性

```python
# 数据库模型
class TestStep(Base):
    # 必填字段 - nullable=False
    id = Column(UUID, primary_key=True)
    test_plan_id = Column(UUID, nullable=False)
    order = Column(Integer, nullable=False)

    # 可选字段 - nullable=True
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)

# Pydantic Schema
class TestStepResponse(BaseModel):
    # 必填字段
    id: UUID
    test_plan_id: UUID
    order: int

    # 可选字段 - 使用 Optional
    name: Optional[str] = None
    description: Optional[str] = None
    started_at: Optional[datetime] = None
```

#### 前端可选性

```typescript
interface TestStep {
  // 必填字段（后端保证返回）
  id: string
  testPlanId: string
  order: number

  // 可选字段（使用 ?）
  name?: string
  description?: string | null  // 允许 null
  startedAt?: string
}
```

**规则**:
1. 后端可选 → 前端必定可选
2. 后端必填 → 前端可选择必填或可选（取决于业务逻辑）
3. 允许 `null` 的字段使用 `T | null`

---

## 4. 常见模式

### 4.1 审计字段

所有实体表都应包含审计字段：

```python
class BaseModel(Base):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), nullable=False)
```

**前端对应**:
```typescript
interface BaseEntity {
  id: string
  createdAt: string
  updatedAt: string
  createdBy: string
}
```

### 4.2 软删除

```python
class TestPlan(BaseModel):
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(String(100), nullable=True)
```

**查询时过滤**:
```python
# 服务层自动过滤已删除记录
def list_plans(db):
    return db.query(TestPlan).filter(TestPlan.is_deleted == False).all()
```

### 4.3 版本控制

```python
class TestCase(BaseModel):
    version = Column(String(50), default="1.0")
    parent_id = Column(UUID, ForeignKey('test_cases.id'), nullable=True)
```

**规则**:
- 使用语义化版本号（`major.minor.patch`）
- `parent_id` 指向原始版本

### 4.4 JSON 字段

```python
# 数据库模型 - 结构化 JSON
class TestPlan(Base):
    dut_info = Column(JSON, comment="Device info: {model, serial, imei}")
    test_environment = Column(JSON, comment="Environment: {temperature, humidity}")

# Pydantic Schema - 定义结构
class DUTInfo(BaseModel):
    model: str
    serial: str
    imei: Optional[str] = None

class TestEnvironment(BaseModel):
    temperature: float
    humidity: float
    chamber_id: str

class TestPlanResponse(BaseModel):
    dut_info: DUTInfo
    test_environment: TestEnvironment
```

**前端对应**:
```typescript
interface DUTInfo {
  model: string
  serial: string
  imei?: string
}

interface TestEnvironment {
  temperature: number
  humidity: number
  chamberId: string
}

interface TestPlan {
  dutInfo: DUTInfo
  testEnvironment: TestEnvironment
}
```

---

## 5. 关系设计

### 5.1 一对多

```python
# 父表
class TestPlan(Base):
    __tablename__ = "test_plans"
    id = Column(UUID, primary_key=True)

# 子表
class TestStep(Base):
    __tablename__ = "test_steps"
    id = Column(UUID, primary_key=True)
    test_plan_id = Column(UUID, ForeignKey('test_plans.id'), nullable=False)

    # 可选: ORM 关系（不建议在大型项目中过度使用）
    # test_plan = relationship("TestPlan", back_populates="steps")
```

**查询**:
```python
# 推荐: 显式查询
plan = db.query(TestPlan).filter(TestPlan.id == plan_id).first()
steps = db.query(TestStep).filter(TestStep.test_plan_id == plan_id).all()

# 不推荐: ORM 关系（可能导致 N+1 查询）
# plan = db.query(TestPlan).filter(TestPlan.id == plan_id).first()
# steps = plan.steps  # 触发额外查询
```

### 5.2 多对多

```python
# 关联表
test_plan_tags = Table(
    'test_plan_tags',
    Base.metadata,
    Column('test_plan_id', UUID, ForeignKey('test_plans.id')),
    Column('tag_id', UUID, ForeignKey('tags.id')),
    UniqueConstraint('test_plan_id', 'tag_id')
)

class TestPlan(Base):
    tags_json = Column(JSON)  # 或者使用关联表

class Tag(Base):
    id = Column(UUID, primary_key=True)
    name = Column(String, unique=True)
```

**简化方案**（推荐用于标签等简单场景）:
```python
# 直接使用 JSON 数组
class TestPlan(Base):
    tags = Column(JSON, default=list)  # ["tag1", "tag2"]
```

### 5.3 自引用

```python
class TestCase(Base):
    id = Column(UUID, primary_key=True)
    parent_id = Column(UUID, ForeignKey('test_cases.id'), nullable=True)
```

**查询**:
```python
# 查询所有版本
def get_versions(db, case_id):
    case = db.query(TestCase).filter(TestCase.id == case_id).first()
    if case.parent_id:
        # 这是一个版本，查找原始版本
        return db.query(TestCase).filter(
            (TestCase.id == case.parent_id) | (TestCase.parent_id == case.parent_id)
        ).all()
    else:
        # 这是原始版本，查找所有子版本
        return db.query(TestCase).filter(
            (TestCase.id == case_id) | (TestCase.parent_id == case_id)
        ).all()
```

---

## 6. DTO 模式

### 6.1 为什么需要 DTO

**问题**: 数据库模型直接暴露给 API 导致:
- 业务逻辑散落在各个端点
- 重复的数据填充代码
- 难以维护和测试

**解决**: 引入 DTO（Data Transfer Object）层

### 6.2 DTO 设计

```python
# api-service/app/dto/test_step.py
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

class TestStepDTO:
    """测试步骤数据传输对象"""

    def __init__(self, db_model):
        # 从数据库模型复制基础字段
        self.id = db_model.id
        self.test_plan_id = db_model.test_plan_id
        self.sequence_library_id = db_model.sequence_library_id
        self.order = db_model.order
        self.status = db_model.status
        self.parameters = db_model.parameters
        # ... 其他字段

        # 计算字段（默认值）
        self.title = None
        self.category = None

    @classmethod
    def from_db(cls, db_model, db_session: Session):
        """
        从数据库模型创建 DTO，自动填充关联数据

        Args:
            db_model: TestStep 数据库模型实例
            db_session: 数据库会话（用于查询关联数据）

        Returns:
            TestStepDTO 实例
        """
        dto = cls(db_model)

        # 如果有序列库 ID，自动填充 title 和 category
        if db_model.sequence_library_id:
            sequence = db_session.query(TestSequence).filter(
                TestSequence.id == db_model.sequence_library_id
            ).first()

            if sequence:
                dto.title = sequence.name
                dto.category = sequence.category
                # 如果步骤没有描述，使用序列的描述
                if not db_model.description:
                    dto.description = sequence.description
            else:
                # 序列不存在时的回退值
                dto.title = f"Step {db_model.order}"
                dto.category = "Unknown"
        else:
            # 没有序列库关联时使用步骤自己的 name
            dto.title = db_model.name or f"Step {db_model.order}"
            dto.category = db_model.type or "Unknown"

        return dto

    def to_dict(self):
        """转换为字典（用于 Pydantic 序列化）"""
        return {
            "id": self.id,
            "test_plan_id": self.test_plan_id,
            "sequence_library_id": self.sequence_library_id,
            "order": self.order,
            "status": self.status,
            "title": self.title,
            "category": self.category,
            # ... 其他字段
        }
```

### 6.3 在 API 端点中使用 DTO

```python
from app.dto.test_step import TestStepDTO

@router.get("/{test_plan_id}/steps", response_model=List[TestStepResponse])
def get_test_steps(
    test_plan_id: UUID,
    db: Session = Depends(get_db)
):
    """获取测试计划的所有步骤"""
    service = TestStepService()
    db_steps = service.get_test_steps(db, test_plan_id)

    # 使用 DTO 转换
    dtos = [TestStepDTO.from_db(step, db) for step in db_steps]

    # 返回字典列表（Pydantic 自动验证和序列化）
    return [dto.to_dict() for dto in dtos]
```

**好处**:
- ✅ 业务逻辑集中（填充关联数据）
- ✅ 代码复用（一次实现，到处使用）
- ✅ 易于测试（DTO 是纯逻辑，无数据库依赖）
- ✅ 易于维护（修改一处即可）

---

## 7. 枚举类型

### 7.1 Python 枚举

```python
import enum

class TestPlanStatus(str, enum.Enum):
    """测试计划状态枚举"""
    DRAFT = "draft"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# 在数据库模型中使用
class TestPlan(Base):
    status = Column(String(50), nullable=False, default=TestPlanStatus.DRAFT)

# 在 Pydantic Schema 中使用
class TestPlanResponse(BaseModel):
    status: TestPlanStatus  # 自动验证
```

### 7.2 TypeScript 枚举

```typescript
// 类型别名（推荐）
export type TestPlanStatus =
  | 'draft'
  | 'ready'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'

// 枚举对象（可选，用于运行时检查）
export const TestPlanStatus = {
  DRAFT: 'draft',
  READY: 'ready',
  QUEUED: 'queued',
  RUNNING: 'running',
  PAUSED: 'paused',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const

// 工具函数
export function isValidStatus(status: string): status is TestPlanStatus {
  return Object.values(TestPlanStatus).includes(status as TestPlanStatus)
}
```

### 7.3 枚举值规范

**规则**:
- 使用小写字母
- 单词之间用连字符分隔（`in-progress` 而非 `in_progress` 或 `inProgress`）
- 保持简短和描述性

**示例**:
```python
class TestStepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

---

## 8. 验证规则

### 8.1 后端验证（Pydantic）

```python
from pydantic import BaseModel, Field, validator

class CreateTestPlanRequest(BaseModel):
    # 字段级验证
    name: str = Field(..., min_length=1, max_length=255)
    priority: int = Field(default=5, ge=1, le=10)
    estimated_duration_minutes: Optional[float] = Field(None, gt=0)

    # 自定义验证器
    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty or whitespace')
        return v.strip()

    # 多字段验证
    @validator('completed_at')
    def completed_must_be_after_started(cls, v, values):
        if v and values.get('started_at') and v < values['started_at']:
            raise ValueError('completed_at must be after started_at')
        return v
```

### 8.2 前端验证（Zod 可选）

```typescript
import { z } from 'zod'

const TestPlanSchema = z.object({
  name: z.string().min(1).max(255),
  priority: z.number().int().min(1).max(10).default(5),
  estimatedDurationMinutes: z.number().positive().optional(),
})

type TestPlan = z.infer<typeof TestPlanSchema>

// 使用
try {
  const validatedData = TestPlanSchema.parse(formData)
  // 数据有效，发送请求
  await api.createTestPlan(validatedData)
} catch (error) {
  if (error instanceof z.ZodError) {
    // 显示验证错误
    console.error(error.errors)
  }
}
```

---

## 9. 迁移和版本控制

### 9.1 数据库迁移

使用 Alembic 进行数据库迁移:

```bash
# 创建迁移
alembic revision --autogenerate -m "Add category field to test_steps"

# 应用迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

### 9.2 迁移脚本示例

```python
"""Add category field to test_steps

Revision ID: abc123
"""

def upgrade():
    op.add_column(
        'test_steps',
        sa.Column('category', sa.String(100), nullable=True)
    )

    # 数据迁移: 从关联的序列库填充 category
    op.execute("""
        UPDATE test_steps
        SET category = (
            SELECT category
            FROM test_sequences
            WHERE test_sequences.id = test_steps.sequence_library_id
        )
        WHERE sequence_library_id IS NOT NULL
    """)

def downgrade():
    op.drop_column('test_steps', 'category')
```

---

## 10. 性能优化

### 10.1 索引策略

```python
class TestStep(Base):
    __tablename__ = "test_steps"

    id = Column(UUID, primary_key=True)
    test_plan_id = Column(UUID, ForeignKey('test_plans.id'), index=True)  # 外键索引
    order = Column(Integer)
    status = Column(String(50), index=True)  # 常用过滤字段
    created_at = Column(DateTime, index=True)  # 常用排序字段

    # 复合索引
    __table_args__ = (
        Index('idx_test_plan_order', 'test_plan_id', 'order'),  # 常一起查询
    )
```

### 10.2 查询优化

```python
# ❌ N+1 查询问题
plans = db.query(TestPlan).all()
for plan in plans:
    steps = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).all()  # N 次查询

# ✅ 使用 JOIN 或 subquery
from sqlalchemy.orm import joinedload

plans = db.query(TestPlan).options(joinedload(TestPlan.steps)).all()

# 或者分别查询然后合并
plans = db.query(TestPlan).all()
plan_ids = [p.id for p in plans]
steps = db.query(TestStep).filter(TestStep.test_plan_id.in_(plan_ids)).all()
steps_by_plan = {}
for step in steps:
    steps_by_plan.setdefault(step.test_plan_id, []).append(step)
```

---

## 11. 测试

### 11.1 数据库模型测试

```python
def test_test_plan_creation(db_session):
    """测试创建测试计划"""
    plan = TestPlan(
        name="Test Plan 1",
        created_by="test_user"
    )
    db_session.add(plan)
    db_session.commit()

    assert plan.id is not None
    assert plan.created_at is not None
    assert plan.status == TestPlanStatus.DRAFT
```

### 11.2 Schema 验证测试

```python
def test_create_test_plan_schema_validation():
    """测试创建请求 Schema 验证"""
    # 有效数据
    valid_data = {
        "name": "Test Plan",
        "priority": 5,
        "created_by": "user"
    }
    schema = CreateTestPlanRequest(**valid_data)
    assert schema.name == "Test Plan"

    # 无效数据
    with pytest.raises(ValidationError):
        CreateTestPlanRequest(
            name="",  # 空名称
            priority=11,  # 超出范围
            created_by="user"
        )
```

---

## 12. 检查清单

实现新数据模型时检查:

- [ ] 表名使用复数形式（`test_plans` 而非 `test_plan`）
- [ ] 主键使用 UUID 类型，字段名为 `id`
- [ ] 外键字段名格式为 `{table_singular}_id`
- [ ] 包含审计字段（`created_at`, `updated_at`, `created_by`）
- [ ] 时间字段使用 `_at` 后缀，存储 UTC 时间
- [ ] 状态字段使用枚举类型
- [ ] 添加必要的索引（外键、常用查询字段）
- [ ] Pydantic Schema 与数据库模型对齐
- [ ] 前端 TypeScript 类型定义与后端对齐
- [ ] 编写数据库迁移脚本
- [ ] 编写单元测试

---

## 13. 参考示例

完整的数据模型示例请参考:
- [api-service/app/models/test_plan.py](api-service/app/models/test_plan.py)
- [api-service/app/schemas/test_plan.py](api-service/app/schemas/test_plan.py)
- [gui/src/features/TestManagement/types/index.ts](gui/src/features/TestManagement/types/index.ts)

