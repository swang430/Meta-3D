# P2-31：SMB `.smu` 工程真值扫描设计

## 可观察故障

当前 F64 厂商工程由操作员把 `.smu` 路径、中心频率分别手工登记到
`ChannelAsset` 与 `connection_params.available_channel_models`。文件名中的频率只是场景族标称，
现场已经证实 `UMa_3600M` 工程内部实际是 3549.99 MHz，`UMa_1800M` 与 `UMa_2450M`
也同样名实不符。新增场景包或重新登记时若继续抄文件名，GUI、频率一致性网和正式 GCM 执行会
消费一份看似完整、实际错误的频率声明。

现有 `scripts/onsite-fix-f64-scenario-assets.py` 只是一张 2026-07-03 手工硬表；它不会扫描新工程，
也不能证明数据库中的值仍等于当前 SMB 文件内容。

## 已完成范围与本片边界

- P2-18 的 EMQuest 10-band 权威表已经交付并被正式消费，本片不再修改 EMQuest、UXM 命令或
  band/SSB 参数。
- `.smu` 工程解析真值已经存在于 `app/hal/smu_project.py`：只认
  `[Channel Group N] CenterFrequency`，不读文件名 token。
- 当前正式资产真值是 `ChannelAsset(source_type="vendor_file")`；legacy
  `StandardChannelDefinition` 只保留存量兼容，不新增双写。
- F64 ATE 不提供可用的 MMEM/FTP 文件读取，本片只读操作员已经挂载到 API 主机的 SMB 副本，
  不向 F64/SMB 写文件，不新增凭证保存或网络 SMB 客户端。

## 产生方、消费方与配置入口全集

### 真值产生方

1. SMB 只读挂载下 `.smu` 文件的 `[Channel Group 0] CenterFrequency`；必须存在 group 0，
   不把其他 group 猜成主载波。
2. `ChannelAsset.payload.scd_config.arfcn`：可执行 NR 中心频率的规范标识。
3. `ChannelAsset.center_frequency_hz`：工作台显示镜像，存在时必须与 `scd_config` 一致。
4. `InstrumentConnection.connection_params.available_channel_models[].center_frequency_mhz`：
   `/instruments/channelEmulator/channel-models` 与 GCM 选择器的实时投影。

### 消费方

- `mimo_ota/channel_asset_resolver.py` 与 `measure.py`：正式执行前的资产解析和频率一致性网；
- `channel_emulator.normalize_channel_model_entries()` 与 channel-models API：GUI/调试清单；
- `ChannelWorkbench`：当前 vendor_file 新建、编辑、查看入口；
- legacy SCD API/卡片：只读兼容，不作为本片写目标；
- `nr_arfcn.parse_smu_center_freq_mhz()`：文件名 loose 提示，明确不作为本片真值。

### 扫描配置

唯一 `channelEmulator` 连接的 `connection_params.smu_project_scan` 提供：

```json
{
  "local_mount_root": "/Volumes/Scenario Packs",
  "instrument_root": "D:\\Scenario Packs"
}
```

`local_mount_root` 是 API 主机上的显式绝对只读挂载；`instrument_root` 只负责把相对路径映射成
F64 可加载路径。端点不接受客户端临时传本地根目录，避免把扫描器变成任意服务器路径读取器；
认证信息继续由操作系统挂载层管理，不进入 API 响应、日志或数据库新字段。

## 方案比较

### A. 服务端只读预览 + 明确一键同步（采用）

服务端从固定配置根扫描、解析并把结果与现有 vendor_file 资产按**完整仪器路径**精确匹配。
操作员先看预览，再触发无参数同步；同步端点重新扫描并只写可证明的一一匹配项。

优点：频率来自文件内部；客户端不能伪造频率或扫描根；写入前能展示所有阻断项；没有常驻任务、
SMB 凭证或 F64 写操作。缺点：仍要求运维先完成只读挂载与两项路径映射配置。

### B. API 内直接连接 SMB

需要新增 SMB 依赖、凭证生命周期、超时/重连和网络权限边界；现有现场匿名挂载已经可用，超出
“替代手工硬表”的最小范围，拒绝采用。

### C. 按文件名/频率自动创建 ChannelAsset

文件名已被现场证伪；仅凭中心频率又无法推导带宽、场景、MIMO、极化与规范名称。自动创建会把
猜测包装成正式资产，拒绝采用。

### D. 后台周期自动写库

SMB 短暂断开、半复制文件或工程更新时会在无人确认下改正式执行真值。首片采用一键预览/同步；
只有积累稳定现场证据后才另行评估周期任务。

## 采用设计

### 1. 只读扫描器

新增纯服务 `smu_project_inventory`：

- `local_mount_root` 必须是存在的绝对目录，解析后的根不得是符号链接；
- 递归枚举大小写不敏感的 `.smu`，不跟随符号链接，任何 symlink 文件/目录只报告为 skipped；
- 固定限制：最多 1024 个 `.smu`、单文件 8 MiB、本轮总读 64 MiB；超过限制整体 fail-loud，
  不返回“看似完整”的半清单；
- 确定性排序；每项记录相对路径、映射后的 F64 路径、大小、SHA-256、全部 Channel Group 频率；
- UTF-8/UTF-8 BOM、带 BOM 的 UTF-16 可直接解码；其他单字节内容用 latin-1 无损映射，
  只让既有 ASCII 节名/键解析器判定；无法得到 group 0 时明确 `parse_error`；
- 文件名只用于显示，绝不参与频率或匹配判决。

### 2. 匹配与同步判据

扫描项只与同一 F64 绑定下活动的 `vendor_file` ChannelAsset 比较。路径按 Windows 语义统一
分隔符并 casefold 后精确相等；不按 basename、频率或名称近似匹配。存量资产的
`instrument_connection_id=null` 可在“仓库只有唯一 channelEmulator 连接且完整路径唯一”时迁入
该绑定；其他绑定或一条路径命中多资产均阻断。

每项状态至少区分：

- `syncable` / `already_synced`：唯一资产、group 0 存在、工程频率可精确往返 NR-ARFCN；
- `unregistered`：工程存在但没有资产；只展示，不自动创建；
- `ambiguous_asset`：同路径多资产；不写；
- `non_nr_raster`：工程频率不能精确往返 NR-ARFCN；不把最近栅格点冒充工程真值；
- `parse_error` / `protected`：坏文件、越界、symlink、配置或读取失败。

精确往返要求 `nr_arfcn_to_freq_mhz(freq_mhz_to_nr_arfcn(x))` 与工程 Hz 完全相等（浮点只容
1 Hz 表示误差）。例如工程 4700.000 MHz 而运行载波按 4700.010 MHz 登记时必须展示
`non_nr_raster` 并保留现状，等待操作员给出有出处的运行映射；禁止自动 round。

### 3. 一次事务中的写入

`POST /channel-assets/vendor-files/smu-sync` 不接受客户端扫描结果，重新读取当前文件并完成全部
冲突预检后，在一个数据库事务中：

1. 对 `syncable`/`already_synced` 资产保留所有未知 payload 字段，只更新：
   - `payload.scd_config.arfcn`；
   - `payload.smu_project_truth = {schema_version, instrument_path, sha256, size_bytes,
     primary_group, center_frequencies_hz}`；
   - 顶层 `center_frequency_hz` 与 `instrument_connection_id`；
   - 从最终 `scd_config` 重新派生 `canonical_name`；
2. 以完整路径 upsert 对应 `available_channel_models` 投影的 `filename/label/description/
   center_frequency_mhz/channel_asset_id`，保留无关条目和未知键，不删除未扫描项；
3. 任一待写项发生规范名冲突、绑定冲突或校验失败，整次同步 rollback，并在响应中指出阻断项。

同步不改资产 name、带宽、场景/MIMO/极化、活动状态，不创建资产，不删旧项，不写 SMB/F64。

### 4. API 与 GUI

- `POST /api/v1/channel-assets/vendor-files/smu-scan`：只读预览；
- `POST /api/v1/channel-assets/vendor-files/smu-sync`：重新扫描后同步可证明项；
- 两个静态路径在 `/{asset_id}` 之前注册，避免 UUID 动态路由遮蔽；
- 信道工作台新增“扫描 F64 工程”按钮与结果 Modal，逐项显示工程路径、group 0 真值、资产、状态/
  原因；只有存在 `syncable` 时显示确认同步按钮；
- 缺配置、挂载不存在、读取越界和同步冲突均显示服务端 detail，不回退文件名或旧清单；
- live OpenAPI、`api/openapi.yaml`、`api.generated.ts` 与手写 GUI 类型同步。

## 安全与失败方向

- SMB 不可达：扫描失败，数据库保持原样；绝不拿旧扫描缓存当最新真值。
- 文件在预览后变化：同步端重新读取并重新计算 SHA/频率，不消费客户端值。
- 半清单：任何全局上限触发则整轮失败；不能用“扫到的一部分”覆盖正式清单。
- 未登记新文件：只展示，避免从文件名猜场景/带宽创建假资产。
- 非 NR 栅格：保留项目原始频率证据但本轮不写正式资产；不能静默取最近 ARFCN。
- 重复路径/规范名：整次回滚，避免 ChannelAsset 与 channel-models 只成功一边。
- 扫描器不执行 mount、credential、copy、rename、delete、write、prune；P2-40 实际清理继续冻结。

## TDD 与验收

1. 临时目录模拟 SMB：文件名写 3600M、内部 group 0 写 3549990000 Hz，预览必须返回
   3549.99 MHz；把实现改回文件名解析时测试会红。
2. group 0 + 多个 SCell 全量保留；只有 group 1 时 `parse_error`，不得采用最小组号 fallback。
3. 缺配置、相对根、symlink、超大文件、总量/数量越界、不可读文件均 fail-closed。
4. 同一路径唯一存量资产：同步后 asset 的 ARFCN/顶层频率/provenance、绑定和
   available_channel_models 同时更新；未知 payload/投影键保留。
5. 无资产、重复资产、其他绑定、inactive、非栅格与 canonical 冲突均不写；事务失败前后快照一致。
6. GUI 契约证明扫描按钮、只读预览、状态原因、确认同步和错误 detail；不新增文件名推断。
7. OpenAPI 三镜像、相关/完整 rule gates、GUI production build、全后端、`compileall`、
   单一 Alembic head（本片预计无迁移）与 `git diff --check` 通过。

## 非目标

- EMQuest/band/SSB 数据与 UXM/F64 SCPI 命令；
- SMB 凭证、自动 mount、网络 SMB 客户端或 SMB 写入；
- 依据文件名/频率自动创建资产或推导带宽/场景；
- legacy SCD 双写或恢复 legacy 编辑器；
- 后台周期任务、删除/移动工程文件、P2-40 实际清理。
