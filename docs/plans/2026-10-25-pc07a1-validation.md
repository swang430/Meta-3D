# PC-07A-1 软件验证摘要

## 结论与版本

实现、软件验证和累计独立内审完成；待创建 PR 并完成 R1/R2 外审，未合并、未关闭 PC-07A-1。基线为已合并 PC-06A-1 `7292f8ed`，最终生产/测试输入为 `107ec2d911013db7b1d9c34fe2ce761f83b80924`，分支 `codex/pc-07a1-calibration-traceability`。本文及同次文档收口不改生产代码、测试、fixture、GUI或构建输入，因此复用该输入的后端结果，不宣称文档提交后重新全跑。

报告的生成、列表、详情、重建、下载以关联原执行的冻结事实重算追溯；GUI/PDF不查询当前配置补历史。逐链 selected/applied/unknown 与顶层状态分开，执行频率和来源覆盖频率分开，原始读数仅保留 run/indices 指针，`raw_readings_embedded=false`。不增加补偿计算，整条路径仍只补偿一次。

## 命令与结果索引

各阶段的完整命令、RED/GREEN、临时数据库、输入 SHA256 和原始日志坐标见以下归档；不是把旧测试数量归到最新提交。

| 输入 | 结果 | 详细证据 |
| --- | --- | --- |
| Task 1 基线 `0b6d1f02` 加报告所列代码/测试，提交 `cdb76061` | RED 13 failed；最终相关集 exit 0，91 passed、772 warnings、99.61s | [Task 1](2026-10-25-pc07a1-validation-evidence/task-1-report.md) |
| Task 2 精确实现 `92dcbc71`，证据提交 `6813bcdb` | 最终相关集 exit 0，179 passed、318 warnings、35.02s；真实 PDF/JSON 及篡改拒绝 | [Task 2](2026-10-25-pc07a1-validation-evidence/task-2-report.md) |
| Task 3 `b81fc541` | GUI 12 passed；build exit 0（8083 modules，12.47s）；真实 API 浏览器 Result passed:8 | [Task 3](2026-10-25-pc07a1-validation-evidence/task-3-report.md) |
| 补验 `602afe0b` | 真实启动422，UUID查询阻塞，无 execution/measure，未冒充执行完成 | 同上“补验” |
| UUID修复 `0f7d6943` | ORM RED 1 failed；相关87 passed/171 warnings/7.55s及52 passed/43 warnings/1.07s，均exit 0；实际Mock执行及报告完成 | 同上“最终补验” |
| 首次全后端 `0f7d6943` | exit 1，2 failed、7466 passed、17 skipped、7289 warnings、587.84s | [原日志](/tmp/pc07a1-final-0f7d6943.log)、[两项修复](2026-10-25-pc07a1-validation-evidence/full-regression-fix-report.md) |
| 修复输入提交 `107ec2d9` | 新增缺值展示RED 1 failed；相关exit 0，171 passed、532 warnings、78.05s | [修复报告](2026-10-25-pc07a1-validation-evidence/full-regression-fix-report.md) |
| 精确 `107ec2d9` 最终全后端 | **exit 0，7469 passed、17 skipped、7289 warnings in 589.88s (0:09:49)** | [最终原日志](/tmp/pc07a1-final-107ec2d9.log) |

最终全后端由主代理唯一安排、在本工作树 `api-service` 运行，使用独立新 SQLite，保留默认 bootstrap：

```sh
USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-final-107ec2d9.db BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest -q -o log_cli=false
```

首次全量同命令形态，数据库为 `sqlite:////tmp/pc07a1-final-0f7d6943.db`。两失败分别为 PDF 将缺值拼为 `None MHz`/`None` 和已跟踪 SDD 报告被忽略规则覆盖。`107ec2d9` 仅修 PDF短参数 None→破折号（保留0、JSON不变）及报告归档，未放宽 `.gitignore` 或测试门。完整旧失败及修复过程保留，不用新结果覆盖旧事实。warnings 和 skipped 未声称清零。

## 浏览器、PDF/JSON与实际Mock边界

原8项真实浏览器输入是 `b81fc541`，本地证据目录为 [原浏览器证据](../../output/playwright/pc07a1-task3-1792901729792/requests-responses.json)，包含HAL、真实列表/详情/生成/重建/下载、旧报告路径及自洽伪造409拒绝；截图、PDF提取文本、DB快照与构建日志位于同目录。合成历史冻结后当前采用推进、当前频率变为3500MHz，报告仍显示旧来源和2595MHz。合成历史的 provenance=real 是夹具构造标记，不是本次Mock或真机采集所得。

实际Mock执行的最终补验输入为 `0f7d6943`；[请求响应](../../output/playwright/pc07a1-mimo-completed-0f7d6943/requests-responses.json)、[原执行](../../output/playwright/pc07a1-mimo-completed-0f7d6943/raw-execution.json)、[审计摘要](../../output/playwright/pc07a1-mimo-completed-0f7d6943/mock-audit-summary.json)、[实际PDF](../../output/playwright/pc07a1-mimo-completed-0f7d6943/actual-mock-report.pdf)及提取文本/截图/DB/日志均保留本地，未纳入Git。执行 `b7c84957-e973-4e75-ba37-2c0e2b47b30f` 终态 completed；五相位有记录，但 **reference skipped**，不是五相位全部实测。measure来源simulated且未验证；analysis为diagnostic/UNKNOWN，正式量值与判据null。报告 `7495573d-bf87-4ce5-ab7b-5a0e13b50737` 为 `overall_result=undetermined`、`pass_rate=null`，三个正式验证标志均false；原行兼容布尔validation_pass=0不被当作正式FAIL。冻结来源仅selected/not_applied，不能称已实际应用。

`107ec2d9` 相对该补验仅影响PDF短参数缺值展示及其测试/文档归档，不改JSON、GUI、硬件或资格冻结。故复用此前浏览器对接口/GUI/追溯关系的证据；新PDF缺值显示由171项相关及最终全后端中的实际渲染测试覆盖。**没有在107ec2d9重跑浏览器、GUI build或下载截图**，不把此前下载PDF称作新版浏览器产物。

本地 `output/`、`/tmp/` 证据依赖当前工作站，不是仓库内附件或永久远程存储；Task 1/2/3与修复报告已归档Git，原scratch及原本地证据未删除、未覆盖。

## 审查与未完成边界

主代理交接：Task 1/2/3分别独立规格/质量 Approved；UUID与全量两项有限修复均获独立复核。累计最终独立审查 `pc07a1_final_review` 覆盖 `7292f8ed..107ec2d9`，结论 CLEAN、规格/质量通过。本文执行者只做文档自查，不将自查冒称独立审查；文档增量独立核验由主代理随后安排。GitHub外审尚未发生，没有PR号、R1/R2或合并声明。

Task 1未复现v2详情差异：当前合法静区证据不足以构造正式资格正例，未改详情接口、未mock正式门，不声称修复或验证未来正式正例。完整计量预算、撤销制度、原始审计包/附件、实物停发证明、真实仪器/现场测量和认证均未完成。PC-05/06其余、完整PC-07、PC-07B及所有B现场/HOLD保持原状态；软件Mock结果不能解除它们。

后续：文档增量独立核验后创建Ready PR；R1核实本片可执行意见并R2，R2无P1即收口，有P1则修复后续审覆盖最新HEAD，直至无P1。外审与合并前不开始下一片。
