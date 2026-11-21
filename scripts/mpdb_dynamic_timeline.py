"""移植自 ChannelEgine 43954a32 的 imt_dynamic_probe.generate；只替换时间轴输入及来源记录。"""

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

from mimo_ota_simulator.imt_probe_bundle import C, directions, polar_basis, read_columns
if __package__:
    from .mpdb_playback import output_grid
else:
    from mpdb_playback import output_grid


def generate(archive, geometry, baseline, output, playback):
    rate = playback["rate_hz"]
    if output.exists():
        raise ValueError("需要新目录")
    raw, digest = read_columns(archive, dynamic=True)
    manifest = json.loads((baseline / "manifest.json").read_text())
    g = json.loads(geometry.read_text())
    if (
        digest != manifest["source_sha256"]
        or g != manifest["geometry"]
        or not manifest["source_frames_only"]
    ):
        raise ValueError("源帧基线与输入或几何不匹配")
    link = {k: v for (t, k), v in raw.items() if t == "LINK"}
    rays = {k: v for (t, k), v in raw.items() if t == "CHANNEL"}
    frames = np.unique(link["FRAME_ID"])
    (fc,) = np.unique(link["FREQUENCY"])

    def link_index(frame, tx):
        (i,) = np.flatnonzero(
            (link["FRAME_ID"].ravel() == frame)
            & (link["TX_ANT"].ravel() == tx)
            & (link["RX_ANT"].ravel() == 0)
        )
        return i

    times = np.asarray(playback["source_times_s"], dtype=float)
    if len(times) != len(frames):
        raise ValueError("时间轴与源帧数量不符")
    if np.any(np.diff(times) <= 0) or rate <= 2 * np.max(np.abs(rays["DOPPLER"])):
        raise ValueError("时间轴重复或采样率不足")
    grid = output_grid(times[-1], rate)
    if len(grid) < 2:
        raise ValueError("动态相位核对至少需要两个输出时刻")
    points = np.array(g["fit_points_m"])

    def transfer(az, zen):
        phase = np.exp(2j * np.pi * fc / C * (points @ directions(az, zen).T))
        return np.einsum("xr,rpc->xcrp", phase, polar_basis(az, zen)).reshape(
            len(points) * 3, -1, 2
        )

    feeds = np.array(g["probe_azimuth_zenith_deg"])
    inverse = np.linalg.pinv(
        transfer(*feeds.T).reshape(len(points) * 3, -1), rcond=1e-8
    )

    def anchor(frame, tx):
        ident = link["LINK_ID"].ravel()[link_index(frame, tx)]
        m = rays["LINK_ID"].ravel() == ident
        e = (rays["POLAR"][m] @ rays["JONES_T"][m]).reshape(-1, 2)
        e *= (rays["FADE_L"][m] * rays["PHASE"][m]).reshape(-1, 1)
        power = np.sum(abs(e.astype(complex)) ** 2, axis=1)
        indices = np.flatnonzero(power > 0)
        delay = rays["DELAY"][m].ravel()
        order = indices[np.argsort(delay[indices])]
        power = power[order]
        groups = np.minimum(
            ((np.cumsum(power) - power / 2) / power.sum() * 24).astype(int), 23
        )
        spatial = transfer(rays["AOA"][m].ravel()[order], rays["ZOA"][m].ravel()[order])
        weights = inverse @ np.einsum("xrp,rp->xr", spatial, e[order])
        return [
            (weights[:, groups == k], rays["DOPPLER"][m].ravel()[order][groups == k])
            for k in np.unique(groups)
        ]

    def advance(groups, dt):
        result = np.zeros((len(dt), len(feeds) * 2, 24), complex)
        for k, (w, doppler) in enumerate(groups):
            result[:, :, k] = np.exp(2j * np.pi * dt[:, None] * doppler) @ w.T
        return result

    report = dict(
        mode="ota",
        evidence="offline_timeline_doppler",
        direction="downlink",
        smu_built=False,
        geometry=g,
        tx_mode=manifest["tx_mode"],
        reference_rx=0,
        source_frames_only=False,
        header=dict(cir_count=len(grid), taps=24, carrier_hz=float(fc), rate_hz=rate),
        source_sha256=digest,
        **playback,
        rows=len(grid),
        hardware_verified=False,
        absolute_phase_verified=False,
        links=[],
    )
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        expected = []
        observed = []
        for tx in range(4):
            recovered_fields = []
            anchors = [anchor(f, tx) for f in frames]
            paths = [
                baseline
                / f"TX{tx}_PROBE{feed // 2:02d}_{('theta', 'phi')[feed % 2]}.asc"
                for feed in range(2 * len(feeds))
            ]
            hashes = {item["file"]: item["sha256"] for item in manifest["links"]}
            for path in paths:
                if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[path.name]:
                    raise ValueError(f"基线文件校验失败：{path.name}")
            source = np.stack(
                [np.loadtxt(p, skiprows=12).reshape(len(times), 24, 3) for p in paths],
                axis=1,
            )
            checked = np.stack([advance(a, np.array([0.0]))[0] for a in anchors])
            base = source[:, :, :, 1] + 1j * source[:, :, :, 2]
            if not np.allclose(base, checked, rtol=1e-6, atol=1e-12):
                raise ValueError("逐帧复系数与基线不一致")
            values = np.empty((len(grid), len(paths), 24), complex)
            reference = np.empty((len(grid), len(paths)), complex)
            delays = np.empty((len(grid), 24))
            for i, (start, end) in enumerate(zip(times, times[1:])):
                mask = (grid >= start) & (
                    (grid < end) if i < len(times) - 2 else (grid <= end)
                )
                t = grid[mask]
                u = (t - start) / (end - start)
                mix = (u * u * (3 - 2 * u))[:, None, None]
                values[mask] = (1 - mix) * advance(
                    anchors[i], t - start
                ) + mix * advance(anchors[i + 1], t - end)

                # 独立检查载频相位：直接合计所有射线，展开正弦、余弦；
                # 不读取写出的抽头数组，也不调用推进函数。
                def carrier_sum(groups, elapsed):
                    w = np.concatenate([weight for weight, _ in groups], axis=1)
                    fd = np.concatenate([doppler for _, doppler in groups]).astype(
                        float
                    )
                    angle = np.outer(elapsed, fd) * (2 * np.pi)
                    return (np.cos(angle) + 1j * np.sin(angle)) @ w.T

                alpha = (3 * u**2 - 2 * u**3)[:, None]
                reference[mask] = (1 - alpha) * carrier_sum(
                    anchors[i], t - start
                ) + alpha * carrier_sum(anchors[i + 1], t - end)
                delays[mask] = (1 - u[:, None]) * source[i, 0, :, 0] + u[
                    :, None
                ] * source[i + 1, 0, :, 0]
            for feed, path in enumerate(paths):
                target = stage / path.name
                with path.open() as f:
                    header = [next(f).rstrip() for _ in range(12)]
                header[1] = f"{len(grid)} CIRs"
                header[9] = f"{rate} CIR_Update_Rate"
                v = values[:, feed]
                triples = np.stack([delays, v.real, v.imag], axis=-1).reshape(
                    len(grid), -1
                )
                np.savetxt(
                    target,
                    triples,
                    fmt="%.12g",
                    delimiter="\t",
                    comments="",
                    header="\n".join(header),
                )
                recovered = np.loadtxt(target, skiprows=12, ndmin=2)
                if not np.allclose(recovered, triples, atol=0, rtol=6e-12):
                    raise ValueError("文件回读失真")
                recovered_fields.append(
                    (recovered[:, 1::3] + 1j * recovered[:, 2::3]).sum(axis=1)
                )
                report["links"].append(
                    dict(
                        tx=tx,
                        probe=feed // 2,
                        polarization=("theta", "phi")[feed % 2],
                        file=target.name,
                        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    )
                )
            expected.append(reference)
            observed.append(np.stack(recovered_fields, axis=-1))
            print(f"TX{tx} 完成", flush=True)
        model = np.array(expected)
        readback = np.array(observed)
        floor = np.max(abs(model), axis=1, keepdims=True) * 1e-4
        valid = (abs(model) > floor) & (abs(readback) > floor)

        def difference(left, right, mask):
            error = np.angle(left[mask] * right[mask].conj(), deg=True)
            if not error.size or np.max(abs(error)) > 1e-4:
                raise ValueError("载频相位回读与独立射线推进计算不一致")
            return dict(
                compared=int(mask.sum()),
                excluded=int(mask.size - mask.sum()),
                max_deg=float(np.max(abs(error))) if error.size else None,
            )

        report["time_step_phase"] = difference(
            readback[:, 1:] * readback[:, :-1].conj(),
            model[:, 1:] * model[:, :-1].conj(),
            valid[:, 1:] & valid[:, :-1],
        )
        report["port_phase"] = {}
        for a in range(4):
            for b in range(a + 1, 4):
                report["port_phase"][f"{a}-{b}"] = difference(
                    readback[a] * readback[b].conj(),
                    model[a] * model[b].conj(),
                    valid[a] & valid[b],
                )
        report["phase_scope"] = (
            "载频处各抽头相加，逐样点与生成模型对照；低于各通道峰值万分之一的幅度排除。未验证实景逐射线相位。"
        )
        (stage / "manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )
        stage.rename(output)
