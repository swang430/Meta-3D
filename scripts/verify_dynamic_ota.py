"""离线读取动态探头 ASC，按指定频谱比较独立空间点的模型场。"""

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path
import zipfile

import numpy as np
from mimo_ota_simulator.imt_probe_bundle import C, directions, polar_basis, read_columns
from scripts.mpdb_playback import output_grid
from scripts.mpdb_ota_spectrum import read_spectrum


def spatial(points, az, zen, frequencies):
    distance = directions(az, zen) @ points.T
    return np.exp(2j * np.pi / C * frequencies[None, :, None] * distance[:, None, :])


def anchor(data, lid, points, carrier, offsets, fit, inverse):
    mask = data["CHANNEL", "LINK_ID"].ravel() == lid

    def take(key):
        return data["CHANNEL", key][mask]

    e = (take("POLAR") @ take("JONES_T")).reshape(-1, 2)
    e *= (take("FADE_L") * take("PHASE")).reshape(-1, 1)
    power = np.sum(abs(e.astype(complex)) ** 2, axis=1)
    delay = take("DELAY").ravel().astype(float)
    idx = np.flatnonzero(power > 0)
    idx = idx[np.argsort(delay[idx])]
    power, delay = power[idx], delay[idx]
    groups = np.minimum(
        ((power.cumsum() - power / 2) / power.sum() * 24).astype(int), 23
    )
    compressed = delay.copy()
    for k in np.unique(groups):
        m = groups == k
        compressed[m] = np.average(delay[m], weights=power[m])
    az, zen = take("AOA").ravel()[idx], take("ZOA").ravel()[idx]
    xyz = np.einsum("rp,rpc->rc", e[idx], polar_basis(az, zen))
    field = (
        spatial(points, az, zen, carrier + offsets)[..., None] * xyz[:, None, None, :]
    )
    fit_phase = spatial(fit, az, zen, np.array([carrier]))[:, 0]
    weights = (fit_phase[:, :, None] * xyz[:, None, :]).reshape(
        len(idx), -1
    ) @ inverse.T
    feed_response = (
        weights[:, None, :] * np.exp(-2j * np.pi * delay[:, None] * offsets)[:, :, None]
    )
    return (
        take("DOPPLER").ravel()[idx],
        *(
            field * np.exp(-2j * np.pi * d[:, None] * offsets)[:, :, None, None]
            for d in (delay, compressed)
        ),
        feed_response,
    )


def propagate(a, dt):
    fd, raw, clustered, feed_response = a
    oscillator = np.exp(2j * np.pi * np.outer(dt, fd))

    def advance(field):
        return (oscillator @ field.reshape(len(fd), -1)).reshape(
            len(dt), *field.shape[1:]
        )

    return raw.sum(axis=0), advance(raw), advance(clustered), advance(feed_response)


def energy(fields, weights):
    return np.einsum("f,tfpc->tp", weights, abs(fields) ** 2)


def phase_error(a, b, c, d):
    # 在每一频点比较两发射口矢量场内积的相角。正交或数值零场无相角。
    def cross(x, y):
        z = (x * y.conj()).sum(axis=-1)
        norm = np.linalg.norm(x, axis=-1) * np.linalg.norm(y, axis=-1)
        return z, abs(z) > 1e-10 * norm

    ref, valid = cross(a, b)
    est, ok = cross(c, d)
    return np.where(valid & ok, np.abs(np.angle(est * ref.conj(), deg=True)), np.nan)


def stats(values, indices):
    ok = np.isfinite(values)
    result = dict(valid=int(ok.sum()), excluded=int(ok.size - ok.sum()))
    if ok.any():
        loc = np.unravel_index(np.nanargmax(abs(values)), values.shape)
        result.update(
            p95_abs=float(np.percentile(abs(values[ok]), 95)),
            worst=float(values[loc]),
            row=int(indices[loc[0]]),
            point=int(loc[-1]),
        )
        if len(loc) == 3:
            result["frequency_index"] = int(loc[1])
    return result


def run(archive, project, output):
    directory = project / "dynamic"
    m = json.loads((directory / "manifest.json").read_text())
    data, digest = read_columns(archive, dynamic=True)
    if digest != m["source_sha256"]:
        raise ValueError("源文件与动态工程不匹配")
    with zipfile.ZipFile(archive) as z:
        spectrum = read_spectrum(z, digest)
    if spectrum is None:
        raise ValueError("缺少同源 ota-spectrum.json")
    offsets, weights = spectrum
    offsets, weights = offsets[weights > 0], weights[weights > 0]
    weights /= weights.max()
    weights /= weights.sum()
    h = m["header"]
    fc, taps = h["carrier_hz"], h["taps"]
    if not np.all(data["LINK", "FREQUENCY"] == fc) or np.min(offsets) + fc <= 0:
        raise ValueError("实际频率不匹配")
    times = np.asarray(m["source_times_s"])
    grid = output_grid(times[-1], h["rate_hz"])
    if len(grid) != h["cir_count"] or np.any(np.diff(times) <= 0):
        raise ValueError("动态行数或源帧时间无效")
    geometry = m["geometry"]
    points = np.asarray(geometry["check_points_m"])
    az, zen = np.asarray(geometry["probe_azimuth_zenith_deg"]).T
    rx = m["reference_rx"]
    txs = sorted(set(data["LINK", "TX_ANT"].ravel().tolist()))
    feeds = [(p, pol) for p in range(len(az)) for pol in ("theta", "phi")]
    links = {(x["tx"], x["probe"], x["polarization"]): x for x in m["links"]}
    if set(links) != {(tx, *feed) for tx in txs for feed in feeds} or len(links) != len(
        m["links"]
    ):
        raise ValueError("动态端口清单不完整或重复")
    basis = spatial(points, az, zen, fc + offsets)
    probe = np.einsum("rfp,rvc->rvfpc", basis, polar_basis(az, zen)).reshape(
        len(feeds), len(offsets), len(points), 3
    )
    fit = np.asarray(geometry["fit_points_m"])
    fit_phase = spatial(fit, az, zen, np.array([fc]))[:, 0]
    fit_basis = np.einsum("rp,rvc->pcrv", fit_phase, polar_basis(az, zen))
    inverse = np.linalg.pinv(fit_basis.reshape(-1, len(feeds)), rcond=1e-8)
    asc = {}
    for tx in txs:
        tables = []
        for p, pol in feeds:
            link = links[tx, p, pol]
            path = directory / f"TX{tx}_PROBE{p:02d}_{pol}.asc"
            if (
                link["file"] != path.name
                or hashlib.sha256(path.read_bytes()).hexdigest() != link["sha256"]
            ):
                raise ValueError(f"端口文件或摘要不符：{path.name}")
            with path.open() as stream:
                header = [stream.readline().split() for _ in range(12)]
                for line, expected, unit in (
                    (1, len(grid), "CIRs"),
                    (2, taps, "Taps/CIR"),
                    (3, fc, "Carrier_Frequency"),
                    (9, h["rate_hz"], "CIR_Update_Rate"),
                ):
                    if (
                        len(header[line]) != 2
                        or header[line][1] != unit
                        or float(header[line][0]) != expected
                    ):
                        raise ValueError(f"ASC 文件头与工程不一致：{path.name}")
                rows = np.loadtxt(stream, ndmin=2)
            if rows.shape != (len(grid), 3 * taps) or not np.isfinite(rows).all():
                raise ValueError(f"动态数据无效：{path.name}")
            tables.append(rows.reshape(len(grid), taps, 3))
        asc[tx] = np.stack(tables, axis=1)

    def source(frame, tx):
        sel = np.ones(len(data["LINK", "LINK_ID"]), dtype=bool)
        for key, val in (("FRAME_ID", frame), ("TX_ANT", tx), ("RX_ANT", rx)):
            sel &= data["LINK", key].ravel() == val
        (lid,) = data["LINK", "LINK_ID"].ravel()[sel]
        return anchor(data, lid, points, fc, offsets, fit, inverse)

    result = dict(
        dynamic_manifest_sha256=hashlib.sha256(
            (directory / "manifest.json").read_bytes()
        ).hexdigest(),
        source_sha256=digest,
        reference_rx=rx,
        source_times_s=times.tolist(),
        rate_hz=h["rate_hz"],
        time_source=m["time_source"],
        speed_m_s=m.get("speed_m_s"),
        sample_count=len(grid),
        last_sample_s=float(grid[-1]),
        links=len(links),
        check_points_m=points.tolist(),
        offsets_hz=offsets.tolist(),
        bin_weights=weights.tolist(),
        interframe_physical_truth="unverified",
        hardware_verified=False,
        segments=[],
    )
    stages = (
        "doppler_effect",
        "cluster_delay_effect",
        "probe_fit_and_delay_interpolation",
        "probe_projection_only",
        "tap_compression_after_projection",
        "total_model_difference",
    )
    if times[0] != 0 or not np.array_equal(
        np.unique(data["LINK", "FRAME_ID"]), np.arange(len(times))
    ):
        raise ValueError("源帧时间与 MPDB 的编号范围不符")
    left = {tx: source(0, tx) for tx in txs}
    for i, (start, end) in enumerate(zip(times, times[1:])):
        indices = np.flatnonzero(
            (grid >= start) & ((grid < end) if i < len(times) - 2 else (grid <= end))
        )
        t = grid[indices]
        u = (t - start) / (end - start)
        alpha = (u * u * (3 - 2 * u))[:, None, None, None]
        segment = dict(
            left_frame=i,
            right_frame=i + 1,
            energy_db=[],
            phase_deg=[],
            next_anchor_energy_db=[],
            feed_phase_deg=[],
        )
        fields = {}
        feed_fields = {}
        for tx in txs:
            right = source(i + 1, tx)
            l = propagate(left[tx], t - start)
            r = propagate(right, t - end)
            frozen, raw, compressed = [
                (1 - alpha) * a + alpha * b for a, b in zip(l[:3], r[:3])
            ]
            feed_ref = (1 - alpha[..., 0]) * l[3] + alpha[..., 0] * r[3]
            table = asc[tx][indices]
            amp = table[..., 1] + 1j * table[..., 2]
            feed_read = np.stack(
                [
                    (amp * np.exp(-2j * np.pi * f * 1e-9 * table[..., 0])).sum(-1)
                    for f in offsets
                ],
                axis=1,
            )
            feed_fields[tx] = (feed_ref, feed_read)
            playback = np.einsum("tfr,rfpc->tfpc", feed_read, probe, optimize=True)
            projected = np.einsum("tfr,rfpc->tfpc", feed_ref, probe, optimize=True)
            fields[tx] = (
                (frozen, raw),
                (raw, compressed),
                (compressed, playback),
                (raw, projected),
                (projected, playback),
                (raw, playback),
            )
            for stage, (a, b) in zip(stages, fields[tx]):
                with np.errstate(divide="ignore", invalid="ignore"):
                    delta = 10 * np.log10(energy(b, weights) / energy(a, weights))
                delta[~np.isfinite(delta)] = np.nan
                segment["energy_db"].append(
                    dict(tx=tx, stage=stage, **stats(delta, indices))
                )
            # 从左端单边外推到下一真实源帧，不混入右端射线。
            frozen_left, advanced_left, _, _ = propagate(
                left[tx], np.array([end - start])
            )
            right_truth = right[1].sum(axis=0)[None]
            for label, prediction in (
                ("frozen", frozen_left[None]),
                ("doppler", advanced_left),
            ):
                with np.errstate(divide="ignore", invalid="ignore"):
                    error = 10 * np.log10(
                        energy(prediction, weights) / energy(right_truth, weights)
                    )
                error[~np.isfinite(error)] = np.nan
                item = stats(error, np.array([i + 1]))
                if "row" in item:
                    item["source_frame"] = item.pop("row")
                segment["next_anchor_energy_db"].append(
                    dict(tx=tx, prediction=label, **item)
                )
            left[tx] = right
        for tx, other in combinations(txs, 2):
            a, c = feed_fields[tx]
            b, d = feed_fields[other]
            # 各通道低于该段峰值万分之一时，保留排除数。
            valid = np.logical_and.reduce(
                [
                    abs(x) > abs(x).max(axis=0, keepdims=True) * 1e-4
                    for x in (a, b, c, d)
                ]
            )
            angles = np.where(
                valid, abs(np.angle(c * d.conj() * a.conj() * b, deg=True)), np.nan
            )
            entry = stats(angles, indices)
            if "point" in entry:
                probe_id, pol = feeds[entry.pop("point")]
                entry.update(probe=probe_id, polarization=pol)
            segment["feed_phase_deg"].append(dict(pair=[tx, other], **entry))
            for stage, (a, c), (b, d) in zip(stages, fields[tx], fields[other]):
                segment["phase_deg"].append(
                    dict(
                        pair=[tx, other],
                        stage=stage,
                        **stats(phase_error(a, b, c, d), indices),
                    )
                )
        result["segments"].append(segment)
    output.write_text(json.dumps(result, allow_nan=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "project", "output"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    run(args.archive, args.project, args.output)
