"""用同一份上传数据构建传导或 OTA 工程，计算在独立进程运行。"""

import os
import json
import sys
from pathlib import Path

import numpy as np
if __package__:
    from .mpdb_playback import resolve_playback
else:
    from mpdb_playback import resolve_playback


def generate_ota(archive, output, playback):
    from mimo_ota_simulator.imt_probe_bundle import read_columns, run
    if __package__:
        from .mpdb_dynamic_timeline import generate
    else:
        from mpdb_dynamic_timeline import generate

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
    if frames.tolist() != playback["frame_ids"]:
        raise ValueError("源帧编号与已检查的时间轴不符")
    if playback["rate_hz"] <= 2 * np.max(np.abs(data["CHANNEL", "DOPPLER"])):
        raise ValueError("输出更新率必须高于原始射线最大绝对多普勒频移的两倍")
    del data
    geometry = (
        Path(os.environ["CHANNEL_ENGINE_PATH"]) / "examples/imt_16probe_geometry.json"
    )
    output.mkdir()
    run(archive, geometry, output / "baseline", 1.0)
    # 上游 CLI 将所有调用参数都标为操作员输入；此处的 1 Hz 只用于源帧顺序浏览。
    manifest_path = output / "baseline/manifest.json"
    baseline = json.loads(manifest_path.read_text())
    baseline["rate_source"] = "source_frame_viewer_placeholder"
    manifest_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2))
    generate(archive, geometry, output / "baseline", output / "dynamic", playback)


if __name__ == "__main__":
    archive, output = map(Path, sys.argv[1:3])
    if sys.argv[3] == "conducted":
        from mpdb_conducted_project import ChooseClustering, build

        try:
            build(archive, output, sys.argv[6] if len(sys.argv) > 6 else None,
                  Path(sys.argv[7]) if len(sys.argv) > 7 else None)
        except ChooseClustering as exc:
            print(exc, file=sys.stderr)
            sys.exit(3)
    else:
        generate_ota(archive, output, json.loads(Path(sys.argv[4]).read_text()))
