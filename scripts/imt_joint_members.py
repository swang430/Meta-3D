"""在 Lauraycs 的 HyperRT Python 环境执行，输出共同分簇成员关系。"""

import math
import hashlib
import inspect
import json
import sys
import zipfile
from pathlib import Path
import torch
import numpy as np
from HyperRT.MiRT.Utils import cluster_rays

src, out = map(Path, sys.argv[1:])
# 这个版本的 cluster_rays 接受弧度；较新的版本在内部将度转换为弧度。
implementation = Path(inspect.getfile(cluster_rays))
if (
    hashlib.sha256(implementation.read_bytes()).hexdigest()
    != "5125f0d41d220cc5531419572613e15488d030dda52132d8ca8b36ee13e7921c"
):
    raise ValueError("本复算脚本需要记录在案的弧度接口版本")


sys.path.insert(0, str(Path(__file__).resolve().parent))
from imt_conducted_spectrum import column

with zipfile.ZipFile(src) as db:
    desc = json.loads(db.read("mpdb.json"))
    fr, tx, rx, lid = [
        column(db, desc, "LINK", k).ravel()
        for k in ("FRAME_ID", "TX_ANT", "RX_ANT", "LINK_ID")
    ]
    ids = column(db, desc, "CHANNEL", "LINK_ID").ravel()
    columns = [
        column(db, desc, "CHANNEL", k).ravel()
        for k in ("H", "DELAY", "AOA", "ZOA", "AOD", "ZOD")
    ]
result = {}
for frame in range(38):
    for t in range(4):
        for r in range(2):
            ident = int(lid[(fr == frame) & (tx == t) & (rx == r)].item())
            mask = (ids == ident) & (abs(columns[0]) > 0)
            v = [torch.from_numpy(col[mask]) for col in columns]
            geom = torch.stack([v[1].double() * 1e9, *[x.double() for x in v[2:]]], 1)
            if t == 0 and r == 0:
                torch.manual_seed(20261121)
                labels = cluster_rays(
                    24, *v[:2], *[a * (math.pi / 180) for a in v[2:]]
                )["assignments"]
                ref = geom
                membership = labels
            else:
                membership = labels[torch.cdist(geom, ref).argmin(1)]
            result[f"L{ident}"] = membership.cpu().numpy()
np.savez_compressed(
    out, source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(), **result
)
