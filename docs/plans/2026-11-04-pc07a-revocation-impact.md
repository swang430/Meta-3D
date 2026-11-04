# PC-07A 历史报告的当前撤销影响

基线#558 `2d3ba892`，继承总设计§9和连续开发授权，WIP=1。故障：采集撤销已阻止新选源，但历史报告仍可生成/重建/下载，且列表可能显示有效报告。原冻结和原文件不能因后来撤销被改写。

## 四行契约与全集

来源：原执行measure阶段的path_loss_application及其冻结source_snapshot；当前撤销事实只读RouteCalibrationRevocation，不读取当前图/采用指针补历史。
范围：独立撤销影响查询、报告服务生成门、API列表/详情/下载、响应契约与GUI报告列表；无仪器或测量算法改动，NotebookLM不适用。
不做：不改变历史PASS/数值，不自动认定质量责任，不删除文件；不把缺追溯的旧报告统标撤销，也不以“未检测到撤销”授予资格。
验收：实际API与生成服务覆盖创建后首次生成/已完成重建/列表/详情/下载，混合来源只关联实际应用的新采用记录；未用来源和其他lab/run不得误伤；原内容/文件字节保持。

## 方案

- 读取report关联执行，复用build_calibration_traceability得到实际应用链；仅confirmed_route的原snapshot中lab/run与source身份可核对时查询撤销。legacy或缺损追溯明确unknown，沿既有历史资格门，不凭当前配置推断。
- 当前投影分revoked/not_detected/unknown，带核对时间、逐执行/链/来源撤销事实和限制说明。无撤销不表示正式有效，原execution_evidence_outcome保持原事实。
- 列表、详情附同源投影；详情仍受原provenance门。已确认撤销优先显示“校准来源已撤销·仅审计”，GUI不显示有效报告或生成/恢复/下载按钮。
- 报告服务在writer claim及文件写入前拒绝已知撤销，直接调用/后台/公共generate同受保护；下载独立重新核对并409。列表/详情可读用于追溯，不重写content_data或原文件；不是撤销后重新生成一份掩盖原记录的报告。
- 内审发现入口检查无法保护并发撤销时的原地重建。按“去掉优先”收窄：有明确已应用新测量来源的已完成/已有文件报告，一律不原地重建；调用现有create为同一执行另建报告。原档保留，不加跨文件I/O长锁；同一未归档条件进入现有原子claim，迟到请求不得重新取得已完成文件的写权。尚未归档的首次生成若在起始核对后遇到并发撤销，可能完成新文件，但读取/下载会重新核对当前撤销并停止交付；不宣称能撤回已经开始的生成或已经下载的文件。
- 来源快照必须属于当前关联execution_id；错挂其他执行的自洽快照保持unknown。checked_source_count仅计实际核对的新测量链，不是完整计量范围或资格计数。
- 范围是#556的新采用测量撤销，不冒称已建立所有参考证书/计量政策。完整审计包及预算仍归后续PC-07，现场B未验。

## 验证流程

新增共享交付门：RED/GREEN、相关报告/撤销链回归、四镜像、GUI build、稳定最终全量；独立内审后再全量，R1/R2外审、SHA合并。不修改运行库或用户服务。

## 实施与验证（2026-11-04）

基线#558 `2d3ba892`。仅隔离SQLite/模拟仪器与HTTP边界替身，用户主目录/运行库未迁移、服务未重启。

- 新测试RED：`pytest tests/test_pc07a_revocation_impact.py`首次1 failed/57 warnings/3.24s，`/tmp/pc07rev-red.log`；初次GREEN1 passed/57 warnings/2.97s。功能新增后相关报告/冻结/撤销4模块47 passed/661 warnings/110.76s；身份和归档限制变更后相关49 passed/615 warnings/118.58s（该轮启动后原子claim修正落地，不作为最终生产输入结果）。
- 内审发现入口保护的并发覆盖窗口、错挂执行快照、失败归档仍显重试按钮；按去掉/收窄修复，新增真实原子claim调度用例。最终独立内审CLEAN；测试替身导入/空值遗漏也已修正。
- 最终生产输入的相关回归：api-service目录 `DATABASE_URL=sqlite:////tmp/pc07rev-compat-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_mimo_ota_report_verified_backcompat.py tests/test_p2_66_api_projection.py tests/test_pc07a_revocation_impact.py -q --color=no --log-cli-level=WARNING`，87 passed/226 warnings/29.60s，exit0，`/tmp/pc07rev-compat-final.log`。
- 反向变异：仅把generate传入claim的`require_unarchived`改成False，运行新增`test_late_generation_claim_cannot_replace_newly_archived_report`，1 failed/58 warnings/3.16s，exit1，`/tmp/pc07rev-mutation.log`；finally逆替换并逐字assert恢复。
- GUI `npm run openapi:generate`及`npm run build` exit0，built in19.71s，`/tmp/pc07rev-build-final.log`；既有chunk警告保留。新增契约真实序列化与YAML/生成TS在后端测试覆盖。
- 浏览器用真实ReportList/ReportViewer及隔离HTTP响应，核对撤销红标、审计提示、历史通过率标识及无生成/下载入口；`output/playwright/pc07-revocation/report-audit.png`已视觉检查。临时入口已移出工作树、浏览器与5177独立服务已关闭。不是连接用户后端的全链验收；实际API行为另由后端测试覆盖。
- 首轮完整回归在73%因五个旧测试替身缺新读取接口/字段而中止，6 failed/6248 passed/17 skipped/5671 warnings/316.46s，exit2，`/tmp/pc07rev-interrupted-full-final.log`。修正仅补测试对象measurements=None与按ID get，未改旧断言或加生产fallback；其后先跑完整相关87项再重启全量。
- 完整生产输入回归：api-service目录 `DATABASE_URL=sqlite:////tmp/pc07rev-full-final-v2.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`，**7 failed / 8555 passed / 17 skipped / 10996 warnings / 1142.50s**，exit1，不能称全绿。`/tmp/pc07rev-full-final.log` SHA256 `226e4deeaa3566d1d4dba3e0f81783769888feb325c30f640ff43e3e56f103fc`。
- 1430非docs输入起止完全一致；`/tmp/pc07rev-all-inputs.json` SHA256 `5e99a5fbe5ae4c6237e912082f79b37a6a809451dfc60bcae69e2485c3f3521d`。六项失败与#557[完整列举](2026-11-04-pc05a-target-applicability.md)完全相同：四项既有契约镜像、G8/G11历史文档路由。
- 唯一额外失败为`test_pc04a4d_conversion.py::test_task4_existing_diagnostic_report_read_download_unchanged_by_conversion`：两次报告读取的新增当前checked_at不同，42个原字段相同。全量后仅适配该局部测试：时间合法且不早于前次，其余完整响应、PDF hash和原config仍相等；生产、契约、共享fixture/依赖不变。按CLAUDE比例档采用完整生产输入回归加修改后单文件回归，**不宣称适配后重新运行整仓全量**。
- 测试适配后单文件回归：api-service目录 `DATABASE_URL=sqlite:////tmp/pc07rev-conversion-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_pc04a4d_conversion.py -q --color=no --log-cli-level=WARNING`，**64 passed / 599 warnings / 55.85s**，exit0，`/tmp/pc07rev-conversion-final.log`。与全量manifest仅差该测试文件，完整生产输入未变化。独立内审核验日志/hash与复用边界CLEAN。
