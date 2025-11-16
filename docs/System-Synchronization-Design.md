# 系统同步设计

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: System Integration (系统集成)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 同步的必要性

MIMO OTA 测试系统的核心是在暗室中精确重现 3GPP 信道模型的**空间特性**和**时间特性**。系统同步是实现这一目标的基础：

**为什么必须同步？**

1. **相位相干性 (Phase Coherence)**：
   - 信道仿真器的 64 个输出通道必须**相位同步**，才能在静区中正确叠加形成 3GPP 信道的空间相关矩阵
   - 相位误差会直接导致空间信道特性失真，使测试结果无效

2. **时间对齐 (Time Alignment)**：
   - 基站仿真器、信道仿真器、数据采集系统的时间戳必须对齐
   - 确保测量数据（吞吐量、RSRP、SINR）与测试状态（信道配置、探头权重）一一对应

3. **触发协调 (Trigger Coordination)**：
   - 多仪器需要协调启动/停止，避免数据采集先于信道建立、或晚于测试结束

### 1.2 系统拓扑

```
┌────────────────────────────────────────────────────────────────────────┐
│                          同步层级结构                                     │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
          ┌──────────────────┐        ┌──────────────────┐
          │  主时钟源         │        │  触发控制器        │
          │  (Master Clock)  │        │  (Trigger Master) │
          │                  │        │                  │
          │ • GPS-DO         │        │ • 测试控制器      │
          │ • Rb 铷钟        │        │ • 软件触发        │
          └────────┬─────────┘        └────────┬─────────┘
                   │                           │
        ┌──────────┼───────────┬───────────────┼──────────┐
        │          │           │               │          │
        ▼          ▼           ▼               ▼          ▼
  ┌─────────┐ ┌─────────┐ ┌─────────┐   ┌─────────┐ ┌─────────┐
  │  基站   │ │  信道   │ │  信号   │   │  数据   │ │  环境   │
  │ 仿真器  │ │ 仿真器  │ │ 分析仪  │   │ 采集系统 │ │ 监测系统 │
  │  BSE    │ │   CE    │ │   SA    │   │  DAQ    │ │  Env    │
  └─────────┘ └─────────┘ └─────────┘   └─────────┘ └─────────┘
       │           │           │               │          │
       └───────────┴───────────┴───────────────┴──────────┘
                          │
                          ▼
                  ┌──────────────┐
                  │   被测设备    │
                  │   DUT (Car)  │
                  └──────────────┘
```

## 2. 同步需求分析

### 2.1 相位同步精度要求

**场景 1: Sub-6 GHz（FR1）**
- **频率范围**: 0.6 - 7.125 GHz
- **典型频点**: 3.5 GHz（n78）
- **波长**: λ = c/f = 3×10⁸ / 3.5×10⁹ = **85.7 mm**
- **相位误差要求**: ±1°（3GPP TS 34.114 建议）
- **时间精度**: 1° @ 3.5 GHz = (1/360) × (1/3.5 GHz) = **79.4 ps**

**场景 2: mmWave（FR2）**
- **频率范围**: 24.25 - 52.6 GHz
- **典型频点**: 28 GHz（n257/n258）
- **波长**: λ = 3×10⁸ / 28×10⁹ = **10.7 mm**
- **相位误差要求**: ±1°
- **时间精度**: 1° @ 28 GHz = (1/360) × (1/28 GHz) = **9.9 ps**

**结论**：
- **Sub-6 GHz**: 相位同步精度需 **< 80 ps**
- **mmWave**: 相位同步精度需 **< 10 ps**（要求极高！）

### 2.2 时间同步精度要求

**数据采集与测试状态关联**：

测试执行过程中，系统会动态改变信道配置（如从 UMa 切换到 UMi），数据采集系统需要知道每个测量数据点对应的信道配置。

- **测试步骤切换时间**: 通常 100-500 ms
- **数据采集间隔**: 10-100 ms（吞吐量测量）
- **时间戳精度要求**: **< 1 ms**（确保数据点归属正确的测试步骤）

**结论**：
- **数据采集系统**: 时间同步精度 **< 1 ms**
- **测试状态记录**: 时间同步精度 **< 1 ms**

### 2.3 触发同步精度要求

**测试启动流程**：
1. 测试控制器发送 START 命令
2. 基站仿真器启动小区广播（约 50 ms）
3. 信道仿真器加载 3GPP 模型（约 100 ms）
4. 数据采集系统开始采样

**触发精度要求**：
- **触发抖动**: < 10 ms（确保各仪器在同一时间窗口启动）
- **实现方式**: 软件触发（TCP/IP 命令）或硬件触发（TTL 信号）

## 3. 同步架构设计

### 3.1 三层同步架构

```
┌────────────────────────────────────────────────────────────────────────┐
│  Layer 1: 相位同步 (Phase Synchronization)                              │
│  • 10 MHz 参考时钟                                                       │
│  • 1 PPS (Pulse Per Second) 脉冲                                        │
│  • 用途: 信道仿真器 64 通道相位锁定                                       │
│  • 精度: < 10 ps @ 28 GHz                                               │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Layer 2: 时间同步 (Time Synchronization)                               │
│  • IEEE 1588 PTP (Precision Time Protocol)                             │
│  • 或 NTP (Network Time Protocol) + GPS                                │
│  • 用途: 所有仪器和数据采集系统的系统时间对齐                              │
│  • 精度: < 1 μs (PTP) 或 < 1 ms (NTP)                                  │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Layer 3: 触发同步 (Trigger Synchronization)                            │
│  • 软件触发: REST API / SCPI 命令                                        │
│  • 硬件触发: TTL / LVDS 触发信号 (可选)                                  │
│  • 用途: 协调测试开始/结束、状态切换                                      │
│  • 精度: < 10 ms                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Layer 1: 相位同步设计

#### 3.2.1 主时钟源选择

**方案 A: GPS 驯服晶振 (GPS-Disciplined Oscillator, GPS-DO)**
- **型号示例**: Symmetricom/Microchip TimeProvider 4100
- **输出**: 10 MHz 正弦波 + 1 PPS TTL
- **精度**: ±1×10⁻¹¹（长期稳定性）
- **相位噪声**: -140 dBc/Hz @ 10 kHz offset
- **优点**: 长期稳定性极高，自动校准
- **缺点**: 需要天线，室内可能无 GPS 信号

**方案 B: 铷原子钟 (Rubidium Atomic Clock)**
- **型号示例**: Stanford Research Systems FS725
- **输出**: 10 MHz 正弦波
- **精度**: ±5×10⁻¹¹（30天老化率）
- **相位噪声**: -130 dBc/Hz @ 10 kHz offset
- **优点**: 不依赖外部信号，短期稳定性极佳
- **缺点**: 长期漂移需定期校准

**推荐方案**: **GPS-DO（首选）+ Rb 时钟（备份）**
- GPS-DO 作为主时钟源，在暗室外架设 GPS 天线
- Rb 时钟作为备份，当 GPS 失锁时自动切换

#### 3.2.2 时钟分配网络

**方案 A: 主动时钟分配器**
- **型号示例**: SRS FS740 GPS 时钟 + 分配放大器
- **输出通道**: 8 路 10 MHz 输出
- **相位一致性**: < 1 ps（同一批次输出）
- **扇出**: 1:8（可级联）

**方案 B: 被动功分器**
- **型号示例**: Mini-Circuits ZX10-2-183-S+ (1:8 功分器)
- **插入损耗**: ~9 dB（1:8 分配）
- **相位一致性**: < 5 ps
- **优点**: 无源、低成本
- **缺点**: 信号衰减需后级放大

**时钟分配拓扑**:
```
              ┌─────────────────┐
              │   GPS-DO        │
              │ (10 MHz + 1PPS) │
              └────────┬────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌─────────────────┐         ┌─────────────────┐
│ 10 MHz 分配器    │         │ 1 PPS 分配器     │
│  (1:8 主动)     │         │  (TTL 扇出)     │
└────────┬────────┘         └────────┬────────┘
         │                           │
    ┌────┼────┬────┬────┐       ┌────┼────┬────┐
    ▼    ▼    ▼    ▼    ▼       ▼    ▼    ▼    ▼
   BSE   CE   SA  备用  备用    BSE   CE   SA  备用
```

#### 3.2.3 仪器时钟锁定配置

**信道仿真器 (Keysight PROPSIM F64)**:
```scpi
# 连接外部 10 MHz 参考
SYSTem:REFerence:FREQuency:EXTernal 10MHz

# 等待锁定
*OPC?

# 检查锁定状态
SYSTem:REFerence:LOCKed?
# 返回: 1 (已锁定) 或 0 (未锁定)
```

**基站仿真器 (Keysight UXM 5G)**:
```scpi
# 设置参考时钟源为外部
SOURce:REFerence:SOURce EXTernal

# 设置频率
SOURce:REFerence:FREQuency 10MHz

# 验证锁定
SOURce:REFerence:STATe?
```

**信号分析仪 (Keysight N9040B)**:
```scpi
# 外部参考
SENSe:ROSCillator:SOURce EXTernal

# 参考频率
SENSe:ROSCillator:EXTernal:FREQuency 10MHz
```

### 3.3 Layer 2: 时间同步设计

#### 3.3.1 方案对比

| 协议 | 精度 | 网络要求 | 硬件要求 | 复杂度 | 推荐场景 |
|------|------|---------|---------|-------|---------|
| **PTP (IEEE 1588v2)** | 10 ns - 1 μs | 支持PTP的交换机 | PTP硬件时钟 | 高 | 高精度测量系统 |
| **NTP** | 1 - 10 ms | 普通以太网 | 无特殊要求 | 低 | 数据采集时间戳 |
| **GPS** | < 100 ns | 无 | GPS接收器 | 中 | 独立仪器 |

**推荐方案**: **PTP (IEEE 1588v2)** 用于局域网内所有设备

#### 3.3.2 PTP 架构设计

**PTP 时钟层级**:
```
                    ┌──────────────────┐
                    │  Grandmaster     │
                    │  (GPS-DO + PTP)  │
                    │  Stratum 0       │
                    └─────────┬────────┘
                              │
                    ┌─────────┴────────┐
                    │  PTP 交换机       │
                    │  (Transparent)   │
                    └─────────┬────────┘
                              │
        ┌─────────┬───────────┼──────────┬──────────┐
        │         │           │          │          │
        ▼         ▼           ▼          ▼          ▼
   ┌────────┐┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │  BSE   ││  CE    │ │  SA    │ │  DAQ   │ │测试控制 │
   │ Slave  ││ Slave  │ │ Slave  │ │ Server │ │ Server │
   └────────┘└────────┘ └────────┘ └────────┘ └────────┘
```

**Grandmaster 配置**:
- **设备**: Meinberg LANTIME M3000 或 Microchip TimeProvider 4100
- **输入**: GPS + Rb 时钟（双重保障）
- **输出**: PTP over Ethernet (1000BASE-T)
- **精度**: ±50 ns（局域网内）

**PTP 交换机选择**:
- **类型**: Transparent Clock（透明时钟）或 Boundary Clock（边界时钟）
- **示例**: Cisco IE-4000, Hirschmann RSP20
- **功能**: 补偿网络延迟，保持 PTP 精度

**Slave 设备配置**:
- 仪器内置 PTP 功能（Keysight/R&S 高端仪器支持）
- 或使用 PTP NIC（如 Intel I210-AT 网卡）

#### 3.3.3 软件实现（Linux 系统）

**安装 PTP 服务**:
```bash
# Debian/Ubuntu
sudo apt-get install linuxptp

# 启动 ptp4l (PTP 守护进程)
sudo ptp4l -i eth0 -m -s  # -s: slave 模式

# 启动 phc2sys (硬件时钟同步到系统时钟)
sudo phc2sys -s eth0 -m -w
```

**配置文件** (`/etc/linuxptp/ptp4l.conf`):
```ini
[global]
slaveOnly 1
priority1 255
priority2 255

# 网络延迟测量
delay_mechanism E2E  # End-to-End
network_transport L2  # Layer 2 (以太网)

# 时钟类型
clock_servo linreg  # 线性回归，适合稳定网络

# 日志
summary_interval 1
```

**验证同步状态**:
```bash
# 查看偏移量
sudo ptp4l -i eth0 -m | grep "master offset"
# 期望: master offset < 1000 ns
```

### 3.4 Layer 3: 触发同步设计

#### 3.4.1 软件触发（推荐）

**实现方式**: 测试控制器通过网络并发发送命令到所有仪器

**优点**:
- 无需额外硬件
- 灵活可配置
- 易于调试

**缺点**:
- 网络延迟不确定（1-10 ms）
- 不适合需要微秒级触发的场景

**代码实现**:
```typescript
class TriggerCoordinator {
  private instruments: Map<string, InstrumentClient> = new Map()

  /**
   * 并发触发所有仪器启动
   */
  async triggerStart(): Promise<void> {
    const timestamp = Date.now()

    // 并发发送触发命令（Promise.all 确保同时发出）
    await Promise.all([
      this.instruments.get('bse')?.start(),
      this.instruments.get('ce')?.start(),
      this.instruments.get('sa')?.start(),
      this.instruments.get('daq')?.start()
    ])

    // 记录触发时间（用于后续数据关联）
    await this.logTriggerEvent({
      event: 'test_start',
      timestamp,
      instruments: ['bse', 'ce', 'sa', 'daq']
    })
  }

  /**
   * 定时触发（在指定的系统时间启动）
   */
  async scheduleStart(targetTime: Date): Promise<void> {
    const now = Date.now()
    const delay = targetTime.getTime() - now

    if (delay < 100) {
      throw new Error('Target time too close, need at least 100ms preparation time')
    }

    // 预配置所有仪器（减少启动延迟）
    await Promise.all([
      this.instruments.get('bse')?.configure(),
      this.instruments.get('ce')?.configure()
    ])

    // 等待到目标时间
    await new Promise(resolve => setTimeout(resolve, delay - 50))

    // 在目标时间前 50ms 发送触发命令
    // （考虑网络延迟约 10-20ms）
    await this.triggerStart()
  }
}
```

#### 3.4.2 硬件触发（可选）

**应用场景**: 需要微秒级触发同步时（如多设备同步采样）

**实现方式**:
```
┌────────────────┐
│  测试控制器     │
│  (DAQ + GPIO)  │
└────────┬───────┘
         │
         ▼ (GPIO 输出 TTL)
    ┌────┴────┬────┬────┐
    │         │    │    │
    ▼         ▼    ▼    ▼
┌────────┐┌────────┐┌────────┐┌────────┐
│  BSE   ││  CE    ││  SA    ││示波器   │
│ TRIG IN││TRIG IN ││TRIG IN ││TRIG IN │
└────────┘└────────┘└────────┘└────────┘
```

**信号标准**: TTL (0V/5V) 或 LVDS

**连接方式**: BNC 线缆（RG58，50Ω）

**GPIO 控制**:
```python
import RPi.GPIO as GPIO  # Raspberry Pi GPIO

# 配置 GPIO 17 为输出
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)

def send_trigger():
    """发送 10ms 触发脉冲"""
    GPIO.output(17, GPIO.HIGH)
    time.sleep(0.01)  # 10ms
    GPIO.output(17, GPIO.LOW)

# 在测试启动时调用
send_trigger()
```

## 4. 设备间同步关系

### 4.1 同步矩阵

| 设备 A | 设备 B | 同步类型 | 精度要求 | 实现方式 |
|-------|-------|---------|---------|---------|
| **CE 通道 1-64** | **内部** | 相位同步 | < 10 ps | 内部 10 MHz 参考 |
| **CE** | **BSE** | 相位同步 | < 80 ps | 外部 10 MHz + 1 PPS |
| **CE** | **SA** | 相位同步 | < 80 ps | 外部 10 MHz + 1 PPS |
| **BSE** | **数据采集** | 时间同步 | < 1 ms | PTP |
| **CE** | **数据采集** | 时间同步 | < 1 ms | PTP |
| **测试控制器** | **所有仪器** | 触发同步 | < 10 ms | 软件触发 (REST API) |
| **数据采集服务器** | **测试控制器** | 时间同步 | < 1 ms | PTP |

### 4.2 关键同步对

#### 4.2.1 信道仿真器内部（最关键）

**为什么重要**:
- 64 个输出通道的相位关系直接决定静区中的空间信道特性
- 这是 MIMO OTA 测试的核心，相位误差 > ±3° 会导致测试失败

**实现方式**:
- 信道仿真器内部使用同一个 10 MHz 参考时钟驱动所有 64 个 RF 通道
- 硬件设计保证通道间相位一致性（工厂校准）

**验证方法**:
```python
# 校准测试：所有 64 个通道输出同相位 CW 信号
ce.configure({
  'mode': 'calibration',
  'frequency': 3.5e9,  # 3.5 GHz
  'channels': list(range(1, 65)),
  'signal': {
    'type': 'CW',  # 连续波
    'power': -20,  # dBm
    'phase': 0  # 所有通道相位设为 0
  }
})

# 用矢量信号分析仪测量相位差
for ch in range(1, 65):
  phase = vsa.measure_phase(ch)
  assert abs(phase) < 1.0, f"Channel {ch} phase error {phase}°"
```

#### 4.2.2 基站仿真器 ↔ 信道仿真器

**为什么重要**:
- 基站信号经过信道仿真后到达 DUT，相位失真会影响 DUT 的解调性能

**实现方式**:
- BSE 和 CE 使用同一个 10 MHz 参考时钟
- 1 PPS 信号用于对齐帧边界（5G NR 帧 = 10ms）

**配置示例**:
```typescript
// 基站仿真器
await bse.setReferenceClock({
  source: 'external',
  frequency: 10e6,  // 10 MHz
  pps: true  // 启用 1 PPS 输入
})

// 信道仿真器
await ce.setReferenceClock({
  source: 'external',
  frequency: 10e6
})
```

#### 4.2.3 数据采集 ↔ 测试状态

**为什么重要**:
- 测试过程中信道配置会变化（如从 UMa 切换到 UMi）
- 数据采集必须知道每个数据点对应的信道配置

**实现方式**:
- 所有服务器通过 PTP 同步系统时间
- 数据采集记录精确时间戳
- 测试控制器记录状态变化时间戳

**数据关联**:
```sql
-- 查询某个时间点的信道配置
SELECT c.scenario_name, c.doppler_hz
FROM channel_configurations c
WHERE c.test_execution_id = 'exec-123'
  AND c.start_time <= '2025-11-16 10:30:15.234'
  AND (c.end_time IS NULL OR c.end_time > '2025-11-16 10:30:15.234')

-- 查询该时刻的测量数据
SELECT m.throughput_mbps, m.rsrp_dbm
FROM measurements m
WHERE m.test_execution_id = 'exec-123'
  AND m.timestamp = '2025-11-16 10:30:15.234'
```

## 5. 同步失效检测与恢复

### 5.1 检测机制

```typescript
class SyncMonitor {
  /**
   * 检查相位同步状态
   */
  async checkPhaseLock(): Promise<SyncStatus> {
    const instruments = ['bse', 'ce', 'sa']
    const status: Map<string, boolean> = new Map()

    for (const inst of instruments) {
      const locked = await this.queryPhaseLock(inst)
      status.set(inst, locked)

      if (!locked) {
        await this.logAlert({
          severity: 'critical',
          message: `${inst} phase lock lost`,
          timestamp: new Date()
        })
      }
    }

    return {
      allLocked: Array.from(status.values()).every(v => v),
      details: status
    }
  }

  /**
   * 检查时间同步状态
   */
  async checkTimeSync(): Promise<TimeSyncStatus> {
    // 查询 PTP 偏移量
    const offset = await this.queryPTPOffset()

    if (Math.abs(offset) > 1e-3) {  // > 1 ms
      await this.logAlert({
        severity: 'warning',
        message: `Time offset ${offset * 1e3} ms exceeds threshold`,
        timestamp: new Date()
      })
    }

    return {
      offset_ns: offset * 1e9,
      synchronized: Math.abs(offset) < 1e-3
    }
  }

  /**
   * 周期性监控
   */
  startMonitoring(interval_ms: number = 1000): void {
    setInterval(async () => {
      const phaseStatus = await this.checkPhaseLock()
      const timeStatus = await this.checkTimeSync()

      if (!phaseStatus.allLocked || !timeStatus.synchronized) {
        // 触发告警，暂停测试
        await this.pauseTest()
      }
    }, interval_ms)
  }
}
```

### 5.2 恢复策略

**相位同步失锁**:
1. 检查 10 MHz 参考时钟连接
2. 重启失锁的仪器
3. 重新执行系统校准
4. 如无法恢复，切换到备用仪器

**时间同步偏移过大**:
1. 检查网络连接（PTP 需要稳定网络）
2. 重启 PTP 服务 (`sudo systemctl restart ptp4l`)
3. 检查 Grandmaster 状态
4. 如使用 GPS，检查天线信号强度

## 6. 部署方案

### 6.1 硬件清单

| 设备 | 型号 | 数量 | 用途 | 预算 (USD) |
|------|------|------|------|-----------|
| **GPS-DO** | Microchip TimeProvider 4100 | 1 | 主时钟源 | $15,000 |
| **Rb 时钟** | SRS FS725 | 1 | 备份时钟 | $5,000 |
| **10 MHz 分配器** | SRS FS740 | 1 | 时钟分配 | $8,000 |
| **PTP 交换机** | Cisco IE-4000 (8 port) | 1 | 网络同步 | $3,000 |
| **同轴线缆** | RG58 BNC (10m) | 10 | 时钟连接 | $200 |
| **GPS 天线** | Trimble GPS Antenna | 1 | GPS 接收 | $500 |
| **合计** | - | - | - | **$31,700** |

### 6.2 布线方案

```
暗室外                          暗室内
┌─────────────┐              ┌─────────────────────────┐
│  GPS 天线   │              │                         │
└──────┬──────┘              │   ┌──────────────┐      │
       │                     │   │  10 MHz 分配 │      │
       │                     │   └───┬──────────┘      │
       │                     │       │                 │
       ▼                     │   ┌───┴───┬───┬───┐     │
┌─────────────┐  10MHz+PPS  │   ▼       ▼   ▼   ▼     │
│  GPS-DO     ├─────────────┼─► BSE    CE  SA  备用   │
│  (机柜)     │             │                         │
└──────┬──────┘              │   PTP 交换机            │
       │                     │   └───┬──────────┘      │
       │                     │       │ Ethernet        │
       │                     │   ┌───┴───┬───┬───┐     │
       │                     │   ▼       ▼   ▼   ▼     │
       │                     │  测试    数据  环境 备用 │
       │                     │  控制    采集  监测      │
       │                     │                         │
       └─────────────────────┤ (穿墙电缆)              │
                             └─────────────────────────┘
```

### 6.3 软件配置

#### 6.3.1 GPS-DO 配置

```bash
# 通过串口连接 GPS-DO
screen /dev/ttyUSB0 115200

# 检查 GPS 状态
gps:status?
# 期望: GPS locked, Satellites: 8+

# 检查输出
output:frequency?
# 期望: 10000000 Hz

output:pps?
# 期望: ON
```

#### 6.3.2 PTP Grandmaster 配置

**使用 Meinberg LANTIME M3000**:
```bash
# Web 界面配置 (https://192.168.1.100)
# 1. 设置 GPS 输入
# 2. 启用 PTP Profile: Default (1588v2)
# 3. 设置优先级: Priority1 = 0 (最高)
# 4. 网络接口: eth0
```

#### 6.3.3 测试控制器配置

```yaml
# /etc/meta3d/sync.yaml
sync:
  phase_sync:
    enabled: true
    reference_source: gps-do
    reference_frequency: 10e6  # 10 MHz
    pps_enabled: true

  time_sync:
    protocol: ptp
    mode: slave
    grandmaster_ip: 192.168.1.100
    network_interface: eth0

  trigger:
    method: software  # 或 hardware
    jitter_tolerance_ms: 10
```

## 7. 校准与验证

### 7.1 相位同步验证

**测试方法**:
1. 配置信道仿真器输出同相位 CW 信号（所有 64 通道）
2. 使用矢量信号分析仪逐通道测量相位
3. 计算相位标准差

**验收标准**:
- **Sub-6 GHz**: σ(相位) < 0.5° @ 3.5 GHz
- **mmWave**: σ(相位) < 0.3° @ 28 GHz

**测试脚本**:
```python
import numpy as np

# 配置 CE 输出 CW
ce.configure_cw(frequency=3.5e9, power=-20, phase=0, channels=range(1,65))

# 测量相位
phases = []
for ch in range(1, 65):
    switch.set_path(channel=ch, probe=1)
    phase = vsa.measure_phase()
    phases.append(phase)

# 统计
phases = np.array(phases)
mean_phase = np.mean(phases)
std_phase = np.std(phases)

print(f"相位均值: {mean_phase:.2f}°")
print(f"相位标准差: {std_phase:.2f}°")
assert std_phase < 0.5, f"相位同步失败，标准差 {std_phase:.2f}° > 0.5°"
```

### 7.2 时间同步验证

**测试方法**:
1. 所有服务器启动 PTP slave
2. 记录 PTP 偏移量（使用 `ptp4l` 日志）
3. 分析偏移量统计特性

**验收标准**:
- **平均偏移**: |μ(offset)| < 500 ns
- **偏移抖动**: σ(offset) < 200 ns

**测试脚本**:
```bash
#!/bin/bash
# 采集 PTP 偏移量（持续 10 分钟）
timeout 600 ptp4l -i eth0 -m | grep "master offset" | \
  awk '{print $5}' > ptp_offsets.log

# 分析（使用 Python）
python3 << EOF
import numpy as np
offsets = np.loadtxt('ptp_offsets.log')
print(f"平均偏移: {np.mean(offsets):.0f} ns")
print(f"标准差: {np.std(offsets):.0f} ns")
print(f"最大偏移: {np.max(np.abs(offsets)):.0f} ns")
EOF
```

## 8. 成本与性能权衡

### 8.1 方案对比

| 同步方案 | 相位精度 | 时间精度 | 成本 | 复杂度 | 推荐 |
|---------|---------|---------|------|-------|-----|
| **方案 A: 完整同步** | < 10 ps | < 100 ns | $32k | 高 | ✅ FR2 (mmWave) |
| **方案 B: 简化同步** | < 100 ps | < 1 μs | $15k | 中 | ✅ FR1 (Sub-6) |
| **方案 C: 最小同步** | < 1 ns | < 10 ms | $3k | 低 | ⚠️ 原型验证 |

**方案 B（推荐用于 Sub-6 GHz）**:
- GPS-DO: $15k（含 10 MHz 分配）
- PTP 交换机: 不需要（使用 NTP 代替）
- 时间同步: NTP（1-10 ms 精度）
- **适用场景**: 仅测试 Sub-6 GHz，不涉及 mmWave

**方案 C（仅用于开发阶段）**:
- 无外部时钟（仪器自由运行）
- NTP 时间同步
- **风险**: 相位误差可能导致测试结果不可重复

## 9. 实施计划

### 9.1 阶段划分

**Phase 1: 基础同步（1 周）**
- [ ] 采购 GPS-DO 和 10 MHz 分配器
- [ ] 布设时钟线缆
- [ ] 配置仪器外部参考时钟
- [ ] 验证相位锁定

**Phase 2: 时间同步（1 周）**
- [ ] 部署 PTP Grandmaster
- [ ] 配置 PTP 交换机
- [ ] 所有服务器配置 PTP slave
- [ ] 验证时间偏移 < 1 μs

**Phase 3: 触发协调（3 天）**
- [ ] 实现 TriggerCoordinator 类
- [ ] 测试多仪器并发触发
- [ ] 测量触发抖动

**Phase 4: 监控与告警（3 天）**
- [ ] 实现 SyncMonitor 类
- [ ] 集成到测试流程
- [ ] 故障恢复测试

### 9.2 验收标准

| 指标 | 目标值 | 验证方法 |
|------|-------|---------|
| **相位同步精度** | < 0.5° @ 3.5 GHz | CW 测试 + VSA |
| **时间同步精度** | < 1 μs | PTP 日志分析 |
| **触发抖动** | < 10 ms | 示波器测量 |
| **同步失锁恢复时间** | < 60 s | 人工拔插测试 |

## 10. 参考标准

- **3GPP TS 34.114**: Test tolerances for MIMO OTA
- **IEEE 1588-2008**: Precision Time Protocol (PTPv2)
- **ITU-T G.811**: Timing characteristics of primary reference clocks
- **SCPI**: Standard Commands for Programmable Instruments

## 11. 附录

### 11.1 术语表

| 术语 | 英文 | 定义 |
|------|------|------|
| **相位同步** | Phase Synchronization | 多个 RF 信号的载波相位保持固定关系 |
| **时间同步** | Time Synchronization | 多个系统的时钟对齐到同一时间基准 |
| **GPS-DO** | GPS Disciplined Oscillator | 使用 GPS 信号校准的高稳定度振荡器 |
| **PTP** | Precision Time Protocol | IEEE 1588 精密时钟同步协议 |
| **1 PPS** | 1 Pulse Per Second | 每秒一个脉冲的时间参考信号 |

### 11.2 供应商信息

| 类型 | 供应商 | 型号 | 联系方式 |
|------|-------|------|---------|
| **GPS-DO** | Microchip | TimeProvider 4100 | www.microchip.com |
| **Rb 时钟** | Stanford Research | FS725 | www.thinksrs.com |
| **PTP Grandmaster** | Meinberg | LANTIME M3000 | www.meinbergglobal.com |
| **PTP 交换机** | Cisco | IE-4000 | www.cisco.com |
| **时钟分配** | SRS | FS740 | www.thinksrs.com |

---

**文档状态**: Draft
**下一步**: 采购硬件，执行 Phase 1 部署
**负责人**: 系统集成团队
