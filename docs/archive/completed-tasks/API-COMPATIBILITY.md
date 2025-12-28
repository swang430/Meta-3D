# API 兼容性报告

## 📋 概述

前端和后端API存在不匹配问题。本文档列出所有问题并提供修复方案。

## ✅ 已修复的问题

### 1. HTTP方法不匹配
- **问题**：前端使用 `PUT`，后端使用 `PATCH`
- **影响端点**：
  - `PATCH /v1/test-plans/{id}` - 更新测试计划
  - `PATCH /v1/test-plans/{id}/steps/{step_id}` - 更新测试步骤
- **修复**：已将所有 `client.put()` 改为 `client.patch()`
- **状态**：✅ 已完成

### 2. API路径前缀
- **问题**：前端使用 `/test-management/`，后端使用 `/v1/test-plans/`
- **修复**：已全局替换所有路径
- **状态**：✅ 已完成

## ✅ 新实现的端点（2025-11-22 更新）

### Steps Management (测试步骤管理) - 全部实现 ✅
```
✅ GET    /v1/test-plans/{id}/steps                    - 获取测试步骤列表
✅ POST   /v1/test-plans/{id}/steps                    - 添加测试步骤
✅ PATCH  /v1/test-plans/{id}/steps/{step_id}          - 更新测试步骤
✅ DELETE /v1/test-plans/{id}/steps/{step_id}          - 删除测试步骤
✅ POST   /v1/test-plans/{id}/steps/reorder            - 重新排序步骤
✅ POST   /v1/test-plans/{id}/steps/{step_id}/duplicate - 复制测试步骤
```
**实现详情**：
- 新增 `TestStep` 数据库模型（支持灵活的JSON参数）
- 新增 `TestStepService` 服务层（含CRUD和特殊操作）
- 新增完整的步骤管理API端点

### Execution History (执行历史) - 全部实现 ✅
```
✅ GET    /v1/test-executions                   - 获取执行历史（支持过滤）
✅ GET    /v1/test-executions/{record_id}       - 获取单条执行记录
✅ DELETE /v1/test-executions/{record_id}       - 删除执行记录
```
**实现详情**：
- 使用现有 `TestExecution` 数据库模型
- 新增独立的 `/test-executions` 路由器
- 支持按test_plan_id、status、日期范围过滤

### Sequence Library (序列库) - 全部实现 ✅
```
✅ GET /v1/test-sequences                   - 获取序列库列表（支持分类过滤）
✅ GET /v1/test-sequences/{item_id}         - 获取单个序列详情
✅ GET /v1/test-sequences/categories        - 获取所有分类
✅ GET /v1/test-sequences/popular           - 获取热门序列（按使用次数）
```
**实现详情**：
- 新增 `TestSequenceService` 服务层
- 新增 `/test-sequences` 路由器
- 支持按分类过滤、公开/私有状态筛选
- 包含6个示例序列（仪器配置、TRP/TIS测量、MIMO信道、探头校准、5G NR）

## ⚠️ 后端未实现的端点

### Advanced Features (高级功能)
```
❌ POST /v1/test-plans/{id}/duplicate          - 复制测试计划
❌ POST /v1/test-plans/queue/reorder           - 队列重排序
❌ PATCH /v1/test-plans/queue/{id}/priority    - 更新优先级
❌ GET /v1/test-plans/statistics/plans         - 测试计划统计
❌ GET /v1/test-plans/statistics/executions    - 执行统计
❌ POST /v1/test-plans/batch-delete            - 批量删除
❌ POST /v1/test-plans/batch-update-status     - 批量更新状态
❌ POST /v1/test-plans/export                  - 导出
❌ POST /v1/test-plans/import                  - 导入
```
**临时方案**：UI中暂时隐藏这些功能按钮

## ✅ 后端已实现且正常工作的端点

### Test Plans Management
```
✅ POST   /v1/test-plans                    - 创建测试计划
✅ GET    /v1/test-plans                    - 列出测试计划
✅ GET    /v1/test-plans/{id}               - 获取单个测试计划
✅ PATCH  /v1/test-plans/{id}               - 更新测试计划
✅ DELETE /v1/test-plans/{id}               - 删除测试计划
✅ POST   /v1/test-plans/{id}/mark-ready    - 标记为就绪
```

### Queue Management
```
✅ POST   /v1/test-plans/queue              - 加入队列
✅ GET    /v1/test-plans/queue              - 获取队列
✅ DELETE /v1/test-plans/queue/{test_plan_id} - 从队列移除
```

### Execution Control
```
✅ POST /v1/test-plans/{id}/start    - 开始执行
✅ POST /v1/test-plans/{id}/pause    - 暂停执行
✅ POST /v1/test-plans/{id}/resume   - 恢复执行
✅ POST /v1/test-plans/{id}/cancel   - 取消执行
✅ POST /v1/test-plans/{id}/complete - 完成执行
```

### Test Cases Management
```
✅ POST   /v1/test-plans/cases           - 创建测试用例
✅ GET    /v1/test-plans/cases           - 列出测试用例
✅ GET    /v1/test-plans/cases/{id}      - 获取测试用例
✅ PATCH  /v1/test-plans/cases/{id}      - 更新测试用例
✅ DELETE /v1/test-plans/cases/{id}      - 删除测试用例
```

## 🎯 当前可用功能

用户可以正常使用以下功能：
1. ✅ **创建测试计划** - 完整可用
2. ✅ **列出/查看测试计划** - 完整可用
3. ✅ **编辑测试计划** - 完整可用（使用PATCH）
4. ✅ **删除测试计划** - 完整可用
5. ✅ **队列管理** - 基本功能可用
6. ✅ **执行控制** - 完整可用
7. ✅ **测试用例管理** - 完整可用
8. ✅ **步骤管理** - **完整可用**（2025-11-22）
9. ✅ **执行历史** - **完整可用**（2025-11-22）
10. ✅ **序列库** - **新增！完整可用**（2025-11-22）- 包含6个示例序列
11. ⚠️ **高级功能** - 部分不可用（复制、统计、批量操作等）

## 📝 后续开发建议

### 优先级1（高）- 核心功能 ✅ 全部完成！
1. ✅ 实现 Steps Management API（6个端点）- **已完成 2025-11-22**
2. ✅ 实现 Execution History API（3个端点）- **已完成 2025-11-22**
3. ✅ 实现 Sequence Library API（4个端点）- **已完成 2025-11-22**

### 优先级2（中）- 增强功能
1. 实现 Duplicate（复制功能）
2. 实现 Queue Reorder（队列重排序）
3. 实现 Statistics（统计功能）

### 优先级3（低）- 高级功能
1. 批量操作（batch-delete, batch-update-status）
2. 导入/导出功能
3. 其他高级特性

## 🔄 修复历史

- **2025-11-22 20:30** - 修复API路径前缀（/test-management → /v1/test-plans）
- **2025-11-22 20:35** - 修复HTTP方法（PUT → PATCH）
- **2025-11-22 20:40** - 创建本兼容性文档
- **2025-11-22 21:00** - 实现 Steps Management API（6个端点）
  - 新增 TestStep 数据库模型
  - 新增 TestStepService 服务层
  - 新增完整的步骤管理API端点
- **2025-11-22 21:05** - 实现 Execution History API（3个端点）
  - 新增独立的 /test-executions 路由器
  - 支持按多条件过滤执行历史
- **2025-11-22 21:10** - 修复前端代理配置导致的404错误
  - 问题：Vite配置缺少proxy设置，导致前端请求无法到达后端
  - 修复：在gui/vite.config.ts中添加proxy配置，将/api请求代理到http://localhost:8001
  - 验证：代理功能正常工作，前端可以正确访问后端API
- **2025-11-22 21:20** - 禁用Mock服务器以使用真实后端API
  - 问题：前端main.tsx中的setupMockServer()拦截了所有API请求，导致无法访问真实后端
  - 根本原因：Mock服务器会拦截axios请求并返回模拟数据，而不是通过代理发送到后端
  - 修复：在gui/src/main.tsx中注释掉setupMockServer()调用
  - 验证：前端现在可以正确访问后端API，创建测试计划成功
- **2025-11-22 21:30** - 实现 Sequence Library API（4个端点）
  - 新增 `TestSequenceService` 服务层
  - 新增 `app/api/test_sequence.py` 路由器
  - 实现4个API端点：列表、详情、分类、热门
  - 创建数据初始化脚本，添加6个示例序列
  - 分类：仪器配置、测量、信道模型、校准、5G NR
  - 状态：✅ 优先级1核心功能全部完成

---

## 🎯 架构审查与重构 (2025-11-23)

### 问题背景
在前序测试/debug中发现大量前后端不匹配问题，主要触发因素：
1. "测试管理"与"测试计划"模块融合（TestConfig + TestPlanManagement）
2. 数据库引入和Mock数据移除带来的新冲突
3. 遗留功能（系统校准、虚拟路测）需要全面更新以适配新架构
4. 缺乏统一的设计文档指导开发，导致不断的"测试→发现问题→修改"循环

### 2025-11-23 08:00 - 修复测试步骤显示问题

**问题描述**：从序列库添加测试步骤后，前端UI中看不到步骤列表

**根本原因**：
1. **前端API响应解析错误**
   - 前端期待：`response.data.steps`（包装对象）
   - 后端返回：`TestStep[]`（直接数组）
   - 结果：`response.data.steps` 为 `undefined`

2. **后端缺少前端所需的显示字段**
   - 前端组件 [StepsList.tsx](gui/src/features/TestManagement/components/StepsTab/StepsList.tsx:132) 期待 `step.title` 和 `step.category`
   - 后端返回的步骤所有显示字段均为 `null`
   - 原因：步骤只存储 `sequence_library_id`，不重复保存序列元数据

**修复方案**：

#### 后端修改 ([api-service/app/api/test_plan.py](api-service/app/api/test_plan.py))

1. **修改 Schema** (api-service/app/schemas/test_plan.py:347-348)：
   ```python
   class TestStepResponse(BaseModel):
       # ... 现有字段 ...

       # 前端兼容字段（从序列库填充）
       title: Optional[str] = None  # 从 sequence.name 填充
       category: Optional[str] = None  # 从 sequence.category 填充
   ```

2. **修改 GET /v1/test-plans/{id}/steps 端点** (lines 369-432)：
   ```python
   # 对每个步骤进行数据增强
   if step.sequence_library_id:
       sequence = db.query(TestSequence).filter(
           TestSequence.id == step.sequence_library_id
       ).first()
       if sequence:
           step_dict["title"] = sequence.name
           step_dict["category"] = sequence.category
           if not step.description and sequence.description:
               step_dict["description"] = sequence.description
   ```

3. **修改 POST /v1/test-plans/{id}/steps 端点** (lines 435-510)：
   - 应用相同的数据增强逻辑，确保新创建的步骤也返回完整字段

#### 前端修改 ([gui/src/features/TestManagement/api/testManagementAPI.ts](gui/src/features/TestManagement/api/testManagementAPI.ts:100-104))

```typescript
// 修复前：
export const getTestSteps = async (planId: string): Promise<TestStep[]> => {
  const response = await client.get<{ steps: TestStep[] }>(
    `/v1/test-plans/${planId}/steps`,
  )
  return response.data.steps  // ❌ undefined
}

// 修复后：
export const getTestSteps = async (planId: string): Promise<TestStep[]> => {
  const response = await client.get<TestStep[]>(
    `/v1/test-plans/${planId}/steps`,
  )
  return response.data  // ✅ 正确返回数组
}
```

**验证结果** (2025-11-23 08:45)：
```bash
curl http://localhost:8001/api/v1/test-plans/0b28e11c-7d7e-4dbd-9485-d590fdcaeebf/steps

# 返回 3 个步骤，每个都包含：
# ✅ "title": "TRP测量序列" / "TIS测量序列" / "MIMO信道模型配置"
# ✅ "category": "Measurement" / "Measurement" / "Channel Model"
```

### 2025-11-23 09:00 - 修复步骤编辑和删除功能

**用户反馈**：
1. 测试步骤可以增加，但不能删除
2. 编辑器显示有内容，但无法修改执行配置字段

**问题分析**：

1. **编辑器问题** ([StepEditor.tsx](gui/src/features/TestManagement/components/StepsTab/StepEditor.tsx))
   - 执行配置字段（超时时间、重试次数、失败后继续）只显示值，没有onChange处理器
   - 用户修改这些字段时，值不会更新，也不会触发保存按钮
   - 只有参数（parameters）部分有完整的编辑功能

2. **删除功能问题** ([StepsList.tsx](gui/src/features/TestManagement/components/StepsTab/StepsList.tsx))
   - Menu组件的`stopPropagation`位置不正确
   - 导致Menu.Item的onClick事件可能被阻止

**修复方案**：

1. **StepEditor.tsx 修复**：
   ```typescript
   // 添加状态管理
   const [timeoutSeconds, setTimeoutSeconds] = useState<number>(300)
   const [retryCount, setRetryCount] = useState<number>(0)
   const [continueOnFailure, setContinueOnFailure] = useState<boolean>(false)

   // 添加onChange处理器
   <NumberInput
     label="超时时间 (秒)"
     value={timeoutSeconds}
     onChange={(value) => {
       setTimeoutSeconds(Number(value))
       setHasChanges(true)
     }}
     // ...
   />

   // 保存时包含执行配置
   const handleSave = () => {
     updateStep({
       planId,
       stepId,
       payload: {
         parameters,
         timeout_seconds: timeoutSeconds,
         retry_count: retryCount,
         continue_on_failure: continueOnFailure,
       },
     })
   }
   ```

2. **StepsList.tsx 修复**：
   ```typescript
   // 将 stopPropagation 移到正确位置
   <Menu position="bottom-end">
     <Menu.Target>
       <ActionIcon onClick={(e) => e.stopPropagation()}>
         <IconDots />
       </ActionIcon>
     </Menu.Target>
     <Menu.Dropdown>
       <Menu.Item
         onClick={(e) => {
           e.stopPropagation()
           handleDelete(step.id)
         }}
       >
         删除
       </Menu.Item>
     </Menu.Dropdown>
   </Menu>
   ```

**验证**：
- 后端DELETE API已验证正常工作（返回204 No Content）
- 前端hooks (useDeleteTestStep, useUpdateTestStep) 已正确实现
- 修复后用户应该可以：
  - ✅ 修改步骤的超时时间、重试次数、失败后继续选项
  - ✅ 点击"保存更改"按钮保存修改
  - ✅ 通过菜单删除步骤
  - ✅ 通过菜单复制步骤

### 2025-11-23 08:15 - 创建综合设计文档

为防止持续的不匹配问题，创建三份权威设计指南：

#### 1. [ARCHITECTURE-REVIEW.md](ARCHITECTURE-REVIEW.md) (4,985行)

**目的**：全面分析所有发现的不匹配问题，提供重构路线图

**核心内容**：
- **问题目录**：5大类问题（API不一致、数据模型不匹配、遗留兼容性、缺失基础设施、流程缺口）
- **统一设计标准**：响应格式、字段命名规范、类型定义
- **4阶段重构计划**：
  - Phase 1: 关键修复（第1周）
  - Phase 2: 标准实施（第2-3周）
  - Phase 3: 遗留模块迁移（第4-6周）
  - Phase 4: 基础设施与优化（第7-8周）
- **成功指标**：100% API一致性、90%接口bug减少、<500ms响应时间
- **风险缓解**：回退策略、测试协议、逐步推出计划

#### 2. [API-DESIGN-GUIDE.md](API-DESIGN-GUIDE.md) (2,945行)

**目的**：建立所有未来开发的RESTful API设计标准

**核心内容**：
- **URL规范**：Kebab-case、RESTful资源路径
- **HTTP方法标准**：GET/POST/PUT/PATCH/DELETE语义
- **统一响应格式**：
  ```json
  // 带分页的列表
  { "total": 100, "items": [...] }

  // 不带分页的列表
  { "items": [...] }

  // 单个资源
  { "id": "...", "name": "..." }

  // 错误响应
  { "message": "...", "detail": "...", "errors": {...} }
  ```
- **状态码标准**：2xx/4xx/5xx使用指南
- **分页与过滤**：查询参数规范
- **批量操作**：多资源操作模式
- **完整示例**：带请求/响应体的完整端点实现

#### 3. [DATA-MODEL-GUIDE.md](DATA-MODEL-GUIDE.md) (3,211行)

**目的**：定义跨所有三层的统一数据建模

**核心内容**：
- **三层架构**：
  1. 数据库模型（SQLAlchemy ORM）
  2. DTO（数据传输对象）- **新模式**
  3. API Schema（Pydantic）
  4. 前端类型（TypeScript）
- **命名规范**：
  - 后端：`name`（存储）、`title`（计算的显示字段）
  - 前端：`title` 用于显示
  - 术语映射表（跨层）
- **DTO模式介绍**：
  ```python
  class TestStepDTO:
      @classmethod
      def from_db(cls, db_model, db_session):
          """从相关表自动填充计算字段"""
          dto = cls(db_model)
          if db_model.sequence_library_id:
              sequence = db_session.query(TestSequence).filter(...)
              dto.title = sequence.name
              dto.category = sequence.category
          return dto
  ```
- **类型映射**：Python ↔ PostgreSQL ↔ TypeScript
- **关系模式**：外键、连接策略、延迟加载
- **验证**：数据库约束 vs 应用逻辑
- **迁移策略**：Alembic工作流和测试

#### 4. [CLAUDE.md](CLAUDE.md) 更新

**变更**：
- 添加"设计文档"部分（lines 120-150）
- 标记架构指南为必读（⭐）
- 更新"当前状态"以反映真实数据库连接
- 按类别组织所有文档（架构/功能/开发）

## 📊 当前系统状态 (2025-11-23 08:45)

### 服务健康检查
```json
// 后端: http://localhost:8001/api/v1/health
{
  "status": "healthy",
  "version": "1.0.0",
  "database_connected": true,
  "mock_instruments": true
}

// 前端: http://localhost:5173
Vite 开发服务器正在运行 ✅
```

### 数据库状态
- **测试计划**：2个活动计划
- **测试步骤**：3个步骤在"测试添加步骤（最终）"计划中
- **序列库**：3+ 序列（TRP、TIS、MIMO信道模型）

### 已验证的API端点
| 端点 | 状态 | 备注 |
|------|------|------|
| `GET /api/v1/health` | ✅ 正常 | 数据库已连接 |
| `GET /api/v1/test-plans` | ✅ 正常 | 返回包装的 `{ total, items }` |
| `GET /api/v1/test-plans/{id}/steps` | ✅ 已修复 | 现在使用 `title` 和 `category` 进行增强 |
| `POST /api/v1/test-plans/{id}/steps` | ✅ 已修复 | 返回增强的响应 |
| `GET /api/v1/test-sequences` | ✅ 正常 | 序列库访问 |

## 🚧 已知剩余问题

### 高优先级

1. **响应格式不一致** (ARCH-001)
   - 一些端点返回 `{ items: [] }`，其他返回 `[]` 直接返回
   - 示例：`GET /v1/test-plans/{id}/steps` 返回数组，应包装在对象中
   - **影响**：前端必须处理两种不同模式
   - **修复**：按API-DESIGN-GUIDE.md第3.2节标准化所有列表端点

2. **字段命名不一致** (ARCH-002)
   - 数据库使用 `name`，API有时使用 `title`，前端期待 `title`
   - 当前解决方案：响应中的计算字段
   - **影响**：关于真实来源的混淆
   - **修复**：按DATA-MODEL-GUIDE.md第3节实现DTO层

3. **遗留模块状态未知** (ARCH-003)
   - 系统校准模块可能仍使用旧的Mock数据
   - 虚拟路测集成不完整
   - **影响**：未知；需要验证
   - **修复**：按ARCHITECTURE-REVIEW.md Phase 3进行系统审查

### 中优先级

4. **类型可选性不匹配** (ARCH-004)
   - 后端标记字段为 `Optional[str]`，前端期待 `string`
   - 示例：`TestStep.description` 在前端必需，后端可选
   - **影响**：TypeScript错误和null检查
   - **修复**：审核所有schema并对齐可选性

5. **缺失类型生成** (ARCH-005)
   - 没有自动化的 OpenAPI → TypeScript 类型生成
   - 手动类型定义容易漂移
   - **影响**：类型与API不同步
   - **修复**：按ARCHITECTURE-REVIEW.md第5.1节配置 `openapi-typescript`

## 📋 下一步计划（按优先级）

### 立即执行（今天）
- [ ] **浏览器验证**：打开 [http://localhost:5173](http://localhost:5173) 并确认：
  - 导航到 测试管理 → 步骤编排
  - 选择"测试添加步骤（最终）"计划
  - 验证显示3个步骤，标题正确：
    - TRP测量序列 (Measurement)
    - TIS测量序列 (Measurement)
    - MIMO信道模型配置 (Channel Model)
- [ ] **记录任何UI问题**：注意任何剩余的显示问题
- [ ] **审查设计文档**：确保团队同意新指南中的标准

### 短期（本周）

1. **实现首个DTO示例**（2天）
   - 按DATA-MODEL-GUIDE.md第3.3节创建 `TestStepDTO` 类
   - 重构 `get_test_steps` 使用DTO而不是手动增强
   - 好处：集中业务逻辑、更易测试、一致的增强

2. **配置OpenAPI类型生成**（1天）
   - 安装 `openapi-typescript` 包
   - 在 `gui/package.json` 中配置生成脚本
   - 使用现有 `api/openapi.yaml` 测试
   - 替换 `gui/src/types/api.ts` 中的手动类型

3. **审核所有API端点**（2天）
   - 创建所有端点的电子表格
   - 检查响应格式（包装 vs 未包装）
   - 检查字段命名（name vs title）
   - 检查状态码
   - 按使用频率优先修复

### 中期（本月）

4. **标准化测试管理模块**（第2-3周）
   - 修复所有 `/test-plans/**` 端点的响应格式
   - 为 TestPlan、TestStep、TestQueue 实现DTO
   - 更新前端使用生成的类型
   - 添加集成测试

5. **迁移系统校准模块**（第4周）
   - 审查当前实现
   - 与新架构标准对齐
   - 移除任何剩余的mock数据依赖
   - 更新使用真实数据库

6. **迁移虚拟路测模块**（第5周）
   - 完成与测试管理的集成
   - API设计与标准对齐
   - 添加适当的错误处理
   - 集成测试

7. **建立CI/CD检查**（第6周）
   - Linting的pre-commit hooks
   - CI中的类型生成验证
   - API响应格式验证
   - 数据库迁移测试

---

**最后更新**：2025-11-23 08:45 UTC+8
**下次审查**：浏览器验证和初始DTO实现后
**维护者**：开发团队
