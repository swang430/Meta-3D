"""对同批八端口的共同分簇结果与已复算的原始 ASC、逐射线谱做配对比较。"""

import argparse
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np
from mimo_ota_simulator.joint_cluster_response import reduce_link
from imt_conducted_spectrum import (
    column,
    spectrum,
    reconstruct,
    describe,
    OFFSETS,
    EVIDENCE,
)


def compare(source, members, verification_dir=None):
    audit = json.loads((EVIDENCE / "timeline-audit.json").read_text())
    archive = source / audit["archive"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != audit["archive_sha256"]:
        raise ValueError("输入 MPDB 与两方对照不同")
    baseline = json.loads((EVIDENCE.parent / "imt-spectrum/spectra.json").read_text())
    lookup = {
        (x["tx"], x["rx"], x["offset_hz"]): x
        for x in baseline["results"]
        if x["time_axis"] == "distance"
    }
    times = np.array(baseline["distance_anchor_times_s"])
    rate = baseline["rate_hz"]
    grid = np.arange(baseline["common_samples"]) / rate
    with zipfile.ZipFile(archive) as outer:
        raw = outer.read("R0B0S0D.mpdb")
    with zipfile.ZipFile(io.BytesIO(raw)) as db:
        desc = json.loads(db.read("mpdb.json"))
        fr, tx, rx, link, fc = [
            column(db, desc, "LINK", k).ravel()
            for k in ("FRAME_ID", "TX_ANT", "RX_ANT", "LINK_ID", "FREQUENCY")
        ]
        ids, h, delay, ao, fd = [
            column(db, desc, "CHANNEL", k).ravel()
            for k in ("LINK_ID", "H", "DELAY", "AOA", "DOPPLER")
        ]
    results = []
    exported = []
    evidence = []
    with np.load(members, allow_pickle=False) as member:
        if str(member["source_sha256"]) != hashlib.sha256(raw).hexdigest():
            raise ValueError("成员表与实际 MPDB 不符")
        for t in range(4):
            for r in range(2):
                anchors = []
                counts = []
                for k in range(len(times)):
                    (ident,) = link[(tx == t) & (rx == r) & (fr == k)]
                    m = (ids == ident) & (abs(h) > 0)
                    clusters = reduce_link(
                        member[f"L{ident}"], h[m], delay[m], ao[m], fd[m]
                    )
                    if verification_dir is not None:
                        labels = member[f"L{ident}"]
                        values = h[m].astype(complex)
                        frequencies = fd[m].astype(float)
                        for cid, c in clusters.items():
                            key = dict(frame=k, tx=t, rx=r, cluster=cid)
                            exported.append(
                                dict(
                                    **key,
                                    real=c["coefficient"].real,
                                    imag=c["coefficient"].imag,
                                    doppler=c["doppler_mean_hz"],
                                )
                            )
                        for cid in np.unique(labels):
                            key = dict(frame=k, tx=t, rx=r, cluster=int(cid))
                            mask = labels == cid
                            rays = values[mask]
                            evidence.append(
                                dict(
                                    **key,
                                    count=len(rays),
                                    sumReal=math.fsum(rays.real),
                                    sumImag=math.fsum(rays.imag),
                                    sumAbs=math.fsum(abs(rays)),
                                    minHz=float(frequencies[mask].min()),
                                    maxHz=float(frequencies[mask].max()),
                                )
                            )
                    counts.append(len(clusters))
                    anchors.append(
                        tuple(
                            np.array([v[name] for v in clusters.values()])
                            for name in ("coefficient", "delay_s", "doppler_mean_hz")
                        )
                    )
                response = reconstruct(anchors, times, grid)
                for j, offset in enumerate(OFFSETS):
                    f, joint = spectrum(response[:, j], rate)
                    np.testing.assert_array_equal(f, baseline["frequency_bins_hz"])
                    base = lookup[t, r, offset]
                    psd = [
                        np.array(base["psd_asc"]),
                        np.array(base["psd_rebuilt"]),
                        joint,
                    ]
                    norm = [p / p.sum() for p in psd]
                    overlaps = [
                        np.minimum(norm[a], norm[b]).sum()
                        for a, b in ((0, 1), (0, 2), (1, 2))
                    ]
                    results.append(
                        dict(
                            tx=t,
                            rx=r,
                            offset_hz=offset,
                            occupied_clusters_per_frame=counts,
                            asc=base["asc"],
                            rays=base["rebuilt"],
                            joint=describe(
                                f, joint, (float(fc[0]) + offset) * 5 / 299792458
                            ),
                            asc_ray_overlap=overlaps[0],
                            asc_joint_overlap=overlaps[1],
                            ray_joint_overlap=overlaps[2],
                            joint_vs_rays_power_db=10
                            * np.log10(joint.sum() / psd[1].sum()),
                            psd_joint=joint.tolist(),
                        )
                    )
    if verification_dir is not None:
        verification_dir.mkdir(parents=True, exist_ok=False)
        identity = dict(
            mpdb=hashlib.sha256(raw).hexdigest(),
            members=hashlib.sha256(members.read_bytes()).hexdigest(),
        )
        for name, rows in (("results", exported), ("evidence", evidence)):
            (verification_dir / (name + ".json")).write_text(
                json.dumps(
                    dict(schema=f"joint-{name}/1", source=identity, rows=rows),
                    allow_nan=False,
                )
            )
    return dict(
        common_samples=len(grid),
        rate_hz=rate,
        frequency_bins_hz=f.tolist(),
        members_sha256=hashlib.sha256(members.read_bytes()).hexdigest(),
        results=results,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "members", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--verification-dir", type=Path)
    args = p.parse_args()
    args.output.write_text(
        json.dumps(
            compare(args.source, args.members, args.verification_dir), allow_nan=False
        )
        + "\n"
    )
