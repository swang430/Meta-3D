"""P2-52/U-13：没有 IRAT 厂商依据时禁止真实窗口写诊断。"""

from app.diagnostics import loader
from app.hal.uxm_command_profiles import UxmLteNrIratProfile


def test_irat_profile_does_not_expose_unsourced_native_window_writes():
    assert not hasattr(UxmLteNrIratProfile, "MEAS_BTHROUGHPUT_LENGTH_ALL")
    assert not hasattr(UxmLteNrIratProfile, "MEAS_BTHROUGHPUT_CONTINUOUS_ALL")


def test_unsafe_native_window_writer_is_not_registered():
    loader.reset_cache()
    keys = {item["key"] for item in loader.list_sequences()}
    assert "uxm_native_window_truth" not in keys
