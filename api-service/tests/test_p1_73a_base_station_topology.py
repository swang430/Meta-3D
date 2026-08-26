"""P1-73A Task 4A：MIMO OTA 拓扑只消费逻辑 BaseStation 端口。"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services.base_station_port_mapping import resolve_base_station_port_mapping
from app.services.mimo_ota.executors.measure import (
    MeasureExecutor,
    _resolve_base_station_route_snapshot,
)
from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology


def _template_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts/dev-fixtures/topology-templates/caict_v4.py"
    )
    spec = importlib.util.spec_from_file_location("p1_73a_caict_v4", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _logical_physical(mapping):
    return {port.logical_port: port.physical_port for port in mapping.ports}


def test_uxm_route_snapshot_preserves_normal_alternate_and_4x4_profiles():
    cases = (
        ("2x2", 2, {1: "RF1OUT", 2: "RF2OUT"}),
        ("2x2_alt", 2, {1: "RF3OUT", 2: "RF4OUT"}),
        (
            "4x4",
            4,
            {1: "RF1OUT", 2: "RF2OUT", 3: "RF3OUT", 4: "RF4OUT"},
        ),
    )
    for preset, layers, tx in cases:
        mapping = resolve_base_station_port_mapping(
            adapter_id="uxm",
            mimo_port_preset=preset,
            mimo_layers=layers,
            route_snapshot={"tx": tx, "ota_uplink": "RF6IN"},
        )
        expected = {f"DL{i}": tx[i] for i in range(1, layers + 1)}
        expected["UL1"] = "RF6IN"
        assert _logical_physical(mapping) == expected
        assert not mapping.warnings


def test_cmw_2x2_uses_driver_snapshot_without_guessing_front_panel_connectors():
    mapping = resolve_base_station_port_mapping(
        adapter_id="cmw500",
        mimo_port_preset="2x2",
        mimo_layers=2,
        route_snapshot={"tx": {1: "TX1", 2: "TX2"}, "ota_uplink": "RX"},
    )
    assert _logical_physical(mapping) == {"DL1": "TX1", "DL2": "TX2", "UL1": "RX"}
    assert not mapping.warnings


def test_missing_physical_route_is_warning_not_runtime_blocker():
    mapping = resolve_base_station_port_mapping(
        adapter_id="cmw500",
        mimo_port_preset="2x2",
        mimo_layers=2,
        route_snapshot=None,
    )
    assert [port.logical_port for port in mapping.ports] == ["DL1", "DL2", "UL1"]
    assert all(port.physical_port is None for port in mapping.ports)
    assert mapping.is_runtime_blocker is False
    assert mapping.warnings


def test_eight_layer_mapping_preserves_all_accepted_logical_ports():
    mapping = resolve_base_station_port_mapping(
        adapter_id="uxm",
        mimo_port_preset=None,
        mimo_layers=8,
        route_snapshot=None,
    )

    assert [port.logical_port for port in mapping.ports] == [
        "DL1", "DL2", "DL3", "DL4", "DL5", "DL6", "DL7", "DL8", "UL1"
    ]
    assert mapping.is_runtime_blocker is False
    assert len(mapping.warnings) == 9


def test_caict_template_migrates_only_mimo_connections_to_logical_base_station():
    topology = _template_module().generate_caict_mimo_topology()
    nodes = {node["id"]: node for node in topology["nodes"]}
    connections = {conn["id"]: conn for conn in topology["connections"]}

    assert nodes["baseStation"]["params"]["ports"] == [
        "DL1", "DL2", "DL3", "DL4", "UL1"
    ]
    for index in range(1, 5):
        conn = connections[f"conn_base_station_dl{index}_to_ce"]
        assert (conn["source"], conn["source_pin"]) == ("baseStation", f"DL{index}")
        assert (conn["target"], conn["target_pin"]) == ("ce_f64", f"in{index}")

    uplink = connections["conn_link_antenna_to_base_station_mimo"]
    assert (uplink["target"], uplink["target_pin"]) == ("baseStation", "UL1")

    # 非 MIMO 的物理 UXM / VNA 路径保持逐项不变。
    assert connections["conn_uxm_rf5_to_switch"]["source_pin"] == "RF5"
    assert connections["conn_link_antenna_to_uxm_trp"]["target_pin"] == "RF6"
    assert connections["conn_vna_p1_to_switch"]["source_pin"] == "Port1"
    assert connections["conn_vna_p2_to_sgh"]["source_pin"] == "Port2"


def test_orchestrator_filters_logical_dl_connections_by_applied_2x2_mapping():
    topology = _template_module().generate_caict_mimo_topology()
    row = SimpleNamespace(
        id=uuid4(),
        name="CAICT runtime",
        version="4.0",
        nodes=topology["nodes"],
        connections=topology["connections"],
        operating_modes=topology["operating_modes"],
    )

    class _Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def first(self):
            return row

    class _Db:
        def query(self, *_args):
            return _Query()

    mapping = resolve_base_station_port_mapping(
        adapter_id="uxm",
        mimo_port_preset="2x2_alt",
        mimo_layers=2,
        route_snapshot={
            "tx": {1: "RF3OUT", 2: "RF4OUT"},
            "ota_uplink": "RF6IN",
        },
    )
    result = orchestrate_switch_topology(
        _Db(), uuid4(), base_station_port_mapping=mapping
    )
    payload = result.to_payload()

    # 32 CE→probe + 2 BS→CE + 1 uplink；DL3/DL4 不得继续算 active。
    assert result.active_connection_count == 35
    assert payload["base_station_ports"][0]["logical_port"] == "DL1"
    assert payload["base_station_ports"][0]["physical_port"] == "RF3OUT"


def test_orchestrator_filters_ports_for_a_custom_mimo_mode_id():
    topology = _template_module().generate_caict_mimo_topology()
    custom_mode = dict(topology["operating_modes"][0])
    custom_mode["id"] = "customer_lte_2x2"
    row = SimpleNamespace(
        id=uuid4(), name="custom", version="4.0",
        nodes=topology["nodes"], connections=topology["connections"],
        operating_modes=[custom_mode],
    )

    class _Query:
        def filter(self, *_args):
            return self
        def order_by(self, *_args):
            return self
        def first(self):
            return row

    class _Db:
        def query(self, *_args):
            return _Query()

    mapping = resolve_base_station_port_mapping(
        adapter_id="cmw500", mimo_port_preset="2x2", mimo_layers=2,
        route_snapshot=None,
    )
    result = orchestrate_switch_topology(
        _Db(), uuid4(), mode_id="customer_lte_2x2",
        base_station_port_mapping=mapping,
    )

    assert result.active_connection_count == 35
    assert len(result.base_station_ports) == 3


def test_measure_wires_selected_adapter_route_snapshot_into_topology_resolver():
    source = inspect.getsource(MeasureExecutor)
    helper_source = inspect.getsource(_resolve_base_station_route_snapshot)
    assert "get_mimo_route_snapshot" in helper_source
    assert "_resolve_base_station_route_snapshot" in source
    assert "resolve_base_station_port_mapping" in source
    assert "base_station_port_mapping=" in source


def test_uxm_profile_is_the_single_source_for_expected_physical_route():
    from app.hal.uxm_test_profiles import get_uxm_mimo_route_snapshot

    assert get_uxm_mimo_route_snapshot("2x2") == {
        "tx": {1: "RF1OUT", 2: "RF2OUT"},
        "rx": {1: "RF1IN", 2: "RF2IN"},
        "ota_uplink": "RF6IN",
    }
    assert get_uxm_mimo_route_snapshot("2x2_alt")["tx"] == {
        1: "RF3OUT", 2: "RF4OUT"
    }


def test_route_snapshot_uses_siso_profile_and_missing_readback_only_warns():
    class _Driver:
        def get_mimo_route_snapshot(self, preset):
            assert preset == "siso"
            raise RuntimeError("external source readback unavailable")

    preset, snapshot = _resolve_base_station_route_snapshot(
        _Driver(),
        configured_preset=None,
        mimo_layers=1,
        inherit=False,
    )

    assert preset == "siso"
    assert snapshot is None
