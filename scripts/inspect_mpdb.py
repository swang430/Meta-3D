#!/usr/bin/env python3
"""S5a离线工具，绕过应用启动，不连接数据库或仪器。"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

MODULE = Path(__file__).resolve().parents[1] / 'api-service/app/services/channel_generation/mpdb_input.py'
spec = importlib.util.spec_from_file_location('mpdb_input', MODULE)
mpdb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mpdb)


def main():
    parser = argparse.ArgumentParser(description='只读适配v3单频单端口V/V MPDB；不生成硬件文件')
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    time = parser.add_mutually_exclusive_group(required=True)
    time.add_argument('--timestamps', type=Path, help='原LINK行顺序的秒时刻JSON列表')
    time.add_argument('--speed-m-s', type=float, help='用户确认的恒速，米/秒')
    parser.add_argument('--coordinate-units', choices=['metres'], help='显式坐标单位假设，并非源文件确认')
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('输出文件已存在；禁止覆盖原件或既有结果')
        timestamp_data = args.timestamps.read_bytes() if args.timestamps else None
        result = mpdb.inspect_mpdb(args.input, timestamps_s=mpdb._json(timestamp_data) if timestamp_data is not None else None,
                                  speed_m_s=args.speed_m_s, coordinate_units=args.coordinate_units, speed_source='user_confirmed')
        if timestamp_data is not None:
            result['parameters']['timestamps_file'] = {'path': args.timestamps.name, 'sha256': mpdb.digest(timestamp_data)}
        serialized = json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        with args.output.open('x', encoding='utf-8') as handle:
            handle.write(serialized)
        print(json.dumps({'output': str(args.output), 'schema_version': result['schema_version'],
                          'directions': [{'direction': d['direction'], 'frames': len(d['frames']),
                                          'paths': len(d['raw_tables']['CHANNEL']['LINK_ID']), 'span_s': d['time']['span_s']}
                                         for d in result['directions']]}, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(f'无法适配：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
