# P2-79A 实施计划

> 执行：使用 executing-plans 顺序执行；任务共享模型/冻结/API 接口，主代理负责实现与集成，不并行写共享文件。最终 fresh 独立审查只读。用户已授权完整 P2-79，不再请求逐步批准。

**Goal**：仪器文件资产明确绑定 connection＋model，切换型号不污染清单，新执行不使用未知/错型号资产。

**Architecture**：复用现有 SCD/ChannelAsset、preset、freeze 与现有 CRUD；ChannelAsset 为现代路径真值，legacy-only SCD 兼容。不猜历史归属、不新增仪器命令。

**Tech Stack**：SQLAlchemy/Alembic、FastAPI/Pydantic、React/Mantine/TypeScript。

**Spec**：[设计](../design/2026-10-05-p2-79a-channel-model-ownership-design.md)。

## Global Constraints

- WIP=1；A 合并同步清理后才启动 B。
- 不新增/猜测 SCPI，不操作真机，不增加 SMB 正式依赖，不改正式 provenance 白名单。
- 历史未知归属保留为 NULL，需操作员显式确认；旧冻结 digest 不改写。
- 草稿型号不写入 owner；服务端核验 saved selected model，过期请求受控拒绝。
- 单项/批量确认均明确列出资产与目标型号/地址；批量原子全部成功或全部拒绝。
- 迁移开发验证在隔离库，运行库迁移只在合并同步后执行。

## Task 1：持久模型、归属校验与迁移

文件：models/standard_channel.py、models/channel_asset.py、services/channel_asset_ownership.py（新）、services/standard_channel_service.py、services/channel_asset_service.py、新 Alembic revision；测试 tests/test_p2_79a_channel_model_ownership.py（新）。

接口：`validate_channel_asset_owner(db, connection_id, model_id, require_selected=True)` 返回合法连接；空归属、错类别、错连接、过期 selected 抛 ValueError。服务写入将其转换为各自业务错误。

- [ ] RED：造同 category 两个 InstrumentModel；F64 SCD 关联后切 FS16，清单不得含 F64 文件；缺 model 新建拒绝；显式历史确认成功，错 selected 不写。
- [ ] Run：`DATABASE_URL=sqlite:////tmp/p2-79a-tests.db USE_MOCK_INSTRUMENTS=true .venv/bin/pytest -q -o log_cli=false tests/test_p2_79a_channel_model_ownership.py`，确认功能断言失败后改实现。
- [ ] GREEN：新增 nullable FK、SCD 型号唯一约束，validator 统一检类别与 saved selection；vendor_file 新建必须归属，软件生成源不强绑型号。迁移不回填历史归属。
- [ ] 运行该专项与 SCD/资产 CRUD，fixture 新建补齐显式 owner；旧数据测试直接构造旧记录，不让 fixture 静默采用 current 型号。
- [ ] 提交 Task 1，记录 RED/GREEN 命令、统计与版本。

## Task 2：投影、非活动 owner 与扫描发布

文件：standard_channel_service.py、channel_emulator_model_preset.py、api/instrument.py、smu_project_inventory.py；测试 preset sync、SMU sync 及新专项。

- [ ] RED：A owner 在 B 活动时关联/删除，只改 A preset；保留手工条目与 B preset；旧错 owner 派生项不能经保存重新进入当前清单。
- [ ] GREEN：按 source owner 重建对应 preset，活动匹配才镜像 connection_params；标记派生 owner，操作员非派生项保留。扫描显式冻结 saved model 并发布该归属，不改变扫描语义。
- [ ] Run：`pytest -q -o log_cli=false tests/test_standard_channel.py tests/test_p2_58_2_channel_emulator_preset_sync.py tests/test_p2_79a_channel_model_ownership.py`，再跑搜索出的 SMU 相关 tests。
- [ ] 提交；并发丢更新留 B，不声称 SQLite 证明行锁。

## Task 3：冻结与首个 I/O 前门

文件：services/channel_emulator_execution_plan.py、services/mimo_ota/channel_asset_resolver.py、standard_channel_service.py、mimo_ota/executors/measure.py、base_station_adapter_profile.py 的资产冻结调用（以实际搜索确认）；测试资产 resolver 与 CE freeze/measure。

- [ ] RED：现代 vendor 与 legacy scd 未确认/错 owner 都无法新冻执行；冻后改 owner 被拒；旧 v1 载荷按原 digest 可读，不补当前型号；非 vendor 原流程不变。
- [ ] GREEN：新版 resolution content 纳入 model_id；复用同次 CE frozen binding核验 owner，freeze 新执行及 MEASURE 对称门消费同一 validator；版本分支明确，旧 payload 不 redump。
- [ ] 搜索所有 freeze/commissioning/measure caller 并逐一列验收；跑相关冻结、证据与正式消费者回归。
- [ ] 提交。

## Task 4：操作员确认/API/GUI 四镜像

文件：api/standard_channel.py、api/channel_asset.py、gui/src/api/standardChannelService.ts、channelAssetService.ts、StandardChannelDefinitionCard.tsx、ChannelWorkbench/ChannelWorkbench.tsx、ChannelAssetForm.tsx、App.tsx、api/openapi.yaml、api.generated.ts、手写类型。

- [ ] RED：真实序列化响应含 nullable owner；列表按 saved connection/model 隔离；批量确认任一错误全部不写；GUI 请求带 saved model，NULL显示待确认，确认对话框逐项列名/路径/目标地址。
- [x] GREEN：CRUD字段/过滤，增加受控批量归属确认操作（不能客户端循环 PUT 冒充原子批量）；GUI 单项也复用同一原子确认端点（单元素数组），既有 PUT 保留显式更新。新建/关联与未知项确认使用 saved 型号；query key 含型号，切换清掉旧确认选择；完成四镜像生成。
- [ ] 跑后端 API/OpenAPI 与 GUI 契约，再 production build；提交。

## Task 5：稳定版本验证与交付

- [ ] 受影响链、隔离 PG migration、单一 head、compileall、diff-check；稳定输入最终后端全量一次。
- [ ] fresh 功能内审只读，不重复跑同输入全量；P1 最小 TDD 收口并复审，测试门意见最高 P2。
- [ ] roadmap 标状态、记录测试证据；推送 Ready PR，读取最新 HEAD/comments/reviews/checks 后请求 Codex R1，核实修复本片意见，确认远端 HEAD 后请求 R2；最新 HEAD 无 P1 且 mergeable/checks满足才合并。
- [ ] main ff-only 同步、运行库 migration、旧资料保留、清理本片工作树/分支；再创建 P2-79B 工作树与设计/计划，复用完整闭环流程。

## 执行记录

2026-10-05：设计批准；基线 45 passed。批量一个原子事务，此操作只改归属，不是 DB 修复或认证端点。Task 1–4 已实现并逐机制 RED→GREEN，功能提交统一在稳定验证/审查后进行（不机械按任务提交暂态）。412 passed/3 旧扫描 fixture 未提供 owner 的扩大回归后补齐 fixture；33 passed 复验通过。隔离 PostgreSQL `p279a_owner_20261005` 复制运行库验证 migration 到 `c1e3f5a7b9d2`，20 vendor_file 的 owner 仍全部 NULL，运行库未迁移。独立内审 P1=0，指出同 ID 旧副本投影、坏派生 ID、同名归属确认与 GUI 过滤选择问题，均最小收口；等待尾审及最终完整验证，不将中间结果冒充交付。

最终交付前验证：受影响链 418 passed（29.58s）；全量首次 6799 passed/5 failed/5 skipped（156.40s），5 个失败均为 migration 在新装 metadata 上重复加字段。修复并核对命名 FK/index 后新装/升级/降级链 6 passed/1 skipped（0.93s），全量复跑 6804 passed/6 skipped（151.78s）。之后仅收窄 NULL owner 不能与空 selected 相等、GUI 共同 catalog key/地址确认清除和 YAML associate 镜像，复跑全部目录/归属消费者 143 passed（12.51s）与 GUI 2 passed/production build（12.14s），复用未受影响全量结果，不称最后微调版本逐项重跑了全量。隔离 PostgreSQL online downgrade→upgrade 与约束/保留历史测试 2 passed（0.11s）；compileall、单一 Alembic head `c1e3f5a7b9d2`、diff-check 通过。fresh 独立功能尾审 P1/P2/P3=0。尚待 Ready PR 外审、合并/main 同步/运行库迁移/清理；B 未开工。
