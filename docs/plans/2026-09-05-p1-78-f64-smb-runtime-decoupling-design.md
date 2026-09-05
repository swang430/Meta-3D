# P1-78：F64 正式执行解除 SMB 运行依赖设计

## 1. 可观察故障

操作员选择已经登记并冻结的 F64 `vendor_file` ChannelAsset 后，MEASURE 在向 F64 发送任何
SCPI 之前重新读取 API 主机上的 SMB 挂载副本。开发期临时挂载目录消失时，执行直接失败：

```text
SMB 只读挂载不存在或不可解析: /tmp/mimo-f64-scenario-packs...: No such file or directory
```

此时 F64 上的 Windows `.smu` 路径仍然有效，现有驱动也已经具备完整的
`CALCulate:FILTer:FILE` 加载、状态回读、错误队列和 operation receipt 链。故障来自把开发期
资产发现通道错误地提升成了正式执行前置条件，而不是 F64 加载能力缺失。

## 2. 边界与裁决

用户确认的边界如下：

- 正式运行只消费执行冻结的 ChannelAsset、其中的 F64 仪器侧 `associated_file_path`，以及同次
  execution/attempt/session/instrument 的 SCPI 加载与生命周期证据。
- SMB scan/sync 只保留为开发、调试和离线资产导入工具；它可以帮助解析工程元数据，但不得参与
  Readiness、执行冻结后的对账或 MEASURE。
- 本片不删除现有 SMB API、GUI 工具或已保存的 `smu_project_scan` 配置，也不迁移数据库。
- F64 文件如何常态化提供、版本化、部署和盘点另立 roadmap 研究项，不在本片设计答案中偷定。
- 不新增、不修改、不猜测任何 F64 SCPI；只复用已有驱动事务和既有证据目录。

## 3. 方案比较

### A. 删除正式执行中的 SMB 字节复核（采用）

冻结时继续固定 ChannelAsset identity 与全部可执行数据库内容；MEASURE 只核对当前数据库资产是否与
冻结件一致。随后把冻结的 F64 Windows 路径交给现有 NativeModelStrategy/PropsimF64Driver，由
SCPI 回执决定本次加载是否成立。

优点是直接去掉错误依赖，运行边界与真实仪器控制面一致，不引入新机制。代价是正式执行不再声称
“本次 F64 文件字节等于某个开发机 SMB 副本”；现有 `smu_project_truth.sha256` 仅表示资产导入时的
离线来源证据。

### B. 运行前自动重挂 SMB

需要凭证、网络重试、挂载生命周期和权限管理，而且仍让 API 主机文件系统决定 F64 能否运行。
不采用。

### C. 每次执行先经 SMB 把文件传到 F64

这会新增文件发布协议和设备写入风险；当前 F64 正式路径已经加载仪器本地文件，也没有相应已确认的
远程文件管理命令。超出本片且违反“不猜 SCPI”。不采用。

## 4. 权威链与全集

### 正式生产链

| 关系 | 权威对象 / 行为 | 本片结论 |
|---|---|---|
| 资产产生 | ChannelAsset 保存或显式 SMB debug sync | 保持现状；sync 不是执行入口 |
| 启动冻结 | `freeze_channel_asset_resolution` | 固定 id/source 与数据库可执行内容 digest |
| MEASURE 对账 | `validate_resolved_channel_asset_against_freeze` | 只校验冻结件和数据库资产，不做文件系统 I/O |
| 路径解析 | `channel_asset_resolver` → `resolved_asset.emulation_file` | 继续取冻结对应资产的 F64 Windows 路径 |
| SCPI 加载 | NativeModelStrategy → `PropsimF64Driver.set_channel_model` | 保持已有加载事务，不改命令 |
| 同次执行证据 | `record_channel_emulator_operation` + F64 evidence projector | 继续绑定 execution/attempt/lease/instrument/asset digest |
| 正式消费者 | P2-66 `ExecutionEvidenceOutcome`、报告、历史、GUI | 继续要求完整真实 receipt/lifecycle；失败保持 fail-closed |

### SMB 开发工具链

`smu_project_inventory`、`/channel-assets/vendor-files/smu-scan|smu-sync` 和 ChannelWorkbench 继续可用，
但文案明确其为开发/调试期离线辅助，不是 F64 Readiness 或运行前检查。临时目录失效只会让操作员主动
调用 scan/sync 时失败，不能影响既有资产执行。

### 枚举后不在本片处理的事项

- `smu_project_scan` 是否应从生产 GUI 隐藏或迁出 InstrumentConnection preset；
- F64 文件发布、校验、版本锁定、现场复制和回滚协议；
- 仪器是否能提供文件内容 hash、版本或更强的工程身份回读；
- 对既有资产做批量重登记或数据库清理。

这些事项进入独立“F64 文件常态化提供”研究项，不能为了修当前故障引入未验证机制。

## 5. 失败语义与安全性

解除 SMB 前置门不等于放宽加载成功判据。F64 路径不存在、文件损坏、设备拒绝、错误队列非空、
模型状态不成立、路径/状态回执不匹配、生命周期不完整或证据身份漂移，仍由既有 SCPI 事务和 P2-60/
P2-66 正式门拒绝。Mock、unknown、diagnostic 仍不能进入正式 KPI。

代价不对称：宁可让 F64 自己明确拒绝并留下同次执行证据，也不能因开发机临时目录缺失而在任何仪器
I/O 前误拒合法测试；同时不能把“SCPI 命令发出”降格成成功。

## 6. 验收

1. vendor_file 资产冻结后，即使没有数据库 session、SMB 配置或本地挂载，也能完成冻结资产对账。
2. 同一 id/path 下数据库 payload、频率、绑定、活动状态等被冻结字段漂移仍在首个远程 I/O 前拒绝。
3. MEASURE 不再调用 `verify_channel_asset_smu_project_bytes`，且仍把精确 Windows 路径交给现有 F64
   SCPI 加载链。
4. F64 load receipt 和 P2-66 正式 outcome 的既有正反例保持通过；没有 SCPI 成功证据不能正式完成。
5. 主动 SMB scan/sync 的成功、坏文件、路径缺失和事务测试保持原行为。
6. GUI/API/roadmap 明确 SMB 是非正式开发工具，并新增独立的 F64 文件常态化研究项。

