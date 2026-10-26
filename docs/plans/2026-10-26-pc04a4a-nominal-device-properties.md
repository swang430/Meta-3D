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

### 0.3 两项已接受的范围裁决（2026-10-26 主代理确认）

1. **旧边 cable_loss_db 的空值不是局部表单问题。** 其schema为float默认0，路径求和/校验和正式binding仍依赖数值。已接受4a仅让新增节点标称字段与旧PA可空，旧边电缆损耗沿既有非空契约；可给其新增来源/频率元数据，不能新增节点线缆损耗第二份值。旧边可空化/损耗归属统一交给4d的专门审计。本片不得把用户在新字段清空转换为0，也不得宣称已解决所有旧缺测语义；不再要求用户重复确认。
2. **旧标称数值当前参与route_digest，新说明元数据不应参与。** 已接受本片只精确排除新`nominal_metadata`（节点与参考边两端），同时按1.2保形读写，保持没有该键的历史digest逐字节不变；不批量重算旧run，不改旧数值改变后的原有适用性判据。不能全量删掉旧gain键让所有存量digest失配。UI明确“数值修改可能触发原通路一致性复核；保存标称不等于采用校准”。

## 1. 契约与文件职责

### 1.1 字段表（单位为应用声明，不是仪器回读单位）

| 对象 | 值的唯一存储键 | 类型/范围 | 编辑入口 |
|---|---|---|---|
| amplifier | `params.gain_db` | finite number 或null，允许0与负数，不猜硬件量程 | PA标称增益(dB) |
| pad | `params.attenuation_db` | finite number≥0 或null | 标称衰减(dB) |
| combiner | `params.loss_db` | finite number≥0 或null | 标称插损(dB) |
| probe / antenna / reference_antenna | `params.gain_dbi` | finite number 或null，允许负增益 | 标称天线增益(dBi) |
| 旧PA边 | `connections[i].pa_gain_db` | 新增/变更只接受finite number或null；相同作用域旧原值兼容保形，见1.2；0保留 | 连线抽屉“旧PA标称增益(dB)”；可从PA边清单定位 |
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

### 1.2 类型安全读取与保形保存（F1/F2/F4修订后的单一路径）

不创建摘要版本机制，不取消既有响应数值规范化，不根据“等于默认值”猜用户意图。连接字段存在性来自**存储连接JSON→真实GET连接仅输出已存字段（值仍按原schema规范化）→草稿保留缺键→原始PATCH请求**。节点/模式/顶层保留既有响应，包括安全默认params对象；不把整张图改成raw或全域稀疏协议。旧typed数值字符串的规范化回传与用户主动重申同一数值无法单靠数值区分，因此只增加一个局部PATCH意图字段 `connection_numeric_declarations`；不建立通用JSON Patch/迁移平台。

1. `TopologyConnection.pa_gain_db` 改成 `JsonValue = None`（Pydantic），不做before数值拒绝或强转；这是兼容传输类型，不是新值业务许可。schema description明确：POST/import及PATCH新增/变更值只能finite number/null；PATCH仅允许与本Lab旧行同ID同键、JSON类型和值均相同的历史值原样保留。Node的params仍是原始字典；边新增`nominal_metadata: JsonValue = None`，保留原始JSON到写校验，不能在请求模型里先把频率string/bool转float。公开请求/响应schema如实呈现兼容JSON类型；不能手写“只接受number”伪契约。手写TS传输字段对应`JsonValue`，数值展示用`typeof === 'number' && Number.isFinite`收窄。
2. **撤销全图raw覆盖与局部JSONResponse帮助函数。** 五端GET单条/GET列表/POST/PATCH/import继续原response_model，只在`SwitchTopologyResponse.connections`加JSON模式field_serializer，对每条已验证Connection调用`model_dump(mode='json',exclude_unset=True)`。连接缺键不补默认；节点/模式/顶层序列化完全不变。已有`cable_loss_db="2.5"`/`calibrated_loss_db="0"`仍返回number 2.5/0.0，CustomEdges.toFixed安全。列表items复用同一Response，POST仍201、其它鉴权/作用域/分页/响应错误不变。只有本片PA/metadata改JsonValue并收窄消费者，不放宽其它typed字段。不能使用exclude_defaults，它会删掉明确存储的0/null/default端口。
3. GUI已核对：`switchTopologyService`直接返回`response.data`，`TopologyFlow`的`useState(topology)/setDraft(topology)`、边/节点抽屉spread、`topologyDraft.ts::updateDraftConnection`均未给边补默认；`initialEdges`的显示对象不写回draft。**唯一额外归一化点是handleSave把ReactFlow默认position写回所有可见节点**，本片收窄为直接保存`draft.nodes`：真实拖动结束已由`handleNodesChange`写入draft，原未声明位置不能因保存标称就补`{x:0,y:0}`。渲染需要默认时只读取，不写回。NumberInput/Select默认显示不是输入事件。用户实际编辑字段时才写键：包括显式0/null/默认端口字符串；只关闭/取消/改名不写缺省字段。旧PA非数值显示“旧值格式未核实（原值只读）”，未编辑则保留原JSON；主动输入新值后严格验证，不自动把字符串转数字。
4. API新增局部async依赖`_raw_topology_body(request: Request) -> dict`读取`await request.json()`；POST/PATCH原函数保持同步，以`Depends`拿到原始对象，不改变SQLAlchemy执行模型。原请求模型仍验证通用结构，但PA与新metadata不提前做有损转换。PATCH先`_resolve_scope/_load_scoped_topology`，再使用原始body与该旧行逐对象ID比较，调用统一`validate_nominal_write`。POST/import无previous，一律新值严格；错误在任何删/写前422。
5. 保存使用原请求模型`model_dump(exclude_unset=True)`候选。节点/模式仍用严格原值保留函数；连接按ID调用`preserve_connection_rows`：先比较raw请求与raw旧值，再对**四个已有typed数值字段**比较raw请求与同一TopologyConnection模型规范化的旧值。两者之一相等且没有对应明确声明标记时恢复旧原表示；不同则保存本次规范化值。只有previous本来存在该键才允许规范化等价保留，缺键→0/null/default端口仍是新增真实声明。任何已知字段从请求删除即按原数组替换删除，不能从previous补回。原来GET不暴露的连接扩展键不视作用户删除：服务端只保留previous中不在TopologyConnection.model_fields的opaque键，不允许本片新增/更改这些键；这是避免无关旧摘要漂移，不提供扩展属性编辑能力。
6. JSON严格判等先比存在性与类型（bool不同number、string不同number）；number域允许int/float数学相等，未明确重新声明时恢复原表示。PA不使用“规范化等价”，仍按F1原始类型校验，1→true拒绝、旧true→1允许明确修正。Metadata始终在原始值上严格验证，没有坏值豁免。
7. PATCH新增 `connection_numeric_declarations: dict[str, list[Literal['cable_loss_db','cable_length_m','calibrated_loss_db','calibrated_phase_deg']]] = {}`，仅声明本次用户确实要写的数值字段；服务端必须验证ID属于本次connections、字段在本次raw连接中确实存在、列表不重复、键在白名单。标记只取消“规范化等价保留”，仍经所有旧结构/新标称校验，不能绕过Lab/身份门。该字段不持久化进拓扑、不进入摘要、不返回给客户端。直接API用户若要把旧字符串改成相同显示number，显式带该标记；否则按“保留旧表示”约定处理，不静默声称已改类型。
8. GUI仅在两个原可写NumberInput（cable_loss_db/cable_length_m）实际onChange后记录选中边的声明键；抽屉局部集合随取消丢弃，应用才合并到draft的独立意图map；清洁GET/reload清空，保存失败保留，成功清空。校准数值仍只读，不产生声明。没有真实事件不标记；即便改后又回到同显示值，意图map保留到应用，服务端按明确声明保存。删除边同时删除它的意图键；禁止让旧Lab或失败后的旧行意图串到新图。新增PA与metadata无此歧义，不加入该清单。

最小函数形状（位于`topology_nominal.py`，仅复用本片保存链；`MISSING`是私有sentinel，非JSON值）：

```python
MISSING = object()

def same_json(left, right):
    if left is MISSING or right is MISSING:
        return left is right
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right  # bool被精确type排除；调用前拒绝非有限新数值
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json(a,b) for a,b in zip(left,right))
    return left == right

def validate_changed_number(raw, previous, *, key, nonnegative=False):
    if raw is MISSING or same_json(raw, previous):
        return
    validate_number(raw, key=key, nonnegative=nonnegative)

def _preserve_unchanged_json(raw, normalized, previous=MISSING):
    from copy import deepcopy
    if same_json(raw, previous):
        return deepcopy(previous)
    if isinstance(raw, dict) and isinstance(normalized, dict):
        old = previous if isinstance(previous, dict) else {}
        result = {}
        for key, value in raw.items():
            prior = old.get(key, MISSING)
            if same_json(value, prior):
                result[key] = deepcopy(prior)
            elif key in normalized:
                result[key] = _preserve_unchanged_json(value, normalized[key], prior)
        return result
    if isinstance(raw, list) and isinstance(normalized, list):
        old = previous if isinstance(previous, list) else []
        return [_preserve_unchanged_json(value, normalized[i], old[i] if i < len(old) else MISSING)
                for i, value in enumerate(raw)]
    return deepcopy(normalized)

def preserve_graph_rows(raw_rows, normalized_rows, previous_rows):
    # 调用前原写结构验证已保证列表/ID有效、唯一及两次解析长度一致。
    old = {row['id']: row for row in previous_rows or []}
    return [_preserve_unchanged_json(raw, normalized, old.get(raw['id'], MISSING))
            for raw, normalized in zip(raw_rows, normalized_rows)]

CONNECTION_NUMERIC_FIELDS = {'cable_loss_db', 'cable_length_m',
                             'calibrated_loss_db', 'calibrated_phase_deg'}

def preserve_connection_rows(raw_rows, normalized_rows, previous_rows, declarations):
    from copy import deepcopy
    old_by_id = {row['id']: row for row in previous_rows or []}
    saved = []
    for raw, normalized in zip(raw_rows, normalized_rows):
        old = old_by_id.get(raw['id'], {})
        # 原字段模型负责已有类型规范化；PA/metadata为JsonValue，无新增强转。
        old_normalized = (TopologyConnection.model_validate(old).model_dump(exclude_unset=True)
                          if old else {})
        result = {key: deepcopy(value) for key, value in old.items()
                  if key not in TopologyConnection.model_fields}
        declared = set(declarations.get(raw['id'], []))  # 此前已严格校验清单
        for key, value in raw.items():
            if key not in normalized:
                continue
            prior = old.get(key, MISSING)
            equal_raw = same_json(value, prior)
            equal_display = (key in CONNECTION_NUMERIC_FIELDS and key in old
                             and same_json(value, old_normalized[key]))
            result[key] = (deepcopy(prior) if key not in declared and (equal_raw or equal_display)
                           else deepcopy(normalized[key]))
        saved.append(result)
    return saved
```

API接线形状：`raw_body`经依赖得到；`typed = request.model_dump(exclude_unset=True)`；`validate_nominal_write`使用raw与作用域内previous；验证并从typed删除意图map（禁止原setattr循环误写），connections调用`preserve_connection_rows`，nodes/operating_modes调用`preserve_graph_rows`。无previous的POST保存原请求存在性，不补缺省；模板通过相同校验后保持原始dict。新metadata校验后仅对明确编辑生成规范化对象；非法metadata不能因保形豁免。此局部连接保存帮助函数放在已有`app/api/switch_topology.py`，避免schema模块反向import自身形成循环；其余纯标称校验仍在topology_nominal.py。

响应修订只有以下形状（五端和列表items复用该响应模型，不改decorator或返回对象）：

```python
class SwitchTopologyResponse(SwitchTopologyBase):
    # 原字段保持；只新增该JSON序列化方法。
    @field_serializer('connections', when_used='json')
    def serialized_connections(self, connections):
        return [connection.model_dump(mode='json', exclude_unset=True) for connection in connections]
```

保形断言覆盖参考边的原有键形态和typed旧值表示，不只排除metadata；不删旧摘要键/重算历史。稀疏但类型安全的响应消除补默认，服务器等价恢复与显式意图map分别处理“未改显示值”和“明确重申”。这一个意图位不可由纯数值比较推导；不增加map就只能吞明确重申或让未改旧字符串导致摘要漂移。

| 原存储 → 原始请求 | 判据与保存策略 |
|---|---|
| 缺键→仍缺键 | 不插入模型默认值，保持缺键 |
| 缺键→显式null（PA）/0/默认端口`out` | 是新增声明，按字段规则严格验证后保存，不能按默认删除 |
| null→0 / 0→null（PA） | 是实际修改，保存准确值；旧电缆null仍由原契约拒绝 |
| 数值0→解析后0.0，但原始请求仍为0 | 同一JSON number，保留存储0表示，避免摘要漂移 |
| 旧cable_loss字符串`"2.5"`→GET number2.5→PATCH number2.5，无声明标记 | 类型安全显示；原字段规范化等价，保存仍为旧字符串，摘要不变 |
| 同上但用户真实onChange并声明该键 | 保存规范化number2.5，是明确重申；对应旧身份变化不隐藏 |
| 旧calibrated_loss字符串`"0"`→GET number0→无标记回传 | 显示0而非崩溃，保存仍为旧字符串；GUI该字段仍只读 |
| 旧cable_loss字符串`"2.5"`→PATCH number0 | 与旧规范化值不同，直接保存0，不要求标记且不能恢复旧2.5 |
| 数值1→原始true | boolean不同number，严格校验拒绝，不吞修改 |
| 旧字符串`"12"`→原样`"12"`，只改名 | 同作用域同ID原值保留；读取也不强转成12 |
| 旧字符串`"12"`→`"13"` / 新PA=`"12"` | 新坏值422，原行原子不变 |
| 旧字符串`"12"`→数值12 | 明确修正成合法新值，保存number；旧数值摘要门仍生效 |
| 旧键→请求删除该键 | 按原全数组替换删除，不从previous复原被删键；真值改变产生的旧身份变化不隐藏 |
| metadata新增或修改 | 在原始值校验unit/source/range；bool/string频率拒绝；校验后仅用于说明，身份副本排除新键 |

原始请求是**意图/存在性/标称类型**的唯一源；Pydantic结果仅用于原有其它字段的结构验证和规范化，不能反向覆盖意图。previous只允许来自当前请求的Lab作用域及同ID行，不从客户端传入或跨Lab查找。

### 1.3 文件分工

- 新建 `api-service/app/schemas/topology_nominal.py`：`NominalFieldMetadata`、支持键/单位表、纯写校验；不导入ORM/HAL。
- 修改 `api-service/app/schemas/switch_topology.py`：PA/新metadata原始JSON传输及准确schema说明；节点params保留扩展字典以兼容旧记录，不设会提前挡旧值的数值validator。
- 修改 `api-service/app/api/switch_topology.py`：原始请求依赖、连接数值声明清单验证、所有写入口作用域内标称校验与保存保形；不把新校验放到GET。
- 修改 `api-service/app/services/calibration/route_calibration.py`：只排除新说明元数据，原历史摘要及物理身份校验不变。
- 新建 `gui/src/features/TopologyEditor/nominalProperties.ts`：字段描述、空值解析、不可变写入与显示标签纯函数；不计算正式补偿。
- 新建 `gui/src/features/TopologyEditor/NominalPropertyFields.tsx`：可复用标称数值/来源/频段表单，接收`disabled`；不自发PATCH。
- 修改 `TopologyEditor.tsx`、`CustomEdges.tsx`、`CustomNodes.tsx`、`gui/src/api/switchTopologyService.ts`：原入口接线、旧PA定位、标注及类型镜像；不拆其它编辑器功能。
- 修改 `api/openapi.yaml`、生成 `gui/src/types/api.generated.ts`；测试放任务各自列出的文件。`topologyDraft.ts`只复用，若无必须改动不触碰。

## 2. Task 1：类型化写入、真实往返与元数据身份边界

**Files:** 上述三个后端schema/API文件、`route_calibration.py`；`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`switchTopologyService.ts`；`TopologyEditor.tsx`/`CustomEdges.tsx`仅传输类型收窄与原数值控件意图接线，不新增PA表单；新测试 `api-service/tests/test_pc04a4a_nominal_properties.py`、`api-service/tests/test_pc04a4a_nominal_identity.py`、`gui/test/topologyNominalTransport.test.ts`。

**Interfaces:** `validate_nominal_write(nodes, connections, *, previous_nodes=None, previous_connections=None) -> None`消费原始JSON，错误抛ValueError由API转422；`same_json`、`_preserve_unchanged_json`、`preserve_connection_rows`、`_raw_topology_body`按1.2接线。TS `TopologyUpdatePayload`在原Partial图类型外加 `connection_numeric_declarations?: Record<string, ConnectionNumericField[]>`（四键联合）；不是SwitchTopology存储/响应字段。`NominalFieldMetadata`只在作用域内纯写校验阶段构造，不增加端点。

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
from pydantic import BaseModel, ConfigDict, field_validator

class NominalFieldMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    unit: Literal['dB', 'dBi']
    source_note: str | None = None
    frequency_range_mhz: tuple[float, float] | None = None

    @field_validator('frequency_range_mhz', mode='before')
    @classmethod
    def strict_range(cls, value):
        if value is None:
            return None
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in value)
                or value[0] > value[1]):
            raise ValueError('频率范围必须为两个有限正数且起点不大于终点')
        return value

def validate_number(value, *, key, nonnegative=False):
    if value is None:
        return
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f'{key} 必须为有限数值或null')
    if nonnegative and value < 0:
        raise ValueError(f'{key} 不得小于0')
```

`NominalFieldMetadata`只在作用域内纯写校验阶段以原始对象构造，频率before校验在这里拒绝bool/string，不在request模型提前强转；unit/source也在原始对象检查，source只允许str/null。PA模型改`JsonValue`保原类型，**不保留旧计划的TopologyConnectionWrite before数值门**。按1.2实现原始请求依赖、保形响应与保存函数；source_note字符串trim与空串→null属于本次明确编辑的规范化，未改旧值不得因此被重新格式化。

- [ ] 在create/update/import写前统一调用；旧字段按1.2严格比较（存在性、JSON类型、值），缺键不同于null、boolean不同number。覆盖：POST合法/非法、PATCH清空、错误单位、半频段/反向/0/负数/bool/string频率、非法元数据键、模板非法且replace=true原行保留、GET/list旧PA原类型保留、旧异常值改名可存但变更异常值拒绝、1→true拒绝、true→1合法修正、跨Lab409。旧坏值fixture只为初始化历史原形可直接入隔离DB；读/改/保存断言必须经真实HTTP，不能在断言阶段直接ORM修改替代生产入口。

- [ ] 先写元数据不影响摘要的真实路径正例，复用 `test_pc04a2_route_selection.py` 的`client/configured/graph/db_session/paths`；先复现GET→原样PATCH默认扩入的RED，再加入以下真实HTTP元数据正例（同样覆盖正常节点、参考节点、参考边三条路径）：

```python
def test_source_metadata_does_not_change_existing_route_identity(client, configured, graph, db_session):
    before = paths(client, configured, graph).json()[0]
    url = f'/api/v1/switch-topologies/{graph.id}'
    scope = {'lab_profile_id': str(configured.id)}
    fetched = client.get(url, params=scope)
    assert fetched.status_code == 200, fetched.text
    raw = fetched.json()
    assert raw['connections'] == graph.connections  # 此fixture是稀疏且无旧数值字符串的连接
    payload = {k: copy.deepcopy(raw[k]) for k in ('nodes','connections','operating_modes')}
    ref = next(n for n in payload['nodes'] if n['id'] == 'reference1')
    ref['params']['nominal_metadata'] = {'gain_dbi': {
        'unit': 'dBi', 'source_note': '目录待核', 'frequency_range_mhz': None}}
    saved = client.patch(url, params=scope, json=payload)
    assert saved.status_code == 200, saved.text
    reloaded = client.get(url, params=scope)
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()['connections'] == raw['connections']
    assert reloaded.json()['nodes'] == payload['nodes']
    after = paths(client, configured, graph).json()[0]
    assert after['route_digest'] == before['route_digest']
    assert after['calibration_nodes'][0]['params']['nominal_metadata']['gain_dbi']['source_note'] == '目录待核'
```

该文件显式导入copy与fixture/helpers。真实API矩阵：①无改动/只改图名→连接存储JSON串保形、旧摘要不变（HTTP返回typed数值，不要求返回旧字符串）；②缺键→显式out/0/null必须保存并允许旧身份变化；③删除已知可选键/重排数组准确反映请求；④旧cable_loss_db="2.5"、calibrated_loss_db="0"→GET/POST/PATCH/import/list响应合法number，无标记回传恢复旧字符串且摘要不变；⑤同显示值带声明标记→保存number，真实0/不同数值不带标记也保存；⑥非法/重复/不存在ID或未提交键的声明清单422；⑦旧opaque扩展不被GET遗漏导致删除或泄露。五端类型/作用域/状态码保留原契约。节点/模式不作全域raw保形承诺，不改既有类型安全默认。

- [ ] 只从`identity_nodes`的params与`calibration_connections`的摘要副本删除新`nominal_metadata`键，原`nodes/connections/calibration_nodes/calibration_connections`快照保留原始完整对象；不修改存储数据，不删其它旧键。新增元数据以前的同一图摘要必须不变。对端口/CE映射/参考天线身份变化仍按原门拒绝；运行旧 `test_cosmetic_change_only_warns_but_changed_port_is_incompatible`。
- [ ] 补checked OpenAPI上述CRUD范围及依赖schemas，保留其它路径原样；隔离环境导入`app.openapi()`提取该闭包，使用apply_patch更新yaml；`gui`运行`npm run openapi:generate`，不要整份live spec覆盖checked文件。新测试逐个比较相关schema/path与live，并验证真实response含字段；手写传输类型的`pa_gain_db?: JsonValue`及metadata原始JSON契约一致，表单只输出已收窄的number/null与明确metadata。`NominalFieldMetadata`用于校验与形状说明，不因未被直接request引用就伪称已自动出现在live闭包。
- [ ] Task1同步完成必要消费收窄与build：`CustomEdges`/箭头颜色先用`typeof value==='number' && Number.isFinite(value)`判断PA，不能继续用`as number`冒充运行时判据；非PA损耗仍由既有响应保证number，不扩成宽松显示。两个旧数值输入的真实onChange与取消/应用/保存失败生命周期按1.2意图map接线，清洁回传不生成标记；新PA表单仍留Task2。cwd=gui运行`npx --yes tsx --test test/topologyNominalTransport.test.ts test/topologyDraft.test.ts test/topologyHandleFreeze.test.ts`与`npm run build`，不能把契约中间态破坏留到Task2。
- [ ] GREEN后定点回归 `tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a3_topology_recovery.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_gui_contract.py`。每次同样显式新临时库/全Mock/default bootstrap。
- [ ] 变异实跑：临时移除写校验→非法写测试RED；临时恢复新元数据参与身份→元数据正例RED；恢复正确代码后GREEN。仅修改本片代码，用apply_patch还原，保存diff和测试末行，不用reset覆盖用户修改。
- [ ] 审查Task1后精确`git add`上述文件，提交 `feat: 补齐拓扑标称参数写入契约`；不push，等待整片验证。

## 3. Task 2：原抽屉标称字段、旧PA定位与真实标注

**Files:** 新`nominalProperties.ts`/`NominalPropertyFields.tsx`；修改`TopologyEditor.tsx`/`CustomNodes.tsx`/`CustomEdges.tsx`；新`gui/test/nominalProperties.test.ts`；本任务先建立`api-service/tests/pc04a4a_browser_fixture.py`、`gui/test/pc04a4aNominalProperties.browser.js`、`gui/test/pc04a4a.vite.config.ts`作为浏览器RED前置，Task3沿用而非再创建。

**Interfaces:** `nominalFieldsForNode(type: string): readonly {key:string,label:string,unit:'dB'|'dBi',nonnegative:boolean}[]`；`parseOptionalNominalNumber(value: number|string): number|null`；`setNodeNominal(node, key, value, metadata): TopologyNode`；`setEdgeNominal(edge, key, value, metadata): TopologyConnection`。组件props为`fields, values, metadata, disabled, onChange(key,value,metadata)`，数值与元数据一次回调、不请求网络。

- [ ] **先于任何Task2生产GUI改动**执行4.0的fixture/代理前置与启动命令，保留Task1完成后的精确SHA与dirty测试文件清单（不是回退到共享旧HEAD）。先用真实GET确认隔离CAICT旧PA边存在、页面已加载，然后浏览器打开原连线抽屉，断言`getByLabel('旧PA标称增益 (dB)', {exact:true})`可见；基线应因该控件不存在RED，留DOM/截图/失败断言。新数值字段只需同一缺功能RED，不把服务/fixture/selector拼错当成功取证。记录退出码及数据manifest，随后关闭本次专用服务或明确保留其PID，再开始下面GUI实现；不修改/回退已完成Task1。Task3只做最终GREEN。

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
- [ ] 按1.2收窄`handleSave`为发送`draft.nodes`，保留`handleNodesChange`真实拖动落草稿；验收“仅编辑元数据不从ReactFlow覆盖草稿位置或注入视图坐标”和“真实拖动后新position保存”。节点既有typed响应可给出`position: {}`并随草稿保存，不要求存储缺键继续缺键，不扩展节点序列化范围。边和模式不额外追加前端默认字段；显示旧PA坏值时数值组件不自动触发onChange重写。
- [ ] 节点抽屉嵌入组件，仅选中的节点落草稿；连线抽屉新增旧PA字段及元数据。提供“含旧PA标称的连线”清单（`pa_gain_db !== null && !== undefined`，含0），显示边ID与两端标签/端口，点击调用提取的`openConnection(id:string)`并高亮同一条边，不能按节点名猜PA归属。沿现有`handleEdgeClick`同源打开逻辑，隐藏/非当前模式边仍可通过清单定位，明确所属模式；不自动改模式或创建PA节点。
- [ ] 所有表单控件与定位/应用入口读取`editingBlocked`；打开后进入采集/保存也锁住。原取消行为保留草稿；节点metadata不因关闭抽屉浅引用泄漏。采集失败/取消后锁恢复由原busy链驱动，不另建定时器。
- [ ] 修正PA显示与箭头颜色的真假判断，0及负数不丢。PA净值只为标称显示，明确非实测；不写回`calibrated_loss_db`。校准字段维持只读、校准值0优先；不改变旧校准采用入口。
- [ ] 移除`CustomNodes.tsx`的CE默认4/32和EMCenter“集成PA ×32”断言，保留用户label；不把端口handles数当硬件端口数。旧inputs/outputs即便非空也写“旧声明：…，未核实”；缺失写“端口数量未声明”。保留原handles与布局，不在4a加入角色编辑、`num_ports`同步或新端口数量推导。
- [ ] GREEN：`npx --yes tsx --test test/nominalProperties.test.ts test/topologyDraft.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts`；`npm run build`。核心变异把null/0处理换成`value || null`应RED；恢复后GREEN。
- [ ] Task2规格/质量审查后精确提交 `feat: 支持器件标称属性与旧PA边编辑`。不用无关重构消除已有lint/build警告。

## 4. Task 3：真实API浏览器与完整回归收口

**Files:** 沿用Task2已建立的 `api-service/tests/pc04a4a_browser_fixture.py`（只造隔离数据）、`gui/test/pc04a4aNominalProperties.browser.js`、`gui/test/pc04a4a.vite.config.ts`（只测试专用代理）；新增 `docs/validation/2026-10-26-pc04a4a-nominal-properties.md` 实际验证摘要；完成后只更新roadmap本片状态/计划复选框。

**Interfaces:** fixture输出`{database,labs:[{name,lab_id,topology_id}],caict_topology_id}`；浏览器脚本沿现有`async page=>{...}`，只发真实HTTP、不伪造APIresponse、不调用前端mockServer。所有证据存本次临时目录，文档只保留可核验摘要/相对归档引用。

### 4.0 浏览器前置规范（Task2实现前先执行一次RED，Task3用新库执行GREEN）

Task2用apply_patch创建专用fixture，复用 `tests/pc04a3_browser_fixture.py` 的默认bootstrap类别/全部driver_mode=mock、文档网段、两Lab独立暗室做法，不导入执行旧fixture。导入app之前验证`DATABASE_URL`严格匹配`sqlite:////tmp/pc04a4a-[A-Za-z0-9]+/browser.sqlite`、文件不存在、父目录存在、两个环境开关均true；失败立即退出。默认bootstrap仍运行，所有类别和Lab binding再次断言mock。准备正常显式两链图及经真实模板导入的CAICT旧图，不复制用户库/历史证据；另有缺默认字段的参考边，保证能验保形。浏览器操作前后存manifest和真实GET。

Task2/Task3分别使用全新目录与对应阶段的精确输入SHA，运行同样命令。确认独占端口（占用则选另一个并同步测试配置，绝不kill用户服务）：

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

### 4.1 最终GREEN及收口

- [ ] 确认Task2已保存缺功能浏览器RED证据，再在最终Task1+Task2输入上用全新隔离库逐项GREEN；不在此时追补基线RED，不回退共享工作树。每行有输入、保存POST/PATCH响应、GET、重载DOM与截图，不以toast作为落库证据：

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
- [ ] 所有新字段的写入/读取/重新保存/模板/历史/冻结消费者已在0.2逐项定责；0.3两项范围裁决已接受，不再重复请求用户确认。F1/F2修订方案仍需原reviewer增量核验后才进入实现。
- [ ] 纯计划交付不构成实现完成，不勾roadmap父项，不解除现场B/HOLD。
