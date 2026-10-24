# PC-03A F64状态记录实施计划

> 使用 executing-plans 顺序执行；实现由主代理负责，独立内审只读。

**目标：** 让操作员读取指定组/输入口/输出口的F64状态，保留可复核记录，不自动改变仪器或校准资格。

**架构：** 复用现有诊断序列、租约、错误队列记录器和DiagnosticRun；新增类型化读写边界，不新增表。GUI只展示服务器记录。设计：`docs/design/2026-10-24-pc-03a-f64-calibration-state.md`。

**技术与约束：** FastAPI/Pydantic/SQLAlchemy、React/Mantine；不新增依赖/数据库迁移；不发写对齐/写补偿/开关命令；来源缺失保持未知，Mock不升正式，配置变化只提醒复核。

## Task 1：类型化读取与证据

文件：新建 `app/schemas/f64_calibration_state.py`、`app/diagnostics/sequences/propsim_f64_calibration_state.py`、`tests/test_pc_03a_f64_calibration_state.py`。

- [x] RED：脚本化RealPropsimF64Driver只替换_query，证明正常原始值/负loss、空User未启用vs超时、非零队列不可确认、CLOSED不发端口、错端口不查询、Mock全模拟、请求非法首个I/O前拒绝。初次测试import拼错已纠正，不把该次当有效RED；有效RED为缺新模块13 failed。
- [x] GREEN：`F64StateRequest(group_id,input_port,output_port)`校验；`read_state(driver, request, binding)`生成`F64CalibrationState`；序列`run(...,resolved_binding=...)`只调用同一读取器。
- [x] 定点及旧许可序列回归通过，随本片实现提交。

## Task 2：捕获/历史与执行保护

文件：`app/api/diagnostic_sequence.py`、新建`app/api/f64_calibration_state.py`、`app/main.py`，扩展本片测试。

- [x] RED：真实HTTP历史与坏输入在入口缺失时2 failed；GREEN后捕获/历史按LabProfile隔离，漂移/非F64拒绝；取消沿用既有审计为不完整，不拼当前状态。
- [x] GREEN：`POST /lab-profiles/{id}/f64-calibration-state`委托既有序列，`GET`仅查完整诊断证据；新序列进入原有事务锁和关闭监控分支，Remote前调用唯一CE resolver并在finally释放DB读锁。
- [x] 普通诊断入口与新API委托同一路径，正式执行互斥仍生效。历史缺损显示不完整，释放失败保留回复但operation失败；随本片提交。

## Task 3：GUI与四镜像

文件：`gui/src/features/LabWorkspace/F64CalibrationStateCard.tsx`、LabOverview、labProfileService、api.ts、api.generated.ts、api/openapi.yaml、浏览器脚本。

- [x] RED：checked OpenAPI缺路由；GREEN后显示读取时间、来源、字段、原始回复和历史；输入变更、切Lab、读取失败不保留旧成功。生成TS直接由checked契约生成。
- [x] 真实前后端Mock自动联调7项通过，7驱动均Mock，不拦截HTTP；捕获记录从真实临时SQLite读回，不生成校准证书。脚本`gui/test/pc03F64State.browser.js`，外部证据目录`/Users/simon/.codex/artifacts/pc03a-real-mock-20261024`。
- [x] `npx tsx --test test/*.test.ts` 177 passed，production build通过；roadmap已记录PC02合并/PC03唯一WIP。直接node运行不支持现有无扩展名import，改用仓库既有tsx命令，不修改旧测试。

## Task 4：验证与交付

- [x] 最终相关、全后端、compileall、单一Alembic head与diff-check；稳定输入完整全量只跑一次，结果及main既有失败见下。
- [x] 独立内审；核心变异只跑本片测试，必要功能问题已修正并复核P1/P2=0。
- [ ] Ready PR、读取每轮最新HEAD与全部意见、R1→R2，最新HEAD无P1后SHA约束merge、安全同步main、归档worktree及清理分支。

### 内审修正与验证记录

- 独立全套只读内审发现IDN整串substring可能错认型号，已严格RED→GREEN改为四字段中的型号字段精确匹配F8800A/PROPSIM F64；启用用户对齐但附加信息为空不应失败，已RED→GREEN保留空串。增量复审P1/P2=0。
- 浏览器联调暴露SQLite UTC时间未带时区，新增HTTP断言RED，接口只为无时区的数据库UTC值附加UTC，已有时区不变；增量内审CLEAN，不改生产日期判断。
- 审查者仅做两条进程内变异：删输出组成员限制1 failed/18 passed；把查询失败也标已读取7 failed/12 passed；函数引用已恢复，未写源码、不重复全量。
- 当前相关回归：`python -m pytest tests/test_pc_03a_f64_calibration_state.py tests/test_pc_03a_f64_calibration_state_api.py tests/test_diagnostic_sequences.py tests/test_p1_65_propsim_f64_license_truth.py tests/test_p2_58_channel_emulator_binding.py tests/test_p2_58_channel_emulator_binding_api.py tests/test_rule_gates.py -q --tb=short --color=no`：280 passed，15.01s，exit 0。
- 首次全量在约2%时发现时间显示问题后主动中止；稳定输入重新跑最终全量，不把中止结果算作完成。仅无关交付文档在最终全量期间更新。
- 最终`python -m pytest -q --tb=short --color=no`：7140 passed / 17 skipped / 1 failed，176.98s，exit 1。唯一失败为`test_p1_64_quiet_zone_evidence_truth.py::test_channel_status_cannot_be_valid_while_quiet_zone_is_unknown`的固定有效期已过仍期望valid；未改main d324048e单跑同样expired != valid（0.06s）。本片保留真实过期判断，不改生产有效性规则，不声称全量全绿。日志`/tmp/pc03-full-backend-final.log`及`/tmp/pc03-main-known-date.log`。
- `python -m compileall -q app`、`git diff --check`均exit 0；`python -m alembic heads`唯一head `c1e3f5a7b9d2`，本片无迁移。GUI 177 passed、build 13.50s；真实Mock浏览器最终7项通过。

### R1 功能问题修复

- PR #526 R1 review `5636546375`覆盖73973439，inline `4365785480`指出只读租约在ATE socket已释放后会走普通connect，恢复保存的用户对齐，违背“不修改”承诺。
- `tests/test_pc_03a_read_only_lease.py`经真实HTTP、真实租约与真实connect，仅替换外部VISA资源，旧实现RED实际发送`USER:SET`。修复为本序列显式传递内部`restore_f64_alignment=False`，F64 acquire/connect仅收窄恢复对齐分支；不改变默认连接、不修改保存配置、不引入共享状态开关、不新增SCPI。释放、取消与重连原逻辑保留。
- GREEN覆盖连续两次释放后读取均不发送对齐写命令，普通连接仍保留原恢复行为；相关租约/连接/诊断/本片/rule gates `266 passed`（10.19s）。独立增量内审CLEAN，已追全参数链与懒重连路径。
- 真实前后端Mock浏览器修复后再次7项通过（`browser-r1.log`）；GUI/生成契约输入未变，复用177项与build结果。共享租约/连接代码变化后由主代理重跑最终全后端，不以此前全量代替。
- R1修复最终`python -m pytest -q --tb=short --color=no`：7142 passed / 17 skipped / 1 failed，176.82s，exit 1，仍仅同一main既有过期日期夹具；日志`/tmp/pc03-r1-full-backend.log`。compileall、diff-check及唯一Alembic head再次通过。当前输入无新增失败，R1修复提交必须由下一轮外审覆盖。

基线：本片开工时旧许可序列+PC02A 48 passed（0.94s）。已知main日期夹具在2026-10-24因固定valid_until过期失败，证据在PC02A记录，本片不得通过放宽生产有效性抹除。
