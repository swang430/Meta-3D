# CMW500 MAC 能力补齐与多信道仿真器接入 Roadmap 设计

**日期**：2026-08-30

**状态**：用户批准进入 roadmap 雷达；未授权自动启动开发

**对应条目**：P1-74、P1-75、P2-54～P2-67

## 1. 决策摘要

采用“按能力合同拆片、现场与非现场双队列”的方案，不建两个覆盖面过大的 CMW/Channel Emulator
史诗项目，也不等待下一台真机到场后再临时抽象。

执行顺序固定为（2026-08-31 修订，P2-64～P2-67 整组前移）：

1. P1-74：先消除 CMW500 Extended BLER 统计基继承旧 session 的正式数据风险；
2. P1-75：在首次仪表 I/O 前拒绝 TestCase 与所选 BaseStation Adapter Manifest 的能力冲突；
3. P2-64～P2-67：紧跟 P1-75 收口同一次 Mock 复盘派生的 Adapter-scoped Mock、共用兼容性
   Readiness、证据终态与日志导出；四片连续，不与母片拆开到不同上下文；
4. P2-54～P2-56：把 RAT-neutral 测试意图、LTE FDD 能力矩阵与 LTE TDD 真机认证分开；
5. P2-57～P2-62：依次建立 Channel Emulator manifest、binding/preset、execution plan/session、
   operation receipt、Diagnostic/Formal certification 与第三 adapter 认证套件；
6. P2-63：真实型号与原始手册确定后才启动，当前 HOLD；它是条件项，位于队列末尾，
   不阻断任何已批准条目。

当前非现场 WIP 为 0。上述条目进入正式雷达不等于开始开发；启动时仍按 WIP=1、独立 worktree、
严格 TDD、fresh 功能内审、Ready PR、Codex R1→R2、覆盖最新 HEAD 无 P1 才合并的既有流程。

## 2. 现状证据与问题边界

### 2.1 CMW500 MAC

- `api-service/app/hal/cmw500_base_station.py::configure_mac_throughput_test()` 已闭环窄范围 LTE FDD
  2×2、满 RB、固定 RMC，但其输入仍承接 `uxm_base_station.py::MacThroughputConfigResult` 及 NR-shaped
  参数；LTE 无等价语义被压进 `no_equivalent`。
- `api-service/app/hal/cmw500_base_station.py` 已明确把 `EBLer:SFRames` 归属窗口层，但当前未驱动；
  TestCase 的 `stat_count` 因此没有成为本次仪表统计基真值。
- P2-51 已查明 LTE TDD 需要 LTE ULDL/RMC 专用字段，NR slot pattern 不能诚实翻译。

因此不能把 P2-51 继续扩大成“完善所有 CMW MAC”。首先要拆开三件不同的事：统计窗口真值、
跨 RAT 测试意图、CMW 具体组合能力。否则一个总布尔仍会掩盖部分字段未确认。

### 2.2 Channel Emulator

- `api-service/app/hal/channel_emulator.py` 默认声称所有信道仿真器支持 `EXTERNAL_WAVEFORM`；
  这是未经每型号证明的共享能力推广。
- `api-service/app/hal/propsim_f64.py` 已形成 Native/ASC/TDL 三种加载管线及大量 F64 专属运行真值；
  `api-service/app/hal/propsim_fs16.py` 同时声明 `EXTERNAL_WAVEFORM`，但 capability 文案又承认
  upload/start/path-loss/doppler/MIMO 未实现。
- `api-service/app/services/mimo_ota/executors/measure.py` 仍直接读取 F64 私有状态并通过可选方法探测
  决定加载、运行、输入/输出与证据路径。新增型号会迫使共同执行器继续加厂商分支。

这说明下一台信道仿真器的主要风险不是“再写一个 driver”，而是缺少 BaseStation 已经具备的
manifest → binding → execution plan/session → receipt → certification → adapter kit 完整接入合同。

## 3. 方案比较

### 方案 A：两个大 Epic

一个“CMW MAC 完善”、一个“多信道仿真器”。优点是标题简单；缺点是跨越 schema、HAL、执行、证据、
GUI 与现场认证，无法维持 WIP=1，也会把厂商命令与平台抽象混入同一 PR。拒绝。

### 方案 B：能力切片双队列（采用）

每片只有一个可观察故障与一个权威合同；非现场先建立可验证平台，现场半只验证真机语义。优点是
失败边界、手册取证和正式 KPI 门清晰，新厂商 PR 的改动面可被认证套件机械约束。代价是条目较多，
但顺序与依赖明确，适合本仓库的硬件安全和外审流程。

### 方案 C：等待下一台真机再抽象

短期零开发，但会在昂贵现场窗口里同时做协议取证、平台设计和 adapter 调试，复现 CMW500 接入期的
链路缝合。拒绝。

## 4. 不变量

1. 模拟、未知、部分确认与诊断数据不进入正式 KPI；不得由请求值、默认值或旧缓存回填。
2. 新增/修改仪器命令、参数域、返回枚举与物理单位必须有仓库原始厂商手册出处；查不到即 unavailable。
3. 写操作必须消费错误队列/拒绝/超时/取消；`*OPC?` 或函数返回成功不能单独证明生效。
4. 安全清理与 release 采用保守方向；未知状态不能跳过 stop/SAFE_IDLE。
5. 厂商 adapter 原则上不得修改 MEASURE、commissioning、Analysis、报告、下载、比较与历史；若必须，
   先登记独立平台缺口。
6. 现场复验与本地实现分别记状态；本地测试永不替代真机认证。

## 5. 交付与验收顺序

| 顺序 | 条目 | 主要交付 | 地点 |
|---|---|---|---|
| 1 | P1-74 | SFrames 统计基冻结、回读、窗口证据 | 非现场 + CMW 真机 |
| 2 | P1-75 | TestCase requirements × Adapter Manifest 首次 I/O 前兼容性硬门 | 非现场 |
| 3 | P2-64 | Adapter-scoped Mock 能力与注册身份 | 非现场 |
| 4 | P2-65 | Preview/Readiness/Freeze 共用兼容性判定 | 非现场 |
| 5 | P2-66 | 执行证据不变量与终态语义 | 非现场 |
| 6 | P2-67 | adapter-neutral 日志与 execution-scoped 导出 | 非现场 |
| 7 | P2-54 | RAT-neutral + NR/LTE discriminated MAC profile | 非现场 |
| 8 | P2-55 | CMW LTE FDD 组合能力矩阵 | 非现场 + CMW 抽样 |
| 9 | P2-56 | LTE TDD 配置、回读与站点认证 | 非现场 + CMW/DUT/SIM |
| 10 | P2-57 | Channel Emulator manifest/registry | 非现场 |
| 11 | P2-58 | 单一 binding、分型号 preset、同步/freeze 同 digest | 非现场 |
| 12 | P2-59 | execution-frozen plan 与单一会话 | 非现场 |
| 13 | P2-60 | 逐操作共同 receipt/evidence | 非现场 |
| 14 | P2-61 | Diagnostic/Formal site certification | 非现场 + 各型号现场 |
| 15 | P2-62 | 第三 adapter 参数化认证套件 | 非现场 |
| HOLD | P2-63 | 下一真实型号 adapter（队列末尾） | 手册到位后非现场 + 真机 |

各片启动前必须重新按 AGENTS.md 0.5 枚举该值/状态的全部产生方、消费方、入口、历史读取和失败路径；
此设计只规定边界与顺序，不代替每片的独立实施计划。
