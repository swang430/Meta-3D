# 功能规划文档

本文档记录计划中但尚未实现的功能特性。

---

## 测试步骤参数编辑功能

**优先级**: 中
**创建时间**: 2025-11-23
**状态**: 计划中

### 需求描述

当前测试步骤编辑器 (StepEditor) 可以编辑执行配置（超时时间、重试次数、失败后继续），但**不支持编辑测试参数 (parameters)**。

测试参数是复杂的动态表单，每个步骤根据其序列库定义有不同的参数结构。

### 技术挑战

1. **动态表单生成**
   - 参数结构由序列库的 `parameters` schema 定义
   - 每个参数有类型（text, number, select, textarea, boolean, json）
   - 需要根据类型动态渲染对应的输入组件

2. **参数验证**
   - 参数有验证规则（required, min, max, options等）
   - 需要在前端和后端都进行验证

3. **参数值管理**
   - 参数值存储在 `parameters` JSON字段中
   - 结构为：`{ [key: string]: StepParameter }`
   - `StepParameter` 包含 value, label, description, type, validation 等字段

### 设计方案

#### 前端实现 (StepEditor.tsx)

当前代码中 [StepEditor.tsx:156-162](gui/src/features/TestManagement/components/StepsTab/StepEditor.tsx#L156-L162) 已经有参数渲染的占位符：

```typescript
{parameterKeys.map((key) => {
  const param = parameters[key]
  return (
    <div key={key}>
      {renderParameterInput(key, param, handleParameterChange, readOnly)}
    </div>
  )
})}
```

`renderParameterInput` 函数 (lines 241-338) 已经实现了基础的输入组件渲染逻辑。

**需要完善的部分**：

1. **参数值初始化**
   - 当从序列库添加步骤时，需要用序列库的 `default_values` 初始化参数
   - 当前只有空的 `parameters: {}`,需要完整填充

2. **保存参数更改**
   - `handleSave` 已经包含了 `parameters` 字段 (line 70)
   - 但实际测试中发现**保存功能不工作** ❌

3. **参数值验证**
   - 需要在保存前验证所有必填参数
   - 需要验证值的类型和范围

#### 后端实现

1. **序列库参数定义**
   - `TestSequence.parameters` 定义参数结构
   - `TestSequence.default_values` 提供默认值
   - `TestSequence.validation_rules` 定义验证规则

2. **步骤创建时初始化**
   - `TestStepService.create_test_step_from_sequence` 需要从序列库复制参数定义和默认值到新步骤
   - 当前实现可能没有正确初始化

3. **更新接口**
   - `PATCH /v1/test-plans/{id}/steps/{step_id}` 接受 `parameters` 字段
   - 需要验证参数结构和值

### 当前阻塞问题 ⚠️

**测试步骤保存功能不工作** - 这是更紧急的问题，必须先修复才能继续参数编辑功能。

**症状**：
```bash
# 发送 PATCH 请求更新执行配置
curl -X PATCH .../steps/{id} -d '{"timeout_seconds": 900, "retry_count": 3}'

# 返回的数据显示值没有变化
"timeout_seconds": 300,  # 期待 900
"retry_count": 0,        # 期待 3
```

**根本原因**（调查中）：
1. ✅ 后端 endpoint 接收请求
2. ✅ 服务层调用 `update_test_step`
3. ✅ SQLAlchemy 执行 setattr
4. ✅ 服务层调用 `db.commit()`
5. ❌ FastAPI 的 `get_db` 依赖在请求结束时触发 ROLLBACK

**尝试的修复**：
- 修改了 `get_db()` 添加事务提交逻辑
- 仍然没有生效，需要进一步调查

### 实施步骤

#### 阶段 1: 修复保存功能 (优先级: 高)
- [ ] 调查为什么数据库更新被回滚
- [ ] 修复事务管理问题
- [ ] 验证执行配置更新功能正常工作

#### 阶段 2: 参数初始化 (优先级: 高)
- [ ] 修改 `create_test_step_from_sequence` 从序列库复制参数定义
- [ ] 确保新创建的步骤有完整的参数结构
- [ ] 前端验证参数正确显示

#### 阶段 3: 参数编辑 UI (优先级: 中)
- [ ] 完善 `renderParameterInput` 支持所有参数类型
- [ ] 添加参数描述和帮助文本显示
- [ ] 实现参数值变更追踪 (`hasChanges`)

#### 阶段 4: 参数验证 (优先级: 中)
- [ ] 前端实现参数验证逻辑
- [ ] 保存前检查所有必填参数
- [ ] 显示验证错误消息

#### 阶段 5: 高级功能 (优先级: 低)
- [ ] 支持参数之间的依赖关系
- [ ] 支持条件显示（某些参数只在特定条件下显示）
- [ ] 参数值的自动计算和联动

### 相关文件

**前端**:
- [StepEditor.tsx](gui/src/features/TestManagement/components/StepsTab/StepEditor.tsx)
- [types/index.ts](gui/src/features/TestManagement/types/index.ts) - `StepParameter` 类型定义

**后端**:
- [app/api/test_plan.py](api-service/app/api/test_plan.py) - 步骤更新端点
- [app/services/test_plan_service.py](api-service/app/services/test_plan_service.py) - `TestStepService`
- [app/models/test_plan.py](api-service/app/models/test_plan.py) - `TestStep`, `TestSequence` 模型
- [app/schemas/test_plan.py](api-service/app/schemas/test_plan.py) - Pydantic schemas

### 参考资料

- [DATA-MODEL-GUIDE.md](DATA-MODEL-GUIDE.md) - 数据模型设计规范
- [TestManagement-Unified-Architecture.md](TestManagement-Unified-Architecture.md) - 测试管理架构文档

---

**最后更新**: 2025-11-23 17:30
**维护者**: 开发团队
