# System Configuration Design

## 文档信息
- **版本**: 1.0.0
- **日期**: 2025-11-16
- **子系统**: System Integration
- **优先级**: P0

## 1. 概述
系统配置管理提供集中化配置管理，支持多环境（开发/测试/生产）、版本控制和热更新。

## 2. 配置层级
```
Global Config
  ├─ Hardware Config
  │   ├─ Channel Emulators
  │   ├─ Base Stations
  │   ├─ Probe Arrays
  │   └─ Positioners
  ├─ Chamber Config
  ├─ Network Config
  └─ Feature Flags
```

## 3. 配置存储
```yaml
# config/production.yaml
hardware:
  channel_emulator:
    primary:
      vendor: "Keysight"
      model: "PROPSIM_F64"
      connection:
        host: "192.168.1.100"
        port: 5025
    
  base_station:
    primary:
      vendor: "Keysight"
      model: "UXM_5G"
      connection:
        host: "192.168.1.101"
        port: 5025

chamber:
  size:
    length_m: 6.0
    width_m: 4.0
    height_m: 3.0
  
  quiet_zone:
    diameter_m: 0.5

probe_array:
  active_config: "32-probe-dual-ring"
  configs:
    "32-probe-dual-ring":
      num_probes: 32
      radius_m: 3.0
      layout: "dual_ring"

features:
  virtual_test_mode: false
  auto_calibration: true
  parallel_execution: true
  max_parallel_tests: 2
```

## 4. 配置API
```typescript
interface ConfigService {
  get<T>(key: string): T
  set(key: string, value: any): void
  reload(): Promise<void>
  validateConfig(): ConfigValidationResult
}
```

## 5. 环境变量
- `MPAC_ENV`: development | testing | production
- `MPAC_CONFIG_DIR`: 配置文件目录
- `MPAC_LOG_LEVEL`: debug | info | warn | error

## 6. 热更新
- 监听配置文件变化
- 非破坏性更新（不影响运行中的测试）
- 配置版本回滚

