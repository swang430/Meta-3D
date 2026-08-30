# BaseStation 诊断执行生命周期收口设计

## 可观察故障

一次冻结为 `diagnostic` 的 UXM/Mock 执行完成全部方位、保存诊断窗口并确认
`SAFE_IDLE` 与 transport release 后，`BaseStationExecutionSession` 仍调用正式证据
完整性判据。模拟配置无法也不应伪造权威回读，因此该判据以
`config_not_confirmed` 拒绝，最终把已安全完成的诊断执行错误标记为 failed。

## 设计选择

执行终态与正式 KPI 资格必须分开判定：

- `formal` 执行继续使用现有严格生命周期判据；配置、route、窗口四阶段、
  cleanup 与 transport release 任一缺失都 fail-closed。
- 冻结 qualification 明确为 `diagnostic` 时，允许使用专用诊断完成判据。
  它只证明本次诊断调度已经完整收尾，不证明任何仪器配置或测量值可信。
- 诊断完成仍必须满足：当前 attempt 一致、请求方位全部覆盖、每个方位的
  窗口基数/索引完整、窗口 ID 唯一、trust 明确允许诊断、cleanup 成功，
  并且对应 lease 的 remote acquire 与 transport release 均已确认。
- 畸形或缺失 qualification 不得推断为 diagnostic；继续走正式严格判据。
- 现有正式 evidence/KPI、报告和 provenance 白名单不变，诊断数值继续为
  `N/A` / `UNKNOWN`。

## 数据流

`run_base_station_execution_session()` 完成 operation 和 lease release 后，
`persist_execution_base_station_release()` 读取本次 execution 冻结的
qualification：

1. `classification == diagnostic`：调用诊断完成判据；
2. 其他情况：调用现有正式生命周期判据；
3. 两条路径都必须先确认 execution 仍为 running 且 transport 已释放；
4. 只更新当前 attempt 的终态，不读取当前 TestCase、site certification 或
   任何可变配置反推本次资格。

## 非目标

- 不改变 UXM/CMW500 命令、SCPI 或测量窗口语义。
- 不让模拟、未知或诊断数据进入正式 KPI。
- 不在本片修改型号配置保存与 LabProfile 同步；该问题使用后续独立片处理。

## 验证

- 复现现场 UXM/Mock：诊断窗口完整、配置未确认、release 已确认，应以
  diagnostic completed 收口。
- 正式执行配置未确认仍失败。
- diagnostic 的窗口缺方位、缺索引、cleanup 失败、release 不确认均失败。
- qualification 缺失或畸形不得走诊断放行。
- 扩大 BaseStation session/evidence/qualification/正式消费者回归与全后端回归。
