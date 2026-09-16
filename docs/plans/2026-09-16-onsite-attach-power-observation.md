# Cell ON 后功率观察窗口实施计划

> 现场快速片：单代理顺序执行，严格 RED→GREEN，只做必要回归。

## Task 1：配置契约

**文件**
- 修改：`api-service/app/schemas/mimo_ota/config.py`
- 测试：`api-service/tests/test_mimo_ota_config.py`（若无合适文件则使用现有 schema 定点文件）
- 修改：对应 GUI 手写类型与表单文件

**步骤**
1. 先写 `attach_power_observation_s=0/60` 合法、负数与大于 300 非法的 RED。
2. 最小实现 `Field(default=0.0, ge=0.0, le=300.0)`。
3. GUI 增加现场可编辑秒数；不增加第二份默认真值。

## Task 2：基站 Cell-ready 回调与功率回读

**文件**
- 修改：`api-service/app/hal/base_station.py`
- 修改：`api-service/app/hal/cmw500_base_station.py`
- 对称修改：`api-service/app/hal/uxm_base_station.py` 与 Mock 实现
- 测试：现有 CMW500 attach 定点测试文件

**步骤**
1. 写 RED，证明回调发生在 `ON,ADJUSTED` 后、首个 PS attach 查询前；回调时间不消耗 attach timeout。
2. 在公共 attach 契约加入可选异步 `on_cell_ready`，所有实现只在各自确认 cell-ready 后调用一次。
3. 在公共基站接口增加默认返回 unknown 的配置下行功率回读；CMW500 仅复用既有 RS-EPRE 查询常量和解析。

## Task 3：F64 功率/拓扑观察与严格门

**文件**
- 新增：`api-service/app/services/mimo_ota/attach_power_observation.py`
- 修改：`api-service/app/services/mimo_ota/executors/measure.py`
- 测试：新增定点测试或扩展现有 MIMO OTA measure 测试

**步骤**
1. 写 RED 覆盖：活动输入缺测时严格拒绝；非严格模式继续并留诊断；等待开始/结束各采一次；等待期间取消。
2. 观察器只消费 `base_station.read_configured_downlink_power_dbm()` 与 `channel_emulator.get_metrics()`。
3. MEASURE 在调用 `attach()` 时注入回调，把结果写入 `result_payload["attach_power_observation"]`。
4. 严格拒绝时使用明确原因结束，不进入 PS attach 查询。

## Task 4：镜像与有限验证

**文件**
- 按搜索结果同步：live OpenAPI、`api/openapi.yaml`、generated TS、手写 GUI 类型。

**步骤**
1. 先用镜像/GUI 契约测试制造 RED，再同步最小字段。
2. 运行 schema、CMW attach、观察器、MIMO measure、GUI 定点测试。
3. 运行 GUI production build、Python `compileall` 与 diff-check。
4. 做一次只读 fresh 功能内审；现场片只处理功能 P1，测试增强按仓库规则不阻塞。
