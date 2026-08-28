# P2-43 BaseStation Adapter SPI、结构化回执与认证套件设计

## 目标

解决一个可观察故障：现有基站适配器把“整组配置是否成功”压成布尔值，无法表达部分字段已权威回读、部分字段未知；共享证据层又直接识别 CMW500 专属 route 结果。第三种基站若沿用该形态，必须再次修改 MEASURE、commissioning 和正式消费链，且容易把未知字段误当成已确认。

本片只稳定 vendor-neutral SPI 与离线认证合同，不新增、修改或猜测任何仪器命令，不实现 P2-44 的 manifest/binding resolver，也不实现 P2-45 的 Diagnostic/Formal 站点认证状态。

## 全集与当前缺口

共同生命周期已经由 P2-42 收敛为 `BaseStationExecutionSession`。P2-43 覆盖其内部使用的八类能力：

1. transport identity 与 capabilities；
2. typed PCell config apply；
3. execution-frozen route apply；
4. cell ON / attach；
5. 独立 measurement window；
6. SAFE_IDLE cleanup；
7. transport release；
8. versioned evidence receipt。

现有生产路径的主要缺口是：

- `BaseStationDriver.apply_requested_config()` 返回 `bool`；CMW500 与 UXM 内部已有回读，但共同层看不到逐字段真值。
- CMW500 route 返回定义在 `cmw500_base_station.py`；`execution_scpi_evidence.py` 为此直接导入厂商类型。
- MEASURE 仍以 `adapter_id` 选择 CMW500 原生窗口或 UXM 旧窗口，并单独建立 CMW attempt context。
- execution evidence schema 把 `uxm/cmw500` 与 CMW route 特例写死；正式消费者本身已只读统一 metric projection，本片不改其输出形状。

厂商驱动内部按自己的手册方言分支是正确边界；禁止的是 MEASURE、commissioning、Analysis、报告、比较、下载和历史消费方新增或继续依赖厂商分支。

## 方案比较

### 方案 A：扩展现有 `BaseStationDriver` 共同合同（采用）

在共同 HAL 定义逐字段回执、配置回执、route 回执和 versioned adapter evidence；UXM 与 CMW500 在已有写入/回读路径中产生这些共同结果。旧布尔方法只保留为兼容壳，统一从结构化回执的 `confirmed` 派生。共享证据写入器只消费共同类型，MEASURE 只调用共同能力。

优点：不增加第二套 facade；第三种 adapter 只实现一个合同；已有 P2-42 会话可直接复用。缺点：需要谨慎迁移两家驱动的返回值，但不要求新增命令。

### 方案 B：在驱动外增加 facade

为 UXM、CMW500 各写一个 wrapper，把旧布尔值和厂商结果翻译成共同结果。改动看似局部，但 wrapper 无法获得驱动内部的逐字段回读，最终只能把成功布尔值伪装成确认，或复制厂商缓存与判断。拒绝。

### 方案 C：只在 evidence writer 归一化

保持驱动不变，在持久化时把布尔值和厂商 route 结果转换为统一证据。改动最少，但未知字段已经在上游丢失，仍不能给第三种 adapter 提供独立认证合同，也无法移除 MEASURE 的厂商分支。拒绝。

## 共同数据合同

共同 HAL 新增以下不可变结果：

- `BaseStationFieldReceipt`
  - `field`：共同字段名；
  - `requested`：本次请求值；
  - `applied`：权威回读值，读不到必须为 `None`；
  - `status`：`confirmed | unknown | not_applicable`；
  - `reason`：字段级原因；
  - `exchange_ids`：产生该结论的交换证据。
- `BaseStationApplyReceipt`
  - `schema_version`；
  - `operation`：`config | route`；
  - `fields`：字段回执全集；
  - `confirmed`：仅当所有适用字段均为 `confirmed` 时为真；
  - `reason` 与全集 `exchange_ids`。

约束：

- `confirmed` 不接受调用方传入的自由布尔值，由字段状态派生。
- `unknown` 不得携带 `applied`；`confirmed` 必须同时有 requested/applied 且精确相等。
- `not_applicable` 只用于该 adapter 没有 execution route 等真正不适用的字段，不得把“读不到”包装成不适用。
- 模拟 adapter 可以产生同形状回执，但其 versioned evidence 必须标记 simulated，正式 provenance gate 保持原白名单并继续排除。

`adapter_id` 在 SPI 层使用非空稳定字符串；“哪些 adapter 已注册”仍由现有 registry 决定，本片不提前引入 manifest。

## 驱动迁移

### 配置

新增共同 `apply_config()` 返回结构化回执。UXM 与 CMW500 复用现有校验、写入、错误队列和回读，不新增查询：

- 已有权威回读的字段按实际值填 `confirmed/unknown`；
- 只写未读、profile 不支持读、查询异常或部分回读的字段标 `unknown`；
- 任一适用字段 unknown 时总结果不得 confirmed；
- 失败/异常/取消路径不更新成功缓存，也不以请求值回填 applied。

旧 `apply_requested_config()` 暂作兼容壳，只返回 `await apply_config(...).confirmed`。所有正式入口迁到 `apply_config()` 后，门禁止新增对旧布尔接口的生产调用。

### Route

共同 `apply_route(frozen_adapter)` 对有 route 的 adapter 返回字段回执；没有 execution route 的 adapter 返回明确的 `not_applicable` receipt。CMW500 保留已有七字段与六物理路径双回读，只把 `BaseStationRouteResult` 迁为共同 receipt；UXM 不伪造 route。

### Cell、窗口、cleanup 与 release

沿用 P2-42 会话所有权。共同合同要求 adapter 提供 identity/capabilities、cell/attach、`measure_base_station_window()`、`ensure_safe_idle()` 与 `release_remote_session()`；不再由 MEASURE 按厂商选择旧吞吐窗口。UXM 若尚无独立生命周期回执，则在本片用其已有独立窗口实现共同结果；缺少权威边界必须返回 unconfirmed，而非借 CMW 命令或 sleep+poll 猜测。

## Evidence 与消费边界

adapter operation receipt 先转换为版本化 `BaseStationAdapterEvidence`，再由唯一 writer 绑定 execution/attempt/lease/session。writer 不导入任何厂商模块，也不按 adapter 解释 payload；它只检查：

- receipt schema/version；
- config/route requested digest 与 execution-frozen digest 一致；
- applied 只来自字段回执；
- unknown 使对应 config/route confirmation fail-closed；
- exchange id 唯一并归属 current attempt/session。

正式消费者继续只读 `base_station_metric_projection`。Analysis、报告、比较、下载、历史与 GUI 公开 KPI 形状不变。

## 认证套件

新增同一套参数化 adapter certification contract，UXM fake transport、CMW500 fake transport 与未来 adapter fixture 均执行：

1. 写前校验失败时零写入；
2. 写后错误队列拒绝不得 confirmed；
3. 部分回读只确认已证明字段，总结果 unknown；
4. 超时、异常、取消不伪造 applied，并执行保守 cleanup；
5. SAFE_IDLE 未确认时 release 不得假成功；
6. attempt/lease/session 不匹配时 evidence writer 拒绝；
7. simulated receipt 不进入正式 KPI。

另加生产路径门：MEASURE、commissioning、Analysis、报告、比较、下载、历史不得新增 `adapter_id/vendor` 分支；厂商驱动目录、registry/readiness 与测试 fixture 不在该门范围。测试门自身的发现严重度遵循 AGENTS.md，最高 P2。

## 错误与安全语义

- 适用字段读不到的保守方向是 unknown，代价是阻断正式 KPI；不得为提高可用性回填请求值。
- SAFE_IDLE 或 release 不确定时保留控制会话并 fail-loud，避免把仍有 RF/信令活动的仪器误判为已释放。
- 模拟/diagnostic 可以继续运行，但结构化证据保持 simulated/unknown；不得改变正式白名单。
- 不新增外部 RF router、功率预算、路径补偿或厂商命令。

## 交付边界

本片完成共同 SPI、两家 adapter 迁移、统一 evidence writer、生产路径分支门和离线认证套件。P2-44 才处理 binding resolver/manifest/GUI schema；P2-45 才处理无校准诊断与站点正式晋级。现场真机 certification 仍保留为现场项，本地 fake transport 不能替代。
