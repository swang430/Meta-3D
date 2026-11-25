"""按端口参考面计算单一发射口在载频连续波激励下的离线功率。"""
import math


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def power_basis(doc, digest, carrier, tx_ports, rx_ports, coefficients, frames, *, complex_source=True):
    if doc is None:
        doc = {}
    elif not isinstance(doc, dict) or doc.get("schema") != "conducted-power-reference/1" or doc.get("source_sha256") != digest:
        raise ValueError("功率参考文件版本或下行 MPDB 摘要不匹配")
    if doc and doc.get("carrier_hz") != carrier:
        raise ValueError("参考文件的载频与 MPDB 不一致")
    bandwidth = doc.get("bandwidth_hz")
    if bandwidth is not None and (not _number(bandwidth) or bandwidth <= 0):
        raise ValueError("参考文件带宽无效")
    powers = doc.get("tx_power_dbm", {})
    spectra = doc.get("tx_psd_dbm_per_hz", {})
    ports = {str(t) for t in tx_ports}
    for values in (powers, spectra):
        if not isinstance(values, dict) or not set(values) <= ports or not all(map(_number,values.values())):
            raise ValueError("功率参考包含未知发射端口或无效数值")
    if spectra and bandwidth is None:
        raise ValueError("功率谱密度需要载频和适用带宽")
    links = doc.get("links", {})
    keys = {f"{t}/{r}" for t in tx_ports for r in rx_ports}
    if not isinstance(links, dict) or not set(links) <= keys:
        raise ValueError("功率参考含未知链路")
    basis = dict(schema="conducted-power-basis/1", source_sha256=digest, carrier_hz=carrier,
                 bandwidth_hz=bandwidth, tx_power_dbm=powers or None, tx_psd_dbm_per_hz=spectra or None,
                 asc_amplitude_scale=1.0, scale_applied_at="ASC 直接保存簇复系数",
                 formal_measurement=False, tx_ports=tx_ports, rx_ports=rx_ports, links={})
    rows = []
    for (tx,rx),series in coefficients.items():
        key = f"{tx}/{rx}"
        entry = links.get(key,{})
        if not isinstance(entry, dict):
            raise ValueError("链路参考需要 JSON 对象")
        record = {k:entry.get(k) for k in ("coefficient_unit","tx_plane","rx_plane","phase_origin",
                  "relative_ray_phase","delay_origin","included_losses","antenna_response",
                  "tx_impedance_ohm","rx_impedance_ohm")}
        basis["links"][key] = record
        ratio = None
        if record["coefficient_unit"] == "power_wave_ratio":
            ratio = 1.0
        elif record["coefficient_unit"] == "voltage_transfer_ratio":
            resistances = (record["tx_impedance_ohm"], record["rx_impedance_ohm"])
            if all(_number(r) and r>0 for r in resistances):
                ratio = resistances[0] / resistances[1]
        coherent = complex_source and (not doc or record["relative_ray_phase"] == "preserved")
        known = all(isinstance(record[k],str) and record[k].strip().lower() not in ("","unknown","unverified","未知","未核验")
                    for k in ("tx_plane","rx_plane","included_losses"))
        complete = known and record["antenna_response"] in ("both","tx","rx","neither")
        for frame,taps in zip(frames,series,strict=True):
            values = list(taps)
            h = complex(math.fsum(complex(v).real for v in values), math.fsum(complex(v).imag for v in values))
            norm = abs(h)**2 if coherent else None
            gain = norm*ratio if norm is not None and ratio is not None and complete else None
            level = None
            if gain is not None and gain>0 and str(tx) in powers:
                level = powers[str(tx)] + 10*math.log10(gain)
            rows.append(dict(frame=frame,tx=tx,rx=rx,carrier_coefficient_norm_squared=norm,
                             carrier_power_ratio=gain,single_tx_carrier_dbm=level))
    return basis, rows
