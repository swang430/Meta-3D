"""Shared datetime serialization for API schemas.

Naive datetimes coming from the database (columns declared as plain `DateTime`
without `timezone=True`) are assumed to be UTC, since they are produced by
`func.now()` / `datetime.utcnow()`. This module ensures they are serialized
as ISO 8601 with a trailing `Z` so browsers do not misinterpret them as local
time.
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer


def _serialize_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[
    datetime,
    PlainSerializer(_serialize_utc, return_type=str, when_used="json"),
]
