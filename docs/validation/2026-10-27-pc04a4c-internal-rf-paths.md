# PC-04A-4c 内部 RF 通路综合验证

## 结论与边界

本片应用层取证及累计修复后的新版后端验证已完成：执行输入 `187b3b11a5760ddd06646f1876aa598152120bfa` 的唯一最终全后端为 **7815 passed /17 skipped /1 failed /8487 warnings，690.58s，exit1**。唯一失败仍为本次核实的未改动历史G8引用误报，**不称全绿**。Task1～4任务级独立审查已完成（Task4含C07真实鼠标未验证的非阻塞P3），累计唯一P1已由187b3b11修复并独立复核为ADDRESSED、无新增功能缺陷；仍待本轮文档增量审查与PR外审，未宣告Ready或合并。4d/4e、父项、现场B/HOLD不关闭。

本片验证应用层有向端口对白名单、保存原子性、运行解析、原开关身份和冻结匹配，不证明实物内部结构、RF导通、真实量值或正式校准资格。

原Task4浏览器/GUI取证与首轮全后端基准为 `f67baac96458ba2955ae13799a9527f76e753615`，交付提交0cc0d552，分支 `codex/pc04a4c-internal-rf-paths`；该阶段仅增加验证脚本，并获准对旧标称测试局部pad补ports/pins，原2/0断言及R1不变。后续累计P1修复187b3b11仅把DB-current触发源从全图字段存在性换为正式所选身份，并透传该身份；原冻结生成/历史/actual-target/量值/资格未改。本文本轮续验没有新的生产、测试、fixture或依赖修改。

## 新版唯一最终全后端与复用边界（187b3b11）

累计唯一P1为无关断开节点或CE源的声明误触严格采集解析、拒绝合法旧BSE直连；修复已独立ADDRESSED。修复相关集 **435 passed /2137 warnings，328.57s**，核心全图判据回退6红、身份透传回退1红并恢复，由修复报告与增量独立复核分别留证；这些是相关/变异证据，不代替下述新版全量。

```sh
cd api-service
env DATABASE_URL=sqlite:////tmp/pc04a4c-GEebeR/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4c-GEebeR/logs .venv/bin/python -m pytest tests -q
```

本轮唯一责任人使用全新临时SQLite，启动前full.sqlite不存在，所有app导入前已设置上述环境；没有启动服务或访问用户默认库。实际收集7833项，末行 **1 failed, 7815 passed, 17 skipped, 8487 warnings in 690.58s (0:11:30)**，exit.txt=1。完整原件 `/tmp/pc04a4c-GEebeR/pytest.log` SHA256=`b2a5b5b1392f06821311349e863ab195cb434e231e9e085d1503947a3a9a3031`；不存在其它失败。唯一G8仍只命中下方旧记录所述同一历史文件第111行UUID执行URL；门/历史相对8d5bc6d4无diff，历史SHA256仍为57aaf7726ffbf697d2ba3e7c21a91f57509b88f0e282ac39b16f56dcdba357c3。不改历史或门，不把8487 warnings未经逐条归因称为全部既有。

1174项后端/GUI/契约/配置输入起止全部OK，清单SHA256=`c9fb66893ff0c4177b76c80d267dab83eedf0552392b429dff5e040d00a47baf`；HEAD起止187b3b11，tracked/staged diff均空、未跟踪测试输入0项，依赖/HEAD/tracked/未跟踪清单起止cmp均0。82条依赖freeze SHA256=`ba9a0540f4c051a1467bde7d78e17716f8edcd129120ae5731a4ed67fd459ca7`，Python3.13.14/pytest9.1.1/Node26.5.1/npm11.17.0。运行后仅同步结果与状态文档，不改上述输入；pytest conftest仍按原隔离覆盖LOG_DIR，完整stdout/stderr保留在pytest.log。

**旧浏览器/GUI复用范围：** 0cc0d552→187b3b11只有两个后端生产文件、一个身份测试和设计状态行变化；gui、OpenAPI、HTTP路由/schema及浏览器fixture/脚本无diff，scope与RF-chain HTTP仍显式序列化原五字段。故原GUI88、build12.18s及本页旧库的界面/保存/原始HTTP/Mock生命周期原件保留复用，未重复浏览器或构建；它们不冒充在187b3b11重跑，新DB-current修复由新增7例、435相关及本轮新版全量覆盖。C07仍只有真实HTTP position PATCH，没有真实鼠标拖动事件证据，保留非阻塞缺项，不扩修。**旧7808/17/1仅为f67baac9→0cc0d552阶段结果，不是本修复输入的全量。**

## 隔离、源身份与原件

- 最终浏览器库：`/tmp/pc04a4c-tRJ0AF/browser.sqlite`。fixture 在任何 app 导入前验证专用 URL、父目录存在、DB 文件不存在及两个严格 true 开关；先实际默认 bootstrap，再显式设全部 category/Lab binding 为 Mock 并逐项核查。**不是 bootstrap 自动全 Mock。** 完整 manifest 在该目录 `fixture.log` 最后一行。
- 甲 Lab `5dba9b72-908a-42ff-b2a8-53884ce65434`，独立暗室 `cc2fddc1-d1ca-42dc-8a78-c12f890ba2c7`，原 POST 图 `e34afc83-ef68-47f8-a08b-a1336df3c4e9`；乙 Lab `ded716c1-a3b9-4f0b-94bf-b482f8d3f2d7`，暗室 `8274be5e-d7c7-4799-bc13-7009540ec728`。全部连接在 `192.0.2.0/24`，7 类目/7 连接及所有绑定均 Mock。
- 仅本任务 API `127.0.0.1:18096` 与 Vite `127.0.0.1:5191`，API/WebSocket/更具体 OTA 代理均指向本任务 API；没有启 CE、调用 OTA 执行或接真硬件。用户默认库和原服务不动，无 route mock。
- 本任务早期脚本校正库 `/tmp/pc04a4c-05M08A` 及所有失败日志保留，不用其计数冒充最终新库矩阵；Task3 首次 RED 日志/DOM/截图原件未覆盖或回退补拍。
- 原编辑器按最新创建行展示，不按 default 选图。矩阵源图的 HTTP 请求/响应/GET 与展示对象 DOM **分栏**：`browser-matrix.log` 各 `rows` 明列 `topology_id` / `display_topology_id`。非最新源图只经真实 POST 建同 JSON 展示副本，并对该副本实际 UI PATCH→GET 精确比对；副本 DOM 不被称为原图 UI 重载证据。C13～C15 始终在原 POST 图实际编辑与采集；C11 的源图来自两次采集冻结的 topology_id，不从可重复显示名猜。
- 正式 resolver 的权威是最新更新的 active 图，不是 default。专用库切换矩阵目标时显式只保留该目标 active，避免同秒排序读取另一图；这只是 fixture 隔离，不扩改生产选图规则。

可重跑输入：`tests/pc04a4c_browser_fixture.py`、`tests/pc04a4c_matrix_evidence.py`（cwd api-service），`test/pc04a4cInternalPaths.browser.js`、`test/pc04a4cMatrix.browser.js`、`test/pc04a4cSupplement.browser.js` 和 `test/pc04a4c.vite.config.ts`（cwd gui）。全部 Python 命令先设置本片新库/Mock/bootstrap 环境。浏览器用专用 `pc04a4c-task4` 会话；离线只控制真实浏览器网络，pending 用 MutationObserver 观察真实 PATCH，不造延时响应。

## C01～C16 既有浏览器/HTTP验收原件（按新版章节边界复用）

下列文件均在最终浏览器目录；截图在 `gui/output/playwright/pc04a4c-task4-*` 和 `pc04a4c-task4-final-*`。普通矩阵 `browser-matrix.log` 包含 260 个真实 HTTP 记录及11行源/展示对象完整 JSON/DOM；截图只是辅助，落库以对应 GET/ORM 为据。

| 行 | 实际结果 | 原件及限制 |
|---|---|---|
| C01 | PA 单向，pad/cable/receive_cable 双向须两行；删除→[]→恢复精确保存，外边仍0；PA反向并存422 | `browser-matrix.log` C01；真实 UI 保存同一展示对象并 GET 比对，不新增内部量值 |
| C02 | 三口合路只返回显式所选 connection_ids，换分支 CE 从 B1.1 到 B1.2；四口分路只两条已列 pair；IN→另一输入口422 | 同日志 C02；未选支路不混入，不按口数量生成配对 |
| C03 | 负载非空422、可作通用路径终点但不向探头中转；[]无完整路径；R1旧双端唯一链保留，多口缺字段不全通 | 同日志 C03；负载终止的路径损耗来自原外边，不代表负载转发 |
| C04 | unknown 草稿可存，所选路径/公共查询422；明确反向声明422；BSE dl/ul冲突拒绝；空气仍虚拟参考模型 | 同日志 C04 与原图参考段；没有给 unknown 或空气授物理能力 |
| C05 | 删除端口/改变方向/清空所选 pair 均422，GET 原图不变；先撤探头显式路径引用，再清空可存 | 同日志 C05；跨模式引用的真实抽屉拒绝另见 C13/C14 |
| C06 | 非法 default POST、部分 nodes PATCH、模式数组、import replace 前置错误及跨Lab请求均先拒绝；ORM 整行/默认/图/历史前后相同 | `browser-matrix.log` C06、`atomic-evidence.log`；非法新模板内部 pair 还由相关真实 TestClient/ORM 用例覆盖；未给服务添加模板注入入口 |
| C07 | 乙 Lab 真正 import caict_v4，所有节点仍缺内部声明；旧双端改名/位置/标称0/metadata/opaque回传保形，route_digest不变 | 同日志 C07；未转换旧模板或宣称其有效，真实鼠标拖动不在本行声明范围 |
| C08 | 显式及R1两组各缺入pin/出pin/两pin：原缺键GET保持，paths/matrix无完整路径、validate定位原边；补真实pin后恢复 | 同日志 C08、`orm-evidence.log` 6组 BFS loss=None；`reference-evidence.log` 参考PA/接收线共14个拒绝及前后正例，非法历史仅专用ORM构造；探头正常终点→参考另起保留 |
| C09 | 合法开关身份继续含原 port_maps/switch_id/relay；缺映射、错配对、同继电器冲突均生产 builder 拒绝，job不增加 | `switch-evidence.log`、`c09-browser.log`；零真实开关动作，合法 Mock 映射留于专用库供同图 UI 保存 |
| C10 | individual候选可读；同CE非互斥分路 simultaneous/批preview/start均422；start带有效幂等UUID，拒绝原因是互斥映射而非缺header | `browser-matrix.log` C10；preview调用原 builder(..., None)，不创建作业；原零I/O保护由相关回归覆盖 |
| C11 | 正常pair改动改变普通/route摘要；参考pair改动不扩普通scope，但改变route/selected摘要；旧固定请求和旧批preview422，两run历史逐字不变 | 同日志 C11、`reference-preview-evidence.log`；普通与参考两组批拒绝均带幂等UUID，Mock资格/采用拒绝不变 |
| C12 | 无开关链：冻结有声明→新pair、冻结无键→实际新增声明，两组DB-current与actual-target均拒绝旧身份，历史读取逐字不变 | `freeze-evidence.log`、`c12-browser.log`；纯生产builder/冻结补证，无真实执行/CE/ASC动作；正式session/preflight链由相关身份/冻结回归覆盖，未制造real样本 |
| C13 | 打开/取消/应用后再取消/恢复缺键与0、opaque都保持；独立断开PA实际UI声明[]→保存→同值重申→有值→恢复，4次PATCH200且GET保形；引用错误保留草稿 | `browser-lifecycle.log`、`c13-explicit-browser.log`；原图生命周期及独立C13图均真实操作，不以展示副本代替；补证图为78abb851-6ec7-47e6-844a-3c62c029bf5d，仍unknown草稿/无采集，旧历史恰两条 |
| C14 | pending实际锁住器件/模式/拖动/handle；离线失败保留，恢复在线真实重试200；直接422后GET不变；dirty切Lab拒绝，清洁甲乙往返/模式/重载不串值 | 同日志，阶段截图和真实pending快照；不以toast代替GET |
| C15 | 两次真实202/running，离线取消未知锁保持；服务器确认终态后可编辑，实际新增combiner pair并保存，再以新digest采集；历史恰两条 | `browser-collection.log`；最终 cancelled / simulated，无正式量值/样本/资格；cleanup_confirmed=null不证明硬件清理 |
| C16 | 两端unknown保存草稿但路径/采集422无job；明确方向可解析；明确组缺分析仪绑定仍422且不建job，两份Mock采用均422 | 同矩阵 C16、`binding-evidence.log`；明确声明实际Mock闭环见C15，旧标称/正式判词不因此提升 |

最终两次采集：`a0833ac2-3a00-40f8-89ed-2d30cf6ca4f1` 与 `01294d0f-53be-4638-915a-14924de3feba`。两条原请求摘要分别为 `3a587fda54bf94de67ae91caea9b2e1ee6c74f1d56727b31ab6b73e9d0d841c2` / `25d96b862c4162705000e135fff11341b6b9d0e3089a696f4536c5260b53f1aa`。均 formal_eligible=false、net_loss_db=null、samples=[]。所有源码脚本和日志/截图/库保留，不清理用户资料。

## 原Task4相关与旧版全后端记录（不代表187b3b11输入）

相关23文件首次结果 `/tmp/pc04a4c-3fmW8Q/pytest.log`：exit1，**2 failed /654 passed /2300 warnings，372.99s**。仅旧 `test_nominal_declarations_never_add_another_topology_compensation` 两参数失败：自建中间pad未存 ports/pins，按新R1返回None，未到原标称补偿断言。主代理已批准只补该函数局部端口证据，并保留后续nominal赋值的ports；原2/0期望及全部断言不动。修后新库 `/tmp/pc04a4c-9hMnvf/pytest.log`：**7 passed /90 warnings，5.11s，exit0**；这是该文件定点，不冒称重跑23文件。

```sh
cd api-service
env DATABASE_URL=sqlite:////tmp/pc04a4c-3fmW8Q/related.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4c-3fmW8Q/logs .venv/bin/python -m pytest tests/test_pc04a4c_internal_contract.py tests/test_pc04a4c_internal_routes.py tests/test_pc04a4c_internal_identity.py tests/test_pc04a4b_port_contract.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a3_topology_recovery.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc_04a_fixed_route_api.py tests/test_pc06a1_batch_plan.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_safety.py tests/test_p1_73a_base_station_topology.py tests/test_rf_chain_resolver.py tests/test_pc04a4b_port_identity.py tests/test_pc04a4a_nominal_identity.py tests/test_pc06a1_batch_jobs.py tests/test_pc_04a_fixed_route_acquisition.py -q
env DATABASE_URL=sqlite:////tmp/pc04a4c-9hMnvf/nominal.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4c-9hMnvf/logs .venv/bin/python -m pytest tests/test_pc04a4a_nominal_identity.py -q
```

GUI：规定九文件 **88/88，922.425292ms，exit0**；production build **exit0，12.18s**。原件 `/tmp/pc04a4c-05M08A/gui.log`、`build.log`；后续仅增加独立浏览器脚本/后端fixture并修改一个pytest局部fixture，没有GUI生产或构建输入变化。保留现有大bundle警告，不称无警告。

```sh
cd gui
npx --yes tsx --test test/topologyInternalPaths.test.ts test/topologyPortContract.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

旧版Task4全后端在独立新库 `/tmp/pc04a4c-KxzsaG/full.sqlite` 完成；`pytest.log` SHA256=`253fd88e9c2f2876dc3a87f120973ecaf1bcececb1d0812f33d0c98ac91c7856`，`exit.txt`实际为1，末行 **1 failed, 7808 passed, 17 skipped, 8363 warnings in 684.38s**。以下命令、输入及门复核均是该旧阶段原件，不替代上方新版结果。

```sh
cd api-service
env DATABASE_URL=sqlite:////tmp/pc04a4c-KxzsaG/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4c-KxzsaG/logs .venv/bin/python -m pytest tests -q
```

唯一失败 `tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes`，仍命中历史 `docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md` 第111行的具体UUID执行URL。该历史文件及门相对4c基线 `8d5bc6d4` 无diff；历史当前/基线SHA256均 `57aaf7726ffbf697d2ba3e7c21a91f57509b88f0e282ac39b16f56dcdba357c3`。不改门、不改历史；8363条warnings未逐条归因，不全称既有。历史4b的7663/17/1与Task2阶段366不作为本片最终统计。

全量输入记录HEAD f67baac9、tracked diff/3个未跟踪测试脚本原文tar、82条依赖freeze及1174项源码/测试/GUI/契约/配置SHA256；全部起止OK，依赖及tracked diff起止cmp=0。输入清单散列 `22c0f633636b49584a8d716efaab3a8cf18b0829435f279e9a1d98ecf78cca78`；依赖清单 `ba9a0540f4c051a1467bde7d78e17716f8edcd129120ae5731a4ed67fd459ca7`。运行后只有结果/状态文档收尾与C13现有UI操作，未改上述1174项输入；文档路由门另定点复核，不重复全量。pytest自身conftest会覆盖LOG_DIR为其临时目录，完整stdout/stderr仍由上述pytest.log留存。

文档结果/状态收尾后的G8定点：新库 `/tmp/pc04a4c-HIaYeu`，相同隔离环境执行 `.venv/bin/python -m pytest tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes -q`，exit1，1 failed/40 warnings，1.01s，仅同一历史文件/同一URL命中，没有新文档路由误报；后续只补该结果数字/来源及不含路由字面量的状态措辞，不改门的语义输入。

## 进程关闭与交付状态

首阶段API51610已定点停；最终API53789、npm/Vite51647/51670/51696及专用browser pc04a4c-task4均按记录身份关闭。自查C13补验只重启本任务API55124、npm/Vite55132/55155/55181和browser pc04a4c-task4-c13，补验后同样定点关闭；两批targets-after-close均仅表头、18096/5191监听复核为空。关闭日志、原库、venv、output和全部截图/SDD保留，未停止用户服务或删除资料。

Task4任务级已Approved（保留C07非阻塞P3）；累计唯一P1修复后限定独立复核为ADDRESSED。后续由主代理审查本轮文档增量，再按AGENTS外审规则判定是否进入Ready PR；当前未Ready、未push/PR/merge。本摘要不是外审回执，也不是4c合并或现场验收声明。

## 阶段校正与未验证范围

早期脚本原件保留在 `/tmp/pc04a4c-05M08A`：C02截图曾等待错误源行；C03误把合法负载终止也期望空；C04应422而非空列表；C07初次加入新的nominal值却误期望摘要不变；同名展示副本曾误作采集源；多active图/同秒排序曾让builder读另一图；旧批start缺header的阶段422不作为互斥/摘要证据；补证曾把individual摘要用于普通固定请求。最终新库已按权威对象/实际入口全部纠正，不是生产修复，也未将选择器或fixture错误冒称功能RED。首次23文件的2失败另按上述主代理裁决处理。

新声明不改变原资格、采用、期限、整链损耗公式、SCPI、原继电器协议域、BSE/CE口解释或ASC排序；无额外节点增益/重复补偿。模拟/脚本化transport的后端“real”fixture只证明拒绝/匹配/补偿逻辑，不证明真机采集。真实RF导通、真实功率/不确定度、证书与实物释放、现场B和4a遗留V1/ASC/CE边界均未验；4d旧转换、4e最终器件操作文档未启动。
