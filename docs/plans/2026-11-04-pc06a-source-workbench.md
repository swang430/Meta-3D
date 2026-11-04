# PC-06A 目标来源与撤销工作台

继承已批准总设计§10及连续开发授权，基线#557 `707c8079`，WIP=1。操作员已有采集/采用入口，但看不到新目标频点逐链来源，也无法在GUI撤销错误测量。本片只接#556/#557现有API，不改后端选择或仪器控制。

## 实施范围

- LabOverview增加只读来源卡：明确填写MHz频率和模式后查询，显示服务器逐链来源/缺口/量值/时间与限制。未查询不显示兼容结论；改目标、切实验室、请求失败/暂停时不展示旧成功结果。服务封装核对响应lab/mode/frequency身份，不自行计算可用性。
- RouteCalibrationPanel既有采用历史每行接独立撤销状态，原记录保留。查看撤销状态后，未撤销的记录提供原因和明确确认；POST成功后重读状态、采用预览与目标来源。不能只因请求发出显示成功；失败保留输入并支持重读状态；服务器同理由幂等契约继续适用。
- 同次采集可能有不同采用编号，撤销状态按lab+run归属核对，不能误把第一次撤销记录的application_id差异当身份错。切换行通过组件key清空前一行表单。
- 现有采集忙状态下禁用撤销，避免用户误解它能取消当前执行；文案明确只停止后续选用，已冻结执行不改写，历史报告影响归PC-07。认证资格始终未知。
- 撤销后的既有采用预览在刷新、失败或暂停时撤下；旧成功回执只说明曾保存，不承诺当前仍可选用。
- 枚举消费方：LabOverview/CalibrationScopeCard是库存和配置盘点；RouteCalibrationPanel是采用历史唯一GUI入口；labProfileService统一API封装；服务器真值来自route_revocation及共享route_calibration_freeze。原HAL摘要保留独立含义。

## 验证与边界

GUI/API接入，不改后端共享行为：请求封装行为测试、真实页面目标切换/错误/撤销回执/原因确认、production build；现有API定向回归。按CLAUDE比例化策略不重复后端全量。独立内审、GitHub R1/R2、SHA约束合并。NotebookLM不适用，无SCPI或仪器语义新断言。用户运行环境保持原版本；浏览器验证用隔离服务/数据，不操作用户仪器。

范围：两个新组件、两处现有挂载点、labProfileService、相关测试/本计划/roadmap。PC-05完整方法范围和PC-07历史影响仍保留，现场B及HOLD不勾选。

## 2026-11-04 验证记录

- 服务封装RED：api-service目录 `DATABASE_URL=sqlite:////tmp/pc06source-tests.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_pc06a_source_workbench.py -q --color=no`，1 failed / 39 warnings / 0.27s，`/tmp/pc06source-red.log`。
- 最终定向回归：同环境，`pytest tests/test_pc06a_source_workbench.py tests/test_pc05a_target_applicability.py tests/test_pc05a_revocation.py -q --color=no --log-cli-level=WARNING`，**11 passed / 154 warnings / 26.50s**，exit0，`/tmp/pc06source-related-final.log`。包括实际HTTP接口和正式冻结消费者；不是浏览器直接连该后端。
- 删除TS封装频率身份拒绝条件，原测试变为1 failed / 39 warnings / 0.28s（Missing expected rejection），`/tmp/pc06source-mutation.log`；finally双向assert精确恢复。
- 最终GUI `npm run build` exit0，built in20.13s，`/tmp/pc06source-build-final.log`；保留既有chunk大小警告。后端未改，本片不重复全量；基线#557仍有六项已披露失败，不据此声称全仓全绿。
- Playwright加载真实生产组件，HTTP外边界使用隔离响应：3499.995 MHz不截断；改目标即清旧结果；503不显示旧量值；原因/确认缺一不可；失败保留输入；成功后目标1/1变0/1；POST提交后回执abort，GET恢复使同run两行同步撤销；POST挂起时另一行GET先读null，POST回执后该null延迟700ms返回，两行仍撤销；切实验室重置目标且拒绝不匹配状态。
- 浏览器证据：`output/playwright/pc06-source/lost-receipt.png`及本地`.playwright-cli`快照；临时harness已移至`/tmp/pc06source-browser-harness`，路由脚本`/tmp/pc06source-browser-routes.js`与`/tmp/pc06source-browser-late.js`。这些为本地验证材料，不随生产代码发布；浏览器与独立5176服务已关闭，用户5173/8000未动。
- 内审发现并修复旧预览残留、迟到GET覆盖及回执丢失后的关联刷新；最终独立内审CLEAN。没有仪器或现场B验收声明。
