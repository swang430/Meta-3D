# 虚拟路测产品 - 架构设计详解

## 目录

- [1. 整体架构](#1-整体架构)
- [2. 统一测试抽象层](#2-统一测试抽象层)
- [3. 数字孪生引擎](#3-数字孪生引擎)
- [4. 传导测试架构](#4-传导测试架构)
- [5. OTA测试架构](#5-ota测试架构)
- [6. 数据模型](#6-数据模型)
- [7. API设计](#7-api设计)
- [8. 前端架构](#8-前端架构)

---

## 1. 整体架构

### 1.1 系统分层架构

```mermaid
graph TB
    subgraph "前端层 - React GUI"
        UI1[模式选择器]
        UI2[场景库]
        UI3[场景编辑器]
        UI4[拓扑配置器]
        UI5[实时监控]
        UI6[结果分析]
    end

    subgraph "服务编排层 - Backend Services"
        SVC1[测试计划管理]
        SVC2[执行引擎]
        SVC3[模式切换器]
        SVC4[资源调度]
        SVC5[数据采集]
    end

    subgraph "执行器层 - Test Executors"
        EXE1[数字孪生执行器<br/>DigitalTwinExecutor]
        EXE2[传导测试执行器<br/>ConductedExecutor]
        EXE3[OTA执行器<br/>OTAExecutor]
    end

    subgraph "基础设施层"
        INF1[算力平台<br/>GPU/CPU]
        INF2[射频硬件<br/>仪表+DUT]
        INF3[MPAC暗室<br/>32探头+转台]
    end

    UI1 & UI2 & UI3 & UI4 & UI5 & UI6 --> SVC1 & SVC2 & SVC3 & SVC4 & SVC5
    SVC2 --> EXE1 & EXE2 & EXE3
    EXE1 --> INF1
    EXE2 --> INF2
    EXE3 --> INF3

    style EXE1 fill:#e1f5ff
    style EXE2 fill:#e8f5e9
    style EXE3 fill:#fff3e0
```

### 1.2 三种测试模式架构对比

```mermaid
graph LR
    subgraph "模式1: 全数字仿真"
        DT1[网络仿真器]
        DT2[信道仿真器]
        DT3[DUT仿真器]
        DT4[场景引擎]
        DT5[算力平台]

        DT4 --> DT1 & DT2 & DT3
        DT1 & DT2 & DT3 --> DT5
    end

    subgraph "模式2: 传导测试"
        CT1[基站仿真器<br/>CMX500]
        CT2[信道仿真器<br/>PropsIM F64]
        CT3[DUT真机]
        CT4[拓扑管理器]

        CT1 -->|RF线缆| CT2
        CT2 -->|RF线缆| CT3
        CT4 -.控制.-> CT1 & CT2 & CT3
    end

    subgraph "模式3: OTA辐射测试"
        OTA1[基站仿真器]
        OTA2[信道仿真器]
        OTA3[功放阵列]
        OTA4[32探头MPAC]
        OTA5[DUT车辆]
        OTA6[转台]

        OTA1 --> OTA2
        OTA2 --> OTA3
        OTA3 --> OTA4
        OTA4 -.空间辐射.-> OTA5
        OTA6 -.旋转.-> OTA5
    end

    style DT5 fill:#e1f5ff
    style CT3 fill:#e8f5e9
    style OTA5 fill:#fff3e0
```

---

## 2. 统一测试抽象层

### 2.1 ITestExecutor 接口设计

```mermaid
classDiagram
    class ITestExecutor {
        <<interface>>
        +initialize(config: TestConfig) Promise~TestResult~
        +validate() Promise~ValidationResult~
        +execute() Promise~ExecutionHandle~
        +pause() Promise~void~
        +resume() Promise~void~
        +stop() Promise~void~
        +cleanup() Promise~void~
        +loadScenario(scenario: RoadTestScenario) Promise~TestResult~
        +configureTopology(topology: NetworkTopology) Promise~TestResult~
        +configureDUT(dut: DUTConfig) Promise~TestResult~
        +queryStatus() Promise~TestStatus~
        +getMetrics() Promise~TestMetrics~
        +subscribeEvents(callback: EventCallback) Subscription
        +getCapabilities() TestCapabilities
        +getSupportedScenarios() RoadTestScenario[]
    }

    class DigitalTwinExecutor {
        -networkSim: INetworkSimulator
        -channelSim: IChannelSimulator
        -dutSim: IDUTSimulator
        -scenarioEngine: ScenarioEngine
        -computeBackend: ComputeBackend
    }

    class ConductedExecutor {
        -topologyManager: TopologyManager
        -bseDriver: IBaseStationDriver
        -ceDriver: IChannelEmulatorDriver
        -dutDriver: IDUTDriver
    }

    class OTAExecutor {
        -scenarioMapper: OTAScenarioMapper
        -bseDriver: IBaseStationDriver
        -ceDriver: IChannelEmulatorDriver
        -mpacController: MPACController
        -positionerController: PositionerController
    }

    ITestExecutor <|.. DigitalTwinExecutor
    ITestExecutor <|.. ConductedExecutor
    ITestExecutor <|.. OTAExecutor
```

### 2.2 测试执行流程

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant ExecutionEngine
    participant Executor as ITestExecutor
    participant Hardware

    User->>Frontend: 选择测试模式
    Frontend->>User: 显示场景库
    User->>Frontend: 选择场景
    Frontend->>ExecutionEngine: createExecution(mode, scenario)
    ExecutionEngine->>Executor: initialize(config)

    Executor->>Executor: validate()
    Executor->>Hardware: 连接设备/分配资源
    Executor-->>ExecutionEngine: 初始化完成

    ExecutionEngine->>Executor: execute()
    Executor->>Hardware: 启动测试

    loop 测试运行中
        Executor->>Hardware: 采集数据
        Hardware-->>Executor: 测量结果
        Executor->>ExecutionEngine: 推送指标
        ExecutionEngine->>Frontend: WebSocket推送
        Frontend->>User: 实时显示
    end

    User->>Frontend: 停止测试
    Frontend->>ExecutionEngine: stopExecution()
    ExecutionEngine->>Executor: stop()
    Executor->>Hardware: 停止并清理
    Executor-->>ExecutionEngine: 测试结果
    ExecutionEngine-->>Frontend: 返回结果
    Frontend->>User: 显示报告
```

### 2.3 模式切换机制

```mermaid
stateDiagram-v2
    [*] --> ModeSelection: 用户启动

    ModeSelection --> DigitalTwin: 选择数字孪生
    ModeSelection --> Conducted: 选择传导测试
    ModeSelection --> OTA: 选择OTA测试

    DigitalTwin --> ScenarioConfig: 配置场景
    Conducted --> TopologyConfig: 配置拓扑
    OTA --> ScenarioConfig: 配置场景

    TopologyConfig --> ScenarioConfig: 拓扑确认

    ScenarioConfig --> DUTConfig: 场景确认
    DUTConfig --> KPIConfig: DUT配置完成
    KPIConfig --> Executing: 启动执行

    Executing --> Paused: 暂停
    Paused --> Executing: 继续
    Executing --> Completed: 测试完成
    Executing --> Failed: 测试失败

    Completed --> [*]
    Failed --> [*]

    note right of DigitalTwin
        无需硬件
        软件仿真
    end note

    note right of Conducted
        需要仪表+DUT
        RF线缆连接
    end note

    note right of OTA
        需要MPAC暗室
        空间辐射
    end note
```

---

## 3. 数字孪生引擎

### 3.1 数字孪生架构

```mermaid
graph TB
    subgraph "数字孪生引擎 - Digital Twin Engine"
        subgraph "网络仿真器 - Network Simulator"
            NET1[gNB/eNB模型]
            NET2[核心网模型]
            NET3[协议栈<br/>RRC/MAC/PHY]
            NET4[调度器<br/>PF/RR/MaxCI]
        end

        subgraph "信道仿真器 - Channel Simulator"
            CH1[几何信道模型<br/>Ray Tracing]
            CH2[统计信道模型<br/>3GPP TR 38.901]
            CH3[多径传播<br/>Multipath]
            CH4[快衰落生成<br/>Jakes模型]
            CH5[H矩阵计算]
        end

        subgraph "DUT仿真器 - DUT Simulator"
            DUT1[车辆平台模型]
            DUT2[天线阵列模型<br/>Pattern/Gain]
            DUT3[RF前端模型<br/>LNA/PA]
            DUT4[协议栈]
            DUT5[应用层]
        end

        subgraph "场景引擎 - Scenario Engine"
            SCE1[轨迹生成器<br/>Trajectory]
            SCE2[环境加载器<br/>Buildings/Trees]
            SCE3[事件触发器<br/>Handover/Beam]
            SCE4[仿真时钟<br/>Time Advance]
        end

        SCE4 --> NET1 & CH1 & DUT1
        NET3 --> CH5
        CH5 --> DUT2
        DUT2 --> DUT4
        SCE1 --> CH1
        SCE2 --> CH1
    end

    subgraph "计算后端 - Compute Backend"
        GPU[GPU加速<br/>CUDA/OpenCL]
        CPU[CPU并行<br/>多线程]
        MEM[内存管理<br/>结果缓存]
    end

    CH5 --> GPU
    NET3 & DUT4 --> CPU
    GPU & CPU --> MEM

    style GPU fill:#ff9800
    style CH5 fill:#4caf50
```

### 3.2 仿真时钟与事件驱动

```mermaid
sequenceDiagram
    participant Clock as 仿真时钟
    participant Scene as 场景引擎
    participant Network as 网络仿真器
    participant Channel as 信道仿真器
    participant DUT as DUT仿真器
    participant Collector as 数据采集器

    Clock->>Scene: tick(t=0.001s)
    Scene->>Scene: 更新车辆位置
    Scene->>Scene: 检查触发事件

    alt 有切换事件
        Scene->>Network: triggerHandover(BS1→BS2)
    end

    Scene->>Channel: updatePosition(lat, lon, alt)
    Channel->>Channel: 计算路径损耗
    Channel->>Channel: 计算多径分量
    Channel->>Channel: 生成H矩阵(4×4)

    Network->>Channel: 发送信号(下行)
    Channel->>DUT: 接收信号(经过H矩阵)
    DUT->>DUT: RF处理
    DUT->>DUT: 基带解调
    DUT->>DUT: 计算吞吐量

    DUT->>Collector: 上报KPI(吞吐量, SINR, BLER)
    Collector->>Collector: 存储时间序列数据

    Clock->>Clock: t += 0.001s
    Clock->>Scene: tick(t=0.002s)
```

### 3.3 信道模型架构

```mermaid
graph TB
    subgraph "信道模型层次结构"
        L1[大尺度衰落<br/>Large Scale Fading]
        L2[小尺度衰落<br/>Small Scale Fading]

        L1 --> L1A[路径损耗<br/>Path Loss]
        L1 --> L1B[阴影衰落<br/>Shadowing]

        L2 --> L2A[多径传播<br/>Multipath]
        L2 --> L2B[多普勒效应<br/>Doppler]

        L1A --> PL1[自由空间<br/>Friis]
        L1A --> PL2[3GPP UMa/UMi/RMa]
        L1A --> PL3[自定义隧道模型]

        L1B --> SH1[对数正态分布<br/>Log-Normal]

        L2A --> MP1[3GPP CDL-A/B/C/D/E]
        L2A --> MP2[3GPP TDL-A/B/C]
        L2A --> MP3[Geometric Model<br/>Ray Tracing]

        L2B --> DP1[Jakes模型]
        L2B --> DP2[Clarke模型]
    end

    subgraph "H矩阵生成"
        H1[抽头延迟<br/>Tap Delays]
        H2[功率分布<br/>Power Delay Profile]
        H3[空间相关<br/>Spatial Correlation]
        H4[H矩阵<br/>NRx × NTx × NTaps]
    end

    MP1 & MP2 & MP3 --> H1 & H2
    H1 & H2 & H3 --> H4

    style H4 fill:#4caf50
```

---

## 4. 传导测试架构

### 4.1 传导测试系统架构

```mermaid
graph LR
    subgraph "基站仿真器 - BSE"
        BSE1[CMX500/8820C]
        BSE2[4个TX端口]
        BSE3[5G NR/LTE协议栈]
    end

    subgraph "信道仿真器 - CE"
        CE1[PropsIM F64/Vertex]
        CE2[4输入 → 64输出]
        CE3[实时信道模型]
    end

    subgraph "DUT"
        DUT1[车辆TCU]
        DUT2[4个RX天线端口]
        DUT3[控制接口<br/>ADB/USB/Ethernet]
    end

    subgraph "拓扑管理器"
        TOPO1[端口映射]
        TOPO2[线缆损耗补偿]
        TOPO3[功率校准]
    end

    subgraph "屏蔽暗室"
        CHAMBER[隔离度 > 80dB]
    end

    BSE2 -->|RF线缆<br/>LMR-400| CE2
    CE2 -->|RF线缆<br/>RG-58| DUT2
    TOPO1 -.配置.-> BSE1 & CE1 & DUT1
    TOPO2 -.补偿.-> BSE1 & CE1
    CHAMBER -.包含.-> BSE1 & CE1 & DUT1

    style CHAMBER fill:#fff9c4
```

### 4.2 拓扑配置数据流

```mermaid
sequenceDiagram
    participant User
    participant TopologyUI as 拓扑配置器UI
    participant TopologyMgr as 拓扑管理器
    participant BSEDriver as 基站驱动
    participant CEDriver as 信道仿真器驱动
    participant DUTDriver as DUT驱动

    User->>TopologyUI: 选择MIMO 4×4拓扑
    TopologyUI->>User: 显示向导
    User->>TopologyUI: 选择CMX500
    User->>TopologyUI: 选择PropsIM F64
    User->>TopologyUI: 配置DUT (ADB接口)

    TopologyUI->>TopologyUI: 生成拓扑JSON
    TopologyUI->>TopologyMgr: validateTopology(topology)

    TopologyMgr->>TopologyMgr: 检查端口冲突
    TopologyMgr->>TopologyMgr: 检查连接有效性
    TopologyMgr-->>TopologyUI: 验证通过

    User->>TopologyUI: 应用配置
    TopologyUI->>TopologyMgr: applyTopology(topology)

    par 并行配置设备
        TopologyMgr->>BSEDriver: connect(192.168.1.100)
        TopologyMgr->>CEDriver: connect(192.168.1.101)
        TopologyMgr->>DUTDriver: connect(adb://192.168.1.102)
    end

    BSEDriver-->>TopologyMgr: 已连接
    CEDriver-->>TopologyMgr: 已连接
    DUTDriver-->>TopologyMgr: 已连接

    TopologyMgr->>BSEDriver: configureOutputs([1,2,3,4])
    TopologyMgr->>CEDriver: configureMapping(4输入→4输出)
    TopologyMgr->>DUTDriver: configureAntennas([1,2,3,4])

    TopologyMgr->>TopologyMgr: 执行功率校准
    TopologyMgr-->>TopologyUI: 配置完成
    TopologyUI->>User: 显示拓扑状态
```

### 4.3 RF链路损耗补偿

```mermaid
graph TB
    subgraph "RF链路"
        BSE[BSE端口1<br/>输出功率: -50dBm]
        CABLE1[线缆1<br/>LMR-400, 5m<br/>损耗: -1.2dB]
        CE_IN[CE输入1<br/>实际功率: -51.2dBm]
        CE_OUT[CE输出1<br/>增益: 0dB<br/>输出功率: -51.2dBm]
        CABLE2[线缆2<br/>RG-58, 2m<br/>损耗: -0.5dB]
        DUT[DUT天线1<br/>实际功率: -51.7dBm]
    end

    subgraph "补偿机制"
        CAL1[功率校准<br/>目标: -50dBm@DUT]
        CAL2[BSE功率调整<br/>+1.7dB]
        CAL3[验证测量<br/>实际-50.1dBm]
    end

    BSE --> CABLE1
    CABLE1 --> CE_IN
    CE_IN --> CE_OUT
    CE_OUT --> CABLE2
    CABLE2 --> DUT

    CAL1 --> CAL2
    CAL2 --> BSE
    DUT --> CAL3

    style CAL3 fill:#4caf50
```

### 4.4 DUT控制架构

```mermaid
classDiagram
    class IDUTDriver {
        <<interface>>
        +connect(interface: DUTInterface) Promise~void~
        +disconnect() Promise~void~
        +configureAntennas(config: AntennaConfig) Promise~void~
        +startDataTransfer(config: TrafficConfig) Promise~void~
        +stopDataTransfer() Promise~void~
        +getThroughput() Promise~ThroughputMetrics~
        +getBLER() Promise~number~
        +getRSSI() Promise~number[]~
        +getSINR() Promise~number[]~
        +enableLogging(categories: string[]) Promise~void~
        +getLogs() Promise~DUTLog[]~
    }

    class ADBDriver {
        -device: ADBDevice
        -shell: ADBShell
        +executeCommand(cmd: string) Promise~string~
        +pullFile(path: string) Promise~Buffer~
        +pushFile(local: string, remote: string) Promise~void~
    }

    class USBDriver {
        -usbDevice: USBDevice
        -endpoint: USBEndpoint
        +sendControlTransfer(setup: USBControlSetup) Promise~void~
        +readBulkData(length: number) Promise~Buffer~
    }

    class EthernetDriver {
        -socket: Socket
        -protocol: 'SCPI' | 'REST' | 'Custom'
        +sendCommand(cmd: string) Promise~string~
        +subscribe(event: string) EventEmitter
    }

    class DUTDriverRegistry {
        -drivers: Map~string, IDUTDriverPlugin~
        +register(plugin: IDUTDriverPlugin) void
        +getDriver(model: string, interface: DUTInterface) IDUTDriver
    }

    IDUTDriver <|.. ADBDriver
    IDUTDriver <|.. USBDriver
    IDUTDriver <|.. EthernetDriver
    DUTDriverRegistry --> IDUTDriver
```

---

## 5. OTA测试架构

### 5.1 场景到OTA映射

```mermaid
graph TB
    subgraph "路测场景 - Road Test Scenario"
        SC1[轨迹<br/>Trajectory<br/>坐标序列+时间戳]
        SC2[环境<br/>Environment<br/>城市/高速/隧道]
        SC3[速度<br/>Speed<br/>30-120 km/h]
        SC4[基站位置<br/>BS Locations<br/>经纬度+高度]
    end

    subgraph "OTA场景映射器 - OTAScenarioMapper"
        MAP1[轨迹→转台运动]
        MAP2[环境→信道模型]
        MAP3[速度→多普勒]
        MAP4[基站→波束方向]
    end

    subgraph "OTA配置 - OTA Configuration"
        OTA1[转台序列<br/>方位角: [0°, 45°, 90°...]<br/>俯仰角: [0°, 10°, 20°...]]
        OTA2[信道模型<br/>3GPP UMa/UMi/RMa]
        OTA3[多普勒配置<br/>最大多普勒频移]
        OTA4[探头权重<br/>32探头复数权重]
    end

    SC1 --> MAP1
    SC2 --> MAP2
    SC3 --> MAP3
    SC4 --> MAP4

    MAP1 --> OTA1
    MAP2 --> OTA2
    MAP3 --> OTA3
    MAP4 --> OTA4

    style MAP1 fill:#e1f5ff
    style MAP2 fill:#e8f5e9
    style MAP3 fill:#fff3e0
    style MAP4 fill:#f3e5f5
```

### 5.2 MPAC探头权重计算

```mermaid
sequenceDiagram
    participant Scenario as 路测场景
    participant Mapper as OTA映射器
    participant ChannelModel as 信道模型
    participant ProbeWeights as 探头权重计算
    participant MPAC as MPAC控制器

    Scenario->>Mapper: 输入场景(t=0s)
    Mapper->>Mapper: 解析车辆位置
    Mapper->>Mapper: 解析环境类型

    Mapper->>ChannelModel: 加载3GPP UMa模型
    ChannelModel->>ChannelModel: 计算路径损耗
    ChannelModel->>ChannelModel: 生成多径分量(20 paths)

    ChannelModel->>ProbeWeights: 输入AoA/AoD/Delay/Power
    ProbeWeights->>ProbeWeights: 球面波合成算法
    ProbeWeights->>ProbeWeights: 计算32探头复数权重

    ProbeWeights->>MPAC: 下发权重[w1, w2, ..., w32]
    MPAC->>MPAC: 配置信道仿真器输出
    MPAC-->>Mapper: 配置完成

    Note over Scenario,MPAC: 每个时间步重复此流程
```

### 5.3 OTA测试时间序列

```mermaid
gantt
    title OTA路测场景执行时间线
    dateFormat  s
    axisFormat  %Ss

    section 场景初始化
    加载场景配置           :done, init1, 0, 2s
    连接MPAC设备          :done, init2, 2s, 4s
    校准探头              :done, init3, 4s, 10s

    section 测试执行
    时刻t=0s, 位置A, BS1  :active, exec1, 10s, 15s
    时刻t=5s, 位置B, BS1  :exec2, 15s, 20s
    时刻t=10s, 位置C, BS1→BS2切换 :crit, exec3, 20s, 25s
    时刻t=15s, 位置D, BS2 :exec4, 25s, 30s
    时刻t=20s, 位置E, BS2 :exec5, 30s, 35s

    section 数据采集
    采集吞吐量            :data1, 10s, 35s
    采集RSRP/SINR        :data2, 10s, 35s
    采集切换事件          :crit, data3, 20s, 25s

    section 结果处理
    保存原始数据          :result1, 35s, 37s
    计算KPI              :result2, 37s, 39s
    生成报告              :result3, 39s, 42s
```

---

## 6. 数据模型

### 6.1 核心数据模型关系图

```mermaid
erDiagram
    RoadTestScenario ||--o{ ScenarioEvent : contains
    RoadTestScenario ||--|| NetworkConfig : has
    RoadTestScenario ||--|| Route : has
    RoadTestScenario ||--|| Environment : has
    RoadTestScenario ||--o{ KPIDefinition : defines

    Route ||--o{ Waypoint : contains
    Environment ||--o{ Obstruction : contains

    NetworkConfig ||--o{ BaseStationConfig : contains

    NetworkTopology ||--|| BaseStationDevice : uses
    NetworkTopology ||--|| ChannelEmulatorDevice : uses
    NetworkTopology ||--|| DUTDevice : uses
    NetworkTopology ||--o{ RFConnection : defines

    TestExecution ||--|| RoadTestScenario : executes
    TestExecution ||--o| NetworkTopology : uses
    TestExecution ||--|| TestStatus : has
    TestExecution ||--o{ TestMetrics : generates

    RoadTestScenario {
        string id PK
        string name
        enum category
        enum source
        string[] tags
    }

    NetworkConfig {
        enum type "5G_NR/LTE/C-V2X"
        string band
        string bandwidth
    }

    Route {
        enum type "predefined/recorded/generated"
        number duration
        number totalDistance
    }

    Waypoint {
        number time
        object position "lat/lon/alt"
        object velocity "speed/heading"
    }

    Environment {
        enum type "urban/highway/tunnel"
        enum weather
        enum trafficDensity
    }

    NetworkTopology {
        string id PK
        enum type "SISO/MIMO_2x2/MIMO_4x4"
    }

    TestExecution {
        string executionId PK
        enum mode "digital_twin/conducted/ota"
        enum status
        datetime startTime
        datetime endTime
    }
```

### 6.2 场景事件类型

```mermaid
graph TB
    ScenarioEvent[ScenarioEvent基类]

    ScenarioEvent --> HandoverEvent[切换事件<br/>HandoverEvent]
    ScenarioEvent --> BeamSwitchEvent[波束切换事件<br/>BeamSwitchEvent]
    ScenarioEvent --> RFImpairmentEvent[RF损伤事件<br/>RFImpairmentEvent]
    ScenarioEvent --> TrafficBurstEvent[流量突发事件<br/>TrafficBurstEvent]

    HandoverEvent --> HO1[源小区ID]
    HandoverEvent --> HO2[目标小区ID]
    HandoverEvent --> HO3[切换类型<br/>intra-freq/inter-freq]

    BeamSwitchEvent --> BS1[源波束ID]
    BeamSwitchEvent --> BS2[目标波束ID]
    BeamSwitchEvent --> BS3[切换原因<br/>RSRP低/负载均衡]

    RFImpairmentEvent --> RF1[损伤类型<br/>signal_loss/interference]
    RFImpairmentEvent --> RF2[持续时间]
    RFImpairmentEvent --> RF3[严重程度<br/>-10dB to -30dB]

    TrafficBurstEvent --> TB1[流量类型<br/>video/file_download]
    TrafficBurstEvent --> TB2[数据量<br/>100MB]
    TrafficBurstEvent --> TB3[持续时间<br/>10s]

    style ScenarioEvent fill:#90caf9
    style HandoverEvent fill:#a5d6a7
    style BeamSwitchEvent fill:#fff59d
    style RFImpairmentEvent fill:#ef9a9a
    style TrafficBurstEvent fill:#ce93d8
```

---

## 7. API设计

### 7.1 RESTful API端点树

```mermaid
graph TB
    API["/api/v1"]

    API --> RT["/road-test"]
    API --> EXEC["/executions"]
    API --> MON["/monitoring"]

    RT --> SC["/scenarios"]
    RT --> TOPO["/topologies"]

    SC --> SC_GET["GET 获取场景列表"]
    SC --> SC_POST["POST 创建场景"]
    SC --> SC_ID["/scenarios/:id"]
    SC_ID --> SC_GET_ID["GET 获取详情"]
    SC_ID --> SC_PUT["PUT 更新场景"]
    SC_ID --> SC_DEL["DELETE 删除场景"]

    TOPO --> TOPO_GET["GET 获取拓扑列表"]
    TOPO --> TOPO_POST["POST 创建拓扑"]
    TOPO --> TOPO_ID["/topologies/:id"]
    TOPO_ID --> TOPO_GET_ID["GET 获取详情"]
    TOPO_ID --> TOPO_PUT["PUT 更新拓扑"]
    TOPO_ID --> TOPO_DEL["DELETE 删除拓扑"]
    TOPO_ID --> TOPO_VAL["POST /validate 验证拓扑"]

    EXEC --> EXEC_POST["POST 创建执行"]
    EXEC --> EXEC_ID["/executions/:id"]
    EXEC_ID --> EXEC_GET["GET 获取状态"]
    EXEC_ID --> EXEC_DEL["DELETE 停止执行"]
    EXEC_ID --> EXEC_CTL["POST /control 控制<br/>pause/resume/stop"]
    EXEC_ID --> EXEC_MET["GET /metrics 获取指标"]
    EXEC_ID --> EXEC_WS["WS /stream 实时流"]

    MON --> MON_DASH["GET /dashboard"]
    MON --> MON_ALERTS["GET /alerts"]

    style API fill:#42a5f5
    style RT fill:#66bb6a
    style EXEC fill:#ffa726
    style MON fill:#ab47bc
```

### 7.2 WebSocket实时数据流协议

```mermaid
sequenceDiagram
    participant Client as 前端客户端
    participant WSServer as WebSocket服务器
    participant Executor as 测试执行器
    participant Hardware as 硬件/仿真器

    Client->>WSServer: 连接 ws://api/v1/executions/:id/stream
    WSServer-->>Client: 连接建立

    Client->>WSServer: {"subscribe": ["metrics", "events", "logs"]}
    WSServer-->>Client: {"subscribed": true}

    loop 每100ms
        Hardware->>Executor: 测量数据
        Executor->>Executor: 计算KPI
        Executor->>WSServer: 推送指标
        WSServer->>Client: {"type": "metrics", "data": {...}}
    end

    alt 触发事件
        Executor->>WSServer: 切换事件
        WSServer->>Client: {"type": "event", "data": {"event": "handover"}}
    end

    alt 告警
        Hardware->>Executor: 温度过高
        Executor->>WSServer: 告警
        WSServer->>Client: {"type": "alert", "severity": "warning"}
    end

    Client->>WSServer: {"unsubscribe": ["logs"]}
    Client->>WSServer: 断开连接
    WSServer-->>Client: 连接关闭
```

---

## 8. 前端架构

### 8.1 前端组件树

```mermaid
graph TB
    App[App.tsx]

    App --> Header[Header组件]
    App --> Sidebar[SidebarNav组件]
    App --> Main[主内容区]

    Main --> VRT[VirtualRoadTest模块]

    VRT --> ModeSelect[ModeSelector<br/>模式选择器]
    VRT --> SceneLib[ScenarioLibrary<br/>场景库]
    VRT --> SceneEdit[ScenarioEditor<br/>场景编辑器]
    VRT --> TopoConfig[TopologyConfigurator<br/>拓扑配置器]
    VRT --> Monitor[ExecutionMonitor<br/>执行监控]
    VRT --> Results[ResultsAnalyzer<br/>结果分析]

    ModeSelect --> ModeCard[ModeCard × 3<br/>数字孪生/传导/OTA]

    SceneLib --> SceneFilter[场景筛选<br/>Tabs + Search]
    SceneLib --> SceneGrid[场景网格<br/>Grid + ScenarioCard]

    SceneEdit --> MapEditor[地图编辑器<br/>OpenStreetMap]
    SceneEdit --> NetworkEditor[网络配置器]
    SceneEdit --> EventTimeline[事件时间线]

    TopoConfig --> TopoWizard[向导模式]
    TopoConfig --> TopoVisual[可视化编辑<br/>Canvas拖拽]
    TopoConfig --> TopoCode[代码模式<br/>JSON编辑]

    Monitor --> DTDashboard[数字孪生仪表板<br/>3D可视化]
    Monitor --> ConductedDash[传导测试仪表板]
    Monitor --> OTADash[OTA测试仪表板]

    DTDashboard --> SimClock[仿真时钟]
    DTDashboard --> Viewer3D[3D场景查看器<br/>Three.js]
    DTDashboard --> KPICharts[实时KPI图表<br/>Line/Bar Charts]

    Results --> CompareView[对比视图<br/>模式间/场景间]
    Results --> ReportGen[报告生成器<br/>PDF/HTML]

    style VRT fill:#e1f5ff
    style DTDashboard fill:#e8f5e9
```

### 8.2 状态管理架构

```mermaid
graph TB
    subgraph "前端状态管理"
        subgraph "服务端状态 - TanStack Query"
            Q1[useScenarios<br/>场景列表]
            Q2[useScenarioDetail<br/>场景详情]
            Q3[useTopologies<br/>拓扑列表]
            Q4[useExecution<br/>执行状态]
            Q5[useMetrics<br/>实时指标]
        end

        subgraph "UI状态 - React Hooks"
            S1[selectedMode<br/>useState]
            S2[selectedScenario<br/>useState]
            S3[topologyConfig<br/>useState]
            S4[filterCategory<br/>useState]
            S5[chartTimeRange<br/>useState]
        end

        subgraph "全局状态 - Context"
            C1[UserContext<br/>用户信息]
            C2[ThemeContext<br/>主题配置]
            C3[NotificationContext<br/>通知队列]
        end
    end

    subgraph "API服务层"
        API1[fetchScenarios]
        API2[createExecution]
        API3[getMetrics]
    end

    subgraph "WebSocket层"
        WS1[useWebSocket<br/>实时数据订阅]
    end

    Q1 & Q2 & Q3 --> API1
    Q4 --> API2
    Q5 --> API3 & WS1

    style Q1 fill:#4caf50
    style Q5 fill:#ff9800
    style WS1 fill:#f44336
```

### 8.3 场景编辑器架构

```mermaid
graph TB
    ScenarioEditor[ScenarioEditor组件]

    ScenarioEditor --> Tabs[编辑器Tabs]

    Tabs --> Tab1[基本信息]
    Tabs --> Tab2[网络配置]
    Tabs --> Tab3[路径轨迹]
    Tabs --> Tab4[环境设置]
    Tabs --> Tab5[事件设置]
    Tabs --> Tab6[KPI定义]

    Tab1 --> Form1[名称/分类/标签<br/>Mantine Form]

    Tab2 --> NetForm[网络类型选择<br/>5G NR/LTE/C-V2X]
    Tab2 --> BSEditor[基站编辑器<br/>地图上放置基站]

    Tab3 --> MapView[地图视图<br/>OpenStreetMap/Leaflet]
    Tab3 --> DrawTool[绘制工具<br/>绘制轨迹路径]
    Tab3 --> SpeedProfile[速度曲线<br/>时间-速度图表]

    Tab4 --> EnvType[环境类型<br/>城市/高速/隧道]
    Tab4 --> Weather[天气条件]
    Tab4 --> ObstEditor[障碍物编辑器<br/>建筑/树木]

    Tab5 --> Timeline[时间轴组件]
    Tab5 --> EventLib[事件库<br/>拖拽添加事件]

    Tab6 --> KPIList[KPI列表<br/>吞吐量/延迟/BLER]
    Tab6 --> TargetInput[目标值输入<br/>数值+单位+百分位]

    style MapView fill:#4caf50
    style Timeline fill:#ff9800
```

---

## 9. 技术选型总结

### 9.1 前端技术栈

| 层次 | 技术选型 | 版本 | 说明 |
|------|---------|------|------|
| **框架** | React | 18.3.1 | 已有 |
| **语言** | TypeScript | 5.9.3 | 已有 |
| **构建** | Vite | 7.1.7 | 已有 |
| **UI库** | Mantine | 8.3.6 | 已有 |
| **状态管理** | TanStack Query | 5.90.5 | 已有 |
| **HTTP客户端** | Axios | 1.12.2 | 已有 |
| **图表** | Recharts / Chart.js | TBD | 新增 |
| **3D可视化** | Three.js | TBD | 新增 |
| **地图** | Leaflet + OpenStreetMap | TBD | 新增 |
| **WebSocket** | native WebSocket API | - | 新增 |

### 9.2 后端技术栈（建议）

| 层次 | 技术选型 | 说明 |
|------|---------|------|
| **框架** | FastAPI (Python) / NestJS (TypeScript) | 推荐FastAPI，与仿真引擎集成方便 |
| **数据库** | PostgreSQL + TimescaleDB | 时序数据优化 |
| **对象存储** | MinIO / S3 | 场景数据存储 |
| **消息队列** | Redis / RabbitMQ | 任务队列 |
| **WebSocket** | Socket.IO / FastAPI WebSocket | 实时数据推送 |
| **任务调度** | Celery / Bull | 异步任务 |

### 9.3 数字孪生仿真引擎（待选型）

| 选项 | 优势 | 劣势 | 推荐度 |
|------|------|------|-------|
| **ns-3** | 开源，5G NR模块成熟，社区活跃 | C++，学习曲线陡峭 | ⭐⭐⭐⭐⭐ |
| **MATLAB** | 工具箱丰富，快速原型开发 | 闭源，License费用高 | ⭐⭐⭐ |
| **自研引擎** | 完全可控，定制化强 | 开发周期长，风险高 | ⭐⭐ |
| **商业仿真软件** | 精度高，支持好 | 成本极高 | ⭐⭐ |

**推荐**: ns-3 + Python绑定 (ns3-ai)，结合GPU加速库（CuPy/PyTorch）

---

## 10. 部署架构

### 10.1 系统部署拓扑

```mermaid
graph TB
    subgraph "用户层"
        Browser[Web浏览器]
    end

    subgraph "应用层 - Docker Compose"
        Nginx[Nginx<br/>反向代理]
        Frontend[前端容器<br/>React SPA]
        Backend[后端容器<br/>FastAPI]
        WSServer[WebSocket服务器]
    end

    subgraph "服务层"
        DTEngine[数字孪生引擎<br/>ns-3容器]
        ConductedCtrl[传导测试控制器]
        OTACtrl[OTA测试控制器]
    end

    subgraph "数据层"
        Postgres[(PostgreSQL<br/>元数据)]
        TimescaleDB[(TimescaleDB<br/>时序数据)]
        MinIO[(MinIO<br/>对象存储<br/>场景文件)]
        Redis[(Redis<br/>缓存+队列)]
    end

    subgraph "硬件层"
        GPU[GPU服务器<br/>NVIDIA A100]
        Instruments[仪表设备<br/>CMX500/PropsIM]
        MPAC[MPAC暗室<br/>32探头]
    end

    Browser --> Nginx
    Nginx --> Frontend
    Nginx --> Backend
    Nginx --> WSServer

    Backend --> DTEngine
    Backend --> ConductedCtrl
    Backend --> OTACtrl

    Backend --> Postgres & TimescaleDB & MinIO & Redis

    DTEngine --> GPU
    ConductedCtrl --> Instruments
    OTACtrl --> MPAC

    style Browser fill:#42a5f5
    style GPU fill:#ff9800
    style Instruments fill:#66bb6a
    style MPAC fill:#ab47bc
```

---

**文档结束**

相关文档:
- [VirtualRoadTest.md](./VirtualRoadTest.md) - 主设计文档
- [VirtualRoadTest-Implementation.md](./VirtualRoadTest-Implementation.md) - 开发者实施指南
