# PC04A4e 器件契约综合验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL：使用 `subagent-driven-development` 或 `executing-plans` 按 Task 1～3 串行执行。用户已授权连续推进，不再询问执行方式；独立审查由主代理安排，实施者不再派子代理。本文件仅为计划，复选框不是执行结果。

**Goal:** 在4a～4d已合并的软件上，交付全器件编辑、显式转换、保存恢复及校准消费者的综合软件验收和可直接操作的用户指南，不把分片证据拼成未经执行的整体验收。

**Architecture:** 复用原编辑器、真实HTTP与隔离SQLite，全Mock浏览器串行走完整生命周期；后端在原生产采集/选择/采用/冻结入口核对声明与正式消费者。默认只补验收脚本和文档；仅真实可观察产品故障才进行最小TDD修复，不为验收增加业务接口、资格、硬件能力或通用框架。

**Tech Stack:** React/TypeScript/Mantine、FastAPI/Pydantic、SQLAlchemy、pytest/tsx、真实浏览器；无新运行依赖、表、SCPI或驱动。

**Spec:** [已批准设计](../design/2026-10-26-topology-device-port-contract.md)、[正式队列](../roadmap-first-call.md)。分支 `codex/pc04a4e-device-contract-acceptance`，基线 `780a4b460d8612b5e39db456ee4a0fb4e73fbc3f`。PR #542 于 `2026-10-27T04:29:08Z` 合并；[R2回执](https://github.com/swang430/Meta-3D/pull/542#issuecomment-6433718993)覆盖 `89f94ac736bcfb25ecf0fffa0a0bab6b5383af0c`，无发现。4d 的7945/17/1仅为旧输入结果，不是4e通过。

## Global Constraints

- 旧记录不批量改写；缺角色/参数显示旧版未声明。用户显式转换前提供变更预览；不更改历史执行或已有证书。正常旧图的无关改名/位置保存不得被新契约误伤。
- params.ports 继续是端口 ID 清单；端口不是左右接点数量。名称不隐式决定方向。角色独立为 input/output/bidirectional/unknown；unknown 不冒充双向能力。
- 复用基站 port_roles 的 dl/ul 权威关系，不用通用角色覆盖它；新角色与其冲突必须拒绝，而非选一端。
- 图边为外部接线，器件内部连通关系独立声明。多端口器件不得默认全互通。开关继续复用现有 port_maps/switch_id/继电器身份，不新增第二套自动切换配置。
- 校准来源、原始采集和历史执行冻结保持只读；整链实测只在原采用入口生效一次。禁止额外叠加节点增益；标称、角色、内部pair和操作员同线缆声明均不授硬件/正式测量资格。
- 所有Python验证在app导入前指定全新临时SQLite、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`。默认bootstrap后显式设置并核查全部category和Lab binding的Mock；并非bootstrap自动全Mock。不碰默认DB、用户服务或用户数据，保留全部失败与成功证据、DB、venv、scratch。
- 浏览器使用真实后端，不启用`mockServer.ts`、不拦截伪造API响应、不通过React内部处理器冒充鼠标操作。网络故障用浏览器离线/限速；编程HTTP与DOM证据分栏。
- 软件Mock/脚本化transport不能证明实物端口、RF导通、停发、计量或现场B；B/HOLD不解除。无新仪器语义，NotebookLM不适用；出现厂商能力问题停止推断、查手册，不能据模板补能力。
- 不改历史模板、执行/证书/报告、既有验证摘要中的当时结论。新的补验只写本片证据。所有示例量值标“隔离验收输入”，未知不补0。
- Task3为唯一最终全后端责任位：本片若只有验收脚本/局部测试与文档，不为身份或push重复全后端；若共享后端生产、契约、冻结、安全生命周期、共享fixture/依赖变化，则稳定输入后必须跑一次最终全量。此后相关输入再变由同一责任位重新冻结复验，保留旧结果。

## 0. 已核对事实、边界与文件职责

本计划已读4a～4d正式摘要；仅作既有证据索引，不将下列未验项假关闭：

| 前片边界 | 本片处置 |
|---|---|
| 4a有效参考PA元数据保形未覆盖真正选中参考段的身份/冻结（V1） | Task1新增显式非空参考路径正例，先证明PA边属于selection，再走原采用/冻结；成功仅形成新的软件证据，失败定位，不修改4a历史 |
| 4a首轮三项异常后续未再现但根因未知 | 保留披露；若本片复现保存原始trace，禁止以再次绿色声称已修复 |
| ASC条件分支/CE服务未执行、真实硬件未验 | 不增开CE服务、不伪造ASC加载；验证到冻结/补偿消费者，仍明确未验ASC与硬件 |
| 4c C07真实鼠标未验 | Task2实际鼠标拖动→保存→重载取新证据；不回填C07 |
| 4d R1历史参考receive_cable缺声明组合未做新版DOM | Task2加入该组合的scope/compare与实际采集拒绝分界；不以盘点200称可采集 |
| PostgreSQL CAS未实跑 | 本片仍SQLite，明确非PG事务验收，不为4e部署新数据库 |

### 0.1 生产关系全集（默认只读，故障才动生产）

| 生产入口→权威判据 | 正式消费者 | 本片可观察断言 |
|---|---|---|
| `api-service/app/api/switch_topology.py`：create/update/import、`_validate_structure`及最终待存JSON | GET/list；`schemas/switch_topology.py`；`topology_nominal.py`/`topology_ports.py`/`topology_internal_paths.py`/`topology_loss_ownership.py` | POST/PATCH/import最终图一致；拒绝不改默认位/行；稀疏原JSON由SQL及preview.before_present证明，GET不是原JSON证明 |
| `TopologyEditor.tsx`→`NominalPropertyFields.tsx`/`PortDeclarationFields.tsx`/`InternalPathFields.tsx`→`topologyDraft.ts` | `gui/src/api/switchTopologyService.ts`→上述HTTP保存 | 数值编辑意图与metadata分离；取消不泄漏；端口引用跨模式检查；实际handle与保存方向一致 |
| `LegacyConversionPanel.tsx`/`legacyConversionState.ts`→`conversion-preview`→原PATCH的conversion字段 | `schemas/topology_conversion.py`、`services/topology_conversion.py`、`_commit_conversion` | 预览无写入/无HAL；同一digest候选原子保存；过期409不覆盖；取消/换图/换Lab废弃旧会话 |
| `services/topology_loss.py`、`services/topology_service.py` | path、calibration-matrix；`services/mimo_ota/switch_orchestrator.py`与`calibration/rf_chain_resolver.py` | 通用按所选owner去重；正式binding仍末边语义；0优先、unknown传播，不额外加节点标称 |
| `services/calibration/configuration_scope.py`→Lab scope/compare | 当前盘点与GUI scope、RFChain显示 | owner只变scope、不变物理身份；旧缺参考声明盘点可读不授采集资格；unknown显示未知、不崩不补0 |
| `api/route_calibration.py`→`services/calibration/route_calibration.py` | `api/fixed_route_acquisition.py`、`api/route_batch.py`及原batch plan/jobs | 同一服务器选择与route_digest；未知/不完整路径失败；Mock单路/批次不可正式采用；终态前不解编辑锁 |
| 原application→`services/mimo_ota/route_calibration_freeze.py` | `resolve_effective_route_compensation`、`freeze_execution_route_compensation`、`read_execution_route_compensation`及原补偿测试 | 新执行消费confirmed一次；metadata/归属不篡改历史；真实pin/pair/mapping变化走失配门；不能从普通盘点借资格 |
| live schema→`api/openapi.yaml`→`gui/src/types/api.generated.ts`及手写服务类型 | 实际HTTP序列化与编辑器 | nullable/枚举保持一致；仅发生契约修复才生成类型，不手改生成文件 |

执行前重跑`git grep -n -E 'pa_gain_db|port_directions|internal_paths|loss_owner_connection_id|confirmed_route' -- api-service/app gui/src`，新增实际消费方补入对应行；不借此扩修无关同名字段。查目标自己的`绝不|不许|禁止|must not|别把`再改。

### 0.2 活接口清单

所有路径前缀均为`/api/v1`；拓扑请求显式带`lab_profile_id`作用域，不从当前GUI文本推断目标。字段形态取对应live schema与现有服务客户端，不使用手写近似响应。

| 真实接口 | 请求/验收用途 |
|---|---|
| `POST /api/v1/switch-topologies`、`GET/PATCH /api/v1/switch-topologies/{topology_id}` | 新图/普通保存；PATCH可只改name或完整图；以SQL原JSON和GET双重核对 |
| `POST /api/v1/switch-topologies/import/from-template` | `template_id=caict_v4`及明确Lab/category；原模板不变，replace受引用保护 |
| `POST /api/v1/switch-topologies/{topology_id}/conversion-preview` | `TopologyConversionRequest(nodes, connections)`，返回source_digest/candidate/differences；只读 |
| `PATCH /api/v1/switch-topologies/{topology_id}` | 转换提交`conversion: {source_digest, changes}`；不能把preview candidate直接当普通PATCH替代CAS |
| `GET /api/v1/switch-topologies/{topology_id}/paths/{mode}`、`GET /api/v1/switch-topologies/{topology_id}/calibration-matrix/{mode}` | 通用路径、未知传播与owner去重的真实响应 |
| `GET /api/v1/lab-profiles/{lab_profile_id}/rf-chains`、`GET /api/v1/lab-profiles/{lab_profile_id}/calibration-scope`、`POST /api/v1/lab-profiles/{lab_profile_id}/calibration-scope/compare` | 正式末边投影及scope；compare携带原baseline，不能重建baseline遮盖变化 |
| `GET /api/v1/lab-profiles/{lab_profile_id}/route-calibration-paths` | 查询`topology_id`/`operating_mode`，返回`list[RouteSelection]`，使用服务端digest |
| `POST/GET /api/v1/lab-profiles/{lab_profile_id}/fixed-route-acquisitions`、`GET /api/v1/lab-profiles/{lab_profile_id}/fixed-route-acquisitions/{run_id}`、`POST /api/v1/lab-profiles/{lab_profile_id}/fixed-route-acquisitions/{run_id}/cancel` | 单路真实start/history/progress/cancel生命周期 |
| `GET /api/v1/lab-profiles/{lab_profile_id}/fixed-route-acquisitions/{run_id}/application-preview`、`POST/GET /api/v1/lab-profiles/{lab_profile_id}/route-calibration-applications` | 原preview/confirm/history，不新增采用通道 |
| `POST /api/v1/lab-profiles/{lab_profile_id}/route-calibration-batches/preview`、`POST/GET /api/v1/lab-profiles/{lab_profile_id}/route-calibration-batches`、`GET /api/v1/lab-profiles/{lab_profile_id}/route-calibration-batches/{job_id}`、`POST /api/v1/lab-profiles/{lab_profile_id}/route-calibration-batches/{job_id}/continue`、`POST /api/v1/lab-profiles/{lab_profile_id}/route-calibration-batches/{job_id}/cancel` | 原批次；沿既有客户端携带作用域header，不把缺header的422当安全门验证 |

### 0.3 计划交付文件

- Task1新增 `api-service/tests/test_pc04a4e_device_contract_acceptance.py`：HTTP组合及实际消费者，只写前片未覆盖的组合；复用既有fixture，不建第二套补偿算法。
- Task2新增 `api-service/tests/pc04a4e_browser_fixture.py`、`gui/test/pc04a4eDeviceContract.browser.js`、`gui/test/pc04a4e.vite.config.ts`：隔离建库/manifest、真实UI矩阵、专用代理。沿4d模式取最小必要代码，不修改旧脚本或共享conftest。
- Task3新增 `docs/guides/topology-device-contract.md` 与 `docs/validation/2026-10-27-pc04a4e-device-contract-acceptance.md`：用户操作指南、正式结果与未验边界；最小更新本计划、批准设计当前状态与roadmap。
- 原始产物放唯一新建 `/tmp/pc04a4e-XXXXXX/`，截图/日志不覆盖旧片；正式摘要列绝对证据路径、SHA256、命令、输入版本与真实统计。生产文件修改清单只有确认真实故障后才能追加，并说明故障输入和最小修法。

## Task 1：真实API组合契约与正式消费者验收

**Files:** 新增上列`test_pc04a4e_device_contract_acceptance.py`；只读复用`test_pc04a4d_conversion.py`、`test_pc04a4d_loss_truth.py`、`test_pc04a4a_nominal_identity.py`、`test_pc04a2_route_application.py`、`test_pc04a2_route_freeze.py`、`test_pc04a2_route_compensation.py`。

**Interfaces:** 消费原POST/PATCH/import/preview及原采用/执行fixture。输出逐case请求/响应、SQL前后、selection与新旧freeze的证据索引，供Task2选择同构图、Task3判定覆盖；不增加业务接口。

- [ ] 1. 读取上述fixture及接口字段，按E01～E06列出新增case与已有case复用映射；记录每个对象的Lab/暗室/topology/node/edge/chain/run/application/execution身份。E05以冻结fixture的`conn_p0v`正常链（终点`probe_0_v`）为身份基准；借用参考图时将原`probe1v`接入点明确映射到`probe_0_v`，参考PA边使用独立`pa_edge_id`并核对实际`calibration_connection_ids`，不能将`conn_p0v`当参考PA边或混用两个probe身份。先冻结模板原件hash。
- [ ] 2. 只新增以下组合；使用真实TestClient/生产resolver，外部transport沿既有受控fixture，不替换builder/parser/正式消费者。对已正确功能允许直接GREEN，不回退生产造RED。

| ID | 输入/步骤 | 必须断言 |
|---|---|---|
| E01 | 同图标称metadata、端口角色、内部pair经POST→PATCH→GET；另原caict_v4真实import→局部显式转换 | 原ID/opaque/未编辑稀疏数值保留；四类声明能共同保存，旧图无关改名位置不被误伤；非法最终图422原子不写 |
| E02 | 正常/参考模式交叉引用；端口删除/改名、删边、错误pair、BSE dl/ul冲突；普通PATCH与conversion各入口 | 拒绝列出实际引用，不偷删；合法替换先更新引用再删旧口可保存；未声明与unknown不获自动能力 |
| E03 | 同cable/receive_cable两边2/2→显式owner→撤销；owner=calibrated0、null、未选owner、跨模式半组 | 通用4→2→4；末边仍原语义，上游组不偷加入末边；0不fallback、未知为None；错误引用拒绝；相位不变 |
| E04 | 原受控采集/确认/执行链先建confirmed，再HTTP改metadata/owner；两次执行与旧冻结回读 | confirmed28 dB一次、不叠加标称/2 dB；原run/采用历史/证书/旧冻结不变；pin/pair变化不能沿用旧匹配。数值仅隔离fixture输入 |
| E05 | 有效calibration模式含被选中的参考PA边，数值键缺省，只改pa_gain_db metadata | 先断言selection参考边ID非空且包含PA；HTTP保存后数值仍缺键、正常/参考摘要符合原metadata契约；重新preview、确认/新freeze沿同一受控采集证据；旧证据不变。不能用不含参考边的fixture代替 |
| E06 | 已解析正常链＋缺ports/internal_paths旧参考receive_cable；owner保存后scope/compare，再selected-route与采集；另无calibration模式 | scope/compare可读当前保存声明，不扩大为整图借值；实际采集严格拒绝，零新有效采集/采用；无calibration模式不投影参考owner |

- [ ] 3. E05先用现存fixture组装完整参考图（依据`test_pc04a4a_nominal_identity.py`的`graph`及4d的正常/参考参数化）；不得把`real_capture`名称当硬件证据。若现成采集fixture无法让参考PA进入真实selection，明确记录缺口并停下该case定位，不写假成功。核心断言形状为：

```python
assert pa_edge_id in selection['calibration_connection_ids']
assert 'pa_gain_db' not in saved_raw_pa_edge
assert after_selection['route_digest'] == before_selection['route_digest']
assert entries(second_execution)['conn_p0v']['source_kind'] == 'confirmed_route'
assert entries(second_execution)['conn_p0v']['value_db'] == 28
assert read_execution_route_compensation(first_execution) == first_freeze
```

`selection`取真实路径响应的单条`RouteSelection`，`calibration_connection_ids`在其顶层。GET采集run的路径快照取`result.configuration.route_selection`；底层`DiagnosticRun`封套取`sequence_evidence.extra.fixed_route_acquisition.configuration.route_selection`；`selection_snapshot`只属于`RouteApplicationRecord`采用记录。按同一run/application身份分别归档，不混用三种封套。`saved_raw_pa_edge`取SQL原JSON，`entries`与freeze reader复用已存在fixture/API；这是断言片段，不是可独立运行的伪fixture，不为片段更改生产契约。

- [ ] 4. 新库隔离运行新增文件及4a～4d契约/identity/route application/freeze/compensation相关集；原命令、实际输出与退出码落证。只有真实生产失败才按第4节RED→最小修复→GREEN，核心变异并恢复hash；脚本错误不计产品RED。
- [ ] 5. 逐case记已验/失败/未执行，独立规格与质量审查；提交本任务最小增量。Task1不跑全后端、不push。

## Task 2：真实浏览器全器件与生命周期验收

**Files:** 新增上述fixture、浏览器脚本和Vite配置；参考4d的`pc04a4d_browser_fixture.py`、`pc04a4dMatrix.browser.js`与`pc04a4dConversion.browser.js`，4b端口和4c内部路径脚本只作操作参考。

**Interfaces:** fixture输出JSON manifest，至少包含database、lab_id、chamber_id、switch_category_id、source_topology_id、display_topology_id、模板hash和逐category/binding Mock核验；脚本输入manifest与目标URL，输出E07～E15行证据。源图和展示图不相同时不得用副本DOM证明源图编辑。

- [ ] 1. 新fixture在任何app导入前照4d验证`sqlite:////tmp/pc04a4e-[A-Za-z0-9]+/browser.sqlite`、文件不存在、父目录存在、两个true开关。默认bootstrap后逐项设Mock/核绑定，地址只用192.0.2.x；建甲乙两独立暗室、两开关图、原CAICT import源图及同构可采集声明图。只创建明确标注的隔离历史样本，不复制用户DB。
- [ ] 2. Vite沿原配置覆盖`/api`、`/api/v1/ota`、`/api/v1/ws`全部指向本片API。建议18099/5194，先检查空闲；冲突换同一manifest与配置，不停止现有服务。记录PID、命令、端口和启动时间；fixture/服务进程使用同库及全Mock环境。
- [ ] 3. 逐类真实打开编辑抽屉并保存重载；器件全集从当前`nodeTypes`/新增菜单/旧图提取，不硬写“14或19类全部通过”。数值输入采用0和非零各一，清空为null，仅metadata保持原缺键/旧字符串。每行保存请求、响应、GET、SQL、DOM截图和对象ID。

| ID | 必须实际操作的器件与属性 | 断言/范围 |
|---|---|---|
| E07 | PA gain_db、pad attenuation_db、combiner loss_db、probe/antenna/reference_antenna gain_dbi；旧PA边pa_gain_db与线缆边cable_loss_db | 单位/来源/频段保存；空/0/非零不混；不为无标称字段的类别发明字段；负衰减/非法频段拒绝 |
| E08 | 普通/接收线缆、CE、基站、EMCenter/开关、SA/VNA、负载、空气段及旧ce_port/bse_port/sa_port | 端口数量来自声明；unknown文案不冒充双向能力；基站逻辑与物理分开，空气虚拟端点不称物理口；目录身份不复制为驱动能力 |
| E09 | PA/衰减器/合路器内部pair白名单；负载终止、开关原port_maps；真实鼠标连线/拖节点 | 合法pair保存且解析可达；非白名单不默认全通；错误方向与删除引用被拒；拖动保存重载坐标确实改变（新证据，不倒填C07） |
| E10 | 原CAICT源图选中旧PA边定位，实际编辑来源/数值并保存重载；旧ce/bse/sa显式转换 | 保留原图ID、非目标节点/边/opaque及模板hash；先预览再取消GET/SQL不变，再确认仅指定字段改变；不是只改测试副本或只看版本提示 |
| E11 | 已有图同线缆owner设置/预览/保存/alias只读/定位owner/撤销；null与0图 | 可见原值/采用源/通用与末边消费区别；显示未知或0.0，不显示None、不补0；撤销后原量值恢复参与；无自动猜测 |
| E12 | 抽屉取消、已应用未保存、422修正重试、真实离线保存失败再恢复 | 取消无泄漏；失败草稿保留；成功PATCH→GET→重载才记通过；不能仅toast证明落库 |
| E13 | 保存pending、转换preview在途、过期digest409、dirty切Lab、清洁甲乙甲、切开关/重导入 | 软件锁真实DOM观察；迟到响应不盖新图；409重预览；转换会话失效；Lab无串写；重导入仅独立无历史图，受引用replace拒绝 |
| E14 | 单路两轮start/running→取消未知→服务端终态→恢复编辑/保存→再进入；批次preview/start/continue或cancel与再次进入 | 两轮run/job身份分开；取消请求尚无回执不解锁；Mock net_loss为空、样本空、formal_eligible=false、采用拒绝；固定直连不生开关I/O，批次不越过人工步骤 |
| E15 | Task1 E06历史参考图组合在当前GUI显示scope/compare，再尝试选择/采集；历史查看/报告读下载 | 当前盘点正常但采集严格失败，不能显示正式PASS；历史样本哈希不改，报告声明仅为软件诊断/Mock，不称客户正式报告 |

- [ ] 4. CAICT图若不是原选择器实际展示对象，在隔离fixture为原import行关联独立全Mock类别使其可选择（只改测试展示关联，不改nodes/edges）。记录源/展示/请求三个ID一致后才执行E10；不得直接调用处理器冒充UI动作。
- [ ] 5. 两种资格证据物理分开：本Task全Mock真实浏览器只验拒绝与生命周期；Task1脚本化transport验证原confirmed软件消费者。不要为浏览器绿色把Mock改“real”或绕过资格。参考PA有效冻结仅以Task1的新证据判断。
- [ ] 6. 运行GUI相关集与production build，记录全部warnings。真实查看关键截图：CAICT旧PA抽屉、方向/pair、转换差异、未知/0、取消未知锁定、重载坐标。失败尝试单独保留，不覆盖首轮日志/截图。
- [ ] 7. 独立规格/质量审查、提交；服务只关闭已核身份的本任务PID与具名浏览器，复核本片端口无监听，不删除证据。若Task3仍需复验可保留受控服务，但交接其准确身份。

## Task 3：操作指南、正式验证摘要与收口

**Files:** 新增上述guide/validation；最小更新设计、roadmap与本计划状态。Task1/2的脚本不因文档需要无故重构。

**Interfaces:** 输入两任务的实测矩阵/证据manifest、输入hash与失败清单；输出用户指南、逐条结果、未验边界、完整当前输入审查包。不把作者自查称独立审查。

- [ ] 1. 用户指南依真实UI写八段：选Lab/原拓扑；增器件与目录引用；标称与metadata；物理/逻辑/虚拟端口；内部pair与外线；CAICT旧PA定位与显式转换；owner两侧归属/撤销与未知；保存/取消/离线/409/采集锁和历史查看。每段给实际按钮、成功回读、拒绝原因及恢复动作，截图标隔离Mock示例；明确声明不等于硬件资格，confirmed整链一次，不能据标称自动补偿。
- [ ] 2. 正式摘要逐行填E01～E15真实结果、输入SHA、对象身份、HTTP/SQL/DOM/消费者证据与未验范围；一个ID含多分支时逐分支列，不把部分通过写整行通过。前片只按未变输入复用并写“未重跑”，V1新证据单独列，不能改旧摘要未验描述。
- [ ] 3. 以下为相关验证命令（须在第5节隔离环境中执行）。按Task1实际引用追加同根文件，不把不同运行统计相加成一次通过。

```sh
# cwd api-service；已设置专用新SQLite与两个true开关
.venv/bin/python -m pytest tests/test_pc04a4e_device_contract_acceptance.py tests/test_pc04a4d_conversion.py tests/test_pc04a4d_loss_truth.py tests/test_pc04a4c_internal_contract.py tests/test_pc04a4c_internal_routes.py tests/test_pc04a4c_internal_identity.py tests/test_pc04a4b_port_contract.py tests/test_pc04a4b_port_identity.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_eligibility.py tests/test_pc_04a_fixed_route_api.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_safety.py -q
# cwd gui
npx --yes tsx --test test/topologyInternalPaths.test.ts test/topologyPortContract.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

- [ ] 4. 先分类最终diff，再决定全后端：若触发Global Constraints的共享输入条件，由本任务唯一责任位跑`.venv/bin/python -m pytest tests -q`；否则记录“本片未跑新版全量”及旧7945/17/1仅前片的边界。全量不可提前与实现并行；起止HEAD、dirty diff、跟踪/未跟踪测试/fixture、依赖、源码/schema和作为门输入的Markdown清单/hash一致才可复用。
- [ ] 5. 文档新增路由字面量会影响G8，单独新库运行`tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes`。若仅历史UUID旧误报，核同一门/历史文件/失败位置无diff后披露，仍不称全绿；新失败必须定位。不得改历史报告或放宽门造绿。
- [ ] 6. 自查链接、路径、事实镜像、`git diff --check`及未验边界；主代理安排累计独立审查。Ready PR后R1→R2；R2无P1收口，仍有P1则修复并续审覆盖最新HEAD直到无P1。R2后P2/P3仅报告不自动入池；最新SHA约束merge、主main安全同步、保留用户改动与全部证据。

## 4. 失败收敛，不为验收扩功能

1. selector/脚本/fixture不足：保存失败原件，仅修本片验收代码；重新核源图身份、模式、pin、最新图排序、selection，不把它叫产品RED。
2. 产品可观察故障：写出输入→错误结果、全部对称消费方及禁令；用真实入口最小测试先RED，优先去掉错误逻辑/换源/收窄，GREEN后核心变异实红并恢复hash。GUI故障先真实API浏览器RED。新机制或范围扩张须主代理重新裁决，不顺手改资格、驱动、共享fixture或历史。
3. 安全/资格相关失败不通过“多捕获异常、补0、放宽匹配”收敛。停止受影响case，保留数据库和日志；其余独立只读/隔离case可继续，但缺项如实列，不给整体验收PASS。
4. 同一输入非预期失败不能靠无限重跑择绿。定位后新输入另起新库，保留首轮与复验；未知根因仍写未知。
5. 本片完成条件：E01～E15的已批准软件范围有可定位证据和独立审查，指南可按真实UI操作；不能执行的边界明确解释并由主代理裁决，不以文档代替运行。B/HOLD、ASC/CE、PG及实物计量仍不关闭。

## 5. 环境与证据操作约定

以下仅执行阶段使用；本计划编写阶段不运行Python测试/应用。每次独立相关/浏览器/全量运行使用不同新目录；启动器在app导入前校路径和开关，不在默认环境先import再修变量。

```sh
# cwd api-service；目录只创建不删除，mktemp返回绝对路径
acceptance_dir=$(mktemp -d /tmp/pc04a4e-XXXXXX)
export DATABASE_URL="sqlite:///$acceptance_dir/browser.sqlite"
export USE_MOCK_INSTRUMENTS=true
export BOOTSTRAP_ON_STARTUP=true
export LOG_DIR="$acceptance_dir/logs"
.venv/bin/python tests/pc04a4e_browser_fixture.py
```

相关/全量用各自新目录下`related.sqlite`/`full.sqlite`，同样先默认bootstrap、显式Mock并核绑定（复用本片fixture中的隔离准备逻辑，不用browser文件存在校验去重建已有库）。pytest旧fixture可能为脚本化transport显式构造“real”语义对象，须逐case说明其transport替身及不触硬件边界，不能宣称每条旧测试binding字段始终Mock。

保存`manifest.json`、命令原文、stdout/stderr、退出码、UTC起止、依赖版本、HEAD/diff/hash、模板/历史前后hash、每阶段HTTP/SQL/DOM/截图、进程与停机记录。摘要分别列“本片执行”“仅复用”“未执行”“失败/未知根因”。任何返回成功均核消费端与持久化，不以进程退出、toast或截图单独替代完整证据。
