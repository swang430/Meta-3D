# P1-62 路损证书应用与可信度叙事真值设计

## 背景与可观察故障

2026-08-22 最近一次手工执行导出 `app_export (1).jsonl`，执行
`e974e199-c1b7-4852-9e93-9246c8cd9165` 明确记录：

- 使用证书 `81a2e595-56fc-4bdd-b847-f01a9cbde1d6`；
- 暗室平均路损为 `56.77 dB`；
- 四个方位全部应用了逐 RF-chain 路损。

但同次执行的 MEASURE warning、正式报告与 GUI 只看到
`path_loss_verified !== true`，于是统一叙述成“无 path-loss certificate / 未补偿”。实际故障不是
正式可信度门过严，而是一个布尔值同时承担了两个不同事实：

1. 本次执行是否真的应用了补偿；
2. 所用证书是否足以进入正式 KPI 与判决。

来源未知的 legacy 证书可以在 mock 流程演练中实际参与计算，但仍不能被当作显式真实证书。
因此必须同时如实表达“已应用”和“来源未知”，并继续把正式结论保持为 `UNKNOWN/N/A`。

## 用户确认的展示策略

来源未知的证书若确实应用：

- 显示“已应用路损补偿，但证书来源未知，不参与正式判定”；
- 显示证书 ID 与来源状态；
- 报告与操作员 GUI 隐藏具体补偿数值；
- 不得写成“无证书”或“未补偿”；
- 正式 KPI、PASS/FAIL、历史 verdict 与下载资格不放宽。

原始执行审计载荷可以保留已应用数值，但必须与结构化来源和应用状态同行；正式报告、GUI 与
判决消费方不得在来源未验证时展示或使用该数值。

## 全集与边界

### 产生方

1. `ProbePathLossCalibrationService.get_latest_calibration()`：按暗室、频率、模式、有效期和
   `require_real` 选择证书；当前只返回证书或 `None`，丢失了“为什么没选中”的事实。
2. PRECHECK：记录证书是否有效、来源和严格门原因；当前只能区分频率窗口缺失与暗室无有效证书，
   GUI 仍把所有 `valid=false` 统一写成“已过期”。
3. MEASURE：先选择候选证书，再按真实/模拟仪表与 strict 设置决定是否应用；
   `path_loss_cert` 是实际应用证书，`selected_path_loss_cert` 还包括真实执行中被拒绝的不可信候选。
4. MEASURE 逐链计算：暗室平均值、逐 RF-chain 值、逐方位补偿和 `chains_used` 是“实际应用”的
   权威写方。
5. MEASURE 结果：`path_loss_certificate_id`、`path_loss_rejected_certificate_id`、
   `path_loss_calibration_use_mock`、`path_loss_compensation_db` 与 `path_loss_verified` 分散表达
   上述事实，但没有一个结构化应用真值。

### 消费方

1. MEASURE warning；
2. ANALYSIS 的正式可信度门；
3. `_build_mimo_ota_content_data()` 的补偿数值、验证标签、报告 manifest；
4. `ReportService` 的历史安全重建与旧报告恢复；
5. 执行历史 `_formal_validation_pass()`；
6. Commissioning `MIMOTestPhase` 的黄色告警；
7. PRECHECK 的消息、失败原因与“校准有效性”表格；
8. 相关 API/OpenAPI/GUI 类型镜像（仅修改实际存在且消费该字段的契约，不扩建无 live caller 的接口）。

### 不在本片范围

- 不把 `use_mock=NULL` 回填或猜成真实；
- 不改变真实仪表 strict 门、bypass 语义、KPI 白名单或报告恢复资格；
- 不修改路损数值、校准算法、RF-chain 映射或仪表命令；
- 不批量改写历史执行或历史报告；
- 不从证书 ID、数值非零、逐链数量或自由文本反推旧记录的应用状态。

## 方案裁决

### 采用：应用、来源与门模式三轴结构化真值

新增版本化 `path_loss_application` 结果对象，由 MEASURE 在实际选择和逐链应用完成后一次生成：

```json
{
  "schema_version": 1,
  "status": "applied | not_applied | unknown",
  "provenance": "real | simulated | unknown | missing",
  "reason": "selected | rejected_untrusted | missing | expired | frequency_mismatch | operating_mode_mismatch | legacy_unclassified",
  "gate_mode": "strict | operator_bypass | mock_not_applicable",
  "certificate_id": "uuid-or-null",
  "value_disclosure": "verified | hidden_unverified | none"
}
```

字段职责互不替代：

- `status` 只回答“有没有实际应用”；
- `provenance` 只回答“证书来源是什么”；
- `reason` 只回答“为什么得到当前状态”；
- `gate_mode` 记录严格门是否适用或被操作员显式绕过；
- `value_disclosure` 规定正式消费方能否展示数值。

`path_loss_verified` 保留为正式可信度兼容字段，且仍只在实际应用证书为显式
`use_mock=False` 时为真。ANALYSIS、报告 manifest 和历史 verdict 继续使用该白名单，不改判据。

### 未采用：各消费方从现有字段自行推断

从 `certificate_id`、`verified`、补偿数值和 rejected ID 拼出文案改动最小，但会复制当前故障：
warning、报告与 GUI 会拥有三套不同判据，历史缺字段时还容易从非零数值猜出错误结论。

### 未采用：把 `path_loss_verified` 改成多值枚举

单个枚举仍把“应用”和“可信”压成一轴，无法准确表达“已应用但来源未知”和“证书存在但因
来源不可信未应用”。同时会破坏现有布尔兼容、历史报告门和前端消费者。

## 状态矩阵

| 场景 | status | provenance | reason | 数值展示 | 正式结论 |
|---|---|---|---|---|---|
| 显式真实证书实际应用 | applied | real | selected | verified，可展示 | 保持现有判据 |
| 来源未知 legacy 证书在 mock 演练中实际应用 | applied | unknown | selected | hidden_unverified | UNKNOWN/N/A |
| mock 证书在 mock 演练中实际应用 | applied | simulated | selected | hidden_unverified | UNKNOWN/N/A |
| 真实执行发现 unknown/mock 候选，strict=true | not_applied | unknown/simulated | rejected_untrusted | none | 执行在 I/O 前失败 |
| 真实执行显式 bypass，unknown/mock 候选被拒绝 | not_applied | unknown/simulated | rejected_untrusted | none | UNKNOWN/N/A |
| 没有任何匹配证书 | not_applied | missing | missing | none | strict 失败或 bypass 未补偿 |
| 只有过期证书 | not_applied | missing | expired | none | strict 失败或 bypass 未补偿 |
| 只有频率窗口外的有效证书 | not_applied | missing | frequency_mismatch | none | strict 失败或 bypass 未补偿 |
| 只有其他 operating mode 的有效证书 | not_applied | missing | operating_mode_mismatch | none | strict 失败或 bypass 未补偿 |
| 历史结果缺少新对象 | unknown | unknown | legacy_unclassified | none | UNKNOWN/N/A |

同一状态对象必须由共享构造器验证组合；畸形或未知 token 在读取端统一降级为
`unknown/legacy_unclassified`，隐藏数值，不得抛出导致整份报告或历史列表不可用。

## 数据流

1. 路损选择层返回“证书 + 未选中原因”，而不是只返回 `Optional[Certificate]`。解析只读取数据库
   现有真值：暗室、频率窗口、operating mode、status、valid_until 与 use_mock。
2. PRECHECK 使用同一选择结果生成有效性、来源和 reason；GUI 不再把 missing、频率不符和
   mode 不符统称“已过期”。
3. MEASURE 依据真实仪表/模拟仪表与 strict/bypass 规则裁决实际证书。只有实际进入
   `calibration_entries`、平均/逐链补偿与逐方位计算的证书，才能写 `status=applied`。
4. MEASURE 在结果中同时写入 `path_loss_application` 和既有兼容字段；不让后续消费方重新查询
   数据库或根据当前证书状态重解释一次已经结束的执行。
5. warning、报告和 GUI 统一从 `path_loss_application` 生成叙事：
   - applied + unknown/simulated：已应用但未验证，隐藏数值；
   - not_applied + rejected：证书存在但未应用；
   - missing/expired/mismatch：明确原因并说明未补偿；
   - applied + real：沿用已验证补偿展示。
6. ANALYSIS 与历史 verdict 继续要求 `path_loss_verified is True` 且
   `path_loss_calibration_use_mock is False`；新对象不能替代或放宽此门。
7. 报告重建遇到缺失或畸形新对象时显示“应用状态未知”，隐藏补偿值，正式判决保持 UNKNOWN；
   不从历史数值或 ID 推断。

## 文案契约

- `applied + unknown`：`已应用路损补偿；证书来源未知，补偿数值不展示，结果不参与正式判定。`
- `applied + simulated`：`已应用模拟路损证书用于流程演练；数值不进入正式结果。`
- `not_applied + rejected_untrusted`：`检测到路损证书，但因来源未验证未应用；本次结果未补偿。`
- `not_applied + missing`：`未找到匹配的路损证书；本次结果未补偿。`
- `not_applied + expired`：`匹配的路损证书已过期；本次结果未补偿。`
- `not_applied + frequency_mismatch`：`现有证书与本次频率不匹配；本次结果未补偿。`
- `not_applied + operating_mode_mismatch`：`现有证书与本次 RF operating mode 不匹配；本次结果未补偿。`
- `unknown + legacy_unclassified`：`历史记录无法证明是否应用路损补偿；补偿数值不展示。`

正式报告不得用“无证书”描述 certificate ID 非空且 `status=applied` 的执行；不得用“未补偿”
描述实际逐链/平均补偿已经参与计算的执行。

## 失败与安全语义

- strict 真实执行的 explicit-real 白名单保持不变；unknown/mock/expired/mismatch 仍在任何仪表 I/O
  前 fail-loud。
- operator bypass 只允许继续未补偿调试；检测到不可信候选也不能把其数值重新接入。
- mock 流程可以演练证书应用，但 `measurement_verified=false` 与来源门继续让 KPI/报告保持 N/A。
- `value_disclosure=hidden_unverified` 只影响正式展示，不删除原始审计证据；任何格式化入口都必须先
  检查 disclosure，不能把隐藏数值通过 PDF、tooltip、表格或 warning 文本泄漏。
- 证书后来过期、被作废或数据库出现更新，不得反向改变已完成执行的应用事实；执行结果保存的是
  当次裁决快照。
- 选择原因探测失败或出现多个互相冲突候选时默认 `unknown`/fail-closed，不猜最近一张。

## 验证策略

先写 RED 测试覆盖：

1. 复现手工日志：unknown legacy 证书在 mock 执行中实际应用，结果为 `applied/unknown`，warning
   不再写“无证书/未补偿”，也不包含 `56.77 dB`；ANALYSIS 仍 UNKNOWN。
2. 报告与 GUI 对 `applied/unknown` 显示已应用但来源未知，隐藏补偿数值；
   `formal_path_loss_verified` 仍为 false。
3. explicit-real 已应用继续显示数值，正式判据不回归。
4. mock 证书已应用明确写流程演练，数值不进入正式结果。
5. 真实 strict 模式的 unknown/mock 候选仍在任何 I/O 前失败。
6. 真实 bypass 模式的 unknown/mock 候选标记为 `not_applied/rejected_untrusted`，补偿保持 0/none，
   文案说明“存在但未应用”。
7. missing、expired、frequency mismatch、operating mode mismatch 各自产生唯一 reason，GUI 不再
   统一写“已过期”。
8. 历史记录缺少或带畸形 `path_loss_application` 时，报告/GUI 显示应用状态未知、隐藏数值，
   不崩溃也不反推。
9. 报告重建、执行历史与 ANALYSIS 的 explicit-real 白名单保持原样。
10. 所有显示路径均不在 unverified 状态泄漏补偿数值；原始审计载荷仍保留证书 ID、来源和应用状态。

随后运行 P1-62 定点测试、校准门/commissioning/报告恢复/执行历史相关套件、完整 rule gates、
GUI 契约与 production build、全后端回归、`compileall`、单一 Alembic head、`diff-check`，再做
fresh 内审与 Codex 外审。
