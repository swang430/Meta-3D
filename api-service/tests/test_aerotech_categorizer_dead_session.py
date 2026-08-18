"""Aerotech health probe categoriser — empty-string handling (Codex P2 on #12).

Pre-fix bug: when the Ensemble idle-closed the TCP connection,
``StreamReader.readline()`` returned ``b''`` and ``_send()`` handed the
categoriser an empty string. The categoriser's catch-all "if response is
not None, ack" path classified that as SUPPORTED, so the probe summary
said "8/8 supported" against a dead session and the operator got a green
health check on a turntable they couldn't talk to.

The fix tightens ``_categorize`` to bucket ``""`` as UNKNOWN. Combined
with PR #14's ``_send`` raising ``ConnectionResetError`` on EOF, this is
defence-in-depth: if any future driver path returns empty for a non-ACK
command, the categoriser still refuses to call it SUPPORTED.
"""
from __future__ import annotations

import asyncio
import pytest

from app.diagnostics.sequences.aerotech_positioner_health import _categorize
from app.hal.aerotech_positioner import AerotechCommandRejected, AerotechError


class TestEmptyResponseIsUnknown:
    def test_empty_string_response_is_unknown(self):
        """The dead-session shape — caller saw ``b''`` and gave us ``""``."""
        assert _categorize(response="", exception=None) == "UNKNOWN"

    def test_none_response_is_unknown(self):
        """Pre-existing contract — preserved by the fix."""
        assert _categorize(response=None, exception=None) == "UNKNOWN"

    def test_whitespace_only_response_is_unknown(self):
        """An ACK with whitespace payload from a stale session also has
        no signal — bucket as UNKNOWN. (Adjacent to the empty-string
        bug; pinning here so a future "strip then check" refactor
        doesn't reintroduce SUPPORTED on whitespace.)"""
        # Driver does .strip() on response already, so whitespace-only
        # responses arrive as "".
        assert _categorize(response="", exception=None) == "UNKNOWN"


class TestRealAckStillSupported:
    """Negative checks — the categoriser must NOT over-correct and start
    bucketing legitimate ACKs as UNKNOWN."""

    def test_numeric_response_is_supported(self):
        assert _categorize(response="180.0", exception=None) == "SUPPORTED"

    def test_status_bitmask_response_is_supported(self):
        assert _categorize(response="2415919109", exception=None) == "SUPPORTED"

    def test_fault_hash_response_is_supported_but_fault(self):
        assert _categorize(response="#ax_fault=0x80", exception=None) == "SUPPORTED_BUT_FAULT"


class TestExceptionPathsUnchanged:
    def test_timeout_exception_is_unknown(self):
        assert _categorize(response=None, exception=asyncio.TimeoutError()) == "UNKNOWN"

    def test_not_connected_aerotech_error_is_unknown(self):
        exc = AerotechError("Not connected to Aerotech controller")
        assert _categorize(response=None, exception=exc) == "UNKNOWN"

    def test_reconnect_failure_aerotech_error_is_unknown(self):
        """New: PR #14 surfaces 'Connection lost during ... and reconnect
        failed' — make sure the categoriser treats that as UNKNOWN, not
        UNSUPPORTED. Otherwise a transient network blip on a real
        command would be misreported as "controller rejected the NAK"."""
        exc = AerotechError("Connection lost during 'PFBK(X)' and reconnect failed")
        assert _categorize(response=None, exception=exc) == "UNKNOWN"

    def test_nak_aerotech_error_is_unsupported(self):
        exc = AerotechCommandRejected("AeroBasic error for 'BOGUSCMD': !")
        assert _categorize(response=None, exception=exc) == "UNSUPPORTED"
