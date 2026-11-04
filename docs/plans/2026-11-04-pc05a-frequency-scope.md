# PC-05A 单频校准适用范围实施计划

> 执行方式：使用 executing-plans，按现有校准总设计与用户连续开发授权推进，WIP=1。

**目标：** 未声明并验证插值域的单频记录不再因落在目标频率 ±5% 内而被采用。

**架构：** 收窄现有选择器，不引入第二套校准引擎。当前单频记录只证明记录频点；返回形状、模式优先级、真实性、有效期判据保持现有契约。历史冻结只读，不迁移或重算旧结果。

**技术栈：** Python、SQLAlchemy、pytest；隔离 SQLite，不连接仪器。

## 范围与验收关系

| 生产入口 | 修改位置 | 验收 |
|---|---|---|
| 路损 API、readiness、预检和普通补偿 | path_loss_calibration_service.resolve_latest_calibration | 精确频点可选；新近邻不遮住旧精确值；仅近邻返回 frequency_mismatch |
| 执行创建逐链冻结 | mimo_ota/route_calibration_freeze.resolve_effective_route_compensation | 近邻不进入 route_entries；旧冻结读取不变 |
| 上下行链路增益 | path_loss_calibration_service.get_latest_uplink/downlink_calibration | 两方向均精确匹配；未指定频率仍可查询最新档案 |
| 方向图校准所用路损证书 | probe_calibration_service 的证书查询 | 同一单频限制，保留原链身份与实测来源检查 |

已枚举调用方：calibration_orchestrator、api/path_loss_calibration、path_loss_preflight、逐链冻结、方向图校准。多频插值、探头方向图本身的频率选择不是单频路损证书，不借本片改写；它们仍属后续 PC-05A 范围。精确中心频率不代表宽带覆盖。

## 实施步骤

1. 基线运行 test_path_loss_mode_filter；新增近邻拒绝、精确优先、上下行对称和执行冻结用例，确认旧行为失败。
2. 将六处 ±5% 查询/原因分类收窄为记录频率等于目标频率；更新紧邻注释，不改原始记录。
3. 跑单频、冻结、预检、方向图相关回归；修复本片造成的问题。核心反例即旧行为变异证明。
4. 稳定输入后运行后端全量，逐项归因失败；历史三门不得称全绿。独立内审后提交 PR，按当前 R1/R2 规则交付。

## 前置与边界

memory 已查询；NotebookLM 不适用：零 SCPI/仪器语义变更，范围约束来自已批准总设计 §5.3。当前单频模型没有可验证插值域，因此不新增容差或假造不确定度。此片不关闭 PC-05 父项、PC-05B 或其余校准范围。

## 验证记录

基准 main `8e2ba32a`，隔离工作树 `codex/pc05a-frequency-scope`。Python 3.13.7、pytest 9.0.1；复用主目录虚拟环境，只从工作树导入代码。所有测试显式 `USE_MOCK_INSTRUMENTS=true`、`DATABASE_URL=sqlite:////tmp/pc05-*.db`；不使用运行数据库。

- 基线：`python -m pytest tests/test_path_loss_mode_filter.py -q --color=no`，6 passed / 59 warnings / 0.38s，exit0。
- RED：新增7反例同命令，7 failed / 6 passed / 83 warnings / 0.73s，exit1。
- GREEN：同命令修后13 passed / 85 warnings / 0.70s，exit0。
- 相关回归：仓库根 `PYTHONPATH=api-service python -m pytest api-service/tests/test_path_loss_mode_filter.py api-service/tests/test_path_loss_calibration.py api-service/tests/test_pc04a2_route_freeze.py api-service/tests/test_pc04a2_route_compensation.py api-service/tests/test_p1_62_path_loss_application_truth.py api-service/tests/test_p2_32b_pattern_real_activation.py -q --color=no`，169 passed / 828 warnings / 74.29s，exit0。
- 首轮全量发现两条旧预检测试要求±5%通过，主动中断：2 failed / 2253 passed / 4 skipped / 2823 warnings / 119.45s，exit2。不是最终验收。全仓同类检索又发现历史追溯fixture依赖旧近邻创建，改为显式构造旧策略冻结，保留原频点差异断言。
- 补充回归：仓库根 `PYTHONPATH=api-service python -m pytest api-service/tests/test_mimo_ota_precheck_cal_gate.py api-service/tests/test_pc07a1_calibration_traceability.py -q --color=no --log-cli-level=WARNING`，69 passed / 921 warnings / 70.34s，exit0。
- 最终全量：api-service 目录 `DATABASE_URL=sqlite:////tmp/pc05-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. /Users/Simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`，8538 collected；**8 failed / 8513 passed / 17 skipped / 10361 warnings / 1120.40s**，exit1。不是全绿。
- 全量前后1419项非docs tracked输入hash一致（清单SHA256 `d32a345e85503cc88535a678cc8fc9e497081ad9aa2bcc7e11699162d3fd2967`）；原始日志 `/tmp/pc05-full.log` SHA256 `84ab8b6ced36aaecb2ea712fce52759c72376213a121a0671179fd9fc5dd1e5d`。结束后只有文档记录变化。

### 全量失败逐项归因

以下六项在未改 main `8e2ba32a`、同Python环境、隔离SQLite下独立重跑同样失败；没有修改它们或契约镜像来消红：

| 测试 | 本轮与main同样失败原因 |
|---|---|
| test_pc04a2_gui_contract.py::test_topology_calibration_public_schemas_and_routes_match_live_openapi | live缺少FixedRouteRequest名称 |
| test_pc04a4a_nominal_properties.py::test_checked_crud_and_schema_closure_match_live_contract | ValidationError字段镜像差异 |
| test_pc06a1_batch_api.py::test_batch_contract_models_live_and_handwritten_openapi_agree | batch契约镜像差异 |
| test_pc_04a_fixed_route_api.py::test_live_checked_openapi_and_generated_types_cover_all_pc04_routes | live缺少FixedRouteRequest名称 |
| test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes | PC07A1历史验证记录中的执行路径 |
| test_rule_gates.py::test_g11_docs_cite_live_api_routes_full_domain | 两份历史验收记录的ws路径 |

基线命令均在主目录api-service执行：`DATABASE_URL=sqlite:////tmp/pc05-contract-baseline.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest <上表nodeid> -q --color=no`（前两组诊断加`--tb=long`，其余`--tb=short`；历史门使用`/tmp/pc05-gates-baseline.db`且同时带`test_gitignore_does_not_shadow_tracked_sources`）。各契约定点分别1 failed/39 warnings/1.57s、1 failed/40 warnings/1.71s、1 failed+1 passed/39 warnings/2.27s（同时运行GUI服务测试）、1 failed/39 warnings/1.68s；历史门2 failed+1 passed/40 warnings/1.67s。均exit1。旧记录中的第三项gitignore门本机已通过，不沿用旧失败计数。

剩余两项为隔离目录缺依赖入口：`test_pc04a5b_revision_migration.py::test_fresh_alembic_head`找不到本地`.venv/bin/alembic`；`test_pc06a1_batch_api.py::test_gui_batch_service_defaults_identity_and_idempotency`找不到typescript。补上指向主目录同一现有环境的`.venv`与`gui/node_modules`链接（不安装/改依赖、不提交链接）后，迁移模块2 passed/39 warnings/0.81s、GUI服务单项1 passed/39 warnings/0.25s，均exit0。命令分别在api-service运行`python -m pytest tests/test_pc04a5b_revision_migration.py -q --color=no`及根目录`PYTHONPATH=api-service python -m pytest api-service/tests/test_pc06a1_batch_api.py::test_gui_batch_service_defaults_identity_and_idempotency -q --color=no`，同样显式Mock与各自/tmp SQLite。

未重跑整套以改写原8失败统计；保留全量失败与局部恢复两份事实。没有新增未知失败，未证明现场硬件行为。

2026-11-04本机运行库只读盘点：`probe_path_loss_calibrations`、`rf_chain_calibrations`、`route_calibration_applications`均0行。此事实只适用于本机；不替代其他实验室存量盘点。未修改数据库、历史冻结或原始记录。

独立内审已检查生产查询入口，未发现功能缺陷；两处旧“最接近”接口说明已修正。新增预检/历史fixture和文档增量独立复核CLEAN；最终验证记录另交审查者核验。


## R1 功能缺口与修复

GitHub R1（review 5764583210，inline 4464693210，审查be47454a）指出：近邻增益被拒绝后，`get_compensation_factors`仍以0代替缺失UL/DL证据，补偿消费者仅检查路损，导致TRP/TIS仍返回有效数值。主代理和首轮内审都漏查了这个None消费结果。

修法为去掉零兜底并收窄有效条件：已配置LNA/PA而没有适用增益时保留None；未配置对应硬件保持无需增益补偿的0；真实精确频点0 dB不被当作缺失。总量、getter、apply接口、批量TRP/积分、summary同源传播不可用，不改公式。修改文件为`calibration_orchestrator.py`、`measurement_compensation.py`及`test_path_loss_calibration.py`。

16个真实DB/HTTP场景覆盖missing/nearby/mock/unknown/expired/zero/exact/not_required×UL/DL。RED：10 failed / 6 passed / 37 deselected / 205 warnings / 1.21s，exit1；修后连同单频选择两模块66 passed / 566 warnings / 3.95s，exit0。命令为根目录`DATABASE_URL=sqlite:////tmp/pc05-gain.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=api-service api-service/.venv/bin/python -m pytest api-service/tests/test_path_loss_calibration.py api-service/tests/test_path_loss_mode_filter.py -q --color=no --log-cli-level=WARNING`；RED仅选第一个文件加`-k required_gain_evidence`。

上文完整后端统计是R1前输入，不能替代此次共享补偿变化后的验证。修后独立内审已追踪getter→apply→JSON/null、bulk→积分拒绝和summary，CLEAN。

新版全量在api-service执行`DATABASE_URL=sqlite:////tmp/pc05-r1-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`：8554 collected，**7 failed / 8530 passed / 17 skipped / 10692 warnings / 1143.21s**，exit1，仍非全绿。1419项非docs tracked输入前后无变，清单SHA `eb85375cdb5b045a7f46f62a7b8589e2961f5a14dcfa92f5318f7dfd83a3ecc0`。日志`/tmp/pc05-r1-full.log` SHA `4ca1a1f0aa69e53d4400836efc87265e3576c203f9c3234a1d792c7721327ae3`。

六项契约/历史门失败与上文相同，两项环境入口失败已不再出现。新增单次失败为`test_pc04a2_route_eligibility.py::test_real_capture_may_be_adopted_without_claiming_certification[-20--10--12.0]`：采集前resolve_configuration报“实验室配置不存在或已停用”，无仪器交换。新版独立运行该参数组2 passed/6 deselected/59 warnings/5.51s；未改main同负增益nodeid连续5次均1 passed/49 warnings（2.92、2.77、2.77、2.75、2.77s）。独立命令均显式Mock、/tmp SQLite与`python -m pytest <nodeid或文件-k real_capture_may_be_adopted> -q --color=no`。

该采集路径未调用此次修改的编排器/补偿消费者。fixture多Session共享SQLite StaticPool单连接是待核线索，**根因未证实，不能称环境故障已解决或新版全量通过**。保留原失败，不以重复至绿覆盖原统计，也不为未复现测试现象扩改采集机制。
