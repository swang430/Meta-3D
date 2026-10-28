# PC-04A-5c 独立 PA：隔离软件验证

## 结论与边界

Task1 离线候选经真实复制、PATCH、历史预览/恢复及真实浏览器验证；完整正常模式的原图与候选都保留相同 32 个 CE/probe/极化身份。此文是软件验证记录，不是现场导通、RF 认证、实测校准、采集资格或 B/HOLD 解除证明。未修改用户原 CAICT、默认数据库、仪器绑定或用户服务；本机部署/备份/恢复演练/副本落地仍由主任务另行执行。

候选沿用原模式描述，实际 PA 结构以节点/连线为准。页面页脚仍可显示原“EMCenter 集成PA”说明；这是保形保留的旧描述，不能作为新副本结构真值。20 dB 仅迁为旧版标称/来源未核；原复合 0.8 dB、5 m 与 cable_type 只在 manifest 和 PA opaque 历史资料中留档，不分摊、不重复补偿。两段损耗保持 null，长度缺键，不新增 owner 或资格。

## 输入、隔离与唯一生产修复

- 基准提交：`37ff55c792abcb28a7d743e1cbff4dec1b426043`。
- 授权源身份：`87df2355-00f2-4fd6-9a38-ebacb2ccb2e5`；读取已跟踪 raw fixture，不访问用户库。原三图数组规范 SHA256：`a7177b02fd15e91fc035fb360616b5db18ac831bc677bd16dd538767eac16153`。
- 候选规范 SHA256：`7080b0e63ecedbcb95ef655fdf2f8065052cf35108d282c37eaea92bb1406037`；120 节点/122 边、32 新 PA/64 替代边。文件 SHA256：candidate.json=`2e2757da38aefddc56144cf7bbefa150897d0f0e4ad8bfd6cb045d183ba92a67`；manifest.json=`53647f5827d42e67777edd3606067f000cacc724cc42009610b313c094d1ed1d`。
- 证据根目录：仓库本机 `output/pc04a5c-task2/`；候选、manifest、逐路预览在其 `candidate-cli/`。
- 新 SQLite：`/tmp/pc04a5c-QJW6Fmit/test.sqlite`、同目录 `browser.sqlite`；首轮全量 `/tmp/pc04a5c-naWSXpB5/test.sqlite`；环境确认 `/tmp/pc04a5c-LcLCAbvl/test.sqlite`；最终全量 `/tmp/pc04a5c-8hoC5bJI/test.sqlite`。全部 DB 与证据保留。
- `pc04a5c_browser_fixture.py` 在任何 app 导入前严格校验路径、文件不存在及显式 Mock/bootstrap 环境；bootstrap 后重新读 7 类别、非空 7 绑定，全部 mock 且端点 `192.0.2.10`；实际初始化的 7 驱动逐个 `is_mock_driver()` 为真并 shutdown。两隔离 Lab/chamber 的新绑定也逐项核对。原 raw 仅替换外层数据库身份，三图数组不变。
- 专用 API 18116、Vite 18117；原 API/GUI 端口未连接、未重启。Vite 三类代理全部指向本片 API，未使用网络 mock。专用 API 启动时关闭重复播种；pytest 启动测试必须保留 bootstrap=true，见下文环境纠正。

完整模式先 RED：原 raw 的四条 BSE→CE 输入保留时 32 路成功，候选于 `_build_probe_binding` 抛出“正常测试CE源端存在回接”（`full-binding-red.log`，1 failed/40 warnings，exit 1）。主任务裁决后仅收窄该函数现有判据：实际节点 type 属于既有 BSE_TYPES 的上游输入允许；路径内 seen 回接及其它来源仍拒绝。不依赖名称、label，不过滤输入边，不改直连、显式路径、参考接线、schema 或模式。

GREEN 同时覆盖完整四输入/32 PA 输出、无 BSE 输入仍 32 路；probe/PA 回接、伪装 baseStation 标签、自环、多父边、中转环路及 BSE 中转拒绝。真实完整 TopologyService 原图/候选均解析出 32 路。输出子图的逐路断言另明确只取 manifest 对应两边，不冒充完整模式：CE→PA→原 probe、PA.in→out 唯一内部身份、两未知损耗源、末端损耗/总损耗/compensation 均 None。反向 pair、缺边、冲突 CE 声明、错 probe 不会通过对应身份断言。

两个进程内变异均实际 RED，未修改磁盘输入：恢复旧 CE 入边判据→1 failed；撤销插 PA→32 PA 断言得到 0，1 failed。原件分别为 `mutation-ce-input.log`、`mutation-no-pa.log`；恢复正常后集成 22 passed。

## 真实 API、恢复与资格边界

新增集成测试复用既有内存 db/client/world/lab fixture，通过真实路由 copy r1→PATCH 候选 r2；不直接 ORM 创建最终副本。保存 raw 与 candidate 全等（数值、缺键、opaque 均比），源全部列、revision、updated_at、历史计数以及正式选图 ID 保持；四张校准记录表及明确 synthetic 旧 execution freeze 不变。confirmed 只计一次与真实消费者正例复用既有 5b qualification/4a2 freeze 测试，未以 Mock 采集制造 confirmed。

原完整 raw 的显式校准查询为 422：“校准参考接线不能作为正常测试通路”。inactive 候选校准查询为 422：“实验室或拓扑已停用”。正常绑定已修不代表校准门已通过；未激活副本或启动采集。

原 copy r1 缺 F64/32 probe ports，r2 主动声明后恢复 r1 会删除声明：restore-preview、restore 均 422，当前候选/revision 2/历史内容零写。r1 只读查看，不改旧快照或放宽门。成功演练是 r2→仅 PA 位置变化 r3→恢复合法 r2 得到 r4，不是“恢复到原始 r1”。过期合法恢复 409、跨暗室 409、缺令牌 422、错 pin/半链 422 均核对失败零修订。

## 真实浏览器回执与截图

浏览器隔离 Lab：`1e8011ce-0d23-4dc0-9ccf-33008f9006bd`；暗室 `5e84fccc-fcdc-48ad-a2c5-80f449e13cf0`。

- 隔离原 raw 行：`736c8120-9940-4461-a29a-a4ca2101ee30`，active/default/r0；它不是用户源 UUID。其规范 raw hash 等于上述原图 hash。
- 主浏览器新副本：`d8770765-79f8-4a54-8af4-f483cdcf930d`，始终 inactive/非 default。
- 实际鼠标点击“复制已保存版本为…”→201/r1；真实 API PATCH 离线候选→200/r2，刷新页面后重新选回该副本。HTTP #550 copy 元数据在 `browser-copy-r1-receipt.txt`，r2 完整回执在 `browser-patch-r2.json`。r1/r3 旧网络响应 body 缓存经重载不可得（对应 response 文件为空），不将其冒充回执；用实际 HTTP 状态元数据、独立 raw 审计及不可变历史补足核验。
- 首/中/末 B1/B16/B32 都真实打开 PA 和两侧边；PA 20 标称、in/input、out/output、in→out，以及两边空损耗核对。浏览器紧密标签遮挡造成的早期 click 超时保留，最终按可见 SVG 交互线段真实鼠标点击并核对精确 connection ID；未调用 React handler。
- 实际鼠标拖 B1，位置 `(550,30)`→`(317.8500986193294,263.31065088757396)`，保存 200/r3、刷新重选；独立 raw 比对仅该位置变化，增益 20、两边 null、所有 opaque 原边完全相同（`browser-r3-raw-comparison.json`）。HTTP #865 元数据在 `browser-r3-network-receipt.txt`。
- r2 时历史 r1 只读详情、预览恢复 r1→422，页面明确 ce_f64 缺 ports，当前图不变。r3 历史面板选 r2→预览 #1130/200、确认恢复 #1131/200→r4。`browser-r2-preview-response.txt`、`browser-r4-restore-response.txt` 为完整回执。
- `browser-final-raw-audit.json`：主副本 r4 raw 精确等于 r2 candidate；r1～r4 历史可读，原隔离源全部列与 r2 前审计相同、历史仍 0；源 hash `a7177b…`、副本 hash `7080b0…`。
- 第一次旧令牌页虽 409，但第二次拖动没有实际形成 dirty；`browser-stale409-receipt.log`/`browser-stale-library-guard.log` 只作失败尝试留档，不算有草稿守卫通过。
- 主任务批准另建并发专用副本 `c58fbc3d-2c82-4842-800a-de52c69861f9`。真实属性表单把 PA 标签改为“真实未保存草稿 B1”，明确 dirty；外部真实 PATCH 将该专用副本 r1→r2，本页 expected=1 保存→409。回执 `browser-concurrency-dirty409.log` 证明 dirtyLabelPresent=true、discardDisabled=false；`browser-real-dirty-guard-status.txt` 证明库选择 disabled=true、仍为专用副本。主副本保留 r4，不为并发演练再制造主副本修订。

截图均在本机 `output/playwright/`，对应同一主副本 UUID：

| 状态 | 证据文件 |
| --- | --- |
| r2 B1 PA/入边/出边 | `pc04a5c-r2-pa-b1.png`、`pc04a5c-r2-edge-b1-in.png`、`pc04a5c-r2-edge-b1-out.png` |
| r2 B16 PA/入边/出边 | `pc04a5c-r2-verified-pa-b16.png`、`pc04a5c-r2-verified-edge-b16-in.png`、`pc04a5c-r2-b16-out-verified.png` |
| r2 B32 PA/入边/出边 | `pc04a5c-r2-b32-pa-verified.png`、`pc04a5c-r2-b32-in-verified.png`、`pc04a5c-r2-b32-out-verified.png` |
| r1 拒绝/鼠标草稿/r3 重载 | `pc04a5c-r2-r1-preview422.png`、`pc04a5c-r2-drag-draft.png`、`pc04a5c-r3-reloaded.png` |
| 合法 r2 预览/r4 恢复/标称复核 | `pc04a5c-r3-preview-r2.png`、`pc04a5c-r4-restored-r2.png`、`pc04a5c-r4-pa-b1-rechecked.png` |
| 另一个并发副本真实 dirty409 | `pc04a5c-concurrency-dirty409.png`，另见真实 disabled 状态文本；早期未形成 dirty 的截图不作通过证据 |

早期 `pc04a5c-r2.png` 为重载回主控台的非目标截图，不作 r2 图证据。浏览器 UI 中长度控件可能显示默认 0，本片未应用该控件；保存 raw 的新边长度依旧缺键，不能将控件默认值写作已测量长度。

## 命令、统计与结果复用

所有 Python 命令从 api-service、GUI 命令从 gui 执行，进程外先设新 SQLite URL、USE_MOCK_INSTRUMENTS=true。Python 3.13.14、Node 26.5.1；依赖使用 `uv pip freeze --python api-service/.venv/bin/python` 记录，venv 无 pip 模块的失败尝试原样保留。

相关定点原命令（`targeted-corrected.log`）：

```bash
.venv/bin/python -m pytest tests/test_pc04a5c_independent_pa.py tests/test_pc04a5c_copy_roundtrip.py tests/test_pc04a4d_loss_truth.py tests/test_pc04a4c_internal_identity.py tests/test_pc04a5a_topology_library.py tests/test_pc04a5b_topology_revisions.py tests/test_pc04a5b_topology_restore.py tests/test_pc04a5b_restore_qualification.py tests/test_pc04a2_route_freeze.py tests/test_rf_chain_resolver.py -q
```

294 passed、1178 warnings、112.53s，exit 0。早期命令误列不存在的 test_switch_orchestrator.py，exit 4/0 collected，保留 `targeted.log`，不算通过。

GUI：原 `node --experimental-strip-types --test` 命令因仓库 extensionless imports 导致 3 个文件加载失败（12 pass/3 fail，exit 1，`gui-tests.log`）。沿仓库已有 tsx 运行方式执行同五个文件：

```bash
npx --no-install tsx --test test/topologyDraft.test.ts test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts
npm run build
```

59 passed/0 failed，645.570708ms，exit 0（`gui-tests-tsx.log`）；build exit 0，13.03s，保留既有 chunk-size warning（`gui-build.log`）。不把 Node 原命令写成通过。

共享生产收窄触发唯一执行者全量；不因审查身份重复。首轮误给 pytest BOOTSTRAP_ON_STARTUP=false，13 failed/8135 passed/18 skipped/9764 warnings/811.66s，exit 1（`full-backend.log`）：其中 10 项启动/目录测试各自创建内存新库，依赖 true 播种而得到空目录；其测试、启动 hook 和目录定义对 BASE 无 diff。这是测试环境错误，不是“13 项历史失败”。主任务批准纠正后，两相关文件在新库 true 定点 17 passed/184 warnings/13.55s，exit 0（`bootstrap-env-confirm-tests.log`），未修改代码或 expected。

最终有效全量环境、bootstrap、依赖、输出：`final-environment.json`、`bootstrap-final.log`、`dependencies-uv-before.txt`/`after.txt`、`final-backend.log`。命令：

```bash
DATABASE_URL=sqlite:////tmp/pc04a5c-8hoC5bJI/test.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests -q
```

实际 **8146 passed、17 skipped、3 failed、9855 warnings，848.12s，exit 1**。仅三项既有门失败：G8 的旧 PC07A1 报告具体执行 UUID 路径；G11 的旧 4e 报告 ws 引用；gitignore 命中九份旧报告。未改历史、规则门或基线刷绿，不称全绿。exec session 35029；记录的启动 UTC 09:07:24Z、结束 UTC 15:45:58Z 间隔异常大，原样保留，原因未核，不把 pytest 848.12s 当作总墙钟。

代码/测试输入、环境真值记录、依赖清单起止 cmp 均 exit 0：

- final-tracked-before/after.sha256 清单自身 SHA256 均 `1a6ce5bc421a4d6db97bdc2de478763bbef60d22dd3e62192206829e2bb29942`。
- final-new-before/after.sha256 均 `edfea7eef4743f759d28da9ce0851685f3ebf0dce4b912e08cd45af3e6ab41cd`。
- final-environment-before/after.sha256 均 `6e7bded6b6dae1384e65be021fa60cae52c0d0eda68998171edf62a7378c483e`。
- dependencies-uv-before/after.txt 完全一致。

全量结束后仅增加本验证摘要、更新 roadmap 的 5c 当前状态、保存忽略目录下的 task-2-report；生产/测试/fixture/依赖不再变更，以上全量结果按输入内容复用。Task1 58 项既有定点过程不重复；本次 294 定点与全量均实际包含其测试。

新增摘要进入索引后，单独运行受文档输入影响的 G8/G11 两门：2 failed/40 warnings/0.99s/exit 1，仍只命中上述两处旧报告，未出现本片文档（`post-doc-gates.log`）；未重跑后端全量。自查 staged diff/禁令、完整路径正反例与源只读证据，diff --check 通过；这是实施者自查，不冒称独立审查。

## 收尾与未验

已按准确 PID/命令核验后只关闭本片 API PID 76881（18116）、Vite PID 76942（18117）和命名浏览器会话 pc04a5c；两专用端口随后无监听，HAL 记录完整 shutdown。SIGTERM 后会话 exit 143 是本片主动停止，不是测试失败。所有 DB/output/scratch 保留；未清理用户 output、venv 或其它数据库。

待主任务：独立规格/质量审查、累计审查、PR 外审/合并及授权本机落地。未执行本机用户库备份恢复、用户服务重启、正式 CAICT 副本创建、采集或现场验收。源码修复不代表旧运行用户服务已生效。没有任意历史均可恢复的承诺；r1 仍保持拒绝。
