# PC-04A-13：完整通路模拟与共享采集流程

## 授权与目标

用户已要求按待办连续完成非阻塞项。本片对应 roadmap PC-04A-13；本片验证识别的既有取消读取竞态由 PC-04A-14 单独修复，随后 PC-04A-12 单独交付。基准 f06dde0c。只操作隔离数据库与模拟仪器，不部署或重启用户服务，不修改原图和历史证据。

故障：现有模拟分支只列命令、复制输入，绕过生产采集事务；线缆损耗只是声明，没有可追溯校准记录。目标是同一套状态检查、设置、采样、错误处理和清理流程，只替换底层通信回复，所有模拟数据始终禁止正式采用。

## 厂商依据与发现

本机厂商原件 `Instrument_API_Doc/Keysight PromSim F64/Propsim ATE environment and practices AN.pdf`，Rev2.2，印刷页14，§2.4.1将创建/删除内部干扰源列入“Commands that shall be issued when emulation is in stopped state”。NotebookLM原答曾声称运行态亦可，复核原文后撤回，不能引用旧推断。

生产采集当前在RUNNING态ADD/REMOVE，与上述约束冲突。独立安全审确认：旧safety_confirmed未授权启动整个场景，STOPPED与无干扰源不能证明全部输出安全。因此本片真实/混合入口在任何状态修改前明确拒绝；全Mock通过唯一共享事务验证，真实通信适配不等于入口已开放。以后需核对已加载场景、所有受影响输出与本次启动授权，再接入同一事务，不能只加一个布尔放行。本片共享流程初态为STOPPED，不打断初态RUNNING的外部任务。停止态创建并设参，GO后确认完成、错误队列与RUNNING，采样后禁用，STOP并确认STOPPED后删除。停止未确认不得继续REMOVE或称清理成功。

命令出处沿既有厂商源：User Reference Rev10.2 §20.4.9.1/.6/.26/.8/.3/.2对应CW创建、策略、MHz、dBm、启禁与删除；§20.4.5.22输出测量参数1、§20.4.5.20输出损耗、§20.4.3.14状态；§20.4.1.7与§20.6.1.2明确OPC只表示操作结束，不能单独判成功；§20.4.2.1错误队列。FSVA沿 `fixed_route_spectrum_commands` 与 `capture_fixed_route_power` 邻近手册出处，不另造命令。

## 最小实现与边界

1. 单路和批量继续调用同一个 `collect_fixed_route`。将FSVA采集步骤提取为可接收底层通信对象的共享函数，真实驱动与模拟响应复用，不把模拟类包装成真实驱动身份。
2. 模拟通信保存当前输出、单音ID、频率、功率、启用及播放状态。未知命令、错误端口、未设频率/功率、错误时序、拒绝、超时都失败；不能默认返回成功。已有显式合成样本兼容，但须经相同查询与状态控制消费，不能直接复制结果。
3. 新模型模拟使用保存的完整 `RouteSelection`，要求发射链及空气段、SGH、接收线缆、绑定分析仪身份齐备；缺项失败，不把空参考链变成成功。模型量值明确为合成，不声称由标称值推导实测。
4. 接收线缆先生成带类型的模拟校准记录，包含ID、线缆身份、频率、两端参考面、模拟生成公式、原始观测及推导损耗；持久化到既有DiagnosticRun证据容器后再被完整路径引用，避免数据库迁移。每次采集生成并关联自己的记录，核对身份、频率和参考面；本片不开放跨次复用入口。完整通路按已有公式仅去嵌一次；固定声明不能冒充校准。
5. SGH同一RF口接FSVA与接VNA互斥，分别记录阶段；此片不新增真实VNA控制或虚构开关。模拟线缆测量的生成方法与真实仪器命令分开记录，不能声称已经执行真实VNA校准。
6. 模拟采样的数值、命令回复、状态和清理证据全部保留模拟来源；模拟清理成功不能设置真机停发确认。真实证据检查同步新的生产时序；历史原件不重写，不因格式旧自动提升资格。

## 新旧输入约定与规格审

独立审查确认总体可实施，无确定功能缺陷；并存规则定为：旧显式样本保持 `operator_supplied_synthetic`，旧线损只作声明，不包装成线缆校准记录，也不计入本片完整模型验收。新请求明确 `mock_model=full_route_v1`，来源 `model_synthetic`；与样本输入互斥，客户端线损和来源须为空，缺完整链不退回旧模式。记录复用须同Lab、线缆身份、频点、参考面；历史读取不重生成。GUI明确选择两模式、请求和导出保留区别。

## 入口到消费者核对

| 入口/传播 | 权威判据与可观察断言 |
|---|---|
| HAL与 `resolve_configuration` | 仍用is_mock_driver，真实/混合拒绝合成输入；保存绑定与实际身份一致 |
| 单路/批预览、启动、租约内重核 | 新模型不得因没有样本数组绕过全Mock保护；等待后配置漂移拒绝 |
| RouteSelection与线缆记录 | 身份、频率、参考面可追溯；SGH/分析仪参考链缺项失败 |
| 共享采集与FSVA事务 | 停止态创建、运行态采样、停止确认后删除；错误/超时/取消均有结果 |
| 保存/历史/JSON和CSV | 保存关联记录与模拟来源，不只留下无来源数值 |
| evidence/确认采用/冻结/证书/KPI | simulated、模拟exchange和绑定检查保持，正式资格继续拒绝 |

## 实施步骤与验收

- [x] 先补失败测试：共享命令实际执行、依赖当前端口/频率/功率、停止态约束、模拟校准关联与去嵌一次、缺参考链及错误路径。
- [x] 最小实现及定点回归；核心修复逆向变异应失败，完整恢复后再验证。
- [x] 新隔离SQLite、显式全Mock，真实API/浏览器跑32路×3500MHz×5样本，核对保存/导出、来源、计算及清理；不操作用户图。
- [x] 独立规格与质量审查；稳定生产输入后唯一完整后端回归，旧失败有基线证据，不称全绿。
- [ ] Ready PR按最新HEAD执行R1/R2，P1修复须被后续外审覆盖，合并后核对main。部署另核授权。

本片实现与隔离浏览器验收已完成；最终全量归因已完成，PR外审尚待收口，不是合并或现场验收声明。

## 已核软件证据（2026-11-08）

- 基准 `f06dde0c` 加本片工作区；全Mock独立SQLite `/tmp/pc04a8-0xZ2B9/browser.sqlite`，没有操作用户库或真实仪器。最终服务在后端停止修改后重新启动，API 18513、GUI 15513。首轮旧进程批次仅作排查，不冒称最终版本。
- 最终批次 `1bd640a2-07cc-4374-b690-f65ac64d19dd`：真实浏览器选择32条路径、3500 MHz、每路5样本，逐项人工确认，共160样本、7680条带模拟标记的控制交换。入口和断言可由 `gui/test/pc04a13FullRoute.browser.js` 复现；夹具 `tests.pc04a13_browser_fixture` 只允许新建受保护的隔离库。
- 页面下载CSV160行与服务器样本、净损耗、32份独立线缆记录逐项一致；数据库原件与引用记录相等且先于首个完整通路样本保存。全部采用预览保持 simulated、eligible=false、正式新净损耗为空；实际确认采用POST返回422。正式采用、证书及旧探头路损表均0行。记录位于上述目录的 `final-audit.json`、`final-records.json`、`final-previews.json`、`final-32-route.csv`、`final-summary.png`，均为本机验证原件。
- 普通器件编辑模拟线损1→1.5，保存刷新回读1.5，再恢复1；普通连线编辑新增0.5并回读，取消声明后保存，字段正确移除且端口、模式、原参数不变。未填模型量值时应用按钮禁用。
- GUI命令（gui目录）：`npx --yes tsx --test test/pc04*test.ts test/pc06*test.ts test/calibrationResultView.test.ts`，52 passed /0 failed；`npm run build`退出0，32.44s。原件 `/tmp/pc13-gui-final-tests.log` 与 `/tmp/pc13-gui-final-build.log`。构建保留既有大分块提示。
- 核心逆变异 `api-service/.venv/bin/python api-service/tests/pc04a13_mutations.py`：4 mutations killed，源码片段完整恢复。覆盖真实入口误放行、双重去嵌、线缆未提交、停止未确认仍删除；原件 `/tmp/pc04a13-mutations.log`。后续Scope/模型身份补充修复有独立红绿回归，不称四变异覆盖全部后续修改。
- 累计独立只读审查未发现功能P1；契约同步后两项行为门2 passed /40 warnings /2.37s（`/tmp/pc04a13-contract-final.log`），未放宽断言。

### 最终完整回归与失败归因

共享后端档由主代理唯一执行：新建 `/tmp/pc04a8-jqAG3E/full.sqlite`，导入前设置DATABASE_URL、USE_MOCK_INSTRUMENTS=true、BOOTSTRAP_ON_STARTUP=true，复用 `tests.pc04a8_browser_fixture --bootstrap-only --kind full` bootstrap并审计7/7实际Mock。api-service目录运行 `.venv/bin/python -m pytest -q --color=no -o log_cli=false`，退出1，**13 failed /8656 passed /17 skipped /11517 warnings /1352.98s**；不称全绿。日志 `full.log` SHA256 `7abb85231691d956ab9f1ade2b5deb7f769bb82488d76b1b6b1d5d929e85f1a0`。

1286项api-service/api/gui输入启动与结束核对：生产、契约、后端测试均相同；仅独立浏览器脚本把不存在的Lab单条GET改成实际列表查询，该脚本不被pytest导入/执行，并已在最终页面验收实跑。其余期间变化为本文和roadmap验证说明。安装包清单在 `/tmp/pc13-packages.txt`。

- 10项旧测试直接给build_batch_plan传None，或给模拟开关保存real策略；新增全Mock前置按预期拒绝。修复只补两测试模块的真实Mock类实例和一致绑定，不删除生产门、不放宽原通路/互斥断言。修后结果单独记录，不把旧全量统计改写。
- G8/G11两门：干净基线 `f06dde0c`、独立SQLite、同环境定向复现 **2 failed /68 deselected /40 warnings /1.48s**；`/tmp/pc13-baseline-doc-gates.log`。错误仍是旧task-3-report的UUID执行路由及两份旧SDD报告的WebSocket路由；未改历史记录或断言。
- 取消测试：固定交错探针 `/tmp/pc13_cancel_race_probe.py` 在当前与干净基线均复现 `stale=running active=False persisted=cancelled returned=interrupted`；日志 `/tmp/pc13-cancel-probe-0.log`、`/tmp/pc13-cancel-probe-1.log` 均1failed。临时新Session重读验证1passed（`/tmp/pc13-cancel-refresh.log`），生产未改。本项是真实既有读取竞态，不是环境错误，独立triage为PC-04A-14；本片不混入状态读取修复。

修后两整模块命令（仓库根目录、新SQLite、LOG_DIR隔离、USE_MOCK_INSTRUMENTS=true）：`api-service/.venv/bin/python -m pytest -q api-service/tests/test_pc04a10_boundary_consumers.py api-service/tests/test_pc04a4c_internal_routes.py`。修前10 failed /74 passed；修后 **84 passed /800 warnings /72.57s**，退出0（`/tmp/pc13-context-{red,green}.log`）。最终生产/契约仍与全量一致，只有这两测试模块的局部上下文变化，故按影响面复用完整回归加两模块结果；不称最终提交重新全量全绿。
