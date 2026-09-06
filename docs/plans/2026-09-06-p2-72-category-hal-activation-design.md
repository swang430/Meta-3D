# P2-72 — 仪器配置保存后按类别激活 HAL 设计

状态：用户已批准 A 方案，进入实现前设计固化。

## 1. 可观察故障与目标

“仪器资源配置”当前把持久化与运行时激活拆成两个不相邻操作：保存型号、endpoint、controller、
连接参数或 driver mode 后，数据库已经变更，`InstrumentHALService.drivers` 仍可能保留旧实例。
操作员必须再点一次全局“重新加载驱动”，即使只改了一类仪器，也会拆卸并重建全部类别。
漏做或顺序做错会产生以下可观察故障：

- GUI 提示保存成功，但连接测试与后续执行仍读旧 driver；
- LabProfile 同步或执行冻结因 saved binding 与 loaded runtime 不一致而 fail-closed；
- 操作员为了让一类仪器生效，被迫中断其他无关仪器连接。

本片目标是把“保存配置 → 激活相应 runtime”变成一个用户动作的受控两阶段流程：配置先提交，
随后服务器仅激活该 `category_key`。LabProfile binding 仍是另一份执行真值，继续由操作员单独同步。

## 2. 全集与权威源

按“改之前先列全集”枚举本片产生方与消费方：

| 事实 | 产生方 / 写入口 | 当前消费方 | 本片裁决 |
|---|---|---|---|
| 已保存仪器型号与连接配置 | `PUT /instruments/{category_key}`；BaseStation/ChannelEmulator 的服务器维护 preset | catalog、binding resolver、readiness、LabProfile sync、HAL 初始化 | 保存事务保持原样；成功后由 GUI 调用类别激活 |
| 已保存 driver mode | `PATCH /instruments/{category_key}/driver-mode` | HAL driver 选择、catalog、GUI mode | 成功后调用同一类别激活入口 |
| loaded runtime driver | `InstrumentHALService.drivers[category_key]` | 连接测试、resolver/runtime identity、执行冻结、诊断和正式执行 | 只允许新服务器激活服务及既有全局 reload 修改 |
| LabProfile instrument binding | `POST /lab-profiles/{id}/instrument-bindings/{category}/sync-current` | readiness、执行配置冻结、正式执行 | 明确不自动修改；仍为单独操作 |
| topology profile / active 状态 | 专用 topology 与 active 端点 | resolver、HAL 初始化、执行 | 不纳入保存后自动激活范围 |
| 全局 HAL reload | `POST /instruments/hal/reload` | 人工恢复、部署与全局重建 | 保留，不再是普通保存后的必需步骤 |

运行配置的数据库权威源仍是 `InstrumentCategory`、所选 `InstrumentModel` 与活动
`InstrumentConnection`；分型号 preset 只保存草稿快照，不取代活动 connection。客户端不能提交整张 preset map。

## 3. 方案选择

采用已批准的 **A 方案：独立服务器类别激活端点**。

未选方案：

- 不把真实硬件 I/O 塞进现有保存事务。数据库事务若与断连、建连共生，失败时既难保证数据库回滚，
  也难保证仪器回到旧运行态；请求超时还会把保存结果变得不确定。
- 不继续调用全局 reload。它扩大拆卸半径，会中断无关仪器，并保留原先容易漏做的概念。

独立端点保留清楚的两阶段语义：第一阶段持久化成功不可因第二阶段失败而假装未保存；第二阶段失败
必须显式报告“配置已保存，但 HAL 尚未激活”。

## 4. API 与 GUI 合同

新增服务器入口：

```text
POST /api/v1/instruments/{category_key}/hal/activate
```

请求不接收 endpoint、model、driver mode 或 preset。服务器只读取最新已提交数据库配置，避免 GUI 草稿
成为第二真值。成功响应至少包含：

- `category_key`
- `status`: `activated`、`unchanged` 或 `inactive`（类别已停用且 runtime 已卸载）
- 实际装载的 driver 标识与 simulated/mode 状态
- 便于 GUI 刷新的明确消息

拒绝与失败：

- 有运行中 execution 或活动 instrument lease：409，返回 blocker；自动流程绝不 force；
- category 不存在、配置缺失或不可解析：沿现有输入语义返回 404/422；
- 断连或新 driver 初始化失败：返回非 2xx，日志保留具体原因，GUI 显示
  “配置已保存，但 HAL 尚未激活：<原因>”。

GUI 两个入口改为串行编排：

1. 保存连接配置成功；
2. 调用类别激活；
3. 激活成功后刷新 catalog，并提示已保存且 HAL 已激活；
4. 激活失败仍刷新 catalog，保留已保存值并给出可操作警告，不自动同步 LabProfile。

driver mode 的保存采用同一流程。active toggle、topology 保存以及全局 reload 按钮不改语义。

并发保存采用“最新已提交配置获胜”：激活入口重新读取数据库，并返回实际激活的 runtime 身份；GUI
以刷新后的服务器响应为准，不假定它激活的一定是本地提交瞬间的草稿。

## 5. HAL 类别激活算法

实现必须复用 `_initialize_from_db()` 的单类别构造路径，不能复制一套 driver registry、连接参数、
TCP preflight、自动 topology 或 readiness 逻辑。计划先把现有初始化循环提取成可测试的单类别 helper，
然后全局初始化与类别激活共同调用。

激活顺序：

1. 读取目标类别及其最新持久配置，构造规范化的期望 runtime 描述；
2. 运行既有 reload blocker 检查；
3. 进入 `hal_mutation_guard`，再次检查 blocker，关闭检查到执行之间的竞态；
4. 进入 HAL lifecycle lock；
5. 若类别已停用，只安全卸载该类别并返回 `inactive`，不得因保存动作反向启用它；
6. 若 loaded driver 仍处于可用/已连接态，且其类、mode/simulated 与规范化 `driver.config` 均匹配，
   返回 `unchanged`；同配置但 driver 已断开或处于错误态仍须重建；
7. 安全断开目标类别旧 driver；真实 CMW 等 driver 若拒绝安全断开，则保留旧实例并失败，不继续覆盖；
8. 只构造、连接并登记目标类别的新 driver，更新该类别 readiness / connection status；
9. 离开 lifecycle lock 后，只对目标类别执行必要的 idle park，不触碰其他类别；
10. 返回实际 runtime 身份。

任何失败都不能让旧实例冒充新配置已激活：

- 旧 driver 未能安全释放：保留对象用于后续人工恢复，但 saved/runtime identity 不一致时既有门继续拒绝；
- 旧 driver 已释放而新 driver 构造或连接失败：移除该类别 runtime，并把连接状态记为错误；
- 不得用 Mock、旧实例或默认地址作静默兜底；
- 不改变正式 provenance 白名单。

类别激活不调用全局 `shutdown()`，也不调用会同时 park F64 与 BaseStation 的全局 helper。若现有 park
只有全局粒度，需提取单类别版本并由全局 helper 复用。

## 6. 并发、锁与安全边界

- 锁顺序沿用现有规则：先 `hal_mutation_guard`，再 lifecycle lock；不得反向获取。
- blocker 在 guard 外和 guard 内各检查一次，避免检查后 execution/lease 刚好启动。
- 自动激活没有 `force` 参数；需要强制处置时仍由操作员使用既有全局恢复流程。
- 不在 lifecycle lock 内执行跨类别 park，也不持锁等待 GUI 或 LabProfile 事务。
- 配置保存已经成功而激活失败时不做数据库“补偿回滚”；回滚到旧配置会再次制造 saved/preset/runtime
  多真值。失败状态必须可见且后续可重试。

## 7. LabProfile 真值边界

LabProfile binding 冻结的是执行要使用的仪器选择、endpoint/profile 与对应 digest。自动把每次仪器目录
保存顺手写入 LabProfile，会在操作员尚未确认暗室、拓扑和用例上下文时修改另一份执行真值，并可能让
其他测试用例无提示切换硬件。因此本片明确保持：

- 自动动作只到“已保存配置对应的 HAL runtime 已激活”；
- “同步到 LabProfile”继续读取已保存且 resolver-valid 的配置，并由操作员显式触发；
- 未保存 GUI 草稿永不进入 LabProfile；
- 后续 LabProfile 统一工作单元可把多个子视图编排成受控流程，但必须另行设计与验收。

## 8. 错误呈现与恢复

GUI 区分三种结果：

- 保存失败：维持现有错误，HAL 不变；
- 保存成功且激活成功/no-op：绿色成功，连接测试和后续操作可继续；
- 保存成功但激活失败/被阻断：黄色或红色明确提示“配置已保存，但 HAL 尚未激活”，展示 blocker/原因，
  提供重试类别激活或使用全局 reload 的恢复路径，绝不显示单一“保存成功”。

LabProfile 同步按钮不自动点击、不静默重试。若 runtime 仍不匹配，现有 resolver/readiness 门继续
fail-closed，并给出同一可操作原因。

## 9. 验收与回归策略

严格 TDD 覆盖：

1. 改 BaseStation 后只替换 BaseStation，F64/positioner 等实例身份和连接状态不变；
2. 改 ChannelEmulator 后只替换该类别；
3. 相同持久配置返回 `unchanged`，不 disconnect/reconnect；
4. model/endpoint/port/controller/connection params/driver mode 变化均会激活最新配置；
5. 活跃 execution、活动 lease、取消、断连失败、构造失败、连接失败均 fail-loud，且没有错误 fallback；
6. 保存成功但激活失败时数据库值保留，GUI 显示部分成功而非假成功；
7. 两个 GUI 保存入口各只触发一次对应类别激活；active/topology 操作不触发；
8. 自动流程从不调用 `sync-current`，LabProfile binding 不变；
9. 全局 reload 行为与恢复入口保持兼容；
10. live OpenAPI 与手写 GUI 类型一致；沿 D19 既有边界，HAL 操作端点不扩入 checked YAML / generated TS。

`api/openapi.yaml` 已明确把 `/hal/status`、`/hal/reload`、`/hal/switch` 排除在 checked contract 外；
本片新增端点保持同一 D19 边界，不单独制造一条半生成的 HAL 操作契约。

验证按共享 HAL 生命周期改动的高风险档执行：受影响专项与规则门、全后端、GUI 契约与 production build、
`compileall`、单一 Alembic head、base-to-HEAD diff-check。功能实现不新增或修改任何 SCPI。

## 10. 非目标

- 不把“仪器资源配置”“探头与暗室配置”“射频拓扑编辑器”合并成统一页面；
- 不自动同步或重写 LabProfile；
- 不改变 TestCase requirements / adapter manifest / compatibility 的职责划分；
- 不修改正式/诊断 provenance 与 KPI 门；
- 不新增硬件能力、默认地址或厂商命令；
- 不移除全局 HAL reload。
