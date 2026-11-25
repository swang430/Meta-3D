"""传导工程交付包的离线文件证据。设备位置只能由播放回读单独填报。"""
import hashlib
import json
from itertools import product
import re
from pathlib import Path

from app.utils.asc_file import inspect


def playback_evidence(directory: Path) -> dict:
    raw = (directory / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    if manifest["direction"] != "downlink" or manifest["mode"] != "conducted":
        raise ValueError("需要下行传导工程清单")
    if "tx_ports" in manifest or "rx_ports" in manifest:
        tx, rx = manifest.get("tx_ports"), manifest.get("rx_ports")
        for ports in (tx, rx):
            if (not isinstance(ports, list) or not ports
                    or any(type(p) is not int or p < 0 for p in ports)
                    or len(set(ports)) != len(ports)):
                raise ValueError("清单端口配置无效")
    else:
        # 旧版交付包只有固定四发两收。
        tx, rx = range(4), range(2)
    files = {}
    pairs = set()
    for link in manifest["links"]:
        name = link["file"]
        match = re.fullmatch(r"[A-Za-z0-9_-]+_TX([0-9]+)_RX([0-9]+)_H\.asc", name)
        if not match or tuple(map(int, match.groups())) != (link["tx"], link["rx"]):
            raise ValueError("清单的物理通路与文件名不符")
        pair = (link["tx"], link["rx"])
        if pair in pairs:
            raise ValueError("清单出现重复的发收通路")
        pairs.add(pair)
        path = directory / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != link["sha256"] or inspect(path) != manifest["header"]:
            raise ValueError(f"文件摘要、响应行或播放参数与清单不符：{name}")
        files[name] = digest
    if pairs != set(product(tx, rx)) or set(files) != {p.name for p in directory.glob("*.asc")}:
        raise ValueError("工程目录与端口清单不一致")
    header = manifest["header"]
    last = header["cir_count"] - 1
    return dict(manifest_sha256=hashlib.sha256(raw).hexdigest(), files=files,
                response_count=header["cir_count"], rate_hz=header["rate_hz"],
                last_asc_response_index=last, first_to_last_response_s=last / header["rate_hz"],
                source_frame_times_s=None, last_observed_device_response=None)
