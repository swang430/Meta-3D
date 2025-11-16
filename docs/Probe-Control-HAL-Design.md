# Probe Control HAL Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Hardware Abstraction Layer (硬件抽象层)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

探头控制硬件抽象层（Probe Control HAL）管理MPAC系统中的探头天线阵列，包括RF开关矩阵、探头供电、探头选择等硬件控制。

**核心功能**:
- **RF路径切换**: 控制RF开关矩阵，路由信号到指定探头
- **探头使能控制**: 独立开关每个探头
- **功率分配**: 控制每个探头的输出功率
- **故障检测**: 探测探头故障和RF链路异常

### 1.2 硬件组件

| 组件类型 | 厂商/型号 | 功能 | 数量 | 优先级 |
|---------|---------|------|------|-------|
| **RF开关矩阵** | Mini-Circuits USB-SP16T-63 | 1:16射频开关 | 2-4 | P0 |
| **功率放大器** | RFHIC RPA1616M29G | 探头功放 | 32+ | P0 |
| **衰减器** | Weinschel/Aeroflex | 可编程衰减器 | 32+ | P1 |
| **电源控制器** | Devantech USB-RLY08 | 继电器控制 | 4 | P0 |
| **GPIO扩展板** | MCP23017 I2C | 数字IO扩展 | 2 | P0 |

### 1.3 标准依据

- **IEEE 488.2**: Standard Digital Interface for Programmable Instrumentation
- **SCPI**: Standard Commands for Programmable Instruments (部分设备)
- **USB HID**: Human Interface Device (继电器、GPIO控制)

## 2. 系统架构

### 2.1 硬件拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│                    Channel Emulator Output                       │
│                    (64 RF Channels)                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   RF Switch Matrix (1:16)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Matrix #1   │  │  Matrix #2   │  │  Matrix #3   │           │
│  │  Ch 1-16     │  │  Ch 17-32    │  │  Ch 33-48    │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Power Amplifiers (Per Probe)                    │
│  ┌──────┐  ┌──────┐  ┌──────┐        ┌──────┐                   │
│  │ PA#1 │  │ PA#2 │  │ PA#3 │  ....  │ PA#32│                   │
│  └──────┘  └──────┘  └──────┘        └──────┘                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Programmable Attenuators (Optional)                 │
│  ┌──────┐  ┌──────┐  ┌──────┐        ┌──────┐                   │
│  │ ATT#1│  │ ATT#2│  │ ATT#3│  ....  │ATT#32│                   │
│  └──────┘  └──────┘  └──────┘        └──────┘                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Probe Antenna Array                           │
│  ┌──────┐  ┌──────┐  ┌──────┐        ┌──────┐                   │
│  │Probe1│  │Probe2│  │Probe3│  ....  │Probe │                   │
│  │ (V+H)│  │ (V+H)│  │ (V+H)│        │  32  │                   │
│  └──────┘  └──────┘  └──────┘        └──────┘                   │
└─────────────────────────────────────────────────────────────────┘

Control Connections:
┌─────────────┐
│ Control PC  │
│ (USB/LAN)   │
└──────┬──────┘
       │
       ├──► RF Switch Matrix (USB)
       ├──► Power Controllers (USB/Relay)
       ├──► GPIO Expanders (I2C/USB)
       └──► Attenuators (USB/SCPI)
```

### 2.2 软件架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
│  - Test Execution Engine                                         │
│  - Calibration Procedures                                        │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Probe Control HAL                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           Unified Probe Controller                       │   │
│  │  - setProbeEnabled(probeId, enabled)                     │   │
│  │  - setProbePower(probeId, powerDbm)                      │   │
│  │  - routeRFPath(channelId, probeId)                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Device Drivers                              │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐           │   │
│  │  │RF Switch   │ │Power Amp   │ │Attenuator  │           │   │
│  │  │Driver      │ │Driver      │ │Driver      │           │   │
│  │  └────────────┘ └────────────┘ └────────────┘           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Hardware Interface                            │
│  - USB HID                                                       │
│  - Serial (RS-232/RS-485)                                        │
│  - I2C/SPI                                                       │
│  - Ethernet (SCPI-over-LAN)                                      │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 统一接口设计

### 3.1 IProbeController接口

```typescript
/**
 * 探头控制器统一接口
 */
interface IProbeController {
  // ============ 初始化 ============
  /**
   * 初始化探头控制系统
   */
  initialize(config: ProbeControlConfig): Promise<void>

  /**
   * 关闭探头控制系统
   */
  shutdown(): Promise<void>

  /**
   * 获取系统状态
   */
  getSystemStatus(): Promise<ProbeSystemStatus>

  // ============ 探头控制 ============
  /**
   * 使能/禁用单个探头
   */
  setProbeEnabled(probeId: number, enabled: boolean): Promise<void>

  /**
   * 批量设置探头使能状态
   */
  setProbesEnabled(probeStates: Map<number, boolean>): Promise<void>

  /**
   * 获取探头使能状态
   */
  getProbeEnabled(probeId: number): Promise<boolean>

  /**
   * 设置探头输出功率
   */
  setProbePower(probeId: number, powerDbm: number): Promise<void>

  /**
   * 获取探头实际输出功率
   */
  getProbePower(probeId: number): Promise<number>

  /**
   * 设置探头衰减
   */
  setProbeAttenuation(probeId: number, attenuationDb: number): Promise<void>

  // ============ RF路径控制 ============
  /**
   * 路由RF信道到探头
   */
  routeRFPath(channelId: number, probeId: number, polarization: 'V' | 'H'): Promise<void>

  /**
   * 批量配置RF路由
   */
  configureRFRouting(routing: RFRoutingConfig): Promise<void>

  /**
   * 获取当前RF路由状态
   */
  getRFRouting(): Promise<RFRoutingConfig>

  /**
   * 断开所有RF连接
   */
  disconnectAllRF(): Promise<void>

  // ============ 故障检测 ============
  /**
   * 检测探头健康状态
   */
  checkProbeHealth(probeId: number): Promise<ProbeHealthStatus>

  /**
   * 扫描所有探头健康状态
   */
  scanAllProbes(): Promise<Map<number, ProbeHealthStatus>>

  /**
   * 获取故障列表
   */
  getFaults(): Promise<ProbeFault[]>

  /**
   * 清除故障
   */
  clearFaults(): Promise<void>

  // ============ 校准支持 ============
  /**
   * 进入校准模式
   */
  enterCalibrationMode(): Promise<void>

  /**
   * 退出校准模式
   */
  exitCalibrationMode(): Promise<void>

  /**
   * 设置校准参考路径
   */
  setCalibrationReference(probeId: number): Promise<void>
}
```

### 3.2 数据模型

#### 3.2.1 探头控制配置

```typescript
interface ProbeControlConfig {
  // 探头阵列配置
  probe_array: {
    num_probes: number
    layout: 'ring' | 'dual_ring' | 'cylindrical' | 'custom'
    polarizations: ('V' | 'H' | 'dual')[]
  }

  // RF开关矩阵配置
  rf_switches: Array<{
    device_type: 'Mini-Circuits' | 'Keysight' | 'Custom'
    model: string
    connection: {
      type: 'USB' | 'Serial' | 'LAN'
      address: string  // USB port, COM port, or IP address
    }
    num_inputs: number
    num_outputs: number
    switch_id: number  // 用于级联
  }>

  // 功率放大器配置
  power_amplifiers?: Array<{
    probe_id: number
    device_type: string
    max_power_dbm: number
    control_type: 'GPIO' | 'I2C' | 'SPI'
    control_address: string
  }>

  // 衰减器配置
  attenuators?: Array<{
    probe_id: number
    device_type: string
    max_attenuation_db: number
    step_size_db: number
    control_type: 'USB' | 'SCPI' | 'GPIO'
    control_address: string
  }>

  // 电源控制器
  power_controllers?: Array<{
    device_type: 'USB_Relay' | 'Network_PDU'
    connection: {
      type: 'USB' | 'LAN'
      address: string
    }
    controlled_probes: number[]  // 此控制器控制的探头ID列表
  }>
}
```

#### 3.2.2 RF路由配置

```typescript
interface RFRoutingConfig {
  routes: Array<{
    channel_id: number  // 信道仿真器输出通道
    probe_id: number
    polarization: 'V' | 'H'
    enabled: boolean
  }>
}
```

#### 3.2.3 探头健康状态

```typescript
interface ProbeHealthStatus {
  probe_id: number
  overall_health: 'healthy' | 'degraded' | 'faulty'

  checks: {
    rf_path_continuity: boolean  // RF路径连通性
    vswr: {
      value: number  // 电压驻波比
      acceptable: boolean  // < 2.0
    }
    power_output: {
      measured_dbm: number
      expected_dbm: number
      within_tolerance: boolean  // ±1 dB
    }
    amplifier_status?: {
      enabled: boolean
      temperature_celsius: number
      current_ma: number
    }
  }

  last_checked: Date
}
```

#### 3.2.4 探头故障

```typescript
interface ProbeFault {
  fault_id: string
  probe_id: number
  fault_type: 'rf_open' | 'rf_short' | 'high_vswr' | 'power_failure' | 'amplifier_overheat'
  severity: 'critical' | 'major' | 'minor'
  detected_at: Date
  description: string
  auto_recoverable: boolean
}
```

#### 3.2.5 系统状态

```typescript
interface ProbeSystemStatus {
  initialized: boolean
  calibration_mode: boolean

  probe_summary: {
    total_probes: number
    enabled_probes: number
    healthy_probes: number
    faulty_probes: number
  }

  rf_switches: Array<{
    switch_id: number
    connected: boolean
    active_paths: number
  }>

  power_controllers: Array<{
    controller_id: number
    connected: boolean
    all_relays_on: boolean
  }>

  faults: ProbeFault[]
}
```

## 4. 设备驱动实现

### 4.1 RF开关矩阵驱动 (Mini-Circuits)

```typescript
class MiniCircuitsRFSwitchDriver {
  private usbDevice: USBDevice
  private switchId: number

  async initialize(config: any): Promise<void> {
    // 打开USB HID设备
    const devices = await navigator.usb.getDevices()
    this.usbDevice = devices.find(d =>
      d.vendorId === 0x20CE &&  // Mini-Circuits VID
      d.productId === 0x0023    // USB-SP16T-63 PID
    )

    if (!this.usbDevice) {
      throw new Error('Mini-Circuits RF switch not found')
    }

    await this.usbDevice.open()
    await this.usbDevice.selectConfiguration(1)
    await this.usbDevice.claimInterface(0)

    this.switchId = config.switch_id
  }

  /**
   * 设置开关路径
   * @param input 输入端口 (通常固定为1)
   * @param output 输出端口 (1-16)
   */
  async setPath(input: number, output: number): Promise<void> {
    // Mini-Circuits命令格式: SETP=<output>
    const command = `SETP=${output}\r\n`
    const encoder = new TextEncoder()
    const data = encoder.encode(command)

    await this.usbDevice.transferOut(1, data)

    // 等待切换完成 (典型10ms)
    await new Promise(resolve => setTimeout(resolve, 20))
  }

  /**
   * 获取当前路径
   */
  async getPath(): Promise<number> {
    const command = 'SWPORT?\r\n'
    const encoder = new TextEncoder()
    const data = encoder.encode(command)

    await this.usbDevice.transferOut(1, data)

    const result = await this.usbDevice.transferIn(1, 64)
    const decoder = new TextDecoder()
    const response = decoder.decode(result.data)

    // 解析响应 "SWPORT=5"
    const match = response.match(/SWPORT=(\d+)/)
    return match ? parseInt(match[1]) : 0
  }

  async close(): Promise<void> {
    if (this.usbDevice) {
      await this.usbDevice.releaseInterface(0)
      await this.usbDevice.close()
    }
  }
}
```

### 4.2 电源控制器驱动 (USB继电器)

```typescript
class USBRelayDriver {
  private serialPort: SerialPort
  private relayStates: Map<number, boolean> = new Map()

  async initialize(config: any): Promise<void> {
    // 打开串口 (USB-RLY08使用串口通信)
    this.serialPort = await navigator.serial.requestPort()
    await this.serialPort.open({ baudRate: 9600 })

    // 初始化所有继电器为OFF
    for (let i = 1; i <= 8; i++) {
      await this.setRelay(i, false)
    }
  }

  /**
   * 设置继电器状态
   * @param relayNum 继电器编号 (1-8)
   * @param enabled true=ON, false=OFF
   */
  async setRelay(relayNum: number, enabled: boolean): Promise<void> {
    if (relayNum < 1 || relayNum > 8) {
      throw new Error(`Invalid relay number: ${relayNum}`)
    }

    // USB-RLY08命令: 0x64 + relay_num (ON), 0x6E + relay_num (OFF)
    const command = enabled ? 0x64 + relayNum : 0x6E + relayNum
    const writer = this.serialPort.writable.getWriter()

    await writer.write(new Uint8Array([command]))
    writer.releaseLock()

    this.relayStates.set(relayNum, enabled)

    // 继电器切换时间 ~10ms
    await new Promise(resolve => setTimeout(resolve, 15))
  }

  /**
   * 获取继电器状态
   */
  getRelayState(relayNum: number): boolean {
    return this.relayStates.get(relayNum) || false
  }

  /**
   * 设置所有继电器
   */
  async setAllRelays(enabled: boolean): Promise<void> {
    for (let i = 1; i <= 8; i++) {
      await this.setRelay(i, enabled)
    }
  }

  async close(): Promise<void> {
    // 关闭前先断开所有继电器
    await this.setAllRelays(false)

    if (this.serialPort) {
      await this.serialPort.close()
    }
  }
}
```

### 4.3 可编程衰减器驱动

```typescript
class ProgrammableAttenuatorDriver {
  private scpiClient: SCPIClient

  async initialize(config: any): Promise<void> {
    this.scpiClient = new SCPIClient({
      host: config.connection.address,
      port: 5025
    })
    await this.scpiClient.connect()
  }

  /**
   * 设置衰减值
   * @param attenuationDb 衰减值 (dB)
   */
  async setAttenuation(attenuationDb: number): Promise<void> {
    // 检查范围 (典型0-90 dB)
    if (attenuationDb < 0 || attenuationDb > 90) {
      throw new Error(`Attenuation out of range: ${attenuationDb} dB`)
    }

    await this.scpiClient.command(`ATT ${attenuationDb}`)
  }

  /**
   * 获取当前衰减值
   */
  async getAttenuation(): Promise<number> {
    const response = await this.scpiClient.query('ATT?')
    return parseFloat(response)
  }

  async close(): Promise<void> {
    if (this.scpiClient) {
      await this.scpiClient.disconnect()
    }
  }
}
```

## 5. 探头控制器实现

```typescript
class ProbeControllerImpl implements IProbeController {
  private config: ProbeControlConfig
  private rfSwitches: MiniCircuitsRFSwitchDriver[] = []
  private powerControllers: USBRelayDriver[] = []
  private attenuators: Map<number, ProgrammableAttenuatorDriver> = new Map()

  private probeStates: Map<number, {
    enabled: boolean
    power_dbm: number
    attenuation_db: number
    rf_route: { channel: number; polarization: 'V' | 'H' } | null
  }> = new Map()

  async initialize(config: ProbeControlConfig): Promise<void> {
    this.config = config

    // 1. 初始化RF开关矩阵
    for (const switchConfig of config.rf_switches) {
      const driver = new MiniCircuitsRFSwitchDriver()
      await driver.initialize(switchConfig)
      this.rfSwitches.push(driver)
    }

    // 2. 初始化电源控制器
    if (config.power_controllers) {
      for (const controllerConfig of config.power_controllers) {
        const driver = new USBRelayDriver()
        await driver.initialize(controllerConfig)
        this.powerControllers.push(driver)
      }
    }

    // 3. 初始化衰减器
    if (config.attenuators) {
      for (const attConfig of config.attenuators) {
        const driver = new ProgrammableAttenuatorDriver()
        await driver.initialize(attConfig)
        this.attenuators.set(attConfig.probe_id, driver)
      }
    }

    // 4. 初始化探头状态
    for (let i = 0; i < config.probe_array.num_probes; i++) {
      this.probeStates.set(i, {
        enabled: false,
        power_dbm: 0,
        attenuation_db: 0,
        rf_route: null
      })
    }

    console.log(`Probe control system initialized: ${config.probe_array.num_probes} probes`)
  }

  async setProbeEnabled(probeId: number, enabled: boolean): Promise<void> {
    const state = this.probeStates.get(probeId)
    if (!state) {
      throw new Error(`Invalid probe ID: ${probeId}`)
    }

    // 通过电源控制器开关探头
    const controllerIdx = Math.floor(probeId / 8)
    const relayNum = (probeId % 8) + 1

    if (controllerIdx < this.powerControllers.length) {
      await this.powerControllers[controllerIdx].setRelay(relayNum, enabled)
    }

    state.enabled = enabled
    this.probeStates.set(probeId, state)
  }

  async setProbesEnabled(probeStates: Map<number, boolean>): Promise<void> {
    // 批量操作，优化性能
    const promises: Promise<void>[] = []

    for (const [probeId, enabled] of probeStates) {
      promises.push(this.setProbeEnabled(probeId, enabled))
    }

    await Promise.all(promises)
  }

  async routeRFPath(channelId: number, probeId: number, polarization: 'V' | 'H'): Promise<void> {
    // 确定使用哪个RF开关
    // 假设每个开关16端口，级联使用
    const switchIdx = Math.floor(probeId / 16)
    const outputPort = (probeId % 16) + 1

    if (switchIdx >= this.rfSwitches.length) {
      throw new Error(`No RF switch available for probe ${probeId}`)
    }

    // 极化选择：V极化用奇数通道，H极化用偶数通道（示例）
    const inputChannel = polarization === 'V' ? channelId * 2 - 1 : channelId * 2

    await this.rfSwitches[switchIdx].setPath(1, outputPort)

    // 更新状态
    const state = this.probeStates.get(probeId)!
    state.rf_route = { channel: channelId, polarization }
    this.probeStates.set(probeId, state)
  }

  async configureRFRouting(routing: RFRoutingConfig): Promise<void> {
    // 批量配置
    for (const route of routing.routes) {
      if (route.enabled) {
        await this.routeRFPath(route.channel_id, route.probe_id, route.polarization)
      }
    }
  }

  async disconnectAllRF(): Promise<void> {
    // 将所有RF开关设置到断开状态（端口0或最大端口+1）
    for (const rfSwitch of this.rfSwitches) {
      await rfSwitch.setPath(1, 0)  // 0表示断开
    }

    // 清除路由状态
    for (const [probeId, state] of this.probeStates) {
      state.rf_route = null
      this.probeStates.set(probeId, state)
    }
  }

  async setProbeAttenuation(probeId: number, attenuationDb: number): Promise<void> {
    const attenuator = this.attenuators.get(probeId)
    if (!attenuator) {
      throw new Error(`No attenuator configured for probe ${probeId}`)
    }

    await attenuator.setAttenuation(attenuationDb)

    const state = this.probeStates.get(probeId)!
    state.attenuation_db = attenuationDb
    this.probeStates.set(probeId, state)
  }

  async checkProbeHealth(probeId: number): Promise<ProbeHealthStatus> {
    // 简化的健康检查
    const state = this.probeStates.get(probeId)

    return {
      probe_id: probeId,
      overall_health: 'healthy',
      checks: {
        rf_path_continuity: state?.enabled || false,
        vswr: {
          value: 1.2,  // 需要实际测量
          acceptable: true
        },
        power_output: {
          measured_dbm: state?.power_dbm || 0,
          expected_dbm: state?.power_dbm || 0,
          within_tolerance: true
        }
      },
      last_checked: new Date()
    }
  }

  async scanAllProbes(): Promise<Map<number, ProbeHealthStatus>> {
    const results = new Map<number, ProbeHealthStatus>()

    for (let i = 0; i < this.config.probe_array.num_probes; i++) {
      const health = await this.checkProbeHealth(i)
      results.set(i, health)
    }

    return results
  }

  async getSystemStatus(): Promise<ProbeSystemStatus> {
    const enabledCount = Array.from(this.probeStates.values())
      .filter(s => s.enabled).length

    return {
      initialized: true,
      calibration_mode: false,
      probe_summary: {
        total_probes: this.config.probe_array.num_probes,
        enabled_probes: enabledCount,
        healthy_probes: enabledCount,  // 简化
        faulty_probes: 0
      },
      rf_switches: this.rfSwitches.map((sw, idx) => ({
        switch_id: idx,
        connected: true,
        active_paths: enabledCount
      })),
      power_controllers: this.powerControllers.map((pc, idx) => ({
        controller_id: idx,
        connected: true,
        all_relays_on: false
      })),
      faults: []
    }
  }

  async shutdown(): Promise<void> {
    // 1. 断开所有RF
    await this.disconnectAllRF()

    // 2. 关闭所有探头电源
    await this.setProbesEnabled(
      new Map(Array.from({ length: this.config.probe_array.num_probes }, (_, i) => [i, false]))
    )

    // 3. 关闭所有驱动
    for (const driver of this.rfSwitches) {
      await driver.close()
    }

    for (const driver of this.powerControllers) {
      await driver.close()
    }

    for (const driver of this.attenuators.values()) {
      await driver.close()
    }

    console.log('Probe control system shut down')
  }

  // ... 其他方法实现 ...
}
```

## 6. 数据库模式

```sql
CREATE TABLE probe_hardware_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  config_name VARCHAR(255) UNIQUE NOT NULL,

  -- 探头阵列
  num_probes INTEGER NOT NULL,
  layout VARCHAR(50),
  polarizations JSONB,

  -- 硬件组件配置
  rf_switches JSONB,
  power_amplifiers JSONB,
  attenuators JSONB,
  power_controllers JSONB,

  active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE probe_health_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  probe_id INTEGER NOT NULL,

  overall_health VARCHAR(50),
  health_checks JSONB,

  checked_at TIMESTAMP DEFAULT NOW(),

  INDEX idx_probe_id (probe_id),
  INDEX idx_checked_at (checked_at)
);

CREATE TABLE probe_faults (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fault_id VARCHAR(100) UNIQUE NOT NULL,
  probe_id INTEGER NOT NULL,

  fault_type VARCHAR(100),
  severity VARCHAR(50),
  description TEXT,

  detected_at TIMESTAMP DEFAULT NOW(),
  resolved_at TIMESTAMP,
  auto_recovered BOOLEAN DEFAULT FALSE,

  INDEX idx_probe_id (probe_id),
  INDEX idx_resolved (resolved_at)
);
```

## 7. REST API

```typescript
// POST /api/v1/probe-control/initialize
interface InitializeProbeControlRequest {
  config: ProbeControlConfig
}

// POST /api/v1/probe-control/probes/{id}/enable
interface EnableProbeRequest {
  enabled: boolean
}

// POST /api/v1/probe-control/rf-routing
interface ConfigureRFRoutingRequest {
  routing: RFRoutingConfig
}

// GET /api/v1/probe-control/status
interface ProbeControlStatusResponse {
  status: ProbeSystemStatus
}

// GET /api/v1/probe-control/probes/{id}/health
interface ProbeHealthResponse {
  health: ProbeHealthStatus
}

// POST /api/v1/probe-control/scan
// 扫描所有探头健康状态
interface ScanProbesResponse {
  results: Map<number, ProbeHealthStatus>
  scan_duration_ms: number
}
```

## 8. 实现计划

### Phase 1: 核心驱动 (1周)
- [ ] RF开关矩阵驱动 (Mini-Circuits)
- [ ] 电源控制器驱动 (USB继电器)
- [ ] 单元测试

### Phase 2: 探头控制器 (1周)
- [ ] ProbeControllerImpl实现
- [ ] 路由配置
- [ ] 健康检查
- [ ] 集成测试

### Phase 3: 高级功能 (3天)
- [ ] 可编程衰减器支持
- [ ] 故障检测和恢复
- [ ] 校准模式支持

### Phase 4: 数据库和API (3天)
- [ ] 数据库表
- [ ] REST API
- [ ] 文档

## 9. 总结

Probe Control HAL为Meta-3D系统提供：

- **硬件抽象**: 统一控制RF开关、功放、衰减器
- **灵活路由**: 动态配置RF路径到任意探头
- **健康监控**: 实时检测探头故障
- **安全关闭**: 确保硬件安全断电

实现后，系统可精确控制32+探头阵列，支持灵活的测试配置。
