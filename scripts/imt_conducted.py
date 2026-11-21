"""将 Lauraycs 下行四发两收 ASC 原样组装为 PROPSIM 向导输入包。"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile


def inspect(path):
    """核对本批导出格式，ASC 各字段依据 PROPSIM User Reference §21.1。"""
    with path.open(encoding="ascii") as source:
        def expect(value):
            if source.readline().strip() != value:
                raise ValueError(f"缺少 {value}")

        def field(name, parse):
            value, key = source.readline().split()
            if key != name:
                raise ValueError(f"缺少 {name}")
            result = parse(value)
            if not math.isfinite(result) or result <= 0:
                raise ValueError(f"{name} 需要正数")
            return result

        expect("***** Header *****")
        rows = field("CIRs", int)
        taps = field("Taps/CIR", int)
        if taps > 48:
            raise ValueError("每行抽头数超过 48")
        carrier = field("Carrier_Frequency", float)
        flags = []
        for allowed in (("Route_Open", "Route_Closed"),
                        ("CIRUpdateRate_Locked", "CIRUpdateRate_Unlocked"),
                        ("CarrierFrequency_Locked", "CarrierFrequency_Unlocked")):
            flag = source.readline().strip()
            if flag not in allowed:
                raise ValueError(f"无法识别文件头 {flag}")
            flags.append(flag)
        resolution = field("Delay_Resolution", int)
        if resolution != 5:
            raise ValueError("PROPSIM 要求文件头声明 5 ns 时延分辨率")
        density = field("Sample_Density", float)
        rate = field("CIR_Update_Rate", float)
        expect("***** Tap data *****")
        if source.readline().split() != ["Delay", "Re", "Im"] * taps:
            raise ValueError("抽头列与文件头不符")
        count = 0
        for count, line in enumerate(source, 1):
            values = list(map(float, line.split()))
            if len(values) != 3 * taps or not all(map(math.isfinite, values)):
                raise ValueError(f"第 {count} 行抽头数量或数值无效")
            delays = values[::3]
            if delays[0] < 0 or delays != sorted(delays):
                raise ValueError(f"第 {count} 行时延顺序无效")
        if count != rows:
            raise ValueError(f"声明 {rows} 行，实际 {count} 行")
    return dict(cir_count=rows, taps=taps, carrier_hz=carrier, rate_hz=rate,
                flags=flags, delay_resolution=resolution, sample_density=density)


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
