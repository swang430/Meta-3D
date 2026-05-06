"""Contract for diagnostic sequences.

A sequence is just a Python module with a `metadata` dict + an async `run`.
Keeping the protocol tiny on purpose — every additional ceremony makes
on-site quick fixes harder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol


@dataclass
class SequenceMetadata:
    """Metadata exposed by each sequence module.

    `required_categories` lists InstrumentCategory keys ('channelEmulator',
    'baseStation', etc.) the sequence calls into; used to pre-flight check
    that the lab has them bound + the driver loaded before invocation.
    Empty list means "no HAL needed" (rare — only for sanity/echo helpers).

    `params_schema` is a *non-validated* hint to the GUI for rendering an
    inputs form. Keep it shallow: each entry { name, label, type:
    "number"|"string"|"boolean", default? }. We deliberately don't pull in
    Pydantic / JSON Schema for these — sequences should be cheap to add.
    """

    name: str
    description: str
    required_categories: List[str] = field(default_factory=list)
    params_schema: List[Dict[str, Any]] = field(default_factory=list)
    # Whether the sequence is generally safe to run while a real test is
    # active (most aren't — they reset cells, query power, etc.).
    safe_during_test: bool = False


@dataclass
class SequenceStepResult:
    """One step in the run output. Sequences append these as they go."""

    label: str
    success: bool
    detail: str = ""
    duration_ms: Optional[int] = None


@dataclass
class SequenceRunResult:
    """Returned by sequence `run` functions."""

    success: bool
    summary: str
    steps: List[SequenceStepResult] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


# Sequence run signature. `log` lets the sequence emit human messages that
# show up in the GUI live console + in diagnostic_runs.output_excerpt.
SequenceRunFn = Callable[..., Awaitable[SequenceRunResult]]


class SequenceModule(Protocol):
    """Static type for what `loader.list_sequences()` returns."""

    metadata: SequenceMetadata
    run: SequenceRunFn
