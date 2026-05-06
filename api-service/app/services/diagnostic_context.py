"""Shared context for workshop-tier diagnostic tools (SCPI + Commissioning).

Both SCPI sequences and Commissioning ad-hoc need the same upstream
resolution: given a LabProfile id, figure out which chamber, which
instruments (with their actual IP / SCPI endpoint), and which RF chains
are active for a given operating mode. Without this helper each tool
re-implements the same JSONB walk over `lab_profile.instrument_bindings`.

The resolved DiagnosticContext also carries a `record_run()` convenience
that writes to the `diagnostic_runs` audit table, so every tool gets
audit-for-free without duplicating boilerplate.

Read-only with respect to LabProfile / chamber / topology — anything that
mutates production state goes through the formal services, not here.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chamber import ChamberConfiguration
from app.models.diagnostic_run import DiagnosticKind, DiagnosticRun
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile
from app.services.calibration.rf_chain_resolver import (
    RFChainResolution,
    resolve_rf_chains,
)

logger = logging.getLogger(__name__)

# Truncate output_excerpt at ~2KB — full trace lives in log files, pointed
# to by `hal_trace_log_path`. 2 KB is enough to render a recap card in the
# list view without blowing up row size for chatty SCPI sweeps.
_OUTPUT_EXCERPT_BYTES = 2048


@dataclass
class InstrumentBinding:
    """One row of LabProfile.instrument_bindings, parsed and resolved."""

    category_id: Optional[UUID]
    category_key: Optional[str]
    instrument_model_id: Optional[UUID]
    connection_endpoint: Optional[str]  # "192.168.1.10:5025" — what SCPI dials
    driver_mode: str  # "auto" | "mock" | "real"
    role: Optional[str]  # "primary_channel_emulator", "vna", etc.


@dataclass
class DiagnosticContext:
    """Pre-resolved everything-the-workshop-tools-need bundle.

    Constructed once per HTTP request via `build_diagnostic_context()`.
    Doesn't hold the DB session — accept it as a parameter where needed —
    so the context object itself is cheaply serialisable for logging.
    """

    lab_profile_id: Optional[UUID]
    lab_profile_name: Optional[str]
    chamber_id: Optional[UUID]
    chamber_name: Optional[str]
    instrument_bindings: List[InstrumentBinding] = field(default_factory=list)
    rf_chains: Optional[RFChainResolution] = None
    warnings: List[str] = field(default_factory=list)

    # ── Lookups ──────────────────────────────────────────────────────────

    def find_binding_by_role(self, role: str) -> Optional[InstrumentBinding]:
        for b in self.instrument_bindings:
            if b.role == role:
                return b
        return None

    def find_binding_by_category_key(self, category_key: str) -> Optional[InstrumentBinding]:
        for b in self.instrument_bindings:
            if b.category_key == category_key:
                return b
        return None

    def endpoint_for(self, category_key_or_role: str) -> Optional[str]:
        """Return the SCPI endpoint (host:port) for a category or role.

        Tries role first (more specific) then category_key. Returns None
        when the lab hasn't bound an instance — caller decides whether to
        fall back to a hardcoded IP or fail loudly.
        """
        b = (
            self.find_binding_by_role(category_key_or_role)
            or self.find_binding_by_category_key(category_key_or_role)
        )
        return b.connection_endpoint if b else None

    # ── Audit ────────────────────────────────────────────────────────────

    def record_run(
        self,
        db: Session,
        *,
        kind: DiagnosticKind,
        target_name: str,
        success: bool,
        params: Optional[Dict[str, Any]] = None,
        output: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        hal_trace_log_path: Optional[str] = None,
        run_by: Optional[str] = None,
    ) -> DiagnosticRun:
        """Persist a diagnostic_run row. Output is truncated on write."""
        excerpt = _truncate_excerpt(output)
        run = DiagnosticRun(
            kind=kind.value,
            lab_profile_id=self.lab_profile_id,
            target_name=target_name[:255],
            params=params,
            success=success,
            output_excerpt=excerpt,
            error_message=error_message,
            duration_ms=duration_ms,
            hal_trace_log_path=hal_trace_log_path,
            run_by=run_by,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def _truncate_excerpt(output: Optional[str]) -> Optional[str]:
    if output is None:
        return None
    encoded = output.encode("utf-8", errors="replace")
    if len(encoded) <= _OUTPUT_EXCERPT_BYTES:
        return output
    truncated = encoded[: _OUTPUT_EXCERPT_BYTES - 24].decode("utf-8", errors="replace")
    return f"{truncated}\n…[truncated, see full trace]"


def _parse_instrument_bindings(
    db: Session, raw: Optional[Any]
) -> List[InstrumentBinding]:
    """Lab profiles store bindings as a JSON array of dicts. Resolve UUID
    strings to actual UUIDs and pull category_key by joining."""
    if not raw:
        return []
    if isinstance(raw, str):
        # Defensive: some seed scripts double-encode; tolerate it.
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("instrument_bindings is a non-JSON string; ignoring")
            return []
    if not isinstance(raw, list):
        logger.warning("instrument_bindings is not a list (got %s); ignoring", type(raw))
        return []

    category_ids: List[UUID] = []
    rows: List[Dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("category_id")
        try:
            cid_uuid = UUID(cid) if cid else None
        except (ValueError, TypeError):
            cid_uuid = None
        if cid_uuid:
            category_ids.append(cid_uuid)
        rows.append({**entry, "_category_uuid": cid_uuid})

    keys_by_id: Dict[UUID, str] = {}
    if category_ids:
        for cat in db.query(InstrumentCategory).filter(
            InstrumentCategory.id.in_(category_ids)
        ).all():
            keys_by_id[cat.id] = cat.category_key

    bindings: List[InstrumentBinding] = []
    for row in rows:
        cid = row.get("_category_uuid")
        try:
            mid_uuid = UUID(row["instrument_model_id"]) if row.get("instrument_model_id") else None
        except (ValueError, TypeError):
            mid_uuid = None
        bindings.append(
            InstrumentBinding(
                category_id=cid,
                category_key=keys_by_id.get(cid) if cid else None,
                instrument_model_id=mid_uuid,
                connection_endpoint=row.get("connection_endpoint"),
                driver_mode=row.get("driver_mode") or "auto",
                role=row.get("role"),
            )
        )
    return bindings


def build_diagnostic_context(
    db: Session,
    *,
    lab_profile_id: Optional[UUID],
    operating_mode: str = "mimo_ota",
    resolve_rf_chains_too: bool = True,
) -> DiagnosticContext:
    """Resolve everything the workshop tools commonly need.

    `lab_profile_id` is intentionally optional — direct SCPI probes against
    a hardcoded IP don't need a lab and shouldn't be forced to invent one.
    When None, the resulting context still has audit + truncate helpers,
    just no upstream resolution.
    """
    if lab_profile_id is None:
        return DiagnosticContext(
            lab_profile_id=None,
            lab_profile_name=None,
            chamber_id=None,
            chamber_name=None,
        )

    lab = db.query(LabProfile).filter(LabProfile.id == lab_profile_id).first()
    if lab is None:
        # Workshop tools should fail loud rather than silently assume a
        # different lab; ValueError surfaces as 422 in API handlers.
        raise ValueError(f"LabProfile {lab_profile_id} not found")

    warnings: List[str] = []
    chamber_name: Optional[str] = None
    if lab.chamber_config_id:
        chamber = db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == lab.chamber_config_id
        ).first()
        if chamber is not None:
            chamber_name = chamber.name
        else:
            warnings.append(
                f"LabProfile {lab.name} references missing chamber {lab.chamber_config_id}"
            )

    bindings = _parse_instrument_bindings(db, lab.instrument_bindings)

    rf_chains: Optional[RFChainResolution] = None
    if resolve_rf_chains_too and lab.chamber_config_id is not None:
        try:
            rf_chains = resolve_rf_chains(db, lab.id, operating_mode)
            warnings.extend(rf_chains.warnings)
        except ValueError as e:
            # Missing chamber etc. — log but don't fail; SCPI tools may not
            # care about RF chains, only direct instrument endpoints.
            warnings.append(f"RF chain resolution skipped: {e}")

    return DiagnosticContext(
        lab_profile_id=lab.id,
        lab_profile_name=lab.name,
        chamber_id=lab.chamber_config_id,
        chamber_name=chamber_name,
        instrument_bindings=bindings,
        rf_chains=rf_chains,
        warnings=warnings,
    )


@contextmanager
def timed_run(
    db: Session,
    ctx: DiagnosticContext,
    *,
    kind: DiagnosticKind,
    target_name: str,
    params: Optional[Dict[str, Any]] = None,
    run_by: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """Surround a workshop-tier run with timing + audit recording.

    Usage::

        with timed_run(db, ctx, kind=..., target_name=...) as bag:
            ...do the thing...
            bag["output"] = stdout
            # raise on failure to mark success=False; otherwise success=True
    """
    bag: Dict[str, Any] = {"output": None, "error": None, "log_path": None}
    started = time.monotonic()
    try:
        yield bag
        ctx.record_run(
            db,
            kind=kind,
            target_name=target_name,
            success=True,
            params=params,
            output=bag.get("output"),
            duration_ms=int((time.monotonic() - started) * 1000),
            hal_trace_log_path=bag.get("log_path"),
            run_by=run_by,
        )
    except Exception as e:
        ctx.record_run(
            db,
            kind=kind,
            target_name=target_name,
            success=False,
            params=params,
            output=bag.get("output"),
            error_message=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
            hal_trace_log_path=bag.get("log_path"),
            run_by=run_by,
        )
        raise
