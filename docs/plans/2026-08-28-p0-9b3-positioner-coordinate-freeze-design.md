# P0-9B-3 Aerotech execution-frozen 坐标合同设计

## 可观察故障

CAICT 现场已通过两次独立动作证明 Aerotech 单轴转台满足
`PFBK(X) - MOVEABS(X) = +90°`。真实驱动也已经按该关系把 TestCase 请求方位映射为
控制器程序坐标，并用最终 `PFBK(X)` 核对请求方位。

但是正式执行证据仍存在两个缺口：

1. `record_positioner_capture()` 固定传入 `coordinate_offset_deg=None` 与
   `offset_calibrated=False`，因此动作正确也只能得到 UNKNOWN；
2. 旧证据构造器把偏置从最终 PFBK 再减一次。对当前驱动语义而言，这会把已经位于 TestCase
   物理方位坐标系的 PFBK 二次换算，导致合法动作被拒绝，或未来错误地混淆程序坐标与物理方位。

## 三层坐标合同

本片明确区分三个不可互换的值：

1. **请求方位**：TestCase 中的 DUT 物理方位，也是最终报告使用的角度；
2. **程序目标**：发给 Aerotech 的 `MOVEABS` 数值；
3. **反馈方位**：控制器 `PFBK(X)` 返回的实际物理方位。

冻结偏置定义为：

```text
coordinate_offset_deg = PFBK - MOVEABS
expected_program_target = requested_angle_deg - coordinate_offset_deg
expected_feedback = requested_angle_deg
```

例如请求 200°、冻结偏置 +90° 时，只接受 `MOVEABS X 110°`，并要求最终
`PFBK(X)` 在圆周误差 ±1° 内到达 200°。证据不得把最终 PFBK 再减 90°。

## 配置与验证是两个事实

偏置是用户可配置的站点参数，继续由 positioner `InstrumentConnection.connection_params`
提供：

- `motion_truth_coordinate_offset_deg`：偏置数值；
- `motion_truth_coordinate_offset_verified`：该数值是否已有现场动作证据；
- `motion_truth_units_verified` / `motion_truth_user_units`：用户单位是否已证明为 degree；
- 既有安全范围、动作速度和反馈容差字段。

“用户填写 +90°”只证明配置存在；`verified=true` 才声明该值已经由现场原始
`MOVEABS/PFBK` 记录证明。执行不会自动估算或修改偏置，也不会把一次测试的反馈反写为新配置。

本次冻结的来源引用固定指向
`docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md` 的 Aerotech 现场记录；执行快照同时保存
服务器冻结时间和稳定摘要，后续配置变化只影响新 execution。

## execution-frozen 快照

新增唯一的 positioner coordinate freeze 服务，复用 `TestExecution.config`，不新增数据库表。
在 TestExecution 排入后台前，从锁定的以下真值构造不可变快照：

- 所选 LabProfile 的唯一 positioner binding；
- positioner category 的 selected model；
- 同一 category 的 InstrumentConnection；
- 连接中持久化的 degree、偏置、安全范围、速度与容差；
- 当前已加载 driver 的类、连接端点、方位轴与相同配置。

真实 Aerotech 缺失任一必需字段、binding/model/connection/driver 不同源时，执行在任何转台动作前
fail-loud。权威 Mock 或非 Aerotech positioner 只冻结诊断/not-applicable 状态，不因本片获得
正式 Aerotech 方位证明。

已有硬件进度的旧 execution 不允许从今天的配置回填快照。相同 execution 重复调用冻结函数只
返回原快照，不覆盖。

## 执行与证据

MEASURE 每个方位在首条 positioner I/O 前：

1. 读取本 execution 已冻结的坐标合同；
2. 纯本地核对活动 driver 的类、端点、轴和动作配置仍与快照一致；
3. 不一致则禁止发送 `MOVEABS`；
4. 动作完成后，把同一 capture 中实际发送的 MOVEABS 和最终 X 轴 PFBK 交给证据构造器；
5. 证据同时验证实际程序目标与派生目标、最终 PFBK 与请求物理方位。

缺快照、快照未验证、实际命令不匹配、反馈缺失、反馈超差、错误 instrument/execution 来源均不得
通过。设备拒绝保持 REJECTED；缺真值或缺传输证明保持 UNKNOWN。请求值不得回填成命令或反馈。

报告、历史、GUI 继续消费现有 `positioner.angle` evidence，不增加第二套判据。

## 安全边界

- 不自动测量、学习或更新偏置；
- 不从 `+90°` 推断 HOME 最终 PFBK；现有非零偏置下 HOME fail-closed 保持不变；
- 不增加双轴动作、自动回零、校准数据库或 GUI 校准向导；
- 不放宽动作安全范围、停止判据、反馈容差或模拟数据正式白名单；
- 配置漂移在首条动作 I/O 前拒绝，不能等动作完成后才发现。

## 本地与现场边界

本地完成：冻结、同源校验、命令/反馈双核对、旧 execution 禁止回填及相关回归。

现场仍需：使用同一 LTE MIMO OTA TestCase 保存各请求方位的原始 MOVEABS/PFBK，并单独取得
HOME 最终 PFBK。未完成现场复验前，P0-9B-3 只标记“本地半完成，待现场复验”。
