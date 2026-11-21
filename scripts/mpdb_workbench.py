"""用同一份上传数据构建传导或 OTA 工程，计算在独立进程运行。"""

import os
import sys
from pathlib import Path

import numpy as np


def generate_ota(archive, output, speed, rate):
    from mimo_ota_simulator.imt_probe_bundle import read_columns, run
    from mimo_ota_simulator.imt_dynamic_probe import generate

    data, _ = read_columns(archive, dynamic=True)
    frame, tx, rx = [
        data["LINK", name].ravel() for name in ("FRAME_ID", "TX_ANT", "RX_ANT")
    ]
    keys = set(zip(frame, tx, rx))
    frames = np.unique(frame)
    if (
        len(frame) != len(frames) * 8
        or len(keys) != len(frame)
        or any(
            (f, t, r) not in keys for f in frames for t in range(4) for r in range(2)
        )
    ):
        raise ValueError("需要每一帧都有完整的四发两收数据")
    if not np.array_equal(frames, np.arange(len(frames))):
        raise ValueError("当前探头生成器要求源帧从 0 连续编号，请核对原始工程的帧范围")
    anchor = (tx == 0) & (rx == 0)
    pos = data["LINK", "RX_ANT_POSITION"][anchor][np.argsort(frame[anchor])].reshape(
        -1, 3
    )
    samples = (
        np.linalg.norm(np.diff(pos.astype(float), axis=0), axis=1).sum() / speed * rate
    )
    if not 1 <= samples < 20000:
        raise ValueError("按距离和速度估算，输出须在 2 至 20000 个时刻之间")
    del data
    geometry = (
        Path(os.environ["CHANNEL_ENGINE_PATH"]) / "examples/imt_16probe_geometry.json"
    )
    output.mkdir()
    run(archive, geometry, output / "baseline", 1.0)
    generate(archive, geometry, output / "baseline", output / "dynamic", speed, rate)


if __name__ == "__main__":
    archive, output = map(Path, sys.argv[1:3])
    if sys.argv[3] == "conducted":
        from mpdb_conducted_project import build

        build(archive, output)
    else:
        generate_ota(archive, output, *map(float, sys.argv[4:6]))
