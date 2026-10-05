# P2-79A：信道资产型号归属设计

状态：用户已批准完整实现 P2-79；本稿为 A 片实施约束，B 在 A 合并清理后独立实施。

## 目标与可观察故障

同一个 channelEmulator connection 在 F64/FS16 切换后，SCD 投影仍聚合该 connection 下所有关联文件，随后镜像进当前型号 preset。结果是另一型号的资产进入当前清单；只修旧 SCD 表还会漏掉现代 ChannelAsset 执行入口。

目标：实体归属、目录投影和新执行冻结使用一致的 connection＋instrument_model_id；不按型号名、文件扩展名或当前选择猜历史归属。

## 实证前置

- 基线：origin/main `6a460170`；工作树 `codex/p2-79a-channel-model-ownership`。根目录已批准但未提交的排期文档复制到本片，原件保留，不覆盖用户未跟踪资料。
- memory 查询完成；历史审计仅作背景，当前结论来自代码与只读 SQL。
- NotebookLM 不适用：不新增/修改 SCPI、仪器参数语义或回读单位。
- 2026-10-05 运行库只读盘点：standard_channel_definitions 0 条；channel_assets 的 vendor_file 20 条，其中 2 条有 connection，18 条无 connection。2 条中仅 1 条带 smu_project_truth；该证明包含文件内容/路径/频率，不含型号身份，不能据此认领型号。运行库 Alembic head `b9d2f4a6c8e0`。
- 基线命令：`DATABASE_URL=sqlite:////tmp/p2-79a-baseline.db USE_MOCK_INSTRUMENTS=true .venv/bin/pytest -q tests/test_standard_channel.py tests/test_p2_58_2_channel_emulator_preset_sync.py`，45 passed，85 warnings。仅隔离 SQLite 功能基线，不是 PostgreSQL 并发证明。

## 方案选择

采用显式实体字段，而非按型号名称过滤或另建分桶归属副本。

1. StandardChannelDefinition 与 ChannelAsset 增加 nullable instrument_model_id，引用 InstrumentModel。nullable 只为历史未知归属/非 vendor 资产；新仪器文件必须明确归属。
2. 新 SCD 的唯一键改为 connection＋model＋standard_name；历史 NULL 项保留原记录，不能通过 NULL 绕过新建校验。同名跨型号可保存，不扩大 ChannelAsset 已有 name/canonical_name 唯一策略。
3. 现代 vendor_file 归属以 ChannelAsset 为真值；legacy-only SCD 才读旧表。同 id 的历史 SCD twin 不能覆盖 ChannelAsset，也不新增双向同步机制。
4. standard_3gpp/custom_static/rt_dynamic 不强加硬件型号归属，不限制软件生成源的既有路径。

## 写入与操作员确认

- 新建/关联请求明确携带 model UUID；服务端检查该型号属于 channelEmulator 类别，且与操作员请求的活动 saved 型号一致。GUI 发送已保存型号，不发送尚未保存的草稿型号。
- 缺失、错类别、已切换的旧页面请求受控 4xx，不能服务端顺手认领当前型号。
- 已知归属不可因普通文件关联而改变；改归属必须是显式操作且通过同一校验，不能靠 notes 或当前 selection 隐式重绑。
- 历史未知 vendor 资产在工作台显示“型号归属待确认”。既有资产更新端点支持显式 connection＋model；GUI 单项/批量统一使用原子归属确认端点，逐项显示文件和已保存型号/地址。legacy-only SCD 通过既有关联请求确认，同 ID 现代资产只能在信道工作台编辑，不另造数据库修复 API。
- 操作员确认仅确认文件归属，不表示文件存在、现场认证通过或正式 KPI 可用；既有证据资格门不变。

## 投影与切换

- _sync_projection_for_binding 只将明确归属于该 saved 型号的 SCD 派生项写入对应 preset；活动型号匹配才更新活动 connection_params。不借当前型号重新归属源实体。
- 删除/改关联依据源记录的 owner 更新对应型号，即使当前选了另一个型号，也不得污染那个型号或留下原 owner phantom。
- 切型号保存、手动增删模型、扫描发布共同核验派生项归属；存量手工条目保留，不把“没有 scd_id”当跨型号证明。
- 原有受控扫描是开发/诊断路径，不新增 SMB 正式依赖；扫描发布写入当次明确的 saved 型号身份，但不使扫描证据获得正式资格。
- 本片只实现归属隔离。跨请求丢更新及同序锁完整性单独交给 P2-79B，不将本片 SQLite 测试宣称为并发验收。

## 迁移与历史策略

- 本次 migration 只增加字段/索引/约束并保留历史数据；不拿 migration 执行时的 selected_model_id 回填过去的归属，不按 .smu/路径/文件名猜 F64。
- 因当前历史载荷缺型号证据，20 个 vendor_file 不自动回填；这会使归属未知项不能启动新的绑定执行，GUI 必须提供可见且受控的确认入口后才交付。
- 旧活动清单/preset 中 SCD 派生项先审计、再从正式活动投影排除未知或错 owner 的项；保留原源记录与手工条目。不得删除历史执行冻结载荷或重写旧 digest。
- migration 的正反例在隔离 PostgreSQL 测试库验证；开发阶段不迁移运行库。运行库只在 PR 合并、main 同步后迁移。

## 执行边界与冻结兼容

- 新 vendor_file 与 legacy scd_id 请求均在任何仪器 I/O 前检查 owner connection/model 对应同次冻结 CE binding。未确认/错 owner 为配置错误；Mock 不能掩盖错归属。
- ChannelAsset resolution 的 executable content digest 纳入 owner；冻结版本显式升级，新版拒绝缺 owner/漂移/篡改，不向旧载荷默认塞字段再重算 digest。
- 旧冻结件仍按其原版本/原 payload/digest读取历史，保留已有资格判据，不给它补当前型号。历史读取兼容不等于允许新执行跳过 owner 检查。
- MEASURE 只消费冻结身份并校验资产漂移，不在执行中自动同步当前配置；报告不查询 current selected_model_id 回填过去。

## 全集与验收关系

| 路径 | 生产位置 | 本片责任 |
|---|---|---|
| SCD CRUD/关联/删除 | models/standard_channel.py、services/standard_channel_service.py、api/standard_channel.py | owner 校验、按 owner 重建/移除投影、历史待确认 |
| 现代 vendor_file CRUD | models/channel_asset.py、services/channel_asset_service.py、api/channel_asset.py | owner 单一真值、显式确认、非 vendor 保持现状 |
| 扫描发布 | services/smu_project_inventory.py | 发布绑定 saved 型号，不改 SMB/SCPI 语义 |
| preset 保存/模型增删 | services/channel_emulator_model_preset.py、api/instrument.py | 防止旧派生项重新进入错误型号，保留手工配置 |
| 新执行 freeze/MEASURE | services/channel_emulator_execution_plan.py、services/mimo_ota/channel_asset_resolver.py、services/standard_channel_service.py、services/mimo_ota/executors/measure.py | connection/model 一致、首个 I/O 前拒绝、owner 纳入冻结版本 |
| GUI/API 镜像 | StandardChannelDefinitionCard、ChannelAsset 工作台、App、API service、live OpenAPI、api/openapi.yaml、api.generated.ts、手写类型 | saved 型号 query key、草稿切换/race 错误、待确认与显式操作 |
| migration/历史 | 新 Alembic revision、旧冻件版本读取 | 不猜归属、不重写历史 digest、单一 head |

相对路径均以 api-service/app 或 gui/src 为根，具体变更文件在实施计划按全仓搜索列全；不按此表盲改不存在的组件。

必须证明：F64→FS16→F64 切换不混资产；非活动 owner 删除/关联不会污染当前型号；跨型号同名 SCD 可独立维护；未知历史不会被当前型号自动认领；现代 vendor 与 legacy scd 入口均拒绝错 owner；已冻结后改 owner 首个 I/O 前失败；软件生成资产未受限；API 四镜像与真实 GUI 操作契约一致。

## 验证与交付

本片属共享契约/冻结/迁移档：逐功能 RED→GREEN、受影响生产链正反例与回归，稳定版本最终后端全量一次，GUI 契约/build、compileall、隔离 PostgreSQL migration、单一 Alembic head、diff-check。按已批准流程 fresh 功能审查、Ready PR、Codex R1→R2，覆盖最新 HEAD 无 P1 后合并同步清理。

实现与隔离验证进行中，无运行库写入、无仪器 I/O。P2-79B 在 A 闭环后开始。
