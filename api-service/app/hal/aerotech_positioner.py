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
import socket
from typing import Dict, Any, List, Tuple, Optional
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

    # P2-3: A3200 controllers can be wired single-axis (CAICT bench) or
    # dual-axis (production chamber). Which one a specific unit is gets
    # determined at connect() by probing axis availability; both tokens
    # belong to the model-level "what's possible" set.
    model_capabilities = frozenset({
        "pos.single_axis_az",
        "pos.dual_axis_azel",
    })

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

        # Axes actually recognised by this controller, discovered during
        # connect() via read-only PFBK probes. Chamber DUT turntables are
        # often single-axis (azimuth only — chamber elevation comes from
        # the probe array, not the positioner), so the configured
        # ``elevation_axis`` may legitimately be absent. ``_axes_present``
        # is the authoritative list every per-axis method consults.
        self._axes_present: List[str] = []

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

        Idle-close handling: Ensemble Socket2 silently closes the TCP
        connection after an idle period (field-verified at CAICT
        2026-05-13 — first command after ~30s gap raises BrokenPipe /
        ConnectionReset). One transparent reconnect is attempted; the
        cached ``_axes_present`` is re-ENABLE'd before the original
        command is retried so callers never see the idle close.

        Returns:
            响应内容 (去掉 '%' 前缀)

        Raises:
            AerotechError: 当控制器返回 '!' 错误响应, 或 reconnect 失败时
            asyncio.TimeoutError: 当超时未收到响应时
        """
        if not self._writer or not self._reader:
            raise AerotechError("Not connected to Aerotech controller")

        async with self._lock:
            try:
                return await self._tx_rx(cmd)
            except ConnectionError as e:
                # Idle-close path. Catches the three concrete
                # ``ConnectionError`` subclasses (``ConnectionResetError``,
                # ``BrokenPipeError``, ``ConnectionAbortedError``) plus the
                # ``ConnectionResetError`` we synthesise on EOF readline.
                # Deliberately NOT ``OSError`` here — Python 3.11 unified
                # ``asyncio.TimeoutError`` onto built-in ``TimeoutError``
                # which is itself an ``OSError`` subclass, so catching
                # OSError here would swallow ``wait_for`` timeouts and
                # silently retry slow but otherwise healthy commands.
                # Only one retry — if the controller is genuinely down
                # we don't want to hammer it.
                logger.warning(
                    f"[Aerotech] connection lost during '{cmd}' "
                    f"({type(e).__name__}: {e}) — attempting silent reconnect"
                )
                if not await self._silent_reconnect():
                    raise AerotechError(
                        f"Connection lost during '{cmd}' and reconnect failed"
                    ) from e
                return await self._tx_rx(cmd)

    async def _tx_rx(self, cmd: str) -> str:
        """One write + readline cycle. Assumes the lock is held and the
        socket pair is non-None.

        Raises ``ConnectionResetError`` on EOF (empty readline) so the
        outer retry path treats clean half-closes the same as broken-pipe
        writes — both come from the same controller behaviour, both need
        the same recovery.
        """
        self._scpi_logger.debug(
            f"TX: {cmd}",
            extra={"instrument_id": self.instrument_id, "direction": "TX"},
        )
        self._writer.write((cmd + "\n").encode("ascii"))
        await self._writer.drain()

        raw = await asyncio.wait_for(
            self._reader.readline(), timeout=self.timeout_s
        )
        if raw == b"":
            raise ConnectionResetError(
                "EOF reading from Aerotech controller (socket closed)"
            )
        response = raw.decode("ascii", errors="replace").strip()

        self._scpi_logger.debug(
            f"RX: {response}",
            extra={
                "instrument_id": self.instrument_id,
                "direction": "RX",
                "query": cmd,
            },
        )

        if response.startswith("!"):
            error_msg = f"AeroBasic error for '{cmd}': {response}"
            logger.error(f"[Aerotech] {error_msg}")
            raise AerotechError(error_msg)

        return response.lstrip("%").strip()

    async def _silent_reconnect(self) -> bool:
        """Reopen TCP + restore ACK/ENABLE state after an idle close.

        Returns True on success. Caller (``_send``) only invokes us with
        the lock held — we use ``_tx_rx`` directly during the handshake
        so we don't re-enter the outer retry loop and risk recursion.

        Refuses to run if ``_axes_present`` is empty — that means
        ``connect()`` never finished, so there's no prior good state to
        restore. The caller should raise instead.
        """
        if not self._axes_present:
            return False

        # Tear down the broken pair. ``close()`` is best-effort here —
        # the transport may already be in a half-closed state.
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
        self._reader = None
        self._writer = None

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip_address, self.port),
                timeout=self.timeout_s,
            )
            self._enable_tcp_keepalive(self._writer)
        except Exception as e:
            logger.error(
                f"[Aerotech] silent reconnect: open_connection failed: {e}"
            )
            self._reader = None
            self._writer = None
            return False

        try:
            await self._tx_rx(AeroBasicCmd.ACKNOWLEDGE_ALL)
            await self._tx_rx(
                AeroBasicCmd.ENABLE.format(axes=" ".join(self._axes_present))
            )
        except Exception as e:
            logger.error(
                f"[Aerotech] silent reconnect: handshake failed: {e}"
            )
            if self._writer:
                try:
                    self._writer.close()
                except Exception:
                    pass
            self._reader = None
            self._writer = None
            return False

        logger.info(
            f"[Aerotech] silent reconnect succeeded — re-enabled "
            f"axes={self._axes_present}"
        )
        return True

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

    @staticmethod
    def _enable_tcp_keepalive(writer: asyncio.StreamWriter) -> None:
        """Turn on SO_KEEPALIVE + tight idle/intvl/cnt on the writer's
        underlying socket.

        Why we need this on top of the silent-reconnect path:
        - silent-reconnect only fires AFTER an attempted write or read
          surfaces the close. For polling/probe code that hits the wire
          every few seconds anyway that's fine.
        - Keepalive lets the OS detect half-closes within ~30 s of going
          idle, so the *next* write isn't the discovery event. Matters for
          calibration loops where minutes pass between motion commands.

        Field-verified at CAICT 2026-05-13: NAT/firewall on the lab
        network silently drops idle TCP entries; without keepalive the
        socket appeared healthy until the next write timed out.

        macOS exposes the idle time as ``TCP_KEEPALIVE``, Linux as
        ``TCP_KEEPIDLE``. Setsockopt failures are non-fatal — the socket
        still works without tighter tuning, just falls back to OS default
        keepidle (~2 hours on most systems).
        """
        try:
            sock = writer.get_extra_info("socket")
        except Exception:
            return
        if sock is None:
            return
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError as e:
            logger.debug(f"[Aerotech] SO_KEEPALIVE not settable: {e}")
            return
        # Idle time before keepalive probes start. Aim for ~20s so we
        # detect a half-close well before the next user command, but stay
        # above OS minimums (Linux ≥1, macOS ≥1).
        for optname_attr, value in (
            # Linux
            ("TCP_KEEPIDLE", 20),
            # macOS — same semantics, different name
            ("TCP_KEEPALIVE", 20),
            # Probe interval after first probe
            ("TCP_KEEPINTVL", 5),
            # Probe count before declaring dead
            ("TCP_KEEPCNT", 3),
        ):
            optname = getattr(socket, optname_attr, None)
            if optname is None:
                continue
            try:
                sock.setsockopt(socket.IPPROTO_TCP, optname, value)
            except OSError as e:
                logger.debug(f"[Aerotech] {optname_attr} not settable: {e}")

    async def _probe_axis(self, axis: str) -> bool:
        """Read-only probe: does the controller recognise this axis name?

        Sends ``PFBK(<axis>)`` — pure feedback read, never touches servo
        state. ACK (``%``) means the controller has this axis; NAK (``!``,
        raised as ``AerotechError``) means it doesn't. Used during
        ``connect()`` to decide whether the configured ``elevation_axis``
        actually exists on this hardware.
        """
        try:
            await self._send(AeroBasicCmd.POSITION_FEEDBACK.format(axis=axis))
            return True
        except AerotechError:
            return False

    @property
    def is_single_axis(self) -> bool:
        """True when the controller exposes only the azimuth axis.
        Populated after ``connect()``; meaningless before."""
        return (
            self.az_axis in self._axes_present
            and self.el_axis not in self._axes_present
        )

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
            self._enable_tcp_keepalive(self._writer)

            # 清除控制器错误缓冲区
            await self._send(AeroBasicCmd.ACKNOWLEDGE_ALL)

            # Discover which configured axes actually exist on this
            # controller. Field-verified at CAICT 2026-05-13 that some
            # chamber turntables are azimuth-only — Y NAK on PFBK is
            # the normal case, not a connect failure.
            self._axes_present = []
            if await self._probe_axis(self.az_axis):
                self._axes_present.append(self.az_axis)
            if self.el_axis and await self._probe_axis(self.el_axis):
                self._axes_present.append(self.el_axis)

            if self.az_axis not in self._axes_present:
                raise AerotechError(
                    f"Azimuth axis {self.az_axis!r} not recognised by "
                    f"controller — check `azimuth_axis` config matches "
                    f"the controller's actual axis name."
                )
            # P2-2: mirror axis-discovery outcome to the canonical
            # capability set so plan-level pre-flight (P1-1) can branch
            # on `pos.single_axis_az` vs `pos.dual_axis_azel` without
            # poking at `_axes_present` internals.
            from app.hal.capabilities import (
                POS_DUAL_AXIS_AZEL, POS_SINGLE_AXIS_AZ,
            )
            if self.is_single_axis:
                self._add_capability(POS_SINGLE_AXIS_AZ)
                self._remove_capability(POS_DUAL_AXIS_AZEL)
                logger.info(
                    f"[Aerotech] Single-axis turntable detected — "
                    f"elevation axis {self.el_axis!r} not present on "
                    f"controller. Elevation commands will be ignored; "
                    f"get_position() returns elevation=0.0."
                )
            else:
                self._add_capability(POS_DUAL_AXIS_AZEL)
                self._remove_capability(POS_SINGLE_AXIS_AZ)

            # ENABLE only the axes the controller actually has.
            await self._send(
                AeroBasicCmd.ENABLE.format(axes=" ".join(self._axes_present))
            )

            # Read initial position(s); elevation defaults to 0 in
            # single-axis mode so the PositionerDriver contract still
            # returns a (az, el) tuple.
            self._current_azimuth = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.az_axis)
            )
            self._current_elevation = (
                await self._query_value(
                    AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.el_axis)
                )
                if not self.is_single_axis else 0.0
            )

            logger.info(
                f"[Aerotech] Connected. Axes: {self._axes_present}. "
                f"Position: Az={self._current_azimuth:.2f}°, "
                f"El={self._current_elevation:.2f}°"
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
                # 禁用所有已知存在的轴 (single-axis controllers reject 'DISABLE Y')
                if self._axes_present:
                    try:
                        await self._send(AeroBasicCmd.DISABLE.format(
                            axes=" ".join(self._axes_present)
                        ))
                    except Exception:
                        pass  # 断连时忽略发送错误

                self._writer.close()
                await self._writer.wait_closed()
                self._writer = None
                self._reader = None

            self._axes_present = []
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
        single = self.is_single_axis
        params: Dict[str, Any] = {
            "azimuth_range": [0, 360],
            "protocol": "AeroBasic/TCP",
            "axes_present": list(self._axes_present),
        }
        if not single:
            params["elevation_range"] = [-90, 90]
        return [
            InstrumentCapability(
                name="3d_positioning" if not single else "2d_positioning",
                description=(
                    "Aerotech "
                    + ("single-axis azimuth" if single else "dual-axis")
                    + " positioning (AeroBasic protocol)"
                ),
                supported=True,
                parameters=params,
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
            if not self._axes_present:
                raise AerotechError("Not connected — no axes to home")
            await self._send(AeroBasicCmd.HOME.format(
                axes=" ".join(self._axes_present)
            ))
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
        单轴转台 (无 elevation 轴) 会忽略 elevation 参数, 只移动 azimuth。
        """
        try:
            if not self._axes_present:
                raise AerotechError("Not connected — cannot move")
            self._set_status(InstrumentStatus.BUSY)

            # Single-axis controllers ignore elevation. Warn (not error)
            # so an operator misreading "move(180, 30)" as 3D motion
            # sees something in the log when only az moves.
            if self.is_single_axis and elevation != 0.0:
                logger.warning(
                    f"[Aerotech] Single-axis turntable — elevation="
                    f"{elevation:.2f}° ignored, only Az={azimuth:.2f}° "
                    f"will be commanded."
                )

            logger.info(
                f"[Aerotech] Moving to Az={azimuth:.2f}°"
                + (f", El={elevation:.2f}°" if not self.is_single_axis else "")
            )

            # AeroBasic MOVEABS uses axis-position interleaving:
            #     MOVEABS X 180.0 Y 45.0
            # (NOT MOVEABS X Y 180.0 45.0 — that NAKs because the parser
            # reads tokens as axis,position,axis,position alternating.)
            # Skip the AeroBasicCmd.MOVE_ABS template here for the dual-
            # axis case; the template's two-bucket "{axes} {positions}"
            # shape is wrong for the multi-axis form.
            if self.is_single_axis:
                cmd_str = f"MOVEABS {self.az_axis} {azimuth:.4f}"
            else:
                cmd_str = (
                    f"MOVEABS {self.az_axis} {azimuth:.4f}"
                    f" {self.el_axis} {elevation:.4f}"
                )
            await self._send(cmd_str)

            # 等待到位
            await self._wait_for_settle()

            # Read back actual position(s). Elevation cache stays at 0
            # in single-axis mode.
            self._current_azimuth = await self._query_value(
                AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.az_axis)
            )
            self._current_elevation = (
                await self._query_value(
                    AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.el_axis)
                )
                if not self.is_single_axis else 0.0
            )

            logger.info(
                f"[Aerotech] Arrived: Az={self._current_azimuth:.2f}°"
                + (f", El={self._current_elevation:.2f}°"
                   if not self.is_single_axis else "")
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
            if not self.is_single_axis:
                self._current_elevation = await self._query_value(
                    AeroBasicCmd.POSITION_FEEDBACK.format(axis=self.el_axis)
                )
        except Exception as e:
            logger.warning(f"[Aerotech] Position read failed: {e}")
        return (self._current_azimuth, self._current_elevation)

    async def stop(self) -> bool:
        """紧急停止所有轴"""
        try:
            if not self._axes_present:
                logger.warning("[Aerotech] stop() called before connect — nothing to abort")
                return False
            await self._send(AeroBasicCmd.ABORT.format(
                axes=" ".join(self._axes_present)
            ))
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

            az_status = int(await self._query_value(
                AeroBasicCmd.AXIS_STATUS.format(axis=self.az_axis)
            ))
            if self._check_status_bit(az_status, AxisStatusBit.FAULT):
                raise AerotechError(
                    f"Azimuth axis fault detected (status=0x{az_status & 0xFFFFFFFF:08X})"
                )
            az_settled = (
                self._check_status_bit(az_status, AxisStatusBit.IN_POSITION)
                and not self._check_status_bit(az_status, AxisStatusBit.MOVE_ACTIVE)
            )

            if self.is_single_axis:
                if az_settled:
                    return
                continue

            el_status = int(await self._query_value(
                AeroBasicCmd.AXIS_STATUS.format(axis=self.el_axis)
            ))
            if self._check_status_bit(el_status, AxisStatusBit.FAULT):
                raise AerotechError(
                    f"Elevation axis fault detected (status=0x{el_status & 0xFFFFFFFF:08X})"
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
