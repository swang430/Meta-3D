"""用同一份上传数据构建传导或 OTA 工程，计算在独立进程运行。"""

import io
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
if __package__:
    from .mpdb_playback import resolve_playback
    from .mpdb_layout import port_layout
    from .imt_conducted_spectrum import column
else:
    from mpdb_playback import resolve_playback
    from mpdb_layout import port_layout
    from imt_conducted_spectrum import column


def generate_ota(archive, output, playback, geometry):
    from mimo_ota_simulator.imt_probe_bundle import read_columns, run
    if __package__:
        from .mpdb_dynamic_timeline import generate
    else:
        from mpdb_dynamic_timeline import generate

    # 物理时钟和操作员逐段时长均不依赖位置。读取同源的原始多普勒，不补造坐标。
    with zipfile.ZipFile(archive) as outer:
        if outer.getinfo("R0B0S0D.mpdb").file_size > 256 * 1024**2:
            raise ValueError("下行样本超过大小上限")
        raw = outer.read("R0B0S0D.mpdb")
    digest = hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw)) as db:
        if sum(i.file_size for i in db.infolist()) > 512 * 1024**2:
            raise ValueError("内层数据超过大小上限")
        desc = json.loads(db.read("mpdb.json"))
        doppler = column(db, desc, "CHANNEL", "DOPPLER")
        frame, tx, rx = [column(db, desc, "LINK", name).ravel()
                         for name in ("FRAME_ID", "TX_ANT", "RX_ANT")]
    del raw
    if doppler.dtype.kind not in "iuf" or not np.isfinite(doppler).all():
        raise ValueError("原始射线多普勒频移无效")
    port_layout(frame, tx, rx)
    frames = np.unique(frame)
    if not np.array_equal(frames, np.arange(len(frames))):
        raise ValueError("当前探头生成器要求源帧从 0 连续编号，请核对原始工程的帧范围")
    if frames.tolist() != playback["frame_ids"]:
        raise ValueError("源帧编号与已检查的时间轴不符")
    if playback["rate_hz"] <= 2 * np.max(np.abs(doppler)):
        raise ValueError("输出更新率必须高于原始射线最大绝对多普勒频移的两倍")
    chamber = json.loads(geometry.read_text())
    if not chamber.get("chamber_id") or not chamber.get("probe_connections"):
        raise ValueError("布局缺少实际暗室或通路记录")
    output.mkdir()
    run(archive, geometry, output / "baseline", 1.0)
    # 上游 CLI 将所有调用参数都标为操作员输入；此处的 1 Hz 只用于源帧顺序浏览。
    manifest_path = output / "baseline/manifest.json"
    baseline = json.loads(manifest_path.read_text())
    baseline["rate_source"] = "source_frame_viewer_placeholder"
    manifest_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2))
    data, dynamic_digest = read_columns(archive)
    if dynamic_digest != digest:
        raise ValueError("检查动态射线时原始文件发生变化")
    data["CHANNEL", "DOPPLER"] = doppler
    generate(data, digest, geometry, output / "baseline", output / "dynamic", playback)


if __name__ == "__main__":
    archive, output = map(Path, sys.argv[1:3])
    if sys.argv[3] == "conducted":
        from mpdb_conducted_project import ChooseClustering, build

        try:
            build(archive, output, sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] != "auto" else None,
                  Path(sys.argv[7]) if len(sys.argv) > 7 else None)
        except ChooseClustering as exc:
            print(exc, file=sys.stderr)
            sys.exit(3)
    else:
        generate_ota(archive, output, json.loads(Path(sys.argv[4]).read_text()), Path(sys.argv[5]))
