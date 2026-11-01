# PC-04A-10：CE源端边界软件验证

日期：2026-11-02。实现基准 `f9822f5b52fdc1dbfdbf059c64506a2faa04bbc4`（含独立审查F1修复）。当前为本地实现与隔离软件验收，待Task2独立审查、累计审查及同一PR外审；未部署、未更改用户图或重启用户服务，不代表现场校准或认证。

## 实现与边界

共享解析与正式执行显式/隐式、直接/带PA分支统一读取完整当前模式，以真实保存的node.pin、方向/BSE角色与已声明内部pair可达性判定CE独立输入，不再把“CE有任何入边”直接当回路。CE/BSE仍不是内部中转器；未声明、冲突、真实返回、当前栈环、重复input与资源歧义保持拒绝。BSE独立UL不被虚构为DL回路，同节点不相交pair不误拒；保存pair实际可达所选路径仍拒绝。

返回身份仍只含CE输出→Probe；上游输入不进connection_ids或正常损耗补偿。未知损耗不补0；不改变采用资格、历史冻结、真实停发判据或B/HOLD。

## 原样GET与声明副本分栏

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

当前HEAD的264源边界+16消费者均由本次全后端实际覆盖：合法BSE DL/独立UL、被动pair/同节点独立pair；端口返回、同output、unknown、缺pins、重复input、当前链环、其他mode隔离；显式/隐式、直接/PA、两CE类型，以及同时/串行资源差异。此为后端矩阵，不冒全部浏览器实测，也不复用F1修复前旧966当新证据。

另新库综合补验使用完整保存参考段+BSE独立输入+PA，但隔离范围**不止替换VISA**：采集复用`test_pc04a2_route_eligibility.py::real_capture`，使用真实驱动类与脚本化VISA，同时注入ready状态、局部HAL和租约，并将本测试隔离绑定/类别设为real；这些设置不是实际仪器状态或资格证据。执行创建复用`test_pc04a2_route_freeze.py::launch`，跳过基站适配profile、信道仿真器binding、plan、执行qualification及转台coordinate profile这五项冻结，替换runner HAL getter与后台`_run_case`，并手动将execution置completed，不能视为后台真实执行完成。

该补验只证明未被替换的**目标route冻结、当前身份重核与直接ChannelEngine取值**：confirmed 28dB在直接调用`_query_calibration_entries`时只计一次、probe_gain=0，上游不累计；确认前旧执行不补填，当前input声明变坏重核拒绝，历史冻结不重写。它不是完整后台执行阶段到达此消费者的证据，不证明其他仪表资格冻结、硬件流程、现场实测或认证。既有结果1 passed/19 warnings/2.82s仅按此范围复用，与纯Mock浏览器证据分开。

## 命令、统计与输入复用

证据根目录 `/tmp/pc04a10-task2-HFVaNt/`；请求/响应、脚本、最终截图、失败日志和新SQLite保留，首轮截图覆盖例外已在上节显著披露。本机SDD `task-2-report.md`提供矩阵、完整命令、身份/关闭、错误预设更正及最终提交定位。

| 验证 | 实际命令（对应目录） | 实际结果 |
|---|---|---|
| 唯一完整后端 | api-service：`.venv/bin/python /tmp/pc04a10-task2-HFVaNt/run_full.py tests -q --log-cli-level=WARNING --log-level=WARNING` | 8514 collected；exit1，**5 failed/8492 passed/17 skipped/10292 warnings，1051.00s** |
| 全量后旧fixture专用声明定点 | api-service：`.venv/bin/python /tmp/pc04a10-task2-HFVaNt/run_fixture_regression.py tests/test_p1_73a_base_station_topology.py -q --log-cli-level=WARNING --log-level=WARNING` | exit0，10 passed/2 warnings，0.05s |
| 综合transport | api-service：`.venv/bin/python /tmp/pc04a10-task2-HFVaNt/run_supplement.py /tmp/pc04a10-task2-HFVaNt/test_integrated_boundary.py -q -o asyncio_mode=auto` | exit0，1 passed/19 warnings，2.82s |
| GUI | gui：`npx --no-install tsx --test test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts test/topologyRevisionTransport.test.ts test/pc04a8MockCalibration.test.ts` | exit0，63 pass/0 fail/0 skipped，977.763125ms |
| production build | gui：`npm run build` | exit0，12.02s；既有混合import/chunk-size警告保留 |

全量在生产/收集输入稳定后唯一运行，起止811项代码/测试/脚本/配置逐项hash全部一致，清单自身SHA `770ca1ee3595c18d78670bc3c54fc366bfb20005b241949d39b67187700cad9e`；760项文档/API/GUI补充清单同样核对。测试期间tracked diff为空，完整BASE树清单另存。后端安装版本清单SHA `b22f9ea3081a08af8c77eadb5e17e1205c8deb562cfdb688ee775fb1b30d5d30`（Python3.13.14/pytest9.1.1）；GUI Node26.5.1/tsx4.23.15/Vite7.3.0。没有安装或修改依赖。

全量两个新增失败只来自P1-73a旧CAICT模板正例：通用out未列真实ports。root批准全量结束核hash后仅在这两用例专用深拷贝补CE输入/输出方向，并按原ce_port显式声明B端source_pin；保35活动边、3个逻辑基站端口等原assert。模板、原raw、生产和其他fixture不改。全量后原811清单**只此测试文件一项变化**，新hash `54e096440246c3a57c4b8c69425a119a63eddd4d35fc77d3fb40d4423049d278`，该文件整个模块10项定点通过（也是resolve_base_station_port_mapping唯一直接测试模块）。最终文档差异另列，不称最终测试输入与原全量相同、不重复全量，也不称最终HEAD全绿。

### 三项历史规则门：精确对照，不改历史

本次三失败与 `output/playwright/pc04a8-task4/full.log`（2026-10-30T15:43:40+0800，SHA256 `9773cb9f098133372641488f6f864bc8bec44bb1ce22aa83f55eae4dccefafe8`）中的相同test IDs、文件、UUID与ignore清单一致：

- `test_g8_docs_only_cite_live_plan_routes`：`docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md:111` 的历史执行路径UUID `29769585-c9f1-43f2-8c0e-0c1c3a1d70ac`。
- `test_g11_docs_cite_live_api_routes_full_domain`：`.superpowers/sdd/2026-10-27-pc04a4e-device-contract-acceptance/task-2-report.md:128`、`.superpowers/sdd/2026-10-29-pc04a5d-topology-acceptance/task-2-report.md:16` 的ws路径记载。
- `test_gitignore_does_not_shadow_tracked_sources`：`2026-10-27-pc04a4e-device-contract-acceptance`下delivery-status-report、final-doc-report、progress、r1-fix-report、task-1/2/3-report；`2026-10-27-pc04a5a-topology-library`下task-1-fix-report、task-1-report；`2026-10-29-pc04a5d-topology-acceptance`下task-2-report（均为`.superpowers/sdd/`中的`.md`）。共10项，逐项同旧日志。

本片对上述历史文件、test_rule_gates与.gitignore的git diff均为零，未删历史、改门或ignore。新全量原件 `full-backend.log` SHA256 `da333d486894221b173b21b63ed32cd03392d64abeb1185abb2bae013751911f`；完整失败列表保留，不能只简称“历史G8”。warnings未逐条消除或重新归因。

## 未验/未做

真实仪器接通、RF功率/连通、现场参考件证书/不确定度、真实停发/外层控制释放、B/HOLD解除、用户r8补声明/迁移及部署均未做。不将路径可读、软件模拟或脚本化transport记录升级为正式资格。初期验收脚本的inactive、错误入口/digest/头字段、Mock cleanup与浏览器等待预设错误均保留原件并在SDD报告明确更正，不伪装产品RED或整轮成功。
