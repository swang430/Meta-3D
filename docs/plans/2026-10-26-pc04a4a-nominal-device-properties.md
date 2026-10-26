# PC04A4a 器件标称参数编辑实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `subagent-driven-development` 或 `executing-plans` 逐任务执行；主代理依据已获授权选择，本文不另派 agent。步骤使用复选框跟踪。

**Goal:** 在原拓扑画布中可靠编辑、保存和恢复器件标称参数及 CAICT 旧 PA 边参数，清楚区分声明、未知和实测，不新增补偿。

**Architecture:** 保留节点 `params` 与旧边 `pa_gain_db` 的存储位置；只给明确字段加类型、来源与适用频率声明。小型器件属性组件嵌入原抽屉，沿原草稿、PATCH、GET 链保存；共享路径与历史采用逻辑不改算法，新说明元数据不成为物理接线身份。

**Tech Stack:** 现有 React/TypeScript/Mantine/ReactFlow、FastAPI/Pydantic、SQLAlchemy JSON、pytest、tsx/node:test、真实浏览器；不新增依赖或表迁移。

**Spec:** [已确认设计](../design/2026-10-26-topology-device-port-contract.md)；排班见 [Current Focus](../roadmap-first-call.md)。用户于 2026-10-26 明确开始；本文件是首片实施计划，尚未实现或验证。

## 全局约束

- WIP=1，4a 合并后才启动 4b；三个任务是同一片内串行、各有 RED→GREEN 与独立审查的交付单元，不是三片并发。
- `params.ports` 继续是端口 ID 清单；本片不新增端口角色、不修改方向绘制、不生成内部通路、不转换旧图。
- 标称增益、衰减、天线增益记录单位、来源说明和适用频率范围；本片新增可空字段未填为 `null`，显式 `0` 原样保存，不能用 `||` 吃掉。
- 标称值不是校准实测，不自动进入正式采用或新补偿路径。校准来源、原始采集和历史执行冻结保持只读；整链实测只在原采用入口生效一次。
- 旧记录不批量改写；正常旧图的无关改名/位置保存不得被本片的新字段约束误伤。
- API 与 GUI 镜像同一契约；绕过 GUI 的 PATCH 也验证。采集/保存期间继续禁止编辑，取消/失败恢复不得遗失草稿。
- 不添加 SCPI、不推断硬件能力、不改 B/HOLD；NotebookLM 不适用。若实现要求 HAL/仪器语义，停止扩域并回报。
- 全部应用导入、pytest、浏览器 API 启动前显式指定本次临时 SQLite、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`；不用默认 DB，不停止用户服务，不提交 `.venv` 或 `output`。
- 纯计划阶段只做 diff/引用/消费者核验，不声称测试通过。实现阶段属于“GUI/API + 共享校准身份契约”，最终稳定输入须全后端回归；不以4e代替本片验证。

## 0. 先审清的边界与消费方全集

### 0.1 基线及复查命令

本计划审计生产基线为 `710f55a3`；设计/roadmap 的确认状态为当前工作区输入，不能把未提交状态冒称该提交已有。实现前重新执行下列命令并记录增量；命令是定位用，不导入应用：

```bash
git status --short
git grep -n -E 'pa_gain_db|gain_dbi|gain_db|attenuation_db|frequency_range_mhz|max_power_dbm' -- api-service/app gui/src api/openapi.yaml api-service/scripts/dev-fixtures/topology-templates
git grep -n -E 'inputs|outputs|4合1|PA ×32|32.*out' -- gui/src/features/TopologyEditor api-service/scripts/dev-fixtures/topology-templates
git grep -n -E 'cable_loss_db|calibrated_loss_db' -- api-service/app/services/topology_service.py api-service/app/services/mimo_ota/switch_orchestrator.py api-service/app/services/calibration/rf_chain_resolver.py
git grep -n -E 'route_digest|parameters_digest|identity_nodes|calibration_connections' -- api-service/app/services/calibration api-service/app/services/mimo_ota/route_calibration_freeze.py
git grep -n -E '绝不|不许|禁止|must not|别把' -- api-service/app/api/switch_topology.py gui/src/features/TopologyEditor
```

### 0.2 生产入口 → 权威数据 → 消费者 → 断言

| 链/全部对称站点 | 当前事实与本片处理 | 可观察断言 |
|---|---|---|
| `app/api/switch_topology.py` 的 create / update / import；`schemas/switch_topology.py` 的 Node / Connection；ORM `models/switch_topology.py` | POST 经 schema、PATCH 合并后经 `_validate_structure`，模板直接 dict 也经该函数；GET/list 用 response schema。增加同一标称验证，不让模板成为绕过点；GET 不执行写校验 | POST、PATCH、import 非法新声明在任何删/写前422；GET/list旧记录可读；PATCH拒绝后原行不变 |
| `TopologyEditor.tsx` 的 `openNode`、`handleEdgeClick`、`applyConnectionEdit`、`handleSave`、重载；`topologyDraft.ts` 的 update node/connection；`switchTopologyService.ts` | 在原抽屉与草稿上编辑，参数对象增量合并；新增嵌套元数据必须不可变更新，不能浅拷贝后改原对象 | 取消不改草稿，应用只改选中对象，保存GET重载一致；未知扩展参数、位置、模式、引用仍保留 |
| `CustomEdges.tsx::SignalEdge` 与 `TopologyEditor.tsx::initialEdges` | 旧 `pa_gain_db` 仅用于 PA/净增益显示、颜色；`>0` 与真假判断现会隐藏0；改为非null有限数存在判定，标“标称，非实测”，净增益只作显示 | 0显示0，负值按有符号值显示；校准值0仍显示校准；没有PA不显示假PA |
| `calibration/configuration_scope.py::_build_scope_payload` 的 `graph['connections']`、节点 parameters/digest | 边PA、节点gain/attenuation/loss等进入配置盘点；完整params摘要已包含新元数据。保留提醒，不另加资格门 | 来源变化可在配置盘点显差异；不写历史证据或采用记录 |
| `calibration/route_calibration.py::_route_selections` → `fixed_route_jobs.py` → `route_batch_plan.py` → `evaluate_route_application`/confirm → `mimo_ota/route_calibration_freeze.py` | 节点几乎全部params与参考边整字典进入 route_digest，新元数据若不排除会制造route_mismatch。只排除本片新 `nominal_metadata`；旧标称数值原身份语义暂不改变，见0.3 | 只有新增/修改元数据时旧route_digest不变；真实端口/映射变化仍拒绝；历史snapshot不重写 |
| `TopologyService.__init__/_dfs_paths/get_end_to_end_loss/get_calibration_matrix/to_dict/validate` | 当前只算边 calibrated_loss/cable_loss，根本不读PA或节点标称增益。不得“补上”PA相减或节点衰减累加 | 同图仅改PA/节点标称值，总损耗与矩阵不变；已有校准值优先 |
| `mimo_ota/switch_orchestrator.py::_build_probe_binding` → `calibration/rf_chain_resolver.py::_binding_to_spec` → `channel_engine_client.py` | 旧边电缆损耗有执行消费者；不是本片要可空化的数据域；新标称字段不送入此链 | 整链采用后端口补偿仍一次；不叠加PA/探头增益/节点损耗 |
| `declared_rf_routes.py::resolve_saved_rf_path/selected_switch_mappings/rf_execution_identity` | 正常接线/开关映射与执行身份独立存在，不改这些规则来迁就新属性 | 缺路径、错端口、错Lab、校准参考段混入正常路径继续拒绝 |
| `scripts/dev-fixtures/topology-templates/caict_v4.py` | `pa_gain_db=20.0`注释为典型值；参考天线gain_dbi=15与链路天线gain_dbi=3无实测身份；CE inputs=4/outputs=32不是已验证端口声明 | 不改模板值、不批量补来源；旧图显示“旧版标称，来源未声明”；新建PA为空 |
| `CustomNodes.tsx` 的 CE/EMCenter；`nodePortHelpers.ts` | 有固定4/32与“集成PA ×32”。本片删除能力式徽标，以“旧版端口示意/数量未声明”提示替代；`params.inputs/outputs`可仅以“旧声明”显示，不能称真实物理口数 | 缺值不回退4/32；0不回退；保留原handles，角色和数量统一待4b |
| `chamber.py` model/schema/API，`ChamberConfigCard/CreateChamberForm`，`channel_engine_client.py`，`path_loss_calibration_service.py`，`e2e_calibration_service.py`，`calibration_report_generator.py` | `chamber.pa_gain_db/probe_gain_dbi` 是另一独立数据域，存在公式/报告消费者，不能因同名就绑定拓扑标称字段。本片不改 | 拓扑保存不写chamber、旧校准记录/证书/报告 |
| `probe_calibration_service.py`、`probe_pattern/*`、`quiet_zone_validation_service.py`，GUI ProbeCalibration / VirtualRoadTest / TestCaseConfig，schemas/models对应gain字段 | 搜索同名命中但为实测、参考量或独立虚拟路测配置，不是拓扑params。保留；不把标称值注入这些来源 | 本片没有新赋值链；回归不把模板增益当测量值 |
| `api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts` | 当前checked OpenAPI没有switch-topologies CRUD/Node/Connection契约，手写接口单独存在；本片只补实际用到的GET/list/POST/PATCH/import与递归schema闭包，不导出整个应用覆盖yaml | checked/live schema、真实JSON、生成类型、手写使用接口一致；既有全局G11继续成立 |

`params.gain_db/gain_dbi/loss_db/attenuation_db` 的当前拓扑消费者主要是params透传与上述摘要，不存在节点到正式补偿的自动接线。其它域同名不等于同一值。测试、归档、已完成计划和现场日志仅作历史证据，不改成新现状。

### 0.3 两项明确裁决建议（实施前由主代理确认，不擅自扩域）

1. **旧边 cable_loss_db 的空值不是局部表单问题。** 其schema为float默认0，路径求和/校验和正式binding仍依赖数值。建议4a仅让新增节点标称字段与旧PA可空，旧边电缆损耗沿既有非空契约；可给其新增来源/频率元数据，不能新增节点线缆损耗第二份值。旧边可空化/损耗归属统一交给4d的专门审计。本片不得把用户在新字段清空转换为0，也不得宣称已解决所有旧缺测语义。若用户要求本片旧边也可空，先修订设计/计划，不偷偷用`None→0`通过。
2. **旧标称数值当前参与route_digest，新说明元数据不应参与。** 建议本片只精确排除新`nominal_metadata`（节点与参考边两端），保持没有该键的历史digest逐字节不变；不批量重算旧run，不改旧数值改变后的原有适用性判据。若要求旧标称数值改动也完全不影响旧run适用性，须先明确摘要版本兼容与原历史数值的裁决，不能全量删掉旧gain键让所有存量digest失配。UI明确“数值修改可能触发原通路一致性复核；保存标称不等于采用校准”。

## 1. 契约与文件职责

### 1.1 字段表（单位为应用声明，不是仪器回读单位）

| 对象 | 值的唯一存储键 | 类型/范围 | 编辑入口 |
|---|---|---|---|
| amplifier | `params.gain_db` | finite number 或null，允许0与负数，不猜硬件量程 | PA标称增益(dB) |
| pad | `params.attenuation_db` | finite number≥0 或null | 标称衰减(dB) |
| combiner | `params.loss_db` | finite number≥0 或null | 标称插损(dB) |
| probe / antenna / reference_antenna | `params.gain_dbi` | finite number 或null，允许负增益 | 标称天线增益(dBi) |
| 旧PA边 | `connections[i].pa_gain_db` | finite number 或null；0保留 | 连线抽屉“旧PA标称增益(dB)”；可从PA边清单定位 |
| 旧电缆边 | `connections[i].cable_loss_db` | 沿旧非空契约，不在此片可空化 | 原损耗字段，新增来源/范围说明 |

不把 `max_power_dbm`、通用`frequency_range_mhz`、`inputs/outputs`扩成新的可执行能力配置。非表内已有params字段原样保留，避免按名称自动变成可写“能力”。线缆/接收线缆节点不另建损耗字段；其抽屉引导编辑相邻边，只提醒单一归属，不替用户自动分摊。

每个支持字段配同级对象上的 `nominal_metadata` 字典：节点位于 `params.nominal_metadata`，边位于 `nominal_metadata`。键是上表字段名；值为下面模型。数值仍只存原键，元数据不重复数值，也不引用校准结果。

```ts
export interface NominalFieldMetadata {
  unit: 'dB' | 'dBi';
  source_note: string | null;
  frequency_range_mhz: [number, number] | null;
}
// 例如 params.gain_db=0 与：
const example = {gain_db: {
  unit: 'dB', source_note: '操作员按器件铭牌录入，未校准',
  frequency_range_mhz: [2500, 2700],
}} satisfies Record<string, NominalFieldMetadata>;
```

元数据unit必须与键匹配；来源去首尾空格后空串存null；频率必须两个有限正数且start≤stop，允许单频[start,start]；两个框全空→null，一个空一个有值→表单拒绝。数字拒绝boolean、字符串、NaN/Infinity；不推测硬件范围。无元数据的旧值仍可读并标“旧版标称/来源未声明”；不能自动写“已核实/实测”。编辑值但未填来源允许保存为未知来源，并持续提示；来源文本永远不是资格证据。

### 1.2 文件分工

- 新建 `api-service/app/schemas/topology_nominal.py`：`NominalFieldMetadata`、支持键/单位表、纯写校验；不导入ORM/HAL。
- 修改 `api-service/app/schemas/switch_topology.py`：边元数据模型、写入专用PA finite校验；节点params保留扩展字典以兼容旧记录。
- 修改 `api-service/app/api/switch_topology.py`：所有写入口调用标称校验，PATCH传旧对象用于未改字段豁免；不把新校验放到GET。
- 修改 `api-service/app/services/calibration/route_calibration.py`：只排除新说明元数据，原历史摘要及物理身份校验不变。
- 新建 `gui/src/features/TopologyEditor/nominalProperties.ts`：字段描述、空值解析、不可变写入与显示标签纯函数；不计算正式补偿。
- 新建 `gui/src/features/TopologyEditor/NominalPropertyFields.tsx`：可复用标称数值/来源/频段表单，接收`disabled`；不自发PATCH。
- 修改 `TopologyEditor.tsx`、`CustomEdges.tsx`、`CustomNodes.tsx`、`gui/src/api/switchTopologyService.ts`：原入口接线、旧PA定位、标注及类型镜像；不拆其它编辑器功能。
- 修改 `api/openapi.yaml`、生成 `gui/src/types/api.generated.ts`；测试放任务各自列出的文件。`topologyDraft.ts`只复用，若无必须改动不触碰。

## 2. Task 1：类型化写入、真实往返与元数据身份边界

**Files:** 上述三个后端schema/API文件、`route_calibration.py`；`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`switchTopologyService.ts`；新测试 `api-service/tests/test_pc04a4a_nominal_properties.py`、`api-service/tests/test_pc04a4a_nominal_identity.py`。

**Interfaces:** `validate_nominal_write(nodes, connections, *, previous_nodes=None, previous_connections=None) -> None`，错误抛`ValueError`由API转422；仅校验支持字段发生变化或新建的字段/元数据，不拒绝未改变的旧标称坏值。`NominalFieldMetadata`作为公开schema；不增加端点。

- [ ] 先写真实POST/PATCH/GET回归。复用现有p1_57的内存DB依赖override，但运行命令仍隔离app导入时的全局DB。以下测试初始应因新元数据被丢弃/非法值未拒绝而RED：

```python
import copy
import pytest
from tests.test_p1_57_topology_lab_context import client, setup_database, world, _mk_row

@pytest.mark.parametrize('value', [None, 0, -3.5, 21.25])
def test_pa_edge_roundtrip_keeps_null_zero_and_metadata(world, value):
    row = _mk_row(world['db'], world['switch_id'], world['chamber_a'].id)
    body = dict(nodes=[dict(id='a', type='ce_port', label='B1.1', params={}),
                       dict(id='p', type='probe', label='P', params={})],
        connections=[dict(id='ap', source='a', target='p', pa_gain_db=value,
            nominal_metadata={'pa_gain_db': dict(unit='dB', source_note=None,
                frequency_range_mhz=None)})], operating_modes=[])
    url = f'/api/v1/switch-topologies/{row.id}'
    scope = {'lab_profile_id': str(world['lab_a'].id)}
    saved = client.patch(url, params=scope, json=body)
    assert saved.status_code == 200, saved.text
    fetched = client.get(url, params=scope)
    assert fetched.status_code == 200, fetched.text
    edge = fetched.json()['connections'][0]
    assert edge['pa_gain_db'] == value
    assert edge['nominal_metadata'] == body['connections'][0]['nominal_metadata']

@pytest.mark.parametrize('bad', [True, '12', [12], {'v': 12}])
def test_invalid_node_nominal_is_rejected_atomically(world, bad):
    row = _mk_row(world['db'], world['switch_id'], world['chamber_a'].id)
    before = copy.deepcopy(row.nodes)
    response = client.patch(f'/api/v1/switch-topologies/{row.id}',
        params={'lab_profile_id': str(world['lab_a'].id)},
        json={'name': '不应保存', 'nodes': [dict(id='pa', type='amplifier', label='PA',
            params={'gain_db': bad})]})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.nodes == before and row.name == 'Row'
```

- [ ] cwd=`api-service`，RED与GREEN各新建目录，实际记录命令、退出码、末行与输入SHA/diff：

```bash
pc04a4a_test_dir=$(mktemp -d /tmp/pc04a4a-test-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a4a_test_dir/test.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests/test_pc04a4a_nominal_properties.py -q
```

- [ ] 最小实现写校验：允许缺键与null，拒绝伪数字，不无条件重建params。模型核心形状如下；unit与字段对应/频率校验及旧值比较在同一模块补齐：

```python
from math import isfinite
from typing import Literal
from pydantic import BaseModel, ConfigDict

class NominalFieldMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    unit: Literal['dB', 'dBi']
    source_note: str | None = None
    frequency_range_mhz: tuple[float, float] | None = None

def validate_number(value, *, key, nonnegative=False):
    if value is None:
        return
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f'{key} 必须为有限数值或null')
    if nonnegative and value < 0:
        raise ValueError(f'{key} 不得小于0')
```

写入专用`TopologyConnectionWrite(TopologyConnection)`对`pa_gain_db`使用`field_validator(mode='before')`，`SwitchTopologyCreate/Update.connections`引用该写入类型，不能让`True/'12'`先被float强转；response仍使用读取模型，不对历史GET追加新限制。模板原始dict由相同纯函数校验。节点保留`Dict[str,Any]`，公开契约通过明确可选属性与additionalProperties表达，不使旧扩展键消失；schema文档的扩展描述必须来自live模型定义，不能只手改yaml伪造类型。新增元数据可选；未涉及标称的PATCH/旧图重保存不注入新元数据空对象；嵌套dump用`exclude_unset=True`保留新增字段的缺省/显式null差异，核对旧source_pin默认仍从现有schema解释。

- [ ] 在create/update/import的写前统一调用；旧字段比较用字段存在性加值比较，缺键不同于null。对每个对象只豁免完全没改的旧值，不能豁免新metadata字段中的坏频率或单位。模板导入在删除旧行前完成校验。覆盖：POST合法/非法、PATCH清空、错误单位、半频段、反向/0/负频率、非法元数据键、模板非法且replace=true原行保留、GET/list旧异常值可读、旧异常值改名可存但改成另一个异常值拒绝、跨Lab409。

- [ ] 先写元数据不影响摘要的真实路径正例，复用 `test_pc04a2_route_selection.py` 的`client/configured/graph/db_session/paths`，覆盖正常节点、参考节点、参考边三条路径：

```python
def test_source_metadata_does_not_change_existing_route_identity(client, configured, graph, db_session):
    before = paths(client, configured, graph).json()[0]
    graph.nodes = [{**n, 'params': {**n.get('params', {}), 'nominal_metadata': {
        'gain_dbi': {'unit': 'dBi', 'source_note': '目录待核', 'frequency_range_mhz': None}
    }}} if n['id'] == 'reference1' else n for n in graph.nodes]
    db_session.commit()
    after = paths(client, configured, graph).json()[0]
    assert after['route_digest'] == before['route_digest']
    assert after['calibration_nodes'][0]['params']['nominal_metadata']['gain_dbi']['source_note'] == '目录待核'
```

- [ ] 只从`identity_nodes`的params与`calibration_connections`的摘要副本删除新`nominal_metadata`键，原`nodes/connections/calibration_nodes/calibration_connections`快照保留原始完整对象；不修改存储数据，不删其它旧键。新增元数据以前的同一图摘要必须不变。对端口/CE映射/参考天线身份变化仍按原门拒绝；运行旧 `test_cosmetic_change_only_warns_but_changed_port_is_incompatible`。
- [ ] 补checked OpenAPI上述CRUD范围及依赖schemas，保留其它路径原样；隔离环境导入`app.openapi()`提取该闭包，使用apply_patch更新yaml；`gui`运行`npm run openapi:generate`，不要整份live spec覆盖checked文件。新测试逐个比较相关schema/path与live，并验证真实response含字段；手写类型的`pa_gain_db?: number | null`及元数据类型一致。
- [ ] GREEN后定点回归 `tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a3_topology_recovery.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_gui_contract.py`。每次同样显式新临时库/全Mock/default bootstrap。
- [ ] 变异实跑：临时移除写校验→非法写测试RED；临时恢复新元数据参与身份→元数据正例RED；恢复正确代码后GREEN。仅修改本片代码，用apply_patch还原，保存diff和测试末行，不用reset覆盖用户修改。
- [ ] 审查Task1后精确`git add`上述文件，提交 `feat: 补齐拓扑标称参数写入契约`；不push，等待整片验证。

## 3. Task 2：原抽屉标称字段、旧PA定位与真实标注

**Files:** 新`nominalProperties.ts`/`NominalPropertyFields.tsx`；修改`TopologyEditor.tsx`/`CustomNodes.tsx`/`CustomEdges.tsx`；新`gui/test/nominalProperties.test.ts`。

**Interfaces:** `nominalFieldsForNode(type: string): readonly {key:string,label:string,unit:'dB'|'dBi',nonnegative:boolean}[]`；`parseOptionalNominalNumber(value: number|string): number|null`；`setNodeNominal(node, key, value, metadata): TopologyNode`；`setEdgeNominal(edge, key, value, metadata): TopologyConnection`。组件props为`fields, values, metadata, disabled, onChange(key,value,metadata)`，数值与元数据一次回调、不请求网络。

- [ ] 写纯函数RED，文件从现有`gui/test/topologyDraft.test.ts`风格沿用node:test/tsx：

```ts
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseOptionalNominalNumber, setNodeNominal} from '../src/features/TopologyEditor/nominalProperties.ts';
test('清空是null且零不丢，编辑不改原节点或扩展字段',()=>{
  assert.equal(parseOptionalNominalNumber(''),null);
  assert.equal(parseOptionalNominalNumber(0),0);
  assert.throws(()=>parseOptionalNominalNumber('not-a-number'));
  const before={id:'pa',type:'amplifier',label:'PA',params:{gain_db:20,unknown:{keep:1}}};
  const metadata={unit:'dB' as const,source_note:null,frequency_range_mhz:null};
  const after=setNodeNominal(before,'gain_db',0,metadata);
  assert.equal(after.params.gain_db,0);
  assert.equal(before.params.gain_db,20);
  assert.deepEqual(after.params.unknown,{keep:1});
});
```

- [ ] cwd=`gui`：`npx --yes tsx --test test/nominalProperties.test.ts`，记录缺实现RED。实现函数最小形状：

```ts
export function parseOptionalNominalNumber(value: number|string): number|null {
  if (value === '') return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('请输入有限数值');
  return value;
}
// 只在有效NumberInput提交/失焦后转换；输入中的'-'等中间串留在组件局部状态，
// 显示错误并禁用应用，不能把中间串自动存0或null。
```

- [ ] 实现表内字段描述，组件用`value={number ?? ''}`、`disabled={editingBlocked}`；来源、频率全空保持null。显示“标称/非实测”，旧值无来源不填典型来源。`setNodeNominal`/`setEdgeNominal`逐层复制params/nominal_metadata，不能mutate旧对象。
- [ ] 节点抽屉嵌入组件，仅选中的节点落草稿；连线抽屉新增旧PA字段及元数据。提供“含旧PA标称的连线”清单（`pa_gain_db !== null && !== undefined`，含0），显示边ID与两端标签/端口，点击调用提取的`openConnection(id:string)`并高亮同一条边，不能按节点名猜PA归属。沿现有`handleEdgeClick`同源打开逻辑，隐藏/非当前模式边仍可通过清单定位，明确所属模式；不自动改模式或创建PA节点。
- [ ] 所有表单控件与定位/应用入口读取`editingBlocked`；打开后进入采集/保存也锁住。原取消行为保留草稿；节点metadata不因关闭抽屉浅引用泄漏。采集失败/取消后锁恢复由原busy链驱动，不另建定时器。
- [ ] 修正PA显示与箭头颜色的真假判断，0及负数不丢。PA净值只为标称显示，明确非实测；不写回`calibrated_loss_db`。校准字段维持只读、校准值0优先；不改变旧校准采用入口。
- [ ] 移除`CustomNodes.tsx`的CE默认4/32和EMCenter“集成PA ×32”断言，保留用户label；不把端口handles数当硬件端口数。旧inputs/outputs即便非空也写“旧声明：…，未核实”；缺失写“端口数量未声明”。保留原handles与布局，不在4a加入角色编辑、`num_ports`同步或新端口数量推导。
- [ ] GREEN：`npx --yes tsx --test test/nominalProperties.test.ts test/topologyDraft.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts`；`npm run build`。核心变异把null/0处理换成`value || null`应RED；恢复后GREEN。
- [ ] Task2规格/质量审查后精确提交 `feat: 支持器件标称属性与旧PA边编辑`。不用无关重构消除已有lint/build警告。

## 4. Task 3：真实API浏览器与完整回归收口

**Files:** 新 `api-service/tests/pc04a4a_browser_fixture.py`（只造隔离数据）、`gui/test/pc04a4aNominalProperties.browser.js`、`gui/test/pc04a4a.vite.config.ts`（只测试专用代理）；新增 `docs/validation/2026-10-26-pc04a4a-nominal-properties.md` 实际验证摘要；完成后只更新roadmap本片状态/计划复选框。

**Interfaces:** fixture输出`{database,labs:[{name,lab_id,topology_id}],caict_topology_id}`；浏览器脚本沿现有`async page=>{...}`，只发真实HTTP、不伪造APIresponse、不调用前端mockServer。所有证据存本次临时目录，文档只保留可核验摘要/相对归档引用。

- [ ] 用apply_patch创建专用fixture，复用 `tests/pc04a3_browser_fixture.py` 的默认bootstrap类别/全部driver_mode=mock、文档网段、两Lab独立暗室的做法，不导入执行它（其路径防护和seed命名属于旧片）。导入app之前验证`DATABASE_URL`严格匹配`sqlite:////tmp/pc04a4a-[A-Za-z0-9]+/browser.sqlite`、文件不存在、父目录存在、两个环境开关均true；失败立即退出。默认bootstrap仍运行，所有类别和Lab binding再次断言mock。准备一个正常显式两链图及一份经真实模板导入的CAICT旧图；不复制用户数据库、历史证书或实测记录。浏览器操作前后存清单与真实GET。
- [ ] 确认独占端口（占用则选另一个并同步测试配置，绝不kill占用服务）：

```bash
lsof -nP -iTCP:18094 -iTCP:5189 -sTCP:LISTEN
pc04a4a_browser_dir=$(mktemp -d /tmp/pc04a4a-XXXXXX)
cd api-service
env DATABASE_URL="sqlite:///$pc04a4a_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4a_browser_dir/logs" .venv/bin/python -m tests.pc04a4a_browser_fixture
env DATABASE_URL="sqlite:///$pc04a4a_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4a_browser_dir/logs" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18094
```

测试专用Vite配置（文件位于`gui/test`；不改生产`vite.config.ts`）：

```ts
import {defineConfig, mergeConfig} from 'vite';
import base from '../vite.config';
export default mergeConfig(base,defineConfig({server:{host:'127.0.0.1',port:5189,strictPort:true,
  proxy:{'/api/v1/ws':{target:'http://127.0.0.1:18094',ws:true},
    '/api':{target:'http://127.0.0.1:18094'},
    '/api/v1/ota':{target:'http://127.0.0.1:18094'}}}}));
```

`gui`启动：`npm run dev -- --config test/pc04a4a.vite.config.ts`。该验收不启动CE服务，不请求OTA接口；专用代理不准意外落到用户8000/8001服务。若需要CE真实软件链验证，另走既有隔离回归夹具，不复用用户服务。浏览器实施者先读当前可用browser skill，采用受支持真实浏览器执行脚本；CLI允许时沿已有 `playwright-cli -s=pc04a4a open http://127.0.0.1:5189 --headed` 路径。不要在计划阶段启动服务。

- [ ] 浏览器RED先断言现状缺PA属性/新字段，再实现后逐项GREEN；每行有输入、保存POST/PATCH响应、GET、重载DOM与截图，不以toast作为落库证据：

| 场景 | 操作与真实断言 |
|---|---|
| 新PA | 新增、明确旧流程所需端口、gain空→0→21.25，分别应用/保存GET/reload；空为null、0不丢，来源/频段精确一致 |
| pad/combiner | 衰减/插损0与正值保存；负值、半频段/倒序拒绝；失败草稿仍可修正 |
| antenna/probe/reference_antenna | 正/负/0 gain_dbi保存；探头编号/极化及正常/校准模式不变；参考天线不进入正常路径 |
| CAICT旧PA | 清单选已有典型20dB边，ID/端点对应原图；改0与null重载；新来源可空；不生成新PA节点、不写chamber.pa_gain_db |
| 旧模板天线/CE/EMCenter | gain_dbi原15/3仍为旧版标称；不称实测；缺inputs/outputs不显示默认4/32，不显示固定PA×32 |
| 线缆/接收线缆 | 保留单一边损耗；节点提示转到邻边，来源可编辑；没有第二份节点损耗或自动重复补偿 |
| 元数据/取消 | 来源编辑后取消，草稿/GET都不变；应用后断网保存失败仍保留草稿，恢复网络重试保存与重载一致 |
| 无关旧图操作 | 未声明新字段的旧图只改名/拖动，GET不新增null标称键/metadata、不修改端口/引用/模式/典型值 |
| 引用保护 | 删除已有显式路径引用对象继续拒绝且草稿不变；非引用节点正常删除；不因新组件绕开原保护 |
| 采集/保存锁 | 用隔离真实API全Mock原采集入口，在实际pending/running窗口检查新控件/定位/应用/保存禁用；取消/完成恢复可编辑，Mock不得采用 |
| 跨Lab | dirty切Lab被阻止；清洁切乙只显示乙数据；手发甲topology+乙lab PATCH返回409，甲乙GET均不变 |
| 旧采用/历史 | 自动回归夹具中先建立原受信采集/采用再只改元数据，preview/冻结保持原资格；旧值/历史冻结未改；物理端口变更仍拒绝 |

真实GET例（端点/ID用fixture manifest解析，不硬编码生产ID）：

```js
const response = await page.request.get(endpoint);
if (!response.ok()) throw new Error(await response.text());
const saved = await response.json();
const pa = saved.nodes.find(n => n.label === 'PC04A4a新PA');
if (pa?.params.gain_db !== 0) throw new Error('显式零未原样落库');
if (pa.params.nominal_metadata.gain_db.source_note !== null) throw new Error('未知来源被伪造');
if (pa.params.nominal_metadata.gain_db.frequency_range_mhz !== null) throw new Error('未知频率被伪造');
```

- [ ] 后端计算反例：纯`TopologyService`同图边损耗2/0，分别设置节点gain=20、attenuation=3、gain_dbi=15与边PA=20，总损耗/矩阵保持2；已有calibrated_loss=0不能因此变成新标称值。正式链沿`tests/test_pc04a2_route_compensation.py::test_real_multihop_mixed_freeze_reaches_compensation_once`增加标称声明输入，仍精确断言原`want`只应用一次、端口/方法/参考面/来源不变。这些是合成transport测试，不标真机证据。
- [ ] 定点稳定后主代理唯一安排最终全后端（新输入新库，cwd=`api-service`）：

```bash
pc04a4a_full_dir=$(mktemp -d /tmp/pc04a4a-full-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a4a_full_dir/full.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4a_full_dir/logs" .venv/bin/python -m pytest tests -q
```

另跑Task2 GUI命令、`npm run build`、`git diff --check`。若全量出现基线历史文档G8误报，逐项与基线输入核实并报告实际统计，不修改历史记录、不称全绿；新失败必须定位，不能引用旧片的7485统计代替本片结果。保留输入SHA、dirty diff、依赖版本、命令、退出码、末行、日志路径。
- [ ] Task3审查与整片累计规格/质量审查完成后精确提交测试与验证摘要 `test: 验证标称参数真实保存与校准隔离`。停止本片创建的确切PID/会话，保留临时证据，不动用户服务；检查`git status`不加入原有venv/output。
- [ ] 由主代理创建Ready PR：附设计/本计划/验证摘要及Roadmap=PC-04A-4a；R1处理本片可执行项→R2，最新HEAD无P1后收口；R2仍有P1继续到修复被新一轮覆盖。P2/P3不自动扩入backlog。合并后安全同步main、更新正式roadmap及台账；才允许4b开工。

## 自查与交接

- [ ] 设计4a覆盖：PA与其他明确标称字段、单位/来源/范围、旧CAICT边定位、固定能力声明清理；4b端口角色、4c内部路径、4d转换及损耗归属不提前施工。
- [ ] 所有新字段的写入/读取/重新保存/模板/历史/冻结消费者已在0.2逐项定责；两个裁决建议已获主代理确认，否则不能开始相应代码。
- [ ] 纯计划交付不构成实现完成，不勾roadmap父项，不解除现场B/HOLD。
