# P1-56 转台动作真值门与诊断载体实施计划

> 设计依据：`docs/plans/2026-08-18-p1-56-positioner-motion-truth-design.md`
>
> 方法：严格 TDD；每项先观察 RED，再写最小 GREEN。WIP=1。

## Task 1：驱动动作真值 RED

**文件**

- 新增 `api-service/tests/test_p1_56_positioner_motion_truth.py`
- 只读 `api-service/app/hal/aerotech_positioner.py`

**步骤**

1. 构造真实 driver 的受控 AeroBasic fake，能分别返回 pre-PFBK、状态位和 post-PFBK。
2. 写 ACK + settled + PFBK 不动的测试，断言 `move_to(90, 0)` 为 False。
3. 写到位、已在目标、0/360 环绕、超差、坏/NaN/Inf PFBK、HOME 不动测试。
4. 运行定点并记录预期失败原因，确认不是 fixture 错误。

## Task 2：驱动动作真值 GREEN

**文件**

- 修改 `api-service/app/hal/aerotech_positioner.py`

**步骤**

1. 增加严格有限数值读取与方位环形距离 helper。
2. 为实际轴实现前后反馈、动作变化与目标容差检查。
3. 接入 `move_to()` 与 `reset()`；`get_position()` 不再吞反馈错误回旧缓存。
4. 非有限目标在任何 I/O 前拒绝；已接受但未证明到位的超时、异常、取消先 ABORT，有限
   PFBK 无论成功失败都同步缓存。
5. MOVE/HOME 的 AXISSTATUS 复用严格整数 bitmask 解析，不允许浮点截断。
6. 新动作下发前拒绝遗留 MOVE_ACTIVE；ABORT ACK 后轮询全部实际轴，只有 MOVE_ACTIVE
   清零才返回成功/释放动作锁。
7. 运行 Task 1 定点直到全绿；再跑 Aerotech、standalone、P1-47C 相关回归。

## Task 3：诊断载体 RED

**文件**

- 新增 `api-service/tests/test_p1_56_aerotech_motion_diagnostic.py`

**步骤**

1. 锁住 loader 注册与 destructive metadata。
2. 锁住参数 fail-closed、权威 mock 拒绝和未连接拒绝。
3. 用 fake clock/driver 锁住无 XF 与有 XF 两段、全程无 DISABLE。
4. 锁住每段 `AXISSTATUS + PFBK` raw 样本、未动/超差失败和移动到位成功。
5. 锁住 AXISSTATUS 严格整数 bitmask、失败/取消 ABORT，以及完整动作与其他写入口共用
   `instrument_test_lease` 协调锁（急停保持可抢占）。
6. 锁住最终 MOVE_ACTIVE 不得成功、ABORT 失败不得继续第二段，以及 post-ABORT PFBK
   必须作为后续起点/最终缓存真值。
7. 锁住 ABORT ACK 但 MOVE_ACTIVE 未清零不得假成功，新动作也不得与遗留运动重叠。
8. 锁住人工急停共享 generation：首段中急停后不得发送第二段；内部 cleanup ABORT 不推进该值。
9. 锁住停止成功但 PFBK 失败时坐标为 null、GUI 不更新位置；HOME 与多实际轴走同一停止门。
8. 运行定点观察 RED。

## Task 4：诊断载体 GREEN

**文件**

- 新增 `api-service/app/diagnostics/sequences/aerotech_positioner_motion_truth.py`

**步骤**

1. 实现参数解析和真实 Aerotech 前置门。
2. 实现 ENABLE-once、两段 MOVEABS 对照与 200ms/10s 采样。
3. 把 raw 样本写入 `SequenceStepResult.raw` / `result_extra`。
4. 只判编码器反馈；物理方向/单位/偏置明确 unknown/Hardware Blocked。
5. 运行 Task 3 定点直到全绿。

## Task 5：消费方与文档镜像

**文件**

- 修改 `api-service/app/services/mimo_ota/cleanup.py`
- 修改 `docs/roadmap-first-call.md`
- 必要时修改现状 runbook（不改历史日志）

**步骤**

1. RED：cleanup 的 `move_to(False)` 必须进入 warnings。
2. GREEN：最小消费 False，不改 best-effort 清理语义。
3. 复扫全部 `move_to()` 调用，记录每一处成功/False/异常处理结论。
4. Roadmap 标记 P1-55 已合并、P1-56 本地片 WIP；现场半继续 Hardware Blocked。

## Task 6：验证、内审与 PR

1. P1-56 定点与全部 Aerotech/positioner/正式消费相关回归。
2. 完整 rule gates、全后端、compileall、GUI production build、diff-check。
3. fresh 内审至 P1=0；P2/P3 按仓库规则处理。
4. 提交、推送、开 Ready PR，触发 Codex R1。
5. R1 本片内意见按 TDD 收口后触发最终 R2；R2 无 P1 merge；R2 有 P1 修完后直接 merge，不发 R3。
6. 合并后验证 origin/main；P1-56 本地片完成，现场物理裁决继续 Hardware Blocked。

## 内审尾修补充

- 人工 stop generation 的最终裁决必须与 MOVE TX 共用驱动通信锁，消除“ABORT 完成后排队
  MOVE 又启动”的竞争窗口。
- sweep PFBK 不可得时，坐标与 `within_tolerance` 同时为 null，GUI 显示灰色“未知”。
