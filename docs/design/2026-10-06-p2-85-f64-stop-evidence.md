# P2-85：F64 停止目标与 GOS 应用证据分离

用户已批准 A 方案。可观察故障：GOS 被拒但同次仪器已 STOPPED 时，驱动返回 True，操作回执仍 unknown，导致正式 CE 证据链 invalid。

## 取证裁决

NotebookLM PROPSIM资料（982222b7-4953-46cd-9949-00fa97882353），2026-10-06 查询 b879fdd79721，conversation f7dcb528-36df-42c1-bac4-635502e3e65f。回答页码有误，以下已与仓内 PDF 原件核对，不采用工具的推断：

- PROPSIM User Reference Rev10.2，2024-09-16，§20.4.3.10/11，印刷页243：STOP 是暂停而不 rewind；GOS 是停止并倒回起点。
- 同书 §20.4.3.14，印刷页244：STOPPED 为“Emulation is not being run”；CLOSED 为“Emulation has not been loaded”。均不能证明 RF 输出关闭或时间轴已回零。
- 同书 §20.5.2，印刷页326：-200 表示执行失败；所举例子是未加载时 GO，不能推广成所有 GOS 拒绝都无害。
- ATE Environment and Practices AN Rev2.2，2021-06-29，§2.5，印刷页14–15：运行中 GOS 后为 stopped，并需 GO 恢复。没有明确规定已经 STOPPED 时重复 GOS 的行为。

## 最小换源设计

不改公共 schema、不增加操作、不新增 SCPI，不修改共享 GOS 应用判据。F64 的 stop receipt 现有 `state` 字段改为证明停止目标的 `runtime_state`，来源为 §20.4.3.14；`operation_succeeded` 沿用 stop 方法的“确保不运行”布尔契约，不能解释为 GOS 被接受。

同一锁事务保留前清队列、GOS、OPC、写后错误、两次 STATE 及最后错误队列查询。GOS 错误原样保留在 capture/日志；只有同 execution/capture/instrument 的非模拟终态交换，两次 STATE 完全一致且为 STOPPED/CLOSED、状态查询之后队列明确干净，才确认实际回读状态。错误文本、OPC、缓存单独均不放行。矛盾状态的驱动布尔也拒绝，不仅靠回执补挡。

`build_f64_evidence(f64.simulation_stop_state)` 仍要求命令接受，拒绝的 GOS 不得洗成 applied/rewound。日志不再无条件声称 rewind。

CLOSED 只证明未加载：回执可记录目标已达成，但现有正式执行最终 safe-idle 必须 STOPPED 的策略保持，加载后消失仍 invalid。其他 adapter、Mock、历史冻结回执均不升级。直通结束的 STATIC 清除与 transport release 各自保持原门，不由停止状态代替。

## 验收关系与全集

真实 stop → 同事务 capture → `project_channel_operation_evidence` → recorder 身份/摘要验证 → CE session 终态 → P2-66 projection → API/历史/报告共同 outcome。对称入口：disconnect、MEASURE 直通预备、cleanup、安全释放、人工 emulation-control、诊断序列；它们继续消费同一 stop 方法，不复制判据。

正例：干净 GOS + STOPPED；拒绝 GOS + 两次 STOPPED；CLOSED 回执但正式最终 CLOSED 不放行；连续两次 recorder 调用各自归属。反例：RUNNING/瞬态/空值/矛盾值、状态查询报错、错误仪器/旧 execution/混 capture/模拟。软件验证不等于设备复验，现场复验仍待实机。
