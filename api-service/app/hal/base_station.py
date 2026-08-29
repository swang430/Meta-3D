"""
Base Station Emulator HAL

Provides interface and mock implementation for base station emulators.
Supports both 5G NR (Keysight UXM) and LTE (R&S CMW500) base station emulators.

应用层统一调用 BaseStationDriver 抽象接口，无需关心底层使用哪种仪器。
"""

import asyncio
import hashlib
import json
import logging
import random
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Dict, Any, Optional, List, ClassVar, Literal
from datetime import datetime, timezone
from uuid import uuid4

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.scpi_evidence import InstrumentEvidenceItem

logger = logging.getLogger(__name__)

LTE_TRANSMISSION_MODES = (
    "TM1",
    "TM2",
    "TM3",
    "TM4",
    "TM6",
    "TM7",
    "TM8",
    "TM9",
)
LteTransmissionMode = Literal[
    "TM1", "TM2", "TM3", "TM4", "TM6", "TM7", "TM8", "TM9",
]


@dataclass(frozen=True)
class BaseStationIdentity:
    """由已注册驱动提供的基站型号、固件与选件身份快照。"""

    adapter_id: str
    model: str
    firmware_version: str | None
    options: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.adapter_id, str) or not self.adapter_id.strip():
            raise ValueError("adapter_id must be a non-empty string")


@dataclass(frozen=True)
class BaseStationRequestedConfig:
    """Vendor-neutral, RAT-aware PCell request owned by the execution layer.

    The request carries mutually exclusive NR/LTE channel numbers.  Adapter
    translation happens below this contract; callers never select a driver
    dialect or put LTE EARFCN into the legacy NR ``arfcn`` slot.
    """

    radio_technology: Literal["nr5g", "lte"]
    channel_kind: Literal["nr_arfcn", "lte_dl_earfcn"]
    frequency_mhz: float
    bandwidth_mhz: float
    band: str
    duplex: str | None
    nr_arfcn: int | None
    lte_dl_earfcn: int | None
    lte_transmission_mode: LteTransmissionMode | None
    subcarrier_spacing_khz: int | None
    mimo_layers: int
    downlink_power_dbm: float
    downlink_power_dbm_per_bandwidth: float | None = None
    port_preset: str | None = None
    scheduler_algorithm: str | None = None
    csi_rs_ports: int | None = None

    def to_driver_payload(self) -> dict[str, Any]:
        """Translate the common request into the existing driver payload API."""

        payload: dict[str, Any] = {
            "radio_technology": self.radio_technology,
            "channel_kind": self.channel_kind,
            "frequency_mhz": self.frequency_mhz,
            "bandwidth_mhz": self.bandwidth_mhz,
            "band": self.band,
            "mimo_layers": self.mimo_layers,
            "dl_power_dbm": self.downlink_power_dbm,
        }
        if self.radio_technology == "nr5g":
            payload["nr_arfcn"] = self.nr_arfcn
            payload["arfcn"] = self.nr_arfcn
            payload["scs_khz"] = self.subcarrier_spacing_khz
        else:
            payload["lte_dl_earfcn"] = self.lte_dl_earfcn
            payload["earfcn"] = self.lte_dl_earfcn
            payload["duplex"] = self.duplex
            payload["lte_transmission_mode"] = self.lte_transmission_mode
        if self.downlink_power_dbm_per_bandwidth is not None:
            payload["dl_power_dbm_per_bw"] = self.downlink_power_dbm_per_bandwidth
        if self.port_preset is not None:
            payload["mimo_port_preset"] = self.port_preset
        if self.scheduler_algorithm is not None:
            payload["sched_algo"] = self.scheduler_algorithm
        if self.csi_rs_ports is not None:
            payload["csi_rs_ports"] = self.csi_rs_ports
        return payload

    def receipt_payload(self) -> dict[str, Any]:
        """Return every non-null field covered by the frozen request receipt.

        This uses the same dataclass field names persisted by the execution
        evidence writer.  Adapter-specific payload aliases are deliberately
        excluded: a partial hardware readback must not confirm a larger frozen
        request merely because the adapter did not include the other fields.
        """

        return {
            name: value
            for name, value in asdict(self).items()
            if value is not None
        }


@dataclass(frozen=True)
class AppliedCellConfig:
    """UE 协商后实际可用的通用小区能力。"""

    ue_max_dl_layers: int | None = None
    ue_max_modulation_dl: str | None = None


@dataclass(frozen=True)
class BaseStationConfigResult:
    """基站配置请求与权威回读形成的应用结果。"""

    requested: dict[str, Any]
    applied: dict[str, Any] | None
    confirmed: bool
    reason: str


@dataclass(frozen=True)
class BaseStationFieldReceipt:
    """One requested field and the adapter's authoritative applied truth."""

    field: str
    requested: Any
    applied: Any
    status: Literal["confirmed", "unknown", "not_applicable"]
    reason: str
    exchange_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.field, str) or not self.field.strip():
            raise ValueError("field must be a non-empty string")
        if self.status not in {"confirmed", "unknown", "not_applicable"}:
            raise ValueError("field receipt status is invalid")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("field receipt reason must be non-empty")
        if (
            not isinstance(self.exchange_ids, tuple)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in self.exchange_ids
            )
            or len(set(self.exchange_ids)) != len(self.exchange_ids)
        ):
            raise ValueError("field exchange ids must be non-empty and unique")
        if self.status == "confirmed":
            if self.applied is None:
                raise ValueError("confirmed field requires an applied value")
            if self.applied != self.requested:
                raise ValueError("confirmed field applied value must match requested")
        elif self.status == "unknown":
            if self.applied is not None:
                raise ValueError("unknown field cannot carry an applied value")
        elif self.requested is not None or self.applied is not None:
            raise ValueError("not_applicable field cannot carry requested or applied values")


@dataclass(frozen=True)
class BaseStationApplyReceipt:
    """Versioned vendor-neutral result for config or route application."""

    schema_version: Literal[1]
    operation: Literal["config", "route"]
    fields: tuple[BaseStationFieldReceipt, ...]
    reason: str
    simulated: bool
    operation_succeeded: bool | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported base-station apply receipt schema")
        if self.operation not in {"config", "route"}:
            raise ValueError("base-station apply operation is invalid")
        if not isinstance(self.fields, tuple) or not self.fields:
            raise ValueError("base-station apply receipt requires fields")
        if any(not isinstance(item, BaseStationFieldReceipt) for item in self.fields):
            raise TypeError("apply receipt fields must be BaseStationFieldReceipt")
        field_names = [item.field for item in self.fields]
        if len(set(field_names)) != len(field_names):
            raise ValueError("apply receipt field names must be unique")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("apply receipt reason must be non-empty")
        if type(self.simulated) is not bool:
            raise TypeError("apply receipt simulated must be bool")
        if (
            self.operation_succeeded is not None
            and type(self.operation_succeeded) is not bool
        ):
            raise TypeError("apply receipt operation_succeeded must be bool or None")

    @property
    def confirmed(self) -> bool:
        applicable = [
            field for field in self.fields if field.status != "not_applicable"
        ]
        return bool(applicable) and all(
            field.status == "confirmed" for field in applicable
        )

    @property
    def diagnostic_execution_allowed(self) -> bool:
        """Separate accepted device operation from formal evidence completeness."""

        if self.operation != "config":
            return False
        if self.operation_succeeded is not None:
            return self.operation_succeeded
        return self.confirmed is True or self.simulated is True

    @property
    def exchange_ids(self) -> tuple[str, ...]:
        unique: list[str] = []
        for field in self.fields:
            for exchange_id in field.exchange_ids:
                if exchange_id not in unique:
                    unique.append(exchange_id)
        return tuple(unique)


BASE_STATION_ATTACH_STAGES = (
    "cell_ready",
    "ue_registered",
    "rrc_connected",
    "data_bearer_established",
)
BaseStationAttachStage = Literal[
    "cell_ready",
    "ue_registered",
    "rrc_connected",
    "data_bearer_established",
]
BaseStationAttachEvidence = Literal[
    "authoritative",
    "diagnostic_only",
    "unavailable",
    "not_applicable",
]


@dataclass(frozen=True)
class BaseStationAttachStageReceipt:
    """One attach milestone observed during the current adapter operation."""

    stage: BaseStationAttachStage
    requested: bool | None
    applied: bool | None
    status: Literal["confirmed", "unknown", "not_applicable"]
    evidence: BaseStationAttachEvidence
    reason: str
    exchange_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.stage not in BASE_STATION_ATTACH_STAGES:
            raise ValueError("attach stage is invalid")
        if self.requested is not None and type(self.requested) is not bool:
            raise TypeError("attach stage requested must be bool or None")
        if self.applied is not None and type(self.applied) is not bool:
            raise TypeError("attach stage applied must be bool or None")
        if self.status not in {"confirmed", "unknown", "not_applicable"}:
            raise ValueError("attach stage status is invalid")
        if self.evidence not in {
            "authoritative",
            "diagnostic_only",
            "unavailable",
            "not_applicable",
        }:
            raise ValueError("attach stage evidence is invalid")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("attach stage reason must be non-empty")
        if (
            not isinstance(self.exchange_ids, tuple)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in self.exchange_ids
            )
            or len(set(self.exchange_ids)) != len(self.exchange_ids)
        ):
            raise ValueError("attach stage exchange ids must be non-empty and unique")
        if self.evidence == "unavailable" and self.status != "unknown":
            raise ValueError("unavailable stage must be unknown")
        if self.evidence == "not_applicable" and self.status != "not_applicable":
            raise ValueError(
                "not-applicable evidence requires not-applicable status"
            )
        if self.status == "not_applicable":
            if self.evidence != "not_applicable":
                raise ValueError(
                    "not-applicable status requires not-applicable evidence"
                )
            if self.requested is not None or self.applied is not None:
                raise ValueError(
                    "not-applicable stage cannot carry requested or applied truth"
                )
            if self.exchange_ids:
                raise ValueError("not-applicable stage cannot carry exchange ids")
        elif self.requested is not True:
            raise ValueError("applicable attach stage must be explicitly requested")
        if self.status == "confirmed":
            if self.applied is None:
                raise ValueError("confirmed stage requires applied truth")
            if not self.exchange_ids:
                raise ValueError("confirmed stage requires exchange ids")
        elif self.status == "unknown":
            if self.applied is not None:
                raise ValueError("unknown stage cannot carry applied truth")
            if self.exchange_ids:
                raise ValueError("unknown stage cannot carry exchange ids")


@dataclass(frozen=True)
class BaseStationAttachReceipt:
    """Versioned vendor-neutral outcome of one BaseStation attach operation."""

    schema_version: Literal[1]
    adapter_id: str
    stages: tuple[BaseStationAttachStageReceipt, ...]
    reason: str
    simulated: bool
    operation_succeeded: bool | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported base-station attach receipt schema")
        if not isinstance(self.adapter_id, str) or not self.adapter_id.strip():
            raise ValueError("attach receipt adapter_id must be non-empty")
        if (
            not isinstance(self.stages, tuple)
            or any(
                not isinstance(item, BaseStationAttachStageReceipt)
                for item in self.stages
            )
            or tuple(item.stage for item in self.stages)
            != BASE_STATION_ATTACH_STAGES
        ):
            raise ValueError("attach receipt requires exact ordered attach stages")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("attach receipt reason must be non-empty")
        if type(self.simulated) is not bool:
            raise TypeError("attach receipt simulated must be bool")
        if (
            self.operation_succeeded is not None
            and type(self.operation_succeeded) is not bool
        ):
            raise TypeError("attach operation_succeeded must be bool or None")
        if not self.simulated and self.operation_succeeded is not None:
            raise ValueError(
                "real attach success must be derived from the terminal stage"
            )

    @property
    def terminal_stage(self) -> BaseStationAttachStage | None:
        for stage in reversed(self.stages):
            if stage.evidence not in {"unavailable", "not_applicable"}:
                return stage.stage
        return None

    @property
    def terminal_stage_receipt(self) -> BaseStationAttachStageReceipt | None:
        terminal = self.terminal_stage
        return next((stage for stage in self.stages if stage.stage == terminal), None)

    @property
    def diagnostic_execution_allowed(self) -> bool:
        if self.simulated:
            return self.operation_succeeded is True
        terminal = self.terminal_stage_receipt
        return bool(
            terminal
            and terminal.status == "confirmed"
            and terminal.applied is True
        )

    @property
    def formally_confirmed(self) -> bool:
        terminal = self.terminal_stage_receipt
        if (
            self.simulated
            or terminal is None
            or terminal.evidence != "authoritative"
            or terminal.status != "confirmed"
            or terminal.applied is not True
        ):
            return False
        authoritative = [
            stage for stage in self.stages if stage.evidence == "authoritative"
        ]
        return bool(authoritative) and all(
            stage.status == "confirmed"
            and stage.applied is True
            and bool(stage.exchange_ids)
            for stage in authoritative
        )

    @property
    def exchange_ids(self) -> tuple[str, ...]:
        unique: list[str] = []
        for stage in self.stages:
            for exchange_id in stage.exchange_ids:
                if exchange_id not in unique:
                    unique.append(exchange_id)
        return tuple(unique)

    def __bool__(self) -> bool:
        raise TypeError(
            "BaseStationAttachReceipt must not be used as bool; inspect its stage truth"
        )


BASE_STATION_MEASUREMENT_WINDOW_STAGES = (
    "clear",
    "run",
    "ready",
    "closed",
)
BaseStationMeasurementWindowStage = Literal[
    "clear",
    "run",
    "ready",
    "closed",
]
BaseStationMeasurementLifecycle = Literal[
    "authoritative_closed",
    "clear_read_only",
    "unavailable",
]


@dataclass(frozen=True)
class BaseStationMeasurementWindowRequest:
    """One execution-frozen native-window request.

    The request owns scope and cardinality.  Drivers may only report what
    happened for this exact request; they cannot silently choose another
    number of windows or widen PCell into all-cells.
    """

    schema_version: Literal[1]
    scope: Literal["pcell", "all_cells"]
    lifecycle: BaseStationMeasurementLifecycle
    cardinality: Literal["single", "requested"]
    requested_window_count: int
    expected_window_count: int
    window_index: int

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported measurement window request schema")
        if self.scope not in {"pcell", "all_cells"}:
            raise ValueError("measurement window scope is invalid")
        if self.lifecycle not in {
            "authoritative_closed",
            "clear_read_only",
            "unavailable",
        }:
            raise ValueError("measurement window lifecycle is invalid")
        if self.cardinality not in {"single", "requested"}:
            raise ValueError("measurement window cardinality is invalid")
        for field_name in ("requested_window_count", "expected_window_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise TypeError(
                    field_name.replace("_", " ") + " must be a positive integer"
                )
        if self.cardinality == "single" and self.expected_window_count != 1:
            raise ValueError("single cardinality requires one expected window")
        if (
            self.cardinality == "requested"
            and self.expected_window_count != self.requested_window_count
        ):
            raise ValueError(
                "requested cardinality requires expected count to match request"
            )
        if (
            isinstance(self.window_index, bool)
            or not isinstance(self.window_index, int)
            or not 0 <= self.window_index < self.expected_window_count
        ):
            raise ValueError("measurement window index is outside the frozen batch")

    @property
    def digest(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "lifecycle": self.lifecycle,
            "cardinality": self.cardinality,
            "requested_window_count": self.requested_window_count,
            "expected_window_count": self.expected_window_count,
            "window_index": self.window_index,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def __bool__(self) -> bool:
        raise TypeError(
            "BaseStationMeasurementWindowRequest must not be used as bool; "
            "inspect its frozen fields"
        )


@dataclass(frozen=True)
class BaseStationMeasurementStageReceipt:
    """One clear/run/ready/closed observation from the current window."""

    stage: BaseStationMeasurementWindowStage
    status: Literal["confirmed", "unknown", "unavailable"]
    reason: str
    exchange_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.stage not in BASE_STATION_MEASUREMENT_WINDOW_STAGES:
            raise ValueError("measurement window stage is invalid")
        if self.status not in {"confirmed", "unknown", "unavailable"}:
            raise ValueError("measurement window stage status is invalid")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("measurement window stage reason must be non-empty")
        if (
            not isinstance(self.exchange_ids, tuple)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in self.exchange_ids
            )
            or len(set(self.exchange_ids)) != len(self.exchange_ids)
        ):
            raise ValueError(
                "measurement window stage exchange ids must be non-empty and unique"
            )
        if self.status == "confirmed" and not self.exchange_ids:
            raise ValueError("confirmed stage requires exchange ids")
        if self.status != "confirmed" and self.exchange_ids:
            raise ValueError(
                "unknown or unavailable stage cannot carry exchange ids"
            )


@dataclass(frozen=True)
class BaseStationMeasurementWindowTrust:
    """Versioned lifecycle truth for one exact frozen window request."""

    schema_version: Literal[1]
    request: BaseStationMeasurementWindowRequest
    request_digest: str
    stages: tuple[BaseStationMeasurementStageReceipt, ...]
    simulated: bool
    exchange_ids: tuple[str, ...]
    reason: str
    context_confirmed: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported measurement window trust schema")
        if not isinstance(self.request, BaseStationMeasurementWindowRequest):
            raise TypeError("measurement window trust requires a frozen request")
        if self.request_digest != self.request.digest:
            raise ValueError("measurement window request digest mismatch")
        if (
            not isinstance(self.stages, tuple)
            or any(
                not isinstance(item, BaseStationMeasurementStageReceipt)
                for item in self.stages
            )
            or tuple(item.stage for item in self.stages)
            != BASE_STATION_MEASUREMENT_WINDOW_STAGES
        ):
            raise ValueError(
                "measurement window trust requires exact ordered lifecycle stages"
            )
        if type(self.simulated) is not bool:
            raise TypeError("measurement window trust simulated must be bool")
        if type(self.context_confirmed) is not bool:
            raise TypeError(
                "measurement window trust context_confirmed must be bool"
            )
        if (
            not isinstance(self.exchange_ids, tuple)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in self.exchange_ids
            )
            or len(set(self.exchange_ids)) != len(self.exchange_ids)
        ):
            raise ValueError("measurement window exchange ids must be non-empty and unique")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("measurement window trust reason must be non-empty")
        stage_exchange_ids = {
            exchange_id
            for stage in self.stages
            for exchange_id in stage.exchange_ids
        }
        if not stage_exchange_ids.issubset(set(self.exchange_ids)):
            raise ValueError(
                "measurement stage exchange ids must belong to the window"
            )
        statuses = {stage.stage: stage.status for stage in self.stages}
        if self.simulated and any(
            status == "confirmed" for status in statuses.values()
        ):
            raise ValueError("simulated window cannot carry confirmed lifecycle truth")
        if (
            self.request.lifecycle == "clear_read_only"
            and statuses["closed"] == "confirmed"
        ):
            raise ValueError("clear-read-only lifecycle cannot confirm a closed boundary")
        if self.request.lifecycle == "unavailable" and any(
            status == "confirmed" for status in statuses.values()
        ):
            raise ValueError("unavailable lifecycle cannot carry confirmed stages")

    @property
    def formally_confirmed(self) -> bool:
        return (
            self.simulated is False
            and self.context_confirmed is True
            and self.request.lifecycle == "authoritative_closed"
            and all(stage.status == "confirmed" for stage in self.stages)
            and bool(self.exchange_ids)
        )

    @property
    def diagnostic_execution_allowed(self) -> bool:
        if self.simulated:
            return True
        if self.formally_confirmed:
            return True
        return (
            self.request.lifecycle in {"clear_read_only", "unavailable"}
            and bool(self.exchange_ids)
        )

    def __bool__(self) -> bool:
        raise TypeError(
            "BaseStationMeasurementWindowTrust must not be used as bool; "
            "inspect formal or diagnostic qualification"
        )


@dataclass(frozen=True)
class BaseStationCleanupResult:
    """MEASURE 阶段拥有的信令停止与 SAFE_IDLE 结果。"""

    stop_signaling_confirmed: bool
    safe_idle_confirmed: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class BaseStationMeasurementWindow:
    """由单一厂商测量边界产生的结构化 KPI 窗口。"""

    window_id: str
    started_at: datetime
    completed_at: datetime | None
    metrics: "ThroughputMetrics"
    preclear_off_confirmed: bool
    running_confirmed: bool
    ready_confirmed: bool
    closed_off_confirmed: bool
    evidence: tuple[InstrumentEvidenceItem, ...]
    confirmed: bool
    reason: str
    trust: BaseStationMeasurementWindowTrust | None = None

    def __post_init__(self) -> None:
        if self.trust is None:
            return
        if not isinstance(self.trust, BaseStationMeasurementWindowTrust):
            raise TypeError("measurement window trust has an invalid type")
        stage_confirmed = {
            stage.stage: stage.status == "confirmed"
            for stage in self.trust.stages
        }
        lifecycle_mirrors = {
            "clear": self.preclear_off_confirmed,
            "run": self.running_confirmed,
            "ready": self.ready_confirmed,
            "closed": self.closed_off_confirmed,
        }
        if any(
            type(value) is not bool or value is not stage_confirmed[stage]
            for stage, value in lifecycle_mirrors.items()
        ):
            raise ValueError(
                "measurement window lifecycle mirrors disagree with trust receipt"
            )
        if self.confirmed is not self.trust.formally_confirmed:
            raise ValueError(
                "measurement window confirmed mirror disagrees with trust receipt"
            )
        expected_scope = (
            ThroughputMetrics.SCOPE_SIMULATED
            if self.trust.simulated
            else (
                ThroughputMetrics.SCOPE_PCELL
                if self.trust.request.scope == "pcell"
                else ThroughputMetrics.SCOPE_NR_ALL_CELLS
            )
        )
        if self.metrics.throughput_scope != expected_scope:
            raise ValueError("measurement window metric scope disagrees with request")


@dataclass(frozen=True)
class BaseStationRemoteSessionResult:
    """驱动成功建立真实 transport session 后返回的不可伪造身份。"""

    adapter_id: str
    session_token: str
    acquired_confirmed: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class BaseStationControlReleaseResult:
    """与单次 lease/attempt 绑定的基站控制会话释放结果。"""

    measurement_attempt_id: str | None
    lease_id: str
    adapter_id: str
    session_token: str
    remote_session_acquired_confirmed: bool
    transport_session_released_confirmed: bool
    front_panel_local_confirmed: bool | None
    warnings: tuple[str, ...]


# ===========================================================================
# 基站仿真器通用枚举
# ===========================================================================

class RadioTechnology(str, Enum):
    """基站支持的无线接入技术"""
    NR5G = "NR5G"
    LTE = "LTE"
    LTE_NR_NSA = "LTE_NR_NSA"  # LTE + NR 非独立组网 (EN-DC)


class CellState(str, Enum):
    """小区状态"""
    OFF = "OFF"          # 小区关闭 (未激活)
    ON = "ON"            # 小区已激活 (射频开启)
    IDLE = "IDLE"        # 等待 UE 接入
    CONNECTED = "CONN"   # UE 已连接 (RRC Connected)
    ERROR = "ERROR"


class ThroughputMetrics:
    """吞吐量测量结果。

    **口径 (2026-08-03 用户定)**: 这里存的是**仪表与终端上报的参数**,
    不是我们自己统计的传输数据量。

    ``*_throughput_mbps`` = 统计窗口内的**平均**吞吐量 (测试例的结论值);
    ``*_throughput_current_mbps`` = 查询时刻的**瞬时**吞吐量 (会随调度抖动,
    适合实时曲线, 不适合当结论)。两者都存, 因为一个回答"这次测出来多少",
    另一个回答"现在跑到多少"。
    """
    SCOPE_UNKNOWN = "unknown"
    SCOPE_PCELL = "pcell"
    SCOPE_NR_ALL_CELLS = "nr_all_cells"
    SCOPE_SIMULATED = "simulated"
    VALID_SCOPES = frozenset({
        SCOPE_UNKNOWN,
        SCOPE_PCELL,
        SCOPE_NR_ALL_CELLS,
        SCOPE_SIMULATED,
    })

    def __init__(
        self,
        dl_throughput_mbps: Optional[float] = None,
        ul_throughput_mbps: Optional[float] = None,
        dl_bler: Optional[float] = None,
        ul_bler: Optional[float] = None,
        cqi: int = 0,
        rank_indicator: int = 1,
        mcs_dl: int = 0,
        mcs_ul: int = 0,
        rsrp_dbm: float = -999.0,
        sinr_db: float = -999.0,
        dl_throughput_current_mbps: Optional[float] = None,
        ul_throughput_current_mbps: Optional[float] = None,
        kpi_valid: Optional[Dict[str, bool]] = None,
        throughput_scope: str = SCOPE_UNKNOWN,
    ):
        self.dl_throughput_mbps = dl_throughput_mbps
        self.ul_throughput_mbps = ul_throughput_mbps
        self.dl_bler = dl_bler
        self.ul_bler = ul_bler
        self.cqi = cqi
        self.rank_indicator = rank_indicator
        self.mcs_dl = mcs_dl
        self.mcs_ul = mcs_ul
        self.rsrp_dbm = rsrp_dbm
        self.sinr_db = sinr_db
        self.dl_throughput_current_mbps = dl_throughput_current_mbps
        self.ul_throughput_current_mbps = ul_throughput_current_mbps
        self.throughput_scope = (
            throughput_scope
            if throughput_scope in self.VALID_SCOPES
            else self.SCOPE_UNKNOWN
        )
        # 显式白名单：真实 0.0 是有效值；缺测 None 不是。真实驱动可以用
        # ``kpi_valid`` 覆盖/补充其余 KPI 的解析真值，正式调用方不得从数值大小猜。
        self.kpi_valid: Dict[str, bool] = {
            "dl_throughput": dl_throughput_mbps is not None,
            "ul_throughput": ul_throughput_mbps is not None,
            "dl_throughput_current": dl_throughput_current_mbps is not None,
            "ul_throughput_current": ul_throughput_current_mbps is not None,
            "dl_bler": dl_bler is not None,
            "ul_bler": ul_bler is not None,
        }
        if kpi_valid:
            self.kpi_valid.update({key: value is True for key, value in kpi_valid.items()})

    def is_valid(self, key: str) -> bool:
        """仅显式 ``True`` 才算可信 KPI；缺键与历史对象一律 fail-closed。"""
        return self.kpi_valid.get(key) is True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dl_throughput_mbps": self.dl_throughput_mbps,
            "ul_throughput_mbps": self.ul_throughput_mbps,
            "dl_throughput_current_mbps": self.dl_throughput_current_mbps,
            "ul_throughput_current_mbps": self.ul_throughput_current_mbps,
            "dl_bler": self.dl_bler,
            "ul_bler": self.ul_bler,
            "cqi": self.cqi,
            "rank_indicator": self.rank_indicator,
            "mcs_dl": self.mcs_dl,
            "mcs_ul": self.mcs_ul,
            "rsrp_dbm": self.rsrp_dbm,
            "sinr_db": self.sinr_db,
            "kpi_valid": dict(self.kpi_valid),
            "throughput_scope": self.throughput_scope,
        }


class BaseStationDriver(InstrumentDriver):
    """
    Abstract interface for Base Station Emulator (HAL Layer 2)

    定义了所有基站仿真器必须实现的标准化操作原语。
    无论底层是 Keysight UXM (5G NR) 还是 R&S CMW500 (LTE),
    应用层通过此接口统一操作。

    核心原语:
      - set_cell_config():     配置物理小区参数 (频率/带宽/SCS)
      - set_frc_config():      配置固定参考信道 (FRC)
      - set_downlink_power():  调节下行发射功率
      - start_signaling():     开启信令，等待 UE Attach
      - stop_signaling():      停止信令
      - get_throughput_metrics(): 轮询读取 MAC 吞吐量 + BLER + CQI
    """

    # Formal CA is opt-in: a driver may only allow SCell writes when it can
    # independently confirm the requested active SCell set. Real drivers keep
    # the fail-closed default until a vendor-documented readback is available.
    SCELL_ACTIVATION_READBACK_AUTHORITATIVE = False
    adapter_id: ClassVar[str]
    # 输入电平闭环是显式 opt-in 能力，不能因某驱动恰好实现同名方法而推断。
    # P1-73A 的 CMW500 功率能力尚未开放，保持默认 False。
    input_level_control_supported: ClassVar[bool] = False
    input_level_legacy_power_field: ClassVar[str | None] = None
    input_level_unavailable_reason: ClassVar[str | None] = None
    # RRC reconfiguration is opt-in.  The abstract method exists to define
    # the contract, so hasattr() cannot distinguish an implemented adapter.
    rrc_reconfiguration_supported: ClassVar[bool] = False
    # Formal MAC-throughput configuration is opt-in. A driver without this
    # capability must not sample a stale scheduler/FRC configuration.
    mac_throughput_configuration_supported: ClassVar[bool] = False
    max_bandwidth_mhz: ClassVar[float | None] = None
    max_mimo_layers: ClassVar[int | None] = None
    measurement_window_cardinality: ClassVar[Literal["requested", "single"]] = (
        "requested"
    )

    # ===================================================================
    # 小区配置
    # ===================================================================

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """
        配置物理小区参数。

        Args:
            config: 小区配置字典, 支持以下字段:
                - band: str,          NR 频段 (e.g., "n78")
                - frequency_mhz: float, 中心频率
                - bandwidth_mhz: float, 信道带宽 (e.g., 100)
                - scs_khz: int,       子载波间隔 (15/30/60/120 kHz)
                - duplex: str,        双工模式 ("TDD" / "FDD")
                - mimo_layers: int,   MIMO 层数 (1/2/4)
                - cell_id: int,       物理小区 ID

        Returns:
            True if configuration successful
        """
        raise NotImplementedError

    async def apply_requested_config(
        self, requested: BaseStationRequestedConfig,
    ) -> bool:
        """Apply one typed request through the adapter's existing primitive."""

        if not isinstance(requested, BaseStationRequestedConfig):
            raise TypeError("requested must be BaseStationRequestedConfig")
        requested_technology = (
            RadioTechnology.NR5G
            if requested.radio_technology == "nr5g"
            else RadioTechnology.LTE
        )
        if requested_technology not in self.get_supported_technologies():
            logger.error(
                "[%s] Rejecting %s configuration: adapter %s does not support it",
                self.instrument_id,
                requested.radio_technology,
                self.adapter_id,
            )
            return False
        if (
            self.max_bandwidth_mhz is not None
            and requested.bandwidth_mhz > self.max_bandwidth_mhz
        ):
            logger.error(
                "[%s] Rejecting bandwidth %.3f MHz: adapter %s maximum is %.3f MHz",
                self.instrument_id,
                requested.bandwidth_mhz,
                self.adapter_id,
                self.max_bandwidth_mhz,
            )
            return False
        if (
            self.max_mimo_layers is not None
            and requested.mimo_layers > self.max_mimo_layers
        ):
            logger.error(
                "[%s] Rejecting %d MIMO layers: adapter %s maximum is %d",
                self.instrument_id,
                requested.mimo_layers,
                self.adapter_id,
                self.max_mimo_layers,
            )
            return False
        return await self.set_cell_config(requested.to_driver_payload())

    async def apply_config(
        self,
        requested: BaseStationRequestedConfig,
    ) -> BaseStationApplyReceipt:
        """Apply a typed request without inventing readback absent from a driver.

        Concrete adapters must override this method before a result can be
        formally confirmed.  The compatibility implementation preserves the
        existing write path but reports every requested field as unknown.
        """

        if not isinstance(requested, BaseStationRequestedConfig):
            raise TypeError("requested must be BaseStationRequestedConfig")
        operation_succeeded = await self.apply_requested_config(requested)
        return BaseStationApplyReceipt(
            schema_version=1,
            operation="config",
            fields=tuple(
                BaseStationFieldReceipt(
                    field=field,
                    requested=value,
                    applied=None,
                    status="unknown",
                    reason="adapter did not provide authoritative field readback",
                )
                for field, value in requested.receipt_payload().items()
            ),
            reason="adapter configuration readback is unavailable",
            simulated=getattr(self, "simulated", False) is True,
            operation_succeeded=operation_succeeded is True,
        )

    async def apply_route(
        self,
        frozen_adapter: dict[str, Any],
    ) -> BaseStationApplyReceipt:
        """Return an explicit non-applicable receipt for adapters without route."""

        if not isinstance(frozen_adapter, dict):
            raise TypeError("frozen_adapter must be a dictionary")
        return BaseStationApplyReceipt(
            schema_version=1,
            operation="route",
            fields=(
                BaseStationFieldReceipt(
                    field="route",
                    requested=None,
                    applied=None,
                    status="not_applicable",
                    reason="adapter has no execution route operation",
                ),
            ),
            reason="route is not applicable to this adapter",
            simulated=getattr(self, "simulated", False) is True,
        )

    def route_allows_diagnostic_execution(
        self,
        receipt: BaseStationApplyReceipt,
    ) -> bool:
        """Accept a route only when it is confirmed or truly not applicable."""

        if not isinstance(receipt, BaseStationApplyReceipt):
            return False
        if receipt.operation != "route":
            return False
        return receipt.confirmed is True or all(
            field.status == "not_applicable" for field in receipt.fields
        )

    def get_mimo_route_snapshot(self, preset: str) -> Dict[str, Any]:
        """Optional physical connector projection for topology display.

        Drivers without an authoritative profile/readback return an empty
        snapshot. The application must warn and keep logical topology usable;
        it must not infer connector names from adapter/model identity.
        """

        return {}

    async def set_frc_config(
        self,
        frc_reference: str,
        modulation: Optional[str] = None,
        target_coding_rate: Optional[float] = None,
    ) -> bool:
        """
        配置固定参考信道 (FRC / Fixed Reference Channel)。

        按 3GPP TS 38.521-4 (NR) 或 TS 36.521 (LTE)
        定义的标准FRC进行配置。

        Args:
            frc_reference: FRC 参考名 (e.g., "G-FR1-A1-1", "R.0")
            modulation: 调制方式 (e.g., "256QAM", "64QAM")
            target_coding_rate: 目标编码率

        Returns:
            True if FRC configured successfully
        """
        raise NotImplementedError

    async def set_downlink_power(self, power_dbm: float) -> bool:
        """
        设置下行发射功率。

        Args:
            power_dbm: 下行功率 (dBm), 典型范围 -120 ~ 0

        Returns:
            True if power set successfully
        """
        raise NotImplementedError

    # ===================================================================
    # 信令控制
    # ===================================================================

    async def attach(self, timeout_s: float = 60.0) -> BaseStationAttachReceipt:
        """Run one attach operation and return current-operation stage truth."""

        raise NotImplementedError

    async def start_signaling(self, timeout_s: float = 60.0) -> bool:
        """
        开启物理小区信令, 激活小区并等待 UE Attach。

        等效于 "Cell ON" + 等待 RRC Connection + Attach Complete。

        Args:
            timeout_s: 等待 UE Attach 的超时时间 (秒)

        Returns:
            True if UE successfully attached within timeout
        """
        receipt = await self.attach(timeout_s=timeout_s)
        return receipt.diagnostic_execution_allowed

    async def stop_signaling(self) -> bool:
        """
        停止物理小区信令, 断开 UE 连接并关闭小区。

        Returns:
            True if signaling stopped successfully
        """
        raise NotImplementedError

    async def start_cell(self) -> bool:
        """Start base station transmission (alias for start_signaling)"""
        return await self.start_signaling()

    async def stop_cell(self) -> bool:
        """Stop base station transmission (alias for stop_signaling)"""
        return await self.stop_signaling()

    async def get_cell_state(self) -> CellState:
        """获取小区当前状态"""
        raise NotImplementedError

    async def ensure_safe_idle(self) -> bool:
        """Confirm the vendor-neutral SAFE_IDLE boundary after signaling stops."""

        return await self.get_cell_state() is CellState.OFF

    # ===================================================================
    # 测量
    # ===================================================================

    async def get_throughput_metrics(
        self,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> ThroughputMetrics:
        """
        轮询读取 MAC 层吞吐量指标。

        返回当前的 DL/UL 吞吐量, BLER, CQI, Rank Indicator, MCS。
        建议采样间隔: 200ms。

        Returns:
            ThroughputMetrics 数据对象
        """
        raise NotImplementedError

    async def measure_throughput_window(
        self,
        window_s: float,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> ThroughputMetrics:
        """
        采集一个独立的 MAC 统计窗口 (Phase 2d 同步语义)。

        语义 = "建立独立统计边界 → 等待 window_s 秒 → 读一次"。
        每次调用对应一个独立的 i.i.d. 样本; 调用方循环 N 次得到 N 个独立样本,
        std/mean 才有意义。区别于 get_throughput_metrics() 的滑动窗口语义。

        默认实现 = sleep + 单次 get_throughput_metrics() — 适用于 mock 或
        不提供独立窗口控制的简单仿真器。真硬件必须按各自有厂商出处的能力
        override；无法确认窗口边界时应保守返回未验证值，不得照搬其他方言。

        Args:
            window_s: 窗口长度 (秒); 对应 stat_count 子帧数 (1ms/subframe)

        Returns:
            该窗口结束时的 ThroughputMetrics 快照
        """
        import asyncio as _asyncio
        await _asyncio.sleep(max(window_s, 0.0))
        return await self.get_throughput_metrics(
            throughput_scope=throughput_scope,
        )

    async def measure_base_station_window(
        self,
        window_s: float,
        *,
        request: BaseStationMeasurementWindowRequest,
    ) -> BaseStationMeasurementWindow:
        """采集带厂商生命周期确认的结构化窗口。

        真实驱动必须显式实现；默认拒绝，防止旧 sleep+poll 结果被误当成
        已确认的独立统计窗口。P1-73C 才把该契约接入通用方位扫描。
        """

        raise NotImplementedError(
            f"{type(self).__name__} does not provide a confirmed measurement window"
        )

    def measurement_window_count(self, requested: int) -> int:
        """Let the adapter own whether one position uses one or N native windows."""

        if isinstance(requested, bool) or not isinstance(requested, int) or requested <= 0:
            raise ValueError("requested measurement window count must be positive")
        return 1 if self.measurement_window_cardinality == "single" else requested

    def unconfirmed_window_allows_diagnostic_execution(
        self,
        window: BaseStationMeasurementWindow,
    ) -> bool:
        """Keep only authoritative simulated windows runnable by default."""

        return (
            getattr(self, "simulated", False) is True
            and isinstance(window, BaseStationMeasurementWindow)
            and window.metrics.throughput_scope == ThroughputMetrics.SCOPE_SIMULATED
        )

    async def get_ue_info(self) -> Dict[str, Any]:
        """
        获取已连接 UE 的信息。

        Returns:
            UE 信息字典 (IMSI, IMEI, capabilities, etc.)
        """
        raise NotImplementedError

    async def query_ue_capability(self) -> Dict[str, Any]:
        """
        查询 UE 上报的 3GPP 能力 (Phase 2e)。

        4x4 MIMO 测试前必须确认 DUT 真支持 4 layer DL — 否则下行配置
        4 layer 但 UE 默认 2 layer attach, 跑出来的数据其实是 2 layer。

        典型返回字段(driver 各自填充):
            - max_dl_layers: int      (1/2/4/8)
            - max_ul_layers: int
            - max_modulation_dl: str  ('64QAM' / '256QAM' / '1024QAM')
            - max_modulation_ul: str
            - supported_bands: List[str]
            - ca_combinations: List[str]  (载波聚合组合, e.g. ['n78+n41'])
            - source: 'real_ue' | 'mock' | 'unavailable'

        Returns:
            能力字典; 至少必须有 'max_dl_layers' 和 'source'
        """
        raise NotImplementedError

    async def reconfigure_rrc(
        self,
        *,
        mimo_layers: Optional[int] = None,
        modulation: Optional[str] = None,
    ) -> bool:
        """
        触发 RRC reconfiguration, 把新参数下推给已 attach 的 UE。

        set_cell_config() 改的是基站内部配置, RRC 重配是把这些变化通知到
        UE 的 RadioBearer/PDSCH-Config。某些 UXM firmware 在 cell config
        变化时会自动触发 RRC reconfig; 其它需要显式调用本接口。

        Args:
            mimo_layers: 目标 DL layer 数 (1/2/4/8); None = 不改
            modulation: 'QPSK' | '16QAM' | '64QAM' | '256QAM' | '1024QAM'; None = 不改

        Returns:
            True if RRC reconfiguration completed (UE acked)
        """
        raise NotImplementedError

    # ===================================================================
    # 载波聚合 (Phase 2g)
    # ===================================================================

    async def add_secondary_cell(
        self,
        cc_index: int,
        cc_config: Dict[str, Any],
    ) -> bool:
        """
        添加 SCell (Secondary Cell)。

        NR-CA 中 PCell 走 set_cell_config (cc_index=0 隐式), SCell 走本接口
        (cc_index ≥ 1)。一次测试可以串多次 add_secondary_cell, 然后调
        activate_secondary_cells 一次性激活全部。

        Args:
            cc_index: SCell 序号, 从 1 开始 (PCell 是 0)
            cc_config: 与 set_cell_config 同结构, 至少含 frequency_mhz / bandwidth_mhz

        Returns:
            True if SCell add succeeded (基站接受配置, 但尚未激活)
        """
        raise NotImplementedError

    async def activate_secondary_cells(
        self,
        *,
        expected_indices: Optional[List[int]] = None,
    ) -> bool:
        """激活 SCell；仅在权威回读确认预期集合均已激活时返回 True。"""
        raise NotImplementedError

    async def remove_all_secondary_cells(self) -> bool:
        """移除所有 SCell (cleanup 用; 异常退出时避免下次测试碰到残留状态)。"""
        raise NotImplementedError

    # ===================================================================
    # 能力查询
    # ===================================================================

    def get_supported_technologies(self) -> List[RadioTechnology]:
        """
        从注册 adapter manifest 的单一真值声明无线接入技术。

        Returns:
            支持的 RadioTechnology 列表
        """
        manifest = getattr(type(self), "adapter_manifest", None)
        rat_capabilities = getattr(manifest, "rat_capabilities", ())
        if rat_capabilities:
            by_manifest_token = {
                "lte": RadioTechnology.LTE,
                "nr5g": RadioTechnology.NR5G,
            }
            return [by_manifest_token[item.rat] for item in rat_capabilities]
        # 未注册的历史/测试驱动继续使用旧默认；所有真实注册 adapter 会由
        # registry gate 强制 schema v2，因此不会落到此兼容分支。
        return [RadioTechnology.LTE]

    # ===================================================================
    # 配置文件管理 (一键配置)
    # ===================================================================

    async def load_state_file(self, filepath: str) -> bool:
        """
        从仪器本机加载已保存的配置文件，一次性恢复全部仪器状态。

        相比逐条 SCPI 配置的优势:
          - 消除参数顺序依赖 (如 Band 必须在 Duplex 之前)
          - 保证所有参数的完整性 (不会遗漏 TDD 配置、RF 路由等)
          - 可由工程师在仪器前面板手动调优后保存为模板

        Args:
            filepath: 仪器本机的文件路径

        Returns:
            True if state loaded successfully
        """
        raise NotImplementedError

    async def save_state_file(self, filepath: str) -> bool:
        """
        将仪器当前完整配置保存为文件。

        Args:
            filepath: 仪器本机的保存路径

        Returns:
            True if state saved successfully
        """
        raise NotImplementedError


# ===========================================================================
# Mock 实现 (开发/测试用)
# ===========================================================================

class MockBaseStation(BaseStationDriver):
    """Mock Base Station Emulator for development."""

    # The mock owns its complete in-memory SCell state and can compare the
    # requested index set exactly. Simulated measurements are still excluded
    # from formal KPI by the existing provenance gate.
    SCELL_ACTIVATION_READBACK_AUTHORITATIVE = True
    rrc_reconfiguration_supported = True

    driver_source = "mock"
    simulated = True

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        configured_model = str(config.get("model") or "").upper()
        self.adapter_id = "cmw500" if "CMW" in configured_model else "uxm"
        self._remote_session_token: str | None = None
        self._cell_running = False
        self._cell_state = CellState.OFF
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0
        self._scs_khz = 30
        self._dl_power_dbm = -50.0
        self._mimo_layers = 2
        self._frc = ""

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        await asyncio.sleep(0.3)
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def acquire_remote_control(self) -> BaseStationRemoteSessionResult:
        await self.connect()
        self._remote_session_token = uuid4().hex
        return BaseStationRemoteSessionResult(
            adapter_id=self.adapter_id,
            session_token=self._remote_session_token,
            acquired_confirmed=True,
            warnings=("simulated transport; front-panel Remote not applicable",),
        )

    async def release_remote_session(
        self,
        expected_session_token: str,
        *,
        measurement_attempt_id: str | None = None,
        lease_id: str = "",
    ) -> BaseStationControlReleaseResult:
        matched = (
            bool(expected_session_token)
            and expected_session_token == self._remote_session_token
        )
        if matched:
            await self.disconnect()
        self._remote_session_token = None
        return BaseStationControlReleaseResult(
            measurement_attempt_id=measurement_attempt_id,
            lease_id=lease_id,
            adapter_id=self.adapter_id,
            session_token=expected_session_token,
            remote_session_acquired_confirmed=matched,
            transport_session_released_confirmed=matched,
            front_panel_local_confirmed=None,
            warnings=("simulated transport; front-panel Local not applicable",),
        )

    async def release_to_local_control(self) -> bool:
        """Release the simulated transport for idle parking/reload paths."""
        released = await self.disconnect()
        self._remote_session_token = None
        return released is True

    async def disconnect(self) -> bool:
        if self._cell_running:
            await self.stop_signaling()
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        return await self.set_cell_config(config)

    async def apply_route(
        self,
        frozen_adapter: dict[str, Any],
    ) -> BaseStationApplyReceipt:
        """Mirror a bound CMW route as simulated unknown evidence."""

        if self.adapter_id != "cmw500":
            return await super().apply_route(frozen_adapter)
        resolution = frozen_adapter.get("resolution")
        profile = resolution.get("profile") if isinstance(resolution, dict) else None
        raw_route = (
            profile.get("lte_2x2_internal_route")
            if isinstance(profile, dict)
            else None
        )
        if raw_route is None:
            return await super().apply_route(frozen_adapter)
        from app.hal.base_station_adapter_profile import (
            Cmw500Lte2x2InternalRoute,
        )

        route = Cmw500Lte2x2InternalRoute.model_validate(raw_route).model_dump()
        return BaseStationApplyReceipt(
            schema_version=1,
            operation="route",
            fields=tuple(
                BaseStationFieldReceipt(
                    field=name,
                    requested=value,
                    applied=None,
                    status="unknown",
                    reason="simulated CMW route has no authoritative readback",
                )
                for name, value in route.items()
            ),
            reason="simulated CMW route excluded from formal evidence",
            simulated=True,
            operation_succeeded=True,
        )

    def route_allows_diagnostic_execution(
        self,
        receipt: BaseStationApplyReceipt,
    ) -> bool:
        """Allow only the complete simulated CMW route shape for diagnostics."""

        if self.adapter_id != "cmw500":
            return super().route_allows_diagnostic_execution(receipt)
        from app.hal.base_station_adapter_profile import (
            Cmw500Lte2x2InternalRoute,
        )

        expected_fields = set(Cmw500Lte2x2InternalRoute.model_fields)
        return (
            isinstance(receipt, BaseStationApplyReceipt)
            and receipt.operation == "route"
            and receipt.simulated is True
            and {field.field for field in receipt.fields} == expected_fields
            and all(
                field.status == "unknown"
                and field.requested is not None
                and field.applied is None
                for field in receipt.fields
            )
        )

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="5g_nr",
                description="5G NR support",
                supported=True,
                parameters={
                    "frequency_range": [450, 6000],
                    "max_bandwidth_mhz": 100,
                },
            ),
            InstrumentCapability(
                name="lte",
                description="LTE support",
                supported=True,
                parameters={
                    "frequency_range": [450, 3800],
                    "max_bandwidth_mhz": 20,
                },
            ),
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        tx_power = self._dl_power_dbm + random.uniform(-0.5, 0.5)
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "cell_running": self._cell_running,
                "cell_state": self._cell_state.value,
                "frequency_mhz": self._frequency_mhz,
                "bandwidth_mhz": self._bandwidth_mhz,
                "scs_khz": self._scs_khz,
                "tx_power_dbm": round(tx_power, 2),
                "mimo_layers": self._mimo_layers,
                "connected_ues": (
                    random.randint(0, 1) if self._cell_running else 0
                ),
            },
        )

    async def reset(self) -> bool:
        if self._cell_running:
            await self.stop_signaling()
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0
        self._scs_khz = 30
        self._dl_power_dbm = -50.0
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        if "frequency_mhz" in config:
            self._frequency_mhz = config["frequency_mhz"]
        if "bandwidth_mhz" in config:
            self._bandwidth_mhz = config["bandwidth_mhz"]
        if "scs_khz" in config:
            self._scs_khz = config["scs_khz"]
        if "mimo_layers" in config:
            self._mimo_layers = config["mimo_layers"]
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_frc_config(
        self, frc_reference: str, modulation=None, target_coding_rate=None
    ) -> bool:
        self._frc = frc_reference
        return True

    async def set_downlink_power(self, power_dbm: float) -> bool:
        if power_dbm < -120 or power_dbm > 0:
            return False
        # 当前 Mock 仍模拟既有 UXM 方言；builder 归 UXM profile 所有，通用 HAL
        # 只在诊断写方调用同一真实命令拼装函数，不复制命令字面量。
        from app.hal.uxm_command_profiles import build_uxm_downlink_power_command

        self._simulate_scpi_write(
            build_uxm_downlink_power_command(self.config, power_dbm)
        )
        self._simulate_scpi_query("*OPC?", "1")
        self._dl_power_dbm = power_dbm
        return True

    async def attach(self, timeout_s: float = 60.0) -> BaseStationAttachReceipt:
        self._set_status(InstrumentStatus.BUSY)
        self._cell_running = True
        self._cell_state = CellState.CONNECTED
        await asyncio.sleep(0.2)
        return BaseStationAttachReceipt(
            schema_version=1,
            adapter_id=self.adapter_id,
            stages=tuple(
                BaseStationAttachStageReceipt(
                    stage=stage,
                    requested=True,
                    applied=None,
                    status="unknown",
                    evidence="diagnostic_only",
                    reason="mock attach state is simulated and not instrument truth",
                )
                for stage in BASE_STATION_ATTACH_STAGES
            ),
            reason="mock attach operation completed with simulated state",
            simulated=True,
            operation_succeeded=True,
        )

    async def stop_signaling(self) -> bool:
        self._cell_running = False
        self._cell_state = CellState.OFF
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_cell_state(self) -> CellState:
        return self._cell_state

    async def get_throughput_metrics(
        self,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_SIMULATED,
    ) -> ThroughputMetrics:
        if not self._cell_running:
            return ThroughputMetrics()
        return ThroughputMetrics(
            dl_throughput_mbps=420.0 + random.gauss(0, 15),
            ul_throughput_mbps=80.0 + random.gauss(0, 5),
            dl_bler=random.uniform(0, 0.05),
            ul_bler=random.uniform(0, 0.08),
            cqi=random.randint(12, 15),
            rank_indicator=min(self._mimo_layers, random.randint(1, 2)),
            mcs_dl=random.randint(24, 27),
            mcs_ul=random.randint(20, 24),
            throughput_scope=ThroughputMetrics.SCOPE_SIMULATED,
        )

    async def measure_base_station_window(
        self,
        window_s: float,
        *,
        request: BaseStationMeasurementWindowRequest,
    ) -> BaseStationMeasurementWindow:
        """Return a same-shape simulated window that can never be formal."""

        if not isinstance(request, BaseStationMeasurementWindowRequest):
            raise TypeError("mock measurement requires a frozen window request")
        started_at = datetime.now(timezone.utc)
        await asyncio.sleep(max(float(window_s), 0.0))
        metrics = await self.get_throughput_metrics(
            throughput_scope=ThroughputMetrics.SCOPE_SIMULATED,
        )
        metrics.throughput_scope = ThroughputMetrics.SCOPE_SIMULATED
        metrics.kpi_valid = {
            key: False for key in metrics.kpi_valid
        }
        trust = BaseStationMeasurementWindowTrust(
            schema_version=1,
            request=request,
            request_digest=request.digest,
            stages=tuple(
                BaseStationMeasurementStageReceipt(
                    stage=stage,
                    status="unavailable",
                    reason="simulated window has no hardware lifecycle proof",
                )
                for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
            ),
            simulated=True,
            exchange_ids=(),
            reason="simulated diagnostic window; excluded from formal KPI",
            context_confirmed=False,
        )
        return BaseStationMeasurementWindow(
            window_id=uuid4().hex,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics=metrics,
            preclear_off_confirmed=False,
            running_confirmed=False,
            ready_confirmed=False,
            closed_off_confirmed=False,
            evidence=(),
            confirmed=False,
            reason="simulated diagnostic window; excluded from formal KPI",
            trust=trust,
        )

    async def get_ue_info(self) -> Dict[str, Any]:
        return {
            "imsi": "001010000000001",
            "imei": "352099001761481",
            "ue_category": "NR-DC",
            "connected": self._cell_running,
        }

    async def query_ue_capability(self) -> Dict[str, Any]:
        """Phase 2e: mock UE that supports up to 4x4 256QAM on n78/n41."""
        return {
            "max_dl_layers": 4,
            "max_ul_layers": 2,
            "max_modulation_dl": "256QAM",
            "max_modulation_ul": "64QAM",
            "supported_bands": ["n78", "n41", "n77", "n79"],
            "ca_combinations": ["n78+n41", "n77+n79"],
            "source": "mock",
        }

    async def reconfigure_rrc(
        self,
        *,
        mimo_layers: Optional[int] = None,
        modulation: Optional[str] = None,
    ) -> bool:
        """Mock: pretend RRC reconfig succeeded."""
        if mimo_layers is not None:
            self._mimo_layers = mimo_layers
            logger.info("[MockBS] RRC reconfig: mimo_layers → %d", mimo_layers)
        if modulation is not None:
            logger.info("[MockBS] RRC reconfig: modulation → %s", modulation)
        return True

    async def add_secondary_cell(
        self,
        cc_index: int,
        cc_config: Dict[str, Any],
    ) -> bool:
        """Mock: track SCell list in memory."""
        if not hasattr(self, "_scells"):
            self._scells = {}
        self._scells[cc_index] = dict(cc_config)
        logger.info(
            "[MockBS] SCell %d added: freq=%.0f MHz BW=%.0f MHz band=%s",
            cc_index,
            cc_config.get("frequency_mhz", 0),
            cc_config.get("bandwidth_mhz", 0),
            cc_config.get("band"),
        )
        return True

    async def activate_secondary_cells(
        self,
        *,
        expected_indices: Optional[List[int]] = None,
    ) -> bool:
        scells = getattr(self, "_scells", {}) or {}
        actual = sorted(scells.keys())
        if expected_indices is not None and actual != sorted(expected_indices):
            logger.warning(
                "[MockBS] SCell set mismatch: expected=%s actual=%s",
                sorted(expected_indices),
                actual,
            )
            return False
        logger.info("[MockBS] Activating %d SCell(s): %s",
                    len(scells), actual)
        return True

    async def remove_all_secondary_cells(self) -> bool:
        n = len(getattr(self, "_scells", {}) or {})
        self._scells = {}
        logger.info("[MockBS] Removed %d SCell(s)", n)
        return True

    def get_supported_technologies(self) -> List[RadioTechnology]:
        return [RadioTechnology.NR5G, RadioTechnology.LTE]

    async def load_state_file(self, filepath: str) -> bool:
        """Mock: 模拟加载配置文件"""
        logger.info(f"[MockBS] load_state_file: {filepath}")
        self._set_status(InstrumentStatus.READY)
        return True

    async def save_state_file(self, filepath: str) -> bool:
        """Mock: 模拟保存配置文件"""
        logger.info(f"[MockBS] save_state_file: {filepath}")
        return True
