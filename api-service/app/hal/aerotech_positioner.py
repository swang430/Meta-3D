"""
Aerotech A3200 / Automation1 Positioner Driver
===============================================

Real HAL Driver for Aerotech motion controllers.
Communicates via raw TCP Socket using AeroBasic ASCII commands.

**不使用 SCPI/PyVISA** — Aerotech 使用自有的 AeroBasic 编程语言。
通信日志仍复用 scpi.log 基础设施以保持统一可追溯性。

Protocol:
  TX: 发送 AeroBasic 命令 (ASCII, 以 \\n 结尾)
  RX: '%' = 成功 (可能带返回值), '!' = 错误 + 错误码

References:
  - Aerotech A3200 AeroBasic Programming Manual
  - Aerotech Automation1 AeroScript Reference (for newer controllers)
"""

import asyncio
import logging
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.positioner import PositionerDriver

logger = logging.getLogger(__name__)


# ===========================================================================
# AeroBasic Command Constants
# ===========================================================================

class AeroBasicCmd:
    """
    AeroBasic ASCII 指令集。
    
    适用于 A3200 控制器。Automation1 (AeroScript) 使用者
    需要调整为对应的函数式语法 (如 MoveAbsolute(X, angle))。
    """
    # 系统
    ACKNOWLEDGE_ALL = "ACKNOWLEDGEALL"   # 清除所有轴错误
    ENABLE = "ENABLE {axes}"              # 启用轴 (e.g., "ENABLE X Y")
    DISABLE = "DISABLE {axes}"            # 禁用轴
    HOME = "HOME {axes}"                  # 回原点
    
    # 运动
    MOVE_ABS = "MOVEABS {axes} {positions}"   # 绝对定位 (e.g., "MOVEABS X 90.0 Y 0.0")
    MOVE_INC = "MOVEINC {axes} {distances}"   # 增量运动
    ABORT = "ABORT {axes}"                     # 紧急停止
    
    # 状态查询
    POSITION_FEEDBACK = "PFBK({axis})"    # 位置反馈 (返回浮点数)
    AXIS_STATUS = "AXISSTATUS({axis})"    # 轴状态位掩码
    VELOCITY_FEEDBACK = "VFBK({axis})"    # 速度反馈
    
    # IDN 等效 (A3200 无标准 *IDN?, 用 GETPARM 读取)
    GET_PARAM = "GETPARM({axis}, {param_id})"  # 读取参数


# AxisStatus 位掩码定义
class AxisStatusBit:
    """A3200 AXISSTATUS 位掩码中的关键位"""
    ENABLED = 0           # bit 0: 轴已启用
    HOMED = 1             # bit 1: 已回原点
    IN_POSITION = 2       # bit 2: 到位 (运动完成)
    MOVE_ACTIVE = 3       # bit 3: 正在运动
    ACCEL_PHASE = 4       # bit 4: 加速阶段
    DECEL_PHASE = 5       # bit 5: 减速阶段
    FAULT = 10            # bit 10: 错误/故障


class AerotechError(Exception):
    """Aerotech 控制器返回的错误"""
    pass


class RealAerotechDriver(PositionerDriver):
    """
    Aerotech A3200 Real HAL Driver.
    
    通过 TCP Socket 发送 AeroBasic ASCII 命令控制转台。
    不走 PyVISA / SCPI，直接使用 asyncio 的 TCP 流。
    
    配置参数 (config dict):
        ip: 控制器 IP 地址 (默认 192.168.1.10)
        port: TCP 端口 (默认 8000, A3200 ASCII Interface)
        azimuth_axis: 方位角轴名 (默认 "X")
        elevation_axis: 俯仰角轴名 (默认 "Y")
        timeout_s: 命令超时秒数 (默认 10)
        settle_timeout_s: 到位等待超时 (默认 60)
        poll_interval_s: 状态轮询间隔 (默认 0.2)
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address: str = config.get("ip", "192.168.1.10")
        self.port: int = config.get("port", 8000)
        self.az_axis: str = config.get("azimuth_axis", "X")
        self.el_axis: str = config.get("elevation_axis", "Y")
        self.timeout_s: float = config.get("timeout_s", 10.0)
        self.settle_timeout_s: float = config.get("settle_timeout_s", 60.0)
        self.poll_interval_s: float = config.get("poll_interval_s", 0.2)

        # asyncio TCP 流
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

        # 缓存的位置
        self._current_azimuth: float = 0.0
        self._current_elevation: float = 0.0

        # 通信锁 (串行化命令发送，防止交错)
        self._lock = asyncio.Lock()

    # ==================================================================
    # 底层通信
    # ==================================================================

    async def _send(self, cmd: str) -> str:
        """
        发送 AeroBasic 命令并等待响应。
        
        AeroBasic TCP 协议:
          TX: 命令字符串 + '\\n'
          RX: '%' + 可选返回值  (成功)
              '!' + 错误码       (失败)
        
        Returns:
            响应内容 (去掉 '%' 前缀)
            
        Raises:
            AerotechError: 当控制器返回 '!' 错误响应时
            asyncio.TimeoutError: 当超时未收到响应时
        """
        if not self._writer or not self._reader:
            raise AerotechError("Not connected to Aerotech controller")

        async with self._lock:
            # 记录到通信日志 (复用 scpi.log 基础设施)
            self._scpi_logger.debug(
                f"TX: {cmd}",
                extra={"instrument_id": self.instrument_id, "direction": "TX"},
            )

            # 发送
            self._writer.write((cmd + "\n").encode("ascii"))
            await self._writer.drain()

            # 接收响应
            raw = await asyncio.wait_for(
                self._reader.readline(), timeout=self.timeout_s
            )
            response = raw.decode("ascii", errors="replace").strip()

            # 记录响应
            self._scpi_logger.debug(
                f"RX: {response}",
                extra={
                    "instrument_id": self.instrument_id,
                    "direction": "RX",
                    "query": cmd,
                },
            )

            # 解析响应
            if response.startswith("!"):
                error_msg = f"AeroBasic error for '{cmd}': {response}"
                logger.error(f"[Aerotech] {error_msg}")
                raise AerotechError(error_msg)

            # 成功: 去掉 '%' 前缀
            return response.lstrip("%").strip()

    async def _query_value(self, cmd: str) -> float:
        """发送查询命令并解析为浮点数"""
        result = await self._send(cmd)
        try:
            return float(result)
        except ValueError:
            logger.warning(f"[Aerotech] Cannot parse '{result}' as float from '{cmd}'")
            return 0.0

    def _check_status_bit(self, status_int: int, bit: int) -> bool:
        """检查 AXISSTATUS 位掩码中的指定位"""
        return bool(status_int & (1 << bit))

    # ==================================================================
    # InstrumentDriver 基础生命周期
    # ==================================================================

    async def connect(self) -> bool:
        """连接到 Aerotech 控制器并启用轴"""
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            logger.info(
                f"[Aerotech] Connecting to {self.ip_address}:{self.port}"
            )
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip_address, self.port),
                timeout=self.timeout_s,
            )

            # 清除控制器错误缓冲区
            await self._send(AeroBasicCmd.ACKNOWLEDGE_ALL)

            # 启用轴
            axes = f"{self.az_axis} {self.el_axis}"
            await self._send(AeroBasicCmd.ENABLE.format(axes=axes))

            # 读取当前位置作为初始值
            self._current_azimuth = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.az_axis)
            )
            self._current_elevation = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.el_axis)
            )

            logger.info(
                f"[Aerotech] Connected. Position: "
                f"Az={self._current_azimuth:.2f}°, El={self._current_elevation:.2f}°"
            )
            self._set_status(InstrumentStatus.CONNECTED)
            self._clear_error()
            return True

        except Exception as e:
            logger.error(f"[Aerotech] Connection failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def disconnect(self) -> bool:
        """安全断开连接"""
        try:
            if self._writer:
                # 禁用轴
                axes = f"{self.az_axis} {self.el_axis}"
                try:
                    await self._send(AeroBasicCmd.DISABLE.format(axes=axes))
                except Exception:
                    pass  # 断连时忽略发送错误

                self._writer.close()
                await self._writer.wait_closed()
                self._writer = None
                self._reader = None

            self._set_status(InstrumentStatus.DISCONNECTED)
            logger.info("[Aerotech] Disconnected")
            return True

        except Exception as e:
            logger.error(f"[Aerotech] Disconnect error: {e}")
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        """应用运行时配置（速度等参数可在此设置）"""
        # 可扩展: 设置运动速度、加速度等参数
        # 例如: SETPARM(X, MaxSpeed, 20.0)
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="3d_positioning",
                description="Aerotech dual-axis positioning (AeroBasic protocol)",
                supported=True,
                parameters={
                    "azimuth_range": [0, 360],
                    "elevation_range": [-90, 90],
                    "protocol": "AeroBasic/TCP",
                },
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.now(),
            metrics={
                "azimuth": self._current_azimuth,
                "elevation": self._current_elevation,
                "controller": f"Aerotech @ {self.ip_address}:{self.port}",
            },
        )

    async def reset(self) -> bool:
        """回原点"""
        try:
            axes = f"{self.az_axis} {self.el_axis}"
            await self._send(AeroBasicCmd.HOME.format(axes=axes))
            await self._wait_for_settle()
            self._current_azimuth = 0.0
            self._current_elevation = 0.0
            self._set_status(InstrumentStatus.READY)
            return True
        except Exception as e:
            logger.error(f"[Aerotech] Home failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    # ==================================================================
    # PositionerDriver 专有接口
    # ==================================================================

    async def move_to(self, azimuth: float, elevation: float) -> bool:
        """
        命令转台移动到绝对位置。
        
        发送 MOVEABS 后轮询 AXISSTATUS 等待到位 (InPosition bit)。
        """
        try:
            self._set_status(InstrumentStatus.BUSY)
            logger.info(
                f"[Aerotech] Moving to Az={azimuth:.2f}°, El={elevation:.2f}°"
            )

            # 构建 MOVEABS 命令
            cmd = AeroBasicCmd.MOVE_ABS.format(
                axes=f"{self.az_axis} {self.el_axis}",
                positions=f"{azimuth:.4f} {elevation:.4f}",
            )
            await self._send(cmd)

            # 等待到位
            await self._wait_for_settle()

            # 读取实际位置
            self._current_azimuth = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.az_axis)
            )
            self._current_elevation = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.el_axis)
            )

            logger.info(
                f"[Aerotech] Arrived: Az={self._current_azimuth:.2f}°, "
                f"El={self._current_elevation:.2f}°"
            )
            self._set_status(InstrumentStatus.READY)
            return True

        except asyncio.TimeoutError:
            logger.error("[Aerotech] Move timeout — settle not achieved")
            self._set_status(InstrumentStatus.ERROR, "Move timeout")
            return False
        except Exception as e:
            logger.error(f"[Aerotech] Move failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def get_position(self) -> Tuple[float, float]:
        """读取当前位置反馈"""
        try:
            self._current_azimuth = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.az_axis)
            )
            self._current_elevation = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.el_axis)
            )
        except Exception as e:
            logger.warning(f"[Aerotech] Position read failed: {e}")
        return (self._current_azimuth, self._current_elevation)

    async def stop(self) -> bool:
        """紧急停止所有轴"""
        try:
            axes = f"{self.az_axis} {self.el_axis}"
            await self._send(AeroBasicCmd.ABORT.format(axes=axes))
            self._set_status(InstrumentStatus.READY)
            logger.warning("[Aerotech] Emergency stop executed")
            return True
        except Exception as e:
            logger.error(f"[Aerotech] Stop failed: {e}")
            return False

    # ==================================================================
    # 内部辅助
    # ==================================================================

    async def _wait_for_settle(self) -> None:
        """
        轮询 AXISSTATUS 等待运动完成。
        
        检查 InPosition bit (bit 2) 为 1 且 MoveActive bit (bit 3) 为 0。
        超时抛出 asyncio.TimeoutError。
        """
        deadline = asyncio.get_event_loop().time() + self.settle_timeout_s

        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(self.poll_interval_s)

            # 查询两个轴的状态
            az_status_raw = await self._query_value(
                AeroBasicCmd.AXIS_STATUS.format(axis=self.az_axis)
            )
            el_status_raw = await self._query_value(
                AeroBasicCmd.AXIS_STATUS.format(axis=self.el_axis)
            )

            az_status = int(az_status_raw)
            el_status = int(el_status_raw)

            # 检查是否有故障
            if self._check_status_bit(az_status, AxisStatusBit.FAULT):
                raise AerotechError(
                    f"Azimuth axis fault detected (status=0x{az_status:04X})"
                )
            if self._check_status_bit(el_status, AxisStatusBit.FAULT):
                raise AerotechError(
                    f"Elevation axis fault detected (status=0x{el_status:04X})"
                )

            # 两个轴都到位 (InPosition=1, MoveActive=0)
            az_settled = (
                self._check_status_bit(az_status, AxisStatusBit.IN_POSITION)
                and not self._check_status_bit(az_status, AxisStatusBit.MOVE_ACTIVE)
            )
            el_settled = (
                self._check_status_bit(el_status, AxisStatusBit.IN_POSITION)
                and not self._check_status_bit(el_status, AxisStatusBit.MOVE_ACTIVE)
            )

            if az_settled and el_settled:
                return

        raise asyncio.TimeoutError(
            f"Aerotech settle timeout ({self.settle_timeout_s}s)"
        )
