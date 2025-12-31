# Data Storage Design

## 文档信息
- **版本**: 1.0.0
- **日期**: 2025-11-16
- **子系统**: Data Management Subsystem
- **优先级**: P1

## 1. 概述
数据存储子系统提供分层存储策略，结合关系型数据库（PostgreSQL）、时序数据库（TimescaleDB/InfluxDB）和对象存储（S3/MinIO）。

## 2. 存储架构
```
┌─────────────────────────────────────────┐
│      Application Layer                  │
└─────────────────────────────────────────┘
              ▼
┌─────────────────────────────────────────┐
│  Storage Abstraction Layer              │
│  - Data Router                          │
│  - Compression                          │
│  - Archival Policy                      │
└─────────────────────────────────────────┘
              ▼
┌──────────────┬──────────────┬───────────┐
│ PostgreSQL   │ TimescaleDB  │  MinIO    │
│ (Metadata)   │ (Timeseries) │ (Objects) │
└──────────────┴──────────────┴───────────┘
```

## 3. 数据分类
| 数据类型 | 存储位置 | 保留期 | 压缩 |
|---------|---------|--------|------|
| 测试计划/配置 | PostgreSQL | 永久 | 否 |
| 执行记录 | PostgreSQL | 2年 | 否 |
| 时序测量数据 | TimescaleDB | 6个月 | 是 |
| 原始数据文件 | MinIO | 1年 | 是 |
| 校准数据 | PostgreSQL | 永久 | 否 |
| 报告PDF | MinIO | 2年 | 否 |

## 4. PostgreSQL Schema
```sql
-- 已在其他设计文档中定义的表
-- test_plans, test_executions, calibrations等
```

## 5. TimescaleDB Schema
```sql
CREATE TABLE measurements_ts (
  time TIMESTAMPTZ NOT NULL,
  execution_id UUID NOT NULL,
  probe_id INTEGER,
  metric VARCHAR(50),
  value DOUBLE PRECISION,
  tags JSONB
);

SELECT create_hypertable('measurements_ts', 'time', chunk_time_interval => INTERVAL '1 day');

-- 自动压缩策略
SELECT add_compression_policy('measurements_ts', INTERVAL '7 days');

-- 数据保留策略
SELECT add_retention_policy('measurements_ts', INTERVAL '6 months');
```

## 6. 对象存储
- **原始数据**: /raw-data/{execution_id}/{timestamp}.csv
- **校准文件**: /calibrations/{type}/{date}.json
- **报告**: /reports/{execution_id}/report.pdf
- **日志**: /logs/{date}/{execution_id}.log

## 7. 数据归档策略
- 热数据（< 30天）: 快速访问，无压缩
- 温数据（30-180天）: 压缩存储
- 冷数据（> 180天）: 归档到对象存储

## 8. 实现计划
- Week 1: PostgreSQL优化
- Week 2: TimescaleDB集成
- Week 3: MinIO配置和归档策略

