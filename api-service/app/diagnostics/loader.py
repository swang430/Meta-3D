"""Discover sequence modules under `app/diagnostics/sequences/`.

Filesystem walk + importlib — no decorator registry. Adding a sequence
means dropping a `.py` into the directory; restart and it's listed.
Modules without `metadata` or without `async def run(...)` are skipped
with a logged warning so a half-written file doesn't break the whole
list endpoint.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Dict, List

from app.diagnostics import sequences as _sequences_pkg
from app.diagnostics.protocol import SequenceMetadata, SequenceModule

logger = logging.getLogger(__name__)

_cache: Dict[str, SequenceModule] = {}
_loaded = False


def _is_sequence_module(mod) -> bool:
    """True iff the module exports both `metadata` and `run` correctly."""
    if not hasattr(mod, "metadata") or not hasattr(mod, "run"):
        return False
    if not isinstance(getattr(mod, "metadata"), SequenceMetadata):
        return False
    if not callable(getattr(mod, "run")):
        return False
    return True


def _load_all() -> Dict[str, SequenceModule]:
    """Import every non-underscore module under sequences/.

    Idempotent — caches on first call. Restart the process to pick up new
    files (acceptable for a workshop tool; we don't watch the filesystem).
    """
    global _loaded, _cache
    if _loaded:
        return _cache

    discovered: Dict[str, SequenceModule] = {}
    for finder, name, _ispkg in pkgutil.iter_modules(_sequences_pkg.__path__):
        if name.startswith("_"):
            continue
        full = f"{_sequences_pkg.__name__}.{name}"
        try:
            mod = importlib.import_module(full)
        except Exception as e:  # noqa: BLE001
            # Don't let a single broken sequence kill the listing.
            logger.warning("Failed to import diagnostic sequence %s: %s", full, e)
            continue
        if not _is_sequence_module(mod):
            logger.warning(
                "Skipping %s: missing `metadata: SequenceMetadata` or `async def run(...)`",
                full,
            )
            continue
        discovered[name] = mod  # type: ignore[assignment]

    _cache = discovered
    _loaded = True
    return discovered


def list_sequences() -> List[Dict[str, object]]:
    """JSON-friendly dump of every loaded sequence's metadata."""
    out: List[Dict[str, object]] = []
    for key, mod in _load_all().items():
        meta = mod.metadata
        out.append(
            {
                "key": key,
                "name": meta.name,
                "description": meta.description,
                "required_categories": list(meta.required_categories),
                "params_schema": list(meta.params_schema),
                "safe_during_test": meta.safe_during_test,
            }
        )
    out.sort(key=lambda d: d["name"])
    return out


def get_sequence(key: str) -> SequenceModule:
    """Return the loaded module for `key`, or raise KeyError."""
    mods = _load_all()
    if key not in mods:
        raise KeyError(
            f"Diagnostic sequence '{key}' not found. Available: {sorted(mods)}"
        )
    return mods[key]


def reset_cache() -> None:
    """Test hook — flush the import cache. Production code shouldn't call this."""
    global _loaded, _cache
    _loaded = False
    _cache = {}
