# PC-06A-1 软件验证摘要

状态（2026-10-25）：多通路/频点/极化受控批校准已实现，软件验证与内审修复完成，待 PR 外审、合并及同步清理。不是 PC-06 整项 Done，不解除 PC-06B 或其他现场验收条件。范围见[实施计划](2026-10-24-pc06a1-topology-batch-calibration.md)。

## 稳定版本与测试

R1修复后最新后端全量实际启动输入为 `6dcf850a5d387e581c6a5883d1d2840c4e4e2a9c`，在 api-service 目录运行：

```sh
USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc06a1-r1-full-6dcf850a.db BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest -q -o log_cli=false > ../output/pc06a1-task6/backend-full-r1-6dcf850a.log 2>&1
```

独立新建临时 SQLite、全 Mock、保留默认 bootstrap；Darwin、Python 3.13.14、pytest 9.1.1。实际退出 0：**7434 passed / 17 skipped / 6839 warnings / 516.12s**，7451 collected。唯一新版完整运行，不复用旧7423或更早结果。`6dcf850a → 6161244d` 只改浏览器验证JS，api-service/api无差异，准确标注全量启动版本，不称在验证提交重新启动。

R1前版本关系保留供查旧证据：`4667448b → aa542c03` 仅 GUI 历史 snapshot 守卫与测试；`aa542c03 → 3122f461` 另有两份浏览器 fixture 和浏览器脚本增量。后端生产代码与常规 pytest 输入不变，但不能称整个 api-service 目录无差异：`tests/pc06a1_browser_fixture.py`、`tests/pc06a1_transport_browser_fixture.py` 不匹配 pytest.ini 的 `test_*.py *_test.py`，全 tests 检索仅有后一个 fixture 导入前一个，没有常规测试导入它们。旧7423全量准确标为4667448b输入，未改写历史日志；R1生产变化由本节新版7434全量覆盖。

GUI生产自 `aa542c0394f3fcf522ba0a10ab412d8caa0ab3b3` 后未变，Task5六文件 **61 pass / 0 fail / 185.13875ms** 记录保留。R1作者在6dcf850a同输入执行 `npx --yes tsx --test test/pc06a1Batch.test.ts test/pc04a2RouteCalibration.test.ts`，**27 pass / 0 fail / 139.086166ms**；最新 `npm run build` 退出0，8083 modules、11.62s。本摘要引用r1-fix-report的作者记录，不冒称由Task6另跑；既有导入/大chunk警告保留，不机械重复同源构建。

61项的原命令（gui目录）：`npx --yes tsx --test test/pc06a1Batch.test.ts test/pc04a2RouteCalibration.test.ts test/pc04FixedRoute.test.ts test/topologyDraft.test.ts test/catalogInvalidStoredFields.test.ts src/features/Equipment/invalidStoredFields.test.ts`。本摘要核对Task5记录后引用，不称由Task6另跑61项。

## 浏览器与核心保护

R1新版真实浏览器复验（6dcf850a，独立临时DB，所有响应均未伪造）：

- 全Mock sameCE父 `7630859e-40f5-4258-981e-2eaf892d8fd3` 两项simulated完成；同源builder的NO/NC命令落 `command_preview`，simulated=true、raw=null、position/write_return未知，HAL无真实switch驱动、无真实开关I/O/回读/采用资格。父释放null、child净损耗null、采用预览均false。它不是SPDT真实auto正例。
- UI以1000000MHz请求，preview200后start422；即时独立DB快照仍3行=原1父2child，无拒绝请求孤儿父。同键 `0f54c000-6417-4300-b3d7-0213941a969c` 由真实API提交修正2595MHz请求后返回202，新父 `d3dac7b5-f6eb-4de1-984d-d2bf4290a673`；页面恢复后两项simulated完成，最终2父4child。422后UI仍保锁的既知边界保持，未冒称被锁表单直接完成修正。
- 新隔离真实HAL＋脚本transport sameCE父 `9963b4d6-03ff-49fc-9165-90a7367b2e90` 两项completed，严格A_2/回读2→A_1/回读1，正式同时集合仍422；仍是禁外连、全硬件transport脚本化的软件证据，不是真机。未重复旧采用201场景，不把旧201归到R1运行。

以下为R1前按原版本留存的通用浏览器和核心变异证据，不冒称全部在R1重新执行：

- 全 Mock、真实 API：原画布保存/刷新、四项预览、首次及跨路人工、失败读取保锁、取消后不续跑、丢启动回执后同请求同 Idempotency-Key 重读、新页面缺 child 身份拒绝继续均有截图/API/DB记录。模拟子项净损耗null、无正式采用资格；释放null仅允许明确纯模拟软件任务结束，不补成真实释放。
- 同CE互斥串行图：默认正式同时集合仍422，individual返回两条B1.1候选，真实页面选择→两项预览→声明→POST202→child入口可达。全Mock父 `af0bbb17-e6d6-4594-977b-cd2b3ccfb772` 两项simulated，两个采用预览均拒绝。
- 真实HAL类＋脚本transport：独立临时库/端口、启动前禁止非回环socket连接、所有外部仪器transport脚本化；生产准备、严格写读、采集及最终化链未被替代。SP6T目标槽正例及错误原始回读拒绝/零后续发射均有记录；不是全Mock，也不是实物。sameCE父 `e517578c-519a-4e79-b6c2-b03f9552ec36` 两项完成，从child原入口实际确认采用得到服务器201（`cf02e0e5-5135-450c-9c98-cefcb294b3b5`）；未伪造或改写响应，不授予RF/计量认证。
- 核心运行时变异：互斥、错误回读进入采集、cleanup未知、重启registry丢失、模拟采用五项均实际产生行为断言失败，`MUTATION_TEST_EXIT=1`、`MUTATION_RESTORED=True`；只改测试进程函数code，生产文件未被改写。重启变异仅撤“registry缺失→interrupted”读取判据；实际SIGKILL重启零动作/零child是另一份未变异证据，不冒称注入自动重发后杀死了该变异。

## 内审与未验证边界

整片内审发现F1：sameCE批候选及child采用错误依赖正式同时集合。`4667448b`改为服务器individual候选和child冻结scope核验，正式同时门未放宽；scoped复核 **F1 ADDRESSED**。其后F2：合法不完整历史snapshot使新读取路径渲染抛错；`aa542c03`收窄形状守卫，未知历史不补当前值，scoped复核 **F2 ADDRESSED / CLEAN（仅该增量）**。不把局部CLEAN写成外审或合并完成。明确422后安全混合历史child缓存未参与解锁的既知P2只披露，不自动积压。

1600×1000下功能控件、原图FitView、状态及采用提示已检查；页面/侧栏依现有滚动设计操作，滚动后上部有裁切，不签整页无裁切。1280×800既有页头/侧栏重叠与初始画布裁切**未通过视觉验收**，本片未扩响应式修复。

早期两次targeted未显式DATABASE_URL，业务fixture虽隔离，仍无法排除lifespan默认数据库连接尝试；已捕获日志无默认库连接/写入证据，但临时细日志退出后清理，**不能据此证明用户库完全未写**。未探查用户数据库；后续相关复验与最终全量均显式临时SQLite。初次错误bootstrap环境中止、旧全量两条物理输出fixture失败与修正记录均保留，未改规则迎合测试。

真实仪器/RF量值、真实停发与Local控制归还、人工身份认证、计量溯源及现场B验收均未证明；模拟绝不可采用。固定直连零switch I/O；生产auto只对已核验SP6T目标槽，SPDT/未知拒绝。既有本地ASC waveform一次补偿的软件消费证据不扩展为native GCM、外部ASC或B2支持。

## 本地证据索引

证据不纳入本摘要复制，完整本地根目录：
`/Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/output/pc06a1-task6/`

- R1前日志：`backend-full-f1-4667448b.log`、`gui-f1-final.log`；旧失败/无效环境日志单独保留。
- R1最新：`backend-full-r1-6dcf850a.log`、`r1-mock-serial-browser.json`、`r1-final-api-audits.json`、`r1-frequency-rejected-browser.json`、`r1-after-rejection.db`、`r1-after-rejection-db-records.json`、`r1-frequency-same-key-reused.json`、`r1-browser-final.db`、`r1-final-db-records.json`、`r1-real-hal-serial-browser.json`、`r1-real-hal-serial.db`、`r1-transport-commands.json`及同前缀PNG。R1详细命令/环境/脚本失败披露见本地SDD `r1-validation-report.md`；修复作者GUI/build来源见`r1-fix-report.md`。
- sameCE：`f1-serial-mock-browser.json`、`f1-serial-mock.db`、`f1-serial-mock-child-rejected.png`；`f1-serial-transport-browser.json`、`f1-serial-transport.db`、`f1-transport-commands.json`、`f1-serial-child-adopted.png`、`f1-final-head-child-view.png`、`f1-browser-version.json`。
- 安全与变异：`idempotency-browser.json`、`missing-child-api.json`、`restart-after.json`、`restart-transport.json`、`transport-wrong-commands.json`；`mutation-exclusion.log`、`mutation-switch-emission.log`、`mutation-cleanup.log`、`mutation-restart.log`、`mutation-mock-adoption.log`。
- 视觉：`small-viewport.png`。详细版本/命令/失败披露与构建来源见同worktree的 `.superpowers/sdd/2026-10-24-pc06a1-topology-batch-calibration/` 下 `task-5-report.md`、`task-6-report.md`、`final-review.md`（本地忽略材料，不作为已提交附件）。

本次隔离服务和可访问浏览器已关闭，临时库、证据、用户配置及共享未跟踪文件保留。后续由主代理组织文档增量审查和PR外审，不提前启动下游或释放主认领。
