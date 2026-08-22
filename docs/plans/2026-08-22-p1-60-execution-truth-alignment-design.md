# P1-60 最近一次手工执行真值对齐设计

## 可观察故障

同一次 mock 手工执行 `3c12ebab-ad6f-4f6f-bd83-a8b8f4fbd613` 中出现五组互相矛盾的证据：

1. 16 个双极化物理探头应对应 32 个端口，但日志只注入 `29/32` 相位补偿；
2. 四个方位只对 `3/4` 使用逐 RF-chain 路损；
3. 已选资产声明 `UMa`，GCM/OOP 却记录 `scenario=UMi`；
4. 已选资产声明 40 MHz，warning 却说“没有可信资产带宽声明”；
5. 本地日志为 10:37，执行快照名与报告人读 ID 为 02:37。

如果按当前形态进入真机执行，前两项会把不同补偿口径混进同一组正式测量，第三项会让派生 OOP/审计元数据与所选工程真值冲突。第四、五项不会改变计算，但会直接误导现场定位。

## 只读实证

- `ChamberConfiguration`: `CAICT-16-Probe-Dual`, `num_probes=16`, `num_polarizations=2`。
- 活动拓扑与路损证书使用物理探头编号 `1..16`；证书含 32 个 `(probe_id, polarization)` RF chain。
- `_query_calibration_entries()` 仍按零基公式 `probe_id * 2 + 1/2`，故 `1..16` 被错误映成端口 `3..34`。
- `ChannelPhaseCalibration` 存量通道为 `0..31`，与 F64/Channel Engine 的人读端口 `1..32` 不同；查询还忽略目标频率、有效期与模拟 provenance。
- `select_active_probe_id(16, [0,90,180,270])` 返回 `0/4/8/12`，而 topology/cert 的物理探头真值为 `1..16`；0° 因不存在 `probe_id=0` 回退暗室平均损耗。
- ChannelAsset `b328d53a-...` 的 `payload.scd_config` 明确为 `scenario=UMa`, `bandwidth_mhz=40`；执行装配未把 scenario 送入 `cdl_model_data`，策略采用默认 `UMi`。
- 本次 `frequency_consistency` 的真实状态是 `SCD=ARFCN 636666/BW40` 已声明、`f64_center_readback_mhz=null`；warning 把“中心频率未回读”误写成“带宽没有声明”。
- DB 生命周期时间继续使用 naive UTC；仅快照名、commissioning 名称与报告人读 ID 需要按运行机本地时区显示。

## 设计裁决

### 1. 物理探头与端口编号

- RF topology 的物理探头编号以 `1..N` 为正式真值；方位索引仍先算零基位置，再显式转换为 `probe_id=index+1`。
- ProbePattern 的存量零基契约不在本片迁移；测量装配不再用同一个 `pid` 同时代表 pattern index 与 RF-chain probe ID。
- 逐链证书一旦非空，就必须覆盖全部请求方位；部分命中不得和 chamber average 混算，直接在采样前 fail-loud。完全没有逐链字段的 legacy 证书保留现有整体平均回退。
- `probe_path_losses` 只接受可判定的完整 `0..N-1` legacy 集或 `1..N` topology 集；含越界、重复形状或含糊子集时拒绝构造端口，不再生成 `33/34` 这类不存在端口。

### 2. 相位校准 provenance 与频率

- `channel_phase_calibrations` 增加 nullable `use_mock`。`NULL` 是历史未知，不按真实放行。
- 新 mock 校准写 `use_mock=true`、`measurement_method=mock`，通道编号改为 `1..num_channels`；真实实现尚未接线，因此不会虚构 `false`。
- 执行消费只选：同 chamber、同目标频率、未过期、`status=valid`，且真实执行只接受 `use_mock=false`、mock dry-run 只接受 `use_mock=true`。
- 通道集合必须精确覆盖当前 payload 的 `1..num_ports`；否则整份相位补偿不应用，绝不部分注入。
- 不回填存量 `NULL`，因为无法证明其真实来源。

### 3. ChannelAsset scenario

- `ResolvedChannelAsset` 把 vendor `scd_config.scenario` 作为显式结果交给 MEASURE。
- MEASURE 将其写入 `cdl_model_data["scenario"]` 与执行证据；无资产 scenario 时只允许复用既有 CDL 名解析器得到的场景，不再静默默认 `UMi`。
- OOP 展示名避免把已有场景前缀重复拼成 `UMa UMa ...`。

### 4. 频率 warning

按真实缺口分三类输出：

- 中心频率未回读、资产带宽已声明；
- 中心频率已回读、资产带宽未声明；
- 两者都未知。

判定 payload 与 `fully_verified=false` 语义不放宽，只修正诊断原因。

### 5. 人读时间

- DB `started_at/completed_at/generated_at` 继续 UTC，API 序列化不变。
- 新建共享的人读 token helper，对 aware UTC 时刻调用运行机本地时区后再格式化。
- TestCase 快照名、commissioning/adhoc 名称、MIMO report human ID 共用该 helper；GUI 日志仍按浏览器本地时区显示。
- 只影响新记录，不回写历史名称。

## 非目标

- 不把 mock KPI 变成正式 KPI；本次既有 `UNKNOWN/N/A` provenance 门保持不变。
- 不新增或猜测任何 F64/UXM SCPI。
- 不回填历史相位校准 provenance、历史执行名或报告 ID。
- 不把 ChannelAsset 的声明带宽冒充 F64 live readback；资产声明与仪器回读仍是两种证据。

## 验收

1. 16×双极化、证书物理 ID `1..16` 构造端口精确为 `1..32`。
2. 0/90/180/270° 的 RF-chain probe ID 为 `1/5/9/13`，逐链证书非空但缺任一方位时在采样前失败。
3. legacy/过期/错频/mock 相位记录不能进入真实执行；完整可信记录只能全量 `32/32` 注入。
4. UMa vendor asset 传到 GCM/OOP 的 scenario 仍为 UMa；缺场景不默认 UMi。
5. mock F64 无中心回读时 warning 如实说明中心频率缺失，并承认资产 BW40 已声明。
6. 同一 aware UTC 时刻生成的执行快照 token、commissioning token、报告 token 与本地日志时区一致；DB 时间仍为 UTC。

