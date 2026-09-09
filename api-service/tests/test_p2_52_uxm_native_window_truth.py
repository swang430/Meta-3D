"""P2-52/U-13：没有 IRAT 厂商依据时禁止真实窗口写诊断。"""

from pathlib import Path

from app.diagnostics import loader
from app.hal.uxm_command_profiles import UxmLteNrIratProfile


def test_irat_profile_does_not_expose_unsourced_native_window_writes():
    assert not hasattr(UxmLteNrIratProfile, "MEAS_BTHROUGHPUT_LENGTH_ALL")
    assert not hasattr(UxmLteNrIratProfile, "MEAS_BTHROUGHPUT_CONTINUOUS_ALL")


def test_unsafe_native_window_writer_is_not_registered():
    loader.reset_cache()
    keys = {item["key"] for item in loader.list_sequences()}
    assert "uxm_native_window_truth" not in keys


def test_detailed_roadmap_requires_vendor_evidence_before_any_irat_write_probe():
    roadmap = (
        Path(__file__).resolve().parents[2] / "docs/roadmap-first-call.md"
    ).read_text(encoding="utf-8")
    section = roadmap.split(
        "### P2-52 — UXM 权威测量窗口关闭边界", 1
    )[1].split("### P2-53", 1)[0]

    assert "先取得可审计的 LTE_NR_IRAT 厂商资料" in section
    assert "不得通过执行或人工试写" in section
    assert "均须在同一冻结 execution/attempt 内取证" not in section
    assert "出发前还须补齐受控载体" not in section
