# PC06A2-1 系统校准首页状态真实性实施计划

> **执行者要求：** 使用 executing-plans 技能逐项实施；步骤以复选框跟踪。先由主代理安排独立计划审查，通过后才实施，不因本计划已提交而跳过审查。

> **2026-10-25 执行状态：** Task 1/2 已按隔离 setup→RED→最小实现→GREEN/变异→剩余验收完成，提交 `0740620c3a95f3d7d4e8fb8a827235fc890d1b18`（实施 BASE `e89d1bc6`）。任务级独立规格符合、质量 Approved、无缺陷；待文档增量累计整片内审及 Ready PR/R1/R2，尚未开 PR、未合并。命令、真实统计、临时 DB 与请求/截图位置见[验证摘要](../validation/2026-10-25-pc06a2-1-calibration-status-truth.md)。下列初始方案/代码示例保留；实际同名 heading 使用 last()，Vite 使用 native config loader，请求白名单包含真实暗室 UUID，详见摘要，不改 App 或放宽核心断言。

**Goal:** 无校准证据时，系统校准首页不再显示写死的有效证书、精度、合格率、趋势、路径校准状态或重校准提示。

**Architecture:** 优先删除错误逻辑，不增加聚合 API、状态机或证据判定器。顶部四项明确显示未知；概览移除固定统计与三套本地示例面板的挂载，保留已有真实 API 基线入口及边界说明。不接入拓扑路径损耗充当 TRP/TIS 验证。

**Tech Stack:** React 18、TypeScript、Mantine 8、Vite；既有真实 FastAPI、临时 SQLite、全 HAL Mock 浏览器验收。

**Spec:** `docs/plans/2026-10-25-topology-editor-calibration-consolidation.md` 的 Todo 2 首项。代码核查基线 `2275ddac`，分支 `codex/pc06a2-calibration-status-truth`。

## 全局约束与四行声明

- 搜索命中：已读 AGENTS 的 Code Review Rules、CLAUDE、总计划；源码明确标注 Dashboard/Timeline/PathLoss 为 Mock；memory 仅提示区分配置、路径校准、正式资格，事实均按当前源码复核。
- 必要性：首次打开系统校准、没有任何真实证书查询，页面仍显示“有效”、固定有效期及精度，并在概览重复输出虚构校准成果。
- 范围：功能仅修改两个现有 GUI 文件，新增一个浏览器行为用例；本计划为交接文件。枚举下表所有站点，本片仅移除首页和概览的固定假状态；历史页、证书页、向导和入口整合明确留给后续范围复核，不宣称已修。
- 爆炸半径：原来无证据仍可能误认已合格 → 修后首页未知且不产生新判决；不改 DB、补偿、报告、冻结、资格、HAL、旧记录或导航目标。
- 不修改用户未跟踪的 `.playwright-cli/`、`api-service/.venv`、`output/` 原文件；新证据使用独立临时目录。
- 本片不涉及仪器语义或 SCPI，NotebookLM 不适用；不可据此断言仪器支持或不支持某方法。
- 未执行的验证不能写“通过”。本文件保留原始实施方案并记录实际勾选进度；已执行的软件验证见摘要，不是真机或认证验收。

## 来源与消费全集（实际源码核查）

| 生产入口/来源 | 权威边界 | 消费者 | 本片处置与可观察断言 |
|---|---|---|---|
| App 的系统校准导航 → SystemCalibration | App 当前分支直接返回该组件 | `index.tsx` 顶部四卡 | 无 API 查询；证书“有效”、日期、TRP/TIS/σ 都是字面量。改为四项未知、无具体截止/精度/标准达标暗示 |
| Dashboard 的 `stats` / `recentTrends` | 本地固定对象，不是测量或证书 | 合格率、精度趋势、重复性表、提醒 | 整段删除；不保留 0%、15次/14次或“改善”等貌似真实的空值替代 |
| PathLossCalibrationCard 的初始 useState | 本地 calibrated=true、32/32、增益、不确定度、频点与日期；刷新仅等待 | Dashboard 中 `<PathLossCalibrationCard />` | 删除 Dashboard 的 import/挂载；组件文件与 index 的兼容导出不动；首页无该示例面板 |
| Timeline 的 `mockEvents` / setTimeout | 无 API | Dashboard 的时间线 | 删除 import/挂载；不把其示例事件算旧真实历史，也不删除其源文件 |
| DependencyGraph 的 `calibrationNodes` | 固定有效/过期/失效，含假重校准提示；不是资格计算器 | Dashboard 的依赖图及统计 | 删除 import/挂载；不增加级联失效机制 |
| BaselineCalibrationCard | 真实 `/calibration/baseline/status/{chamberId}`；暗室来自 useOperationalLab | 概览现有基线表、quick/drift 操作 | 原样保留，不执行写操作；只在外层标明“基线状态不代表系统证书或 TRP/TIS 验证” |
| CalibrationHistory 的 `mockData` | 固定演示记录，无真实历史 API 消费 | 独立“校准记录”Tab | 本片不动、不重算历史；仍有示例记录问题，后续入口/历史整合必须独立处理，不能宣称此 Tab 可信 |
| CertificateViewer 的 `mockCertificate` / jsPDF | 固定证书和本地合成 PDF，无 fetchCertificates | 独立“证书管理”Tab、详情/下载 | 本片不动、不删除真实库中证书；这是后续证书入口真实性问题，不把它作为首页来源 |
| CalibrationWizard | calibrationService 的 TRP/TIS/重复性/静区/多频点，另有直接 fetch 路损/基线 | “新建校准”Modal | 本片不改方法、调用和结果；路径分支强设 validation_pass、服务 fallback 等属于后续方法/入口审计，不顺带修 |
| calibrationService | 默认 auto，若 API 失败会走多项 Mock fallback；含随机值；类型非证据资格 | Wizard；本目录历史和证书组件实际上没有消费相应 fetch 方法 | 本片不调用 fetchCalibrationStats/fetchCertificates/fetchCalibrationHistory 来“补真值”；不修改 fallback 全局策略 |
| 当前后端 `app/api/calibration.py` | GET TRP/TIS/repeatability/certificate 列表；certificate 返回数组。TRP/TIS POST 显式构造 MockInstrumentOrchestrator，重复性/静区 POST 当前拒绝 | 独立历史与证书 API | 数据存在不等于真实来源或适用当前实验室；本片不拿列表条数/平均误差推导系统有效性 |
| 拓扑采集/采用 | fixed-route-acquisitions、route-calibration-applications 是链与通路记录，不是标准 DUT TRP/TIS 证书 | RouteCalibrationPanel、执行冻结/报告 | 完全不改；有实测或模拟路径记录都不能把首页未知变成有效 |

查阅命令：

```bash
git grep -n -E 'SystemCalibration|CalibrationDashboard|PathLossCalibrationCard|CalibrationTimeline|CalibrationDependencyGraph' -- gui/src
git grep -n -E '2026-11-16|trpAccuracy|recentTrends|mockEvents|calibrationNodes|所有校准参数均在标准范围内' -- gui/src/components/SystemCalibration
git grep -n -E 'fetchCalibrationStats|fetchCertificates|fetchCalibrationHistory|ALLOW_FALLBACK' -- gui/src
```

这些命中中，只有顶部及 Dashboard 输出是本片要消除的故障；独立 Tab/向导不是本片宣称修复的消费者。后续不能以“本片已完成”关闭 PC-06A-2 整项。

## 文件责任

| 文件 | 标记 | 改动 |
|---|---|---|
| `gui/src/components/SystemCalibration/index.tsx` | 修 | 四张卡未知；证书无日期、精度无数值或无依据阈值；中性色图标；顶部区域加稳定测试定位 |
| `gui/src/components/SystemCalibration/CalibrationDashboard.tsx` | 修 | 删除固定统计/趋势/全合格提醒和三套示例面板挂载；保留 BaselineCalibrationCard；加入中性边界说明及测试定位 |
| `gui/test/pc06a2CalibrationStatusTruth.browser.js` | 修 | 既有 async page=> 用例风格，真实 DOM、真实 API、离线行为、刷新验证 |

不增加 helper、hook、服务或依赖；不修改 App、calibrationService、任何后端、历史组件、证书组件、向导与拓扑编辑器。若发现必须改这些才可完成上述故障，先报告原因与新范围，不擅自扩展。

## Task 1：同一故障的浏览器 TDD 与最小实现

**Interfaces:** 消费现有 SystemCalibration/CalibrationDashboard 组件和 useOperationalLab 上下文；不改变 props 或 API 类型。产生两个测试容器 `system-calibration-summary`、`system-calibration-overview`；不产生正式判决。

- [x] Step 1：先新增浏览器用例。先用现有“系统校准”导航进入页面，以既有标题/概览 Tab 定位，先断言旧的顶部“有效”及固定精度不再可见（此时必须实际失败，不能只因新 testid 不存在而失败）。用下列行为断言作为核心：

```javascript
async page => {
  const requireValue = (ok, message) => { if (!ok) throw new Error(message) };
  await page.goto('http://127.0.0.1:5189');
  await page.getByRole('tab', { name: '系统校准', exact: true }).click();
  await page.getByRole('heading', { name: '系统校准', exact: true }).waitFor();
  // 旧页面的可见假状态让 RED 失败，而非等待尚不存在的测试标记。
  requireValue(!await page.getByText('±0.12 dB', { exact: true }).first().isVisible(), '无证据仍展示 TRP 精度');
  const summary = page.getByTestId('system-calibration-summary');
  const overview = page.getByTestId('system-calibration-overview');
  requireValue(await summary.getByText('未知', { exact: true }).count() === 4, '四项状态必须未知');
  const text = await summary.innerText();
  requireValue(!/2026-11-16|±\d|σ\s*=|有效期至:/.test(text), '顶部存在无来源数值或日期');
  requireValue(!await summary.getByText('有效', { exact: true }).count(), '证书不得宣称有效');
  const body = await overview.innerText();
  requireValue(!/93\.3|过去 4 个月|所有校准参数均在标准范围内|需重新校准|32\/32|25\.3|30\.1/.test(body), '概览仍有固定成果');
  for (const name of ['TRP 精度趋势', 'TIS 精度趋势', '可重复性趋势', '校准时间线', '校准依赖关系', '路径校准状态 (DL/UL Path Calibration)']) {
    requireValue(!await overview.getByText(name, { exact: true }).count(), `仍挂载示例面板: ${name}`);
  }
  await overview.getByText('基线状态不代表系统证书或 TRP/TIS 验证', { exact: true }).waitFor();
  // Tab 保留仅验证可达，不把这些遗留页面内容当作本片可信状态验收。
  for (const name of ['校准记录', '证书管理', '概览']) {
    await page.getByRole('tab', { name, exact: true }).click();
  }
  await page.getByRole('button', { name: '新建校准', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  await page.keyboard.press('Escape');
  return { checks: ['四项未知', '无固定成果', '移除示例状态挂载', '旧入口保留'], formal_acceptance: false };
}
```

实施时补上请求记录与隔离前置（Task 2）；若导航实际语义不是 tab，以当前 DOM 证据换定位，不能改 App 来迎合用例。

- [x] Step 2：在隔离环境运行该用例并保存 RED 的错误、受测 SHA、命令与截图。旧页面必须因“无证据仍展示 TRP 精度”失败。
- [x] Step 3：修改 index 顶部 Grid，加 `data-testid="system-calibration-summary"`；保留四个原标签，每个值改成 `<Text size="xl" fw={700} mt={4}>未知</Text>`。说明分别为“当前首页未接入可验证的证书来源”“当前首页未接入可验证的 TRP 验证结果”“当前首页未接入可验证的 TIS 验证结果”“当前首页未接入可验证的重复性结果”；图标颜色统一 gray，不使用勾选成功外观。删除日期与三项标准阈值，不以 0 代空。
- [x] Step 4：将 Dashboard 最小化为以下结构，删除全部闲置 import、stats、recentTrends 与旧 JSX；不删除三套子组件源文件，不动 Baseline 实现：

```tsx
import { Alert, Stack } from '@mantine/core';
import { BaselineCalibrationCard } from './BaselineCalibrationCard';

export function CalibrationDashboard() {
  return (
    <Stack gap="md" data-testid="system-calibration-overview">
      <Alert color="gray" title="系统校准状态未知">
        当前首页未接入可验证的系统证书、TRP/TIS 或重复性证据，不展示精度、合格率或趋势。
      </Alert>
      <Alert color="gray" title="方法边界">
        基线状态不代表系统证书或 TRP/TIS 验证
      </Alert>
      <BaselineCalibrationCard />
    </Stack>
  );
}
```

- [x] Step 5：同一浏览器用例 GREEN，保存 DOM 文本与截图；再暂时恢复顶部旧精度验证用例会红，然后恢复实现并重跑 GREEN。变异仅在这两个已认领文件的自有改动中操作，不使用破坏性 checkout。
- [x] Step 6：运行相关现有前端用例与生产构建（cwd=gui）：

```bash
npx --yes tsx --test test/pc01aCalibrationScope.test.ts test/pc04a2RouteCalibration.test.ts
npm run build
```

记录真实结尾统计与 exit code。它们是回归辅助，核心修复保护是上面的实际 DOM 行为测试。

## Task 2：真实 API + 临时 DB + 全 HAL Mock 验收

本片不添加后端测试 fixture 或运行整个后端套件：纯 GUI 删除展示、无 API/schema/资格变更，全后端不是自然验收门。以下后端仅为真实浏览器数据环境，不 mock HTTP 响应。

- [x] Step 1：读取 computer-use / 所选浏览器技能再操作浏览器。先检查 `lsof -nP -iTCP:18089 -sTCP:LISTEN` 与 `lsof -nP -iTCP:5189 -sTCP:LISTEN`；端口被占用则选择另一组空闲端口并同步用例配置，绝不杀用户进程。
- [x] Step 2：`pc06_tmp=$(mktemp -d /tmp/pc06a2-status.XXXXXX)`，记录绝对目录；以此目录隔离 DB、日志与截图。检查 `.venv/bin/python` 是否可执行；用户的未跟踪 venv 是依赖，不删除或重建。
- [x] Step 3：在 api-service 目录用独立 PTY 启动：

```bash
env USE_MOCK_INSTRUMENTS=true DATABASE_URL="sqlite:///$pc06_tmp/browser.db" BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc06_tmp/logs" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18089
```

`pc06_tmp` 必须在该启动 shell 中显式设置为 Step 2 的实际绝对值，不能依赖跨会话变量。SQLite 由现有 init_db/create_all 与 bootstrap 初始化，不迁移用户库。
- [x] Step 4：用 apply_patch 在临时目录写 Vite 配置，导入当前工作树 gui/node_modules 下 Vite 和 React 插件，root 指向本工作树 gui；复制当前 vite 配置的 Plotly alias，仅将 `/api` 和 `/api/v1/ws` 代理目标设为 18089，其他设置保持一致。用 `gui/node_modules/.bin/vite --config <临时配置绝对路径> --host 127.0.0.1 --port 5189 --strictPort` 启动，不改仓库 vite.config.ts。执行者应将临时配置原文放入验证报告以便复跑。
- [x] Step 5：明确建立隔离配置。`app/services/bootstrap/__init__.py::ALL_SEEDERS` 不包含 LabProfile 创建，不能假定新库里已有可选实验室。以下命令在隔离 API 启动后执行，仅创建两个各自绑定测试暗室、空仪器绑定的配置；不复制用户库、不创建校准/证书/采集记录、不增加生产 fixture。Payload 来源是 `app/schemas/chamber.py::ChamberConfigurationCreate` 与 `app/api/lab_profile.py::LabProfileCreateRequest/create_lab_profile`，路由分别为 `/chambers` 和 `/lab-profiles`。

```bash
python3 - "$pc06_tmp/browser.db" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path
from urllib.request import Request, urlopen

db_path = Path(sys.argv[1]).resolve(strict=True)
assert db_path.parent.name.startswith('pc06a2-status.'), '只核验本次临时目录'
base = 'http://127.0.0.1:18089/api/v1'
def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)

assert api('/instruments/hal/status')['mode'] == 'mock'
assert api('/calibration/certificate') == []
assert api('/lab-profiles') == [], '不是全新隔离库，停止且不要清空已有数据'
created = []
for suffix in ('甲', '乙'):
    chamber = api('/chambers', {
        'name': 'PC06A2状态测试暗室' + suffix,
        'chamber_radius_m': 2.0,
        'num_probes': 1,
        'num_rings': 1,
        'has_turntable': False,
        'has_channel_emulator': False,
        'supports_trp': False,
        'supports_tis': False,
        'supports_mimo_ota': False,
    })
    lab = api('/lab-profiles', {
        'name': 'PC06A2状态测试' + suffix,
        'chamber_config_id': chamber['id'],
        'instrument_bindings': [],
        'description': '仅隔离软件状态验收，无仪器或校准证据',
        'is_active': True,
        'created_by': 'pc06a2-browser-validation',
    })
    assert lab['chamber_config_id'] == chamber['id']
    created.append(lab)
assert len(api('/lab-profiles')) == 2
assert api('/calibration/certificate') == []
# POST/GET 返回 LabProfileSummary，没有 instrument_bindings 字段。
# 当前无通用 LabProfile 详情 GET；只读核验本次独立 SQLite 的实际保存值。
with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
    rows = db.execute(
        'SELECT id, name, chamber_config_id, instrument_bindings '
        'FROM lab_profiles ORDER BY name'
    ).fetchall()
assert len(rows) == 2
for lab in created:
    row = next(row for row in rows if row[1] == lab['name'])
    assert row[0].replace('-', '') == lab['id'].replace('-', '')
    assert row[2].replace('-', '') == lab['chamber_config_id'].replace('-', '')
    assert json.loads(row[3]) == [], '隔离配置出现仪器绑定，停止'
print(json.dumps(created, ensure_ascii=False, indent=2))
PY
```

`pc06_tmp` 在执行该命令的 shell 中也须显式设为 Step 2 的实际目录。保存这次实际输出的两个 LabProfile ID/暗室 ID。字段核对：暗室 POST 的字段均在 ChamberConfigurationBase/Create，响应的 id 在 ChamberConfigurationResponse；实验室 POST 字段来自活路由的 LabProfileCreateRequest，响应只使用 LabProfileSummary 的 id/name/chamber_config_id；绑定保存值来自 `app/models/lab_profile.py::LabProfile` 的 `lab_profiles.instrument_bindings` 列，不从摘要猜字段。全 Mock 前提不只看 HAL status：启动命令必须显式 `USE_MOCK_INSTRUMENTS=true`、指向本次新建临时 SQLite，保存启动日志；两个新 LabProfile 的空绑定以以上只读 DB 核验排除其中的 real override，测试只读首页/基线状态，绝不点击 quick、drift 或向导开始执行。若发现请求触发连接/采集、配置含真实端点或库非新库立即停止，不用 status 字段替代这些隔离条件。真实 GET `/calibration/certificate` 必须 200、空数组；禁止调用 TRP/TIS/校准/证书生成 POST 来制造验收样本。
- [x] Step 6：运行 Task 1 用例，补充记录所有 `/calibration/` 请求；首页只允许既有 baseline/status 读取，不得新增 stats/history/certificate 请求来推导四项。截图必须只框首页/当前概览，不用隐藏 Tab 文本污染断言。
- [x] Step 7：在“当前 LabProfile”选择器显式选择 Step 5 创建的“PC06A2状态测试甲”，再切换“PC06A2状态测试乙”后返回甲、刷新；将实际 ID 与 Step 5 输出逐项核对。四项仍未知，无固定数据回潮；当前 API 校准/证书记录数不增加。重新以 Step 5 的 `sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)` 查询同一临时库 `SELECT name, instrument_bindings FROM lab_profiles ORDER BY name`，断言恰好甲乙两行且每行 `json.loads(instrument_bindings) == []`；不从创建/列表摘要读取该字段。仅系统首页的未知状态不依赖实验室，不能据此宣称基线组件全部跨实验室竞态已验收。
- [x] Step 8：用浏览器离线模式造成真实网络失败（不 route.fulfill），在首页检查四项仍未知、没有重新生成数值；恢复在线再刷新。此断言仅针对本片的顶部与新中性概览，不把既有 Baseline 网络错误显示改造偷偷纳入。
- [x] Step 9：回读 certificate 列表仍空；保存请求清单、RED/GREEN/变异输出、截图路径、构建输出和受测 SHA。浏览器结束仅停止本次创建的 PTY 服务，保留证据目录供审查。

## 收口与后续边界

- [x] `git diff --check` 通过，功能提交仅本计划允许的三项功能/测试文件；全仓 grep 已区分遗留独立入口和历史记录，不修改历史文档来制造一致性。
- [x] Task 1/2 独立规格符合、质量 Approved，确认“无证据首页不输出假状态”；遗留证书页、方法扩展、编辑完整性不并入修复。文档收口后的累计整片内审仍待完成。
- [x] 功能提交 `0740620c` 已完成，仅包含两 GUI 与浏览器测试。原提交示例与约束：`git add gui/src/components/SystemCalibration/index.tsx gui/src/components/SystemCalibration/CalibrationDashboard.tsx gui/test/pc06a2CalibrationStatusTruth.browser.js`，`git commit -m "fix: 移除系统校准首页无来源状态"`；最初计划审查阶段未提前提交功能。
- [ ] 按仓库要求推进 Ready PR、R1/R2；R2 无 P1 收口，仍有 P1 则修复后覆盖最新 HEAD 续审。测试建议不扩大为新机制。
- [ ] 本片完成后再做 PC-04A-3 编辑完整性，再做 PC-06A-2 后续入口整合：真实历史/证书读取、方法可用性、唯一拓扑工作台、LabProfile 上下文隔离均另片审查；PC-09/10 HOLD 不解除。

### 计划自查

已枚举首页所有固定状态来源并明确删挂载优先；不将 Mock API 或路径数据冒充系统证书；两处生产代码足以修本片故障，无需后端变更。独立历史/证书/向导的已观察问题明确保留，不能用本片结果宣称整个系统校准已可信。初始计划提交时所有验证尚未执行；现 Task 1/2 已按勾选完成，真实 RED/GREEN/变异、相关 9 测试和 build 证据见本片验证摘要，不引用旧片统计，不宣称全后端、真机或认证验收。
