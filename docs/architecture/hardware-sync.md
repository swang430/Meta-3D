# 硬件同步架构设计

**版本**: v1.0
**创建日期**: 2025-12-11
**状态**: 设计阶段
**所有者**: 系统架构团队

---

## 1. 概述

### 1.1 背景

MIMO OTA 测试系统涉及多种硬件设备的协同工作，包括信道仿真器、基站仿真器、信号分析仪等。这些设备之间需要不同层级的同步：

- **时钟同步**: 确保所有射频设备使用同一时基
- **触发同步**: 确保测量和信号生成的精确时序
- **参数同步**: 确保射线跟踪计算结果实时传递到信道仿真器

### 1.2 设计目标

1. **分层解耦**: 不同精度需求的同步在不同层级处理
2. **可扩展性**: 支持未来添加更多仪器和同步需求
3. **向后兼容**: 不破坏现有 B/S 架构
4. **渐进实现**: 支持分阶段交付

### 1.3 同步层级定义

```
┌────────────────────────────────────────────────────────────────┐
│                      同步层级架构                               │
├──────────┬─────────────┬─────────────┬────────────────────────┤
│   层级    │   时间精度   │   实现位置   │   典型场景             │
├──────────┼─────────────┼─────────────┼────────────────────────┤
│ L0 时钟   │   < 1 ns    │   硬件      │  10MHz参考、载波相位    │
│ L1 触发   │   < 1 μs    │   硬件+固件  │  采样触发、帧同步       │
│ L2 参数   │   < 10 ms   │   软件实时   │  信道系数、大尺度参数   │
│ L3 控制   │   < 100 ms  │   应用层    │  测试流程、状态管理     │
└──────────┴─────────────┴─────────────┴────────────────────────┘
```

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户界面层                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    GUI (React + Mantine)                      │  │
│  │              配置 / 监控 / 可视化 / 告警                        │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ WebSocket / REST
                              │ L3: < 100ms
┌─────────────────────────────▼───────────────────────────────────────┐
│                          控制平面层                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                  API Service (FastAPI)                        │  │
│  │           测试编排 / 状态机 / 数据持久化 / 认证                   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    SQLite / PostgreSQL                        │  │
│  │              测试计划 / 配置 / 报告 / 历史记录                   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ gRPC / ZeroMQ
                              │ L2: < 10ms
┌─────────────────────────────▼───────────────────────────────────────┐
│                          实时计算层                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Channel Engine Service (Python)                  │  │
│  │        射线跟踪 / 大尺度参数 / 信道矩阵计算 / 参数缓冲            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   Redis / SharedMemory                        │  │
│  │              热数据缓存 / 实时参数 / 状态同步                    │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ SharedMemory / DMA
                              │ L2: < 1ms
┌─────────────────────────────▼───────────────────────────────────────┐
│                        硬件抽象层 (HAL)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  VISA Driver │  │  SCPI Parser │  │  TCP/IP Ctrl │                │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Sync Controller (同步控制器)                      │  │
│  │         触发编排 / 时序管理 / 硬件状态监控                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ VISA / LAN / PXI
                              │ L1: < 1μs (软件不参与)
┌─────────────────────────────▼───────────────────────────────────────┐
│                          硬件层                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ 信道仿真器   │  │ 基站仿真器   │  │ 信号分析仪   │  │ 功率计    │  │
│  │ (Keysight   │  │ (R&S CMX)   │  │ (Keysight   │  │ (Keysight │  │
│  │  PROPSIM)   │  │             │  │  MXA/PXA)   │  │  U2000)   │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘  │
│         │                │                │               │        │
│         └────────────────┴────────────────┴───────────────┘        │
│                          │                                         │
│              ┌───────────▼───────────┐                             │
│              │   10MHz Reference     │  L0: < 1ns (纯硬件)          │
│              │   Trigger Bus (PXI)   │  L1: < 1μs (纯硬件)          │
│              └───────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流向

```
射线跟踪场景变化
       │
       ▼
┌──────────────────┐
│ Channel Engine   │  计算大尺度参数 (路径损耗、角度扩展、时延扩展)
│ (Python)         │  计算信道矩阵 H(t,f)
└────────┬─────────┘
         │ ZeroMQ PUB (JSON) - 大尺度参数
         │ SharedMemory - 信道矩阵 (大数据块)
         ▼
┌──────────────────┐
│ HAL Sync         │  参数格式转换
│ Controller       │  触发时序编排
└────────┬─────────┘
         │ SCPI/VISA
         ▼
┌──────────────────┐
│ 信道仿真器 FPGA   │  实时信道卷积
│                  │  多径衰落生成
└──────────────────┘
```

---

## 3. L2 实时通信层详细设计

### 3.1 组件架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    L2 Realtime Layer                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Parameter Publisher (参数发布器)              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │ ZMQ PUB     │  │ SharedMem   │  │ gRPC Stream │       │  │
│  │  │ (小参数)    │  │ (大数据块)   │  │ (可选)      │       │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Parameter Buffer (参数缓冲器)                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │ Ring Buffer │  │ Double      │  │ Timestamp   │       │  │
│  │  │ (历史)      │  │ Buffering   │  │ Correlation │       │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Sync Monitor (同步监控器)                     │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │ Latency     │  │ Jitter      │  │ Health      │       │  │
│  │  │ Tracker     │  │ Monitor     │  │ Check       │       │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 核心接口定义

#### 3.2.1 参数发布接口

```python
# channel-engine-service/sync/publisher.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import numpy as np
from datetime import datetime

@dataclass
class SyncTimestamp:
    """同步时间戳，用于参数关联"""
    wall_clock: datetime           # 系统时间
    simulation_time: float         # 仿真时间 (秒)
    frame_number: int              # 帧号 (用于与L1触发关联)
    sequence_id: int               # 单调递增序列号


@dataclass
class LargeScaleParams:
    """大尺度参数 (L2 同步)"""
    timestamp: SyncTimestamp

    # 路径损耗 (每条路径)
    path_loss_db: list[float]      # [n_paths] dB

    # 角度信息
    aod_azimuth: list[float]       # [n_paths] 度
    aod_elevation: list[float]     # [n_paths] 度
    aoa_azimuth: list[float]       # [n_paths] 度
    aoa_elevation: list[float]     # [n_paths] 度

    # 时延和多普勒
    delay_ns: list[float]          # [n_paths] 纳秒
    doppler_hz: list[float]        # [n_paths] Hz

    # 极化
    xpr_db: list[float]            # [n_paths] 交叉极化比 dB

    # 簇信息 (可选)
    cluster_powers: Optional[list[float]] = None
    cluster_delays: Optional[list[float]] = None


@dataclass
class ChannelMatrix:
    """信道矩阵 (L2 同步 - 大数据块)"""
    timestamp: SyncTimestamp

    # 信道矩阵 H[rx, tx, subcarrier, time_sample]
    # 典型尺寸: [32, 4, 1200, 14] for 5G NR
    H: np.ndarray                  # complex64

    # 元数据
    n_rx: int
    n_tx: int
    n_subcarriers: int
    n_ofdm_symbols: int
    subcarrier_spacing_khz: float  # 15, 30, 60, 120 kHz


class IParameterPublisher(ABC):
    """参数发布器接口"""

    @abstractmethod
    async def publish_large_scale(self, params: LargeScaleParams) -> bool:
        """发布大尺度参数 (低延迟要求)"""
        pass

    @abstractmethod
    async def publish_channel_matrix(self, matrix: ChannelMatrix) -> bool:
        """发布信道矩阵 (高带宽要求)"""
        pass

    @abstractmethod
    def get_publish_latency_ms(self) -> float:
        """获取最近一次发布的延迟"""
        pass


class IParameterSubscriber(ABC):
    """参数订阅器接口 (HAL 层实现)"""

    @abstractmethod
    async def on_large_scale_update(self, params: LargeScaleParams):
        """接收大尺度参数更新"""
        pass

    @abstractmethod
    async def on_channel_matrix_update(self, matrix: ChannelMatrix):
        """接收信道矩阵更新"""
        pass
```

#### 3.2.2 ZeroMQ 实现

```python
# channel-engine-service/sync/zmq_publisher.py

import zmq
import zmq.asyncio
import json
import numpy as np
from multiprocessing import shared_memory
import struct
from typing import Optional
import asyncio
import time

from .publisher import (
    IParameterPublisher,
    LargeScaleParams,
    ChannelMatrix,
    SyncTimestamp
)


class ZeroMQParameterPublisher(IParameterPublisher):
    """
    基于 ZeroMQ 的参数发布器

    通信模式:
    - 大尺度参数: ZMQ PUB/SUB (JSON)
    - 信道矩阵: SharedMemory + ZMQ 通知
    """

    # IPC 端点
    LARGE_SCALE_ENDPOINT = "ipc:///tmp/mimo_large_scale_params"
    MATRIX_NOTIFY_ENDPOINT = "ipc:///tmp/mimo_matrix_notify"

    # 共享内存配置
    SHM_NAME = "mimo_channel_matrix"
    SHM_SIZE = 256 * 1024 * 1024  # 256MB (支持大规模MIMO)

    def __init__(self):
        self.context = zmq.asyncio.Context()

        # 大尺度参数发布 socket
        self.large_scale_socket = self.context.socket(zmq.PUB)
        self.large_scale_socket.setsockopt(zmq.SNDHWM, 100)  # 发送高水位
        self.large_scale_socket.bind(self.LARGE_SCALE_ENDPOINT)

        # 信道矩阵通知 socket
        self.matrix_notify_socket = self.context.socket(zmq.PUB)
        self.matrix_notify_socket.bind(self.MATRIX_NOTIFY_ENDPOINT)

        # 共享内存 (延迟初始化)
        self._shm: Optional[shared_memory.SharedMemory] = None
        self._shm_buffer: Optional[np.ndarray] = None

        # 延迟监控
        self._last_latency_ms: float = 0.0

    def _ensure_shared_memory(self, required_size: int):
        """确保共享内存已分配且足够大"""
        if self._shm is None or self._shm.size < required_size:
            # 清理旧的共享内存
            if self._shm is not None:
                self._shm.close()
                self._shm.unlink()

            # 创建新的共享内存
            actual_size = max(required_size, self.SHM_SIZE)
            self._shm = shared_memory.SharedMemory(
                name=self.SHM_NAME,
                create=True,
                size=actual_size
            )

    async def publish_large_scale(self, params: LargeScaleParams) -> bool:
        """发布大尺度参数"""
        start_time = time.perf_counter()

        try:
            # 序列化为 JSON
            data = {
                "timestamp": {
                    "wall_clock": params.timestamp.wall_clock.isoformat(),
                    "simulation_time": params.timestamp.simulation_time,
                    "frame_number": params.timestamp.frame_number,
                    "sequence_id": params.timestamp.sequence_id,
                },
                "path_loss_db": params.path_loss_db,
                "aod_azimuth": params.aod_azimuth,
                "aod_elevation": params.aod_elevation,
                "aoa_azimuth": params.aoa_azimuth,
                "aoa_elevation": params.aoa_elevation,
                "delay_ns": params.delay_ns,
                "doppler_hz": params.doppler_hz,
                "xpr_db": params.xpr_db,
            }

            if params.cluster_powers:
                data["cluster_powers"] = params.cluster_powers
                data["cluster_delays"] = params.cluster_delays

            # 发送 (非阻塞)
            await self.large_scale_socket.send_json(data, zmq.NOBLOCK)

            self._last_latency_ms = (time.perf_counter() - start_time) * 1000
            return True

        except zmq.Again:
            # 缓冲区满，丢弃旧数据
            return False
        except Exception as e:
            print(f"[ZMQ Publisher] Large scale publish error: {e}")
            return False

    async def publish_channel_matrix(self, matrix: ChannelMatrix) -> bool:
        """发布信道矩阵 (通过共享内存)"""
        start_time = time.perf_counter()

        try:
            # 计算所需内存
            # Header: 64 bytes (元数据)
            # Data: H.nbytes
            header_size = 64
            data_size = matrix.H.nbytes
            total_size = header_size + data_size

            # 确保共享内存足够
            self._ensure_shared_memory(total_size)

            # 写入 header
            # Format: seq_id (8) + sim_time (8) + frame (8) +
            #         n_rx (4) + n_tx (4) + n_sc (4) + n_sym (4) +
            #         scs_khz (4) + data_size (8) + reserved (8)
            header = struct.pack(
                '<QddIIIIfQQ',
                matrix.timestamp.sequence_id,
                matrix.timestamp.simulation_time,
                float(matrix.timestamp.frame_number),
                matrix.n_rx,
                matrix.n_tx,
                matrix.n_subcarriers,
                matrix.n_ofdm_symbols,
                matrix.subcarrier_spacing_khz,
                data_size,
                0  # reserved
            )
            self._shm.buf[:header_size] = header

            # 写入信道矩阵数据
            matrix_bytes = matrix.H.tobytes()
            self._shm.buf[header_size:header_size + data_size] = matrix_bytes

            # 发送通知 (包含序列号和大小)
            notify_msg = {
                "sequence_id": matrix.timestamp.sequence_id,
                "shm_name": self.SHM_NAME,
                "total_size": total_size,
                "header_size": header_size,
            }
            await self.matrix_notify_socket.send_json(notify_msg, zmq.NOBLOCK)

            self._last_latency_ms = (time.perf_counter() - start_time) * 1000
            return True

        except Exception as e:
            print(f"[ZMQ Publisher] Channel matrix publish error: {e}")
            return False

    def get_publish_latency_ms(self) -> float:
        return self._last_latency_ms

    def close(self):
        """清理资源"""
        self.large_scale_socket.close()
        self.matrix_notify_socket.close()
        self.context.term()

        if self._shm is not None:
            self._shm.close()
            try:
                self._shm.unlink()
            except FileNotFoundError:
                pass
```

#### 3.2.3 参数缓冲器

```python
# channel-engine-service/sync/buffer.py

from collections import deque
from dataclasses import dataclass
from typing import Optional, Generic, TypeVar
import threading
import time

T = TypeVar('T')


@dataclass
class BufferedItem(Generic[T]):
    """带时间戳的缓冲项"""
    data: T
    received_at: float  # perf_counter 时间
    sequence_id: int


class RingBuffer(Generic[T]):
    """
    线程安全的环形缓冲区
    用于保存历史参数，支持按时间戳或序列号查询
    """

    def __init__(self, capacity: int = 100):
        self._buffer: deque[BufferedItem[T]] = deque(maxlen=capacity)
        self._lock = threading.RLock()
        self._latest_seq: int = -1

    def push(self, item: T, sequence_id: int) -> None:
        """添加新项"""
        with self._lock:
            buffered = BufferedItem(
                data=item,
                received_at=time.perf_counter(),
                sequence_id=sequence_id
            )
            self._buffer.append(buffered)
            self._latest_seq = sequence_id

    def get_latest(self) -> Optional[T]:
        """获取最新项"""
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[-1].data

    def get_by_sequence(self, sequence_id: int) -> Optional[T]:
        """按序列号查询"""
        with self._lock:
            for item in reversed(self._buffer):
                if item.sequence_id == sequence_id:
                    return item.data
            return None

    def get_history(self, count: int) -> list[T]:
        """获取最近 N 个项"""
        with self._lock:
            items = list(self._buffer)[-count:]
            return [item.data for item in items]

    @property
    def latest_sequence_id(self) -> int:
        return self._latest_seq


class DoubleBuffer(Generic[T]):
    """
    双缓冲区 - 用于无锁读写
    写入者写入后台缓冲区，完成后交换
    """

    def __init__(self):
        self._buffers: list[Optional[T]] = [None, None]
        self._front_index: int = 0
        self._lock = threading.Lock()
        self._swap_count: int = 0

    def write(self, data: T) -> None:
        """写入后台缓冲区并交换"""
        back_index = 1 - self._front_index
        self._buffers[back_index] = data

        with self._lock:
            self._front_index = back_index
            self._swap_count += 1

    def read(self) -> Optional[T]:
        """读取前台缓冲区 (无锁)"""
        return self._buffers[self._front_index]

    @property
    def swap_count(self) -> int:
        return self._swap_count
```

### 3.3 同步监控

```python
# channel-engine-service/sync/monitor.py

from dataclasses import dataclass, field
from typing import Optional
from collections import deque
import time
import statistics
import threading


@dataclass
class SyncMetrics:
    """同步性能指标"""
    # 延迟统计 (ms)
    latency_avg_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    latency_max_ms: float = 0.0

    # 抖动 (ms)
    jitter_ms: float = 0.0

    # 吞吐量
    messages_per_second: float = 0.0
    bytes_per_second: float = 0.0

    # 健康状态
    dropped_count: int = 0
    error_count: int = 0
    is_healthy: bool = True


class SyncMonitor:
    """
    同步监控器
    跟踪 L2 层的同步性能指标
    """

    # 延迟阈值 (ms)
    LATENCY_WARNING_THRESHOLD = 5.0
    LATENCY_ERROR_THRESHOLD = 10.0

    def __init__(self, window_size: int = 1000):
        self._latencies: deque[float] = deque(maxlen=window_size)
        self._timestamps: deque[float] = deque(maxlen=window_size)
        self._message_sizes: deque[int] = deque(maxlen=window_size)

        self._dropped_count: int = 0
        self._error_count: int = 0
        self._lock = threading.Lock()

        self._start_time = time.perf_counter()

    def record_publish(self, latency_ms: float, message_size: int = 0):
        """记录一次发布"""
        with self._lock:
            now = time.perf_counter()
            self._latencies.append(latency_ms)
            self._timestamps.append(now)
            self._message_sizes.append(message_size)

    def record_drop(self):
        """记录丢弃"""
        with self._lock:
            self._dropped_count += 1

    def record_error(self):
        """记录错误"""
        with self._lock:
            self._error_count += 1

    def get_metrics(self) -> SyncMetrics:
        """获取当前指标"""
        with self._lock:
            if not self._latencies:
                return SyncMetrics()

            latencies = list(self._latencies)
            timestamps = list(self._timestamps)
            sizes = list(self._message_sizes)

        # 延迟统计
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        metrics = SyncMetrics(
            latency_avg_ms=statistics.mean(latencies),
            latency_p50_ms=sorted_latencies[n // 2],
            latency_p95_ms=sorted_latencies[int(n * 0.95)],
            latency_p99_ms=sorted_latencies[int(n * 0.99)],
            latency_max_ms=max(latencies),
        )

        # 抖动 (延迟的标准差)
        if len(latencies) > 1:
            metrics.jitter_ms = statistics.stdev(latencies)

        # 吞吐量
        if len(timestamps) >= 2:
            time_span = timestamps[-1] - timestamps[0]
            if time_span > 0:
                metrics.messages_per_second = len(timestamps) / time_span
                metrics.bytes_per_second = sum(sizes) / time_span

        # 健康状态
        metrics.dropped_count = self._dropped_count
        metrics.error_count = self._error_count
        metrics.is_healthy = (
            metrics.latency_p95_ms < self.LATENCY_ERROR_THRESHOLD and
            self._error_count == 0
        )

        return metrics

    def get_health_status(self) -> dict:
        """获取健康状态 (用于 API 暴露)"""
        metrics = self.get_metrics()

        status = "healthy"
        if metrics.latency_p95_ms > self.LATENCY_ERROR_THRESHOLD:
            status = "degraded"
        if metrics.error_count > 0:
            status = "error"

        return {
            "status": status,
            "latency_p95_ms": round(metrics.latency_p95_ms, 2),
            "jitter_ms": round(metrics.jitter_ms, 2),
            "messages_per_second": round(metrics.messages_per_second, 1),
            "dropped_count": metrics.dropped_count,
            "error_count": metrics.error_count,
        }
```

---

## 4. L1/L0 硬件同步服务需求

### 4.1 L0 时钟同步 (纯硬件)

软件层**不直接参与** L0 同步，但需要提供以下服务：

#### 4.1.1 时钟配置服务

```python
# api-service/app/services/clock_service.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ClockSource(Enum):
    """时钟源类型"""
    INTERNAL = "internal"           # 仪器内部时钟
    EXTERNAL_10MHZ = "external_10mhz"  # 外部 10MHz 参考
    EXTERNAL_100MHZ = "external_100mhz"
    PXI_BACKPLANE = "pxi_backplane"  # PXI 背板时钟
    GPS = "gps"                      # GPS 授时


class ClockSyncStatus(Enum):
    """时钟同步状态"""
    UNLOCKED = "unlocked"           # 未锁定
    LOCKING = "locking"             # 正在锁定
    LOCKED = "locked"               # 已锁定
    HOLDOVER = "holdover"           # 保持模式 (参考丢失)
    ERROR = "error"


@dataclass
class ClockConfig:
    """时钟配置"""
    source: ClockSource
    reference_frequency_hz: float = 10_000_000  # 10 MHz
    output_enabled: bool = True                  # 是否输出参考


@dataclass
class ClockStatus:
    """时钟状态"""
    sync_status: ClockSyncStatus
    source: ClockSource
    frequency_offset_ppb: float    # 频率偏移 (ppb)
    phase_offset_ps: float         # 相位偏移 (ps)
    lock_time_seconds: float       # 锁定时间


class ClockService:
    """
    时钟管理服务

    职责:
    1. 配置各仪器的时钟源
    2. 监控时钟锁定状态
    3. 验证系统时钟一致性
    """

    async def configure_clock(
        self,
        instrument_id: str,
        config: ClockConfig
    ) -> bool:
        """配置仪器时钟源"""
        # TODO: 通过 HAL 发送 SCPI 命令
        # 例如: :ROSC:SOUR EXT
        #       :ROSC:EXT:FREQ 10E6
        pass

    async def get_clock_status(self, instrument_id: str) -> ClockStatus:
        """获取时钟状态"""
        # TODO: 查询仪器时钟状态
        pass

    async def verify_system_clock_coherence(self) -> dict:
        """
        验证系统时钟一致性
        检查所有仪器是否锁定到同一参考
        """
        # TODO: 遍历所有仪器，检查时钟状态
        pass
```

#### 4.1.2 时钟拓扑配置

```yaml
# config/clock_topology.yaml

# 时钟分配拓扑
clock_distribution:
  master_source: "GPS_DISCIPLINED_OSCILLATOR"
  reference_frequency: 10_000_000  # 10 MHz

  # 分配树
  distribution_tree:
    - output: "SPLITTER_1"
      destinations:
        - instrument: "channel_emulator"
          port: "REF_IN"
        - instrument: "base_station_emulator"
          port: "REF_IN"

    - output: "SPLITTER_2"
      destinations:
        - instrument: "signal_analyzer"
          port: "REF_IN"
        - instrument: "power_meter"
          port: "EXT_REF"

# 验证规则
validation_rules:
  max_frequency_offset_ppb: 50
  max_phase_offset_ps: 100
  lock_timeout_seconds: 30
```

### 4.2 L1 触发同步

#### 4.2.1 触发配置服务

```python
# api-service/app/services/trigger_service.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List


class TriggerSource(Enum):
    """触发源"""
    IMMEDIATE = "immediate"         # 立即触发
    EXTERNAL = "external"           # 外部触发输入
    SOFTWARE = "software"           # 软件触发
    TIMER = "timer"                 # 定时触发
    BUS = "bus"                     # 触发总线 (PXI)
    VIDEO = "video"                 # 视频触发 (示波器)


class TriggerEdge(Enum):
    """触发沿"""
    RISING = "rising"
    FALLING = "falling"
    EITHER = "either"


class TriggerMode(Enum):
    """触发模式"""
    SINGLE = "single"               # 单次触发
    CONTINUOUS = "continuous"       # 连续触发
    GATED = "gated"                 # 门控触发


@dataclass
class TriggerConfig:
    """触发配置"""
    source: TriggerSource
    edge: TriggerEdge = TriggerEdge.RISING
    mode: TriggerMode = TriggerMode.SINGLE
    delay_ns: float = 0.0           # 触发延迟
    level_v: float = 1.5            # 触发电平 (外部触发)
    holdoff_ns: float = 0.0         # 触发保持


@dataclass
class TriggerEvent:
    """触发事件"""
    timestamp_ns: int               # 触发时间戳 (纳秒)
    source: TriggerSource
    event_id: int


class TriggerService:
    """
    触发管理服务

    职责:
    1. 配置仪器触发模式
    2. 编排多仪器触发序列
    3. 监控触发事件
    """

    async def configure_trigger(
        self,
        instrument_id: str,
        config: TriggerConfig
    ) -> bool:
        """配置仪器触发"""
        # TODO: 通过 HAL 发送触发配置命令
        pass

    async def arm_trigger(self, instrument_id: str) -> bool:
        """武装触发 (等待触发)"""
        pass

    async def send_software_trigger(self, instrument_ids: List[str]) -> bool:
        """发送软件触发到多个仪器"""
        # 注意: 软件触发有不确定延迟，仅用于非时间关键操作
        pass

    async def configure_trigger_sequence(
        self,
        sequence: 'TriggerSequence'
    ) -> bool:
        """配置触发序列 (多仪器协调)"""
        pass


@dataclass
class TriggerSequence:
    """
    触发序列 - 定义多仪器的触发时序关系

    示例: 信道仿真器开始 -> 100μs -> 基站开始发送 -> 信号分析仪开始采集
    """
    name: str
    steps: List['TriggerStep']


@dataclass
class TriggerStep:
    """触发步骤"""
    instrument_id: str
    action: str                     # "arm", "trigger", "wait"
    delay_after_us: float = 0.0     # 此步骤后的延迟
    wait_for_event: Optional[str] = None  # 等待的事件
```

#### 4.2.2 触发序列示例

```python
# 典型的 MIMO OTA 测试触发序列

def create_ota_measurement_trigger_sequence() -> TriggerSequence:
    """创建 OTA 测量触发序列"""
    return TriggerSequence(
        name="ota_measurement",
        steps=[
            # 1. 信道仿真器准备
            TriggerStep(
                instrument_id="channel_emulator",
                action="arm",
                delay_after_us=0
            ),

            # 2. 基站仿真器准备
            TriggerStep(
                instrument_id="base_station",
                action="arm",
                delay_after_us=0
            ),

            # 3. 信号分析仪准备采集
            TriggerStep(
                instrument_id="signal_analyzer",
                action="arm",
                delay_after_us=0
            ),

            # 4. 发送主触发 (通过触发总线)
            TriggerStep(
                instrument_id="trigger_controller",
                action="trigger",
                delay_after_us=100  # 100μs 后开始采集
            ),

            # 5. 等待测量完成
            TriggerStep(
                instrument_id="signal_analyzer",
                action="wait",
                wait_for_event="measurement_complete"
            ),
        ]
    )
```

### 4.3 同步控制器设计

```python
# api-service/app/services/sync_controller.py

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import asyncio


class SyncState(Enum):
    """同步状态"""
    IDLE = "idle"
    CONFIGURING = "configuring"
    SYNCHRONIZED = "synchronized"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class SystemSyncStatus:
    """系统同步状态"""
    state: SyncState

    # L0 状态
    clock_locked: bool
    clock_source: str

    # L1 状态
    trigger_armed: bool
    trigger_sequence: Optional[str]

    # L2 状态
    parameter_latency_ms: float
    parameter_jitter_ms: float

    # 各仪器状态
    instrument_states: Dict[str, str]


class SyncController:
    """
    同步控制器

    协调 L0/L1/L2 三层同步，提供统一的同步管理接口
    """

    def __init__(
        self,
        clock_service: 'ClockService',
        trigger_service: 'TriggerService',
        parameter_publisher: 'IParameterPublisher',
        sync_monitor: 'SyncMonitor'
    ):
        self._clock = clock_service
        self._trigger = trigger_service
        self._publisher = parameter_publisher
        self._monitor = sync_monitor

        self._state = SyncState.IDLE
        self._instruments: Dict[str, str] = {}

    async def initialize_sync(self, topology_config: dict) -> bool:
        """
        初始化系统同步

        1. 配置时钟分配
        2. 验证时钟锁定
        3. 配置默认触发模式
        4. 启动参数发布
        """
        self._state = SyncState.CONFIGURING

        try:
            # L0: 配置时钟
            for instrument in topology_config.get("instruments", []):
                await self._clock.configure_clock(
                    instrument["id"],
                    ClockConfig(source=ClockSource.EXTERNAL_10MHZ)
                )

            # 等待时钟锁定
            await self._wait_for_clock_lock(timeout_seconds=30)

            # L1: 配置默认触发
            for instrument in topology_config.get("instruments", []):
                await self._trigger.configure_trigger(
                    instrument["id"],
                    TriggerConfig(source=TriggerSource.BUS)
                )

            self._state = SyncState.SYNCHRONIZED
            return True

        except Exception as e:
            self._state = SyncState.ERROR
            raise

    async def _wait_for_clock_lock(self, timeout_seconds: float):
        """等待所有仪器时钟锁定"""
        start_time = asyncio.get_event_loop().time()

        while True:
            coherence = await self._clock.verify_system_clock_coherence()
            if coherence.get("all_locked", False):
                return

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                raise TimeoutError("Clock lock timeout")

            await asyncio.sleep(0.5)

    async def start_measurement(
        self,
        trigger_sequence: TriggerSequence,
        channel_params: 'LargeScaleParams'
    ) -> bool:
        """
        启动测量

        1. 发布信道参数 (L2)
        2. 配置触发序列 (L1)
        3. 执行触发
        """
        if self._state != SyncState.SYNCHRONIZED:
            raise RuntimeError(f"Invalid state for measurement: {self._state}")

        self._state = SyncState.RUNNING

        try:
            # L2: 发布信道参数
            await self._publisher.publish_large_scale(channel_params)

            # 等待参数传播 (确保硬件已接收)
            await asyncio.sleep(0.010)  # 10ms

            # L1: 配置并执行触发序列
            await self._trigger.configure_trigger_sequence(trigger_sequence)

            # 执行触发
            for step in trigger_sequence.steps:
                if step.action == "arm":
                    await self._trigger.arm_trigger(step.instrument_id)
                elif step.action == "trigger":
                    # 发送触发
                    pass
                elif step.action == "wait":
                    # 等待事件
                    pass

                if step.delay_after_us > 0:
                    await asyncio.sleep(step.delay_after_us / 1_000_000)

            return True

        finally:
            self._state = SyncState.SYNCHRONIZED

    def get_sync_status(self) -> SystemSyncStatus:
        """获取同步状态"""
        metrics = self._monitor.get_metrics()

        return SystemSyncStatus(
            state=self._state,
            clock_locked=True,  # TODO: 实际查询
            clock_source="external_10mhz",
            trigger_armed=False,
            trigger_sequence=None,
            parameter_latency_ms=metrics.latency_avg_ms,
            parameter_jitter_ms=metrics.jitter_ms,
            instrument_states=self._instruments
        )
```

---

## 5. API 设计

### 5.1 同步状态 API

```yaml
# 添加到 api/openapi.yaml

paths:
  /api/v1/sync/status:
    get:
      summary: 获取系统同步状态
      tags: [Sync]
      responses:
        200:
          description: 同步状态
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SystemSyncStatus'

  /api/v1/sync/clock:
    get:
      summary: 获取时钟状态
      tags: [Sync]
      responses:
        200:
          description: 时钟状态
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ClockStatus'

    post:
      summary: 配置时钟
      tags: [Sync]
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ClockConfig'

  /api/v1/sync/trigger/sequence:
    post:
      summary: 配置触发序列
      tags: [Sync]
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TriggerSequence'

  /api/v1/sync/metrics:
    get:
      summary: 获取同步性能指标
      tags: [Sync]
      responses:
        200:
          description: 性能指标
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SyncMetrics'

components:
  schemas:
    SystemSyncStatus:
      type: object
      properties:
        state:
          type: string
          enum: [idle, configuring, synchronized, running, error]
        clock_locked:
          type: boolean
        clock_source:
          type: string
        trigger_armed:
          type: boolean
        parameter_latency_ms:
          type: number
        parameter_jitter_ms:
          type: number
        instrument_states:
          type: object
          additionalProperties:
            type: string

    ClockStatus:
      type: object
      properties:
        sync_status:
          type: string
          enum: [unlocked, locking, locked, holdover, error]
        source:
          type: string
        frequency_offset_ppb:
          type: number
        phase_offset_ps:
          type: number
        lock_time_seconds:
          type: number

    SyncMetrics:
      type: object
      properties:
        latency_avg_ms:
          type: number
        latency_p95_ms:
          type: number
        latency_p99_ms:
          type: number
        jitter_ms:
          type: number
        messages_per_second:
          type: number
        dropped_count:
          type: integer
        error_count:
          type: integer
        is_healthy:
          type: boolean
```

---

## 6. 实现路线图

### Phase 1: 基础架构 (当前)

- [x] 定义同步层级和接口
- [ ] 实现 ZeroMQ 参数发布器
- [ ] 实现共享内存信道矩阵传输
- [ ] 实现同步监控器

### Phase 2: HAL 集成

- [ ] 实现 ClockService (SCPI 命令)
- [ ] 实现 TriggerService (SCPI 命令)
- [ ] 实现 SyncController 基础版本
- [ ] 添加同步状态 API

### Phase 3: 硬件验证

- [ ] 与真实信道仿真器集成测试
- [ ] 时钟同步验证 (频谱仪测量)
- [ ] 触发时序验证 (示波器测量)
- [ ] 端到端延迟测量

### Phase 4: 优化

- [ ] 延迟优化 (目标 L2 < 5ms)
- [ ] 添加 gRPC 备选通信
- [ ] 实现自适应缓冲
- [ ] 添加告警和自动恢复

---

## 7. 测试策略

### 7.1 单元测试

```python
# tests/test_sync_publisher.py

import pytest
import numpy as np
from datetime import datetime

from channel_engine_service.sync.publisher import (
    LargeScaleParams, ChannelMatrix, SyncTimestamp
)
from channel_engine_service.sync.zmq_publisher import ZeroMQParameterPublisher


class TestZeroMQPublisher:

    @pytest.fixture
    def publisher(self):
        pub = ZeroMQParameterPublisher()
        yield pub
        pub.close()

    @pytest.mark.asyncio
    async def test_publish_large_scale_params(self, publisher):
        params = LargeScaleParams(
            timestamp=SyncTimestamp(
                wall_clock=datetime.now(),
                simulation_time=1.0,
                frame_number=100,
                sequence_id=1
            ),
            path_loss_db=[100.0, 105.0, 110.0],
            aod_azimuth=[0.0, 45.0, 90.0],
            aod_elevation=[0.0, 10.0, -10.0],
            aoa_azimuth=[180.0, 225.0, 270.0],
            aoa_elevation=[0.0, 5.0, -5.0],
            delay_ns=[0.0, 100.0, 200.0],
            doppler_hz=[0.0, 10.0, -10.0],
            xpr_db=[8.0, 8.0, 8.0]
        )

        result = await publisher.publish_large_scale(params)
        assert result is True
        assert publisher.get_publish_latency_ms() < 1.0  # < 1ms

    @pytest.mark.asyncio
    async def test_publish_channel_matrix(self, publisher):
        # 创建测试信道矩阵 [32 rx, 4 tx, 100 subcarriers, 14 symbols]
        H = np.random.randn(32, 4, 100, 14) + 1j * np.random.randn(32, 4, 100, 14)
        H = H.astype(np.complex64)

        matrix = ChannelMatrix(
            timestamp=SyncTimestamp(
                wall_clock=datetime.now(),
                simulation_time=1.0,
                frame_number=100,
                sequence_id=1
            ),
            H=H,
            n_rx=32,
            n_tx=4,
            n_subcarriers=100,
            n_ofdm_symbols=14,
            subcarrier_spacing_khz=30.0
        )

        result = await publisher.publish_channel_matrix(matrix)
        assert result is True
        assert publisher.get_publish_latency_ms() < 10.0  # < 10ms
```

### 7.2 集成测试

```python
# tests/test_sync_integration.py

import pytest
import asyncio


class TestSyncIntegration:
    """同步系统集成测试"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires hardware")
    async def test_end_to_end_latency(self):
        """测试端到端参数传输延迟"""
        # 1. 发布参数
        # 2. 在 HAL 层接收
        # 3. 验证延迟 < 10ms
        pass

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires hardware")
    async def test_clock_lock_sequence(self):
        """测试时钟锁定序列"""
        pass

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires hardware")
    async def test_trigger_sequence_execution(self):
        """测试触发序列执行"""
        pass
```

---

## 8. 附录

### A. 参考资料

- ZeroMQ Guide: https://zguide.zeromq.org/
- Python SharedMemory: https://docs.python.org/3/library/multiprocessing.shared_memory.html
- VISA/SCPI Programming: Keysight IO Libraries Suite Documentation

### B. 术语表

| 术语 | 定义 |
|------|------|
| L0 时钟同步 | 基于 10MHz 参考的射频时基同步 |
| L1 触发同步 | 微秒级的事件触发同步 |
| L2 参数同步 | 毫秒级的信道参数传输同步 |
| L3 控制同步 | 应用层的测试流程控制 |
| HAL | 硬件抽象层 (Hardware Abstraction Layer) |
| SCPI | 可编程仪器标准命令 (Standard Commands for Programmable Instruments) |
| PXI | PCI eXtensions for Instrumentation |

### C. 变更日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2025-12-11 | v1.0 | 初始版本 |

---

**文档结束**
