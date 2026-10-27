# PC04A4c 器件内部 RF 通路实施计划

> **For agentic workers:** REQUIRED SUB-SKILL：使用 `subagent-driven-development` 串行执行 Task 1～4；每项独立规格/质量审查，最后累计分支审查。实施者不得再派子代理。主代理给每个 task brief 同时附全局约束、本文契约及已落地接口，不只交任务标题。

**Goal:** 外部连线只有穿过器件明确允许的内部端口配对才构成新声明通路；合路器不默认全互通、PA不反向贯通、负载不穿通，保存、查询、采集和正式执行读取同一约束。

**Architecture:** 在原 `TopologyNode.params` 增加可选 `internal_paths` 有向端口对白名单；保留外部 `connections`、探头 `rf_path_selection` 及既有开关 `port_maps` 身份。纯校验/穿越函数为三类路径读取链共用，GUI在原器件抽屉编辑，不新建资产、路径或自动控制系统。

**Tech Stack:** 现有 React/TypeScript/Mantine/ReactFlow、FastAPI/Pydantic、SQLAlchemy JSON、pytest、tsx/node:test；无新依赖/迁移/SCPI。

**Spec:** [已批准器件与端口设计](../design/2026-10-26-topology-device-port-contract.md)、[正式队列](../roadmap-first-call.md)。分支 `codex/pc04a4c-internal-rf-paths`；基线 `8d5bc6d48805b6de7be246e4c40940de33534fa8`。4c 已由 [PR #541](https://github.com/swang430/Meta-3D/pull/541) 于 `2026-10-26T22:31:48Z` 合并至 `39d4bb0bc27ab6e13eca04ec0f7b4c82f14eb46a`；[R2 回执](https://github.com/swang430/Meta-3D/pull/541#issuecomment-6428803419)于 `22:26:25Z` 覆盖 `fd473fba1cbad208f5604d4f2465279dab39ba7b` 无发现。主目录 main 已快进同步，用户修改与资料保留。新版最终全后端 **7822 passed /17 skipped /1 历史 G8 failed**（8597 warnings，700.70s，exit1）不称全绿；C07真实鼠标未验和现场B/HOLD边界保留。当前仅启动4d计划，4e未启动；前片验证不代表4d通过。

### 实际进度（施工规范的完成状态以此为准）

| 任务 | 已落地输入与独立审查 | 实际验证边界 |
|---|---|---|
| Task1 | 01eebe12，规格符合/质量通过 | 写入/引用/四镜像；定点276通过，非最终全后端 |
| Task2 | 7352d0b6＋89f83f06，规格符合/质量Approved | 三类解析/参考/身份/诊断；阶段14文件366与最终3文件145分别记录，不相互冒充 |
| Task3 | f67baac9，规格符合/质量Approved | 真实浏览器RED/GREEN/变异恢复，GUI88与build；原RED保留 |
| Task4原交付 | 0cc0d552，任务级Approved（C07非阻塞P3） | 原浏览器库`/tmp/pc04a4c-tRJ0AF` C01～C16/C13补证按未变GUI/API输入边界复用；GUI88/build12.18s不重复。旧全后端`/tmp/pc04a4c-KxzsaG` 7808/17/1仅f67baac9→0cc0d552历史输入，不代表累计修复 |
| 累计修复旧阶段 | 187b3b11累计P1已独立ADDRESSED | 435相关与核心变异；旧阶段专用库`/tmp/pc04a4c-GEebeR`全量7815/17/1仅187b3b11输入，不代表R1修复后版本 |
| PR #541 R1修复与新版补验 | 71774b09，原reviewer独立内审ADDRESSED，无新增功能缺陷 | 442相关及四项核心变异恢复；新库`/tmp/pc04a4c-WSV9eC`唯一最终全后端7822通过/17跳过/1历史G8失败/8597 warnings，700.70s，exit1，1174输入及依赖起止一致。[正式摘要](../validation/2026-10-27-pc04a4c-internal-rf-paths.md)区分新旧与GUI/浏览器复用边界；R2覆盖最终HEAD无发现，PR #541已合并39d4bb0b |

下方逐步清单保留施工/复现规范，不以原计划空框否定本表已证实状态；独立内审、R1修复及覆盖最终HEAD的R2已完成，PR #541已合并。当前进入4d计划，不重复4c验证。

## Global Constraints

- 图边为外部接线，器件内部连通关系独立声明。多端口器件不得默认全互通。开关继续复用现有 port_maps/switch_id/继电器身份，不新增第二套自动切换配置。
- params.ports 继续是端口 ID 清单；端口不是左右接点数量。名称不隐式决定方向。角色独立为 input/output/bidirectional/unknown；unknown 不冒充双向能力。
- 复用基站 port_roles 的 dl/ul 权威关系，不用通用角色覆盖它；新角色与其冲突必须拒绝，而非选一端。
- 校准来源、原始采集和历史执行冻结保持只读；整链实测只在原采用入口生效一次。禁止额外叠加节点增益。
- 不做4d旧图转换预览/模板补齐/批量回写，不改原证书期限、采用政策、损耗公式、资格门、SCPI、硬件绑定或原继电器协议域。现场B/HOLD及父项不关闭。
- 新声明只是操作员接线约束，不证明实物内部结构、射频导通或可控性；unknown和Mock不得因声明完整变为real/passed/eligible。BSE物理口继续来自原route snapshot，CE口继续用原解析。
- 保留4a数值意图、缺键/原JSON、null/0、opaque及4b角色/旧边只读几何。无关改名/位置保存不补声明，不改历史摘要或冻结。内部通路不得带新增增益/损耗数值，外部边不被拆成虚构内部边。
- 复用 `editingBlocked`、`savingRef`、`collectionBusyRef` 与现有服务器作业锁；保存失败/取消未确认不丢草稿或提前解锁。不建立第二个锁/重试状态机。
- 所有Python app导入、pytest、fixture/API进程启动**之前**设置本片新建临时SQLite、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`；默认bootstrap真实执行后核查所有category和Lab binding均Mock。不读写用户DB，不启动/停止用户服务，不清理worktree、venv、DB、output、scratch。
- 验证档位：GUI/API四镜像＋共享路径/冻结匹配；Task 4实施者是**唯一最终全后端执行责任人**。Task1～3只做定点相关回归，reviewer复用同输入证据，禁止提前或重复全量。后续功能/测试/fixture/依赖变化由主代理重新判影响并安排同一责任位补跑。
- 每任务先生产入口RED，后实现/GREEN/核心变异恢复，再独立规格与质量审查；GUI必须先真实HTTP浏览器RED再生产UI修改。计划提交本身不push、不建PR；最终Ready PR按AGENTS R1/R2/最新HEAD无P1规则，不为回填状态递归开PR。
- 已读memory仅用于边界提醒，当前事实来自本次源码及GitHub回读。NotebookLM当前不适用：本片只定义应用声明；一旦结论依赖仪器语义，先匹配厂商原文，未证实保持unknown，交主代理重定界。

## 0. 已核对的生成/消费全集

以下文件均相对仓库根；`app/`在`api-service/`下。这里描述基线代码，不当作硬件能力证明。修改前重跑：

```bash
git grep -n -E 'resolve_saved_rf_path|selected_switch_mappings|rf_execution_identity|execution_route_identity' -- api-service/app
git grep -n -E 'internal_paths|rf_path_selection|port_maps|routeGraphMatchesSaved|probePathDeclaration' -- api-service/app gui/src
git grep -n -E 'get_end_to_end_loss|_find_shortest_path|_dfs_paths|resolve_paths|get_calibration_matrix' -- api-service/app
git grep -n -E '绝不|不许|禁止|must not|别把' -- api-service/app/services/declared_rf_routes.py api-service/app/services/topology_service.py api-service/app/services/mimo_ota/route_calibration_freeze.py gui/src/features/TopologyEditor
```

| 入口/生产者 | 权威、处理和任务 | 消费者及必须观察的断言 |
|---|---|---|
| `schemas/switch_topology.py::TopologyNode.params`；`preserve_graph_rows/preserve_connection_rows` | 原开放JSON保形；新字段不赋默认值；Task1增加严格声明验证 | GET/list/POST/PATCH/import原始JSON缺键保持缺键，不把[]补给历史 |
| `api/switch_topology.py::create_switch_topology/update_switch_topology/import_topology_from_template` | 最终候选图：保形→结构/端口/内部声明→默认位/删除替换/ORM；Task1 | POST/PATCH部分数组与全图/import错误422前无任何写入；跨Lab409/非法Lab422不变 |
| `_validate_structure` → `resolve_saved_rf_path` | 当前保存显式路径会调用运行解析；Task1/2明确保存兼容与运行约束分离，保留引用连续性/环/端口/探头/开关映射形态检查 | 旧图纯name/label/position roundtrip可存；新声明错误不能借兼容放过，显式路径失配定位探头/节点/端口/边 |
| `TopologyEditor.tsx::openNode/addNode/applyNodeEdit/onConnect/applyConnectionEdit/handleSave`；`topologyDraft.ts::updateDraftNode/updateDraftConnection/removeDraftConnections/removeDraftNodes` | Task3抽屉产生内部声明；端口删改及所有模式引用校验；原外部边/损耗归属不变 | 仅开抽屉/取消/标签改名不物化字段；重新接线/删内部pair后不能保留失效显式路线 |
| `PortDeclarationFields.tsx` / `nodePortHelpers.ts::resolveNodePorts/validateNodePortDeclaration` | 端口及有效方向仍4b真值；Task3新组件只消费，必要时在端口应用前增加内部引用检查 | 清单删除口不能偷偷删除internal_paths；BSE dl/ul不被新编辑器覆盖 |
| `declared_rf_routes.py::resolve_saved_rf_path` | 当前唯一链以节点级incoming/outgoing判断，显式链拒绝全部非开关分叉；Task2换成选中入/出pin配对检查 | 显式合路/分路只放行已列pair；未选支路不串入；缺pair/反向PA/负载中转拒绝 |
| `declared_rf_routes.py::selected_switch_mappings/validate_simultaneous_switch_mappings/switch_execution_identity`；`route_calibration.py::route_switch_steps` | 开关配对与物理继电器身份继续唯一来源；Task2仅让内部白名单作为额外结构约束 | internal_paths绝不替代path_name/port_maps；配对缺失/冲突仍拒绝，不能让合路器变自动开关 |
| `TopologyService.resolve_paths/_dfs_paths/_find_shortest_path/get_end_to_end_loss/get_calibration_matrix/validate` | Task2 DFS/BFS/validate按connection ID从`self._raw`保存连接取pin，不能读已补out/in的连接对象证明端点；同一端口级穿越，路径状态至少包含原始入pin | 公开`/paths/{mode}`、`/calibration-matrix/{mode}`没有禁止或缺端点通路；BFS不可借另一输入口穿越，缺pin时不得输出完整路径损耗；负载可终止不可继续 |
| `calibration/route_calibration.py::_route_selections` 普通段与参考BFS | Task2正常段复用共享解析；参考段逐相邻边检查同一内部声明，不只normal节点 | ordinary/individual/指定terminal三入口一致；参考receive_cable/参考PA坏pair拒绝；探头→空气参考面是原模型边界，不要求探头新造内部RF转发 |
| `calibration/configuration_scope.py::build_calibration_scope/build_selected_route_calibration_scope/_build_scope_payload` | 当前完整params摘要和selected_route_digest已经消费新字段；Task2回归，无需另造摘要或排除键 | 声明改变后新scope/digest变化；纯显示改动旧规则保持；不将盘点提醒改成资格撤销 |
| `fixed_route_jobs.py::resolve_configuration` 及启动后重核；`route_batch_plan.py::build_batch_plan`；`route_batch_jobs.py` | 共用保存路径与scope，Task2读/回归；预览零I/O、start重新核验 | 缺pair/过期route_digest/preview_digest在创建作业或硬件动作前拒绝；同CE非互斥分路仍不当可串行开关 |
| `evaluate_route_application/confirm_route_application/list_route_applications` | 当前匹配重核与历史只读保持；Task2回归 | 旧采集与新声明不匹配不能采用；历史快照、Mock门、net_loss_db不改 |
| `mimo_ota/switch_orchestrator.py::orchestrate_switch_topology/_build_probe_binding` | 有显式路径、无显式路径且经中间器件、直接CE→probe三分支；Task2都接共享穿越核验，不只首分支 | 正式actual target不经负载/禁止pair；同CE唯一门和原BSE端口过滤不放宽 |
| `calibration/rf_chain_resolver.py::resolve_rf_chains` → `switch_orchestrator` → CE/预检消费者 | Task2回归共享正式链路，不把中间器件标签当CE口 | CE/probe/polarization仍原真值，未知不补真，不变ASC/CE量值政策 |
| `declared_rf_routes.py::rf_execution_identity` → `route_calibration_freeze.py::_execution_route/_validate/frozen_route_identity_error` | Task2按R2最小身份扩展；当前actual-target分支仅比较含switch_mappings身份是漏点 | DB-current和实际resolved_topology两分支均发现内部路径变化；旧历史无新字段仍按原投影读取，不能因新校验使历史报告不可读 |
| `mimo_ota/path_loss_preflight.py::evaluate_path_loss_preflight`、`executors/measure.py`的`frozen_route_identity_error`调用 | Task2生产调用回归、原则上不改执行器；不能只单测helper | 拒绝发生在正式测量前；输入frozen/actual-target来源可追，不靠全局单例猜 |
| `routeCalibrationState.ts::routeGraphMatchesSaved/routeMatchesSaved/probePathDeclaration/buildRouteAcquisitionRequest/buildBatchRequest/batchStartRequest` | params全比较已覆盖新键；Task3复用/补内部pair本地错误定位，不重算服务器digest | 正常和参考声明变更均使旧选择不可用；重载重选后仍沿原资格门 |
| live Pydantic、`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts`＋真实响应 | Task1四镜像，只同步CRUD参数说明/递归闭包；生成TS不得手改 | 新声明JSON往返/checked-live一致；未被live引用的独立schema不得声称自动进入闭包 |
| `scripts/dev-fixtures/topology-templates/caict_v4.py`等模板、旧ce/bse/sa | 原文件不改；Task1/4导入兼容取证 | 旧图未转换、未补内部pair；4d独立承担用户显式转换 |

## 1. 唯一字段契约、路径规则与预检裁决

### 1.1 数据形态与方向

```ts
export type TopologyInternalPath = { from_port: string; to_port: string };
// 位于原node.params，不新增外部connection，不携带gain/loss/switch命令。
// internal_paths?: TopologyInternalPath[];
const declaredExample = {
  ports: ['IN1', 'IN2', 'OUT'],
  port_directions: {IN1: 'input', IN2: 'input', OUT: 'output'},
  internal_paths: [
    {from_port: 'IN1', to_port: 'OUT'},
    {from_port: 'IN2', to_port: 'OUT'},
  ],
};
```

- 每行恰为`from_port/to_port`两键；非空无首尾空白字符串，区分大小写，均属于显式`params.ports`，两端不同；同向pair唯一。拒绝null、布尔、数字、数组中的非对象/多余键、自环、重复、孤立端口；不接受`bidirectional:true`或开关位置字段。
- 缺键＝旧版未声明；`[]`＝明确无内部贯通；两者不等价。反向需另写反向pair，不能由bidirectional端口、Bi-Di外边、型号或命名推导。
- 内部方向与外部源/靶方向不同：入器件的`from_port`不可为已知output；出器件的`to_port`不可为已知input。unknown可以保存声明草稿但不证明方向/能力；同样不得覆盖BSE权威。**运行明确规则：有internal_paths的新声明中转，选中from有效方向必须input或bidirectional，to必须output或bidirectional；任一unknown即不可作为可采集/正式运行的完整路径，返回“内部通路方向未声明”而非补真。** 普通路径查询亦不枚举为完整通路，只在validate提示；尚未组成/方向未知草稿可保存（即使探头保存了结构合法connection_ids），不因保存成功解运行门。旧缺字段兼容仅按R1保留原状态，不把旧unknown改成新声明。
- 所选穿越定义为前一外边`target_pin`→后一外边`source_pin`；新显式声明必须使用外边实际保存的pin，不接受schema默认out/in补作新证据。起点无入边、终点无出边，无需凭空生成内部pair。
- 不新增每pair模式字段。内部物理声明对所有模式生效；模式仍只决定原外部边集合。`active_connections=[]`继续回退边自身`modes`。所有引用保护必须遍历全部模式，不能只看当前画布。

| 器件类别 | 非空声明规则 | 运行处理 |
|---|---|---|
| `amplifier` | 两个显式端口，只允许一条入→出pair；禁止反向pair并存。未填方向不由名字补 | 缺/反向pair不通；标称增益不参与新路径计算 |
| `pad/cable/receive_cable` | 两个显式端口；可声明一个方向或两个相反方向，各方向独立 | 仅列表方向可穿越，不增加第二份线损 |
| `combiner` | 明确N端口及任意合法有向pair列表，不固定4合1，不按数量生成pair | 仅已列pair；可表示合路或分路声明，但多候选选择不唯一时要求原探头显式路径；不承诺同时隔离/功率能力 |
| `switch_slot` | ports内有向pair可作结构约束；不允许path_name/relay/position进入新字段 | 仍须原rf_path_selection.switch_mappings→port_maps精确pin配对和同继电器互锁；缺映射不能凭pair执行 |
| `termination` | 仅允许缺键或[]，非空一律422 | 即使历史没有字段，也无中转路径；通用路径可在负载终止，但不能把其下游当连通 |
| `air_path/reference_antenna/antenna/probe` | 可保持原参考模型；新字段若显式存在只作为所声明端点之间约束，不推导物理口/辐射能力 | 正常probe/antenna为终点；参考段从已选probe另起，不能因此要求probe将正常RF输入穿至虚拟参考输出。参考链中间air_path/reference_antenna有声明则遵守，缺声明只沿原唯一参考模型；显式多端口缺pair仍拒绝 |
| `ce_port/channel_emulator/bse_port/communication_tester/sa_port/signal_analyzer/vna/emcenter` | 本片不提供非空内部通路编辑；明确非空拒绝，缺键/[]可读 | CE/BSE为原源、SA为参考终点；禁止拿此字段新建CE/仪器内部转发或EMCenter第二套控制，旧专用路径仍原门 |

### 1.2 写入与旧图兼容（不做迁移）

`validate_internal_path_write(nodes, connections, modes, *, previous_nodes=None, previous_connections=None, previous_modes=None, allow_legacy_missing=False) -> None`：只读最终候选原JSON，错误抛`ValueError`；API适配为422。previous只能来自同Lab已加载原行；不得以客户端previous为依据。

| 请求场景 | 必须验证 | 兼容与原子性 |
|---|---|---|
| POST、新插节点、同ID换type | 存在的新字段按1.1严验；新中间器件欲被显式路线选中必须有匹配内部声明 | 未接线或尚无路线声明器件可保存缺声明草稿，查询不授予已声明路径；不把绘图建议持久化 |
| PATCH内部pair/ports/directions/type变化 | 完整字段形态、每条内部pair、关联全部外边及受影响的已存显式路径；声明方向冲突必须拒绝 | 不自动删pair/外边/探头声明；错误说明包含节点、pair与相关外边/探头ID，默认位与整行不变 |
| PATCH只有节点label/position、图name/4a标称、GET全量往返 | 原有结构/引用检查保持；未触及内部路径契约不要求旧图补字段 | 稀疏pins、无声明、opaque逐字保形；运行不能解析不等于禁止无关保存 |
| PATCH新边/重接pins/修改模式使路线生效 | 校验受影响已存显式路径及所有显式内部声明；只考虑同模式实际相邻外边，避免跨模式笛卡尔积误报 | `[]`不可绕过；不能把变更当无关保存；非路径草稿仍可存但不能返回贯通路线 |
| PATCH删除internal_paths | 视为主动撤销，不是历史缺键；若仍有显式路径依赖该节点即拒绝，先撤销/改好原探头声明或使用[]并解除依赖 | 不靠删除键恢复旧推断；服务器须用previous判意图，GUI显示引用原因 |
| import/from-template | 缺字段旧模板原样；明确存在的新字段必须合法；显式内部路径引用须有效 | 在replace删行前完成验证，不改模板强行过门；旧转换仍4d |
| GET/list/历史读取 | 原值透传，坏旧值只读提示未知/不可解析 | 不修复、不回写、不填默认，不以一次GET触发迁移 |

保存入口`_validate_structure`现调用运行解析，Task2加`check_internal_paths: bool = True`关键字参数，仅保存原结构检查传`False`；这个开关不能关闭旧引用/连续性/环/源端/参考作用域检查。保存后再运行上表内部写入校验，明确的新声明和主动变化仍严格。所有运行消费者保持默认True，**禁止从HTTP请求暴露开关**。

写入校验与运行校验只共享字段解析、pair成员和已知方向冲突规则；写入允许unknown草稿，不直接调用会拒绝unknown的`internal_transition`。运行helper每次先验证现存字段形态（不能只信曾经保存通过）；旧脏字段读运行保持unknown/拒绝，而不是异常500。

### 1.3 主代理已明确的推荐边界与独立计划审查重点

R1（兼容运行范围）：主代理已明确“旧保存与运行分开，负载不通，多端口不能推全互通；两端唯一链须具体白名单及端口依据”。据此本计划采用以下可测试边界，交独立计划审查核验，不重复问用户：

| 旧缺internal_paths的类别/证据 | 允许的兼容范围 | 拒绝与证据依据 |
|---|---|---|
| `amplifier/pad/cable/receive_cable`，已有合法显式ports恰为2个，实际相邻边两pin都明确保存、不同且集合恰等于ports，当前模式各1入/1出 | 保持原有顺序链，仅返回legacy，不创建pair、不宣称已核验；已有明确方向与本次入/出相矛盾时拒绝 | ports缺失、>2、pin缺失/同口/不属于清单、分叉都拒绝运行；只靠外边数/默认handle/型号/nominal字段不算“两端证据”。白名单是批准设计中双端应用器件分类，实际端口依据仅保存ports/pins，不据此断言厂商物理能力 |
| `combiner` | 不走双端兼容，即使当前只接两根线也须声明pair | 设计明确其数量可变且不得全互通；两根外线不证明内部连通 |
| `switch_slot` | 不由双端helper猜；缺internal_paths时只沿原显式rf_path_selection.switch_mappings与绑定port_maps的精确配对 | 复用原selected_switch_mappings及relay身份。正式/采集缺映射拒绝；不新增配置或猜默认位置。通用TopologyService无绑定上下文时不推定缺声明开关穿越，可显示未解析原因 |
| `air_path/reference_antenna`参考链中间节点 | 缺字段且原唯一参考链时保持原虚拟参考模型，返回legacy；若保存了>2个显式端点则不兼容 | 这是既有参考模型边界，不是RF两端器件白名单；任何明确internal_paths都必须检查。正常路径仍禁止参考器件 |
| `probe/antenna`正常末端、CE起点、SA参考末端 | 无中转，不调用内部穿越；probe→参考段另起边界 | 不把正常入pin与虚拟参考出pin拼成物理内部通路；其他非白名单器件无声明中转拒绝 |

上述收窄可能使缺物理端口依据的旧路径暂不可运行，但仍可GET/改名/移位保存，提示“内部通路未声明/端口依据不足”，不自动改原校准记录或宣告证书无效。Task2必须保留这种真实兼容边界的反例；为验证其它功能而需要可运行链的测试fixture可显式补两端证据，但不得把专门的旧缺端口用例改成新图掩盖行为变化。所有有字段（含[]）的节点严格按白名单，不凭缺键授新资格。

R2（冻结匹配最小扩展）：主代理已允许最小所选内部穿越身份与actual-target匹配扩展。在`rf_execution_identity`仅对具有明确内部声明的所选中间节点增加`internal_paths`投影：`[{node_id, from_port, to_port}]`，按路径顺序；不含未选pair、描述或名义数值。旧无字段路线不加新键，保持原历史投影。`frozen_route_identity_error`的DB-current与actual-target都比较该身份，不能只在switch_mappings存在时比较。历史只读`_validate`不得调用当前运行校验或借当前图补新字段。不改冻结版本、历史数据、补偿值/算法或采用政策；独立计划审查仍须核实以下对称矩阵：

| 冻结身份 / 当前实际身份 | 历史只读 | 当前运行匹配 |
|---|---|---|
| 两者均无internal_paths | 原快照自洽投影，不查当前图 | 保留原比较形态/规则，无新键注入 |
| 冻结无键，当前新增声明有键 | 旧历史仍可读 | 不把当前新键删掉冒称同一路线；创建新执行重新确认 |
| 冻结有键，当前无键/[]/禁止pair | 原历史仍可读 | 运行解析失败或身份不等拒绝，不降级legacy |
| 两者有键且选中pair相同 | 自洽读取 | 与原节点/边/开关身份共同相等才通过匹配，不授任何额外资格 |
| 两者有键且pair改变 | 历史不重写 | DB-current及resolved_topology两端都拒绝；包括无switch的链 |

### 1.4 运行与身份共同接口

新增纯模块`api-service/app/schemas/topology_internal_paths.py`，由Task1提供，Task2消费；函数不访问DB/HAL，不推导厂商能力。返回旧式兼容与明确声明必须可区分，不能都叫verified。

```python
def validate_internal_path_write(nodes, connections, modes, *, previous_nodes=None,
                                 previous_connections=None, previous_modes=None,
                                 allow_legacy_missing=False) -> None: ...

def internal_transition(node: dict, from_port: str, to_port: str, *,
                        incoming_count: int, outgoing_count: int) -> str:
    # 返回 'declared' / 'legacy'；禁止或无依据抛ValueError。
    # 只有Task1实现此规则，其他消费者不得复制type白名单或default all-to-all。
    ...

def validate_internal_traversals(path_nodes: list[dict], path_edges: list[dict], *,
                                 active_connections: list[dict]) -> list[dict]:
    # 每个中间节点取上一target_pin、下一source_pin；返回选中declared穿越，
    # 形态[{node_id, from_port, to_port}]；legacy不伪造新身份。
    ...
```

以上省略号仅为接口签名，不是实现步骤；Task1下方给出关键实现顺序与可运行RED。入口/出口计数按当前有效模式（参考段用calibration），不是整张图所有模式混算。相邻端口相同也不是“零长度自动相连”；内部自环拒绝。

`path_edges/active_connections`端口依据必须是原保存JSON，不是经过默认值填充的连接对象。`TopologyService`已有`self._raw`保留输入，按connection ID读取其中原始`source_pin/target_pin`，缺键不填out/in；新声明和R1旧双端兼容共用这个来源。原`TopologyConnection`展示/损耗对象及旧序列化默认可保留，不为此全局改模型；纯穿越helper接收前须拒绝缺键、null、空串或非字符串pin，不能把它们转换成默认字符串。

`resolve_saved_rf_path(nodes, active_connections, terminal_connection_id, *, check_internal_paths=True) -> tuple[list[dict], list[dict]]`保留返回形态；选中路径核验内部穿越。显式合路器分支放行必须同时满足保存的连接序列、每个pair、无环、CE/probe规则及全部既有开关门；无显式选择有多条可达路线仍拒绝。`TopologyService`仅在表示一般路径时枚举允许分支，不以路径可见替代正式集合资格。

`rf_execution_identity(nodes, edges, switch_identity=()) -> dict`保留签名，按R2从保存列表投影所选pair；**投影不得执行运行严验**，否则旧历史读会因新规则坏掉。当前运行先校验再投影，历史读取只做原冻结自洽校验。

开关缺内部字段的纯声明解析只标记“需原映射核验”，不在`validate_internal_traversals`内造新pair；其返回列表仍只含明确声明。`route_calibration`和`switch_orchestrator`必须在将路径返回为可用/生成正式binding前完成原`route_switch_steps/selected_switch_mappings`，无探头映射不得直接返回可用。`TopologyService`没有绑定上下文，缺声明开关不枚举完整路径，在validate给未解析提示；有内部声明的开关仅展示声明图可达性，不授自动执行资格。

## Task 1: 内部声明写契约、引用保护与四镜像

**Files:** 新建`api-service/app/schemas/topology_internal_paths.py`、`api-service/tests/test_pc04a4c_internal_contract.py`；修改`api-service/app/api/switch_topology.py`、`api-service/app/schemas/switch_topology.py`、`api/openapi.yaml`、`gui/src/types/api.generated.ts`（生成）、`gui/src/api/switchTopologyService.ts`（辅助类型）。必要fixture仅在已有测试不再表达自身目的时最小调整，禁止把历史兼容用例全补新字段。

**Interfaces:** 消费`topology_ports.resolve_port_direction`、`topology_nominal.MISSING/same_json`与最终保形图；产出1.4三个纯函数及`TopologyInternalPath`类型。运行解析接线由Task2负责，本任务先证明声明保存原子性，不能把未接入的普通/参考解析称已完成。

- [ ] **Step 1：写HTTP RED。** 复用`test_pc04a4b_port_contract.py`的`client/world/seed/post/graph`与真实SQLAlchemy；不替换API。以下首条先运行，基线会因开放params接受非法字段而红：

```python
from tests.test_pc04a4b_port_contract import client, setup_database, world, graph, post

def test_post_rejects_internal_reference_outside_ports(world):
    payload = graph()
    payload['nodes'][0]['params']['internal_paths'] = [
        {'from_port': 'missing', 'to_port': 'out'}]
    response = post(world, payload)
    assert response.status_code == 422, response.text
    assert 'a' in str(response.json()['detail'])
```

- [ ] **Step 2：实跑RED并留原件。** 新`mktemp`目录、下面环境命令，只跑新测试；确认失败是HTTP201而非导入/fixture失败。记录HEAD、diff、DB路径、命令、退出码/断言及末行，不覆盖后续GREEN输出。
- [ ] **Step 3：补参数矩阵。** 正例合路IN1→OUT/IN2→OUT、双向线缆两条pair、PA单向、[]、缺键旧图；反例1.1全部坏形态、PA反向双行、三端pad、负载非空、仪器非空、孤立pin、端口删改/方向冲突。POST default、PATCH name/default+非法pair、非法template replace同时从真实GET与ORM refresh断言行数、原图/default未变。跨模式和无active列表回退必须覆盖。
- [ ] **Step 4：最小实现。** 原结构校验先保证索引，再`validate_internal_path_write`；遍历raw字段按精确类型/键集合检查，复用4b方向权威；前后节点按ID及type/ports/directions/internal_paths/探头声明/外边端点/模式变化判受影响。`previous`缺键与主动删除分开；全模式受影响显式路线必须检查选中pair；不逐模式拼所有入出边笛卡尔积。核心穿越顺序如下：

```python
# internal_transition 的规则顺序（node/ports已由同模块声明校验）：
if node['type'] == 'termination':
    raise ValueError(f"器件 {node['id']} 为负载，不能作为中转")
params = node.get('params') or {}
if 'internal_paths' in params:
    pair = {'from_port': from_port, 'to_port': to_port}
    if pair not in params['internal_paths']:
        raise ValueError(f"器件 {node['id']} 未声明内部通路 {from_port}→{to_port}")
    if (resolve_port_direction(node, from_port)[0] not in {'input', 'bidirectional'}
            or resolve_port_direction(node, to_port)[0] not in {'output', 'bidirectional'}):
        raise ValueError(f"器件 {node['id']} 内部通路方向未声明或冲突")
    return 'declared'
# 此后严格按R1裁决，仅原唯一链兼容；不是创建一个默认pair列表。
ports = params.get('ports')
if (node['type'] not in {'amplifier', 'pad', 'cable', 'receive_cable'}
        or not isinstance(ports, list) or len(ports) != 2
        or not isinstance(from_port, str) or not isinstance(to_port, str)
        or from_port == to_port or {from_port, to_port} != set(ports)
        or incoming_count != 1 or outgoing_count != 1):
    raise ValueError(f"器件 {node['id']} 内部通路未声明，不能推定多端口贯通")
# 已有明确方向矛盾仍拒绝；unknown不在此被改写为双向。
if resolve_port_direction(node, from_port)[0] == 'output' or resolve_port_direction(node, to_port)[0] == 'input':
    raise ValueError(f"器件 {node['id']} 旧顺序链与已声明方向冲突")
return 'legacy'
```

运行模型中参考虚拟端点例外、既有开关映射分别按1.3表在调用边界处理；不得靠node名称跳过已显式internal_paths。首/末节点不是中转，不传给上例。开关缺字段时共享纯helper不能独自证明可穿越；必须完成原映射配对才返回正常路径，通用无绑定路径不得fallback全互通。

- [ ] **Step 5：四镜像和保形。** `params`保持开放，不默认注入；live schema description列字段/缺键/[]/方向及旧兼容；只同步CRUD递归闭包，cwd gui运行`npm run openapi:generate`。HTTP真实JSON、live OpenAPI、checked OpenAPI、generated TS及手写类型核对，不创建未引用schema空壳。
- [ ] **Step 6：GREEN/核心保护。** 同以下相关命令运行，临时绕过一个写入口验证非法POST/PATCH会红，恢复后检查diff与GREEN；不跑全量。报告三入口是否全消费失败信号。

```bash
cd api-service
pc04a4c_test_dir=$(mktemp -d /tmp/pc04a4c-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a4c_test_dir/test.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4c_test_dir/logs" .venv/bin/python -m pytest tests/test_pc04a4c_internal_contract.py tests/test_pc04a4b_port_contract.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a3_topology_recovery.py tests/test_p1_57_topology_lab_context.py -q
```

**恢复/锁矩阵：** API拒绝/异常前不改ORM；GUI尚无新控件，不改变原锁。旧无关改名、位置、标称、稀疏GET回传、取消未写入、跨Lab均有明确状态断言；模式/端口/内部pair主动变更不得走旧豁免。报告路径`task-1-report.md`；提交`feat: 校验拓扑内部通路声明与引用`，主代理独立规格/质量通过才Task2。

## Task 2: 三类路径解析、开关映射与当前冻结匹配

**Files:** 修改`api-service/app/services/declared_rf_routes.py`、`api-service/app/services/topology_service.py`、`api-service/app/services/calibration/route_calibration.py`、`api-service/app/services/mimo_ota/switch_orchestrator.py`、`api-service/app/api/switch_topology.py`保存解析参数；按R2最小修改`api-service/app/services/mimo_ota/route_calibration_freeze.py`。新建`api-service/tests/test_pc04a4c_internal_routes.py`、`api-service/tests/test_pc04a4c_internal_identity.py`。`configuration_scope.py/fixed_route_jobs.py/route_batch_plan.py/rf_chain_resolver.py/path_loss_preflight.py/executors/measure.py`是必须跟踪/回归消费者，原则上不改；若确有同根必要遗漏先报主代理并写Ruling。

**Interfaces:** 消费Task1三个纯函数和原`selected_switch_mappings`；产出1.4保持旧签名/返回形态的路径解析与identity。保存兼容只用于`_validate_structure`，所有运行读取都默认严格。正式执行和参考段不能各复制一套内部通路判据。

- [ ] **Step 1：先写真实HTTP RED。** 用`test_pc04a2_route_selection.py`的`client/configured/graph/paths`，在专用fixture已知合法两端pad上声明`[]`后请求路径，基线仍200应红；再用反方向声明及负载中转证明实际错误。示例独立于GUI：

```python
import copy
from tests.test_pc04a2_route_selection import (
    client, configured, graph, paths, db_session, chamber, topology_two_chains, lab_profile)

def test_saved_route_cannot_cross_explicitly_disconnected_pad(client, configured, graph, db_session):
    nodes = copy.deepcopy(graph.nodes)
    nodes[1]['params']['internal_paths'] = []
    graph.nodes = nodes
    db_session.commit()  # 仅隔离fixture构造已存形态，不绕过生产API证明保存。
    response = paths(client, configured, graph)
    assert response.status_code == 422, response.text
    assert 'pad1' in str(response.json()['detail'])
```

- [ ] **Step 2：完整正反例。** 真实POST/PATCH产生合法CE→PA→pad→combiner→probe链，显式rf_path_selection选择一个合法支路；路径响应只含该支路/原CE口。缺pair、PA反向、负载中转、声明三口无pair、已存脏声明、环、缺pin/映射、同继电器冲突拒绝。声明combiner IN1→OUT与IN2→OUT不可导出IN1→IN2；splitter同CE两探头仍过原simultaneous重复CE门、batch同CE缺互斥映射仍拒绝。
  补明确反例：隔离fixture保存CE→pad→probe，pad含`ports=['in','out']`、方向input/output及`internal_paths=[{from_port:'in',to_port:'out'}]`，没有探头显式路径；分别删入边`target_pin`、出边`source_pin`及两者。公共paths不得列出该CE→probe完整路径，matrix不得含其path_id，`get_end_to_end_loss`返回None，validate定位缺pin的原连接ID。移除internal_paths后相同稀疏图也不得借R1兼容；补回实际保存pin后对应明确/legacy正例恢复。读API前后原JSON缺键不变；不能仅断言helper拒绝而漏公开查询。
- [ ] **Step 3：接三类解析。** `resolve_saved_rf_path`在顺序重建后校验每个中转pair；只对明确内部pair的非开关分叉解除旧一刀切拒绝，缺字段保持R1。`TopologyService` DFS以`path_hops[-1][1].id`和候选边id定位`self._raw['connections']`中的原保存连接，分别取原始`target_pin`/`source_pin`；**不得取连接对象的同名属性**，因为`__init__`已给它们补out/in。BFS和validate也只消费同一原始连接索引与缺键判定；R1旧双端兼容不得走已补值对象。进入helper前检查两个键实际存在且为非空字符串，否则跳过该贯通并由validate列出节点/原连接ID，不造完整路径或损耗。BFS queue/visited按`(node_id, 原始incoming_pin)`而不是只按node，路径终点负载不可扩展。原展示/损耗连接对象和旧序列化默认保留，无需全局修改。拒绝某个候选pair时DFS/BFS跳过该分支并由validate列原因，不把局部不通冒成500；字段合法、raw端口及方向明确的未选/未声明交叉候选只提示warning，不因此判整图非法；明确选中路径失效、坏声明或缺raw pin仍error，诊断不得按错误文案分类，也不改变运行拒绝。已保存显式探头路径只能返回其选中connection_ids。原path_id、损耗/相位累加与calibration_status算法不扩域；若仍有同source→target的多条候选造成旧path_id碰撞，在公共paths/matrix返回422要求显式选择，不让字典最后写入覆盖另一条损耗。API两读取入口捕获该ValueError，不能返回500；测试保留双支路同端点正反例，不新增矩阵格式。
- [ ] **Step 4：参考段与正式绑定全入口。** `_route_selections`参考BFS对中间参考节点检查前后pin，不把正常probe终点到参考模型起点误作RF穿越；普通/individual/explicit selection同源。`switch_orchestrator`显式、旧中间链、直接CE三分支在生成binding前核验；旧allow_incomplete的CE解释保持原范围。获取path后仍跑绑定port_maps精确配对和互锁，不把internal_paths转换成继电器命令/位置。
- [ ] **Step 5：按R2最小扩展身份。** `rf_execution_identity`从历史/当前各自保存的nodes/edges投影所选明确pair；无新声明不加键。`frozen_route_identity_error`读取权威actual-target时，冻结端或实际端任一带internal_paths都必须比较完整identity（否则旧冻结无键→新实际有键仍会漏掉），原switch_mappings比较保留；无显式probe声明但有内部声明的binding同样产出identity。DB-current路径同样比较。旧历史`_validate`可重读、不访问当前图、不运行新严验；对新声明删除/反转/改端口的当前执行明确拒绝，不能降为legacy忽略。
- [ ] **Step 6：真实链生命周期/摘要。** normal和reference两段分别改pair：新route_digest及selected-route configuration_digest改变；normal变化也改变普通mode configuration_digest，reference变化时普通mode scope可按既有仅正常活跃节点边界保持不变，不扩摘要契约。旧选择POST422、旧batch preview启动拒绝；采集中改保存图由原启动/重核路径拒绝，不从新表单授权限。只改内部列表顺序按现有params摘要规则确实可能需重选，不偷偷canonicalize改历史。未选pair变更可使route_digest变化，但execution identity仅选中pair，说明“重新选择”和“正在执行实际接线变化”不是同一判据。
- [ ] **Step 7：历史/资格/补偿。** 用`test_pc04a2_route_freeze.py`和`test_pc04a2_route_compensation.py`真实生产builder及正式preflight/actual-target输入，明确冻结前/冻结后新图改变两条路径都拒绝旧匹配；旧无字段快照读值逐字不改。Mock仍samples空/net_loss null/formal_eligible=false/采用拒绝；缺绑定/映射/参考量不因pair完整消失。旧整链数值与补偿一次性、旧PA边/节点nominal双记不叠加。
- [ ] **Step 8：GREEN/核心变异。** 以下相关链回归，不全量；临时移除参考段核验和actual-target内部身份比较，各自行为断言须RED，恢复并核对输入散列。保留非法图查询不调用HAL的spy；不替换parser/builder/session来造正例。

```bash
cd api-service
pc04a4c_route_dir=$(mktemp -d /tmp/pc04a4c-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a4c_route_dir/routes.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4c_route_dir/logs" .venv/bin/python -m pytest tests/test_pc04a4c_internal_contract.py tests/test_pc04a4c_internal_routes.py tests/test_pc04a4c_internal_identity.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc_04a_fixed_route_api.py tests/test_pc06a1_batch_plan.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_safety.py tests/test_p1_73a_base_station_topology.py tests/test_rf_chain_resolver.py -q
```

**恢复/锁矩阵：** 校验拒绝前job数/lease/历史不变；预览零I/O；start旧摘要拒绝；采集中取消不确认释放保持原锁；成功/失败/取消后历史只读且连续第二次任务可重入。仅真实安全终态可解锁，未新增清理动作。报告`task-2-report.md`含R1/R2具体裁决与消费者逐行结论；提交`feat: 让射频路径解析消费内部端口通路`，独立规格/质量通过才Task3。

## Task 3: 原器件抽屉内部通路编辑与草稿恢复

**Files:** 新建`gui/src/features/TopologyEditor/InternalPathFields.tsx`、`gui/src/features/TopologyEditor/internalPathHelpers.ts`、`gui/test/topologyInternalPaths.test.ts`、`api-service/tests/pc04a4c_browser_fixture.py`、`gui/test/pc04a4cInternalPaths.browser.js`、`gui/test/pc04a4c.vite.config.ts`；修改`TopologyEditor.tsx`、`topologyDraft.ts`、`routeCalibrationState.ts`及必要`PortDeclarationFields.tsx`引用提示。`CustomNodes.tsx/CustomEdges.tsx`保持4b几何，不为内部pair增加ReactFlow外边；仅必要声明状态文案可最小调整。

**Interfaces:** 消费`TopologyInternalPath`及4b `resolveNodePorts`的ports/effectiveDirections/source；产出`validateNodeInternalPaths(node: TopologyNode): void`、`validateDraftInternalPaths(draft: SwitchTopology, previous: SwitchTopology): void`及`InternalPathFields`组件。组件props固定`{node:TopologyNode, disabled:boolean, onChange:(paths:TopologyInternalPath[])=>void, onRestore:()=>void}`，只输出新列表；未开/取消保持原缺键，不重建params。`probePathDeclaration`仍产原connection_ids/switch_mappings，校验失败不制造新控制配置。

- [ ] **Step 1：先建立浏览器RED。** 先只添加fixture/config/脚本，按Task4隔离规范启动Task2真实API及未经本任务修改GUI；通过真实POST构造PA/pad/combiner/termination和普通+参考有效路径。打开PA原抽屉确认已有4a/4b控件后断言`内部通路`编辑区及`添加内部通路`按钮存在，缺控件为RED。保存DOM、截图、请求/GET、SHA/diff/退出码；选择器/启动失败不是缺功能RED，绝不后补截图冒称首次。
- [ ] **Step 2：纯函数RED。** 节点pair=IN→OUT时reverse不存在；ports移除IN但internal_paths仍引IN必须拒绝且原对象深相等；[]与缺键不同；BSE role优先；unknown仅提示。草稿端口改变要列出内部pair和所有模式显式路径引用，不能沿4b只过滤方向map后把pair静默删掉。测试示例：

```ts
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {validateNodeInternalPaths} from '../src/features/TopologyEditor/internalPathHelpers';
test('删除内部通路使用的端口会失败且不改输入', () => {
  const node = {id:'pa',type:'amplifier',label:'PA',position:{x:0,y:0},params:{
    ports:['OUT'],internal_paths:[{from_port:'IN',to_port:'OUT'}]}};
  const original = structuredClone(node);
  assert.throws(() => validateNodeInternalPaths(node), /pa|IN/);
  assert.deepEqual(node, original);
});
```

- [ ] **Step 3：实现声明表单。** 下拉仅显式ports，输入口与输出口依据内部方向规则过滤，unknown保留但说明未知。每pair可增/删；“声明无内部贯通”显式写[]；“恢复原内部声明”恢复打开时快照（含缺键），不是暗造in/out。PA单向、双端pad/线缆、任意N合路按表约束；负载仅显示终止说明，不给非空入口；switch_slot明确“此处不配置自动控制”，链接/文字引导原port_maps位置；虚拟参考面不能统称RF物理口。
- [ ] **Step 4：原子草稿应用。** `applyNodeEdit`先构造候选params合并，再验证node和draft；成功才setDraft。对不受影响的旧图不物化任何字段；编辑pair后若显式probe引用失效，错误列出引用，需要先重新声明路径，不自动级联。连线拖入/抽屉重接/模式变化共享同一草稿验证，不把“未组成完整路径的草稿”误作有效运行路径。按钮、回调以及Enter提交都守原锁，不能只disabled外观。
- [ ] **Step 5：服务器选择一致性。** `routeGraphMatchesSaved`当前全params比较已覆盖internal_paths，保留此权威比较；补normal/reference相同图差一pair的行为用例。旧选择失效，保存成功后重新读取服务器路线；不在前端重算digest/eligible。内部path仅抽屉/文字，不添加外部connections、损耗字段或虚构“已接通”绿标。
- [ ] **Step 6：GREEN与恢复矩阵。** 执行下表本任务部分和Task4命令中的GUI相关/production build，临时移除内部引用校验或把缺键物化[]时相关行为必须红，恢复GREEN。保存失败、取消、跨Lab、运行锁均从真实UI/API取证，不以toast代替GET。

| 生命周期 | 输入/动作 | 结果与恢复 |
|---|---|---|
| 未改/取消 | 打开缺字段旧PA，改pair但取消抽屉 | draft和服务端均无新键，旧标称/端口意图保留 |
| 已应用/再取消 | 应用pair，再改另一值取消 | 第一次应用仍在草稿，第二次不泄漏；保存GET/重载一致 |
| 清空/删除引用 | []或删pin，原探头声明仍引用 | 明确拒绝且列出引用；无静默删边/改switch_mappings |
| 保存pending | 真实保存期间操作pair/ports/模式/拖动 | 全部输入、按钮、回调与handle冻结；失败后草稿恢复 |
| 422/离线 | 错pair直PATCH、浏览器离线点击保存再恢复 | 422定位；未保存草稿保留，恢复本任务服务后重试成功 |
| 采集/未知取消 | running时打开抽屉/离线取消 | 内部/端口/外线均锁；未收到安全终态不解锁 |
| 终态后二次 | 同Lab再次编辑并开始第二次Mock采集 | 新请求重新选路；只新增两次预期作业，无重放/双启动 |
| 跨Lab/模式 | dirty切Lab、保存后A→B→A、正常↔calibration | 脏图保护、无串声明，隐藏器件仍可恢复，内部声明对所有模式一致 |

报告`task-3-report.md`含浏览器RED原件和GREEN；提交`feat: 在拓扑器件抽屉编辑内部通路`，主代理独立规格/质量通过才Task4。

## Task 4: 真实HTTP全矩阵、唯一最终全量与交付证据

**Files:** 完成Task3 fixture/browser脚本GREEN，新增`docs/validation/2026-10-27-pc04a4c-internal-rf-paths.md`，更新本计划与roadmap实际状态。生产修复仅处理本片可观察失败，由主代理确认文件归属并经增量独立复审；不抢做4d/4e或历史G8门修复。

**Interfaces:** 消费Task1～3报告、当前实现SHA/diff/环境及R1/R2裁决；产出正式验证摘要和`task-4-report.md`。唯一最终全后端责任人是本任务实施者；reviewer/主代理不得为审查身份重复跑同输入全量。历史4b `7663/17/1`只作历史记录，不能复用为4c结果。

### 隔离前置（Task3 RED与本Task GREEN各自新库）

fixture只参考4b构造方式，不导入执行4b fixture。**任何app导入之前**检查URL精确符合`sqlite:////tmp/pc04a4c-[A-Za-z0-9]+/browser.sqlite`、父目录存在且文件不存在、两个环境开关严格true；默认bootstrap成功后再断言全部category/Lab binding为mock。只生成专用甲乙Lab、独立暗室、文档网段`192.0.2.0/24`连接；manifest含DB路径、Lab/chamber/topology/category/connection IDs及全部Mock边界。显式新图用真实POST，旧CAICT用真实import，非法历史形态仅专用fixture显式标注构造，不复制用户库。

```bash
lsof -nP -iTCP:18096 -iTCP:5191 -sTCP:LISTEN
pc04a4c_browser_dir=$(mktemp -d /tmp/pc04a4c-XXXXXX)
cd api-service
env DATABASE_URL="sqlite:///$pc04a4c_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4c_browser_dir/logs" .venv/bin/python -m tests.pc04a4c_browser_fixture
env DATABASE_URL="sqlite:///$pc04a4c_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4c_browser_dir/logs" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18096
```

端口冲突换本任务专用端口并同步config/manifest，不杀用户服务。Vite配置继承base但`host=127.0.0.1, port=5191, strictPort=true`，`/api`、WebSocket及更具体OTA代理全指18096，不落回8000/8001；cwd gui运行`npm run dev -- --config test/pc04a4c.vite.config.ts`。使用当时可用browser技能支持的真实浏览器API，先完整读技能，不锁死不支持的通道；不route mock HTTP、不调用OTA硬件执行、不启CE服务。保存pending用实际DOM变化观察，离线只控制真实浏览器网络。

### 验收矩阵（每行原始请求、响应、GET、重载DOM/截图＋必要ORM证据）

| ID | 场景 | 可观察正反例 |
|---|---|---|
| C01 | PA/衰减器/两种线缆内部声明增删保存 | PA仅单向；线缆双向须两行；重载pair精确一致，无新增外部边/损耗 |
| C02 | 合路3口/分路4口、未选支路 | 只列pair可通；禁止IN1→IN2；显式probe只选对应connection_ids，端口数量不生pair |
| C03 | 负载、内部空列表、缺键、多端口 | 负载非空声明422、中转拒绝、通用路径可终止；[]不通；旧唯一链兼容按R1，缺字段多口不能全互通 |
| C04 | 不同有效方向/BSE/未知/虚拟参考面 | 内部from为output/to为input拒绝；unknown仅草稿；BSE role未变；空气不被标物理RF内部口 |
| C05 | 端口删改/方向改/内部pair删改引用 | 全模式列出相关pair/外边/探头；非法422不丢草稿；正确先改路径解除引用后可存 |
| C06 | POST default/PATCH部分nodes/模式数组/import replace错误、跨Lab | 原默认/行数/图/历史GET与ORM均不变；跨Lab409，非法Lab422 |
| C07 | 旧CAICT、新旧稀疏pin、opaque、改名/鼠标移位/4a标称 | 缺internal_paths不自动补；旧模板未转换，未宣称有效；旧无关保存digest及JSON按既有边界不变 |
| C08 | 公共paths/calibration-matrix/BFS与保存normal/reference链；稀疏外边＋明确internal_paths及R1缺字段两组 | 所有消费者排除禁止pair；从原保存JSON取pin，分别缺入pin/出pin/两者均无完整路径、matrix无其path_id、BFS损耗None且validate定位原边；补回保存pin后恢复正例。reference中间PA/接收线同验；参考从probe另起不误拒；损耗投影只原外部边 |
| C09 | 开关slot映射与合路/分路 | 原port_maps/switch_id/relay身份不变；缺/错映射拒绝；相同继电器冲突仍拒绝；合路器不能变自动开关 |
| C10 | individual/simultaneous/批preview/start | 合法候选可读但同CE非互斥分路仍拒绝批启动/正式集合；preview零HAL I/O；pair变更旧preview拒绝 |
| C11 | 普通和参考pair变更、旧单采集选择、采用记录 | 新digest变化，旧请求422；旧run/应用/history冻结逐字不变；资格不由声明提升 |
| C12 | 冻结DB-current及actual-target、无switch的新声明链 | 两分支均发现选中内部pair变化；无新字段历史仍可读；实际目标先验后测量，无CE/ASC重排或额外补偿 |
| C13 | UI打开/取消/应用/同值重申/[]/恢复 | 缺键、[]、有值三态可辨；取消不泄漏，原port/nominal意图不丢，恢复到原缺键不偷偷转换 |
| C14 | 保存pending/422/离线/重试/切Lab/切模式 | 消费Task3完整恢复矩阵，保存拒绝与重试均有GET；只恢复本任务进程 |
| C15 | running/未知取消/释放后第二次采集 | 所有内部端口和原编辑锁一致；两次真实202→Mock终态→可编辑，计数恰两次，无误解锁 |
| C16 | 内部pair两端unknown/明确方向两组、缺绑定与Mock | unknown组保存草稿成功但路径/采集422且无job；明确组可走原Mock采集但无正式量值、采用拒绝。另明确组缺绑定仍拒绝；旧标称与正式报告判词不变 |

- [x] **Step 1：独立新库GREEN。** 原Task3 RED原件已存在；Task4新库逐行执行C01～C16，不在共享工作树回退补拍历史RED。缺无法在纯Mock真实验证的硬件结果写未验证，不制造real样本；后端fixture中的real证据测试须注明仅证明拒绝/匹配逻辑。
- [x] **Step 2：相关后端与GUI。** Task1/2命令累计运行，加`test_pc04a4b_port_identity.py`、`test_pc04a4a_nominal_identity.py`、`test_pc06a1_batch_jobs.py`、`test_pc_04a_fixed_route_acquisition.py`覆盖；精确记录完整命令/实际数量。GUI命令：

```bash
cd gui
npx --yes tsx --test test/topologyInternalPaths.test.ts test/topologyPortContract.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

- [x] **Step 3：唯一最终全量。** 功能及fixture稳定后本任务实施者执行一次新库全后端；先记录HEAD、tracked diff、未跟踪测试输入、依赖清单及输入散列，结束复核未变。若发生后续功能改动，主代理明确要求其补跑对应验证/必要全量，不让reviewer再跑。命令：

```bash
cd api-service
pc04a4c_full_dir=$(mktemp -d /tmp/pc04a4c-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a4c_full_dir/full.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a4c_full_dir/logs" .venv/bin/python -m pytest tests -q
```

- [ ] **Step 4：证据与审查交付。** 记录真实退出码/统计/warnings/耗时/失败重跑历史；历史G8如仍失败须本次核实，不改历史、不叫全绿。`git diff --check`；正式摘要逐C行列实际证据、范围和未验证项。独立Task4规格/质量→累计分支审查→修复增量复审；满足新片当前输入验证再Ready PR/R1/R2。合并后才勾4c/启动4d，父项/B/HOLD保持。

**恢复/锁矩阵：** C13～C15不允许抽样省略；保留新库/日志/截图/SDD workspace/venv，不清理用户资料。只能按本次记录PID定点停止本次API/Vite，停止结果留证。报告`task-4-report.md`；提交`test: 完成内部射频通路综合验证`。

## 2. 计划预检任务接口表（派工前必须逐行核验）

| 任务对/自身 | 生产→消费接口/共享文件 | 核验结果与需主代理动作 |
|---|---|---|
| T1自身 | raw声明→shape/write验证→HTTP/ORM | 写入严格但草稿缺键/unknown可保存；运行不等于保存。R1白名单和端口依据已列，不制造迁移标记 |
| T2自身 | raw连接ID/pins→pure transition→normal/reference/DFS/BFS/actual-target | 通用链不能用已补默认pin的对象作证；R1与新声明同源，稀疏边无路径/损耗。历史投影不调用运行严验；R2已获主代理边界裁决 |
| T3自身 | 字段组件→候选draft→校验→PATCH | 缺键/[]有值三态、引用保护与锁一致；代码后补RED不接受 |
| T4自身 | Task报告→新库矩阵→当前输入全量→摘要 | 唯一全量责任清楚；4b统计不复用，纯文档收尾不能伪称新功能全量 |
| T1/T2 | topology_internal_paths三函数、switch_topology保存调用 | T1先独立验证声明；T2运行接入后保存`check_internal_paths=False`仅跳新运行规则，最终写门仍严验主动变化 |
| T1/T3 | TopologyInternalPath＋服务器422/GUI引用提示 | 键名/from-to方向完全一致；GUI不把外部方向规则照搬内部 |
| T1/T4 | HTTP原子性/四镜像及模板legacy入口 | 最终实际JSON再核，不根据开放Dict类型推断已支持全部语义 |
| T2/T3 | route_selection nodes params/route_digest、probePathDeclaration | 声明改变先保存重选；GUI不造digest，不把画布可达当正式集合资格 |
| T2/T4 | 解析/冻结/actual-target、批preview/start、采用/history | 必须覆盖无switch的新内部链和参考端；旧历史读取与当前匹配分开断言 |
| T3/T4 | fixture/browser/config与全部锁/恢复矩阵 | RED前置Task3；GREEN新库Task4，使用不同证据文件不覆盖原件 |

计划审查后主代理把R1/R2裁决、实际接口名与任务状态记入本计划独立SDD `progress.md`；此表不是“已实现/已验证”声明。设计所有4c要求由T1～T4覆盖；旧转换和全器件最终操作手册分别留在4d/4e，不承接本片遗漏验证。
