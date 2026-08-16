# P1-52 TestCase 编辑绑定保护设计

## 可观察故障

TestCase 详情读取成功、LabProfile 列表读取失败时，编辑弹窗当前把失败折叠成空列表。界面只剩“不绑定”选项，操作员无法区分“确实没有 LabProfile”和“列表暂时不可用”；一旦选择并保存，PATCH 会显式发送 `lab_profile_id: null`，从而清空原本有效的实验室绑定。

## 入口全集

- 详情真值：`getTestCase(testCaseId)` 返回当前 `lab_profile_id`。
- 可选项真值：`fetchAllLabProfiles()` 返回活动与历史停用 LabProfile。
- 修改入口：`TestCaseEditModal` 的 LabProfile `Select`。
- 写入口：`updateTestCase()` 的 PATCH；字段省略保持原值，显式 `null` 才解除绑定。
- 对称状态：列表加载中、加载成功、加载失败、重试成功、弹窗关闭或切换 TestCase 后旧请求返回。

创建弹窗已独立维护 `labsLoading` / `labsError` 并 fail-closed；本片只修编辑弹窗，不改变创建语义，也不新增后端数据模型或 API。

## 方案比较

### 方案 A：列表失败时禁止整个弹窗保存

安全，但名称、描述、标签和测试配置等不依赖 LabProfile 列表的编辑也被阻断，扩大了瞬时网络故障的影响面。

### 方案 B：冻结绑定并省略 PATCH 字段（采用）

详情与列表分开加载。列表不可用时保留详情返回的原绑定，禁用 LabProfile 下拉并显示可重试错误；保存其他字段时省略 `lab_profile_id`，复用后端“字段省略保持原值”的权威契约。列表成功后，只有操作员明确改变选择时才发送新 ID 或 `null`。

该方案直接去掉错误输入，不新增并发控制机制，也不让前端复制后端绑定判据。

### 方案 C：后端增加绑定版本或条件 PATCH

可覆盖更广泛的并发编辑，但本故障不是多人并发写冲突，而是前端把读取失败伪装成空列表；为此增加版本机制不成比例。

## 状态与数据流

编辑弹窗维护：

- `labsLoading`：本次列表请求尚未完成；
- `labsError`：列表请求失败的可操作文本；
- `labsReady`：列表成功返回，即使结果确实为空也算 ready；
- `originalLabProfileId`：详情读取时的原绑定，只用于判断是否发生显式修改；
- 请求代次或取消标记：关闭弹窗、切换 TestCase 后，旧列表响应不得覆盖新弹窗状态。

加载流程：

1. 打开或切换 TestCase 时重置列表状态并同时发起详情与列表请求。
2. 详情失败仍关闭弹窗；列表失败不关闭弹窗，也不改写 `selectedLabId`。
3. 列表失败时 Select 禁用并显示错误；操作员可重试列表请求。
4. 列表成功后显示“不绑定”、活动选项和当前历史停用绑定；停用项只展示，不允许新选。

保存流程：

1. 名称、描述、标签和 configuration 始终按原契约保存。
2. 仅当列表 ready 且选择相对 `originalLabProfileId` 真正变化时，PATCH 才包含 `lab_profile_id`。
3. 列表 loading/error 或选择未变化时省略该字段，后端保留原绑定。
4. 显式选择“不绑定”且列表 ready 时发送 `null`；选择活动 LabProfile 时发送其 ID。

## 错误处理

- 列表失败必须在弹窗内展示，不能再 `.catch(() => [])`。
- 重试只重拉 LabProfile 列表，不重载 TestCase，也不覆盖操作员已经编辑的其他字段。
- 保存失败继续优先显示后端 `detail`；本片不新增自动重试或静默回退。

## 验证

- RED/GREEN 行为测试锁住：列表不可用时保存 payload 省略绑定；列表 ready 后显式清空发送 `null`；显式换绑发送新 ID；未改变绑定时省略字段。
- TypeScript production build 验证编辑弹窗接入策略 helper，并正确渲染 loading/error、禁用 Select 与重试入口；仓库当前没有 React 组件测试运行时，本片不为一处回归引入整套框架。
- 运行完整 rule gates、GUI production build、相关后端 TestCase PATCH 回归与 diff-check。

## 非目标

- 不为默认关闭的 mock server 增加 `/lab-profiles` handler。
- 不改变 inactive LabProfile 的后端换绑白名单。
- 不增加 TestCase 乐观锁或通用表单状态框架。
