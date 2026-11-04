# PC-08A 四类信道诊断的来源与正式消费边界

基线#561 2b5de140；继承已批准总体设计§7.5/§11 PC08与连续开发授权，WIP=1。

来源：当前Doppler、spatial、Angular、EIS的唯一服务写方及全部消费者；模拟判词违反AGENTS规则3。NotebookLM已恢复；本片不改SCPI/仪器参数或声明硬件能力，不把非Mock类等同经验证方法。当前schema没有独立方法/参考资格证据，真实Doppler请求也只能保留未验证诊断。
范围：四类新写入保存已知来源，正式判词未知；详情、历史、状态、会话、workflow、CDL编排、报告/PDF及下载不能将无资格数值作为正式KPI。
不做：不实现真实spatial/Angular/EIS、不批准Doppler标准方法、不添加插值/预算/阈值、不回填历史来源、不修改原文件、不部署用户服务或数据库。
验收：模拟/实际Mock/非Mock但无方法证据/旧来源缺失均不获得正式PASS；原材料可审计；含未验证请求即使失败未落记录也不能被汇总成通过。

## 全集与最小方案

2026-11-04只读Docker meta3d_db使用容器现有用户执行四表count查询，doppler_calibrations/spatial_correlation_calibrations/angular_spread_calibrations/eis_validations均0；这不证明历史报告不存在，不按JSON形状伪造来源。

- 四表各增加同义可空diagnostic_provenance JSON，一次增量迁移、旧行NULL。spatial没有可用原始JSON容器，不能污染confidence_interval或借作者字段；删除判词不能同时保存来源事实，故该字段是最小必要持久化，不建资格引擎。
- 新Doppler use_mock或is_mock_driver实际绑定判simulated；非Mock仅unverified并保存驱动类/方法，不推定测量有效。spatial模拟、Angular/EIS随机写方明确simulated；spatial真实拒绝保持。所有本片新记录pass=None/status=unknown/valid_until=None，工程统计可保留为诊断。
- 四类共同只读投影：正式测量数组{}、统计/误差/pass/valid_until为空；diagnostic_data保留原始数组、统计、当时判词/状态与来源。旧来源缺失unknown，不贴simulated。理论参考和请求值不当成实测结果。
- 详情API与历史/状态同源；布尔筛选不匹配未知记录。会话完成与四返回面均排除这些记录正式计数；与temporal已有投影统一，不留下“另一套四类仍算PASS”的口径。静区既有UNKNOWN边界保持；未建立资格的信道方法无正式分母。
- 每种有session的请求在采集前登记已有requested_calibration_types；异常未落结果也保留请求。workflow原样消费None且沿#561显式False计失败；CDL消息不把None打印成FAIL/PASS。
- 校准报告明细、综合session元数据、总览同样排除数值；未知数按记录或未落请求计算，pass_rate未知。PDF所有四类数值为空，判词UNKNOWN。复用sidecar新增四类已处理标识，旧报告不能冒充已处理正式输出，原文件保留。
- GUI复用已有诊断弹窗扩展四类；完成提示说明诊断、历史null徽标；schema/YAML/生成TS/手写类型四镜像同步。

消费文件：channel_calibration_service、temporal_calibration_truth、api/channel_calibration、workflow_engine、calibration_orchestrator、calibration_report_generator、api/calibration_report、pdf_generator、GUI ChannelCalibration page/dashboard/history/types/API。源字段与方法声明同时核对model/schema/docstring；不改历史档案。

## 验证

共享持久化/响应/正式判定档：先行为RED，真实HTTP四类旧记录原文不变/数组清空/历史过滤/会话/报告，写方来源及实际Mock绑定，失败请求登记，迁移升级降级与空库head，GUI生成构建/隔离浏览器，真实PDF，核心逆变异。稳定输入最终后端全量由主代理执行，原基线失败和偶发不洗绿。独立计划/实现内审、R1/R2、按SHA合并；没有现场B完成声明。

计划内审F1：EIS入口读取不存在的test_config.min_eis_dbm，换为schema已有顶层request.min_eis_dbm，并补真实HTTP入口验证；不移动契约或新增阈值。

## 实施与验证进展

- 基线2b5de140，四类原始8例行为RED：8 failed/99 warnings/4.51s，/tmp/pc08c-red.log，均是实际旧/新PASS暴露。第一次命令路径多写api-service而未创建测试，未计作RED；修正绝对工作目录后运行上述有效证据。
- 初步24 passed；扩大回归11 failed/208 passed，包含新增Mock类导入错误、Angular真实入口字段缺陷和旧判词预期。Angular改positioner_id，EIS改顶层min_eis_dbm；GUI EIS补schema必需dut.type且明确模拟车辆。旧测试保持落库、工程统计和报告生成保护，只把未知判词/计数改为新语义。两次局部补丁assert先停且shell仍启动测试，中间输出不冒称稳定最终结果。
- 最终相关：根目录 `DATABASE_URL=sqlite:////tmp/pc08c-related-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=api-service api-service/.venv/bin/python -m pytest api-service/tests/test_pc08a_channel_diagnostics.py api-service/tests/test_pc08a_temporal_boundary.py api-service/tests/test_channel_calibration.py api-service/tests/test_e2e_calibration.py api-service/tests/test_workflow_engine.py api-service/tests/test_p1_70_channel_validation.py api-service/tests/test_p1_64_quiet_zone_evidence_truth.py api-service/tests/test_calibration_report.py -q --color=no --log-cli-level=WARNING`，222 passed/537 warnings/36.16s，exit0，/tmp/pc08c-related-final.log。
- 新增d5e7f9012345迁移父c4d6e8f01234；隔离SQLite `DATABASE_URL=sqlite:////tmp/pc08c-fresh-migration.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m alembic upgrade head` exit0，/tmp/pc08c-fresh-migration.log。相关用例另验证旧表原数据/NULL、重复upgrade、downgrade后upgrade；用户库未迁移。
- 内审F2异常来源原文单独保留recorded_provenance，三形态HTTP覆盖；F3四类端点不再承诺真实扫描/正式验收，同步OpenAPI与生成类型。GUI四卡固定有效期与能力描述同步降为诊断，未改QZ既有行为。
- 实际逆变异只将详情判词恢复旧row.validation_pass：四类HTTP全部红，4 failed/17 deselected/87 warnings/4.23s，/tmp/pc08c-mutation.log；finally双向assert精确恢复。
- GUI生成/build最终28.64s，exit0，/tmp/pc08c-build-final2.log；原chunk大小警告保留。浏览器实际ChannelCalibrationPage+隔离HTTP响应，四类历史UNKNOWN，诊断弹窗明确非正式并保留旧true，EIS启动提交dut.type并黄色完成提示；output/playwright/pc08-channel/diagnostic.png与completed.png已查看。临时入口移至/tmp/pc08c-browser-harness，独立5180服务与pc08c浏览器关闭，不动用户服务。
- 实际生产PDF生成器读取四类旧PASS行：/tmp/pc08c-diagnostic.pdf无原数值/100%，四类UNKNOWN；末页渲染/tmp/pc08c-diagnostic-page.png已查看。使用隔离SQLite，脚本/tmp/pc08c_pdf.py，日志/tmp/pc08c-pdf.log。
- 主代理最终全量（api-service目录）：`DATABASE_URL=sqlite:////tmp/pc08c-full-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`，exit1，**8 failed /8604 passed /17 skipped /11381 warnings /1234.96s**，/tmp/pc08c-full-final.log；基线2b5de140+本片工作区，/tmp/pc08c-inputs.json记录1360个源码/测试/契约/配置输入，运行起止SHA256逐一相同。
- 失败逐项核验：6项是既有基线（PC04A2/PC04A4a/PC06A1/PC04固定路由四项契约漂移、G8/G11两项历史记录路由；前片基线证据见时域边界计划），另2项为旧测试预期：test_channel_model_real的模拟空间相关性要求非空判词、test_pc04a5b_revision_migration写死旧head c4d6e8f01234。实际新库已成功升级d5e7f9012345。此前拓扑偶发未在本轮出现，未宣称根因修复。
- 全量结束后仅适配上述两测试：判词None并核simulated、保留落库/间距/工程统计；迁移head换为实际新编号，原表与空记录断言保持。生产输入不变，按独立内审判定追加整模块与相关回归，不冒称修后HEAD重新跑过全量；不为同一生产输入重复20分钟全量。完整计量与现场B未验。

- 修后回归（api-service目录）：`DATABASE_URL=sqlite:////tmp/pc08c-postfull.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_channel_model_real.py tests/test_pc04a5b_revision_migration.py tests/test_pc08a_channel_diagnostics.py tests/test_pc08a_temporal_boundary.py tests/test_channel_calibration.py tests/test_e2e_calibration.py tests/test_workflow_engine.py tests/test_p1_70_channel_validation.py tests/test_p1_64_quiet_zone_evidence_truth.py tests/test_calibration_report.py -q --color=no --log-cli-level=WARNING`，exit0，236 passed/555 warnings/30.11s，/tmp/pc08c-postfull.log。独立尾审复核快照仅两测试变化、累计及增量无新增功能缺陷，推送前门齐备。
