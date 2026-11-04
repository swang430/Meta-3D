# PC-05A 已采用测量撤销

依据用户连续开发授权与总设计§9.2，承接#554/#555；WIP=1。不是参考仪器证书管理平台，不关闭PC-05父项。

## 契约与验收关系

故障：已确认采用的采集发现问题后没有撤销入口，仍会供给新执行。方案追加不可变撤销行，不修改采用原文、选择指针或采集原文。

- POST某实验室/采用ID/revocation：必须明确confirmed=true及非空reason；服务从采用行解析采集run，在同run上锁后写入。每lab/run最多一条撤销；同原因重试返回原结果，不同原因409。不伪造认证操作者，actor仍null。
- GET同路径：返回当前该采集的撤销记录或null；采用不存在/跨lab404。与原不可变历史接口分开，不能把当下状态塞回旧证据。
- 撤销针对该采用所依赖的整次采集，防止换幂等键或选择另一份同run采用绕过；预览eligible=false，新确认拒绝，新冻结跳过该run的所有采用。
- 其他独立、有效来源仍可按原规则选择；不把撤销一条证据扩成撤销整个暗室。旧执行按原冻结读取，不从当前库回填/改写。历史报告影响投影归PC-07，GUI入口归PC-06，本片只交付软件API与正式选择阻断。

生产关系：撤销API→应用/采集身份及明确确认→追加撤销表；预览→同run撤销→不可采用；确认→同预览与原事务→拒绝新采用；新执行→同run撤销→不选该记录；旧执行→原hash冻结→内容不变。原确认幂等重放仍返回历史记录，不创建/激活新记录。

原表immutable事件禁止UPDATE/DELETE；故不能复用原行状态字段。删除原行丢审计、只清指针可被同run重新采用、仅前端挡不保护API，因此最小新增持久撤销行是必要的。

## 实施与验证

1. 真实API正反例先RED：撤销、重试/冲突、跨lab、空理由、预览/重新采用拒绝、新冻结拒绝/其他链保留/旧冻结不变。
2. 模型+增量迁移；追加服务与GET/POST；原预览/冻结读取同一撤销事实。无SCPI或仪器语义变更，NotebookLM不适用。
3. 四镜像契约更新，生产构建；隔离SQLite新建/升级、受影响回归，稳定输入最终后端全量，由主代理唯一执行。既有失败逐项区分，不借改门变绿。
4. 独立内审→PR→R1/R2及P1-only续审→按SHA合并→安全同步。不得把Mock当现场B，不运行用户库迁移。

范围：model、schema、API、route_calibration服务、冻结服务、模型导出、迁移、YAML/生成TS/API类型、对应测试与本计划/roadmap。新增schema有明确作用域，不扩成通用事件系统。撤销后不提供恢复按钮；恢复使用新测量/新采用记录，历史处置由质量负责人判断。

## 方案内审修正

预览同时排除当前旧指针所指run的撤销量值，即使待采用的新run有效，也不把撤销旧值用于delta；保留旧指针ID用于CAS。

确认/撤销/冻结复用采集行事务锁。PostgreSQL按run UUID排序取行锁；SQLite的FOR UPDATE无效，改用不改列值的id=id UPDATE取数据库写锁，失败传播而非继续冻结。三个创建入口均在冻结后提交；先取得锁并提交的冻结保留撤销前证据，撤销成功返回后取得锁的新冻结必查到撤销。冻结只使用取锁前同批选择指针，避免取锁后追到未锁的新run。此为既有数据库事务的局部排序，不添加进程锁/工作流引擎。

## 验证记录

基线main `7f5bb56b`，Python3.13.7/pytest9.0.1。api-service目录，显式 `DATABASE_URL=sqlite:////tmp/pc05rev-*.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=.`；不连接仪器或用户数据库。命令均用现有`.venv/bin/python -m pytest`。

- RED `tests/test_pc05a_revocation.py -q --color=no`：exit1，2 failed / 61 warnings / 5.86s，`/tmp/pc05rev-red.log`。
- 首批GREEN同命令：exit0，2 passed / 69 warnings / 7.49s，`/tmp/pc05rev-green.log`。
- 相关 `tests/test_pc05a_revocation.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a5b_revision_migration.py -q --color=no`：exit0，46 passed / 512 warnings / 88.55s，`/tmp/pc05rev-related.log`。
- 扩展新增模块 `tests/test_pc05a_revocation.py -q --color=no --log-cli-level=WARNING`：exit0，7 passed / 121 warnings / 19.96s，`/tmp/pc05rev-extra.log`。覆盖三个创建入口、并发提交次序、历史保形、新run仍可采用、写失败回滚、同源契约。
- 内审发现POST重试200未声明：补200/201模型、GET/POST404与POST409，四镜像同步。为避免输入混淆，主动中断首轮全量：exit2，2098 passed / 4 skipped / 1733 warnings / 82.70s，`/tmp/pc05rev-full.log`；不是完成结果。
- 修后契约与新库迁移 `tests/test_pc05a_revocation.py::test_revocation_contract_matches_live_and_generated_types tests/test_pc04a5b_revision_migration.py::test_fresh_alembic_head -q --color=no --log-cli-level=WARNING`：exit0，2 passed / 39 warnings / 2.31s，`/tmp/pc05rev-contract-final.log`。
- GUI `npm run openapi:generate`及`npm run build`：exit0，最终Vite built in18.24s，保留大chunk警告，`/tmp/pc05rev-build-final.log`。
- 逆变异将冻结中的撤销集合换为空：核心历史/新执行测试exit1，1 failed / 56 warnings / 3.11s，`/tmp/pc05rev-mutation.log`；finally双向assert恢复原文。

PostgreSQL锁路径目前只静态核对；并发实跑来自隔离SQLite，不冒称PG实测。最终全量由主代理在稳定1137项代码/测试/契约输入上执行，清单 `/tmp/pc05rev-final-inputs.json`；完成结果另行追加。

最终全量：api-service目录 `DATABASE_URL=sqlite:////tmp/pc05rev-full-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`，8565 collected，**6 failed / 8542 passed / 17 skipped / 10801 warnings / 1110.90s**，exit1。不是全绿。1137项相关输入前后hash无变化；日志 `/tmp/pc05rev-full-final.log` SHA256 `c4ebd5d53acea5677da7621046d4c5efb38e089986c2641fc852833c75d46c11`，清单SHA256 `f07b72599a9b8554a72fab2f1a5e173465c8ac737e44e6797fe5655fad65efab`。

未修改main `7f5bb56b`独立对照下列六个nodeid：`DATABASE_URL=sqlite:////tmp/pc05rev-main-baseline.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. LOG_DIR=/tmp/pc05rev-main-logs .venv/bin/python -m pytest <下列六个nodeid> -q --color=no --tb=short --log-cli-level=WARNING`，exit1，6 failed / 40 warnings / 2.89s，日志 `/tmp/pc05rev-main-baseline.log`。失败集合与最终全量相同：

| nodeid | 对照原因 |
|---|---|
| tests/test_pc04a2_gui_contract.py::test_topology_calibration_public_schemas_and_routes_match_live_openapi | live缺少旧FixedRouteRequest名字 |
| tests/test_pc04a4a_nominal_properties.py::test_checked_crud_and_schema_closure_match_live_contract | ValidationError镜像字段差异 |
| tests/test_pc06a1_batch_api.py::test_batch_contract_models_live_and_handwritten_openapi_agree | 既有batch契约镜像差异 |
| tests/test_pc_04a_fixed_route_api.py::test_live_checked_openapi_and_generated_types_cover_all_pc04_routes | live缺少旧FixedRouteRequest名字 |
| tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes | 历史PC07验证文档路径 |
| tests/test_rule_gates.py::test_g11_docs_cite_live_api_routes_full_domain | 历史.superpowers验收文档ws路径 |

没有修改这些旧契约/历史记录或门来消红。最终全量后仅追加本验证记录，不把本片测试宣称为真实仪器或PostgreSQL并发验收。
