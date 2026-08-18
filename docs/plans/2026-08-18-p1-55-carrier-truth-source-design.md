# P1-55 PCell 配置单一真值源设计

## 可观察故障

`TestCase.configuration` 同时保存顶层 `frequency_hz`、`bandwidth_mhz`、
`subcarrier_spacing_khz` 和 `component_carriers[0]` 的同名字段。当前只有 GUI 的三个输入框
尽量同步两份值，REST PATCH、服务层写入和历史数据没有统一约束；执行链又分别读取两端：
UXM、F64 与小区配置主要读取 PCell，波形合成、校准选择、探头增益、PRECHECK、REFERENCE
仍有站点读取顶层。两端一旦分叉，同一次测试会在不同频率或带宽上配置、校准和判定，且表单
可能展示第三种理解。

本片的验收目标是：PCell（`component_carriers[0]`）成为唯一运行真值；显式冲突必须在保存或
任何硬件动作前失败；缺少顶层兼容镜像的历史记录可从 PCell 无损补齐；GUI 显示、REST 写入、
执行和报告快照观察到同一组频率、带宽与 SCS。

## 改前全集

### 产生方

1. `POST /api/v1/test-plans/cases`：`TestCaseCreate.configuration` 是自由字典。
2. `PATCH /api/v1/test-plans/cases/{id}`：整体替换自由字典，无 MIMO 载波一致性校验。
3. `TestCaseService.create_test_case/update_test_case`：其他内部调用者可绕过 REST 直接写入。
4. `MIMOOTAConfigForm`：三个输入框已同步顶层与 PCell，但显示仍读取顶层；保存其他字段时不会
   修复外部或历史路径形成的冲突。
5. Commissioning/factory、bootstrap 与 legacy migration：通过
   `MIMOOTAConfiguration.model_dump()` 产生完整配置。

### 消费方

1. `MIMOOTAConfiguration._resolve_component_carriers()`：CC 为空时由顶层构造；CC 非空时只改
   role，不检查或补齐顶层镜像。
2. `MeasureExecutor`：UXM PCell/SCell 和部分 F64 配置读取 CC；路损校准、探头方向图、ASC
   `sim_rules`、日志/结果仍有顶层读取。
3. `PrecheckExecutor`：路损证书与探头方向图查询读取顶层。
4. `ReferenceExecutor`：SA 中心频率和测量带宽读取顶层。
5. MIMO factory：TestCase 派生列仍读取顶层。
6. GUI：表单三个控件读取顶层；列表已经优先读取 CC[0]，因此冲突时同屏可不一致。

### 真实数据分布

2026-08-18 对当前 PostgreSQL 生产库只读枚举：622 条 TestCase 中 268 条为 MIMO_OTA，253 条
带非空 `component_carriers`；频率、带宽、SCS 的显式冲突均为 0，3 条记录缺少至少一个顶层
兼容镜像。该数字只用于选择迁移策略，不作为运行判据或长期不变量。

## 方案比较

### 方案 A：PCell 唯一真值；冲突拒绝、缺失补齐（采用）

- CC 存在且顶层字段显式存在：必须与 CC[0] 相等，否则 fail-loud。
- CC 存在但顶层字段缺失：从 CC[0] 补齐兼容镜像。
- CC 缺失：保留旧兼容语义，由顶层字段构造单 PCell。
- 所有 MIMO 执行消费者改读共享 `primary_carrier` accessor。

优点是不会猜操作员意图，也不破坏 3 条仅缺镜像的历史记录；缺点是外部客户端若提交冲突值会
收到 422，需要明确修正后重试。代价不对称下这是正确方向：响亮拒绝比静默在错误频率执行更轻。

### 方案 B：静默以 CC[0] 覆盖顶层

能自动修复冲突，但无法知道操作员真正想改的是顶层还是 PCell；会把一次可能正确的改频静默撤销。
不采用。

### 方案 C：顶层重新成为权威

会破坏 CA 模型中 PCell/SCell 已建立的执行语义，并让现有 UXM/F64 主链反向施工。不采用。

## 设计

### 1. Schema 真值门

在 `MIMOOTAConfiguration` 的 before validator 中处理原始输入，从而区分“字段缺失”和“字段显式
提交默认值”：

1. `component_carriers` 为空或缺失时，沿用顶层三字段构造单 PCell。
2. 存在 PCell 时，逐项检查 `frequency_hz`、`bandwidth_mhz`、
   `subcarrier_spacing_khz`：
   - 顶层缺失：写入 PCell 的值作为兼容镜像；
   - 顶层存在且相等：接受；
   - 顶层存在但不等：抛出带字段名和两端值的 ValidationError。
3. 既有 after validator 继续强制 CC[0] 为 `pcell`、其余为 `scell`。
4. 新增只读 `primary_carrier` accessor；执行代码不再自行索引或读取顶层镜像。

为保持自由 JSON 的向后兼容，服务层保存的是“原 payload + schema 归一后的 CC 列表和三项镜像”，
不把全部 Pydantic 默认值无条件膨胀进稀疏历史配置。

### 2. 写入链

`TestCaseService` 作为所有生产写入口的共同门：

- create：最终 `test_type == MIMO_OTA` 时归一化 configuration；冲突在 `db.add/commit` 前失败；
- update：先读取现有行，按更新后的最终 `test_type` 判定；configuration 变更时同样归一化；
- REST 将载波真值冲突映射为 422，并保留可操作 detail；其他内部调用者得到同一 domain error，不能
  绕过真值门。

不做数据库批量迁移：当前库没有显式冲突，3 条缺镜像记录可在下一次读取/保存时无损归一；执行加载
本身也经过 schema，因此不会按默认顶层值运行。

### 3. 执行链

MIMO factory、PRECHECK、REFERENCE、MEASURE 中所有代表“本次 PCell 工作点”的频率、带宽和 SCS
统一读取 `config.primary_carrier`。包括：

- path-loss 证书窗口与 probe pattern 查询；
- SA reference setup；
- UXM PCell/ARFCN、F64 中心频率与带宽；
- ASC 波形合成 `sim_rules`；
- 执行快照、日志和结果载荷。

SCell 仍只来自 `component_carriers[1:]`。`band` 没有顶层镜像，本片不增加频段推断或
`band ↔ frequency` 校验；该问题继续独立管理，避免把无完整频段表的推断混入本片。

### 4. GUI

提取纯函数读取 PCell 兼容值：有 CC[0] 时三个控件显示 PCell，无 CC 时显示顶层。三个编辑动作继续
同时更新 PCell 与顶层镜像，只修改 PCell，不修改 SCell。若草稿本身含显式冲突，提交由后端 422
拒绝；GUI 展示服务端 detail，不静默挑一端覆盖。

### 5. 错误与安全语义

- 冲突：保存/执行前 fail-loud，不连接 UXM/F64，不查询校准，不生成波形。
- 缺镜像：从 PCell 补齐，不把 schema 通用默认当成操作员声明。
- 缺 CC：继续由顶层构造单 PCell，兼容老客户端。
- 无效 CC 结构或数值：沿用 Pydantic 422/执行失败语义。
- 不新增后台修复、数据库猜测迁移或 band 推断。

## 测试与验证

1. Schema 行为：三字段冲突逐项失败；缺镜像从 PCell 补齐；无 CC 从顶层构造；CA 的 SCell 不被改。
2. API/Service：create 与 PATCH 冲突均在提交前拒绝；缺镜像保存为 canonical payload；非 MIMO 不受影响。
3. 执行：PRECHECK、REFERENCE、MEASURE/factory 的工作点均来自同一个 primary carrier；把任一消费点
   改回顶层时核心行为测试应变红。
4. GUI：显示优先 PCell，编辑同步镜像且不改 SCell；冲突错误展示服务端 detail。
5. 回归：MIMO schema、factory、precheck、reference、measure、TestCase API、GUI 契约、完整 rule gates、
   后端全量、GUI production build、compileall、单一 Alembic head、`git diff --check`。

## 非目标

- 不删除顶层兼容字段。
- 不修改 SCell 语义。
- 不推断或自动删除 `band`。
- 不扩展到 TRP/VRT/ChannelAsset 的其他频率模型。
- 不批量重写历史 TestCase。
