"""按操作员指定的离散发射谱，核对源帧独立空间点的相对场能量。"""
import json
import numpy as np


def read_spectrum(archive, digest):
    name = "ota-spectrum.json"
    entries = [item for item in archive.infolist() if item.filename == name]
    if not entries:
        return None
    if len(entries) != 1 or entries[0].file_size > 256_000:
        raise ValueError("OTA 发射谱文件重复或超过大小上限")
    doc = json.loads(archive.read(entries[0]))
    if not isinstance(doc, dict) or doc.get("source_sha256") != digest:
        raise ValueError("OTA 发射谱与下行 MPDB 的摘要不符")
    offsets = np.asarray(doc.get("offsets_hz"))
    powers = np.asarray(doc.get("relative_bin_power"))
    if (offsets.ndim != 1 or not 2 <= offsets.size <= 4096 or powers.shape != offsets.shape
            or any(a.dtype.kind not in "iuf" or not np.isfinite(a).all() for a in (offsets, powers))
            or len(np.unique(offsets)) != offsets.size or np.any(powers < 0)
            or np.count_nonzero(powers) < 2):
        raise ValueError("请给出不同的频偏及对应的非负频点功率，至少两个频点有功率")
    return offsets.astype(float), powers.astype(float)


def field_energy(points, az, zen, e, delays, carrier, offsets, weights):
    from mimo_ota_simulator.imt_probe_bundle import directions, polar_basis, C

    xyz = np.einsum("rp,rpc->rc", e, polar_basis(az, zen))
    energy = []
    for point in points:
        flight = directions(az, zen) @ point / C
        base = xyz * np.exp(2j * np.pi * carrier * flight)[:, None]
        total = 0.0
        for start in range(0, len(offsets), 32):
            part = slice(start, start + 32)
            fields = np.exp(-2j * np.pi * np.outer(offsets[part], delays - flight)) @ base
            total += weights[part] @ np.sum(abs(fields)**2, axis=1)
        energy.append(float(total))
    return np.asarray(energy)


def compare(directory, manifest, data, chamber, spectrum):
    offsets, weights = spectrum
    weights = weights / weights.max()
    weights /= weights.sum()
    carrier = manifest["header"]["carrier_hz"]
    if np.min(offsets) <= -carrier:
        raise ValueError("OTA 发射谱的实际频率必须为正")
    points = np.asarray(chamber["check_points_m"])
    angles = np.asarray(chamber["probe_azimuth_zenith_deg"])
    link = {k: v.ravel() for (table, k), v in data.items() if table == "LINK"}
    rays = {k: v for (table, k), v in data.items() if table == "CHANNEL"}
    rows = []
    for tx in manifest["tx_ports"]:
        feeds = [f for f in manifest["links"] if f["tx"] == tx]
        asc = np.stack([np.loadtxt(directory / f["file"], skiprows=12, ndmin=2)
                        for f in feeds])
        asc = asc.reshape(len(feeds), asc.shape[1], -1, 3)
        taps = asc.shape[2]
        az, zen = np.repeat(angles[[f["probe"] for f in feeds]], taps, axis=0).T
        pol = np.repeat([int(f["polarization"] == "phi") for f in feeds], taps)
        for frame in range(asc.shape[1]):
            lid, = link["LINK_ID"][(link["FRAME_ID"] == frame) & (link["TX_ANT"] == tx)
                                   & (link["RX_ANT"] == manifest["reference_rx"])]
            m = rays["LINK_ID"].ravel() == lid
            e = (rays["POLAR"][m] @ rays["JONES_T"][m]).reshape(-1, 2)
            e *= (rays["FADE_L"][m] * rays["PHASE"][m]).reshape(-1, 1)
            source = field_energy(points, rays["AOA"][m].ravel(), rays["ZOA"][m].ravel(),
                                  e, rays["DELAY"][m].ravel(), carrier, offsets, weights)
            delay, real, imag = asc[:, frame].reshape(-1, 3).T
            components = np.zeros((len(pol), 2), complex)
            components[np.arange(len(pol)), pol] = real + 1j * imag
            result = field_energy(points, az, zen, components, delay * 1e-9, carrier, offsets, weights)
            for point, (ref, actual) in enumerate(zip(source, result)):
                rows.append(dict(frame=frame, tx=tx, check_point=point, source_field_energy=ref,
                                 asc_field_energy=actual, ratio=actual/ref if ref > 0 else None))
    return dict(source_sha256=manifest["source_sha256"], carrier_hz=carrier,
                check_points_m=points.tolist(), reference_rx=manifest["reference_rx"],
                offsets_hz=offsets.tolist(), normalized_bin_power=weights.tolist(),
                scope="source_frames_individual_tx_relative_field_energy", rows=rows)
