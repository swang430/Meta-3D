# PC-04A-8 全 Mock 数值校准实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 排除无关上行边对下行校准选路的误挡，并让显式提供的全 Mock 功率样本经生产计算、持久化、界面与演练 CSV 完整对账，始终不能取得正式采用资格。

**Architecture:** 继续使用现有单路采集、批清单、租约及父子最终化，不新建执行引擎。请求增加严格的显式模拟输入，数值计算与真实采集共享；模拟来源独立于状态保存并贯穿读取及采用判据。先做局部选路修复，再后端契约与安全、GUI 录入导出，最后集中验收。

**Tech Stack:** Python / FastAPI / Pydantic v2 / SQLAlchemy；React / TypeScript / Mantine；既有 pytest、Node test、Vite。仅使用已有依赖。

**Spec:** `docs/design/2026-10-30-pc04a8-mock-calibration.md`（用户已确认）。

## 全局约束

- 本片 P1、WIP=1、一个 PR；四任务串行，每任务完成后由主代理安排独立规格与质量审查，再进入下一任务。
- 本文基准为 `codex/pc04a8-mock-calibration`、`7492488b`。本次只编写计划；下面代码、测试和验收均未执行。
- “未提供模拟输入时保留原命令预览兼容行为，不自动生成数值。”
- “缺接收线缆值/来源不计算损耗、不填0。”
- “模拟结果保持simulated与formal_eligible=false，并显式保存模拟输入来源。”
- “cleanup_confirmed与真实释放未知不能补true。”
- “不得通过删除原上行边、改用户器件类型、全局忽略参考节点或硬编码节点ID解决。”
- 不改 HAL 命令或仪器语义；NotebookLM 不适用。若实施发现必须改变真实命令，先报告并重新界定范围。
- 不安装依赖，不改既有 fixture 的实现，不触及默认数据库、用户服务、原 CAICT 或 PA 副本保存内容；不自动部署。
- 新临时 SQLite 的 `DATABASE_URL`、Mock、bootstrap、日志环境必须先于任何 `app` 导入；bootstrap 后重核类别、连接、Lab 绑定和实际 HAL。
- 全后端只在最终稳定测试输入执行一次；任何后续产品/测试输入变化按影响重新判断，不能复用不相同输入的全量。
- 不宣称真机、计量认证、现场清理、B/HOLD 通过。测试/门意见等级遵循 AGENTS 第 0 条。

任务1/2每次开启新的后端验证终端，先执行下列隔离前置，再执行任务中的 pytest 命令。这里复用现有5d bootstrap-only脚本及其路径守卫，目录每次新建，既有fixture源码不改；任务4改用本片专用脚本。不得省略前置直接让 app 读取默认DB。

```bash
cd /Users/simon/.codex/worktrees/restore-editable-topology/MIMO-First/api-service
pc04a8_target_dir=$(mktemp -d /tmp/pc04a5d-XXXXXX)
export DATABASE_URL="sqlite:///$pc04a8_target_dir/test.sqlite"
export USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true AUTH_MODE=disabled
export LOG_DIR="$pc04a8_target_dir/logs"
.venv/bin/python -m tests.pc04a5d_browser_fixture --bootstrap-only --kind test
```

下文 `cd api-service` 表示从仓库根目录执行；已在该目录时不再次嵌套进入。bootstrap输出必须含非空全Mock绑定和运行HAL核验后才运行测试。

## 1. 已核实事实及原图边界

只读证据：`/tmp/pc04a5d-BVAwTu/source-before.json`、`routes.json`、`run.py`、`report.md`。这些是本机证据，不是远程下载地址，不得覆盖。

1. r6 是 120 节点、122 边；正常模式 `mimo_ota` 有 69 条 active connection。`link_antenna` 为 `reference_antenna`，经 `conn_link_antenna_to_base_station_mimo` 接 `baseStation.UL1`。现有 `_route_selections` 尚未定位下行路径，就遍历全部正常边拒绝该类型。
2. `_route_selections` 的参考解析仅调用 `effective('calibration')`。r6 的模式 ID 为 `mimo_ota/siso_trp/siso_tis/passive/calibration_e2e`，没有 `calibration`。生产 `api-service/app` 与 `gui/src` 无 `calibration_e2e` 字面量支持；不得按名字相似增加 alias。
3. r6 的参考器件是 `sgh/link_antenna/fsva3000`，没有 `receive_cable/air_path` 节点；`fsva3000.params` 没有 `instrument_category_id`。校准相关边包含 CE→PA→probe、VNA→SGH、SGH→FSVA，但没有 probe→参考段出边。原图能被列出下行路由，不等于存在完整可冻结参考段；旧解析允许空参考段，不能把该兼容行为当作新真实性证明。
4. 本片仅把禁入判定收窄到 `resolve_saved_rf_path` 返回的下行节点，保留参考遍历、端口/内部通路、CE 物理输出与开关映射检查。原 r6 只做原样导入后的入口/缺项诊断，缺项逐项报告；不补模式、边、端口、仪器 ID 或用户声明。
5. 完整 32×2×5 验收另用明确命名为 synthetic 的独立图，逐路具备显式参考段。它证明软件链，不代表 r6 全流程通过。完成指南须说明原图后续需操作员核实并保存受支持的参考模式、probe→参考→接收线→分析仪接线及分析仪绑定；本片不代做。

复核命令（仓库根目录，均只读）：

```bash
git rev-parse HEAD
rg -n 'effective\(.calibration.|校准参考接线不能|resolve_saved_rf_path' api-service/app/services/calibration/route_calibration.py
rg -n 'calibration_e2e' api-service/app gui/src
jq '[.operating_modes[] | {id, count:(.active_connections|length)}]' /tmp/pc04a5d-BVAwTu/source-before.json
jq '[.connections[] | select(.source|startswith("hprobe"))]' /tmp/pc04a5d-BVAwTu/source-before.json
```

第二条 `rg` 无匹配退出 1 是调查结论，不是兼容证明。

## 2. 生产入口与消费者全集

下表是此次实施关系，不是要求全表改代码。没有实际缺陷的站点只回归，不为凑文件数改写。

| 入口/站点 | 权威值及下游 | 本片处理与可观察断言 |
|---|---|---|
| `services/calibration/route_calibration.py::_route_selections` 三个公开包装 | `resolve_saved_rf_path` 的已选下行节点；独立参考遍历 | 任务1收窄类型禁入；无关上行保留且200，实际穿越参考节点422；全量/individual/explicit三入口同源 |
| `schemas/fixed_route_acquisition.py::FixedRouteRequest` | 单路 POST、批子请求、历史 result.request | 任务2新增 `mock_input`，严格有限数值、禁止可信身份/时间；无输入保持旧预览 |
| `schemas/route_batch.py::BatchPlanRequest/BatchReference` | preview/start、冻结计划、幂等重放 | 任务2新增唯一完整模拟矩阵；仅显式模拟矩阵允许线损/来源 null，旧请求仍须完整 |
| `api/fixed_route_acquisition.py::start/history/progress/cancel` | `fixed_route_jobs`，`FixedRouteRecord` | 不新增路由；真实序列化响应/读取负例回归 |
| `api/route_batch.py::preview/start/history/progress/continue_job/cancel` | `build_batch_plan`、批 job | explicit preview 传当前 HAL；不启动/连接 HAL；旧 preview 仍可零硬件无 HAL；读取保留来源 |
| `services/calibration/route_batch_plan.py::build_batch_plan` | 逐 `(chain_id,frequency_mhz)` 子请求、digest | 任务2映射样本和 expected；任何模拟输入变化改变摘要；完整性在创建 job 前拒绝 |
| `fixed_route_jobs.py::resolve_configuration/start/_execute` | Lab binding、CE binding resolver、实际 `is_mock_driver` | 任务2显式模拟模式零I/O守卫；start、lease前复核覆盖；真实/混合/未知不发命令 |
| `route_batch_jobs.py::start/_execute/_prepare_item` | 冻结计划、当前绑定、每项驱动、人工等待后重读 | 任务2首 lease/首开关动作前检查；每项准备与人工等待后重核，模拟 CE+真实 switch 必拒绝 |
| `fixed_route_acquisition.py::collect_fixed_route` | 传入的 ce/sa、server-frozen request | 任务2消费样本；真实与模拟复用计算；底层也挡 real/mixed；命令 builder 和真实 finally 不改 |
| `fixed_route_jobs.py::_sequence_evidence/build_record_row/save_record_result/record` | DiagnosticRun JSON；单/批共同存读 | 任务2冻结来源和输入；读取 completed 篡改不展示实测；旧记录不迁移/补数；`success` 仅软件完成，不等于正式资格 |
| `fixed_route_evidence.py::check_fixed_route_evidence` | 采用白名单唯一证据检查 | 任务2先拒 `request.mock_input` 或服务器模拟来源；即使 completed、cleanup true、exchange.simulated false 仍拒 |
| `route_calibration.py::evaluate_route_application/confirm_route_application` | check evidence；新量值仅 real | 保留逻辑并生产 API 回归：new_net_loss null、eligible false、确认422、无 application/selection 新行 |
| `route_calibration.py::list_route_applications/_replay` | 不可变历史应用记录 | 不从模拟采集创建应用，不回写旧应用；既有真实采用幂等回归，无需改历史语义 |
| `mimo_ota/route_calibration_freeze.py::resolve_effective_route_compensation/_validate/read_execution_route_compensation` | 已确认应用及冻结来源，非直接读采集 | 正式链仍只接受 real adoption；任务2/4证明模拟记录无法产生 confirmed_route；不得把模拟数值塞旧证书或冻结快照 |
| `mimo_ota` 的 ASC/补偿/报告消费者 | 通过上述正式冻结，非 FixedRouteResult | 回归 `test_pc04a2_route_compensation.py/test_pc04a2_route_freeze.py`；不新增补偿方式，不把 mock expected 当报告KPI |
| `api/diagnostic_run.py::list_diagnostic_runs/get_diagnostic_run` | SequenceEvidence 原封套 | 诊断详情会原样携带模拟来源；无此校准的正式报告导出路由；回归 generic detail 的 UNDETERMINED/模拟标记，不把软件 success 当PASS |
| `services/calibration/fixed_route_method.py` + `schemas/calibration_method.py` | 另一个人工公式预览 | 没有自动采集结果消费，不改；不可用它替代本片生产入口 |
| `hal/rs_fsva.py` | 真实功率样本生产 | 不改；模拟输入在服务层消费，不伪造 SCPI response |
| `api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/types/api.ts` | 四镜像类型契约 | 任务2同步 YAML/生成类型/手写别名；任务3服务函数仍传原请求并校验 lab/run/job identity |
| `gui/src/features/LabWorkspace/fixedRouteDisplay.ts` | 旧实测展示与两处卡片 | 旧 `.loss/.source/.received` 不放行模拟；任务3新增独立 mock 展示结构，明确“模拟演练” |
| `RouteCalibrationPanel.tsx`、`RouteBatchPanel.tsx`、`routeCalibrationState.ts` | 保存图、锁、preview identity、历史/子项 | 任务3输入、CSV校验、结果/历史标记与导出；dirty/busy/unknown/跨对象迟到仍拒绝 |
| `FixedRouteCalibrationCard.tsx`、`FixedRouteAcquisitionCard.tsx` | 老工作台展示/共享表单 | 共享展示保持标记；不新开第二套批入口，旧表单默认不发送 mock_input |
| 新演练 CSV | 只读服务器回存的 FixedRouteRecord | 任务3仅导出明确模拟输入记录，每行模拟标记及 formal_eligible=false；不新增正式报告/证书 |

再次审计命令：

```bash
rg -n 'net_loss_db|sample_std_db|check_fixed_route_evidence|fixed_route_acquisition' api-service/app gui/src
rg -n 'read_execution_route_compensation|route_calibration_freeze|resolve_effective_route_compensation' api-service/app
rg -n '绝不|不许|禁止|must not|别把' api-service/app/services/calibration gui/src/features/TopologyEditor/routeCalibrationState.ts
```

## 3. 文件职责及接口约定

不新建引擎或数据库表。后端只在原 schema/jobs/acquisition/evidence 扩展；GUI 新建一个纯 CSV 模块和一个共用模拟结果组件，避免两面板复制校验/导出。

### 新字段（任务2一次定义，任务3直接消费）

```python
# app/schemas/fixed_route_acquisition.py，Number/Text复用现有别名。
class MockPowerSample(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    source_before_dbm: Number
    received_dbm: Number
    source_after_dbm: Number

class ExplicitMockInput(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    samples: tuple[MockPowerSample, ...] = Field(min_length=2, max_length=10)
    expected_loss_db: Number | None = None

# 加到 FixedRouteRequest；现有 sample_count validator 后再核数量。
mock_input: ExplicitMockInput | None = None

# 加到 FixedRouteResult；服务端设置，禁止客户端请求携带。
simulation_input_source: Literal['operator_supplied_synthetic'] | None = None
```

`FixedRouteSample.host_time` 只由服务端构造，为“演练处理时间”，不是硬件时间。expected 只保存在 request.mock_input，不进入净损耗计算；界面差值为返回 net_loss 减 expected，无 PASS 判词。

```python
# app/schemas/route_batch.py
# 从 app.schemas.fixed_route_acquisition 导入 ExplicitMockInput。
class BatchMockInput(ExplicitMockInput):
    chain_id: Text
    frequency_mhz: Number = Field(gt=0)

# BatchPlanRequest 新字段；None和空tuple不等价，空列表拒绝。
mock_inputs: tuple[BatchMockInput, ...] | None = Field(default=None, min_length=1)

# BatchReference 两字段改为可空；旧模式的强制性移至complete_explicit_matrix。
receive_cable_loss_db: Number | None = None
receive_cable_source: Text | None = None
```

已有 `complete_explicit_matrix` 继续核 references 与所选笛卡尔积严格相等。`mock_inputs is None` 时每个 reference 线损和来源必须非空；显式模拟时仍须每组 reference、天线身份存在，但允许线损或来源缺失，结果保存样本且两项统计为 null。mock_inputs 的键集合必须恰等所选矩阵、无重复，每组样本数等于 sample_count。

```python
# FixedRouteRequest 的新 model_validator(mode='after') 核心：
if self.mock_input is not None and len(self.mock_input.samples) != self.sample_count:
    raise ValueError('模拟样本数必须等于本次sample_count')
return self

# BatchPlanRequest.complete_explicit_matrix 的新增末段：
if self.mock_inputs is None:
    if any(r.receive_cable_loss_db is None or not r.receive_cable_source for r in self.references):
        raise ValueError('普通批采集每个频点必须有线缆损耗与来源')
else:
    mock_keys = [(row.chain_id, row.frequency_mhz) for row in self.mock_inputs]
    if (len(mock_keys) != len(set(mock_keys)) or
        set(mock_keys) != {(chain, frequency) for chain in self.chain_ids for frequency in self.frequencies_mhz} or
        any(len(row.samples) != self.sample_count for row in self.mock_inputs)):
        raise ValueError('显式模拟矩阵须完整唯一，且每组样本数必须一致')
return self
```

客户端不得传 `host_time/simulated/formal_eligible/measurement_provenance/simulation_input_source` 到 mock_input 或样本；`extra='forbid'` 拒绝。`Number` 拒 bool、数字字符串、NaN/Inf；样本数2–10不变。

## 任务1：把参考节点禁入限定到所选下行路径

**Files（均为“修”）:**
- Modify: `api-service/app/services/calibration/route_calibration.py::_route_selections`
- Test: `api-service/tests/test_pc04a2_route_selection.py`

**Interfaces:** 输入/返回不改：`list_route_selections(db, lab_id: UUID, topology_id: UUID, operating_mode: str) -> list[RouteSelection]`，individual 和 explicit 包装继续同源。

- [ ] **1. 写失败测试。** 使用该测试文件已有 `graph/paths/client/configured/db_session` fixture；只改本测试持有的 DB 图，不改 fixture 定义。

```python
def test_unrelated_uplink_reference_does_not_block_selected_downlink(client, configured, graph, db_session):
    nodes = copy.deepcopy(graph.nodes)
    edges = copy.deepcopy(graph.connections)
    modes = copy.deepcopy(graph.operating_modes)
    nodes += [dict(id='link', type='reference_antenna', params={}),
              dict(id='bse', type='bse_port', params={})]
    edges.append(dict(id='uplink', source='link', target='bse', source_pin='rf', target_pin='UL1'))
    modes[0]['active_connections'].append('uplink')
    graph.nodes, graph.connections, graph.operating_modes = nodes, edges, modes
    db_session.commit()
    before = copy.deepcopy((graph.nodes, graph.connections, graph.operating_modes))
    for params in ({}, {'selection_scope':'individual'}):
        response = paths(client, configured, graph, **params)
        assert response.status_code == 200, response.text
        assert response.json()[0]['node_ids'] == ['ce1','pad1','probe1v']
        assert response.json()[0]['calibration_node_ids'] == ['reference1','rx-cable1','sa1']
    assert (graph.nodes, graph.connections, graph.operating_modes) == before

@pytest.mark.parametrize('kind', ['reference_antenna','receive_cable','signal_analyzer','air_path'])
def test_reference_type_on_selected_downlink_still_rejected(client, configured, graph, db_session, kind):
    nodes = copy.deepcopy(graph.nodes)
    nodes[1]['type'] = kind
    graph.nodes = nodes
    db_session.commit()
    assert paths(client, configured, graph).status_code == 422
```

- [ ] **2. RED。** `cd api-service && .venv/bin/python -m pytest tests/test_pc04a2_route_selection.py -q`；新增无关上行正例应因现有422变红，记录实际输出。
- [ ] **3. 最小修复。** 从 `for c in active` 删除节点类型/connection_scope 检查，仅保留 incoming/outgoing 建索引；在 `route_nodes,route_edges=resolve_saved_rf_path(...)` 后、switch_steps 前插入原条件，不改条件本身。

```python
for node in route_nodes:
    if (node.get('params', {}).get('connection_scope') == 'calibration' or
        node.get('type') in ('reference_antenna','receive_cable','signal_analyzer','air_path')):
        raise ValueError('校准参考接线不能作为正常测试通路')
```

- [ ] **4. GREEN 与对称回归。** 运行 `tests/test_pc04a2_route_selection.py tests/test_pc04a4c_internal_routes.py tests/test_pc06a1_batch_plan.py`；补直接 explicit 调用正例并断言 connection_ids 相等。原分支/回路/端口缺损反例继续红于错误输入，不全局放宽正式集合。
- [ ] **5. 核心变异。** 暂恢复全图检查，新无关上行正例应失败；删除新所选检查，非法参考类型测试应失败。每次恢复后 `git diff` 确认仅预期实现，不在变异版提交。
- [ ] **6. 提交并独立审查。**

```bash
git add api-service/app/services/calibration/route_calibration.py api-service/tests/test_pc04a2_route_selection.py
git commit -m "fix: 限定校准参考禁入检查到所选下行路径"
```

任务1不承诺 r6 完整参考段，也不增加 `calibration_e2e` 支持。

## 任务2：显式 Mock 契约、共享计算与全入口安全

**Files（修）:**
- Modify: `api-service/app/schemas/fixed_route_acquisition.py`、`api-service/app/schemas/route_batch.py`
- Modify: `api-service/app/services/calibration/fixed_route_acquisition.py`、`fixed_route_jobs.py`、`fixed_route_evidence.py`、`route_batch_plan.py`、`route_batch_jobs.py`
- Modify: `api-service/app/api/route_batch.py`
- Modify: `api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/types/api.ts`
- Create: `api-service/tests/test_pc04a8_mock_contract.py`、`test_pc04a8_mock_safety.py`
- Test existing: `test_pc_04a_fixed_route_acquisition.py`、`test_pc_04a_fixed_route_api.py`、`test_pc04a2_route_eligibility.py`、`test_pc04a2_route_application.py`、`test_pc04a2_route_freeze.py`、`test_pc06a1_batch_plan.py`、`test_pc06a1_batch_jobs.py`、`test_pc06a1_batch_api.py`、`test_pc06a1_batch_safety.py`

**Interfaces:**
- 消费任务1三种选路；原 jobs/collect 签名保持。
- 新增 `fixed_route_acquisition.calculate_sample_losses(samples: list[FixedRouteSample], receive_cable_loss_db: float | None, receive_cable_source: str | None) -> tuple[float | None, float | None]`。
- 新增 `fixed_route_jobs.require_explicit_mock_context(db: Session, lab_id: UUID, hal, *, switch_steps=()) -> None`，只读，无连接/查询/写硬件。失败抛 `ValueError`。
- 新增 `fixed_route_evidence.has_explicit_mock_input(result: FixedRouteResult) -> bool`；无循环依赖（只消费 schema），jobs/evidence共用。
- 新契约按第3节，不改 result.version 1/2 或记录表；来源是额外字段，不重写旧行。

- [ ] **1. 创建独立数值/契约测试，不改旧 fixture。**

```python
import asyncio
import copy
import math
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.schemas.fixed_route_acquisition import FixedRouteRequest, FixedRouteResult
from app.services.calibration.fixed_route_acquisition import collect_fixed_route
from tests.test_pc_04a_fixed_route_acquisition import request

def mock_payload():
    return dict(samples=[dict(source_before_dbm=-20., received_dbm=-50., source_after_dbm=-18.),
                         dict(source_before_dbm=-22., received_dbm=-52., source_after_dbm=-20.)],
                expected_loss_db=999.)

@pytest.mark.asyncio
@pytest.mark.parametrize('cable,source,want', [(2.,'synthetic cable',29.), (0.,'synthetic zero',31.),
                                             (None,'synthetic cable',None), (2.,None,None)])
async def test_explicit_mock_uses_measured_sample_formula_once(cable,source,want):
    body=request().model_dump()
    body.update(mock_input=mock_payload(), receive_cable_loss_db=cable, receive_cable_source=source)
    value=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),
        request=FixedRouteRequest.model_validate(body),configuration={})
    value=await collect_fixed_route(MockChannelEmulator('ce',{}),MockSignalAnalyzer('sa',{}),
        value,output_port=1,cancel=asyncio.Event())
    assert value.status=='simulated' and value.formal_eligible is False
    assert value.simulation_input_source=='operator_supplied_synthetic'
    assert len(value.samples)==2 and value.net_loss_db==want
    assert value.sample_std_db==(0. if want is not None else None)
    assert value.cleanup_confirmed is None
    assert all(e.simulated and e.response is None for e in value.exchanges)

@pytest.mark.parametrize('value', [True,'-20',float('nan'),float('inf')])
def test_mock_sample_rejects_nonfinite_or_coerced_values(value):
    body=request().model_dump();body['mock_input']=mock_payload()
    body['mock_input']['samples'][0]['source_before_dbm']=value
    with pytest.raises(ValidationError): FixedRouteRequest.model_validate(body)

@pytest.mark.parametrize('field', ['host_time','formal_eligible','measurement_provenance','simulated'])
def test_mock_input_cannot_claim_trusted_identity(field):
    body=request().model_dump();body['mock_input']=mock_payload()
    body['mock_input']['samples'][0][field]=True
    with pytest.raises(ValidationError): FixedRouteRequest.model_validate(body)
```

增加负增益/非零标准差正例：两样本 `(-20,-10,-18)`、`(-22,-14,-20)`，Lrx=2，逐样本损耗 -11/-9，均值 -10、样本标准差 `sqrt(2)`。增加样本数少/多于 sample_count、空矩阵、重复/额外/缺组合的 schema反例，所有用生产模型验证。

- [ ] **2. RED。** `cd api-service && .venv/bin/python -m pytest tests/test_pc04a8_mock_contract.py -q`。当前模型拒绝 mock_input 为 extra；记录该失败，不能先修改旧测试让它接收。
- [ ] **3. 实现第3节 schema 与共享计算。**

```python
def calculate_sample_losses(samples, receive_cable_loss_db, receive_cable_source):
    if receive_cable_loss_db is None or not receive_cable_source:
        return None, None
    losses = [(s.source_before_dbm + s.source_after_dbm) / 2 -
              (s.received_dbm + receive_cable_loss_db) for s in samples]
    return _number(str(statistics.mean(losses))), _number(str(statistics.stdev(losses)))
```

真实分支原公式换成此函数，前后状态/cleanup不动。Mock 分支继续同源命令预览；其后有 mock_input 时逐样本 `check_cancel()`，用 `FixedRouteSample(**sample.model_dump())` 构造服务端时间，设置 simulation_input_source 并调用共享函数，缺线缆追加现有缺项说明。来源在开始消费前设置，部分失败/取消也不丢来源。旧无输入仍 samples=[]、统计 null、原提示。底层在 `try` 内任何命令/锁动作前执行：

```python
if request.mock_input is not None and not (is_mock_driver(ce) and is_mock_driver(sa)):
    raise ValueError('显式模拟样本仅允许全Mock驱动，未操作仪器')
```

不能写入仿真 SCPI response，不能调用 expected 参与计算。异常/取消清空 net_loss 和 sample_std，保留已处理样本及来源，不补 cleanup。

- [ ] **4. 实现服务端全 Mock 零 I/O 守卫。** `require_explicit_mock_context` 按以下固定关系检查，不凭名字或 USE_MOCK_INSTRUMENTS 字符串放行：

```python
lab = db.get(LabProfile, lab_id)
if lab is None or not lab.is_active or not lab.instrument_bindings:
    raise ValueError('显式模拟需要当前实验室的完整Mock绑定')
seen = set()
for binding in lab.instrument_bindings:
    if not isinstance(binding, dict):
        raise ValueError('实验室绑定缺损')
    try:
        category_id = UUID(binding['category_id'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('实验室绑定身份缺损') from exc
    if category_id in seen:
        raise ValueError('实验室绑定重复')
    seen.add(category_id)
    category = db.get(InstrumentCategory, category_id)
    connection = db.query(InstrumentConnection).filter_by(category_id=category_id).one_or_none()
    if (category is None or connection is None or category.driver_mode != 'mock' or
        binding.get('driver_mode') != 'mock' or
        str(category.selected_model_id) != binding.get('instrument_model_id') or
        connection.endpoint != binding.get('connection_endpoint')):
        raise ValueError('显式模拟需要一致的全Mock实验室绑定')
required = {'channelEmulator','signalAnalyzer'} | ({'rfSwitch'} if switch_steps else set())
for key in required:
    category = db.query(InstrumentCategory).filter_by(category_key=key).one_or_none()
    driver = hal.drivers.get(key) if hal is not None else None
    if category is None or not category.is_active or category.id not in seen or not is_mock_driver(driver):
        raise ValueError('显式模拟的参与仪器未获全Mock运行时证明')
for step in switch_steps:
    if step.driver_mode != 'mock' or step.category_id not in seen:
        raise ValueError('显式模拟的开关绑定不是Mock')
```

最终实现同时验证所选 model 行存在且属于 category；以上循环不自动同步任何 binding。`one_or_none` 多行配置异常必须转明确拒绝，不能作为成功。`resolve_configuration` 保留既有CE/SA型号、endpoint、manifest权威检查；仅 request.mock_input 非空调用新守卫。普通真实模式不新增“全Lab必须Mock”限制。

调用站点必须全部接通：

1. `build_batch_plan` 展开完 items 后，explicit mock 时对每项 switch_steps 调守卫；API preview 仅 explicit 分支以 `get_hal_service()` 传入现有运行 HAL，不初始化它；无运行 HAL 返回422，不启动真实仪器。
2. 单路 `resolve_configuration`：start 和 `_execute.validate_before_remote` 均已调用，守卫置于返回之前。
3. 批 start 通过 build + resolve；`_execute.validate` 对每项在 lease 前调守卫（含该项 switch_steps）。
4. `_prepare_item`：人工等待后的现有 SessionLocal 重核块内、`apply_batch_switch_steps` 前调守卫；此时重新读 binding/category/driver，不用预览快照判是否 Mock。
5. `collect_fixed_route` 的参数驱动防线如上。

固定直连不要求不存在的 rfSwitch 驱动；有实际 switch_steps 才要求该参与驱动。所有 Lab 保存 binding 必须显式 Mock，真实/auto/未知声明不允许显式样本模式；不影响旧普通请求对 auto 的现有策略。

- [ ] **5. 将批模拟矩阵按键复制进子请求。**

```python
mock_by_key = {(entry.chain_id, entry.frequency_mhz): entry for entry in request.mock_inputs or ()}
entry = mock_by_key.get((chain, frequency))
mock_input = (ExplicitMockInput(samples=entry.samples, expected_loss_db=entry.expected_loss_db)
              if entry is not None else None)
# 在既有 FixedRouteRequest(...) 构造中传 mock_input=mock_input。
```

请求/计划 model_dump 已参与 digest，复用现有深拷贝规则。不可从 expected 反推样本，不能用下标 zip 联结输入。新增完整矩阵测试，改变任一样本/线缆/expected 后旧 preview_digest 必须拒绝；幂等同键不同模拟数据409。

- [ ] **6. 来源贯穿读取与正式门。**

```python
def has_explicit_mock_input(result):
    return (result.request.mock_input is not None or
            result.simulation_input_source == 'operator_supplied_synthetic')

# check_fixed_route_evidence 的第一道拒绝条件：
if (has_explicit_mock_input(result) or result.status == 'simulated' or
    any(event.simulated for event in result.exchanges)):
    return 'simulated', ['simulated_measurement']
```

`fixed_route_jobs.record` 在解析后、不写DB地将“有显式模拟来源且 status=completed”的读取副本改回 simulated、cleanup_confirmed=None；失败/取消状态保留，来源仍模拟。不得清空来源来通过 schema，不依据 net_loss 形状判断旧记录。以请求 mock_input 或结果来源任一存在为拒绝，二者缺一也不能升级。

测试必须经真实 HTTP 单路开始→结束→DB 改状态为 completed/cleanup true/exchange.simulated false→详情/历史/采用预览→确认采用；断言模拟标记保留、new_net_loss null、确认422、application/selection/旧证书行数不变。然后经 `resolve_effective_route_compensation` 与正式 freeze/read 消费，断言无模拟 run 导出的 confirmed_route。已有真实 `real_capture` 正例必须继续能采用；不重写历史真数据。

- [ ] **7. 安全测试矩阵。** 在新 `test_pc04a8_mock_safety.py` 引用既有 `configured/client/start/finish` fixture，但不修改其实现。真实类仅用脚本 transport；所有硬件入口替换为“调用即 AssertionError”的探针，不能连接实际 endpoint。覆盖：CE real、SA real、混合、驱动缺失、binding缺失/重复/漂移/auto、真实switch、preview后改绑定、人工等待后改驱动、取消后第二次运行、同幂等键重放不生第二条run。每次拒绝同时断言硬件探针调用数0、没有 running 孤儿；采集中取消仍沿既有清理/最终化，不用新守卫阻止必要真实清理。

```python
# 契约正例直接复用生产HTTP helper；两次run证明不残留锁。
from tests.test_pc04a8_mock_contract import mock_payload

def test_http_explicit_mock_two_runs_do_not_gain_adoption(client, configured):
    from tests.test_pc_04a_fixed_route_api import start, finish
    for _ in range(2):
        response = start(client, configured, mock_input=mock_payload())
        assert response.status_code == 202, response.text
        run_id = response.json()['run_id']
        record = finish(client, configured, run_id)
        assert record['result']['net_loss_db'] == 29.
        result = client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}/application-preview')
        assert result.status_code == 200, result.text
        assert result.json()['eligibility']['measurement_provenance'] == 'simulated'
        assert result.json()['new_net_loss_db'] is None
```

- [ ] **8. 四镜像同步。** YAML 的 FixedRouteRequest/Result、BatchPlanRequest/Reference及两个新 schema 同第3节；generated由 `cd gui && npm run openapi:generate` 生成；`api.ts` 加 `ExplicitMockInput/MockPowerSample/BatchMockInput` generated别名，不手写第二份字段。保持已有 services 请求/响应身份校验。
- [ ] **9. GREEN/相关回归。** 执行新两文件及本任务 Files 所列旧测试，另跑 `tests/test_rule_gates.py` 受契约影响门；此时不全后端。核心变异仅暂去掉显式来源门、把 Lrx 加两次、移除首动作前 mock 检查；对应反例分别应失败，恢复核 hash/diff。
- [ ] **10. 提交并独立审查。** 暂存本任务明确文件（包括 generated）后 `git commit -m "feat: 增加全Mock显式校准样本与来源隔离"`。提交说明附实际测试命令、结尾统计、输入版本，不提前写“全量通过”。

## 任务3：界面显式样本、严格 CSV 导入及模拟结果导出

**Files（修）:**
- Modify: `gui/src/features/TopologyEditor/RouteCalibrationPanel.tsx`、`RouteBatchPanel.tsx`、`routeCalibrationState.ts`
- Modify: `gui/src/features/LabWorkspace/fixedRouteDisplay.ts`、`FixedRouteCalibrationCard.tsx`
- Create: `gui/src/features/TopologyEditor/mockCalibrationCsv.ts`、`MockCalibrationResult.tsx`
- Create: `gui/test/pc04a8MockCalibration.test.ts`
- Test: `gui/test/pc04FixedRoute.test.ts`、`gui/test/pc06a1Batch.test.ts`、`gui/test/pc04a2RouteCalibration.test.ts`（三个路径均已核实存在）。

**Interfaces（新模块）:**

```typescript
import type { ExplicitMockInput, BatchMockInput, BatchPlanRequest, FixedRouteRecord } from '../../types/api'
export type MockCsvImport = {
  mockInputs: BatchMockInput[]
  references: BatchPlanRequest['references']
}
export function parseMockCalibrationCsv(text: string, selection: {
  chainIds: string[]; frequenciesMhz: number[]; sampleCount: number
  referenceAntennas: Record<string, string>
}): MockCsvImport
export function exportMockCalibrationCsv(records: FixedRouteRecord[]): string
```

`referenceAntennas` 按 chain_id 填写已核对参考天线/位置，CSV 无此列不能偷偷默认参考身份。批量导入先在表单已有路径/频点/参考身份之内校验；不会自动选择未知通路或另造 topology。

- [ ] **1. 写解析/导出失败测试。** Node test沿现有方式，不增vitest。使用以下实际 CSV：

```typescript
import assert from 'node:assert/strict'
import test from 'node:test'
import {parseMockCalibrationCsv} from '../src/features/TopologyEditor/mockCalibrationCsv.ts'
const header='chain_id,frequency_mhz,sample_index,source_before_dbm,received_dbm,source_after_dbm,receive_cable_loss_db,receive_cable_source,expected_loss_db'
const csv=[header,
  'route-a,2595,1,-20,-50,-18,2,"synthetic, cable",29',
  'route-a,2595,2,-22,-52,-20,2,"synthetic, cable",29'].join('\n')
const selection={chainIds:['route-a'],frequenciesMhz:[2595],sampleCount:2,
  referenceAntennas:{'route-a':'synthetic REF at centre V'}}
test('按通路频率及1起始样本编号组合，保留引号来源',()=>{
  const value=parseMockCalibrationCsv(csv,selection)
  assert.equal(value.mockInputs[0].samples.length,2)
  assert.equal(value.references[0].receive_cable_source,'synthetic, cable')
  assert.equal(value.mockInputs[0].expected_loss_db,29)
})
test('重复/缺组/额外组/空数字/同组公共值冲突不发请求',()=>{
  for(const bad of [csv+'\n'+csv.split('\n')[1], csv.split('\n').slice(0,2).join('\n'),
    csv.replace('route-a,2595,2','route-b,2595,2'),csv.replace('1,-20','1,'),
    csv.replace('2,-22,-52,-20,2','2,-22,-52,-20,3')]){
    assert.throws(()=>parseMockCalibrationCsv(bad,selection))
  }
})
```

- [ ] **2. RED。** `cd gui && node --experimental-strip-types --test test/pc04a8MockCalibration.test.ts`，模块不存在或实现缺失应失败。
- [ ] **3. 实现无新增依赖 CSV parser。** 字符扫描处理 RFC4180 双引号/双引号转义、CRLF/BOM；未闭合引号、重复/未知列、非预期列数、空必需功率/非有限数均拒绝；空行可忽略。frequency正数，sample_index严格十进制整数1..sampleCount，排序后序列严格等于1..N。组键用 `JSON.stringify([chain_id, frequency])`，不以 `split(':')` 解串。数值解析先 `trim()!==''` 再 `Number.isFinite`，避免空串转0。

```typescript
const finite=(raw:string,label:string):number=>{
  if(!raw.trim())throw new Error(`${label}不能为空`)
  const value=Number(raw)
  if(!Number.isFinite(value))throw new Error(`${label}须为有限数值`)
  return value
}
const optional=(raw:string,label:string)=>raw.trim()?finite(raw,label):null
const key=(chain:string,frequency:number)=>JSON.stringify([chain,frequency])
```

同组 cable/source/expected 必须逐行相等（空视为null），不同组独立；线损/来源空可输入显式模拟，预览明确“只留样本，不计算损耗”。每组 reference_antenna 来自 selection.referenceAntennas，不从expected或图标签猜。错误消息包含行号/组/字段；导入失败不得部分覆盖表单、旧preview必须失效。

- [ ] **4. 接入现有状态。** 单路增加默认关闭的“模拟演练样本”开关与每样本三功率输入、可选expected。开启后 `buildRouteAcquisitionRequest` 额外接收 `mockInput?: ExplicitMockInput`；不开启省略字段。批构造函数尾部增加可选 `mockInputs?: BatchMockInput[]`；仅显式矩阵放宽表单线缆非空要求，schema语义与任务2完全相同。每次模式/路径/频点/样本数/CSV/公共值/expected修改都清preview；切换 Lab/topology/运行真实输入模式清模拟草稿，不能静默携带。dirty/busy/unknown/pending禁录入和启动，沿已有请求身份与幂等重试，不新增持久锁系统。
- [ ] **5. 独立模拟结果组件。** `MockCalibrationResult({records}:{records:FixedRouteRecord[]})` 只接服务器记录；显示每条run、chain、freq、全样本、服务器net/std、expected与差值、模拟来源、时间性质、formal=false。`fixedRouteDisplay` 原实测字段继续不给模拟数值；新增 `mock` 返回字段仅在request.mock_input或simulation_input_source明确时出现，旧无样本preview仍“未计算”。两个面板及老工作台使用同一模拟结果组件，避免模拟数字旁边仍写“F64实测”。批历史/列表显示“模拟演练（非实测）”，不是只换颜色。
- [ ] **6. 导出。** 每样本一行，字段为 `run_id,lab_profile_id,chain_id,frequency_mhz,sample_index,source_before_dbm,received_dbm,source_after_dbm,receive_cable_loss_db,receive_cable_source,expected_loss_db,net_loss_db,sample_std_db,expected_delta_db,simulation_input_source,formal_eligible,host_time,time_basis`。source固定服务器来源、formal固定false、time_basis=`simulation_processing_time`；null为空单元格，0保留。拒绝导出缺run/result/source的记录；CSV引用逗号/引号/换行，文本字段首个非空白字符为`= + - @`时前置单引号防公式（数字列原样数值）。下载 `mock-calibration-<job或run UUID>.csv`，Blob URL下载后revoke；不是正式报告。
- [ ] **7. GREEN与真实交互。**

```bash
cd gui
node --experimental-strip-types --test test/pc04a8MockCalibration.test.ts test/pc04FixedRoute.test.ts test/pc06a1Batch.test.ts test/pc04a2RouteCalibration.test.ts
npm run build
```

扩展测试覆盖quoted/CRLF/BOM、空线损null/已知0/负增益、expected不改服务器数值、公式转义、旧preview不导出模拟数值、status篡改仍mock标记、跨lab/run不串结果。浏览器使用任务4隔离服务：单路编辑→批CSV→逐项校验→服务端preview→明确start→history→下载检查；不 mock HTTP 响应。
- [ ] **8. 提交与独立审查。** `git commit -m "feat: 提供模拟校准样本录入与演练CSV导出"`，仅暂存本任务明确文件。审查重点为用户看见的数据来源及锁行为，而非增加新的导航机制。

## 任务4：隔离32路完整对账、原图缺项回执、最终唯一全后端

**Files（修）:**
- Create: `api-service/tests/pc04a8_browser_fixture.py`、`test_pc04a8_acceptance.py`
- Create: `gui/test/pc04a8.vite.config.ts`
- Create: `docs/validation/2026-10-30-pc04a8-mock-calibration.md`
- Update: 本计划复选框、设计状态、`docs/roadmap-first-call.md` PC-04A-8条目；不得将原图缺口标完成。

**Interfaces:** 新 fixture导出 `bootstrap_mock_database(kind: str = 'browser') -> dict`、`synthetic_graph_32() -> dict`、`seed_world(db) -> dict`。CLI `--bootstrap-only --kind {browser,test,full}`，遵循已有 pc04a5d 脚本结构，但检查 `/tmp/pc04a8-.../` 且不改旧脚本；复用旧 `configure_mock/audit_mock/verify_hal/declaration_graph` 函数时仅新库调用，不能复用旧 `checked_path`（它绑定pc04a5d前缀）。

- [ ] **1. 写32路图与独立期望表测试。** 用 `declaration_graph()` 深拷贝32次，节点/连接ID全部前缀 `synthetic-01-` 到 `synthetic-32-`，CE端口为B1..B32，probe编号为`(i-1)//2`、奇数V偶数H；显式路径ID、参考段ID同步前缀。保留PA标称20作为“不重复补偿”反例，线缆声明仅属synthetic。SA节点填当前隔离signalAnalyzer category ID；不得引用原r6真实声明。

```python
def samples_for(route_index, frequency_index):
    return [dict(source_before_dbm=-30.+j*.2,
                 source_after_dbm=-29.8+j*.2,
                 received_dbm=-48.+route_index*.7+frequency_index*.3+j*.1)
            for j in range(5)]

def expected_for(route_index, frequency_index):
    # 独立代数展开，不调用生产calculate_sample_losses。
    # Lrx=2；五样本均值中的j均值=2，样本方差=(.1^2)*2.5。
    return 16.3-route_index*.7-frequency_index*.3, (0.025)**0.5
```

索引route_index=0..31、frequency_index=0..1，频点2595/3500MHz，仅演练输入不是仪器频段承诺。该矩阵同时含正损耗、负增益；已知0/未知线缆由任务2另例验证。expected_loss_db可填独立期望值用于显示差值；服务端只从样本算。

- [ ] **2. 隔离前置与RED。** 新脚本严格验证路径不存在、父目录存在、Mock/BOOTSTRAP环境精确true后才import app；Base.metadata.create_all→bootstrap→configure_mock→audit_mock→verify_hal→seed_world→再次audit/verify。新建两实验室/暗室：一个只导入r6三个数组，一个synthetic32；原默认库不查写。fixture manifest记录source SHA256、三数组canonical hash、输入commit/diff hash、类别/绑定/实际HAL分类。

```bash
cd api-service
pc04a8_dir=$(mktemp -d /tmp/pc04a8-XXXXXX)
export DATABASE_URL="sqlite:///$pc04a8_dir/test.sqlite"
export USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true AUTH_MODE=disabled
export LOG_DIR="$pc04a8_dir/logs"
.venv/bin/python -m tests.pc04a8_browser_fixture --bootstrap-only --kind test
.venv/bin/python -m pytest tests/test_pc04a8_acceptance.py -q
```

夹具/测试只用现有依赖；不要以安装包“修环境”，也不要改之前验收fixture。RED要捕获预期新矩阵/标记或尚未实现完整链路的断言，若任务2/3已使新增验收初次全绿，诚实记“集成验收初次绿”，不声称虚构RED。

- [ ] **3. 完整生产API验收。** `test_pc04a8_acceptance.py` 通过真实 FastAPI路由（TestClient/ASGI不是浏览器）取synthetic32选路→构造64项preview→start→逐manual transition确认→终态→按run_id读64子记录，不能用默认history limit20代表全量。使用既有批HTTP测试的轮询方式，给出有界超时，失败保留父/子回执。断言：

```python
assert len(routes) == 32
assert len(final['items']) == 64
assert len({(r['result']['request']['chain_id'],r['result']['request']['frequency_mhz'])
            for r in children}) == 64
assert sum(len(r['result']['samples']) for r in children) == 320
assert all(r['status']=='simulated' and r['result']['formal_eligible'] is False for r in children)
assert all(r['result']['cleanup_confirmed'] is None for r in children)
for record in children:
    result=record['result']
    index=chain_to_index[result['request']['chain_id']]
    frequency_index=[2595.,3500.].index(result['request']['frequency_mhz'])
    mean,std=expected_for(index,frequency_index)
    assert result['net_loss_db']==pytest.approx(mean,abs=1e-9)
    assert result['sample_std_db']==pytest.approx(std,abs=1e-9)
```

`chain_to_index`由图构造时的synthetic编号与最终终端connection_id manifest建立，不能用服务器result数值反推。请求、preview、parent、children、独立期望、actual diff、采用拒绝、正式freeze无confirmed_route分别保存JSON。记录父finalization真实值，f64_control_released null不补true。完成后再启动单路及取消重入验证，非完整/失败运行不得计入64项成功。

- [ ] **4. 原r6诊断独立留痕。** 先对导入前三数组hash与读回hash相等；调用生产 `route-calibration-paths?selection_scope=individual`，保存实际HTTP状态/详情及每路参考段缺项。窄修后若仍422，记录具体生产阻塞；若200但参考段为空，报告“下行入口解除误挡，参考段未声明”，不能据此宣称当前图32路全流程完成。原r6不提交校准start来掩盖参考段缺失、不更改mode或节点。该结果与synthetic32对账物理分栏。

- [ ] **5. 真实TCP服务与浏览器。** 新建第二个`/tmp/pc04a8-.../browser.sqlite`，同环境前置bootstrap/seed，使用独立端口18048/15148，先以 `lsof -nP -iTCP:18048 -iTCP:15148 -sTCP:LISTEN` 检查；占用则停止本次启动并选空闲端口同步本片配置/manifest，不杀已有服务。后端 `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18048`。已核实默认Vite代理固定8000/8001，不能只改GUI端口；新增本片独立配置，模式与既有`gui/test/pc04a5d.vite.config.ts`一致：

```typescript
import {defineConfig,mergeConfig} from 'vite'
import base from '../vite.config'
export default mergeConfig(base,defineConfig({server:{host:'127.0.0.1',port:15148,strictPort:true,
  proxy:{'/api/v1/ws':{target:'http://127.0.0.1:18048',ws:true},
    '/api/v1/ota':{target:'http://127.0.0.1:18048'},
    '/api':{target:'http://127.0.0.1:18048'}}}}))
```

GUI命令：`cd gui && node node_modules/vite/bin/vite.js --config test/pc04a8.vite.config.ts`。真实浏览器按任务3流程录入并运行32路，保存截图、HTTP回执和下载CSV；64组合/320行及列值与同批JSON逐项比对。浏览器需确认当前transition，不制造接口回复。测试后仅停止本片新建PID，不关闭用户Chrome/既有服务。

- [ ] **6. 稳定版相关回归、构建与最终全量。** 先跑前3任务相关集、GUI构建、独立审查修复；全部稳定后新建第三个SQLite，在app导入前隔离，bootstrap后核全Mock，再唯一一次：

```bash
cd api-service
pc04a8_full_dir=$(mktemp -d /tmp/pc04a8-XXXXXX)
export DATABASE_URL="sqlite:///$pc04a8_full_dir/full.sqlite"
export USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true AUTH_MODE=disabled
export LOG_DIR="$pc04a8_full_dir/logs"
.venv/bin/python -m tests.pc04a8_browser_fixture --bootstrap-only --kind full
.venv/bin/python -m pytest -q
```

记录完整命令、环境（不含凭据）、输入commit/diff/hash、退出码、末尾passed/skipped/warnings/failed、日志位置。已有警告与新回归分别说明；不能为绿而跳过失败或改旧fixture。仅文档状态更改可复用同输入输出；产品修复后不得称旧全量覆盖新版。

- [ ] **7. 文档、累计独立审查与单PR。** 验收文档含：原图缺项、synthetic32结果、用户操作指南、三态/公式/expected边界、软件/真机区别、完整消费者审计、测试输入清单与未验项。计划/设计/roadmap只写实际完成状态；创建Ready PR与R1/R2由主代理按AGENTS执行，最新HEAD仍有P1则续审。最终不自动部署。
- [ ] **8. 最终提交。** `git commit -m "test: 完成模拟校准32路对账与隔离验收说明"`。提交内容限本片fixture/test/docs；不提交临时SQLite、日志、用户快照或凭据。

## 4. 自审与完成判据

- [x] 计划规格覆盖自查：路径识别→任务1；样本/缺值/公式/来源/安全/采用冻结→任务2；CSV/显示/导出/锁→任务3；32×2×5、原图缺项、真实浏览器、最终全量→任务4。
- [x] 计划类型一致自查：`mock_input: ExplicitMockInput | None`（单路）与`mock_inputs: tuple[BatchMockInput,...] | None`（批），最终均冻结为子request.mock_input；simulation_input_source仅服务器结果；expected仅请求字段，不是实测。
- [x] 新接口在本计划定义，既有生产路径与测试路径只读核实；四个任务尚未执行。
- [x] 已扫描空白实现占位；任务2不能在未覆盖正式消费者时通过独立审查。
- [x] 读图/导入/校准生成/历史读取/采用/冻结/导出均已列生产关系及验收断言。
- [x] 计划编写阶段未修改原用户数据或服务；r6不完整参考声明与synthetic32验收分开。

实施交接：用户已要求按已批准设计连续推进；本计划独立审查通过后，主代理按四任务串行执行并安排审查，不再重新询问已确认的实施方式。本次计划作者不执行产品、不跑全量、不释放主代理台账认领。
