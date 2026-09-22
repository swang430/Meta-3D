# P2-77 信道资产频率语义设计

## 1. 可观察故障

同一份 F64 `.smu` 工程已在 2026-09-16 现场先后接受 2565 MHz 与 1960 MHz，证明工程内记录的中心频率不是天然排他的执行身份。当前实现却同时存在两个相反行为：

1. `MIMOOTAConfiguration` 每次执行把 PCell 频率作为 `center_frequency_mhz` 传给 F64；
2. `vendor_file` ChannelAsset 的 `scd_config` 中心频率又作为独立 `SCD` 身份进入频率一致性门。

结果是 F64 已按 TestCase 工作点运行，执行仍可能因“资产登记频率 != TestCase 频率”被拒绝。反方向也存在假成功：当前驱动写完 `CENT` 后直接把请求值记入缓存，没有验证仪器是否自动钳位。

## 2. 厂商手册依据

权威来源为 `Instrument_API_Doc/Keysight PromSim F64/Propsim User Reference.pdf`，PROPSIM User Reference User Guide Revision 10.2（2024-09-16）：

- §20.4.6.1，PDF 第 280 页：`CALCulate:FILTer:CENTer:CH <channel>,<frequency>` 按信道组设置中心频率；同输入或同输出的通道属于同组。
- §20.4.6.2，PDF 第 280–281 页：`CALCulate:FILTer:CENTer:CH? <channel>` 回读信道组中心频率。
- §20.4.6.8，PDF 第 282 页：`CALCulate:FILTer:CENTer:LIMits? <channel>` 返回该信道组可接受的中心频率区间；可返回多个以分号分隔的区间；越界值会被自动设置为最近可接受值。

因此，“SCPI 写命令没有错误”不足以证明请求频率实际生效。软件必须在写前验证全部组的运行时范围，并在写后逐组回读。

## 3. 真值分工

| 事实 | 权威来源 | 语义 |
|---|---|---|
| 工程默认中心频率 | ChannelAsset 的已验证 `.smu` 工程元数据 | 审计与操作员提示；对可受控调频的 vendor asset 不排他 |
| 本次请求频率 | execution-frozen TestCase PCell | 本次执行唯一请求真值 |
| 本次允许范围 | 加载后每个实际信道组的 `CENT:LIM?` | 运行时、仪器实例相关；不持久化成可编辑资产真值 |
| 本次实际频率 | 写后每个实际信道组的 `CENT:CH?` | 执行应用真值 |
| 场景带宽 | ChannelAsset/SCD 的已登记工程声明 | 不拿 F64 系统许可带宽冒充项目带宽 |

`standard_3gpp`、`custom_static`、`rt_dynamic` 的中心频率仍参与合成、Doppler 或射线物理语义，继续保持固定身份；本片只改变有明确 adapter 能力声明的 `vendor_file`。

## 4. 选择的方案

采用“运行时有界调频”：

1. 新增 vendor-neutral HAL 操作 `set_center_frequency_bounded`。它的契约不是普通 setter，而是“查询所有组限值 → 全量预检 → 写入 → 错误队列门 → 所有组回读”的原子语义。
2. ChannelEmulator manifest 升级新 schema，只有真实实现上述契约的 adapter 才声明 `implemented`。历史 manifest/plan 的操作词汇保持冻结，不用当前词汇重新解释。
3. execution plan 冻结该能力。只有 `source_type=vendor_file` 且本次冻结计划包含该操作时，资产频率才按“工程默认值”解释；否则维持现有固定身份和 fail-closed 行为。
4. F64 加载 `.smu`、完成拓扑/组回读后执行有界调频。任一组限值未知、返回畸形、请求值不在任一区间、写入错误或回读不一致，加载失败且不得把请求值写入驱动缓存。
5. 成功时保存不可变 `CenterFrequencyApplicationEvidence`：请求值、每组代表通道、允许区间、实际回读、是否确认。MEASURE 只消费该共同证据，不通过 adapter 名称或对象形状猜能力。
6. 频率一致性门在“有界 vendor_file”路径比较 TestCase、BaseStation 实际身份、ChannelEmulator 实际回读；资产工程默认频率只进审计载荷，不再作为第三个排他身份。资产带宽仍参与一致性判断。

## 5. 失败语义

- 限值查询空回复、语法不合法、反向区间、NaN/Inf：在任何 `CENT` 写入前失败。
- 多组中只要一组不包含请求频率：在任何 `CENT` 写入前失败。
- 写入后错误队列非空：失败，不更新 programmed 状态。
- 任一组回读空、非数值或不等于请求值：失败，不更新 programmed 状态。
- manifest 未声明能力、历史 plan 无该操作：不推断可调，继续要求资产固定频率与 TestCase 一致。
- Mock 结果保持诊断/模拟，不进入正式 KPI；本片不借 Mock 声明真实硬件能力。

## 6. API 与 GUI

- `ChannelAsset.center_frequency_hz` 不改数据库列，避免制造第二份迁移真值；OpenAPI 描述明确：vendor_file 为工程默认中心频率，其他来源仍为物理身份。
- 信道工作台对 vendor_file 显示“工程默认中心频率”。
- TestCase 选择 vendor_file 时显示：执行频率来自 PCell，是否可改由冻结 adapter 能力及加载后的仪器限值裁决。
- GUI 不本地计算范围，也不把一次现场成功固化成白名单。

## 7. 不在本片范围

- 不把 450–6000 MHz 系统许可范围当作 `.smu` 工程范围。
- 不新增或猜测任何 SCPI；只使用上述手册明确的 `CENT:LIM?`、既有 `CENT` 写入与 `CENT?` 回读。
- 不改变 `.smu` 文件供应、SMB 调试扫描或正式 provenance 白名单。
- 不将本地测试解释为 F8800A 真机验收；合并后仍需现场覆盖不同合法频点、越界频点和多区间工程。

## 8. 验收条件

1. 同一 vendor `.smu` 的工程默认频率与 TestCase 不同时，只在冻结 adapter 声明有界调频且全部运行时证据通过时允许执行。
2. 越界自动钳位绝不被记录为请求频率成功。
3. 限值与回读覆盖全部实际信道组，不从通道数猜组数。
4. 旧 adapter、旧冻结件和非 vendor asset 维持现有固定频率 fail-closed 语义。
5. execution evidence 同时保留工程默认、请求、允许范围和实际回读，不让 GUI 或报告重算。
