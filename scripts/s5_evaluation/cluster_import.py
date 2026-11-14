"""读取Lauraycs完整聚簇轨迹；仅离线交接，不聚簇、不生成硬件文件。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_trajectory(data):
    from mimo_ota_simulator.imported_cluster_trajectory import validate_trajectory as validate
    return validate(data)


def read_trajectory(path):
    from mimo_ota_simulator.imported_cluster_trajectory import read_trajectory as read
    return read(path)


def sampled_responses(data, offsets_hz):
    from mimo_ota_simulator.imported_cluster_trajectory import sampled_responses as response
    return response(data, offsets_hz)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--frequency-offsets-hz', nargs='+', type=float)
    parser.add_argument("--ce-repo", type=Path)
    args = parser.parse_args()
    if args.ce_repo:
        sys.path.insert(0, str(args.ce_repo.resolve()))
    data = read_trajectory(args.input)
    print(json.dumps(dict(
        status='validated_structure_only', frames=len(data['frames']),
        timeSpanSeconds=data['timing']['timesSeconds'][-1]-data['timing']['timesSeconds'][0],
        source=data['source'], angleCoordinateSystem=data['angleCoordinateSystem'],
        hardwareEligible=False,
        frequencyOffsetsHz=args.frequency_offsets_hz,
        sampledResponses=(sampled_responses(data, args.frequency_offsets_hz)
                          if args.frequency_offsets_hz is not None else None),
        note='仅完成文件结构校验；未聚簇、未合成、未验证来源真实性或设备适用性。',
    ), ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
