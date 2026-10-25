# PC04A3 拓扑编辑恢复验证记录

> 最新结论见“继续阶段最终验证”。首次WIP快照保留，不抹去暂停时的未完成事实。

## 首次阶段快照（ff80859d，13:55Z暂停）

输入基准 `5812f08987cd52a57fc065a2e4cb7114f473162c`。2026-10-25按用户15分钟时限推进Task2，截止13:58:52Z前暂停；本记录不表示PC04A3完成、可合并或现场验收。

当前最小实现：显式引用边改接/删除及中间节点删除先原子拒绝；删除探头自身不被自身声明拦截；数值损耗可编辑。前端错误在事件层捕获并保留抽屉、输入与草稿。POST/PATCH合并/模板替换共用保存校验，复用既有解析器只解释声明子图，不限制无声明旧图读取、不判断硬件/绑定资格。取消显式声明有专门确认，图内给出人工替代路径流程。

实际验证：后端同根8文件165 passed（839 warnings，96.78s）；前端相关4文件39 passed；恢复变异后新后端17 passed；production build成功（最后12.02s，有分包警告）。前端引用保护变异3项红，后端跳过保存保护变异2项红，均已恢复。基线RED的损耗表征测试曾有dataclass/矩阵访问写法错误，已修正，不计入功能RED。

可重跑命令（各后端轮次必须独立mktemp并显式三项环境，mktemp失败阻断）：

```bash
# cwd api-service
task_db_dir=$(mktemp -d /tmp/pc04a3-green-XXXXXX) && test -d "$task_db_dir" && DATABASE_URL="sqlite:///$task_db_dir/green.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests/test_pc04a3_topology_recovery.py tests/test_pc04a1_topology_editing.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_gui_contract.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_freeze.py tests/test_pc06a1_batch_plan.py -q
# cwd gui
npx --yes tsx --test test/topologyDraft.test.ts test/pc04a2RouteCalibration.test.ts test/topologyOperationalLabContext.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

真实浏览器新库由默认bootstrap创建，6 seeders/+116/0failed，所有category mock；使用18081/5188，不触碰已有8000/5187。数据库 `/tmp/pc04a3-Fskn5V/browser.sqlite` 保留，现场边界为全HAL Mock。默认启动/HAL日志、运行日志、输入hash和截图位于本机 `output/playwright/pc04a3/`；必要团队验收须补共享证据，不能依赖该本机路径作最终验收。

真实插线定点最终通过：引用边改pin/删除会拒绝并保留输入；新增A/B线缆→真实鼠标拖两边→探头重声明完整路径→删除旧边→真实PATCH/GET→reload，线缆两邻边损耗和2dB（不是4dB），新边无旧校准值。新chain由服务器选路API返回。该定点脚本第七次运行exit0；前六次动画/严格定位/原生confirm/拖线操作问题均留痕，不算通过。

未完成：19类完整逐类浏览器矩阵、端口改名替代流程、取消声明确认完整正反例、旧脚本新库重跑、离线重试/跨lab/采集pending全编辑冻结、最终全后端、独立累计内审和PR外审。父计划及roadmap保持未完成；无正式测量/采用/认证结论。详细本地交接在 `.superpowers/sdd/2026-10-25-pc04a3-topology-editing-recovery/task-2-report.md`（不随仓库共享）。

## 继续阶段最终验证（2026-10-25，旧截止已撤销）

从ff80859d接续，Task1实现不重做。补齐本片浏览器验收，并在真实Mock采集pending发现自定义端口未消费ReactFlow的NodeProps.isConnectable：按钮/拖动已锁，28个接点仍有连接手势。复用既有DeclaredPortsContext，将同一可连接真值传至旧式/显式handles三属性；保留角色、ID、标签及“显式端点替换旧端点”不变量。不改HAL、SCPI、正式资格、采用或补偿。

真实浏览器RED后补SSR正反例；SSR使用真实ReactFlow/Handle，不mock节点。强置isConnectable=true变异两项红；恢复后GUI **41 passed/0 failed**，production build **exit0/12.95s**（既有动态import/chunk体积警告）。最后定点后端新独立库 **17 passed/57 warnings/1.11s**。

### 19类逐类矩阵（最终renderer版本全部通过）

每行均实跑“名称/端口应用、真实鼠标拖动、至少一次真实接线、pin修改、无引用节点及关联边删除、保存GET/reload”。14类经真实新增菜单创建；5类仅导入类型经现有列表/属性入口，未新增菜单。无声明被动器件和bse_port先断言没有handles；只查看属性并保存不自动写ports，再由操作员明确声明。

| 类型 | 入口 | 属性/端口 | 拖动/接线/改pin | 删除/保存GET/reload | 最终证据 |
|---|---|---|---|---|---|
| cable | 新增 | 通过 | 通过 | 通过 | matrix-cable-final-result.json |
| receive_cable | 新增/校准 | 通过 | 通过 | 通过 | matrix-receive_cable-final-result.json |
| pad | 新增 | 通过 | 通过 | 通过 | matrix-pad-final-result.json |
| amplifier | 新增 | 通过 | 通过 | 通过 | matrix-amplifier-final-result.json |
| combiner | 新增 | 通过 | 通过 | 通过 | matrix-combiner-final-result.json |
| termination | 新增 | 通过 | 通过 | 通过 | matrix-termination-final-result.json |
| probe | 新增 | 通过 | 通过 | 通过 | matrix-probe-final-result.json |
| channel_emulator | 新增 | 通过 | 通过 | 通过 | matrix-channel_emulator-final-result.json |
| communication_tester | 新增 | 通过 | 通过 | 通过 | matrix-communication_tester-final-result.json |
| emcenter | 新增 | 通过 | 通过 | 通过 | matrix-emcenter-final-result.json |
| vna | 新增 | 通过 | 通过 | 通过 | matrix-vna-final-result.json |
| reference_antenna | 新增/校准 | 通过 | 通过 | 通过 | matrix-reference_antenna-final-result.json |
| signal_analyzer | 新增/校准 | 通过 | 通过 | 通过 | matrix-signal_analyzer-final-result.json |
| air_path | 新增/校准 | 通过 | 通过 | 通过 | matrix-air_path-final-result.json |
| ce_port | 导入 | 通过 | 通过 | 通过 | matrix-ce_port-final-result.json |
| bse_port | 导入 | 通过 | 通过 | 通过 | matrix-bse_port-final-result.json |
| switch_slot | 导入 | 通过 | 通过 | 通过 | matrix-switch_slot-final-result.json |
| antenna | 导入 | 通过 | 通过 | 通过 | matrix-antenna-final-result.json |
| sa_port | 导入 | 通过 | 通过 | 通过 | matrix-sa_port-final-result.json |

证据根为本机 `output/playwright/pc04a3/`。`matrix-final-summary.json`含每行的详细checks，另有每类型prepare/confirm/finish日志和截图。renderer冻结修复前的一轮19类也保留，但不冒充最终版本。夹具布局/原生modal调用的失败尝试同样留痕，没有force、固定sleep、响应拦截或手改draft。

### 专项真实链验证

- 历史全隐藏普通/校准节点恢复、清空模式拒绝、缺calibration模式先创建再恢复，未知参数与旧位置保持；恢复脚本5组具体checks通过。
- 显式引用改pin/删边明确拒绝且输入保留；插入A/B线缆、真拖两条替代边、重声明、删旧边、PATCH/GET/reload通过。邻边标称和2dB，不是4dB；新边无旧校准值，不声称任意上游损耗自动进入正式补偿。
- 原生确认后拒绝删除被引用中间节点，草稿/抽屉输入/服务器原子保持；取消显式声明的取消/确认两支通过；加新端口→真建替代边→重声明→删旧边→删旧端口→保存并选新服务器路径通过，route_digest变化、旧校准不复制。最终证据 `guards-final-result.json`（旧轮v2也保留）。
- 离线保存失败保留草稿→恢复在线重试→真实GET；dirty拒切lab；clean切乙读取乙图且无甲草稿/结果。实际Mock采集POST202的pending快照：inputs/buttons均disabled、draggable=0、connectable=0、drawers=0；结束可再编辑。模拟记录功率/损耗为空、samples=[]、确认采用422/采用历史零；真实POST取消保存cancelled。证据 `resume-lifecycle-v3-result.json`的10组checks。
- 旧 `topologyEditing.browser.js`在新库同源回归8项通过，原生删除确认后另等到脚本最终结果再签通过，证据 `old-editing-final-result.json`。离线错误及切lab时服务器409拒绝旧拓扑请求均保留，不宣称console零error。

### 全后端结果与待独立审查concern

独立临时SQLite `/tmp/pc04a3-full-ZfSrfB/full.sqlite`，显式DATABASE_URL/USE_MOCK_INSTRUMENTS=true/BOOTSTRAP_ON_STARTUP=true，实际 `pytest tests -q` **exit1：7485 passed、17 skipped、1 failed、7306 warnings，595.41s**。不得写成全量绿。

唯一失败是G8文档路由门，命中输入BASE已存在的历史 `docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md` 的具体UUID执行URL。`git show 5812f089:<文件>`确认原段已存在；真实路由仍是 `app/api/test_plan.py` 注册的POST `/cases/{test_case_id}/execute`（router前缀test-plans）。基线/路径归一化误报由独立审查核验；本片不修改历史、不扩改G8。

全量之后后端生产/已收集pytest输入不变；仅修未被pytest收集或引用的浏览器fixture（默认目录实际选中FSVA3000及文档网段测试端点）、GUI renderer/浏览器脚本/本文。按仓库规则复用上述后端结果，不因GUI改动重复全量，也不隐藏其失败。

所有浏览器库分离并保留：首续跑 `/tmp/pc04a3-fWVS2d/browser.sqlite`、绑定修复后的 `/tmp/pc04a3-OeRyze/browser.sqlite`、最终 `/tmp/pc04a3-Cv12Qu/browser.sqlite`；每个默认bootstrap均6seeders/+116/0failed，全类别mock。第一轮空端点/默认FSW43被采集门422拒绝、第二轮pending接点冻结RED均记录；生产资格门未放松。

GUI最终命令（cwd gui）：

```bash
npx --yes tsx --tsconfig tsconfig.app.json --test test/topologyHandleFreeze.test.ts test/topologyDraft.test.ts test/pc04a2RouteCalibration.test.ts test/topologyOperationalLabContext.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

本地软件验证不等于独立审查、外审或现场验收。独立任务/累计审查由主代理安排；父项PC04A3及现场HOLD不抢先勾选，无push/PR。

## 累计审查最终修复：Controls交互锁旁路

BASE b29d57e2累计审查无P1，一条P2发现默认Controls按钮直接改ReactFlow store。实跑RED：实际Mock采集POST202/pending中原生连续切换两次，按钮仍禁用但draggable=8/connectable=28，交互锁入口=1；不是手改draft/store。RED新库 `/tmp/pc04a3-v7UmWM/browser.sqlite`及原生记录保留。

生产仅一行改为 `<Controls showInteractive={!editingBlocked} />`：冻结时隐藏交互切换，保留缩放和FitView，不新增状态机。独立新库 `/tmp/pc04a3-f6gf2Y/browser.sqlite` 默认bootstrap/全Mock GREEN exit0：pending draggable=0/connectable=0、交互锁入口=0、缩放按钮2个、FitView保留；解除冻结后按钮恢复，两次原生切换可恢复拖动和接线。真实生命周期11组checks、Mock不可采用及实际取消仍通过。

相关GUI5文件 **41 passed/0 failed**，build **exit0/11.63s**。证据 `controls-red.log`、`controls-green-result.json`、RED/GREEN网络及console、`logs/pc04a3-controls-*.log` 位于原证据根。两个新库分开且保留，所有Python app导入前显式文件SQLite/Mock/bootstrap。

本波仅GUI Controls开关，后端/renderer/草稿算法不变；依主代理明确边界复用此前19类及后端结果，不重复全矩阵/全量，也不把G8基线误报改写为全绿。增量独立复核由原累计reviewer执行；不修改历史或扩改G8，无push/PR。
