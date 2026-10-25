# PC06A2 系统校准入口整合：软件验证记录

## 交付范围与边界

管理页统一进入当前 LabProfile 的原射频拓扑；方法说明不再执行旧校准。旧 TRP/TIS、执行指标对齐及证书从真实 API 只读回放，原字段/判词不升级成当前资格。生产后端、HAL/SCPI、采用、补偿、执行冻结及报告逻辑未改。

验证生产输入基准 `6380023bc66c8541e55f176f070c7e75e3c5f425`（Task1 `5bae8481`、Task2 `6380023b`）。本任务新增 `gui/test/pc06a2EntryLifecycle.browser.js`，其余为证据和当前状态文档。各任务及整片累计独立内审完成，[PR #537](https://github.com/swang430/Meta-3D/pull/537)于2026-10-25T18:35:05Z合并至 `f632d26c873f0514785946b65c15660a5ead6880`；[R2 回执](https://github.com/swang430/Meta-3D/pull/537#issuecomment-6401459096)于2026-10-25T18:26:56Z覆盖 `805bddca6e`，未发现重大问题。与首页首片[PR #535](https://github.com/swang430/Meta-3D/pull/535)共同完成PC-06A-2批准软件待办；仅关闭该软件范围，不关闭PC-06其余范围或B/HOLD。下文保留当时实际测试输入、结果与未验边界，合并不等于正式计量/现场验收。

全部为独立 SQLite、真实 HTTP/REST 序列化、全 HAL Mock 的软件验证，`formal_acceptance:false`。不证明仪器能力、实物接线、停发、射频量值或正式计量合格；现场 B、PC-09/10 HOLD 不变。

## 隔离环境与复现

首次试跑目录 `/tmp/pc06a2-entry-HUp9ud`；第二次完整矩阵目录 `/tmp/pc06a2-entry-y7t6c1`。两次均由 `mktemp -d /tmp/pc06a2-entry-XXXXXX` 新建，未删除旧行冒充空库，未借用 Task1/2 已执行的数据库。第一次生命周期在取消后期待解锁的断言失败，证据保留；见下文保守锁边界。

GUI `127.0.0.1:5190`，API `127.0.0.1:18090`。初查这两个端口空闲，5191/18091 的 Task2 服务未触碰。Vite 配置原文 `/tmp/pc06a2-entry-HUp9ud/vite.config.mjs`：

```js
import { defineConfig } from '/Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/gui/node_modules/vite/dist/node/index.js';
import react from '/Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/gui/node_modules/@vitejs/plugin-react/dist/index.js';
export default defineConfig({
  root: '/Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/gui',
  plugins: [react()],
  resolve: { alias: { 'plotly.js/dist/plotly': 'plotly.js-dist-min' } },
  server: { proxy: {
    '/api/v1/ws': { target: 'http://127.0.0.1:18090', ws: true, changeOrigin: true, secure: false },
    '/api': { target: 'http://127.0.0.1:18090', changeOrigin: true },
  } },
});
```

所有 `/api` 含 OTA 均指此 API；不启用 setupMockServer，不 route.fulfill。第二库继续使用同一代理，停止第一库 API 后才接入第二库，manifest/HAL 实读重新核验。

API 目录下，应用导入前显式设置三项环境变量和专用日志目录：

```sh
env USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true DATABASE_URL=sqlite:////tmp/pc06a2-entry-y7t6c1/browser.sqlite LOG_DIR=/tmp/pc06a2-entry-y7t6c1/logs .venv/bin/python -m tests.pc06a2_entry_browser_fixture
env USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true DATABASE_URL=sqlite:////tmp/pc06a2-entry-y7t6c1/browser.sqlite LOG_DIR=/tmp/pc06a2-entry-y7t6c1/logs .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18090
```

根目录前端命令：

```sh
gui/node_modules/.bin/vite --configLoader native --config /tmp/pc06a2-entry-HUp9ud/vite.config.mjs --host 127.0.0.1 --port 5190 --strictPort
```

默认 bootstrap 两次均 `6 seeders · +116 new · =0 kept · 0 failed`；真实 HAL `mode:mock, driver_count:7`。只读 SQL 确认全部类别及全部 Lab bindings 为 mock，无 real override；CE/SA 为文档网段192.0.2.10/11，分析仪显式选择目录已有 FSVA3000。三个 Lab 中第三个无暗室且 bindings=[]。

第二库 manifest：

| 对象 | Lab ID | 暗室 ID | 拓扑 ID |
|---|---|---|---|
| 甲 | f5af8689-928d-4867-8046-4d933098d287 | 4722f789-a13a-4a23-b610-9ce35c055f4c | 15fb47f6-382d-4b22-896e-16afbfae7fe6 |
| 乙 | f14bd627-f298-433e-a7df-ba14158dad3b | 589a8478-3d30-48f9-9159-6ade84622a82 | 334a56bf-5536-43c3-8f7f-cd28379b7582 |
| 无暗室 | f2b76e2a-28a9-4cd5-beaa-f37288a39600 | null | null |

浏览器真实 session 为 `pc06a2-entry-task3`、`pc06a2-entry-task3b`。使用既有 Playwright CLI，先 snapshot，再执行 checked-in `async page =>` 行为脚本；未更换为伪响应单测。完整命令、输出、PID/session 和本地输入清单保留在本地 Task3 交接报告及上述目录。

## 浏览器矩阵与数据不变性

固定顺序为新空库→首页/空记录→停本次 API→同库显式 `--seed-legacy`→重启→旧档案/导航→显式原图采集。fixture拒绝重复 seed，不调用旧证书/TRP/TIS生成 POST。旧档案为22 TRP、1 TIS、1稀疏 execution_metrics、1证书、2基线；不是现场测量证据，证书 pdf_path=NULL。

| 场景 | 实际结果/原始日志（第二库目录） |
|---|---|
| 初始空库 | `browser-empty.log`、`browser-status-empty.log`：四项未知，记录/证书空且成功，无演示、生成或下载 |
| 甲→乙→甲、双入口、无Lab/无暗室 | `browser-navigation-seeded.log`：同Lab GET 参数/暗室身份正确；未伪选候选；所有管理请求GET |
| 旧记录与分页 | `browser-legacy-seeded.log`、`browser-restored.log`：22TRP按真实服务器顺序20+2，ID/原数值/原判词/详情JSON逐项一致；TIS原false；执行对齐NULL保持未知，不补execution IDs |
| 基线切换与刷新 | 甲2595、乙3500、再甲；显示原valid、资格未知；无quick/drift/create POST |
| 离线与真实API失败 | 旧档案脚本真实offline刷新显示paused并隐藏旧行；`browser-api-error.log`真实停API后502，证书详情/列表隐藏旧成功，Lab error禁跳转；恢复后真实读取成功 |
| 完整采集前置 | `browser-lifecycle.log`先真实PATCH甲图12节点/10连接，双极化各有正常/空气/参考天线/接收线缆/分析仪段，再从真实paths取得chain_id |
| 单路 | run `efd2b1f2-811e-4c7b-8ddb-0fc1e0af9aa4` 属甲，simulated、net_loss_db=NULL、采用禁用；离管理页再回来仍是原run |
| 活动期与恢复 | 真实waiting_manual窗口图冻结；离开到管理仍拒绝跨Lab，服务端未自动cancel；回来恢复同job，不复制引擎 |
| 四项批与人工 | fixed-h/fixed-v ×2595/3500，预览4项；首项与跨路人工确认；job `43025cd4-bfaa-4969-9407-4494f989b8c6`完成4个simulated子项，均无正式采用资格 |
| 终态跨Lab | 第一批completed且软件锁释放后切乙，乙run/job历史为空；返回甲仍有5个原run |
| 取消 | 第二批 `f0b69165-b28d-414f-b9ca-7968d09f6df0`两项后取消；cancelled+finalization_committed，刷新不续跑，共7个甲run；取消Mock保守锁仍保留，不宣称取消后切Lab通过 |

单路 Mock 终止很快，本任务未观察到单路活动窗口；活动期跨页/跨Lab保护由确实观察的批次 waiting_manual 窗口与后端生命周期回归补证，不以终态冒称活动期。

取消锁来自原 `routeCalibrationState.batchPureSimulationEnded`：只对完整 completed 纯模拟记录释放软件锁；取消缺真实释放证明不走此例外。第一轮 `browser-lifecycle.log` 对取消后解锁的错误期望导致 `TimeoutError: page.waitForFunction`（CLI外壳exit0，实际Error，不算通过）。不改生产判据；另建新库重跑正确分开的completed与cancelled场景。没有用关闭页面充当实物停发证明。

主代理核实 `batchCanRelease/batchPureSimulationEnded` 后裁决：这是既有保守契约，不作本片新入口回归阻塞；第一批completed且完整父子证据后验证跨Lab，第二批cancelled保留锁单列。代价是Mock取消后仍受软件锁限制；不宣称所有终态可切Lab或实物停发，最终独立审查仍可核对本片是否改变行为。

只读SQL证据：

- `target-before.sql` 与 `target-after-lifecycle.sql`，旧四类档案、基线、Lab（含证书FK）、RouteCalibrationSelection、TestExecution、test_reports 全字段dump相同，cmp exit0；单/批采集只产生显式作业，不写旧档案/正式执行/报告。
- 首个全库比较窗口 `management-before.sql`→`management-after.sql` 与显式生命周期PATCH调度重叠，唯一差异是甲拓扑的预期完整接线PATCH，不能称全库零写。单独重做纯管理窗口 `readonly-final-before.sql`→`readonly-final-after.sql`，全库dump完全相同、cmp exit0。
- 所有dump均只读打开原文件库；`target-before.sql`从原始before快照装入SQLite内存后导出目标表，不写回证据库。没有删除任何证书文件。

截图在仓库未跟踪 `output/playwright/`：`pc06a2-task3-single.png`、`pc06a2-task3-preview.png`、`pc06a2-task3-active-recovery.png`、`pc06a2-task3-cross-route.png`、`pc06a2-task3-cancelled.png`、`pc06a2-task3-cancelled-detail.png`、`pc06a2-task3-api-error.png`；旧档案最终截图沿用 `pc06a2-task2-*` 文件名。活动恢复与取消详情截图已实际查看。大产物只保留本地，不当作已随Git共享。

## 回归、构建与变异

本任务实际命令（GUI cwd=gui）：

```sh
npx --yes tsx --tsconfig tsconfig.app.json --test test/pc06a2LegacyRead.test.ts test/pc01aCalibrationScope.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts test/topologyDraft.test.ts test/topologyOperationalLabContext.test.ts test/topologyHandleFreeze.test.ts
npm run build
```

`/tmp/pc06a2-entry-HUp9ud/gui-related.log`：60 tests/60 pass/0 fail，exit0；`gui-build.log`：TypeScript+Vite exit0，`built in 12.38s`。保留service.ts静态/动态导入混用提示及大于500kB chunk警告，不扩域优化。

后端 cwd=api-service，每次先创建全新专用SQLite再设三项env，不继承browser库：

```sh
pc06_related_tmp=$(mktemp -d /tmp/pc06a2-related-XXXXXX)
env DATABASE_URL="sqlite:///$pc06_related_tmp/tests.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_jobs.py tests/test_pc06a1_batch_safety.py tests/test_pc07a1_calibration_traceability.py -q
pc06_full_tmp=$(mktemp -d /tmp/pc06a2-full-XXXXXX)
env DATABASE_URL="sqlite:///$pc06_full_tmp/tests.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests -q
```

相关库 `/tmp/pc06a2-related-2xYGFS/tests.sqlite`，`backend-related.log`：**226 passed / 1219 warnings / 275.10s，exit0**。涵盖补偿、采用、旧执行冻结、批次取消安全及报告实际采用追溯；不另造正式资格。

最终全后端由本Task3唯一责任人执行一次，库 `/tmp/pc06a2-full-9xE8F8/tests.sqlite`，原始日志 `backend-full.log`，实际尾部 **1 failed, 7485 passed, 17 skipped, 7306 warnings in 592.20s (0:09:52)**，exit1。唯一失败为下述G8旧历史引用误报，不能称全绿。虽统计与旧片相同，本次是新库完整实跑，不复用旧片结果。生产/pytest输入与BASE6380023b一致；后续只有新增独立浏览器脚本和证据/状态文档，不以HEAD相等充当测试输入证明。

文档更新后另以新库 `/tmp/pc06a2-gates-sWefus/tests.sqlite` 单独复核G8：`pytest tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes -q`，`g8-current-docs.log`：**1 failed / 40 warnings / 0.97s，exit1**。唯一指向旧 `docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md` 第111行的真实历史执行URL。该文件Git对象在BASE6380023b与工作区均为 `1017db2acaba7415b8442070ab4c0e912f03424d`，gate源和生产API相对BASE diff为空；该段记载当时HTTP422，不是当前路由施工说明。未改该历史原文或G8规则，不称全绿。此为当前文档影响复核，不是第二次全后端或一次新生产验证。

核心变异复用已精确绑定且本任务未改的生产输入：

- Task1 `5bae8481`，`/tmp/pc06a2-entry-1I7BC1/`：旧执行按钮恢复→“管理向导仍可执行旧校准”；回调dashboard→原拓扑面板超时；自身补丁恢复前后SHA/diff cmp均exit0，恢复GREEN。
- Task2 `6380023b`，`/tmp/pc06a2-entry-LAC8G9/`：local-demo→真实分页/transport失败；假PDF按钮→“证书存在生成或下载入口”；最终恢复SHA/diff cmp均exit0，GREEN与transport 2passed。最初transport模块缺失RED仅有会话原始输出，不能伪造成本任务日志。
- 本任务没有重新执行上述变异；相应生产源/单测输入与基准一致。Task1/2的额外91/93项GUI结果仍是各自报告，不冒称本任务60项之外的新运行。

## 保留边界与下一步

证书fixture仅1条，证书满20再空页仅检查现有分页代码；404为真实只读适配器transport单测边界，不为浏览器404删除旧行。稀疏execution_metrics只测历史形态，不是实际正式执行对齐。无实物射频开关动作、无新正式采用、无PDF生成、无现场验收。

累计独立内审及R1/R2已完成、PR #537已合并，正式队列中的PC-06A-2批准软件待办关闭；PC-06其余范围、现场B、PC-09/10 HOLD及上述未验边界保留。Task3自身新建服务/浏览器已关闭，证据目录、venv、scratch与用户资料保留；本次仅文档状态同步，没有重新运行测试或操作服务。
