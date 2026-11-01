# PC-04A-10：CE源端边界软件验证

日期：2026-11-02。最新实现基准 `ddb9aa4d50e35d60635738f17e3acccd5a09958c`；累计F1修复已由原reviewer独立ADDRESSED、规格通过/质量Approved，修后唯一新版全量见下。当前待最终记录复核与同一PR外审；未部署、未更改用户图或重启用户服务，不代表现场校准或认证。首轮`f9822f5b`的API/浏览器与旧全量保留原版本，不冒称新版重跑。

## 实现与边界

共享解析与正式执行显式/隐式、直接/带PA分支统一读取完整当前模式，以真实保存的node.pin、方向/BSE角色与已声明内部pair可达性判定CE独立输入，不再把“CE有任何入边”直接当回路。CE/BSE仍不是内部中转器；未声明、冲突、真实返回、当前栈环、重复input与资源歧义保持拒绝。BSE独立UL不被虚构为DL回路，同节点不相交pair不误拒；保存pair实际可达所选路径仍拒绝。

返回身份仍只含CE输出→Probe；上游输入不进connection_ids或正常损耗补偿。未知损耗不补0；不改变采用资格、历史冻结、真实停发判据或B/HOLD。

累计F1还修正路径外上游多跳pair被直接前驱筛选漏掉的问题：核完整相关前驱链而非只看直接to_port，逐pair核声明、相关unknown与当前栈环；合法唯一多跳、DAG汇合及不同CE inputs共源不误拒，不把无关未知分支扩大成整图运行门。没有新增CE中转、开关控制、资格或冻结机制。

## 首轮旧输入：原样GET与声明副本分栏

本节为首轮`f9822f5b`的真实HTTP/浏览器记录，未在本轮重开用户GET副本或浏览器旅程；新版证据另见后文的HTTP定点及全后端，不混用版本。

源为只读GET快照 `/tmp/pc04a10-readonly-RDxFCl/pa-copy-r8-get.json`，不是数据库raw原保存证据：图 `f5883b11-f7ae-462c-acb1-a42062e51711`、revision8、120节点/122边，SHA256 `8755ec1fd8a4acb6b336eaefc9f6f474aa4c801533d9bee81f45fb9fbb0729c9`。所有导入/修改仅在新临时SQLite，全Mock，无真实仪器。

| 输入/入口 | 实际结果 |
|---|---|
| GET三个数组原样隔离导入，正常同时/逐路 | 均422；准确指出mimo_ota、conn_base_station_dl1_to_ce、ce_f64.in1方向unknown/声明不足，不伪造空成功列表 |
| 独立隔离副本仅补in1..4=input并启用、保持非default | 两入口各200/32；B1..B32→独立PA→原Probe及pins保留，每条仅3节点/2边；原样图结束整响应不变 |
| 真实浏览器错误→补声明副本→选择 | 下拉32项完整内容落盘；选B32→探头16H，后端与库选择同图ID，显示B32→in/out→in及真实路径高亮，无旧图/新候选错配成功 |
| 参考模式“空集”假设 | **不成立**：保存active_connections为空，但66边标记calibration，旧fallback使通用路径接口200/32；专用正常路径接口拒calibration参考模式422。不扩修该旧行为 |
| r8正常selection参考段 | 32条参考node/connection IDs均空，reference_antenna_id/analyzer_category_id均null；界面明确“尚未声明参考接线”。通用32路径不证明参考段齐备 |
| 人工参考说明的r8单项/批预览 | 正确full scope单项202→simulated，无样本、净损耗null、非正式；批预览200/manual/formal_eligible=false。人工说明不补造保存参考段，预览不计采集或采用 |
| 独立完整参考段小图 | BSE独立输入+CE→PA→Probe及Probe→reference→rx→sa真实保存；两次HTTP模拟采集、浏览器模拟采集/禁用采用与过期route_digest拒绝均核验 |
| 完整小图真实批次 | 预览→启动→waiting_manual→真实人工continue→completed；child为simulated，finalization_committed=true；cleanup=false、外层release=null保留，不能冒称真实停发 |

本片新库Mock类别7个、连接7个、全部Lab非空绑定逐项核验；HAL实际7驱动均Mock。模拟运行未创建route_calibration_applications、route_calibration_selections或probe_path_loss_calibrations（均0行）。专用8018/5198服务与独立浏览器已精确关闭，端口复核为空；证据、DB和输出保留。

**浏览器截图原件例外**：组合脚本重跑曾覆盖同名`pc04a10-task2-Mock-0.png`，不能称首轮截图完整。首轮run `3846d0e1-35c9-45f9-9c10-2447b1f9e71b`只以保留的真实GET、服务器审计与当轮脚本日志核验；最终run `8ed15bed-cca2-4b22-a58b-25f8ee057a60`另有独立terminal截图、DOM与POST封套，明确无值/模拟/禁用采用。两run分开记录，没有补造或重跑冒充首轮截图。

## 资格、冻结与一次补偿

累计F1修复后的本轮全量实际覆盖280源边界+16消费者（296项全部PASSED）：合法BSE DL/独立UL、被动pair/同节点独立pair；端口返回、同output、unknown、缺pins、重复input、当前链环、其他mode隔离；显式/隐式、直接/PA、两CE类型，以及同时/串行资源差异。新增16项还覆盖路径外直接/多跳返回、合法唯一多跳、共源、DAG汇合、相关内部环及unknown并存分支。此为后端矩阵，不冒全部浏览器实测，也不复用修前旧966/8492当新版结果。

首轮旧后端的独立综合补验使用完整保存参考段+BSE独立输入+PA，本轮未重跑，不称其为ddb版新通过。其隔离范围**不止替换VISA**：采集复用`test_pc04a2_route_eligibility.py::real_capture`，使用真实驱动类与脚本化VISA，同时注入ready状态、局部HAL和租约，并将本测试隔离绑定/类别设为real；这些设置不是实际仪器状态或资格证据。执行创建复用`test_pc04a2_route_freeze.py::launch`，跳过基站适配profile、信道仿真器binding、plan、执行qualification及转台coordinate profile这五项冻结，替换runner HAL getter与后台`_run_case`，并手动将execution置completed，不能视为后台真实执行完成。

该补验只证明未被替换的**目标route冻结、当前身份重核与直接ChannelEngine取值**：confirmed 28dB在直接调用`_query_calibration_entries`时只计一次、probe_gain=0，上游不累计；确认前旧执行不补填，当前input声明变坏重核拒绝，历史冻结不重写。它不是完整后台执行阶段到达此消费者的证据，不证明其他仪表资格冻结、硬件流程、现场实测或认证。首轮结果1 passed/19 warnings/2.82s仅保留为旧后端上述有限场景的证据，与纯Mock浏览器分开，不参与新版通过统计。

## 累计F1修后：新HTTP定点与最终全量

新证据根目录 `/tmp/pc04a10-final-validation-KpqoLm/`。app导入前新SQLite/Mock，bootstrap后7类别、7保留地址连接及全部Lab非空Mock绑定显式核验。真实网络HTTP定点使用独立新http.sqlite与专用18310：正常独立输入、合法唯一多跳在simultaneous/individual各200/1，多跳CE返回两个入口各422并定位mimo_ota/feed/up.d，共6请求；保存port/pair写契约先实核。该服务PID14738按精确身份关闭，端口无监听；不证明仪器或后台执行，也不是浏览器。

本轮全量自带的独立32×2×5合成API矩阵亦通过：`/tmp/pc04a8-WbFv5r/evidence/`确记ddb9aa4d/new test.sqlite，64记录/320样本全simulated/formal=false；parent completed/finalization_committed=true，但release=null、cleanup=false保留。它不是用户r8副本或浏览器重跑。

首轮证据仍在`/tmp/pc04a10-task2-HFVaNt/`，截图覆盖例外保留。最新本机SDD `final-validation-report.md`记录完整原件/起止hash/版本/关闭及提交定位；旧`task-2-report.md`只作首轮与其文档修订记录。

### 命令、统计与复用边界

| 验证 | 实际命令（对应目录） | 实际结果 |
|---|---|---|
| 修后唯一新版完整后端 | api-service：`.venv/bin/python /tmp/pc04a10-final-validation-KpqoLm/run_full.py tests -q --log-cli-level=WARNING --log-level=WARNING` | 8530 collected；exit1，**3 failed/8510 passed/17 skipped/10292 warnings，1041.56s**；仅下列历史三门，不称全绿 |
| 新版真实HTTP定点 | 仓库根：`api-service/.venv/bin/python /tmp/pc04a10-final-validation-KpqoLm/http_probe.py` | exit0，6请求全部符合上述正反例 |
| 首轮旧输入全量（非新版） | api-service：`.venv/bin/python /tmp/pc04a10-task2-HFVaNt/run_full.py tests -q --log-cli-level=WARNING --log-level=WARNING` | 8514 collected；exit1，5 failed/8492 passed/17 skipped/10292 warnings，1051.00s |
| 首轮后旧fixture声明定点（旧执行） | api-service：`.venv/bin/python /tmp/pc04a10-task2-HFVaNt/run_fixture_regression.py tests/test_p1_73a_base_station_topology.py -q --log-cli-level=WARNING --log-level=WARNING` | exit0，10 passed/2 warnings，0.05s；该模块已由新版全量再次整体通过 |
| 首轮综合transport（旧后端、未重跑） | api-service：`.venv/bin/python /tmp/pc04a10-task2-HFVaNt/run_supplement.py /tmp/pc04a10-task2-HFVaNt/test_integrated_boundary.py -q -o asyncio_mode=auto` | 旧结果exit0，1 passed/19 warnings，2.82s；范围限制见上 |
| GUI（仅前端输入不变，复用旧执行） | gui：`npx --no-install tsx --test test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts test/topologyRevisionTransport.test.ts test/pc04a8MockCalibration.test.ts` | 旧结果exit0，63 pass/0 fail/0 skipped，977.763125ms |
| production build（复用旧执行） | gui：`npm run build` | 旧结果exit0，12.02s；既有混合import/chunk-size警告保留 |

新版在ddb9aa4d稳定输入后只运行一次全量，UTC命令记录2026-11-01T17:19:34Z–2026-11-01T17:37:04Z；起止全部1808项tracked文件hash完全相等，清单SHA `daa4929e1446233f1cb7bd72ee5b63b0111be62454d46dd65f87d91634614e79`，测试期间及结束时tracked diff为空。后端安装版本清单起止同SHA `b22f9ea3081a08af8c77eadb5e17e1205c8deb562cfdb688ee775fb1b30d5d30`（Python3.13.14/pytest9.1.1）。全量结束后仅本摘要与roadmap状态同步，代码/测试/配置未变。

GUI在f9d3821d..ddb9aa4d差异0，385项tracked GUI输入清单SHA `6a5df9db915c672f12ba61cdb3b3cb893eaaee84d86218cdb4b8a9a5e556b395`，故仅限定复用旧前端回归/build，不重称新版执行或浏览器。GUI仍Node26.5.1/tsx4.23.15/Vite7.3.0；没有安装或修改依赖。累计F1的455相关/296恢复与核心回退2红原件已独立核验，本轮重核其789输入全部一致，不重复跑该集。

首轮旧全量的两个非历史失败来自P1-73a旧CAICT模板正例：通用out未列真实ports。root当时批准只给两用例专用深拷贝补声明，保35活动边/3基站端口原assert，模板及raw不改；原811清单只此测试文件变化，随后10项定点通过。这是首轮旧输入归因，不是本轮的全量豁免：新版已整体重新覆盖，P1-73a十项及source/consumer296项均在新原件PASSED。

### 三项历史规则门：精确对照，不改历史

本次三失败与 `output/playwright/pc04a8-task4/full.log`（2026-10-30T15:43:40+0800，SHA256 `9773cb9f098133372641488f6f864bc8bec44bb1ce22aa83f55eae4dccefafe8`）中的相同test IDs、文件、UUID与ignore清单一致：

- `test_g8_docs_only_cite_live_plan_routes`：`docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md:111` 的历史执行路径UUID `29769585-c9f1-43f2-8c0e-0c1c3a1d70ac`。
- `test_g11_docs_cite_live_api_routes_full_domain`：`.superpowers/sdd/2026-10-27-pc04a4e-device-contract-acceptance/task-2-report.md:128`、`.superpowers/sdd/2026-10-29-pc04a5d-topology-acceptance/task-2-report.md:16` 的ws路径记载。
- `test_gitignore_does_not_shadow_tracked_sources`：`2026-10-27-pc04a4e-device-contract-acceptance`下delivery-status-report、final-doc-report、progress、r1-fix-report、task-1/2/3-report；`2026-10-27-pc04a5a-topology-library`下task-1-fix-report、task-1-report；`2026-10-29-pc04a5d-topology-acceptance`下task-2-report（均为`.superpowers/sdd/`中的`.md`）。共10项，逐项同旧日志。

本轮直接对新旧原始日志剥ANSI比较上述30行失败块，`historical-gates-block.diff`为0字节；对历史文件、test_rule_gates与.gitignore的本轮diff亦为零，未删历史、改门或ignore。新版`/tmp/pc04a10-final-validation-KpqoLm/full-backend.log` SHA256 `2ccec7a86a33448eb528525c8038e8cb6022de87a5a5bfd8f52cb91c62776662`；首轮旧全量日志SHA `da333d486894221b173b21b63ed32cd03392d64abeb1185abb2bae013751911f`保留，不把它改名为新结果。完整三失败与warnings保留，不称全绿，warnings未逐条消除或重新归因。

## 未验/未做

真实仪器接通、RF功率/连通、现场参考件证书/不确定度、真实停发/外层控制释放、B/HOLD解除、用户r8补声明/迁移及部署均未做。不将路径可读、软件模拟或脚本化transport记录升级为正式资格。初期验收脚本的inactive、错误入口/digest/头字段、Mock cleanup与浏览器等待预设错误均保留原件并在SDD报告明确更正，不伪装产品RED或整轮成功。
