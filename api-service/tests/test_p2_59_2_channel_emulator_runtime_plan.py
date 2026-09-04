"""P2-59②：MEASURE 不再靠 F64 对象形状猜能力。"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.channel_emulator import ChannelEmulatorDriver, MockChannelEmulator
from app.hal.channel_emulator_manifest import (
    CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS,
    CHANNEL_EMULATOR_OPERATIONS,
    ChannelEmulatorManifest,
)
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.propsim_fs16 import RealPropsimFs16Driver
from app.services.channel_emulator_binding import (
    ResolvedChannelEmulatorBinding,
    _validate_existing_channel_emulator_freeze,
)


_ROOT = Path(__file__).resolve().parents[1]
_MEASURE = _ROOT / "app/services/mimo_ota/executors/measure.py"

_P2_59_2_OPERATIONS = {
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
}


def _operation_map(driver_type: type) -> dict[str, object]:
    return {
        item.operation: item
        for item in driver_type.adapter_manifest.operations
    }


def test_new_instrument_operations_are_manifested_per_model() -> None:
    assert _P2_59_2_OPERATIONS <= set(CHANNEL_EMULATOR_OPERATIONS)

    f64 = _operation_map(RealPropsimF64Driver)
    fs16 = _operation_map(RealPropsimFs16Driver)
    mock = _operation_map(MockChannelEmulator)
    for operation in _P2_59_2_OPERATIONS:
        assert f64[operation].support == "implemented"
        assert f64[operation].source_reference
        assert "propsim_f64.py" in f64[operation].source_reference
        assert fs16[operation].support == "not_implemented"
        assert mock[operation].support == "not_implemented"


def test_manifest_v1_keeps_original_vocabulary_and_binding_digest() -> None:
    current = RealPropsimF64Driver.adapter_manifest.model_dump(mode="json")
    legacy_manifest = {
        **current,
        "schema_version": 1,
        "operations": [
            item
            for item in current["operations"]
            if item["operation"] in CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS
        ],
    }
    parsed = ChannelEmulatorManifest.model_validate(legacy_manifest)
    assert parsed.schema_version == 1
    assert tuple(item.operation for item in parsed.operations) == (
        CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS
    )
    resolved = ResolvedChannelEmulatorBinding.model_validate(
        {
            "schema_version": 1,
            "status": "configured",
            "execution_mode": "real",
            "category_id": "category-v1",
            "instrument_model_id": "model-v1",
            "instrument_connection_id": "connection-v1",
            "lab_profile_id": "lab-v1",
            "manifest": legacy_manifest,
            "expected_driver_module": "app.hal.propsim_f64",
            "expected_driver_name": "RealPropsimF64Driver",
            "expected_transport": {"host": "192.0.2.10", "port": 1234},
            "binding_digest": "b" * 64,
            "runtime_driver": {
                "driver_module": "app.hal.propsim_f64",
                "driver_name": "RealPropsimF64Driver",
                "adapter_id": "propsim_f64",
                "simulated": False,
                "transport": {"host": "192.0.2.10", "port": 1234},
            },
        }
    )
    assert resolved.manifest is not None
    assert resolved.manifest.schema_version == 1

    identity = {
        "schema_version": 1,
        "binding_digest": "b" * 64,
        "resolved_binding": {"manifest": legacy_manifest},
    }
    frozen = {**identity, "digest": canonical_payload_digest(identity)}
    assert _validate_existing_channel_emulator_freeze(frozen) is frozen


def test_f64_manifested_operations_have_concrete_implementations() -> None:
    for operation in _P2_59_2_OPERATIONS:
        assert operation in RealPropsimF64Driver.__dict__, operation


def test_runtime_protocol_is_explicit_on_all_production_drivers() -> None:
    protocol = {
        "build_p0_5_command_evidence",
        "get_loaded_emulation_file",
        "get_active_output_count",
        "get_active_input_count",
        "get_active_output_ports",
        "get_active_input_ports",
    }
    assert protocol <= set(ChannelEmulatorDriver.__dict__)
    for driver_type in (
        RealPropsimF64Driver,
        RealPropsimFs16Driver,
        MockChannelEmulator,
    ):
        assert protocol <= set(driver_type.__dict__), driver_type.__name__


def test_measure_has_no_channel_emulator_shape_or_private_state_probes() -> None:
    source = _MEASURE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_names = {
        "build_p0_5_command_evidence",
        "ensure_topology",
        "get_center_frequency_mhz",
        "set_output_gain",
        "set_output_level_dbm",
        "set_crest_factor",
        "measure_input",
        "get_active_input_ports",
    }
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id not in {
            "hasattr",
            "getattr",
        }:
            continue
        if len(node.args) < 2:
            continue
        owner, name = node.args[0], node.args[1]
        if not isinstance(owner, ast.Name) or owner.id != "emulator":
            continue
        if isinstance(name, ast.Constant) and name.value in forbidden_names:
            hits.append((node.lineno, str(name.value)))
        elif isinstance(name, ast.Name) and name.id == "getter_name":
            hits.append((node.lineno, "getter_name"))

    assert hits == []
    assert 'getattr(emulator, "_loaded_emulation_file"' not in source
    assert "_TOPOLOGY_ESCAPE_HINT" not in source
    assert "emulator.get_supported_load_modes()" not in source


def test_load_mode_strategies_do_not_query_live_driver_capability() -> None:
    from app.services.channel_generation import b2_parametric_strategy, gcm_strategy

    for module in (b2_parametric_strategy, gcm_strategy):
        source = inspect.getsource(module)
        assert ".get_supported_load_modes()" not in source
