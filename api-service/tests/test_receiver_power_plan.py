import pytest
from app.services.road_test.receiver_power_plan import receiver_levels


def test_window_and_terminal_plane():
    samples = [dict(frame=frame, rx=rx, asc_mw=10**((dbm-frame)/10))
               for frame in [0, 1] for rx,dbm in [(0,-75),(1,-80)]]
    paths = [dict(rx=r, output_port=r+2, rx_cable_loss_db=3, dut_input={"uncertainty_db":0.2}) for r in [1,2]]
    calibration = {"applicable":True,"ports":paths}
    plan = receiver_levels(samples,0,{0:-70},calibration,{0:1,1:2})
    assert plan["common_offset_db"] == pytest.approx(5)
    assert plan["predictions"][0]["f64_connector_target_dbm"] == pytest.approx(-67)
    assert plan["predictions"][-1]["target_dut_dbm"] == pytest.approx(-76)
    assert all(row["measured_dut_dbm"] is None for row in plan["predictions"])
    with pytest.raises(ValueError,match="同一个增益"):
        receiver_levels(samples,0,{0:-70,1:-70},calibration,{0:1,1:2})
    no_cal = receiver_levels(samples,0,{},{"applicable":False},{0:1,1:2})
    assert no_cal["predictions"][0]["f64_connector_target_dbm"] is None


def test_registered_working_point_requires_matching_physical_evidence(tmp_path, monkeypatch):
    import hashlib
    import json
    from app.services.road_test.receiver_power_plan import registered_plan

    monkeypatch.setenv("VRT_CALIBRATION_APPROVED_DIR", str(tmp_path))
    def put(name, data):
        content=json.dumps(data).encode()
        (tmp_path/name).write_bytes(content)
        return {"filename":name,"sha256":hashlib.sha256(content).hexdigest()}
    report=put("prediction.json",dict(receiver_power_verified=True, bandwidth_source="power_reference",
            analysis_bandwidth_hz=20e6,receiver_band_power_mw=[dict(frame=7,rx=r,asc_mw=1e-7) for r in [0,1]]))
    report.update(asset_sha256="asset",source_to_receiver={"0":1,"1":2})
    reg={"receiver_power_evidence":report}
    cal=dict(applicable=True,id="cal",evidence_sha256="measurement",meter_serial="power-meter",
             ports=[dict(rx=1,output_port=2,rx_cable_loss_db=3,dut_input={"uncertainty_db":0.1},
                         emulator_output_setting_dbm=-67)])
    def plan():
        return registered_plan(reg,"asset",20,7,{},cal)
    assert plan()["verified_operating_point"] is False
    manifest=put("asc.json",dict(mode="conducted",direction="downlink",frames=[7],tx_ports=[0,1,2,3],rx_ports=[0,1],
                        links=[dict(tx=t,rx=r) for t in range(4) for r in range(2)],
                        power_basis={"links":{f"{t}/{r}":{"rx_plane":f"dut/in/{r+1}"} for t in range(4) for r in range(2)}}))
    report["manifest_file"]="asc.json"
    cal["required_margin_db"]=1
    cal["ports"][0].update(dut_reference_plane="dut/in/1", emulator_output_dbm=-60)
    cal["ports"][0]["dut_input"].update(peak_dbm=-65,max_safe_input_dbm=-40)
    cal["ports"]=[{**cal["ports"][0],"tx":t,"rx":r,"output_port":r+1,"dut_reference_plane":f"dut/in/{r}"} for t in range(1,5) for r in [1,2]]
    anchor=dict(asc_manifest_sha256=manifest["sha256"], final_cable_compensation="physical_connector_target_only",source="physical_instrument_measurement",asset_sha256="asset",
                calibration_sha256="measurement",prediction_sha256=report["sha256"], bandwidth_hz=20e6,
                frame=7,meter_serial="power-meter",receiver_ports={str(r):{"output_setting_dbm":-67,"dut_average_dbm":-70} for r in [1,2]})
    report["reference_measurement"]=put("anchor.json",anchor)
    assert plan()["verified_operating_point"] is True
    anchor["source"]="simulated"
    report["reference_measurement"]=put("anchor.json",anchor)
    with pytest.raises(ValueError,match="不一致"):
        plan()
