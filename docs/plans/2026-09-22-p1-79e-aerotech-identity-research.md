# P1-79E：Aerotech 活跃身份查询取证裁决

**日期**：2026-09-22。**性质**：厂商资料、现有协议实现与正式证据链核对；本次没有连接、查询或写入真实转台。

## 1. 裁决

当前 CAICT Aerotech 的活跃控制路径是 AeroBasic/TCP；当前取得的厂商资料包为 Ensemble 3.04，但它仍没有足够厂商证据支持“安全只读地取得现场控制器型号与固件版本”。现场控制器的实际型号和固件版本本身仍是未知，不能由资料包版本反推。因此 P1-79E **不能进入 HAL 实现**，`RealAerotechDriver.capture_evidence_environment()` 继续把 `model` / `firmware_version` 保持为 `None`，`positioner.azimuth.NNN` 的正式判词继续 fail-closed 为 `unknown`。

这不是“没有任何 Aerotech API 能显示身份”。厂商资料能证明：

- Ensemble Windows SDK 有基于已连接 controller handle 的 controller information API：C API 可读 `EnsembleInformationGetName()`，.NET API 还可读 `controller.Information.Version.FirmwareVersion` 与 `controller.Information.MasterType`；
- 新一代 Automation1 有 `ControllerGetName()`、`ControllerGetSerialNumber()`、`ControllerGetVersion()`；
- Aerotech 的迁移表提到旧 AeroBasic `DRIVEINFO` 被 Automation1 `DriveGetItem()` 替代。

但三者都不能直接证明现场生产进程当前使用的 **raw TCP port 8000** 可以发送哪一条命令、命令是否覆盖现场尚未确认的控制器型号/固件版本、参数枚举是什么、返回值如何解释，以及读取是否不改变控制器状态。把 SDK 调用、Automation1 函数或仅有名字的 `DRIVEINFO` 拼成生产命令，会违反“同一协议、同一型号/版本、可核对返回语义”的硬件证据边界。

## 2. 厂商证据与不成立的迁移

| 证据 | 能证明什么 | 不能证明什么 | 本片裁决 |
|---|---|---|---|
| 仓内 `Aerotech_Ensemble_ASCII_TCP转台控制集成说明.docx` 与当前驱动 | port 8000 的 AeroBasic ASCII framing、ACK/NAK，以及已使用的运动/反馈命令 | 型号、控制器名或固件版本查询 | 继续作为运动协议来源，不扩写身份命令 |
| 本机现有的 Ensemble 3.04 Help / 官方 ASCII 样例（用户仪器资料，不纳入本 PR） | ASCII 接口可执行 AeroBasic 命令并读取状态/参数；官方样例覆盖 `PFBK`、状态与 `GETPARM` | 全文未给可核对的 controller model / firmware ASCII recipe；本次全文检索 `DRIVEINFO` 为 0 命中 | 不从样例外推命令 |
| Ensemble C SDK `Information.h` / .NET 官方参考与样例 | C API 的 `EnsembleInformationGetName(handle, ...)` 可读 controller name；.NET 的 `controller.Information.Version.FirmwareVersion` 明确返回 controller firmware version，`controller.Information.MasterType` 返回 controller component type | 这些不是 raw ASCII/TCP 命令；当前 macOS API 服务不能直接加载 Windows SDK；`MasterType` 到正式 evidence catalog 所需确切 `model` 的厂商映射与现场同设备绑定仍未建立 | 记录 SDK 可读的 live firmware/component type，但不把 SDK 安装版本、controller name 或未映射的 `MasterType` 冒充现场设备型号 |
| Aerotech [Configure the ASCII Command Interface](https://knowledgebase.aerotech.com/spaces/AKB/pages/58524063/Configure%2Bthe%2BASCII%2BCommand%2BInterface) | A3200/Ensemble/Soloist 的 ASCII 接口、端口与服务端配置边界 | 未给身份查询命令 | 只证明传输入口，不证明身份语义 |
| Aerotech [AeroScript Equivalents of AeroBasic Commands for Ensemble/Soloist](https://help.aerotech.com/automation1/Content/AeroScript-Equivalents-of-AeroBasic-Ens-Sol.htm) | `DRIVEINFO` 这个旧命令名存在，迁移到 `DriveGetItem()` | 未给当前取得的 Ensemble 3.04 资料所需的语法、item 枚举、返回格式和支持版本；也没有证明它返回 controller model / controller firmware | 命令名本身不足以进入生产代码 |
| Aerotech [Controller Information Functions](https://help.aerotech.com/automation1/Content/Concepts/Controller-Information-Functions.htm) | Automation1 的 `ControllerGetName/SerialNumber/Version()` 及版本返回格式 | Automation1 是另一代控制平台；页面没有声明这些函数可由现场 Ensemble AeroBasic/TCP 使用 | 禁止跨平台移植 |
| Aerotech [A3200 C Library Getting Started Guide](https://knowledgebase.aerotech.com/download/attachments/3211553/A3200%20C%20Library%20Getting%20Started%20Guide.pdf?api=v2&modificationDate=1536846143706&version=1) 的 `DRIVEINFO(X, DRIVEINFO_AmplifierTemperature)` 示例 | A3200 某版本可执行一个 drive-level 查询 | 示例字段是放大器温度，不是 controller model / firmware；文档面向 A3200，而现场控制器的型号/版本正是未知 | 不能据类比创造 `DRIVEINFO_*` identity token |

这里的“检索未命中”只裁决**当前取得的资料不足**，不声称所有 Aerotech 产品/版本永远没有身份能力。若厂商后续提供覆盖现场 Ensemble 控制器的正式 recipe，应重新立项核对。

## 3. 当前软件为何必须保持 `unknown`

正式位置证据的实际链路是：

1. `RealAerotechDriver.capture_evidence_environment()` 从活跃 `_reader/_writer` 和 HAL 状态判定是否 live；
2. `build_p0_5_position_evidence()` 把该 `InstrumentEnvironment` 交给 `scope_for_evidence()`；
3. scope 缺 `model` 或 `firmware_version` 时，角度交换即使真实、误差即使为 0.0°，也不能升级为正式 mandatory evidence；
4. P2-66 outcome、报告与历史页面只消费这个冻结判词，不从数据库 connection config 或当前仪器目录回填身份。

这条 fail-closed 路径正是在防止“配置写着 A3200，所以把任何响应它的 8000 端口都认成目标转台”。删除型号/固件门、用 IP/端口或 configured model 代替 live identity，都会把错误设备或版本漂移洗成正式位置证据。

## 4. 解除阻塞的两个可审出口

### 出口 A：同一 AeroBasic/TCP 协议的厂商 recipe（优先）

厂商资料必须同时给出：

- 覆盖现场 Ensemble 控制器的确切型号和固件版本（二者当前均未确认）；
- 完整命令字面量、参数枚举、返回字段/格式；
- 明确是只读查询，不触发 reset、program execution、参数写入或轴状态变化；
- 型号与固件分别来自哪个返回字段，空值/NAK/版本不支持时如何判定；
- 允许在当前 ASCII command interface / TCP server session 上执行。

满足后另开小片，严格 TDD 接入 connect-time identity capture；查询拒绝、空回、解析失败、重连或断开都必须清空缓存并保持 `unknown`，不能回退 configured model。

### 出口 B：Windows SDK 身份采集（需独立架构批准）

若厂商确认 Ensemble 只能通过 Windows SDK 取身份，需要一个与 API 服务分离、部署在受支持 Windows 主机上的受控采集器。它至少要解决同一设备绑定、认证、时间新鲜度、重连/漂移、传输安全和 execution freeze。.NET SDK 已有 live `FirmwareVersion` 来源，但 controller name 不等同于硬件 model，`MasterType` 到 evidence catalog 所需确切 model 的厂商映射仍须核实。这已是新子系统，不属于 P1-79E 的最小修复，不能在当前驱动里顺手加一个配置字段替代。

设备迁移/升级到 Automation1 是实验室硬件决策，也不能作为软件默认假设。

## 5. 验证与状态

本片没有修改生产代码、schema、命令或 provenance 白名单。验证目标是：

- 现有真实驱动在没有已佐证身份查询时仍只发布 live connection，型号与固件保持空；
- 正式位置证据仍因缺 live model/firmware 而 `unknown`；
- roadmap 不再把“Automation1/SDK 有身份 API”误写成“P1-79E 可本地实现”。

P1-79E 状态为 **Hardware/Vendor-Protocol Blocked**，同时仍是 P0-5 正式验收前置。它不是软件已完成，也不能由本地测试、配置声明或诊断成功替代。
