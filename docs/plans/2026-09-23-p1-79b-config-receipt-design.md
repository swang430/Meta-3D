# P1-79B BaseStation 配置回执控制字段设计

## 可观察故障

CMW500 已对本次 LTE 配置的 band、EARFCN、带宽、双工、传输模式、MIMO 层数和下行功率完成权威回读，但 `BaseStationApplyReceipt.confirmed` 仍恒为 `false`。根因是 `radio_technology`、`channel_kind`、`frequency_mhz` 三个冻结描述字段也被当成须逐字段回读的仪表控制量；CMW500 没有独立写入/回读这三个字段，所以它们恒为 `unknown`，进而让 attempt 生命周期返回 `config_not_confirmed`，也无法签发 BaseStation site certification。

## 全集与边界

`BaseStationRequestedConfig` 包含两类事实：

1. **冻结描述/判别字段**：`radio_technology`、`channel_kind`、`frequency_mhz`。它们用于在执行前确定 adapter/RAT、区分 NR-ARFCN 与 LTE EARFCN，并提供中心频率派生视图；它们不是独立的仪表控制寄存器。
2. **仪表控制字段**：其余字段。非空且适用于所选 adapter 的控制字段必须由同一次真实执行的权威回读确认，任何缺失或不匹配仍使整个配置回执未确认。

冻结描述字段仍受以下现有门保护，不从配置回执删除真值：

- P1-75 requirements × manifest compatibility 固定 RAT 和 adapter；
- `BaseStationRequestedConfig` 的 RAT-aware channel shape 固定 channel kind；
- NR-ARFCN / LTE band + EARFCN 的已有手册换算与校验固定中心频率；
- P1-79D 将只从本次已确认的控制字段形成频率身份，不从请求视图补真。

## 决策

采用“从配置回执的必需确认集合中移出冻结描述字段”，不把它们伪装成直接仪表回读，也不新增 SCPI。

- `receipt_payload()` 只返回独立仪表控制字段；名称与说明改成明确的 applied-control receipt 投影。
- CMW500/UXM 的现有 `apply_config()` 继续对投影里的每个非空字段逐一回读；没有任何 `operation_succeeded` 兜底。
- 错误队列拒绝、回读缺失、回读不匹配仍产生全量/对应 `unknown`。
- Mock 仍为 simulated/unknown，不进入正式资格。
- manifest 仍完整声明所有 requested config 字段；不改 manifest schema、digest 或历史冻结件。
- 历史 execution/report 不追溯升级；只有新执行使用新的回执投影。

## 非目标

- 不实现 P1-79C 的共同强制证据写方。
- 不实现 P1-79D 的 CMW500 频率身份。
- 不修改 site certification、qualification 或 KPI 判据。
- 不新增、修改或猜测任何 SCPI 命令。

## 验证

- RED：完整 CMW500 权威回读在旧实现仍因三个描述字段而未确认。
- GREEN：完整控制字段回读后回执确认；字段集合不含三个描述字段。
- 反例：任一控制字段缺失/不匹配、错误队列拒绝、模拟回执仍不得确认。
- 对称性：UXM 也使用同一控制字段投影，不再要求不存在的独立描述字段回读。
- 回归：P1-73B/P2-43/P2-46/P2-65/P2-66、rule gates、全后端、compileall、单一 Alembic head、diff-check。
