# P1-51：删除仪表默认 IP 猜测并在缺配置时失败

## 可观察故障

真实驱动在未收到连接地址时会使用源码里的 `192.168.*` 或 `127.0.0.1`。这会把“未配置”
伪装成“仪表离线”，更危险的是可能连接到同网段内另一台设备。仪表 bootstrap 也会为新数据库
写入一组猜测地址，使上层看不到配置缺失。

## 全集

### 运行时地址消费者

- 信道仿真器：PROPSIM F64、FS16；
- 基站仿真器：UXM、CMW500；
- 转台：ETS EMCenter、Aerotech A3200；
- VNA：Keysight ENA、R&S ZNA；
- 信号源：Keysight MXG、R&S SMW200A；
- 信号分析仪：R&S FSW、FSVA、Keysight X-Series；
- 射频开关：ETSL switch；
- 工厂入口：`InstrumentHalService` 与 `DriverRegistry`；
- 新库目录：`services/bootstrap/instruments.py` 七类 connection seed。
- 人工诊断入口：仪表目录的连接测试、SCPI probe、单条 SCPI（Enter 与发送按钮）；它们必须与
  HAL 驱动读取同一份合并配置，不能让审计目标与实际命令目标分叉。

`PropsimF64Controller` 没有生产调用方，是旧兼容壳；本片仍删除它的默认 IP，避免未来调用复活猜测值。

### 地址真值源

按白名单读取显式配置：

1. `ip` / `controller_ip` / `ip_address`；
2. VISA `visa_resource` / `endpoint` 中的 host；
3. 普通 `host:port` endpoint 中的 host。

端口、传输协议和 HiSLIP index 是设备协议常量，不属于“猜测设备地址”，本片保留。

## 方案

1. 在 HAL 基类提供一个无副作用的地址解析函数，所有真实驱动复用；未配置时返回空串，不生成地址。
2. 在真实驱动 `connect()` 第一行调用统一 fail-closed 门：地址为空时设置 ERROR 与清晰原因并返回
   `False`，发生在 ResourceManager、socket、preflight 或 SCPI 之前。
3. 全部真实驱动消费同一个完整解析结果，而不是只拿 host 后重拼默认目标。UXM/CMW500 及
   PyVISA 驱动原样使用兼容的完整 TCPIP VISA resource；raw SOCKET 驱动消费显式端口。
   F64 的固定 3334、raw/INSTR/VXI-11 等协议约束遇到不兼容 endpoint 时在任何 I/O 前
   fail-loud。两个完整 VISA resource 还必须连同传输类型与 HiSLIP 子地址完全一致，禁止
   preflight、界面配置与 connect 指向不同仪表或 Test App。
4. `DriverRegistry` 的 auto 判据改读同一解析函数，只有显式地址存在才选择真实驱动。
5. bootstrap 的新 connection 行使用 `endpoint=None/controller_ip=None`，仍保留型号、协议与端口，提示
   操作员配置。既有 connection 行一律不改，避免清空真实现场地址。
6. 删除旧 F64 compatibility controller 的默认参数，调用者必须显式给地址。
7. 基站/信道仿真器是单会话控制类别：三个人工诊断入口禁止请求体临时覆盖地址，必须先保存配置并
   reload HAL，再复用活动会话。GUI 草稿与已保存 endpoint 不同时直接提示保存，保存成功后明确提示
   reload。后端在与 reload 共用的协调锁内、取得 Remote 前，重新读取最新持久化配置并确认它与
   请求开始时的完整快照一致，再用完整合并配置（含 `connection_params`、传输类型、VISA 子地址，
   以及影响 UXM Test App/HiSLIP 子地址的 `uxm_profile`）核对活动 driver 目标；任一变化或不一致
   即拒绝。UXM driver 与 validator 复用同一 protocol/profile 归一函数；单会话类别无活动 driver
   且没有显式数字端口或完整 resource 时不得猜 5025，直接要求保存完整配置并 reload。其他类别
   保留一次性覆盖能力。

## 状态与错误语义

- 已配置但网络不可达：仍由现有 preflight/connect 报网络或 SCPI 失败；
- 未配置：`connect()` 在外部 I/O 前返回 `False`，状态 `ERROR`，原因含仪器 ID 与“未配置连接地址”；
- 多个显式地址互相矛盾：仍选择真实驱动承载配置错误，但在外部 I/O 前返回 `False`，不得静默
  降级为 Mock，也不得选择其中任一地址尝试连接；所有真实驱动都保留并返回原始冲突、非法
  resource 或越界端口原因，不得把它折叠成“未配置连接地址”；
- Mock 驱动：不受本片影响；
- 历史数据库：不自动修改；新库不再生成猜测地址。

## 验收

1. 全部真实驱动以空配置 connect 时在任何外部连接动作前失败，且没有猜测地址；
2. `ip`、VISA endpoint、普通 `host:port` 三种显式配置能解析为同一 host；
3. 全部真实驱动消费兼容的显式端口/完整 TCPIP VISA resource；协议固定驱动对不兼容传输
   fail-loud。地址、端口及完整 VISA resource/HiSLIP 子地址冲突与空白值均在任何 I/O 前失败；
4. DriverRegistry auto 在无地址时选择 Mock，有显式 endpoint（包括无效或冲突配置）时选择 Real，
   由真实驱动 fail-loud，不把配置错误伪装成模拟模式；
5. fresh bootstrap 七类 connection 的地址均为空；已有连接再次 seed 后保持原值；
6. 全仓生产代码不再含真实驱动地址兜底。
7. 基站/信道仿真器的连接测试、SCPI probe 与单条 SCPI 在 GUI 草稿未保存时均不发请求；配置一致时
   请求不携带地址覆盖；后端在协调锁内、Remote I/O 前按 host、effective port、完整 resource、
   protocol 与 UXM profile 核对持久化合并目标和活动 driver 目标，未 reload 的旧会话必须
   fail-loud；无活动 driver 时不得为缺失端口生成 5025 fallback；有活动 driver 时审计记录该 driver
   真正使用的 effective port。其他类别仍可携带显式临时目标。
