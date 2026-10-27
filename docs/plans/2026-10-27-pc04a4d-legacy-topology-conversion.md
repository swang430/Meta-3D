# PC04A4d 旧拓扑显式转换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL：使用 `subagent-driven-development` 串行执行 Task 1～4，各任务独立规格/质量审查，最后累计审查；实施者不再派子代理。计划及Task1～3已独立批准，Task4综合验证/最终全后端与审查尚在收尾；不表示已外审、合并或现场通过。

**Goal:** 旧 CAICT 导入图及已有图由操作员明确补充声明并先看变更预览，原子保存时保留身份和引用；未知线缆损耗不再伪装为零，也不新增重复补偿源。

**Architecture:** 保留原拓扑 JSON、节点/边/模式 ID、原 PATCH 与原编辑器；增加局部转换操作清单和只读预览，确认时服务器重建并以数据库条件更新原子保存候选。量值仍取原外部边；操作员可显式将同一线缆两侧表示归属于其中一条边，非归属边原值保留但不重复计数。节点不新建第二份数值，不拆集成 PA、不自动推物理图、不批量迁移数据库。

**Tech Stack:** FastAPI/Pydantic、SQLAlchemy JSON、React/TypeScript/Mantine、pytest/tsx；无新依赖、数据库表、SCPI 或驱动。

**Spec:** [已批准设计](../design/2026-10-26-topology-device-port-contract.md)、[正式队列](../roadmap-first-call.md)、[4a 的 0.3 范围裁决](2026-10-26-pc04a4a-nominal-device-properties.md)。分支 `codex/pc04a4d-legacy-topology-conversion`，基线 `39d4bb0bc27ab6e13eca04ec0f7b4c82f14eb46a`。前置 PR #541 已于 `2026-10-26T22:31:48Z` 合并；[R2 回执](https://github.com/swang430/Meta-3D/pull/541#issuecomment-6428803419)覆盖 `fd473fba1cbad208f5604d4f2465279dab39ba7b` 无发现。4c 的 7822 passed/17 skipped/1 历史 G8 failed 仅属前片证据，不当作本片结果。

## Global Constraints

实施进度（2026-10-27）：Task1～3已实现并独立批准，最终前置SHA为`3c49bdc8`。Task4独立新库浏览器矩阵与真实HTTP/SQL相关集完成，GUI74项/build通过；首轮7条旧测试输入问题经root裁决只显式本地已知0，65/123项相关回归通过。重新冻结1196项输入后，同一责任位最终全后端 **7941 passed /17 skipped /1历史G8 failed /9618 warnings /799.05s，exit1**，不称全绿；首轮7934/17/8完整保留。见[正式摘要](../validation/2026-10-27-pc04a4d-legacy-conversion.md)。尚未Task4独立/累计审查、PR外审或合并，4e未启动。

- 旧记录不批量改写；缺角色/参数显示旧版未声明。用户显式转换前提供变更预览；不更改历史执行或已有证书。正常旧图的无关改名/位置保存不得被新契约误伤。
- params.ports 继续是端口 ID 清单；端口不是左右接点数量。名称不隐式决定方向。角色独立为 input/output/bidirectional/unknown；unknown 不冒充双向能力。
- 复用基站 port_roles 的 dl/ul 权威关系，不用通用角色覆盖它；新角色与其冲突必须拒绝，而非选一端。
- 图边为外部接线，器件内部连通关系独立声明。多端口器件不得默认全互通。开关继续复用现有 port_maps/switch_id/继电器身份，不新增第二套自动切换配置。
- 校准来源、原始采集和历史执行冻结保持只读；整链实测只在原采用入口生效一次。禁止额外叠加节点增益；声明、转换确认、标称完整都不是硬件能力或正式资格。
- 不改变真实端口映射、仪器绑定、certificate、历史 snapshot、confirmed application 或执行结果。配置变化提示复核，不自动撤销证书/强制重校准；当前执行不匹配仍走原门。
- 每组由操作员明确声明为同一线缆的两侧边只取一条原边的量值：owner的calibrated_loss_db（含0）优先，否则owner的cable_loss_db；不相加。无归属声明仍沿原语义。不增加节点损耗字段，不按数值/类型猜“重复”，不把合成边拆成实物线缆。
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
| `TopologyService.__init__/_dfs_paths/get_end_to_end_loss/get_calibration_matrix/validate/to_dict` | Task1求和改取所选路径中唯一owner集合，缺归属仍原逐边；有效量未知总量None，matrix compensation也None；response同步可空 | 显式同线缆2+2变2而不是4/None；没有声明仍4；calibrated0优先；不影响phase求和 |
| `switch_orchestrator.py::_build_probe_binding`→`rf_chain_resolver.py::_binding_to_spec` | Task1保留终端边语义，仅当该末边显式引用owner时换到已选路径内owner；不改为多段求和 | owner0不退到alias旧值，owner未知不补alias值；未知chain不drop、不补0 |
| `api/lab_profile.py::RFChainEntry`→`gui/src/api/labProfileService.ts::RFChainEntry`→`CalibrationScopeCard`、`RFChainDiagramPanel` | Task1后端和实际手写TS均改nullable，生成类型不能替代手写类型 | 列表保留身份，未知数值不崩/不显示0，TS不再误导无条件toFixed |
| `calibration/configuration_scope.py`与`schemas/calibration_scope.py::ScopeChain` | Task1可空chain，不改scope版本/摘要算法；Task2转换声明按既有params摘要进入current | 真实旧量值不因新键投影漂移；下述两类旧scope占位0纠正允许当前差异。null新声明只提示复核；历史baseline解析不查当前补值 |
| `path_loss_calibration_service.py::start_calibration_for_lab_profile`的chain.cable_loss_db公式/float消费者 | Task1缺量值在硬件lease前返回原失败结果，不生成测量/证书；后续单独参数cable_loss_db与chamber.typical_cable_loss_db不是同一来源 | 未知链不能执行`float(None)`或作为0；已知0照常工作；全部链先核再碰HAL |
| `route_calibration.py`/`fixed_route_method.py`/`fixed_route_acquisition.py`→`route_batch_plan.py`/jobs | Task1仅将新loss_owner_connection_id排除参考整边身份投影；接收线缆请求仍独立，不读本字段或自动填nominal | 单改量值归属不改变正常/参考route_digest，confirmed整链仍只算一次；实改ports/pair仍沿原门 |
| `declared_rf_routes.py::rf_execution_identity`→`route_calibration_freeze.py`→path_loss_preflight/measure→channel_engine_client | 身份只读物理所选路径，不加入量值归属字段；Task4回归，不改资格/历史/正式补偿算法 | 原冻结/报告前后逐字一致；声明同一线缆不自动撤证或使confirmed失配；实际端点变更仍拒绝 |
| `TopologyEditor`旧number input、`nominalProperties`、`CustomEdges` | Task1/3清空送null，保留数值编辑意图；PA净值任一输入未知显示未知 | 显式0/空/缺键分开；不再`??0`/`||0`伪装缺测 |
| `topology_nominal.py::preserve_graph_rows`与4a metadata | Task1/2延续缺键/旧opaque保形；来源说明改变不擅改数值；不新增节点线缆数值 | 六类标称和旧PA/参考边只改说明时旧数值与route摘要不被补null |
| `models/chamber.py`、`channel_engine_client.py`、旧e2e服务的同名cable字段 | 不改独立暗室默认/旧演示数学；只核其入口不消费本次nullable RFChainSpec | 不能把本片扩成全校准算法清洗；若发现新增直接消费Nullable chain需纳入同根修复 |
| live Pydantic→`api/openapi.yaml`→`gui/src/types/api.generated.ts`→`switchTopologyService.ts`及真实响应 | Task1/2四镜像，生成TS不手改 | POST/PATCH/list/import/path/lab/scope契约均能真实序列化null |

### 0.2 Ruling：显式同线缆归属，保留原外边为唯一量值源

主代理已裁决维持批准规格，不能退化为提示。最小新增字段为非归属边上的 `loss_owner_connection_id?: string`：操作员明确确认该边与所指owner边是同一物理线缆的两侧表示，量值只取owner原字段。缺键＝沿旧逐边语义；非空字符串＝引用另一已保存边。持久化不接受null/空串/self，不用0/null代表不参与。

选择“加最小引用字段”的必要性：删旧数值会失去来源且None变未知；换值到另一边仍无法表示非归属侧不参与；仅收窄数值条件无法区分两条真实等损耗线缆与同一线缆的两侧表示。因而必须保存操作员明确关联，但无需物理资产表、新测量值或节点损耗副本。字段只是应用归属声明，不证明实物、量值真实性或校准资格。

**支持域与保存规则：**
- 一组恰含owner与一个alias，两边必须在图中通过同一个`cable/receive_cable`节点相邻（一路入、一路出），仅以此限定可声明范围，绝不因此自动生成归属。每边最多属于一组；owner不再指向别边，无级联、环、自指、第二alias或跨节点合并。旧无声明图不新增任何字段。
- 每个有效模式按原`active_connections`/空列表回退语义检查：该两侧要么都激活，要么都不激活，不能同线缆一侧在normal另一侧在calibration。所选实际路径含本组时须包含两边且通过这个节点的合法原内部通路；只有半组的查询不产生完整量值，运行拒绝而非借全图别处的owner补数。
- 预览要求用户勾选“这两条边表示同一条物理线缆”，选择owner并展示两侧原cable_loss/calibrated_loss/来源、最终采用源与非参与旧值。转换只新增/撤销引用，不复制/清空/移动这些原数值。owner未知则整组未知，即使alias保留已知旧值也不兜底；owner calibrated0必须取0。
- POST/PATCH/import均校验显式新字段；GET/list纯读取。无关旧图编辑无字段时兼容。普通编辑删除owner/alias、改接端点/pins、换节点type、改模式时必须校验所有现存组：不得静默删引用或降回双份计数，返回全部关联边ID。用户要解组须在转换预览明确撤销引用；普通PATCH显式删除已知字段同样代表主动撤销，保留原值并通过全部引用门，不由“端点不存在”自动撤销。
- alias原数值原样保留作为旧声明，GUI列“旧值保留、不参与本组计算”，不可在alias抽屉直接编辑这些数值，提供定位owner；owner编辑沿原数值意图和元数据契约。直接PATCH同时修改alias数值不是引用失效，但须拒绝并提示先解组或编辑owner，避免写出看似生效的假编辑。

**消费者精确语义：**

| 场景 | 通用路径/矩阵 | 正式旧binding末边 | confirmed整链及历史 |
|---|---|---|---|
| 无归属两边各2 | 原求和4 | 原末边2 | 原规则不变 |
| 用户确认两边同线缆，末边alias→前边owner2 | owner集合只计2一次；alias不是数值0 | 末边换源读取同一已选路径owner2，不求和其他段 | 不读取此字段，不另加/减2 |
| owner0、alias旧2 | 计0一次 | 末边alias取0 | 不变 |
| owner未知、alias旧2 | None；matrix compensation None | None，需此值的旧测量入口在lease前拒绝 | 独立confirmed整链仍按原证据可用，不套用nominal门 |
| 归属组在上游但末边是另一条真实边3 | owner组计一次再加其它边3 | 仍末边3，不扩成多段求和 | 不变；预览明确正式旧binding未消费上游组 |
| 撤销归属 | 两侧原值重新各自参与，预览清楚显示2→4 | 恢复末边原值 | 不改旧记录 |

**摘要与失效边界：** 新归属键进入configuration_scope的当前图白名单，比较只提示复核；不要改scope版本或历史payload。它不改物理接线，故不加入rf_execution_identity、不改变正常route_digest；参考route_digest现整边投影应仅额外排除这一个新键（快照本身照存），正常/参考结果对称。已有confirmed整链与证书不被自动撤销/失效；既有执行冻结及报告不追当前owner。新旧per-chain方法创建新测量时使用当前明确owner，新执行confirmed值仍只沿原冻结一次。实际端点/内部pair/开关映射改变仍沿原身份不匹配门，不通过归属豁免。

**错判代价：** 把两条实物误认为同一条会少计损耗，故绝不自动识别，必须操作员逐组明确；漏声明只保留原值与可见重复风险。owner缺失/半组/循环若兜底可能错误功率补偿，故拒绝/未知，不以alias旧值补救。保存“归属”不等于认证这条物理事实，现场B仍未验。

F4裁决：Task1将实际所选正常及参考路径的显式新归属声明纳入当前scope可比较投影，覆盖active_connections为空时按边modes回退。仅投影存在的新键；无声明不新增null键、不因新归属投影漂移旧scope（下述旧占位纠正除外），不扩大全部参考字段。历史baseline按原payload验证，不回填当前声明。

Task1补充裁决（scope旧占位例外）：`build_calibration_scope(topology_id=...)`与`build_selected_route_calibration_scope`原来仅以四身份字段构造RFChainSpec，默认0不是实际量值。两入口必须复用本片所选路径末边/owner helper读取真实值（非零/0/None），不得为维持错误0造兼容算法。因此此两类当前scope允许0→真实量值/None的纠正差异，仅提示复核；“旧已知摘要不变”不适用于原虚假占位。历史baseline原payload/hash不改、不回填；物理route identity/confirmed不变、不自动撤证。错判代价：保留占位会把未知或非零说成零，必须纠正当前声明；代价仅增加真实的配置复核提示，不改变硬件量值或历史。

### 0.3 明确的null契约

`TopologyConnection.cable_loss_db: float | None = None`；新缺键的运行值None，保形写入保持原已存缺键、数值（含0）及未改字符串表示。GET为经schema处理的读模型（可能默认化或转型），不能用其字段存在性或数值类型证明原保存JSON；GUI依Task3区分GET展示与preview原始证据。写入允许有限非负number/null；拒绝bool/NaN/Inf/负数及主动字符串写入，旧未改字符串的4a兼容保留。`calibrated_loss_db`既有有符号值允许负增益，不因本片改其数值域。

```python
def effective_connection_loss(connection: dict) -> float | None:
    value = connection.get('calibrated_loss_db')
    if value is None:
        value = connection.get('cable_loss_db')
    return None if value is None else float(value)
```

该helper仅消费已通过现有typed/schema处理的数据，不被拿来放行bool/坏字符串；DB旧坏值在现有诊断/响应边界报告错误而非补零。通用total_loss的任一hop未知则None/calibration_status维持missing；validate给出缺失边ID。正式chain的nullable只传播声明，使用其做旧单段扣除的校准方法在lease前拒绝未知；confirmed整链冻结计算不依赖它，不加额外门。

Task1同模块还提供 `loss_sources_for_path(nodes: list[dict], connections: list[dict], selected_ids: list[str]) -> list[dict]`：connections为本模式实际有效边全集，selected_ids为已解析的有序路径；只返回该路径唯一owner原边集合，不返回伪造0贡献。先检查所选组两边均在路径、相邻且原内部穿越有效，再按owner ID去重；缺失/半组/重复/循环抛ValueError。`loss_source_for_terminal(nodes, connections, selected_ids) -> dict`复用同一完整性检查后只返回末边或其owner，不返回上游其它量值。

新增 `schemas/topology_loss_ownership.py::validate_loss_owner_write(nodes, connections, modes, *, previous_connections=None) -> None`承担0.2的字段、成组/全部模式/引用及alias数值修改保护，由原POST/PATCH/import和新转换最终候选调用。显式归属可存unknown数值但不能返回known；路径坏字段不靠前次保存证明，runtime helper也检查。`TopologyConnection` live/TS/service dataclass及to_dict均保留新引用键，老缺键不补null。phase只沿原原边算法，归属明确只管loss，不自动去重相位。

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
    loss_owner_connection_id: str | None = None
    same_physical_cable_confirmed: bool = False

class TopologyConversionRequest(BaseModel):
    nodes: list[ConversionNodeEdit] = []
    connections: list[ConversionConnectionEdit] = []

# model_fields_set区分未提交与明确null；ports/directions/roles/internal_paths/pins/ce_port
# 明确null拒绝；cable_loss_db明确null撤销标称数值，loss_owner_connection_id明确null撤销归属键。
# 设置/撤销归属必须same_physical_cable_confirmed=True，此确认只在操作请求，不持久化作资格。
def build_conversion(source: dict, changes: TopologyConversionRequest) -> dict: ...
def conversion_source_digest(source: dict) -> str: ...
```

- `TopologyInternalPath`使用本片schema局部严格二键模型（from_port/to_port），shape与4c一致；不导入不存在的模型。纯builder深复制原nodes/connections/modes，按ID精确替换白名单字段；每ID最多一项，空操作拒绝。所有未指名键原样保留。用户必须显式输入ports；从现存raw pin可展示“原保存声明”，但不自动列成已确认ports。`ports=None`缺省不表示删除。
- 改type只允许三组旧/新等价类型内切换，不能把PA变CE；保留原node ID/label/position/params。旧ce_port改channel_emulator若仅靠旧label取CE身份，必须显式提交ce_port；不可在服务端从label补。BSE port_roles保留权威；SA不补仪器category或测量能力。普通器件可补声明，不可借target_type改类别。
- 原source/target、边ID、mode ID/active_connections、probe_id/polarization、rf_path_selection、switch_id/mapping、calibrated_loss/phase/pa_gain、仪器绑定、默认位均不在操作白名单；需要改变这些应取消转换后沿原编辑器处理。归属设置/撤销只触引用键，不改上述原数值，且本次不能同时改该组两边cable_loss；先归属或先沿原编辑调整量值，避免预览混淆。预览展示全部保留值和实际采用源。
- 新端点 `POST /switch-topologies/{topology_id}/conversion-preview?lab_profile_id=...`：从同Lab当前原行读取，不从GET已默认化对象重建source；body为上述changes。返回 `{source_digest, changes, candidate:{nodes,connections,operating_modes}, differences:[{object_kind,object_id,field,before_present,before,after}], warnings:[str]}`。differences省略before仅在before_present=false；没有持久化、默认位改变或HAL动作。
- 预览先builder再用与PATCH相同的最终保形/结构/nominal/port/internal校验。坏输入422（含关联所有模式/边/探头），跨Lab404沿现有loader；warnings区分“未声明/仅操作员声明/配置变化需复核”，不把运行不可用称为非法草稿。
- 原 `SwitchTopologyUpdate`增加可选 `conversion: {source_digest:str, changes:TopologyConversionRequest}`。有此字段不能同时带其它更新字段（含connection_numeric_declarations），否则422；服务器读取当前原图重新核digest，失配409“原图已变化，请重新预览”，不是覆盖另一会话。digest仅用于本次并发保护，不进入校准摘要或历史身份。
- 确认阶段重建候选并复用原PATCH最终验证，不信客户端candidate/differences。cable_loss显式意图由服务器根据changes生成原numeric declarations；仅这些数值变更解除4a等价保留，不对所有边一律重申。提交必须按§1.1 CAS原子条件写，不能复用普通ORM无条件赋值分支。
- digest包含topology id、所属chamber、switch category以及原nodes/connections/modes，用现有JSON number规范一致序列化；排序对象键、不重排数组、不把缺键与null合并；预览到确认任何涉及图的变化均要求重预览。普通PATCH不要求digest，保留旧无关保存契约。
- 不新增HAL锁；转换提交复用既有 `execution_exclusion_guard.active_unsafe_diagnostic()`忙信号拒绝409，预览仍只读；不通过取消请求解除busy。GUI继续复用savingRef/collectionBusyRef及原activeWork跨Lab门。服务器现有普通CRUD没有相同guard，本片仅约束新增conversion路径，不冒称重构了所有编辑锁。

### 1.1 F1：源一致条件与转换写入原子成立

现模型没有version_id；updated_at使用func.now且时间精度不能证明未写过，不用它作唯一CAS。现API同步线程池的读→ORM提交不是串行保证，提交前再次SELECT也不构成保护。采用数据库单条条件UPDATE，不新建表或要求普通PATCH客户端提供digest。

转换确认事务以一次同Lab SELECT同时取ORM图及 `cast(nodes, Text)`、`cast(connections, Text)`、`cast(operating_modes, Text)` 的数据库原始文本快照，避免Python重新序列化的空格/键序造成SQLite误判。使用这一份source校digest、构建和验证候选；不把先前Session identity-map旧对象当新读。最后只在同id/chamber/category及三份图列快照仍相同时写候选与统计值：

```python
statement = update(SwitchTopology).where(
    SwitchTopology.id == topology_id,
    SwitchTopology.chamber_id == chamber.id,
    SwitchTopology.switch_category_id == saved_category_id,
    cast(SwitchTopology.nodes, Text) == raw_nodes,
    cast(SwitchTopology.connections, Text) == raw_connections,
    cast(SwitchTopology.operating_modes, Text) == raw_modes,
).values(nodes=candidate['nodes'], connections=candidate['connections'],
         operating_modes=candidate['operating_modes'], **statistics)
result = db.execute(statement.execution_options(synchronize_session=False))
if result.rowcount != 1:
    db.rollback()
    raise HTTPException(409, '原图已变化，请重新预览')
db.commit()
db.expire_all()
```

`statistics`只含原update_statistics定义的total_nodes/connections/probes/channels，按候选计算，不在Session给旧ORM对象赋dirty值；否则后续flush可能绕过条件UPDATE。updated_at沿既有onupdate更新；name/default/category/chamber不在SET，因此并发非图字段不被覆盖。确认返回重新加载同Lab真实保存行；CAS失败/SQLite锁冲突先rollback，不让get_db的退出commit提交任何残留。

SQLite相同源被其它连接先写时，条件更新rowcount=0；若SQLite事务快照升级返回SQLITE_BUSY/SQLITE_LOCKED系列（按原dbapi sqlite_errorcode准确识别），返回409并要求重新预览，不自动重试旧候选。其它OperationalError不吞成409，沿原错误处理。PostgreSQL JSONB→Text是DB自身确定表示，UPDATE等待竞争写后重新评估WHERE；不靠Pythonhash函数在SQL中虚构同一性。普通PATCH仍无需客户端digest；本片保证的是转换写不覆盖在它之前已提交的不同图，不宣称修复了所有普通PATCH互相覆盖。

计划阶段已用 `/tmp/pc04a4d-plan-cas-XJbPkU/probe.py` 的独立SQLAlchemy最小表、同JSONB/SQLite JSON变体、两个连接验证：B先写后A旧CAS rowcount0保留B；A新CAS rowcount1落库，exit0。没有app导入/默认DB或服务；PG只编译出JSONB UPDATE WHERE CAST列比较，**未执行PG测试**。此可行性原件不代替Task2真实API并发测试；其需在读快照与UPDATE间用测试屏障让普通PATCH真正提交，且在稳定SQLite文件库验证保存无覆盖，不只跑顺序预览例。

## 2. 串行任务与验收

### Task 1：显式损耗归属与未知值贯通真实读写和消费者

**Files:** 新增 `api-service/app/services/topology_loss.py`、`api-service/tests/test_pc04a4d_loss_truth.py`；修改 `schemas/switch_topology.py`、`schemas/topology_nominal.py`、`services/topology_service.py`、`services/mimo_ota/switch_orchestrator.py`、`services/calibration/rf_chain_resolver.py`、`schemas/calibration_scope.py`、`api/lab_profile.py`、`services/path_loss_calibration_service.py`（均在api-service/app下）；`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts`、`gui/src/features/TopologyEditor/{TopologyEditor.tsx,CustomEdges.tsx}`、`gui/src/features/{LabWorkspace/CalibrationScopeCard.tsx,ProbeCalibration/components/RFChainDiagramPanel.tsx}`。

**Interfaces:** Produces `effective_connection_loss(connection: dict) -> float | None`；现RFChainSpec/ScopeChain/RFChainEntry.cable_loss_db及SignalPath.total_loss_db/response同步nullable。Consumes原4a保形与numeric declarations，不能改为全图raw响应。

**补充Files/Interfaces（F2/F3）：** 新增 `api-service/app/schemas/topology_loss_ownership.py`；修改 `api-service/app/api/switch_topology.py`、`api-service/app/services/calibration/configuration_scope.py`、`api-service/app/services/calibration/route_calibration.py` 和手写 `gui/src/api/labProfileService.ts::RFChainEntry`（`cable_loss_db: number | null`）。产生§0.3两个所选路径量值源helper和`validate_loss_owner_write`，所有POST/PATCH/import最终候选复用；不能只改generated类型。

- [x] 先真实HTTP RED验证显式owner/alias：两侧各2无声明通用4，声明后通用2且正式末边alias只取owner2；owner0优先、ownerNone为未知、alias原值仍保存；上游组加末边3时正式仍3。覆盖半组、孤立引用、环、跨模式、删除/重接/alias改数值拒绝。先记录现生产不能表达归属的失败，禁止仅以新helper缺失作为唯一RED。
- [x] normal/reference各验证仅归属改变时route_digest及执行identity不变、scope变化提示复核、confirmed整链不叠加；改变真实pin/pair仍拒绝。原冻结/证书hash不变。phase仍原算法，不能顺手去重。

- [x] 先新增真实HTTP/实际resolver测试：建同Lab已知端口的直连/两段图，分别0/null/缺键/已有calibrated0/负calibrated；HTTP GET/list/PATCH/import/path/matrix/lab/scope不得崩或补0。核心断言内容：

```python
assert client.patch(url, json={'connections': cleared}, params=scope).status_code == 200
assert client.get(url, params=scope).json()['connections'][0]['cable_loss_db'] is None
assert effective_connection_loss({'calibrated_loss_db': 0, 'cable_loss_db': 5}) == 0
assert effective_connection_loss({'cable_loss_db': None}) is None
assert service.get_end_to_end_loss('ce', 'probe') is None
# 原测试fixture提供同Lab图/真实client；新增fixture在本测试文件显式实现，不改默认DB。
```

- [x] 使用新目录环境运行 `.venv/bin/python -m pytest tests/test_pc04a4d_loss_truth.py -q`，先保存schema不接受null/零优先失败的RED原件，不接受仅import不存在作为唯一RED。
- [x] 按0.3替换各消费方的错误零兜底；旧方法只在其确实需要chain loss的入口一次检查全部chain，返回原CalibrationResult失败，位于lease前；不禁用独立整链方法。GUI未改cable输入之前先真实浏览器清空并保存RED，再改为null和“未知”，PA净值不再扣默认0。
- [x] GREEN运行新增测试与 `tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_rf_chain_resolver.py tests/test_pc_01a_calibration_scope.py tests/test_path_loss_calibration.py tests/test_path_loss_ce_sa.py tests/test_pc04a2_route_freeze.py`。`gui`运行 `npm run build`；记录实际命令/统计而非预设通过数。
- [x] 分别回退零优先、None兜底两处核心变异应红；恢复后验证输入相同。提交 `fix: 保留拓扑线缆损耗未知与显式零值`，独立规格/质量通过后交Task2，不跑全后端。

### Task 2：服务器只读转换预览与原PATCH确认

**Files:** 新增 `api-service/app/{schemas,services}/topology_conversion.py`、`api-service/tests/test_pc04a4d_conversion.py`；修改 `api-service/app/api/switch_topology.py`、`api-service/app/schemas/switch_topology.py`、`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts`。不修改CAICT模板常量、历史证书或DB模型。

**Interfaces:** Consumes `effective_connection_loss(dict)`和既有 `_validate_structure/_validate_nominal/_validate_ports/_validate_internal_paths`；Produces §1请求/响应、`build_conversion(source,changes)`、`conversion_source_digest(source)`及service `previewConversion(id,labId,changes)` / 原`updateTopology`的conversion分支。

- [x] HTTP RED从旧CAICT真实import、三种旧节点、显式端口合法图各起一组；记录原row/default/history hash。核心请求及断言：

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

- [x] 落实§1纯builder及严格模型；preview与commit都验证最终候选，不在默认位更新后才失败。按§1.1单条CAS UPDATE保存，不给旧ORM对象赋dirty。真实HTTP并发屏障必须卡在转换读取快照后、条件UPDATE前，让普通PATCH在另一连接提交；随后转换409且另一写入保留。另测新快照成功、SQLite BUSY/LOCKED回滚、get_db最终commit不泄漏dirty、并发name变更不被覆盖；普通PATCH不要求新digest。
- [x] 设置/撤销owner必须显式same_physical_cable_confirmed，预览展示两侧原值/owner源/通用总值和正式末边分栏。测试同操作改组数值拒绝、解组恢复原值参与、删除owner/相邻线缆/模式半组拒绝；无声明旧图不增加字段。直接PATCH非法归属不能绕过原最终候选校验。
- [x] 负例逐项：未知ID/重复操作/额外字段、跨Lab、无CE声明改type、缺pin/孤立pair/方向矛盾、BSE权威冲突、受引用端口删除、全部模式引用、busy、伪造candidate/digest、确认重复旧digest。正例：unknown草稿、取消、仅元数据正常PATCH兼容、全部ID/opaque/损耗原值保留。
- [x] 运行 `.venv/bin/python -m pytest tests/test_pc04a4d_conversion.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a4b_port_contract.py tests/test_pc04a4c_internal_contract.py tests/test_pc04a3_topology_recovery.py -q`；生成四镜像后build。回退stale比较和原图before保护各一项变异实红恢复。
- [x] 提交 `feat: 增加旧拓扑显式转换预览与确认保存`，独立审查，Task3消费最终接口；不跑全后端。

### Task 3：原图转换面板与草稿/锁生命周期

**Files:** 新增 `gui/src/features/TopologyEditor/LegacyConversionPanel.tsx`、`gui/src/features/TopologyEditor/legacyConversionState.ts`、`gui/test/legacyConversionState.test.ts`、`gui/test/pc04a4dConversion.browser.js`、`gui/test/pc04a4d.vite.config.ts`、`api-service/tests/pc04a4d_browser_fixture.py`；修改 `TopologyEditor.tsx` 和 `switchTopologyService.ts`，不新建编辑画布。

**Interfaces:** Consumes Task2 `previewConversion`与PATCH conversion；Produces `conversionContextKey(labId:string, topologyId:string):string`、`buildConversionRequest(nodeEdits,connectionEdits):TopologyConversionRequest`。预览结果只留当前面板会话，不持久化到图params。

- [x] 先新库bootstrap/显式Mock/真实API及专用代理；首次接UI前真实浏览器观察“转换旧配置”入口不存在为RED，但首次CLI异常未保留完整DOM，不将勾选理解为首次证据完整。Task3后续仅回退入口按钮重现RED并补录DOM/GET/截图，明确是后补回退重现，不是首次RED；详见Task3报告披露。初始fixture包括CAICT原图、旧ce/bse/sa与新声明对照、普通/参考cable、opaque及历史冻结样本，源图ID与展示图ID分栏。
- [x] 使用原Mantine抽屉/Modal实现“编辑转换项→预览差异→确认保存”。原保存值/缺键只依据服务器preview差异before/before_present所涉及字段；candidate仅展示为候选原始JSON，不当作原图before。预览前GET节点/边及端点、owner选项统一标“GET展示值，原保存声明待核”，不把默认out/in、0或转换后的数值当原声明，不以GET缺键推断raw缺键；本片不新增raw接口。提供明确type选择、ports/方向/pair、损耗显式输入，不提供一键猜测/自动补齐。dirty时不自动覆盖，提示先原保存或关闭转换继续草稿。确认按钮必须有当前成功预览，编辑任一项即使改回也使预览失效；409保留输入供重新预览。
- [x] 每个事件处理先查 `savingRef.current || collectionBusyRef.current`；不是只disabled按钮。预览中context变化丢弃迟到响应；外层换Lab/selectedSwitch/重导入同时清会话，保存成功通过原onSaved更新，失败保留输入与原图。
- [x] 原面板新增逐组“同一物理线缆”确认与owner原边选择，不按相等数值自动关联；alias原值只读并能定位owner，解组预览明确恢复参与。无声明保留原样。用户确认不显示实物验证/认证成功。
- [x] helper测试明确断言取消/换图清预览但不改原draft，序列化未提交键不补null；null只允许cable清值和owner显式撤销，后者要求确认且落库删除键：

```ts
const request = buildConversionRequest([], [{connection_id:'wire',cable_loss_db:null}]);
assert.deepEqual(request.connections,[{connection_id:'wire',cable_loss_db:null}]);
assert.equal('source_pin' in request.connections[0],false);
assert.notEqual(conversionContextKey('a','g'),conversionContextKey('b','g'));
```

- [x] 真浏览器先编辑→取消→预览→保存→GET同ID；再断网→失败→恢复重试、stale409、切Lab迟到响应、保存pending、采集running/取消未确认/终态释放后连续两次重入。采集全Mock只证明软件生命周期，不称实物停发。
- [x] 运行 `node --import tsx --test test/legacyConversionState.test.ts` 和 `npm run build`，回退事件层busy保护/缺值null各一项变异RED恢复。提交 `feat: 在原拓扑编辑器预览并确认旧声明转换`，独立任务审查。不用Task3定点证据替代Task4矩阵。

### Task 4：综合闭环、最终全后端与正式交付文档

**Files:** 新增 `api-service/tests/pc04a4d_matrix_evidence.py`、`gui/test/pc04a4dMatrix.browser.js`、`docs/validation/2026-10-27-pc04a4d-legacy-conversion.md`；补Task1/2测试和Task3fixture；更新本文实际进度、`docs/roadmap-first-call.md`、设计状态与应用操作文档 `docs/产品特性/calibration-system.md` 的本功能入口说明。不得扩改历史算法宣传。

**Interfaces:** Consumes全部Task1～3生产HTTP/GUI和原单路/批采集/冻结读取，不生产新接口。Produces真实版本/输入/依赖/命令/统计/退出码及未验边界可核对的正式摘要。

| 矩阵 | 必验真实结果 |
|---|---|
| D01 | CAICT原import→预览取消原图不变→逐项显式声明保存；模板文件/hash不变；不是静默全模板转换 |
| D02 | ce_port/bse_port/sa_port保持ID显式改type；CE身份缺证据拒绝，BSE角色不覆盖，SA不增加测量资格 |
| D03 | 缺键/null/0/旧非空/typed旧字符串往返，旧calibrated0优先；多hop未知总值None，GUI无None/0假值 |
| D04 | 六种标称/参考PA只改来源保形；用户明确同线缆两侧各2→选owner→预览通用4变2/正式末边取owner→保存重载→撤销恢复4，alias原值不丢；无声明不变，owner0/unknown、上游组末边3与全部引用反例覆盖，节点无数值副本，集成PA不拆分 |
| D05 | 多模式、显式probe路径、内部pair、switch mapping引用冲突原子422；默认位与所有历史hash不变 |
| D06 | preview零DB写零HAL；错误scope404，真实双连接在读后写前交错的CAS409保留普通PATCH结果，新快照可写，name并发不覆盖；同default重导入保护不变 |
| D07 | 草稿取消/保存失败/断网恢复/换图/换Lab/迟到响应，实际操作对象ID、请求ID、DOM一致 |
| D08 | 保存pending、单路/批采集running、取消未确认锁定；软件释放后两次编辑保存重入 |
| D09 | 普通与参考单路/批预览和Mock采集保持；未声明/未知拒绝不授资格；固定直连零switch I/O |
| D10 | 转换前已有执行冻结/报告读取下载不变；仅量值归属改变正常/参考身份不变且scope提醒，confirmed整链仍一次；真实端点/内部pair变更仍按当前身份门拒绝 |
| D11 | 旧需chain loss方法未知在lease前失败，已知0通过；独立confirmed整链不因无关nominal未知被挡 |
| D12 | 原编辑器真实鼠标移动、显式应用/保存重载、删除引用拒绝；本片证据独立，不冒称补验4c的C07历史 |

- [x] 新建独立浏览器库，执行D01～D12；每组请求/响应/GET、SQL前后、截图与对象身份见正式摘要分栏，非所有反例均由DOM点击。客户端不route mock；隔离fixture不是现场数据；模拟不进入正式PASS。
- [x] 运行新增两测试及消费者相关集、GUI测试/build，稳定后冻结全部源码/测试/fixture/契约/依赖输入。只有本Task责任位执行以下最终全量：

```sh
pc04a4d_run=$(mktemp -d /tmp/pc04a4d-final-XXXXXX)
cd api-service
env DATABASE_URL="sqlite:///$pc04a4d_run/full.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4d_run/logs" .venv/bin/python -m pytest tests -q
```

- [x] 留存stdout/stderr与exit、输入起止hash/依赖/HEAD。G8同历史引用，已核文件及门基线未变并披露，不改门不称全绿；其它7条经root裁决只修测试本地已知零输入，不改预期。改变稳定输入后由本责任位唯一补跑。
- [x] 更新正式验证摘要并列未验项；服务关闭只用已核PID/session，保留全部证据。
- [ ] 提交 `test: 验证旧拓扑显式转换与损耗边界` 后独立Task4审查→累计基线至HEAD审查→Ready PR R1/R2；通过merge后才4e。

## 3. 计划自查与交接

- [x] 独立计划审查批准前禁止生产实现；审查重点是nullable所有消费者、原型转型CE来源、最终候选引用原子性、预览stale与busy边界，以及0.2对物理单一归属的真实承诺范围。
- [ ] 每任务brief附本文全局约束、exact接口与上一任务最终SHA/report；不只转任务标题。
- [x] 模板/旧图显式转换由Task2/3交付；损耗非空迁移与未知由Task1交付；完整矩阵与唯一全量由Task4交付，不推迟给4e；本地验证不等于独立审查或合并。
- [x] 初始计划阶段仅计划与4c状态文档，当时未运行生产测试或改模板/生产文件；该历史事实保留。当前实现/验证进度以上方实施进度与正式摘要为准，仍未push。正式计划随本片PR共享，本机SDD仅交接镜像。
