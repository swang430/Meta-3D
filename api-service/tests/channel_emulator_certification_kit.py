"""P2-62 Channel Emulator adapter 认证模板的第三方测试夹具。

`certfake_ce` 只是一条测试协议，不代表任何真实仪器，也不注册生产 HAL。
这里的 command token 不是 SCPI；它们只用于证明共同 exchange/receipt 管线能
绑定 execution、capture、instrument 与错误队列顺序。
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, ClassVar, Iterator, Literal
from unittest.mock import patch
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator

from app.hal.base import InstrumentCapability, InstrumentMetrics, InstrumentStatus
from app.hal.channel_emulator import (
    CalibrationToneCapability,
    ChannelEmulatorDriver,
)
from app.hal.channel_emulator_manifest import (
    CHANNEL_EMULATOR_OPERATIONS,
    ChannelEmulatorManifest,
    channel_emulator_manifest_for,
)
from app.hal.scpi_evidence import record_exchange_intent, record_exchange_terminal


_CERTFAKE_CE_SOURCE = (
    "tests/channel_emulator_certification_kit.py test fixture contract; "
    "not a vendor manual"
)


class CertFakeChannelEmulatorProfile(BaseModel):
    """测试域第三 adapter 的严格保存配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    adapter: Literal["certfake_ce"]
    endpoint: str
    asset_name: str

    @field_validator("endpoint", "asset_name")
    @classmethod
    def non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("certfake channel emulator profile values must be non-blank")
        return normalized


CERTFAKE_CE_PROFILE = {
    "schema_version": 1,
    "adapter": "certfake_ce",
    "endpoint": "fixture://channel-emulator-1",
    "asset_name": "fixture-native-model",
}


_manifest = channel_emulator_manifest_for(
    adapter_id="certfake_ce",
    model_name="Certification Fixture CE",
    vendor="Test Fixture",
    implemented=CHANNEL_EMULATOR_OPERATIONS,
    load_modes=("native_model", "external_waveform", "parametric_tdl"),
    reason="implemented by the P2-62 test fixture contract",
)
CERTFAKE_CE_MANIFEST = ChannelEmulatorManifest(
    **{
        **_manifest.model_dump(mode="python"),
        "operations": tuple(
            item.model_copy(update={"source_reference": _CERTFAKE_CE_SOURCE})
            for item in _manifest.operations
        ),
    }
)


class CertFakeChannelTransport:
    """脚本化测试传输；支持部分回读、错误、延迟与取消。"""

    def __init__(
        self,
        *,
        partial_fields: set[str] | None = None,
        rejected_operations: set[str] | None = None,
        delay_s: float = 0.0,
        simulated: bool = False,
    ) -> None:
        self.partial_fields = set(partial_fields or ())
        self.rejected_operations = set(rejected_operations or ())
        self.delay_s = delay_s
        self.simulated = simulated
        self.closed = False

    def _exchange(
        self,
        *,
        instrument_id: str,
        operation: str,
        command: str,
        response: str | None = None,
        result_type: str = "ok",
    ) -> str:
        exchange_id = uuid4().hex
        record_exchange_intent(
            exchange_id=exchange_id,
            instrument_id=instrument_id,
            operation=operation,
            command=command,
            simulated=self.simulated,
        )
        record_exchange_terminal(
            exchange_id=exchange_id,
            result_type=result_type,
            response=response,
            simulated=self.simulated,
        )
        return exchange_id

    async def apply(
        self,
        *,
        instrument_id: str,
        operation: str,
        requested: dict[str, Any],
    ) -> bool:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        self._exchange(
            instrument_id=instrument_id,
            operation="write",
            command=f"CERTFIXTURE APPLY {operation}",
        )
        rejected = operation in self.rejected_operations
        self._exchange(
            instrument_id=instrument_id,
            operation="query",
            command=f"CERTFIXTURE ERROR_QUEUE {operation}",
            response="ERROR" if rejected else "CLEAN",
            result_type="response",
        )
        if rejected:
            return False
        for field, value in requested.items():
            if field in self.partial_fields:
                continue
            self._exchange(
                instrument_id=instrument_id,
                operation="query",
                command=f"CERTFIXTURE READBACK {operation} {field}",
                response=json.dumps(value, sort_keys=True),
                result_type="response",
            )
        return True

    def observe(
        self,
        *,
        instrument_id: str,
        operation: str,
        field: str,
        value: Any,
    ) -> Any:
        self._exchange(
            instrument_id=instrument_id,
            operation="query",
            command=f"CERTFIXTURE READBACK {operation} {field}",
            response=json.dumps(value, sort_keys=True),
            result_type="response",
        )
        return value

    def close(self) -> bool:
        self.closed = True
        return True


class CertFakeChannelEmulatorDriver(ChannelEmulatorDriver):
    """只供 P2-62 套件使用的完整第三 adapter。"""

    adapter_manifest: ClassVar[ChannelEmulatorManifest] = CERTFAKE_CE_MANIFEST

    def __init__(self, instrument_id: str, config: dict[str, Any]):
        super().__init__(instrument_id, config)
        self.transport = config.get("transport") or CertFakeChannelTransport()
        self.events: list[str] = []
        self._connection_host = str(config.get("ip_address") or "192.0.2.62")
        self._connection_port = config.get("port")
        self._connection_resource = config.get("resource")
        self._running = False
        self._model = ""
        self._center_mhz = float(config.get("center_frequency_mhz", 3500.0))

    async def _apply(self, operation: str, requested: dict[str, Any]) -> bool:
        return await self.transport.apply(
            instrument_id=self.instrument_id,
            operation=operation,
            requested=requested,
        )

    async def connect(self) -> bool:
        self._status = InstrumentStatus.CONNECTED
        return True

    async def acquire_remote_control(self) -> bool:
        self.events.append("acquire")
        return True

    async def release_to_local_control(self) -> bool:
        self.events.append("release")
        return True

    async def disconnect(self) -> bool:
        self.transport.close()
        self._status = InstrumentStatus.DISCONNECTED
        return True

    async def configure(self, config: dict[str, Any]) -> bool:
        return await self._apply("configure", dict(config))

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="certification_fixture",
                description="P2-62 test-only adapter",
                supported=True,
            )
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.now(timezone.utc),
            metrics={},
            status="diagnostic",
        )

    async def reset(self) -> bool:
        self._running = False
        return True

    async def set_channel_model(
        self, model_type: str, scenario: str, parameters: dict[str, Any]
    ) -> bool:
        ok = await self._apply(
            "set_channel_model",
            {"model_type": model_type, "scenario": scenario, "parameters": parameters},
        )
        if ok:
            self._model = model_type
        return ok

    async def set_mimo_config(
        self,
        tx_antennas: int,
        rx_antennas: int,
        correlation_matrix: list[list[float]] | None = None,
    ) -> bool:
        return await self._apply(
            "set_mimo_config",
            {
                "tx_antennas": tx_antennas,
                "rx_antennas": rx_antennas,
                "correlation_matrix": correlation_matrix,
            },
        )

    async def set_path_loss(
        self, path_loss_db: float, distance_m: float | None = None
    ) -> bool:
        return await self._apply(
            "set_path_loss",
            {"path_loss_db": path_loss_db, "distance_m": distance_m},
        )

    async def set_doppler(
        self, frequency_hz: float, velocity_kmh: float | None = None
    ) -> bool:
        return await self._apply(
            "set_doppler",
            {"frequency_hz": frequency_hz, "velocity_kmh": velocity_kmh},
        )

    async def start_emulation(self) -> bool:
        self.events.append("start")
        ok = await self._apply("start_emulation", {"state": "running"})
        if ok:
            self._running = True
        return ok

    async def stop_emulation(self) -> bool:
        self.events.append("safe-idle")
        ok = await self._apply("stop_emulation", {"state": "idle"})
        if ok:
            self._running = False
        return ok

    async def get_channel_state(self) -> dict[str, Any]:
        return self.transport.observe(
            instrument_id=self.instrument_id,
            operation="get_channel_state",
            field="state",
            value={"running": self._running, "model": self._model},
        )

    async def upload_asc_files(
        self, asc_files_dir: str, cdl_model_name: str = ""
    ) -> bool:
        return await self._apply(
            "upload_asc_files",
            {"waveform_dir": asc_files_dir, "model_name": cdl_model_name},
        )

    async def set_external_attenuators(
        self, attenuator_values_db: list[float]
    ) -> bool:
        return await self._apply(
            "set_external_attenuators", {"attenuator_values_db": attenuator_values_db}
        )

    async def set_baseband_power(
        self, power_dbm: float, input_ports: list[int] | None = None
    ) -> bool:
        return await self._apply(
            "set_baseband_power",
            {"power_dbm": power_dbm, "input_ports": input_ports},
        )

    async def ensure_topology(self) -> bool:
        return await self._apply("ensure_topology", {"topology": "fixture"})

    def get_center_frequency_mhz(self) -> float:
        return self.transport.observe(
            instrument_id=self.instrument_id,
            operation="get_center_frequency_mhz",
            field="center_frequency_mhz",
            value=self._center_mhz,
        )

    async def set_output_gain(self, output_num: int, gain_db: float) -> bool:
        return await self._apply(
            "set_output_gain", {"output_num": output_num, "gain_db": gain_db}
        )

    async def set_output_level_dbm(
        self, level_dbm: float, output_ports: list[int] | None = None
    ) -> bool:
        return await self._apply(
            "set_output_level_dbm",
            {"level_dbm": level_dbm, "output_ports": output_ports},
        )

    async def set_crest_factor(self, input_num: int, crest_db: float) -> bool:
        return await self._apply(
            "set_crest_factor", {"input_num": input_num, "crest_db": crest_db}
        )

    async def measure_input(
        self, input_num: int, measurement_time_s: float = 1.0
    ) -> tuple[float, float]:
        return self.transport.observe(
            instrument_id=self.instrument_id,
            operation="measure_input",
            field="measurement",
            value=(-35.0, 7.0),
        )

    async def autoset_inputs(
        self, input_nums: list[int], measurement_time_s: float = 3.0
    ) -> bool:
        return await self._apply(
            "autoset_inputs",
            {"input_nums": input_nums, "measurement_time_s": measurement_time_s},
        )

    async def get_input_level_limits(self, input_num: int) -> tuple[float, float]:
        return self.transport.observe(
            instrument_id=self.instrument_id,
            operation="get_input_level_limits",
            field="limits",
            value=(-80.0, -5.0),
        )

    async def set_input_measurement_mode(self, input_num: int, mode: Any) -> bool:
        return await self._apply(
            "set_input_measurement_mode", {"input_num": input_num, "mode": str(mode)}
        )

    async def set_burst_trigger_level(
        self, input_num: int, trigger_dbm: float
    ) -> bool:
        return await self._apply(
            "set_burst_trigger_level",
            {"input_num": input_num, "trigger_dbm": trigger_dbm},
        )

    async def get_group_clipping(
        self, group_num: int = 1, reset: bool = False
    ) -> float:
        return self.transport.observe(
            instrument_id=self.instrument_id,
            operation="get_group_clipping",
            field="clipping_db",
            value=0.0,
        )

    async def get_system_status(self) -> tuple[bool, list[str]]:
        return self.transport.observe(
            instrument_id=self.instrument_id,
            operation="get_system_status",
            field="status",
            value=(True, []),
        )

    def get_calibration_tone_capabilities(self) -> list[CalibrationToneCapability]:
        return [CalibrationToneCapability.PASSTHROUGH_ONLY]

    async def set_calibration_tone(
        self, frequency_hz: float, power_dbm: float, ce_port: str | None = None
    ) -> bool:
        return await self._apply(
            "set_calibration_tone",
            {"frequency_hz": frequency_hz, "power_dbm": power_dbm, "ce_port": ce_port},
        )

    async def stop_calibration_tone(self) -> bool:
        return await self._apply("stop_calibration_tone", {"state": "idle"})

    async def set_passthrough_mode(
        self,
        ce_port: str | None = None,
        ce_input_port: str | None = None,
        mode: int | None = None,
    ) -> bool:
        return await self._apply(
            "set_passthrough_mode",
            {"ce_port": ce_port, "ce_input_port": ce_input_port, "mode": mode},
        )

    async def clear_passthrough_mode(self) -> bool:
        return await self._apply("clear_passthrough_mode", {"state": "idle"})

    def build_p0_5_command_evidence(self, **kwargs: Any) -> None:
        return None

    def capture_channel_emulator_certification_identity(self) -> Any:
        from app.services.channel_emulator_certification import (
            build_channel_emulator_certification_identity,
        )

        return build_channel_emulator_certification_identity(
            instrument_id=self.instrument_id,
            adapter_id=self.adapter_manifest.adapter_id,
            model="Certification Fixture CE",
            firmware_version="fixture-1",
            serial_number="fixture-serial",
            options=("fixture-option",),
            options_observed=True,
            simulated=self.transport.simulated,
            captured_from_live_connection=not self.transport.simulated,
        )

    def project_channel_operation_evidence(
        self,
        *,
        operation: str,
        requested: dict[str, Any],
        operation_succeeded: bool | None,
        exchanges: tuple[Any, ...],
        execution_mode: str,
    ) -> dict[str, Any]:
        if execution_mode != "real" or self.transport.simulated:
            projected = super().project_channel_operation_evidence(
                operation=operation,
                requested=requested,
                operation_succeeded=operation_succeeded,
                exchanges=exchanges,
                execution_mode="simulated",
            )
            for field in projected["fields"]:
                field["provenance"] = "simulated"
            return projected

        error_queue = [
            item
            for item in exchanges
            if item.command == f"CERTFIXTURE ERROR_QUEUE {operation}"
        ]
        clean = (
            len(error_queue) == 1
            and error_queue[0].result_type == "response"
            and error_queue[0].response == "CLEAN"
        )
        fields = []
        used_ids: list[str] = []
        for name, requested_value in requested.items():
            readbacks = [
                item
                for item in exchanges
                if item.command == f"CERTFIXTURE READBACK {operation} {name}"
                and item.result_type == "response"
                and item.response is not None
                and not item.simulated
            ]
            confirmed = operation_succeeded is True and clean and len(readbacks) == 1
            applied = None
            if confirmed:
                try:
                    applied = json.loads(readbacks[0].response)
                except (TypeError, ValueError):
                    confirmed = False
            selected_ids = [readbacks[0].exchange_id] if confirmed else []
            used_ids.extend(selected_ids)
            fields.append(
                {
                    "field": str(name),
                    "requested": requested_value,
                    "applied": applied if confirmed else None,
                    "applied_present": confirmed,
                    "status": "confirmed" if confirmed else "unknown",
                    "provenance": "authoritative_readback",
                    "exchange_ids": selected_ids,
                    "source_reference": _CERTFAKE_CE_SOURCE if confirmed else None,
                }
            )
        return {
            "fields": fields,
            "exchange_ids": [item.exchange_id for item in exchanges],
            "error_queue_exchange_ids": [
                item.exchange_id for item in error_queue
            ],
        }

    def get_loaded_emulation_file(self) -> str | None:
        return self._model or None

    def get_active_output_count(self) -> int:
        return 4

    def get_active_input_count(self) -> int:
        return 4

    def get_active_output_ports(self) -> list[int]:
        return [1, 2, 3, 4]

    def get_active_input_ports(self) -> list[int]:
        return [1, 2, 3, 4]


@contextmanager
def temporary_certfake_channel_emulator_registration() -> Iterator[None]:
    """只在一个测试作用域内把第三 adapter 注入 binding resolver。"""

    from app.services import channel_emulator_binding

    original = channel_emulator_binding.get_real_driver_class

    def lookup(category_key: str, model_name: str) -> type | None:
        if (
            category_key == "channelEmulator"
            and model_name == "Certification Fixture CE"
        ):
            return CertFakeChannelEmulatorDriver
        return original(category_key, model_name)

    with patch.object(channel_emulator_binding, "get_real_driver_class", lookup):
        yield
