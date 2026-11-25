"""将 Lauraycs 下行四发两收 ASC 原样组装为 PROPSIM 向导输入包。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import shutil
import tempfile


# 命令行组包和服务端执行核对使用同一份 ASC 格式定义。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api-service"))
from app.utils.asc_file import inspect


def build(source, destination):
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        links = []
        common = None
        for tx in range(4):
            for rx in range(2):
                name = f"R0B0S0D_TX{tx}_RX{rx}_H.asc"
                copy = stage / name
                shutil.copyfile(source / name, copy)
                try:
                    header = inspect(copy)
                    if common is not None and header != common:
                        raise ValueError("与同组链路文件头不一致")
                except ValueError as exc:
                    raise ValueError(f"{name}: {exc}") from exc
                common = header
                links.append(dict(tx=tx, rx=rx, file=name,
                                  sha256=hashlib.sha256(copy.read_bytes()).hexdigest()))
        result = dict(direction="downlink", mode="conducted", header=common, links=links,
                      evidence="offline_asc_validation", smu_built=False, hardware_verified=False)
        (stage / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
        stage.rename(destination)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build(args.source, args.destination)
