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
)

logger = logging.getLogger(__name__)


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

    现场未证实项 (做成 config 可调, 默认按权威文档; 现场只调配置不改代码, 同 P0-8 哲学):
    - ``port``: TCP 端口号三份在仓文档都没有 (在未到手的主手册 399342)。默认占位, 现场实测 /
      查机箱触摸屏 Info 界面填 binding connection_params.port; 候选见调研文档。
    - ``command_style``: "raw" (默认, 裸命令, 符合文档) | "verbose" (回退 Write/Query 包装,
      仅当 raw 现场无响应时试; 无文档依据)。
    - ``line_terminator``: "cr" (默认, 符合文档) | "lf" | "crlf"。
    """

    # 未经文档证实的占位端口; 真实值现场实测后填 binding connection_params.port。
    # 调研推断候选: 9221 / 5025 / 2001 (均未证实, 见调研文档)。
    _DEFAULT_PORT_UNVERIFIED = 2001
    _TERMINATOR_MAP = {"cr": "\r", "lf": "\n", "crlf": "\r\n"}

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._ip = config.get("ip_address", "127.0.0.1")
        self._port = int(config.get("port") or self._DEFAULT_PORT_UNVERIFIED)
        self._command_style = str(config.get("command_style") or "raw").lower()
        self._line_terminator = self._TERMINATOR_MAP.get(
            str(config.get("line_terminator", "cr")).lower(), "\r"
        )
        self._reader: asyncio.StreamReader = None
        self._writer: asyncio.StreamWriter = None

    async def connect(self) -> bool:
        try:
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
            body = f"Query {cmd}" if cmd.endswith("?") else f"Write {cmd}"
        else:
            body = cmd
        return body + self._line_terminator

    @staticmethod
    def _parse_response(raw: str) -> str:
        """裸响应去终止符。容错: verbose/旧固件可能带 'Read ' 动作前缀, 一并剥。"""
        return raw.replace("Read ", "").strip()

    async def _send_command(self, cmd: str) -> Optional[str]:
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
        cmd = f"{switch_id}_{output_port}"
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
