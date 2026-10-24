# PC-04A-2：原拓扑选路、采集与确认应用实施计划

> **执行说明：** 主代理审定后，由单一实现worker使用 executing-plans 技能逐任务执行，复用独立只读审查者复核；不是禁止使用子agent。本片 WIP=1，不并行开展另一片功能。以下保留原批准施工清单，复选框不是当前交付状态；不以测试替身代替来源核验。当前状态：Task1～6已实现并分别独立内审收口，Task7最终验证与整片内外审仍在进行，尚未合并；以roadmap当前状态及本片SDD报告的版本/命令证据为准。

**Goal:** 在原可编辑射频拓扑选中单条完整通路，复用采集、取消和历史；有充分可信证据且经操作员确认的新整条校准进入新执行，已开始执行保持原冻结选择，整条量值只补偿一次。

**Architecture:** 原 ReactFlow 继续负责器件、接线和路径高亮，侧栏复用固定通路采集逻辑。不可变采集记录与不可变确认应用记录分离，逐通路当前选择通过事务更新；执行启动前将本次有效混合来源和数值整体冻结，所有消费方使用同一冻结对象。新方法不写旧单段损耗、不覆盖旧证书、不自动签发资格。

**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/Alembic；React/TypeScript/Mantine/ReactFlow/TanStack Query；pytest、tsx node:test、Playwright CLI；独立SQLite全Mock真实API浏览器。

**Spec:** `docs/design/2026-10-24-topology-calibration-integration.md` 第二片及全局约束；量值依据 `docs/design/2026-10-22-pc-02a-calibration-method-reference.md` §3。

## Global Constraints

- 保留原可编辑射频拓扑，不另做只读替代画布；原拖动、连线编辑和保存继续工作。
- 复用 `services/calibration/fixed_route_jobs.py` 的绑定核验、独占访问、取消及持久化记录，不另起一套仪器采集。
- 先保存拓扑再采集，采集期间冻结本次通路、设备身份、端口、频率、极化及参考件信息；不得在结果读取或报告时用当前配置补填历史。
- 配置变化只提醒操作员复核，不自动降低就绪状态或强制重校准；身份、频率覆盖、证书状态和真实证据要求独立保持。
- 模拟、缺测、来源未知、停止未确认的结果不得应用为正式校准。
- 本片仅现有固定直连，不自动切换开关、不新增SCPI，不把声明端口或目录关联当硬件控制资格。
- `L_NET=P_CE-(P_SA+L_RX)`，正衰减、负增益，不取绝对值；不再增减参考天线/探头增益或PA标称增益。
- 新值不是纯传播损耗、场强或DUT功率；不能写到任一单段 `calibrated_loss_db` 再累计。
- 每项先行为RED再最小GREEN；生产共享冻结/补偿契约变化后最终全后端由主代理执行，不能用Mock解除现场验收。
- 本计划只覆盖PC-05A必要适用/冻结/应用子集，不整项关闭PC-05A，不启动整套自动测量或PC-07A完整报告工程。

## 0. 真实来源、确认采用与认证资格分别表达

现有可信对象已经核对：

1. `schemas/fixed_route_acquisition.py::FixedRouteResult/FixedRouteRecord` 的 `formal_eligible` 均为 `Literal[False]`；默认 `missing_items` 包含仪器绝对准确度、参考件证书及完整不确定度待核。
2. `schemas/calibration_scope.py` 明确只盘点配置，`physical_identity='unverified'`，不是资格来源。
3. `models/probe_calibration.py::ProbePathLossCalibration` 有 `use_mock/status/valid_until`、SGH字段和旧路损数据，但没有将新采集run与源端功率参考、接收线缆证书、不确定度审核逐项绑定的关系。
4. `models/calibration.py::CalibrationCertificate` 与 `schemas/calibration.py::GenerateCertificateRequest` 是TRP/TIS/重复性等系统证书；不是本次指定F64口→参考天线端口测量的资格记录。不能按它的 `overall_pass` 给新采集背书。

**结论：现有证据可以支持服务器核验真实采集并由操作员确认采用，但不能宣称计量认证合格。** PC-04A的恒False是上一片不授予资格、不自动应用的边界，不是对全部真实记录永久拒绝的判决。本片不更改原采集的False及missing_items；应用记录分别写 `operator_confirmed=true`、经服务器判定的 `measurement_provenance=real`、`certification_status=unknown`。确认不是来源证据，样本标准差不是完整不确定度，缺计量资料须展示，但不自行增加认证平台、外部证书审核或整套预算通过后才能采用的门槛。

### Task 0：主代理已审定证据映射、采用期限与参考面，不另建认证平台

主代理裁决已记录于 `.superpowers/sdd/2026-10-24-pc04a2-topology-calibration-apply/progress.md`：真实采用与认证未知分开；选用截止时间由操作员显式填写，不默认180天，不是证书期限。Task 1已获实施批准，其余任务按顺序单独交接。

**Files:** 本计划及上述Spec，由主代理审定；本任务不创建生产接口。

- [x] 审定下述逐项服务端证据校验；不收客户端use_mock/verified/认证布尔。采集时参考天线、位置和接收线缆来源仍按操作员声明保存，不假装仪器自动核验实物接线。
- [x] 保留完整计量预算、仪器绝对准确度、参考件证书等缺项为warnings及认证未知；不把缺少新认证审核入口作为整个正向采用的阻塞。
- [x] 明确新端口到端口量值在信道引擎的参考面适配：新方法已包含实际探头/空气/参考天线关系，生成补偿entry时新method的净损耗只进入一次修正，不能再沿旧方法加 `probe_gain_dbi`；普通控制预算与ASC预失真各自验证。仍不宣称该值就是DUT功率或自由空间路损。
- [x] 审定以下明确的采用期限策略，不让实现者默选180天。主代理定稿是本计划的一部分，不重复向用户索取产品方向批准。

### 既有有效期及本计划采用期限策略

`path_loss_calibration_service.py::PATH_LOSS_VALIDITY_DAYS=180`，由旧 `start_calibration()`和`start_calibration_for_lab_profile()`给旧ProbePathLossCalibration设置valid_until；`resolve_latest_calibration()`要求status=VALID、valid_until>当前时间，同频匹配使用请求频率±5%，mode精确优先、再legacy空mode。这些是旧证书的软件政策，不是厂商保证，也没有源码依据证明自动适用于新method。

主代理已采纳显式新策略：新确认请求必须提供 `adoption_valid_until`（UTC带时区、未来截止时刻），它是操作员声明的**选用期限**，不是仪器/计量证书有效期；不提供时422，不默认180天，不把计量缺项变成无限期认证。应用记录保存 `validity_source=operator_declared_adoption_window`，范围仅所测频点/极化/参考面。若实际关联的独立资料已明确失效、撤销或不兼容，仍拒绝；不能以声明截止时间延长这些资料。旧证书仍沿旧180天/±5%规则。本项为已批准、尚待Task3实现的应用策略，不是已有生产事实。

### 服务端真实来源校验的具体落点

- `fixed_route_jobs.resolve_configuration()`已核对Lab绑定、已保存/已加载F64和FSVA型号连接、真实/模拟一致性；结果configuration快照及CE binding用于身份匹配，目录名称不是证明。
- `collect_fixed_route()`的真实分支要求两台确切真实驱动类；states.f64_identity与exchanges中的F64 IDN匹配；指定output的参数1实测命令必须有当次有限读数，不能取requested_power_dbm。前后RUNNING、零output_loss及期间未变条件均须有匹配记录。
- `RealRsFsvaDriver.capture_fixed_route_power()`保存分析仪IDN、明确单位/窗口设置、完整单次结束、错误队列和功率回复；应用评估复核这些已实现的证据类型，不新增查询或猜另一种方言。
- `samples/exchanges`必须属于同一run的两台身份，含至少请求次数的有限真实样本、有效主机时间和无simulated/error交换；服务器按原method重算均值与净损耗，不能收客户端结果。
- `status=completed`、`cleanup_confirmed=True`、`states.f64_control_released=True`，且不是中断/取消/缺损历史。缺接收线缆值或本频点来源不能计算/采用；现有reference_antenna和fixed_route_confirmed保留为明确操作员声明，不提升成自动接线证明。
- `path_loss_preflight._evaluate_path_loss_provenance_for_measure()`、`measure._is_path_loss_certificate_verified()`现有保护核心是明确真实来源；新版应用通过上述证据取得相同真实来源分类，不借确认按钮改布尔。precheck对已有失败系统证书、执行diagnostic/invalid资格的独立规则保持；缺系统证书当前只是warning，不增设强制认证。

## 1. 实际生产读写全集

| 环节 | 现有函数/对象 | 本片要求 |
|---|---|---|
| 原画布 | `gui/src/features/TopologyEditor/TopologyEditor.tsx::TopologyFlow`、`topologyDraft.ts` | 保留同一草稿，保存后选路；侧栏不另存另一张图 |
| 链身份 | `calibration/rf_chain_resolver.py::resolve_rf_chains/_binding_to_spec/RFChainSpec` | 当前是终端边身份，不是完整多跳路径；保留chain_id兼容并补完整序列 |
| 正常接线 | `mimo_ota/switch_orchestrator.py::orchestrate_switch_topology/_parse_probe_binding` | 正式执行读显式活动连接；不因选择校准参考件改变正常探头身份 |
| 图通用解析 | `topology_service.py::resolve_paths/get_mode_connections` | 空活动列表回退标签；选路必须明示采用集合，不让新路自动启停旧路 |
| 配置快照 | `calibration/configuration_scope.py::build_calibration_scope` | 保存完整选择及参考接线，不把digest差异变成必须重校准 |
| 采集 | `fixed_route_jobs.py::resolve_configuration/start/_execute/record/request_cancel`、`fixed_route_acquisition.py::collect_fixed_route` | 复用；历史只读采集快照 |
| 旧逐链校准 | `path_loss_calibration_service.py::start_calibration_for_lab_profile/_real_path_loss_measurement_via_ce_sa` | 旧计算带天线增益和abs，不能与新净损耗混用 |
| 证书选择 | `ProbePathLossCalibrationService.resolve_latest_calibration` | 当前整份latest、旧频率容差及mode回退；不能让单链新记录遮住整套旧记录 |
| 执行创建 | `test_case_runner.py::launch_test_case_execution` | 在后台调度前冻结路损选择与数值；现有BS/CE/坐标冻结不能代替此对象 |
| 硬件前门 | `base_station_execution_session.py::_path_loss_preflight`内闭包 | 不再独立选最新，读执行冻结结果；仍先于硬件控制 |
| 应用选择 | `mimo_ota/path_loss_preflight.py::evaluate_path_loss_preflight` | 统一适用性、来源、实际应用，不重查当前指针补旧执行 |
| 信道建立 | `channel_engine_client.py::_query_calibration_entries/_build_payload`；MEASURE内建立仪器/信道，无独立setup.py | 消费冻结的逐端口有效补偿，不再查询最新 |
| 真正补偿 | `channel-engine-service/app/api/endpoints/hardware_pipeline.py::_compute_control_instructions`及确定性ASC `calibration_config` | 普通控制预算与ASC预失真分别核对，不能在两处叠加同一补偿 |
| 测量 | `mimo_ota/executors/measure.py::MeasureExecutor.execute` | 当前再次选证书、逐链映射及记录方位补偿；改为同一冻结对象 |
| 判定/报告 | `executors/analysis.py`、`executors/report.py::_build_mimo_ota_content_data`、`mimo_ota/path_loss_application.py` | 保留正式白名单；混合来源可追溯，不以当前配置重建历史 |
| 旁路消费者 | `probe_calibration_service.py`方向图校正使用旧逐链 `total_insertion_loss_db` | 不把新端口量值伪装旧空间校正，方向图旧方法保持不变 |

## 2. 拟新增契约与接口（均为计划，不是已存在）

新建 `api-service/app/schemas/route_calibration.py`，所有请求 `extra='forbid'`，数值有限、无默认零：

- `RouteSelection`：`lab_profile_id, chamber_id, topology_id, operating_mode, chain_id, ce_port, probe_id, polarization, node_ids, connection_ids, ports[{connection_id,source,source_pin,target,target_pin}], route_digest, calibration_node_ids, calibration_connection_ids, reference_antenna_id, analyzer_category_id`。`route_digest`只覆盖身份/连接/参考面，不包括位置坐标与纯显示文案。
- `RouteEligibility`：`eligible_for_adoption:bool, blockers:list[str], warnings:list[str], acquisition_run_id, route_digest, method, frequency_mhz, measurement_provenance:real|simulated|unknown, certification_status:unknown`。前者只表示服务端采集证据及目标适用允许确认采用，不是认证结果。
- `RouteApplicationPreview`：`selection, acquisition_run_id, expected_current_application_id, old_value_db:float|None, new_net_loss_db:float|None, delta_db:float|None, eligibility`。旧/新不存在时差值也为空，不用0代替。
- `ConfirmRouteApplication`：`acquisition_run_id, route_digest, expected_current_application_id:UUID|None, idempotency_key:UUID, confirmed:Literal[True], adoption_valid_until:UTCDateTime`。截止只表达操作员选用窗口；不接收损耗、真实来源/认证布尔、证书编号或硬件地址。
- `RouteApplicationRecord`：`id, predecessor_id, acquisition_run_id, selection_snapshot, method, frequency_mhz, coverage_snapshot, reference_snapshot, net_loss_db, adoption_evidence_snapshot, operator_confirmed, certification_status:unknown, confirmed_at, confirmed_by`；不可原地覆盖。
- `FrozenRouteCompensation`：`version=1, execution_id, lab_profile_id, chamber_id, topology_id, operating_mode, frequency_mhz, route_entries[], source_records[], selected_at, digest`。每条entry含稳定route身份、`source_kind=legacy_certificate|confirmed_route|unavailable`、source_id、method、参考面、带符号数值、来源与适用结果；没有值时保持空。

嵌套字段合同：`coverage_snapshot={frequency_mhz, polarization, reference_identity_digest, adopted_at, adoption_valid_until, validity_source}`，按Task 0显式拟议策略；只覆盖自身测量频点，不继承旧证书±5%容差，不插值扩大频带。`reference_snapshot={reference_antenna_id, identity_description, position_description, polarization, receive_cable_identity, receive_cable_loss_db, receive_cable_source, analyzer_binding_snapshot}`；已有自由文本足以保存声明来源，不能另要求一个系统尚无的认证UUID；缺真正必需的链/端口/参考件描述仍拒绝，未知实物序列号如实披露，不能拿拓扑UUID冒充。`adoption_evidence_snapshot={acquisition_run_id, checked_exchange_indices, checked_state_keys, evaluated_at, method, blockers, warnings, measurement_provenance, certification_status:unknown}`；来源来自本次服务器保存的原始证据，不收客户端布尔。`source_records[]`逐项冻结来源类型、原记录ID、实际route身份/值/适用范围及证据摘要，不能只冻结ID后读取可变原行。

接口定义：

1. `GET /api/v1/lab-profiles/{lab_id}/route-calibration-paths?topology_id={id}&operating_mode={mode}` → `list[RouteSelection]`；404缺行、409错暗室、422歧义/非法路径。不读取未保存草稿。
2. 复用现有四类 `/fixed-route-acquisitions` 开始/进度/取消/历史；扩展请求增加 `route_digest`，结果version=2保存 `RouteSelection`。旧version=1历史继续可读，不补当前路径，不具新增确认资格。
3. `GET /api/v1/lab-profiles/{lab_id}/fixed-route-acquisitions/{run_id}/application-preview` → `RouteApplicationPreview`，只查询与计算，不写当前选择。
4. `POST /api/v1/lab-profiles/{lab_id}/route-calibration-applications`，body=`ConfirmRouteApplication` → `RouteApplicationRecord`；201新确认、200幂等重放、409当前选择变化、422真实采集证据/适用/终态/采用窗口不满足。
5. `GET /api/v1/lab-profiles/{lab_id}/route-calibration-applications?chain_id={id}&topology_id={id}` → 历史 `list[RouteApplicationRecord]`，不能在读取时补资格或重算旧记录。

新增纯/查询服务函数定义于 `services/calibration/route_calibration.py`：

```python
def list_route_selections(db, lab_id, topology_id, operating_mode) -> list[RouteSelection]: ...
def evaluate_route_application(db, lab_id, run_id) -> RouteApplicationPreview: ...
def confirm_route_application(db, lab_id, request, actor) -> RouteApplicationRecord: ...
def resolve_effective_route_compensation(db, lab_id, mode, frequency_mhz) -> FrozenRouteCompensation: ...
```

新增 `services/mimo_ota/route_calibration_freeze.py`：`freeze_execution_route_compensation(db, execution, test_case) -> FrozenRouteCompensation`、`read_execution_route_compensation(execution) -> FrozenRouteCompensation`。冻结缺损必须显式报错/旧版未知，不能以当前配置补写。

## Task 1：完整路径选择与采集快照

**Files:** 修改 `calibration/rf_chain_resolver.py`、`configuration_scope.py`、`fixed_route_jobs.py`、`schemas/fixed_route_acquisition.py`；新增上述 `schemas/route_calibration.py`、`services/calibration/route_calibration.py`、`api/route_calibration.py`，在 `app/main.py`按现有方式注册；测试 `tests/test_pc04a2_route_selection.py`。

**Interfaces:** 实现 `list_route_selections()` 与接口1；显式route_digest必须匹配保存图中唯一选择，version2保存完整选择，旧version1历史只读。兼容旧请求：configuration_digest仍强制核验，服务器必须在绑定实验室/模式/拓扑中唯一解析完整路径才能创建version2；缺完整路径、端口或歧义不回退。开始与租约前核对同一冻结选择，显式错误digest不能走缺省分支。Task 6新客户端必须发送topology_id/operating_mode/route_digest。

- [ ] 写RED：CE→被动器件→probe为一个完整序列，校准参考件只在独立快照，不被当正常probe；两个可达分支、回路、未知CE口分别422；跨实验室409且无仪器I/O。
- [ ] 运行 `cd api-service && .venv/bin/python -m pytest tests/test_pc04a2_route_selection.py -q -o log_cli=false`，确认断言因尚无完整路径/快照而失败；不把导入错误当行为RED。
- [ ] 最小实现反向追溯唯一源到目标，保留既有终端chain_id；原有连接明确ce_port优先，不根据被动器件标签猜F64口。不改变旧正常执行解析器。
- [ ] 开始与租约前复核一致保存选择，运行中不再读当前图；停止/取消/互斥原实现复用。
- [ ] 同命令GREEN，并跑 `tests/test_pc_04a_fixed_route_api.py tests/test_pc_04a_fixed_route_acquisition.py`，显式stage本任务文件后提交。

样例测试意图（fixture中的真实服务端小图由测试数据库构造）：

```python
def test_passive_hops_are_frozen_without_promoting_reference_nodes(db, lab, topology):
    routes = list_route_selections(db, lab.id, topology.id, 'mimo_ota')
    assert routes[0].node_ids == ['ce1', 'pad1', 'probe1v']
    assert routes[0].connection_ids == ['ce-pad', 'pad-probe']
    assert routes[0].calibration_node_ids == ['reference1', 'rx-cable1', 'sa1']
    assert routes[0].probe_id == 1
```

## Task 2：真实证据评估、确认采用与量值适配边界

**Files:** `services/calibration/route_calibration.py`、`schemas/route_calibration.py`、`tests/test_pc04a2_route_eligibility.py`；复用现有采集证据，不建认证资料审核平台。

**Interfaces:** `evaluate_route_application()`；接口3；`RouteEligibility`不改变原始采集的恒False。

- [ ] 写RED表：simulated、running、cancelled、cleanup_unconfirmed、interrupted、缺原始交换/样本、缺接收线缆来源、旧version1缺完整路径历史均不可采用；completed单字段不能自动获准。
- [ ] 固定时钟构造采用窗口已过期与已有独立记录明确失效反例，不延长生产有效期；改变图坐标或无关标签只warning，不自动失去适用性。路径/端口/极化/参考面实际不匹配拒绝该候选，不命令重校准。
- [ ] 运行 `.venv/bin/python -m pytest tests/test_pc04a2_route_eligibility.py -q -o log_cli=false`，记录RED输入与具体失败。
- [ ] 按Task 0列出的具体生产证据实现白名单，不能用missing_items是否为空判来源；保留准确度/计量预算缺项为warning和认证未知，不挡已满足实测证据的操作员采用。
- [ ] 同命令GREEN；真实正例和不提升认证资格同时断言：

```python
def test_real_capture_may_be_adopted_without_claiming_certification(db, lab, completed_real_run):
    preview = evaluate_route_application(db, lab.id, completed_real_run.id)
    assert preview.eligibility.eligible_for_adoption is True
    assert preview.eligibility.measurement_provenance == 'real'
    assert preview.eligibility.certification_status == 'unknown'
    assert completed_real_run.sequence_evidence['extra']['fixed_route_acquisition']['formal_eligible'] is False
```

- [ ] 审定量值适配的正衰减28dB、负增益-12dB算例；新净损耗不得再加参考/探头增益，不能取abs，不写旧空间路损字段；样例数据始终标合成，不称实测。
- [ ] GREEN后独立提交；只有拒绝分支或只有界面确认不能冒充整片正向应用闭环。

## Task 3：不可变确认应用与并发选择

**Files:** 新增 `app/models/route_calibration.py`；修改 `app/models/__init__.py`按现有模型注册；新增单个Alembic revision（生成时以当时唯一head为down_revision，不预造revision号）；实现 `route_calibration.py`服务/接口4、5；测试 `tests/test_pc04a2_route_application.py`。

**Schema:** 两张表：不可变 `route_calibration_applications` 保存上述record；`route_calibration_selections`以 `(lab_profile_id, topology_id, operating_mode, chain_id, frequency_mhz, reference_identity_digest)` 唯一，保存 `application_id/version`。应用表对 `(lab_profile_id,idempotency_key)` 唯一。外键关联DiagnosticRun；不修改任何历史证书或采集记录。

- [ ] 写正向采用测试：用已有真实驱动类和脚本化外部transport走collect_fixed_route→DiagnosticRun→真实评估→确认；不mock评估返回True，不伪造新证书。数据是合成测试输入，不称现场实测。
- [ ] 写RED：预览不写入；候选不合格422零写入；错实验室404；expected_current不匹配409；相同幂等键/同载荷200同记录、同键异载荷409；两个并发确认仅一个成功，其余409；旧应用仍可读取。
- [ ] 运行 `.venv/bin/python -m pytest tests/test_pc04a2_route_application.py -q -o log_cli=false`，确认行为RED。
- [ ] 事务内再次载入run及实际独立适用状态，核对目标选择版本和显式采用截止；用条件UPDATE版本比较及唯一约束，不能仅依赖SQLite无效的FOR UPDATE。证据/写入失败回滚，界面不能显示已应用；缺认证材料本身不伪装成来源未知。
- [ ] 迁移在临时数据库验证 upgrade→downgrade→upgrade；不回填历史为已确认，不给旧采集发假证书。
- [ ] 同命令GREEN，检查唯一Alembic head后提交。

## Task 4：混合来源解析与执行冻结

**Files:** 新增 `services/mimo_ota/route_calibration_freeze.py`；修改 `test_case_runner.py::launch_test_case_execution`、`base_station_execution_session.py`、`mimo_ota/path_loss_preflight.py`、`path_loss_application.py`；测试 `tests/test_pc04a2_route_freeze.py`。

**Interfaces:** `resolve_effective_route_compensation()`按实际route身份、频率、极化、参考面解析：适用的新确认逐链记录优先，仅覆盖自身通路；其余通路保留适用旧证书来源；两者均缺则该链unavailable。不把部分新记录存成整份latest证书，不将旧证书平均值冒充缺失链的新覆盖。

- [ ] 写RED：旧证书覆盖a/b，确认仅a的新值28后，新执行a=28/b=旧值，来源分别可追溯；不匹配频率的新记录不遮住适用旧记录。
- [ ] 写RED：执行E1先冻结旧值，确认a新值后创建E2；E1所有消费仍旧值，E2采用新a；冻结后改变当前拓扑、证书或选择指针，不补填E1。
- [ ] 运行 `.venv/bin/python -m pytest tests/test_pc04a2_route_freeze.py -q -o log_cli=false`，确认E1/E2行为RED。
- [ ] 在执行创建事务内、后台启动和硬件控制前一次冻结；已存在历史执行无新冻结时明确legacy未知，不回填。纯前置门与MEASURE读取同一冻结，不再各选一次latest。
- [ ] `path_loss_application`增加可区分混合来源的version2，保留version1解析；不能把多个应用记录伪装成一个旧certificate_id。正式判据逐链核对，不因单链成功把整套判成合格。
- [ ] 同命令GREEN，跑 `tests/test_p1_62_path_loss_application_truth.py`及既有执行资格冻结测试，独立提交。

样例断言：

```python
def test_new_confirmation_does_not_change_an_already_frozen_execution(world):
    first = world.launch_and_freeze()
    world.confirm_real_supported_route('a', net_loss_db=28.0)
    second = world.launch_and_freeze()
    assert world.read_frozen(first, 'a').net_loss_db == 20.0
    assert world.read_frozen(second, 'a').net_loss_db == 28.0
    assert world.read_frozen(second, 'b').source_kind == 'legacy_certificate'
```

`world.confirm_real_supported_route`是本任务测试fixture封装现有真实驱动类的脚本化transport采集、持久化、服务器证据检查和确认服务，并提供明确adoption_valid_until；不是生产方法，也不得mock来源判断或称合成输入为现场验收。

## Task 5：同一冻结值真正进入补偿且仅一次

**Files:** `channel_engine_client.py::_query_calibration_entries/_build_payload`、`mimo_ota/executors/measure.py::MeasureExecutor.execute`、`analysis.py`、`report.py::_build_mimo_ota_content_data`；必要时修改 `channel-engine-service/app/api/endpoints/hardware_pipeline.py`的本地计算/构建，不改厂商指令；测试 `tests/test_pc04a2_route_compensation.py`、`channel-engine-service/tests/test_route_calibration_application.py`。

- [ ] 写RED：新净损耗28、旧拓扑线损3、旧功放标称增益10、探头增益8同时存在时，选择新method后实际使用的总校正只能是28，不能31/18/36；负净损耗-12必须保留符号。
- [ ] 写RED：普通控制预算与确定性ASC分别通过其真实生产函数验证补偿数值；同一执行路径不能同时烘进ASC又再次作为额外硬件修正。仅断言payload字段存在不算通过。
- [ ] 写RED：部分链没有任何适用来源时保持缺项，不能生成“全套校准已应用”；模拟新采集不影响实际正式值及报告。
- [ ] 运行API目录 `.venv/bin/python -m pytest tests/test_pc04a2_route_compensation.py -q -o log_cli=false`，信道引擎目录使用其已安装解释器运行 `python -m pytest tests/test_route_calibration_application.py -q`，分别记录RED。
- [ ] 按Task 0批准参考面转换一次：`fixed_route_port_to_reference_v1`的entry采用`cable_loss_db=net_loss_db, probe_gain_dbi=0`，只在已核对该参考端口参考面的补偿分支使用；这是软件适配口径，不是把实际线缆损耗改成整条损耗，也不是宣称DUT接收功率等于参考天线端口功率。相位仍来自独立既有来源，不从标量净损耗推导。逐端口处理混合来源，旧证书原方法保持原有转换，方向图消费者不接新method。
- [ ] MEASURE逐方位记录实际使用的route/source/method/value；analysis和最小报告兼容新冻结来源，历史报告不重新查当前资料。不扩展PC-07A全部报表需求。
- [ ] 两目录GREEN及既有path-loss/信道生成回归通过后提交。

## Task 6：原画布侧栏完整闭环

**Files:** `gui/src/features/TopologyEditor/TopologyEditor.tsx`；新增同目录 `RouteCalibrationPanel.tsx`；重用/拆分 `LabWorkspace/FixedRouteAcquisitionCard.tsx`采集逻辑和 `fixedRouteDisplay.ts`；修改 `gui/src/api/labProfileService.ts`、`gui/src/types/api.ts`、`api/openapi.yaml`及生成镜像；入口迁移后修改 `LabWorkspace/LabOverview.tsx`移除重复自动采集入口，保留仍有独立价值的人工方法说明。

- [ ] 写纯状态/请求RED：草稿未保存不能采集；所选路径来自当前保存图；切模式不换历史run身份；采集中冻结选择且取消保持可达；预览旧/新/差值有缺项时显示未知；确认失败保留结果、不显示已应用。
- [ ] `cd gui && npx --yes tsx --test test/pc04a2RouteCalibration.test.ts`实跑RED，不用源码token存在性替代核心行为。
- [ ] 点击完整通路高亮原节点/边，侧栏显示频率/极化/参考接线、原新值及未满足条件；复用服务器取消与历史，不以中断HTTP假装停止。
- [ ] 采集中保护实验室切换及图修改；未保存图要求先保存，不能采集旧服务器图而显示草稿高亮。取消完成后保留结果和安全状态。
- [ ] 有完整真实采集证据且目标适用时确认调用接口4，明确输入采用截止，成功后刷新应用预览/历史；源证据/停止状态缺失明确阻断；准确度/完整预算等计量缺项继续显示“认证资格未知”，不隐瞒、不因此自动降低实验室就绪。
- [ ] 全Mock真实API浏览器覆盖选路、拖动/连线回归、开始/取消/历史、跨lab、失败草稿保留；不拦截响应冒充持久化。Mock确认必须拒绝，正式确认正例由真实服务端合成证据fixture验证而非假仪器读数。
- [ ] 目标测试GREEN，`npx --yes tsx --test test/*.test.ts`与 `npm run build`；独立提交。

## Task 7：收口验证、审查与下一片边界

- [ ] 列最终修改全集，核对create/读取/确认/新执行/旧执行/历史/报告及普通合成/ASC对称路径，无新值写旧单段字段。
- [ ] API定点命令合并上述 `test_pc04a2_*.py` 与既有PC04、path-loss、冻结、报告来源和规则检查；主代理跑最终完整后端，记录当前HEAD/命令/结尾统计，不引用前一片输出。
- [ ] 编译检查、单Alembic head、临时迁移验证、GUI契约/build、真实浏览器截图与服务器回读，分别留证。
- [ ] 核实正例走真实驱动类/脚本化transport→持久化采集→服务端来源检查→操作员确认→冻结→实际补偿；原始formal_eligible=False、缺项和认证未知始终保留。只有拒绝分支或只有UI成功不能标整片完成。
- [ ] 内审后Ready PR；R1处理本片可执行意见，R2无P1立即收口，仍有P1则修复后覆盖最新HEAD续审。只有完成全部闭环才开始PC-06A-1。
