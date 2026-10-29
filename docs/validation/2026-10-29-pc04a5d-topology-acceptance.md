# PC-04A-5d 综合软件验收摘要

日期：2026-10-29。批准范围是已交付拓扑库/修订恢复/独立PA的组合软件验收与[恢复指南](../guides/topology-library-recovery.md)，不是产品新功能、用户库部署或现场验收。本片**未跑新版全后端**；没有生产/shared fixture/schema/依赖/生成契约变化，不触发条件全量。Task3是唯一条件全量责任位，若后续共享输入改变，须重新判档并先由主任务确认旧脚本transport测试的无外部I/O例外，不能偷偷切real。

Task1最终 `4b5a2917`、Task2 `1eedefafa786c9305de556113b2df1be41435cfc` 已独立规格/质量 Approved；Task3及累计审查、Ready PR外审/合并由主任务继续，本摘要不代签。文档门真实结果见末节，不称全绿。旧5c的8146 passed/17 skipped/3 failed仅为[前片参考](2026-10-28-pc04a5c-independent-pa.md)，不是5d统计。

## 1. 身份与证据分层

所有5d写验收用新临时SQLite，app导入前 `USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true`；bootstrap后逐类别、连接、每Lab非空binding回读Mock，endpoint192.0.2.10，实际HAL经生产is_mock_driver核七类Mock并shutdown。没有连接默认PG、8000/5173或用户仪器，不改原CAICT和用户PA副本，不新做其备份或重启。

用户源/副本定位与5c交付依据见[指南](../guides/topology-library-recovery.md)。5c部署回执 `output/pc04a5c-deployment.md` 是本机资料、未作为公开附件发布；5d不重新核其现状。仓库可追踪[PR547](https://github.com/swang430/Meta-3D/pull/547)和5c validation。

以下本机证据路径不是远程下载链接，也不保证/tmp永久存在；未嵌未跟踪PNG。已跟踪的[Task2回执](../../.superpowers/sdd/2026-10-29-pc04a5d-topology-acceptance/task-2-report.md)保留原始命令、退出边界和逐分支截图名。

| 证据组 | 本机位置与身份 | 使用边界 |
|---|---|---|
| A 早期相关集 | `/tmp/pc04a5d-idnQIt/receipts/attempt-20261029T012345-7819724d/`；每例JSON内manifest/HTTP/raw全列；`task1-related.log` | 输入test SHA5b206eaa…，不是最终测试文件；279/4deselected结果仅属当次 |
| A2 收集修正后 | `/tmp/pc04a5d-LTOz6l/`；17世界JSON/DB已逐字节归档到 `/tmp/pc04a5d-AmYHpZ/pytest-356/` | 18例定点输入60a398f6…；34文件清单SHA48d93265…已独立核同 |
| S 最终synthetic | `/tmp/pc04a5d-unuf7u7i/test_d11_d12_synthetic_saved_confirmation_once_and_history_immutable.{json,sqlite}` | 输入ae0122d3…的一例；已存历史/零I/O冻结，不是新实测 |
| B 真浏览器 | `/tmp/pc04a5d-ItdcnV/`；完整保留副本 `output/playwright/pc04a5d/evidence-ItdcnV/`，截图在其父目录 | 每attempt输入/HTTP/结构化error/截图SHA见receipt-index.json；最终源码hash不冒充早期attempt输入 |

浏览器世界B的完整UUID：

| 对象 | UUID / 最终修订 |
|---|---|
| source | `f6d60fdf-e102-4150-82b4-03c86a66de60` / r0、history0 |
| 普通副本 | `925453b7-e99e-414b-bdde-d2a99c9cbe4e` / r4 |
| PA副本 | `6ebf965d-9f10-4171-b9a2-d53e00c3681f` / **r9** |
| collection | `83e7a0d0-9e0a-4e63-93c5-72c336acee9e` / r2 |
| 端口练习图 | `e0f9c807-aad9-43b7-be14-51cc4d0d67e8` / r6 |
| Lab A / A共享 / B | `24ef3811-cd4a-4cc8-86f5-d12c6b4a573c` / `b1f8f7e5-a839-4251-b715-4a28e6e26306` / `d0252874-5a98-4a21-aaea-9f1fc19a2cf2` |
| A共享chamber / B chamber | `847744e9-dedf-4d93-9ad8-abaf5b8389cb` / `8655be80-68bb-4d5c-80a3-1167091ef16d` |
| rfSwitch category | `c208809d-a150-427f-a37d-483901f89aba` |

S世界：声明图 `fe470e51-0c1d-45ca-bd7a-fd856d3092f8`；synthetic历史run `f030ec45-e449-4c99-9d34-42e69127be10`，Application `724362cd-0423-4431-812a-6194f5f041ea`，Selection `1669e1de-8397-4c31-98a8-8994ec03fb82`。E1 `e8fa621e-fc41-4707-a3b2-59c1f900f7ae`、E2 `68f9d4d0-e5d5-493d-8874-e6ba068b0941`、E3 `90daba02-794e-4d86-a360-2925acacf209`。它们不是B世界采集run，也没有在B库播confirmed。

## 2. D01～D12分支矩阵

“新验”表示5d实施阶段取得；“复用”表示Task3只读引用已审原件、不重跑；未验/失败单列，不把部分成功整行写PASS。A/A2中每用例UUID不同，准确值在同名JSON的manifest/http与归档DB，不跨世界拼接；S和B上表为本摘要明确引用身份。

| ID | 新验入口、权威源与实际证据（Task3复用） | 未验/失败/限制 |
|---|---|---|
| D01 | A/A2 `test_d01_copy_rename_keep_source_raw_and_execution_choice`：copy201/r1、新UUID/inactive/nondefault；name PATCH200/r2，updated_at不变；raw/修订/Lab全列保护，orchestrator/resolver仍原图。B `D01-attempt1.txt`同名图按短ID复制、命名并回读 | CAICT本身calibrated均null；非null清空/缺键不补由同次279里的旧5a `test_copy_preserves_raw_except_calibration`补证，不冒称新例覆盖非null。B全列SQL基线采在D01后；复制前全列/正式resolver关联A，B只另有复制前后DTO/raw比较 |
| D02 | B `D02-attempt3.txt`：设置本浏览器默认→重载自动选普通副本；独立context键为空；清洁切回source。A正式选择不变 | localStorage按Lab/category；不是跨浏览器默认、不是执行选择/激活证明 |
| D03 | B合法PA图 `D03-pre-attempt3.txt` / `D03-check-cancel-attempt3.txt` / `D03-save-attempt3.txt`：属性实改dirty、范围守卫；原生取消保留，确认放弃无写；另保存r5、重载值一致 | 原raw副本缺ports不作编辑成功载体；attempt1误判Lab必须disabled，attempt2原生modal无结构化结果不计通过 |
| D04 | A/A2 `test_d04_d05_legal_r2_restores_as_r4_but_r1_rejected_without_writes`；B `D04-attempt1.txt`：copy r1→候选PATCH r2（准备，不冒充鼠标改接）→鼠标位置r3→r2 preview200零写→勾选恢复200/r4；r4 raw=r2，r1～r3不变 | 恢复不授校准资格、不改active/default；后续PA到r9，不能只报r4 |
| D05-r1/token | A/A2：r1 detail200，preview/restore422均零写；PATCH/preview/restore旧令牌409、缺令牌422六分支。B `D04-attempt1.txt`只新验r1 preview422 | B没把restore422另冒新浏览器验证；真实两入口拒绝引用A/A2 |
| D05-409 | B `D05-attempt3.txt`：B页先dirty，A页命名200，B旧token PATCH409后草稿/输入/放弃按钮保留；只读核对不采用、取消不覆盖；旧restore409零写 | attempt2误传target_revision得到422，不混称409成功 |
| D05-unknown/pending | B `D05-unknown-attempt3.txt`：真实restore已写后GET abort，组件unknown挡编辑/拓扑写；跨SPA新GET服务器r9无重发。`D05-pending-attempt1.txt`：真PATCH在途跨卸载beginWork守Lab，回包落定后重入标签已保存、写次数1 | unknown早期两attempt实际restore也落库，不能称零写。数据库dirty/unknown不跨SPA持久；和硬件采集unknown不混同 |
| D06 | A/A2共享chamber同记录，不同chamber七入口409且raw/history不变。B `D06-attempt5.txt`共享数据但Lab偏好分开，旧A list/detail原样200且delivered=true，切B后未夺选择/弹旧核对框 | attempt2异步库未就绪，attempt3/4过早unroute，attempt4虽error:null但未投递，不计迟到响应成功 |
| D07 | A/A2 `test_d07_d08_complete_32_routes_and_unknown_nominal_consumers`：保四条BSE→CE完整输入、原/候选32身份集合与manifest独立期望全等，TopologyService各32路径；B `D07-attempt3.txt` B1/B16/B32 UI加SQL全32路映射 | UI三处不是32路证明；inactive副本不自动用于正式执行，source正式resolver仍原图 |
| D08 | A/A2逐32输出子图64边、PA唯一in/input→out/output pair、loss null/length缺键，path/末边/matrix None；0独立小图仍0。错pin/反pair/缺边四例422零修订；CE矛盾PATCH200后正式_build_probe_binding抛“完整通路中的CE输出口声明互相矛盾”。B SQL/DOM 20标称来源未核、opaque旧.8/5不重复补偿 | 保存不等执行；输出子图不冒完整图；gain20不加量值；控件0不当落库值。首轮3失败含两测试假设和CE保存门假设，未改生产造绿 |
| D09 | B `D09-attempt5.txt`及`D09-visual-visual-attempt1.txt`：唯一DOM Handle/boundingBox，鼠标down/move/up真连两边，save/reload/SQL/mimo_ota active_connections/完整二跳path一致；out→out无新dirty/写入。边UUID `856abe89-7ac5-4f90-a251-781fedf03984`、`93476ddd-3dbb-4348-8396-3d189cee1a10` | 独立练习图非32路图，inactive不可采集。早期中断/空结果/关闭Drawer/原生确认不计通过，但准备已产生修订，最终r6不称零写 |
| D10-两轮 | B `D10-1-attempt1.txt`、`D10-2-attempt1.txt`：真实start202、辅助GET确有running、同run真实租约取得/释放；第二轮DOM cancel真实200；GET未知锁、跨SPA采集锁、显式终态→编辑保存/重载/重入，不自动重发 | 两主run及lease见下表；延迟回包本身不代running。Mock simulated/cancelled不证明实物停发/cleanup |
| D10-补证/拒采用 | B `D10-lock-target-attempt1.txt`第三run单补Lab/恢复实际守卫；`D10-history-attempt3.txt`和`D10-history-visual-attempt1.txt`实际Mock历史preview200/new_net_loss=null/simulated阻断，采用按钮disabled。A/A2两轮真实确认POST422、Application/Selection零写 | 第三run不充前两轮。早期脚本按钮名不存在，不能用空locator证明禁用。真实采用资格未验 |
| D11 | S：真实route-calibration-paths→RouteSelection→明确synthetic已存ORM历史→真实factory/freeze→ChannelEngine消费者。E1/E2 source_kind=confirmed_route/value28；consumer各port1 cable_loss28/probe_gain0，恢复后仍一次，不叠20/两边/99 | DTO measurement_provenance=real只是历史输入形态，run success=false、params/sequence_evidence synthetic、无伪交换/样本；不证明新确认接口成功或实测合格；B无confirmed展示冒称 |
| D12 | S：name保存/restore后E1冻结和Diagnostic/Application/Selection全列不变，E2当前28；真实source_pin改other后E3 unavailable/null，旧E1 identity检查拒、旧冻结不回写 | ProbePathLossCalibration为0行，仅证明空表未写，不宣称非空旧证书保形；没有实际运行仪器执行/正式报告下载 |

| B run用途 | run UUID | lease_id | 终态 |
|---|---|---|---|
| 第一主轮 | `c2e0c849-01ed-4dd9-ac71-2a9984b0b350` | `4d43f7cb2eb9421cab872d3e6ee097c2` | simulated |
| 第二主轮 | `c27b66c0-3e57-44ef-8ec4-9cb759377036` | `77380bd2674c4d6796a6c4042846abc9` | cancelled |
| Lab/恢复守卫补证 | `c3fb9735-8574-4f7a-a5b6-31857c860267` | `3a297b95a2774a80a9065f9a1431288f` | simulated |

B SQL终态：DiagnosticRun3、Application0、Selection0、TestExecution0；三run均samples=[]、net_loss=null、cleanup_confirmed=null，F64 control release未知。B原图raw等跟踪fixture；相对D01后全列基线，source/Lab（含bindings）/category/connection保持。PA r1～r9全留，r2=r4。软件锁证明不推广为现场B/HOLD、校准认证、真实cleanup_unconfirmed/interrupted或正式报告交付。

## 3. 命令、结果和输入判档（不混算）

累计BASE `285cd4a96575471d3aac4e79eb088f66f03eda16` → Task3交付；Task3增量BASE `1eedefafa786c9305de556113b2df1be41435cfc`。所有文件均属“修”，只服务组合验收与指南，不新增产品行为。

| 累计变化文件 | 分类 |
|---|---|
| `api-service/tests/pc04a5d_browser_fixture.py` | 专用验收；非shared fixture |
| `api-service/tests/test_pc04a5d_topology_acceptance.py` | 专用验收；新增测试输入，与5c不同 |
| `gui/test/pc04a5dTopologyAcceptance.browser.js` | 专用验收；按attempt记录不同脚本输入 |
| `gui/test/pc04a5d.vite.config.ts` | 专用验收；非production Vite配置 |
| `docs/plans/2026-10-29-pc04a5d-topology-acceptance.md` | 文档/进度 |
| `docs/roadmap-first-call.md` | 文档/当前状态最小更新 |
| `docs/guides/topology-library-recovery.md` | 文档/操作指南 |
| 本摘要、已跟踪Task2回执 | 文档/验证证据 |

生产、shared fixture、source fixture、转换器、schema、依赖与生成契约变化均为零，`git diff --name-status BASE`可逐文件复查。未跟踪的/tmp及output日志/JSON/SQLite/PNG只作证据，不是测试运行时产品输入；原件hash在manifest/receipt-index，不假装新检出自带这些本机文件。既有venv/node_modules未安装/更新；Task2实录Python3.13.14、Node26.5.1、npm11.17.0；Task3另存当前依赖清单。没有新增依赖。

| 验证层/命令（cwd） | 实际输出、exit与输入责任 |
|---|---|
| Task1首轮 `pytest tests/test_pc04a5d_topology_acceptance.py -q`（api-service，前缀均`.venv/bin/python -m`） | `/tmp/pc04a5d-h555q5/task1-attempt1.log`：3 failed/15 passed/211 warnings/21.73s，exit1；纠正两测试假设并报告CE边界。其后17 passed/1 deselected/202 warnings/20.92s，exit0。早期固定名部分JSON已覆盖，失败完整log保留；不能称全部原件无损 |
| Task1相关集 | 精确九文件和两个`-k not`排除命令见[计划Task1](../plans/2026-10-29-pc04a5d-topology-acceptance.md)；`/tmp/pc04a5d-idnQIt/task1-related.log`：279 passed/4 deselected/985 warnings/94.58s，exit0，test SHA5b206eaa…；4个real_capture旧用例未跑，不能算passed |
| 收集修正后定点 | `/tmp/pc04a5d-LTOz6l/` full RED collect exit2/no tests collected/1 error；GREEN full/ordinary各collect18、exit0；`fix-focused.log`18 passed/211 warnings/22.08s、exit0，test SHA60a398f6…；未重跑279 |
| 证据保留修正后单例 | `pytest tests/test_pc04a5d_topology_acceptance.py::test_d11_d12_synthetic_saved_confirmation_once_and_history_immutable -q`，`/tmp/pc04a5d-AmYHpZ/preservation-focused.log`：1 passed/58 warnings/1.37s、exit0，test SHAae0122d3…；未重跑18/279。warnings未逐类归因，不称全是既有 |
| Task2浏览器（gui真实CLI） | stage输入/完整CLI命令、每attempt实际源码见已跟踪Task2回执与本机receipt-index。最终分支结构化error:null和独立SQL交叉核；早期部分子CLI exit未持久记录，不补称全部exit0；原生modal无结果不当通过 |
| Task2 GUI | `npx --no-install tsx --test test/topologyDraft.test.ts test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts`（gui）：75 tests/75 pass/0 fail/774.143792ms，工具回执exit0 |
| Task2 build | `npm run build`（gui）：built in13.48s，工具回执exit0，存在大chunk警告；日志尾无独立shell exit标记，不据日志补造早期exit。后续仅专用验收/文档变，GUI相关与production build输入无diff，Task3不重跑 |
| Task3文档门 | 新test.sqlite安全bootstrap后，仅G8/G11文档路由门与gitignore门；真实输出见末节。Task3未重启浏览器或服务、不重跑上列任何相关集/build/最终全量 |

最终稳定输入SHA256（Task3起止相同；早期test输入不同已分栏）：

| 文件 | SHA256 |
|---|---|
| source fixture | `e10bbebee929e7fcc076fcc4f73b2e55e917ce8d42339c75f0a9d4b89911539a` |
| 5c converter | `a9d079380fcd5c79b8ae5323bcccb717e1c784d69829fa19319dea879a5aa9a9` |
| 5d fixture CLI | `96b64070cc1a62a6306aacc5734948a8abf826c0d4823cf1171cf5f95efb9470` |
| 5d API测试 | `ae0122d3e4c3db0f1bc290d4ec8000033b6a255e6a77666e740f74469ad7c92c` |
| 最终browser脚本 | `048ccfb6a14ae3b7f567a05e5bdd521311b654fa860814216fb33f57e9c516aa` |
| 专用Vite配置 | `cd8f70dc29dea3c50aa5077d7ae1b83a689584a142abdee4c8b3a5c152d2c834` |

S JSON SHA `25b85e35916d24e4e2b0005363ac5c0c0bcc087d140d5ff5a60b472933d3c111`；备份DB SHA `74b7ec3795753ea406992d58dee9bcb501b4a88bd3c521e5215a812946cfc095`。SQLite backup非字节复制：S原/备份逻辑dump同为646c11eb…，B原/备份逻辑dump同为7cd6439f…；B原DB0805d4d1…、备份a99ddd91…不称字节相等。B receipt-index SHA `4487ffa08243d667970845a1c25a4a9a5de3eb0812ab9fd93507d41a70934b6b`，收尾SQL审计JSON SHA `a42f16b0fe0c656eb17efe514d8907b790b8daab7b8400fff250434b9d65e5c0`。

## 4. 文档门与交接

Task3实际新库 `/tmp/pc04a5d-ZcxvXd/test.sqlite`，先设置Mock/bootstrap环境再运行`.venv/bin/python -m tests.pc04a5d_browser_fixture --bootstrap-only --kind test`，exit0。bootstrap JSON回读7类别、7连接、1个Lab的7条非空Mock bindings及7个实际Mock HAL；独立jq断言exit0，非仅依赖env。未启动API或浏览器。

在api-service实际执行：

```bash
.venv/bin/python -m pytest tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes tests/test_rule_gates.py::test_g11_docs_cite_live_api_routes_full_domain tests/test_rule_gates.py::test_gitignore_does_not_shadow_tracked_sources -q
```

原件`/tmp/pc04a5d-ZcxvXd/docs-gates-attempt1.log`，**3 failed, 40 warnings in 0.99s，exit1**。完整日志SHA256 `58c3e0b75aeb50dc9638129067164c8fdb51740c47fe451ee79f2a9d08609c5e`。不修改历史、不放宽门，不称全绿，也不能统称“三旧门”：

| 门 | 累计BASE285cd4a9已有命中 | 5d累计新增命中（Task3 BASE1eedefaf已含） |
|---|---|---|
| G8 | `docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md:111`，带具体UUID的execute历史记录 | 无 |
| G11 | `.superpowers/sdd/2026-10-27-pc04a4e-device-contract-acceptance/task-2-report.md:128`，代理前缀被当独立路由 | `.superpowers/sdd/2026-10-29-pc04a5d-topology-acceptance/task-2-report.md:16`，同类代理前缀命中；不改Task2回执消门 |
| gitignore | 4e的delivery-status-report/final-doc-report/progress/r1-fix-report/task-1-report/task-2-report/task-3-report，以及5a的task-1-fix-report/task-1-report，共9份 | 本片已跟踪Task2回执同样命中`.superpowers/sdd/.gitignore`第一行`*`，总数10；Task3回执仅本地保留，不强制新增跟踪 |

旧命中文件、`.gitignore`、门源码相对累计BASE逐项diff为空，exit0；本片Task2回执在累计BASE不存在、在Task3 BASE已存在，不能把此新增失败归为旧5c。新指南已先staged进入现状文档网且没有命中；计划/本摘要按日期文件不在该网，roadmap在门的既定豁免中。门后仅更新结果/checkbox、指南按钮准确全称和不带路由的链接，路由扫描输入与跟踪文件集合不变，故按输入复用本次原件，不重复运行同三门。

依赖核查未安装/升级：venv无pip，`python -m pip freeze`工具实际输出`No module named pip`（该子命令未单独捕获exit码）；首次标准库导出因命令引号错误SyntaxError/exit1、空文件保留；修正只读命令后importlib.metadata导出exit0到`python-distributions-attempt2.txt`，SHA256 `b22f9ea3081a08af8c77eadb5e17e1205c8deb562cfdb688ee775fb1b30d5d30`。Python3.13.14/Node26.5.1/npm11.17.0；requirements/package.json/package-lock相对BASE无diff。未用失败空清单作依赖证明。

作者只读自查`reference-audit-attempt2.txt` exit0：10个本地Markdown链接目标均已跟踪且存在，嵌图0，19个字面按钮及2个JSX动态确认按钮有现状源码依据；S执行/消费者及B索引/SQL审计hash精确匹配，指南七段、D01～D12均有定位。首轮检查器把动态“确认复制”误当源码字面串，exit1后修正检查判据，未改生产；首轮输出保留。此为作者自查，不替代主任务安排的独立审查。

Task2准确身份核验后已关闭专用browser session和API23373/Vite23428；18126/18127无监听的历史exit边界见Task2回执。Task3不再启动这些进程。保留新库、备份、失败与成功原件；不关闭用户服务，不清理旧output/DB/venv。主任务负责Task3/累计独立审查、外审/合并、台账/handoff和主claim释放。
