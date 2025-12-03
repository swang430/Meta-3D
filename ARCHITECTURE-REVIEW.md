# 架构审查与重构计划

**文档版本**: 1.0.0
**创建日期**: 2025-11-23
**审查范围**: 全系统前后端接口、数据模型、命名规范

---

## 1. 执行概要

### 1.1 审查背景

在测试管理功能开发和集成过程中，发现了大量前后端不匹配问题，主要源于：

1. **模块融合冲突**: "测试管理"与"测试计划"概念融合不完整
2. **Mock 数据移除影响**: 从 Mock 数据切换到真实数据库后暴露的接口不一致
3. **Legacy 代码兼容**: 新功能与现有功能（系统校准、虚拟路测）的集成冲突
4. **缺少统一规范**: API 设计、数据模型、命名约定缺乏系统性规范

### 1.2 核心问题分类

| 问题类别 | 严重程度 | 影响范围 | 示例 |
|---------|---------|---------|------|
| API 响应格式不一致 | 🔴 高 | 全局 | `{ steps: [] }` vs `[]` |
| 字段命名不统一 | 🟡 中 | 多模块 | `title` vs `name` |
| 类型定义不匹配 | 🔴 高 | 前后端 | `string` vs `string \| null` |
| 端点路径不规范 | 🟡 中 | API 层 | `/test-plans` vs `/test_plans` |
| 数据库模型与 API Schema 不同步 | 🔴 高 | 后端 | 字段缺失、类型不一致 |

---

## 2. 详细问题分析

### 2.1 API 设计不一致

#### 问题 1: 响应格式混乱

**现状**:
```typescript
// 不一致的响应格式
GET /test-sequences        → { items: [...] }  // 包装对象
GET /test-plans/{id}/steps → [...]             // 直接数组
GET /test-plans            → { total: N, items: [...] }  // 带分页信息
```

**影响**:
- 前端需要针对不同端点使用不同的数据提取逻辑
- 增加了代码复杂度和出错概率

**根本原因**:
- 缺少统一的 API 响应规范
- 不同开发阶段使用了不同的设计模式

#### 问题 2: 字段命名不统一

**现状**:
```typescript
// 数据库模型
class TestSequence:
    name: str           // 序列名称

// 前端期望
interface TestStep:
    title: string       // 步骤标题 (期望从 sequence.name 获取)

// 后端返回
{
  "name": "...",        // 数据库字段
  "title": null         // 前端期望字段
}
```

**影响**:
- 前端无法直接显示数据
- 需要额外的数据转换层

**根本原因**:
- 数据库模型、API Schema、前端类型定义独立演进
- 缺少统一的领域模型定义

#### 问题 3: 可选性不一致

**现状**:
```typescript
// 前端类型定义 (types/index.ts)
interface TestStep {
  title: string           // 必填
  description: string     // 必填
  category: string        // 必填
}

// 后端 Schema
class TestStepResponse(BaseModel):
    title: Optional[str] = None     // 可选
    description: Optional[str] = None
    category: Optional[str] = None
```

**影响**:
- TypeScript 类型检查失效
- 运行时错误（访问 undefined）

**根本原因**:
- 前后端类型定义分离
- 缺少自动化类型同步机制

### 2.2 数据模型不一致

#### 问题 4: 数据库模型与业务逻辑分离

**现状**:
```python
# 数据库模型 (models/test_plan.py)
class TestStep(Base):
    name = Column(String, nullable=True)
    sequence_library_id = Column(UUID, ForeignKey(...), nullable=True)
    # 步骤元数据在 sequence_library_id 存在时应从序列库加载

# API 端点需要手动填充
def get_test_steps():
    # 手动查询序列库并填充 title, category
    if step.sequence_library_id:
        sequence = db.query(TestSequence).filter(...)
        step_dict["title"] = sequence.name  # 手动映射
```

**影响**:
- 每个端点都需要重复相同的填充逻辑
- 容易遗漏，导致数据不完整

**根本原因**:
- 缺少数据访问对象（DAO）模式
- 业务逻辑与数据访问层耦合

### 2.3 Legacy 功能兼容问题

#### 问题 5: 系统校准模块未更新

**现状**:
- 系统校准仍使用旧的 Mock 数据结构
- 未适配新的数据库 Schema
- 与测试管理模块的集成不完整

**文件位置**:
- `api-service/app/api/calibration.py` - API 端点
- `gui/src/features/SystemCalibration/` - 前端组件

**需要更新**:
1. 数据库模型（已存在但可能不完整）
2. API 端点与新 Schema 对齐
3. 前端类型定义
4. 前端 API 调用

#### 问题 6: 虚拟路测模块未集成

**现状**:
- 虚拟路测是独立模块
- 未与测试管理统一架构集成
- 可能存在重复的概念和数据结构

**文件位置**:
- `VirtualRoadTest-*.md` - 设计文档
- 实现代码可能缺失或分散

---

## 3. 统一设计规范

### 3.1 API 设计规范

#### 3.1.1 端点命名规范

```
规则: 使用 RESTful 风格，使用连字符（kebab-case）

✅ 正确:
  GET  /v1/test-plans
  POST /v1/test-plans/{id}/steps
  GET  /v1/test-sequences

❌ 错误:
  GET  /v1/test_plans        // 不要使用下划线
  POST /v1/testPlans         // 不要使用驼峰命名
  GET  /v1/getSequences      // 不要在路径中使用动词
```

#### 3.1.2 响应格式规范

**原则**: 统一使用包装对象，除非是单一资源查询

```typescript
// 列表查询（带分页）
{
  "total": number,
  "items": T[],
  "page"?: number,
  "page_size"?: number
}

// 列表查询（不带分页）
{
  "items": T[]
}

// 单一资源
T

// 操作成功（无返回数据）
{
  "message": string
}

// 错误响应
{
  "message": string,
  "detail"?: string,
  "errors"?: Record<string, string[]>
}
```

**实施计划**:
1. 修改所有返回数组的端点，使用 `{ items: [...] }` 包装
2. 更新前端 API 调用逻辑
3. 更新 OpenAPI 规范

#### 3.1.3 字段命名规范

**原则**: 前后端使用统一的字段名，遵循 snake_case（后端）和 camelCase（前端）的转换规则

```python
# 后端 (Python - snake_case)
class TestStep:
    sequence_library_id: UUID
    created_at: datetime
    test_plan_id: UUID
```

```typescript
// 前端 (TypeScript - camelCase)
interface TestStep {
  sequenceLibraryId: string
  createdAt: string
  testPlanId: string
}
```

**自动转换**:
- 后端使用 Pydantic 的 `alias_generator` 自动转换
- 前端使用 Axios 的拦截器自动转换

### 3.2 数据模型规范

#### 3.2.1 领域模型定义

**统一术语表**:

| 概念 | 英文 | 数据库表 | 字段关键名 |
|-----|------|---------|-----------|
| 测试计划 | Test Plan | test_plans | name, description |
| 测试步骤 | Test Step | test_steps | title (显示), name (存储) |
| 序列库 | Sequence Library | test_sequences | name, category |
| 测试例 | Test Case | test_cases | name, test_type |
| 测试队列 | Test Queue | test_queue | position, priority |

**规则**:
1. **显示名称统一**: 所有面向用户的字段使用 `title`（前端）/ `name`（后端）
2. **分类字段统一**: 使用 `category` 而非 `type`（避免与 Python 关键字冲突）
3. **时间字段统一**: 创建时间 `created_at`，更新时间 `updated_at`，开始时间 `started_at`

#### 3.2.2 DTO 层设计

**引入 DTO（Data Transfer Object）模式**:

```python
# 后端: 数据库模型 → DTO → API Response
class TestStep(Base):              # 数据库模型
    """原始数据库模型"""
    pass

class TestStepDTO:                 # 数据传输对象
    """包含业务逻辑的数据对象"""
    @classmethod
    def from_db(cls, db_model, db_session):
        """从数据库模型创建，自动填充关联数据"""
        dto = cls(**db_model.__dict__)
        if db_model.sequence_library_id:
            sequence = get_sequence(db_session, db_model.sequence_library_id)
            dto.title = sequence.name
            dto.category = sequence.category
        return dto

class TestStepResponse(BaseModel): # API 响应 Schema
    """API 响应格式"""
    pass
```

**好处**:
- 业务逻辑集中在 DTO 层
- API 端点只负责序列化和反序列化
- 减少重复代码

### 3.3 类型系统规范

#### 3.3.1 可选性原则

```typescript
// 前端类型定义原则
interface TestStep {
  // 1. 必填字段: 后端保证一定返回
  id: string
  testPlanId: string
  order: number
  status: TestStepStatus

  // 2. 可选字段: 可能为 null 或 undefined
  title?: string                    // 显示名称（可能从序列库加载）
  description?: string | null       // 允许 null
  sequenceLibraryId?: string        // 可选关联

  // 3. 运行时字段: 只在特定状态下存在
  startedAt?: string                // 只在 status='running' 时存在
  completedAt?: string              // 只在 status='completed' 时存在
}
```

**后端对应**:
```python
class TestStepResponse(BaseModel):
    # 必填字段
    id: UUID
    test_plan_id: UUID
    order: int
    status: str

    # 可选字段 - 使用 Optional
    title: Optional[str] = None
    description: Optional[str] = None
    sequence_library_id: Optional[UUID] = None

    # 运行时字段
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
```

#### 3.3.2 类型生成工具链

**建议引入工具**:
1. **后端 → OpenAPI**: 使用 FastAPI 自动生成
2. **OpenAPI → TypeScript**: 使用 `openapi-typescript` 生成前端类型
3. **验证**: 使用 `zod` 在运行时验证类型

**工作流**:
```bash
# 1. 后端生成 OpenAPI 规范
cd api-service
python scripts/generate_openapi.py > openapi.json

# 2. 生成 TypeScript 类型
cd gui
npx openapi-typescript ../openapi.json -o src/types/api.generated.ts

# 3. 前端使用生成的类型
import type { TestStepResponse } from '@/types/api.generated'
```

---

## 4. 重构路线图

### 4.1 Phase 1: 建立规范和基础设施 (Week 1)

#### 任务清单

- [ ] **文档更新**
  - [ ] 创建 `API-DESIGN-GUIDE.md` - API 设计规范
  - [ ] 创建 `DATA-MODEL-GUIDE.md` - 数据模型规范
  - [ ] 更新 `CLAUDE.md` - 添加新规范链接

- [ ] **工具链设置**
  - [ ] 配置 OpenAPI 自动生成脚本
  - [ ] 配置 TypeScript 类型生成
  - [ ] 添加 pre-commit hooks 验证一致性

- [ ] **DTO 层框架**
  - [ ] 创建 `api-service/app/dto/` 目录
  - [ ] 实现 `BaseDTO` 基类
  - [ ] 实现 `TestStepDTO` 示例

### 4.2 Phase 2: 测试管理模块标准化 (Week 2)

#### 任务清单

- [ ] **后端重构**
  - [ ] 统一所有 API 响应格式为 `{ items: [...] }`
  - [ ] 实现所有 DTO 类
  - [ ] 更新所有 API 端点使用 DTO
  - [ ] 添加单元测试

- [ ] **前端重构**
  - [ ] 更新所有 API 调用适配新格式
  - [ ] 使用生成的类型替换手动定义
  - [ ] 添加运行时类型验证（可选）

- [ ] **验证**
  - [ ] 端到端测试所有测试管理功能
  - [ ] 修复发现的问题

### 4.3 Phase 3: Legacy 模块迁移 (Week 3)

#### 3.3.1 系统校准模块

- [ ] **数据库层**
  - [ ] 审查现有数据库模型
  - [ ] 与测试管理模型对齐
  - [ ] 添加缺失的字段和关系

- [ ] **API 层**
  - [ ] 使用 DTO 模式重构
  - [ ] 统一响应格式
  - [ ] 更新 OpenAPI 规范

- [ ] **前端层**
  - [ ] 更新类型定义
  - [ ] 更新 API 调用
  - [ ] 集成测试

#### 3.3.2 虚拟路测模块

- [ ] **架构设计**
  - [ ] 评估与测试管理的集成方案
  - [ ] 定义数据模型
  - [ ] 设计 API 端点

- [ ] **实现**
  - [ ] 后端 API 实现
  - [ ] 前端组件实现
  - [ ] 集成测试

### 4.4 Phase 4: 文档和培训 (Week 4)

- [ ] **文档完善**
  - [ ] 更新 AGENTS.md
  - [ ] 创建 API 参考文档
  - [ ] 创建开发者指南

- [ ] **示例代码**
  - [ ] 创建新模块开发模板
  - [ ] 创建 API 调用示例
  - [ ] 创建数据模型示例

---

## 5. 立即行动项

### 5.1 紧急修复（今天完成）

1. **修复步骤显示问题** ✅ 已完成
   - 前端 API 调用格式修正
   - 后端响应填充序列库信息

2. **统一测试步骤响应格式**
   ```python
   # 当前: 直接返回数组
   @router.get("/{test_plan_id}/steps")
   def get_test_steps(...):
       return steps  # List[TestStepResponse]

   # 修改为: 包装对象
   @router.get("/{test_plan_id}/steps")
   def get_test_steps(...):
       return {"items": steps}
   ```

3. **更新前端 API 调用**
   ```typescript
   // 当前
   export const getTestSteps = async (planId: string): Promise<TestStep[]> => {
     const response = await client.get<TestStep[]>(...)
     return response.data
   }

   // 修改为
   export const getTestSteps = async (planId: string): Promise<TestStep[]> => {
     const response = await client.get<{ items: TestStep[] }>(...)
     return response.data.items
   }
   ```

### 5.2 短期改进（本周完成）

1. **创建 API 设计规范文档**
2. **实现第一个 DTO 示例（TestStepDTO）**
3. **配置 OpenAPI 自动生成**
4. **审查所有现有 API 端点，记录不一致问题**

### 5.3 中期目标（本月完成）

1. **完成测试管理模块标准化**
2. **迁移系统校准模块**
3. **建立 CI/CD 检查**

---

## 6. 成功指标

### 6.1 技术指标

- [ ] **一致性**: 100% API 端点遵循统一响应格式
- [ ] **类型安全**: 前后端类型定义自动同步，0 手动维护
- [ ] **测试覆盖**: 所有 API 端点有集成测试
- [ ] **文档完整**: 所有 API 有 OpenAPI 文档

### 6.2 开发效率指标

- [ ] **Bug 率下降**: 接口不匹配相关 bug 减少 90%
- [ ] **开发速度**: 新功能开发时间减少 50%
- [ ] **维护成本**: 前后端同步维护时间减少 70%

### 6.3 用户体验指标

- [ ] **稳定性**: 无因接口不匹配导致的运行时错误
- [ ] **功能完整**: 所有功能正常工作
- [ ] **性能**: API 响应时间 < 200ms (p95)

---

## 7. 风险和缓解

### 7.1 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|-----|-------|------|---------|
| 破坏现有功能 | 中 | 高 | 全面回归测试 + 分阶段部署 |
| 开发时间超预期 | 高 | 中 | 优先级排序 + 增量迁移 |
| 团队抵触 | 低 | 低 | 充分沟通 + 示例代码 |
| 工具链学习曲线 | 中 | 低 | 文档 + 培训 |

### 7.2 回滚策略

- **Git 分支策略**: 每个 Phase 使用独立分支
- **Feature Flags**: 新旧实现并存，通过配置切换
- **数据库迁移**: 可逆的 migration scripts
- **前端兼容层**: 保留旧 API 调用接口，内部切换到新实现

---

## 8. 附录

### 8.1 相关文档

- [AGENTS.md](AGENTS.md) - 系统架构文档
- [TestManagement-Unified-Architecture.md](TestManagement-Unified-Architecture.md) - 测试管理架构
- [API-COMPATIBILITY.md](API-COMPATIBILITY.md) - API 兼容性记录
- [CLAUDE.md](CLAUDE.md) - Claude Code 工作指南

### 8.2 参考资源

- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [RESTful API Design Guide](https://restfulapi.net/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

### 8.3 变更日志

| 版本 | 日期 | 变更内容 | 作者 |
|-----|------|---------|------|
| 1.0.0 | 2025-11-23 | 初始版本 | Claude |

