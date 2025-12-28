# 实现检查清单

## 为什么需要这个文档？

在开发过程中，我们连续发现了两个相同模式的bug：
- **BUG-001**: `TestStepUpdate` schema 缺少执行配置字段
- **BUG-002**: `TestPlanUpdate` schema 缺少 `status` 字段

这些bug有共同特点：
1. ✅ **功能设计层面是完整的** - 文档中有状态机、执行流程
2. ❌ **实现细节层面有遗漏** - Update schema 缺少关键字段
3. ❌ **静默失败** - Pydantic 忽略未定义字段，不报错

**根本问题**：缺少**从设计到实现的系统性检查机制**

---

## 问题分析：设计文档 vs 实现细节

### 现有文档的层次

| 文档 | 层次 | 覆盖范围 |
|------|------|----------|
| AGENTS.md | 架构设计 | 系统整体架构、功能模块 |
| TestManagement-Unified-Architecture.md | 功能设计 | 功能流程、UI组件结构 |
| DATA-MODEL-GUIDE.md | 数据模型 | 数据库模型、关系 |
| API (OpenAPI) | API 契约 | 请求/响应格式 |

### 缺失的层次

❌ **实现检查清单** - 从设计到代码的bridge
- API Schema 必需字段检查
- 状态转换完整性检查
- UI-API 数据流验证
- 错误处理覆盖度

---

## 核心原则：CRUD 完整性检查

对于每个实体（TestPlan, TestStep, TestCase等），确保：

### 1. Schema 完整性

**Create Schema** - 包含所有必需字段
**Update Schema** - 包含所有**可修改**字段（包括状态字段！）
**Response Schema** - 返回所有字段

#### ✅ 检查清单

```
□ Create schema 包含所有业务必需字段
□ Update schema 包含：
  □ 所有可编辑的业务字段
  □ status 字段（如果实体有状态机）
  □ 配置字段（如 timeout、retry 等）
□ Update schema 与数据模型字段一致性
□ 所有 Optional 字段都有 Field(None, ...) 定义
```

### 2. 状态机完整性

对于有状态的实体，确保：

```
□ 状态枚举已定义（draft, ready, queued, running, etc.）
□ 每个状态都有对应的UI显示（Badge颜色、图标）
□ 每个状态转换都有：
  □ 后端API支持（Update schema 包含 status）
  □ 前端按钮/操作
  □ 权限检查
  □ 状态转换验证
□ 状态机图已文档化（见 STATE-MACHINE.md）
```

### 3. UI-API 数据流完整性

```
□ 每个可编辑字段都有：
  □ 后端 Update schema 定义
  □ 前端表单控件
  □ 保存/更新 API 调用
  □ 成功/失败反馈
□ 字段命名一致性（前端 camelCase vs 后端 snake_case）
□ 类型映射正确（number → int, boolean → bool）
```

---

## 实现流程检查表

### Phase 1: 设计审查

在开始编码前：

```
□ 阅读功能设计文档（如 TestManagement-Unified-Architecture.md）
□ 识别所有实体及其状态机
□ 列出所有可编辑字段
□ 绘制状态转换图（见 STATE-MACHINE.md）
□ 确认所有状态转换都有对应的API和UI
```

### Phase 2: 后端实现

```
□ 定义 Pydantic Schema（Create, Update, Response）
  □ Update schema 检查：包含所有可编辑字段 + status
□ 实现 CRUD endpoint
□ 实现状态转换 endpoint（如需要）
□ 添加字段验证（Field constraints）
□ 编写单元测试覆盖所有字段
```

### Phase 3: 前端实现

```
□ 实现 API hooks (useCreate, useUpdate, useDelete)
□ 实现表单组件
  □ 每个可编辑字段都有对应控件
  □ 包含状态转换按钮
□ 实现状态显示（Badge, Icon）
□ 实现错误处理和用户反馈
```

### Phase 4: 集成测试

```
□ 测试 Create 流程（所有字段都能保存）
□ 测试 Update 流程：
  □ 每个字段都能单独更新
  □ 批量更新多个字段
  □ 状态转换功能正常
□ 测试状态机所有转换路径
□ 测试错误场景（无效数据、权限等）
```

---

## Schema 设计模式

### 模式 1: 分离 Create 和 Update

**推荐** - 最灵活，避免字段污染

```python
class TestPlanCreate(BaseModel):
    """Create时的必需字段"""
    name: str = Field(..., min_length=1)
    # ... 其他必需字段

class TestPlanUpdate(BaseModel):
    """Update时的所有可修改字段"""
    name: Optional[str] = Field(None, min_length=1)
    status: Optional[str] = None  # ⭐ 不要忘记 status!
    timeout_seconds: Optional[int] = None  # ⭐ 配置字段
    # ... 所有其他可编辑字段，全部 Optional
```

### 模式 2: 字段来源检查

创建 Update schema 时，参考：
1. **数据模型** - `api-service/app/models/*.py`
2. **Response schema** - 确保 Update 能修改 Response 中的字段
3. **前端表单** - 确保表单字段都在 Update schema 中

### 模式 3: 使用 Pydantic 配置避免静默失败

```python
class TestPlanUpdate(BaseModel):
    class Config:
        # 可选：拒绝未定义的字段（更严格）
        extra = "forbid"
```

---

## 自动化检查（TODO）

未来可以实现的自动检查：

```python
# scripts/check_schema_completeness.py

def check_update_schema_completeness(entity_name):
    """检查 Update schema 是否包含所有必要字段"""
    model_fields = get_model_fields(f"models/{entity_name}.py")
    update_fields = get_schema_fields(f"schemas/{entity_name}.py", "Update")

    # 检查 status 字段
    if 'status' in model_fields and 'status' not in update_fields:
        raise Error(f"{entity_name}Update 缺少 status 字段")

    # 检查配置字段
    config_fields = ['timeout', 'retry', 'continue_on_failure']
    missing = [f for f in config_fields if f in model_fields and f not in update_fields]
    if missing:
        raise Error(f"{entity_name}Update 缺少配置字段: {missing}")
```

---

## 总结：为什么会不断发现问题？

### 问题根源

1. **设计文档足够** - AGENTS.md、架构文档都很详细
2. **实现映射缺失** - 没有从设计到代码的系统性检查
3. **静默失败模式** - Pydantic 的 `exclude_unset=True` 静默忽略字段

### 解决方案

1. ✅ **使用本检查清单** - 每次实现CRUD功能时
2. ✅ **文档化状态机** - 参考 STATE-MACHINE.md
3. ✅ **Code Review 关注点** - Update schema 完整性
4. 🔄 **考虑自动化** - Schema 完整性检查脚本

### 关键原则

> **"Update schema 必须包含所有可编辑字段，包括 status 和配置字段"**

---

**创建时间**: 2025-11-23
**维护者**: 开发团队
**相关**: [BUGFIX-LOG.md](BUGFIX-LOG.md), [STATE-MACHINE.md](STATE-MACHINE.md)
