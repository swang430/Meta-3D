# P1-79D CMW500 频率身份设计

## 可观察故障

CMW500 已把 LTE Band、DL EARFCN 与带宽写入仪表并精确回读，但共同频率一致性网只认识
UXM 的 `get_frequency_identity()`。因此 BaseStation 被记为「未报告（跳过）」、
`fully_verified=false`，正式判词停在 `frequency_identity_not_fully_verified`。

## 真值与边界

- 不增加 SCPI。复用现有 CMW500 Band / DL EARFCN / DL bandwidth 写后查询；其厂商出处已在
  `CmwScpiCommands` 紧邻注释中固定为 R&S CMW500 LTE UE User Manual
  1173.9628.02-41 printed pp.636-637、p.680。
- 频率身份只能由同一次 `apply_config()` 回执中三个 `confirmed` 的 applied control 形成。
  请求里的 `frequency_mhz`、构造函数默认 `_band/_earfcn/_bandwidth_mhz`、旧执行缓存均不补真。
- `set_cell_config()` 旧入口只能写硬件，不能自行取得正式身份；它会先清除旧证明。
- 新配置、取消、设备拒绝、回读漂移、失败重连、实际释放或断连都会让旧证明失效。
  SAFE_IDLE 未确认且传输仍保持打开时不伪称已经释放，但后续新配置仍会先清旧证明。
- 历史执行不回填；Mock 与没有权威实现的 adapter 继续报告 `None`。

## 共同 HAL

`BaseStationDriver` 明确定义当前配置身份与继承态实时身份两个接口，默认均 fail-closed 返回
`None`。执行器直接调用共同 HAL，不再用 `hasattr` 从对象形状猜适配器能力。UXM 保持既有实现；
CMW500 只实现当前配置身份，不把配置缓存冒充继承态 live readback。

## 验收

- CMW500 正常回执形成 RAT-aware `LTE band + EARFCN + bandwidth` 身份，并可与同一 TestCase
  精确比较；中心频率只由 LTE band/EARFCN 规范换算。
- 默认缓存、直调旧入口、错误队列拒绝、字段漂移、取消与传输生命周期均不能留下旧身份。
- 不改变 OpenAPI、数据库、GUI、provenance 白名单或任何仪器命令。
