# PC06A2-1 系统校准首页状态真实性验证摘要

## 结论与版本

2026-10-25，PC06A2-1 已实现，功能/测试提交为 `0740620c3a95f3d7d4e8fb8a827235fc890d1b18`，实施 BASE 为 `e89d1bc62e2a558c01178603e2d6d3e2d47d025d`，分支为 `codex/pc06a2-calibration-status-truth`。Task 1/2 的独立审查结论为规格符合、质量 Approved、无缺陷；该结论由主代理交接确认，本文不把作者自查冒称独立审查。文档收口后的累计整片内审、Ready PR 与 R1/R2 仍待推进，**尚未开 PR、未合并，不关闭 PC-06A-2 整项**。

本片只消除“无证据仍显示系统证书有效、固定精度/合格率/趋势”的首页故障：顶部四项未知，概览仅保留两条中性说明和原基线组件；路径示例卡、时间线、依赖图不再挂载。没有新增 API 或判决，不用路径损耗充当 TRP/TIS。范围见[本片计划](../plans/2026-10-25-pc06a2-1-calibration-status-truth.md)、[总计划](../plans/2026-10-25-topology-editor-calibration-consolidation.md)。

提交仅涉及三个文件：

- `gui/src/components/SystemCalibration/index.tsx`
- `gui/src/components/SystemCalibration/CalibrationDashboard.tsx`
- `gui/test/pc06a2CalibrationStatusTruth.browser.js`

本次文档收口不改生产或测试输入，复用上述版本的实际验证，不宣称文档提交后重跑 build 或浏览器。

## 命令与结果

| 阶段及输入 | 实际结果 | 原始证据文件 |
| --- | --- | --- |
| RED：BASE 加新浏览器测试，尚无生产修改 | `Error: 无证据仍展示 TRP 精度`；不是新 testid 不存在 | `red.txt`、`red.png` |
| 两处 GUI 最小修改后的 GREEN | 四项未知、无固定成果、示例面板不挂载、旧 Tab/新建入口保留 | `green.txt`、`green-a-final.txt` |
| 仅顶部 TRP 回注 `±0.12 dB`，最终测试版变异 | 同一错误再次 RED；随后 apply_patch 恢复未知并 GREEN | `mutation-final.txt`、`green-restored-final.txt` |
| 精确提交 `0740620c` | 同一浏览器用例再次 GREEN | `green-committed.txt` |
| 甲→乙→甲→刷新 | 实际持久化 ID 与本次新库响应一致；顶部仍四项未知 | `select-a.txt`、`switch-refresh.txt` |
| 浏览器真实离线后基线只读刷新 | `net::ERR_INTERNET_DISCONNECTED`；四项仍未知、无固定数值；恢复在线并 GREEN | `offline.txt`、`green-online-final.txt` |
| 相关前端回归 | exit 0，9 passed、0 failed、0 skipped，140.115542 ms | `frontend-tests.txt` |
| 生产构建（最终生产代码相同） | exit 0，`✓ built in 12.96s`；保留既有 dynamic/static import、chunk-size 警告 | `build.txt` |
| 最终数据复核 | 两实验室空绑定；24 张名称含 calibration 的表均 0 行；certificate 200 `[]` | `db-final.txt`、`final-certificate.txt` |

浏览器命令（本次独立 `pc06a2` 会话，cwd=工作树根）：

```bash
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=pc06a2 open http://127.0.0.1:5189 --headed
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=pc06a2 run-code "$(< gui/test/pc06a2CalibrationStatusTruth.browser.js)" | tee /tmp/pc06a2-status.anIJw7/green-committed.txt
! rg -q '^### Error' /tmp/pc06a2-status.anIJw7/green-committed.txt
```

wrapper 路径是本工作站路径，其他机器可用可用的 `playwright-cli -s=pc06a2 run-code` 执行同一 async page 用例；必须先建立下述全 Mock 隔离环境。CLI 的 `run-code` 在断言报错时也可能返回进程 exit 0，故 RED 以 `### Error` 和具体错误文本判定，GREEN 另检查无 `### Error`，不能只读 CLI exit code。

初始 RED 与最终变异 RED 各自的完整错误输出相同：

```text
### Error
Error: 无证据仍展示 TRP 精度
```

最终 GREEN 的返回包含以下验收结果，并附顶部/概览真实 DOM 文本与全部页面 calibration 请求：

```json
{"checks":["四项未知","无固定成果","移除示例状态挂载","旧入口保留"],"formal_acceptance":false}
```

GUI 相关命令（cwd=`gui`）：

```bash
npx --yes tsx --test test/pc01aCalibrationScope.test.ts test/pc04a2RouteCalibration.test.ts
npm run build
```

测试结尾原文：

```text
ℹ tests 9
ℹ suites 0
ℹ pass 9
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 140.115542
```

没有跑全后端：本片纯 GUI 展示删除，无后端/schema/资格改动；后端仅作为真实浏览器数据环境。核心保护是实际 DOM RED/GREEN/变异，不把辅助源码测试当作浏览器验收。

## 真实 API、隔离配置与请求边界

先确认端口 18089 / 5189 空闲；由 `mktemp -d /tmp/pc06a2-status.XXXXXX` 创建本次独立目录 `/tmp/pc06a2-status.anIJw7`，不使用、迁移或清理用户库。SQLite 为该目录的 `browser.db`，日志在 `logs/`；默认 bootstrap 初始化新库。后端在 `api-service` 独立 PTY 启动：

```bash
env USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc06a2-status.anIJw7/browser.db BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc06a2-status.anIJw7/logs .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18089
```

启动日志证明全局 mode=mock、7/7 Mock 驱动；该 status 不是唯一隔离依据，另核验新库、显式 env 和空仪器绑定。新库原 lab-profiles 与 certificate 均空；仅通过真实 POST `/chambers`、`/lab-profiles` 创建两项测试配置（payload/完整初始化代码见本片计划 Task 2 Step 5），没有创建校准/证书/采集记录，也没有伪造 HTTP 响应。

| LabProfile | 实际 ID | 绑定暗室 ID |
| --- | --- | --- |
| PC06A2状态测试甲 | `bf1dd958-4256-4ddc-b238-ba45f3169ba2` | `e9bdf66c-6c61-479d-a182-566549e165b0` |
| PC06A2状态测试乙 | `018d4231-b729-4c0d-be1a-714312f11407` | `4e8206f3-524c-497e-9dab-324c290769b8` |

POST/列表返回摘要不含 instrument_bindings；用 `sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)` 查询 `lab_profiles` 实际列，创建后和最终复核均恰好两行且 `json.loads(instrument_bindings) == []`。最终 24 张含 calibration 名称的表逐表计数全零，证书再次读取为 HTTP 200 空数组。

Vite 临时配置 `/tmp/pc06a2-status.anIJw7/vite.config.mjs` 导入本工作树 `gui/node_modules` 的 Vite/React 插件，root 指向本工作树 gui，保留 Plotly alias 和 `/api/v1/ota` 原代理，只把 `/api` 与 `/api/v1/ws` 目标改为 18089。未改仓库配置。启动命令：

```bash
gui/node_modules/.bin/vite --configLoader native --config /tmp/pc06a2-status.anIJw7/vite.config.mjs --host 127.0.0.1 --port 5189 --strictPort
```

本次临时配置原文（复跑须把工作树路径换成实际 checkout，并为证据重新创建独立临时目录）：

```javascript
import { defineConfig } from '/Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/gui/node_modules/vite/dist/node/index.js';
import react from '/Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/gui/node_modules/@vitejs/plugin-react/dist/index.js';
export default defineConfig({
  root: '/Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/gui',
  plugins: [react()],
  resolve: { alias: { 'plotly.js/dist/plotly': 'plotly.js-dist-min' } },
  server: { proxy: {
    '/api/v1/ws': { target: 'http://127.0.0.1:18089', ws: true, changeOrigin: true, secure: false },
    '/api/v1/ota': { target: 'http://localhost:8001', changeOrigin: true },
    '/api': { target: 'http://127.0.0.1:18089', changeOrigin: true },
  } },
});
```

默认 bundle loader 首次报 `Missing "./internal" specifier in "vite" package`，用 native loader 后正常；最初浏览器早于服务就绪的 ERR_CONNECTION_REFUSED 不计为功能 RED。实际版本 Node v26.5.1、npm 11.17.0、playwright-cli 0.1.22、Vite 7.3.0。临时配置原文随本地证据保留。

页面只观察到既有 GET `/calibration/baseline/status/{chamberId}`，没有新增 stats/history/certificate 查询去推导四项；真实 200 响应与离线失败见 `calibration-requests-final.txt`、`requests.txt`、`logs/app.log`/`audit.log`。测试主动调用的 certificate GET 是隔离前置/收尾核验，不是首页数据源。未点击 quick、drift 或向导开始执行，未触发真实硬件操作。

离线通过 `playwright-cli -s=pc06a2 network-state-set offline` 后只点既有基线“刷新”，等到真实 requestfailed，再检查顶部/概览；不是 route.fulfill。恢复 online 后重跑 GREEN。

## 证据位置、审查及未完成范围

原输出、DB、日志、临时配置和截图均保留在 `/tmp/pc06a2-status.anIJw7/`，截图有 `red.png`、`green-a.png`、`switch-refresh.png`、`summary-final.png`、`overview-final.png`、`offline.png`。断言限定顶部/当前概览，不拿隐藏 Tab 文本污染结果。SDD 完整过程报告仍在本地 `.superpowers/sdd/2026-10-25-pc06a2-1-calibration-status-truth/task-1-report.md`，本摘要已包含团队理解结论所需证据，不要求访问个人 memory 或 scratch。**这些本地大证据不是 Git 附件或永久共享存储**；本次只归档摘要，不提交 scratch、DB、截图、用户 `.venv` 或既有 output。

任务级独立审查覆盖 `e89d1bc6..0740620c` 并核验原证据，规格符合、质量 Approved、未报缺陷；本次纯文档增量和累计整片内审尚待主代理安排。`git diff --check` 已通过功能提交；本文文档增量另做 diff-check，不借此宣称外审完成。

明确未完成：独立 CalibrationHistory/CertificateViewer 的演示数据、向导及 fallback 方法审计、真实历史/证书读取、唯一拓扑工作台入口与 LabProfile 上下文整合、PC-04A-3 编辑完整性。保留的 Baseline 网络错误呈现和跨实验室竞态没有被本片全面验收。PC-06A-2 整项、现场 B、正式计量/认证、PC-09/10 HOLD 均不因此解除。软件 Mock 与“首页未知”不证明任何实测精度或整套校准能力。

本次隔离前后端 PTY 与独立浏览器会话已经关闭，未杀用户服务；新库和原始证据未删除。后续按 WIP=1 完成整片内审、Ready PR、R1/R2 与合并收口，才续接下一片。
