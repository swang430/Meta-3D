"""把已评估的上下行 CSV 与原始非均匀时间轴组织为计算服务可消费的轨迹。"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api-service"))
from app.trajectory.cluster_csv import CLUSTER, QUALITY, cluster_path, read_groups
from app.trajectory.cluster_exchange import REFERENCE_HASHES, convert


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("adapted", "directory", "evaluation", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    declaration = json.loads(args.evaluation.read_bytes())
    data = args.adapted.read_bytes()
    adapted_hash = sha256(data).hexdigest()
    new_delivery = declaration.get("schemaVersion") == "meta3d-cluster-delivery/1"
    if new_delivery:
        if adapted_hash != declaration.get("inputSha256", {}).get(args.adapted.name):
            raise ValueError("清单中的时间轴校验值与当前适配文件不同")
    elif (declaration.get("input_sha256") != REFERENCE_HASHES
          or adapted_hash != REFERENCE_HASHES["adapted-final.json"]):
        raise ValueError("旧评估记录与当前适配文件不匹配；新批次须提供自身配套清单")
    document = json.loads(data)
    directions = document["directions"]
    if new_delivery:
        directions = [d for d in directions if d["direction"] == declaration.get("direction")]
        if len(directions) != 1:
            raise ValueError("配套清单必须对应一个方向")
    trajectories = [convert(document, direction, args.directory, declaration if new_delivery else None)
                    for direction in directions]
    args.output.mkdir(exist_ok=True, parents=True)
    for trajectory in trajectories:
        path = args.output / (trajectory["direction"] + ".json")
        path.write_text(json.dumps(trajectory, ensure_ascii=False, allow_nan=False), encoding="utf-8")
