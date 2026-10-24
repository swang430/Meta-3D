# PC-02A 固定通路校准方法实施计划

> 使用 executing-plans 顺序执行，每一步先测试后实现；不并行开发。

**目标：** 在实验室总览提供开关固定通路的方法和计算预览，不把计算预览冒充真实校准。

**设计：** `docs/design/2026-10-22-pc-02a-calibration-method-reference.md`。框架必须记录射频开关；首批只固定一路，不切换、不扫描。参考量均为操作员输入，服务器返回计算结果及无正式资格的说明。

**技术：** Pydantic、FastAPI、React/Mantine。无数据库迁移、HAL调用或新SCPI。

## 改动全集与边界

- 新建 `app/schemas/calibration_method.py`：只接受固定通路，开关身份/通路、参考天线、工作频率与三项参考值及来源必填；有限数校验，缺失拒绝。
- 新建 `app/services/calibration/fixed_route_method.py`：唯一计算 `P_CE - (P_SA + L_RX)`，保留负数；仅返回输入声明与预览，不写旧 `path_loss_db`。
- 现有 `app/api/path_loss_calibration.py` 新增只读 POST `/fixed-route/preview`，无 Session/HAL依赖，不影响旧start、多频、VNA、历史、正式应用入口。
- GUI在实验室总览挂接独立卡片，明确开关固定、人工输入、非仪器实测。服务器负责计算；输入修改后旧结果不显示。
- 同步live OpenAPI、`api/openapi.yaml`、generated TS与手写类型引用。无新正式报告/下载/历史消费者；旧路径保持不变。

## 任务1：方法与计算

- [x] 测试先走HTTP，正损耗28dB、负损耗-12dB、接收修正为负、零值可用；缺来源、缺开关身份、自动切换模式、非有限输入均拒绝。
- [x] 运行 `pytest tests/test_pc_02a_fixed_route_method.py -q`，新路由缺失404，21 failed（RED）。
- [x] 实现请求/响应及纯计算，结果始终 `formal_eligible=false`、`operator_entered`；重复器件增益参数拒绝。
- [x] 定点GREEN，旧校准与PC01及rule gates合计210 passed（12.63s）。

## 任务2：GUI与接口镜像

- [x] GUI先验证入口，缺卡片RED；镜像缺路由1RED；再加入表单与镜像。
- [x] 每次输入变更清除旧结果；API保留正负号，GUI明确显示损耗/增益及幅度、完整三项输入和开关身份/通路；不提供启动硬件或保存正式证书按钮。浏览器3项通过。
- [x] 导出OpenAPI与TS，`npx tsx --test test/*.test.ts` 177 passed，`npm run build`通过；980px卡片无横向溢出。

## 任务3：闭环

- [x] 全后端7113 passed/17 skipped/1既有日期夹具失败（188.07s）；主目录main单跑同例亦失败，固定valid_until已过期，不改生产判据。compileall、单一Alembic head `c1e3f5a7b9d2`、diff-check通过。
- [x] 独立只读内审CLEAN；错误abs变异2 failed，接收修正反号变异3 failed，进程内函数引用已恢复，未写源码；roadmap同步实际范围。
- [ ] Ready PR，R1处理本片功能意见，R2最新HEAD无P1后合并；P1修复继续外审。main安全同步并清理。

现场依赖保留PC-02B；本片计算通过不代表开关实物确认、设备量值有效或实际校准完成。

## 验证记录

验证责任人为主代理，基准 `68ee4a44`，实现从 `ddc06dc1` 的设计继续；本计划记录更新不改变已验证的生产/测试输入。命令在工作树执行，Python使用主目录现有 `.venv/bin/python`：

- `python -m pytest tests/test_pc_02a_fixed_route_method.py -q`：21 RED→21 GREEN，新增镜像1 RED→最终22 passed。
- `python -m pytest tests/test_pc_02a_fixed_route_method.py tests/test_pc_01a_calibration_scope.py tests/test_path_loss_ce_sa.py tests/test_path_loss_calibration.py tests/test_path_loss_mode_filter.py tests/test_p1_62_path_loss_application_truth.py tests/test_rule_gates.py -q --tb=short`：210 passed，exit 0。
- `python -m pytest -q --color=no --tb=short`：7113 passed/17 skipped/1 failed，exit 1；失败是 `test_p1_64_quiet_zone_evidence_truth.py::test_channel_status_cannot_be_valid_while_quiet_zone_is_unknown`。main `68ee4a44` 原样单跑同样失败（预期valid、实际expired），与本片无关。
- `npx tsx --test test/*.test.ts`：177 passed，exit 0。最初直接node运行无法解析现有无扩展名import，改用tsx后正常；未修改旧测试或生产解析规则。
- `playwright-cli --session pc02a run-code "$(< gui/test/pc02aFixedRoute.browser.js)"`：真实App隔离HTTP边界，卡片缺失RED→3项GREEN；没有连接生产API。`npm run build`、compileall与diff-check均exit 0。
- 独立内审CLEAN，两项核心内存变异分别2/3项失败。资料依据采用设计中已核手册原文；本次未变更仪器命令或回读语义，不重复查证不存在的新SCPI。

完整输出保留 `/Users/simon/.codex/artifacts/pc02a-fixed-route-20261024/`；外审请求、实际覆盖SHA和消费时刻在PR台账更新，不为完成状态另造需重审的提交。
