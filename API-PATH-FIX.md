# API 路径修复记录

## 修复日期
- **Phase 1**: 2025-11-25 - service.ts 路径修复
- **Phase 2**: 2025-11-26 - testManagementAPI.ts 路径修复

## 问题描述
前后端 API 路径不一致，导致请求无法正确路由到后端端点。

## 路径对照表

### 修复前后对比

| 功能 | 前端路径（旧） | 后端实际路径 | 前端路径（新）| 状态 |
|------|--------------|-------------|--------------|------|
| **测试计划** | | | | |
| 获取测试计划列表 | `/tests/plans` | `/test-plans` | `/test-plans` | ✅ 已修复 |
| 获取单个测试计划 | `/tests/plans/{id}` | `/test-plans/{id}` | `/test-plans/{id}` | ✅ 已修复 |
| 创建测试计划 | `/tests/plans` | `/test-plans` | `/test-plans` | ✅ 已修复 |
| 更新测试计划 | `/tests/plans/{id}` (PUT) | `/test-plans/{id}` (PATCH) | `/test-plans/{id}` (PATCH) | ✅ 已修复 |
| 删除测试计划 | `/tests/plans/{id}` | `/test-plans/{id}` | `/test-plans/{id}` | ✅ 已修复 |
| 重排队列 | `/tests/plans/reorder` | `/test-plans/queue/reorder` | `/test-plans/queue/reorder` | ✅ 已修复 |
| **测试步骤** | | | | |
| 获取步骤列表 | `/tests/plans/{id}/steps` | `/test-plans/{id}/steps` | - | 无需前端调用 |
| 添加步骤 | `/tests/plans/{id}/steps/append` | `/test-plans/{id}/steps` | `/test-plans/{id}/steps` | ✅ 已修复 |
| 重排步骤 | `/tests/plans/{id}/steps/reorder` | `/test-plans/{id}/steps/reorder` | `/test-plans/{id}/steps/reorder` | ✅ 保持 |
| 删除步骤 | `/tests/plans/{id}/steps/{stepId}` | `/test-plans/{id}/steps/{stepId}` | `/test-plans/{id}/steps/{stepId}` | ✅ 已修复 |
| **测试用例** | | | | |
| 获取测试用例列表 | `/tests/cases` | `/test-plans/cases` | `/test-plans/cases` | ✅ 已修复 |
| 获取单个测试用例 | `/tests/cases/{id}` | `/test-plans/cases/{id}` | `/test-plans/cases/{id}` | ✅ 已修复 |
| 创建测试用例 | `/tests/cases/new` | `/test-plans/cases` | `/test-plans/cases` | ✅ 已修复 |
| 从计划创建用例 | `/tests/cases` | `/test-plans/cases` | `/test-plans/cases` | ✅ 已修复 |
| 删除测试用例 | `/tests/cases/{id}` | `/test-plans/cases/{id}` | `/test-plans/cases/{id}` | ✅ 已修复 |
| **序列库** | | | | |
| 获取序列库 | `/sequence/library` | `/test-sequences` | `/test-sequences` | ✅ 已修复 |
| **模板** | | | | |
| 获取测试模板 | `/tests/templates` | `/test-plans/cases?is_template=true` | `/test-plans/cases?is_template=true` | ✅ 已修复 |
| **执行历史** | | | | |
| 获取最近测试 | `/tests/recent` | `/test-executions/recent` | `/test-executions/recent` | ⚠️ 待后端实现 |

## 修改文件

### 前端文件
- `gui/src/api/service.ts` - 更新所有测试相关的 API 调用路径 (Phase 1)
- `gui/src/features/TestManagement/api/testManagementAPI.ts` - 移除重复的 /v1 前缀 (Phase 2)

### 后端路由文件（无需修改）
- `api-service/app/api/test_plan.py` - 测试计划和测试用例路由
- `api-service/app/api/test_sequence.py` - 序列库路由
- `api-service/app/api/test_execution.py` - 执行控制路由

## 修复详情

### 1. 测试计划路径统一
**问题**: 前端使用 `/tests/plans`，后端使用 `/test-plans`
**原因**: 命名不一致，前端使用嵌套路径，后端使用连字符
**修复**: 前端改为 `/test-plans`，遵循 RESTful 命名规范

### 2. 测试用例路径调整
**问题**: 前端使用 `/tests/cases`，后端使用 `/test-plans/cases`
**原因**: 后端将测试用例作为测试计划的子资源
**修复**: 前端改为 `/test-plans/cases`，保持资源层级一致

### 3. 序列库路径修正
**问题**: 前端使用 `/sequence/library`，后端使用 `/test-sequences`
**原因**: 路径命名不一致
**修复**: 前端改为 `/test-sequences`

### 4. HTTP 方法统一
**问题**: 更新测试计划时，前端使用 PUT，后端使用 PATCH
**原因**: RESTful 最佳实践，PATCH 用于部分更新
**修复**: 前端改为使用 PATCH 方法

### 5. 步骤添加端点简化
**问题**: 前端使用 `/steps/append`，后端使用 `/steps` POST
**原因**: 语义冗余，POST 本身就表示添加
**修复**: 前端改为 `/steps` POST

### 6. TestManagement 模块重复前缀问题 (Phase 2)
**问题**: testManagementAPI.ts 使用 `/v1/test-plans` 等路径，与 client.baseURL `/api/v1` 重复
**原因**: 模块开发时未考虑 client 已配置的 baseURL，导致实际请求路径为 `/api/v1/v1/test-plans`
**影响**: 创建测试计划等操作返回 404 错误
**修复**: 批量移除所有 `/v1/` 前缀，改为 `/test-plans` 等相对路径
**影响范围**:
- 测试计划 CRUD 操作 (13+ 处修改)
- 测试步骤管理
- 队列管理
- 执行控制
- 历史记录查询
- 序列库查询

## 待办事项

### 后端需要实现的端点
1. ⚠️ `/api/v1/test-executions/recent` - 获取最近测试执行记录
   - 优先级：中
   - 影响功能：测试管理 - 历史记录Tab

2. ⚠️ `/api/v1/test-plans/queue/reorder` - 重排队列顺序
   - 优先级：中
   - 影响功能：测试管理 - 队列Tab

## 测试建议

1. **单元测试**: 验证所有 API 服务函数的路径正确性
2. **集成测试**: 测试完整的测试计划生命周期（创建 → 添加步骤 → 排队 → 执行）
3. **端到端测试**: 在实际 UI 中验证所有功能模块

## 回归风险评估

| 功能模块 | 风险等级 | 说明 |
|---------|---------|------|
| 测试计划管理 | 高 | 路径大幅调整，需要全面测试 |
| 测试用例管理 | 高 | 路径调整，影响创建和查询 |
| 序列库 | 中 | 路径调整，影响步骤添加 |
| 其他模块 | 低 | 未修改 |

## 验证清单

- [x] TypeScript 编译通过
- [ ] 启动前后端服务
- [ ] 测试计划列表加载
- [ ] 创建新测试计划
- [ ] 添加测试步骤
- [ ] 测试用例列表加载
- [ ] 序列库加载
- [ ] 队列操作

## 参考文档

- [API-DESIGN-GUIDE.md](./API-DESIGN-GUIDE.md) - API 设计规范
- [ARCHITECTURE-REVIEW.md](./ARCHITECTURE-REVIEW.md) - 架构审查文档
- [API-COMPATIBILITY.md](./API-COMPATIBILITY.md) - API 兼容性记录

## 备注

此次修复严格遵循 RESTful API 设计原则：
- 使用名词复数表示资源集合
- 使用连字符分隔多词资源名
- 子资源嵌套在父资源路径下
- 使用正确的 HTTP 方法（GET/POST/PATCH/DELETE）
