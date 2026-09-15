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
2. 通过产品受控资产流程加载指定 LTE UMa `.smu`。确需命令行交还控制权或加载时，只保留的
   入口是：

   ```bash
   python scripts/onsite-f64-control.py local
   python scripts/onsite-f64-control.py load '<F64 本机上的完整 .smu 路径>'
   ```

   不猜路径、不扫 SMB、不用已退役的一键吞吐脚本。
3. 运行 `propsim_f64_p08_gate`，保存加载、运行、错误队列和安全收尾证据。
4. 运行 `propsim_f64_output_level_windows`，只接受本次仪器返回的活动物理输出集合；记录
   `diagnostic_run_id` 与每个活动口的窗口。
5. 仅在需要复核 P2-71 支持分类时运行 `propsim_f64_health`。它会发送 `*CLS` 并消耗错误
   队列，绝不能与执行并发。`MMEM_CDIR/CAT` 的目标回复、异常与错误队列原文保存在
   `extra.scpi_observations`；这些证据只能分类该设备是否支持查询，不能证明设备文件字节、
   版本、发布或回滚。

## 2. CMW500 关闭小区矩阵抽样

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

本轮优先可关闭 P2-55、P1-2、NEW-1、NEW-2；P2-51、P1-74、P0-9、P0-8b、P1-4、
P2-56 与 P2-61/62 是否关闭取决于同一真实执行能否满足各自独立验收条件。P2-71 本轮最多
补设备查询支持分类，文件字节摘要、版本发布和回滚仍保持 Hardware Blocked。UXM 专属项与其他
不在 CMW500 + F64 链上的硬件项不由本轮关闭。
