# PC-03A F64状态记录实施计划

> 使用 executing-plans 顺序执行；实现由主代理负责，独立内审只读。

**目标：** 让操作员读取指定组/输入口/输出口的F64状态，保留可复核记录，不自动改变仪器或校准资格。

**架构：** 复用现有诊断序列、租约、错误队列记录器和DiagnosticRun；新增类型化读写边界，不新增表。GUI只展示服务器记录。设计：`docs/design/2026-10-24-pc-03a-f64-calibration-state.md`。

**技术与约束：** FastAPI/Pydantic/SQLAlchemy、React/Mantine；不新增依赖/数据库迁移；不发写对齐/写补偿/开关命令；来源缺失保持未知，Mock不升正式，配置变化只提醒复核。

## Task 1：类型化读取与证据

文件：新建 `app/schemas/f64_calibration_state.py`、`app/diagnostics/sequences/propsim_f64_calibration_state.py`、`tests/test_pc_03a_f64_calibration_state.py`。

- [ ] RED：脚本化RealPropsimF64Driver只替换_query，证明正常原始值/负loss、空User未启用vs超时、非零队列不可确认、CLOSED不发端口、错端口不查询、Mock全模拟、请求非法首个I/O前拒绝。
- [ ] GREEN：`F64StateRequest(group_id,input_port,output_port)`校验；`read_state(driver, request, binding)`生成`F64CalibrationState`；序列`run(...,resolved_binding=...)`只调用同一读取器。
- [ ] 定点及旧许可序列回归，提交。

## Task 2：捕获/历史与执行保护

文件：`app/api/diagnostic_sequence.py`、新建`app/api/f64_calibration_state.py`、`app/main.py`，扩展本片测试。

- [ ] RED：真实HTTP捕获/历史按LabProfile隔离，缺绑定/漂移/非F64拒绝，错误/取消不得拼当前状态，旧历史损坏受控显示不完整。
- [ ] GREEN：`POST /lab-profiles/{id}/f64-calibration-state`委托既有序列，`GET`仅查完整诊断证据；新序列进入原有事务锁和关闭监控分支，Remote前调用唯一CE resolver并在finally释放DB读锁。
- [ ] 检查普通诊断入口与新API入口行为对称，正式执行互斥仍生效，提交。

## Task 3：GUI与四镜像

文件：`gui/src/features/LabWorkspace/F64CalibrationStateCard.tsx`、LabOverview、labProfileService、api.ts、api.generated.ts、api/openapi.yaml、浏览器脚本。

- [ ] RED：缺卡片/缺路由/缺生成类型；GREEN后显示读取时间、来源、字段、原始回复和历史；输入变更、切Lab、读取失败不保留旧成功。
- [ ] 真实前后端Mock自动联调，7驱动均Mock，不拦截HTTP；捕获记录能从真实数据库读回且不生成校准证书。
- [ ] GUI契约、production build、更新roadmap中PC02已合并/PC03唯一WIP。

## Task 4：验证与交付

- [ ] 最终相关、全后端、compileall、单一Alembic head与diff-check；只在最终输入运行一次必需全量。
- [ ] 独立内审；核心变异只跑本片测试，修复必要功能问题。
- [ ] Ready PR、读取每轮最新HEAD与全部意见、R1→R2，最新HEAD无P1后SHA约束merge、安全同步main、归档worktree及清理分支。

基线：本片开工时旧许可序列+PC02A 48 passed（0.94s）。已知main日期夹具在2026-10-24因固定valid_until过期失败，证据在PC02A记录，本片不得通过放宽生产有效性抹除。
