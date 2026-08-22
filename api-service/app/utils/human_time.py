"""Formatting helpers for operator-facing identifiers.

Persistence and API timestamps remain UTC.  These helpers are only for names
that an operator compares with local logs and the wall clock.
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings


def _operator_timezone() -> tzinfo:
    try:
        return ZoneInfo(settings.operator_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"unknown OPERATOR_TIMEZONE: {settings.operator_timezone!r}"
        ) from exc


def format_human_local_timestamp(
    moment: Optional[datetime] = None,
    *,
    fmt: str = "%Y%m%d-%H%M%S",
    timezone_override: Optional[tzinfo] = None,
) -> str:
    """Format an instant in the configured operator timezone for a human token."""
    instant = moment or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    local = (
        instant.astimezone(timezone_override)
        if timezone_override is not None
        else instant.astimezone(_operator_timezone())
    )
    return local.strftime(fmt)
