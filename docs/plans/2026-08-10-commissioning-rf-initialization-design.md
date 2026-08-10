# 暗室首测 RF 冷启动初始化设计

> 状态：2026-08-10 用户批准，立即进入当前开发。

## 可观察故障

2026-08-07 的现场 execution 在 UXM 报告 DUT attach 成功后，才开始加载 F64 `.smu`
并设置 F64 中心频率。attach 因而依赖 F64 先前遗留的 `STOPPED + STATIC 2` 和
3549.99 MHz 状态，不能证明本次会话建立了正确的 F64 初始态。冷启动、换场景或现场
有人改过仪器时，这条链不可重复。

## 目标

“暗室首测”必须在第一次 DUT attach 之前，由当前 TestExecution 建立并核对完整 RF
初始态：

1. 解析本次信道资产或显式 `.smu`；
2. 加载 F64 模型并设置/回读中心频率；
3. 按显式参数设置 F64 输入参考、crest 和输出电平；
4. 建立 attach 所需的直通状态并回读 `STATE`/`STATIC`；
5. 设置并回读 UXM ARFCN、带宽和功率；
6. 之后才允许 `start_signaling()` 等待 DUT attach；
7. attach 后若为直通辅助模式，执行 `STATIC 0 + GO`，确认 `RUNNING` 并复核 DUT 仍连接；
8. 全部关键往返归入同一个 TestExecution。

## 方案选择

采用独立的“RF 初始化”编排，而不是继续在现有 measure 函数中复制一段 F64 动作。

- 只移动 `set_passthrough_mode`：改动小，但仍依赖预加载 `.smu`，不能解决冷启动。
- 新增独立初始化编排（采用）：把模型加载、频率、工作点和 attach 状态作为一个事务，
  可被暗室首测和正式 TestCase 共用，失败即停止。
- 保留外部预置：现场最快，但无法审计，不满足商用可重复性要求。

## 带宽语义

不新增任何未经厂商手册证明的 F64 带宽 SCPI。`SYST:INFO?` 中的
`Bandwidth:100.000MHz` 是系统能力/许可信息，不是当前 `.smu` 的仿真带宽。

- UXM 的 40 MHz 必须由本次执行下发并回读；
- F64 仿真带宽来自已登记的 ChannelAsset/SCD 或经核验的 `.smu` 元数据；
- 没有可信资产元数据时，F64 带宽保持 `unknown`，不得硬编码成 100 MHz，也不得假绿；
- F64 中心频率继续用 `CALC:FILT:CENT:CH?` 的实时回读闭环。

## 暗室首测界面

会话创建前显式显示并提交：中心频率、UXM 带宽/功率、信道引擎、信道资产或 `.smu`、
F64 输入参考、crest、输出电平，以及是否用 Butler 直通辅助 attach。现场基线可预填，
但必须作为本次请求数据保存，不能靠共享 schema 默认或仪器残留状态。

## 失败策略

任何模型加载、中心频率核对、输入/输出工作点设置、直通建立、UXM APPLY/回读失败，
都在 attach 前 fail-loud。不得退回旧仪器状态继续测试。未知的 F64 仿真带宽允许作为
显式 `unknown` 留痕，但正式 P0-5 证据门不能因此变绿。

## 测试与验收

- 行为测试证明 `F64 load/configure → bypass → UXM start_signaling` 的严格顺序；
- 冷启动 F64（无预加载模型）不再依赖遗留状态；
- F64 初始化失败时 `start_signaling` 从未调用；
- `get_frequency_identity()` 不再把硬件 100 MHz 能力冒充当前仿真带宽；
- 暗室首测 GUI 请求包含现场工作点与信道选择；
- 既有正式 TestCase、直通基线和默认非直通路径保持兼容；
- 本地 mock 回归、后端针对性测试和前端构建通过后，现场只需进行同次 execution 复验。
