# Data Acquisition Design

## 文档信息
- **版本**: 1.0.0
- **日期**: 2025-11-16
- **子系统**: Data Management Subsystem
- **优先级**: P0

## 1. 概述
数据采集子系统负责实时采集OTA测试中的各类测量数据，包括吞吐量、RSRP/SINR、探头功率等，支持高速采样和流式处理。

## 2. 采集数据类型
- **吞吐量数据**: DL/UL Mbps, 实时/平均/峰值
- **射频测量**: RSRP, RSRQ, SINR, RSSI
- **探头数据**: 每个探头的功率、相位
- **DUT数据**: 位置、姿态、温度
- **仪器状态**: 基站、信道仿真器状态

## 3. 采集架构
```typescript
interface DataAcquisitionService {
  // 启动采集
  startAcquisition(config: AcquisitionConfig): Promise<AcquisitionHandle>
  
  // 停止采集
  stopAcquisition(handle: AcquisitionHandle): Promise<void>
  
  // 获取实时数据流
  getDataStream(handle: AcquisitionHandle): AsyncIterator<DataPoint>
  
  // 配置采样率
  setSamplingRate(rate_hz: number): void
}

interface AcquisitionConfig {
  data_sources: DataSource[]
  sampling_rate_hz: number  // 1-1000 Hz
  buffer_size: number
  storage_mode: 'memory' | 'disk' | 'database'
}
```

## 4. 数据模型
```typescript
interface DataPoint {
  timestamp: Date
  source: string
  type: 'throughput' | 'radio' | 'probe' | 'position'
  value: number | object
  unit: string
  quality: 'good' | 'degraded' | 'bad'
}
```

## 5. 数据库模式
```sql
CREATE TABLE measurement_data (
  id BIGSERIAL PRIMARY KEY,
  execution_id UUID REFERENCES test_executions(id),
  timestamp TIMESTAMPTZ NOT NULL,
  source VARCHAR(100),
  data_type VARCHAR(50),
  value JSONB,
  INDEX idx_execution_timestamp (execution_id, timestamp)
);

-- 时序数据表（使用TimescaleDB）
CREATE TABLE timeseries_measurements (
  time TIMESTAMPTZ NOT NULL,
  execution_id UUID,
  metric VARCHAR(100),
  value DOUBLE PRECISION,
  tags JSONB
);

SELECT create_hypertable('timeseries_measurements', 'time');
```

## 6. 实时流处理
- WebSocket推送实时数据
- 支持数据降采样（减少传输量）
- 缓冲区管理（防止数据丢失）
- 异常检测和告警

## 7. 实现计划
- Week 1: 核心采集引擎
- Week 2: 流式处理和WebSocket
- Week 3: TimescaleDB集成

