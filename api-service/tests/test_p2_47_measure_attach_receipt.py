"""P2-47 production MEASURE consumes the structured attach receipt."""

from __future__ import annotations

import inspect

from app.services.mimo_ota.executors.measure import MeasureExecutor


def test_measure_persists_attach_receipt_before_deciding_whether_to_continue():
    source = inspect.getsource(MeasureExecutor.execute)

    attach = source.index("attach_receipt = await base_station.attach()")
    persist = source.index("confirm_base_station_attach(", attach)
    decide = source.index("attach_receipt.diagnostic_execution_allowed", persist)

    assert attach < persist < decide
    assert "await base_station.start_signaling()" not in source
    assert "manifest=execution_manifest" in source[persist:decide]
    assert "receipt=attach_receipt" in source[persist:decide]


def test_measure_failure_exposes_terminal_stage_and_evidence_without_bool_reduction():
    source = inspect.getsource(MeasureExecutor.execute)

    assert "attach_receipt.terminal_stage" in source
    assert "attach_receipt.terminal_stage_receipt" in source
    assert "terminal_attach_stage.evidence" in source
    assert "if not attach_receipt:" not in source
    assert "signaling_started" not in source


def test_live_attach_milestones_publish_stage_truth_and_keep_rrc_as_compatibility():
    source = inspect.getsource(MeasureExecutor.execute)

    assert '"stage_truth": stage_truth' in source
    assert '"attach_stage_truth": final_attach.get("stage_truth")' in source
    assert '"rrc_connected": final_attach.get("attached")' in source
    assert "manifest_stages = tuple(attach_receipt.stages)" in source
