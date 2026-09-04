# P2-59 设计稿 —— ChannelEmulatorExecutionPlan + 单一会话（v1，已批准）

> 状态：**已批准** —— 2026-09-04 用户对 §6 五问「按你的建议来」。① 随本稿同 PR 开工；② ③ 各自开工前在 §8 出补遗。
> 前身：P2-58 ①（#450）/ ②（#452）均已合并；本稿事实枚举于 2026-09-04（Explore + 逐项 grep 核实）。

## ⓪ 动手前四行
- **搜索命中**：memory `project_f64_driver_review_20260723`（病根「该问仪器的地方在猜」，`DIAG:SIMU:STATE?` 全驱动零用）、`project_f64_ate_server_capabilities`（F64 ≠ FS16 SCPI 表面；手头只有 FS16 手册）、`feedback_effective_end_not_nominal`；仓库权威：P2-50 `BaseStationExecutionPlan`（`app/hal/base_station.py:903-1025`）、`run_base_station_execution_session`（`app/services/base_station_execution_session.py:88`）、P2-57 manifest 14 个操作（`app/hal/channel_emulator_manifest.py:37`）、P2-58 ① `ResolvedChannelEmulatorBinding` 与 `CE_FREEZE_CONFIG_KEY`（`app/services/channel_emulator_binding.py:524` / 冻结写入 `:621`）；roadmap 条目 :4724。
- **必要性**：执行期对信道仿真器（CE）的能力判断与生命周期没有冻结件可对照 —— ① 冻进 execution.config 的 CE binding **全仓零读取方**（grep `channel_emulator_binding_freeze` 只命中 binding.py 自己）；MEASURE 靠 16 行 `hasattr(emulator, …)` / `getattr(emulator, …)` 探测（`grep -c` 可复现；探的方法**全在 14 个 manifest 操作之外**，P2-57 的 AST 门对它们恒绿）+ 私有缓存 `_loaded_emulation_file`（`measure.py:657`）+ 驱动私有常量 import（`measure.py:80`）选路径。**roadmap 条目写的两半可观察故障都成立** —— 我此前判「`hasattr` 那半已被 P2-57 清掉」是错的，Explore 逐行证伪。
- **范围**：拆三片（§4），本稿只求批 ①；枚举到的镜像站点（手工 CE 端点 6 个、诊断序列若干、`f64_*` 配置字段 6 个）进 Discovered 待评估池。
- **爆炸半径**（①）：纯加法 —— 新 dataclass + 冻结 + 证据字段 + 已 manifest 化的 3 个操作改读 plan。原 X = 能力 / load mode 漂移无检测；修完 Y = 漂移在 I/O 前 FAILED（fail-loud）。Y ≤ X。② ③ 开工前各自另写四行。

## 1. 双实证
- **memory**：已查（上述两条 + 母题总纲）。落到本稿的约束：a) 「预期回读」只能用手册有据、驱动已在用的回读；b) 型号语义（什么叫 safe idle、哪条命令算加载成功）留在驱动 / manifest，**共同执行器不得替仪器断言**；c) F64 的 manifest `source_reference` 今天只能写「驱动源码 / 现场实测」—— 没有 F64 手册。
- **NotebookLM**：① **不适用**（不改任何 SCPI、不新增回读，只把已有判据搬进冻结件）。③ **部分适用** —— 若 safe idle 阶段要新增「`STATE?` 回读判定」而不是沿用 `cleanup.py:176` 的 `stop_emulation()`，开工前须查 PROPSIM notebook：「`DIAG:SIMU:STATE?` 在 CLOSED / 未加载时返回什么，可否作 safe idle 判据」。② 每新增一个 manifest 操作若写手册出处，逐条查（F64 无手册 → 标「实测」）。

## 2. 现状（事实；Explore 枚举，符号与行号已逐个 grep 核实）
### 2.1 `app/services/mimo_ota/executors/measure.py`（4100 行）
- 型号专属标识符 21 个：`_describe_f64_frequency_verification_gap`（:253）；`f64_*` 六个配置字段（`app/schemas/mimo_ota/config.py:484-555`：`f64_bypass_mode` / `f64_fade_after_attach` / `f64_input_ref_dbm` / `f64_crest_db` / `f64_output_gain_db` / `f64_output_level_dbm`）；证据键 `f64.model_loaded` / `f64.model_load` / `f64.output_state` / `f64.bypass_mode` / `f64.simulation_state`；`from app.hal.propsim_f64 import _TOPOLOGY_ESCAPE_HINT`（:80）。无 fs16。
- 能力探测 16 行（其中 `_call_topology_getter` 一处服务 3 个 getter；`required_ce_methods` 一处探 7 个）：`hasattr(emulator, "build_p0_5_command_evidence")` ×4（:1946 / :2283 / :2326 / :2622，注释明写「有 build 能力 = F64 语义驱动」）、`_call_topology_getter`（:364）的 `getattr(emulator, getter_name, None)`、`required_ce_methods` 一次探 7 个（:3876）、`callable(getattr(emulator, "get_active_input_ports", None))`（:4001，「有拓扑能力 = 真 F64」三分叉）等。走 manifest 的只有 `set_passthrough_mode` / `stop_emulation` / `set_baseband_power`。
- 私有状态：`getattr(emulator, "_loaded_emulation_file", None)`（:657，`resolve_model_load_requested` :650 用它当 `f64.model_loaded` 的 requested 真值）。
- 自造驱动：`emulator is None` 时就地 `MockChannelEmulator(...)`（:1647-1653），绕过 HAL 与租约。
- 运行时能力查询：`emulator.get_supported_load_modes()`（:1781）—— 不是 manifest 的 `load_modes`，双真值。
- 参照物就在同文件：BS 的 `evidence.execution_plan.digest != live_execution_plan.digest` 漂移检测（:998）。

### 2.2 四类入口
formal（`services/test_case_runner.py:571`）、commissioning run-phase（`api/commissioning.py:1185`）、adhoc（:1377）、run-all（:1579）**都**经 `run_base_station_execution_session`。CE 没有自己的会话：租约是 BS 会话开的 `instrument_test_lease(...)`（`base_station_execution_session.py:104`），CE 靠 `control_f64: bool = True` 的默认值（`instrument_test_lease.py:362 / :642`）被捎上；CE 的 load / configure / run / safe-idle 是 MeasureExecutor 里的内联语句流，收尾在 `services/mimo_ota/cleanup.py:171-176` 的 `stop_emulation()`。① 的 `freeze_execution_channel_emulator_binding` 两处写方（`commissioning.py:1722`、`test_case_runner.py:288`）**无读方**；`_freeze_instrument_lease`（`commissioning.py:1701`）的校验只装 baseStation / positioner。
另两类不在条目的「四类」里、各写一份：手工 CE 端点（`api/instrument.py:4524 load-smu` 起 6 个，经 `_call_f64_method` :4355 / `_exclusive_f64_control_operation` :4419，`getattr(driver, "load_local_scenario", None)` :4550 取 F64 专属方法名）；诊断序列（`api/diagnostic_sequence.py:212` 自开租约，序列体各写收尾）。

### 2.3 可取材的结构
`ResolvedChannelEmulatorBinding`（含 `manifest` / `expected_driver_module` / `expected_driver_name` / `expected_transport` / `binding_digest` / `runtime_driver`）；`ChannelEmulatorManifest`（`load_modes` / `operations`，各带 support + reason + source_reference）；`ResolvedChannelAsset`（`services/mimo_ota/channel_asset_resolver.py:53`，frozen：`engine_mode` / `emulation_file` / …）。BS 侧四件：`_EXECUTION_PLAN_DIMENSIONS`（:903）/ `BaseStationExecutionPlanItem`（:916，禁当 bool）/ `BaseStationExecutionPlan`（:951，`as_payload` + digest）/ `resolve_base_station_execution_plan`（:1025）；证据落点 `services/execution_scpi_evidence.py:294`；测试 `tests/test_p2_50_execution_plan.py`（22 例）。CE 驱动基类 `ChannelEmulatorDriver`（`app/hal/channel_emulator.py:102`）。

## 3. 参照物与有意差别
镜像 P2-50：plan = 纯函数从（manifest, binding, resolved asset）派生、frozen、canonical payload、digest 进证据、执行期 digest 漂移 → FAILED。
有意差别：a) BS plan 只冻「四维能力」；CE plan 还要冻 **load mode**（asset 的 `engine_mode` ↔ manifest `load_modes` 的 support）与**阶段顺序**（字面常量元组，不是运行时算出来的）；b) CE 有 ① 的 binding 冻结件在先，plan 只引用 `binding_digest`，不重复其字段；c) BS 的 planned 判据替代的是 adapter 声明，CE 替代的是 `hasattr` —— 每切一处消费方都要配「不支持 → 不静默跳过」（沿用 P2-57 门 `test_capability_checks_in_measure_have_no_silent_negative_path` 的口径）。

## 4. 切片（各 1 PR，WIP = 1）
### ① ChannelEmulatorExecutionPlan（本稿求批的这一片）
- **可观察故障**：CE 能力 / load mode 在执行期没有冻结件可对照；① 的 binding 冻结件零读方。
- **做**：新文件 `app/hal/channel_emulator_execution_plan.py`：`ChannelEmulatorExecutionPlanItem` / `ChannelEmulatorExecutionPlan`（frozen；字段 `adapter_id`、`load_mode`、`operations`（14 个操作各一项：planned / capability_source / reason）、`phase_order`（字面元组 acquire → identity → load → configure → run → safe_idle → release → terminal）、`binding_digest`、`asset_engine_mode`）、`resolve_channel_emulator_execution_plan(manifest, binding, resolved_asset)`（零 I/O；asset 要的 load mode 不被 manifest 支持 → 计划期 ValueError，把 `measure.py:1781` 的运行时 `get_supported_load_modes()` 判定**前移到计划期**）。冻结：`freeze_execution_channel_emulator_plan` 与 `CE_FREEZE_CONFIG_KEY` 同处落 execution.config，接上同两处写方。证据：镜像 `execution_scpi_evidence.py:294`，加 `channel_emulator_execution_plan` payload + digest。**首个消费方**：MeasureExecutor 已 manifest 化的 3 个操作改读 `plan.planned(op)`，并在 I/O 前做 digest 漂移检测（镜像 :998）；其余 `hasattr` 站点本片**不动**（② 做）。
- **门**（每条配变异）：canonical payload 稳定 —— 打乱 manifest 元组顺序 digest 不变（变异：删排序 → 红）；load mode 不支持 → 计划期 ValueError（变异：去判定 → 红）；冻结 → 读回相等且二次调用不再解析（变异：写方漏字段 → 红）；执行期漂移 → FAILED 且**零 SCPI**（变异：删漂移检测 → 红，spy 计 SCPI 次数）；3 个消费站点改读 plan 后 P2-57 的「无静默负路径」门仍绿；plan / item 禁当 bool（镜像 BS）。
- **爆炸半径**：加法；最坏 Y = 计划期误判 load mode 不支持 → FAILED 而非误跑。≤ X。
- **预估**：新 1 源文件 + 改 `channel_emulator_binding.py` / `execution_scpi_evidence.py` / `measure.py`（3 站点）/ `commissioning.py` 与 `test_case_runner.py`（各 1 行）+ openapi（若证据 schema 外露）+ 1 个门文件。
### ③ 单一会话（建议排第二）
- **可观察故障**：CE 生命周期由 BS 会话的租约默认值捎带；冻结件复用不对照当前 HAL（Discovered `[discovered 2026-09-03 during P2-58 ① 内审 F1]`）；`emulator is None` 时执行器自造 Mock 绕过 HAL / 租约（:1647）。
- **做**：在 `run_base_station_execution_session` 内嵌 `channel_emulator_execution_scope(plan, binding, hal, execution)`（**一处插入覆盖四类入口**）：identity（frozen binding 的 `expected_driver_*` / transport / simulated 对照 live `hal`，零 I/O，镜像 BS 的 `validate_frozen_base_station_before_remote`）→ yield → safe idle（沿用 `stop_emulation`，不新增 SCPI）→ terminal evidence（release 结果落盘）。删 :1647 的自造 Mock（HAL 无 CE → 按 binding 的 `execution_mode` 决定 simulated 还是 FAILED）。
### ② measure.py 去 F64（最大，排最后）
16 行探测 → `plan.planned`；`_loaded_emulation_file` → 驱动公开回读；`_TOPOLOGY_ESCAPE_HINT` import → manifest reason；`build_p0_5_command_evidence` 探测 → 在 `ChannelEmulatorDriver` 基类上声明的协议方法（Mock 也实现）。需先扩 manifest 词汇（§6 Q2）。`f64_*` 六字段与 `f64.*` 证据键**改名不在此片**（契约破坏面：openapi / GUI / 报告 / 测试）。

## 5. Discovered 候选（越界，不做）
手工 CE 端点 6 个各开租约、走 `getattr` 取 F64 专属方法名；诊断序列各写收尾；`f64_*` 配置字段与 `f64.*` 证据键命名；`get_supported_load_modes()` 运行时能力与 manifest `load_modes` 双真值。

## 6. 拍板记录（原问题保留）
> **2026-09-04 用户：「按你的建议来」** —— Q1 ① → ③ → ②；Q2 分两类（仪器操作进 manifest，证据构造 / 拓扑 getter 改基类协议必实现方法）；Q3 `f64_*` 六字段与 `f64.*` 证据键本 P2-59 不改名、另立片；Q4 手工端点与诊断序列不在 P2-59、登记 Discovered；Q5 CE 作用域嵌在 BS 会话内（一处插入）。

- **Q1 切片顺序**：① → ③ → ②？（建议：③ 让 ① 的冻结件立刻有执行期消费方，顺手关掉 ① 内审 F1 那条 Discovered；② 是长尾。）
- **Q2 manifest 词汇**：把 14 个操作扩到覆盖 23 个探测名（每个 F64 条目的 `source_reference` 只能写「驱动源码 / 现场实测」），还是分两类 —— 仪器操作进 manifest；证据构造 / 拓扑 getter 改成基类协议必实现方法（不进 manifest，`hasattr` 归零）。建议：分两类。
- **Q3 `f64_*` 六字段与 `f64.*` 证据键**：P2-59 不改名（消费方经 plan 判能力即可），改名另立片。同意？
- **Q4 手工端点与诊断序列**：不在 P2-59（条目写的是四类入口），登记 Discovered。同意？
- **Q5 会话形态**：嵌在 BS 会话内（一处插入）vs 独立 CE 会话（四处插入）。建议：嵌套。

## 7. 明确不做
不改任何 SCPI 命令形式与下发顺序；不改 `f64_*` 契约字段；不碰手工端点 / 诊断序列；不引入第三型号分支；不改 P2-57 的 14 操作语义（只可能在 ② 里扩充）。

## 8. 补遗（① 落地时所得，2026-09-04）

### 8.A 计划的来源 = MEASURE 将要用的那个驱动，不是 binding 的目录 manifest
§4 ① 原写「从（manifest, binding, resolved asset）派生」，落地时把 manifest 的来源定死为**当下 HAL 装载的 CE 驱动**，
HAL 里没有就按 `measure.py` 既有兜底规则取 `MockChannelEmulator` 的类级 manifest（`services/channel_emulator_execution_plan.py::channel_emulator_for_execution_plan`，
冻结与 MEASURE 共用）。理由：① 这正是 BS 的做法（`execution_scpi_evidence.py:294` 从 live driver 推导、`measure.py` 重算对账）；② mock 模式下
binding.manifest 是所选真型号的声明而 MEASURE 跑的是 mock —— 用目录 manifest 会让 mock 运行按 FS16 的「全不支持」被拒，那是行为变化不是冻结；
③ 同一驱动 → 同一答案，所以 P2-57 已 manifest 化的 3 个站点改读计划后答案逐字不变。副产物：冻结与测量之间换驱动被 digest 抓住 ——
这是 `[discovered 2026-09-03 during P2-58 ① 内审 F1]` 那条的一半（逐字段身份对照仍留给 ③）。

### 8.B engine_mode 与 MEASURE 同源
冻结时的 engine_mode 取自 `load_mimo_ota_config(execution)`（基站冻结件里的 MIMO OTA 配置快照优先，否则 TestCase 行）+ `resolve_channel_asset`
覆盖 —— 与 MEASURE 逐行同源（`measure.py` 的 `config.engine_mode = resolved_asset.engine_mode`）。resolver 的最终答案与来源另存为
`channel_emulator_load_request_freeze`，并绑定基站冻结件里**原始稀疏** MIMO payload 的摘要和 CE plan digest；后续证据投影不得查询
current asset，也不得用显式 asset 覆盖前的 stale `mimo_ota_configuration.engine_mode` 重算。初版从 `test_case.configuration` 直接解析，
端到端夹具立刻实证了「两边读不同源就自漂」（用例在建上下文后改了配置，对账把它判成漂移）。写方顺序因此固定为 BS 冻结 → CE binding → CE load request + plan。

### 8.C 对账位置 = 首次 CE I/O 之前，不是取到驱动之后
初版放在 `emulator = hal.drivers.get(...)` 之后、路损门之前，`test_mimo_ota_precheck_cal_gate.py` 7 个与 CE 无关的前置门被「计划缺席」顶掉。
挪到 RF 冷启动块、造兜底 mock 之前（其后紧接加载 = 第一处 CE I/O）。门 `test_measure_no_longer_queries_driver_capability_directly_and_reconciles_before_first_ce_use`
钉住三处相对顺序：路损门 < 对账 < 兜底 mock 创建 < 首处消费。

### 8.D 有意收窄：本片不进 evidence
§4 ① 原写「镜像 `execution_scpi_evidence.py:294` 加 payload + digest」。落地不做：CE 冻结件家族在 `execution.config`（P2-58 ① 先例），
`BaseStationExecutionEvidence` 是 BS 命名的契约模型且带 parse 兼容门；CE 的 terminal evidence 形态由 ③ 一并定。MEASURE 对账读 config，不读 evidence。

### 8.E 建会话处也冻
`_freeze_instrument_lease` 有 **4** 个调用点（Explore 列了 3 个漏了 `POST /sessions` 的 :1062）；计划冻结接在它里面，所以建会话、run-phase、
adhoc、run-all 四处同刻冻。`test_commissioning_smoke.py::_create_fast_session` 绕过端点自己复刻三个冻结，须同步加第四个（① 时同样在这里加过 binding）。

### 8.F 夹具影响（端到端）
执行行要带三个同刻键（binding 冻结件至少含 `binding_digest`；resolver-owned load request 投影冻结有效 engine/load 来源并引用 plan digest；计划用同一服务函数冻）；无 manifest 的裸 CE 替身冻不出加载模式（P2-57 fail-closed）→ 借 mock 的 manifest 换 adapter_id；
用例在建上下文后改配置要重冻（`_refreeze_ce_plan`）；夹具冻不出计划时不冻（如故意给退役资产，让 MEASURE 走它自己更早的门）。

### 8.G 行为变化清单（三处，全部 fail-closed 方向）
1. 加载模式不被将要用的驱动支持：MEASURE 期 `FAILED` → 启动期 `CaseNotExecutable` / 422（§4 ① 已批）。
2. 无 manifest 的 CE 驱动：此前一路按「不支持」跑到加载；现在启动期拒。生产驱动都有 manifest（P2-57 构建期门），只影响测试替身。
3. 冻结与测量之间换驱动 / 换 engine_mode：此前零检测；现在 I/O 前 RuntimeError。
其余：同一驱动上 3 个已 manifest 化站点的答案逐字不变；其余 13 行 `hasattr` 探测本片不动（②）。

### 8.H ③ 的单点插入与阶段所有权（2026-09-04）
③ 不在 formal、run-phase、adhoc、run-all 四处各复制一份生命周期；四条活路径已经共同经过
`run_base_station_execution_session`，所以该函数改为进入统一的
`channel_emulator_execution_scope(plan, binding, hal, execution)`。scope 内部继续复用
`instrument_test_lease` 的同一把 HAL 协调锁与 Remote/Local 交接，不另造第二把锁，也不改手工 CE
端点和诊断序列。阶段固定为：锁内严格路损资格纯检查 → 冻结件结构/摘要校验 → 锁内 live identity 与 plan 对账 →
BaseStation Remote acquire → CE Remote acquire（最后取得）→ 业务 yield → terminal safe idle →
Local release → terminal evidence。safe idle 位于租约 yield 的
`finally`，因此严格早于 Local release；terminal evidence 位于租约退出之后，因而读取的是实际 release
结果，不是预期值。MEASURE 既有 `cleanup_chamber_instruments` 在 scope 持有 CE safe-idle 所有权时只收尾
BaseStation 与转台，不再第二次调用 `stop_emulation`；离开统一 scope 的旧调用仍保留原有 CE 尽力停机。
成功、异常、取消三条 session 路径都只允许一次 GOS，不能假设厂商驱动对重复停止幂等。

scope 组合现有 BaseStation `validate_before_remote` 与 CE 校验器，并原样转发前者的
`validation_identity` / `lease_audit_context`，避免破坏嵌套租约和 P2-67 公共审计。CE 校验器在
`instrument_test_lease` 已持协调锁、但尚未 clear cache / acquire Remote 的位置执行；因此任何 binding、
plan、驱动或连接漂移均在首个 CE I/O 前 fail-loud。租约赢锁并完成 acquire 后，scope 把该刻的
完整 HAL 视图与实际 CE driver 固定到当前 execution task；业务体后续再次读取 `get_hal_service()`
也不会随 force reload 切到 replacement，模拟 driver 同样不会被新加载的真实 CE 覆盖。

严格路损门复用 MEASURE 的同一纯 evaluator，并在同一协调锁内、任何 BaseStation/CE/转台 I/O
之前执行；MEASURE 内保留防御性复核及既有 `path_loss_application` 失败载荷。顺序恒为“路损门 →
CE 对账 → 首个仪器 I/O”，避免 PRECHECK/REFERENCE 先触碰硬件后才在 MEASURE 拒绝证书。

### 8.I ③ 的冻结身份与受控模拟边界
P2-58 的 binding 冻结件补入 `execution_mode`；它进入冻结件外层 digest，已存在但缺该字段的旧冻结件
不从当前数据库回填，进入③会被判为不完整/legacy，不能继续正式硬件执行。真机模式逐字段核对：
`expected_driver_module`、`expected_driver_name`、`expected_driver_connection`、冻结 binding digest、计划引用的
binding digest、计划 digest，以及 live driver 的 manifest 派生计划。任一不一致均零 CE I/O 拒绝。

模拟模式只认 `instrument_hal_service.is_mock_driver()` 的权威白名单和 Mock CE 的 manifest，不靠类名前缀。
HAL 仍有 mock 时直接对账；HAL 缺 CE 时，只有冻结 `execution_mode == simulated` 才由 scope 在当前
execution task 的 HAL view 中临时覆盖 `MockChannelEmulator`，进程级 `hal.drivers` 始终不变，并发
readiness / preview / freeze 请求仍看到真实的“CE 未加载”。真机冻结遇到 HAL 缺 CE 必须 fail-loud；执行器
`measure.py` 不再就地构造 Mock。模拟 acquire/release 明确记 `not_applicable`，绝不伪造 true，且整个
execution 的正式 outcome 被降为 diagnostic，数值不得进入正式 KPI。

### 8.J ③ 的终态证据与四向状态表
终态写入 `TestExecution.config.channel_emulator_terminal_evidence`，每次 scope 追加一条不可变、带 canonical
digest 的记录；同一 `session_id` 幂等复用，冲突内容拒绝覆盖。记录绑定 execution id、scope session id、
租约 id（若已取得）、binding/plan digest、execution mode、adapter/runtime identity、Remote acquire、
safe idle、Local release、业务终态与错误。P2-66 outcome 只读这些冻结/终态记录，不查 current HAL、目录、
LabProfile 或连接。binding 与 terminal 都先按 `schema_version=1`、`extra=forbid` 的不可变模型完整
解析，再核 canonical digest；非法 execution mode、空成功态 session/lease/instrument 身份、成功位与
错误字段矛盾均 fail-closed，重新计算摘要不能把畸形字段洗成正式证据。P2-66 还必须从 binding 的
冻结身份与 resolver-owned load request 投影纯重建权威计划，再用共同 verifier 对账：configured real 消费
binding manifest，simulated/diagnostic-unbound 消费固定权威 Mock manifest；现代 binding 的 source 固定为启动
冻结时已加载的 `hal`。load request 同时冻结原始 MIMO 配置摘要、是否由 ChannelAsset 覆盖、asset id/source_type、
最终 engine/load 与 plan digest；显式 asset 时按冻结 source_type 重算 engine/load，无 asset 时才要求 engine 与冻结
MIMO 字段一致。P2-66 不查 current asset，也不能借待验证 plan 自己的 source/load-mode 自证。相同 binding digest
不能让另一 adapter、fallback source 或另一加载模式的合法 plan 混入。

| 业务方向 | safe idle | release | terminal state | 正式性 |
|---|---|---|---|---|
| 成功 | 普通链必须 `stop_emulation is True`；直通链必须在最后一次 STATIC 写之后 `clear_passthrough_mode is True` | 真机必须确认；模拟为 `not_applicable` | `completed` | 仅真机完整证据可正式 |
| 设备拒绝/业务失败 | 仍执行 | 仍执行 | `failed` | 不正式 |
| 异常 | 仍执行；失败与原异常并列留痕 | 仍执行 | `failed` | 不正式 |
| 取消 | 仍执行；不得因取消跳过 | 仍执行 | `cancelled` | 不正式 |

取消命中 safe idle 或任一 Local release 时，安全动作在独立 task 中继续到真实完成/失败；调用 task
只延迟传播 `CancelledError`，不得用 `shield` 后立即进入下一阶段。SAFE_IDLE 与 release 始终使用租约
进入时实际 acquire 的同一 driver 引用，HAL force reload 不能把新旧实例拼成一条完整生命周期。

safe idle 只调用计划声明的既有动作：普通链为 `stop_emulation`；直通链前置 stop 后进入 STATIC，
终态改用既有 `clear_passthrough_mode`，并把 action 写入 terminal，前置 stop 不能冒充终态确认。计划未声明、
方法缺失、返回 False 或抛异常都不能写成 confirmed。驱动协程自身抛 `CancelledError` 但调用 task 未被
取消时按 safe-idle failed 记录，不能伪装成操作员取消。若直通 attach 后继续启动衰落，必须在
`start_emulation` 前把终态 action 保守切回 `stop_emulation`；启动返回 False、抛异常、被取消或部分生效
都在 release 前执行 GOS，不能用较早的 clear-passthrough 证明最终安全。若业务本身已失败，收尾失败不得被吞；聚合错误同时保留原业务异常和收尾失败。若 terminal
evidence 落库失败，成功链必须失败；异常/取消链先回滚业务事务，再用同一会话的新事务追加 terminal，
避免 terminal 的 commit 顺带提交半成品测量。落库自身再失败时仍保留原异常/取消，但把落库失败作为明确
并列失败附在原异常上，不能只写日志后静默丢失。

### 8.K ③ 的明确边界
③ 不清理剩余 13 个 `hasattr/getattr` 能力探测（② 负责），不改 `f64_*` / `f64.*` 键，不触碰手工 CE
端点或诊断序列，不新增状态查询或任何 SCPI，也不改变现有 provenance 白名单。`stop_emulation` 的既有
厂商语义、错误队列与回读仍完全由驱动实现负责；共同 scope 只消费其布尔确认。

### 8.L load request / plan 的原子冻结与独立资产身份
`channel_emulator_load_request_freeze` 与 `channel_emulator_execution_plan_freeze` 是同一个启动决定的两个
不可拆分投影：二者都不存在时才允许一次性解析并创建；二者都存在时只校验和复用；任一单边存在都视为
现代冻结链损坏，启动期 fail-closed，不能查询 current ChannelAsset 把孤儿冻结件“修好”。已有执行进度或
已完成历史同样不回填，只能按既有历史策略审计降级。

显式 `channel_asset_id` 的来源不能由 load request 自证。BaseStation 冻结时由 resolver 同刻产生独立的
`channel_asset_resolution`（asset id + source type + 自身 digest），并把它纳入 BaseStation 外层 canonical
digest；随后 load request 只从这份独立身份派生有效 engine/load，plan 再引用 load request 的确定性结果。
因此把 `standard_3gpp` 成组改成 `vendor_file`，即使同步重算 request/plan/terminal 的所有内部摘要，也会与
独立冻结身份冲突。无显式 asset 时则禁止出现该身份，effective engine 必须与冻结 MIMO 配置一致。

统一 scope 的锁内、零 I/O validator 必须先完整验证 BaseStation 外层摘要、独立 asset 身份、原始稀疏 MIMO
摘要、load request 摘要、request→plan digest 及 scope 参数中的 plan 完全一致，再从 request 的权威
`requested_load_mode` 与 binding 的权威 source 规则重建 live plan。任何缺件、孤儿、坏摘要、资产来源漂移或
plan 自证换档，都在 BaseStation / CE / 转台首次 I/O 前拒绝；P2-66 复用同一纯校验器，不查询 current asset。

### 8.M ② 补遗：MEASURE 去 F64 运行时探测（2026-09-04，Q2 已批准）

#### ⓪ 动手前四行
- **搜索命中**：`measure.py` 的 CE 对象上仍有 16 个运行时探测站点：动态拓扑 getter 1 处、`ensure_topology` 2 处、`build_p0_5_command_evidence` 4 处、中心频率 1 处、输出增益 2 处、输出电平 1 处、crest factor 1 处、input measurement 1 处、7 个闭环方法聚合探测 1 处、active input ports 1 处；另有 `_loaded_emulation_file` 私有缓存 1 处、`_TOPOLOGY_ESCAPE_HINT` 私有常量 import/消费 2 处、load mode 运行时查询 1 处。`get_supported_load_modes()` 的生产方只有 `ChannelEmulatorDriver`；消费方为 `ChannelEmulatorDriver.load_channel` 的 HAL 防御门、`NativeModelStrategy`、`B2ParametricTdlStrategy` 与 `MeasureExecutor`。
- **必要性**：同一执行已经冻结 `ChannelEmulatorExecutionPlan`，MEASURE 仍可用 Python 对象形状、F64 私有实现和可变 live manifest 改选路径；换驱动或漏方法时可能静默降级，也可能在硬件 I/O 后才以 `AttributeError` 失败。
- **范围**：仪器操作进入 manifest 并逐型号显式声明；证据构造、拓扑 getter 与已加载模型 getter成为 `ChannelEmulatorDriver` 明确协议。MEASURE 和两种生成策略只消费冻结 plan；HAL 的 `load_channel` 仍保留由同一 manifest 派生的本地防御门，不成为执行路径的第二判据。
- **爆炸半径**：F64 在既有源码已实现的操作上答案不变；FS16 与 Mock 对未实现操作显式 `not_implemented`，负路径保留既有 diagnostic 或更早 fail-loud。不得改六个 `f64_*` 字段、`f64.*` 证据键、手工端点、诊断序列、provenance 白名单，也不得在 `MeasureExecutor` 的 `emulator is None` 自造 Mock 段及 session/safe-idle/release 证据上施工。

#### 机械全集与归属

| 现有站点 | 真值归属 | ② 的替换形态 |
|---|---|---|
| `getattr(emulator, getter_name)`，消费 `get_active_output_count/get_active_input_count/get_active_output_ports` | 基类协议 | 直接调用必实现 getter；异常/协程保持既有 unknown 处理 |
| `getattr(emulator, "_loaded_emulation_file")` | 基类协议 | `get_loaded_emulation_file()`；Measure 不再读私有缓存 |
| `getattr(..., "ensure_topology")` ×2 | manifest 操作 | `plan.planned("ensure_topology")` 后直接调用；不支持时保留原 diagnostic |
| `hasattr(..., "build_p0_5_command_evidence")` ×4 | 基类协议 | 无条件调用；不适用驱动明确返回 `None`，回读仍 unknown/simulated |
| `hasattr(..., "get_center_frequency_mhz")` | manifest 操作 | plan 决定是否读取，直接调用协议方法 |
| `hasattr(..., "set_output_gain")` ×2 | manifest 操作 | plan 决定走 gain 或既有 diagnostic |
| `hasattr(..., "set_output_level_dbm")` | manifest 操作 | 不支持时 fail-loud，不再靠对象形状 |
| `hasattr(..., "set_crest_factor")` | manifest 操作 | 不支持时保留既有 skip warning |
| `hasattr(..., "measure_input")` | manifest 操作 | 不支持时保留既有 skip warning |
| `hasattr` 探 `autoset_inputs/measure_input/get_input_level_limits/set_input_measurement_mode/set_burst_trigger_level/get_group_clipping/get_system_status` | manifest 操作 | 七项全部读取 frozen plan；缺任一项沿用 diagnostic skip |
| `getattr(..., "get_active_input_ports")` | 基类协议 + `ensure_topology` 计划 | getter 直接调用；只有计划声明拓扑读取却无数据才 fail-loud，未声明驱动保留既有确定性 fallback |
| `_TOPOLOGY_ESCAPE_HINT` import + 2 个消费点 | manifest reason | 使用冻结 `ensure_topology` / 对应操作 item 的 reason，不跨层 import F64 私有常量 |
| `MeasureExecutor` / Native GCM / B2 的 `get_supported_load_modes()` | frozen plan | `load_mode_planned`；不支持在 I/O 前拒绝 |
| `ChannelEmulatorDriver.load_channel()` 的同名消费 | HAL 本地防御 | 保留：它只从类 manifest 派生，且执行前已有 digest 对账；非执行调用仍须自守 |

#### manifest 与协议边界
- 新增操作词汇：`ensure_topology`、`get_center_frequency_mhz`、`set_output_gain`、`set_output_level_dbm`、`set_crest_factor`、`measure_input`、`autoset_inputs`、`get_input_level_limits`、`set_input_measurement_mode`、`set_burst_trigger_level`、`get_group_clipping`、`get_system_status`。F64 只能引用现有 `propsim_f64.py::<method>` 与既有现场问题记录，绝不补写或猜测 SCPI；FS16/Mock 逐项声明 `not_implemented`。
- 基类协议方法：`build_p0_5_command_evidence`、`get_loaded_emulation_file`、`get_active_output_count`、`get_active_input_count`、`get_active_output_ports`、`get_active_input_ports`。F64 暴露既有真值；FS16/Mock 明确返回 `None`，所以不会凭空产生回读或正式证据。
- `ensure_topology` 既是会触发仪器 I/O 的 manifest 操作，也是判断「该型号承诺可取得拓扑」的唯一能力来源；getter 本身不再拿对象形状当能力宣言。
- Mock 不声明上述仪器操作可用；下发侧不另写命令语义，已有真实 builder 的调用关系保持不变；回读与证据仍为 simulated/unknown。

### 8.I ② 集成补遗：计划词汇必须版本化（2026-09-04）

① 已发布的 `schema_version=1` 冻结件固定覆盖原始 14 个操作。② 把 manifest 操作扩为 26 个后，若让
v1 的校验器读取当前全局元组，旧执行会在部署后无任何数据变化的情况下变成「结构损坏」，并可能让
P2-66 的历史终态/报告随软件版本漂移。这是功能 P1，不是迁移便利性问题。

- `CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS` 与
  `CHANNEL_EMULATOR_EXECUTION_PLAN_V1_OPERATIONS` 都永久固定为原 14 项；manifest/plan 的 v2
  词汇固定为本片 26 项。旧 `resolved_binding.manifest` 必须按自身 schema 解析，不能借当前全集重解释。
- 新冻结件写 `schema_version=2`，按 26 项生成。parser 按冻结件自己的版本选词汇，并对**原始 payload**
  （排除 `digest` 字段）复算摘要；不得把 v1 补齐成 v2 再重算，也不得重写旧冻结件。
- 历史/terminal/P2-66 投影不直接解释新 12 项；它们只审计当时冻结的 v1 语义，因此合法 v1 仍合法。
- 新 MEASURE 路径会消费新操作。未开始/待执行却携带 v1 的执行必须 fail-closed，并明确提示重建执行，
  不能拿 live v2 覆盖；已经完成的 v1 只读历史不受影响。

机械消费方：直接 parser/validator 只有 `services/channel_emulator_execution_plan.py` 的 validate/freeze/verify
与 `MeasureExecutor._channel_emulator_plan_context`；`test_case_runner` 和四类 commissioning 入口只写冻结件。
P2-66 `execution_evidence_outcome.py`、报告 terminal/history API 不直接解析此键，只通过既有冻结执行事实
投影，所以本片不得把新词汇反向注入它们。
