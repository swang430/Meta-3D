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


def driver_not_loaded_summary(category: str) -> str:
    """Actionable summary for the common "sequence needs a loaded driver but
    none is present" failure.

    A driver is only in ``hal.drivers`` after a SUCCESSFUL connect — setting a
    category to ``real`` just means "attempt a real connection", not that it
    succeeded. These signaling/SCPI sequences need a *connected* instrument, so
    when the driver didn't load they can't run. The terse old message
    ("No X driver loaded — check HAL init") left the operator stuck; point them
    at the lower-level connectivity tools that DON'T need a loaded driver."""
    return (
        f"未加载 {category} 驱动：real 模式下该仪表连接失败/未连接（驱动仅在 "
        f"connect 成功后才进 HAL）。本探针需要已连接的 {category}。"
        f"先用「SCPI 探测 / 连接测试」(/instruments/{category}/scpi-probe · "
        f"test-connection，自开 socket、无需已加载驱动) 或看主控台「系统就绪」的 "
        f"{category} 行排查连通性（网络不可达 vs SCPI 无响应）；连上后重跑本序列。"
    )


def mock_driver_refusal_summary(category: str, driver: Any) -> Optional[str]:
    """If ``driver`` is a mock, return an actionable refusal summary for a
    hardware health/identity probe; otherwise ``None``.

    Hardware probes (IDN/SYST:INFO identity checks, SCPI-command sweeps, DUT
    signaling) are meaningless against a mock: the mock returns canned/empty
    values, so the probe either silently "passes" (useless) or fails with a
    cryptic message (e.g. ``Identity check failed: IDN=''`` against
    MockChannelEmulator). Caller short-circuits with this summary so the
    operator gets "this probe needs real hardware" instead. Mirrors the gate
    aerotech_positioner_health + the SCPI Console already use (name-based, so a
    driver class outside the Mock* family is treated as real)."""
    cls_name = type(driver).__name__
    if cls_name.startswith("Mock"):
        return (
            f"{category} 当前是 mock 驱动（{cls_name}，HAL 在 mock 模式）。本探针针对"
            f"真实硬件（*IDN?/SYST:INFO?/信令 校验），对 mock 无意义（mock 返回空/占位值）。"
            f"切到 real 模式并连接真实 {category} 后再跑本序列。"
        )
    return None


# Sequence run signature. `log` lets the sequence emit human messages that
# show up in the GUI live console + in diagnostic_runs.output_excerpt.
SequenceRunFn = Callable[..., Awaitable[SequenceRunResult]]


class SequenceModule(Protocol):
    """Static type for what `loader.list_sequences()` returns."""

    metadata: SequenceMetadata
    run: SequenceRunFn
