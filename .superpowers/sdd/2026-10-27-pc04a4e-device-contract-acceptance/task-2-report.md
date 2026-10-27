# PC04A4e Task2 真实浏览器实施报告

## 范围与结论边界

输入基线 `5cb20d78f826f272e6f11ca45d6d5f25512263c6`。新增本片 fixture、浏览器脚本、Vite配置与本报告，未改生产、schema、共享fixture、驱动、历史模板或资格判据；未push，未释放主claim。主代理另行安排独立规格/质量审查，本报告不是独立审查。

使用 executing-plans、work-ledger、playwright、verification-before-completion。已resolve并读PROJECT/handoff、Task2 brief/progress、Task1接口证据、计划Global Constraints/§0/§4/§5和AGENTS/CLAUDE；memory精确关键词未命中，不据旧记忆作结论。NotebookLM不适用：无新增仪器语义/SCPI或驱动修改。

**不作无条件的E07～E15整体验收PASS声明。** 下表逐分支列本轮证据；Mock、脚本化transport、正式硬件/计量分栏。Task1的confirmed/冻结证据不由本片Mock代替。正式报告下载未验，现场B/HOLD、PG CAS、ASC/CE服务与实际RF状态不关闭。

root在本片实施中明确裁决：

1. 新库可建立明确标注的校准采用FK历史哨兵，仅证明原有引用保护409；不计为采集、confirmed、真实采用或资格证据。旧库误用TestExecution引用导致200替换及后续404全部保留，不恢复旧库、不改历史掩盖失败。
2. 不创建TestReport/custom文件冒充fixed-route流程产物。E15验真实scope/compare、严格采集拒绝、诊断历史JSON读取与哈希。**不适用：该诊断流程无专属下载入口；正式报告下载未验。** 由Task3据此同步计划和正式摘要。
3. root独立核对计划E14、`fixedRouteStillActive`与模拟分支后批准：本次纯Mock服务器cancelled终态恢复**软件编辑**，符合“无回执不解锁→服务器终态→恢复”；取消未知指HTTP/服务器状态未知，不把cleanup=null解释为实物清理确认。不改生产造锁，不改real。真实cleanup_unconfirmed/interrupted释放仅代码现状、未实测，不升级成已证实硬件危险，也不冒称验收通过。

## 环境与对象身份

所有Python均在app导入前设置全新 `sqlite:////tmp/pc04a4e-<随机>/browser.sqlite`、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`；fixture先检查URL/文件不存在/父目录存在/两个true，再默认bootstrap、逐category设Mock并逐Lab binding核验。所有连接地址仅192.0.2.x，无用户数据库复制。

主矩阵目录 `/tmp/pc04a4e-GMwdXP`：

| 对象 | 身份 |
|---|---|
| Lab甲 / 暗室甲 | `c39d52c3-c562-47df-b456-887dd5cb9799` / `eda86f3b-a526-462c-86fb-2d90ce1716df` |
| 主图 / 第二开关图 | `b9ed2852-5bb7-4cbc-853e-fb396ed7d109` / `18a89cf3-e46b-4df1-9da3-9de0f3a0798c` |
| 原CAICT import源图=展示图=保存请求图 | `4dabc6b8-0d4b-446d-b122-9046db9a80d5`，旧PA边 `conn_ce_b1_to_hprobe_1v` |
| Lab乙 / 暗室乙 | `a16c7ee5-15fe-44a1-a5eb-877ea4d91396` / `05237a30-4cbe-4336-a43e-871ee1b4e221` |
| 历史缺声明参考图 | `46903245-b65f-4a40-970c-bc7a5bd3da68` |

定点复验目录 `/tmp/pc04a4e-9TxR8N`：

| 对象 | 身份 |
|---|---|
| Lab甲 / 暗室甲 | `65a207dc-e0aa-484a-9f43-fd683e4958a4` / `97dd376a-0628-4a66-a15e-5a81aa495a7e` |
| 原主图 / 第二开关图 | `894416d6-a8cb-4f28-8bbd-213860ab830c` / `9493bef2-d06a-4b64-9dac-3b6c35e18a79` |
| 原CAICT源图=展示图 | `f985b869-4919-4820-bf95-805f49d2928f`（本库未重复旧CAICT数值矩阵） |
| 缺声明历史参考图 | `eb224708-68a1-49a6-92ea-6d885791422f` |
| FK哨兵 / 其诊断行 | `3209ce0f-0c3c-4181-8a12-64e19bf03fe8` / `ee6f90ff-b204-4c52-86f2-482186cc24b8` |
| 两次单路run | `1e572021-24f5-43fe-9d8f-bed66261e6d7` / `e3baf465-60bc-430d-af83-ac8e1cd9b291` |
| pair解析图 PA / pad / combiner | `79ee2ce7-5fc0-4cdc-983b-42b82e989e65` / `c1965e83-5706-4079-be41-91b64bcab7ef` / `91b50dd2-614c-4187-9bd7-3f240671cfa7` |

每库manifest包含Lab/暗室/类别/拓扑映射、初始原SQL、模板hash、全部category和binding Mock逐项记录。主库初始fixture的额外CAICT/legacy category key未匹配GUI的Switch筛选；仅在隔离库改key以显示原行（`catalog-before.json` / `catalog-after.json`），没有改源图nodes/edges；最终fixture已在创建时使用Switch key，新库无需修补。

## 分支矩阵与原件

下表路径未带目录者：主矩阵使用 `/tmp/pc04a4e-GMwdXP`，标“新库”者使用 `/tmp/pc04a4e-9TxR8N`。每个browser日志包含真实请求/响应、GET、DOM、对象ID及本轮实际执行的完整脚本；`sql-observations.jsonl`（主库）与`sql-observations.log`（新库）为SQLite只读采样，不是伪API响应。日志的`GREEN`只表示其列出的断言通过，不代表未列条件。

| ID | 实际执行分支 | 证据与边界 |
|---|---|---|
| E07 | PA、pad、combiner、probe、antenna、reference_antenna各0/3.25/null，全部真实抽屉修改→PATCH→GET→重载；单位/来源/频段；负衰减及倒序频段禁用应用 | 六份`nominal-*.log`各3行，共18数值分支；不是把旧4a结果搬过来 |
| E07旧值 | 原CAICT旧PA实际0/14.5/null保存；cable_loss 0/null/2显式转换保存；新库历史PA字符串`"12"`仅改metadata，原cable_loss缺键仍缺键 | `caict-revised.log`、`zero-revised.log`；新库`legacy-metadata.log`与`audit.json`原SQL核对，不把GET模型当raw证明 |
| E08 | 当前nodeTypes∪新增菜单∪旧图全集19类，逐抽屉改名、保存、GET、重载；线缆无第二损耗、unknown非双向、BSE物理/逻辑分开、空气虚拟端点 | `inventory-revised.log`19行；19是实际集合，不是硬写“19全部能力通过”。新库`catalog.log`实际关联目录并保存，目录响应逐字不变，不复制驱动/连接能力 |
| E09 | PA/pad/combiner清空白名单、重新添加IN→OUT；引用删口拒绝、错误方向HTTP422；真实鼠标pad→combiner连线保存；真实拖动保存重载坐标变化 | `pairs.log`、`lifecycle.log`；新库`pair-routes.log`另有三张独立CE→器件→probe图：空pair路径为空，真实抽屉添加pair后paths只有一条、损耗0。开关仅沿原port_maps提示/路径，不生成第二套控制配置 |
| E10原图 | 原import行真实选择旧PA边；三次保存请求的图ID与源/展示一致；非目标节点、边、模式与模板不变 | `caict-revised.log`；新库`audit.json`只读核原主矩阵CAICT SQL，仅一条边的pa_gain_db/metadata改变，nodes/modes与其余字段逐字不变 |
| E10转换 | 旧ce_port→channel_emulator（显式B1.1）、bse_port→communication_tester、sa_port→signal_analyzer，均预览→取消GET不变→重预览确认→重载 | `conversion.log`3行；不改旧模板，不用预览candidate冒充落库 |
| E11 | 同cable两侧owner设置、alias数值只读及定位owner、撤销；通用路径2→4，正式末边始终2；另0/null/2对应通用2/null/4与UI未知/0标签 | 新库`owner.log`5行（包含通用paths及rf-chains），主库`owner-revised.log`、`zero-revised.log`；参考receive_cable owner保存与scope见E15，不赋予参考接收线正式运行binding资格 |
| E12 | 抽屉取消不泄漏、已应用未保存不写服务器；真实setOffline保存失败草稿保留、恢复在线成功；新节点缺端口真实PATCH422、更正后保存/重载 | `lifecycle.log`、`retry.log`；失败不是toast即成功，均有PATCH/GET及SQL |
| E13 | 保存pending实际禁用DOM；预览在途改输入不接纳迟到响应；409保留输入重预览；dirty切Lab阻断、清洁甲乙甲、两开关往返 | 主库`lifecycle.log`、`retry.log`；新库`races.log`包含**真实取消在途Modal后鼠标切第二开关**，迟到响应抵达后新图无旧预览且确认禁用，没有使用旧4d的React内部handler |
| E13重导入 | 独立无历史乙图真实重导入200；新库原主图被FK哨兵引用，真实重导入409且GET/raw不变 | `reimport-revised.log`；新库`replace-protected.log`。主库误用普通执行历史的200/404失败单列，不能冒称该轮409 |
| E14单路 | 两轮各start202/running→离线取消未知时编辑锁定→恢复读服务器终态→编辑保存→再进入；每run样本[]、net_loss=null、formal_eligible=false；真实采用POST422 | 新库`collection.log`7行与全部HTTP；两个run身份独立，诊断原件GET200。终态是cancelled、cleanup_confirmed=null、F64 release=null；软件解锁不等于真实停发确认，见下方生命周期边界 |
| E14批次 | 两轮各preview/start→人工步骤等待→确认当前步骤继续→completed，items均simulated；job身份独立 | 主库`batch.log`2行；没有用Mock改real，也未跳过人工。单路selection.switch_execution_identity=[]，固定直连无开关目标；本片未另接物理I/O监测，不能声称实物开关未动作 |
| E15 | 缺ports/internal_paths旧receive_cable owner保存；scope/compare200并requires_review，当前GUI总览盘点/比较；切历史图后selected-route422、实际acquisition422、零新增run；诊断历史查看与JSON读取 | 新库`legacy.log`2行、`collection.log`历史查看。历史config/result与FK哨兵只读哈希不变，`audit.json`；不把盘点200称为可采集/正式PASS。专属诊断下载入口不适用，正式报告下载未验（root裁决） |

实际器件全集：`air_path, amplifier, antenna, bse_port, cable, ce_port, channel_emulator, combiner, communication_tester, emcenter, pad, probe, receive_cable, reference_antenna, sa_port, signal_analyzer, switch_slot, termination, vna`。

### 单路生命周期边界（root已明确收窄）

真实离线窗口中，取消请求没有成功回执，界面显示“采集状态未确认结束”并锁定。恢复网络后两个run的服务器status均为`cancelled`，但`cleanup_confirmed=null`、`states.f64_control_released=null`；界面随后按既有终态枚举解除编辑锁，可保存且可再入。所有binding为Mock、所有exchange.simulated=true，模拟分支只追加命令记录和sleep，不向仪器发送I/O。因此这是**软件终态/编辑恢复观察**，不是实物清理确认，不能从`collection.log`的GREEN推导真实安全停发。

已将该精确观察及`fixedRouteStillActive`/`RouteCalibrationPanel.track`权威关系上报root；root按上方裁决3接受其软件范围。未自行修改生产或放宽门，也未将Mock改real制造安全回执。真实cleanup_unconfirmed/interrupted状态未实测。

## 失败原件与复用依据

| 原件 | 实际失败及处置 |
|---|---|
| `/tmp/pc04a4e-9oeXqb/fixture.log` | 新fixture误把lab_profile_id传ORM拓扑模型，exit1；改为模型权威chamber_id，未启动此库服务 |
| `/tmp/pc04a4e-7bh1Cd/inventory-first.log` | 用id前缀而实际菜单label在前，选择器超时；修为真实option value |
| 同库`inventory-second.log` | fixture参考器件visible_modes误设正常与校准，UI拒绝应用；另CE改显示名破坏旧label身份。新库将参考器件仅校准可见、CE显式B1.1；未动生产 |
| 主矩阵`inventory.log` | unknown角色是Select inputValue，不在innerText；修断言读DOM输入值，`inventory-revised.log`19行GREEN |
| `caict.log` | 隔离目录category key未满足GUI的Switch筛选；仅修测试目录key，不改源图，`caict-revised.log`三ID一致GREEN |
| `owner.log` | 点击定位owner后立即读input，尚未等待React渲染；补DOM可观察等待，`owner-revised.log`及新库`owner.log`GREEN |
| `replace-protected-revised.log` / `collection-revised.log` | 普通TestExecution不是既有采用外键保护，真实200替换主图后404；输入错误不报产品RED。经root裁决，新库FK哨兵使原入口409、两轮单路及历史重验 |

以上所有DB和日志不删除、不回填；早期无attempt后缀的部分阶段截图名曾重复使用，不能保证早期同名局部截图都独立保留，失败日志及DB仍在。之后截图加入唯一attempt毫秒，后续成功/失败截图不覆盖；不宣称首轮截图全集无损。

主库已成功的19类/18标称/CAICT/转换/离线/鼠标/422/跨Lab/两批证据仍属于该库原输入。新库只重验受影响的引用、单路、owner及历史边界，另补目录关联、在途切开关、三类pair解析。没有把新旧统计相加叫“一次全量”；各日志内保留当时完整执行脚本，最终输入hash不反向冒充旧脚本hash。

## 命令、统计与输入

fixture（cwd `api-service`，每轮替换为全新目录）：

```sh
DATABASE_URL=sqlite:////tmp/pc04a4e-9TxR8N/browser.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4e-9TxR8N/logs PYTHONPATH=. .venv/bin/python tests/pc04a4e_browser_fixture.py > /tmp/pc04a4e-9TxR8N/fixture.log 2>&1
DATABASE_URL=sqlite:////tmp/pc04a4e-9TxR8N/browser.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4e-9TxR8N/logs .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18099
# cwd gui
npm run dev -- --config test/pc04a4e.vite.config.ts
```

playwright-cli具名`pc04a4e`、headed真实Chrome。先从manifest将labs/node_types/Mock核验结果写入本片localStorage输入，再逐阶段：

```sh
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=pc04a4e goto 'http://127.0.0.1:5194/?stage=collection'
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=pc04a4e run-code --filename gui/test/pc04a4eDeviceContract.browser.js
```

原始阶段stdout各存同名`*.log`，导航stdout存`*-nav.log`，种子输入命令原文在`seed.log`。CLI对脚本返回的FAILED也可能exit0，因此判定必须看日志结构化`status`，不能拿shell exit0遮盖失败。`audit.json`逐个核23份选定阶段日志status=GREEN、raw SQL/历史与模板不变，audit命令exit0；每日志SHA、stdout创建/末次写入UTC时间均入审计。没有产品RED/变异，不回退正确生产造RED。

另以只读流式解析主库807次SQLite采样，独立确认六类标称各`0`/`3.25`/`null`均曾真实落库，`/tmp/pc04a4e-GMwdXP/sql-nominal-coverage.json`为GREEN、命令exit0。原`sql-observations.jsonl`实际是连续SQLite JSON数组文档流（不是逐行独立对象），解析按完整数组收束，不把后缀当格式证明。

GUI相关集（cwd `gui`）实际命令：

```sh
npx --yes tsx --test test/topologyInternalPaths.test.ts test/topologyPortContract.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

`/tmp/pc04a4e-GMwdXP/gui-tests.log`：**88 tests / 88 pass / 0 fail / 0 cancelled / 0 skipped，1177.822792ms，exit0**。`build.log`：tsc与Vite production build均成功，**12.96s，exit0**；保留chunk超过500kB警告（bundle约7434.35kB、gzip2220.39kB），未为消警告做范围外改动。Node26.5.1/npm11.17.0；GUI依赖见`gui-npm-dependencies.txt`。

最终fixture SHA256 `c8f58616f4eb1739e7432f765b87a477f4d44b0a64a1ad4eb8c06d4e1b1775eb`；浏览器脚本 `318a0b58adce069bafb5eadf396310cf4f7bafbef1874e911d9c7a77a1c4cbe8`；Vite配置 `444ddcc62083e6d7538731afa75b223942bfbad1f4d05b308575c8752a64d986`。新库manifest `b66a0e41311872247e1f01d520a0547e23e0c2a3440d4d8ad399e1089c0ba1f8`；audit `0d7582562db00224dfecce7e2802d5d797952acd8af6e11978e66fab0b19ba42`。模板始终为 `9532474f6106b452349a9b84ea1509d6f00702c6e9036b04969e132d965fce91`。

本片没有后端全量触发输入变动，未跑全后端、未重跑Task1的669。Task3仍为唯一最终全后端判定责任位。当前仅验收代码与本报告变化，GUI88/build输入生产文件未变；浏览器定点脚本改动按各阶段日志自身源文本归属，不当成一次未执行的整套重跑。

## 截图、进程与交接

已真实查看：原CAICT旧PA抽屉、combiner方向/pair、409差异/输入保留、未知损耗、取消未知锁定、拖动重载截图。截图在仓库`output/playwright/pc04a4e-*.png`，对应日志包含绝对工作区可解析的相对路径；全部为隔离Mock软件示例。

18099/5194启动前均无监听；Vite本任务PID39973（父npm39923/39946），首API39911、主矩阵API40666、定点新库API44003，均有准确命令和启动时间。前两个API仅核身份后TERM；`processes-start.txt`、`processes-end-before-stop.txt`保留。所有代理`/api`、`/api/v1/ota`、`/api/v1/ws`均指向18099，没有借用用户服务。

本报告交由root独立审查；以下收工记录只关闭已核身份的本任务PID与具名浏览器，所有数据库/日志/截图保留，不释放主claim。

收工：具名`pc04a4e`浏览器正常close；TERM本任务API44003、SQL采样44014及Vite/npm39973/39946/39923。首次即时端口检查仍看到API正在优雅退出，原件`ports-after-stop.txt`保留；随后`ports-after-graceful.txt`为空（lsof无监听），`owned-pids-after-graceful.txt`只有表头（五个PID均已退出）。没有关闭旧4d或用户浏览器，没有清理/删除证据。

142份临时目录原件索引：`/tmp/pc04a4e-9TxR8N/artifact-sha256.txt`，SHA256 `314aec38674cd38d831bada0d53edda0c83f2b690896876f7883529cd4b6fb9a`；97份现存本任务截图索引：`screenshots-sha256.txt`，SHA256 `1774a17daa8297409f7b06b188c82d175d3811cc6600f1b1f72d7439743d4518`。索引不含自身；截图索引与原件索引分别冻结，早期同名截图保留边界如前披露。
