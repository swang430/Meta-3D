# PC-04A-4a 标称器件属性软件验证

## 状态与边界

**交付更新（2026-10-26）：** [PR #539](https://github.com/swang430/Meta-3D/pull/539)已于2026-10-26T14:29:23Z合并至`1207f8c547df3f253430cc8c84694343ff50aa71`；[R2回执](https://github.com/swang430/Meta-3D/pull/539#issuecomment-6418381233)覆盖`111e5126cd`且无重大问题。4a软件交付完成，当前4b计划审查。下述实施与R1阶段的“等待/未合并”措辞是当时记录，以下统计、失败历史和未验边界原样保留，不用后续合并状态改写测试证据。

本片实现类型化标称写入、原抽屉编辑和 CAICT 旧 PA 边定位；Task1 `690401a6`、Task2 `d4f44bfe`、Task3 `d2f9187a` 已分别通过独立规格/质量审查。Task3阶段原正式全量复验为 **7543 passed /17 skipped /1 failed**，唯一失败为已核对基线的历史G8误报，不称全绿。首轮另外三项采集前置异常后续未再现，根因未确认，不称已修复。原累计F1已由 `ba1ac371` 修复并经原reviewer确认ADDRESSED、累计内审Ready；V1非阻塞证据缺口按下节收窄声明。PR #539 的R1覆盖 `a087ed76` 后新增一条POST最终图校验P1，本轮已修复并完成相关/新库全量验证（见R1增量），等待原reviewer独立增量及R2覆盖修复提交；尚未合并交付，4b不启动。

全部结果仅为隔离 SQLite、真实 HTTP、真实浏览器与 Mock／脚本化 transport 的软件证据。不代表真机、物理端口能力、参考件计量认证、现场 B 或 HOLD 解除。标称数据不自动成为采用记录，也不新增补偿。

## 累计内审 F1 修复增量

累计审查输入 `d2f9187a394a6f21e1934ebde704e4483e51f454` 发现一个同根 P1：旧节点缺标称数值键时，仅改来源/频段会补 null，造成原采用失配、新执行从 confirmed_route 28 dB 退回旧证书 20 dB。现沿已有 `numberEdited` 收窄 GUI 写入：未编辑数值只更新 metadata，保留缺键、null、0及旧原值；明确输入/清空仍写 number/null。生产改动仅 `NominalPropertyFields.tsx` 与 `nominalProperties.ts`，不改后端摘要、资格、历史或补偿。原reviewer已覆盖修复提交 `ba1ac371de2cca53bb7e0eef5c3e7f4cef52b3be` 确认F1已解决、累计内审Ready；这不等于外审通过或合并交付。

- 新 RED：纯函数回归 **4 pass /1 fail**，失败为缺键被新增；原 Field→草稿→真实 PATCH 的浏览器 RED 明确报 `gain_db=null` 被补入。证据在 `output/playwright/pc04a4a-final-fix/`，不覆盖原证据。
- 新 GREEN：六类缺键节点分别只改来源、再只改频段，PATCH/GET/重载均保持数值缺键；参考 PA 边只改 metadata 同样保持缺键。节点明确0/清空、参考 PA 明确输入再清空仍为 number/null；旧字符串PA只改metadata仍为原字符串；取消无泄漏、真实离线保存失败保留草稿，恢复重试仍保形。最终全新库 **18 次 PATCH 均200**，`browser-final.log`/`browser-result.json` 保存请求、响应、baseline与最终GET。
- GUI相关回归 **49/49 pass /678.187625ms**；构建 **11.83s**，既有import/chunk警告保留。后端相关identity/compensation **39 passed /342 warnings /41.48s**。将真实GUI请求的标称片段映射到原脚本化transport fixture后，已验证所选普通探头的原摘要不变、preview可采用、新冻结仍confirmed_route 28 dB、旧冻结/原run/采用历史不改。**参考PA边仅有上项真实浏览器缺键/明确null保形验证**：重放fixture未建立calibration模式，`selection_snapshot.calibration_connection_ids=[]`，参考PA未参与所选参考身份，因此没有覆盖有效参考段身份及冻结；日志中的相同摘要/28 dB不能作为该覆盖证明。这是V1非阻塞P2证据缺口，本轮不扩测；以上均不是浏览器采集实测或硬件证据。
- 最终浏览器库 `/tmp/pc04a4a-8AUqR0/browser.sqlite`，两个开关均true且默认bootstrap；全过程未访问用户DB或停止用户服务。专用服务身份与停机记录见本次证据目录，原库和本次库均保留。
- 本次为影响面明确的局部GUI修复，没有后端生产、契约、测试或fixture变动；原四项后端canonical输入hash仍一致，原浏览器脚本只同步了旧坏值metadata保形断言，并新增本次浏览器脚本。故不重跑全后端，也不将原 **7543/17/1** 改称本修复HEAD的新全量结果。首轮 **7538/17/6**、三项前置异常未知根因、历史G8失败、ASC条件分支/CE未执行及B/HOLD边界全部保留。

## PR #539 R1：POST最终待存图校验增量

R1覆盖 `a087ed76ffa63840d14a4c10bd48d5f1dac6789e`，inline `4377906975`：POST在补out/in的完整模型上校验，却保存缺端口的稀疏图；真实HTTP复现201→正式resolver报“显式路径必须保存完整端口”→原样PATCH422。生产最小修复仅将POST原候选构造前移，使用原 `_validate_structure` 校验最终待存图，且早于任何默认位UPDATE；不补缺键、不改resolver/历史/资格。PATCH/import原校验已保留缺键语义，本轮以对称回归确认，不改其生产逻辑。

- 新增三入口×三种缺端口拒绝及三入口×完整显式/普通稀疏消费共15项真实HTTP测试；拒绝时无拓扑INSERT/UPDATE/DELETE、原默认位与行不变；完整显式和普通稀疏保存后由 `resolve_saved_rf_path` / `resolve_rf_chains` 消费，GET原样PATCH仍200。先RED **3 failed /12 passed**，修后相关 **182 passed /665 warnings /75.52s**。
- 本轮唯一新库全后端：`/tmp/pc04a4a-r1-full-gk69P2/full.sqlite`，应用导入前显式两个true开关、默认bootstrap；命令 `python -m pytest tests -q --tb=short -o log_cli=false`（使用项目.venv）。**7558 passed /17 skipped /1 failed /7438 warnings /596.76s**，exit1；新增15项全部通过。唯一失败仍为同一历史G8，已重核检查器/涉事历史/路由与原基线无差异，不改历史或门、不称全绿；原三项未知原因异常披露保留。
- 证据在 `output/playwright/pc04a4a-r1/`：`http-red-v2.log`、`repro.log`、`related-green.log`、`backend-full.log`、退出/起止文件；`full-input-head.txt`、两个输入diff和 `full-input-sha256.txt`保存BASE加本轮生产/新测试输入，结束后五项hash全部一致。随后仅更新不改变测试行为的本片状态/验证说明，不把原7543统计替换为本轮结果。
- GUI、依赖与API镜像相对BASE无变动，复用原GUI49/49和build11.83s，不冒称本轮重跑。V1有效参考PA身份/冻结缺口、ASC/CE未执行、Mock/脚本化transport及B/HOLD边界均未改变；本轮不补足这些未验范围。修复等待独立增量内审及R2，未合并不勾交付。

## 精确输入与环境（原Task3）

- 工作树：`restore-editable-topology/MIMO-First`，分支 `codex/topology-device-contract-design`；Task3 基准 HEAD：`d4f44bfe772000ea8aacd2aa3d477063b8ec7db1`。
- 后端相关输入修改 `tests/test_pc04a2_route_compensation.py`、`tests/test_pc04a4a_nominal_identity.py`，并经主代理核实对齐 `tests/test_pc04a1_topology_editing.py` 的旧pin响应断言，另扩展独立浏览器 fixture 与原浏览器脚本。没有生产代码、共享DB fixture、依赖、HAL／SCPI、补偿算法或门的变更。
- 本机证据根目录：`output/playwright/pc04a4a-task3/`。`task3-final-test-input.diff`、`final-test-input-sha256.txt` 保存全后端启动输入；`input-head.txt` 为基准 SHA。后续只有浏览器证据补充与不作为测试输入的本片文档状态，不把它们冒称原提交内容。
- 浏览器库：`/tmp/pc04a4a-TUI8rw/browser.sqlite`；后端相关库：`/tmp/pc04a4a-related-krOzw5/related.sqlite`；首轮全后端库：`/tmp/pc04a4a-full-4MECTd/full.sqlite`；契约对齐后正式复验库：`/tmp/pc04a4a-full-final-eMTjE6/full.sqlite`。均由本片新建，未复制用户库；所有库、日志、venv、scratch 保留。
- Node `v26.5.1`、npm `11.17.0`、Python `3.13.14`；FastAPI `0.141.1`、Pydantic `2.13.4`、SQLAlchemy `2.0.51`、pytest `9.1.1`、pytest-asyncio `1.4.0`。

fixture 在应用导入前检查新 SQLite 路径、文件不存在、父目录存在及 `USE_MOCK_INSTRUMENTS=true`／`BOOTSTRAP_ON_STARTUP=true`；保留默认 bootstrap，随后所有类别与 Lab bindings 再断言 Mock。CAICT 旧图经真实模板导入端点创建。`fixture.log` 保留完整 manifest，两个 Lab 使用独立暗室；没有访问或停止用户 8000/8001 服务，没有启动 CE 服务。

## 真实 API 浏览器矩阵

专用服务为 API `127.0.0.1:18094`、Vite `127.0.0.1:5189`，所有测试代理都指向 18094。执行沿用 Playwright CLI，非前端 mockServer，不伪造 HTTP 响应。分阶段通过 `?nominalStage=<阶段>` 调用同一 `gui/test/pc04a4aNominalProperties.browser.js`；每阶段结果归档完整 request／response、GET、重载 DOM 与截图，不以 toast 当落库证据。

| 场景 | 实际证据与结果 |
|---|---|
| 新 PA | 原新增菜单创建、明确 in/out；空→0→21.25→负值；来源 trim／空来源 null、单位 dB、频段 [2500,2700]，每步 PATCH／GET／重载恢复；`node-amplifier.log` |
| pad／combiner | 0、正值、清空 null 保存；负值、半频段、倒序禁用应用，修正后可保存；`node-pad-v2.log`、`node-combiner.log` |
| antenna／probe／reference_antenna | 正、负、0、null；原探头编号/极化、连接/显式引用和正常/校准模式均保持；`node-antenna.log`、`node-probe.log`、`node-reference_antenna.log` |
| CAICT 旧 PA | 精确 `conn_ce_b1_to_hprobe_1v` 原典型20→0→−1→null；每步保存/GET/重载；空来源为 null，未新建 PA、未改其它边/节点/模式或 chamber；`caict-pa.log`。原定点脚本还覆盖0值清单、非当前模式精确ID定位高亮不切模式及数值声明事件 |
| 旧天线/数量徽标 | 旧15/3 dBi 仍标旧版标称、非实测；CE/EMCenter缺数量不回退4/32、明确0不回退且只称未核实旧声明，无固定PA×32；`legacy-v4.log` |
| 旧坏 PA | 原Task3输入下字符串 `"12"` 可读、来源编辑要求先修正/清空；这是原 `legacy-v4.log` 的历史行为。累计F1修复后仅改metadata允许保留原字符串，新验证见上节；明确改数值仍严格校验 |
| 线缆/接收线缆 | 节点提示去相邻边，无第二数值存储；真实曲线点击参考稀疏边只改来源，GET仍不补 cable_loss/PA 默认键；`legacy-v4.log`、`cable-source.log` |
| 无关旧图操作 | 未声明标称的线缆只改名与真实鼠标拖动，位置实际落库/重载，params、其它边及模式保持；`legacy-v4.log` |
| 取消/失败/跨Lab | 来源取消不改草稿/GET；真实离线保存失败保留草稿，恢复后重试/重载准确；dirty切Lab拒绝、手发跨Lab PATCH=409且双图不变、清洁切乙无甲节点；`recovery-v5.log` |
| 保存/采集锁 | MutationObserver只观察真实保存窗口，定位/器件/保存均禁用；真实采集 pending 窗口全部定位编辑/拖动/保存锁住，结束后恢复；`cable-source.log`、`collection-v5.log` |
| Mock/取消 | 两次原采集入口真实POST；第一条 simulated、net_loss=null、samples=[]、formal_eligible=false，UI禁用采用且服务器采用POST=422；第二条真实取消POST落库cancelled，新控件/应用恢复，历史两条保留、采用历史为空；`collection-v5.log` |
| 引用保护 | 删除仍被探头显式路径引用的CE节点，原生确认后拒绝并保留局部输入/草稿/GET；非引用天线原生确认后可删并保存/重载；`references-start-v6.log`→`references-reject-v6.log`→`references-middle-v6.log`→`references-delete-v6.log`→`references-final-v6.log` |

各行成功日志均含 `### Result`，最终引用结果不是“弹出确认即退出0”。截图使用 `animations:'disabled'`；已人工查看新PA 21.25的抽屉渲染。浏览器开始的 Task2 定点重跑 `browser-targeted.log` 退出0，但其函数只 console 输出，完整结构化落库材料以后续上述矩阵日志为准，不将只打印脚本本身的日志当 JSON 返回值。

`matrix-index.jsonl` 是12阶段Result的结构化索引；`browser-final-get.log` 为关闭服务前两个Lab的最终真实回读，`final-storage-index.json`核实甲保留simulated/cancelled两条、net_loss=null/samples=[]/formal_eligible=false，乙历史为空。专用CLI浏览器与API94592/Vite94652/npm94626均已关闭，随后确认18094/5189无监听；`service-identities.log`与`services-stopped-at.txt`保留身份和时点。旧Task2数据、普通用户服务未动。

前期脚本失败均保留：一次内联CLI语法错误、0声明样本缺 visible_modes、Drawer焦点恢复和短ID模糊selector、引用保护最初选了被删探头自身。只修测试输入/selector：旧0样本通过真实PATCH补测试可见模式、不清库；改成精确option value、等Drawer退出；保护场景改选仍被另一节点引用的CE。原生confirm分阶段由CLI接受，不重写window.confirm。这些不作为产品RED，不回退共享代码补造RED。Task2既有缺控件RED与变异证据仍保留在原目录。

已知非本片新增噪声：CAICT旧图 route-calibration-paths 422、开发时 React DevTools提示，以及既有构建动态/静态import和大chunk警告。未借本片改旧图/清警告。

## 校准隔离与回归

后端相关命令（cwd=`api-service`，每次应用导入前显式设置上述新库、两个 true 开关与独立 LOG_DIR）：

```sh
.venv/bin/python -m pytest tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc04a3_topology_recovery.py -q
```

退出0，`backend-related.log`：**172 passed / 1080 warnings / 165.37s**。该轮开始后新增的“采用后元数据”测试另外在新临时库运行，不冒称已被172覆盖；`backend-new-metadata.log`：**3 passed / 57 warnings / 3.14s**，退出0。

- 纯 TopologyService：边损耗2/0与新增gain=20、attenuation=3、gain_dbi=15及旧PA=20，总损耗/矩阵不变；已有calibrated_loss=0仍优先为0。
- 复用原真实生产采集/parser/builder/确认/冻结/补偿链，只替换外部transport：原 `want` 28或−12保持一次，端口、方法、参考面、来源不变；不把脚本化transport称真机。
- 本轮未设置 `CHANNEL_ENGINE_PATH`，上述既有测试的条件分支 `assert_final_loaded_asc` 未执行；验证到原补偿 entries/冻结/采用消费者，不宣称本轮实际调用CE服务生成/加载ASC或完成硬件波形验收。
- 先建立受信transport采集/采用与旧混合证书，真实HTTP仅改metadata后preview仍可采用、新执行冻结同值同来源；旧采用快照、原始run与旧执行冻结不改；真实接线端口变化仍拒绝。

GUI（cwd=`gui`）：

```sh
env TSX_TSCONFIG_PATH=tsconfig.app.json npx --yes tsx --test test/nominalProperties.test.ts test/topologyDraft.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
env TSX_TSCONFIG_PATH=tsconfig.app.json npx --yes tsx --test test/topologyNominalTransport.test.ts
npm run build
```

分别退出0：**45/45 pass**（716.618292ms）、**3/3 pass**（1272.070041ms）、构建 `built in 15.67s`。日志为 `gui-related.log`、`gui-transport.log`、`build.log`；不把48项GUI称完整浏览器或全后端。

## 最终全后端

唯一责任人 Task3；两轮全量均独立新库、串行执行。先保留首轮实际结果，再按主代理批准的pin契约对齐进行一次正式复验，不无限重跑择绿。首轮命令：

```sh
env DATABASE_URL=sqlite:////tmp/pc04a4a-full-4MECTd/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4a-full-4MECTd/logs .venv/bin/python -m pytest tests -q
```

首轮退出1，**7538 passed /17 skipped /6 failed /7419 warnings /774.06s**（7561项）。其中两项旧默认pin响应断言与本片已批准稀疏契约冲突，经主代理独立核实后只对齐该测试：缺键存储/GET保形、schema有效默认out/in、显式坏pin422且原子不改；新库定点 **2 passed /42 warnings /0.47s**。其余三项在原采集fixture开始前失败（两项tuple index out of range，一项Lab不存在/停用，均零exchanges），另有历史G8。采用资格4项、批校准1项独立复现，以及257项full顺序、13项迁移前序、30次采集重复+4迁移共34项诊断均通过；尚不能只凭复跑通过确认根因。只读pool观察证明同一StaticPool DBAPI连接曾同时被两个Session checkout，是否为首轮三项的直接原因仍在核验，不改生产资格/锁。当前不能作为最终通过证据，不能以G8豁免其它失败。

首轮结果保存于 `backend-full.log`、`backend-full-exit.txt`、`full-failure-summary.txt` 与 `full-start.txt`／`full-end.txt`；诊断日志为 `pins-reproduction.log`、`pins-aligned-green.log`、`eligibility-reproduction.log`、`batch-reproduction.log`、`sequence-diagnostics.log`、`migration-order-diagnostics.log`、`repeat-diagnostics.log`、`pool-observation.log`。输入稳定后另起新库最终全量并保留首轮，不引用旧片7485统计。

主代理裁决不改共享fixture：双checkout尚不足以证明首轮三项异常根因；不能写成已修复。仅已批准pin断言对齐后的正式canonical复验，无诊断plugin、不改三项资格断言/生产，命令如下：

```sh
env DATABASE_URL=sqlite:////tmp/pc04a4a-full-final-eMTjE6/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4a-full-final-eMTjE6/logs .venv/bin/python -m pytest tests -q
```

输入存于`task3-final-canonical-input.diff`、`final-canonical-input-sha256.txt`；命令结果存`backend-full-final.log`、`backend-full-final-exit.txt`、`full-final-start.txt`／`full-final-end.txt`，不以诊断plugin的回归替代本次正式全量。

正式复验退出1，**7543 passed /17 skipped /1 failed /7423 warnings /628.35s**。首轮两项pin断言已按批准契约对齐并在full通过；另外三项本轮full均PASSED，未修改其断言、采集资格或共享fixture，仍记为“首轮出现、修后复验未再现、根因未确认”。唯一G8与下述基线同一条。复验结束后五个应用/测试/fixture/浏览器输入SHA256全部检查OK；此后只有不参与后端测试的本片文档状态更新。`node --check`、`git diff --check`均退出0。Task3及累计独立审查现已完成，F1修复经增量复审通过；Ready仅指可进入PR/外审，不将本文或作者自查当作独立审查证明。

G8定点 `g8-current.log` 已退出1：旧历史报告 `docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md` 的真实执行UUID路由被当作路由形状未命中。与基线 `710f55a3f65f70c8cc593003e501fcf8e2204739` 比较，检查器、涉事历史、main路由注册及test_plan路由文件均无差异（git diff --quiet退出0）；历史写的就是当时真实422执行，不应改历史或门来造绿。该次正式复验仍仅此失败，实际统计按上文保留，不能称“全绿”。
