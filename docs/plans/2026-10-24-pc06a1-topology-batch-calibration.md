# PC-06A-1 拓扑内整套逐通路测量实施计划

> **执行流程：** 使用 subagent-driven-development 逐任务TDD、任务内审与整片审查。计划审查完成后才实施生产代码。

**Goal:** 在原可编辑拓扑内，从已保存 MIMO OTA 通路及用户明确选择的频点/极化生成清单，复用单条采集逐项测量，在物理换线或移动参考件前安全停发并等待人工，保留逐项真实覆盖与取消/中断事实。

**Architecture:** 整批协调器持有既有全局执行互斥和仪器租约，同一任务内逐项调用既有 `collect_fixed_route`；不循环调用各自抢互斥的 `fixed_route_jobs.start`。每项仍生成既有 `FixedRouteResult` / DiagnosticRun，以原有采用预览/确认链消费；父作业只编排、持久化清单和关联，不另造采集引擎或校准补偿。

**Tech Stack:** FastAPI/Pydantic、SQLAlchemy DiagnosticRun JSON envelope、asyncio、React/Mantine/React Query、既有拓扑画布。

**Spec:** `docs/design/2026-10-24-topology-calibration-integration.md` 第三片。PC04A2已由PR #531合并；基线`33a0a4f4`，实施分支`codex/pc-06a1-topology-batch-calibration`。当前唯一WIP是本片规划；PC04A2不重复开工。

## 全局边界

- WIP=1，仅 PC-06A-1；PC05 其余、PC07、B现场、PC09/10 HOLD不关闭。
- 原画布编辑、拖动、连线、保存行为保留；作业活动时冻结编辑/设备/模式/实验室，查看历史不替代活动身份。
- 首批仅整条损耗/增益，不宣称相位、极化校准、静区或计量认证；极化是所选探头身份，不生成额外不存在的 H/V 路径。
- 固定直连不调用任何开关写/读/复位；需换路/移动参考天线时默认人工暂停，不猜参考天线已对准。
- Mock只验证流程，`net_loss_db=None`、`cleanup_confirmed=None`、formal_eligible=False，采用仍拒绝；“全部模拟项走完”不显示“整套校准成功”。
- 不向旧单段 `calibrated_loss_db` 写入整条损耗；采用/冻结/补偿继续PC04A2同源，旧执行不漂移。
- `cleanup_unconfirmed`优先于取消/一般失败，任何安全停发未确认不能进入换线提示或继续测量；释放Remote不等于停发。
- 批child测量完成不等于可采用：只有所属批外层lease真实释放确认且父子最终事务成功提交，才可进入原采用核验。批活动、释放未知/失败、最终落盘失败或崩溃时，child均不可采用；旧单项语义不变。
- 不新增SCPI。自动切换只能调用已核验驱动操作；缺证据的通路明确不可自动切换，不能以任意拓扑开关节点或 capability.supported=True推定资格。

## 已核对的生产关系与缺口

| 生产入口 | 权威判据 | 消费者 | 本片可观察断言 |
|---|---|---|---|
| `calibration/route_calibration.py::list_route_selections` | 已保存图、完整路径、probe V/H、route digest、独立校准接线 | 批预览→批启动→逐项FixedRouteRequest→画布高亮 | 未保存、跨lab、重复/缺失通路拒绝；请求不允许伪造节点/实测值 |
| `fixed_route_jobs.resolve_configuration` | configuration_scope、CE绑定、FSVA真实类别/连接与HAL一致 | 入Remote前/每项前再次零I/O核验 | 绑定/拓扑在预览后漂移，不发射、不拿当前值补历史 |
| `collect_fixed_route` | 同次F64/FSVA实测、错误队列、专属tone、清理 | 子DiagnosticRun→application-preview→confirm→route freeze→本地ASC waveform | 不新增第二套功率测量；child可复用原确认链；Mock/停止未知拒绝采用 |
| `execution_exclusion_guard` | token持有者；单进程单事件循环契约 | TestCase runner、破坏性诊断、F64控制操作、单条/批作业 | 测量之间、等待人工、失败暂停都不让正式测试插入 |
| `instrument_test_lease` | 全局单飞、同task可嵌套、F64 Remote/release与monitor门 | HAL reload policy、全部仪器操作 | 外层整批持租约、同一驱动身份、monitor关闭，最终收尾后释放 |
| `EtslSwitchDriver.set_mapped_path/switch_path/get_path` | 保存port_maps + 对应relay_type + 已核验绑定/操作 + 本次位置回读 | 批项切换→确认后collect | 写返回True仅表示发送，绝不能直接变成接通；错误/缺失回读不发射 |
| `TopologyEditor/RouteCalibrationPanel` 与 `OperationalLab.beginWork` | 服务器作业身份与冻结route，不靠组件挂载 | 图高亮、锁、取消、进度、历史、采用 | 切页/网络失败不解锁；重载后恢复同批只读状态，不自动续跑 |

当前开关来源：`hal/rf_switch.py`类docstring列 Part #1801188 Rev A（2025-08）；`diagnostics/sequences/emcenter_switch_health.py`列原件 `Instrument_API_Doc/ETS-L EMCenter/EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf` 与SPDT/SP6T原文定位。`switch_orchestrator`只是声明解析，不是自动切换实现；`rf_switch_calibration_service`存在忽略写返回的调用，不能拿来当新作业成功判据，也不顺带重构它。

已完成第二轮手册核验，见核验依据。尚未发现可以仅凭一条历史记录直接授予“该物理通路已验证”的完整载体；不得凭一个前端checkbox把通路变成已验证。自动切换是本片必须实现的软件正例，不可把所有通路退人工后宣称该能力完成。

## 统一契约

新增 `api-service/app/schemas/route_batch.py`、`api-service/app/services/calibration/route_batch_plan.py`、`api-service/app/services/calibration/route_batch_jobs.py`、`api-service/app/api/route_batch.py`；现有文件只提取共享单项执行/持久化helper，不复制采集代码。沿用DiagnosticRun，不为本片新增数据库表/迁移。

API全部在 `/api/v1/lab-profiles/{lab_profile_id}`：

- `POST /route-calibration-batches/preview`：选择 topology_id、operating_mode=mimo_ota、去重chain_ids、明确频点、每项参考天线/位置/极化、该频率线缆损耗及来源、功率/样本数、安全声明；返回服务器生成的逐项快照、摘要digest和人工/自动步骤。频点按实际输入展开，不做插值/推整个频带。
- `POST /route-calibration-batches`（202）：提交同一选择和preview_digest及请求幂等UUID；服务器重算一致后冻结父记录再派任务；禁止客户端提供实测结果/confirmed状态。
- `GET /route-calibration-batches` 与 `GET /route-calibration-batches/{job_id}`：服务器持久化事实，不从当前图补历史。
- `POST /route-calibration-batches/{job_id}/continue`：只对同一活动job、当前等待item_id/transition_id，明确人工操作完成及本项参考位置；原子消费一次确认。失败暂停如继续后续项，明确“保留失败并跳过该项”，不悄悄重跑。
- `POST /route-calibration-batches/{job_id}/cancel`：只设置cancel，不把HTTP成功伪装成停发；由协调器停发/落盘至终态。

不新增批量采用API：结果列表可多选，但逐条调用已有 application-preview/confirm（独立幂等键及 expected_current_application_id），显示每条成功/冲突/不符合；不声称跨条原子采用，不因其一成功勾选全批。首批默认单项确认也可满足“仅明确选择的结果”。

父记录 `target_name=route_calibration_batch`，extra.route_calibration_batch包含版本、job_id/lab_id、预览digest、请求幂等键、冻结计划/绑定/路径/参考信息、顺序item_id、子run_id、当前索引、等待transition_id、cancel_requested、安全状态、逐项摘要与错误。每个状态切换及每项开始前/结束后提交；子记录仍 `target_name=fixed_route_power_acquisition`，完整v2 result可被PC04A2读取。

父子最终交接：child的states保存`batch_job_id`、`batch_item_id`和实际`lease_id`，每项只写自身`cleanup_confirmed`，外层lease仍活动时`f64_control_released`保持None。父保存真实lease释放结果及其lease_id、finalization_id、最终提交状态。退出外层lease后，以同一数据库事务更新父终态及全部已存在child的真实释放结果和同一finalization_id；只在实际outcome确认为True时写True，不把本项tone停止冒充外层释放。采用资格必须数据库核对父子归属/lease/finalization一致及父最终事务已提交，随后仍过原真实测量证据门。

最终写入窗口逐一封闭：逐项提交失败立即停止推进并做既有cleanup/lease退出；lease退出失败或unknown时，最终事务保存失败/未知释放事实，所有child不可采用；lease已经释放但最终事务失败时回滚全部父子最终更新，旧child仍缺释放证明且父仍未最终化；进程在退出lease前后任意位置崩溃且未最终提交时，重读为interrupted/unknown不可采用，不从当前HAL补证据。只有真实释放为True且最终事务成功，父/child才显示“批已结束且释放确认”；事务成功但真实释放False/unknown仍显示失败/未知，不能因提交成功升级。仅各自真实completed、所属批所有已启动tone收尾确认且满足原门的child可被明确选择采用；父failed/cancelled但正常收尾释放已确认时也不能把失败child升级，已经完成的合格child按实际覆盖显示。父cleanup_unconfirmed时全部child保持不可采用。

状态分离：父 `running/waiting_manual/paused_failure/completed/cancelled/failed/cleanup_unconfirmed/interrupted/incomplete`；项 `pending/measuring/waiting_manual/completed/simulated/failed/cancelled/interrupted`。父completed表示所有计划项流程结束，不表示正式资格；展示真实completed数量、simulated数量、失败/取消/待测数量。失败后未测项仍pending；用户整批取消时未测项cancelled且无采集run。父终态不能只读“当前项终态”推定。

## 核验依据与已定实施边界（2026-10-24）

### A. 可复核出处，及NotebookLM页码纠错

Notebook：`dc42a7e4-a170-40e3-b7aa-787137604ec5`（EMCenter模块化射频测试平台手册）；query conversation `71281842-0fc2-4bb7-98fd-bc93ccdb5f6d`；引用source `aece0dd7-240e-4030-a911-e87ef9428faf`。本轮实际调用NotebookLM，不是仅沿用旧注释。随后用仓内原件 `Instrument_API_Doc/ETS-L EMCenter/EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf` 的 `pdftotext -f 8 -l 12 -layout ... -` 逐页重核，原件页脚为准：

| 操作 | 原件页码/标题 | 原文短锚点与本片规则 |
|---|---|---|
| SPDT读 | p8 `All EMSwitch Model Commands` | `Response NO or NC`；`INT_RELAY_<R>?`，R=A/B/C/D |
| SPDT写 | p9 同节 | `INT_RELAY_<R>_[NC/NO]`；写值只认NC/NO，不发送应用层0/1 |
| SP6T读写 | p12 `Relay SP6T Card Commands` | 写`<N> = Positions (1-6)`；读0..6；`If ‘0’ is returned, no coil is energized`，全部输出开路，不是选通路径 |
| 互锁 | p11 `Relay SP6T Card Commands` | `0: No interlock` / `1: Interlock active (supply relay off)`；缺失/ERROR/空串为unknown，不当0 |
| 继电器错误 | p83 `EMSwitch 7001-0xx Errors` | 201/202分别为切至NC/NO错误；不据此虚构通用SYST:ERR?查询方式 |

NotebookLM把SPDT写归p8、SP6T读写归p11，这两处与原件分页不符，已按原件纠正；实现注释必须用p9/p12，不照抄工具答案。手册没有规定NC→0/NO→1，也未证明状态查询检测的是物理触点还是控制逻辑；因此“本次位置回读匹配”只证明设备报告的位置匹配，不单独证明端到端RF通路已现场验证。

### B. 现有HAL复用与严格归一化

`RfSwitchDriver.set_mapped_path(name)`消费 `_mappings=connection_params.port_maps`，取 `switch_id`（兼容relay）、`output_port`（兼容position）、input_port；最终调用既有 `switch_path` 和 `build_emcenter_switch_command`。本片不接受其中缺失output默认0的宽松路径：先验证映射完整、类型明确、值合法，再传给同一既有拼装函数。

`EtslSwitchDriver.switch_path`当前只把_send_command非None当True；raw/vxi11写实现可能只返回本地`OK`，不是仪器确认。所有布尔必须消费，后面仍查询同一relay本次原始状态。`get_path`当前NC/NO用子串判断且把NC→0/NO→1，可能把错误文本误归类；本片最小收窄为精确raw域解析，不能直接信旧int值。

局部增加 `read_mapped_path_receipt(path_name)`：使用与现有get_path相同命令与transport，返回raw、relay_type、canonical位置和error，原get_path可委托精确parser保持旧int契约；不增加新命令、不改其它校准服务。SPDT canonical保留字符串NC/NO，兼容旧int契约的0/1只在旧接口边界；SP6T canonical整数1..6，读0记录all_open但不匹配任何测量目标。严格拒绝`ERROR ... NC`、空/None、数值越界、spdt配置数值输出、sp6t配置NC/NO；样本TDD逐个覆盖。

最小新增/修改文件：`hal/rf_switch.py`仅抽取精确回读receipt/helper，`services/calibration/route_batch_switch.py`编排本次写读并存证；既有mock/real复用同一builder。所有回读事件保存 command/raw/error/host_time/simulated、当前job/item/attempt和驱动身份，不仅存True。

### C. 历史健康诊断能证明什么、缺什么

`emcenter_switch_health.run`以只读_query保存逐步label/raw、chassis_idn、VERSION_SW、slots[*].idn及relay值、interlock/verdict。外层diagnostic_sequence把完整SequenceEvidence写进DiagnosticRun（包括lab_profile_id/run_at），不是只留截断摘要；可作为“当时该机箱/卡/继电器应答”的原始支持材料。

但该序列不写继电器，不逐条port_maps选通；最终extra没有冻结connection/endpoint/driver/port_maps摘要/route_digest。DiagnosticContext.record_run也不会自动把全部ctx.instrument_bindings存入extra。故：历史SUCCESS + 当前port_maps不能拼成“同一绑定该路径已验证”；同一继电器一次读到合法位置也不能证明其它位置、其它探头路由。既有2.5.1精确互锁ERROR只等于unknown，不能按SUCCESS升级。

已定软件auto资格（不建新的证书系统）：保存图的显式路径和对应port_maps映射快照、绑定/连接/驱动/机箱/卡身份；引用现有DiagnosticRun ID及确实匹配的raw项；并保存操作员对该映射实际接线核对的说明/时间/身份（这是人工接线声明，不是SCPI验证）。当前作业内再做逐映射写→严格回读，记录同一job/item交换。历史证据身份不充分时不能从当前绑定倒填：改为本次开始时用既有已核验只读查询生成完整身份快照，并由本作业后续写读形成完整软件记录；现场RF连通/插损验证仍保持PC06B未验收。

“已验证自动切换”软件门必须实现并通过真实HAL类、仅替换外部transport的正例；真实设备是否允许开启，依赖当前冻结身份、明确保存映射、操作员接线确认及本次严格回读匹配；未知身份或互锁不得自动放行，不要求凭空历史verified布尔。对真实身份/互锁/映射证据不齐的单项明确阻止auto，并显示原因；有资格项仍可auto，不能全部强制人工后把auto项标完成。哪些物理RF路径完成现场验证单独列出，未拿到就不标已现场验收。

### D. 保存拓扑与分叉：最小显式路径选择方案

核对现状：SwitchTopology保存结构检查只验证节点/连线/模式引用与端口，不禁止分叉；TopologyService.resolve_paths本来DFS返回所有候选路径。PC04A2 `list_route_selections`却要求每个中间节点整体outdegree=1（未区分器件不同物理端口），且全局拒同CE口多个通路；因此共享switch_slot即使是不同输入/输出配对也会被拒。CAICT v4模板MIMO部分是固定直连（CE→PA→水平环），不能拿TRP/被动切换模板当本片MIMO实物已验证；模板`get_switch_command_for_channel/get_emcenter_calibration_sequence`含旧占位样式，绝不复用为命令来源。

最小改变不是改全仓DFS/执行器，而是为需要选择的保存图增加显式有序路径声明，并让校准完整路径的生产/采用/冻结共用该解析：

1. 在探头节点现有`params`保存可选`rf_path_selection`：`{connection_ids:[按源到探头顺序], switch_mappings:[{node_id,path_name}]}`。该params已由原保存API持久化，不新增独立拓扑/表/地址；UI在原侧栏通过已保存连接候选选择，不让操作员写JSON/SCPI。无分叉旧图不要求新增字段。
2. 新增零I/O纯解释模块`api-service/app/services/declared_rf_routes.py`，生产函数`resolve_saved_rf_path(nodes,active_connections,terminal_connection_id)`从保存节点的rf_path_selection取有序连接ID，返回严格正常路径节点/边。仅校验当前模式有效边、连续、无环、唯一CE源和探头末端、probe/pol、完整端口及开关明确配对；若同一terminal多候选且无保存声明，不默认第一条。`route_calibration.py::resolve_explicit_route_selection(db,lab_id,topology_id,mode,terminal_connection_id,connection_ids)`负责数据库lab/topology范围、与保存声明一致、校准参考段、真实CE口、digest等封套，复用该纯解释，不导入正常执行orchestrator，避免循环依赖。
3. 只有switch_slot明确配对的分叉可由声明解释；非开关中间器件分叉仍拒绝，不把PA/分配器/未知节点推定为可切换。switch_mappings路径名必须在已绑定仪器port_maps中唯一，node对应同一类别/模块、输入输出端口匹配；不能根据P2/P4标签猜NC/NO或relay字母。
4. `list_route_selections`保留无声明旧图严格模式，有声明的terminal只调用同一显式helper，批清单从已保存声明获取；多条校准项可共用CE物理输出但仅在本批串行且显式互斥开关映射下，不能因此允许正式MIMO同时复用一个物理输出。
5. 子FixedRouteRequest不新增`connection_ids`字段；用保存声明重读，冻结原有request+route_digest。resolve_configuration按同一resolver重新核对route_digest，防预览后改声明。RouteSelection快照/digest包含实际有序连线/端口与switch映射引用，显示字段不参与身份，旧历史不能回填新声明。
6. 所有消费者统一换源而非绕过：`switch_orchestrator._build_probe_binding`在存在保存显式路径时复用`declared_rf_routes.resolve_saved_rf_path`，不再对整个共享switch节点使用入出度=1代替端口配对；旧无声明唯一路线仍严格解析。`rf_chain_resolver.resolve_rf_chains`继续经该orchestrator消费同一声明，集合层保留正式重复CE拒绝；`route_calibration_freeze.resolve_effective_route_compensation`及`frozen_route_identity_error`由此拿到相同保存路线。最终MEASURE中独立调用的`orchestrate_switch_topology`也由同一只读解释生成实际target，保留`frozen_route_identity_error(...,resolved_topology=topology_result)`独立比较，不拿冻结对象直接冒充实际target。`fixed_route_jobs.resolve_configuration`、`evaluate_route_application`、GUI routeGraphMatchesSaved/highlight对应同一完整路径。全链只改变声明判据来源，不给正式setup/measure/analysis/channel-engine新增开关动作，不取消原补偿/实际target门。
7. 正式冻结对同CE输出重复使用、当前mode无法确定可同时执行路线明确不采用/unsupported，strict硬件前拒绝；不拿批作业的串行能力默默扩张正式MIMO硬件能力。若现有目标拓扑只有端口独立共享节点，则验证每条CE端口唯一即可继续PC04A2既有实际应用。

Task1对应新增RED：同switch节点两条独立输入输出路线显式选中可生成2项；无声明/交叉错配/伪造连接/非switch分叉/环路拒绝；两条指向同一terminal未明确选择拒绝；声明变化改digest。Task4/5追加：显式完整路径child可走原application-preview/confirm，执行冻结准确选择同route_digest；旧执行不漂移；同CE复用仅批串行允许而正式strict拒绝。先把这些关系测全再继续批编排。

## Task 1：清单与可控通路证据边界

文件：新增`api-service/app/schemas/route_batch.py`、`api-service/app/services/calibration/route_batch_plan.py`及纯解释`api-service/app/services/declared_rf_routes.py`；修改`api-service/app/services/calibration/route_calibration.py`实现完整封套及采用路径重核、`api-service/app/services/mimo_ota/switch_orchestrator.py`将`_build_probe_binding`换源为保存显式路径、`api-service/app/services/calibration/rf_chain_resolver.py`落实正式集合重复CE拒绝、`api-service/app/services/mimo_ota/route_calibration_freeze.py`保持当前路线/冻结核对同源；测试新增`api-service/tests/test_pc06a1_batch_plan.py`。`executors/measure.py`现有独立actual-target比较不删除、不绕过，测试直接覆盖其传入resolved_topology的生产核对函数，不新增正式切换。

接口：`schemas/route_batch.py`定义`BatchPlanRequest`、`BatchPlan`；生产函数固定为`route_batch_plan.py::build_batch_plan(db: Session, lab_id: UUID, request: BatchPlanRequest, hal) -> BatchPlan`。它零硬件I/O，供Task2启动重核、Task4 preview/start共用；Task3消费其冻结switch_steps，不再独立解析另一套映射。`route_calibration.py::resolve_explicit_route_selection`只接受已保存连接ID及严格校验后的路径声明，旧无声明唯一链行为保持。批内复用CE时逐条调用显式helper，不把全局`list_route_selections`的CE唯一门删除；单条配置重核与采用重核也针对同一保存显式路径调用helper。正式冻结仍调用全局唯一集合检查，不以批任务的串行声明绕过。

- [ ] RED：2通路(V/H实际各一条)×2频点=4项，顺序稳定；重复chain/频点、NaN、缺参考来源、跨实验室、calibration模式、摘要漂移拒绝；固定直连计划无开关步骤。
- [ ] RED：真实保存图CE1→switch.in1/out1→probeV与CE2→同switch.in2/out2→probeH，显式路线经过orchestrate_switch_topology→resolve_rf_chains→resolve_effective_route_compensation/冻结→独立实际orchestrator→frozen_route_identity_error(resolved_topology=...)，两条已确认整条校准保持准确映射并可继续本地ASC一次应用。换端口/错配配对、非switch分叉、重复CE、实际target遗漏/替换任一probe均拒绝；不能只测新helper绿而旧生产链仍报唯一源端错误。
- [ ] 实跑上述测试，记录缺功能红灯；实现`build_batch_plan(db,lab_id,request,hal)`返回不可变快照、逐项请求和转换步骤，频率线缆资料按item绑定。
- [ ] 自动切换依据采用已核验的ETS手册；按核验依据定义保存路径→port_maps→原始诊断→本次写读的证据关系。真实现场材料缺失不阻碍实现软件正反门，但该目标实物通路不得冒称已验收。
- [ ] GREEN：按前述“显式路径选择”实现局部严格枚举，不全局放宽正常测试解析器，也不按当前relay位置猜通路。提交并审核此可独立交付的预览契约。

定点命令（测试文件由本任务创建后，先RED再GREEN）：`cd api-service && .venv/bin/python -m pytest tests/test_pc06a1_batch_plan.py -q -o log_cli=false`。

## Task 2：持久化整批生命周期与跨项独占

文件：新增`api-service/app/services/calibration/route_batch_jobs.py`；修改`fixed_route_jobs.py`提取共享子记录构建/完成保存helper及父归属读取、`api-service/app/api/fixed_route_acquisition.py`全部record调用传入批归属上下文、`route_calibration.py`预览/确认同样核对父归属最终化、`main.py`注册批shutdown；测试`test_pc06a1_batch_jobs.py`，回归PC04A单项API。

接口：`route_batch_jobs.batch_child_context(db,row)`返回由父记录及本批运行注册表推导的父活动/最终化/lease关联事实；`fixed_route_jobs.record(row, *, batch_context=None)`在有batch_job_id时消费该上下文，没有上下文则保守unknown，不假注册child进单项_running。原无batch关联记录继续用原单项判据。预览/确认通过同一上下文检查已提交的父子finalization，不能仅看child.states的True。所有既有record调用点（单条列表/详情/取消、采用预览、确认重读）均显式追全。

- [ ] RED：真实临时DB建立父+子记录；两项间插入TestCase/单条采集/unsafe诊断均409；等待人工仍独占；连续两批终态后能重入；父/子落盘失败不得启动后续项；已完成child详情能走原preview。
- [ ] 实跑RED；最小实现：启动先现有case检查+try_acquire token；只创建一个task，外层instrument_test_lease(control_f64=True,control_uxm=False,enable_monitoring=False,restore_f64_alignment=False)，逐项直接调用既有collect。批task持有token直至终态落盘尝试与cleanup，finally只释放自己的token。
- [ ] 每项重新检查冻结身份与当前绑定，不重建历史；本项开始先提交measuring+child，收尾后提交child与父进度，但child仍标“所属批活动/外层释放未确认、不可采用”。本项cleanup与整批lease退出各自记录，不能写伪releaseTrue。最终按统一契约在退出真实lease后同一事务提交父终态及所有child释放来源；任意提交失败不推进后续项。
- [ ] RED→GREEN：活动child从原history读取不误判独立interrupted；首child实测完成、后续人工等待时，预览/确认仍拒绝；本批真实外层释放成功并父子最终事务提交后，相同child才可通过原真实测量证据门。分别注入tone停止失败、lease释放失败、单项落盘失败、释放后最终事务失败、最终提交前崩溃，均无child假采用；重复读取不补真。旧单项释放/采用行为不变。
- [ ] 重启：活动父/项读取为interrupted、安全unknown；不派任务、不发SCPI、不恢复continue。正常shutdown先cancel并await安全收尾，再HAL关闭。历史中断不等于已停发，界面要求现场核验。
- [ ] GREEN及提交。沿用单API worker部署，不引入分布式锁；多worker需求明确不在本片。

定点命令（测试文件由本任务创建后，先RED再GREEN）：`cd api-service && .venv/bin/python -m pytest tests/test_pc06a1_batch_jobs.py -q -o log_cli=false`。

## Task 3：逐项切换、人工暂停、失败/取消安全

文件：`api-service/app/services/calibration/route_batch_jobs.py`；新增`api-service/app/services/calibration/route_batch_switch.py`封装资格核对与既有HAL调用；修改`api-service/app/hal/rf_switch.py`增加严格receipt；`fixed_route_acquisition.py`不复制/替换测量。测试新增`api-service/tests/test_pc06a1_batch_safety.py`。软件auto正例为本Task必交付，不以现场条件不足取消实现。

接口：`route_batch_switch.py::apply_batch_switch_steps(hal, frozen_steps, receipt_sink)`消费Task1冻结映射，产出逐条严格receipt；任何False/unknown/错误位置均返回阻止测量的失败，不由调用者忽略。HAL `read_mapped_path_receipt(path_name)`返回raw、relay_type、canonical位置与error；receipt_sink只追加同job/item记录，不写校准采用指针。

- [ ] RED：固定直连所有rfSwitch调用次数0；auto只在映射资格完整时调用set_mapped_path并消费bool及read_mapped_path_receipt；写False/旧get_path的-1对应未知raw/错误位置/超时/身份变更→不调用collect，保存失败并暂停；SPDT/ SP6T按手册域比较，不混同0/NC。
- [ ] RED：首项参考摆放也需确认；同一参考位置且无换线不无故暂停；移动参考件前前项cleanup必须True。停止未知时continue永久拒绝且提示可能发射；Mock分支仅“模拟人工步骤”不声明实物已安全。
- [ ] 最小实现：先完成既有tone停止/移除，再产生等待transition；人工明确确认消费后仅下一item运行。不调用reset_paths、恢复初始路径或全局F64停止来冒充安全收尾。自动切换在无本作业tone活动的边界进行。
- [ ] RED→GREEN：cancel在待启动、切换中、测量中、人工等待、失败暂停均不再启下一项；重复cancel/continue不重发硬件；任务取消期间用await_completion_despite_cancellation等待既有cleanup；cleanup失败覆盖cancel并清空可采用值。失败项不会因continue自动重测；重测需新作业。
- [ ] GREEN及提交。手册查证未完成的真实自动路径保持不开放，不用Mock绿替代资格。

定点命令（测试文件由本任务创建后，先RED再GREEN）：`cd api-service && .venv/bin/python -m pytest tests/test_pc06a1_batch_safety.py -q -o log_cli=false`。

## Task 4：API与历史/确认消费

文件：新增`api/route_batch.py`；修改`main.py`、`api/openapi.yaml`、`gui/src/types/api.ts`、`gui/src/api/labProfileService.ts`；复核Task2已修改的`api/fixed_route_acquisition.py`、`route_calibration.py`父关联上下文消费，不重造第二套判据；测试`test_pc06a1_batch_api.py`。

- [ ] RED：真实FastAPI+临时DB，preview/start/GET/continue/cancel全链；跨lab/job伪造404；无效输入422；已有占用409；pending POST响应丢失重试同幂等key返回同job不新增tone；过期transition拒绝。
- [ ] 最小实现全部上述接口，幂等身份限定lab+请求内容；原固定采集列表/详情/取消可识别child所属批且不假作独立任务，child取消导向所属批取消或明确409提示批入口，不报告已停止；application-preview/confirm在真实来源/适用/tone cleanup之外核对所属批真实外层lease释放及已提交finalization，Mock仍拒绝。跨lab父关联、孤儿child、lease_id或finalization不符、父活动/未最终化均拒绝。
- [ ] RED→GREEN：真实API临时DB保存首child完成且父waiting_manual，原child history显示所属批活动/待释放而非interrupted；直接POST确认拒绝。真实lease退出+最终事务提交后重新预览/确认才可成功，落盘失败或崩溃后GET/preview/confirm一致显示unknown不可采用，父状态不显示“释放已确认”。
- [ ] GREEN：模型/活OpenAPI/手写OpenAPI/GUI四镜像对齐；原PC04应用、冻结、ASC一次补偿回归保持。

定点命令（测试文件由本任务创建后，先RED再GREEN）：`cd api-service && .venv/bin/python -m pytest tests/test_pc06a1_batch_api.py -q -o log_cli=false`。

## Task 5：同图多项工作台

文件：`TopologyEditor/RouteCalibrationPanel.tsx`、`routeCalibrationState.ts`，必要时新增同目录`RouteBatchPanel.tsx`作为原侧栏内子组件（不是新画布/新页面）；现有OperationalLab机制保持；GUI行为测试新增`gui/test/pc06a1Batch.test.ts`，运行`cd gui && npx --yes tsx --test test/pc06a1Batch.test.ts`先RED再GREEN；构建运行`cd gui && npm run build`。

- [ ] RED：真实保存路径多选、频点/参考位置输入→预览完整清单；dirty阻止preview/start；当前项正常路径及参考段同图高亮；清单计数与结果逐项对应。
- [ ] 实现预览→明确开始→逐项进度/等待人工/失败暂停→继续/取消→历史；活动身份存于服务器，前端beginWork跨卸载保留锁。网络失败、空历史、开始回执未知不提前解锁；只读历史不覆盖活动job。
- [ ] RED→GREEN：人工continue必须针对当前transition；真实cleanup未知不显示可换线提示；模拟明确黄色且正式采用不可用；不把一项完成显示整套成功。首child测量完成但父活动/等待人工时，父面板与单项历史均显示所属批、tone状态、外层释放未确认、不可采用；仅所属批终止且真实lease释放及父子最终提交确认后，选择合格child才显示原采用预览/期限确认。释放/落盘未知不显示已释放，失败冲突保留其他结果。
- [ ] 生产构建通过，原图编辑/保存、PC04单项采集与确认交互回归。

## Task 6：真实API临时DB全Mock浏览器、最终回归与收口

文件：新增`gui/test/pc06a1Batch.browser.js`，复用`pc04a2RouteLifecycle.browser.js`真实API/全Mock模式检查与生命周期验证形态；测试种子只进入临时数据库，不写用户实验室。

- [ ] 起隔离后端+临时SQLite+全HAL Mock，检查HAL确为mock后启动浏览器。使用真实API保存含2条通路与校准接线的图；刷新后按2频点形成4项并截图。
- [ ] 浏览器验证：开始、首项人工摆位、逐项进度、跨通路人工暂停、continue、取消、已完成/未完成覆盖、离页返回锁、失败读取保持锁；API GET与DB持久化交叉核对。不得拦截响应伪造成功/结果。
- [ ] 错误切换、cleanup未确认、取消竞态由真实服务API+仅替换外部transport的后端测试覆盖；若浏览器需要故障注入，仅隔离测试fixture注入驱动行为，不增加生产“模拟成功/故障”端点。浏览器必须包含Mock自动切换流程正例及拒绝错误回读反例，仍明确模拟不是真实资格；目标实物现场证据缺失显示不可用原因，不虚报已真机自动切换。
- [ ] 真实重启后读同父job为interrupted、无新增child/动作；取消后刷新无自动续跑；单条/正式测试占用竞争与任务间独占后端证据归档。
- [ ] 补充后端真实生产链正例：共享switch独立两CE端口经正常orchestrator、freeze及独立actual-target核对消费正确校准；无正式开关写。父活动child拒绝采用、真实lease退出且最终事务提交才开放；全部最终写入失败窗口仍unknown。全Mock浏览器核对父子待释放提示与采用禁用，不伪造真实采用成功。
- [ ] 执行下列已核实运行入口；PC06文件由本计划指定任务先创建，再运行对应命令，缺文件/导入失败不算行为RED。相关回归的既有文件均已核对存在。记录HEAD、未提交测试输入、退出码、统计行；既有过期fixture单独披露，不改有效期规则。

```bash
# 在仓库根目录逐条执行
cd api-service
.venv/bin/python -m pytest tests/test_pc06a1_batch_plan.py tests/test_pc06a1_batch_jobs.py tests/test_pc06a1_batch_safety.py tests/test_pc06a1_batch_api.py -q -o log_cli=false
.venv/bin/python -m pytest tests/test_pc_04a_fixed_route_acquisition.py tests/test_pc_04a_fixed_route_api.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_gui_contract.py -q -o log_cli=false
.venv/bin/python -m pytest -q -o log_cli=false
cd ../gui
npx --yes tsx --test test/pc06a1Batch.test.ts
npx --yes tsx --test test/pc04a2RouteCalibration.test.ts
npm run build
```

GUI新增`gui/test/pc06a1Batch.test.ts`由Task5创建；package.json没有test脚本，不写`npm test`。浏览器文件由Task6创建，使用实际浏览器工具载入导出函数执行，遵守browser skill，不把该函数文件直接当node CLI运行。
- [ ] 核心变异最少覆盖：去掉外层跨项互斥→竞争测试红；忽略get_path错误→禁止发射测试红；cleanup未知放行continue→人工安全测试红；重启自动续跑→零动作断言红；Mock采用放行→原资格链红。不为更多测试设计扩大本片。
- [ ] 按仓库流程内审、Ready PR、R1处理本片可执行意见、R2无P1收口；有P1续审最新HEAD。只有主代理在完成证据后更新roadmap当前片状态及台账；不整项关闭PC05/06或现场B。

## 覆盖自检

第三片要求均落到任务：多通路/频点/极化Task1；控制/停发人工Task3；跨项互斥/持久化/重启Task2；真实接口与历史Task4；原图交互/覆盖/确认Task5；软件与现场边界Task6。当前仅形成实施计划与路线图状态同步；所有Task仍未实施，不引用PC04测试结果冒充本片验证。

## 单进程、人工等待与重启裁定

沿现有单API进程部署，不新增分布式锁。人工等待、失败暂停和跨项间隙由同一批task持有既有互斥与外层租约；本作业tone必须已经确认停止，Remote释放不冒充停发。服务重启不自动重发，历史活动作业显示interrupted、安全unknown；不宣称跨重启硬件隔离。仅F64/BS存在专门Remote生命周期，不能据此声称FSVA/rfSwitch已确认归还Local。
