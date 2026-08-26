"""R&S CMW500 LTE 2x2 routing and Extended BLER command profile.

Only commands whose response contracts are cited from the vendor manual live
here.  The same builders are used by real and diagnostic transports.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class CmwCommandSpec:
    template: str
    source_reference: str
    purpose: str
    minimum_firmware: str | None = None
    required_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class CmwNx2Route:
    pcc_bb_board: str
    rx_connector: str
    rx_converter: str
    tx1_connector: str
    tx1_converter: str
    tx2_connector: str
    tx2_converter: str


@dataclass(frozen=True)
class CmwNx2RouteReadback:
    scenario: str
    controller: str
    rx_connector: str
    rx_converter: str
    tx1_connector: str
    tx1_converter: str
    tx2_connector: str
    tx2_converter: str


@dataclass(frozen=True)
class CmwExtendedBlerAbsolute:
    reliability: int
    ack_count: int
    nack_count: int
    subframe_count: int
    throughput_average_kbit_per_s: float
    throughput_minimum_kbit_per_s: float
    throughput_maximum_kbit_per_s: float
    dtx_count: int
    scheduled_count: int
    median_cqi: int


@dataclass(frozen=True)
class CmwExtendedBlerRelative:
    reliability: int
    ack_percent: float
    nack_percent: float
    bler_percent: float
    throughput_average_percent: float
    dtx_percent: float


_LTE_MANUAL = "R&S CMW LTE UE User Manual 1173.9628.02-41"

# Every literal below is adjacent to an auditable vendor-manual reference.
CMW500_LTE_COMMANDS: dict[str, CmwCommandSpec] = {
    "route_nx2": CmwCommandSpec(
        template="ROUTe:LTE:SIGN{i}:SCENario:TRO:FLEXible",
        source_reference=f"{_LTE_MANUAL}, §2.6.8.1, printed p.630-631",
        purpose="Select the LTE 1CC-nx2 internal signal route",
        minimum_firmware="V3.5.40",
        required_options=("CMW-KS520",),
    ),
    "route_query": CmwCommandSpec(
        template="ROUTe:LTE:SIGN{i}?",
        source_reference=f"{_LTE_MANUAL}, §2.6.2.2, printed p.459-460",
        purpose="Read the active LTE scenario and its relevant RX/TX paths",
    ),
    "ebler_absolute_query": CmwCommandSpec(
        template="FETCh:LTE:SIGN{i}:EBLer:PCC:ABSolute?",
        source_reference=f"{_LTE_MANUAL}, §3.4.4, printed p.957-958",
        purpose="Read absolute PCC Extended BLER counts and throughput in kbit/s",
        minimum_firmware="V3.0.10",
    ),
    "ebler_relative_query": CmwCommandSpec(
        template="FETCh:LTE:SIGN{i}:EBLer:PCC:RELative?",
        source_reference=f"{_LTE_MANUAL}, §3.4.4, printed p.959",
        purpose="Read relative PCC BLER and throughput percentages",
        minimum_firmware="V3.0.30",
    ),
    "ebler_init": CmwCommandSpec(
        template="INITiate:LTE:SIGN{i}:EBLer",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.950",
        purpose="Start or restart Extended BLER and enter RUN",
        minimum_firmware="V1.0.15.20",
    ),
    "ebler_stop": CmwCommandSpec(
        template="STOP:LTE:SIGN{i}:EBLer",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.950",
        purpose="Stop Extended BLER in RDY while retaining results",
        minimum_firmware="V1.0.15.20",
    ),
    "ebler_abort": CmwCommandSpec(
        template="ABORt:LTE:SIGN{i}:EBLer",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.950",
        purpose="Abort Extended BLER to OFF, clear values, and release resources",
        minimum_firmware="V1.0.15.20",
    ),
    "ebler_state_query": CmwCommandSpec(
        template="FETCh:LTE:SIGN{i}:EBLer:STATe?",
        source_reference=f"{_LTE_MANUAL}, §3.4.2, printed p.951",
        purpose="Read the Extended BLER OFF, RUN, or RDY state",
        minimum_firmware="V1.0.15.20",
    ),
}


def _channel(value: int) -> int:
    if value not in (1, 2):
        raise ValueError("CMW LTE signaling channel must be 1 or 2")
    return value


_ROUTE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")


def normalize_cmw_route_token(value: str, name: str) -> str:
    """Accept only the manual's bare alphanumeric signal-path enum tokens.

    R&S CMW LTE UE User Manual 1173.9628.02-41, §2.6.1.4,
    printed p.363-365 lists the path-selection values as unquoted
    alphanumeric enumerations.  Rejecting every other character prevents a
    persisted route field from becoming an additional SCPI program unit.
    """

    token = value.strip()
    if not _ROUTE_TOKEN_RE.fullmatch(token) or token.upper() == "NAV":
        raise ValueError(f"invalid CMW route token: {name}")
    return token


def _csv(response: str, count: int) -> list[str]:
    values = [value.strip() for value in response.strip().split(",")]
    if len(values) != count or any(not value for value in values):
        raise ValueError(f"expected exactly {count} CMW response fields")
    return values


def _finite(value: str, name: str) -> float:
    if value.upper() == "NAV":
        raise ValueError(f"CMW returned NAV for {name}")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"CMW returned non-numeric {name}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"CMW returned non-finite {name}")
    return parsed


def _integer(value: str, name: str) -> int:
    parsed = _finite(value, name)
    if not parsed.is_integer():
        raise ValueError(f"CMW returned non-integer {name}")
    return int(parsed)


def _reliability(value: str) -> int:
    reliability = _integer(value, "reliability")
    # Manual pp.945-949: 0 is the only "no error" value.  Every other code
    # describes incomplete, impaired, unavailable, or otherwise invalid data.
    if reliability != 0:
        raise ValueError(f"CMW measurement reliability is {reliability}, not 0")
    return reliability


def _percent(value: str, name: str) -> float:
    parsed = _finite(value, name)
    if parsed < 0.0 or parsed > 100.0:
        raise ValueError(f"CMW returned out-of-range {name}")
    return parsed


class Cmw500LteCommandProfile:
    """Builders and strict response parsers for the sourced command subset."""

    @staticmethod
    def _format(name: str, sign_channel: int) -> str:
        return CMW500_LTE_COMMANDS[name].template.format(i=_channel(sign_channel))

    @classmethod
    def build_route_nx2(cls, sign_channel: int, route: CmwNx2Route) -> str:
        values = (
            (route.pcc_bb_board, "pcc_bb_board"),
            (route.rx_connector, "rx_connector"),
            (route.rx_converter, "rx_converter"),
            (route.tx1_connector, "tx1_connector"),
            (route.tx1_converter, "tx1_converter"),
            (route.tx2_connector, "tx2_connector"),
            (route.tx2_converter, "tx2_converter"),
        )
        encoded = ",".join(
            normalize_cmw_route_token(value, name) for value, name in values
        )
        return f"{cls._format('route_nx2', sign_channel)} {encoded}"

    @classmethod
    def route_query(cls, sign_channel: int) -> str:
        return cls._format("route_query", sign_channel)

    @classmethod
    def ebler_absolute_query(cls, sign_channel: int) -> str:
        return cls._format("ebler_absolute_query", sign_channel)

    @classmethod
    def ebler_relative_query(cls, sign_channel: int) -> str:
        return cls._format("ebler_relative_query", sign_channel)

    @classmethod
    def ebler_init(cls, sign_channel: int) -> str:
        return cls._format("ebler_init", sign_channel)

    @classmethod
    def ebler_stop(cls, sign_channel: int) -> str:
        return cls._format("ebler_stop", sign_channel)

    @classmethod
    def ebler_abort(cls, sign_channel: int) -> str:
        return cls._format("ebler_abort", sign_channel)

    @classmethod
    def ebler_state_query(cls, sign_channel: int) -> str:
        return cls._format("ebler_state_query", sign_channel)

    @staticmethod
    def parse_route_readback(response: str) -> CmwNx2RouteReadback:
        values = _csv(response, 8)
        if values[0].upper() != "TRO":
            raise ValueError("CMW route is not the LTE 1CC-nx2 TRO scenario")
        if values[0] != "TRO" or values[1].upper() == "NAV":
            raise ValueError("invalid CMW route scenario/controller")
        for index, name in enumerate(
            ("rx_connector", "rx_converter", "tx1_connector", "tx1_converter",
             "tx2_connector", "tx2_converter"),
            start=2,
        ):
            normalize_cmw_route_token(values[index], name)
        return CmwNx2RouteReadback(*values)

    @staticmethod
    def parse_ebler_absolute(response: str) -> CmwExtendedBlerAbsolute:
        values = _csv(response, 10)
        return CmwExtendedBlerAbsolute(
            reliability=_reliability(values[0]),
            ack_count=_integer(values[1], "ACK count"),
            nack_count=_integer(values[2], "NACK count"),
            subframe_count=_integer(values[3], "subframe count"),
            throughput_average_kbit_per_s=_finite(values[4], "average throughput"),
            throughput_minimum_kbit_per_s=_finite(values[5], "minimum throughput"),
            throughput_maximum_kbit_per_s=_finite(values[6], "maximum throughput"),
            dtx_count=_integer(values[7], "DTX count"),
            scheduled_count=_integer(values[8], "scheduled count"),
            median_cqi=_integer(values[9], "median CQI"),
        )

    @staticmethod
    def parse_ebler_relative(response: str) -> CmwExtendedBlerRelative:
        values = _csv(response, 6)
        return CmwExtendedBlerRelative(
            reliability=_reliability(values[0]),
            ack_percent=_percent(values[1], "ACK percent"),
            nack_percent=_percent(values[2], "NACK percent"),
            bler_percent=_percent(values[3], "BLER percent"),
            throughput_average_percent=_percent(values[4], "throughput percent"),
            dtx_percent=_percent(values[5], "DTX percent"),
        )

    @staticmethod
    def parse_ebler_state(response: str) -> str:
        state = response.strip()
        if state not in {"OFF", "RUN", "RDY"}:
            raise ValueError(f"unknown CMW Extended BLER state: {state!r}")
        return state
