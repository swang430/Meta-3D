"""P0-5 仪器级 SCPI/AeroBasic 证据模型与严格判定。

本模块不持久化证据；P1-47C 会把这里产出的脱敏摘要写入 TestExecution。
原始往返仍只留在 scpi.log，摘要仅保存 exchange_id 关联。
"""
from __future__ import annotations

import contextvars
import fnmatch
import json
import math
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EvidenceLevel(str, Enum):
    INTENT = "E0"
    TRANSPORT = "E1"
    ACCEPTED = "E2"
    APPLIED = "E3"
    OUTCOME = "E4"


class EvidenceStatus(str, Enum):
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    ONSITE_OBSERVED = "onsite-observed"


class EvidenceVerdict(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    source_id: str
    document: str
    section: str


class EvidenceApplicability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: tuple[str, ...]
    test_applications: tuple[str, ...] = ()
    firmware_versions: tuple[str, ...] = ("*",)


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    instrument: str
    mandatory: bool
    command: str
    query: Optional[str] = None
    status: EvidenceStatus
    max_evidence_level: EvidenceLevel
    source: EvidenceSource
    applicability: EvidenceApplicability
    notes: str = ""


class EvidenceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    entries: dict[str, CatalogEntry]


class InstrumentEnvironment(BaseModel):
    """只接受由已建立的真实连接采集的环境快照。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    instrument: str
    # BaseStation 写方显式保存适配器与选件快照；其它仪表保持 None/空元组。
    # 真实性仍由 HAL 的 real/mock 白名单与 live connection 判据决定，不能从
    # adapter 名称本身推导。
    adapter_id: Optional[str] = None
    options: tuple[str, ...] = ()
    model: Optional[str]
    # ``firmware_version`` 是当前命令端点的软件/固件版本，用于手册范围匹配。
    firmware_version: Optional[str]
    test_application: Optional[str] = None
    application_version: Optional[str] = None
    hardware_firmware_version: Optional[str] = None
    serial_number: Optional[str] = None
    captured_from_live_connection: bool = False


class ScopeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    eligible: bool
    instrument_id: str
    source_reference: str
    max_evidence_level: EvidenceLevel
    required_evidence_level: EvidenceLevel
    reason: str


class ScpiExchangeRef(BaseModel):
    """脱敏后的单次往返索引；response 仅供内存判定，不进数据库原始副本。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    exchange_id: str
    instrument_id: str
    operation: str
    command: str
    execution_id: str
    capture_id: str
    sequence: int
    result_type: str = "intent"
    response: Optional[str] = None
    simulated: bool = False


class InstrumentEvidenceItem(BaseModel):
    """P1-47C 固定摘要字段；额外保留 instrument/evidence_key 便于消费。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument: str
    evidence_key: str
    requested: Any
    command_sent: Optional[str]
    readback: Any = None
    exchange_ids: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel
    source_reference: Optional[str]
    verdict: EvidenceVerdict
    reason: str


@dataclass
class _ExchangeCollector:
    execution_id: str
    capture_id: str = field(default_factory=lambda: uuid4().hex)
    exchanges: list[ScpiExchangeRef] = field(default_factory=list)


_exchange_collectors: contextvars.ContextVar[tuple[_ExchangeCollector, ...]] = (
    contextvars.ContextVar("scpi_exchange_collectors", default=())
)


@contextmanager
def capture_scpi_exchanges() -> Iterator[list[ScpiExchangeRef]]:
    """捕获当前上下文（及其子 task）的往返索引，按 TX 发生顺序排列。"""

    from app.core.logging_config import current_execution_id

    collector = _ExchangeCollector(execution_id=current_execution_id.get("-"))
    token = _exchange_collectors.set((*_exchange_collectors.get(), collector))
    try:
        yield collector.exchanges
    finally:
        _exchange_collectors.reset(token)


def record_exchange_intent(
    *,
    exchange_id: str,
    instrument_id: str,
    operation: str,
    command: str,
    simulated: bool = False,
) -> None:
    for collector in _exchange_collectors.get():
        collector.exchanges.append(
            ScpiExchangeRef(
                exchange_id=exchange_id,
                instrument_id=instrument_id,
                operation=operation,
                command=command,
                execution_id=collector.execution_id,
                capture_id=collector.capture_id,
                sequence=len(collector.exchanges),
                simulated=simulated,
            )
        )


def record_exchange_terminal(
    *,
    exchange_id: str,
    result_type: str,
    response: Optional[str] = None,
    simulated: bool = False,
) -> None:
    for collector in _exchange_collectors.get():
        for item in reversed(collector.exchanges):
            if item.exchange_id == exchange_id:
                item.result_type = result_type
                item.response = response
                item.simulated = simulated
                break


_APPROVED_SOURCE_KINDS = {
    "f64": ("notebooklm", "982222b7-4953-46cd-9949-00fa97882353"),
    "uxm": ("notebooklm", "236d9621-e3ce-4ed1-a8e1-7819b674dbcd"),
    "positioner": ("vendor-integration", "aerotech-ensemble-ascii-v1.0"),
}


def validate_catalog_document(raw: dict[str, Any]) -> EvidenceCatalog:
    if raw.get("schema_version") != 1:
        raise ValueError(
            f"unsupported catalog schema_version: {raw.get('schema_version')!r}"
        )
    commands = raw.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("catalog commands must be a non-empty list")
    entries: dict[str, CatalogEntry] = {}
    for item in commands:
        source = item.get("source") if isinstance(item, dict) else None
        if not isinstance(source, dict) or not all(
            source.get(key) for key in ("kind", "source_id", "document", "section")
        ):
            raise ValueError(f"catalog entry {item.get('id')!r} missing source")
        entry = CatalogEntry.model_validate(item)
        approved_source = _APPROVED_SOURCE_KINDS.get(entry.instrument)
        if approved_source != (entry.source.kind, entry.source.source_id):
            raise ValueError(
                f"catalog entry {entry.id!r} source kind/id is not approved for "
                f"{entry.instrument}"
            )
        if entry.id in entries:
            raise ValueError(f"duplicate catalog id: {entry.id}")
        entries[entry.id] = entry
    return EvidenceCatalog(schema_version=1, entries=entries)


def load_p0_5_catalog(path: str | Path) -> EvidenceCatalog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_catalog_document(raw)


@lru_cache(maxsize=1)
def load_default_p0_5_catalog() -> EvidenceCatalog:
    path = Path(__file__).resolve().parents[1] / "data/scpi_evidence/p0_5_commands.json"
    return load_p0_5_catalog(path)


def scope_for_evidence(
    evidence_key: str, environment: InstrumentEnvironment
) -> ScopeDecision:
    catalog = load_default_p0_5_catalog()
    try:
        entry = catalog.entries[evidence_key]
    except KeyError as exc:
        raise ValueError(f"unknown P0-5 evidence key: {evidence_key}") from exc
    return evaluate_catalog_scope(entry, environment)


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    folded = value.casefold()
    return any(fnmatch.fnmatchcase(folded, pattern.casefold()) for pattern in patterns)


def _source_reference(entry: CatalogEntry) -> str:
    src = entry.source
    return f"{src.kind}:{src.source_id}:{src.document}#{src.section}"


def parse_ieee488_identity(raw: Optional[str]) -> dict[str, Optional[str]]:
    """解析常见 manufacturer,model,serial,firmware；缺字段保持 None。"""
    parts = [part.strip() for part in (raw or "").strip().split(",")]
    return {
        "manufacturer": parts[0] or None if len(parts) > 0 else None,
        "model": parts[1] or None if len(parts) > 1 else None,
        "serial_number": parts[2] or None if len(parts) > 2 else None,
        "firmware_version": parts[3] or None if len(parts) > 3 else None,
    }


def evaluate_catalog_scope(
    entry: CatalogEntry, environment: InstrumentEnvironment
) -> ScopeDecision:
    reference = _source_reference(entry)
    if not environment.captured_from_live_connection:
        return ScopeDecision(
            eligible=False,
            instrument_id=environment.instrument_id,
            source_reference=reference,
            max_evidence_level=entry.max_evidence_level,
            required_evidence_level=entry.max_evidence_level,
            reason="environment_not_captured_from_live_connection",
        )
    if not environment.model or not environment.firmware_version:
        return ScopeDecision(
            eligible=False,
            instrument_id=environment.instrument_id,
            source_reference=reference,
            max_evidence_level=entry.max_evidence_level,
            required_evidence_level=entry.max_evidence_level,
            reason="live_environment_missing_model_or_firmware_version",
        )
    if entry.status is not EvidenceStatus.CONFIRMED:
        return ScopeDecision(
            eligible=False,
            instrument_id=environment.instrument_id,
            source_reference=reference,
            max_evidence_level=entry.max_evidence_level,
            required_evidence_level=entry.max_evidence_level,
            reason=f"catalog_status={entry.status.value}",
        )
    if environment.instrument.casefold() != entry.instrument.casefold():
        return ScopeDecision(
            eligible=False,
            instrument_id=environment.instrument_id,
            source_reference=reference,
            max_evidence_level=entry.max_evidence_level,
            required_evidence_level=entry.max_evidence_level,
            reason="instrument_mismatch",
        )
    if not _matches(environment.model, entry.applicability.models):
        return ScopeDecision(
            eligible=False,
            instrument_id=environment.instrument_id,
            source_reference=reference,
            max_evidence_level=entry.max_evidence_level,
            required_evidence_level=entry.max_evidence_level,
            reason=f"model_out_of_scope:{environment.model}",
        )
    if not _matches(
        environment.firmware_version, entry.applicability.firmware_versions
    ):
        return ScopeDecision(
            eligible=False,
            instrument_id=environment.instrument_id,
            source_reference=reference,
            max_evidence_level=entry.max_evidence_level,
            required_evidence_level=entry.max_evidence_level,
            reason=f"firmware_version_out_of_scope:{environment.firmware_version}",
        )
    apps = entry.applicability.test_applications
    if apps and (
        not environment.test_application
        or not _matches(environment.test_application, apps)
    ):
        return ScopeDecision(
            eligible=False,
            instrument_id=environment.instrument_id,
            source_reference=reference,
            max_evidence_level=entry.max_evidence_level,
            required_evidence_level=entry.max_evidence_level,
            reason=f"test_application_out_of_scope:{environment.test_application}",
        )
    return ScopeDecision(
        eligible=True,
        instrument_id=environment.instrument_id,
        source_reference=reference,
        max_evidence_level=entry.max_evidence_level,
        required_evidence_level=entry.max_evidence_level,
        reason="confirmed_scope_match",
    )


def _clean_device_error(response: Optional[str]) -> bool:
    if not response:
        return False
    code = response.strip().split(",", 1)[0].strip()
    try:
        return int(code) == 0
    except ValueError:
        return False


_LEVEL_ORDER = {
    EvidenceLevel.INTENT: 0,
    EvidenceLevel.TRANSPORT: 1,
    EvidenceLevel.ACCEPTED: 2,
    EvidenceLevel.APPLIED: 3,
    EvidenceLevel.OUTCOME: 4,
}


def _apply_scope(
    scope: ScopeDecision,
    level: EvidenceLevel,
    verdict: EvidenceVerdict,
    reason: str,
) -> tuple[EvidenceLevel, EvidenceVerdict, str]:
    if not scope.eligible:
        return level, EvidenceVerdict.UNKNOWN, scope.reason
    if _LEVEL_ORDER[level] > _LEVEL_ORDER[scope.max_evidence_level]:
        return (
            scope.max_evidence_level,
            EvidenceVerdict.UNKNOWN,
            f"catalog_max_evidence_level={scope.max_evidence_level.value}",
        )
    if (
        verdict is EvidenceVerdict.PASSED
        and _LEVEL_ORDER[level] < _LEVEL_ORDER[scope.required_evidence_level]
    ):
        return (
            level,
            EvidenceVerdict.UNKNOWN,
            f"required_evidence_level={scope.required_evidence_level.value}",
        )
    return level, verdict, reason


_TRANSPORT_TERMINALS = {
    "ok",
    "response",
    "empty_response",
    "whitespace_response",
    "not_ready",
}


def _transport_succeeded(exchange: Optional[ScpiExchangeRef]) -> bool:
    return bool(
        exchange
        and not exchange.simulated
        and exchange.result_type in _TRANSPORT_TERMINALS
    )


def _value_response(exchange: Optional[ScpiExchangeRef]) -> Optional[str]:
    if not exchange or exchange.simulated or exchange.result_type != "response":
        return None
    return exchange.response


def _command_header(exchange: Optional[ScpiExchangeRef]) -> str:
    if not exchange:
        return ""
    return exchange.command.strip().split(maxsplit=1)[0].upper()


def _declared_header_variants(declared: str) -> tuple[str, ...]:
    header = declared.strip().split(maxsplit=1)[0]
    if "[:NEXT]" in header:
        return (header.replace("[:NEXT]", ""), header.replace("[:NEXT]", ":NEXT"))
    return (header,)


def _segment_matches_declared(actual: str, declared: str) -> bool:
    if declared.startswith("<") and declared.endswith(">"):
        return bool(actual)
    if "<" in declared and ">" in declared:
        prefix, remainder = declared.split("<", 1)
        _, suffix = remainder.split(">", 1)
        return actual.upper().startswith(prefix.upper()) and actual.upper().endswith(
            suffix.upper()
        )
    common_prefix = "*" if declared.startswith("*") else ""
    if common_prefix and not actual.startswith(common_prefix):
        return False
    actual = actual.removeprefix(common_prefix)
    declared = declared.removeprefix(common_prefix)
    mandatory = "".join(char for char in declared if char.isupper() or char.isdigit())
    full = "".join(char for char in declared if char.isalpha() or char.isdigit()).upper()
    actual = actual.upper()
    return bool(mandatory) and len(actual) >= len(mandatory) and full.startswith(actual)


def _header_matches_declared(
    exchange: Optional[ScpiExchangeRef], declared: str, *, optional_bse: bool = False
) -> bool:
    if not exchange:
        return False
    actual_header = _command_header(exchange)
    for variant in _declared_header_variants(declared):
        declared_query = variant.endswith("?")
        actual_query = actual_header.endswith("?")
        if declared_query != actual_query:
            continue
        actual = actual_header.removesuffix("?").lstrip(":").split(":")
        template = variant.removesuffix("?").lstrip(":").split(":")
        if optional_bse and actual and actual[0] == "BSE" and template[0] != "BSE":
            actual = actual[1:]
        matched = True
        for index, declared_segment in enumerate(template):
            if declared_segment == "<parameter>" and index == len(template) - 1:
                matched = len(actual) > index
                break
            if index >= len(actual) or not _segment_matches_declared(
                actual[index], declared_segment
            ):
                matched = False
                break
        if matched and (
            len(actual) == len(template) or template[-1] == "<parameter>"
        ):
            return True
    return False


def _matches_catalog_role(
    exchange: Optional[ScpiExchangeRef],
    evidence_key: str,
    field_name: str,
    *,
    optional_bse: bool = False,
) -> bool:
    entry = load_default_p0_5_catalog().entries[evidence_key]
    declared = getattr(entry, field_name)
    if not declared:
        return False
    expected_operation = "query" if field_name == "query" else "command"
    return bool(
        exchange
        and exchange.operation == expected_operation
        and _header_matches_declared(exchange, declared, optional_bse=optional_bse)
    )


def exchange_matches_catalog_role(
    exchange: Optional[ScpiExchangeRef],
    evidence_key: str,
    field_name: str,
    *,
    optional_bse: bool = False,
) -> bool:
    """P1-47C 公共选择器：按已审清单识别捕获往返，不复制命令拼写。"""
    return _matches_catalog_role(
        exchange,
        evidence_key,
        field_name,
        optional_bse=optional_bse,
    )


def _is_error_query(exchange: Optional[ScpiExchangeRef]) -> bool:
    return _matches_catalog_role(exchange, "f64.error_queue", "query")


def _is_opc_query(exchange: Optional[ScpiExchangeRef]) -> bool:
    return _matches_catalog_role(exchange, "f64.operation_complete", "query")


def _is_f64_state_query(exchange: Optional[ScpiExchangeRef]) -> bool:
    return _matches_catalog_role(exchange, "f64.simulation_state", "query")


def _is_uxm_apply(exchange: Optional[ScpiExchangeRef]) -> bool:
    return _matches_catalog_role(exchange, "uxm.config_apply", "command")


def _is_uxm_protocol_state_query(exchange: Optional[ScpiExchangeRef]) -> bool:
    return _matches_catalog_role(exchange, "uxm.cell_status", "query")


def exchange_matches_uxm_cell_activation(
    exchange: Optional[ScpiExchangeRef],
) -> bool:
    """识别 start_signaling 的 CELL ON 写入，不把任意 ON 命令当应用证据。"""
    return bool(
        exchange
        and exchange.operation == "command"
        and _transport_succeeded(exchange)
        and _header_matches_declared(
            exchange,
            "CONFigure:NR5G:<cell>:ACTive:STATe",
            optional_bse=True,
        )
        and str(_command_operand(exchange)).strip().upper() in {"1", "ON"}
    )


def _is_positioner_move(exchange: Optional[ScpiExchangeRef]) -> bool:
    return _matches_catalog_role(exchange, "positioner.move_absolute", "command")


def _is_positioner_feedback(exchange: Optional[ScpiExchangeRef]) -> bool:
    return _matches_catalog_role(exchange, "positioner.position_feedback", "query")


_F64_RECIPES = {
    "f64.model_load": ("f64.model_load", "f64.model_state", "f64.simulation_state"),
    "f64.simulation_state": (
        "f64.simulation_state",
        "f64.simulation_state",
        "f64.simulation_state",
    ),
    "f64.center_frequency": ("f64.center_frequency", "f64.center_frequency", None),
    "f64.input_reference": ("f64.input_reference", "f64.input_reference", None),
    "f64.crest_factor": ("f64.crest_factor", "f64.crest_factor", None),
    "f64.output_gain": ("f64.output_gain", "f64.output_gain", None),
    "f64.output_loss": ("f64.output_loss", "f64.output_loss", None),
    "f64.bypass_mode": (
        "f64.bypass_mode",
        "f64.bypass_mode",
        "f64.simulation_state",
    ),
}

_F64_SIMULATION_STATES = frozenset(
    {"CLOSED", "OPENING", "STOPPING", "STOPPED", "RUNNING", "EDITING", "CLOSING"}
)


def _f64_roles_match(
    evidence_key: str,
    command_exchange: Optional[ScpiExchangeRef],
    readback_exchange: Optional[ScpiExchangeRef],
    state_exchange: Optional[ScpiExchangeRef],
) -> bool:
    recipe = _F64_RECIPES.get(evidence_key)
    if not recipe:
        return False
    command_key, readback_key, state_key = recipe
    if not _matches_catalog_role(command_exchange, command_key, "command"):
        return False
    if evidence_key == "f64.simulation_state":
        # 运行态 recipe 既可带 MODEL:STATE? 作为模型上下文，再用 STATE?
        # 判 RUNNING；也可像活跃 start_emulation 一样直接以同一条 STATE?
        # 同时承担回读和生效状态。
        return _matches_catalog_role(
            readback_exchange, "f64.model_state", "query"
        ) or _matches_catalog_role(
            readback_exchange, "f64.simulation_state", "query"
        )
    if not _matches_catalog_role(readback_exchange, readback_key, "query"):
        return False
    return state_key is None or _matches_catalog_role(
        state_exchange, state_key, "query"
    )


def _uxm_config_roles_match(
    command_exchange: Optional[ScpiExchangeRef],
    readback_exchange: Optional[ScpiExchangeRef],
) -> bool:
    roles_match = _matches_catalog_role(
        command_exchange, "uxm.config_readback", "command", optional_bse=True
    ) and _matches_catalog_role(
        readback_exchange, "uxm.config_readback", "query", optional_bse=True
    )
    if not roles_match:
        return False
    command_path = _command_header(command_exchange).removesuffix("?")
    query_path = _command_header(readback_exchange).removesuffix("?")
    command_path = command_path.removeprefix("BSE:")
    query_path = query_path.removeprefix("BSE:")
    return command_path == query_path


def _requested_scalar(requested: Any) -> Any:
    if isinstance(requested, dict):
        if len(requested) != 1:
            return None
        return next(iter(requested.values()))
    return requested


def _command_operand(exchange: Optional[ScpiExchangeRef]) -> Any:
    if not exchange:
        return None
    parts = exchange.command.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    return _parse_first_scalar(parts[1].rsplit(",", 1)[-1])


def _parse_first_scalar(response: Optional[str]) -> Any:
    if response is None:
        return None
    token = response.strip().split(",", 1)[0].strip().strip("\"'")
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return token


def _response_matches_expected(response: Optional[str], expected: Any) -> bool:
    actual = _parse_first_scalar(response)
    return _scalar_values_match(actual, expected)


def _scalar_values_match(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None or isinstance(expected, bool):
        return False
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and math.isclose(
            actual, float(expected), rel_tol=1e-9, abs_tol=1e-9
        )
    return str(actual).casefold() == str(expected).strip().strip("\"'").casefold()


def _exchange_ids(*exchanges: Optional[ScpiExchangeRef]) -> list[str]:
    """按事务语义顺序输出去重后的往返 ID。"""
    ordered: list[str] = []
    for exchange in exchanges:
        if exchange and exchange.exchange_id not in ordered:
            ordered.append(exchange.exchange_id)
    return ordered


def _apply_exchange_origin(
    scope: ScopeDecision,
    level: EvidenceLevel,
    verdict: EvidenceVerdict,
    reason: str,
    exchanges: list[Optional[ScpiExchangeRef]],
    *,
    allow_interleaved: bool = False,
) -> tuple[EvidenceLevel, EvidenceVerdict, str]:
    exchange_ids = [exchange.exchange_id for exchange in exchanges if exchange]
    if len(exchange_ids) != len(set(exchange_ids)):
        return level, EvidenceVerdict.UNKNOWN, "duplicate_exchange_id_across_stages"
    wrong = sorted(
        {
            exchange.instrument_id
            for exchange in exchanges
            if exchange and exchange.instrument_id != scope.instrument_id
        }
    )
    if wrong:
        return (
            level,
            EvidenceVerdict.UNKNOWN,
            f"exchange_instrument_mismatch:{','.join(wrong)}",
        )
    present = [exchange for exchange in exchanges if exchange]
    if present:
        from app.core.logging_config import current_execution_id

        execution_ids = {exchange.execution_id for exchange in present}
        active_execution_id = current_execution_id.get("-")
        if (
            len(execution_ids) != 1
            or "-" in execution_ids
            or "" in execution_ids
            or active_execution_id in {"", "-"}
            or execution_ids != {active_execution_id}
        ):
            return level, EvidenceVerdict.UNKNOWN, "exchange_execution_mismatch"
        capture_ids = {exchange.capture_id for exchange in present}
        if len(capture_ids) != 1 or "" in capture_ids:
            return level, EvidenceVerdict.UNKNOWN, "exchange_capture_mismatch"
        sequence = [exchange.sequence for exchange in present]
        if sequence != sorted(sequence) or len(sequence) != len(set(sequence)):
            return level, EvidenceVerdict.UNKNOWN, "exchange_stage_order_mismatch"
        if (
            not allow_interleaved
            and sequence != list(range(sequence[0], sequence[0] + len(sequence)))
        ):
            return level, EvidenceVerdict.UNKNOWN, "exchange_stage_interleaved"
    return level, verdict, reason


def _error_queue_precleared(exchanges: list[ScpiExchangeRef]) -> bool:
    """允许先排出旧错误，但最后一条必须是可解析的 clean 响应。"""
    return bool(
        exchanges
        and all(
            _is_error_query(exchange) and _value_response(exchange) is not None
            for exchange in exchanges
        )
        and _clean_device_error(_value_response(exchanges[-1]))
    )


def build_f64_evidence(
    *,
    evidence_key: str,
    requested: Any,
    preclear_exchanges: list[ScpiExchangeRef],
    command_exchange: Optional[ScpiExchangeRef],
    opc_exchange: Optional[ScpiExchangeRef],
    error_exchange: Optional[ScpiExchangeRef],
    readback_exchange: Optional[ScpiExchangeRef],
    state_exchange: Optional[ScpiExchangeRef],
    scope: ScopeDecision,
) -> InstrumentEvidenceItem:
    command_sent = command_exchange.command if command_exchange else None
    opc_response = _value_response(opc_exchange)
    error_response = _value_response(error_exchange)
    simulation_state = _value_response(state_exchange)
    readback_response = _value_response(readback_exchange)
    expected_readback = _requested_scalar(requested)
    command_operand = _command_operand(command_exchange)
    command_matches_requested = (
        evidence_key == "f64.simulation_state"
        or _scalar_values_match(command_operand, expected_readback)
    )
    wire_expected = (
        expected_readback
        if evidence_key == "f64.simulation_state"
        else command_operand
    )
    readback_matches_wire = (
        bool(readback_response and readback_response.strip())
        if evidence_key == "f64.model_load"
        else _response_matches_expected(readback_response, wire_expected)
    )
    bypass_state_valid = evidence_key != "f64.bypass_mode" or (
        _transport_succeeded(state_exchange)
        and _is_f64_state_query(state_exchange)
        and (simulation_state or "").strip().upper() in _F64_SIMULATION_STATES
    )
    queue_precleared = _error_queue_precleared(preclear_exchanges)
    level = EvidenceLevel.INTENT
    verdict = EvidenceVerdict.UNKNOWN
    reason = "command_not_sent"
    if _transport_succeeded(command_exchange):
        level = EvidenceLevel.TRANSPORT
        reason = "transport_recorded_but_acceptance_not_proven"
    relevant = [
        command_exchange,
        opc_exchange,
        error_exchange,
        readback_exchange,
        state_exchange,
    ]
    rejected_stage = next(
        (
            exchange
            for exchange in relevant
            if exchange and exchange.result_type == "device_rejected"
        ),
        None,
    )
    if rejected_stage:
        level = EvidenceLevel.TRANSPORT
        verdict = EvidenceVerdict.REJECTED
        reason = f"device_rejected:{rejected_stage.exchange_id}"
    elif not queue_precleared:
        reason = "error_queue_preclear_not_confirmed"
    elif (
        _transport_succeeded(command_exchange)
        and error_response is not None
        and not _clean_device_error(error_response)
    ):
        verdict = EvidenceVerdict.REJECTED
        reason = f"device_error:{error_response}"
    elif (
        _transport_succeeded(command_exchange)
        and command_exchange.operation == "command"
        and _is_opc_query(opc_exchange)
        and opc_response is not None
        and opc_response.strip() == "1"
        and _is_error_query(error_exchange)
        and _clean_device_error(error_response)
        and _f64_roles_match(
            evidence_key, command_exchange, readback_exchange, state_exchange
        )
        and readback_response is not None
        and readback_matches_wire
        and not command_matches_requested
    ):
        level = EvidenceLevel.ACCEPTED
        verdict = EvidenceVerdict.REJECTED
        reason = "requested_command_mismatch"
    elif (
        _transport_succeeded(command_exchange)
        and command_exchange.operation == "command"
        and _is_opc_query(opc_exchange)
        and opc_response is not None
        and opc_response.strip() == "1"
        and _is_error_query(error_exchange)
        and _clean_device_error(error_response)
        and _f64_roles_match(
            evidence_key, command_exchange, readback_exchange, state_exchange
        )
        and readback_response is not None
        and readback_matches_wire
        and command_matches_requested
        and bypass_state_valid
    ):
        level = EvidenceLevel.ACCEPTED
        verdict = EvidenceVerdict.PASSED
        reason = "opc_complete_error_queue_clean_readback_matched"
        recipe = _F64_RECIPES[evidence_key]
        if (
            evidence_key == "f64.model_load"
            and (simulation_state or "").strip().upper()
            in {"STOPPED", "RUNNING", "EDITING"}
        ):
            level = EvidenceLevel.APPLIED
            reason = (
                "accepted_and_model_loaded_state="
                f"{(simulation_state or '').strip().upper()}"
            )
        elif evidence_key == "f64.bypass_mode":
            level = EvidenceLevel.APPLIED
            reason = (
                "accepted_and_bypass_readback_matched_state="
                f"{(simulation_state or '').strip().upper()}"
            )
        elif recipe[2] and _is_f64_state_query(state_exchange) and (
            simulation_state or ""
        ).strip().upper() == "RUNNING":
            level = EvidenceLevel.APPLIED
            reason = "accepted_and_simulation_running"
    elif (
        _transport_succeeded(command_exchange)
        and command_exchange.operation == "command"
        and _is_opc_query(opc_exchange)
        and opc_response is not None
        and opc_response.strip() == "1"
        and _is_error_query(error_exchange)
        and _clean_device_error(error_response)
        and _f64_roles_match(
            evidence_key, command_exchange, readback_exchange, state_exchange
        )
        and readback_response is not None
        and (not readback_matches_wire or not command_matches_requested)
    ):
        level = EvidenceLevel.ACCEPTED
        verdict = EvidenceVerdict.REJECTED
        reason = "readback_mismatch"
    elif error_exchange and not _transport_succeeded(error_exchange):
        reason = f"error_query_terminal={error_exchange.result_type}"
    elif readback_exchange and not _transport_succeeded(readback_exchange):
        reason = f"readback_terminal={readback_exchange.result_type}"
    elif evidence_key == "f64.bypass_mode" and state_exchange is None:
        reason = "state_readback_missing"
    elif evidence_key == "f64.bypass_mode" and not _transport_succeeded(
        state_exchange
    ):
        reason = f"state_query_terminal={state_exchange.result_type}"
    elif evidence_key == "f64.bypass_mode" and not _is_f64_state_query(
        state_exchange
    ):
        reason = "catalog_command_role_mismatch"
    elif evidence_key == "f64.bypass_mode" and not bypass_state_valid:
        reason = "state_readback_invalid"
    elif command_exchange or readback_exchange:
        reason = "catalog_command_role_mismatch"
    origin_exchanges = [
        *preclear_exchanges,
        command_exchange,
        opc_exchange,
        error_exchange,
        readback_exchange,
        state_exchange,
    ]
    if evidence_key == "f64.simulation_state":
        # GO 的业务回读与生效状态是同一条 STATE?；只在 provenance 顺序门中
        # 去重，摘要 exchange_ids 本来也按 ID 去重。
        seen_origin_ids: set[str] = set()
        deduplicated: list[Optional[ScpiExchangeRef]] = []
        for exchange in origin_exchanges:
            if exchange is None or exchange.exchange_id not in seen_origin_ids:
                deduplicated.append(exchange)
                if exchange is not None:
                    seen_origin_ids.add(exchange.exchange_id)
        origin_exchanges = deduplicated
    level, verdict, reason = _apply_exchange_origin(
        scope,
        level,
        verdict,
        reason,
        origin_exchanges,
    )
    level, verdict, reason = _apply_scope(scope, level, verdict, reason)
    return InstrumentEvidenceItem(
        instrument="f64",
        evidence_key=evidence_key,
        requested=requested,
        command_sent=command_sent,
        readback={
            "value": _parse_first_scalar(readback_response),
            "expected": expected_readback,
            "simulation_state": simulation_state,
        },
        exchange_ids=_exchange_ids(
            *preclear_exchanges,
            command_exchange,
            opc_exchange,
            error_exchange,
            readback_exchange,
            state_exchange,
        ),
        evidence_level=level,
        source_reference=scope.source_reference,
        verdict=verdict,
        reason=reason,
    )


def build_uxm_evidence(
    *,
    evidence_key: str,
    requested: Any,
    command_exchange: Optional[ScpiExchangeRef],
    readback_exchange: Optional[ScpiExchangeRef],
    apply_exchange: Optional[ScpiExchangeRef],
    protocol_state_exchange: Optional[ScpiExchangeRef],
    scope: ScopeDecision,
    activation_exchange: Optional[ScpiExchangeRef] = None,
) -> InstrumentEvidenceItem:
    command_sent = command_exchange.command if command_exchange else None
    protocol_state = _value_response(protocol_state_exchange)
    readback_response = _value_response(readback_exchange)
    expected_readback = _requested_scalar(requested)
    command_operand = _command_operand(command_exchange)
    command_matches_requested = _scalar_values_match(
        command_operand, expected_readback
    )
    readback_matches_wire = _response_matches_expected(
        readback_response, command_operand
    )
    level = EvidenceLevel.INTENT
    verdict = EvidenceVerdict.UNKNOWN
    reason = "command_not_sent"
    if _transport_succeeded(command_exchange):
        level = EvidenceLevel.TRANSPORT
        reason = "transport_recorded_but_readback_missing"
    rejected_stage = next(
        (
            exchange
            for exchange in (
                command_exchange,
                readback_exchange,
                apply_exchange,
                activation_exchange,
                protocol_state_exchange,
            )
            if exchange and exchange.result_type == "device_rejected"
        ),
        None,
    )
    if rejected_stage:
        level = EvidenceLevel.TRANSPORT
        verdict = EvidenceVerdict.REJECTED
        reason = f"device_rejected:{rejected_stage.exchange_id}"
    elif (
        _transport_succeeded(command_exchange)
        and _uxm_config_roles_match(command_exchange, readback_exchange)
        and readback_response is not None
        and readback_matches_wire
        and not command_matches_requested
    ):
        level = EvidenceLevel.ACCEPTED
        verdict = EvidenceVerdict.REJECTED
        reason = "requested_command_mismatch"
    elif (
        _transport_succeeded(command_exchange)
        and _uxm_config_roles_match(command_exchange, readback_exchange)
        and readback_response is not None
        and readback_matches_wire
        and command_matches_requested
    ):
        # 配置 query 只证明配置被接受；手册没有保证它等于协议栈生效值。
        level = EvidenceLevel.ACCEPTED
        verdict = EvidenceVerdict.PASSED
        reason = "configuration_readback_matched"
    elif (
        _transport_succeeded(command_exchange)
        and _uxm_config_roles_match(command_exchange, readback_exchange)
        and readback_response is not None
        and (not readback_matches_wire or not command_matches_requested)
    ):
        level = EvidenceLevel.ACCEPTED
        verdict = EvidenceVerdict.REJECTED
        reason = "readback_mismatch"
    elif command_exchange or readback_exchange:
        reason = "catalog_command_role_mismatch"
    state = (protocol_state or "").strip().upper()
    apply_path = bool(
        _transport_succeeded(apply_exchange) and _is_uxm_apply(apply_exchange)
    )
    activation_path = exchange_matches_uxm_cell_activation(activation_exchange)
    if (
        level is EvidenceLevel.ACCEPTED
        and verdict is EvidenceVerdict.PASSED
        and (apply_path or activation_path)
        and _is_uxm_protocol_state_query(protocol_state_exchange)
        and _value_response(protocol_state_exchange) is not None
        and state in {
            "ON",
            "IDLE",
            "CONN",
            "CONNECTED",
            "AGGR",
            "AGGREGATED",
            "ACT",
            "ACTIVATED",
        }
    ):
        level = EvidenceLevel.APPLIED
        reason = (
            f"apply_sent_and_protocol_state={state}"
            if apply_path
            else f"cell_activated_and_protocol_state={state}"
        )
    application_exchange = (
        apply_exchange
        if apply_path
        else (
            activation_exchange
            if activation_path
            else apply_exchange or activation_exchange
        )
    )
    semantic_origin = [
        command_exchange,
        application_exchange,
        protocol_state_exchange,
        readback_exchange,
    ]
    present_origin = [exchange for exchange in semantic_origin if exchange]
    if len(present_origin) == 4:
        cmd_seq = command_exchange.sequence
        apply_seq = application_exchange.sequence
        state_seq = protocol_state_exchange.sequence
        read_seq = readback_exchange.sequence
        valid_transaction_order = (
            cmd_seq < apply_seq < state_seq < read_seq
            or cmd_seq < read_seq < apply_seq < state_seq
            # RealUxmDriver.set_cell_config 的 ON 路径先发 APPLY、随后做配置
            # readback；长事务末尾 start_signaling 才提供协议状态。
            or cmd_seq < apply_seq < read_seq < state_seq
        )
        if valid_transaction_order:
            semantic_origin = sorted(present_origin, key=lambda item: item.sequence)
    elif (
        present_origin
        and command_exchange is not None
        and command_exchange.sequence
        == min(exchange.sequence for exchange in present_origin)
        and len({exchange.sequence for exchange in present_origin})
        == len(present_origin)
    ):
        semantic_origin = sorted(present_origin, key=lambda item: item.sequence)
    level, verdict, reason = _apply_exchange_origin(
        scope,
        level,
        verdict,
        reason,
        semantic_origin,
        allow_interleaved=True,
    )
    level, verdict, reason = _apply_scope(scope, level, verdict, reason)
    return InstrumentEvidenceItem(
        instrument="uxm",
        evidence_key=evidence_key,
        requested=requested,
        command_sent=command_sent,
        readback={
            "value": _parse_first_scalar(readback_response),
            "expected": expected_readback,
            "protocol_state": protocol_state,
        },
        exchange_ids=_exchange_ids(*semantic_origin),
        evidence_level=level,
        source_reference=scope.source_reference,
        verdict=verdict,
        reason=reason,
    )


def build_uxm_throughput_evidence(
    *,
    requested: Any,
    throughput_exchange: Optional[ScpiExchangeRef],
    scope: ScopeDecision,
) -> InstrumentEvidenceItem:
    """业务结果必须来自本次成功 query；有效且有限的正值才判 E4 通过。"""
    level = EvidenceLevel.INTENT
    verdict = EvidenceVerdict.UNKNOWN
    reason = "throughput_query_not_sent"
    if _transport_succeeded(throughput_exchange):
        level = EvidenceLevel.TRANSPORT
        reason = "throughput_transport_recorded_but_value_missing"
    response = _value_response(throughput_exchange)
    parsed: list[Optional[float]] = []
    if response is not None:
        for token in response.split(","):
            try:
                value = float(token.strip())
            except (TypeError, ValueError):
                parsed.append(None)
                continue
            parsed.append(
                value
                if math.isfinite(value) and abs(value) < 9.9e36
                else None
            )
    progress = parsed[0] if len(parsed) == 6 else None
    throughput_bps = parsed[4] if len(parsed) == 6 else None
    measurement_valid = bool(
        progress is not None
        and progress > 0
        and throughput_bps is not None
        and throughput_bps > 0
    )
    if (
        _matches_catalog_role(
            throughput_exchange, "uxm.dl_throughput", "query"
        )
        and response is not None
    ):
        level = EvidenceLevel.OUTCOME
        if measurement_valid:
            verdict = EvidenceVerdict.PASSED
            reason = "valid_positive_downlink_throughput"
        else:
            verdict = EvidenceVerdict.REJECTED
            reason = "invalid_or_nonpositive_downlink_throughput"
    level, verdict, reason = _apply_exchange_origin(
        scope, level, verdict, reason, [throughput_exchange]
    )
    level, verdict, reason = _apply_scope(scope, level, verdict, reason)
    return InstrumentEvidenceItem(
        instrument="uxm",
        evidence_key="uxm.dl_throughput",
        requested=requested,
        command_sent=(
            throughput_exchange.command if throughput_exchange else None
        ),
        readback={
            "throughput_bps": throughput_bps,
            "measurement_valid": measurement_valid,
            "progress": progress,
        },
        exchange_ids=_exchange_ids(throughput_exchange),
        evidence_level=level,
        source_reference=scope.source_reference,
        verdict=verdict,
        reason=reason,
    )


def build_positioner_evidence(
    *,
    requested_angle_deg: float,
    coordinate_offset_deg: Optional[float],
    offset_calibrated: bool,
    tolerance_deg: float,
    move_exchange: Optional[ScpiExchangeRef],
    feedback_exchange: Optional[ScpiExchangeRef],
    scope: ScopeDecision,
) -> InstrumentEvidenceItem:
    command_sent = move_exchange.command if move_exchange else None
    response = _value_response(feedback_exchange)
    # AeroBasic 的成功响应在线上以 ``%`` 开头；P1-47A 捕获的是驱动剥离
    # ACK 之前的原始响应，因此证据解析必须在这里显式识别该协议前缀。
    normalized_response = (
        response.strip().removeprefix("%").strip() if response is not None else None
    )
    parsed_feedback = _parse_first_scalar(normalized_response)
    raw_feedback_angle_deg = (
        parsed_feedback if isinstance(parsed_feedback, float) else None
    )
    corrected = (
        (raw_feedback_angle_deg - coordinate_offset_deg) % 360.0
        if raw_feedback_angle_deg is not None and coordinate_offset_deg is not None
        else None
    )
    formal_tolerance_deg = min(max(float(tolerance_deg), 0.0), 1.0)
    readback = {
        "raw_feedback_angle_deg": raw_feedback_angle_deg,
        "coordinate_offset_deg": coordinate_offset_deg,
        "offset_calibrated": offset_calibrated,
        "corrected_angle_deg": corrected,
        "tolerance_deg": formal_tolerance_deg,
    }
    level = EvidenceLevel.INTENT
    verdict = EvidenceVerdict.UNKNOWN
    reason = "command_not_sent"
    if (
        _is_positioner_move(move_exchange)
        and move_exchange.result_type == "device_rejected"
    ):
        level = EvidenceLevel.TRANSPORT
        verdict = EvidenceVerdict.REJECTED
        reason = "controller_device_rejected_move"
    elif _is_positioner_move(move_exchange) and _transport_succeeded(move_exchange):
        level = EvidenceLevel.ACCEPTED
        reason = "controller_acknowledged_move_but_position_not_proven"
    if verdict is EvidenceVerdict.REJECTED:
        pass
    elif not _transport_succeeded(move_exchange):
        reason = "move_transport_not_confirmed"
    elif (
        not _is_positioner_feedback(feedback_exchange)
        or _value_response(feedback_exchange) is None
    ):
        reason = "position_feedback_transport_not_confirmed"
    elif not offset_calibrated or corrected is None:
        reason = "coordinate_offset_not_calibrated"
    else:
        error = abs((corrected - requested_angle_deg + 180.0) % 360.0 - 180.0)
        readback["error_deg"] = error
        level = EvidenceLevel.APPLIED
        if error <= formal_tolerance_deg:
            verdict = EvidenceVerdict.PASSED
            reason = "calibrated_feedback_within_tolerance"
        else:
            verdict = EvidenceVerdict.REJECTED
            reason = f"feedback_error_exceeds_tolerance:{error:.6f}"
    level, verdict, reason = _apply_exchange_origin(
        scope,
        level,
        verdict,
        reason,
        [move_exchange, feedback_exchange],
        # 真实 move_to 在 MOVEABS 与最终 PFBK 之间使用厂商指南有出处的
        # WAIT INPOS，并以零速 VFBK + 最终 PFBK 做动作真值门。
        # 这些同 capture/同仪器的受控查询不能让合法证据永久降级为 interleaved。
        allow_interleaved=True,
    )
    level, verdict, reason = _apply_scope(scope, level, verdict, reason)
    return InstrumentEvidenceItem(
        instrument="positioner",
        evidence_key="positioner.angle",
        requested={"angle_deg": requested_angle_deg},
        command_sent=command_sent,
        readback=readback,
        exchange_ids=_exchange_ids(move_exchange, feedback_exchange),
        evidence_level=level,
        source_reference=scope.source_reference,
        verdict=verdict,
        reason=reason,
    )
