"""把已评估的上下行 CSV 与原始非均匀时间轴组织为计算服务可消费的轨迹。"""
import argparse
import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api-service"))
from app.trajectory.cluster_csv import CLUSTER, QUALITY, cluster_path, read_groups
from app.trajectory.cluster_exchange import REFERENCE_HASHES, convert
from scripts.s5_evaluation.run import sha


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("adapted", "directory", "evaluation", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    evaluation = json.loads(args.evaluation.read_bytes())
    if not (sha(args.adapted) == evaluation["input_sha256"][args.adapted.name] == REFERENCE_HASHES["adapted-final.json"]):
        raise ValueError("时间轴输入与评估时的文件不一致")
    if evaluation["input_sha256"] != REFERENCE_HASHES:
        raise ValueError("评估清单与已核实的交付记录不一致")
    document = json.loads(args.adapted.read_bytes())
    args.output.mkdir(exist_ok=True, parents=True)
    trajectories = []
    for direction in document["directions"]:
        trajectory = convert(document, direction, args.directory)
        trajectories.append(trajectory)
    for trajectory in trajectories:
        path = args.output / (trajectory["direction"] + ".json")
        path.write_text(json.dumps(trajectory, ensure_ascii=False, allow_nan=False), encoding="utf-8")
