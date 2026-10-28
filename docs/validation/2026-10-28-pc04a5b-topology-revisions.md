# PC04A5b 拓扑持久修订与恢复：隔离软件验证

2026-10-28实施验证快照；最终交付以功能PR合并回执为准。验证基线及全量前后生产代码HEAD均为`479e9e3773decc19b272543d532fab17455cf286`。Task1～3已实现的生产代码未在本任务修改；本任务新增隔离夹具、只读审计、CLI浏览器场景与专用代理配置。Task4独立/整片累计审查与Ready PR外审合并尚未完成，不另开递归状态PR。后端全量有3项历史规则失败，不称全绿。

## 安全边界与环境

新库 `/tmp/pc04a5b-tWkCas/browser.sqlite`，首次seed前不存在；所有应用Python导入前设置DATABASE_URL、USE_MOCK_INSTRUMENTS=true、BOOTSTRAP_ON_STARTUP=true和独立LOG_DIR。schema→bootstrap→逐类别/全部Lab binding改Mock→commit→重新查询核验：8类别、4 Lab、28非空binding全Mock；实际HAL初始化7驱动，逐个`is_mock_driver()`为true。第二类别无型号所以HAL跳过，不称其硬件连接成功。

两次早期夹具尝试因bootstrap默认无非空Lab绑定断言失败，日志与新库均保留：`fixture-first.log`、`fixture-second.log`。有效库在夹具中明确新建隔离Mock Lab后再验证非空绑定。新库内新增两个暗室、两个独立Lab、一个共享暗室Lab、两个开关类别。明确旧r0由ORM种入且标注来源；新图经真实HTTP创建r1；分页图连续真实PATCH101次，r102/102条历史。

API专用18106（PID44239，exec session7712）；首Vite15186（node44301）由本任务核身份后关闭，新Vite node45695（session74979）。首次配置漏覆盖继承的`/api/v1/ota`，经独立核查纠正后重启专用Vite；合并配置的`/api/v1/ws`、`/api/v1/ota`、`/api`全部指18106。现存请求/服务日志未发现8000/8001或OTA请求，不将日志未命中扩张为对所有系统进程的断言。

浏览器为CLI真实headed命名会话`pc04a5b-task4`、`task4b`、`task4c`、`task4d`；脚本`gui/test/pc04a5bRevisions.browser.js`只通过DOM鼠标键盘编辑。辅助真实HTTP只用于第二客户端/只读验证；双页另有真实UI完整用例。延迟使用`route.fetch()`取得原始服务器response，再延迟原始response交付，未构造200/JSON假响应；断网场景只abort真实网络。早期工具等待文本/label及release-unroute竞争失败原件保留，不计为通过。

原CAICT、用户默认数据库、用户服务未操作。Mock采集只验证生命周期，不把模拟样本记为正式测量、confirmed、B/HOLD通过。5c/5d未启动，原automation保持PAUSED。

## 真实浏览器与API矩阵

下列文件均位于本机证据目录`output/playwright/pc04a5b/`，为本机完整命令/代码/请求/截图索引，不是fresh-clone可用的图片链接。未将未跟踪截图嵌入正式文档。

| 编号 | 实际行为与断言 | 本机证据日志/截图前缀 |
|---|---|---|
| H01 | r0历史只读无写；真实鼠标拖节点→PATCH200 r1；baseline0 raw不补pin；重载坐标相同 | `H01-third.log`；`H01-1793165325293-*` |
| H02 | 正确改名→误保存→历史预览无写→checkbox二次确认→恢复新rN+1；内嵌校准清null、原历史值不变；再次图保存不回退名称 | `H02-third.log`；`H02-1793165466878-*` |
| H03 | 两真实页面同rN；A鼠标改名200、B鼠标拖图旧令牌409；B草稿保留，显式GET核查不覆盖 | `H03-two-pages-final.log`；`H03-two-pages-1793165679603-*`；另`H03-first.log`为辅助HTTP第二客户端 |
| H04 | 原转换Modal填null，预览后仅外部改名；旧digest不变但revision409；原输入保留，显式重预览后才可保存 | `H04-first.log`；`H04-1793165362042-*` |
| H05 | restore POST成功、后续GET阻断；服务器r+1但UI持续unknown；再次点保存零写；显式GET/history核查并采用后才恢复 | `H05-second.log`；`H05-1793165404801-*` |
| H06 | 历史第2页真实skip50/limit50，total102；同名不同UUID不串图；异暗室409；跨类别及共享暗室Lab独立UI验证；默认图偏好不变 | `H06-second.log`、`H06-scope-final.log`；`H06-1793165410770-*`、`H06-scope-1793165657816-*` |
| H07 | 图保存真实在途仅1 PATCH，恢复预览禁用；库命名在途图写/恢复入口锁；Mock POST202开始回执在途、状态GET阻断终态unknown仍锁，finally未释放；显式确认终态后释放 | `H07-second.log`、`H07-library-final.log`、`H07-collection-final.log`；对应1793165417392/1793165673515/1793165569515截图 |
| H08 | 延迟旧历史后切图不接纳；保存中SPA离页返回，以新GET重建基线、无自动POST；库核查迟到期间Flow成功保存/成功恢复，及A→B→A均丢弃旧核查，旧采用Modal不出现 | `H08-history-corrected.log`、`H08-library-final.log`、`H08-library-restore-final.log`、`H08-roundtrip-final.log`；1793165581560/1793165545603/1793165551633/1793165558204截图 |
| H09 | dirty可只读但不能预览恢复；原生confirm显式放弃只回已知快照，前后history JSON字节相同；单独历史预览后仍须checkbox二次确认 | `H09-final-prepare.log`、`H09-dialog-accept.log`、`H09-final-verification.log`、`H09-before-discard.json`/`H09-after-discard.json`（cmp0）、`H09-final-discard-and-second-confirm.png` |
| H10 | 同内容restore仍增新行；缺令牌422、过期409/不存在目标404均无写；显式新增非法legacy r0夹具后仅修正当前图，历史预览422无写；UI复制新UUID/r1且只1条copy历史，源历史不变 | `H10-first.log`、`fixture-invalid-case.log`、`H10-invalid-final.log`、`H10-copy-final.log`；1793165384626/1793165663765/1793165668651截图 |

组件内保护不等于全局SPA离页守卫；本片不实现跨卸载持久草稿/unknown。离页不取消服务端请求，重入不宣称原写成功、不使用缓存旧令牌、不自动重发。采集未知的既有保守锁不放宽。

补充精确出口：`empty-library-final.log`及`empty-library-1793165941783-*`证明真正空库import POST200仅1次、随后GET失败unknown，不建伪成功Flow；显式GET/history核查仍锁，明确采用才建立r1保存基线。该例仅向同一隔离库新增空暗室及Lab（Lab `8344c5b4-5333-477c-a9f1-ad1367851251`）：初始seed快照为4个浏览器业务Lab/28 bindings；最终只读复算为**全库55 Lab，其中5个浏览器业务Lab各7 bindings，另50个归属测试Lab的bindings为NULL**，合计35个非空binding、8类别全部Mock。新import图`ca47b1a0-5810-487c-adb9-2e7425e51da3`，只有1条r1/import历史。

`doubleclick-final.log`及本机独立`doubleclick.browser.js`保留实际`page.mouse.dblclick`代码，真实PATCH计数为1，恢复在途禁用；截图前缀`H07-1793165961258-*`。`late-preview-lab-final.log`及`late-preview-lab-1793166043247-*`证明真实restore-preview原响应延迟时关闭历史并切Lab，旧preview不进入新图，也不产生写入。

`matrix-index.json`索引21个成功场景、51张关联截图、220条可追溯请求（30条写/预览请求）；H09原生确认另有独立截图。`executed-code-index.json`将实际完整操作代码单独归档（63份）；6份只有CLI错误的日志明确标为不含执行代码，绝不当作成功操作或完整脚本。所有文件仅本机证据，不保证fresh-clone取得截图。

## 只读审计与资格/冻结消费者

`tests/pc04a5b_browser_audit.py`在严格新库路径检查后使用SQLite mode=ro，只SELECT，不初始化。`audit-before.json`/`audit-middle.json`/`audit-after.json`与`verify-audit.mjs`/`audit-verification.log`：每图revision唯一，当前等于max；copy UUID独立且只有1条copy历史；183条已存在历史（含snapshot/metadata/created_at）逐条完全不变。所有旧图scope、active/default、created_at保持。

`calibration_certificates`、`route_calibration_applications`、`route_calibration_selections`、`test_executions`、`test_plan_executions`前后计数及内容摘要完全相同。Mock采集没有产生采用/证书/正式执行资格。

补证前后`audit-after.json`/`audit-after-supplement.json`及`audit-verification-supplement.log`进一步确认192条已有历史完全不变，上述5类正式表计数/hash不变；最终8类别、全库55 Lab（5个浏览器业务Lab及50个NULL bindings归属测试Lab）、35非空binding。原`audit-verification-supplement.log`的`lab_count=5`将业务Lab误写为总数，原件不覆盖；追加只读`SELECT id,name,instrument_bindings FROM lab_profiles`更正原件`lab-count-correction-r1.json`，记录完整分类及原审计SHA256。50个空绑定Lab来源可定位到`tests/test_pc04a4d_loss_truth.py::world`的归属测试夹具，未清理数据库。`calibrated-reset-proof.log`在实际库中定位到历史r4内嵌2.5→restore r5为null，原r4仍为2.5；这些值均为synthetic输入，不能称现场校准值。旧`probe_path_loss_calibrations`等资格实体的恢复前后不变由Task2定点生产入口测试覆盖，不冒称都包含于本机按表名筛选的5类审计。

相关后端：`tests/test_pc04a5b_topology_revisions.py tests/test_pc04a5b_topology_restore.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a4d_loss_truth.py`，`pytest -q`：183 passed，1208 warnings，171.56秒，退出0（`targeted-first.log`）。补充`test_pc04a5b_restore_contract.py test_pc04a5b_restore_qualification.py test_pc04a5b_revision_migration.py`：5 passed，84 warnings，6.83秒，退出0（`targeted-supplement.log`）。其中迁移覆盖实际文件`f28a91c7d6b3_topology_revisions.py`；双连接CAS及回滚、同身份confirmed一次补偿、身份变化后当前和旧freeze两端拒绝均沿真实生产入口测试，synthetic软件证据不等于现场实测。

GUI：`npx --no-install tsx --test test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/legacyConversionState.test.ts test/topologyOperationalLabContext.test.ts`，tsx4.23.15/Node26.5.1，46 passed/0 failed，556.947792ms，退出0。`npm run build`退出0，11.80秒；保留既有chunk-size警告（`gui-tests.log`/`gui-build.log`）。

### 累计 F1 最小 GUI 修复补验

累计审查发现与 H08-library 相反的遗漏：同图库命名开始/保存模型变更未使 Flow 较早的“服务器最新”核查失效。新隔离库 `/tmp/pc04a5b-66qL8r/browser.sqlite`、专用 API18106/GUI15186，bootstrap 后显式重读8类别/4 Lab/28非空bindings全 Mock；不连接默认库或用户服务。真实 DOM 改名及真实响应延迟实跑：RED 分别复现迟到核查和已展示核查使 UI 退回旧 r0/r1（DB仍是r1/r2）；GREEN两站旧核查丢弃，保留当前保存基线。只延迟 `route.fetch()` 得到的真实响应，不合成业务响应、不调用 React handler。

最小修复复用 Flow 读代数与保存模型身份，在库写开始/同图模型变化时作废在途及已展示核查；读取完成和最终采用均校验捕获的修订/代数，不换新token配旧draft。补验 GUI 47 passed/0 failed（563.1325ms、退出0），build退出0（real15.61秒，保留chunk-size警告）。请求、截图、RED/GREEN、输入hash索引为本机 `output/playwright/pc04a5b-final-fix/index.json`；详细阶段与限制在本片 SDD `final-fix-report.md`。本轮仅GUI及验证说明变化，**下节后端全量限定复用原后端输入，未重跑、也不冒称它覆盖新GUI**；未开始5c/5d或部署/现场验证。

## 唯一最终后端全量

完整原始命令脚本为本机`output/playwright/pc04a5b/run-final.sh`；唯一全量exec session78567，pytest PID48819。新库`/tmp/pc04a5b-Ziu3Cj/full.sqlite`，与browser.sqlite分离；bootstrap退出0并重读7类别、1 Lab、7非空binding全Mock。

命令：从api-service以本节新库及Mock/bootstrap/LOG_DIR环境运行`.venv/bin/python -m pytest tests -q`。实际收集8086项，**8066 passed、17 skipped、3 failed、9855 warnings，818.25秒，退出1**；runner墙钟826秒。runner UTC开始05:35:56、结束05:49:58（含启动/清单步骤，测试耗时以pytest结尾为准）。完整输出`final-backend.log`，退出/墙钟及输入比较`final-runner.log`。

3项失败的实际指向：G8为旧`docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md`中的已拆路由；G11为旧4e `task-2-report.md`中的ws引用；gitignore门为7份旧4e及2份旧5a报告被既有忽略规则命中。未改历史记录、G8/G11或ignore规则；本片新报告不force-add。不将前片8003/17/3当本片结果。

实际输入predicate：`git ls-files -co --exclude-standard`中的文件逐个SHA256；排除output（含api-service/gui下output）、CLI生成物、目录型venv/node_modules及被Git忽略的缓存/pycache，不排除实际被规则读取的tracked MD。runner还尝试用`rg --files --hidden`并入本片SDD，但rg尊重ignore，所以本片未跟踪SDD报告实际未进入清单，不能声称覆盖它。规则`tests/test_rule_gates.py::_live_doc_paths()`明确通过`git ls-files -z *.md`读取tracked MD，`test_gitignore_does_not_shadow_tracked_sources()`同样读取Git跟踪清单；既有tracked旧SDD报告在1676内，ignored本片SDD不是这些扫描输入。开始和结束均1676个文件，列表/内容cmp退出0，清单SHA256均`2c97d1a94a3e377c0ed72c43f8f8d9579a2f9927f620a9b0ef92cf07f53498c0`（`final-inputs-before.sha256`/`after.sha256`）。生产HEAD前后相同；原runner与原清单保留。

依赖披露：原runner的`python -m pip freeze`因venv无pip失败，原错误保留，空freeze文件不能作依赖证明。随即在运行初段（本地13:36:28）用`uv pip freeze --python api-service/.venv/bin/python`取只读依赖清单，结束后同法重取，cmp退出0；两清单SHA256均`ba9a0540f4c051a1467bde7d78e17716f8edcd129120ae5731a4ed67fd459ca7`。该依赖起点晚于pytest启动，不声称精确覆盖此前十余秒；期间未安装或修改依赖。Python二进制及GUI package-lock前后SHA清单cmp退出0。

全量结束后只同步design/plan/roadmap/validation和本机Task4报告的实施状态、统计及操作边界；不修改生产/测试/夹具/config输入。`post-docs-input-delta.json`确认1676中仅4个MD变动，其余生产/测试/夹具/config一致；ignored本机Task4报告不在该清单或规则扫描内。进入Git跟踪后使用全新`/tmp/pc04a5b-EEAG0k/test.sqlite`对`test_g8_docs_only_cite_live_plan_routes`、`test_g11_docs_cite_live_api_routes_full_domain`、`test_gitignore_does_not_shadow_tracked_sources`重新定点，实际3 failed/40 warnings/退出1，命中仍为同3项旧引用/旧忽略文件，没有本片新增命中，耗时以`post-docs-rule-gates.log`结尾为准；不由旧全量冒称覆盖新文档，不递归全量。本轮SQLite迁移/CAS及软件证据不代表真实PostgreSQL部署或现场RF验证。

## 本片最小操作提示（不启动5d）

1. 已有库部署前先备份，确认目标部署环境及迁移链，显式执行Alembic升级（本片head `f28a91c7d6b3`，实际文件`api-service/alembic/versions/f28a91c7d6b3_topology_revisions.py`）后再启动新版API。本任务没有迁移默认库或操作用户部署。
2. 选择当前Lab、开关类别及目标UUID。旧r0打开“保存修订历史”只读，不会补造历史；界面明确“尚无修订留痕，从首次保存开始记录”，不能找回系统从未记录的更早保存。
3. dirty时先保存，或用“放弃未保存改动”及原生二次确认只回到已知保存快照；它不写服务器、不追加历史，不是历史恢复。随后在“保存修订历史”选r编号→“预览恢复差异”，核对历史原件、候选和差异，勾选“确认将此历史声明恢复为新的保存修订”，再点“恢复为新修订”。
4. 恢复生成新rN+1，当前已有内嵌校准值清null、历史原件不改；不恢复采用、证书或执行资格，不自动重新采用/启用图。仍需沿现有资格/冻结身份门核对，不凭新revision一刀切断言资格。
5. 409保留草稿和转换输入，不自动重试。Flow用“刷新查看服务器最新”，库写用“核查服务器最新拓扑库（只读）”；读取只展示比较，明确“确认放弃旧草稿并采用服务器最新”或库中的“确认采用服务器最新并结束核查”才采用。unknown时禁止重复恢复/导入，先核对服务器修订、操作及内容。
6. 外部脚本的`expected_revision`必须来自**开始编辑时载入的已保存快照**，与该草稿绑定；不要临时GET新token配旧draft覆盖。409后须显式核对/放弃或重新建立编辑基线，不能自动换令牌重放旧内容。
7. 不提供全局SPA离页守卫或跨卸载草稿/unknown持久存储。离页不取消服务器请求；返回从服务器GET建立新基线，须核查最新修订，不宣称离页前请求成功、不自动POST。真实采集未知继续保守锁定，关闭页面不等于停止。
