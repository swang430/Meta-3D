# P1-56 转台动作真值门与诊断载体设计

## 1. 可观察故障

2026-08-07 现场连续 15 次看到控制器接受 `MOVEABS`，但 `PFBK(X)` 一个计数未动，
`RealAerotechDriver.move_to()` 仍仅凭 `AXISSTATUS` 的 InPosition/MoveActive 位返回成功。
一旦正式 MIMO 方位循环继续运行，多个方位可能在同一物理位置采样，并生成外观正常的
吞吐与报告。这是“命令被接受”被误当成“机械动作已发生”的假成功。

本地片只解决可由仓内协议证据判定的两件事：

1. 控制器反馈没有按请求目标变化时，真实 Aerotech `move_to()` / `reset()` 必须失败，
   所有正式消费方随既有布尔契约停止采集；
2. 提供可在现场重复运行的破坏性诊断序列，保存带/不带 `XF` 的命令、
   `AXISSTATUS` 与 `PFBK` 原始时间序列。

控制器型号/固件、user units 是否为 degree、控制坐标到 DUT 物理方位的偏置、正反方向和
真实机械动作仍需要人在暗室观察，继续标记 Hardware Blocked。诊断成功不关闭该现场门。

## 2. 全集枚举

### 2.1 动作产生方

- `RealAerotechDriver.move_to()`：真实 AeroBasic/TCP `MOVEABS`；本片主修复点。
- `RealAerotechDriver.reset()`：真实 `HOME`；当前同样只信状态位并把缓存直接写为 0。
- `RealEtsEmcenterDriver.move_to()`：独立 ETS/SCPI 方言；不共享 Aerotech 现场证据，本片不泛化。
- `MockPositioner.move_to()`：模拟驱动；不代表真实机械动作，不进入本片真硬件判据。

### 2.2 `move_to()` 生产消费方

- MIMO OTA `MEASURE` 每方位；已在 False 时终止并返回 FAILED。
- 探头方向图扫描；已在 False 时抛错，停止后续 SA 采样。
- 静区真实 grid；已在 False 时抛错。
- 空间相关校准两位置；已在 False 时抛错。
- 信道生成 OOP 的示例调用；不是活动执行器。
- 独立 positioner move/sweep API；已消费 False，sweep 另做最终容差比对。
- MIMO cleanup 回零；当前忽略 False，本片改为 warning，不把清理假成功吞掉。

因此判据放在真实 Aerotech driver 后，上述正式入口会同时获得保护；不在各服务复制一套
“移动了没有”的判断。

### 2.3 证据与诊断消费方

- P1-47C `record_positioner_capture()` 已保存同次 `MOVEABS` 与最终方位 `PFBK`，但因坐标
  偏置未校准，正式证据保持 UNKNOWN；本片不伪造偏置。
- `aerotech_positioner_health` 是严格只读探针，不能改成运动探针。
- 新建独立 `aerotech_positioner_motion_truth`，由现有 loader、API、GUI 动态发现；结果进入
  `DiagnosticRun.result_extra`，不新建数据库表或专用页面。

## 3. 方案比较与选择

### 方案 A：真实驱动强制动作真值 + 独立诊断序列（采用）

优点：一处修复覆盖全部正式消费；既阻止假数据，又保留现场定位所需原始轨迹；不改变
`PositionerDriver.move_to() -> bool` 公共接口。缺点：只对有 Aerotech 协议证据的驱动生效，
ETS 仍按其独立方言处理。这是有意的证据边界。

### 方案 B：在每个业务消费方做前后位置比较（不采用）

同一判断要复制到 MIMO、方向图、静区、校准和独立 API，容易漏现场实际路径；也会让业务层
猜测 Aerotech 状态位与反馈语义。

### 方案 C：只增强 standalone sweep/诊断（不采用）

能暴露问题但挡不住正式 MIMO 在旧角度继续采样，不能解决假报告风险。

## 4. 驱动动作真值

### 4.1 严格反馈读取

动作门新增严格数值读取：空串、非数字、NaN、Inf 一律抛错；不得沿用 `_query_value()` 的
`0.0` 兜底，也不得回退到缓存。`get_position()` 对真实 Aerotech 同样使用严格读取并让异常
到达调用方，独立 API 才能正确返回 `position_read_failed`。

### 4.2 MOVEABS

`move_to()` 按以下顺序执行：

1. 命令前严格读取各实际轴的 `PFBK`；
2. 发送既有 `MOVEABS`；
3. 轮询既有 `AXISSTATUS`，故障或超时失败；
4. 严格读取最终 `PFBK`；
5. 每个实际轴都要求最终反馈在配置容差内到达请求目标；
6. 若请求目标与起点的距离超过容差，还要求反馈相对起点发生可观察变化；否则返回 False，
   错误明确为 `motion_not_observed`，不得打印 Arrived。

方位误差使用 360° 环形距离，避免 359.8°→0° 被误判；俯仰使用线性距离。已在目标位置时
不强求再次运动，只要求最终反馈仍在容差内。

容差是应用判据，不是仪器回读单位推断；默认 0.5°，可由连接参数
`position_tolerance_deg` 收窄配置。user units 是否真为 degree 仍须现场确认。

### 4.3 HOME

`reset()` 不再在 HOME/状态位后直接把缓存写成 0。它读取前后反馈，要求最终反馈到 0；
起点明显非零时还要求有反馈变化。失败返回 False。

## 5. 诊断载体

新序列 `aerotech_positioner_motion_truth`：

- 只接受权威 `is_mock_driver()` 判定为 real、已连接且暴露 AeroBasic `_send` 的 positioner；
- `safe_during_test=False`，复用现有破坏性诊断互斥与审计链；
- 参数：安全小步进（默认 10°，限定 0.1..30°）、`XF` 速度（默认 5，限定 0.1..20）、
  采样时长（默认/最大 10s）、采样间隔（固定默认 0.2s，限定 0.1..1s）和容差；
- 运行前读取起点，显式 `ENABLE <axis>` 一次，此后不发送 `DISABLE`；
- 第一段不带 `XF` 移动；若已到目标，第二段带 `XF` 返回起点；若第一段未动，第二段带
  `XF` 重试同一目标，用于回答“是否缺进给速度”；
- 每段在命令后连续采 `AXISSTATUS(axis)` + `PFBK(axis)`，保存 elapsed、原始回复、解析值；
- 每段输出 `command_accepted / feedback_changed / target_reached / axis_fault`，只有反馈变化且
  到达目标才算该段动作有证据；
- `result_extra` 保存全部样本，`SequenceStepResult.raw` 保存关键原始回复。诊断结论只说明
  “控制器编码器反馈是否移动/到达”，不声称 DUT 物理角度已校准。

命令依据来自仓内 `Instrument_API_Doc/Aerotech/Aerotech_Ensemble_ASCII_TCP转台控制集成说明.docx`
§4–§7：`MOVEABS X <angle> [XF<speed>]`、`ENABLE X`、`AXISSTATUS(X)`、`PFBK(X)`、
到位后再采集。仓内对象为 Ensemble、驱动头仍写 A3200/Automation1；该型号差异不在本地猜测。

## 6. 状态与失败路径

- 成功：缓存只由严格最终反馈更新，状态 READY。
- 设备拒绝、故障、超时、反馈无效、未发生应有动作、最终超差：返回 False，状态 ERROR；
  正式消费方停止采样。
- 取消：保持异常传播语义，不伪装 False 后继续；诊断框架负责审计 cancelled。
- cleanup 的 False 进入 warnings，但不遮蔽原始执行错误。

## 7. 验收

1. `MOVEABS` ACK + settled，但请求 90°、PFBK 始终 0° → `move_to()` False，无 Arrived。
2. 起点已在目标容差内 → 可成功，不要求无意义的额外运动。
3. 359.8°→0° 按环形容差成功；明显超差失败。
4. PFBK 空/坏/NaN/Inf 不得变成 0 或旧缓存成功。
5. HOME 后反馈未回 0 → reset False。
6. 全部活动正式消费方继续消费同一 bool；cleanup False 可见。
7. 新诊断序列可由 loader/API/GUI 动态列出；mock/无连接 fail-closed。
8. 诊断带/不带 `XF` 两段不发送 DISABLE，按 200ms/10s 保存 raw 状态与位置样本。
9. 本地完成后 P1-56 本地片可合并；现场真实机械方向/单位/偏置/型号裁决仍 Hardware Blocked。

