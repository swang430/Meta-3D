"""P2-46 production gates for one static BaseStation capability truth."""

import ast
from pathlib import Path

from app.hal.base_station import BaseStationDriver
from app.hal.base_station_manifest import (
    validate_base_station_adapter_registrations,
)
from app.services.instrument_hal_service import (
    _real_driver_registry,
    get_base_station_adapter_registration,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_registered_real_adapters_only_use_manifest_derived_rat_support():
    registrations = {
        model_name: get_base_station_adapter_registration(model_name)
        for model_name in _real_driver_registry()["baseStation"]
    }

    validate_base_station_adapter_registrations(registrations)
    assert registrations
    for registration in registrations.values():
        assert registration.manifest.schema_version == 2
        assert (
            registration.driver_class.get_supported_technologies
            is BaseStationDriver.get_supported_technologies
        )


def test_generic_gui_projection_has_no_vendor_identity_or_profile_version_split():
    source = (REPO_ROOT / "gui/src/types/baseStationManifest.ts").read_text()

    assert "manifest.profile_schema_version" in source
    assert "envelope.schema_version !== manifest.schema_version" not in source
    assert "schema_version: manifest.schema_version" not in source
    assert "cmw500" not in source.lower()
    assert "uxm" not in source.lower()


def test_measure_orchestration_has_no_adapter_identity_capability_branch():
    path = REPO_ROOT / "api-service/app/services/mimo_ota/executors/measure.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    forbidden = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        names = {
            operand.attr
            for operand in operands
            if isinstance(operand, ast.Attribute)
        } | {
            operand.id
            for operand in operands
            if isinstance(operand, ast.Name)
        }
        values = {
            operand.value.lower()
            for operand in operands
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str)
        }
        if names & {"adapter_id", "model", "model_name"} and values & {
            "cmw500",
            "uxm",
            "uxm 5g e7515b",
        }:
            forbidden.append(node.lineno)

    assert forbidden == []


def test_roadmap_keeps_p2_46_merged_truth_after_queue_advances():
    roadmap = (REPO_ROOT / "docs/roadmap-first-call.md").read_text()

    assert "P2-46 已由 PR #412 以 merge commit" in roadmap
    assert "P2-46/P2-47/P2-48 已分别由 PR #412/#413/#414" in roadmap
    assert "P2-44（Ready PR 后续 P1-only 外审中）" not in roadmap
