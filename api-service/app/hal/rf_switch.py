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
    Real Driver for ETS-Lindgren EMCenter switch components.
    Expects SCPI control like `Write 1:INT_RELAY_A_4\n` -> slot 1, relay A, position 4.
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._ip = config.get("ip_address", "127.0.0.1")
        self._port = config.get("port", 2001)
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

    async def _send_command(self, cmd: str) -> Optional[str]:
        if not self._writer:
            return None
        # ETS-L typically accepts Write or Query prefix via virtual wrappers,
        # but direct raw SCPI might also work depending on the parser. 
        # For safety we wrap in 'Write ' / 'Query ' based on the manual.
        if cmd.endswith("?"):
            formatted_cmd = f"Query {cmd}\n"
        else:
            formatted_cmd = f"Write {cmd}\n"

        try:
            self._writer.write(formatted_cmd.encode("ascii"))
            await self._writer.drain()
            
            # If query, read response
            if "?" in cmd:
                response = await self._reader.readline()
                return response.decode("ascii").strip()
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
        cmd = f"{switch_id}?"
        resp = await self._send_command(cmd)
        if resp:
            try:
                # the manual reads something like 'Read NC\n' or numbers
                return int(resp.replace("Read ", "").strip())
            except ValueError:
                # Fallback mapping for 'NC', 'NO'
                if "NC" in resp: return 0
                if "NO" in resp: return 1
        return -1

    async def reset_paths(self) -> bool:
        success = True
        handled_relays = set()
        
        for item in self._mappings.values():
            relay = str(item.get("switch_id", item.get("relay")))
            if relay and relay not in handled_relays:
                handled_relays.add(relay)
                if "EXT_RELAY" in relay:
                    if not await self._send_command(f"{relay}_0"):
                        success = False
                elif "INT_RELAY" in relay:
                    if not await self._send_command(f"{relay}_NC"):
                        success = False
                        
        return success
