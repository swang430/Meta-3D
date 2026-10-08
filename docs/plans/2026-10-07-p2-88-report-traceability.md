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
- 设计范围沿用用户已过目的三片拆分；未合并前不得称已交付。
- 来源捕获与冻结后改源用例的生产入口反例先 RED；公共报告投影 GREEN 后覆盖 PDF parameters 与 GUI `step_configs`，不创建另一套客户端参数真值。
- 窗口与应用证据：同 execution/adapter/connection/current attempt/request digest，窗口按同 lease/session 对账；实际记录数不借旧 sampling 计划数补真。窗口来源读取各 window `trust.simulated`，混合为 `mixed`；全局应用值要求全部窗口租约一致确认，Mock/缺失/冲突保持 unknown/null。
- modern ChannelAsset 与 legacy SCD 两路径都在原 freeze 中捕获 name/path，只展示冻结描述，不查询当前数据库；有效引擎请求来自通过独立 scope/digest 校验的 CE load request，与配置 engine 分开。
- 历史 null/missing 只展示冻结 raw，parser 仅校验、不把其默认值写到报告。已按当前保存入口补齐 LTE frame/carrier 与派生 TDD period 的来源映射。
- 实际 PDF 生成反例检出 361 方位整块 JSON 的 LayoutError；改为长数组 16 项分块、窗口/资产/应用逐项展示，未修改 PDF 机制。
- 严格 RED→GREEN：应用/资产 3 RED；历史 null 与 F64 请求 2 RED；内审三条功能 P1 3 RED；361 方位实际 PDF 1 RED；LTE 来源映射 1 RED，均已 GREEN。全新只读增量及同根复审 P1/P2/P3=0。
- 最终相关链及正式消费者合并命令（在 `api-service`）：`.venv/bin/python -m pytest tests/test_p2_88_report_traceability.py tests/test_arch1_case_runner.py tests/test_p2_21_report_flags_cert_cjk.py tests/test_p2_66_execution_evidence_outcome.py tests/test_p2_59_channel_emulator_execution_plan.py tests/test_p2_79a_channel_model_ownership.py tests/test_rule_gates.py tests/test_p1_73c_formal_consumers.py tests/test_p2_45_diagnostic_formal_consumers.py tests/test_p2_66_formal_consumers.py tests/test_p1_61_report_final_state_truth.py tests/test_p1_48_report_provenance.py tests/test_p1_22_report_trustworthy.py tests/test_mimo_ota_report_verified_backcompat.py tests/test_arch1_history_resource.py -q --color=no -o log_cli=false -o addopts='' --tb=short --show-capture=no --disable-warnings` → exit 0，355 passed / 239 warnings，13.08s。
- `gui`：`node --experimental-strip-types --test test/reportRecovery.test.ts test/reportLifecycleTruth.test.ts src/types/executionEvidenceOutcome.test.ts` → exit 0，10 passed，70.9ms；`npm run build` → exit 0（11.58s，已有 chunk/import 警告）。本片仅填充既有 `content_data`/`step_configs.parameters` 自由结构，未增 API 路由/response 字段/客户端类型，因此 OpenAPI/generated TS/手写类型均不改。
- `api-service`：`python -m compileall -q app` exit 0；`alembic heads` 单 head `c1e3f5a7b9d2`；base-to-working diff-check exit 0。
- 全量第一次因收到可执行 P1 主动中断（4842 passed / 5 skipped，203.91s），不冒充完整全量。稳定最终版本在 `api-service` 执行 `.venv/bin/python -m pytest -q --color=no -o log_cli=false -o addopts='' --tb=short --show-capture=no --disable-warnings` → exit 0，6982 passed / 17 skipped / 5325 warnings，246.78s；结束后核对生产/测试 diff 摘要未变，未按 push 次数重复全量。

### R1 收口（2026-10-08）

- GitHub PR #514 R1 覆盖 `3679435e973f90a580675458415405535139439f`，review `5449491454`，inline P1 `4212937100` / P2 `4212937108`。
- 两条反例先 RED：缓存配置回读无激活被误标 confirmed；旧 `uxm_config_mode=inherit` 来源误标 launch_default。命令：`.venv/bin/python -m pytest tests/test_p2_88_report_traceability.py -k 'cached_config or legacy_config_mode' -q -o log_cli=false -o addopts='' --tb=short --disable-warnings` → exit 1，2 failed。
- 最小 GREEN：抽取原正式配置 projector 的 receipt 判据供报告共用，唯一同 attempt/lease/session 的 config+attach、冻结 manifest 权威回读域与 exchange 范围同时成立才确认；MAC command_error_queue 不升级字段确认。旧模式键映射到保存输入来源。合法确认 fixture 补齐完整权威 manifest 摘要与激活证据，未改生产 provenance 白名单。
- 只读独立增量及同根内审 P1/P2/P3=0。此前完整相关链同一命令重跑 → exit 0，360 passed / 239 warnings，13.35s；compileall、diff-check、单一 Alembic head `c1e3f5a7b9d2` 通过。
- 因共享 projector 判据抽取，最终全量按上述全量命令重跑 → exit 0，6987 passed / 17 skipped / 5325 warnings，249.66s；输入 diff SHA256 `de00858373b96c38bf70306bf839e4b30eb8293b7a1fcf4f8f1f592da2306180` 结束后核对一致。GUI/自由结构未变，复用此前 GUI 契约与 build；不重复同输入全量。
