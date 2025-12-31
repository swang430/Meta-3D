# Channel Emulator HAL Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Hardware Abstraction Layer (硬件抽象层)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

信道仿真器硬件抽象层（Channel Emulator HAL）为不同厂商的信道仿真器提供统一的软件接口，使上层应用无需关心具体的硬件厂商和通信协议。

**核心价值**:
- **厂商无关**: 支持Keysight, Spirent, R&S, Anritsu等主流厂商
- **即插即用**: 更换硬件无需修改上层代码
- **配置简化**: 统一的3GPP信道模型配置接口
- **故障隔离**: HAL层处理硬件故障，防止系统崩溃

### 1.2 支持的信道仿真器

| 厂商 | 型号 | 通道数 | 带宽 | 通信接口 | 优先级 |
|------|------|-------|------|---------|-------|
| **Keysight** | PROPSIM F64 | 64 | 2 GHz | SCPI/TCP | P0 |
| **Spirent** | VR5 | 64 | 2 GHz | REST API | P0 |
| **R&S** | SMW200A | 32 | 2 GHz | SCPI/LAN | P1 |
| **Anritsu** | MT8000A | 32 | 1 GHz | SCPI/USB | P1 |
| **Virtual** | ChannelEngine | ∞ | N/A | Python API | P0 |

### 1.3 标准依据

- **3GPP TR 38.901**: Channel model for frequencies from 0.5 to 100 GHz
- **SCPI**: Standard Commands for Programmable Instruments
- **IEEE 488.2**: Standard Digital Interface for Programmable Instrumentation

## 2. 系统架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Test Engine  │  │ Calibration  │  │ Virtual Test │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Channel Emulator HAL                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Unified Interface Layer                     │   │
│  │  - IChannelEmulator (abstract interface)                │   │
│  │  - Common data models (ChannelConfig, ScenarioConfig)   │   │
│  │  - Error handling and logging                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Adapter Layer                               │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐           │   │
│  │  │  Keysight  │ │  Spirent   │ │    R&S     │           │   │
│  │  │  Adapter   │ │  Adapter   │ │  Adapter   │           │   │
│  │  └────────────┘ └────────────┘ └────────────┘           │   │
│  │  ┌────────────┐ ┌────────────┐                          │   │
│  │  │  Anritsu   │ │  Virtual   │                          │   │
│  │  │  Adapter   │ │  Adapter   │                          │   │
│  │  └────────────┘ └────────────┘                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Physical Hardware Layer                        │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                   │
│  │  Keysight  │ │  Spirent   │ │    R&S     │                   │
│  │  F64       │ │    VR5     │ │  SMW200A   │                   │
│  └────────────┘ └────────────┘ └────────────┘                   │
│  ┌────────────┐ ┌────────────┐                                  │
│  │  Anritsu   │ │ChannelEngine                                  │
│  │ MT8000A    │ │  (Python)  │                                  │
│  └────────────┘ └────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 统一接口层 (Unified Interface Layer)

提供厂商无关的抽象接口。

#### 2.2.2 适配器层 (Adapter Layer)

实现具体厂商的协议适配。

#### 2.2.3 连接管理器 (Connection Manager)

管理与硬件的网络连接、超时、重试。

#### 2.2.4 配置管理器 (Configuration Manager)

管理信道配置、场景参数、校准数据。

## 3. 统一接口设计

### 3.1 IChannelEmulator接口

```typescript
/**
 * 信道仿真器统一接口
 */
interface IChannelEmulator {
  // ============ 连接管理 ============
  /**
   * 连接到信道仿真器
   */
  connect(config: ConnectionConfig): Promise<void>

  /**
   * 断开连接
   */
  disconnect(): Promise<void>

  /**
   * 检查连接状态
   */
  isConnected(): boolean

  /**
   * 获取仪器信息
   */
  getInstrumentInfo(): Promise<InstrumentInfo>

  // ============ 信道配置 ============
  /**
   * 配置3GPP信道模型
   */
  configureChannel(config: ChannelConfiguration): Promise<void>

  /**
   * 获取当前信道配置
   */
  getChannelConfiguration(): Promise<ChannelConfiguration>

  /**
   * 设置探头权重（幅度、相位）
   */
  setProbeWeights(weights: ProbeWeight[]): Promise<void>

  /**
   * 获取探头权重
   */
  getProbeWeights(): Promise<ProbeWeight[]>

  // ============ 信道控制 ============
  /**
   * 启动信道仿真
   */
  start(): Promise<void>

  /**
   * 停止信道仿真
   */
  stop(): Promise<void>

  /**
   * 暂停信道仿真
   */
  pause(): Promise<void>

  /**
   * 恢复信道仿真
   */
  resume(): Promise<void>

  /**
   * 重置信道仿真器到初始状态
   */
  reset(): Promise<void>

  // ============ 状态监控 ============
  /**
   * 获取运行状态
   */
  getStatus(): Promise<EmulatorStatus>

  /**
   * 获取错误列表
   */
  getErrors(): Promise<EmulatorError[]>

  /**
   * 清除错误
   */
  clearErrors(): Promise<void>

  // ============ 高级功能 ============
  /**
   * 设置多普勒频移
   */
  setDopplerShift(dopplerHz: number): Promise<void>

  /**
   * 设置信道衰落
   */
  setFadingParameters(params: FadingParameters): Promise<void>

  /**
   * 加载信道场景文件
   */
  loadScenarioFile(filePath: string): Promise<void>

  /**
   * 保存当前配置到文件
   */
  saveConfiguration(filePath: string): Promise<void>
}
```

### 3.2 数据模型

#### 3.2.1 连接配置

```typescript
interface ConnectionConfig {
  // 厂商和型号
  vendor: 'Keysight' | 'Spirent' | 'R&S' | 'Anritsu' | 'Virtual'
  model: string  // e.g., 'PROPSIM_F64'

  // 连接参数
  connection: {
    type: 'TCP' | 'USB' | 'GPIB' | 'VXI11'
    host?: string  // IP address for TCP
    port?: number  // TCP port
    timeout_ms?: number  // Default 30000
  }

  // 认证（如果需要）
  authentication?: {
    username?: string
    password?: string
    api_key?: string
  }
}
```

#### 3.2.2 仪器信息

```typescript
interface InstrumentInfo {
  vendor: string
  model: string
  serial_number: string
  firmware_version: string
  hardware_version: string

  capabilities: {
    max_channels: number
    max_bandwidth_mhz: number
    supported_frequencies_ghz: [number, number]  // [min, max]
    supported_3gpp_models: string[]  // ['UMa', 'UMi', 'InH', ...]
    max_taps: number  // 最大抽头数
    max_doppler_hz: number
  }
}
```

#### 3.2.3 信道配置

```typescript
interface ChannelConfiguration {
  // 场景类型
  scenario: {
    type: '3GPP_TR_38.901'
    model: 'UMa' | 'UMi' | 'RMa' | 'InH' | 'CDL' | 'TDL'
    condition?: 'LOS' | 'NLOS' | 'O2I'
  }

  // 频率参数
  frequency: {
    carrier_frequency_ghz: number
    bandwidth_mhz: number
  }

  // 几何参数
  geometry: {
    distance_2d_m: number
    tx_height_m: number
    rx_height_m: number
    street_width_m?: number  // UMi特有
    building_height_m?: number  // UMi特有
  }

  // 时延参数
  delay: {
    rms_delay_spread_ns: number
    max_delay_ns: number
    num_clusters: number
  }

  // 角度参数
  angle: {
    aoa_mean_deg: number  // Angle of Arrival
    aoa_spread_deg: number
    aod_mean_deg: number  // Angle of Departure
    aod_spread_deg: number
  }

  // 多普勒参数
  doppler: {
    velocity_kmh: number
    direction_deg: number  // 移动方向
    spectrum_type: 'classical' | 'flat' | 'custom'
  }

  // MIMO配置
  mimo: {
    num_tx_antennas: number
    num_rx_antennas: number
    tx_antenna_spacing_lambda: number
    rx_antenna_spacing_lambda: number
    correlation_matrix?: number[][]  // 可选：自定义相关矩阵
  }
}
```

#### 3.2.4 探头权重

```typescript
interface ProbeWeight {
  probe_id: number
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP'

  // 复数权重
  weight: {
    magnitude: number  // 线性幅度
    phase_deg: number  // 相位（度）
  }

  // 或者等效的
  weight_complex?: {
    real: number
    imag: number
  }

  enabled: boolean
}
```

#### 3.2.5 仿真器状态

```typescript
interface EmulatorStatus {
  state: 'idle' | 'configured' | 'running' | 'paused' | 'error'

  // 当前配置
  current_scenario?: string
  current_frequency_ghz?: number

  // 运行时间
  uptime_seconds: number
  run_time_seconds: number

  // 健康状态
  health: {
    temperature_celsius: number
    power_consumption_w: number
    errors_count: number
    warnings_count: number
  }

  // 性能指标
  performance: {
    cpu_usage_percent: number
    memory_usage_percent: number
    channel_processing_rate_mhz: number
  }
}
```

#### 3.2.6 仿真器错误

```typescript
interface EmulatorError {
  error_code: string
  error_message: string
  severity: 'critical' | 'error' | 'warning' | 'info'
  timestamp: Date
  details?: {
    [key: string]: any
  }
}
```

## 4. 适配器实现

### 4.1 Keysight PROPSIM F64 Adapter

#### 4.1.1 连接实现

```typescript
class KeysightPropsimAdapter implements IChannelEmulator {
  private scpiClient: SCPIClient
  private config: ConnectionConfig
  private isConnectedFlag: boolean = false

  async connect(config: ConnectionConfig): Promise<void> {
    this.config = config

    // 创建SCPI客户端
    this.scpiClient = new SCPIClient({
      host: config.connection.host!,
      port: config.connection.port || 5025,  // Keysight默认端口
      timeout: config.connection.timeout_ms || 30000
    })

    try {
      await this.scpiClient.connect()

      // 验证仪器身份
      const idn = await this.scpiClient.query('*IDN?')
      if (!idn.includes('Keysight') && !idn.includes('PROPSIM')) {
        throw new Error(`连接到的仪器不是Keysight PROPSIM: ${idn}`)
      }

      // 清除错误队列
      await this.scpiClient.command('*CLS')

      this.isConnectedFlag = true
    } catch (error) {
      throw new Error(`连接Keysight PROPSIM失败: ${error.message}`)
    }
  }

  async disconnect(): Promise<void> {
    if (this.scpiClient) {
      await this.scpiClient.disconnect()
    }
    this.isConnectedFlag = false
  }

  isConnected(): boolean {
    return this.isConnectedFlag
  }

  async getInstrumentInfo(): Promise<InstrumentInfo> {
    const idn = await this.scpiClient.query('*IDN?')
    const parts = idn.split(',')

    return {
      vendor: 'Keysight',
      model: parts[1],
      serial_number: parts[2],
      firmware_version: parts[3],
      hardware_version: await this.scpiClient.query('SYSTem:HARDware:VERSion?'),

      capabilities: {
        max_channels: 64,
        max_bandwidth_mhz: 2000,
        supported_frequencies_ghz: [0.4, 40],
        supported_3gpp_models: ['UMa', 'UMi', 'RMa', 'InH', 'CDL-A', 'CDL-B', 'CDL-C', 'CDL-D', 'CDL-E', 'TDL-A', 'TDL-B', 'TDL-C'],
        max_taps: 24,
        max_doppler_hz: 2000
      }
    }
  }

  async configureChannel(config: ChannelConfiguration): Promise<void> {
    // 1. 设置频率
    await this.scpiClient.command(
      `SOURce:FREQuency:CARRier ${config.frequency.carrier_frequency_ghz}GHz`
    )
    await this.scpiClient.command(
      `SOURce:BANDwidth ${config.frequency.bandwidth_mhz}MHz`
    )

    // 2. 选择3GPP模型
    const modelCmd = this.map3GPPModelToKeysightCommand(config.scenario)
    await this.scpiClient.command(modelCmd)

    // 3. 设置几何参数
    await this.scpiClient.command(
      `CHANnel:PROPagation:DISTance ${config.geometry.distance_2d_m}m`
    )
    await this.scpiClient.command(
      `CHANnel:PROPagation:TXHeight ${config.geometry.tx_height_m}m`
    )
    await this.scpiClient.command(
      `CHANnel:PROPagation:RXHeight ${config.geometry.rx_height_m}m`
    )

    // 4. 设置多普勒
    await this.scpiClient.command(
      `CHANnel:DOPPler:VELocity ${config.doppler.velocity_kmh}kmh`
    )
    await this.scpiClient.command(
      `CHANnel:DOPPler:DIRection ${config.doppler.direction_deg}deg`
    )

    // 5. 设置MIMO配置
    await this.scpiClient.command(
      `CHANnel:MIMO:TX:ANTennas ${config.mimo.num_tx_antennas}`
    )
    await this.scpiClient.command(
      `CHANnel:MIMO:RX:ANTennas ${config.mimo.num_rx_antennas}`
    )

    // 6. 应用配置
    await this.scpiClient.command('CHANnel:APPLy')

    // 7. 等待配置完成
    await this.waitForOperationComplete()
  }

  private map3GPPModelToKeysightCommand(scenario: ChannelConfiguration['scenario']): string {
    const model = scenario.model
    const condition = scenario.condition || ''

    // Keysight PROPSIM的3GPP模型命令映射
    const modelMap: { [key: string]: string } = {
      'UMa_LOS': 'CHANnel:MODel:SELect "3GPP_38.901_UMa_LOS"',
      'UMa_NLOS': 'CHANnel:MODel:SELect "3GPP_38.901_UMa_NLOS"',
      'UMi_LOS': 'CHANnel:MODel:SELect "3GPP_38.901_UMi_StreetCanyon_LOS"',
      'UMi_NLOS': 'CHANnel:MODel:SELect "3GPP_38.901_UMi_StreetCanyon_NLOS"',
      'InH_LOS': 'CHANnel:MODel:SELect "3GPP_38.901_InH_OfficeOpen_LOS"',
      'InH_NLOS': 'CHANnel:MODel:SELect "3GPP_38.901_InH_OfficeOpen_NLOS"',
      'CDL-A': 'CHANnel:MODel:SELect "3GPP_38.901_CDL_A"',
      'CDL-B': 'CHANnel:MODel:SELect "3GPP_38.901_CDL_B"',
      'CDL-C': 'CHANnel:MODel:SELect "3GPP_38.901_CDL_C"',
      'CDL-D': 'CHANnel:MODel:SELect "3GPP_38.901_CDL_D"',
      'CDL-E': 'CHANnel:MODel:SELect "3GPP_38.901_CDL_E"',
    }

    const key = condition ? `${model}_${condition}` : model
    const command = modelMap[key]

    if (!command) {
      throw new Error(`不支持的3GPP模型: ${key}`)
    }

    return command
  }

  async setProbeWeights(weights: ProbeWeight[]): Promise<void> {
    for (const weight of weights) {
      // Keysight: 探头从1开始编号
      const probeNum = weight.probe_id + 1

      // 设置幅度（dB）
      const amplitudeDb = 20 * Math.log10(weight.weight.magnitude)
      await this.scpiClient.command(
        `SOURce:PROBe${probeNum}:AMPLitude ${amplitudeDb}dB`
      )

      // 设置相位
      await this.scpiClient.command(
        `SOURce:PROBe${probeNum}:PHASe ${weight.weight.phase_deg}deg`
      )

      // 启用/禁用
      await this.scpiClient.command(
        `SOURce:PROBe${probeNum}:STATe ${weight.enabled ? 'ON' : 'OFF'}`
      )
    }
  }

  async start(): Promise<void> {
    await this.scpiClient.command('CHANnel:STARt')
    await this.waitForOperationComplete()
  }

  async stop(): Promise<void> {
    await this.scpiClient.command('CHANnel:STOP')
    await this.waitForOperationComplete()
  }

  async getStatus(): Promise<EmulatorStatus> {
    const state = await this.scpiClient.query('CHANnel:STATe?')
    const uptime = parseFloat(await this.scpiClient.query('SYSTem:UPTime?'))
    const runTime = parseFloat(await this.scpiClient.query('CHANnel:RUNTime?'))

    return {
      state: this.mapKeysightStateToUnified(state),
      uptime_seconds: uptime,
      run_time_seconds: runTime,

      health: {
        temperature_celsius: parseFloat(await this.scpiClient.query('SYSTem:TEMPerature?')),
        power_consumption_w: 0,  // PROPSIM不提供此信息
        errors_count: parseInt(await this.scpiClient.query('SYSTem:ERRor:COUNt?')),
        warnings_count: 0
      },

      performance: {
        cpu_usage_percent: parseFloat(await this.scpiClient.query('SYSTem:CPU:USAge?')),
        memory_usage_percent: parseFloat(await this.scpiClient.query('SYSTem:MEMory:USAge?')),
        channel_processing_rate_mhz: parseFloat(await this.scpiClient.query('CHANnel:PROCessing:RATE?'))
      }
    }
  }

  private async waitForOperationComplete(): Promise<void> {
    const timeout = 30000  // 30秒超时
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

  private mapKeysightStateToUnified(state: string): EmulatorStatus['state'] {
    const stateMap: { [key: string]: EmulatorStatus['state'] } = {
      'IDLE': 'idle',
      'CONF': 'configured',
      'RUN': 'running',
      'PAUS': 'paused',
      'ERR': 'error'
    }
    return stateMap[state.toUpperCase()] || 'idle'
  }

  // ... 其他方法实现 ...
}
```

### 4.2 Spirent VR5 Adapter

```typescript
class SpirentVR5Adapter implements IChannelEmulator {
  private restClient: RESTClient
  private config: ConnectionConfig
  private sessionId?: string

  async connect(config: ConnectionConfig): Promise<void> {
    this.config = config

    // Spirent VR5 使用REST API
    this.restClient = new RESTClient({
      baseURL: `http://${config.connection.host}:${config.connection.port || 8080}`,
      timeout: config.connection.timeout_ms || 30000,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${config.authentication?.api_key}`
      }
    })

    try {
      // 创建会话
      const response = await this.restClient.post('/api/v1/sessions', {
        name: 'Meta-3D_Session',
        description: 'MPAC OTA Test Session'
      })

      this.sessionId = response.data.session_id
    } catch (error) {
      throw new Error(`连接Spirent VR5失败: ${error.message}`)
    }
  }

  async configureChannel(config: ChannelConfiguration): Promise<void> {
    // Spirent REST API配置
    const spirentConfig = {
      scenario: {
        type: `3GPP_TR38.901_${config.scenario.model}_${config.scenario.condition}`,
        parameters: {
          frequency_ghz: config.frequency.carrier_frequency_ghz,
          bandwidth_mhz: config.frequency.bandwidth_mhz,
          distance_m: config.geometry.distance_2d_m,
          velocity_kmh: config.doppler.velocity_kmh,
          tx_antennas: config.mimo.num_tx_antennas,
          rx_antennas: config.mimo.num_rx_antennas
        }
      }
    }

    await this.restClient.put(
      `/api/v1/sessions/${this.sessionId}/channel`,
      spirentConfig
    )
  }

  async setProbeWeights(weights: ProbeWeight[]): Promise<void> {
    const probeConfig = weights.map(w => ({
      probe_id: w.probe_id,
      amplitude_linear: w.weight.magnitude,
      phase_deg: w.weight.phase_deg,
      enabled: w.enabled
    }))

    await this.restClient.put(
      `/api/v1/sessions/${this.sessionId}/probes`,
      { probes: probeConfig }
    )
  }

  async start(): Promise<void> {
    await this.restClient.post(
      `/api/v1/sessions/${this.sessionId}/control/start`,
      {}
    )
  }

  // ... 其他方法实现 ...
}
```

### 4.3 Virtual (ChannelEngine) Adapter

```typescript
class VirtualChannelEngineAdapter implements IChannelEmulator {
  private channelEngineClient: ChannelEngineClient
  private currentConfig?: ChannelConfiguration

  async connect(config: ConnectionConfig): Promise<void> {
    // ChannelEngine是本地Python服务
    this.channelEngineClient = new ChannelEngineClient({
      baseUrl: config.connection.host || 'http://localhost:8000'
    })

    // 验证服务可用
    const health = await this.channelEngineClient.healthCheck()
    if (!health.ok) {
      throw new Error('ChannelEngine服务不可用')
    }
  }

  async configureChannel(config: ChannelConfiguration): Promise<void> {
    this.currentConfig = config
    // ChannelEngine的配置会在start()时应用
  }

  async setProbeWeights(weights: ProbeWeight[]): Promise<void> {
    // Virtual模式下，探头权重由ChannelEngine自动计算
    // 这里可以存储用户覆盖的权重
  }

  async start(): Promise<void> {
    if (!this.currentConfig) {
      throw new Error('未配置信道')
    }

    // 调用ChannelEngine API生成探头权重
    const request: ProbeWeightRequest = {
      scenario: {
        type: this.currentConfig.scenario.model as any,
        condition: this.currentConfig.scenario.condition as any,
        fc_ghz: this.currentConfig.frequency.carrier_frequency_ghz,
        distance_2d: this.currentConfig.geometry.distance_2d_m,
        bs_height: this.currentConfig.geometry.tx_height_m,
        ut_height: this.currentConfig.geometry.rx_height_m
      },
      probe_array: {
        num_probes: 32,  // 从系统配置获取
        radius: 3.0,
        height: 0,
        layout: 'ring'
      },
      mimo_config: {
        tx_antennas: this.currentConfig.mimo.num_tx_antennas,
        rx_antennas: this.currentConfig.mimo.num_rx_antennas,
        tx_antenna_spacing: this.currentConfig.mimo.tx_antenna_spacing_lambda,
        rx_antenna_spacing: this.currentConfig.mimo.rx_antenna_spacing_lambda
      }
    }

    const result = await this.channelEngineClient.generateProbeWeights(request)

    // Virtual模式下，"start"意味着权重已生成并可用
  }

  async getStatus(): Promise<EmulatorStatus> {
    return {
      state: 'running',
      uptime_seconds: 0,
      run_time_seconds: 0,
      health: {
        temperature_celsius: 25,
        power_consumption_w: 0,
        errors_count: 0,
        warnings_count: 0
      },
      performance: {
        cpu_usage_percent: 0,
        memory_usage_percent: 0,
        channel_processing_rate_mhz: 0
      }
    }
  }

  // ... 其他方法实现 ...
}
```

## 5. 适配器工厂

```typescript
class ChannelEmulatorFactory {
  /**
   * 根据配置创建适配器实例
   */
  static createEmulator(config: ConnectionConfig): IChannelEmulator {
    switch (config.vendor) {
      case 'Keysight':
        return new KeysightPropsimAdapter()

      case 'Spirent':
        return new SpirentVR5Adapter()

      case 'R&S':
        return new RohdeSchwarzAdapter()

      case 'Anritsu':
        return new AnritsuAdapter()

      case 'Virtual':
        return new VirtualChannelEngineAdapter()

      default:
        throw new Error(`不支持的信道仿真器厂商: ${config.vendor}`)
    }
  }

  /**
   * 自动检测并连接
   */
  static async autoDetectAndConnect(
    configs: ConnectionConfig[]
  ): Promise<IChannelEmulator> {
    for (const config of configs) {
      try {
        const emulator = this.createEmulator(config)
        await emulator.connect(config)
        return emulator
      } catch (error) {
        console.warn(`连接 ${config.vendor} ${config.model} 失败: ${error.message}`)
        continue
      }
    }

    throw new Error('无法连接到任何信道仿真器')
  }
}
```

## 6. 配置管理

### 6.1 配置文件

```yaml
# channel_emulators.yaml

emulators:
  - name: "Primary_Keysight_F64"
    vendor: "Keysight"
    model: "PROPSIM_F64"
    connection:
      type: "TCP"
      host: "192.168.1.100"
      port: 5025
      timeout_ms: 30000
    priority: 1  # 优先使用
    enabled: true

  - name: "Backup_Spirent_VR5"
    vendor: "Spirent"
    model: "VR5"
    connection:
      type: "TCP"
      host: "192.168.1.101"
      port: 8080
    authentication:
      api_key: "your_api_key_here"
    priority: 2
    enabled: true

  - name: "Virtual_ChannelEngine"
    vendor: "Virtual"
    model: "ChannelEngine_v1.0"
    connection:
      type: "TCP"
      host: "http://localhost"
      port: 8000
    priority: 3  # 最低优先级，用于虚拟测试
    enabled: true

# 默认连接策略
connection_strategy:
  auto_detect: true  # 自动检测并连接最高优先级的可用仿真器
  failover: true  # 主仿真器失败时自动切换到备份
  health_check_interval_seconds: 60
```

### 6.2 配置加载器

```typescript
class ChannelEmulatorConfigLoader {
  static loadConfig(filePath: string): ChannelEmulatorConfig {
    const yaml = fs.readFileSync(filePath, 'utf8')
    const config = YAML.parse(yaml)

    return {
      emulators: config.emulators
        .filter((e: any) => e.enabled)
        .sort((a: any, b: any) => a.priority - b.priority),
      connection_strategy: config.connection_strategy
    }
  }
}
```

## 7. 数据库模式

```sql
CREATE TABLE channel_emulators (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) UNIQUE NOT NULL,
  vendor VARCHAR(100) NOT NULL,
  model VARCHAR(255) NOT NULL,

  -- 连接配置
  connection_type VARCHAR(50),
  connection_host VARCHAR(255),
  connection_port INTEGER,

  -- 认证（加密存储）
  api_key_encrypted TEXT,

  -- 优先级
  priority INTEGER DEFAULT 10,
  enabled BOOLEAN DEFAULT TRUE,

  -- 元数据
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),

  INDEX idx_priority (priority),
  INDEX idx_enabled (enabled)
);

CREATE TABLE channel_emulator_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  emulator_id UUID REFERENCES channel_emulators(id),

  -- 会话信息
  session_start TIMESTAMP DEFAULT NOW(),
  session_end TIMESTAMP,
  duration_seconds INTEGER,

  -- 配置快照
  channel_configuration JSONB,

  -- 状态
  final_status VARCHAR(50),  -- 'completed', 'error', 'interrupted'
  error_message TEXT,

  INDEX idx_emulator_id (emulator_id),
  INDEX idx_session_start (session_start)
);
```

## 8. REST API

```typescript
// GET /api/v1/channel-emulators
interface ListEmulatorsResponse {
  emulators: Array<{
    id: string
    name: string
    vendor: string
    model: string
    status: 'connected' | 'disconnected' | 'error'
    priority: number
  }>
}

// POST /api/v1/channel-emulators/{id}/connect
interface ConnectEmulatorRequest {
  // 可选覆盖配置
  connection_override?: Partial<ConnectionConfig>
}

// POST /api/v1/channel-emulators/{id}/configure
interface ConfigureChannelRequest {
  configuration: ChannelConfiguration
}

// POST /api/v1/channel-emulators/{id}/set-probe-weights
interface SetProbeWeightsRequest {
  weights: ProbeWeight[]
}

// GET /api/v1/channel-emulators/{id}/status
interface GetEmulatorStatusResponse {
  emulator_id: string
  status: EmulatorStatus
  last_updated: Date
}
```

## 9. 实现计划

### Phase 1: 核心框架 (1周)

- [ ] IChannelEmulator接口定义
- [ ] 数据模型定义
- [ ] 适配器工厂
- [ ] 配置加载器

### Phase 2: Keysight适配器 (1周)

- [ ] SCPI客户端实现
- [ ] KeysightPropsimAdapter完整实现
- [ ] 单元测试和集成测试

### Phase 3: Virtual适配器 (3天)

- [ ] VirtualChannelEngineAdapter实现
- [ ] ChannelEngine集成
- [ ] 测试

### Phase 4: Spirent适配器 (1周)

- [ ] REST客户端实现
- [ ] SpirentVR5Adapter实现
- [ ] 测试

### Phase 5: 数据库和API (3天)

- [ ] 数据库表创建
- [ ] REST API实现
- [ ] 文档

## 10. 总结

Channel Emulator HAL为Meta-3D系统提供：

- **厂商无关**: 支持5+主流厂商信道仿真器
- **统一接口**: 简化上层应用开发
- **自动检测**: 自动连接可用仿真器
- **故障切换**: 主仿真器失败自动切换备份
- **虚拟支持**: 集成ChannelEngine实现零硬件成本测试

实现后，系统可灵活切换不同硬件，降低供应商锁定风险，提高系统可靠性。
