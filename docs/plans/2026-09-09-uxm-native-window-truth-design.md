# UXM 原生有限窗口现场诊断设计

## 1. 可观察故障

现有 `uxm_window_boundary_probe` 只读一个未经手册明确列出的 `STATe?`，不能回答
UXM 在现场 `LTE_NR_IRAT` Test Application 下是否真的接受手册示例中的 Single +
Length，也不能证明 `progress-count` 会在长度边界停止、连续两次窗口互不继承。
因此 P2-52 / P2-54 的 UXM 原生窗口证据仍是 hardware blocker。

## 2. 范围与非目标

新增独立诊断序列 `uxm_native_window_truth`，只形成现场观察证据：

- 只允许真实 `baseStation` 驱动、`LTE_NR_IRAT` 方言和操作员显式确认；
- 固定使用手册示例的 `CELL1`，不开放自由 SCPI 或任意 cell 注入；
- 连续执行两个相同长度的有限窗口，观察命令接受、错误队列、进度到界、到界后
  保持不变，以及第二窗口重新起算；
- 所有命令和原始回复留在诊断步骤与 `extra`，不写入正式 execution、报告或 KPI；
- 即使全部观察成立，`SequenceRunResult.success` 与 `formal_verdict` 仍保持 false /
  `unverified`。手册 Application Mode 只标 NSA/SA，不能据此宣称 IRAT 正式适用；
- 不改变 P2-48/P2-54 正式窗口实现、provenance 白名单或 lifecycle；不新增或猜测
  SCPI，不用 `*OPC?` 代替错误队列和进度证据。

## 3. 手册来源与命令边界

来源为仓库归档
`Instrument_API_Doc/Keysight UXM NR SCPI/5G_NR_Test_Application_SCPI_Reference.zip`
中的 `Examples > Measuring BLER` 与相邻命令条目。示例给出的命令顺序为：清除、
停止、配置 `LENGth:ALL`、配置 `CONTinuous:ALL 0`、启动，并说明结果数组第一字段
`progress-count` 达到所配长度时测量结束。

新常量只放在 `UxmLteNrIratProfile`，沿用生产代码已使用的
`BSE:MEASure:NR5G:BTHRoughput` 路径：

- `MEAS_BTHROUGHPUT_LENGTH_ALL`
- `MEAS_BTHROUGHPUT_CONTINUOUS_ALL`

基类与 `Uxm5GNRTestAppProfile` 保持 `None`。注释必须同时保留手册锚点、NSA/SA
范围错位和“仅供现场诊断”的限制。长度仅接受保守交集 `2000..360000` 且为 200
的倍数；不发明 Length/Continuous 查询形，所以输出使用 `requested_length`、
`observed_progress`、`observed_boundary`，绝不称为 `applied_length`。

## 4. 执行状态机

### 4.1 写入前门

所有失败都在首条写命令前结束：

1. 校验 `confirm_write is True`、长度、轮询间隔和总超时；
2. 拒绝 Mock、非 `LTE_NR_IRAT`、缺少 `_query/_write` 或缺任何必需 profile 常量；
3. 查询 `CELL_STATUS_QUERY(CELL1)`，只接受 `CONN` / `CONNECTED`；
4. 有界排空当前方言 `ERR`；历史错误可以归档，但必须最终读到 0，否则拒跑。

### 4.2 每个窗口

严格执行并逐项归属错误队列：

1. `CLEar`
2. `STATe 0`
3. `LENGth:ALL <N>`
4. `CONTinuous:ALL 0`
5. `STATe 1`
6. 轮询 `DL:BLER:CELL1?`，每次查询后立即查错误队列；只解析首字段为有限、
   非负整数 progress；要求单调、不越界，并在超时前精确等于 N；
7. 再等待一个采样间隔并读取一次，要求仍精确等于 N，作为 Single 到界停住的观察；
8. 第二窗口首个样本必须小于 N，随后再次精确到 N，证明没有继承前一窗口终值。

任一写入被错误队列拒绝、回复畸形、进度回退/越界、超时或第二窗口继承都判
`BLOCKED`，不得产生正式成功。

### 4.3 收尾与取消

只要尝试过写入，`finally` 必须发送同一已取证写形的 `STATe 0` 并立刻读取当前方言
错误队列；所有 cleanup 原始证据都留存。同步 PyVISA I/O 在线程执行，取消时等待
线程真实结束后再传播 `CancelledError`，避免外层先释放 unsafe lease 而旧 I/O 仍在
仪表上运行。序列不伪称自己完成了 release；lease release 由诊断 API 外层负责。

## 5. 输出语义

- `verdict=OBSERVED`：两次行为观察均成立，但 `success=false`；
- `verdict=BLOCKED`：现场行为与前提不成立或不可判；
- `verdict=ABORTED`：写前门未过，零写命令；
- `formal_verdict=unverified` 恒定；
- `observed_boundary`、`single_shot_observed`、`repeatable_observed` 只表达诊断事实；
- 保留每个窗口 progress 数组、错误队列原文和 cleanup 状态，不生成 KPI 数值。

## 6. 测试与镜像

测试必须覆盖零写前门、两窗口命令顺序、每步错误归属、正常到界但仍非正式、写拒绝、
畸形/回退/越界/超时/继承、异常与取消 cleanup、Mock 拒绝、手册锚点，以及新常量没有
进入正式窗口消费路径。更新 roadmap blocker、U-13 和旧 P2-52 计划的“现场复验”未来
清单；历史结论保持原样，只标明已被新受控载体取代。
