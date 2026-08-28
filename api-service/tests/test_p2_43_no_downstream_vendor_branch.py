"""P2-43：正式消费者不得按 BaseStation 厂商选择行为。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


API_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CONSUMERS = (
    "app/services/mimo_ota/executors/measure.py",
    "app/services/mimo_ota/executors/analysis.py",
    "app/services/mimo_ota/executors/report.py",
    "app/services/report_service.py",
    "app/api/commissioning.py",
)
BASE_STATION_VENDOR_IDS = {"uxm", "cmw500"}


def _vendor_literals(node: ast.AST) -> set[str]:
    return {
        child.value.lower()
        for child in ast.walk(node)
        if isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and child.value.lower() in BASE_STATION_VENDOR_IDS
    }


def _downstream_vendor_branches(source: str) -> list[tuple[int, tuple[str, ...]]]:
    tree = ast.parse(source)
    branches: list[tuple[int, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        vendors = tuple(sorted(_vendor_literals(node)))
        if vendors:
            branches.append((node.lineno, vendors))
    return branches


def test_detector_finds_only_vendor_literals_in_branch_predicates():
    source = """
requires_evidence = adapter_id == "cmw500"
label = "UXM"  # display text is not a behavior branch
if receipt.confirmed:
    use_common_path()
"""

    assert _downstream_vendor_branches(source) == [(2, ("cmw500",))]


@pytest.mark.parametrize("relative_path", PRODUCTION_CONSUMERS)
def test_base_station_production_consumers_have_no_vendor_branch(relative_path):
    path = API_ROOT / relative_path

    assert _downstream_vendor_branches(path.read_text(encoding="utf-8")) == []
