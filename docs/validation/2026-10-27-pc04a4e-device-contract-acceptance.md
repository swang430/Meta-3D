# PC04A4e 综合软件验收摘要

结论：已执行的软件分支有证据；不是 E01～E15 全项无保留 PASS。Task1 独立规格/质量通过，Task2 规格有限通过、质量 Approved，附首轮同名截图覆盖 P2。Task3 仅作者自查，最终任务及累计独立审查、PR 外审由主代理继续安排。硬件、ASC/CE、PostgreSQL CAS、现场 B/HOLD 均不关闭。

## 输入与证据身份

本次文档基线 `c579efb5b07ca2b14ec6fcf7b87afc3698678347`。不修改前片验证摘要、模板、报告、生产、驱动或资格。软件输入/对象全表见[Task1报告](../../.superpowers/sdd/2026-10-27-pc04a4e-device-contract-acceptance/task-1-report.md)、[Task2报告](../../.superpowers/sdd/2026-10-27-pc04a4e-device-contract-acceptance/task-2-report.md)；两份独立审查分别为同目录 task-1-review.md / task-2-review.md。

| 证据组 | 输入及原件 | 身份/范围 |
|---|---|---|
| A 原相关集（未重跑） | `/tmp/pc04a4e-quy1R7`；基线 bd71f2d8919f24d2091f07ba8e3670ff8687aca5 加新增测试；输入清单 SHA256 `1599dae6f8b9aa26f09100b8957c66dd055caf79f75523e79aeb6dcc53d09b8a` | E01图 fae506c8-ac20-4d1a-a486-bb4c31719663；E04/05图164d384d-75a5-4c4c-9535-8360a0f2b5ea，chain conn_p0v→probe_0_v；16份case JSON包含逐请求/SQL |
| V1 新完整 E04/E05（未重跑） | `/tmp/pc04a4e-vJhvY1`；0f0fe46ad58aab8eb42f07ccf478b04c7839fb2e 加历史GET修订；清单 SHA256 `79b69e828337243d04e61de29b2799d8c81654f16a588cadc83261b41984e7dc` | Lab f5092616-1ba1-44d1-a7dd-62cc36eaa218；暗室38c6f038-0e74-4419-87fe-0c4963db77e5；图a945d8d6-0593-48a7-b848-6241f71eb758；run92d9132b-21d5-4bdf-803d-fbe626692c5c；参考PA边pa-reference-edge |
| B 浏览器主矩阵（未重跑） | `/tmp/pc04a4e-GMwdXP`；5cb20d78f826f272e6f11ca45d6d5f25512263c6 加当阶段脚本；完整脚本文本各阶段日志内冻结，不将最终脚本倒填旧阶段 | Lab c39d52c3-c562-47df-b456-887dd5cb9799；暗室eda86f3b-a526-462c-86fb-2d90ce1716df；主图b9ed2852-5bb7-4cbc-853e-fb396ed7d109；CAICT源=展示=请求图4dabc6b8-0d4b-446d-b122-9046db9a80d5 |
| C 浏览器定点（未重跑） | `/tmp/pc04a4e-9TxR8N`；最终fixture SHA256 c8f58616f4eb1739e7432f765b87a477f4d44b0a64a1ad4eb8c06d4e1b1775eb；脚本318a0b58adce069bafb5eadf396310cf4f7bafbef1874e911d9c7a77a1c4cbe8；manifest b66a0e41311872247e1f01d520a0547e23e0c2a3440d4d8ad399e1089c0ba1f8 | Lab65a207dc-e0aa-484a-9f43-fd683e4958a4；暗室97dd376a-0628-4a66-a15e-5a81aa495a7e；主图894416d6-a8cb-4f28-8bbd-213860ab830c；两单路run1e572021-24f5-43fe-9d8f-bed66261e6d7/e3baf465-60bc-430d-af83-ac8e1cd9b291 |

## E01～E15 逐分支结果

“软件通过”仅指列出的输入→消费者断言，不包括未验边界。A 为真实编程 HTTP；B/C 为真实浏览器与服务端，编程请求在原日志单独标注。

| ID | 真实结果及消费者 | 原件/边界 |
|---|---|---|
| E01 | 软件通过：组合 POST/PATCH/GET、真实模板 import、局部 SA+sgh 显式转换；非法最终 pair 422 原子不写；SQL opaque/稀疏保形 | A `cases/test_e01_combined_post_patch_get_and_real_template_conversion.json`；不是硬件声明验证 |
| E02 | 软件通过：正常/参考引用、删/改口、错误pair、删边、BSE冲突两入口10反例；合法整体重接、unknown不获贯通 | A `cases/test_e02_cross_mode_references_atomic*.json`及合法正例；conversion伪造delete字段拒绝，不称支持删边 |
| E03 | 软件通过：cable/receive_cable 4→2→4；0/null/半组拒绝/phase30不变；正式正常末边2/0/None，参考线拒正式资格 | A `cases/test_e03_http_group_undo_zero_unknown_and_terminal*.json`；未选owner/上游组由同轮4d loss_truth覆盖 |
| E04 | 软件通过（V1新证据）：生产受控采集→采用→两次冻结；metadata/owner保存后28 dB一次、probe_gain=0；pin/pair改接拒旧匹配；三次历史GET200，1/1/2条且旧记录不变 | V1 `cases/test_e04_e05_selected_reference_pa_http_metadata_owner_and_two_freezes.json`、`application-history-sql.json`；原A历史GET实际422仍未验，不能据669改写原结论 |
| E05 | 软件通过（V1）：非空selection含pa-reference-edge；仅改PA metadata，数值键仍缺省；正常/参考摘要、旧run/证书/冻结不变，重新确认新freeze28 | V1同case；executions b2fbd306-7b3a-4e98-813a-a0545c732b7c/9ae04bf4-af01-40ee-ae51-ce4da2e33c6e；VISA仅脚本化transport，completed置值不是完整硬件执行 |
| E06 | 软件通过：历史缺ports/internal_paths参考receive_cable owner保存后scope/compare200需review；selected-route/采集422、零新增有效采集/采用；无calibration模式不投影 | A `cases/test_e06_legacy_reference_scope_not_capture_permission.json`；盘点不是资格 |
| E07 | 软件通过：六类0/3.25/null共18分支，真实抽屉→保存→GET→重载；单位/来源/频段、负衰减/倒序拒绝。旧CAICT PA 0/14.5/null，线损0/null/2；旧字符串12只改metadata仍保形 | B `nominal-*.log`、`caict-revised.log`、`zero-revised.log`；C `legacy-metadata.log`；SQL807次采样与audit，不当实测 |
| E08 | 软件通过：当前注册∪菜单∪旧图19类逐抽屉保存；目录引用持久化且目录不变；线缆无第二损耗、BSE逻辑/物理分离、空气虚拟、unknown非双向 | B `inventory-revised.log`；C `catalog.log`；19仅本次集合快照，不授能力 |
| E09 | 软件通过：PA/pad/combiner空pair无路径、加IN→OUT各一条零损耗路径；删引用口/错方向拒绝；真实鼠标连线、拖动保存重载 | B `pairs.log`、`lifecycle.log`；C `pair-routes.log`；开关沿原port_maps，不验证实物继电器 |
| E10 | 软件通过：原CAICT图旧PA边conn_ce_b1_to_hprobe_1v三次保存源/展示/请求同ID，nodes/modes/非目标边和模板不变；ce/bse/sa三类型预览→取消不写→确认→重载 | B `caict-revised.log`、`conversion.log`；C `audit.json`核原SQL；模板hash9532474f6106b452349a9b84ea1509d6f00702c6e9036b04969e132d965fce91 |
| E11 | 软件通过：owner/alias只读定位/撤销；通用2→4、正式末边2；0/null/2对应通用2/null/4，UI未知/零；参考owner仅scope | C `owner.log`；B `owner-revised.log`、`zero-revised.log`；不授参考接收线正常运行资格 |
| E12 | 软件通过：取消不泄漏、应用未保存不写；真实离线失败保留→恢复成功；缺端口PATCH422→修正重载 | B `lifecycle.log`、`retry.log`；均有HTTP/GET/SQL，不仅toast |
| E13 | 软件通过：pending锁、预览迟到、409保输入重预览、dirty阻Lab/清洁甲乙甲、两开关切换取消旧会话；独立无历史图重导入200；FK哨兵引用409且raw不变 | B `lifecycle.log`、`retry.log`、`reimport-revised.log`；C `races.log`、`replace-protected.log`。旧主库普通执行历史不能保护，200替换/后续404失败保留。哨兵只证明引用保护，非采集/confirmed/资格 |
| E14 | 软件通过但范围受限：两单路start202/running→取消无回执锁定→服务器cancelled后软件编辑/保存/再入；样本[]、net_loss=null、formal_eligible=false、采用422。两批人工等待→确认continue→completed、items simulated | C `collection.log`；B `batch.log`。cleanup_confirmed/F64 release=null，不证明停发；真实cleanup_unconfirmed/interrupted未验。固定直连selection无开关目标，无独立实物I/O监测 |
| E15 | 部分通过：旧参考scope/compare200需review、GUI盘点/比较；selected-route/实际采集422零新增；诊断历史JSON与历史配置/结果哈希不变 | C `legacy.log`、`collection.log`、`audit.json`。该诊断流程无专属下载入口（不适用），正式报告下载未验，不称客户正式报告通过 |

器件全集：air_path、amplifier、antenna、bse_port、cable、ce_port、channel_emulator、combiner、communication_tester、emcenter、pad、probe、receive_cable、reference_antenna、sa_port、signal_analyzer、switch_slot、termination、vna。

## 证据完整性与残余边界

Task2现存142份临时原件、97张截图索引已独立核hash；首轮部分同名截图被覆盖不可恢复，明确保留P2缺口，不补造/重跑冒原件。各失败目录与数据库均保留，修脚本/fixture后另库复验，不把fixture错误当产品RED。原4a三项未再现异常根因仍未知；本片V1/鼠标拖动是新证据，不回写4a/4c当时未验结论。

所有Python运行在导入前限定新SQLite与两个true开关，默认bootstrap后显式设Mock并核所有category/Lab binding。旧采集fixture仅在专属库用real语义＋脚本化VISA替换外部transport，不触硬件；不能声称旧测试所有阶段绑定都为Mock。所有示例量值均隔离验收输入。

## 最终验证与复用

本片未跑新版全量；旧7945 passed/17 skipped/1历史G8 failed只是4d前片结果，不冒充4e。累计diff仅局部验收/文档，无共享生产、schema、fixture或依赖变化，未触发最终全后端条件。

原相关集669 passed/3598 warnings/466.18s未重跑；原轮HTTP历史422不算通过。V1修订定点1 passed/60 warnings/2.97s独立保留，不能相加叫670或新版669。Task3核原清单所有api-service/gui已跟踪输入，仅本片测试与原清单不同，恰等于V1清单；其余生产/依赖/共享fixture相同，新增浏览器专用文件不被旧pytest导入。依据和hash差异存`/tmp/pc04a4e-task3-haS6yY/reuse-audit.json`。GUI88/build本片重新执行；最终统计与独立新库G8见[Task3报告](../../.superpowers/sdd/2026-10-27-pc04a4e-device-contract-acceptance/task-3-report.md)。构建保留axios、service.ts动态/静态导入及chunk>500kB警告，不为消警告修改生产。

指南见[拓扑器件声明操作](../guides/topology-device-contract.md)。本摘要不替代最新HEAD独立审查或PR外审；R2无P1即收口，仍有P1则修复并续审覆盖最新HEAD。B/HOLD、ASC/CE、PG、实物计量仍未验。
