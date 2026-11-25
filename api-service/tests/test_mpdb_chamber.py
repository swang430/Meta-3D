from copy import deepcopy
from types import SimpleNamespace as Row

import pytest

from app.services.mpdb_chamber import assemble_geometry


def inputs():
    probes = [Row(id=str(i), probe_number=i, channel_port=i, polarization=pol, status="idle",
                  position={"azimuth": 42, "elevation": -15, "radius": 3.5})
              for i, pol in ((1, "V"), (2, "H"))]
    installation = dict(lab_profile_id="lab", topology_id="top", chamber_id="room",
                        tx_inputs={"1":"B1.1","3":"B1.2"}, feeds={},
                        fit_points_m=[[0,0,0]], check_points_m=[[0,0,.1]])
    snap = dict(chamber_id="room", lab_profile_id="lab", topology_id="top",
                input_wiring={"B1.1":{}, "B1.2":{}}, route_entries=[], frequency_mhz=3550, selected_at="now")
    for p, basis in zip(probes, ("theta","phi")):
        name = "chain"+str(p.id)
        installation["feeds"][p.id] = dict(chain_id=name, ce_port=p.id, basis=basis, positive_basis_confirmed=True)
        snap["route_entries"].append(dict(chain_id=name, probe_id=1, ce_port=p.id, polarization=p.polarization,
            measurement_provenance="real", reason="selected", value_db=-4.1, source_id="cal"+p.id))
    return Row(id="room", name="暗室甲", num_probes=1, num_polarizations=2), probes, installation, snap, [1,3]


def test_actual_coordinates_and_route_identity_are_frozen():
    args = inputs()
    result = assemble_geometry(*args)
    assert result["probe_azimuth_zenith_deg"] == [[42,105]]
    assert result["probe_connections"][0]["feeds"]["phi"]["source_id"] == "cal2"
    changed = deepcopy(args)
    changed[3]["route_entries"][1]["value_db"] = -3.9
    assert assemble_geometry(*changed)["configuration_sha256"] != result["configuration_sha256"]


@pytest.mark.parametrize("key,value", [("measurement_provenance","simulated"),("source_id",None),("value_db",None)])
def test_missing_real_calibration_names_output(key,value):
    args = inputs()
    args[3]["route_entries"][1][key] = value
    with pytest.raises(ValueError, match="探头 2、输出 2 在 3550 MHz"):
        assemble_geometry(*args)


def test_downlink_wiring_uses_mode_edges_when_active_list_empty():
    from app.services.mpdb_chamber import input_wiring
    topology = Row(operating_modes=[{"id":"mimo_ota","active_connections":[]}],
                   nodes=[{"id":"bs","type":"communication_tester"},{"id":"ce","type":"channel_emulator"}],
                   connections=[dict(id="wire",source="bs",target="ce",source_pin="RF2",
                                     target_pin="in2",direction="DL",modes=["mimo_ota"])])
    assert input_wiring(topology)["in2"]["source_pin"] == "RF2"
