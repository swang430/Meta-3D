# Task 2：真实浏览器旅程回执

BASE：`4b5a2917`；分支：`codex/pc04a5d-topology-acceptance`。本次只新增浏览器旅程和专用 Vite 配置，并按主任务裁决注明 D03 的有效 PA 副本载体；生产源码、共享 fixture、schema、依赖、用户库和用户服务零改动。主代理自查，非独立内审；独立规格/质量审查由 root 安排。未 push，未跑后端全量，未 claim/release 主台账。

## 隔离世界与证据位置

- 新建目录及原件：`/tmp/pc04a5d-ItdcnV/`；新库 `browser.sqlite`。从未使用 Task1/旧片 browser 库。
- 完整保留副本：`output/playwright/pc04a5d/evidence-ItdcnV/`（包含日志、逐次 CLI 输出、manifest、候选、只读 SQL 审计和数据库）。截图原件在 `output/playwright/pc04a5d/`，使用 case/attempt/stage 唯一名，失败不覆盖。
- `receipt-index.json` 索引每份 attempt 日志、SHA256、结构化 error/checks/截图及日志内实际执行源码指纹。原始 CLI 输出内有完整 HTTP method/URL/body/status/response 和当次实际源码；不能用最终脚本 hash 冒充所有早期 attempt 的输入。
- 新 source：`f6d60fdf-e102-4150-82b4-03c86a66de60`；普通副本：`925453b7-e99e-414b-bdde-d2a99c9cbe4e`；32 路 PA 副本：`6ebf965d-9f10-4171-b9a2-d53e00c3681f`。
- 独立 collection：`83e7a0d0-9e0a-4e63-93c5-72c336acee9e`；端口练习图：`e0f9c807-aad9-43b7-be14-51cc4d0d67e8`。小图的 200 不替代 32 路 inactive 副本的 422。
- Lab A：`24ef3811-cd4a-4cc8-86f5-d12c6b4a573c`；A共享：`b1f8f7e5-a839-4251-b715-4a28e6e26306`；B：`d0252874-5a98-4a21-aaea-9f1fc19a2cf2`。A/A共享 chamber `847744e9-dedf-4d93-9ad8-abaf5b8389cb`；B chamber `8655be80-68bb-4d5c-80a3-1167091ef16d`；rfSwitch category `c208809d-a150-427f-a37d-483901f89aba`。

环境在任何 app 导入前设置；fixture checked_path 先核新 SQLite/Mock/bootstrap 守卫，再导入应用。bootstrap 后七类别均 mock、全部连接 `192.0.2.10`、四个 Lab 均非空七条 Mock bindings；初始化后及播种后实际七类 HAL 均 `is_mock_driver=true` 并 shutdown。服务启动后每个 browser case 又读取本片 HAL status 为 mock；收尾只读 SQL 重新核对全部类别/连接/绑定，非仅依赖 env。

浏览器只连接 GUI `127.0.0.1:18127`；三条代理 `/api/v1/ws`、`/api/v1/ota`、`/api` 全部 `18126`。没有访问 8000/5173、默认 PostgreSQL、用户 CAICT 原图或用户已落地副本。候选只由已跟踪 JSON 的纯转换函数生成，最终 PA 图是真 copy→PATCH，不是 ORM 直造。

## 实际启动及执行命令

```bash
# cwd api-service；mktemp 输出 /tmp/pc04a5d-ItdcnV，原件保留
DATABASE_URL=sqlite:////tmp/pc04a5d-ItdcnV/browser.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a5d-ItdcnV/logs .venv/bin/python -m tests.pc04a5d_browser_fixture > /tmp/pc04a5d-ItdcnV/manifest.json 2> /tmp/pc04a5d-ItdcnV/seed.stderr
lsof -nP -iTCP:18126 -sTCP:LISTEN
lsof -nP -iTCP:18127 -sTCP:LISTEN
DATABASE_URL=sqlite:////tmp/pc04a5d-ItdcnV/browser.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=false LOG_DIR=/tmp/pc04a5d-ItdcnV/logs .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18126 > /tmp/pc04a5d-ItdcnV/api.log 2>&1
# cwd gui
npx --no-install vite --config test/pc04a5d.vite.config.ts > /tmp/pc04a5d-ItdcnV/vite.log 2>&1
```

播种 exit0；端口先核无监听，两次 lsof exit1 表示空闲。health 200/healthy/mock_instruments=true。实际 API PID `23373`，Vite PID `23428`；命令、父 PID 保存在 `process-before-stop.txt`。Vite 默认代理未被沿用。

浏览器已完整读取 playwright 技能，使用它的真实 CLI，不使用 React handler/store，不伪造响应。打开命令：

```bash
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh --session pc04a5d-task2 open 'http://127.0.0.1:18127/?stage=D01' --headed
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh --session pc04a5d-task2 goto 'http://127.0.0.1:18127/?stage=<case>'
/Users/simon/.codex/skills/playwright/scripts/playwright_cli.sh --session pc04a5d-task2 run-code --filename gui/test/pc04a5dTopologyAcceptance.browser.js
```

初始输入通过真实 CLI 的 `page.evaluate` 仅设置测试输入键 `pc04a5d.manifest`、`pc04a5d.candidate`；值分别为本片 `manifest.json` 和由 `build_candidate()` 生成的 `candidate.json`，没有注入 React 状态。另只设置应用既有操作 Lab localStorage 键。D03 原生确认分三段：D03-pre→真实点击“放弃未保存改动”→CLI `dialog-dismiss`→测试输入 `pc04a5d.stageOverride=D03-check-cancel`→再点击放弃→CLI `dialog-accept`→D03-save；结束清除 stageOverride。CLI 会在原生 modal 出现时返回，不能把这种无结构化回执当通过。

D09 准备步骤也由真实属性表单完成：probe 的显式路径两项用 Backspace 移除→点击“应用器件修改”→原生确认“取消显式RF路径声明后，将恢复服务器唯一链解析…”→CLI dialog-accept→真实保存。当前 D09 主旅程要求该准备已完成，否则明确报错；没有 PATCH 代连线或绕过确认。随后两个连接均为真实 DOM handle/boundingBox/鼠标 down→move(20 steps)→up。

## 分支结果与持久事实

下表只认列出的最终结构化回执 `error:null`；早期失败见下一节。HTTP/DOM 原件在对应 `.txt`；独立只读 SQL 全列/历史核验在 `sql-audit-after-stop.json` 与 `audit_readonly.py`，均已实际执行 exit0。截图前缀均位于 `output/playwright/pc04a5d/`。

本片 SQL 全列基线 `sql-after-D01.sql` 采于 D01 后；它与最终 source/Lab/category/connection 全列一致。D01 复制前后另有完整 API DTO/raw/history 比较，复制前 DB 全列及正式 resolver 的独立验证关联 Task1，不将这份后采 SQL 基线说成复制前快照。

| 分支 | 最终实际回执 / 关键截图 | HTTP、DOM 与 SQL 结论 |
|---|---|---|
| D01/D02 | `D01-attempt1.txt`、`D02-attempt3.txt`；`D02-1793238300245-automatic-default-no-choose.png` | source r0/history0 只读；同名复制按短 UUID 选择，201/r1/inactive/nondefault，trim 命名200/r2。本浏览器偏好重载自动选副本（D02不先手选），清洁可切原图；独立 browser context 偏好键为空。source 全列/三个 raw 数组/历史、Lab 全列及绑定不变。正式 resolver 不变的生产消费者证明关联 Task1 D01，本片不新造执行。 |
| D03 | `D03-pre-attempt3.txt`、`D03-check-cancel-attempt3.txt`、`D03-save-attempt3.txt`；`D03-save-1793238286448-saved-property-reload.png` | 按 root 裁决使用合法 PA 副本，不放宽旧 raw 的 ports 门。实改属性→dirty，库/category/复制/命名锁；实际 Lab 切换被 guard 拒。原生取消放弃保留dirty，显式放弃没有拓扑写，raw/revision不变；再改标签真保存 r5，重载属性值相同。 |
| D04/D05恢复 | `D04-attempt1.txt`；`D04-1793238024786-r1-readable-preview422.png`、`r2-preview-no-write.png`、`r4-restored-r2.png` | 新PA演练副本copy r1→真实候选PATCH r2；r1 raw可读但preview422（缺ports）；仅鼠标拖B1位置存r3；r2只读预览零写、未勾选恢复禁用→勾选后恢复r4。r4三个raw数组精确等r2，r1～r3快照不改。 |
| D05双页 | `D05-attempt3.txt`；`D05-1793238305344-B-dirty-before-A.png`、`B409-dirty-input.png`、`B-inspect-not-adopted.png` | 两真实页读同r3；B属性形成dirty并截图在先，A真命名200/r4；B旧令牌PATCH409，草稿输入及放弃按钮保留。GET核对不自动采用，取消不覆盖。旧revision restore409，raw/revision不变。 |
| 数据库写未知 | `D05-unknown-attempt3.txt`；`D05-unknown-1793238589904-database-unknown-component-lock.png`、`database-unknown-SPA-new-GET-no-retry.png` | 真实restore写入但随后GET abort，组件unknown继续挡写/编辑；点击仍可见的保存按钮不会发拓扑写。只读核对不自动解除。离SPA重入重新GET服务器r9，不自动重发、不承诺跨SPA持久草稿/unknown，也不把数据库未知注册成永久硬件采集。 |
| 数据库真在途跨卸载 | `D05-pending-attempt1.txt`；`D05-pending-1793238514537-database-pending-global-Lab-guard.png`、`database-pending-release-reentry.png` | 真PATCH已到服务端后只延迟原样response；离开至主控台，实际Lab切换仍被beginWork拒绝。响应落定后释放，重新进入读到真实保存标签，写计数1、不重试。 |
| D06 | `D06-attempt5.txt`；`D06-1793238473824-shared-Lab-source-default.png`、`late-list-B-not-stolen.png`、`late-detail-B-not-stolen.png` | A与A共享同chamber/同图，分别设浏览器默认再reload互不覆盖；B不同chamber。实际旧A list与detail均route.fetch→延迟→原样fulfill，审计明确status200/delivered=true；切B后迟到响应未夺选择、未跨scope弹旧核对框；Lab/原图SQL原样。 |
| D07/D08 | `D07-attempt3.txt`；`D07-1793238326971-B1-*`、`B16-*`、`B32-*` 共9张 | 同一个32路PA副本：三PA UI 20/来源未核、in输入/out输出、有向in→out；每侧损耗控件空，raw loss=null、length缺键；控件展示0不当落库值。旧PA边不重复。并列独立SQL全32路：CE B1～B32→各PA.in→PA.out→原probe/pin/极化映射，opaque旧20/.8/5完整留档而不参与当前两边补偿。 |
| D09 | `D09-attempt5.txt`、`D09-visual-visual-attempt1.txt`；`D09-visual-1793238666071-full-three-node-connection.png` | 真拖PA坐标；真鼠标CE.out→PA.in、PA.out→probe.in，保存reload后两新edge UUID为`856abe89-7ac5-4f90-a251-781fedf03984`、`93476ddd-3dbb-4348-8396-3d189cee1a10`。完整path、相同pins、PA内部pair及mimo_ota active_connections一致；out→out真拖无新dirty/合法链、服务器零写。练习图inactive，不声称可采集。 |
| D10第1轮 | `D10-1-attempt1.txt`；`D10-1-1793238048167-start-pending-unknown-lock.png`、`GET-unknown-keeps-lock.png`、`terminal-release-save-reenter.png` | 真选完整通路/2595MHz/−30dBm/参考件及接收线缆来源synthetic非实测/两确认→真实start202。server GET确实running，非仅延迟回包；GET未知继续锁，明确读终态simulated后释放，可改标签保存reload。 |
| D10第2轮 | `D10-2-attempt1.txt`；`D10-2-1793238099739-cancel-pending-unknown-lock.png`、`cancel-pending-SPA-reentry-locked.png`、`GET-unknown-keeps-lock.png`、`terminal-release-save-reenter.png` | 不同run，server GET确实running后DOM真cancel；只延迟原样真实cancel响应，未知不解锁。跨SPA卸载重入仍锁；明确读服务器cancelled后可编辑保存，再离页/重入重新GET，不自动重发start/cancel。 |
| D10定点补证 | `D10-lock-target-attempt1.txt`；`D10-lock-target-1793238689255-acquisition-unknown-Lab-restore-guard.png` | 独立第3 run，只补前两轮未实际点击的Lab切换与恢复入口：实际切Lab被拒；历史r0可读但预览/恢复均禁用；真实GET running、未知锁、终态释放。不能冒充原两轮。 |
| Mock不可采用 | `D10-history-attempt3.txt`、`D10-history-visual-attempt1.txt`；`D10-history-1793238670983-actual-Mock-history-adopt-disabled.png` | 真查看本片simulated历史，真实application-preview200/new_net_loss=null、simulated_measurement阻断；实际“确认采用此实测记录”按钮disabled。早期D10脚本误用了不存在的按钮名称，故该项只由本条定点补证及Task1拒采用真实接口证明，不使用早期空locator冒充。 |

最终修订不是早期 r4：source r0；普通副本 r4；PA 副本 r9；collection r2；端口练习图 r6。PA 的 r1复制/r2候选/r3坐标/r4恢复/r5属性，随后 r6/r8/r9为各次真实unknown分支restore、r7为真在途标签保存，历史全部保留；并非覆盖早期r4。端口练习图早期失败准备也实际产生坐标修订，保留r1～r6，不把失败阶段写成零写。

## 运行身份、租约与边界

| 用途 | run UUID | lease_id | 服务器终态 |
|---|---|---|---|
| 第1轮 | `c2e0c849-01ed-4dd9-ac71-2a9984b0b350` | `4d43f7cb2eb9421cab872d3e6ee097c2` | simulated |
| 第2轮真cancel | `c27b66c0-3e57-44ef-8ec4-9cb759377036` | `77380bd2674c4d6796a6c4042846abc9` | cancelled |
| 定点补证 | `c3fb9735-8574-4f7a-a5b6-31857c860267` | `3a297b95a2774a80a9065f9a1431288f` | simulated |

`api.log` 同run取得/释放真实软件租约分别在本地时间09:40:49～50、09:41:40～41、09:51:30～31；不是临时改状态或伪running。三条终态均samples=[]、net_loss_db=null、cleanup_confirmed=null，正式Application/Selection/TestExecution均0行，DiagnosticRun=3。未使用测试级时钟夹具，未改Mock行为、资格函数或binding real。

软件Mock终态、取消响应与租约退出不能证明真实RF停发、真实cleanup、F64控制会话释放或任何现场资格；B/HOLD保持。浏览器fixture只播种source/collection/port练习三张r0图，**从未播种synthetic confirmed历史**；浏览器没有“新采集confirmed成功”。

### D11/D12只关联Task1机器证据

独立文件：`/tmp/pc04a5d-unuf7u7i/test_d11_d12_synthetic_saved_confirmation_once_and_history_immutable.json`及同名`.sqlite`；本次只读重新核身份，未修改或拿来当浏览器库。synthetic已存run `f030ec45-e449-4c99-9d34-42e69127be10`；Application `724362cd-0423-4431-812a-6194f5f041ea`；Selection `1669e1de-8397-4c31-98a8-8994ec03fb82`。

Task1中E1/E2新执行零I/O冻结与实际ChannelEngine消费者各只消费一次`confirmed_route/28`，源pin改other后E3 unavailable/None、旧冻结不变；浏览器不复造确认历史、不切real、不点击确认造绿。`measurement_provenance=real`仅已存synthetic DTO输入形态，非本片采集/资格/正式校准证据。该JSON hash `25b85e35916d24e4e2b0005363ac5c0c0bcc087d140d5ff5a60b472933d3c111`，DB hash `74b7ec3795753ea406992d58dee9bcb501b4a88bd3c521e5215a812946cfc095`，详细消费者证据见Task1报告。

## 首轮失败与复验边界

所有首次失败原始输出/FAILED截图仍在原位置及归档，不覆盖。没有发现需改生产的功能故障；下列均为定位/测试判据或CLI原生交互问题，不能把早期失败删掉后称“一次全绿”：

- D03 attempt1把Lab guard误当必须disabled；改为真实尝试切Lab后核context不变。attempt2在原生confirm处CLI提前返回，无结构化结果，不计通过；最终三段原生dismiss/accept才闭合。
- D05 attempt2旧restore请求误写`target_revision`而非schema的`revision`，得到422；最终正确请求409。D06 attempt2未等reload异步库；attempt3/4过早unroute，旧response未实际投递。attempt4即使error:null也不计迟到响应通过；attempt5新增delivered=true硬断言，真实list/detail才均投递。
- D07 attempt2误用innerText读来源输入框，最终改读inputValue。D09 attempt2批次被中断/无结果，attempt3 Escape关闭Drawer，attempt4在清除显式路径原生确认处返回；准备过程仍产生坐标r1～r3，后续真实保存清路径r4，最后鼠标拖连r5/r6通过。
- 数据库unknown attempt1误要求保存按钮disabled（实际handler挡写）；attempt2把异步frontend日志POST算作拓扑写，最终仅计真实topology域POST/PATCH并点击验证无新写。其早期restore均已真实落库，故最终PA为r9，不虚报r5或零写。
- 部分早期批次未逐个持久记录子CLI exit码；保留stdout/stderr和结构化error或无结果，不能宣称每条CLI都exit0。最终是否通过以列出的结构化error:null及独立SQL为准；CLI外层exit0本身不能替代内部断言。最终相关集/build/SQL审计/备份/diff核验的exit码均由工具输出实际确认。

## GUI相关集、构建与输入指纹

```bash
# cwd gui
npx --no-install tsx --test test/topologyDraft.test.ts test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts
npm run build
```

两条均exit0；`gui-related.log`结尾 `tests 75 / pass 75 / fail 0 / duration_ms 774.143792`；`gui-build.log`结尾`✓ built in 13.48s`，存在chunk体积警告，不隐瞒、不扩改生产。Node v26.5.1/npm11.17.0/Python3.13.14。后续只改验收脚本/报告和专用配置，未变这些GUI测试/production build的源码、依赖或常规构建配置输入，故不重复相关集/build。没有后端共享行为变化，不触发本任务全量；Task3仍是唯一条件全量责任位。

最终文件SHA256：

- 浏览器旅程：`048ccfb6a14ae3b7f567a05e5bdd521311b654fa860814216fb33f57e9c516aa`。
- 专用Vite配置：`cd8f70dc29dea3c50aa5077d7ae1b83a689584a142abdee4c8b3a5c152d2c834`。
- 未改fixture CLI：`96b64070cc1a62a6306aacc5734948a8abf826c0d4823cf1171cf5f95efb9470`；未改源JSON：`e10bbebee929e7fcc076fcc4f73b2e55e917ce8d42339c75f0a9d4b89911539a`。
- `receipt-index.json`：`4487ffa08243d667970845a1c25a4a9a5de3eb0812ab9fd93507d41a70934b6b`。
- 原browser.sqlite：`0805d4d1b89570f8411dbd6934cc54fc7385e6a08c7eeca3634680fb0c026518`；SQLite backup `browser-evidence.sqlite`：`a99ddd91120fc2a07a0a471e0fa94a64d5bbb0139f75dc9159c1e6dc0b0d3d08`，backup不是字节相等。二者逻辑dump SHA均`7cd6439fb2da78afd896f95a5e893e4418f0e374e8611b664f1c2a08745c2c68`；quick_check=ok。
- 收尾只读SQL审计JSON：`a42f16b0fe0c656eb17efe514d8907b790b8daab7b8400fff250434b9d65e5c0`。

已通过真实view_image逐张查看关键截图：自动默认/原图、r1拒恢复/r2预览/r4恢复、409dirty属性、共享Lab、B1/B16/B32端口与内部pair、完整三节点鼠标连线、两轮未知锁/跨SPA重入、数据库未知释放边界、Mock确认按钮disabled。截图是软件观察，不提升为现场测量。

## 进程收尾与交接

核对准确PID/命令后关闭本片专用浏览器session `pc04a5d-task2`（原daemon PID23533），仅向API23373/Vite23428发SIGTERM；两执行session返回143是本次主动终止。随后18126/18127各lsof exit1无监听，三个PID均不存在；用户8000/5173和Docker未操作。原库、backup、所有截图/日志/失败原件均保留，归档不删除源。

交 root：本报告、最终脚本/专用代理配置、全部证据目录。Task3可只读复核，无本片运行服务需要接管；如需浏览器复验须重新启动这两个专用端口并核Mock，不得误连用户API。独立审查尚由root安排；未声明整片5d已完成、可发布或现场B/HOLD通过。
