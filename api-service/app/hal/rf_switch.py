"""
RF Switch Matrix HAL

Provides abstract interface, Mock implementation, and Real ETS-Lindgren driver 
for RF switch networks.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
    resolve_configured_instrument_host,
)

logger = logging.getLogger(__name__)


def build_emcenter_switch_command(switch_id: str, output_port: Union[int, str]) -> str:
    return f"{switch_id}_{output_port}"


class RfSwitchDriver(InstrumentDriver):
    """
    Abstract interface for RF Switch Matrices (HAL Layer 2)
    Typically used to route signals from Channel Emulator to various OTA probes.
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._mappings: Dict[str, Any] = config.get("port_maps", {})

    async def configure(self, config: Dict[str, Any]) -> bool:
        if "port_maps" in config:
            self._mappings = config["port_maps"]
        return True

    async def set_mapped_path(self, path_name: str) -> bool:
        """Route based on a predefined mapping."""
        if path_name not in self._mappings:
            logger.error(f"[{self.instrument_id}] Mapping not found for '{path_name}'")
            return False
            
        mapping = self._mappings[path_name]
        switch_id = str(mapping.get("switch_id", mapping.get("relay")))
        output_port = mapping.get("output_port", mapping.get("position", 0))
        input_port = mapping.get("input_port", 0)
        
        return await self.switch_path(switch_id, input_port, int(output_port) if isinstance(output_port, (int, float)) else output_port)

    async def switch_path(self, switch_id: str, input_port: int, output_port: Union[int, str]) -> bool:
        """
        Set a specific switch component to route input_port to output_port.
        For simple SPDT or SP6T, input_port is often implied (e.g. 0).
        output_port can be int (position index) or str ('NC'/'NO' for SPDT).
        """
        raise NotImplementedError

    async def get_path(self, switch_id: str) -> int:
        """
        Get the current active output_port of a switch component.
        """
        raise NotImplementedError

    async def reset_paths(self) -> bool:
        """
        Reset all switches to safe default (e.g., terminated or open).
        """
        raise NotImplementedError


class MockRfSwitch(RfSwitchDriver):
    """Fallback Mock implementation"""

    driver_source = "mock"
    simulated = True

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._states: Dict[str, int] = {}

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def disconnect(self) -> bool:
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        if "port_maps" in config:
            self._mappings = config["port_maps"]
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(name="routing", description="RF Signal Routing", supported=True, parameters={})
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(timestamp=datetime.utcnow(), metrics={"states": self._states})

    async def reset(self) -> bool:
        await self.reset_paths()
        self._set_status(InstrumentStatus.READY)
        return True

    async def switch_path(self, switch_id: str, input_port: int, output_port: Union[int, str]) -> bool:
        # Transparent simulation
        command = build_emcenter_switch_command(switch_id, output_port)
        # Real EMCenter transport treats commands without ``?`` as writes and
        # returns a local success sentinel; do not fabricate an instrument RX.
        self._simulate_scpi_write(command)
        self._states[switch_id] = output_port
        await asyncio.sleep(0.05)
        return True

    async def get_path(self, switch_id: str) -> int:
        return self._states.get(switch_id, 0)

    async def reset_paths(self) -> bool:
        self._states.clear()
        return True


class EtslSwitchDriver(RfSwitchDriver):
    """
    Real Driver for ETS-Lindgren EMCenter switch components (EMSwitch 7001-0xx cards).

    协议 (权威: EMCenter SCPI Commands and Error Codes, Part #1801188 Rev A, 2025-08;
    见 docs/site-debug/2026-06-04-emcenter-switch-protocol.md):
    - 命令格式: ``<slot>[<port>]:<COMMAND>`` 裸文本, **无** "Write"/"Query" 前缀
      —— 文档表格里的 Write/Query/Read 是动作标签, 不是协议的一部分 (旧实现误读, 极可能
      是 2026-05-27 现场 raw socket 无响应的真因之一)。
    - 终止符: **CR (0x0D)**。文档 p5 "carriage return (CR) must terminate each command"
      (文档把 CR 口语写成 LF, 实际是 CR)。旧实现用 LF, 同属无响应嫌疑。
    - SPDT (INT_RELAY A-D): ``<slot>:INT_RELAY_<R>_[NC|NO]``; 回读 -> NC|NO。
    - SP6T (INT_RELAY A-B): ``<slot>:INT_RELAY_<R>_<1-6>``; 回读 -> 1-6 (0=全开)。
    - 外部继电器: ``EXT_RELAY_<A|B>_<0-6>`` (0=无输出)。
    - 互锁: ``INTLK? SAFETYRELAY`` -> 0 正常 / 1 互锁 (Relay A 被硬件锁, 软件无法覆盖)。
    - 双槽卡 (SP6T) 用两槽中靠前的槽号寻址 (文档 p5)。

    Transport (P2-9 现场收口, 2026-07-03 CAICT 实证):
    - ``transport``: **"vxi11" (默认)** | "raw"。老固件 (现场机 2.5.1) LAN **只有
      VXI-11** (rpcinfo 395183/395184@tcp879), raw socket 5025 仅新固件才有 ——
      2026-05-27 现场 raw 无响应的最终真因。VXI-11 走 pyvisa
      ``TCPIP0::{ip}::inst0::INSTR`` + 裸命令 + CR (全通实证); 响应尾带
      ``\\n\\x00``, _parse_response 清洗。raw 路径保留 (新固件/串口桥)。

    现场未证实项 (做成 config 可调, 默认按权威文档; 现场只调配置不改代码, 同 P0-8 哲学):
    - ``port``: 仅 raw transport 用。官方手册不写 LAN 端口 (ETS 系统性不文档化), 默认
      SCPI 行业标准 5025; 真实值查机箱触摸屏 Configuration Screen 后填 binding
      connection_params.port。
    - ``command_style``: "raw" (默认, 裸命令, 符合文档) | "verbose" (回退 Write/Query 包装,
      仅当 raw 现场无响应时试; 无文档依据)。
    - ``line_terminator``: "cr" (默认, 符合文档 + VXI-11 实证) | "lf" | "crlf"。
    """

    # LAN socket 端口: 官方主手册 399342 + SCPI 命令文档均不写 (ETS 系统性不文档化)。默认用 SCPI
    # 行业标准 raw-socket 端口 5025 (IANA/Keysight 标准; EMCenter 命令是裸 SCPI 风格, 有依据非瞎猜)。
    # 现场试序 5025 -> 5024 (SCPI-telnet) -> 23; 不通切串口 plan B (tcp_serial_redirect 桥
    # RS-232 9600 8N1 -> TCP, driver 直接连该 TCP 口)。真实值填 binding connection_params.port。
    _DEFAULT_PORT = 5025
    _TERMINATOR_MAP = {"cr": "\r", "lf": "\n", "crlf": "\r\n"}

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        # Codex #202 R9 P2: HAL 标准路径注入的是 config["ip"] (=binding 的
        # controller_ip, 与 F64/UXM 同惯例), 只认 ip_address 会让标准绑定
        # 落 127.0.0.1 → VXI-11 永远连不上真开关。"ip" 优先 (结构化列权威),
        # ip_address 保留兼容 (onsite 脚本 / 旧 connection_params)。
        self._ip = self._connection_host
        self._port = self._resolved_tcp_port(self._DEFAULT_PORT)
        # P2-9: 默认 vxi11 — 现场机老固件 (2.5.1) 唯一实证 LAN 通路
        self._transport = str(config.get("transport") or "vxi11").lower()
        if self._transport == "vxi11":
            self._reject_incompatible_visa_resource(allowed_type="INSTR")
            self._reject_plain_endpoint_port(fixed_type="VXI-11 INSTR")
            self._reject_nondefault_metadata_port(
                default=self._DEFAULT_PORT, fixed_type="VXI-11 INSTR"
            )
            if self._connection_resource:
                resource_parts = self._connection_resource.split("::")
                if (
                    len(resource_parts) == 4
                    and resource_parts[-1].strip().casefold() == "instr"
                    and resource_parts[2].strip().casefold() != "inst0"
                ):
                    self._connection_config_error = (
                        "ETSL VXI-11 仅接受默认 INSTR 或 inst0::INSTR 资源；"
                        f"不接受子地址 {resource_parts[2]!r}"
                    )
        else:
            self._reject_incompatible_visa_resource(allowed_type="SOCKET")
        self._connection_visa_resource = self._resolved_visa_resource(
            f"TCPIP0::{self._ip}::inst0::INSTR",
            explicit_port_to_socket=(self._transport != "vxi11"),
        )
        self._command_style = str(config.get("command_style") or "raw").lower()
        self._line_terminator = self._TERMINATOR_MAP.get(
            str(config.get("line_terminator", "cr")).lower(), "\r"
        )
        self._reader: asyncio.StreamReader = None
        self._writer: asyncio.StreamWriter = None
        self._visa_rm = None
        self._visa_session = None

    async def connect(self) -> bool:
        if self._connection_config_error or not self._ip:
            return self._fail_missing_connection_address()
        try:
            if self._transport == "vxi11":
                import pyvisa
                self._visa_rm = pyvisa.ResourceManager("@py")
                resource = self._connection_visa_resource
                self._visa_session = await asyncio.to_thread(
                    self._visa_rm.open_resource, resource
                )
                # 终止符交 pyvisa (裸命令 + CR 现场全通); 响应尾 \n\x00 由
                # _parse_response 清洗, 不设 read_termination (避免吞 \x00 前内容)
                self._visa_session.write_termination = self._line_terminator
                self._visa_session.timeout = 5000
                logger.info(f"[EtslSwitch] VXI-11 connected: {resource}")
            else:
                self._reader, self._writer = await asyncio.open_connection(self._ip, self._port)

            # Check safety interlock
            interlock_status = await self._send_command("INTLK? SAFETYRELAY")
            if interlock_status == "1":
                logger.error(f"[EtslSwitch] Hardware Interlock Active. Cannot operate relays.")
                self._set_status(InstrumentStatus.ERROR)
                return False

            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[EtslSwitch] Connection failed: {e}")
            self._set_status(InstrumentStatus.ERROR)
            return False

    async def disconnect(self) -> bool:
        if self._visa_session is not None:
            try:
                await asyncio.to_thread(self._visa_session.close)
            except BaseException:
                pass
            self._visa_session = None
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except BaseException:
                pass
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    def _frame(self, cmd: str) -> str:
        """按 command_style 包装命令体 + 加终止符。

        raw (默认, 权威文档): 裸 ``<slot>:<cmd>`` —— 文档 p5 命令示例无任何前缀。
        verbose (现场逃生): 旧 Write/Query 包装 (无文档依据, 仅当 raw 现场无响应时回退试)。
        """
        if self._command_style == "verbose":
            # 查询判定用 "?" in cmd, 跟 _send_command 读响应的判定一致 —— 否则像
            # `INTLK? SAFETYRELAY` (? 在中间) 会被包成 Write 却又等响应, verbose 下挂死
            # (Codex P2 on PR #130)。
            body = f"Query {cmd}" if "?" in cmd else f"Write {cmd}"
        else:
            body = cmd
        return body + self._line_terminator

    @staticmethod
    def _parse_response(raw: str) -> str:
        """裸响应去终止符。容错: verbose/旧固件可能带 'Read ' 动作前缀, 一并剥;
        VXI-11 响应尾带 ``\\n\\x00`` (2026-07-03 实录), NUL 一并清洗。"""
        return raw.replace("Read ", "").strip("\x00 \t\r\n")

    async def _send_command(self, cmd: str) -> Optional[str]:
        if self._transport == "vxi11":
            return await self._send_command_vxi11(cmd)
        if not self._writer:
            return None
        try:
            self._writer.write(self._frame(cmd).encode("ascii"))
            await self._writer.drain()
            # 查询 (含 '?') 才读响应
            if "?" in cmd:
                response = await self._reader.readline()
                return self._parse_response(response.decode("ascii"))
            return "OK"
        except Exception as e:
            logger.error(f"[EtslSwitch] Command {cmd} failed: {e}")
            return None

    async def _send_command_vxi11(self, cmd: str) -> Optional[str]:
        """VXI-11 路径: 终止符由 pyvisa write_termination 加 (connect 时按
        line_terminator 配), _frame 的 command_style 包装仍生效但不再自拼终止符。"""
        if self._visa_session is None:
            return None
        body = self._frame(cmd)
        if self._line_terminator and body.endswith(self._line_terminator):
            body = body[: -len(self._line_terminator)]
        try:
            if "?" in cmd:
                raw = await asyncio.to_thread(self._visa_session.query, body)
                return self._parse_response(raw)
            await asyncio.to_thread(self._visa_session.write, body)
            return "OK"
        except Exception as e:
            logger.error(f"[EtslSwitch] VXI-11 command {cmd} failed: {e}")
            return None

    async def configure(self, config: Dict[str, Any]) -> bool:
        if "port_maps" in config:
            self._mappings = config["port_maps"]
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(name="etsl_routing", description="EMCenter internal/external relay", supported=True, parameters={})
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(timestamp=datetime.utcnow(), metrics={})

    async def reset(self) -> bool:
        await self.reset_paths()
        return True

    async def switch_path(self, switch_id: str, input_port: int, output_port: Union[int, str]) -> bool:
        """
        Switch path over EMCenter.
        Example switch_id: "1:INT_RELAY_A"
        Translates to -> Write 1:INT_RELAY_A_<output_port>\n
        """
        # ETS-L expects position value. Input_port usually ignored as it's a 1xN switch.
        cmd = build_emcenter_switch_command(switch_id, output_port)
        resp = await self._send_command(cmd)
        return resp is not None

    async def get_path(self, switch_id: str) -> int:
        """回读. SP6T -> 位置 1-6 (0=全开); SPDT -> NC=0 / NO=1.
        响应已由 _send_command/_parse_response 去终止符 + 'Read ' 前缀。"""
        resp = await self._send_command(f"{switch_id}?")
        if resp:
            try:
                return int(resp)
            except ValueError:
                if "NC" in resp:
                    return 0
                if "NO" in resp:
                    return 1
        return -1

    async def reset_paths(self) -> bool:
        """复位各继电器到安全默认。

        EXT_RELAY -> _0 (无输出); SPDT INT_RELAY -> _NC。
        SP6T INT_RELAY 复位语义 (set 0 是否合法 / 安全位是哪个) 文档未明确, 需现场确认 ——
        故 mapping 标 ``relay_type="sp6t"`` 的项**跳过**复位 (不发可能非法的 _NC), 仅 warning。
        mapping item 可加 ``"relay_type": "spdt"|"sp6t"`` 区分 (同名 INT_RELAY 命令对两种卡
        值域不同: SPDT=NC/NO, SP6T=1-6)。
        """
        success = True
        handled_relays = set()

        for item in self._mappings.values():
            relay = str(item.get("switch_id", item.get("relay")))
            if not relay or relay in handled_relays:
                continue
            handled_relays.add(relay)
            relay_type = str(item.get("relay_type", "")).lower()
            if "EXT_RELAY" in relay:
                if not await self._send_command(f"{relay}_0"):
                    success = False
            elif "INT_RELAY" in relay:
                if relay_type == "sp6t":
                    logger.warning(
                        f"[EtslSwitch] SP6T relay '{relay}' reset semantics unconfirmed; "
                        "skipping reset (field-confirm SP6T safe position)."
                    )
                    continue
                if not await self._send_command(f"{relay}_NC"):
                    success = False

        return success
