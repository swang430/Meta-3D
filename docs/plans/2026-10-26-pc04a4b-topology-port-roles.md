# PC04A4b 拓扑端口清单与角色实施计划

> **For agentic workers:** 使用 `subagent-driven-development` 串行执行 Task 1～3；每个任务由主代理安排独立规格/质量审查，实施者不再派子代理。`task-brief` 可按下列 Task 标题提取；主代理同时交付“全局约束”和相应契约章节，不让执行者自行猜测接口。

**Goal:** 原拓扑抽屉编辑的端口清单、角色、数量和方向图使用同一声明；明确错误接线在 POST/PATCH/import 写入前拒绝，未知只表示未知，旧图无关保存不自动转换或改变执行资格。

**Architecture:** 保留 `params.ports` 和 BSE `params.port_roles`；新增应用层方向声明 `params.port_directions`，用纯解析/校验函数同时服务表单、画布和写入边界。不创建资产平台、迁移表、驱动能力表或内部通路解释器。

**Tech Stack:** 现有 React/TypeScript/Mantine/ReactFlow、FastAPI/Pydantic、SQLAlchemy JSON、pytest、tsx/node:test；不新增依赖。

**Spec:** [已批准设计](../design/2026-10-26-topology-device-port-contract.md)；[正式队列](../roadmap-first-call.md)。基线 `1207f8c547df3f253430cc8c84694343ff50aa71`，分支 `codex/pc04a4b-topology-port-roles`。PR [#539](https://github.com/swang430/Meta-3D/pull/539) 已于 2026-10-26T14:29:23Z 合并，[R2 回执](https://github.com/swang430/Meta-3D/pull/539#issuecomment-6418381233)覆盖 `111e5126cd`、无重大问题。4b 为唯一 WIP，尚未合并；本文为实施计划与执行索引，不代替审查/正式验收。

**实施状态（2026-10-27）**：Task1（6215e6ac）与Task2（143be900及a7961b91修复）已独立Approved。Task3综合矩阵已实跑，相关后端469/GUI77通过、build成功；唯一最终新库全后端7663 passed/17 skipped/1 failed/7579 warnings（历史G8与基准一致，不称全绿），详见[正式验证摘要](../validation/2026-10-26-pc04a4b-topology-port-roles.md)。Task3和累计分支独立审查、PR外审尚待完成；4c/4d及B/HOLD不启动或关闭。下方Task1/2原清单保留为施工步骤，完成依据为对应独立任务报告，不从计划文字推断验收。

## 全局约束

- 不改内部通路规则（4c）、旧 CAICT 图转换（4d）、采用记录/冻结算法/补偿/历史执行；父项和现场 B/HOLD 不关闭。4e 不承接本片遗漏验证。
- 端口 ID 不是方向，名称/型号/图标/`inputs`/`outputs` 不授予角色或物理数量。`unknown` 不等于 `bidirectional`；左右两个绘图 handle 不是两个端口。
- BSE 的 `port_roles` 继续为 `dl/ul` 唯一声明来源；物理连接器来自既有 `base_station_port_mapping.resolve_base_station_port_mapping` 的 route snapshot。新通用方向不能替代、扩充或覆盖该运行时来源。
- 新字段不授予执行、自动切换、真实测量、校准采用或正式通过资格；缺声明旧图沿既有服务器权威门。图保存成功不等于绑定同步或校准生效。
- 保留 4a 的缺键/原 JSON 保形、数值声明意图、零值与 null、扩展参数及原校准只读字段；不把显示默认值写回旧行。只在最终待存图验证通过后更改默认行/删除替换行/写 ORM。
- 采集/保存锁复用 `editingBlocked`、`savingRef`、`collectionBusyRef` 和原工作锁，不另造锁；取消/拒绝/网络失败保留草稿，跨 Lab 不串草稿或声明意图。
- 所有 app 导入、pytest、API 启动先指定本片新建临时 SQLite、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`。不触用户服务/DB/证书，不连接硬件，不清理 worktree、venv、output 或 scratch。
- 本片不新增 SCPI、不作厂商能力断言，NotebookLM 不适用；若实现需要仪器语义，回主代理重新定界，不能猜命令。
- 验证档位为 GUI/API + 共享拓扑契约。Task 3 实施者是**唯一最终全后端执行责任人**；主代理核对证据并承担交付责任，reviewer 不重复跑相同输入的全量。后续功能/fixture/依赖改动使结果失效，由主代理明确安排同一责任位重跑。
- 每任务先 RED 后生产修改，再 GREEN 和独立任务审查；最后累计独立审查。Ready PR 后 R1/R2，覆盖最新功能 HEAD 无 P1 才合并；本计划提交本身不 push/开 PR/合并。

## 0. 已核对的生产入口与消费全集

以下是基线源码观察，不是硬件能力证明。实现前重跑 `git grep` 核对增量，不需要导入应用来读代码。

```bash
git grep -n -E 'params.*ports|port_roles|physical_port_display|getNodePorts|resolvePortHandles' -- api-service/app gui/src
git grep -n -E 'source_pin|target_pin|direction|resolve_saved_rf_path|rf_execution_identity' -- api-service/app/services gui/src/features/TopologyEditor
git grep -n -E 'route_digest|parameters_digest|nominal_metadata' -- api-service/app/services/calibration gui/src/features/TopologyEditor
git grep -n -E '绝不|不许|禁止|must not|别把' -- api-service/app/api/switch_topology.py gui/src/features/TopologyEditor
```

| 生产入口/站点 | 权威与本片处理 | 正式消费者/可观察断言 |
|---|---|---|
| `schemas/switch_topology.py::TopologyNode.params`，`TopologyConnection.source_pin/target_pin` 默认 out/in，Response 连接 `exclude_unset` serializer | 保持旧 Dict 扩展能力和连接稀疏响应；新方向在 raw JSON 上校验，不能强转或默认补全 | GET/list/POST/PATCH/import 回应与存储分开核对；缺方向不自动出现 unknown map |
| `api/switch_topology.py::create_switch_topology/update_switch_topology/import_topology_from_template` | POST 已在保形后结构校验；PATCH 现先检 typed 图再保形。新增方向校验必须作用在最终候选，并能读取同 Lab previous 作局部兼容 | 422 前无默认行变更/删行；PATCH 数组替换或部分字段提交均校验合成后的完整图；不能只验证请求出现的半张图 |
| 同文件 `_validate_structure`、`_validate_nominal`、`preserve_connection_rows`、`preserve_graph_rows` | 扩展已有写入链，不另造端点；沿用缺键和原值保形，不把数值声明 map 用于端口 | 稀疏参考边/旧 typed 数值/opaque 继续保形；所有拒绝后原数据库行不变 |
| `nodePortHelpers.ts::getNodePorts/nodePortsToSelectOptions` 默认表 | 拆开“明确声明”与“旧版示意”，保留可读渲染，不把默认表当保存能力 | 编辑/数量/候选列表引用同一解析结果；不存在节点不能回退 out/in 通过新连接 |
| `TopologyEditor.tsx::openNode/addNode/applyNodeEdit/onConnect/applyConnectionEdit/initialEdges/handleSave`，`topologyDraft.ts` | 同一端口编辑数据驱动草稿，新增建议只有显式应用才声明；连线拖入与抽屉重接同校验 | 只改 label/position 不补声明；新设备无端口不得保存；失败草稿/未应用抽屉互不污染 |
| `CustomNodes.tsx::withDeclaredPorts` 与各旧节点 handle | 现非 BSE 显式端口两侧都画。本片改为声明方向；几何刷新依赖 ports+directions+BSE roles | 已知 input 只 target、output 只 source；双向同 ID 两种 handle；未知显式标灰/问号；计数按唯一 ID，不按 DOM handle |
| `baseStationPorts.ts::resolvePortHandles`、`baseStationPortsTruth.test.ts` | `dl→source/output`、`ul→target/input` 不变；不能按 DL/UL 名字识别 | 叫 RF5 的 dl 仍输出；叫 DL1 的未知仍未知；冲突拒绝，物理显示仍只读 |
| `CustomEdges.tsx::SignalEdge`、`initialEdges` | 现 `direction` 只影响 UL 色与虚线，marker 固定在 target。本片由解析结果决定是否画方向证据；不反写 edge.direction | 未知接线无“已知流向”箭头；UL 标签不反转 source/target；4a 损耗/PA显示保留 |
| `declared_rf_routes.py::resolve_saved_rf_path/selected_switch_mappings/rf_execution_identity` | 原选择路径、明确 pins、port_maps 和继电器身份继续权威，不把新声明当内部可穿通路径 | 改接/删除被引用边仍拒绝；失效开关映射不因 bidirectional 被放行；新声明不能凭空增加解析分支 |
| `TopologyService.resolve_paths/get_mode_connections/_dfs_paths/validate/get_calibration_matrix` | 原节点级路径与边损耗算法不扩展，内部通路缺口归4c | 新方向不改变损耗/矩阵；不会宣称已验证 PA/合路器内部通路 |
| `calibration/route_calibration.py::_route_selections`，`configuration_scope.py::_build_scope_payload` | 当前 route_digest 包括 ports/port_roles 等 params；配置摘要含完整 params 摘要。新方向属于接线约束，沿原摘要机制，不自行排除 | 没有新字段的旧图原样往返 digest 不变；明确新增/改方向会改变新生成 route_digest/配置摘要，需重新获取服务器路径；不回写历史 snapshot |
| `routeCalibrationState.ts::routeGraphMatchesSaved/routeMatchesSaved` | 当前对 ports/port_roles 按所选端点独立比较；新方向须与服务器快照比较，dirty 仍阻止操作 | 变更后不能用旧选择发采集/采用请求；新服务器选择仍须原 eligibility/real 来源，不能凭声明变绿 |
| `fixed_route_jobs.py`、`route_batch_plan.py`、`evaluate_route_application/confirm`、`mimo_ota/route_calibration_freeze.py` | 只回归既有摘要/身份与资格，**不修改这些资格或冻结算法** | 新摘要与旧记录不兼容按原规则显示；历史证据不被“补角色”，配置提醒不自动撤销证书/旧采用记录 |
| `mimo_ota/executors/measure.py` → `base_station_port_mapping.py` → `mimo_ota/switch_orchestrator.py`；`calibration/rf_chain_resolver.py` → channel engine | 原运行时 baseStationPortMapping 从实际 route snapshot 投影，active logical ports 过滤，端口/损耗链不读新声明授予资格 | 运行映射、CE端口、开关 binding 未变；输出 unavailable/unknown 的原场景仍不提升，整链补偿不多一遍 |
| `api/openapi.yaml`、`gui/src/types/api.generated.ts`、`switchTopologyService.ts` | 4a 已有 CRUD schema 闭包；只同步本片 schema description/必要闭包与手写辅助类型 | checked/live schema/真实 JSON/生成 TS 四镜像一致，不替换整份 OpenAPI |
| `scripts/dev-fixtures/topology-templates/caict_v4.py`、旧 ce_port/bse_port/sa_port | 旧图数据不转换/不批量补 ports；保留 import 的旧图入口，具体缺失显示旧版未声明 | 旧 CAICT 导入仍可读/改名/移位；新显式非法声明不能因来自模板豁免 |

## 1. 本片契约

### 1.1 声明、角色与数量

```ts
type TopologyPortDirection = 'input' | 'output' | 'bidirectional' | 'unknown';
// 位于原 params，对不存在的键不赋默认值、不把 null 当缺失写回。
// ports: string[];                       // ID 唯一来源
// port_directions?: Record<string, TopologyPortDirection>;
// port_roles?: Record<string, 'dl' | 'ul'>; // 只沿既有 BSE 语义
```

新 `port_directions` 为非 null 对象，只允许 `ports` 已存在的 ID；值严格四枚举，拒绝 bool/number/数组/空串/未知值。可以是部分 map，未填的 ID 解析为 unknown，但不自动补键。显式 `{}` 表示撤销通用方向声明，不表示双向。不新增“已验证”字段。端口 ID 为非空、无首尾空白、唯一的字符串；不按大小写/数字/型号改名，`RF1` 与 `rf1` 不合并。UI trim 在操作员输入时进行；服务端拒绝不规范新 ID，不能悄悄重写引用。

BSE (`communication_tester`/`bse_port`) 复用原 `port_roles` 下拉（下行 dl / 上行 ul / 未声明）；未知时不生成 dl/ul。解析已知 BSE role 后得 output/input；通用方向缺键或 unknown 不覆盖它；同向可接受；反向或 bidirectional 与单向 BSE role 冲突即422。非 BSE 不读取 `port_roles` 猜方向，也不提供该专用字段编辑；旧扩展内容原样保留。`physical_port_display` 不可编辑、不从模型名补值。BSE 显示“已声明逻辑端口 N；物理连接器见运行映射”，air_path 显示“已声明虚拟参考端点 N”，其余显示“已声明端口 N（未核验硬件）”，不能统称真实 RF 口。

数量仅来自合法显式 `ports.length`；missing/null/坏旧值显示“端口数量未声明/旧版示意”，不取 `inputs/outputs/num_ports` 或画布 handle 数量。`ports=[]` 仅允许尚未保存的新建草稿；不允许作为保存后的明确端口列表。新增任意器件（包括 CE/EMCenter/PA/合路器/SA/VNA/负载/空气/线缆）不给自动默认数量。建议 A/B 或其它现有默认值必须标“未确认”，经过显式应用才写入。

### 1.2 有向外部连接与草稿

`source/source_pin→target/target_pin` 是已保存的外部接线次序，不由 `direction=UL` 反转。新建或涉及端点/声明变化的连接：source 必须不是已知 input，target 必须不是已知 output；因此 output→output、input→input、input→output 均拒绝。output→input、output→bidirectional、bidirectional→input、bidirectional→bidirectional 可保存。unknown 可在任一端保存草稿，但突出“方向未声明，非双向能力”；不产生额外执行资格。

节点绘制：input 左 target、output 右 source；bidirectional 两侧同 ID，标签明确“双向声明”；unknown 可保留两侧作为**草稿连接入口**，必须同 ID、灰色问号/未知文字且无“已确认流向”暗示。缺 ports 的旧节点保留旧 handles 供可读，不计入数量、不自动物化到 params；无关编辑不需要补声明。新建连线必须由明确端口清单选择，不把旧默认表当用户声明。

边绘制：两端方向明确且合法时按 source→target 画箭头；双向两端只有边本身明确 `Bi-Di` 时画双向，否则仍是本条接线声明的 source→target；只要任一端有效方向 unknown 就无实心流向箭头并显示未知提示。保留 DL/UL/Bi-Di 业务标签和旧损耗颜色，不由它猜端口能力；旧边不因渲染改变 JSON。

### 1.3 写入全集、兼容与引用保护

| 入口/变更 | 校验边界 | 拒绝后的保证 |
|---|---|---|
| POST 新拓扑 | 每个新增节点必须有非空显式 ports；新 map 严格；全图节点/边/模式与方向校验 | 无新行、不改变原默认行 |
| PATCH 新节点或改 ports/port_directions/BSE port_roles | 合成 previous+本次数组替换，按 ID 判断新增/明确变更；严格验证该节点的声明及所有关联边（含其他模式和校准边） | 原行、默认位、摘要和校准记录不变 |
| PATCH 仅改 label/position/标称/模式，旧节点缺方向或 ports | 不补默认，不把 untouched 缺声明变成错误；原结构/引用/校准作用域校验仍执行；纯改名与位置需覆盖稀疏 GET→PATCH | 不触发隐式旧图转换；端口缺失不新增资格 |
| PATCH 新边/改端点或 pins | 两端必须有显式 ports、包含所选 ID；角色有效性按1.2。仅改旧边标称/模式不视为主动重接；原显式路径和作用域校验仍执行 | 不自动换方向、删边、重写 rf_path_selection 或 port_maps |
| PATCH 删除端口/改 ID | 任何仍引用旧 ID 的外部边拒绝；探头 rf_path_selection、switch_mappings 继续由原解析验证；要改接先加新口/替代边→重声明路径→删旧边→删旧口 | 提示相关节点/端口/边 ID，不静默级联删路径 |
| PATCH 清空/删除方向 map | 只取消通用声明，不取消 BSE dl/ul；变更影响的全体关联边仍校验；不存在→空/unknown 是显式声明，不从值相等猜无操作 | 不能靠删除字段回避新连接的端口成员约束 |
| import/from-template | 注册模板是旧图数据入口，允许原缺失声明保形导入；所有**明确存在**的 ports/方向/角色必须合法；新方向与既有 BSE 冲突拒绝，先校验后 replace_existing | 不改模板文件以强行过门、不以模板名/型号豁免明确错误；非法模板不删既有图 |
| GET/list/响应序列化 | 只读不执行写入迁移；方向作为 params 原值透传，渲染防御坏值显示未知 | 旧坏/缺数据不崩溃，不标已核验 |

兼容是“原缺失未改”而非全局跳过校验；同 ID 换 type、ports、端点、新插入节点均不能冒充旧图。原 schema 的 out/in 只用于旧缺 pin 的保形/结构语义，新显式路径仍须真实保存 pins。原 `_validate_structure` 的显式路径引用检查不得被局部兼容旁路。内部通路字段尚不存在，本片不发明或解析它；现有 `rf_path_selection/port_maps` 不叫“内部通路已完成”。

### 1.4 摘要与资格的明确取舍

本片**不改 route_digest 排除列表、不改冻结/采用算法**：新 `port_directions` 沿原 params 投影参与新生成摘要；它不是4a的纯说明元数据。旧图没有该键且未改 ports/port_roles 时，无关保存必须逐字保持原 route_digest。明确添加或改方向后，需要重新从服务器选路，旧缓存选择不能直接采集/采用；已有记录的适用性由原 route_digest 匹配规则决定，UI 不宣称“仅标注所以所有旧校准仍可用”。不能自动更新旧 snapshot、撤销历史采用或重校准证书。

区别三件事：配置盘点差异仍是提醒；已有路径身份不兼容是原独立规则；方向声明本身不是运行许可。全 unknown→全部明确甚至 bidirectional 后，原 binding/CE/参考量/real provenance/证书/用途/开关互锁缺口仍保持。若实现只能通过改冻结/采用政策来满足本片，停止扩域交主代理裁决，不自行排除新键或批量重算摘要。

## Task 1: 服务器声明契约、写前校验与四镜像

**Files:** 新建 `api-service/app/schemas/topology_ports.py`（仅纯声明读写校验）、`api-service/tests/test_pc04a4b_port_contract.py`、`api-service/tests/test_pc04a4b_port_identity.py`；修改 `app/api/switch_topology.py`、`app/schemas/switch_topology.py` 的契约说明、`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts` 的辅助类型。需要改其它生产文件先由主代理核对范围。

**Interfaces:** 主代理交付本文全局约束和第0～1节。本任务提供纯函数 `validate_port_write(nodes, connections, *, previous_nodes=None, previous_connections=None, allow_legacy_missing=False)`；在最终候选图上工作，previous 仅同 Lab 加载的原行；import 明确传 `allow_legacy_missing=True` 仅容许没有声明的旧节点，不豁免已存在的错误声明。解析返回有效方向与来源（BSE/explicit/unknown），不访问 HAL/DB。命名可按仓库惯例微调，语义与接口落地后记录给Task2。

- [ ] 写真实 HTTP RED：沿 `test_p1_57_topology_lab_context.py` 的 `client/world/_mk_row`，不通过直接调用新 helper 假装 API 验证。POST 缺 ports、PATCH output→output、孤立 map 键、BSE冲突、无效枚举应422，而基线会放行其中新增契约错误。每类至少一条先证明旧行为失败断言；fixture失败不算RED。
- [ ] 按第1节覆盖正例/反例：四方向、空值/坏类型/重复ID、端口无关大小写、不猜DL字样、已有/新节点、部分PATCH/全图PATCH、跨模式关联边、新旧 sparse pins、BSE已知/未知/冲突；全16种 source/target 有效方向组合断言保存允许/拒绝，不只截图。
- [ ] 原子性覆盖：错误POST且 `is_default=true`；错误PATCH同时改 name/default；错误模板 `replace_existing=true`；从真实GET及 ORM refresh 两端检查无删/无写。跨Lab409和非法Lab422保持。
- [ ] 旧图兼容覆盖：同Lab旧节点无 ports/方向，仅 name、node label、position 与全量GET回传；不得补 ports/方向/default pins。旧CAICT模板导入可读并明确旧版；新边接旧未声明口必须先声明。不得把当前4a测试中无 ports 的“新增”fixture当生产豁免：若测试目的是标称字段而非旧图，补明确fixture端口；历史兼容测试仍保留缺声明。
- [ ] 实现最小纯校验并接入三写入口，保形后的最终候选同时过原结构/新方向校验，全部位于默认位/replace删行/ORM赋值之前。错误 detail 含节点/端口/边定位；不新建通用错误框架。
- [ ] 新字段在 `params` 保留开放 JSON：Pydantic模型不默认插入 map。以description明确字段与写入限制；若使用独立四枚举模型，保证它确实被live schema引用，不能声称未引用模型自动出现在闭包。只更新CRUD递归闭包，`npm run openapi:generate`更新生成类型，不手改生成TS。
- [ ] 新建 `test_pc04a4b_port_identity.py`，复用 `test_pc04a2_route_selection.py` 的真实 API configured/graph/paths：普通节点和参考节点两端，旧图GET→PATCH digest不变；明确map变化新digest变化、旧选择拒绝；新路径响应带map；原记录/snapshot不变，未知→明确不提升mock/缺绑定资格。沿用4a稀疏参考边与旧typed值测试，损耗/矩阵不变。
- [ ] RED/GREEN 命令均在新目录执行，保留SHA/diff/退出码/末行：

```bash
cd api-service
pc04a4b_test_dir=$(mktemp -d /tmp/pc04a4b-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a4b_test_dir/test.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4b_test_dir/logs" .venv/bin/python -m pytest tests/test_pc04a4b_port_contract.py tests/test_pc04a4b_port_identity.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_pc04a1_topology_editing.py tests/test_pc04a3_topology_recovery.py tests/test_p1_57_topology_lab_context.py -q
```

- [ ] GUI运行 `npm run build`；行为变异临时移除一个写入口校验，必须出现对应错误写成功的RED；恢复后GREEN。再移除BSE冲突校验确认核心保护会红。只用apply_patch改本片代码并精确还原。
- [ ] 报告交主代理，记录测试真实统计及输入，独立任务审查同时给规格与质量结论后再Task2；不声称真机或全量已通过。

## Task 2: 同源端口表单、方向画布及生命周期

**Files:** 新建小组件 `gui/src/features/TopologyEditor/PortDeclarationFields.tsx`、`gui/test/topologyPortContract.test.ts`；修改 `nodePortHelpers.ts`、`baseStationPorts.ts`（仅复用方向投影所需）、`TopologyEditor.tsx`、`CustomNodes.tsx`、`CustomEdges.tsx`、`topologyDraft.ts`、`routeCalibrationState.ts`；新增浏览器前置 `api-service/tests/pc04a4b_browser_fixture.py`、`gui/test/pc04a4bPortRoles.browser.js`、`gui/test/pc04a4b.vite.config.ts`。既有4a相关回归文件仅在必要时补断言，不重写框架。

**Interfaces:** 主代理交付全局约束、第1节、Task1实际字段/错误契约及测试报告。GUI纯解析结果至少包含 `{ports, declared, effectiveDirections, directionSources}`；`getNodePorts` 的旧默认用途明确隔离。表单输出增量params而不是重建节点；BSE下拉更新原port_roles，其通用方向不得冲突。端口内容“显式应用”事件独立于是否恰好等于旧默认字符串，不能再仅比较 `getNodePorts(previous)` 后省略用户确认。

- [ ] **先于本任务任何生产GUI修改**建立专用fixture和浏览器脚本，Task1版本启动真实 API/前端，确认页面和原抽屉已加载，然后断言按端口 ID 可定位的“端口角色”下拉可见；基线不存在此控件应RED，留下DOM/截图/退出码。不能把服务未启动、选择器错误或缺测试数据当RED。该前置按Task3的隔离规范执行，最终Task3另起新库GREEN。
- [ ] 纯函数RED覆盖1.1/1.2完整角色表；unknown≠bidirectional；同 ID 两个 handle 数量只计1；名字 RF5/DL1 不决定角色；只有已存 ports 决定数量；air_path/BSE数量文案不同；声明内容与当前默认相同仍可明确写入；只改名不创建声明。
- [ ] 实现原抽屉端口行（ID+角色；BSE另显示原DL/UL角色），新增/移除/清空/恢复/取消不可变更新。角色修改检查所有关联边，不只当前模式；引用未解除先拒绝。原可恢复器件列表、模式可见性、探头显式路径和4a标称组件保留。
- [ ] 拖线与连线抽屉修改共享纯验证；候选Select按source/target方向过滤，但unknown保留且标注。已有不合法旧边可读并提示，不能为了画图改其pins或角色。保存服务器422显示定位且保留草稿。
- [ ] `withDeclaredPorts` 唯一绘制显式handles，原同ID隐藏handles不能共存；`useUpdateNodeInternals`依赖包含方向与BSE角色，纯角色改变也更新几何。连接 ID 使用物理/逻辑端口原ID，不把 `in-/out-` UI前缀存为pin。
- [ ] `initialEdges` 与 `SignalEdge` 按1.2箭头契约接线，必要时传markerStart；保留PA/null/0/Cal显示。unknown草稿可编辑，但不得用箭头/颜色把它标成双向或就绪。
- [ ] `routeGraphMatchesSaved` 加入本片声明与服务器快照一致性；不客户端重算digest、不改 adoption eligibility。dirty/保存成功后旧路径缓存处理复用原服务器重选流程；普通和参考节点都覆盖，不能只比较normal端。
- [ ] 生命周期回归：打开未改/取消/应用、同显示值显式应用、角色改后再回原值、删除仍被引用端口、重新声明探头路径、切模式、切Lab、保存拒绝/断网/重试/重载、保存pending/采集running/取消未确认/释放后再进入。新组件每个输入/按钮/handle都消费原锁；未确认取消不得解锁。
- [ ] cwd=`gui`：`npx --yes tsx --test test/topologyPortContract.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts`，再 `npm run build`；变异unknown→bidirectional或跳过角色刷新依赖时对应行为用例应RED，恢复GREEN。
- [ ] 主代理安排独立任务审查；提交报告包含初始浏览器RED、GUI测试、build及本任务增量SHA，不把最后综合浏览器留空后声称已验收。

## Task 3: 真实 API 浏览器矩阵与唯一最终全量

**Files:** 沿Task2浏览器fixture/脚本/config补齐GREEN；新增 `docs/validation/2026-10-26-pc04a4b-topology-port-roles.md`，按实际进度更新本计划/roadmap。生产修复只能针对本片可观察失败，经主代理定界并重新独立审查，不提前做4c/4d。

**Interfaces:** 主代理交付全局约束和第1节、Task1/2报告、实际测试SHA/diff、Task2已保存浏览器RED路径。本任务实施者是最终全量唯一执行人；reviewer不重复全量，主代理负责结果可复用性核对。

### 隔离前置与输入

fixture参考现有 `tests/pc04a4a_browser_fixture.py` 的构造方法，不导入执行旧fixture。导入app之前要求数据库URL严格匹配 `sqlite:////tmp/pc04a4b-[A-Za-z0-9]+/browser.sqlite`、父目录存在、文件不存在和两个环境开关均true；默认bootstrap必须执行，再断言所有category/binding均mock。两Lab独立暗室、文档网段地址；manifest记录database、lab/chamber/topology/category IDs及全Mock边界。通过真实POST创建显式两链和全器件矩阵，通过真实template import建立旧CAICT；历史缺/坏数据测试只在专用fixture明确构造，不复制用户库。

```bash
lsof -nP -iTCP:18095 -iTCP:5190 -sTCP:LISTEN
pc04a4b_browser_dir=$(mktemp -d /tmp/pc04a4b-XXXXXX)
cd api-service
env DATABASE_URL="sqlite:///$pc04a4b_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4b_browser_dir/logs" .venv/bin/python -m tests.pc04a4b_browser_fixture
env DATABASE_URL="sqlite:///$pc04a4b_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4b_browser_dir/logs" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18095
```

端口占用改本次专用配置/manifest，不kill用户服务。`gui/test/pc04a4b.vite.config.ts`继承base，host127.0.0.1、port5190、strictPort:true，`/api`、`/api/v1/ws`及更具体OTA代理全部指向18095，绝不落回8000/8001。cwd=gui：`npm run dev -- --config test/pc04a4b.vite.config.ts`。真实浏览器使用当时可用browser skill支持的API，不在此计划锁死未经支持的自动化通道；测试脚本只真实HTTP，不route mock API。不开CE服务、不请求OTA硬件执行接口。

### 验收矩阵（每项保留输入、响应、GET、重载DOM/截图）

| 编号 | 动作/输入 | 必须观察的结果 |
|---|---|---|
| B01 | 新增全部原可选器件类型，含PA/衰减/合路/两线缆/天线探头参考/CE/BSE/EMCenter/开关/SA/VNA/负载/空气及旧ce/bse/sa | 未声明不可保存新设备；明确N个ID后数量=N；逻辑/虚拟端点不标物理RF口；不新增内部路径 |
| B02 | 同一器件 input/output/bidirectional/unknown 逐一应用，含只改角色不改端口列表 | handles/标签/实际边几何立即一致；unknown可草稿不标双向；无旧隐藏同IDhandle残留 |
| B03 | 16种角色组合及相同角色的多个不同命名端口 | 允许/拒绝与1.2一致，拖线与抽屉一致；直接PATCH绕GUI仍拒绝已知错误 |
| B04 | BSE RF5=dl、名字DL1但无role、UL1=ul；冲突通用声明 | 方向从role而非名字；冲突422；physical display未伪造、运行映射未被改写 |
| B05 | 旧CAICT/稀疏参考边，仅改label/位置/PA来源后保存重载 | ports/方向不自动生成、旧数值/opaque保形；未改方向时route_digest不变；版本提示不等于完成转换 |
| B06 | 新端口ID与旧默认完全相同但明确应用；删除/改名被多模式边引用的口 | 明确应用确实保存；引用错误定位所有相关边，草稿保留；不静默级联删边/路径 |
| B07 | 合法替代边→探头重声明→删旧边/旧口；错误/缺失rf_path_selection或switch_mappings | 原引用门完整；新map不构成内部通路或开关自动控制许可 |
| B08 | 新声明或改direction，保存后查看路径列表/采集选择与已有记录 | 新route_digest变化并须重选；旧快照不变；unknown→明确也不提升mock/缺证书/用途/绑定资格 |
| B09 | 非法POST is_default、PATCH部分数组、非法template replace_existing；跨Lab | 保存前后真实GET与ORM确认无副作用；Lab隔离状态码与旧契约一致 |
| B10 | 抽屉取消、应用再取消其它编辑、保存422、真实后端暂不可达后重试 | 前三态不污染原数据；失败保留草稿及4a数值意图；成功GET与重载一致；只恢复本次服务 |
| B11 | 保存pending、真实全Mock采集running、取消待服务器确认、最终释放后第二次进入 | 所有角色/端口输入、增删、拖线均锁住；未知取消不解锁；结束后可恢复编辑，不多启任务 |
| B12 | 脏图尝试切Lab、正常切Lab后回来，模式切换与隐藏器件列表恢复 | 原保护提示保留；不将Lab A角色或意图写给B；已保存节点/边恢复正确 |
| B13 | 正常与参考节点的新map、全unknown与全明确两图；已有标称/实测值 | 原损耗和校准矩阵/补偿次数不变；实测/冻结数据不改，报告不凭map出现passed |

- [x] 确认Task2的缺功能RED已有可核验输入，在最终实现输入上以全新库执行完整GREEN；不回退共享工作树补拍RED。保存三端原始JSON（POST/PATCH、GET、路径响应）与阶段截图/DOM，不用toast证明落库。原RED截图覆盖偏差按主代理裁决披露，不把后补基线截图当原件。
- [x] 扩充Task1相关后端回归：`test_pc04a2_route_selection.py`、固定采集/批任务/采用/冻结、BSE拓扑与端口映射相关测试，以实际 `rg --files tests` 清单记录命令，不猜不存在的文件。验证普通/参考两端及连续两次释放重入，不连接硬件。
- [x] Task3执行最终新库全后端一次（有功能修复后须重跑受影响验证及必要全量），记录真实退出码/结尾统计/日志/SHA/diff/依赖；本次退出1、唯一历史G8保留，不能称全绿。命令从api-service运行：

```bash
pc04a4b_full_dir=$(mktemp -d /tmp/pc04a4b-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a4b_full_dir/full.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4b_full_dir/logs" .venv/bin/python -m pytest tests -q
```

- [x] 最终GUI跑Task2命令与 `npm run build`，`git diff --check`。若唯一失败是历史G8，重新核实本次输出与基线归因并如实记失败，不修改历史、不称全绿、不复用4a的7558统计。任何新失败先定位。
- [ ] 验证摘要写各矩阵实际状态/证据、范围排除、未验证项、失败/复跑历史和原输入；正式文档不引用唯一存在本机scratch的结论而无摘要。交独立任务审查，再累计分支独立审查；所有修复有增量复审。
- [ ] 主代理根据最新功能输入核实全量与审查覆盖后再Ready PR/R1/R2；合并且同步主main后才勾选4b、启动4c。保留父项、B/HOLD、4a未覆盖V1/ASC/CE边界；本片不声称其已验证。
