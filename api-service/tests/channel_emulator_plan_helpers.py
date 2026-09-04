"""测试专用的 execution-frozen ChannelEmulatorExecutionPlan 构造器。"""

from app.hal.channel_emulator_execution_plan import (
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import channel_emulator_manifest_for


RUNTIME_MEASURE_OPERATIONS = (
    "ensure_topology",
    "get_center_frequency_mhz",
    "set_output_gain",
    "set_output_level_dbm",
    "set_crest_factor",
    "measure_input",
    "autoset_inputs",
    "get_input_level_limits",
    "set_input_measurement_mode",
    "set_burst_trigger_level",
    "get_group_clipping",
    "get_system_status",
)


def runtime_measure_plan(*, implemented=RUNTIME_MEASURE_OPERATIONS):
    """构造只供 helper 单测使用的冻结计划，不从测试替身运行时反推能力。"""

    manifest = channel_emulator_manifest_for(
        adapter_id="runtime_measure_test",
        model_name="Runtime Measure Test",
        vendor="test",
        implemented=tuple(implemented),
    )
    return resolve_channel_emulator_execution_plan(
        manifest=manifest,
        driver_source="hal",
        requested_load_mode="external_waveform",
        binding_digest="t" * 64,
    )
