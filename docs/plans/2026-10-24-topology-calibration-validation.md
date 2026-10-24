# 射频拓扑校准整合：验证记录

## 范围与责任

基线main `192dd9d02bdcade9ad2aa51ff473b26d47ceb3c7`；分支 `codex/pc-04a-topology-calibration`。
设计提交 `57199f53` 后的本片生产及测试输入，除本文件明确记录的文档差异外，不复用其它版本的全量结论。
主代理顺序实现、负责最终验证；独立只读内审不修改文件、不重复全量。

本片新增参考选择及共享响应字段，按“GUI/API契约并涉及持久化状态”档处理，最终补一次后端全量。
没有改变仪器命令、真实采集公式、驱动能力或正式校准资格；NotebookLM不适用，不把工具名称当仪器出处。
证据目录：`/Users/simon/.codex/artifacts/topology-calibration-20261024`。命令均在本片工作树对应子目录执行，main基线复现另行标明。

## RED → GREEN及核心保护

- 旧总览仍挂校准卡的真实浏览器反例先失败，见`browser-red.log`。
- 内审指出同ID旧图混新配置、上游歧义只画半条路径；增加反例先失败，图完全换源为同一保存快照，歧义/断路受控拒绝，见`review-graph-red.log`、`review-graph-green.log`。
- 运行记录失败或离线不能作为停发证据；新增`calibrationActivity`反例先模块缺失，再实现并通过；取消使用已知运行编号，不依赖当前图/配置读取成功。
- 参考选择HTTP先404；实现后模拟记录422、数字确认422、并发配置摘要409、异拓扑422，真实采集200；验证采用不写原连接、不写旧证书、不增加仪器命令。见`reference-red.log`、`reference-topology-red.log`、`api-review-green.log`。
- 历史按chain在数据库筛选后再limit，反例固定两条记录时间保证旧逻辑必败，不依赖随机UUID顺序。
- 进程内核心变异：移除真实采集采用门，直接保护测试出现`200 != 422`失败；退出码1，磁盘源SHA前后相同。见`mutation-reference.log`，结束标记`MUTATION_DETECTED`。变异不改正在全量测试的磁盘输入。

## 最终软件验证

- `gui: npx --yes tsx --test test/*.test.ts`：**190 passed / 0 failed**，`gui-final.log`。
- `gui: npm run build`：成功，**13.21s**，`build-final.log`。仍有既有大包提示，不是构建失败。
- `api-service: .venv/bin/python -m pytest tests/test_pc_04a_fixed_route_api.py -q`：**17 passed in 22.75s**，`api-review-green.log`。
- 最终受影响链：`.venv/bin/python -m pytest tests/test_pc_04a_fixed_route_acquisition.py tests/test_pc_04a_fixed_route_api.py tests/test_p2_28_diagnostic_sequence_evidence.py tests/test_rule_gates.py -q --tb=short --show-capture=no -o log_cli=false`，**109 passed in 26.72s**，`affected-final.log`；包含采集核心、共享诊断历史、参考选择/身份与规则检查。
- `api-service: .venv/bin/python -m compileall -q app`：退出0。
- `api-service: .venv/bin/python -m alembic heads`：单头 **c1e3f5a7b9d2**；本片无数据库迁移。
- `git diff --check`：通过。
- 独立内审初轮4项均已收口，增量结论CLEAN；未把测试意见升级为功能P1。

### 后端最终全量

命令：`api-service: .venv/bin/python -m pytest tests -q`。输出`backend-full.log`，退出1：**1 failed, 7179 passed, 17 skipped in 297.14s (0:04:57)**。唯一失败为下面在main独立复现的既有日期fixture，没有本片新增失败，不把非全绿声称为全绿。
生产输入固定后只改了图中文字“开关/功放/探头”为“已保存接线”、浏览器脚本和非测试输入文档；不改后端/fixture/生成契约，最终GUI/build另行重跑。

主目录main独立复现既有日期基线：
`.venv/bin/python -m pytest -q tests/test_p1_64_quiet_zone_evidence_truth.py::test_channel_status_cannot_be_valid_while_quiet_zone_is_unknown --tb=short --show-capture=no -o log_cli=false`
结果 **1 failed in 0.07s**，断言`expired != valid`，证据`main-date-baseline.log`。该旧fixture已过期，不为变绿而更改生产证书有效期规则。

## 浏览器实际验证

真实Vite `127.0.0.1:5187` + FastAPI `127.0.0.1:18080` + 独立临时SQLite + 全HAL Mock，未拦截响应、未伪造功率；未重启用户服务或写用户数据库。
命令：`/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=topocal run-code --filename=gui/test/topologyCalibration.browser.js`。
以输出`### Result`为准，不能只看CLI退出码。`browser-final.log`记录 **11 passed**，运行编号 `480e40bc-8635-453f-b62a-4d4f07ee39b0`：

1. 总览撤除独立校准卡。
2. 图选B1.1后完整补空口到分析仪。
3. 真POST进入Mock任务，无实测功率和损耗。
4. GUI和服务器均拒绝模拟采用为实测参考。
5. 900px窄窗口无页面横向溢出。
6. 图切B1.2，端口正确、输入不串用。
7. 真实编号取消，不伪称模拟停发为真实确认。
8. 离线阻止连接编辑，恢复后重读可编辑。
9. 返回原通路可读服务器历史，不借另一通路结果。
10. 配置复核/F64状态在图内面板可达，复核不再列通路表格。
11. 切实验室清空输入，跨实验室读取404。

已实际查看截图：证据目录的`output/playwright/topology-calibration-graph.png`、`topology-calibration-narrow.png`；配置值与实测分开，图含两端和参考测量段。截图只是Mock软件操作证据，不是硬件校准证明。

## 交付边界

真实F64/FSVA3000量值、实际开关固定通路、参考天线与接收线缆证书、重复性/不确定度仍由PC-04B现场验证。本片不自动切开关、覆盖配置损耗、启用补偿或签发资格。下一软件项PC-05A仍排在本片合并/同步/清理之后。

外审及合并状态待本片实际结果回填，不以发出请求代替完成。
