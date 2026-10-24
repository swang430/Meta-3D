# PC-06A-1 软件验证摘要

状态（2026-10-25）：多通路/频点/极化受控批校准已实现，软件验证与内审修复完成，待 PR 外审、合并及同步清理。不是 PC-06 整项 Done，不解除 PC-06B 或其他现场验收条件。范围见[实施计划](2026-10-24-pc06a1-topology-batch-calibration.md)。

## 稳定版本与测试

后端全量实际启动输入为 `4667448bb5bf3ec825c5bed3dcacd021309bcd47`，在 api-service 目录运行：

```sh
USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc06a1-f1-full-4667448b.db BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest -q -o log_cli=false > ../output/pc06a1-task6/backend-full-f1-4667448b.log 2>&1
```

独立新建临时 SQLite、全 Mock、保留默认 bootstrap；Darwin、Python 3.13.14、pytest 9.1.1。实际退出 0：**7423 passed / 17 skipped / 6835 warnings / 512.79s**，7440 collected。本轮是新增后端/API修复后的完整新运行，未用旧7422结果替代。

输入关系：`4667448b → aa542c03` 仅 GUI 历史 snapshot 守卫与测试；`aa542c03 → 3122f461` 另有两份浏览器 fixture 和浏览器脚本增量。后端生产代码与常规 pytest 输入不变，但不能称整个 api-service 目录无差异：`tests/pc06a1_browser_fixture.py`、`tests/pc06a1_transport_browser_fixture.py` 不匹配 pytest.ini 的 `test_*.py *_test.py`，全 tests 检索仅有后一个 fixture 导入前一个，没有常规测试导入它们。全量准确标为4667448b输入，不称在3122f461重新运行。

GUI 最终生产输入 `aa542c0394f3fcf522ba0a10ab412d8caa0ab3b3`：Task5 六文件相关回归 **61 pass / 0 fail / 185.13875ms**，`npm run build` 退出0，8083 modules、12.23s；既有导入/大chunk警告保留。Task6另实跑 `npx --yes tsx --test test/pc06a1Batch.test.ts test/pc04a2RouteCalibration.test.ts`，**27 pass / 0 fail / 158.788875ms**、退出0。未机械重复同源构建。

61项的原命令（gui目录）：`npx --yes tsx --test test/pc06a1Batch.test.ts test/pc04a2RouteCalibration.test.ts test/pc04FixedRoute.test.ts test/topologyDraft.test.ts test/catalogInvalidStoredFields.test.ts src/features/Equipment/invalidStoredFields.test.ts`。本摘要核对Task5记录后引用，不称由Task6另跑61项。

## 浏览器与核心保护

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

- 最终日志：`backend-full-f1-4667448b.log`、`gui-f1-final.log`；旧失败/无效环境日志单独保留。
- sameCE：`f1-serial-mock-browser.json`、`f1-serial-mock.db`、`f1-serial-mock-child-rejected.png`；`f1-serial-transport-browser.json`、`f1-serial-transport.db`、`f1-transport-commands.json`、`f1-serial-child-adopted.png`、`f1-final-head-child-view.png`、`f1-browser-version.json`。
- 安全与变异：`idempotency-browser.json`、`missing-child-api.json`、`restart-after.json`、`restart-transport.json`、`transport-wrong-commands.json`；`mutation-exclusion.log`、`mutation-switch-emission.log`、`mutation-cleanup.log`、`mutation-restart.log`、`mutation-mock-adoption.log`。
- 视觉：`small-viewport.png`。详细版本/命令/失败披露与构建来源见同worktree的 `.superpowers/sdd/2026-10-24-pc06a1-topology-batch-calibration/` 下 `task-5-report.md`、`task-6-report.md`、`final-review.md`（本地忽略材料，不作为已提交附件）。

本次隔离服务和可访问浏览器已关闭，临时库、证据、用户配置及共享未跟踪文件保留。后续由主代理组织文档增量审查和PR外审，不提前启动下游或释放主认领。
