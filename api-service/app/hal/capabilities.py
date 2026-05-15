"""Centralised driver-capability vocabulary (P2-2).

# Why this module exists

Before P2-2, "what does this driver expose right now" was scattered across
boolean attributes on each driver class:

  - ``RealPropsimF64Driver.has_interference_generator``  (Optional[bool])
  - ``RealAerotechDriver.is_single_axis``               (bool, derived)
  - ``DriverBase._installed_options``                   (List[str], unused)

Each new capability flag added another ad-hoc attribute, and consumers
that needed to gate behaviour on capabilities had to know the exact
attribute name on each driver. That ad-hoc surface is what blocks P1-1
(plan-level pre-flight) — a step template can't say "this needs an
interference generator" without conditional branches per driver type.

This module defines a **single token vocabulary**. Each driver populates
``DriverBase.capabilities: Set[str]`` during ``connect()`` / probe
sequences using these canonical tokens. Consumers read the set; the
legacy boolean attributes remain as backwards-compat aliases so existing
tests + call sites keep working, but new code reads from the set.

# Token naming convention

  ``{category-prefix}.{capability-name}``

  - ``ce.*``    — channel emulator (PROPSIM F64, FS16, future…)
  - ``bs.*``    — base station emulator (UXM, CMW500, …)
  - ``pos.*``   — positioner / turntable (Aerotech, ETS-Lindgren, …)
  - ``vna.*``   — vector network analyzer
  - ``sa.*``    — signal analyzer
  - ``sg.*``    — signal generator

Token names are lower_snake_case after the prefix. Dot separates only the
namespace from the capability — no nested dots.

# How to add a new token

  1. Add a line in ``KNOWN_CAPABILITIES`` below with a docstring-style
     comment naming WHAT the token means.
  2. Have whichever driver detects the capability call
     ``self._add_capability("<token>")`` in its connect/probe path.
  3. (P1-1) declare ``needs: ["<token>"]`` on the step templates that
     require it.

Don't add tokens speculatively — only when a real driver populates one
AND a real consumer reads one. Drift between "documented tokens" and
"actually-set tokens" is exactly what the centralisation is here to
prevent.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical capability vocabulary
# ---------------------------------------------------------------------------
#
# Frozen on purpose: an unknown token added at runtime is almost always a
# typo or a forgotten registration here. `DriverBase._add_capability` warns
# loudly when called with a non-canonical token rather than silently
# accepting it.

# Channel emulator
CE_INTERFERENCE_GENERATOR = "ce.interference_generator"
"""F64 K01 / equivalent — driver can emit an internal interference tone
suitable for the CE+SA path-loss calibration loop."""

CE_USER_ALIGNMENT = "ce.user_alignment"
"""F64 / equivalent — driver currently has an active user alignment
loaded (Integrated Setup Calibration, the per-deployment cal table
that rides on top of factory cal). Runtime state: set after a
successful ``SYST:CALIB:USER:SET 1,<name>`` handshake on connect,
cleared when ``_active_alignment`` goes None. Reflects whether the
F64 will actually USE per-deployment cal at run time, not just
whether the feature is licensed."""

# Positioner
POS_SINGLE_AXIS_AZ = "pos.single_axis_az"
"""Positioner has azimuth only (no elevation axis). Aerotech single-axis
turntables hit this; chamber commissioning that requires elevation
sweeps must check for the absence of this token + presence of
``pos.dual_axis_azel``."""

POS_DUAL_AXIS_AZEL = "pos.dual_axis_azel"
"""Positioner has both azimuth and elevation axes. Default for full
MPAC chamber turntables."""


KNOWN_CAPABILITIES: frozenset[str] = frozenset({
    CE_INTERFERENCE_GENERATOR,
    CE_USER_ALIGNMENT,
    POS_SINGLE_AXIS_AZ,
    POS_DUAL_AXIS_AZEL,
})
