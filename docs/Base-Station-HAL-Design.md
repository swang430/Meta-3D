# Base Station Emulator HAL Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Hardware Abstraction Layer (硬件抽象层)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

基站仿真器硬件抽象层（Base Station Emulator HAL）为不同厂商的5G/LTE基站仿真器提供统一的软件接口，支持OTA测试中的下行链路（DL）和上行链路（UL）测试。

**核心功能**:
- **信号生成**: 生成符合3GPP标准的5G NR/LTE信号
- **调度控制**: 配置RB分配、MCS、MIMO层数
- **测量采集**: 获取吞吐量、BLER、RSRP/SINR等指标
- **多厂商支持**: Keysight, R&S, Anritsu等主流厂商

### 1.2 支持的基站仿真器

| 厂商 | 型号 | 支持制式 | 带宽 | 通信接口 | 优先级 |
|------|------|---------|------|---------|-------|
| **Keysight** | UXM 5G | 5G NR, LTE | 400 MHz | SCPI/LAN | P0 |
| **R&S** | CMW500 | 5G NR, LTE | 200 MHz | SCPI/LAN | P0 |
| **Anritsu** | MT8000A | 5G NR, LTE | 100 MHz | SCPI/USB | P1 |
| **Keysight** | E7515B UXM | LTE-A Pro | 160 MHz | SCPI/LAN | P1 |
| **Virtual** | Mock BS | 5G NR, LTE | N/A | REST API | P0 |

### 1.3 标准依据

- **3GPP TS 38.101**: NR User Equipment (UE) radio transmission and reception
- **3GPP TS 36.101**: LTE UE radio transmission and reception
- **3GPP TS 38.521**: NR UE conformance specification
- **SCPI**: Standard Commands for Programmable Instruments

## 2. 系统架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ EIS Testing  │  │ Throughput   │  │ BLER Testing │           │
│  │              │  │   Testing    │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Base Station Emulator HAL                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Unified Interface Layer                     │   │
│  │  - IBaseStationEmulator (abstract interface)            │   │
│  │  - Common data models (CellConfig, MeasurementResults)  │   │
│  │  - Call flow management                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Adapter Layer                               │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐           │   │
│  │  │  Keysight  │ │    R&S     │ │  Anritsu   │           │   │
│  │  │    UXM     │ │  CMW500    │ │  MT8000A   │           │   │
│  │  └────────────┘ └────────────┘ └────────────┘           │   │
│  │  ┌────────────┐                                          │   │
│  │  │  Virtual   │                                          │   │
│  │  │  Mock BS   │                                          │   │
│  │  └────────────┘                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Physical Hardware Layer                        │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                   │
│  │  Keysight  │ │    R&S     │ │  Anritsu   │                   │
│  │  UXM 5G    │ │  CMW500    │ │  MT8000A   │                   │
│  └────────────┘ └────────────┘ └────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 连接管理器
管理SCPI/REST连接，处理超时和重连。

#### 2.2.2 呼叫流程管理器
管理UE注册、RRC连接、数据传输等呼叫流程。

#### 2.2.3 调度配置器
配置资源块分配、MCS、MIMO参数。

#### 2.2.4 测量采集器
实时采集吞吐量、BLER、RSRP等测量结果。

## 3. 统一接口设计

### 3.1 IBaseStationEmulator接口

```typescript
/**
 * 基站仿真器统一接口
 */
interface IBaseStationEmulator {
  // ============ 连接管理 ============
  connect(config: BSConnectionConfig): Promise<void>
  disconnect(): Promise<void>
  isConnected(): boolean
  getInstrumentInfo(): Promise<BSInstrumentInfo>

  // ============ 小区配置 ============
  /**
   * 配置5G NR小区
   */
  configureCellNR(config: NRCellConfig): Promise<void>

  /**
   * 配置LTE小区
   */
  configureCellLTE(config: LTECellConfig): Promise<void>

  /**
   * 获取当前小区配置
   */
  getCellConfig(): Promise<CellConfig>

  /**
   * 激活小区（开始广播）
   */
  activateCell(): Promise<void>

  /**
   * 去激活小区
   */
  deactivateCell(): Promise<void>

  // ============ UE呼叫管理 ============
  /**
   * 注册UE（模拟UE接入）
   */
  registerUE(ueConfig: UEConfig): Promise<UEHandle>

  /**
   * 去注册UE
   */
  deregisterUE(ueHandle: UEHandle): Promise<void>

  /**
   * 建立数据承载
   */
  establishDataBearer(ueHandle: UEHandle, bearerConfig: BearerConfig): Promise<void>

  /**
   * 释放数据承载
   */
  releaseDataBearer(ueHandle: UEHandle): Promise<void>

  // ============ 下行链路（DL）配置 ============
  /**
   * 配置下行调度
   */
  configureDLScheduling(config: DLSchedulingConfig): Promise<void>

  /**
   * 设置下行功率
   */
  setDLPower(powerDbm: number): Promise<void>

  /**
   * 配置MIMO层数
   */
  setMIMOLayers(numLayers: 1 | 2 | 4): Promise<void>

  /**
   * 设置MCS（调制编码方案）
   */
  setMCS(mcsIndex: number): Promise<void>

  // ============ 上行链路（UL）配置 ============
  /**
   * 配置上行调度
   */
  configureULScheduling(config: ULSchedulingConfig): Promise<void>

  /**
   * 设置上行功率控制
   */
  setULPowerControl(config: ULPowerControlConfig): Promise<void>

  // ============ 数据传输 ============
  /**
   * 启动下行数据传输
   */
  startDLTraffic(trafficConfig: TrafficConfig): Promise<void>

  /**
   * 启动上行数据传输
   */
  startULTraffic(trafficConfig: TrafficConfig): Promise<void>

  /**
   * 停止数据传输
   */
  stopTraffic(): Promise<void>

  // ============ 测量采集 ============
  /**
   * 获取吞吐量
   */
  getThroughput(): Promise<ThroughputMeasurement>

  /**
   * 获取BLER（块错误率）
   */
  getBLER(): Promise<BLERMeasurement>

  /**
   * 获取RSRP/RSRQ/SINR
   */
  getRadioMeasurements(): Promise<RadioMeasurements>

  /**
   * 启动连续测量
   */
  startContinuousMeasurement(interval_ms: number): Promise<void>

  /**
   * 停止连续测量
   */
  stopContinuousMeasurement(): Promise<void>

  /**
   * 获取测量结果（流式）
   */
  getMeasurementStream(): AsyncIterator<MeasurementResult>

  // ============ 状态监控 ============
  getStatus(): Promise<BSStatus>
  getErrors(): Promise<BSError[]>
  clearErrors(): Promise<void>

  // ============ 高级功能 ============
  /**
   * 加载测试用例配置文件
   */
  loadTestCase(filePath: string): Promise<void>

  /**
   * 保存当前配置
   */
  saveConfiguration(filePath: string): Promise<void>

  /**
   * 触发切换（Handover）
   */
  triggerHandover(targetCell: string): Promise<void>
}
```

### 3.2 数据模型

#### 3.2.1 5G NR小区配置

```typescript
interface NRCellConfig {
  // 频率配置
  frequency: {
    band: string  // e.g., 'n78' (3.5 GHz)
    dl_arfcn: number  // Absolute Radio Frequency Channel Number
    ul_arfcn: number
    scs_khz: 15 | 30 | 60 | 120  // Subcarrier Spacing
    bandwidth_mhz: 5 | 10 | 15 | 20 | 25 | 30 | 40 | 50 | 60 | 80 | 90 | 100
  }

  // 小区身份
  identity: {
    pci: number  // Physical Cell ID (0-1007)
    plmn: string  // e.g., '46000' (中国移动)
    tac: number  // Tracking Area Code
    cell_id: number
  }

  // TDD配置（如适用）
  tdd?: {
    pattern: 'DDDSU' | 'DDDSUU' | 'custom'
    periodicity_ms: 2.5 | 5 | 10
    dl_slots: number
    ul_slots: number
    special_slots: number
  }

  // SSB配置（同步信号块）
  ssb: {
    periodicity_ms: 5 | 10 | 20 | 40 | 80 | 160
    pattern: 'Case A' | 'Case B' | 'Case C'
    scs_khz: 15 | 30
  }

  // MIMO配置
  mimo: {
    dl_layers: 1 | 2 | 4 | 8
    ul_layers: 1 | 2 | 4
    transmission_mode: 'TM1' | 'TM2' | 'TM3' | 'TM4'
  }

  // 功率配置
  power: {
    ss_pbch_power_dbm: number  // SSB功率
    pdsch_power_dbm: number  // 下行数据信道功率
    reference_signal_power_dbm: number
  }
}
```

#### 3.2.2 LTE小区配置

```typescript
interface LTECellConfig {
  frequency: {
    band: number  // e.g., 3 (1800 MHz), 7 (2600 MHz), 41 (2.5 GHz TDD)
    dl_earfcn: number
    ul_earfcn: number
    bandwidth_mhz: 1.4 | 3 | 5 | 10 | 15 | 20
  }

  identity: {
    pci: number  // Physical Cell ID (0-503)
    plmn: string
    tac: number
    cell_id: number
  }

  tdd?: {
    uplink_downlink_config: 0 | 1 | 2 | 3 | 4 | 5 | 6
    special_subframe_config: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
  }

  mimo: {
    dl_transmission_mode: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
    num_tx_antennas: 1 | 2 | 4
    num_rx_antennas: 1 | 2 | 4
  }

  power: {
    reference_signal_power_dbm: number
    pdsch_power_offset_db: number
  }
}
```

#### 3.2.3 调度配置

```typescript
interface DLSchedulingConfig {
  // 资源分配
  resource_allocation: {
    type: 'type0' | 'type1' | 'type2'  // NR资源分配类型
    rbg_size: number  // Resource Block Group size
    start_rb: number  // 起始RB
    num_rbs: number  // RB数量
  }

  // MCS配置
  mcs: {
    index: number  // 0-28 (NR), 0-31 (LTE)
    modulation: 'QPSK' | '16QAM' | '64QAM' | '256QAM'
    code_rate: number  // 编码率
  }

  // HARQ配置
  harq: {
    max_retransmissions: number
    enabled: boolean
  }

  // 调度策略
  scheduling_type: 'static' | 'dynamic' | 'semi_persistent'
}

interface ULSchedulingConfig {
  resource_allocation: {
    start_rb: number
    num_rbs: number
  }

  mcs: {
    index: number
    modulation: 'QPSK' | '16QAM' | '64QAM'
  }

  power_control: {
    p0_nominal_pusch: number  // dBm
    alpha: 0 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1
  }
}
```

#### 3.2.4 测量结果

```typescript
interface ThroughputMeasurement {
  timestamp: Date

  downlink: {
    instantaneous_mbps: number
    average_mbps: number
    peak_mbps: number
    total_bytes: number
  }

  uplink: {
    instantaneous_mbps: number
    average_mbps: number
    peak_mbps: number
    total_bytes: number
  }

  duration_seconds: number
}

interface BLERMeasurement {
  timestamp: Date

  downlink: {
    total_blocks: number
    error_blocks: number
    bler_percent: number
  }

  uplink: {
    total_blocks: number
    error_blocks: number
    bler_percent: number
  }
}

interface RadioMeasurements {
  timestamp: Date

  rsrp_dbm: number  // Reference Signal Received Power
  rsrq_db: number   // Reference Signal Received Quality
  sinr_db: number   // Signal-to-Interference-plus-Noise Ratio

  // NR特有
  ss_rsrp_dbm?: number  // SSB RSRP
  csi_rsrp_dbm?: number  // CSI-RS RSRP

  // LTE特有
  rssi_dbm?: number  // Received Signal Strength Indicator
}
```

#### 3.2.5 基站状态

```typescript
interface BSStatus {
  state: 'idle' | 'cell_active' | 'ue_registered' | 'data_active' | 'error'

  cell_info?: {
    technology: '5G_NR' | 'LTE'
    band: string
    bandwidth_mhz: number
    pci: number
  }

  ue_info?: {
    registered: boolean
    rrc_state: 'idle' | 'connected'
    num_active_bearers: number
  }

  traffic_info?: {
    dl_active: boolean
    ul_active: boolean
    duration_seconds: number
  }

  health: {
    temperature_celsius: number
    errors_count: number
    warnings_count: number
  }
}
```

## 4. 适配器实现

### 4.1 Keysight UXM 5G Adapter

```typescript
class KeysightUXMAdapter implements IBaseStationEmulator {
  private scpiClient: SCPIClient
  private config: BSConnectionConfig
  private ueHandle?: UEHandle
  private measurementTimer?: NodeJS.Timer

  async connect(config: BSConnectionConfig): Promise<void> {
    this.config = config

    this.scpiClient = new SCPIClient({
      host: config.connection.host!,
      port: config.connection.port || 5025,
      timeout: config.connection.timeout_ms || 60000  // UXM操作可能较慢
    })

    await this.scpiClient.connect()

    // 验证仪器
    const idn = await this.scpiClient.query('*IDN?')
    if (!idn.includes('Keysight') && !idn.includes('UXM')) {
      throw new Error(`不是Keysight UXM: ${idn}`)
    }

    // 重置到已知状态
    await this.scpiClient.command('*RST')
    await this.scpiClient.command('*CLS')

    // 设置为5G NR模式
    await this.scpiClient.command('CONFigure:NRSub6:MEAS:STAN')
  }

  async configureCellNR(config: NRCellConfig): Promise<void> {
    // 1. 频率配置
    await this.scpiClient.command(
      `CONFigure:NRSub6:RFMW:BAND:DL ${config.frequency.band}`
    )
    await this.scpiClient.command(
      `CONFigure:NRSub6:RFMW:CHAN:DL ${config.frequency.dl_arfcn}`
    )
    await this scpiClient.command(
      `CONFigure:NRSub6:RFMW:CHAN:UL ${config.frequency.ul_arfcn}`
    )
    await this.scpiClient.command(
      `CONFigure:NRSub6:RFMW:BWIDth ${config.frequency.bandwidth_mhz}MHz`
    )
    await this.scpiClient.command(
      `CONFigure:NRSub6:RFMW:SCS ${config.frequency.scs_khz}kHz`
    )

    // 2. 小区身份
    await this.scpiClient.command(
      `CONFigure:NRSub6:CELL:PCI ${config.identity.pci}`
    )
    await this.scpiClient.command(
      `CONFigure:NRSub6:CELL:PLMN:MCC:MNC "${config.identity.plmn}"`
    )

    // 3. TDD配置（如适用）
    if (config.tdd) {
      await this.scpiClient.command(
        `CONFigure:NRSub6:RFMW:TDD:PATTern ${config.tdd.pattern}`
      )
    }

    // 4. SSB配置
    await this.scpiClient.command(
      `CONFigure:NRSub6:SYNC:PERiodicity ${config.ssb.periodicity_ms}ms`
    )

    // 5. MIMO配置
    await this.scpiClient.command(
      `CONFigure:NRSub6:MIMO:DL:LAYers ${config.mimo.dl_layers}`
    )

    // 6. 功率配置
    await this.scpiClient.command(
      `CONFigure:NRSub6:RFOU:LEVel:SSB ${config.power.ss_pbch_power_dbm}dBm`
    )
    await this.scpiClient.command(
      `CONFigure:NRSub6:RFOU:LEVel:PDSCH ${config.power.pdsch_power_dbm}dBm`
    )

    // 应用配置
    await this.scpiClient.command('CONFigure:NRSub6:CELL:APPLy')
    await this.waitForOperationComplete()
  }

  async activateCell(): Promise<void> {
    await this.scpiClient.command('CONFigure:NRSub6:CELL:STATe ON')
    await this.waitForOperationComplete()
  }

  async registerUE(ueConfig: UEConfig): Promise<UEHandle> {
    // UXM的UE注册流程
    await this.scpiClient.command('CALL:NRSub6:SIGN:ACTion CONNect')

    // 等待UE注册
    let attempts = 0
    while (attempts < 30) {  // 最多等待30秒
      const state = await this.scpiClient.query('CALL:NRSub6:SIGN:STATe?')
      if (state === 'CONN') {
        this.ueHandle = { id: 'ue_1' }
        return this.ueHandle
      }
      await new Promise(resolve => setTimeout(resolve, 1000))
      attempts++
    }

    throw new Error('UE注册超时')
  }

  async establishDataBearer(ueHandle: UEHandle, bearerConfig: BearerConfig): Promise<void> {
    // 建立EPS承载（LTE）或PDU Session（5G NR）
    await this.scpiClient.command('CALL:NRSub6:DATA:STATe ON')
    await this.waitForOperationComplete()
  }

  async configureDLScheduling(config: DLSchedulingConfig): Promise<void> {
    // 设置MCS
    await this.scpiClient.command(
      `CONFigure:NRSub6:DL:PDSCH:MCS ${config.mcs.index}`
    )

    // 设置RB分配
    await this.scpiClient.command(
      `CONFigure:NRSub6:DL:PDSCH:RBALloc:STARt ${config.resource_allocation.start_rb}`
    )
    await this.scpiClient.command(
      `CONFigure:NRSub6:DL:PDSCH:RBALloc:NRBs ${config.resource_allocation.num_rbs}`
    )

    await this.scpiClient.command('CONFigure:NRSub6:DL:APPLy')
  }

  async startDLTraffic(trafficConfig: TrafficConfig): Promise<void> {
    // 配置数据源
    await this.scpiClient.command(
      `CONFigure:NRSub6:DATA:DL:PATTern ${trafficConfig.pattern || 'PRBS'}`
    )

    if (trafficConfig.target_throughput_mbps) {
      // UXM会自动调整MCS以达到目标吞吐量
      await this.scpiClient.command(
        `CONFigure:NRSub6:DATA:DL:TARGet ${trafficConfig.target_throughput_mbps}Mbps`
      )
    }

    // 启动下行数据
    await this.scpiClient.command('CONFigure:NRSub6:DATA:DL:STATe ON')
  }

  async getThroughput(): Promise<ThroughputMeasurement> {
    const dlThroughput = parseFloat(
      await this.scpiClient.query('FETCh:NRSub6:DATA:DL:THRoughput?')
    )
    const ulThroughput = parseFloat(
      await this.scpiClient.query('FETCh:NRSub6:DATA:UL:THRoughput?')
    )

    const dlBytes = parseFloat(
      await this.scpiClient.query('FETCh:NRSub6:DATA:DL:BYTes?')
    )
    const ulBytes = parseFloat(
      await this.scpiClient.query('FETCh:NRSub6:DATA:UL:BYTes?')
    )

    return {
      timestamp: new Date(),
      downlink: {
        instantaneous_mbps: dlThroughput,
        average_mbps: dlThroughput,  // UXM返回平均值
        peak_mbps: dlThroughput,
        total_bytes: dlBytes
      },
      uplink: {
        instantaneous_mbps: ulThroughput,
        average_mbps: ulThroughput,
        peak_mbps: ulThroughput,
        total_bytes: ulBytes
      },
      duration_seconds: 0
    }
  }

  async getRadioMeasurements(): Promise<RadioMeasurements> {
    const rsrp = parseFloat(
      await this.scpiClient.query('FETCh:NRSub6:MEAS:RSRP?')
    )
    const rsrq = parseFloat(
      await this.scpiClient.query('FETCh:NRSub6:MEAS:RSRQ?')
    )
    const sinr = parseFloat(
      await this.scpiClient.query('FETCh:NRSub6:MEAS:SINR?')
    )

    return {
      timestamp: new Date(),
      rsrp_dbm: rsrp,
      rsrq_db: rsrq,
      sinr_db: sinr
    }
  }

  async startContinuousMeasurement(interval_ms: number): Promise<void> {
    this.measurementTimer = setInterval(async () => {
      try {
        const throughput = await this.getThroughput()
        const radio = await this.getRadioMeasurements()

        // 触发事件或回调
        this.emit('measurement', { throughput, radio })
      } catch (error) {
        console.error('测量错误:', error)
      }
    }, interval_ms)
  }

  async stopContinuousMeasurement(): Promise<void> {
    if (this.measurementTimer) {
      clearInterval(this.measurementTimer)
      this.measurementTimer = undefined
    }
  }

  private async waitForOperationComplete(): Promise<void> {
    const timeout = 60000
    const startTime = Date.now()

    while (true) {
      const opc = await this.scpiClient.query('*OPC?')
      if (opc === '1') {
        return
      }

      if (Date.now() - startTime > timeout) {
        throw new Error('操作超时')
      }

      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
}
```

### 4.2 R&S CMW500 Adapter

```typescript
class RohdeSchwarzCMW500Adapter implements IBaseStationEmulator {
  private scpiClient: SCPIClient

  async configureCellLTE(config: LTECellConfig): Promise<void> {
    // R&S命令语法
    await this.scpiClient.command(
      `CONFigure:LTE:SIGN:CELL:BAND OB${config.frequency.band}`
    )
    await this.scpiClient.command(
      `CONFigure:LTE:SIGN:CELL:DL:EARFCN ${config.frequency.dl_earfcn}`
    )
    await this.scpiClient.command(
      `CONFigure:LTE:SIGN:CELL:BANDwidth:DL BW${config.frequency.bandwidth_mhz}_00`
    )

    // PCI配置
    await this.scpiClient.command(
      `CONFigure:LTE:SIGN:CELL:PCI ${config.identity.pci}`
    )

    // MIMO配置
    await this.scpiClient.command(
      `CONFigure:LTE:SIGN:DMODe:TM TM${config.mimo.dl_transmission_mode}`
    )

    // 应用配置
    await this.scpiClient.command('CONFigure:LTE:SIGN:CELL:APPLy')
  }

  // ... 其他方法实现类似 ...
}
```

### 4.3 Virtual Mock BS Adapter

```typescript
class VirtualMockBSAdapter implements IBaseStationEmulator {
  private mockState: {
    cellActive: boolean
    ueRegistered: boolean
    trafficActive: boolean
    currentThroughput: number
  } = {
    cellActive: false,
    ueRegistered: false,
    trafficActive: false,
    currentThroughput: 0
  }

  async connect(config: BSConnectionConfig): Promise<void> {
    // Mock连接，立即成功
    console.log('Mock BS connected')
  }

  async configureCellNR(config: NRCellConfig): Promise<void> {
    // Mock配置，存储配置但不执行实际操作
    console.log('Mock cell configured:', config)
  }

  async activateCell(): Promise<void> {
    this.mockState.cellActive = true
  }

  async registerUE(ueConfig: UEConfig): Promise<UEHandle> {
    this.mockState.ueRegistered = true
    return { id: 'mock_ue_1' }
  }

  async startDLTraffic(trafficConfig: TrafficConfig): Promise<void> {
    this.mockState.trafficActive = true
    this.mockState.currentThroughput = trafficConfig.target_throughput_mbps || 100
  }

  async getThroughput(): Promise<ThroughputMeasurement> {
    // 返回模拟吞吐量（带随机波动）
    const variation = (Math.random() - 0.5) * 10  // ±5 Mbps
    const throughput = this.mockState.currentThroughput + variation

    return {
      timestamp: new Date(),
      downlink: {
        instantaneous_mbps: throughput,
        average_mbps: this.mockState.currentThroughput,
        peak_mbps: this.mockState.currentThroughput * 1.1,
        total_bytes: 0
      },
      uplink: {
        instantaneous_mbps: throughput * 0.5,
        average_mbps: this.mockState.currentThroughput * 0.5,
        peak_mbps: this.mockState.currentThroughput * 0.55,
        total_bytes: 0
      },
      duration_seconds: 0
    }
  }

  async getRadioMeasurements(): Promise<RadioMeasurements> {
    // 返回模拟测量值
    return {
      timestamp: new Date(),
      rsrp_dbm: -80 + (Math.random() - 0.5) * 10,
      rsrq_db: -10 + (Math.random() - 0.5) * 4,
      sinr_db: 20 + (Math.random() - 0.5) * 10
    }
  }
}
```

## 5. 适配器工厂

```typescript
class BaseStationEmulatorFactory {
  static createEmulator(config: BSConnectionConfig): IBaseStationEmulator {
    switch (config.vendor) {
      case 'Keysight':
        if (config.model.includes('UXM')) {
          return new KeysightUXMAdapter()
        }
        throw new Error(`不支持的Keysight型号: ${config.model}`)

      case 'R&S':
        if (config.model.includes('CMW')) {
          return new RohdeSchwarzCMW500Adapter()
        }
        throw new Error(`不支持的R&S型号: ${config.model}`)

      case 'Anritsu':
        return new AnritsuMT8000AAdapter()

      case 'Virtual':
        return new VirtualMockBSAdapter()

      default:
        throw new Error(`不支持的厂商: ${config.vendor}`)
    }
  }
}
```

## 6. 数据库模式

```sql
CREATE TABLE base_station_emulators (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) UNIQUE NOT NULL,
  vendor VARCHAR(100) NOT NULL,
  model VARCHAR(255) NOT NULL,

  connection_type VARCHAR(50),
  connection_host VARCHAR(255),
  connection_port INTEGER,

  capabilities JSONB,  -- {technologies: ['5G_NR', 'LTE'], max_bandwidth_mhz: 400}

  priority INTEGER DEFAULT 10,
  enabled BOOLEAN DEFAULT TRUE,

  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE bs_test_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  emulator_id UUID REFERENCES base_station_emulators(id),

  -- 小区配置快照
  cell_config JSONB,

  -- UE信息
  ue_registered BOOLEAN,
  ue_imsi VARCHAR(20),

  -- 测试配置
  test_type VARCHAR(100),  -- 'throughput', 'eis', 'bler'
  dl_scheduling JSONB,
  ul_scheduling JSONB,

  -- 会话时间
  session_start TIMESTAMP DEFAULT NOW(),
  session_end TIMESTAMP,

  -- 结果摘要
  avg_dl_throughput_mbps FLOAT,
  avg_ul_throughput_mbps FLOAT,
  avg_rsrp_dbm FLOAT,
  avg_sinr_db FLOAT,

  INDEX idx_emulator_id (emulator_id),
  INDEX idx_session_start (session_start)
);
```

## 7. REST API

```typescript
// POST /api/v1/base-stations/{id}/configure-cell
interface ConfigureCellRequest {
  technology: '5G_NR' | 'LTE'
  config: NRCellConfig | LTECellConfig
}

// POST /api/v1/base-stations/{id}/register-ue
interface RegisterUERequest {
  ue_config: UEConfig
}

interface RegisterUEResponse {
  ue_handle: UEHandle
  registration_time_ms: number
}

// POST /api/v1/base-stations/{id}/start-traffic
interface StartTrafficRequest {
  direction: 'downlink' | 'uplink' | 'both'
  traffic_config: TrafficConfig
}

// GET /api/v1/base-stations/{id}/measurements/current
interface CurrentMeasurementsResponse {
  throughput: ThroughputMeasurement
  bler: BLERMeasurement
  radio: RadioMeasurements
}

// WebSocket: /ws/base-stations/{id}/measurements
// 实时测量数据流
```

## 8. 实现计划

### Phase 1: 核心框架 (1周)
- [ ] IBaseStationEmulator接口
- [ ] 数据模型定义
- [ ] 适配器工厂

### Phase 2: Keysight UXM适配器 (1.5周)
- [ ] 连接和配置管理
- [ ] 呼叫流程实现
- [ ] 测量采集
- [ ] 测试

### Phase 3: Virtual Mock适配器 (3天)
- [ ] Mock实现
- [ ] 测试

### Phase 4: R&S CMW500适配器 (1周)
- [ ] 适配器实现
- [ ] 测试

### Phase 5: 数据库和API (3天)
- [ ] 数据库表
- [ ] REST API
- [ ] WebSocket实时数据

## 9. 总结

Base Station Emulator HAL为Meta-3D系统提供：

- **多厂商支持**: Keysight, R&S, Anritsu等主流设备
- **双模支持**: 5G NR + LTE
- **完整呼叫流程**: 从UE注册到数据传输
- **实时测量**: 吞吐量、BLER、RSRP/SINR
- **虚拟模式**: Mock BS用于开发和CI/CD

实现后，系统可灵活控制不同基站仿真器执行OTA测试。
