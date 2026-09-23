# P2-32A 多频路损真实入口闭环设计

## 可观察故障

系统校准向导的“多频点路损校准”并未调用已经存在的 CE+SA 多频路损服务，而是调用
`POST /api/v1/calibration/multi-frequency`。该旧端点用 `random.gauss()` 生成 TRP/TIS
结果并返回 `overall_pass=true/false`，既不绑定当前 LabProfile 暗室，也不持久化真实校准
provenance。操作员会把随机结果误认为完成了多频路损校准。

与此同时，真实入口 `POST /api/v1/calibration/path-loss/multi-frequency/start` 已能显式
选择 `use_mock=false` 并复用 CE+SA、仪器租约和逐频错误队列，但 GUI 无调用方；底层
`CalibrationResult.warnings` 只存在于当次响应，`MultiFrequencyPathLoss` 与校准报告不留痕。

## 目标

1. 系统校准向导只调用服务器权威的多频路损入口。
2. Real/Mock 必须由操作员显式选择；未选择不得启动硬件。
3. Real 使用既有 CE+SA 服务和任务级租约，不新增或修改 SCPI。
4. Mock 保留为诊断演练，但服务器响应、GUI 和报告均明确标为模拟，不产生正式 PASS。
5. 每个探头的 acquire/cleanup warnings 写入对应数据库行，并进入校准报告。
6. 旧随机 TRP/TIS 多频端点与前端 fallback 被删除，不能再成为可达生产路径。

## 非目标

- 不实现静区测量；静区仍因缺少厘米级 XY 扫描平台保持 Hardware Blocked。
- 不实现探头方向图真实入口；它是后续独立子片 P2-32B。
- 不改变 CE、SA、RF Switch 或转台的 SCPI 命令。
- 不为多频扫频新增 PASS/FAIL 阈值；完成真实采集不等于通过认证判据。
- 不改变 API 省略 `use_mock` 时的历史兼容默认值 `true`；GUI 必须显式发送。

## 权威数据流

```text
Active LabProfile.chamber_config_id
        + 操作员输入的 probe / polarization / sweep / SGH / mode
        -> POST /calibration/path-loss/multi-frequency/start
        -> MultiFrequencyPathLossService(use_mock=显式值)
        -> Real: CE+SA + instrument_test_lease
           Mock: 诊断数据，use_mock=true
        -> MultiFrequencyPathLoss(use_mock, warnings, sweep data)
        -> CalibrationJobResponse(use_mock, warnings)
        -> GUI 只按服务器返回的 use_mock 分类结果
        -> CalibrationReportGenerator 逐行输出 warnings/provenance
```

## API 与错误语义

- 保留 `StartMultiFrequencyPathLossRequest.use_mock` 的兼容默认值 `true`。
- `CalibrationJobResponse` 增加可空 `use_mock`；本入口始终回填布尔值，其他既有入口可保持
  `null`，避免伪造其 provenance。
- 真实服务缺 CE+SA 接线、租约失败、测量异常时保持现有非 2xx 失败，不回退 Mock。
- 旧 `/calibration/multi-frequency` 路由和只服务于它的 schema 删除；不存在自动 fallback。
- GUI 不把“真实采集完成”显示成“校准通过”；Mock 显示黄色诊断完成。

## warnings 持久化

- `multi_frequency_path_losses.warnings` 新增 nullable JSON 列。
- `NULL` 表示迁移前未记录；新写入用列表，空列表表示本次明确无 warning。
- 每个 probe 使用独立 `probe_warnings`，写入该 probe 行；作业响应汇总所有 probe warnings。
- 报告输出 `warnings` 原值，不按 warning 文本推导正式判决。

## GUI

多频页面改为显式字段：探头 ID 列表、极化、起止频率、步进、SGH 型号、SGH 增益、
执行模式。执行模式初始为空，操作员必须选择“真实 CE+SA”或“模拟诊断”。真实模式文字
明确会驱动硬件；模拟模式明确不进入正式判定。

请求构造放在纯函数中，负责把 CSV 探头列表归一化、拒绝空/重复/非整数/负数，并使用
当前 `OperationalLab` 的 `chamberId`。HTTP client 只调用服务器权威路径且不提供 fallback。

## 安全与兼容

- Real 仍由既有 `instrument_test_lease(control_f64=True, control_uxm=False)` 包住整次扫频。
- 请求没有明确模式或当前 LabProfile 未绑定暗室时，GUI 在发请求前 fail-loud。
- 后端仍校验暗室存在；本片不把配置声明当实际硬件状态。
- 历史 `warnings=NULL`、`use_mock=NULL` 继续可读，但不进入正式报告分母。
- checked-in OpenAPI、generated TypeScript 和手写 GUI 类型同步更新。

## 验收

1. 变异 GUI 回旧 `/calibration/multi-frequency` 时测试失败。
2. 未选择模式、无暗室、非法 probe CSV 均不产生请求。
3. `use_mock=false` 精确到达真实 service；失败不回退模拟。
4. acquire warning 按 probe 落库，并在 start 响应与两条校准报告收集路径中可见。
5. Mock 行在报告中保持 `validation_pass=null`；真实、有效且未过期行才可进入现有正式分母。
6. 旧随机端点从 live OpenAPI 消失，四份契约镜像一致。

