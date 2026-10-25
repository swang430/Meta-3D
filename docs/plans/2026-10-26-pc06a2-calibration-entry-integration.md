# PC06A2 校准入口职责统一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `subagent-driven-development` 按任务实施，两阶段独立审查；步骤用复选框跟踪。用户已选择 SDD，不再询问执行方式。先由主代理安排独立计划审查，通过后才写生产代码。

**Goal:** 系统校准成为管理总入口；新路径测量只在同一 LabProfile 的原射频拓扑中操作，旧记录只读可追溯且不冒充当前正式资格。

**Architecture:** 在 App 现有 section 导航与 OperationalLabProvider 上增加一个回调，不新增路由协议、不复制实验室状态、不复制采集引擎。把旧执行向导收窄为方法说明及拓扑入口；真实旧记录用独立的只读 API 适配器读取，和按 Lab 隔离的拓扑采集历史分区。移除管理页本地演示结果及可达模拟写操作，保留数据库、证书文件和正式消费者原行为。

**Tech Stack:** React 18、TypeScript、Mantine 8、TanStack Query、现有 Axios；FastAPI 真实 API；默认 bootstrap、独立文件 SQLite、全 HAL Mock 浏览器验收。

**Spec:** [总计划 Todo 2](2026-10-25-topology-editor-calibration-consolidation.md)、[拓扑内校准设计](../design/2026-10-24-topology-calibration-integration.md)、[正式队列](../roadmap-first-call.md)。源码基线 `503a5a8d92d2a86845f65471e16bb0577fd33ce7`，分支 `codex/pc06a2-calibration-entry-integration`。

**2026-10-26 交付状态：** Task1/2/3及累计独立内审完成，[PR #537](https://github.com/swang430/Meta-3D/pull/537)于2026-10-25T18:35:05Z合并至 `f632d26c873f0514785946b65c15660a5ead6880`；[R2 回执](https://github.com/swang430/Meta-3D/pull/537#issuecomment-6401459096)于2026-10-25T18:26:56Z覆盖 `805bddca6e`，未发现重大问题。连同首页首片PR #535，PC-06A-2批准软件待办已交付；不关闭PC-06其余范围、现场B或HOLD。综合证据、最终全量 **7485 passed / 17 skipped / 1 failed**（仅G8历史引用误报）及未验边界见[验证摘要](../validation/2026-10-26-pc06a2-entry-integration.md)，不称全绿。下文保留原实施步骤/规划时复选框，当前完成状态以总计划及验证摘要为准。取消Mock无真实释放证明时仍保留既有锁，不为验收修改安全判据。

## 全局约束

- WIP=1；本片不解除 PC-01B～07B、PC-09/10 HOLD，也不完成 PC-05/06/07 其余范围。
- 2026-10-26 规划时，PC06A2-1 已合并 #535 / `b870e91a`；PC04A3 已合并 #536 / `503a5a8d`，R2 [回执 6400170137](https://github.com/swang430/Meta-3D/pull/536#issuecomment-6400170137)覆盖 `e4d639782d`，未发现重大问题。PC-06A-2 父项保持未完成。
- 不把模型演示、Mock、历史缺少 provenance 或缺测值变成真实量值、正式判词或 0；保留原记录值的同时明确“原记录字段，不是当前验证”。
- “系统校准是管理总入口；射频拓扑是路径校准的唯一操作工作台”；不维护第二套路径表单。这里的“唯一”指生产 GUI 的路径操作入口，不宣称删除所有历史 API。
- 跳转只带共享上下文，不伪造已选链、topology_id、route_digest、频率、极化、参考件或自动开关资格；用户到图内按真实候选选择。
- 整条路径只补偿一次，不把整条测量写到任一单段；采用/执行冻结/报告全部复用已合并链，生产代码不在本片修改。
- 配置差异只提醒复核，不自动失效或强制重校准；TRP/TIS、重复性、相位、静区、相对基线与逐路径损耗不是同一种方法。
- 不删除、迁移、补认证或重算旧记录，不生成新证书，不触发会重建 PDF 的旧下载端点。已存在的证书文件保留；新管理页只提供原记录详情，不伪称提供原件下载。
- 参考件/证书信息展示已有字段及缺项；当前没有本片可复用的独立参考件证书注册库，不能做一个假注册表。参考天线、接收线缆来源仍在原拓扑采集表单填写/冻结。
- NotebookLM：本片不改 HAL/SCPI，不断言仪器能力；只据软件调用链标注“本入口无已验证真实方法”，不据此宣称硬件不支持。
- memory 已查询，仅用作历史风险提示；下述事实全部按当前源码复核。团队实施不依赖个人 memory。
- 不动用户未跟踪 `.playwright-cli/`、`.venv`、现有 `output/`；新增证据独立目录保留。初始规划时尚未实施或运行验证；后续实际状态以本文开头及验证摘要为准。

## 最小可交付边界与非目标

一个 PC06A2 功能片，三个可独立审查的任务：① 管理入口/方法职责及同 Lab 跳转；② 旧记录/证书真实只读；③ 真实 API 综合验收与交付记录。① 是最小可观察交付：新建不再执行旧路径/模拟方法，点击后进入现有同 Lab 图；② 消除同一管理面剩余演示历史，不为此新建后端聚合 API。①②完成后统一外审，不并行开下一 PC。

明确不做：旧 POST API 的下线/认证制度改造、全仓 calibrationService fallback 清理、系统证书与 Lab 绑定修复、参考件注册库、证书签发/重新生成/PDF 下载改造、旧数据清洗、通用路由框架、全局导航防丢草稿机制、拓扑自动导入策略、采集/开关/HAL/lease、资格/补偿/冻结/报告逻辑变更。

这些边界不掩盖遗留风险：旧 API 仍可能被外部调用；本片只承诺管理 GUI 不再调用它们。旧数据真实来源不足，不能仅按“它来自数据库”判成实测，也不能把所有旧数据一律写回为 simulated。

## 实际入口、权威源、消费者全集

以下使用稳定函数/token 定位，不用改动后易漂移的行号。核查命令为 `git grep -n -E '<表内 token>' -- gui/src api-service/app api/openapi.yaml`；同名但未挂载的演示组件不算运行入口。

| 入口 → 当前权威事实 | 消费者 | 本片处置及可观察断言 |
|---|---|---|
| `App.tsx::renderSection('systemCalibration')` → `<SystemCalibration />` | 管理入口 | 增加 `onOpenPathCalibration: () => void`，只调用 `payload.setActiveSection('topologyEditor')`；不写 localStorage、不调用 requestLabChange |
| `OperationalLabContext.tsx::useOperationalLab` → selectedLabProfile / chamberId / error | SystemCalibration、TopologyEditor | 同一 provider 是唯一 Lab 真值；loading/error/无 Lab/无暗室时不导航，解释原因；可用时显示 Lab 名与 ID |
| `renderSection('topologyEditor')` → `LabWorkspace` + `TopologyEditor` | 原图、`RouteCalibrationPanel`、`RouteBatchPanel` | 不新增第二个实例；不改默认 operating mode，不强制进入 `calibration` 模式（该模式不加载测试通路候选） |
| `TopologyEditor::getTopologies` → `switchTopologyService`，携带 lab_profile_id | 画布与保存 | 保留原同 Lab 解析及现有空拓扑模板导入；验收先建两套保存拓扑，导航本身不应新增采集/采用 POST；不得写“导航绝无任何配置写请求”误盖既有自动导入 |
| `CalibrationWizard::executeCalibration`，path_loss/uplink_chain/downlink_chain/multi_frequency | 旧独立表单、旧路损 API、强设 validation_pass=true | 整个执行向导替换为方法选择说明；路径类别只指向同一个回调，无请求体、执行 mutation 或伪造已选路由 |
| Wizard TRP/TIS → `calibrationService` → `api/calibration.py::execute_*` 固定 MockInstrumentOrchestrator | 本地 fallback / DB 记录 | 新 GUI 不执行；说明“本入口没有可验证真实 TRP/TIS 测量链”；不移植旧模拟能力 |
| Wizard repeatability/quiet_zone → 后端 `execute_repeatability_test`/`execute_quiet_zone_calibration` 恒 503 | 原向导结果 | 无开始按钮；分别说明历史重复性和 execution_metrics 对齐不是同一判据，静区/相位需独立方法与现场条件 |
| `BaselineCalibrationCard` → baseline/create、quick、drift-check；`RelativeCalibrationService(use_mock=True)`，`_measure_single_channel` 使用随机数 | 管理页快速校准/漂移成功提示 | 收窄为同暗室只读 `get_baseline_status`；移除 POST、推导量值及成功提示。状态只显示原始记录字段，不签当前有效资格 |
| `get_baseline_status` → CalibrationBaseline，按 chamber_id 过滤、只读 | 基线表 | 保留查询；TanStack Query key 含 chamberId，失败不展示上一暗室/上次成功缓存，不用空数组冒充失败 |
| `CalibrationHistory::mockData` | 旧记录 Tab，空操作按钮 | 删除演示数组；用真实 TRP/TIS/repeatability 三类列表，分页、类型切换及原始详情；不显示 API 没返回的 DUT/工程师/频率 |
| `CertificateViewer::mockCertificate` + jsPDF | 固定证书、伪 PDF | 替换为真实列表/详情，原始证书号/日期/参考信息/签名字符串只读；不把“原 overall_pass=true”称作当前系统合格 |
| `calibrationService::fetchCalibrationHistory`/fetchCalibrationStats | 当前无生产调用者；`/history`、`/stats` 无活后端路由 | 不复用、不扩建假端点；保留未挂载兼容代码，不宣称全部 fallback 已修复 |
| calibrationService fetchCertificates/fetchCertificate/downloadCertificatePDF | 当前无生产调用者；类型错误/自动 fallback | 本片新增独立只读适配器，不让生产管理页导入旧 fallback 模块；multiFrequencyCalibration 的类型引用与测试保留，不做无关删除 |
| `api/calibration.py::list_*`，schemas/calibration.py | TRP/TIS/repeatability/certificate 列表、certificate detail | 列表为数组，参数 skip/limit；无 Lab/chamber 过滤，不把全局归档冒充所选 Lab；展示在“旧系统记录（全局、实验室归属未知）”区域 |
| `download_certificate_pdf` | `/certificate/{id}/download` | pdf_path 缺失会生成文件并 commit，不是纯读取；新 GUI 不调用，不改端点，不删除原文件 |
| `CalibrationCertificateService::generate_certificate` | 旧证书写入/计算 | 不调用；不按旧证书列表拼接新证书，不把图内新量值灌入 TRP/TIS |
| `models/calibration.py::RepeatabilityTest` → test_type=execution_metrics，nullable dBm字段、metric_deltas | `report_service.py::ReportComparisonService`、历史列表 | 保留原执行 ID/指标差分；空量值显示未知，不变成 dBm=0、不套 TRP/TIS 判词 |
| `labProfileService::fetchFixedRouteAcquisitions`/fetchRouteCalibrationBatches | 原图采集与批历史 | 管理页只导航去原图看当前 Lab 历史，不复制轮询/取消/采用 UI；甲作业不可出现在乙的路径历史 |
| `api/route_calibration.py::paths/application_preview/confirm_application` → route_calibration 服务 | 原图候选/预览/确认 | 原身份/范围/真实证据判据不变；Mock 不能采用，确认不是认证 |
| `fixed_route_jobs` / `route_batch_jobs` → DiagnosticRun + 父批终态 | 原图恢复、取消、activeWork | 原安全生命周期不改；离页不当停止，返回可恢复，活动期跨 Lab 仍拒绝 |
| `models/lab_profile.py::active_calibration_certificate_id`、TestCase.calibration_certificate_id | `readiness.py`、`test_execution/hydrate.py::build_step_context` | 旧证书有正式消费者；本片不解绑、不改 FK、不重判 readiness，不把管理 UI 的 unknown 写进后端 |
| `route_calibration_freeze.py`、`path_loss_preflight.py`、`path_loss_application.py`、`ChannelEngineClient::_query_calibration_entries`、`executors/measure.py` | 冻结、ASC 实际补偿与测量 | 不改；现有回归证明整条只补偿一次、旧执行不读当前记录、unsupported 保持拒绝 |
| `calibration_traceability.py::build_calibration_traceability` → report_service | 原执行报告生成/读取/重建/下载 | 仍只投影原冻结记录；入口导航/看旧证书不得写执行或改变报告，不另造“证书下载”等价于执行报告的链 |

## 文件责任与接口

所有实施文件均为“修”：不改它，管理页仍有平行执行或不真实档案。无生产后端文件在允许列表。

| 文件 | 责任 |
|---|---|
| `gui/src/App.tsx` | 现有 renderSection 回调连接；不增加浏览器 URL/section 枚举 |
| `gui/src/components/SystemCalibration/index.tsx` | 同 Lab 导航门、方法入口；保留四项未知，Tabs 用 keepMounted=false 避免隐藏档案页提前请求 |
| `gui/src/components/SystemCalibration/CalibrationWizard.tsx` | 保留导出名及 Modal opened/onClose 契约，替换为只读方法选择/拓扑跳转，不保留执行表单 |
| `gui/src/components/SystemCalibration/BaselineCalibrationCard.tsx` | 原基线只读表与错误呈现，去 POST/随机成果消费 |
| `gui/src/components/SystemCalibration/CalibrationHistory.tsx` | 全局旧记录真实读取、分页/详情、未知边界 |
| `gui/src/components/SystemCalibration/CertificateViewer.tsx` | 全局证书档案真实列表/详情，只读；去本地生成 PDF |
| 新增 `gui/src/api/systemCalibrationReadService.ts` | 活只读 API 类型/调用/格式化小函数；与旧写入 fallback 物理隔离，避免无关改造 legacy 模块 |
| 新增 `gui/test/pc06a2LegacyRead.test.ts` | 只读适配器用 Node test + axios-mock-adapter，仅单测替换 HTTP transport |
| 新增 `gui/test/pc06a2EntryIntegration.browser.js` | 真 DOM + 真 API 的入口、方法、Lab隔离及拒绝链 |
| 修改 `gui/test/pc06a2CalibrationStatusTruth.browser.js` | 旧用例标题/方法选择与新增只读请求白名单同步；四项未知等核心不放宽 |
| 新增 `api-service/tests/pc06a2_entry_browser_fixture.py` | 专用新库默认 bootstrap、两 Lab 拓扑、显式旧档案测试行，无资格替身 |
| 新增 `docs/validation/2026-10-26-pc06a2-entry-integration.md` | 执行后记录受测版本、RED/GREEN/变异、原始输出/截图、未验边界；计划阶段不预填通过 |

不新增 API，故 `api/openapi.yaml`、生成类型、mockServer/mockDatabase 无新契约需镜像；这些旧 `/calibration` GET 当前不在受维护 YAML 子集中。适配器必须以活 Pydantic response model 为准，浏览器验证真实序列化；不为本片补全全仓 OpenAPI。

## Task 1：管理页只能导航到原拓扑，独立方法明确不可用

**Files:** 修改 App、SystemCalibration/index、CalibrationWizard、BaselineCalibrationCard；新增浏览器用例与隔离 fixture；同步既有首页行为用例。

**Interfaces:**

```ts
// App renderSection 只传此回调；没有 Lab ID 第二份状态。
<SystemCalibration onOpenPathCalibration={() => payload.setActiveSection('topologyEditor')} />

interface SystemCalibrationProps { onOpenPathCalibration: () => void }
interface CalibrationWizardProps {
  opened: boolean
  onClose: () => void
  onOpenPathCalibration: () => void
  pathUnavailableReason: string | null
}
```

- [ ] **Step 1：写浏览器 RED。** 建立下文隔离环境后，旧代码点击“新建校准”，在对话框“选择校准类型”可达执行流程；断言无旧“开始校准”流程、存在方法边界与唯一拓扑按钮。RED 必须落在旧行为仍存在/新入口缺失，不能把环境启动失败当 RED。测试脚本沿用 `async page => { ... }`：

```js
const ensure = (ok, message) => { if (!ok) throw new Error(message) };
await page.getByRole('tab', {name:'系统校准',exact:true}).click();
await page.getByRole('button',{name:'新建校准',exact:true}).click();
const dialog = page.getByRole('dialog');
ensure(await dialog.getByRole('button',{name:'进入当前实验室射频拓扑',exact:true}).count() === 1,
  '系统校准仍是独立执行向导，没有唯一拓扑入口');
ensure(await dialog.getByRole('button',{name:'开始校准',exact:true}).count() === 0,
  '管理向导仍可执行旧校准');
await dialog.getByText('TRP/TIS：本入口没有可验证真实测量链', {exact:true}).waitFor();
```

- [ ] **Step 2：运行 RED 并归档。** 用实际浏览器会话运行 `gui/test/pc06a2EntryIntegration.browser.js`，记录当前 SHA、无生产修改的 diff、错误/截图；单测不得代替此项。
- [ ] **Step 3：最小生产实现。** SystemCalibration 的 guard 必须同时作用于按钮 disabled 和回调，不在 callback 中切换 Lab。Modal 内容只有下表说明与同一个按钮；点击后调用 callback、关闭 Modal，不执行 request/定时器/通知成功。

```tsx
const lab = useOperationalLab();
const pathUnavailableReason = lab.loading ? '正在加载当前实验室'
  : lab.error ? '当前实验室读取失败'
  : !lab.selectedLabProfileId ? '请先选择当前 LabProfile'
  : !lab.chamberId ? '当前 LabProfile 未绑定暗室' : null;
const openPath = () => {
  if (pathUnavailableReason) return;
  setWizardOpen(false);
  onOpenPathCalibration();
};
// 两处按钮复用 openPath；不另传 labId/routeId，拓扑从同一 provider 读取。
<Button disabled={pathUnavailableReason !== null} onClick={openPath}>
  进入当前实验室射频拓扑
</Button>
```

| 方法文案（实际显示） | 操作 |
|---|---|
| 路径损耗/增益、上下行链、多频点：在当前实验室拓扑核对接线并选择已有通路；只开放该工作台已支持的范围 | 唯一跳转按钮；不是承诺所有上下行路径都已实现 |
| TRP/TIS：本入口没有可验证真实测量链 | 无执行按钮，PC-10 HOLD 不变 |
| 重复性：旧测量入口未开放；执行指标对齐不等于 TRP/TIS 重复性验证 | 无执行按钮，不新增报告导航/报告分析写入 |
| 静区/相位/互耦：需要独立方法和已验证现场条件，路径损耗不能替代 | 无执行按钮，PC-09/10 不变 |
| 相对基线：仅保留原记录查询，不执行旧模拟 quick/drift | 无新建/快速/漂移按钮 |
| 参考件：参考天线/接收线缆来源在原拓扑填写；证书有效性、适用频率和不确定度仍需独立核验 | 不编造参考件已认证或完整证书注册能力 |

BaselineCalibrationCard 去掉 selectedType/frequency/quickResult、POST handlers、green有效判定和结果区，只保留下列查询与原字段表；不改 CalibrationDashboard 原四项未知说明：

```tsx
const { chamberId, error: labError } = useOperationalLab();
const history = useQuery({
  queryKey: ['legacy-calibration-baselines', chamberId],
  enabled: Boolean(chamberId) && !labError,
  retry: false,
  queryFn: async () => {
    const res = await fetch(`/api/v1/calibration/baseline/status/${chamberId}`);
    if (!res.ok) throw new Error(`基线读取失败 (${res.status})`);
    const data = await res.json();
    if (data.chamber_id !== chamberId || !Array.isArray(data.baselines))
      throw new Error('基线响应与当前暗室不一致');
    return data.baselines as BaselineStatus[];
  },
});
// 只在没有 error、paused、fetching 时显示本次成功 rows。
const rows = !labError && !history.isError && !history.isPaused && !history.isFetching
  ? history.data : undefined;
```

表头用“原类型 / 原频率 / 原通道数 / 原截止日期 / 原状态”；状态原样灰色显示，旁注“来源与当前正式资格未知”。刷新失败显示错误，首次成功空数组才是“暂无原基线记录”。不把 `days_remaining` 或 `status=valid` 推导为本系统可用；不写回数据。query key 隔离避免甲响应晚到覆盖乙。

- [ ] **Step 4：GREEN 与边界。** 保存真实请求日志：管理页无 calibration POST；选择甲从管理入口进入图，API getTopologies 和 paths 请求携带甲 ID，图内未选择候选时没有高亮/采集请求；返回系统校准切乙再进入，ID 为乙且无甲图/记录。没有 Lab 或暗室时按钮不可用。原图单路/批次按钮仍在，不复制第二面板。
- [ ] **Step 5：回归既有首页用例。** “新建校准”保留按钮名称，Modal 改为方法说明；Tabs 用 keepMounted=false。该用例顺序打开历史/证书后请求白名单加真实只读 GET `/calibration/(trp|tis|repeatability|certificate)` 和 certificate UUID detail，仍严格拒绝 POST、`/history`、`/stats`、`/download`。四项未知、无固定精度/趋势断言逐字保留。

实施时同步修正 `gui/test/pc06a2CalibrationStatusTruth.browser.js` 的两处旧 `5189`：将 `base` 改为本片已验证隔离 GUI origin `http://127.0.0.1:5190`，并将硬编码 `page.goto('http://127.0.0.1:5189')` 改为 `page.goto(base)`。Task 3 若因端口占用选择其他端口，`base` 使用报告中实际验证过的 GUI origin，其代理必须指向本片隔离 API（默认18090）；前置检查和导航必须共用同一 `base`，不能只替换其中一处。保留原有 HAL 为 Mock、证书 HTTP 200 且空数组的前置断言，不为适配后续档案样本删除或放宽它们：

```js
const base = 'http://127.0.0.1:5190';
const hal = await page.request.get(`${base}/api/v1/instruments/hal/status`);
requireValue(hal.ok() && (await hal.json()).mode === 'mock', '必须使用全 HAL Mock 环境');
const certificate = await page.request.get(`${base}/api/v1/calibration/certificate`);
requireValue(certificate.status() === 200 && (await certificate.json()).length === 0, '隔离库证书必须为空');
await page.goto(base);
```

此回归只在初始 seed 后、`--seed-legacy` 之前的空档案阶段执行。需要重跑时使用新的专用空库，不删除已有档案测试行来满足前置条件；seed后的档案验证由本片集成用例负责。
- [ ] **Step 6：提交可独立验证的任务。** `git add` 仅列本任务文件；`git commit -m "fix: 统一系统校准到同实验室拓扑入口"`。提交前独立规格/质量审查由主代理安排；不得因为一个任务通过就称整片已合并。

## Task 2：旧记录和证书使用真实只读数据，不推导正式资格

**Files:** 新增 systemCalibrationReadService 与对应单测；修改 CalibrationHistory/CertificateViewer；补充同一浏览器用例与 fixture。

**Interfaces:** 适配器只导入 calibrationClient，无 `import.meta.env`、Mock 生成器和任何 post；不导入旧 calibrationService。

```ts
export type LegacyKind = 'trp' | 'tis' | 'repeatability';
export interface LegacyRow {
  id: string; tested_at: string; validation_pass: boolean | null;
  measured_trp_dbm?: number; trp_error_db?: number;
  measured_tis_dbm?: number; tis_error_db?: number;
  absolute_error_db?: number; threshold_db?: number | null; num_probes_used?: number;
  test_type?: string; num_runs?: number; mean_dbm?: number | null;
  std_dev_db?: number | null; coefficient_of_variation?: number | null;
  min_dbm?: number | null; max_dbm?: number | null; range_db?: number | null;
  measurements?: Record<string, unknown>[]; test_case_id?: string | null;
  execution_ids?: string[] | null; metric_deltas?: Record<string, unknown> | null;
}
export interface LegacyCertificateSummary {
  id: string; certificate_number: string; overall_pass: boolean;
  trp_pass: boolean; tis_pass: boolean; repeatability_pass: boolean;
  calibration_date: string; valid_until: string; issued_at: string;
}
export interface LegacyCertificateDetail {
  id: string; certificate_number: string; system_name: string;
  system_serial_number: string | null; system_configuration: Record<string, unknown> | null;
  lab_name: string | null; lab_address: string | null; lab_accreditation: string | null;
  calibration_date: string; valid_until: string; standards: string[] | null;
  trp_error_db: number | null; trp_pass: boolean | null;
  tis_error_db: number | null; tis_pass: boolean | null;
  repeatability_std_dev_db: number | null; repeatability_pass: boolean | null;
  overall_pass: boolean; calibrated_by: string | null; reviewed_by: string | null;
  digital_signature: string | null; issued_at: string;
}
export async function listLegacyCalibrations(kind: LegacyKind, skip = 0, limit = 20): Promise<LegacyRow[]>;
export async function listLegacyCertificates(skip = 0, limit = 20): Promise<LegacyCertificateSummary[]>;
export async function getLegacyCertificate(id: string): Promise<LegacyCertificateDetail>;
export const legacyNumber = (value: number | null | undefined, unit: string): string =>
  typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)} ${unit}` : '未知';
export const legacyVerdict = (value: boolean | null | undefined): string =>
  value === true ? '原记录：通过' : value === false ? '原记录：未通过' : '原记录：未知';
```

- [ ] **Step 1：写 RED transport 单测。** 采用现有 Node `test`、`assert`，新增模块缺失先红，之后还必须用真实页面旧 mock 数据触发浏览器 RED。

```ts
import test from 'node:test';
import assert from 'node:assert/strict';
import MockAdapter from 'axios-mock-adapter';
import calibrationClient from '../src/api/calibrationClient';
import { listLegacyCalibrations, listLegacyCertificates, getLegacyCertificate,
  legacyNumber, legacyVerdict } from '../src/api/systemCalibrationReadService';

test('真实数组契约、skip分页与失败不fallback', async () => {
  const mock = new MockAdapter(calibrationClient);
  try {
    mock.onGet('/calibration/trp', {params:{skip:20,limit:20}}).reply(200, []);
    assert.deepEqual(await listLegacyCalibrations('trp',20,20), []);
    mock.onGet('/calibration/certificate', {params:{skip:0,limit:20}}).reply(200, []);
    assert.deepEqual(await listLegacyCertificates(), []);
    mock.onGet('/calibration/tis').reply(503, {detail:'不可用'});
    await assert.rejects(listLegacyCalibrations('tis'));
    mock.onGet('/calibration/repeatability').reply(200, {items:[]});
    await assert.rejects(listLegacyCalibrations('repeatability'), /数组/);
    mock.onGet('/calibration/certificate/requested').reply(200,{id:'another'});
    await assert.rejects(getLegacyCertificate('requested'), /不一致/);
    assert.equal(mock.history.post.length, 0);
    assert.equal(legacyNumber(null,'dBm'), '未知');
    assert.equal(legacyNumber(0,'dBm'), '0.00 dBm');
    assert.equal(legacyVerdict(null), '原记录：未知');
    assert.equal(legacyVerdict(false), '原记录：未通过');
  } finally { mock.restore(); }
});
```

- [ ] **Step 2：执行 RED。** cwd=gui：`npx --yes tsx --test test/pc06a2LegacyRead.test.ts`；保留实际失败。浏览器旧页面“校准记录”会出现固定 Engineer A/Standard Dipole，空库也非空；断言真实空库无该记录，必须红。
- [ ] **Step 3：实现严格只读适配。** 使用下列代码，定义上表完整接口，不把类型断言当真实 API 验证；浏览器要对照 JSON。非法 envelope 直接抛错，不能返回演示或空数组；详情 ID 不匹配直接抛错。

```ts
import calibrationClient from './calibrationClient';
async function readArray<T>(path: string, skip: number, limit: number): Promise<T[]> {
  const { data } = await calibrationClient.get<unknown>(path, {params:{skip,limit}});
  if (!Array.isArray(data)) throw new Error('旧记录响应应为数组');
  return data as T[];
}
export async function listLegacyCalibrations(kind: LegacyKind, skip=0, limit=20) {
  return readArray<LegacyRow>(`/calibration/${kind}`,skip,limit);
}
export async function listLegacyCertificates(skip=0,limit=20) {
  return readArray<LegacyCertificateSummary>('/calibration/certificate',skip,limit);
}
export async function getLegacyCertificate(id: string) {
  const { data } = await calibrationClient.get<LegacyCertificateDetail>(
    `/calibration/certificate/${encodeURIComponent(id)}`);
  if (!data || data.id !== id) throw new Error('证书响应与所选记录不一致');
  return data;
}
```

- [ ] **Step 4：替换两页 UI。** History 用 type 默认 trp，offset=0，page size=20；key=`['legacy-system-calibration',kind,offset]`，切类型同步 offset=0、selectedId=null；显示当前页“本页 N 条”，不编造 total/全局排序。上一页在 offset=0 禁用，下一页在本页不足20条禁用；满20条允许下一页空页并可返回。检索只按实际返回 ID，不保留假 DUT/工程师搜索。详情用选中当前页原对象 JSON，只读保存来源路径及原ID；不从当前 Lab 补属性。

```tsx
const records = useQuery({queryKey:['legacy-system-calibration',kind,offset],
  queryFn:()=>listLegacyCalibrations(kind,offset,20),retry:false});
const rows = !records.isError && !records.isPaused && !records.isFetching ? records.data : undefined;
// 先渲染 error/paused/loading；只有成功空数组才渲染“暂无旧记录”。
// 每页一直可见，不依赖用户展开详情才看到来源边界：
<Alert color="gray">旧系统记录（全局、实验室归属未知）。仅回放原字段，来源与当前正式资格未知，不计入当前实验室校准状态。</Alert>
```

TRP 用 measured_trp_dbm/trp_error_db，TIS 用 measured_tis_dbm/tis_error_db，repeatability 用 mean_dbm/std_dev_db；`test_type=execution_metrics` 显示“执行指标对齐（非TRP/TIS校准）”，保留 test_case_id/execution_ids/metric_deltas JSON；null 不格式化成0。validation_pass 用 legacyVerdict，全部灰色，不生成新的 passed/failed 状态。

CertificateViewer 同样分页 key=`['legacy-system-certificates',offset]`，详情 key=`['legacy-system-certificate',selectedId]`、enabled=Boolean(selectedId)、retry=false。翻页清 selectedId。详情读取失败/404/paused 时不显示旧详情，原“下载 PDF”、jsPDF、假证书、生成/应用按钮移除；固定显示“仅原记录详情；此入口不生成、认证或下载证书。已有文件未删除”。`overall_pass` 原样前缀“原记录”，过期日期只展示原日期，不另算当前有效/过期资格；签名原字符串不声称验证成功。系统顶部四项仍未知。

- [ ] **Step 5：GREEN、失败与变异。** 单测重跑；浏览器真实空库/seed旧记录/详情返回与DB逐项对照。真正断网再刷新：显示读取失败/离线等待，无演示 fallback、无旧数据冒充当前读取。恢复在线再次成功。变异把只读列表改为本地固定数组，空库/ID断言应红；恢复后核对 diff，再 GREEN。不改真实 DB 为“通过”。
- [ ] **Step 6：提交。** `git add gui/src/api/systemCalibrationReadService.ts gui/src/components/SystemCalibration/CalibrationHistory.tsx gui/src/components/SystemCalibration/CertificateViewer.tsx gui/test/pc06a2LegacyRead.test.ts`，加本任务实际修改的同一 browser/fixture 文件；`git commit -m "fix: 以真实只读档案替换校准演示记录"`。遗留 calibrationService 未挂载 fallback 保持原样；全仓搜索证明新生产页未导入它。

## Task 3：隔离真实 API、生命周期及报告回归

**Files:** 同一 browser/fixture、验证摘要及两份状态文档；不为测试改生产资格或放宽门。

**Interfaces:** 使用现有 `app.main:app`、默认 `run_bootstrap_on_startup(SessionLocal)`、真实 REST 序列化；只替换存储为新临时 SQLite、HAL 为全 Mock。transport fixture 若用于后台单元测试，仅证明软件，不形成现场数据。

- [ ] **Step 1：在任何浏览器 RED 前建立安全环境。** 查空闲端口 18090/5190；占用则记录未使用端口，不杀用户服务。`mktemp -d /tmp/pc06a2-entry-XXXXXX`，把实际路径保存到报告。专用 fixture 在 app 导入前检查：

```python
import os, re, sys
from pathlib import Path
url = os.environ.get('DATABASE_URL', '')
path = Path(url.removeprefix('sqlite:///'))
legacy_mode = sys.argv[1:] == ['--seed-legacy']
if (os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
    or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'
    or not re.fullmatch(r'sqlite:////tmp/pc06a2-entry-[A-Za-z0-9]+/browser.sqlite', url)
    or not path.parent.is_dir() or (not legacy_mode and path.exists())
    or (legacy_mode and not path.is_file())):
    raise RuntimeError('只允许本次mktemp目录的新文件库和全Mock默认bootstrap')
```

fixture 仿 `tests/pc04a3_browser_fixture.py::seed` 的实际构造：Base.metadata.create_all→默认 bootstrap；所有 InstrumentCategory.driver_mode='mock'，所有 Lab bindings.driver_mode='mock'，CE/SA endpoint 仅192.0.2.10/11。保留 bootstrap 目录，不设 BOOTSTRAP_ON_STARTUP=false；将 analyzer 显式选已有 FSVA3000，只作本地 Mock 软件通路。两 Lab/暗室/已保存双路径拓扑按原 fixture 的 nodes/edges/operating_modes 字段创建，命名改为“PC06A2入口甲/乙”；不借用已执行 fixture 的DB，不 monkeypatch route资格、adoption、HAL truth。增加第三个无暗室 Lab 用于禁用入口验收，instrument_bindings=[]。manifest 输出实际 lab_id/chamber_id/topology_id。路径采集场景开始前，在当前甲图通过真实 switch-topologies PATCH 保存 `gui/test/pc04a3TopologyLifecycle.browser.js` 开头的完整正常/空气/参考天线/接收线缆/分析仪接线结构，lab/topology/switch ID 换为本次manifest值；不可拿初始只有正常段的草图冒充完整采集通路。

初次 seed 校准档案表为空以跑真实空库 RED/GREEN。另提供 fixture 的显式 `--seed-legacy` 模式，打开同一本次专用库、API暂停时才调用 `seed_legacy(session)`；再次核验三个Lab名称及所有driver_mode为mock、四张目标表全空，否则拒绝，不运行初始seed或覆盖库。解析器只接受空参数或 `--seed-legacy`，其他参数报错。不调用旧 TRP/TIS/证书生成 POST：

```python
from datetime import datetime
from app.models.calibration import SystemTRPCalibration, SystemTISCalibration, RepeatabilityTest, CalibrationCertificate
def seed_legacy(db):
    now = datetime(2026, 10, 26)
    db.add(SystemTRPCalibration(standard_dut_model='隔离旧TRP',standard_dut_serial='fixture-trp',
        reference_trp_dbm=10,frequency_mhz=3500,measured_trp_dbm=10.2,trp_error_db=.2,
        absolute_error_db=.2,num_probes_used=1,validation_pass=True,threshold_db=.5,tested_at=now))
    db.add(SystemTISCalibration(standard_dut_model='隔离旧TIS',standard_dut_serial='fixture-tis',
        reference_tis_dbm=-90,frequency_mhz=3500,measured_tis_dbm=-88,tis_error_db=2,
        absolute_error_db=2,num_probes_used=1,validation_pass=False,threshold_db=1,tested_at=now))
    db.add(RepeatabilityTest(test_type='execution_metrics',measurements=[],num_runs=2,
        mean_dbm=None,std_dev_db=None,validation_pass=None,metric_deltas={},tested_at=now))
    db.add(CalibrationCertificate(certificate_number='PC06A2-ISOLATED-LEGACY',system_name='隔离旧证书',
        calibration_date=now,valid_until=datetime(2027,10,26),issued_at=now,
        overall_pass=True,trp_pass=True,tis_pass=False,repeatability_pass=False,pdf_path=None))
    db.commit()
```

这一 execution_metrics 行仅测试稀疏历史形态，不冒充实际执行对齐结果；页面也不得补 execution IDs。同一次事务再增加21条不同ID的TRP旧行测试分页（共22条TRP），数值取同一fixture值，序列号分别为fixture-trp-1至fixture-trp-21；保留服务器分页原序，不假设最新在末尾。重复运行拒绝而不是清空；记录 fixture manifest/行数。证书pdf_path=None刻意验证管理页不会生成文件。基线用 `CalibrationBaseline` 创建甲/乙各一行，`chamber_id`来自对应Lab，`calibration_type='path_loss'`，频率分别2595/3500，reference_channel_id=0、reference_value_db=10、delta_matrix={}、total_channels=1、baseline_date=now、valid_until=datetime(2027,10,26)、status='valid'；仅供原字段显示，不是实测证据。

- [ ] **Step 2：启动真实服务与浏览器。** 以下变量仅本任务 shell 设置，`pc06_entry_tmp` 必须是 Step1 实际路径；应用导入前 env 已确定。先运行新 fixture seed，再启动同一个真实 app（不要用旧库）。

```bash
env USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true DATABASE_URL="sqlite:///$pc06_entry_tmp/browser.sqlite" LOG_DIR="$pc06_entry_tmp/logs" .venv/bin/python -m tests.pc06a2_entry_browser_fixture
env USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true DATABASE_URL="sqlite:///$pc06_entry_tmp/browser.sqlite" LOG_DIR="$pc06_entry_tmp/logs" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18090
```

cwd=api-service；启动日志与 `/instruments/hal/status` 同时核验全Mock，另只读SQL核验每类别/绑定不存在real override。临时Vite配置由 apply_patch 写到 `$pc06_entry_tmp/vite.config.mjs`，root/React插件/Plotly alias沿[首片实际配置](../validation/2026-10-25-pc06a2-1-calibration-status-truth.md)；所有 `/api`（含ws/ota）本次统一指向18090或不访问，绝不误连用户8000/8001；根目录启动用 `gui/node_modules/.bin/vite --configLoader native --config "$pc06_entry_tmp/vite.config.mjs" --host 127.0.0.1 --port 5190 --strictPort`。记录实际配置原文。不开启 main.tsx 的 setupMockServer，不用浏览器 route.fulfill。

- [ ] **Step 3：运行各任务 RED/GREEN 与集成矩阵。** 浏览器按既有技能选择真实工具；脚本返回检查名、请求清单、Lab/记录ID与 formal_acceptance:false，截图保留。CLI若把断言错误包装成exit0，必须检查实际错误段，不以exit0冒称通过。

固定顺序：初始空库→确认5190代理指向本次18090隔离API→运行 Task 1 Step 5 的既有首页回归及空库检查→暂停本次API→`--seed-legacy`→恢复同库API→运行旧档案/分页等集成检查。不得在seed之后运行要求空证书的旧用例，也不得沿用其旧5189地址。

| 场景 | 必须观察到的结果 |
|---|---|
| 初始空库管理页、历史/证书 | 四项unknown；三类列表空但成功、非示例；证书空，无生成/下载请求 |
| 甲管理按钮→拓扑，乙同流程，再甲刷新 | 真实 GET 的 lab_profile_id / 返回 topology.chamber_id 与 manifest一致；不伪选路径、不写采集/采用；两个入口是同一原拓扑 |
| 无选择、Lab读取失败、无暗室 | guard拒绝跳转，有原因，不偷偷选择第一个 Lab |
| 旧 TRP/TIS/执行对齐/证书、21条分页 | ID/数值/原判词与真实JSON一致，nullable未知；每页来源/全局归属未知可见，无 DUT/频率字段补造，无新增PDF |
| 真实离线→刷新→恢复 | 明确error/paused，无Mock fallback/旧成功冒新成功，恢复后真实读取 |
| 甲/乙基线快速切换及刷新 | query key按暗室隔离，当前展示频率只属于该暗室；无 quick/drift/create POST，无当前有效资格 |
| 在图中显式选择真实候选后单路Mock采集、离开管理页再返回 | run归属甲，状态simulated，不开放正式采用；离开不当cancel；存在活动作业时跨Lab受原activeWork保护 |
| 在甲结束/取消且服务端终态后切乙 | 乙历史不含甲run；甲重复进入仍见原run，不复制任务/引擎 |
| 原拓扑MIMO批操作 | 在本片browser内复用 `pc06a1Batch.browser.js` 的实际交互方式：按本次真实paths响应的chain_id和2595/3500生成四项，预览、人工确认、取消、恢复；不直接运行旧脚本（它硬要求3驱动、旧Lab名和conn_p0v/h，与本次默认bootstrap及fixed-v/h不同）。不增加真实开关动作或签现场通过 |
| 管理页读档案前后 | 旧校准/证书行、pdf_path、Lab证书FK、RouteCalibrationSelection、TestExecution、报告内容未被管理读取写改；新run仅来自显式原图采集 |

活动期/取消场景可用既有 Mock采集的样本数构造足够可观察窗口；若作业瞬间终止，不把未观察到的活动保护写通过，改用现有后端生命周期回归补证并明确浏览器未观察。

- [ ] **Step 4：运行相关回归与构建。** cwd=gui：

```bash
npx --yes tsx --tsconfig tsconfig.app.json --test test/pc06a2LegacyRead.test.ts test/pc01aCalibrationScope.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts test/topologyDraft.test.ts test/topologyOperationalLabContext.test.ts test/topologyHandleFreeze.test.ts
npm run build
```

cwd=api-service：

```bash
pc06_related_tmp=$(mktemp -d /tmp/pc06a2-related-XXXXXX) && test -d "$pc06_related_tmp" && DATABASE_URL="sqlite:///$pc06_related_tmp/tests.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_jobs.py tests/test_pc06a1_batch_safety.py tests/test_pc07a1_calibration_traceability.py -q
pc06_full_tmp=$(mktemp -d /tmp/pc06a2-full-XXXXXX) && test -d "$pc06_full_tmp" && DATABASE_URL="sqlite:///$pc06_full_tmp/tests.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests -q
```

档位：GUI/API消费新增功能，最终全后端跑一次，由主代理指定一名验证责任人；纯计划阶段不跑。conftest仅保证Mock默认值及独立日志，不保证根DB隔离，所以上述命令每轮显式创建新SQLite并传三项env，不继承浏览器 DATABASE_URL 到全量。旧片“7485 passed/17 skipped/1 failed”是历史结果，不能冒充本片；若G8仍是历史文档误报，记录当前实际输出/基线对照，不能改历史或虚称全绿。涉及任何共享契约/冻结/安全生产变更应停下重新审范围，不能靠加回归默许扩域。

- [ ] **Step 5：核心变异。** 分别临时恢复旧Wizard执行按钮/让回调切到错误section、旧mockData、证书本地假PDF入口；对应行为断言必须红。恢复只用自身补丁，记录恢复前后diff，重跑核心GREEN。后台补偿/报告代码未改，不为本片重复构造新资格门。
- [ ] **Step 6：整理实际证据与交付。** 验证摘要记 commit、未跟踪输入、命令/环境/退出码/结尾、原始请求与截图、DB只读前后比较；明确“软件Mock，非正式计量/现场”。独立内审累计范围通过后 Ready PR，R1/R2及P1-only续审按AGENTS；不开第二WIP。只有合并后可关闭本片软件待办，PC-06及B/HOLD仍保留。关闭本次启动的服务/浏览器，不清证据目录。

## 计划自查与审查交接

- [x] 批准 Todo 2 的入口全集、同 Lab工作台、原图执行/历史复用、独立方法边界、旧记录只读与unknown、报告追溯均有任务/回归；没有以路损替代TRP/TIS。
- [x] 每个后端URL与参数均从活路由核对；没有新增 `/calibration/history`、`/stats`、参考件注册API或假导航URL。
- [x] 更改优先删除旧执行/假展示、换真实只读来源；新增只读模块是为了不把可回退模拟的写服务带入管理读取，不引入新状态机或后端机制。
- [x] 计划状态与历史快照分开；旧计划/验证摘要里当时“未合并”的文字不回写伪造历史。
- [ ] 主代理独立计划审查；核实范围及代码示例，实施前修复本片缺陷。当前没有实施、测试或外审通过声明。
