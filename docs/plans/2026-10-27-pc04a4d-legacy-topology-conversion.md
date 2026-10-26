# PC04A4d 旧拓扑显式转换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL：使用 `subagent-driven-development` 串行执行 Task 1～4，各任务独立规格/质量审查，最后累计审查；实施者不再派子代理。本文目前仅为待独立审查的实施计划，不表示生产已实现。

**Goal:** 旧 CAICT 导入图及已有图由操作员明确补充声明并先看变更预览，原子保存时保留身份和引用；未知线缆损耗不再伪装为零，也不新增重复补偿源。

**Architecture:** 保留原拓扑 JSON、节点/边/模式 ID、原 PATCH 与原编辑器；增加局部转换操作清单和只读预览，确认时服务器重建并验证同一候选。损耗仍只存原外部边，节点不新建第二份数值；不拆集成 PA、不自动推物理图、不批量迁移数据库。

**Tech Stack:** FastAPI/Pydantic、SQLAlchemy JSON、React/TypeScript/Mantine、pytest/tsx；无新依赖、数据库表、SCPI 或驱动。

**Spec:** [已批准设计](../design/2026-10-26-topology-device-port-contract.md)、[正式队列](../roadmap-first-call.md)、[4a 的 0.3 范围裁决](2026-10-26-pc04a4a-nominal-device-properties.md)。分支 `codex/pc04a4d-legacy-topology-conversion`，基线 `39d4bb0bc27ab6e13eca04ec0f7b4c82f14eb46a`。前置 PR #541 已于 `2026-10-26T22:31:48Z` 合并；[R2 回执](https://github.com/swang430/Meta-3D/pull/541#issuecomment-6428803419)覆盖 `fd473fba1cbad208f5604d4f2465279dab39ba7b` 无发现。4c 的 7822 passed/17 skipped/1 历史 G8 failed 仅属前片证据，不当作本片结果。

## Global Constraints

- 旧记录不批量改写；缺角色/参数显示旧版未声明。用户显式转换前提供变更预览；不更改历史执行或已有证书。正常旧图的无关改名/位置保存不得被新契约误伤。
- params.ports 继续是端口 ID 清单；端口不是左右接点数量。名称不隐式决定方向。角色独立为 input/output/bidirectional/unknown；unknown 不冒充双向能力。
- 复用基站 port_roles 的 dl/ul 权威关系，不用通用角色覆盖它；新角色与其冲突必须拒绝，而非选一端。
- 图边为外部接线，器件内部连通关系独立声明。多端口器件不得默认全互通。开关继续复用现有 port_maps/switch_id/继电器身份，不新增第二套自动切换配置。
- 校准来源、原始采集和历史执行冻结保持只读；整链实测只在原采用入口生效一次。禁止额外叠加节点增益；声明、转换确认、标称完整都不是硬件能力或正式资格。
- 不改变真实端口映射、仪器绑定、certificate、历史 snapshot、confirmed application 或执行结果。配置变化提示复核，不自动撤销证书/强制重校准；当前执行不匹配仍走原门。
- 一条外部边保留一个损耗来源：已有 calibrated_loss_db（含0）优先，否则原 cable_loss_db；不相加。不增加 cable/receive_cable 节点损耗字段，不按数值相等猜“重复”，不把合成边拆成两条实物线缆。
- Python app 导入之前创建新临时 SQLite 并设置 `DATABASE_URL`、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`；默认 bootstrap 后显式设置并核查全部 category/Lab binding 的 Mock，不声称 bootstrap 自动全 Mock。不碰默认 DB、用户服务、旧样本；保留 worktree/venv/DB/output/scratch。
- Task4 是本片唯一最终全后端责任人；Task1～3仅定点相关。稳定共享输入变化才由同一责任位重跑；reviewer不因身份重复全量。历史G8核实后披露，不能改历史/门或称全绿。
- 每Task先真实生产入口RED，再最小实现/GREEN/核心变异恢复；GUI必须先真实API浏览器RED。完成独立审查后才下一Task。全部内审后 Ready PR，R1/R2覆盖最新SHA无P1才SHA约束合并，同步main保留用户修改。4e尚未启动，现场B/HOLD不解除。
- memory检索只作索引检查，本计划的接口事实以本次源码为准。NotebookLM不适用：无新仪器命令/能力断言；一旦需要厂商事实，暂停该推论查手册，不把CAICT dev-fixture注释当实测依据。

## 0. 审计结论与最小范围裁决

### 0.1 生产入口与消费全集

实施前重跑以下检索，将新增消费点归入下面关系，不借同名字扩修暗室独立字段：

```sh
git grep -n -E 'cable_loss_db|calibrated_loss_db|pa_gain_db' -- api-service/app gui/src
git grep -n -E 'ce_port|bse_port|sa_port|rf_path_selection|port_maps' -- api-service/app/services gui/src/features/TopologyEditor
git grep -n -E 'preserve_connection_rows|import_topology_from_template|update_switch_topology|active_unsafe_diagnostic' -- api-service/app
git grep -n -E '绝不|不许|禁止|must not|别把' -- api-service/app/api/switch_topology.py gui/src/features/TopologyEditor
```

| 入口→权威来源 | 正式消费者与本片责任 | 可观察断言 |
|---|---|---|
| `api/switch_topology.py` POST/PATCH/GET/list/import；`schemas/switch_topology.py`原始请求与connection serializer | Task1可空字段；Task2预览/确认复用`preserve_connection_rows`和最终图校验，before只来自同Lab数据库 | 缺键保持缺键，null不是0，旧numeric字符串无意图往返保持原JSON；422/409之前默认位/整行无变化 |
| `api-service/scripts/dev-fixtures/topology-templates/caict_v4.py::generate_topology_record`→原import | Task2/3原样导入后走同一转换；不改模板数值/型号/端点，不借replace删有历史图 | 预览、取消、打开页面不转换原图；旧导入JSON不自动新增ports/internal_paths |
| `TopologyEditor.tsx`外层加载/重导入与内层draft/handleSave | Task3同一入口，绑定lab/topology/source；转换不得先调用重导入 | dirty草稿先明确保存或取消转换；取消不丢草稿，换Lab/图清预览且旧响应不可覆盖新图 |
| `topologyDraft.ts`删除/改接；`topology_ports.py`、`topology_internal_paths.py`与`_validate_structure` | Task2/3复用完整最终图引用校验：全部模式、active_connections、边source/target/pins、probe.rf_path_selection.connection_ids/switch_mappings | 不偷删引用，不生成默认in/out；保留全部ID，改声明冲突列全相关边/探头 |
| `TopologyService.__init__/_dfs_paths/get_end_to_end_loss/get_calibration_matrix/validate/to_dict` | Task1保持原求和算法，边有效量未知则总量None；`SignalPathResponse.total_loss_db`同步可空 | mixed known/unknown不输出部分和；calibrated0优先；所有已知旧数据结果不变 |
| `switch_orchestrator.py::_build_probe_binding`→`rf_chain_resolver.py::_binding_to_spec` | Task1只替换truthiness/float-or-zero；保留现有终端边来源，不改为多段求和 | calibrated0不退到nominal；未知binding→未知chain，不悄悄drop链或补0 |
| `api/lab_profile.py::RFChainEntry`→`CalibrationScopeCard`、`RFChainDiagramPanel` | Task1 null序列化和展示“未知”，不调用None.toFixed | 列表保留身份，未知数值不崩/不显示0 |
| `calibration/configuration_scope.py`与`schemas/calibration_scope.py::ScopeChain` | Task1可空chain，不改scope版本/摘要算法；Task2转换声明按既有params摘要进入current | 旧已知原值摘要不变，null新声明可产生真实差异但只提示复核；历史baseline解析不查当前补值 |
| `path_loss_calibration_service.py::start_calibration_for_lab_profile`的chain.cable_loss_db公式/float消费者 | Task1缺量值在硬件lease前返回原失败结果，不生成测量/证书；后续单独参数cable_loss_db与chamber.typical_cable_loss_db不是同一来源 | 未知链不能执行`float(None)`或作为0；已知0照常工作；全部链先核再碰HAL |
| `route_calibration.py`/`fixed_route_method.py`/`fixed_route_acquisition.py`→`route_batch_plan.py`/jobs | Task1/4回归：request.receive_cable_loss_db仍独立操作员输入，不从拓扑nominal自动填 | 整链Lnet只算一次；已确认整链可用时不因无关nominal未知额外否定资格 |
| `route_calibration_freeze.py`→path_loss_preflight/measure→channel_engine_client | Task4生产回归，不改其资格/历史/正式补偿算法 | 原执行冻结与报告前后逐字一致；新执行按当前身份拒绝不匹配或沿原confirmed来源，不用标称代替confirmed |
| `TopologyEditor`旧number input、`nominalProperties`、`CustomEdges` | Task1/3清空送null，保留数值编辑意图；PA净值任一输入未知显示未知 | 显式0/空/缺键分开；不再`??0`/`||0`伪装缺测 |
| `topology_nominal.py::preserve_graph_rows`与4a metadata | Task1/2延续缺键/旧opaque保形；来源说明改变不擅改数值；不新增节点线缆数值 | 六类标称和旧PA/参考边只改说明时旧数值与route摘要不被补null |
| `models/chamber.py`、`channel_engine_client.py`、旧e2e服务的同名cable字段 | 不改独立暗室默认/旧演示数学；只核其入口不消费本次nullable RFChainSpec | 不能把本片扩成全校准算法清洗；若发现新增直接消费Nullable chain需纳入同根修复 |
| live Pydantic→`api/openapi.yaml`→`gui/src/types/api.generated.ts`→`switchTopologyService.ts`及真实响应 | Task1/2四镜像，生成TS不手改 | POST/PATCH/list/import/path/lab/scope契约均能真实序列化null |

### 0.2 损耗归属：不把转换变成补偿重构

当前通用路径按多边求和，正式旧binding取终端边；两者不是相同算法。本片保持它们各自原来源，只修未知/零值选择；**不把旧数值迁到任意邻边，不自动累加节点或中间边到正式binding**。已有非空cable_loss_db完整保留；用户显式清空才null，不因为旧0可能是默认就改写成null。

“一线缆单一归属”本片实现为：转换只提供原外部边的损耗编辑/来源展示，不提供节点第二份数值，不拆/合边、不复制数值；cable/receive_cable节点提示选择原连线编辑，并展示全部邻边ID/已有量值，提醒同一实物不得重复登记。两边是否同一实物无法从相同数值/节点类型证明，不自动去重或宣称机器已核实实物唯一。已有重复须操作员按实际接线修改原边后再预览；不创造“另一边0”的虚假测量。若要求跨边物理唯一的强制约束，需另行明确物理线缆身份与正式多段策略，不能在本片伪装已经做到。

### 0.3 明确的null契约

`TopologyConnection.cable_loss_db: float | None = None`；新缺键的运行值None，GET仍exclude_unset保留缺键。原已存数值（含0）和未改字符串表示保持。写入允许有限非负number/null；拒绝bool/NaN/Inf/负数及主动字符串写入，旧未改字符串的4a兼容保留。`calibrated_loss_db`既有有符号值允许负增益，不因本片改其数值域。

```python
def effective_connection_loss(connection: dict) -> float | None:
    value = connection.get('calibrated_loss_db')
    if value is None:
        value = connection.get('cable_loss_db')
    return None if value is None else float(value)
```

该helper仅消费已通过现有typed/schema处理的数据，不被拿来放行bool/坏字符串；DB旧坏值在现有诊断/响应边界报告错误而非补零。通用total_loss的任一hop未知则None/calibration_status维持missing；validate给出缺失边ID。正式chain的nullable只传播声明，使用其做旧单段扣除的校准方法在lease前拒绝未知；confirmed整链冻结计算不依赖它，不加额外门。

## 1. 转换接口与原子性

新增仅限应用声明的 `schemas/topology_conversion.py`、`services/topology_conversion.py`；没有迁移表/后台任务。请求模型均extra=forbid。

```python
class ConversionNodeEdit(BaseModel):
    node_id: str
    target_type: Literal['ce_port','channel_emulator','bse_port','communication_tester','sa_port','signal_analyzer'] | None = None
    ports: list[str] | None = None
    port_directions: dict[str, Literal['input','output','bidirectional','unknown']] | None = None
    port_roles: dict[str, Literal['dl','ul']] | None = None
    internal_paths: list[TopologyInternalPath] | None = None
    ce_port: str | None = None

class ConversionConnectionEdit(BaseModel):
    connection_id: str
    source_pin: str | None = None
    target_pin: str | None = None
    cable_loss_db: float | None = None

class TopologyConversionRequest(BaseModel):
    nodes: list[ConversionNodeEdit] = []
    connections: list[ConversionConnectionEdit] = []

# model_fields_set区分未提交与明确null；ports/directions/roles/internal_paths/pins/ce_port
# 明确null拒绝，不允许删除原声明；只有cable_loss_db明确null表示操作员撤销该标称数值。
def build_conversion(source: dict, changes: TopologyConversionRequest) -> dict: ...
def conversion_source_digest(source: dict) -> str: ...
```

- `TopologyInternalPath`使用本片schema局部严格二键模型（from_port/to_port），shape与4c一致；不导入不存在的模型。纯builder深复制原nodes/connections/modes，按ID精确替换白名单字段；每ID最多一项，空操作拒绝。所有未指名键原样保留。用户必须显式输入ports；从现存raw pin可展示“原保存声明”，但不自动列成已确认ports。`ports=None`缺省不表示删除。
- 改type只允许三组旧/新等价类型内切换，不能把PA变CE；保留原node ID/label/position/params。旧ce_port改channel_emulator若仅靠旧label取CE身份，必须显式提交ce_port；不可在服务端从label补。BSE port_roles保留权威；SA不补仪器category或测量能力。普通器件可补声明，不可借target_type改类别。
- 原source/target、边ID、mode ID/active_connections、probe_id/polarization、rf_path_selection、switch_id/mapping、calibrated_loss/phase/pa_gain、仪器绑定、默认位均不在操作白名单；需要改变这些应取消转换后沿原编辑器处理。预览展示这些保持不变的事实。
- 新端点 `POST /switch-topologies/{topology_id}/conversion-preview?lab_profile_id=...`：从同Lab当前原行读取，不从GET已默认化对象重建source；body为上述changes。返回 `{source_digest, changes, candidate:{nodes,connections,operating_modes}, differences:[{object_kind,object_id,field,before_present,before,after}], warnings:[str]}`。differences省略before仅在before_present=false；没有持久化、默认位改变或HAL动作。
- 预览先builder再用与PATCH相同的最终保形/结构/nominal/port/internal校验。坏输入422（含关联所有模式/边/探头），跨Lab404沿现有loader；warnings区分“未声明/仅操作员声明/配置变化需复核”，不把运行不可用称为非法草稿。
- 原 `SwitchTopologyUpdate`增加可选 `conversion: {source_digest:str, changes:TopologyConversionRequest}`。有此字段不能同时带其它更新字段（含connection_numeric_declarations），否则422；服务器读取当前原图重新核digest，失配409“原图已变化，请重新预览”，不是覆盖另一会话。digest仅用于本次并发保护，不进入校准摘要或历史身份。
- 确认阶段重建候选并复用原PATCH最终验证和事务；不信客户端candidate/differences。cable_loss显式意图由服务器根据changes生成原numeric declarations。仅这些数值变更解除4a等价保留；不对所有边一律重申。
- digest包含topology id、所属chamber、switch category以及原nodes/connections/modes，用现有JSON number规范一致序列化；排序对象键、不重排数组、不把缺键与null合并；预览到确认任何涉及图的变化均要求重预览。普通PATCH不要求digest，保留旧无关保存契约。
- 不新增HAL锁；转换提交复用既有 `execution_exclusion_guard.active_unsafe_diagnostic()`忙信号拒绝409，预览仍只读；不通过取消请求解除busy。GUI继续复用savingRef/collectionBusyRef及原activeWork跨Lab门。服务器现有普通CRUD没有相同guard，本片仅约束新增conversion路径，不冒称重构了所有编辑锁。

## 2. 串行任务与验收

### Task 1：未知边损耗贯通真实读写与数值消费者

**Files:** 新增 `api-service/app/services/topology_loss.py`、`api-service/tests/test_pc04a4d_loss_truth.py`；修改 `schemas/switch_topology.py`、`schemas/topology_nominal.py`、`services/topology_service.py`、`services/mimo_ota/switch_orchestrator.py`、`services/calibration/rf_chain_resolver.py`、`schemas/calibration_scope.py`、`api/lab_profile.py`、`services/path_loss_calibration_service.py`（均在api-service/app下）；`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts`、`gui/src/features/TopologyEditor/{TopologyEditor.tsx,CustomEdges.tsx}`、`gui/src/features/{LabWorkspace/CalibrationScopeCard.tsx,ProbeCalibration/components/RFChainDiagramPanel.tsx}`。

**Interfaces:** Produces `effective_connection_loss(connection: dict) -> float | None`；现RFChainSpec/ScopeChain/RFChainEntry.cable_loss_db及SignalPath.total_loss_db/response同步nullable。Consumes原4a保形与numeric declarations，不能改为全图raw响应。

- [ ] 先新增真实HTTP/实际resolver测试：建同Lab已知端口的直连/两段图，分别0/null/缺键/已有calibrated0/负calibrated；HTTP GET/list/PATCH/import/path/matrix/lab/scope不得崩或补0。核心断言内容：

```python
assert client.patch(url, json={'connections': cleared}, params=scope).status_code == 200
assert client.get(url, params=scope).json()['connections'][0]['cable_loss_db'] is None
assert effective_connection_loss({'calibrated_loss_db': 0, 'cable_loss_db': 5}) == 0
assert effective_connection_loss({'cable_loss_db': None}) is None
assert service.get_end_to_end_loss('ce', 'probe') is None
# 原测试fixture提供同Lab图/真实client；新增fixture在本测试文件显式实现，不改默认DB。
```

- [ ] 使用新目录环境运行 `.venv/bin/python -m pytest tests/test_pc04a4d_loss_truth.py -q`，先保存schema不接受null/零优先失败的RED原件，不接受仅import不存在作为唯一RED。
- [ ] 按0.3替换各消费方的错误零兜底；旧方法只在其确实需要chain loss的入口一次检查全部chain，返回原CalibrationResult失败，位于lease前；不禁用独立整链方法。GUI未改cable输入之前先真实浏览器清空并保存RED，再改为null和“未知”，PA净值不再扣默认0。
- [ ] GREEN运行新增测试与 `tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_rf_chain_resolver.py tests/test_pc_01a_calibration_scope.py tests/test_path_loss_calibration.py tests/test_path_loss_ce_sa.py tests/test_pc04a2_route_freeze.py`。`gui`运行 `npm run build`；记录实际命令/统计而非预设通过数。
- [ ] 分别回退零优先、None兜底两处核心变异应红；恢复后验证输入相同。提交 `fix: 保留拓扑线缆损耗未知与显式零值`，独立规格/质量通过后交Task2，不跑全后端。

### Task 2：服务器只读转换预览与原PATCH确认

**Files:** 新增 `api-service/app/{schemas,services}/topology_conversion.py`、`api-service/tests/test_pc04a4d_conversion.py`；修改 `api-service/app/api/switch_topology.py`、`api-service/app/schemas/switch_topology.py`、`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts`。不修改CAICT模板常量、历史证书或DB模型。

**Interfaces:** Consumes `effective_connection_loss(dict)`和既有 `_validate_structure/_validate_nominal/_validate_ports/_validate_internal_paths`；Produces §1请求/响应、`build_conversion(source,changes)`、`conversion_source_digest(source)`及service `previewConversion(id,labId,changes)` / 原`updateTopology`的conversion分支。

- [ ] HTTP RED从旧CAICT真实import、三种旧节点、显式端口合法图各起一组；记录原row/default/history hash。核心请求及断言：

```python
preview = client.post(f'{url}/conversion-preview', params=scope,
    json={'nodes':[{'node_id':'legacy_ce','target_type':'channel_emulator',
                    'ports':['P1'],'port_directions':{'P1':'output'},'ce_port':'B1.1'}],
          'connections':[]})
assert preview.status_code == 200
assert read_raw_graph() == before
p = preview.json()
assert client.patch(url, params=scope, json={'conversion':{
    'source_digest':p['source_digest'],'changes':p['changes']}}).status_code == 200
assert read_history_hashes() == history_before
```

- [ ] 落实§1纯builder及严格模型；preview与commit都验证最终候选，不在默认位更新后才失败。并发测试先preview→另一个PATCH改图→conversion409，原另一个写入保留。
- [ ] 负例逐项：未知ID/重复操作/额外字段、跨Lab、无CE声明改type、缺pin/孤立pair/方向矛盾、BSE权威冲突、受引用端口删除、全部模式引用、busy、伪造candidate/digest、确认重复旧digest。正例：unknown草稿、取消、仅元数据正常PATCH兼容、全部ID/opaque/损耗原值保留。
- [ ] 运行 `.venv/bin/python -m pytest tests/test_pc04a4d_conversion.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a4b_port_contract.py tests/test_pc04a4c_internal_contract.py tests/test_pc04a3_topology_recovery.py -q`；生成四镜像后build。回退stale比较和原图before保护各一项变异实红恢复。
- [ ] 提交 `feat: 增加旧拓扑显式转换预览与确认保存`，独立审查，Task3消费最终接口；不跑全后端。

### Task 3：原图转换面板与草稿/锁生命周期

**Files:** 新增 `gui/src/features/TopologyEditor/LegacyConversionPanel.tsx`、`gui/src/features/TopologyEditor/legacyConversionState.ts`、`gui/test/legacyConversionState.test.ts`、`gui/test/pc04a4dConversion.browser.js`、`gui/test/pc04a4d.vite.config.ts`、`api-service/tests/pc04a4d_browser_fixture.py`；修改 `TopologyEditor.tsx` 和 `switchTopologyService.ts`，不新建编辑画布。

**Interfaces:** Consumes Task2 `previewConversion`与PATCH conversion；Produces `conversionContextKey(labId:string, topologyId:string):string`、`buildConversionRequest(nodeEdits,connectionEdits):TopologyConversionRequest`。预览结果只留当前面板会话，不持久化到图params。

- [ ] 先新库bootstrap/显式Mock/真实API及专用代理；真实浏览器观察“转换旧配置”入口不存在为RED并保留DOM/截图/原始请求，不先改UI。初始fixture包括CAICT原图、旧ce/bse/sa与新声明对照、普通/参考cable、opaque及历史冻结样本，源图ID与展示图ID分栏。
- [ ] 使用原Mantine抽屉/Modal实现“编辑转换项→预览差异→确认保存”。显示raw保存端点/未声明警告、明确type选择、ports/方向/pair、旧损耗；不提供一键猜测/自动补齐。dirty时不自动覆盖，提示先原保存或关闭转换继续草稿。确认按钮必须有当前成功预览，编辑任一项即使改回也使预览失效；409保留输入供重新预览。
- [ ] 每个事件处理先查 `savingRef.current || collectionBusyRef.current`；不是只disabled按钮。预览中context变化丢弃迟到响应；外层换Lab/selectedSwitch/重导入同时清会话，保存成功通过原onSaved更新，失败保留输入与原图。
- [ ] helper测试明确断言取消/换图清预览但不改原draft，序列化未提交键不补null，null仅cable字段：

```ts
const request = buildConversionRequest([], [{connection_id:'wire',cable_loss_db:null}]);
assert.deepEqual(request.connections,[{connection_id:'wire',cable_loss_db:null}]);
assert.equal('source_pin' in request.connections[0],false);
assert.notEqual(conversionContextKey('a','g'),conversionContextKey('b','g'));
```

- [ ] 真浏览器先编辑→取消→预览→保存→GET同ID；再断网→失败→恢复重试、stale409、切Lab迟到响应、保存pending、采集running/取消未确认/终态释放后连续两次重入。采集全Mock只证明软件生命周期，不称实物停发。
- [ ] 运行 `node --import tsx --test test/legacyConversionState.test.ts` 和 `npm run build`，回退事件层busy保护/缺值null各一项变异RED恢复。提交 `feat: 在原拓扑编辑器预览并确认旧声明转换`，独立任务审查。不用Task3定点证据替代Task4矩阵。

### Task 4：综合闭环、最终全后端与正式交付文档

**Files:** 新增 `api-service/tests/pc04a4d_matrix_evidence.py`、`gui/test/pc04a4dMatrix.browser.js`、`docs/validation/2026-10-27-pc04a4d-legacy-conversion.md`；补Task1/2测试和Task3fixture；更新本文实际进度、`docs/roadmap-first-call.md`、设计状态与应用操作文档 `docs/产品特性/calibration-system.md` 的本功能入口说明。不得扩改历史算法宣传。

**Interfaces:** Consumes全部Task1～3生产HTTP/GUI和原单路/批采集/冻结读取，不生产新接口。Produces真实版本/输入/依赖/命令/统计/退出码及未验边界可核对的正式摘要。

| 矩阵 | 必验真实结果 |
|---|---|
| D01 | CAICT原import→预览取消原图不变→逐项显式声明保存；模板文件/hash不变；不是静默全模板转换 |
| D02 | ce_port/bse_port/sa_port保持ID显式改type；CE身份缺证据拒绝，BSE角色不覆盖，SA不增加测量资格 |
| D03 | 缺键/null/0/旧非空/typed旧字符串往返，旧calibrated0优先；多hop未知总值None，GUI无None/0假值 |
| D04 | 六种标称/参考PA只改来源保形；cable节点无第二数值，所有邻边值列明，集成PA边不拆分 |
| D05 | 多模式、显式probe路径、内部pair、switch mapping引用冲突原子422；默认位与所有历史hash不变 |
| D06 | preview零DB写零HAL；错误scope404，stale409及同default重导入保护不变 |
| D07 | 草稿取消/保存失败/断网恢复/换图/换Lab/迟到响应，实际操作对象ID、请求ID、DOM一致 |
| D08 | 保存pending、单路/批采集running、取消未确认锁定；软件释放后两次编辑保存重入 |
| D09 | 普通与参考单路/批预览和Mock采集保持；未声明/未知拒绝不授资格；固定直连零switch I/O |
| D10 | 转换前已有执行冻结/报告读取下载不变；转换后新执行按当前身份校验，原confirmed整链只采用一次 |
| D11 | 旧需chain loss方法未知在lease前失败，已知0通过；独立confirmed整链不因无关nominal未知被挡 |
| D12 | 原编辑器真实鼠标移动、显式应用/保存重载、删除引用拒绝；本片证据独立，不冒称补验4c的C07历史 |

- [ ] 新建独立浏览器库，执行D01～D12；每组保存请求/响应/GET、SQL前后、截图与对象身份。客户端不route mock；隔离fixture不是现场数据；模拟不进入正式PASS。
- [ ] 运行新增两测试及消费者相关集、GUI测试/build，稳定后冻结全部源码/测试/fixture/契约/依赖输入。只有本Task责任位执行以下最终全量：

```sh
pc04a4d_run=$(mktemp -d /tmp/pc04a4d-final-XXXXXX)
cd api-service
env DATABASE_URL="sqlite:///$pc04a4d_run/full.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4d_run/logs" .venv/bin/python -m pytest tests -q
```

- [ ] 留存stdout/stderr与exit、输入起止hash/依赖/HEAD。若G8仍同历史引用，独立核文件及门基线未变后披露，不改门不称全绿；其它失败定位生产或测试契约，不擅改预期凑绿。修复影响稳定输入则由本责任位唯一补跑。
- [ ] 更新正式验证摘要并列未验项；服务关闭只用已核PID/session，保留全部证据。提交 `test: 验证旧拓扑显式转换与损耗边界`，独立Task4审查→累计基线至HEAD审查→Ready PR R1/R2；通过merge后才4e。

## 3. 计划自查与交接

- [ ] 独立计划审查批准前禁止生产实现；审查重点是nullable所有消费者、原型转型CE来源、最终候选引用原子性、预览stale与busy边界，以及0.2对物理单一归属的真实承诺范围。
- [ ] 每任务brief附本文全局约束、exact接口与上一任务最终SHA/report；不只转任务标题。
- [ ] 模板/旧图显式转换由Task2/3交付；损耗非空迁移与未知由Task1交付；完整矩阵与唯一全量由Task4交付，不推迟给4e。
- [ ] 本轮仅计划与4c状态文档；没有运行生产测试、没有改模板/生产文件、没有push。正式计划随本片PR共享，本机SDD仅交接镜像。
