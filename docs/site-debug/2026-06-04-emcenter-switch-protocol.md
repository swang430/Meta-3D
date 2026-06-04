# EMCenter / AMS8947 RF 开关控制协议调研 (P2-9 本地半)

> **日期**: 2026-06-04 | **Roadmap**: P2-9 (EMCenter switch bring-up) | **来源**: 2026-05-27 现场 raw socket 无响应
> **状态**: 本地半 (① 协议调研 + ② driver 协议修正 + 单测) ✅ done;现场半 (端口实测 / 卡型号 / SP6T 映射 / 接入) 🚧 blocked

## 背景

CAICT 暗室射频开关 **"TMC Beijing AMS8947-195-1"**。2026-05-27 现场用 raw TCP socket 直连
`192.168.0.50` 探测**无任何 SCPI 响应**,当时归类为"不吃 raw SCPI,可能必须经 EMQuest 软件"。
本次 offline 调研推翻了这个初判。

## 核心结论

1. **AMS8947-195-1 = ETS-Lindgren EMCenter 模块化机箱 + EMSwitch 插卡**。系统图标题直接印
   "ETS-Lindgren AMS8947",开关框标注 "Slot4 A/B/C"、"Slot5 A/B",与 EMCenter 的 slot/relay
   命名完全吻合。AMS8947 是 ETS 给这套暗室的**项目级系统总成型号**(机箱+卡+合路器+放大器+天线+
   定位器),不是单台开关的型号。
2. **EMCenter 原生支持远程 SCPI,不必经 EMQuest**。EMQuest / TILE! 是 ETS 可选上位软件;EMSwitch
   手册明确把"其他测试自动化软件"列为合法控制路径。系统图里的 "EMQuest NET Port" 是**物理接线盘
   标签**,不代表必须跑 EMQuest 软件。
3. **控制接口 = LAN(以太网)或 GPIB**。EMSwitch 手册安装步骤:"Connect the EMCenter to a computer
   using Ethernet or GPIB";处理器板 7000-008=ARM,7000-009=ARM+GPIB。(RS-232 仅用于机箱级联,
   不是上位机控制口。)
4. **现场无响应不是"不支持 SCPI",而是现有 driver 的协议格式 bug**(见下)+ 端口未知。

## 发现:EtslSwitchDriver 已存在但有协议 bug

`api-service/app/hal/rf_switch.py::EtslSwitchDriver` 早已存在并在 driver_registry 注册
(model "EMCenter Switch" → 它),但**没有任何协议层单测**,导致以下 bug 长期潜伏 —— 对照权威文档
**EMCenter SCPI Commands and Error Codes, Part #1801188 Rev A (2025-08)**:

| 项 | 旧 driver (bug) | 权威文档正解 | 影响 |
|----|----------------|-------------|------|
| 命令前缀 | `Write/Query <slot>:<cmd>` | **裸** `<slot>:<cmd>` | 文档表格里 Write/Query/Read 是**动作标签**不是协议;EMCenter 收到 `Write 1:...` 无法解析 → 无响应 |
| 终止符 | LF | **CR (0x0D)** | 文档 p5 "carriage return (CR) **must** terminate";严格设备收 LF 不回包 |
| 响应解析 | 硬剥 `Read ` 前缀 | 裸响应 (`NC` / `3`) | 同一误读;裸响应时无害但反映同源问题 |
| TCP 端口 | 默认 `2001`(来源不明) | 官方手册都不写 → SCPI 标准 `5025` | 修正: 默认 → 5025 + 串口 plan B(见 web 补充) |
| 协议单测 | **零** | — | bug 无人发现的根因 |

**前两条(Write/Query 前缀 + LF 终止符)极可能就是 2026-05-27 现场 raw socket 无响应的真因**
(即使端口对了,这两个格式错误也会让设备不回包)。旧 driver 注释自己承认是猜测:
"ETS-L typically accepts Write or Query prefix... might also work"。权威 RevA 文档(2025-08,
现场当时没有)证实命令是裸 `<slot>:<cmd>` + CR。

## 修正 (本 PR)

`EtslSwitchDriver` 改为**默认按权威文档 + 可配置回退**(现场只调配置不改代码,同 P0-8 哲学):

- **命令格式**: 默认裸 `<slot>:<cmd>`;`command_style="verbose"` 可回退旧 Write/Query 包装(逃生)。
- **终止符**: 默认 CR;`line_terminator="lf"|"crlf"` 可切(逃生)。
- **响应解析**: 统一 `_parse_response`(去终止符,容错剥 `Read ` 前缀)。
- **端口**: 默认 `5025`(SCPI 行业标准 raw-socket 端口, 有依据 —— 见下方 web 调研补充), 真实值由 binding `connection_params.port` 提供。
- **reset_paths SP6T 安全**: mapping 标 `relay_type="sp6t"` 的项跳过复位(不发非法 `_NC`),仅 warning;
  SP6T 复位语义待现场确认。
- **单测**: `tests/test_etsl_switch_protocol.py` 18 例,断言命令字节流 = 裸+CR、响应解析、逃生开关、
  SP6T 跳过、端口配置。

## EMCenter SCPI 命令集 (set_route / get_route 用)

命令格式 `<slot>[<port字母>]:<COMMAND>` + **CR 终止**;`<slot>`=1-7(双槽卡用靠前槽号)。

| 用途 | 命令 | 说明 |
|------|------|------|
| 识别 | `<slot>:*IDN?` | 返回 `ETS-Lindgren, EMSwitch 7001-003, 4.3.3`(认卡型号) |
| 系统版本 | `*IDN?` / `VERSION_SW?` | 无前缀=机箱系统 |
| SPDT 设 | `<slot>:INT_RELAY_<A-D>_[NC\|NO]` | 例 `4:INT_RELAY_A_NO` |
| SPDT 读 | `<slot>:INT_RELAY_<A-D>?` | → `NC` / `NO` |
| SP6T 设 | `<slot>:INT_RELAY_<A\|B>_<1-6>` | 例 `5:INT_RELAY_A_4` |
| SP6T 读 | `<slot>:INT_RELAY_<A\|B>?` | → 1-6(0=全开) |
| 外部继电器 设 | `<slot>:EXT_RELAY_<A\|B>_<0-6>` | 0=无输出 |
| 外部供电压 | `<slot>:EXT_VOLTAGE?` / `_<12\|24\|28>` | |
| 级联远程继电器 | `N<box><relay>RELAY_<sw>_<pos>` | 例 `N12RELAY_2_4` |
| 互锁 | `INTLK? SAFETYRELAY` | 0 正常 / 1 互锁(Relay A 被硬件锁,软件无法覆盖) |
| 复位/清错 | `RESET` / `CLEAR` / `REBOOT SYSTEM` | |

> ⚠️ 同名 `INT_RELAY_<R>` 命令对 SPDT 卡(值域 NC/NO)和 SP6T 卡(值域 1-6)语义不同 ——
> **从命令名无法区分卡类型**,driver 的 mapping 需用 `relay_type` 显式标注。

## 物理拓扑 (AMS8947-195-1 系统图)

- **SISO 页**(可切换开关网,driver 主要控制对象):
  - **Slot4 = 多路 SPDT**(A/B/C 三个继电器,疑似 7001-002 4×SPDT):RF1/RF3/NR-TIS 源 → SPDT。
  - **Slot5 = 2×SP6T**(A/B,疑似 7001-003,占 Slot5+6):汇聚到 AMS8900 定位器 Theta/Phi 探头 +
    3102 喇叭天线。
  - 中间一个无源**合路器**(带内部端接)。
  - 角色:把测量仪表源灵活路由到暗室探头/天线(TRP/TIS/Passive 单天线测量)。
- **MIMO 页**(基本固定布线,非可切换):UXM P1-P4 → 功放 A1-A4 → 接线盘 → 32 条 RF 路径到
  **16 个双极化探头**(1V/1H...16V/16H),分 Vertex1/Vertex2 两套。端口标 `S<slot> P<port>`,
  再次印证 EMCenter slot/port 寻址。

`set_route` 设计:driver 内建"逻辑路由 → (哪些 slot/relay 拨到哪态)"映射表,照系统图标定;
切换后 `<slot>:INT_RELAY_<R>?` 回读确认 + `STATUS?` 查无错。

## 现场半 runbook (下次现场,按 SCPI 探测优先)

1. **核对地址/端口**: 机箱触摸屏 Info/Settings 界面看真实 IP 是否 `.50`、有无端口配置项。
2. **定端口**(官方手册都不写,见下方 web 调研补充):
   - 试序: **5025**(SCPI 标准 raw-socket, driver 默认)→ 5024(SCPI-telnet)→ 23(telnet)。改 `connection_params.port` 逐个试, 先发无前缀 `*IDN?`+CR 探机箱有无命。
   - 都不通 → **串口 plan B**: 现场跑 `tcp_serial_redirect`(RS-232 9600 8N1 → 本地 TCP), driver 连该 TCP 口(不用加 pyserial)。
3. **确认协议格式**: 默认 `command_style=raw` + `line_terminator=cr`。若无响应,逐一试
   `line_terminator=lf/crlf`、`command_style=verbose`(逃生开关,不用改代码)。
4. **认卡**: `4:*IDN?` / `5:*IDN?` 确认每槽实际插的卡型号(SPDT vs SP6T)。
5. **标定 SP6T 映射**: SP6T 位置 1-6 ↔ 物理天线/探头的对应,实拨 + 看链路验证,填进 driver mapping
   (含 `relay_type`)。
6. **确认 SP6T 复位语义**: set 0 是否合法 / 安全位是哪个(本 PR 暂跳过 SP6T 复位)。
7. **接入 TopologyEditor**(P2-9 ③): 把标定好的 mapping 接进拓扑 mapping/连线编辑。

## 缺口清单 (现场或向 ETS 补)

| 缺口 | 来源 | 备注 |
|------|------|------|
| TCP 端口号 | 现场实测(5025 首选)/ 触摸屏 | 官方手册都不写; 5025 是 SCPI 标准首选, 有串口 plan B 兜底, 非阻塞 |
| 每槽实际卡型号 | 现场 `<slot>:*IDN?` | Slot4=? Slot5=? |
| SP6T 位置↔天线映射 | 现场实拨 | set_route 映射表依赖它 |
| SP6T 复位安全位 | 现场 | reset_paths SP6T 分支待实现 |
| "195 / -1" 型号编码含义 | 向 ETS 确认 | 不影响 driver,配置文档要写对 |
| MIMO 页是否含可切换继电器 | 现场 | 决定要不要给 16 探头也写 set_route |

## 2026-06-04 web 调研补充 (端口确认 + 串口 plan B)

初版 (#130) 留"端口三份在仓文档都没有, 只能现场试"。用户追问"还是只能现场试?" 后做 web 调研, 把不确定性大幅收敛:

1. **挖到主手册 399342 Rev B** (archive.org 公开, 即初版说"未到手"那份): Configuration Screen (p31) 确认 EMCenter 有 IP 配置 (示例 192.168.8.253 / Gateway 192.168.8.1, 触摸屏可改); Remote Control (p33) **二次印证 CR 终止** (原文 "Terminate each command with a carriage return (CR)"); 错误码表 (p36)。**但连主手册都不写 LAN 的 TCP 端口号** —— ETS 系统性不文档化, 留给 VISA / 标准约定。

2. **端口候选收敛 + 纠错**: 初版 agent 推断的 **9221 是错的** (那是 Prologix GPIB-网口适配器端口, 跟 EMCenter 无关)。按 SCPI 行业标准, raw-socket 标准端口是 **5025** (IANA / Keysight 标准化); EMCenter 命令是裸 SCPI 风格, 所以 **5025 是有依据的首选** (driver 默认已从 2001 改 5025)。试序 5025 → 5024 (SCPI-telnet) → 23。

3. **串口 9600 8N1 是已验证 plan B**: 开源 klingm/EMCenter-Controller 实测走 EMCenter RS-232 (9600 8N1), 经 `tcp_serial_redirect` (本地 TCP) 桥接。**现有 TCP driver 不用加 pyserial** —— 现场跑 redirect 脚本, driver 连它的本地 TCP 口即可。注: klingm 用 LF 终止 (串口路径容忍), 跟主手册的 CR 不冲突 (正是 driver `line_terminator` 可配的价值)。

4. **错误码表** (主手册 p36, 可补进 driver 解析): ERROR 1 buffer overflow / 2 command too long / 3 invalid command / 4 too short / 5 invalid param / 6 param too high / 7 too low / 8 hardware failure / 20 unknown device type / 21 unknown device number。

**结论**: LAN 端口的确切数字仍需现场确认 (官方系统性不写), 但已从"盲试"变成"有依据的优先试序 (5025 首选) + 串口 plan B 兜底"。

## 参考文档

- **写 driver 主参考**: `Instrument_API_Doc/ETS-L EMCenter/EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf`
  (命令语法 p5、EMSwitch 全命令 p8-14、错误码 p83)
- 系统接线图: `Instrument_API_Doc/CAICT Chamber Switch/TMC Beijing AMS8947-195-1 system diagram V3.0(1).pdf`
- EMSwitch 卡手册: `Instrument_API_Doc/ETS-L EMSwitch/399343-EMSwitch-Rev-K.pdf`(卡型号表 p7)
- 主手册 399342 Rev B(archive.org 公开): https://ia601800.us.archive.org/9/items/manualzilla-id-5822155/5822155.pdf —— Configuration Screen (p31, IP 配置) + Remote Control (p33, CR 二次印证) + 错误码 (p36); **但 LAN 端口号它也不写**
- 开源参考: https://github.com/klingm/EMCenter-Controller —— 实测走 RS-232 9600 8N1 经 tcp_serial_redirect 桥 TCP
- SCPI 标准端口 5025: 行业约定 (IANA / Keysight 标准化 raw-socket 口)
- 现场背景: [`2026-05-27-morning-log.md`](2026-05-27-morning-log.md) §10.1
