# P2-88 报告参数与执行事实追溯：设计与实施计划

用户已批准报告作为主要追溯入口，以及 P2-88→P2-89→P2-90 顺序。本片是既有执行/报告链的有界扩展，不增参数查询界面、不增数据库表。

## 权威关系与边界

- 生产入口 `test_case_runner.launch_test_case_execution` → 执行入口记录源用例名称与已保存字段路径（不记录 SIM 密钥）→ `base_station_adapter_profile` 将来源标记与 canonical 配置纳入同一冻结 digest → 公共报告构建器 → PDF 步骤参数与 GUI 现有配置页签。
- “源用例已保存”不等同于“操作员亲手填过”：保存链可能已经补默认。只证明本次启动输入/启动时默认，不倒推此前编辑行为。
- 当前 `mimo_ota_configuration` 和嵌套 MAC 是执行请求真值；冻结 binding、asset resolution、runtime load request 是各自对象的真值。报告白名单展示，不 dump 原始 configuration/认证信息。
- 窗口取同次 `base_station_execution_evidence.measurement_windows`，过滤当前 attempt/身份；其 request.expected_window_count 与 requested_window_count 区分计划/请求，实际数量由记录计数。没有证据不以旧 sampling 数量补真。
- 请求值始终标“请求/冻结配置”，应用确认保留已有 receipt/逐字段证据与 provenance；不把配置冻结或 Mock 成功称为生效。
- 重建只读执行，不读可变 source/snapshot TestCase 或当前 LabProfile。旧执行缺来源记录时明确不可追溯；缺冻结配置时不调用带默认的 config parser 补真。
- 任意畸形/摘要不一致审计块降级，不修改正式判决策略；不允许新增审计内容泄漏未确认正式 KPI。

## 验收与顺序

1. 基线：既有 report renderer 与 case runner（36 passed）。
2. RED：生产启动输入缺字段的来源、冻结后改源用例不影响报告；报告 PDF/GUI 配置页签可见真实冻结参数；缺失/畸形/Mock/旧执行不补真，敏感字段不出现。
3. GREEN：入口仅记录路径/名称；freeze 纳入来源；新增公共只读审计 projection，挂现有报告 parameters/step_configs，不新 API 路由。
4. RED→GREEN：从合法当前 attempt 窗口说明请求/计划/实际数量，单发 CMW 与多发 UXM 区别及实际 elapsed；缺记录保持未知。
5. 受影响正式消费者回归、规则门、最终后端全量；GUI 如有类型/控件变化同步四镜像并 production build；compileall、Alembic head、diff-check。
6. fresh 只读独立功能内审；Ready PR、核对最新 SHA 后 R1→R2；R2 无 P1 合并/main ff-only/清理，随后才启动 P2-89。

NotebookLM 不适用：本片不改仪器命令、单位解析或厂商取值域。现有已解析 schema 字段仅以同次执行原有语义展示。窗口行为改动留在 P2-89，判据改动留在 P2-90。

## 实施台账

- 已建立独立工作树；基线 36 passed（6.60s）。
- 设计范围沿用用户已过目的三片拆分；未实施、未推送前不得称已交付。
