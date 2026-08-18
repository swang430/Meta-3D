# P1-56 转台动作真值门与诊断载体设计

## 1. 可观察故障

2026-08-07 现场连续 15 次看到控制器接受 `MOVEABS`，但 `PFBK(X)` 一个计数未动，
`RealAerotechDriver.move_to()` 仍仅凭 `AXISSTATUS` 的 InPosition/MoveActive 位返回成功。
一旦正式 MIMO 方位循环继续运行，多个方位可能在同一物理位置采样，并生成外观正常的
吞吐与报告。这是“命令被接受”被误当成“机械动作已发生”的假成功。

本地片只解决可由仓内协议证据判定的两件事：

1. 控制器反馈没有按请求目标变化时，真实 Aerotech `move_to()` / `reset()` 必须失败，
   所有正式消费方随既有布尔契约停止采集；
2. 提供可在现场重复运行的破坏性诊断序列；只有站点显式确认 degree user-units 与
   安全坐标范围后，才发送带明确 `XF` 的小步前进/返回命令并保存 `VFBK`、`PFBK` 原始轨迹。

控制器型号/固件、控制坐标到 DUT 物理方位的偏置、正反方向和真实机械动作仍需要人在暗室
观察，继续标记 Hardware Blocked。user-units 与安全范围未先写入现场核验配置时，诊断保持
fail-closed；该配置只允许本地载体运行，不替代物理目视验收。

## 2. 全集枚举

### 2.1 动作产生方

- `RealAerotechDriver.move_to()`：真实 AeroBasic/TCP `MOVEABS`；本片主修复点。
- `RealAerotechDriver.reset()`：真实 `HOME`；当前同样只信状态位并把缓存直接写为 0。
- `RealEtsEmcenterDriver`：仓内 EMCenter 手册只覆盖 RF switch，不证明转台位置、停止或回读
  方言；真实 `move_to/get_position/stop/reset` 全部在 SCPI I/O 前 fail-closed，能力标 unsupported。
- `MockPositioner.move_to()`：模拟驱动；不代表真实机械动作，不进入本片真硬件判据。

### 2.2 `move_to()` 生产消费方

- MIMO OTA `MEASURE` 每方位；已在 False 时终止并返回 FAILED。
- 探头方向图扫描；已在 False 时抛错，停止后续 SA 采样。
- 静区真实 grid 的输入是厘米线性位移；旋转转台 degree API 不能消费，缺少已验证的 XY stage
  API 时在任何转台/CE/SA I/O 前 fail-closed。
- 空间相关校准的输入是米制天线间距；旋转转台 degree API 不能消费，缺少已验证的线性 stage
  API 时在任何转台/SA I/O 前 fail-closed。
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
EMCenter 转台方言在仓内没有动作/回读协议证据，因此四个真实入口与位置 metrics 全部
fail-closed；这不是把 Aerotech 证据推广到另一驱动。

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

1. 在任何控制器 I/O 前拒绝 bool、NaN、Inf 等非有限目标；
2. 命令前读取仓内手册有明确语义的 `VFBK`；任一实际轴非精确零速则拒绝叠加；
3. 命令前严格读取各实际轴的 `PFBK`；
4. 仅在站点显式证明 controller user-units=degree、安全范围、正 XF feed，且实际轴为
   单一方位轴时，发送指南有出处的 `MOVEABS X <target> XF<feed>`；双轴写法没有仓内出处，
   保持 fail-closed；
5. 发送指南有出处的 `WAIT INPOS X`，再以 `VFBK(X)` 的有限精确零速确认已停止；
6. 严格读取最终 `PFBK`，先同步有限编码器真值到缓存，再判成功与否；
7. 每个实际轴都要求最终反馈在配置容差内到达请求目标；
8. 若请求目标与起点的距离超过容差，还要求反馈相对起点发生可观察变化；否则返回 False，
   错误明确为 `motion_not_observed`，不得打印 Arrived。

方位误差使用 360° 环形距离，避免 359.8°→0° 被误判；俯仰使用线性距离。已在目标位置时
不强求再次运动，只要求最终反馈仍在容差内。

容差是应用判据，不是仪器回读单位推断；默认 0.5°，可由连接参数
`position_tolerance_deg` 收窄配置。正式动作和诊断均要求现场先写入
`motion_truth_units_verified=true`、`motion_truth_user_units=degree`、安全上下界与正
`motion_truth_xf_speed`；缺任一项就在控制器 I/O 前拒绝。

### 4.3 HOME

`reset()` 不再在 HOME/状态位后直接把缓存写成 0。只有上述单轴/单位/范围/feed 配置已证明
且 0 在安全范围内才发送指南有出处的 `HOME X`，随后 `WAIT INPOS X` + VFBK/PFBK；它读取
前后反馈，要求最终反馈到 0，起点明显非零时还要求有反馈变化。失败返回 False。

## 5. 诊断载体

新序列 `aerotech_positioner_motion_truth`：

- 只接受权威 `is_mock_driver()` 判定为 real、已连接且暴露 AeroBasic `_send` 的 positioner；
- `safe_during_test=False`，复用现有破坏性诊断互斥与审计链；
- 完整 MOVE/HOME 另复用 `instrument_test_lease` 的协调锁，因此正式消费者、standalone
  写入口和 destructive diagnostic 之间不会在两条 TX/RX 之间插入另一条机械动作；急停
  `ABORT` 不取该操作锁，必须能抢占未结束动作；
- 前置配置：`motion_truth_units_verified=true`、`motion_truth_user_units=degree`，以及显式
  `motion_truth_min_deg` / `motion_truth_max_deg`；缺任一项都在 ENABLE/MOVEABS 前拒绝；
- 参数：安全小步进（默认 10°，限定 0.1..30°）、采样时长
  （默认/最大 10s）、采样间隔（默认 0.2s，限定 0.1..1s）和容差；
  `XF` 速度只能消费站点批准的 `motion_truth_xf_speed`，请求不可覆盖；
- 运行前读取起点，显式 `ENABLE <axis>` 一次，此后不发送 `DISABLE`；
- 不做 360° 取模；只在显式安全范围内选择正向或反向小步，前进与返回都使用手册明确展示的
  `MOVEABS ... XF...` 形式；第一段未获完整证明时禁止再发返回段；
- 每段连续采 `VFBK(axis)` + `PFBK(axis)`，保存 elapsed、原始回复、解析值；只有反馈变化、
  到达目标、样本全为有限值且最终 VFBK 精确为零才算动作有证据；
- 新诊断动作下发前同样确认全部实际轴 VFBK 为零；已接受但未证明动作的段先 `ABORT`，
  再轮询全部轴直到 VFBK 精确为零，无论 stop 成败都独立回读 PFBK；ABORT 或回读未确认时
  禁止发送返回段；
- `result_extra` 保存全部样本，`SequenceStepResult.raw` 保存关键原始回复。诊断结论只说明
  “控制器编码器反馈是否移动/到达”，不声称 DUT 物理角度已校准。

命令依据来自仓内 `Instrument_API_Doc/Aerotech/Aerotech_Ensemble_ASCII_TCP转台控制集成说明.docx`
§4–§7：`MOVEABS X <angle> XF<speed>`、`ENABLE X`、`VFBK(X)`、`PFBK(X)`、到位后再采集。
仓内指南没有给出无 XF 的安全语义，也没有给出 AXISSTATUS 位号，因此本诊断不据此下发或
判成功。仓内对象为 Ensemble、驱动头仍写 A3200/Automation1；型号差异不在本地猜测。

## 6. 状态与失败路径

- 成功：缓存由严格最终反馈更新，状态 READY。
- 设备拒绝、故障、超时、反馈无效、未发生应有动作、最终超差：返回 False，状态 ERROR；
  正式消费方停止采样。只要已接受动作但未证明到位，先 best-effort `ABORT`，再尽力回读；
  只有动作段成功，或 ABORT 已由全部实际轴零速证明成功时，有限 PFBK 才同步为稳定缓存；
  停止未证时的瞬时 PFBK 只作 raw evidence，稳定缓存保持 UNKNOWN，避免 metrics 发布旧值
  或把运动中的瞬时坐标冒充到位位置。
- 取消：已接受动作先完成 `ABORT`/回读收尾，再保持 `CancelledError` 传播语义；诊断框架
  负责审计 cancelled，不得在释放 destructive token 后留下后台运动。
- ABORT 的 ACK 不是停止成功；只有全部实际轴的有限 VFBK 都精确为零才返回 True/释放动作
  互斥。严格零速可能产生安全侧假阴性，但不会用无出处位号假称已停。
- 人工 `/positioner/stop` 与内部安全 cleanup 必须区分：只有人工急停推进 driver 上的共享 stop
  generation；破坏性诊断及正式 `move_to()` / `reset()` 都在动作入口 snapshot generation，
  并把前置条件与实际 MOVE/HOME TX 放进同一个驱动通信锁临界区。无论人工 ABORT 在动作
  前置回读期间还是命令发送后取得顺序，急停完成后都不得排队重启转台；历史急停之后新发起
  的动作会 snapshot 当前 generation，仍可正常运行。MIMO、方向图与 cleanup 在一次多步操作
  开始时保留同一 generation，急停后后续点和自动回零均不得重启。静区与空间相关因线性单位
  API 缺失已在更早位置 fail-closed，不再调用旋转转台。
- generation 基线由执行所有者在**正式受理/等待仪器租约前**建立：TestCase 正式执行在创建
  后台 task 前建立并由 task 继承；commissioning run-all 在整条五相位链开始时建立；单阶段与
  adhoc 在各自 phase 请求进入租约前建立。所有入口均用同一 ContextVar 传入 MEASURE/cleanup，
  并在正常、异常和取消出口恢复上下文；等待租约期间执行行已经是 running，HAL reload 不能
  静默换掉 driver-local generation 真值。
- TCP 静默重连只恢复 transport，不发送 ACK/ENABLE 等写命令；只读查询可在重连后重试一次，
  HOME/MOVE/ENABLE/ABORT 等非幂等写若在收发中断线，结果保持 UNKNOWN 并禁止重放。
- `connect()` 只做 transport 建立与只读轴发现；`disconnect()` 只关闭 transport。清错、使能和
  禁用没有当前仓内出处，不得夹带在连接生命周期里制造假成功或改变机械状态。
- AeroBasic `#` task-fault 是明确失败，不得当成 ACK；AXISFAULT/AXISSTATUS 只有完整、有限、
  非负整数才可作为 raw bitmask，坏值保持 UNKNOWN。健康诊断的 mock 判定复用 HAL 权威白名单。
- PFBK/VFBK 在未获得 degree user-unit 站点证明时只能显示 raw controller units，不能写入
  `*_deg`、缓存 degree 位置或 GUI 正式位置。
- 急停停止确认与位置反馈是两个独立事实。ABORT 已确认但 PFBK 失败时，REST 仍可报告停止
  成功，但方位/俯仰必须为 `null`，GUI 保留上一次已知位置，不得用 `0°` 伪装未知位置。
- sweep 的到位判词同样是三态：位置可信且到位为 true，位置可信但超差为 false，PFBK
  不可得为 null/“未知”；不得把未测到渲染成红色“超差”。
- 诊断动作结束：最终 VFBK 非零/不可读、ABORT 未确认或 post-ABORT PFBK 不可得时均
  fail-closed；不得释放互斥后声称成功或叠加下一条动作。
- cleanup 的 False 进入 warnings，但不遮蔽原始执行错误。

## 7. 验收

1. `MOVEABS` ACK + settled，但请求 90°、PFBK 始终 0° → `move_to()` False，无 Arrived。
2. 起点已在目标容差内 → 可成功，不要求无意义的额外运动。
3. 359.8°→0° 按环形容差成功；明显超差失败。
4. PFBK 空/坏/NaN/Inf 不得变成 0 或旧缓存成功。
5. HOME 后反馈未回 0 → reset False。
6. 全部活动正式消费方继续消费同一 bool；cleanup False 可见。
7. 新诊断序列可由 loader/API/GUI 动态列出；mock/无连接 fail-closed。
8. 诊断只用带明确 `XF` 的前进/返回，不发送 DISABLE，按 200ms/10s 保存 raw 速度与位置样本。
9. 部分移动/超差时缓存反映最终有限 PFBK，但结果仍 False；NaN/Inf 目标在任何 I/O 前拒绝。
10. 诊断 VFBK/PFBK 的坏值、NaN、Inf 均不得折叠成零或成功；VFBK 非零不得宣称停止。
11. destructive diagnostic 与其他 MOVE/HOME 共用完整操作锁，stop/ABORT 保留抢占能力。
12. 未证明动作、超时、异常与取消均执行 ABORT+独立 PFBK 回读；ABORT 失败不继续第二段，
    post-ABORT PFBK 不得被旧样本覆盖。
13. ABORT ACK 后 VFBK 仍非零必须返回 False，禁止返回段与后续 MOVE/HOME；零速后才可继续。
14. 人工急停落在诊断首段时，第二段 MOVEABS 永不发送；内部安全 ABORT 不会误取消正常诊断。
15. 急停后 PFBK 失败返回空坐标且 GUI 不更新当前位置；HOME 与全部实际轴的停止门有直接保护。
16. generation 必须在实际发送锁内复核；人工 stop 已推进 generation 后，排队中的诊断 MOVE
    不得在 ABORT 之后发出。
17. sweep PFBK 失败时到位判词为 null/灰色“未知”，不能显示红色“超差”。
18. 正式 `move_to()` 与 `reset()` 在 preflight/PFBK 期间发生人工急停时，也必须在 TX 前拒绝
    后续 MOVEABS/HOME；不得只保护诊断序列。
19. 本地完成后 P1-56 本地片可合并；现场真实机械方向/单位/偏置/型号裁决仍 Hardware Blocked。
20. 未验证 user-units/range 时诊断在 ENABLE/MOVEABS 前拒绝；起点 10000 不得经 `% 360` 变成
    290，也不得发送任何无明确 XF 的 MOVEABS。
21. 人工急停发生在 MIMO 或方向图多点操作任一位置后，后续 move 与 MIMO cleanup 回零都
    复用操作开始 generation 并 fail-closed；静区厘米网格和空间相关米制间距不得进入旋转
    转台 degree API。
22. 正式 `MOVEABS/HOME` 与诊断共用显式 degree/range/feed 白名单；正式 MOVE 只发有出处的
    `MOVEABS X ... XF... → WAIT INPOS X`，不得用未证实 AXISSTATUS 位号或双轴命令宣称到位。
23. 健康诊断可保留 AXISSTATUS 原始十六进制证据，但不得显示 Enabled/InPosition/
    MoveActive 等未获仓内手册证明的位含义。
24. 诊断必须在 ENABLE 前完成起点、目标和安全范围验证；越界起点不得留下已使能轴。
25. EMCenter 转台四个真实动作/回读入口没有厂商协议证据时全部在 SCPI I/O 前拒绝；
    不得返回缓存位置、假停止成功或暴露 supported capability。
26. 动作命令在 silent reconnect 或断线重试期间发生人工急停时，必须在每次真实 TX 前重新
    核对 generation；不得在重连完成后补发 MOVE/HOME。
27. 控制器返回 `#` task-fault 时正式动作与健康诊断均不得当成功；fractional/NaN/Inf bitmask
    保持 UNKNOWN，不得通过整数截断洗成健康 0。
28. silent reconnect 只恢复 transport；断线后的非幂等命令不得重放，只读反馈最多重试一次。
29. connect/disconnect 不发送无出处 ACK/ENABLE/DISABLE；只有经站点证明的正式动作/诊断可
    在目标与安全范围校验后显式 ENABLE。
30. 诊断 `XF` 只能使用站点批准的 `motion_truth_xf_speed`；请求体不得改写硬件动作 feed。
31. EMCenter metrics 不得发布假 0°；未验证 PFBK/VFBK 只能作为 raw controller-unit 诊断证据。
32. Aerotech runtime/catalog 只声明当前有命令证据的单轴能力；读到双轴控制器或缺少
    degree/range/feed attestation 时 capability 必须 unsupported，不能把物理潜力当已实现契约。
