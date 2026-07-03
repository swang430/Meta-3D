"""Shared PyVISA conn-lost classifier for the silent-reconnect pattern.

PR #14 added transparent silent reconnect to the Aerotech driver (raw
asyncio socket). PR #15 brings the equivalent pattern to PyVISA-backed
drivers (F64, FS16, UXM in this rollout — ENA waits for evidence).

The retry loop itself stays in-driver because each driver owns its own
PyVISA resource string + open kwargs + timeout-context bookkeeping;
factoring only the classifier (which is a constant lookup) is the
sweet spot for code reuse without forcing every driver into the same
retry mould.

The same Codex P2 lesson from #14 applies here:
  - ``VI_ERROR_CONN_LOST`` (0xBFFF00B5) → socket dropped, retry.
  - ``VI_ERROR_INV_OBJECT`` (0xBFFF000E) → session handle dead, retry.
  - ``VI_ERROR_TMO`` (0xBFFF0015) → device too slow, NOT a socket drop;
    must propagate so the caller can decide.

Adding new conn-lost codes here is a one-line change that automatically
covers every driver using ``is_visa_conn_lost``.
"""
from __future__ import annotations

# VPP-4.3 (VISA Library Specification) status codes.
_CONN_LOST_CODES = frozenset({
    0xBFFF00B5,  # VI_ERROR_CONN_LOST
    0xBFFF000E,  # VI_ERROR_INV_OBJECT
})


def is_visa_conn_lost(exc: BaseException) -> bool:
    """Tell apart 'controller dropped the socket' from every other
    VisaIOError (timeout / parse / device-state).

    Returns False if PyVISA isn't importable in this environment (e.g.
    Mock-only test mode) so callers don't have to guard the import.
    """
    try:
        import pyvisa
    except ImportError:
        return False
    if not isinstance(exc, pyvisa.errors.VisaIOError):
        return False
    code = getattr(exc, "error_code", None)
    if code is None:
        return False
    # error_code on Windows can be the signed-32 form; normalise to
    # unsigned for comparison against the spec hex constants.
    return (code & 0xFFFFFFFF) in _CONN_LOST_CODES


def is_visa_timeout(exc: BaseException) -> bool:
    """VI_ERROR_TMO (0xBFFF0015) — device 没在窗口内应答。P1-21 ②: 这类
    错误后会话可能残留迟到应答 (下一条 query 会读错位), 调用方应做轻量
    排水 (SYST:ERR? 循环) 而不是直接重载。与 conn-lost 互斥分类。"""
    try:
        import pyvisa
    except ImportError:
        return False
    if not isinstance(exc, pyvisa.errors.VisaIOError):
        return False
    code = getattr(exc, "error_code", None)
    if code is None:
        return False
    return (code & 0xFFFFFFFF) == 0xBFFF0015  # VI_ERROR_TMO
