# PC-04A-4d 旧拓扑显式转换验证

当前状态：R1修复`a50137061674a2837fef70da6f6221ffdfcc7d30`已独立ADDRESSED；该版全后端 **7945通过/17跳过/1历史G8失败**（793.12s，exit1），不称全绿。Task4及前累计内审已完成，但未发现此前R1组合回归，不能替代本次新版验证。待本文档增量独立审查、push及R2，尚未合并；4e未启动，现场B/HOLD不解除。旧7941/17/1仅为R1前记录。

## R1新版验证（当前输入）

R1修复的是：正常链已解析、历史参考receive_cable缺ports/internal_paths时，显式owner保存成功却使普通scope/compare错误422。普通盘点中的owner投影现只取所选正常链保存路径及从该probe可达的保存参考边声明；存在模式的空active_connections按modes回退，不存在calibration模式则不投影。显式topology、selected-route和实际采集仍走原严格入口；盘点200不授予采集资格，不改物理identity、历史baseline或整链补偿。

唯一责任位于`/tmp/pc04a4d-r1-final-uBsqpf/`执行一次新版全量：**1 failed,7945 passed,17 skipped,9654 warnings in793.12s，exit1**。2026-10-27T04:01:12Z开始、04:14:32Z结束，HEAD起止均a5013706。1196项源码/测试/schema/依赖、373份跟踪Markdown、Python依赖及独立seed脚本运行期间起止全部一致；核对完成后才更新本文。stdout SHA256=`04577744be38b0ce8a4fbc09d977ae36015fe407adf2e531380b4b2e4802aaa2`，stderr为空；stdout/stderr/exit、起止清单及seed记录均保留。9654 warnings未逐条归因，不称全部既有。

初次app导入前full.sqlite不存在，环境显式Mock/default bootstrap；`seed_mock.py`默认bootstrap后将7/7类别设为Mock并核对。默认bootstrap没有Lab，初始bindings清单为空；后续各测试使用其隔离fixture，不声称旧测试始终保持强制Mock字段。随后同库运行（api-service cwd）：

```sh
env DATABASE_URL=sqlite:////tmp/pc04a4d-r1-final-uBsqpf/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4d-r1-final-uBsqpf/logs .venv/bin/python -m pytest tests -q
```

唯一失败精确仍为下文同一历史G8文件第111行同UUID引用；门/历史相对39d4bb0b diff为0，hash仍cb9c219…/57aaf772…。没有其它失败，不改历史或门。本轮未重跑GUI、build或浏览器；R1相对7e8c2270的GUI/OpenAPI diff为空，旧GUI74项/build13.38s及D01～D12浏览器原件仅复用于未变输入，不冒称新的历史参考图组合已做新版DOM验收。R1最终81项相关集属a501输入，较早193项属于无模式收窄前输入；新版完整回归只以上述本轮全量为准。未验证真仪器/PG或解除现场资格，资料与证据全部保留。

## 已实现入口与量值边界

当前Lab → 实验室配置 → 射频拓扑 → 转换旧配置。沿原编辑器逐项声明器件类型、真实端口/方向、CE身份、内部pair、原边损耗及显式同线缆owner；先预览差异，再确认保存。取消/打开/预览不自动迁移，脏草稿须先明确保存；保存失败保留输入，409要求重新预览。切Lab、切图/开关及重导入使旧会话失效；采集和保存pending保持软件锁。

GET是可能转型/默认化的展示模型，不是数据库原JSON证明。原值存在性及格式以本次preview的before/before_present、只读candidate和SQL为证据，范围分别说明。旧字符串未修改时保形；缺键/null不是0；calibrated 0优先；任一未知hop使通用总损耗未知。节点不保存第二份线缆损耗。

同线缆两侧各2，仅在操作员逐组明确确认并选择owner后：通用4→2，正式旧binding仍只取末边（末边alias时换源至同路径owner），不是多段求和；owner0/unknown不回退alias。撤销恢复两侧原值各自参与。正常/参考物理身份不因归属改变，当前scope提示复核；原占位0纠正为真实末边仅改当前scope，不回填历史。独立confirmed整链仍一次，模拟结果不进入正式PASS/资格。

## R1前综合矩阵（未变部分复用）

调试原件：`/tmp/pc04a4d-OguahX/`；顺序终验新库：`/tmp/pc04a4d-VFJmbm/`。两个库均在app导入前指定新SQLite、USE_MOCK_INSTRUMENTS=true、BOOTSTRAP_ON_STARTUP=true；默认bootstrap后显式修改并核查全部category及Lab binding为Mock，端点仅192.0.2.x。并非现场数据或硬件验收，不碰用户默认库。

终验对象：Lab甲 `60853901-fcc2-440d-abda-1d67be44dd0e`，原展示图 `cbc731f4-4a22-46b2-8217-3a419e925e28`，第二开关图 `f335c224-1995-44fb-9e72-ff6a97cace3f`，CAICT源图 `0607a7bb-89d1-47e2-8c79-b541505b1d85`；Lab乙 `328abe24-a5c3-449e-af70-ec5a79cc568a`，展示图 `69019b88-263a-481b-84d8-b5990f191dc5`。源图、展示图、第二开关图不是同一对象。

| 项 | 证据入口与本片断言 |
|---|---|
| D01 | 新库fixture真实原import；`api-matrix.log`仅证明preview后GET不变及显式单边转换同ID；`source-ui.log`另证明原Modal真实点击取消后GET不变、再次明确预览/保存；模板hash前后核验，未静默整模板转换 |
| D02 | 浏览器三类节点保持ID显式换type；`test_three_old_types_keep_raw_identity_and_opaque`及invalid/BSE冲突反例；SA转换不新增资格 |
| D03 | 本片新增`test_task4_raw_sparse_loss_survives_unrelated_conversion`覆盖缺键/null/0/旧非空/typed旧字符串，SQL原行保形；原loss_truth覆盖calibrated0、多hopNone及真实Lab/scope；GUI相关测试和真实转换DOM |
| D04 | `flow.log`真实owner预览、保存重载、alias只读、撤销；loss_truth覆盖owner0/unknown、上游组末边3及非法引用；新增六类来源/旧集成PA保形真实HTTP，不拆PA、不增加节点数值副本 |
| D05 | 本片重跑转换、4a最终图、4b端口、4c内部契约集；多模式/显式路径/pair/mapping冲突422，HTTP及SQL前后由证据插件逐case保存 |
| D06 | 真实TestClient零SQL写预览、错误scope404、双连接读后写前CAS409/新快照成功及name不覆盖；default/import保护相关回归。没有PG实跑；不以SQLite证明PG事务实测 |
| D07 | `flow.log`取消/保存失败/断网恢复/换Lab迟到；`mouse-switch.log`真实第二类别选择及在途切图（遮罩下仅切图事件使用原Select处理器，另有真实鼠标选择，不将处理器调用冒充鼠标） |
| D08 | `flow.log`保存pending；`collection.log`真实单路running、断网取消未知锁定、软件终态后两次编辑保存；批次运行/取消未知见`batch.log`，Mock取消不推断真实释放 |
| D09 | 425项相关集含原单路/批HTTP、Mock结果不可采用及固定直连零switch I/O；新库真实单路采集与批次预览/完成，未声明/未知仍拒绝 |
| D10 | loss_truth正常/参考identity、scope复核、confirmed整链一次及真端点拒绝；新增真实Mock诊断报告generate/detail/download前后字节hash不变与既有execution配置不变，不冒称客户正式报告 |
| D11 | loss_truth真实Lab入口未知在lease前失败、已知0通过；独立confirmed未知nominal仍一次28，不额外扣/加2 |
| D12 | `mouse-switch.log`原画布真实鼠标移动、显式应用/PATCH、重载后重新选择第二开关核对坐标及名称、删除仍引用边拒绝。仅本片证据，不补写4c C07历史 |

TestClient证据插件不替换响应，保存HTTP请求/响应及每case数据库前后JSON；浏览器脚本无route mock，CDP仅延迟网络。截图在`output/playwright/pc04a4d-task4-*.png`及原转换脚本命名截图；源/展示/请求对象ID在结构化日志内。矩阵由真实HTTP、SQL、运行消费者和浏览器交叉组成，不声称所有反例都由DOM点击执行。

## 命令与已结束统计

- API相关集：两新增测试及4a/4b/4c/recovery/freeze/原单路/batch_api/batch_safety，`OguahX/related2.stdout`：425 passed /1540 warnings /210.75s，exit0。
- 新增稀疏及六类来源/集成PA：`OguahX/supplement.stdout`：11 passed /52 deselected /139 warnings /9.98s，exit0。
- 新增真实报告读/下载：`VFJmbm/report.stdout`：1 passed /63 deselected /50 warnings /1.46s，exit0。
- 稳定后两新增测试全文件：`VFJmbm/final-related.stdout`：119 passed /1061 warnings /101.25s，exit0；HTTP 424条及逐case SQL快照在`final-api-evidence/`。前述425项相关集HTTP1120条另存，不将两者统计相加冒充无重复用例数。
- GUI相关9文件：74 tests /74 pass /0 fail，801.773ms，exit0；`npm run build`：13.38s，exit0，既有大bundle警告保留。

D03另有纯观察补充新库`/tmp/pc04a4d-8NEG3s/`：同一未改fixture默认bootstrap并全Mock后，在启动服务前显式设置第一边null、第二边0。真实浏览器读图`334a3416-518f-4497-ba35-5410169b4119`，边DOM分别为“损耗未知”和“0.0 DB”，没有None或未知补0；原SQL前后完全一致。临时浏览器观察脚本/hash、GET/DOM/截图与关闭日志留在该根；它不参与pytest输入，未改冻结源码、测试、fixture或依赖，不因此重复全后端。

D01追加真实Modal源图取消/保存：同补充库服务关闭时仅增加全Mock展示类别并关联原import源图`f2718d21-e168-4d01-b208-62d4e6f34a8c`（不改nodes/边/模式），从原选择器选该源图；88节点/90边。`source-ui.log`真实预览→点击取消的GET完全一致，再次明确预览/保存，仅一条选定边0.3→null，ID与nodes不变，HTTP `[200,200,200]`，非整模板转换。SQL前后、截图与脚本hash保留；类别仅用于隔离GUI展示，不是pytest输入，不改冻结仓库fixture。D02的ce旧型转换实际发生在`flow.log`，bse/sa发生在`api-matrix.log`，不把后者已转型ce的同类型声明重算为旧型转换。

所有命令使用仓库`api-service/.venv/bin/python`；具体完整参数、stdout/stderr、exit文件及最终输入hash见Task4报告和证据根。历史4c的7822/17/1不属于本片统计。前Task RED/变异只作前序出处，本片未改生产逻辑，不虚构新的产品RED；脚本导航、Select定位、Fit View动画及取消锁契约调试失败单列，不当产品缺陷/通过。

## 未验边界

无真实硬件、RF停发、实物同线缆核验、参考件证书/计量溯源、正式采用或现场B验收。PostgreSQL CAS未实跑。模板原件和历史记录不改写；4c C07历史未验仍保留。六类标称/参考PA来源保形不等于关闭旧4a V1有效参考PA正式身份/冻结的未验边界。Task4/前累计及R1修复增量内审已完成；新版仍待文档增量审查、push/R2，不能称合并或现场通过。

## R1前全后端与关闭记录（历史原件保留）

首次冻结输入完整全后端在`/tmp/pc04a4d-final-v4sN3x/`执行，7959项，实际 **7934 passed /17 skipped /8 failed /9616 warnings，802.23s，exit1**。1196项源码/测试/契约/fixture/依赖输入起止完全一致，依赖和HEAD亦一致。stdout SHA256=`46086815a7647965e23597c0e41e03dc5bd306a6583bf177625a934964e83d6a`。不隐去这轮失败。

7条为旧租约/内部可达性测试未声明损耗却假定零：3条Lab-profile租约场景提前被unknown门拒绝，4条内部路由场景实际None而旧断言期待0。主代理核trace/实际输入后批准，仅在`test_p2_30_task_level_lease.py`四个构造及`test_pc04a4c_internal_routes.py`三个测试的本地边明确已知0；原断言、不可达None、共享fixture、MultiFrequency构造及生产未知门不改。另补只读preview禁止访问HAL的实际断言。定点回归后重新冻结，由同一责任位唯一补跑；不是同输入为审查身份重跑。

修订定点在`/tmp/pc04a4d-fix-s7bN71/`结束：lease整文件+loss_truth+preview零HAL/DB写 **65 passed /526 warnings /47.89s，exit0**；4c内部路由整文件+loss_truth **123 passed /1105 warnings /110.37s，exit0**。补跑全部输入重新冻结于`/tmp/pc04a4d-final-ACiV4H/`，实际结果见下方最终补跑记录；不将前述119项或首轮7934通过冒充新最终输入结果。

第8条唯一G8仍只命中`docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md`第111行的历史UUID执行URL；该历史文件与门相对39d4bb0b无diff，当前/基线SHA分别为`57aaf7726ffbf697d2ba3e7c21a91f57509b88f0e282ac39b16f56dcdba357c3`和`cb9c219f3380d0e4d0ef200eecaa86aef801107957152d18205e4b2cbf0716ed`。不改历史/门、不称全绿。

最终补跑实际结果：`/tmp/pc04a4d-final-ACiV4H/`，**1 failed,7941 passed,17 skipped,9618 warnings in799.05s，exit1**。2026-10-27T02:41:42Z开始、02:55:09Z结束；唯一失败仍为上述同一历史G8，无其它失败。1196项源码/测试/schema契约/fixture/依赖清单起止逐一OK、清单cmp0、Python依赖cmp0、HEAD均3c49bdc8。交付MD不在此源码清单；状态/统计收尾不改路由语义，另以G8定点确认。stdout SHA256=`6ac50c02f61b1e2ab5e5614d650226bdfd9d0769ebc7a8a4b3b4d2b2a4cb9116`，stderr为空；完整stdout/stderr/exit及起止清单保留。不把9618条warnings未经逐条归因称为全部既有。

命令（api-service cwd；app导入前新库不存在）：

```sh
env DATABASE_URL=sqlite:////tmp/pc04a4d-final-ACiV4H/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4d-final-ACiV4H/logs .venv/bin/python -m pytest tests -q
```

专用API/Vite均按已核PID关闭，具名浏览器仅关闭本任务会话；最终18098/5193无监听。所有数据库、venv、output、scratch及失败原件保留。实施者自查，非独立内审；后续独立/累计审查及PR流程交主代理，不提前4e。

文档状态/统计收尾后G8定点：新库`/tmp/pc04a4d-g8-Y3KrHq/check.sqlite`、同隔离环境，api-service cwd执行`.venv/bin/python -m pytest tests/test_rule_gates.py::test_g8_docs_only_cite_live_plan_routes -q`，**1 failed /40 warnings /0.97s，exit1**，仅同一历史文件/同UUID引用。后续仅补此统计和无路由字面量的证据说明，不改G8语义输入；不是另一轮全量。
