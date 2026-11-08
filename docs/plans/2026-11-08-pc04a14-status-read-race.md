# PC-04A-14：采集终态读取一致性

## 目标与授权

按用户连续完成非阻塞待办的授权实施，基准为 PC-04A-13 合并提交 `013ef53e`。本片只修采集记录已提交取消或完成，却因旧数据库行与新活动表混读而显示中断的问题。PC-04A-12 界面清理另片完成，不操作用户数据库或仪器。

## 已核故障与边界

当前与干净基线 `f06dde0c` 的固定交错均为：读取旧 running → 后台提交 cancelled → 移除活动任务 → 解析旧行得到 interrupted。证据为 `/tmp/pc13-cancel-probe-0.log` 与 `/tmp/pc13-cancel-probe-1.log`。批任务解析也在读行后查询活动表，具有相同根因。

后台成功收尾顺序是提交终态后移除活动任务；保存失败也会移除活动任务。因此 inactive 不表示取消成功，持久化仍为活动态时必须保持 interrupted。正式采用确认有锁内证据读取，不能在通用解析器里偷偷另开 Session 或刷新调用者对象。

初版“先活动快照再读库”在正方向21项通过，但反方向固定交错2项失败：旧快照后新任务提交/注册，列表读到新running却误判中断（`/tmp/pc14-reverse-red.log`）。该方案撤回。也不采用把同步SQL搬到事件循环的四处async方案，避免数据库等待拖延取消与硬件清理。

## 实现关系

| 入口 | 权威来源与修改 | 可观察断言 |
|---|---|---|
| 单项/批次启动 | 配置验证后注册任务，再提交首次运行记录；两步间无await | 数据库记录可见时已登记任务；提交失败撤销未运行任务并释放互斥 |
| 单项进度、历史 | 读行后观察活动；inactive且记录仍活动时，用独立只读 Session 复核一次 | 提交终态不被旧行改成中断；仍活动才按孤儿判中断 |
| 批进度、历史 | 覆盖running/waiting_manual/paused_failure；单次观察取消标记 | 不在两次活动表读取之间发生退出索引错误 |
| 批子项 | 父inactive时同一新只读 Session 重读父子及context，包含已完成子项 | 核对实验室、批项、lease、finalization，旧子项不拼新父状态 |
| start、cancel、continue 响应 | 枚举响应是否复用动作前旧行，需要时走相同只读入口 | 动作与返回记录一致，取消请求不冒充已取消 |
| 正式采用预览/确认 | 保留调用者事务与锁内证据；不隐式换 Session | 模拟、未释放、缺损证据继续拒绝 |
| validated_batch_item | 保留服务器冻结计划的原事务 | 不丢失同事务已 flush 的真实上下文 |

通用解析可接收本次活动观察，不隐式读库。独立复核前已观察inactive，结合注册先于首次提交、最终提交先于移除、同ID不重启的约束，无需循环。提交成功后生命周期归后台任务；后续refresh或响应解析失败不能提前释放互斥。原始诊断证据读取没有这类活动推断，不改。修法为换读取来源与时序，不加缓存、重试、等待或终态保留表。厂商命令不变，NotebookLM 不适用。

## 验证与交付

- [x] 固定交错负测试先红，再修单项与批次的对称入口。
- [x] 真正遗留 running、保存失败、父子关联不匹配、未确认释放保持保守；原正式采用边界不放宽。
- [x] 连续执行、释放后重入及逆向变异实跑；变异使用逆替换，不用 checkout 回滚。
- [x] 隔离数据库定向回归，稳定输入后主代理唯一执行共享状态档完整后端；如有既有失败分别举证。
- [ ] 独立内审，Ready PR 同一最新 HEAD 的 R1/R2；P1 修复必须获得后续覆盖，合并后核实 main。

修订规格已由独立审查核对启动发布、commit→pop、提交失败清理与正式采用锁边界。实现与验证结果待追加，不把设计视作完成。

## 已核定向证据

以下命令在仓库根目录执行，每次导入前新建 `/tmp/pc14-<用途>-XXXXXX/test.db`，设置 `DATABASE_URL=sqlite:///<绝对路径>`、`USE_MOCK_INSTRUMENTS=true`；均未接触用户库或真实硬件。

1. 相关回归：`api-service/.venv/bin/python -m pytest -q --tb=short api-service/tests/test_pc04a14_status_read_race.py api-service/tests/test_pc04a14_start_ownership.py api-service/tests/test_pc04a14_status_asgi.py api-service/tests/test_pc_04a_fixed_route_api.py api-service/tests/test_pc06a1_batch_api.py api-service/tests/test_pc06a1_batch_jobs.py api-service/tests/test_pc06a1_batch_safety.py api-service/tests/test_pc04a2_route_eligibility.py api-service/tests/test_pc04a2_route_application.py api-service/tests/test_pc04a13_api_safety.py`。结尾 **193 passed /478 warnings /174.97s**，退出0，日志 `/tmp/pc14-final-targeted.log`。
2. 后续补充边界及变异恢复后复验：`api-service/.venv/bin/python -m pytest -q --tb=short api-service/tests/test_pc04a14_status_read_race.py api-service/tests/test_pc04a14_start_ownership.py api-service/tests/test_pc04a14_status_asgi.py`。结尾 **48 passed /39 warnings /5.69s**，退出0，`/tmp/pc14-restored.log`。覆盖真实ASGI线程与后台实际提交交错、历史SQL与新启动交错、父子及缺损关联、读取/最终保存失败、启动发布与互斥归属、三次取消重入、模拟采用拒绝及调用者事务保留。两组有重叠，不相加计数。
3. 启动失败路径红测试：`/tmp/pc14-ownership-red.log` **5 failed /4 passed /1 skipped**；关联失败不等于父任务退出的红测试 `/tmp/pc14-denied-red.log` **2 failed**。前者不适用的批refresh组合在最终参数中移除，最终48项无跳过。
4. 核心变异：`api-service/.venv/bin/python api-service/tests/pc04a14_mutations.py`，退出0，`/tmp/pc14-mutations.log`。跳过单项重读9 failed、跳过批重读3 failed、先发布后注册2 failed、响应失败提前释放3 failed、denied当退出2 failed；各子进程退出1，结尾 **5 mutations killed; all source fragments restored**。每次逆替换恢复并核验全文相同，8个任务文件哈希与 `/tmp/pc14-input-frozen.json` 一致。

生产4文件自相关回归至恢复复验保持不变；新增测试边界由最终48项覆盖。累计独立内审已修正一条P2：关联校验的denied不再冒充实际观察父任务退出。完整后端回归另记录，不把上述结果称为全量通过。

## 完整回归原件（2026-11-09）

主代理唯一执行，先用 `tests.pc04a8_browser_fixture --bootstrap-only --kind full` 新建 `/tmp/pc04a8-cPKrIR/full.sqlite`，导入前设置 `DATABASE_URL`、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`、独立 `LOG_DIR`；bootstrap审计7类实际驱动全部为Mock。api-service目录运行 `.venv/bin/python -m pytest -q --color=no -o log_cli=false`，退出1，**4 failed /8713 passed /17 skipped /11541 warnings /1319.17s**。不称全绿。

原件 `full.log` SHA256：`a28658f824850cc45dd0ba0cc00a0d91dbd82e5b4836fb1cfbc44a62d319074c`。运行起止1265项生产、契约、测试及配置输入哈希一致，记录 `inputs-before.json`、`inputs-after-check.json`；原运行脚本 `/tmp/pc14-full.sh`。

- 两项G8/G11失败与PC13干净基线复现的具体文件、路径相同：旧pc07a1任务报告的UUID执行路由，及两份旧SDD报告的WebSocket路由。沿用 `/tmp/pc13-baseline-doc-gates.log` 的同红证明；本片未修改门或这些历史文件。
- 两项本片 `test_real_final_commit_failure_releases_but_preserves_orphan` 失败在日志捕获 `caplog.text` 为空；不能据此声称后续断言已执行。局部日志捕获复现、修正及相关复验另记，不改写上述全量结果。

### 全量后局部测试修正

实际迁移测试会执行 `alembic/env.py` 的 `fileConfig`，默认禁用已有logger。将迁移测试放在前面，原两项失败复现为 **2 failed /1 passed**；完整三个相关模块同序复现 **2 failed /47 passed**。探针打印两个作业logger均 `disabled=True`，不是数据库污染。原件 `/tmp/pc14-logging-red.log`、`/tmp/pc14-logging-modules-red.log`。

只在两个参数测试内增加注释及两条monkeypatch，临时启用当前logger并允许传播，退出后恢复；所有原断言逐字保留。新独立SQLite与显式Mock，api-service目录运行 `.venv/bin/python -m pytest -q --tb=short -p pc14_logging_probe tests/test_channel_asset_migration.py::TestBackfillMigration::test_custom_and_scd_backfill tests/test_pc04a14_start_ownership.py tests/test_pc04a14_status_read_race.py tests/test_pc04a14_status_asgi.py`，`PYTHONPATH=/tmp:$PWD`，探针只打印状态、不修改状态。结果 **49 passed /39 warnings /5.03s**，退出0，`/tmp/pc14-logging-green.log`。

全量后只有该测试捕获变化，4个生产文件、其他测试及变异脚本与冻结哈希一致。按影响范围复用原全量与该顺序回归，不冒称最终提交重新全量全绿。内审与R1/R2结果以功能PR回执为准，不为填时间另追加需重审的提交。
