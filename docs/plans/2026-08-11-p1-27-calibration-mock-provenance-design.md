# P1-27 路损校准来源门设计

## 可观察故障

现场曾先用 `use_mock=True` 生成路损校准记录，随后在真实 F64/UXM 测试中运行 strict
precheck。现有门只检查记录存在、频率窗口、有效期与状态，因此该模拟记录被判为
`cal_pass=true`，其路损值会继续作为真实测量补偿使用。

## 已核对的全集

权威记录是 `ProbePathLossCalibration`，不是系统级 `CalibrationCertificate`。生产写入有三类：

1. `ProbePathLossCalibrationService.start_calibration()`；
2. `start_calibration_for_lab_profile()`；
3. 校准数据包导入路径（来源可能来自新版数据包，也可能是未带来源的历史包）。

读取侧包括 latest API、precheck、measure、补偿服务与校准编排器。本片只改变已批准的
strict precheck 判定，不在底层查询中静默过滤记录，也不改变操作员显式关闭 strict 的语义。

## 方案比较

### A. 可空 `use_mock` 三态 + strict 白名单（采用）

- `False`：本服务明确走真实仪器路径生成；
- `True`：本服务明确走模拟生成；
- `None`：迁移前历史记录或来源未声明的导入记录。

真实 channel emulator 且 `precheck_strict_cal=True` 时，只允许明确 `False`；`True` 与
`None` 都 fail-loud。优点是不会把无法证明来源的旧记录洗成真实，且字段名称与既定 roadmap
一致。代价是升级后历史证书需要重新做真实校准，或由操作员显式关闭 strict 进行非正式演练。

### B. 非空布尔并把历史记录回填 `False`（否决）

兼容性最好，但没有证据证明历史数据都来自真实仪器。默认回填会把未知来源伪装为真实来源，
正好延续本片要消除的假成功。

### C. 新增通用来源枚举并同时改所有校准表（否决本片）

长期表达力更强，但会跨越 P1-27 的路损证书故障，扩大迁移与消费方范围。后续若要统一所有
校准类型，可从 Discovered 单独立项。

## 数据流与判定

两条正常生成路径在落库时直接写入服务实例的 `self.use_mock`。新版导出包携带该字段；导入时
只原样传播 `True` / `False`，缺字段保持 `None`，不从 `vna_model` 文本猜来源。latest API
显式返回三态，precheck payload 记录 `path_loss_calibration_use_mock` 便于 GUI、日志和报告审计。

strict 判定保持现有运行时硬件来源：仅当当前 live channel emulator 是真实驱动时启用。此时
`path_loss_valid`、证书总体状态和来源白名单共同决定 `cal_pass`。显式 bypass 或 mock CE 仍不
阻塞，但 `cal_pass_reason` 必须记录 mock/unknown 在 strict 下会失败。

## 迁移与兼容

新增 nullable Boolean 列，不设 server default，不批量回填。这样 brownfield 数据保持
`unknown`，greenfield 新记录由所有已知生产写点显式赋值。迁移沿用仓库的幂等列检查，并支持
downgrade。

## 测试

1. 先在 precheck 定点测试中把原有非来源用例明确标为 `use_mock=False`；
2. 新增真实 CE + strict 的 `False` 通过、`True` 拒绝、`None` 拒绝；
3. 新增 bypass 审计理由，证明模拟/未知不会被悄悄写成 `ok`；
4. 验证两条正常校准生成路径写入来源，并验证 API schema 暴露三态；
5. 运行 migration head、相关回归、完整规则门与差异检查。
