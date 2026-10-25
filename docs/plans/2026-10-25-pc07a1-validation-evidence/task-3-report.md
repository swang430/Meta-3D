# Task 3 交付与验证

状态：GUI 与隔离真实 API 浏览器验收完成；真实 MIMO OTA 曾受既有 UUID 查询错误阻塞，经主代理授权最小前置修复后五相位已完成，实际报告保持 simulated/UNKNOWN（见文末最终补验）。未 push，未释放主认领。

实现输入/验证提交：`b81fc541062ec9657884230ffcac932e32f67a4e`，基线 `6813bcdbc3b2d411b49a3861dafb060d1389a0b5`。本文仅记录证据，不改变运行输入。

## 范围（全部为“修”）

- `gui/src/components/Report/ReportViewer.tsx`：只读响应 `calibration_traceability`；逐链状态不继承顶层 applied；无字段显示历史追溯未生成；保留全部原快照但默认折叠，区分执行频率/来源覆盖、采用/认证、指针/附件。
- `gui/src/types/report.ts`：追溯响应类型。
- `gui/src/features/Reports/pages/ReportsPage.tsx`：真实浏览器发现原 `ReportList` 没传 `onView`，详情入口不可达；最小接入只读 Modal，不添加编辑/采用权限。主代理已同意范围。
- `gui/test/pc07a1Report.test.js`：既有 Node test + React SSR，不新增框架；4 条本片断言。
- `gui/test/pc07a1Report.browser.js`：真实 HTTP/GUI，无响应拦截，独立 API 18089、GUI 5197；每次创建独立时间戳证据目录。
- `api-service/tests/pc07a1_browser_fixture.py`：显式新建临时 SQLite/全 Mock/专属输出的前置检查；仅种子局部 `BOOTSTRAP_ON_STARTUP=false`，生产默认未改；合成历史脚本化 transport 和实际 Mock 采集分开。另提供仅隔离 DB 的 forge 命令。

真实浏览器另发现：MIMO 报告没有虚拟路测的 phases/events/kpi_summary，原查看器挂载崩溃；新增 RED 后，仅缺项显示“未提供通用汇总/阶段时间线，以下载报告原字段为准”，不填 0、不编摘要。未重构报告数据。

## RED / GREEN / 变异

命令均在 GUI 目录：

1. `node --test test/pc07a1Report.test.js`：最初 exit 1，2 failed（混合来源未展示、历史无字段提示缺失）；最小实现后 exit 0，2 passed。
2. 同命令：详情接线 RED 为 exit 1，2 passed/1 failed；接线后 exit 0，3 passed。
3. 真实 MIMO 缺数组 RED 为 exit 1，3 passed/1 failed（读取 undefined.length）；缺项防护后 exit 0，4 passed。
4. 暂时把 selected 分支改为 false，实跑同命令 exit 1（“仅选择，未应用”缺失）；已恢复，恢复后最终相关回归通过。证据 `mutation-selected.log`。
5. 精确提交 b81fc541：`node --test test/reportLifecycleTruth.test.ts test/reportRecovery.test.ts test/pc07a1Report.test.js` exit 0，12 passed/0 failed；`npm run build` exit 0，8083 modules、12.47s。既有动态/静态混合导入和 >500kB 分包警告保留，未扩改。

## 夹具与真实服务

临时根：`/tmp/pc07a1-Ah5AxP`，DB `sqlite:////tmp/pc07a1-Ah5AxP/browser.db`。不使用默认数据库。

种子命令（api-service 目录）：

```sh
env USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-Ah5AxP/browser.db PC07A1_OUTPUT=/tmp/pc07a1-Ah5AxP BOOTSTRAP_ON_STARTUP=false .venv/bin/python -m pytest tests/pc07a1_browser_fixture.py -q
```

exit 0，1 passed/51 warnings/3.72s。macOS `/tmp` 实际解析为 `/private/tmp`，初次 guard 因该别名拒绝，已按真实路径比较修正；未访问默认库。直接运行 fixture 的 forge 要用 `python -m tests.pc07a1_browser_fixture`，不是路径执行（路径执行的首次尝试 import 失败，无修改）。显式把 OUTPUT 指向用户仓库的拒绝检查 exit 1，导入业务模块前即拒绝，证据 `fixture-refuse.log`。

API 在该临时根以 `PYTHONPATH=<本工作树>/api-service USE_MOCK_INSTRUMENTS=true DATABASE_URL=<上述DB> BOOTSTRAP_ON_STARTUP=false LOG_DIR=<临时根>/logs python -m uvicorn app.main:app --host 127.0.0.1 --port 18089` 启动。GUI 使用临时 vite 配置，将代理指向 18089；仓库默认代理/端口未改。

原历史 confirmed ID `e507aeb9-83a8-419a-b39f-66eeec07665f`，legacy ID `7790ce07-5052-479a-bbed-a5a63665dd81`；冻结后当前采用已推进到 `c40d8618-5581-4abf-bc0b-3dbe1cd0818a`，当前用例频率改为 3500MHz。原报告仍保持执行 2595MHz 与上述旧 ID。

## 浏览器与下载证据

精确提交 b81fc541 上执行：

```sh
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=pc07a1 run-code "$(< gui/test/pc07a1Report.browser.js)"
```

exit 0 且实际 Result `passed:8`；不是只看 CLI 退出码。最终证据目录（未纳入 git）：

`output/playwright/pc07a1-task3-1792901729792/`

- `requests-responses.json`：完整方法、路径、请求体、响应状态和响应体，包括 HAL `mode=mock`、driver_count=2，报告列表/详情、两次真实生成/重建、旧无键读取/生成、实际 Mock 采集/采用预览。
- `list.png`、`detail.png`：真实列表、只读详情；已目视检查，弹窗过渡结束后取图。原来源、认证 unknown、原始读数未内嵌可见。
- `downloaded.pdf`、`downloaded.txt`：通过真实页面下载按钮取得；PDF 提取文本逐一核对两个旧 source ID、2595MHz、原始读数未内嵌，均通过。
- `manifest.json`、`browser.db`：种子来源及临时 SQLite 快照；合成历史完整记录在快照内，非现场认证。
- `api-logs/`：API 专属日志（含 calibration、SCPI、audit）；`build-committed.log`、`gui-tests-committed.log`：最终构建/回归输出。
- `forgery-responses.json`：报告内部 application 与 projection 同时改成自洽伪造 v1，真实详情=409、下载=409、列表 requires_regeneration=true；真实 generate=200，从原执行恢复两条旧来源。forge 操作 `PC07A1_ACTION=forge ... python -m tests.pc07a1_browser_fixture` exit 0。

实际全 Mock 校准采集 ID `9a601f72-9434-4389-9f7d-45d39779dbb0`：真实 API 返回 simulated、samples=[]、net_loss_db=null、formal_eligible=false；采用预览 eligible_for_adoption=false/new_net_loss_db=null。这不是合成“真实来源”历史的生产者，不混称。

## 自查与未验边界

- 按仓库规则自查全部新增字段读方、生成/读取/重建/下载/旧报告入口；GUI 不查当前来源或配置拼值，不增加 SCPI，不改静区/采用/兼容资格。
- 本任务执行者自查，**非独立内审**；按主代理要求不派 reviewer，独立审查由主代理后续安排。
- 完整 MIMO OTA 全相位执行、现场真仪器、硬件连接/校准、正式认证均未验。实际 Mock 执行证据仅为固定通路校准采集，不能冒充全相位 MIMO OTA。合成历史本身含 scripted transport 构造的 real provenance，不是 Mock 获得真实采用，更非真机认证。报告整体保持非正式、静区未验证，不输出正式 PASS。
- PDF 既有 None 文案仅披露，未扩改；通用详情缺 MIMO 时间/KPI映射明确显示缺项，不声称已完整重构。
- 初次浏览器暴露的崩溃、关闭按钮无 aria-label 导致等待，以及初次过渡帧截图均保留在独立临时日志/旧输出；最终证据使用新目录不覆盖历史输出。

生产/验收输入文件 SHA256：

```text
9f4f246d88879adfabba67903a6a28b5e0ef28f560eab24419ed85d42a2e93a3 gui/src/components/Report/ReportViewer.tsx
1d7f8a225fd326329050538b8f52498919e25dd7ac2368e15fd69b19b9d11e62 gui/src/types/report.ts
9ec488be617c2e9d4fcd069a5ac3e2dd079ff36b62b5af033cde31d28c37faae gui/src/features/Reports/pages/ReportsPage.tsx
ce13668ea6f02b91455c3748257da923968fe6de26ef7ffb5a4af41dc6f886c1 gui/test/pc07a1Report.test.js
aa5d0082a77f3d519209344128e051e3560811531d7aa7f95806ea9d52e0afdb gui/test/pc07a1Report.browser.js
948abe87fd5353f76d84a552ce4ae86ea29b71e15b85aedbd6b736cb48f38894 api-service/tests/pc07a1_browser_fixture.py
```

## 补验：真实全 Mock MIMO OTA 启动（现有冻结阶段阻塞）

主代理要求补全实际 MIMO OTA 流程，不能以校准采集替代。本次按要求实际调用生产启动入口；未改生产代码、未改 Diagnostic policy、未放宽任何门。

精确补验输入提交：`602afe0bf1d4874ded01b42a305447758c266e06`（追加 `38325b3d` 和 `602afe0b`，均只涉及夹具/补验脚本）。原 b81fc541 的 GUI/构建/8 项浏览器结果复用，本次未无谓重跑，也未跑全后端。

新增范围：

- `api-service/tests/pc07a1_browser_fixture.py` 新增仅显式 `PC07A1_ACTION=prepare-mimo` 的临时 DB 种子动作，补 UXM 5G E7515B 和 EMCenter 两类 Mock 品类/型号/绑定；先核验全部原品类为 mock；不会覆盖既有同类配置。现有两类 CE/SA 未改为 real。保留原历史执行。
- `gui/test/pc07a1Mimo.browser.js` 新增独立补验脚本，只跑真实启动→终态→报告路径；启动非 202 明确返回 `blocked`，不假造 execution ID、measure 或报告。若现有门允许运行，后续脚本会核验实际报告不含正式 PASS/正式量值。

执行命令与结果：

```sh
# api-service 目录
env USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-Ah5AxP/browser.db PC07A1_OUTPUT=/tmp/pc07a1-Ah5AxP PC07A1_ACTION=prepare-mimo BOOTSTRAP_ON_STARTUP=false LOG_DIR=/tmp/pc07a1-Ah5AxP/mimo-prepare-logs .venv/bin/python -m tests.pc07a1_browser_fixture
# 工作树根目录
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=pc07a1 run-code "$(< gui/test/pc07a1Mimo.browser.js)"
node --check gui/test/pc07a1Mimo.browser.js
```

prepare-mimo exit 0；真实 POST `/api/v1/instruments/hal/reload` =200（forced=false），加载 baseStation/channelEmulator/positioner/signalAnalyzer 共 4 类。HAL GET 实际 `mode=mock,driver_count=4`。

脚本首次读取 LabProfile summary 时发现无 instrument_bindings 字段而失败（exit 1），已改为本夹具唯一实验室检查，没有补伪造字段。最终 602afe0b 上脚本 exit 0，但 Result **`blocked:true, stage:launch_freeze`**，不是运行成功；Node 语法检查 exit 0，Python `py_compile tests/pc07a1_browser_fixture.py` exit 0。

真实用例创建 POST `/api/v1/test-plans/cases` =201，ID `29769585-c9f1-43f2-8c0e-0c1c3a1d70ac`。配置为 2595MHz/BW100、azimuths=[0]、settling=0、每方位1个窗口、switch_mode_id=mimo_ota、base_station_config_mode=dispatch；未设置执行 policy、校准旁路或其他跳门字段。沿既有默认 strict 和标准配置规范化。

真实执行 POST `/api/v1/test-plans/cases/29769585-c9f1-43f2-8c0e-0c1c3a1d70ac/execute` = **422**：

```text
信道仿真器执行资格无法冻结: (builtins.AttributeError) 'str' object has no attribute 'hex'
... FROM instrument_connections WHERE instrument_connections.id = ?
```

静态定位到 `api-service/app/services/channel_emulator_certification.py::freeze_channel_emulator_execution_qualification`：从已冻结 binding 取字符串 `instrument_connection_id`，随后用 `InstrumentConnection.id == connection_id` 查询 SQLite UUID 列。在开始 phase 之前由真实执行入口拒绝。这里只定位、未修生产。

真实 DB 查询本次 source_test_case_id 的结果：`executions_created=0, measurement_rows=null`（SQLite sum 对空集合为 null，不是 0）。因此 **不存在本次原始 measure，也没有实际执行的报告可供生成/读取**；不能把合成历史旧报告或校准采集报告冒充本次 MIMO OTA 的完成证据。没有伪造终态或补写测量，也没有改 Diagnostic policy 绕过冻结。当前只能证明全 Mock 的真实启动被既有错误 fail-loud 拦截，不能声称五相位 simulated/unknown 已完成。

新增证据目录（不覆盖原 8 项证据）：

`output/playwright/pc07a1-mimo-supplement-602afe0b/`

- `requests-responses.json`：完整 HAL、LabProfile、用例创建与执行请求/响应，包含最终 422 原文。
- `case.json`：真实 DB 的用例配置；`execution-measure-audit.json`：无 execution/measure 的原始查询结果。
- `browser.db`：补验后 SQLite 快照；`mimo-prepare.log`：全 Mock 仪器种子动作输出；`api-logs/`：实际启动/拒绝日志。

本次阻塞需要后续独立修复 UUID 冻结查询（不属于 Task3 GUI 工作范围）或提供生产已支持的隔离数据库环境后重验。未自行添加生产能力。

补验输入 SHA256：

```text
dc16db264518289bb944f377ef610c930d500c77e9ba15cc23d643ecf6a44942 api-service/tests/pc07a1_browser_fixture.py
33a922e6c0258e712199fafd2b5c8481a400a32276f9e1ed0223f7275884fc83 gui/test/pc07a1Mimo.browser.js
```

## 最终补验：最小 UUID 前置修复后，真实五相位与报告通过

主代理明确授权把上述既有阻塞作为 Task3 验收必要前置修复，并要求遇下一阻塞先报告。已独立提交 `0f7d69434158c6d90c0236a7f29f80662cec04c8`，未 push。实际重试没有下一阻塞。

### 根因与最小新增范围

- 既有来源归属：查询由 `c2269ca9bec70e8fb9055ff0860e5edac6808801`（2026-09-05）引入，已为 Task3 基线祖先；resolver 字符串投影由 `1614e2d965cfd0149cd547da1bbb1299aa46dddc` 引入。本片此前未改这条生产链。
- 模型 `InstrumentConnection.id` 是 `UUID(as_uuid=True)`；真实 ORM 读回 UUID。resolver 有意 `str(connection.id)`，冻结 schema 也有意要求字符串。真实创建用例请求只提交 lab_profile_id，不提交 connection_id；此 ID 来自该实验室的合法已配置连接，不是客户端非法类型。SQLite UUID bind processor 收到 UUID 对象正常，收到对应字符串即 `.hex` 错误。
- `api-service/app/services/channel_emulator_certification.py` 仅在 `freeze_channel_emulator_execution_qualification` 内增加 UUID 导入，把唯一该查询改为 `InstrumentConnection.id == UUID(connection_id)`；不改冻结字典、身份比对、with_for_update、schema 或资格判据。无效 UUID 直接 ValueError，缺失连接沿既有明确拒绝。该函数无第二处连接查询；同模块 revoke/activate 是 API UUID 参数，不消费本冻结字符串，不需同改。
- 新增 `api-service/tests/test_pc07a1_qualification_uuid_boundary.py`：真实临时 SQLite + ORM 连接行，通过实际资格冻结函数验证查询、身份保留、无有效认证仍 diagnostic；删除连接后明确拒绝；非法 UUID 明确拒绝。
- 更新 `api-service/tests/test_p2_61_channel_emulator_certification.py` 的既有夹具：原 MagicMock 的 `ce-connection` 是非 UUID 占位符，换成合法固定 UUID 并同步该夹具引用；不为占位符给生产加兜底。

### RED / GREEN 与精确命令

api-service 目录，显式 `USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-Ah5AxP/qualification-tests.db`：

```sh
.venv/bin/python -m pytest tests/test_pc07a1_qualification_uuid_boundary.py -q -o log_cli=false --tb=short
.venv/bin/python -m pytest tests/test_pc07a1_qualification_uuid_boundary.py tests/test_p2_61_channel_emulator_certification.py tests/test_arch1_case_runner.py -q -o log_cli=false --tb=short
.venv/bin/python -m pytest tests/test_p2_62_channel_emulator_adapter_certification.py tests/test_p2_77_channel_asset_frequency_semantics.py -q -o log_cli=false --tb=short
```

- 首个初版测试先发现旧 MagicMock fixture 使用 `ce-connection` 本身不是合法 UUID，调整为合法冻结身份后，真实 ORM RED：exit 1，1 failed/40 warnings/0.32s，`StatementError: (AttributeError) 'str' object has no attribute 'hex'`，证据 `qualification-red-orm.log`。
- 两行最小修复及旧夹具身份同步后：exit 0，**87 passed/171 warnings/7.55s**，证据 `qualification-green-final.log`。首次组合回归的 85 passed/2 failed 仅为旧激活 fixture 仍硬编码 ce-connection，已同步为同一冻结 UUID，未改其判据。
- 搜索发现该认证夹具还有 P2-62/P2-77 两组消费者，定点补跑：exit 0，**52 passed/43 warnings/1.07s**，证据 `qualification-fixture-consumers.log`。
- 不跑全后端，不重新跑已通过的原 8 项浏览器或无变化 GUI build。

### 实际 MIMO OTA 五相位执行证据

终止旧隔离 API PID 10571 后，用同临时 DB/18089 端口、全 Mock、bootstrap=false 启动精确提交 0f7d6943；日志改为 `/tmp/pc07a1-Ah5AxP/logs-after-uuid`，未覆盖旧日志。

重新执行现有补验脚本：

```sh
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=pc07a1 run-code "$(< gui/test/pc07a1Mimo.browser.js)"
```

exit 0，实际 Result `blocked:false, terminal:completed`。真实执行 ID **`b7c84957-e973-4e75-ba37-2c0e2b47b30f`**；真实启动=202，原 DB measurements 含 **precheck/reference/measure/analysis/report 五相位**。

- 原 measure：`measurement_source=simulated`、`measurement_verified=false`、simulated_sources=[baseStation,channelEmulator,positioner]。
- 原 analysis：`execution_classification=diagnostic`、`verdict=UNKNOWN`，avg_throughput/throughput_pass、rsrp_variance/rsrp_pass、avg_sinr/sinr_pass、avg_rank/rank_pass、qz_pass 等正式量值/判据均 null。
- 原行 raw `validation_pass=0` 一并原样保留；没有把此兼容布尔当成正式结论。实际报告的权威投影为未判定/UNKNOWN，不呈现正式失败或通过。
- 新实际报告 `7495573d-bf87-4ce5-ab7b-5a0e13b50737`：真实创建=201、生成=200、详情=200、下载=200（application/pdf，115080 bytes）。`overall_result=undetermined`、`pass_rate=null`，formal_path_loss_verified/formal_rf_kpi_verified/formal_quiet_zone_verified 全 false。
- 本次仍能看见合成历史中选定的校准来源，但 `status=not_applied`、gate_mode=mock_not_applicable、每链 application_state=selected，**仅选择不等于实际应用**。来源快照 provenance=real 是先前合成历史标记，不是本次 Mock 采集产生的真实量值。
- 额外真实 GUI 只打开该新报告详情一次，截图显示“诊断完成·仅审计”“通过率未判定”和逐链“仅选择，未应用”。不是重跑原 8 项。

最终新增证据目录：

`output/playwright/pc07a1-mimo-completed-0f7d6943/`

内含完整 `requests-responses.json`、原 DB `raw-execution.json`、`mock-audit-summary.json`、真实下载 `actual-mock-report.pdf` 与提取文本、`actual-mock-report.png`、补验后 SQLite 快照、API 专属日志和三份定点测试日志。PDF 提取文本含模拟执行/UNKNOWN、Passed(0)/Failed(0)、未判定通过率；非真机认证。原阻塞证据目录全部保留，不删改历史。

本任务执行者自查，非独立内审；累计独立审查仍由主代理安排。没有新增硬件 SCPI，没有改静区、模拟量值、正式 KPI、采用或资格门。

最小前置新增输入 SHA256（其余任务输入沿上一节）：

```text
1c1bfbd87bab728899066fc752512f186cf807e663b546e85d2075fc0a4b5bfb api-service/app/services/channel_emulator_certification.py
01c3ade22ce4aac083664ce66b25fd90fcb574e6a5e35a89457bb7bb3350abce api-service/tests/test_p2_61_channel_emulator_certification.py
12771947636a5d18b2749efb91bf9a1c2c3813309a66ba07a654c35d183fe80e api-service/tests/test_pc07a1_qualification_uuid_boundary.py
```
