# FS16 现场调试工作进展总结

日期：2026-06-12
项目：Meta-3D 传导测试准备
主题：软件控制 Keysight PROPSIM FS16 加载并回放 `.smu` 文件

## 1. 今日最终结论

今天已经打通了软件控制真实 FS16 进行 `.smu` 回放的核心流程。

当前已经确认：

- 软件可以连接真实 FS16。
- 软件可以让 FS16 打开 `Emulation0609.smu`。
- FS16 可以进入 emulation / playback 相关页面。
- GUI 已加入 FS16 回放控制按钮：暂停、继续、停止回起点、关闭 emulation 界面。
- 当前 KPI 摘要仍然是 mock 数据，只用于验证软件流程，不代表真实射频通信性能。

一句话总结：

> 今天完成的是 **FS16 real 控制链路打通**，不是完整真实传导通信性能测试。

## 2. 当前系统边界

当前工作模式是：

| 模块 | 当前模式 | 说明 |
|---|---|---|
| FS16 / channelEmulator | real | 真实仪表，软件已能控制加载和回放 `.smu` |
| baseStation | mock | 目前没有真实基站仿真器接入 |
| DUT / 终端 | mock | 目前没有真实终端 attach 和真实业务流 |
| KPI 指标 | mock | 仅用于验证软件执行链路和结果卡展示 |

需要特别注意：

- GUI 里看到的 `DL/UL throughput`、`BLER`、`CQI`、`Rank Indicator`、`MCS`、`RSRP`、`SINR` 都是 mock 指标。
- 这些指标不是 FS16 测出来的，也不是真实终端回传的。
- 它们不能作为真实传导测试结论。

## 3. 已完成工作

### 3.1 FS16 控制链路

已完成软件到 FS16 的控制链路验证：

1. 软件连接 `channelEmulator`。
2. 软件校验 playback 文件。
3. 软件发送 FS16 `.smu` 打开命令。
4. FS16 UI 进入 emulation 页面。
5. FS16 日志显示 `Opening emulation completed`。

现场观察说明：软件端已经能真实影响 FS16 状态，不再只是 mock 流程。

### 3.2 `.smu` 文件依赖确认

现场确认了一个关键现象：

- 单独移动一个 `.smu` 文件到其他目录后，FS16 UI 导入会报文件不可用。
- 说明 `.smu` 文件不是完全独立的单文件，生成时的一组关联文件也会参与回放打开过程。

当前处理方式：

- 已将 `Emulation0609.smu` 以及生成时关联的一组文件放到：

```text
D:\User Playbacks
```

后续现场操作时，不建议只拷贝单个 `.smu` 文件。

## 4. SCPI 指令确认

今天确认并使用的 FS16 回放控制指令如下：

| 动作 | SCPI 指令 | GUI 对应按钮 / 流程 |
|---|---|---|
| 加载 `.smu` | `CALC:FILT:FILE <file>` | 运行序列中自动执行 |
| 开始回放 | `DIAG:SIMU:GO` | 运行序列中自动执行 |
| 暂停回放 | `DIAG:SIMU:STOP` | `暂停` |
| 继续回放 | `DIAG:SIMU:CONT` | `继续` |
| 停止并回到起点 | `DIAG:SIMU:GOS` | `停止回起点` |
| 关闭 emulation 界面 | `DIAG:SIMU:CLOSE` | `关闭界面` |
| 查询回放状态 | `DIAG:SIMU:STATE?` | 控制按钮发送后自动查询 |

其中 `DIAG:SIMU:CLOSE` 是今天最后新增的控制项，用于解决跑完后 FS16 UI 停留在 emulation 页面的问题。

## 5. 软件端改动

### 5.1 后端 / HAL

已完成：

- FS16 playback load 默认命令改为：

```text
CALC:FILT:FILE {path}
```

- 修正了 FS16 已经成功打开 `.smu`，但软件误报 `load failed: 1` 的问题。
- 对 stale `*OPC?` 响应做了兼容处理，避免把裸 `1` 当成真正错误。

### 5.2 诊断序列

已保留并使用 hybrid smoke 结构：

```text
fs16_hybrid_kpi_smoke
```

该序列的定位是：

- FS16 使用 real。
- baseStation 当前使用 mock。
- DUT / KPI 当前使用 mock。
- 后续接真实基站仿真器后，同一骨架可以继续复用。

重要设计原则：

- real / mock 模式不在后端写死。
- 模式应由 GUI / HAL 配置决定。
- 当前让 baseStation 和 DUT mock，只是因为今天现场没有真实基站仿真器和真实 DUT。

### 5.3 前端 GUI

已完成：

- 优化参数布局：
  - `.smu` 文件输入栏单独一行。
  - 开关选项单独一行。
  - 运行参数集中展示。
  - 参数说明改为中文简短定义。
- 新增 FS16 回放控制按钮：
  - 暂停
  - 继续
  - 停止回起点
  - 关闭界面
- 控制按钮统一通过现有接口发送 SCPI：

```text
/api/v1/instruments/channelEmulator/scpi-command
```

这样不会绕过当前 HAL 和 GUI 的仪器配置。

## 6. 当前已验证项

| 验证项 | 结果 | 说明 |
|---|---|---|
| 软件连接 FS16 | 通过 | 可连接真实 channelEmulator |
| `.smu` 文件可见性检查 | 通过 | `Emulation0609.smu` 可被软件端找到 |
| `.smu` 打开流程 | 通过 | FS16 UI 显示打开完成 |
| 软件误报 `load failed: 1` | 已处理 | 属于响应读取/判定问题 |
| GUI 参数显示 | 已优化 | 现场输入不再拥挤 |
| GUI 暂停/继续/停止/关闭按钮 | 已加入 | 尚需现场逐个按钮实测 |
| KPI 展示 | 流程可用 | 但指标来源仍是 mock |

## 7. 尚未完成 / 不能误判的部分

今天尚未完成真实传导通信性能测试。

原因：

- 没有真实基站仿真器接入 FS16。
- 没有真实 DUT / 终端 attach。
- 没有真实业务流。
- 没有真实 KPI 来源。

因此当前不能得出：

- 真实 DL throughput。
- 真实 UL throughput。
- 真实 BLER。
- 真实 RSRP / SINR。
- 真实 CQI / MCS / Rank Indicator。

当前只能得出：

> 软件已经具备控制 FS16 加载并回放指定 `.smu` 文件的能力。

## 8. 下一步现场计划

### P0：继续验证 FS16 控制按钮

在 FS16 已打开 emulation 后，逐个验证：

1. `暂停`
2. `继续`
3. `停止回起点`
4. `关闭界面`

验收标准：

- FS16 UI 状态变化与按钮动作一致。
- 软件通知中的 `DIAG:SIMU:STATE?` 状态可读。
- 不出现误报失败。

### P0：固定 playback 文件管理方式

建议现场统一使用：

```text
D:\User Playbacks\Emulation0609.smu
```

并保持关联文件同目录。

不要只迁移单个 `.smu` 文件。

### P1：准备接入真实基站仿真器

接入真实基站仿真器前，需要确认：

- GUI 仪器资源中 `baseStation` driver mode 可切换为 real。
- 后端没有把 baseStation 写死为 mock。
- baseStation endpoint、频段、带宽、功率、同步方式、射频链路连接关系明确。

### P1：真实传导测试时切换策略

后续真实传导测试路线：

1. 前端将 `channelEmulator` 保持为 FS16 real。
2. 前端将 `baseStation` 从 mock 切为 real。
3. 配置真实 baseStation endpoint。
4. HAL reload。
5. 序列参数中将 `base_station_mode` 从 mock 改为 real。
6. 接入真实 DUT / 终端。
7. 将 KPI 来源从 mock 替换为真实仪表或终端数据。

## 9. 今日结论归档

今天的工作价值主要在于：

- 证明软件控制 FS16 的链路已经可用。
- 明确了 `.smu` 文件依赖关联文件，不能只看单个文件。
- 修正了 FS16 打开成功但软件误判失败的问题。
- 增强了 GUI 的现场控制能力。
- 明确划清了 mock KPI 与真实通信性能之间的边界。

下一阶段重点应从“软件能不能控 FS16”转向：

> “真实基站信号如何进入 FS16，并由真实 DUT 产生可追溯的真实 KPI。”
