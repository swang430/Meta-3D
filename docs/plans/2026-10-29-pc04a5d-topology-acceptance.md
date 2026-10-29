# PC-04A-5d：可恢复拓扑库与独立 PA 综合软件验收计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在全新隔离 SQLite/Mock 环境把已经交付的拓扑库、修订恢复及独立 PA 串成可复现的真实 API/浏览器旅程，并交付不会误导用户修改原图、激活副本或套用校准的操作指南。

**Architecture:** 只新增本片验收文件和指南，不预设生产修复。真实 HTTP 写入后同时核 ORM 原始 JSON、不可变修订和正式消费者；真实浏览器只连本片隔离 API。32 路 CAICT 完整图与可采集/confirmed 的小型声明图分开，不能把一个图的成功移植给另一个图。

**Tech Stack:** 既有 FastAPI、SQLAlchemy、pytest、ReactFlow、Vite、tsx、Playwright；不新增依赖、不改共享 fixture。

**Spec:** `docs/design/2026-10-27-topology-library-pa-recovery.md`（用户已批准 5a→5d）；本片为 roadmap `PC-04A-5d`。基线 `285cd4a96575471d3aac4e79eb088f66f03eda16`，分支 `codex/pc04a5d-topology-acceptance`。

## Global Constraints

- 本文件是计划，勾选前不宣称已执行。既有功能验收可直接 GREEN；只有真实产品故障才走 RED→最小修复→GREEN，不倒退生产代码制造 RED。
- WIP=1；不重开 4a～4e，不新增自动激活、跨浏览器默认、执行绑定重构、删除入口或通用迁移机制。发现真实功能故障先报主任务，获最小范围裁决才实施。
- 所有写验收使用本片新临时 SQLite；环境必须先于任何 app 导入。bootstrap 后重新设置、回读全部类别及所有 Lab bindings 为 Mock，非空绑定、端点 `192.0.2.10`；实际 HAL 用 `is_mock_driver()` 逐个核验并 shutdown。每个后增 Lab 同样核验。
- 不连接默认 PostgreSQL，不访问用户 API 8000/Vite 5173，不停止或重启用户服务，不改原 CAICT `87df2355-00f2-4fd6-9a38-ebacb2ccb2e5` 或用户已落地 PA 副本 `f5883b11-f7ae-462c-acb1-a42062e51711`。本片 UUID 必须来自新 manifest，不把这两个用户 UUID 当请求参数。
- 只读取已跟踪 `api-service/tests/fixtures/pc04a5c_caict_source.json`，纯 JSON 转换复用 `api-service/scripts/pc04a5c_independent_pa.py::build_candidate(source)`；不重新导出或改用户图。原 fixture 和模板不改，生成 candidate/manifest 只落本片证据目录。
- 复制必须走真实 copy→PATCH；不得 ORM 直造最终 PA 副本。只有明确注明的 legacy 原始 r0 和 synthetic 已存历史样本可用 ORM 播种，不能把它们称作新采集或正式资格。
- unknown 保持 null/缺键，0 与未知分开。旧 20 dB 仅来源未核的标称；旧 0.8 dB/5 m 只留档，不分摊；两新边损耗 null、长度缺键。PA 不是线缆 owner。
- 全 Mock 采集不能产生 confirmed 正例。不得切 real、修改 `is_mock_driver`、替换资格函数或伪造 API 响应造绿。现有 `real_capture` fixture 会修改 binding/category 为 real，本片新相关集不调用它。
- confirmed 正例使用明确标注 synthetic 的**已存** ORM 历史输入，经真实恢复/冻结/补偿消费者验证一次消费；其 DTO 所需 `measurement_provenance='real'` 只是历史模型输入，不是本片新实测。单列此证据层；Mock 采集另验拒采用及生命周期，不冒充真实采集资格验证。
- 真实鼠标拖节点、拖端口、点击表单；不调用 React handler/store 或用 PATCH 冒充鼠标连线。可以第二客户端真实 HTTP 制造并发；网络故障只 abort 或延迟原样真实响应，禁止改 response body/status。
- 真实在途 start/cancel、终态未知、释放后重入至少两轮，run ID 不同；Mock 终态仅软件释放，不证明真实停发、cleanup 或 F64 control release。现场 B/HOLD 保持。
- 截图/日志用 `case + attempt + stage` 唯一名；首次失败原件保留，不覆盖，不清理旧 output/DB/venv。应用源码、共享 fixture、schema、依赖及环境配置默认零改动。
- 验证按 `CLAUDE.md` 输入变化分档。Task 1/2 不跑最终全量，Task 3 是唯一条件全量责任位；不能因新增本片独立验收文件、审查身份或文档更新重复全量。旧 5c 的 `8146 passed /17 skipped /3 failed` 只属旧版，不能写成 5d 已跑。
- NotebookLM 不适用：本片不改 HAL/SCPI，不断言仪器语义；软件锁与 Mock 结果不替代厂商/现场证据。

## 1. 文件路由与验收关系全集

### 1.1 计划中的文件变化

| 文件 | 责任与归属 |
|---|---|
| 新增 `api-service/tests/pc04a5d_browser_fixture.py` | 本片独立路径检查、bootstrap、Mock 核验与三 Lab/两 chamber 隔离世界；不改 5b/5c 共享 fixture（修） |
| 新增 `api-service/tests/test_pc04a5d_topology_acceptance.py` | 真实 API→raw SQL/修订→正常解析/恢复/冻结/补偿的组合验收及 synthetic 历史输入（修） |
| 新增 `gui/test/pc04a5dTopologyAcceptance.browser.js` | manifest 驱动的真实 DOM/鼠标旅程、原样 HTTP 故障注入与证据返回（修） |
| 新增 `gui/test/pc04a5d.vite.config.ts` | 只供本片，三代理全部指隔离 API，严格端口（修） |
| 新增 `docs/guides/topology-library-recovery.md` | 图选择/复制/恢复/冲突/采集锁及独立 PA 操作指南，链接已有器件指南而不复制全文（修） |
| 新增 `docs/validation/2026-10-29-pc04a5d-topology-acceptance.md` | D01～D12 分支证据、输入复用、失败/未验与进程清单（修） |
| 最小更新 `docs/roadmap-first-call.md`、本计划 checkbox | 只写当前交付状态，不覆盖带日期历史快照或前片 validation（修） |

其余生产文件只读。独立审查若发现需要新增生产机制/文件，先回到主任务裁决，不能把验收片悄悄扩成新功能片。

### 1.2 生产入口 → 权威判据 → 消费者 → 可观察断言

以下路由均带真实 `lab_profile_id`，`{id}` 是 manifest 的隔离 UUID。请求前重新读 revision，不用 `version` 字符串当 token。

| ID | 生产入口和权威判据 | 正式消费者与断言 |
|---|---|---|
| D01 原图保护/复制/改名 | `app/api/switch_topology.py::copy_switch_topology/update_switch_topology`；`topology_revisions.py::cas_revision/raw_snapshot` | copy 201/r1/new UUID/inactive/nondefault，已有两 calibrated 键清 null、缺键不补；raw 保形；源全部列/历史/绑定不变。name-only revision 递增但 `updated_at` 不变，`orchestrate_switch_topology` 仍选原图 |
| D02 浏览器默认≠正式选择 | `TopologyEditor.tsx::savePreference`；`topologyLibraryState.ts` 的 scope preference；`mimo_ota/switch_orchestrator.py::orchestrate_switch_topology` 按 chamber/active/updated_at 选图 | localStorage `meta3d.topology-editor.default.v1:<labId>:<categoryId>` 仅 UUID；同浏览器重载选副本，原图 active/default、绑定、正式 resolver 不变；新浏览器无该偏好，不声称跨浏览器生效 |
| D03 草稿放弃 | `TopologyEditor.tsx::resetToSaved` 及 dirty/busy ref；`OperationalLab/OperationalLabContext.tsx` | dirty 阻切图/category/Lab、命名/复制/恢复；取消确认保留草稿；确认放弃仅回已知保存快照，HTTP 无写、revision 不变，不是历史恢复 |
| D04 合法修订恢复 | `switch_topology.py::_restore_selection/preview_topology_restore/restore_topology`；`topology_revisions.py::restore_candidate/cas_revision` | copy r1→候选 r2→仅位置 r3→预览 r2 零写→明确确认恢复为 r4；当前 raw 等 r2，r1～r3 不变；恢复不改 active/default，不恢复旧 calibrated 数值/采用资格 |
| D05 r1 无声明边界/冲突 | `restore-preview/restore` 白名单候选与当前结构验证；PATCH `expected_revision` | r1 可读但缺 F64/probe ports，两个恢复入口均 422 零写；旧 token 保存/恢复 409，缺 token 422，失败 raw/历史数不变，真实 dirty 草稿不丢 |
| D06 Lab/chamber | `switch_topology.py::_resolve_scope/_load_scoped_topology`；Lab→`resolve_current_chamber` | Lab A/A共享同 chamber 看见同一记录但偏好分开；Lab B 不同 chamber，显式越界 409，不伪称共享 chamber 是数据隔离；甲→乙→甲迟到只读回包不覆盖新选择 |
| D07 完整 32 路 | `build_candidate` manifest；`_build_probe_binding`、`TopologyService.resolve_paths`、`rf_chain_resolver.resolve_rf_chains` | 保留四条 BSE→CE 入边及完整模式，原/副本 32 个 `(ce_port,probe_id,pol)` 全等；B1～B32 和 manifest 两边/pair 一一对应，非只拿输出子图绿色代替整图 |
| D08 unknown/标称 | `declared_rf_routes.resolve_saved_rf_path`、`validate_internal_traversals`、`topology_loss.py`、`TopologyService.get_calibration_matrix` | 每路 CE→PA.in / PA.out→原 probe；PA in/input、out/output、唯一 in→out；两 loss None、长度缺键；path total/末边/compensation None，不将 gain_db=20 加入量值；0 样本仍为 0 |
| D09 鼠标编辑/连线 | `CustomNodes.tsx::withDeclaredPorts` 的真实 Handle；`TopologyEditor.tsx::onConnect/handleSave`；`topologyDraft.ts::addDraftConnection` | 实际拖 PA 坐标及端口产生连线，保存 PATCH→GET→reload→raw 确认 source_pin/target_pin、pair、位置。小型端口练习图单独建，不改变 32 路映射图来凑验收 |
| D10 在途/未知/重入 | `app/api/fixed_route_acquisition.py` start/progress/cancel；`calibration/fixed_route_jobs.py`；`RouteCalibrationPanel.tsx` 与 `beginWork` | 真实 start 202、请求在途锁及 GET 失败未知锁；cancel 未确认不释放，重读真实服务器终态后编辑/保存/第二轮 start 可用；Mock samples 空/net_loss None/formal_eligible false，application-preview 不可采用，确认入口拒绝 |
| D11 confirmed 只一次 | 已存 synthetic `RouteCalibrationApplication/Selection`；`resolve_effective_route_compensation/freeze_execution_route_compensation/read_execution_route_compensation`；`ChannelEngineClient._query_calibration_entries` | 真生产解析得到 `source_kind='confirmed_route'`、精确 28；恢复后仍 28，不加标称 20、两侧线损或旧 embedded 99；消费者 cable_loss=28、probe_gain=0；不调用确认接口制造 synthetic 成功，不称新采集/资格通过 |
| D12 历史冻结不变 | 新建 execution 冻结入口与历史 reader；`frozen_route_identity_error` | 先冻结 E1，copy/rename/restore 后 E1 字节/语义不变；创建 E2 读当前；真实 pin/pair 身份变化使当前旧选择不可用但不回写 E1。原证书、Application、Selection、DiagnosticRun、旧 execution 全列/hash保持 |

## 2. 隔离与证据启动约定

执行者先读 `work resolve` 的 PROJECT/handoff、AGENTS/CLAUDE、spec、本计划与前片 validation/deployment。不要重新 claim/release 另一个执行者持有的主 claim。输出目录由主执行者管理。

### 2.1 新 fixture 必须提供的接口

接口：`checked_path(kind: str) -> Path`（kind 只允许 browser/test/full）、`bootstrap_mock_database(kind: str = 'browser') -> dict`、`seed() -> dict`。

这是要实现的接口签名，不是可运行的函数体。`checked_path` 的完整守卫如下；CLI 默认为 `seed()`，`--bootstrap-only --kind test|full` 仅准备新库。不得让原 5c fixture 接受新前缀来省事。

```python
url = os.environ.get('DATABASE_URL', '')
assert kind in ('browser', 'test', 'full')
assert re.fullmatch(r'sqlite:////tmp/pc04a5d-[A-Za-z0-9]+/' + kind + r'\.sqlite', url), url
path = Path(url.removeprefix('sqlite:///'))
assert path.parent.is_dir() and not path.exists(), path
assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'
# 以上断言全部完成，才允许 from app.main import app 等应用导入。
```

准备流程复用 5c 已审实现的顺序，而非直接调用其路径校验：create_all→bootstrap(true)→所有 category.driver_mode=mock→所有 connection.endpoint=192.0.2.10→所有 Lab 非空 Mock bindings→commit/expire/requery→实际 HAL initialize/is_mock_driver/shutdown。运行服务前后也留一次类别/绑定审计；不得仅核全局 env。

新 manifest 至少包含：database、源码 commit/diff hash、source fixture canonical hash、category UUID、Lab A/A共享/B及 chamber UUID、隔离 raw source UUID、独立 collection/port-exercise 图 UUID、逐项 category/binding Mock 审计、HAL class/is_mock_driver、synthetic 边界、candidate/manifest hash。API 创建的副本 UUID 在后续 receipt 追加，不硬编码旧片 UUID。

### 2.2 准备与启动命令（执行阶段运行，三个终端）

```bash
# 终端一；cwd = 仓库/api-service。每个 test/browser/full 运行单独 mktemp，不删除。
acceptance_dir=$(mktemp -d /tmp/pc04a5d-XXXXXX)
export DATABASE_URL="sqlite:///$acceptance_dir/browser.sqlite"
export USE_MOCK_INSTRUMENTS=true
export BOOTSTRAP_ON_STARTUP=true
export LOG_DIR="$acceptance_dir/logs"
.venv/bin/python -m tests.pc04a5d_browser_fixture > "$acceptance_dir/manifest.json"
# 阅读 manifest 并核上述所有审计项后才启动；端口任何占用都先报告，绝不 kill 用户进程。
lsof -nP -iTCP:18126 -sTCP:LISTEN
lsof -nP -iTCP:18127 -sTCP:LISTEN
BOOTSTRAP_ON_STARTUP=false .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18126
```

`lsof` 无监听时 exit 1 是空闲，不是失败。若占用，统一更改本片 API/GUI/config/manifest，重新检查；不要用默认代理。服务进程 false 只跳重复播种，不复用于 pytest。准备程序失败就停止，不启动半成品库。

```ts
// gui/test/pc04a5d.vite.config.ts 的完整内容
import {defineConfig, mergeConfig} from 'vite';
import base from '../vite.config';
export default mergeConfig(base, defineConfig({server:{host:'127.0.0.1',port:18127,strictPort:true,
  proxy:{'/api/v1/ws':{target:'http://127.0.0.1:18126',ws:true},
    '/api/v1/ota':{target:'http://127.0.0.1:18126'},
    '/api':{target:'http://127.0.0.1:18126'}}}}));
```

```bash
# 终端二；cwd = 仓库/gui
npx --no-install vite --config test/pc04a5d.vite.config.ts
# 终端三；健康和图数据来自本片API，不用默认 /health。
curl --fail http://127.0.0.1:18126/api/v1/health
```

浏览器执行前主执行者必须完整读所选 browser skill。使用该 skill 允许的真实浏览器控制；本仓库 `gui/test/*.browser.js` 只是可复用的 `async page => {}` 旅程函数，不强制跨 skill 调用旧 CLI。脚本输入从 manifest 与 `?stage=D01` 读取，建议 `window` 不写业务状态；只读 DOM/evaluate 或设置操作 Lab 的既有 localStorage 可用，不能通过 evaluate 修改 React 状态或调用 handler。脚本和返回 JSON 分别保存本次 attempt。

每次运行保存命令、stdout/stderr、退出码、UTC、HEAD、tracked/untracked 输入 hash、依赖清单、HTTP 方法/URL/body/status/response、raw SQL/历史前后、DOM断言与截图路径。屏幕证据用 `Dxx-<attempt>-<stage>.png`，异常截图另名 `FAILED`，不覆盖首轮。

## Task 1：真实 API 契约与正式消费者组合验收

**Files:** 新增 `api-service/tests/test_pc04a5d_topology_acceptance.py` 和 `api-service/tests/pc04a5d_browser_fixture.py`。只读上表生产文件、5c转换器及 source fixture；不改 shared tests/fixtures。

**Interfaces:** 消费真实 `POST /api/v1/switch-topologies/{id}/copy`（仅 `{name}`）、`PATCH /api/v1/switch-topologies/{id}`（`expected_revision`）、`POST /api/v1/switch-topologies/{id}/restore-preview` 与 `POST /api/v1/switch-topologies/{id}/restore`（`revision,expected_revision`）、revision list/detail。产出 D01/D04～D08/D11～D12 JSON 证据及供 Task 2 使用的安全 manifest。`seed()` 只播原 r0 和独立小型声明世界；最终副本由接口生成。

- [ ] 1. 写 fixture 与 import 前守卫；API 测试本身使用 pytest `tmp_path` 的新文件库及本片 db/client fixture，无 lifespan 的真实 TestClient 可按 5a dependency override 方式复用，但不用其空 bindings/world 当“全绑定 Mock”证明。每个测试世界在创建后完整审计类别、Lab bindings，空集合不算通过。失败守卫不应 import app，不触默认 DB。
- [ ] 2. 新测试按下列名称实现真实序列；原图全部列、历史全部列、Lab bindings 和四类历史表先后 raw 快照，用 JSON 类型/缺键保持比较，不仅比较 typed GET。全部测试允许首次直接 GREEN。

| 测试名 | 必须完成的可运行序列和断言 |
|---|---|
| `test_d01_copy_rename_keep_source_raw_and_execution_choice` | POST copy→PATCH name-only；copy r1/inactive，rename r2；source全部列/history/bindings全等；name-only updated_at不动，正式resolver ID不变 |
| `test_d04_d05_legal_r2_restores_as_r4_but_r1_rejected_without_writes` | 下面完整copy/restore helper加raw/history逐分支零写比较；过期token409与缺token422另参数化 |
| `test_d06_shared_chamber_not_cross_lab_data_isolation` | A/A共享list/detail同记录；不同chamber B显式越界409，所有失败无写 |
| `test_d07_d08_complete_32_routes_and_unknown_nominal_consumers` | 原完整四输入保留；32组身份/64边/pair全等，所有未知消费与0独立反例 |
| `test_d11_d12_synthetic_saved_confirmation_once_and_history_immutable` | 下述已存历史输入经production restore/freeze/consumer断言28/0，旧freeze不变及身份变化拒采用 |

可直接放入新测试文件的真实写入/恢复核心；调用者提供本片 `audit(topology_id: str) -> dict` 回调，返回当前副本raw/revision/全部历史列的深拷贝，不用response成功代替持久化：

```python
def copy_restore_receipts(client, source_id, lab_id, raw_source, audit):
    from copy import deepcopy
    from scripts.pc04a5c_independent_pa import build_candidate
    root = '/api/v1/switch-topologies'
    scope = {'lab_profile_id': str(lab_id)}
    copied = client.post(f'{root}/{source_id}/copy', params=scope,
                         json={'name':'5d隔离PA演练副本'})
    assert copied.status_code == 201, copied.text
    row = copied.json()
    assert row['revision'] == 1 and row['is_active'] is False and row['is_default'] is False
    url = f"{root}/{row['id']}"
    graph, manifest = build_candidate(raw_source)
    saved = client.patch(url, params=scope, json={'expected_revision':1, **graph})
    assert saved.status_code == 200 and saved.json()['revision'] == 2, saved.text
    for suffix in ('restore-preview', 'restore'):
        before = audit(row['id'])
        rejected = client.post(f'{url}/{suffix}', params=scope,
                               json={'revision':1,'expected_revision':2})
        assert rejected.status_code == 422, rejected.text
        assert audit(row['id']) == before
    changed = deepcopy(graph)
    pa = next(n for n in changed['nodes'] if n['id'] == manifest['routes'][0]['pa_node_id'])
    pa['position']['x'] += 31
    moved = client.patch(url, params=scope, json={'expected_revision':2, **changed})
    assert moved.status_code == 200 and moved.json()['revision'] == 3, moved.text
    before_preview = audit(row['id'])
    preview = client.post(url+'/restore-preview', params=scope,
                          json={'revision':2,'expected_revision':3})
    assert preview.status_code == 200, preview.text
    assert audit(row['id']) == before_preview
    restored = client.post(url+'/restore', params=scope,
                           json={'revision':2,'expected_revision':3})
    assert restored.status_code == 200 and restored.json()['revision'] == 4, restored.text
    return row['id'], graph, manifest
```

D07 使用 `test_pc04a5c_copy_roundtrip.py::full_bindings` 的完整模式方式；DB原图调用 `orchestrate_switch_topology` 与 `resolve_rf_chains` 核正式选择，inactive副本不为获得选图而激活。原/副本完整JSON分别调用 `_build_probe_binding` 与纯 `TopologyService(complete_graph).resolve_paths('mimo_ota')`，32路期望直接比source与manifest集合，不只断言数量。

- [ ] 3. D08 逐路只在**明确标注的输出子图**调用 `resolve_saved_rf_path`/`loss_sources_for_path`/`loss_source_for_terminal`/`TopologyService` 检查 None；原/候选完整模式解析另存证，不拿子图冒充完整模式。首/中/末 B1/B16/B32 UI只抽样，不能代替本步骤32路机器核验。错pin/反pair/缺一边按实际结构校验检查HTTP拒绝后零修订；CE身份冲突允许保存，但必须由正式 `_build_probe_binding` 消费者抛出明确异常拒绝，保存不等于可执行，不宣称HTTP拒绝。0样本在独立小图而非改unknown候选。（2026-10-29主任务裁决C：不在验收片新增生产保存门。）
- [ ] 4. 在独立、已活动的小型声明图创建明确 synthetic 旧 DiagnosticRun/Application/Selection 输入，所有绑定仍 Mock。`selection_snapshot` 必须取真实 `route-calibration-paths` 响应并用 `RouteSelection` 验证；不手拼伪 route digest、不patch qualification/freeze。根据当前 `RouteApplicationRecord` 完整构造：

```python
record = RouteApplicationRecord(
    id=application_id, predecessor_id=None, acquisition_run_id=diagnostic_id,
    selection_snapshot=selection, method='fixed_route_net_loss_v1', frequency_mhz=2595,
    coverage_snapshot={'frequency_mhz':2595,'polarization':selection.polarization,
        'reference_identity_digest':reference_digest,
        'adoption_valid_until':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
        'synthetic_fixture':True},
    reference_snapshot={'synthetic_fixture':True,'identity_description':'5d历史模型输入，非实测'},
    net_loss_db=28,
    adoption_evidence_snapshot={'measurement_provenance':'real','synthetic_fixture':True,
        'boundary':'仅已存confirmed消费者输入；未采集、未核采用资格'},
    operator_confirmed=True, certification_status='unknown',
    confirmed_at=datetime.now(timezone.utc), confirmed_by=None)
```

`application_id/diagnostic_id` 新 uuid4；`reference_digest=sha256(b'PC04A5d synthetic stored reference').hexdigest()`；旧 DiagnosticRun `kind='scpi_sequence'`、`target_name='PC04A5d synthetic stored history'`、`success=False`、`params/sequence_evidence` 显式 synthetic，绝不伪造交换/样本。Application 各 ORM 外键/chain/lab/topology 与 selection 一致，`record=record.model_dump(mode='json')`；Selection 频率/模式/chain/reference/application/version 全部一致；request_payload只写synthetic边界，不声称来自确认API。

用 `factory.build_mimo_ota_test_case` 的真实 configuration 建用例与新 execution，然后直接走 `freeze_execution_route_compensation(db,execution,test_case)`（无硬件I/O），保存 E1；name-only保存→恢复合法旧修订→E2冻结，要求两次 `source_kind='confirmed_route'`、value 28，旧E1不变。再以冻结载荷调用 `ChannelEngineClient._query_calibration_entries(chamber.id,2595e6,chamber,path_loss_calibration=None,route_compensation=freeze)`，只能替换其独立 phase 查询为 `{}`，不替换待验补偿消费者；实际返回对应端口 cable_loss 28、probe_gain 0。若模型输入未进消费者，报失败和原因，不能patch门让其通过。真实 pin/pair 改变后新freeze不再confirmed，旧E1仍不变。

- [ ] 5. Mock真实采集负例使用生产 start/progress/application-preview，核 simulated、空samples、net_loss None、formal_eligible false、不可采用和确认拒绝；不复用 `real_capture`。新相关集仅运行本片及不调用该fixture的 5a/5b/5c契约与loss/identity消费者：

```bash
# cwd api-service；先新mktemp，env先于Python；test.sqlite不得已存在。
acceptance_dir=$(mktemp -d /tmp/pc04a5d-XXXXXX)
export DATABASE_URL="sqlite:///$acceptance_dir/test.sqlite"
export USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true
export LOG_DIR="$acceptance_dir/logs"
.venv/bin/python -m tests.pc04a5d_browser_fixture --bootstrap-only --kind test
.venv/bin/python -m pytest tests/test_pc04a5d_topology_acceptance.py tests/test_pc04a5a_topology_library.py tests/test_pc04a5b_topology_revisions.py tests/test_pc04a5b_topology_restore.py tests/test_pc04a5b_restore_contract.py tests/test_pc04a5c_independent_pa.py tests/test_pc04a5c_copy_roundtrip.py tests/test_pc04a4d_loss_truth.py tests/test_pc04a4c_internal_identity.py -q -k 'not test_confirmed_whole_chain_not_readded_and_history_not_rewritten and not test_confirmed_source_history_projects_own_internal_snapshot_only'
```

测试旧文件中的 memory/tmp_path fixture 不访问默认库；新全局 app DB 同样已bootstrap核Mock。旧5b confirmed/4a2 eligibility/freeze文件不加入该相关命令；前片测试结果只能作背景。2026-10-29执行前核实4d/4c上述两个测试各有两参数例会调用 `real_capture`，原命令漏排除；主任务批准明确deselect共4例，不能写成这四例已通过。

- [ ] 6. 写 task回执（命令/输出/exit/输入/每个分支），自查核心消费者真实命中；独立规格/质量审查后提交本任务。若只新增验收且GREEN，不做无意义的生产回退/变异；若批准新增产品修复或新守门，按仓库规则补核心变异并恢复输入hash。Task1不push、不最终全量。

## Task 2：真实浏览器跨功能旅程与两轮采集锁

**Files:** 新增 `gui/test/pc04a5dTopologyAcceptance.browser.js`、`gui/test/pc04a5d.vite.config.ts`；使用 Task1 新fixture，不改已有 browser 文件来覆写旧证据。

**Interfaces:** 输入 Task1 新 manifest+本片 URL+stage；产出 `{case,attempt,checks,exchanges,shots,error}`。HTTP监听捕获真实请求/响应，SQL审计由单独只读核验完成。浏览器不能伪装 Task1 的 synthetic confirmed 为新采集；其历史显示明确标“synthetic软件示例”。

- [ ] 1. 新建 browser.sqlite 并按 §2 启动，核API/GUI准确PID、命令、端口、DB路径和Mock审计。原图从manifest选中，截图中名称/短ID与请求/SQL一致。开两个真实页面和第二独立浏览器context供并发/偏好核验，不复用旧片hardcoded UUID。
- [ ] 2. 执行以下串行旅程；每个分支保留独立case结果，失败不将整行标通过。

| 旅程 | 真实操作与持久断言 |
|---|---|
| D01/D02 | 原图只读留raw→点击“复制已保存版本为…”（201/r1）→重命名（trim后名/r2）→“设为本浏览器默认编辑图”→reload仍选副本；清洁切回原图仍可选。副本inactive/nondefault，原图全列/历史/绑定/resolver不变；独立context无偏好；同名图区分短ID |
| D03 | 使用D04已合法声明的隔离PA演练副本（主任务2026-10-29载体裁决：原raw副本缺ports，现有严格门不放宽）；属性表单实改标签，观察dirty→尝试库/category/Lab/复制/命名被阻止→放弃确认取消仍dirty→显式确认放弃，网络无写且raw/revision不变。再新改标签并真正保存为后续修订，reload确认不是只改toast；D04 r1～r4原件保留 |
| D04/D05 | 在单独PA演练副本完成copy r1→真实API候选r2（这是准备，不冒称鼠标改接）→r1历史可读/preview422→鼠标拖B1仅位置保存r3→历史选r2预览零写→checkbox二次确认→恢复r4，raw精确等r2；r1～r3快照不改 |
| D05 双页面 | A/B都读同revision；B真实表单形成dirty并截图；A真实命名保存200；B旧token保存409，草稿/输入及“放弃未保存改动”保留。只读“刷新查看服务器最新”不自动采用，取消核对不覆盖；另核旧restore409零写。不要把没有dirty的409算草稿保护通过 |
| D06 | A与A共享同chamber看同图、分别设浏览器默认并reload，偏好各自独立；清洁切B不同chamber再回A，原图不变。延迟真实list/detail回包（route.fetch后等待再原样fulfill），切上下文后迟到回包不夺选择；不得改JSON制造另一Lab结果 |
| D07/D08 | 同一个32路PA副本打开B1/B16/B32 PA及两侧边，分别核20标称来源、in/input、out/output、in→out、两损耗空、无重复旧PA边；把UI抽样与Task1全32路mapping并列；独立raw确认长度仍缺键，输入控件显示0不当落库值 |
| D09 | 独立port-exercise图中真鼠标拖PA坐标、CE输出Handle→PA.in、PA.out→probe输入Handle；保存、reload、SQL和完整path核同一connection/pin/pair。invalid方向尝试不生成可保存合法链。不得用第二客户端PATCH连线代替本旅程 |
| D10 第1轮 | 切独立可采集图，真实选完整通路/填频率2595、功率−30、参考件/接收线缆来源“synthetic非实测”并勾两确认；start请求在途期间编辑/库/Lab/恢复全部锁；响应/GET未知时继续锁，不能finally解锁。恢复网络显式读历史/状态确认终态后恢复编辑，save/reload可用 |
| D10 第2轮 | 新start产生不同run UUID→真实cancel请求在途（只延迟真实响应）→未知保持锁→回读服务器终态→编辑保存→离页再进入重新GET同scope，不能自动重发start/cancel、不能以空历史认定未启动。始终Mock不可采用，不称真实cleanup |
| D11/D12 展示边界 | 可只读查看Task1 synthetic旧历史/冻结原值与identity；不得浏览器切real或点击确认造confirmed成功。与Task1消费者证据关联UUID，不把32路inactive副本的422换成可采集小图的200来声称副本可采集 |

- [ ] 3. D09 端口鼠标操作沿当前 `.react-flow__node[data-id="<nodeId>"] .react-flow__handle[data-handleid="<port>"]` 定位，并按 source/target class筛选；必须由实际DOM确认目标唯一、`boundingBox()`可见。鼠标的最小操作形状如下，不运行React函数：

```js
const a = await sourceHandle.boundingBox(), b = await targetHandle.boundingBox();
if (!a || !b) throw Error('端口不可见，不能把脚本失败算连接通过');
await page.mouse.move(a.x+a.width/2, a.y+a.height/2);
await page.mouse.down();
await page.mouse.move(b.x+b.width/2, b.y+b.height/2, {steps:20});
await page.mouse.up();
await page.getByTestId('topology-save-stage').filter({hasText:'拓扑草稿未保存'}).waitFor();
```

ReactFlow重载可能生成新edge UUID，比较实际新edge的端点/pin而非猜ID。若空间遮挡，先用现有fit/zoom/pan或拖节点使可见，不直接调用 handler。保存请求要核 `source_pin/target_pin` 与当前模式引用，不能只看画面线段。

- [ ] 4. 生命周期故障注入仅允许保留原样真实请求/响应：`route.fetch()` 到服务端后延迟原样 `route.fulfill({response})`，或 abort 当前GET使状态未知；保存“已到服务端”与请求次数。start pending可证API已受理但不是“采集任务仍运行”的证据；还须实际GET观察run running并核真实活动租约，再进行cancel。Mock过快时不能伪造running：先报主任务，允许的最小解决仅是本片测试级Mock/时钟阻塞夹具经真实runner/lease执行，不改生产状态/结果或假API响应。若没取得真实running则该分支明确未验。
- [ ] 5. 明确区别数据库写未知与硬件采集未知：前者组件内unknown/dirty不承诺跨SPA持久草稿，离页回到新GET不自动重试；`beginWork`真实在途跨卸载直到请求落定；采集未知继续保守锁，不能用“导航卸载”当停发。分别实测离页/重入，至少两轮release/run身份不继承。
- [ ] 6. 跑GUI现有相关集和build，日志不覆盖；真实视觉查看关键截图（copy/偏好、r1拒绝、r2恢复、409dirty、共享Lab、三处PA端口、真实连接、两轮未知锁与重入）：

```bash
# cwd gui
npx --no-install tsx --test test/topologyDraft.test.ts test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts
npm run build
```

- [ ] 7. 独立规格/质量审查并提交；若Task3还复核，交接准确PID/DB/端口/浏览器session；否则只停已核身份的本片进程，验证本片端口无监听。保留所有DB/证据，不停止用户8000/5173服务或Docker。

## Task 3：指南、验证摘要与唯一条件全量收口

**Files:** 新增 `docs/guides/topology-library-recovery.md`、`docs/validation/2026-10-29-pc04a5d-topology-acceptance.md`，最小更新 roadmap 和本计划。输入 Task1/2 manifest、逐分支回执/SQL/消费者/截图及其失败原件；不改历史报告。

**Interfaces:** 输出可照真实UI执行的指南、D01～D12“新验/复用/未验/失败”证据矩阵和新片输入责任说明。本任务唯一决定并承担最终全量，不默认转给reviewer。

- [ ] 1. 指南按真实按钮写七段：选Lab/chamber/category和原图短ID；复制已保存图与命名；本浏览器默认≠正式执行选择；“应用”/保存/放弃草稿区别；误保存恢复合法修订和r1缺声明422；409/未知写只读核查及显式采用；独立PA映射/unknown/标称/confirmed一次及采集未知锁。每段包含成功回读、拒绝原因、保守恢复动作；链接 `topology-device-contract.md`，不照旧指南建议修改用户原CAICT。
- [ ] 2. 明确用户落地源/副本只作定位说明；5d没有更新它们。新备份不是本片动作，不重新恢复PG。旧部署回执在 `output/pc04a5c-deployment.md` 为本机资料，远程读者可能不可得，不能提供不存在的公开下载；repo可追溯依据为PR547、5c validation与本片新证据摘要。浏览器截图均为隔离Mock样例，历史synthetic confirmed另列，不能显示“新实测合格”。
- [ ] 3. 摘要逐分支列D01～D12输入、图/run/execution/application UUID、真实HTTP/SQL/DOM/消费者证据、退出码/统计/警告与未验边界；一个case部分通过不整行PASS。保存失败尝试及复验差别；未取得真实running、鼠标连接或消费者source_kind时如实未验并由主任务裁决，不以计划文字补齐。
- [ ] 4. 最终影响分类与输入复用：对BASE→最终diff逐文件标“生产/shared fixture/schema/依赖/生成契约/专用验收/文档”，列命令、环境、依赖与tracked/untracked输入起止hash。若只有本片独立验收文件及文档，跑新相关集+浏览器+GUI/build+受影响文档门，写“本片未跑新版全后端”；旧5c统计仅前片参考，不冒新版全量，也不声称本片全部测试输入与5c相同（新增测试已不同）。可复用仅指逐项证明未变输入的既有结果，明确哪些未重跑。
- [ ] 5. 若获批准的真实bug修复改变共享生产行为、共享fixture、依赖/schema或影响面无法说明，则当前共享输入变化触发**本Task唯一执行者**稳定后新full.sqlite跑一次最终全量；Task1/2与reviewer不重复。由于既有全量包含 `real_capture` 等脚本transport语义fixture，本片全Mock新验收约束不能被偷偷扩大：触发前先报告主任务确认旧测试严格无外部I/O的范围例外，禁止自行解除全局Mock或连接用户仪器。缺确认就保留该最终责任与阻塞，不以相关集冒全量。

```bash
# 只有Step5条件成立且旧suite的脚本transport边界已获主任务确认才执行；cwd api-service。
acceptance_dir=$(mktemp -d /tmp/pc04a5d-XXXXXX)
export DATABASE_URL="sqlite:///$acceptance_dir/full.sqlite"
export USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true
export LOG_DIR="$acceptance_dir/logs"
.venv/bin/python -m tests.pc04a5d_browser_fixture --bootstrap-only --kind full
.venv/bin/python -m pytest tests -q
```

全量后新增文档如果是规则门输入，另跑受影响门，不为文档再跑一遍全量。功能/fixture/配置再次变化则重新判影响；不能只看HEAD相同或不同决定复用。

- [ ] 6. 本计划/指南/摘要作为文档门输入，最终新库单独运行下列门；发现旧失败逐条核BASE与失败位置无diff，不能写“3旧门”然后漏掉本片新失败。失败不改历史或放宽门刷绿。

```bash
# cwd api-service；复用已安全bootstrap的本片test环境，仅非破坏检查。
.venv/bin/python -m pytest tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes tests/test_rule_gates.py::test_g11_docs_cite_live_api_routes_full_domain tests/test_rule_gates.py::test_gitignore_does_not_shadow_tracked_sources -q
git diff --check
```

- [ ] 7. 自查全部路径/接口/链接、事实镜像、禁令及D01～D12覆盖；主任务安排累计独立审查。Ready PR按AGENTS R1→R2，R2无P1收口；仍有P1则修复并续审覆盖最新HEAD直到无P1。R2后P2/P3只报告不自动入池，不把“测试更强”升P1阻塞。push/外审/合并由主任务按授权执行，作者计划阶段不做。
- [ ] 8. 完成时只关闭已核本片进程/浏览器，保留新DB、证据、失败原件和用户服务；主任务更新台账/handoff并release主claim。完成出口是已批准综合软件范围有真实可定位证据+可用指南，不是现场B、真实cleanup、校准认证、正式报告下载或HOLD解除。

## 3. 裁决、风险与自查清单

1. **三任务，不新增功能。** Task1真实API/消费者，Task2真实浏览器旅程，Task3指南/验证责任；专用fixture/config属于验收设施，不因此触发共享生产全量。风险：确有生产bug时需主任务最小裁决，不能隐性扩片。
2. **r1保持422。** 合法恢复只用r2→r3→r2为r4；copy raw不是补声明。风险：不能向用户承诺“任意历史都能恢复”。
3. **confirmed证据分层。** 旧real_capture会将category/binding切real，故不在5d新相关集复跑；改用显式synthetic已存历史，经真实restore/freeze/consumer核28一次。风险：只证明已存输入的消费者语义，不证明新采用资格；若真门没命中必须报失败，不能patch门造绿。
4. **真实在途≠延迟回包。** 两轮running/lease证据与未知客户端锁分开；Mock过快先主任务裁决专用测试阻塞，不能造API running。风险：未得实际running则该分支不能收PASS；软件终态不证明真cleanup。
5. **最终全量按输入。** Task3唯一责任，不复制5c旧8146/17/3当新版；若共享输入不变不重复全量。风险：全量若触发包含旧脚本transport用例，先明确其例外与无外部I/O边界，不能与全Mock新验收混说。

执行前自查：D01～D12每项都有入口/权威源/消费者/断言；所有新文件职责唯一；命令路径真实，默认库/服务无写入；没有自动激活；不会改历史r1；unknown和0分开；截图唯一；指南不把浏览器偏好说成执行选择；先读相关skill才用浏览器；每任务可独立验收并提交。计划编写阶段只做只读源码核实与文档自查，不运行应用、测试或硬件。
