# .smu 测试固件

Keysight PROPSIM Channel Studio 工程文件（INI 文本）的真实样本。

## `New GCM Model 5.smu`

**来源**：厂商资料 `Propsim资料/New GCM Model 5.gcm/`，用户 2026-09-03 提供，未脱敏（用户明示不需要）。

**形态**：2×2 双向实验室模型 —— `ClosedRoute = true`，两个 channel group（DL/UL），
**4 输入 / 4 输出 / 8 通道**。对应 `MODEL:INFO?` 会回 `4,8,4`。

⚠️ **它不代表 OTA 形态。** CAICT 现场的 OTA 模型是 `MODEL:INFO?='4,128,32'`
（4 输入 / 32 输出 / 128 通道，见 `app/hal/propsim_f64.py` 顶部注释）。
拿这一份样本推断「.smu 的节结构不变量」是不成立的 —— 要做解析器，
**OTA 形态的样本必须另外拿一份**。

## 这份文件里能拿到什么（离线，零仪器 I/O）

| 事实 | 出处 |
|---|---|
| 输入 / 输出 / 通道**数** | `[Input N]` / `[Output N]` / `[Channel N]` 节的**个数**（不是某个键） |
| **物理连接器号** | 每个 `[Input N]` / `[Output N]` 的 `Connector`（本样本输出是 `COMMON 3,4,1,2` —— **不是 1,2,3,4**） |
| 通道路由矩阵 | `[Channel N]` 的 `Input=` / `Output=` |
| 每口电平 / 波峰因子 / 增益 | `AvgInputLevel` / `CrestFactor` / `[Output N] Gain` |
| 中心频率 | `[Channel Group N] CenterFrequency`（`app/hal/smu_project.py` 已在解析这一项） |
| 天线配置 | `[Device N] TXAntennas` / `RXAntennas` |

## ⚠️ 解析陷阱：`Direction` 与 `Group name` 相反

```ini
[Channel Group 0]
Direction = UPLINK        ← 键写 UPLINK
Group name = Downlink     ← 名字叫 Downlink
```

而 `[Link 0]` 声明 `ChannelGroup = 0`、`TXDevice = 0`(Base station) → `RXDevice = 1`(Mobile station)，
**功能上它就是下行**。按 `Direction` 判 DL/UL 会全判反。

`Direction` 的真实语义属**厂商语义**，裁决权在手册不在这份文件 ——
真要消费它，先查 PROPSIM NotebookLM（见 CLAUDE.md「必查 NotebookLM」一节）。本仓当前**不消费**该键。
