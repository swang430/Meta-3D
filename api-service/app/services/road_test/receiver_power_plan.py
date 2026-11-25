"""从同一工程的接收功率预测和已采用校准，计算公共偏移与逐口目标。"""
from math import isclose, isfinite, log10


def receiver_levels(rows, frame, targets, calibration, source_to_receiver):
    """rows 为同一带宽、同一工程的 H Q Hᴴ 积分，rx 为工程原始编号。"""
    selected = [row for row in rows if row["frame"] == frame]
    if not selected:
        raise ValueError("这个参考帧没有接收功率预测")
    base = {}
    for row in selected:
        port, mw = row["rx"], row["asc_mw"]
        if port in base or not isfinite(mw) or mw <= 0:
            raise ValueError("参考帧接收功率重复、缺失或无法换算为 dBm")
        base[port] = 10 * log10(mw)
    if any(port not in base or not isfinite(level) for port, level in targets.items()):
        raise ValueError("接收目标引用未知端口或非有限功率")
    offsets = [value-base[port] for port,value in targets.items()]
    offset = offsets[0] if offsets else 0.
    if any(not isclose(value, offset, rel_tol=0, abs_tol=1e-6) for value in offsets):
        raise ValueError("多个端口的目标无法用同一个增益偏移实现")
    if set(source_to_receiver) != set(base) or len(set(source_to_receiver.values())) != len(base):
        raise ValueError("源接收端口到实物插口的映射不完整或重复")
    seen = set()
    for row in rows:
        key = row["frame"], row["rx"]
        if key in seen:
            raise ValueError("预测出现重复的帧与接收口")
        seen.add(key)
    if seen != {(f,r) for f in {row["frame"] for row in rows} for r in base}:
        raise ValueError("至少一帧未覆盖全部接收口")
    mapped = {}
    if calibration.get("applicable") is True:
        for path in calibration["ports"]:
            key = path["rx"]
            item = (path["output_port"], path["rx_cable_loss_db"],path["dut_input"]["uncertainty_db"])
            if key in mapped and mapped[key] != item:
                raise ValueError("同一接收口的末段线损或测量依据不一致")
            mapped[key] = item
    predictions = []
    for row in rows:
        port = row["rx"]
        if port not in base or row["asc_mw"] < 0 or not isfinite(row["asc_mw"]):
            raise ValueError("接收功率预测的端口或数值不一致")
        level = 10*log10(row["asc_mw"]) + offset if row["asc_mw"] > 0 else None
        physical = source_to_receiver[port]
        calibrated = mapped.get(physical)
        physical_output = level+calibrated[1] if calibrated and level is not None else None
        predictions.append(dict(output_port=calibrated[0] if calibrated else None, frame=row["frame"], rx=port, physical_rx=physical, target_dut_dbm=level,
                                f64_connector_target_dbm=physical_output,
                                f64_setting_readback_dbm=None, measured_dut_dbm=None))
    return dict(reference_frame=frame, common_offset_db=offset, predictions=predictions,
                calibration_id=calibration.get("id"), calibrated_paths={str(rx):list(values) for rx,values in mapped.items()},
                formal_measurement=False)


def registered_plan(registration, asset_sha, bandwidth_mhz, frame, targets, calibration):
    """实验室将预测文件摘要与已扫描的工程、端口和带宽一起登记。"""
    import hashlib
    import json
    from app.services.road_test.port_calibration import _read_approved_file

    record = registration.get("receiver_power_evidence")
    if not isinstance(record, dict) or record.get("asset_sha256") != asset_sha:
        raise ValueError("工程未登记同源接收功率预测")
    data = _read_approved_file(record["filename"], ".json")
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("接收功率预测文件内容与登记摘要不符")
    report = json.loads(data)
    if (report.get("receiver_power_verified") is not True or report.get("bandwidth_source") != "power_reference"
            or report.get("analysis_bandwidth_hz") != bandwidth_mhz*1e6):
        raise ValueError("接收功率预测缺发射谱矩阵、参考面或同一带宽依据")
    mapping = {int(k):v for k,v in record["source_to_receiver"].items()}
    plan = receiver_levels(report["receiver_band_power_mw"],frame,targets,calibration,mapping)
    plan["prediction_sha256"] = record["sha256"]
    plan["verified_operating_point"] = False
    # 独立的参考帧平均测量与逐路径峰值是两份证据。峰值不能冒充平均值。
    anchor = record.get("reference_measurement")
    if anchor and calibration.get("applicable") is True:
        raw = _read_approved_file(anchor["filename"], ".json")
        if hashlib.sha256(raw).hexdigest() != anchor["sha256"]:
            raise ValueError("参考帧平均功率测量原件摘要不一致")
        measured = json.loads(raw)
        if (measured.get("source") != "physical_instrument_measurement"
                or measured.get("asset_sha256") != asset_sha
                or measured.get("calibration_sha256") != calibration.get("evidence_sha256")
                or measured.get("prediction_sha256") != record["sha256"]
                or measured.get("bandwidth_hz") != bandwidth_mhz*1e6 or measured.get("frame") != frame
                or measured.get("meter_serial") != calibration.get("meter_serial")):
            raise ValueError("参考帧测量的工程、仪表、帧号、带宽或校准依据不一致")
        calibrated_ports = {p["rx"] for p in calibration["ports"]}
        if calibrated_ports != set(mapping.values()):
            raise ValueError("预测未覆盖校准接线的所有实物插口")
        manifest_bytes = _read_approved_file(record["manifest_file"], ".json")
        manifest = json.loads(manifest_bytes)
        if (hashlib.sha256(manifest_bytes).hexdigest() != measured["asc_manifest_sha256"]
                or manifest.get("mode") != "conducted" or set(manifest["rx_ports"]) != set(mapping)
                or set(manifest["frames"]) != {p["frame"] for p in plan["predictions"]}
                or measured.get("final_cable_compensation") != "physical_connector_target_only"):
            raise ValueError("预测的源帧、ASC 工程或末段补偿位置未获确认")
        expected = {(p["tx"],p["rx"]) for p in calibration["ports"]}
        tx_ports = manifest["tx_ports"]
        rx_ports = manifest["rx_ports"]
        if (manifest.get("direction") != "downlink" or tx_ports != [0,1,2,3] or rx_ports != [0,1]
                or len(expected) != 8 or {p for _,p in expected} != set(mapping.values())
                or set(manifest["power_basis"]["links"]) != {f"{t}/{r}" for t in tx_ports for r in rx_ports}
                or sorted((row["tx"],row["rx"]) for row in manifest["links"]) != [(t,r) for t in tx_ports for r in rx_ports]):
            raise ValueError("ASC 清单、功率依据和校准必须覆盖下行四发两收的八条通路")
        for prediction in plan["predictions"]:
            rx = prediction["physical_rx"]
            paths = [p for p in calibration["ports"] if p["rx"] == rx]
            model_rx = prediction["rx"]
            for p in paths:
                if any(manifest["power_basis"]["links"][f"{tx}/{model_rx}"]["rx_plane"] != p["dut_reference_plane"]
                       for tx in manifest["tx_ports"]):
                    raise ValueError("预测参考面与接收机插口不一致")
                level = prediction["target_dut_dbm"]
                if level is not None and (
                    level > p["dut_input"]["peak_dbm"]
                    or level + p["dut_input"]["uncertainty_db"] + calibration["required_margin_db"] > p["dut_input"]["max_safe_input_dbm"]
                    or prediction["f64_connector_target_dbm"] > p["emulator_output_dbm"]):
                    raise ValueError(f"帧 {prediction['frame']} 的接收口 {rx} 预测已超过实测峰值或安全范围")
        checkpoints = measured["receiver_ports"]
        ports = {str(item["physical_rx"]) for item in plan["predictions"]}
        if set(checkpoints) != ports:
            raise ValueError("参考帧测量未覆盖全部接收插口")
        for prediction in (item for item in plan["predictions"] if item["frame"] == frame):
            rx = prediction["physical_rx"]
            point = checkpoints[str(rx)]
            paths = [p for p in calibration["ports"] if p["rx"] == rx]
            if (not paths or prediction["target_dut_dbm"] is None
                    or any(p["emulator_output_setting_dbm"] != point["output_setting_dbm"] for p in paths)
                    or not isclose(point["dut_average_dbm"], prediction["target_dut_dbm"], abs_tol=1e-6, rel_tol=0)):
                raise ValueError("选择的目标与该工作点校准时的参考帧插口平均实测不符")
        plan["verified_operating_point"] = True
        plan["reference_measurement_sha256"] = anchor["sha256"]
    return plan
