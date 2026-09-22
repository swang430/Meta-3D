# P1-79C BaseStation 共同执行证据设计

## 可观察故障

CMW500 已完成配置回读、attach、测量窗口和吞吐量回读，但
`base_station.pcell.config_applied` 与
`base_station.throughput.azimuth.NNN` 仍缺失。当前写方由
`hasattr(driver, "build_p0_5_*_evidence")` 控制，记录器又按 UXM 的命令角色和
证据键写死，所以只有 UXM 驱动能产出强制证据。

## 真值与边界

新写方只消费服务器已经冻结并校验过的 BaseStation 真值：

1. 配置证据消费同一 execution/attempt/lease 的
   `BaseStationAdapterOperationEvidence(config)`、
   `BaseStationAttachOperationEvidence` 与冻结 manifest；
2. 吞吐证据消费 cleanup 后已经持久化的
   `BaseStationMeasurementWindowEvidence`、冻结 metric registry 与冻结 manifest；
3. 原始 SCPI exchange 只用于核对 execution/capture/instrument 并回链日志，
   共同投影不解析厂商命令文本、不新增命令、不猜测厂商语义；
4. 环境快照来自 execution 初始化时冻结的、已经由真实连接验证的身份，
   不重新查询当前 HAL，也不从 adapter 名称推导真实性；
5. 历史 UXM translator 只读保留，不给旧记录补造新证据。

## 配置投影

- 请求 channel number 必须等于冻结请求中的 NR ARFCN 或 LTE DL EARFCN；
- 配置 operation 必须完整确认、非 simulated、digest 对齐冻结请求；
- attach operation 必须与配置 operation 属于同一 attempt/lease/session，且
  `formally_confirmed=true`；
- manifest 中所有被确认控制字段及已确认 attach 阶段必须具有权威来源；
- 满足全部条件才输出 E3/APPLIED + passed；缺失、漂移、模拟或来源不足均输出
  unknown/rejected，绝不借 `operation_succeeded` 或当前仪表状态补真。

## 吞吐投影

- 先持久化窗口，再从同一 execution/attempt/lease/position 读取唯一窗口；
- `dl_throughput_mbps` 必须来自冻结 registry 的 authoritative capability，
  metric value 为有限正数，window trust 正式确认，且 metric exchange IDs 属于窗口；
- 满足全部条件才输出 E4/OUTCOME + passed；模拟、diagnostic-only、零值、缺值、
  registry/digest/position/attempt 漂移均保持 unknown 或 rejected；
- source reference 只复用冻结 manifest/registry 已有出处，不改变正式 provenance
  白名单。

## 调用顺序

配置投影在配置与 attach 回执都写入后执行；吞吐投影移到 finally 中，在
`append_base_station_measurement_window()` 之后执行。这样强制证据与服务器窗口真值
不会出现先写摘要、后写权威窗口的双真值或时序裂缝。

## 验收

- CMW500 与 UXM 都通过同一投影函数产出 `base_station.*`；
- `MeasureExecutor` 不再用 `hasattr(...build_p0_5...)` 决定证据写方；
- CMW confirmed receipts/window 能生成 E3/E4；模拟、跨执行、跨 lease、缺来源与
  非权威 metric 均 fail-closed；
- 既有 UXM 正式路径、历史 translator、Mock 诊断边界与报告终判不回归。
