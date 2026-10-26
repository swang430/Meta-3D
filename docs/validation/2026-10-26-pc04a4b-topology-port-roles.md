# PC-04A-4b 端口清单与角色验证

## 结论与边界

本片应用层综合验证已完成：相关后端469通过，GUI77通过，构建成功；唯一最终全后端 **7663 passed /17 skipped /1 failed /7579 warnings**，退出1，唯一失败为基线未变的历史G8，不能称全绿。等待独立审查及后续 PR 外审；4b 尚未合并，不勾选完成。

本片验证的是应用层端口清单、角色、画布和写前校验的一致性，不证明硬件端口能力、内部通路、真实测量或校准采用资格。4c/4d、父项、现场 B/HOLD 和 4a 未覆盖的 V1/ASC/CE 边界保持原状态。

实现输入为分支 `codex/pc04a4b-topology-port-roles`，基准 `a7961b919ba0dec6fe42ccbd61702ce2d8803fc9`，叠加本任务最小修复：移除/改名端口的错误消息一次列出所有跨模式引用边，不改变拒绝条件，不删除接线或路径。新 `port_directions` 沿既有 params 参与新摘要；未改冻结、采用、补偿算法或任何 SCPI。

## 隔离与证据身份

- 主浏览器库：`/tmp/pc04a4b-abjBpI/browser.sqlite`。导入 app 前已设置新 SQLite、`USE_MOCK_INSTRUMENTS=true`、`BOOTSTRAP_ON_STARTUP=true`；fixture 检查路径、父目录和文件不存在，执行默认 bootstrap，再确认所有 category/Lab binding 均为 Mock。地址使用文档网段 `192.0.2.0/24`。
- 主 Lab 甲：`97cbbd2c-4e1d-4cb2-b366-e2c1a4d76eb1`；暗室 `cff203ff-e89b-4b68-83ce-a21b2e5e16ec`；初始真实 POST 图 `7621fa9b-4706-4762-94a8-3fb2dea0db50`。组合 POST 的各图均保留；为继续按“最新图”显示的编辑器流程，另经真实 POST 建立同 fixture 的合法副本 `7c173589-be52-41ad-ab51-47708ef6728a`，不复制用户数据，旧非法边样本仍在原图。
- Lab 乙：`cf42b6b3-e423-4bb1-a6c2-b599e83e415d`；独立暗室 `8ae0a19b-4089-4c37-991c-31ae9521e06e`；真实 `caict_v4` import 图 `edddf2dd-d17b-4d5d-956c-1be08652559c`。没有转换或批量补齐该旧图。
- 补充历史无边样本库：`/tmp/pc04a4b-NChXC2/browser.sqlite`；fixture 开关 `PC04A4B_LEGACY_UNDECLARED_FIXTURE=true` 明确构造 `legacy-default-pad`，不是 CAICT 原节点。甲 Lab `04252d4f-9c3a-47ad-8605-db65556eae5e`，图 `2287f2fa-8790-4f2d-ab8d-ca11d5338e1e`。
- GUI `5190` 的 `/api`、WebSocket 和更具体 OTA 代理全部指向本任务 `18095`。只运行 API/Vite，未启动 CE 服务、未调用 OTA 硬件执行接口、未接仪器、未使用默认数据库。请求不使用 route mock/伪造响应；离线测试仅改变真实浏览器网络。
- 可重跑脚本：`api-service/tests/pc04a4b_browser_fixture.py`、`gui/test/pc04a4bMatrix.browser.js`、`gui/test/pc04a4bDirectionMatrix.browser.js`；原始请求、响应、GET、DOM 和阶段截图分别保留在各临时目录日志及 `gui/output/playwright/`。下表包含实际结论，不要求读者仅凭本机截图推断通过。

## B01～B13 实际矩阵

| 项 | 实际结果 | 证据与限制 |
|---|---|---|
| B01 | 14 个原新增选项逐个未声明保存 422，明确 A/B 后保存/GET/重载；原 19 类（含旧 ce/bse/sa/switch、天线）另做候选/鼠标几何 | `B01-attempt1.log`、`geometry-attempt2.log`。数量来自唯一 ID；BSE 显示逻辑端口，空气显示虚拟端点，未生成内部通路 |
| B02 | 同 ID 的 input/output/bidirectional/unknown 连续应用、真实保存，source/target 数量分别 0/1、1/0、1/1、1/1，无隐藏同 ID 旧 handle | `B02-attempt1.log`；unknown 文案保持“非双向能力”；19 类真实连线端点与已有可见 handle 屏幕误差≤3px |
| B03 | 16 种真实 POST 组合为 9 接受/7 拒绝；真实 UI 16 组合中9种鼠标拖线/抽屉候选/PATCH/GET通过，7种不暴露所需非法方向handle且直接PATCH422、GET不变 | `B02-attempt1.log`、`directions-final4.log`、GUI77/77。相同方向的不同命名ID不合并；unknown边无实心流向箭头；禁止组合没有虚构不存在的handle去“拖线” |
| B04 | RF5=dl 仍输出、UL1=ul 仍输入，名字 DL1 未声明；反向通用 map 422 且 GET 不变 | `B02-attempt1.log`。只读 physical display 不补值，不修改运行映射来源 |
| B05 | 旧 CAICT 仅改名/位置/PA来源保存重载，旧缺声明、数值、其它边和节点 params 保形；已有显式 ports 未改而应用器件修改不重写声明 | 主库`B05-attempt1.log`、补库`position-final.log`（仅位置为真实API PATCH/GET/重载抽屉，不冒称鼠标拖动）。缺ports且相邻未声明时明确应用如实拒绝并保留草稿；版本提示不是转换；稀疏参考JSON与旧digest往返另由后端回归覆盖 |
| B06 | 删除 probe 的 in/out 时一次列出正常 fixed-v 与参考 reference-0，拒绝后旧草稿/服务器不变；独立历史无边样本显示默认恰为in/out，点击“应用端口声明”后PATCH/GET/重载确有显式ports | `all-references-red.log`→`all-references-green.log`、`B10-attempt3.log`、补库`legacy-final.log`。旧opaque保留，不注入unknown map，不以CAICT的拒绝冒称同值成功 |
| B07 | 加 NEW 端口/替代边→探头抽屉重声明 replacement-v→UI保存→删除旧 fixed-v/旧 out 口→服务器重选新路径；错误路径引用 422 | `B07-attempt3.log`。映射失败/缺失原门另有固定、批任务与选择回归；没有授予内部通路/自动开关许可 |
| B08 | 普通 ce_port 与参考 reference_antenna 的新 map 均改变 route_digest；旧 selection 真实 POST 422，重新选择新服务器候选；旧三份记录 result/冻结 snapshot 逐字不变 | `B08-attempt4.log`。不是客户端计算摘要；Mock采用仍422 |
| B09 | 非法 default POST、部分 nodes PATCH 均422，跨 Lab PATCH409；甲乙 GET 不变，SQLite直读前后快照 cmp 一致 | `B09-final.log`、`B09-orm-before/after.json`。非法已注册模板 replace 原子性由真实 TestClient/ORM 用例覆盖，没有给线上 API 加模板注入接口 |
| B10 | 抽屉取消不泄漏，已应用角色与4a来源不被后续取消抹掉；离线保存失败保留，422更正重试后GET/重载一致 | `B10-attempt3.log`。保存 pending 的 MutationObserver 实际捕获输入/按钮冻结、无可拖/连接节点，不延迟或伪造保存响应 |
| B11 | 两轮真实202/running；离线取消尚无回执时保持图/模式/增删/拖线锁；收到服务器终态才释放，两次均恢复普通/BSE编辑，任务数量恰增2 | `B11-attempt3.log`。第一轮离线取消可能排队，未把按钮点击称停发；第二轮实际POST取消并落库cancelled。Mock损耗null、样本空、formal_eligible=false |
| B12 | dirty切 Lab 被阻止；清洁甲→乙→甲恢复声明与图，角色/4a意图不串；在校准模式仍保护正常边引用 | `B10-attempt3.log`。未宣称控制台零错误，保留预期离线/422及跨Lab旧查询409 |
| B13 | 普通/参考新 map 前后正常损耗投影及校准矩阵相同、历史快照不改；所选正常/参考通路全unknown与全明确两图均真实采集simulated、损耗null、样本空、formal_eligible=false、采用422 | `B08-attempt4.log`、`states-final4.log`、18文件469通过。两图均保留BSE已有权威role：通用unknown不覆盖dl/ul；补偿/冻结未改，不据新map生成passed |

### 证据偏差及中间失败

Task 2 的首次 RED 截图被覆盖，主代理已接受原 RED 日志/DOM 与实现后基线复证的明确披露。后补截图不是首次原件，本任务没有回退工作树补造历史。

本轮中间失败日志均保留：多选输入为隐藏 input，改用原键盘操作；替代边须先纳入当前模式才会成为路径候选；同一 Select 重复点击会取消选择，改为明确先选 H 再选 V；损耗比较排除合法改变的 source_node.params，只比路径身份与损耗/相位/校准状态；几何在连线后重新读取真实屏幕坐标。无边组合fixture须明确visible_modes；SQLite创建时间精度为秒，连续POST前等待真实下一秒，避免列表同秒顺序歧义；终态改用实际HTTP轮询，不依赖浏览器求值句柄返回形态。这些是脚本/fixture校正，不冒称新增产品修复。唯一生产修复是引用消息首项截断，纯函数定点 RED 确认旧消息只有 normal-in，修后一次含 normal-in/reference-out。

## 回归命令与当前结果

cwd=`gui`：

```bash
npx --yes tsx --test test/topologyPortContract.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

实际退出均0：`77 tests / 77 pass / 0 fail / 1070.279792ms`；tsc/Vite 成功，`7836 modules transformed`、`built in 13.25s`。保留动态/静态混用与大 chunk 警告，不称 pristine。

cwd=`api-service`，新库 `/tmp/pc04a4b-FXzeth/related.sqlite`：

```bash
env DATABASE_URL=sqlite:////tmp/pc04a4b-FXzeth/related.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4b-FXzeth/logs .venv/bin/python -m pytest tests/test_pc04a4b_port_contract.py tests/test_pc04a4b_port_identity.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc_04a_fixed_route_acquisition.py tests/test_pc_04a_fixed_route_api.py tests/test_pc06a1_batch_jobs.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_plan.py tests/test_pc06a1_batch_safety.py tests/test_p1_73a_base_station_topology.py tests/test_rf_chain_resolver.py -q
```

实际退出0：`469 passed, 1474 warnings in 290.18s`。包含真实选择/历史冻结、Mock资格、缺绑定、固定采集、批任务、采用、基站映射、补偿一次性及4a保形回归。警告数量照实保留，不未经核验归为全部既有。

唯一最终全后端在新库 `/tmp/pc04a4b-eQkBA8/full.sqlite` 已完成，退出1：`7663 passed, 17 skipped, 1 failed, 7579 warnings in 615.72s`。本轮实际统计，不复用4a的7558/17/1。

```bash
env DATABASE_URL=sqlite:////tmp/pc04a4b-eQkBA8/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4b-eQkBA8/logs .venv/bin/python -m pytest tests -q
```

唯一失败为`tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes`，命中历史`docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md`中含具体UUID的执行URL。已核实门与该历史文件相对基准`a7961b91`无diff；历史文件当前与基准SHA256均为`57aaf7726ffbf697d2ba3e7c21a91f57509b88f0e282ac39b16f56dcdba357c3`。不改门、不改历史，不因属旧失败称全绿。7579条warnings未经逐条归因，不能全称既有。

依赖：Python3.13.14、pytest9.1.1、FastAPI0.141.1、Pydantic2.13.4、SQLAlchemy2.0.51、httpx0.28.1、uvicorn0.52.1；Node26.5.1、npm11.17.0。完整依赖清单 SHA256=`b22f9ea3081a08af8c77eadb5e17e1205c8deb562cfdb688ee775fb1b30d5d30`。全量启动时 backend文件清单 SHA256=`63cce8d73c5748a24d6cf59f649ead4df58afd4a9bc4aefb950e629243a483e3`。

全量起止文件散列逐项比对，唯一后端目录差异为浏览器非收集fixture增加独立历史无边分支：`032d591eb1571f6079e314087aa0b9d2f0799bee1fb12080afcd1b1a230dd91a`→`2c6b2177de2a2438475c45f0544056b6587519138bb50187dc8fd84673197b36`；`test_*.py`/app未引用该模块，未改变全量的生产/收集测试输入。该分支已在补库单独执行，不冒称在pytest全量中执行。其后只有浏览器脚本及状态文档补齐，无生产/收集测试/依赖改动；由主代理独立核对结果复用。
