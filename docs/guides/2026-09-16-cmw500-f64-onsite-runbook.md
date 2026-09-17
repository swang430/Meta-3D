# 2026-09-16 CMW500 + F64 现场单步调试 Runbook

## 目的与证据边界

本轮目标是用现有受控诊断和正式 TestCase 关闭 CMW500 + F64 的现场半项，不创建一键硬件
编排器，也不临时试探 SCPI。

- 数据库中的 `connected` 是配置/历史状态，不是本次现场活连接证明。
- Mock、simulated 或本地测试不是真机验收。
- 诊断序列 `SUCCESS` 只证明该序列定义的事实；不自动获得 calibration、site certification
  或正式 KPI 资格。
- 只有同一真实 execution 冻结的 binding、adapter、MAC profile、校准/认证、生命周期和
  release 证据全部成立，正式报告才可能放行。

2026-09-15 的非现场盘点仅用于安排顺序，现场开始前必须重新读取当前配置、证书和仪器身份，
不得把盘点快照当作明日实况。

## 0. 开始前

1. 确认系统处于 Real 模式，没有其他执行、诊断或人工 VISA/ATE 会话占用仪器。
2. 在 LabProfile 中核对已保存的 CMW500、F64、暗室、RF 拓扑与 TestCase。保存仪器配置后，
   以分类 HAL 激活结果为准；不要用单独整体 reload 掩盖配置漂移。
3. 运行 `chamber_configuration_integrity`，记录 `diagnostic_run_id` 及各仪器本次读取的身份。
   若型号、endpoint、selected model、adapter 或 LabProfile binding 不一致，停止，不继续下发。
4. 重新核对路损校准、BaseStation/F64 site certification、DUT/SIM 与安全互锁。任何正式前置
   缺失时，本轮只能做诊断并保持 KPI `UNKNOWN/N/A`，不得把结果签成正式通过。
5. 为正式执行复制/建立专用 LTE FDD TM3/2 TestCase。不要把现有 LTE TDD 用例临时改成
   FDD；TDD 必须使用另一份显式含 `lte_tdd_frame_structure` 的 TestCase。

## 1. F64 独占维护窗口

先保全已有错误队列证据，再运行会发送 `*CLS` 或读取错误队列的序列。此阶段禁止正式执行并
确保没有第二个 ATE 客户端。

1. 运行 `propsim_f64_license_truth`，保存 `diagnostic_run_id`、身份、许可/校准原始证据和终态。
   **2026-09-16 现场更正**：当日两次连续运行已稳定复现本序列自身产生错误队列残留，
   详见 §7；在软件修复前不再重复运行，也不得据当前绿色步骤或总体 `UNDETERMINED`
   关闭 P1-2。
2. 通过产品受控资产流程加载指定 LTE UMa `.smu`。确需命令行交还控制权或加载时，只保留的
   入口是：

   ```bash
   python scripts/onsite-f64-control.py local
   python scripts/onsite-f64-control.py load '<F64 本机上的完整 .smu 路径>'
   ```

   不猜路径、不扫 SMB、不用已退役的一键吞吐脚本。
3. **CMW500 本轮禁止运行 `propsim_f64_p08_gate`**。该序列的当前契约硬编码
   `uxm_dl_confirmed`、“UXM 满 RB DL”和“UXM DL 接入”，不是 CMW500 输入源的合法载体。
   2026-09-16 误启动的 `diagnostic_run_id=78aa4816-7eab-435b-aec9-7866a1152d31`
   因未勾选 UXM 确认而在参数门拒绝，未进入 F64 动作；不得为了让它继续而虚假勾选。
   当日 F64 + CMW500 闭环改由 §2 的 CMW 诊断和 §3 的正式 LTE TestCase 取证；
   不为跑过本序列而切换到 UXM、改写 LabProfile 或重载错的 adapter。
4. 运行 `propsim_f64_output_level_windows`，只接受本次仪器返回的活动物理输出集合；记录
   `diagnostic_run_id` 与每个活动口的窗口。
5. 仅在需要复核 P2-71 支持分类时运行 `propsim_f64_health`。它会发送 `*CLS` 并消耗错误
   队列，绝不能与执行并发。`MMEM_CDIR/CAT` 的目标回复、异常与错误队列原文保存在
   `extra.scpi_observations`；这些证据只能分类该设备是否支持查询，不能证明设备文件字节、
   版本、发布或回滚。

## 2. CMW500 关闭小区矩阵抽样

> **2026-09-17 更正：本节由必做降为可选。** 现场结论：开测前的矩阵抽样对「这次测试」不必要 —— 探针产出只进
> `DiagnosticRun`、正式执行链零读取；§3 的正式执行自带同次的写→错误队列→回读证据；`tm1_one` 在正式 schema 不可达；
> 且探针要求仪器「已配置 FDD」却不切 duplex，该前置只有正式执行才会建立（2026-09-16 `a0395c8a` 因仪器在 TDD 被预检拒）。
> P2-55 的 TM3+2TX 格改由正式执行的同次回执签收。只有在评估「是否开放 TM1 等新取值域」时才需要跑本节。

在 GUI「调试维护 → 调试序列 + 单阶段」中运行 `cmw500_fdd_matrix_probe`：

1. 选择 `TM1 + 1 TX（SIMO 1x2）`（参数值 `tm1_one`），保存 `diagnostic_run_id`、写入、
   回读和错误队列证据。
2. 再选择 `TM3 + 2 TX（MIMO 2x2）`（参数值 `tm3_two`），保存同样证据。

该序列会关闭小区，只做 FDD/20 MHz/1CC-nx2 配置抽样；它不 Attach、不测吞吐、不授予
正式资格。跨 TM 的中间设置若被仪器拒绝，保留原始证据并停止，不按手册类比猜自动耦合。

## 3. FDD 正式链优先

1. 选择专用 FDD TM3/2 TestCase，确认冻结的 CMW adapter/binding、LTE MAC profile digest、
   F64 channel asset 与当前 LabProfile 一致。
2. 使用真实 DUT/SIM 完成 Attach、业务窗口、方位测量、SAFE_IDLE 和 transport release。
   保存 `execution_id`、每个 attempt 的 MAC receipt、窗口证据、F64 模型/输出状态、转台反馈、
   终态与报告 outcome。
3. 为 P1-74 使用至少两个不同 `stat_count` 连续执行，证明第二次统计基来自本次 TestCase，
   不继承上一 session。两次都保存原始写/读/错误队列证据。
4. 为 P1-4 在同一 TestCase 上完成两次可比 execution，再使用 execution 级比较报告；不要拿
   两个不同配置的结果宣称重复性。
5. 只有 FDD 基线可复现后才运行 TDD。TDD 使用独立 TestCase，并显式冻结
   `uldl_configuration` 与 `special_subframe`；不得从仪器复位状态或 FDD 用例补真。

## 4. F64 Local 交还

1. 运行 `propsim_f64_local_handback_check`，选择 `release`。
2. 等序列完成并释放 lease/socket 后，**先观察前面板**：记录 Remote mode 水印和 Local Mode
   按钮的实际状态。不要先启动 confirm；confirm 会重新取得运行上下文，可能改变观察条件。
3. 再运行同一序列，选择 `confirm`，填写观察原文并显式选择 `local` 或 `remote`。留空会得到
   UNDETERMINED；不得把 `ate_socket_released` 自动写成“面板已 Local”。
4. 保存两段各自的 `diagnostic_run_id`。人工 Local 观察不会升级 calibration/site certification
   或正式 KPI 资格。

## 5. 停止条件

遇到以下任一情况，保留原始证据并停止当前链，不临时改命令、不重试到“变绿”：

- 实时 IDN、selected model、adapter、endpoint、LabProfile binding 或冻结 digest 不一致；
- HAL 激活失败或仍加载旧 adapter；
- F64 出现未解释的错误队列残留、模型/输出状态未知或独占条件不成立；
- CMW 写后回读不一致、错误队列非零、选件不满足或小区状态无法安全确认；
- 正式目标下 calibration/site certification 缺失、撤销或与本次 binding 不匹配；
- DUT/SIM Attach 失败、模拟/未知 provenance 出现、SAFE_IDLE 或 release 无法确认；
- 转台坐标/反馈、F64 输出或其他安全状态未知。

## 6. 证据交接清单

每个关闭项至少交付：

- 序列名、参数、`diagnostic_run_id`、开始/结束时间与终态；
- 正式运行的 TestCase ID、`execution_id` 与 attempt/lease 标识；
- 本次实时仪器身份、固件/选件原始回复（序列已采集的范围内）；
- frozen LabProfile、adapter、binding、MAC profile/channel asset digest；
- CMW requested/applied/readback、统计窗口、错误队列与 MAC receipt；
- F64 模型加载、运行、活动输出窗口和错误队列证据；
- DUT Attach、转台方位/HOME、SAFE_IDLE、transport release 与报告 outcome；
- 任何 BLOCKER/UNDETERMINED 的原始回复和操作员观察，不只抄摘要。

本轮优先可关闭 P2-55、NEW-1、NEW-2；P1-2 已因 §7 的现场发现转为“软件修复后现场复验”，
当前不能关闭。P2-51、P1-74、P0-9、P0-8b、P1-4、
P2-56 与 P2-61/62 是否关闭取决于同一真实执行能否满足各自独立验收条件。P2-71 本轮最多
补设备查询支持分类，文件字节摘要、版本发布和回滚仍保持 Hardware Blocked。UXM 专属项与其他
不在 CMW500 + F64 链上的硬件项不由本轮关闭。

> **2026-09-17 结果**：以上是出发前的预期。实际关闭了 P0-8b、P2-51 现场半（按现场证据）；P2-55 现场半（改验收后收口）；P0-9 整项与 P2-56 现场半（用户 2026-09-17 裁决关闭 —— 校准相关条件移交、TDD 下的真实 Attach / 窗口仍无真机样本，不是验收条件已满足）；P1-74 / P1-4 / P1-2 未关闭；
> NEW-1 / NEW-2 / P2-71 / P2-61/62 当日未跑。逐项依据见[现场总结](../site-debug/2026-09-16-cmw500-f64-onsite-summary.md) §4。

## 7. 当日现场发现（只记录，不在现场临时修）

### `instrument_idn_sweep` 范围与身份读取契约失效

- 现场执行：`diagnostic_run_id=94a93c8a-9035-4190-acef-baea28b41cad`，结果为
  `7/7 instruments did not respond`。该摘要**不能作为七台仪表均离线的证据**。
- 当日仪器目录中只有 `baseStation`、`channelEmulator`、`positioner`、`rfSwitch` 四类启用，
  但 `CAICT-Lab-1.instrument_bindings` 仍保留七类；停用的 `vectorSignalGenerator`、`vna`、
  `signalAnalyzer` 因序列无条件遍历全部 LabProfile binding 而被纳入。VNA binding 还保留
  `192.168.100.25`，与当前仪器目录 endpoint `192.168.0.10` 不同，属于配置漂移证据。
- 四个已加载驱动均在 `0 ms` 内返回
  `Driver exposes none of get_identity/query_idn/query`，证明失败发生在本地方法分派、没有向仪表
  发出身份查询。CMW500、F64/UXM 已分别拥有结构化身份/环境快照接口，序列却仍探测早期通用
  方法名；转台当前明确没有安全的型号/固件查询，RF Switch 也没有统一身份投影。因此这四项是
  “诊断契约不匹配/身份不适用”，不能解释成硬件无响应。
- 该序列还没有服务器侧核对 selected model、endpoint 与 loaded adapter；即使取得字符串，也只能
  靠操作员人工比对，无法兑现序列描述中的“确认与 LabProfile 声明一致”。
- 现场处置：保留本次审计记录，不据此重连、reload 或改写 LabProfile，不临时增加/猜测身份 SCPI；
  分别使用已有分类健康探针和 HAL readiness 判断四台当前连接状态。
- 后续软件修复已登记到 `docs/roadmap-first-call.md` 的 2026-09-16 Discovered 条目：目标范围应明确为
  当前启用类别与所选 LabProfile binding 的受控交集，并显式报告被排除的旧 binding；身份读取改用
  adapter 已有的只读结构化投影，区分“匹配 / 不匹配 / 未加载 / 身份未知或不适用”，不得重新开放
  任意底层 `query("*IDN?")`。

### `propsim_f64_license_truth` 把错误空回复显示为成功

- 现场连续两次执行分别为
  `e916b910-a7cf-4d1e-a89c-54941c4e6ccd`（2026-09-16 03:49:48Z）和
  `c3a445a2-cad7-427f-8567-1b6d2cf20c40`（03:54:34Z）；两次均为
  `UNDETERMINED`，并稳定得到完全相同的尾队列：
  `-200,"Execution error;No simulation opened"`、
  `-100,"Command error;ATE command not supported"`。
- 两次运行之间第一轮已经把错误队列读到零，且没有第二个 ATE 客户端或其他 F64 操作；因此
  第二轮复现排除了“历史残留”解释。不要继续重跑、`*CLS` 或为变绿而临时打开仿真。
- 当日 `DIAG:SIMU:STATE?=CLOSED`；`SYSTem:CALIBration:VALid?` 返回空串，却被步骤显示为
  `✓ 解析不出 <in use>,<valid>`。2026-08-27 的同机历史运行
  `4aa35f2b-d240-409c-8158-776015a173a4` 在 `STOPPED` 时该查询返回 `1,0`，尾队列只有
  `-100`。结合本次命令顺序，现场证据把新增 `-200 No simulation opened` 归到 CLOSED 下的
  `CALIBration:VALid?`。
- `SYSTem:CALIBration:USER:GET?` 在上述三次运行中都返回空串；2026-08-27 即使
  `VALid?=1,0`、仿真为 `STOPPED`，尾队列仍稳定只有 `-100 ATE command not supported`。
  因而本机空串不能继续解释为“未启用用户对齐”，应为 `UNKNOWN/unsupported on observed unit`；
  不把这一台 F8800A/当前软件面的观察推广成所有 F64 的能力结论。
- 当前能确认的真机事实只有：身份匹配；`SYSTem:INFO?` 返回 10 条许可字段且与驱动
  `INT-GEN` 声明无差异；`CALIBration:LIST?` 返回
  `CalibrationConfig10,CalibrationConfig12`。当前加载校准、校准有效性与用户对齐状态均未确认，
  不得进入正式 calibration/site-certification/KPI 资格。
- 后续软件修复并入 P1-2：错误队列须能归属到具体查询；空回复只有在该查询的错误队列为零且
  符合手册值域时才算成功；结果须分列 `license`、`calibration`、`user_alignment`，不得用许可
  成功补真校准。优先按已观察状态/许可收窄现有查询，不新增或猜测替代 SCPI。修复完成后在同一
  F8800A 上从干净队列复验，只有有效子判决与终态零残留同时成立才可关闭 P1-2。
