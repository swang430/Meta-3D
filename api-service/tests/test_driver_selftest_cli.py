"""P3-2 — `python -m scripts.driver_selftest` CLI contract.

Pins both the pure report builder and the renderers so a future
refactor of the HAL surface can't silently break the on-site
debugging tool. Tests don't initialise a real HAL — they construct
stand-in driver objects whose shape mirrors the post-P2-2 /
post-P2-3 contract (live ``capabilities`` set + class-level
``model_capabilities`` ClassVar), then call ``build_report``
directly.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Set

import pytest

from scripts.driver_selftest import (
    DriverReport,
    SelftestReport,
    build_report,
    render_json,
    render_markdown,
    render_text,
)


def _stub_driver(
    *,
    cls_name: str,
    model_capabilities: frozenset = frozenset(),
    live_capabilities: Set[str] | None = None,
    endpoint: str | None = None,
    ip: str | None = None,
    port: int | None = None,
    status: str = "connected",
    last_error: str | None = None,
) -> SimpleNamespace:
    """Build a stand-in driver. We use SimpleNamespace + a dynamic
    type for the class name so the report builder sees what it'd see
    from a real driver: ``type(driver).__name__`` + class-level
    ``model_capabilities`` + instance-level ``capabilities`` /
    ``config`` / ``status`` / ``last_error``.

    Status is passed as the string the InstrumentStatus.value would
    yield post-rendering, since the report builder accepts either
    enum-with-.value or plain string."""
    cls = type(cls_name, (), {"model_capabilities": model_capabilities})
    driver = cls()
    driver.capabilities = set(live_capabilities) if live_capabilities else set()
    cfg = {}
    if endpoint:
        cfg["endpoint"] = endpoint
    if ip:
        cfg["ip"] = ip
    if port:
        cfg["port"] = port
    driver.config = cfg
    driver.status = SimpleNamespace(value=status)
    driver.last_error = last_error
    return driver


class _StubHal:
    def __init__(self, drivers):
        self.drivers = drivers


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

class TestBuildReport:
    def test_empty_hal_yields_zero_drivers(self):
        report = build_report(_StubHal({}), mode_label="mock")
        assert report.drivers_loaded == 0
        assert report.drivers == []
        assert report.init_error is None

    def test_single_driver_shape(self):
        d = _stub_driver(
            cls_name="RealPropsimF64Driver",
            model_capabilities=frozenset({
                "ce.interference_generator", "ce.user_alignment",
            }),
            live_capabilities={"ce.interference_generator"},
            ip="192.168.0.132",
            port=5025,
        )
        report = build_report(
            _StubHal({"channelEmulator": d}), mode_label="real",
        )
        assert report.drivers_loaded == 1
        d_rep = report.drivers[0]
        assert d_rep.category == "channelEmulator"
        assert d_rep.driver_class == "RealPropsimF64Driver"
        assert d_rep.is_mock is False
        assert d_rep.endpoint_display == "192.168.0.132:5025"
        assert d_rep.status == "connected"
        # Capability surfaces — both sets present + sorted + diffs computed.
        assert d_rep.live_capabilities == ["ce.interference_generator"]
        assert d_rep.model_capabilities == [
            "ce.interference_generator", "ce.user_alignment",
        ]
        # Declared - live: tokens the model claims but driver hasn't probed.
        assert d_rep.declared_but_not_live == ["ce.user_alignment"]
        # Live - declared: should be empty (P2-3 invariant).
        assert d_rep.live_but_not_declared == []

    def test_invariant_breach_surfaces(self):
        """If a driver registers a live token its model doesn't
        declare, the report calls it out — this is a vocabulary drift
        signal even if it's harmless at runtime."""
        d = _stub_driver(
            cls_name="WeirdDriver",
            model_capabilities=frozenset({"ce.interference_generator"}),
            live_capabilities={"ce.interference_generator", "ce.unknown_token"},
        )
        rep = build_report(_StubHal({"x": d}), mode_label="mock").drivers[0]
        assert rep.live_but_not_declared == ["ce.unknown_token"]

    def test_mock_drivers_flagged(self):
        d = _stub_driver(cls_name="MockChannelEmulator")
        rep = build_report(_StubHal({"x": d}), mode_label="mock").drivers[0]
        assert rep.is_mock is True

    def test_endpoint_prefers_ip_port_over_visa_string(self):
        """Operator-readable form: ip:port beats TCPIP0::host::port::INSTR
        when both are in config (HAL factory sets both)."""
        d = _stub_driver(
            cls_name="X",
            endpoint="TCPIP0::192.168.0.132::5025::INSTR",
            ip="192.168.0.132",
            port=5025,
        )
        rep = build_report(_StubHal({"x": d}), mode_label="mock").drivers[0]
        assert rep.endpoint_display == "192.168.0.132:5025"

    def test_endpoint_falls_back_to_raw_visa(self):
        """When parsed ip/port aliases aren't set (older drivers), the
        raw endpoint string is still shown rather than rendering empty."""
        d = _stub_driver(
            cls_name="X",
            endpoint="TCPIP0::192.168.0.132::5025::INSTR",
        )
        rep = build_report(_StubHal({"x": d}), mode_label="mock").drivers[0]
        assert rep.endpoint_display == "TCPIP0::192.168.0.132::5025::INSTR"

    def test_drivers_sorted_by_category(self):
        """Stable rendering across runs — categories sorted
        alphabetically rather than HAL-load order."""
        hal = _StubHal({
            "positioner": _stub_driver(cls_name="X"),
            "channelEmulator": _stub_driver(cls_name="Y"),
            "baseStation": _stub_driver(cls_name="Z"),
        })
        report = build_report(hal, mode_label="mock")
        cats = [d.category for d in report.drivers]
        assert cats == sorted(cats)
        assert cats == ["baseStation", "channelEmulator", "positioner"]


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------

class TestJsonRenderer:
    def test_output_is_valid_json(self):
        report = build_report(
            _StubHal({"x": _stub_driver(cls_name="MockChannelEmulator")}),
            mode_label="mock",
        )
        parsed = json.loads(render_json(report))
        assert parsed["hal_mode"] == "mock"
        assert parsed["drivers_loaded"] == 1
        assert parsed["drivers"][0]["driver_class"] == "MockChannelEmulator"

    def test_json_preserves_capability_lists(self):
        report = build_report(
            _StubHal({"x": _stub_driver(
                cls_name="X",
                model_capabilities=frozenset({"ce.user_alignment"}),
                live_capabilities={"ce.user_alignment"},
            )}),
            mode_label="mock",
        )
        parsed = json.loads(render_json(report))
        d = parsed["drivers"][0]
        assert d["live_capabilities"] == ["ce.user_alignment"]
        assert d["model_capabilities"] == ["ce.user_alignment"]
        assert d["declared_but_not_live"] == []
        assert d["live_but_not_declared"] == []


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------

class TestTextRenderer:
    def test_empty_report_says_so(self):
        report = build_report(_StubHal({}), mode_label="mock")
        out = render_text(report)
        assert "Drivers loaded: 0" in out
        assert "(no drivers loaded)" in out

    def test_includes_capability_diff_when_present(self):
        report = build_report(
            _StubHal({"channelEmulator": _stub_driver(
                cls_name="RealPropsimF64Driver",
                model_capabilities=frozenset({
                    "ce.interference_generator", "ce.user_alignment",
                }),
                live_capabilities={"ce.interference_generator"},
            )}),
            mode_label="real",
        )
        out = render_text(report)
        assert "declared but not live: ce.user_alignment" in out

    def test_invariant_breach_calls_out_loudly(self):
        report = build_report(
            _StubHal({"x": _stub_driver(
                cls_name="X",
                model_capabilities=frozenset(),
                live_capabilities={"ce.interference_generator"},
            )}),
            mode_label="mock",
        )
        out = render_text(report)
        assert "INVARIANT BREACH" in out
        assert "ce.interference_generator" in out

    def test_mock_tag_visible(self):
        report = build_report(
            _StubHal({"x": _stub_driver(cls_name="MockChannelEmulator")}),
            mode_label="mock",
        )
        out = render_text(report)
        assert "[MOCK]" in out


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

class TestMarkdownRenderer:
    def test_includes_table_header(self):
        report = build_report(_StubHal({}), mode_label="mock")
        out = render_markdown(report)
        # Empty report doesn't include the table — only the heading.
        assert out.startswith("# Driver self-test")
        assert "_(no drivers loaded)_" in out

    def test_table_row_per_driver(self):
        report = build_report(
            _StubHal({
                "channelEmulator": _stub_driver(
                    cls_name="RealPropsimF64Driver",
                    model_capabilities=frozenset({"ce.interference_generator"}),
                    live_capabilities={"ce.interference_generator"},
                    ip="1.2.3.4", port=5025,
                ),
            }),
            mode_label="real",
        )
        out = render_markdown(report)
        # Header + separator + 1 row
        assert "| Category | Driver class | Endpoint" in out
        assert "| `channelEmulator` |" in out
        assert "`RealPropsimF64Driver`" in out
        assert "1.2.3.4:5025" in out

    def test_issues_section_when_diffs_present(self):
        report = build_report(
            _StubHal({"x": _stub_driver(
                cls_name="X",
                model_capabilities=frozenset({"ce.user_alignment"}),
                live_capabilities=set(),
            )}),
            mode_label="real",
        )
        out = render_markdown(report)
        assert "## Issues" in out
        assert "declared but not live" in out


# ---------------------------------------------------------------------------
# main() — exit codes + end-to-end
# ---------------------------------------------------------------------------

class TestMainExitCodes:
    """Drive the CLI end-to-end against a mocked HAL so we can pin
    exit-code semantics without touching real hardware."""

    def test_zero_drivers_returns_exit_2(self, monkeypatch, capsys):
        """0 drivers loaded should NOT report success — operator
        needs to see something's wrong with their catalog."""
        import scripts.driver_selftest as mod

        async def _stub_run(mode, category_filter):
            return SelftestReport(
                timestamp="2026-05-17T00:00:00+00:00",
                hal_mode=mode, drivers_loaded=0,
            )

        monkeypatch.setattr(mod, "_run", _stub_run)
        rc = mod.main(["--format", "json"])
        assert rc == 2

    def test_init_error_returns_exit_1(self, monkeypatch, capsys):
        import scripts.driver_selftest as mod

        async def _stub_run(mode, category_filter):
            return SelftestReport(
                timestamp="2026-05-17T00:00:00+00:00",
                hal_mode=mode, drivers_loaded=0,
                init_error="ConnectionError: blah",
            )

        monkeypatch.setattr(mod, "_run", _stub_run)
        rc = mod.main(["--format", "json"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "ConnectionError" in out

    def test_success_returns_exit_0(self, monkeypatch, capsys):
        import scripts.driver_selftest as mod

        async def _stub_run(mode, category_filter):
            return SelftestReport(
                timestamp="2026-05-17T00:00:00+00:00",
                hal_mode=mode, drivers_loaded=1,
                drivers=[DriverReport(
                    category="channelEmulator",
                    driver_class="RealPropsimF64Driver",
                    is_mock=False,
                    endpoint_display="192.168.0.132:5025",
                    status="connected",
                    last_error=None,
                    live_capabilities=["ce.interference_generator"],
                    model_capabilities=[
                        "ce.interference_generator", "ce.user_alignment",
                    ],
                    declared_but_not_live=["ce.user_alignment"],
                    live_but_not_declared=[],
                )],
            )

        monkeypatch.setattr(mod, "_run", _stub_run)
        rc = mod.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "RealPropsimF64Driver" in out
        assert "declared but not live" in out

    def test_category_filter_passed_through(self, monkeypatch):
        import scripts.driver_selftest as mod
        captured = {}

        async def _stub_run(mode, category_filter):
            captured["mode"] = mode
            captured["category"] = category_filter
            return SelftestReport(
                timestamp="t", hal_mode=mode, drivers_loaded=1,
                drivers=[DriverReport(
                    category="x", driver_class="X", is_mock=True,
                    endpoint_display=None, status="connected",
                    last_error=None, live_capabilities=[],
                    model_capabilities=[],
                    declared_but_not_live=[], live_but_not_declared=[],
                )],
            )

        monkeypatch.setattr(mod, "_run", _stub_run)
        mod.main(["--mode", "real", "--category", "channelEmulator"])
        assert captured == {"mode": "real", "category": "channelEmulator"}

    def test_default_mode_maps_to_mock_force(self, monkeypatch):
        """Codex P1 on PR #30: ``--mode mock`` (default) must map to
        ``DriverMode.MOCK_FORCE`` not ``DriverMode.MOCK``, otherwise
        per-instrument ``driver_mode='real'`` bindings still open
        real TCP/VISA. Pin the mapping so a future refactor of
        ``_run`` can't silently regress the safety guarantee."""
        import scripts.driver_selftest as mod
        from app.services.instrument_hal_service import DriverMode

        captured = {}

        async def _stub_initialize(mode):
            captured["mode"] = mode

        async def _stub_shutdown():
            pass

        class _StubHal:
            drivers: dict = {}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.initialize_hal_service",
            _stub_initialize,
        )
        monkeypatch.setattr(
            "app.services.instrument_hal_service.shutdown_hal_service",
            _stub_shutdown,
        )
        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: _StubHal(),
        )

        # No --mode arg → default 'mock' → must hit MOCK_FORCE.
        mod.main([])
        assert captured["mode"] == DriverMode.MOCK_FORCE

        # Explicit --mode real → DriverMode.REAL (unchanged path).
        mod.main(["--mode", "real"])
        assert captured["mode"] == DriverMode.REAL

    @pytest.mark.parametrize("fmt", ["text", "json", "md"])
    def test_format_choice_round_trips(self, monkeypatch, capsys, fmt):
        import scripts.driver_selftest as mod

        async def _stub_run(mode, category_filter):
            return SelftestReport(
                timestamp="2026-05-17T00:00:00+00:00",
                hal_mode=mode, drivers_loaded=1,
                drivers=[DriverReport(
                    category="x", driver_class="MockX", is_mock=True,
                    endpoint_display="1.2.3.4:5025", status="connected",
                    last_error=None,
                    live_capabilities=["t.one"], model_capabilities=["t.one"],
                    declared_but_not_live=[], live_but_not_declared=[],
                )],
            )

        monkeypatch.setattr(mod, "_run", _stub_run)
        mod.main(["--format", fmt])
        out = capsys.readouterr().out
        # Format-specific shape sanity check.
        if fmt == "json":
            parsed = json.loads(out)
            assert parsed["drivers_loaded"] == 1
        elif fmt == "md":
            assert out.lstrip().startswith("#")
        else:  # text
            assert "Driver self-test" in out
