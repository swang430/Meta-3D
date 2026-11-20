"""从原始MPDB只读核查GCM离线输入；不生成设备文件，不连接仪器。"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

if __package__:
    from .gcm_cluster_evidence import audit_exports
    from .gcm_route_limits import route_limits
else:
    from gcm_cluster_evidence import audit_exports
    from gcm_route_limits import route_limits

MODULE = Path(__file__).resolve().parents[2] / 'api-service/app/services/channel_generation/mpdb_input.py'
spec = importlib.util.spec_from_file_location('s5_mpdb_input', MODULE)
mpdb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mpdb)


def audit(source, *, coordinate_units, speed_m_s, evidence=None):
    """操作者证据原样记录为未独立核实，不升级物理身份或设备适用性。"""
    if coordinate_units != 'metres':
        raise ValueError('必须显式声明米制假设；不从坐标量级猜单位或参考系')
    # 复用已有白名单解析器，时间仅作为离线推导，不声称实播时间。
    parsed = mpdb.inspect_mpdb(source, speed_m_s=speed_m_s, coordinate_units='metres', speed_source='declared')
    result = dict(schema_version='s5-gcm-input-audit/1', hardware_eligible=False,
                  source_files=parsed['source_files'], manifest=parsed['manifest'],
                  parser_sha256=parsed['adapter_source_sha256'],
                  tool_sha256=mpdb.digest(Path(__file__).read_bytes()),
                  route_limits_sha256=mpdb.digest(Path(__file__).with_name('gcm_route_limits.py').read_bytes()),
                  coordinate_unit_source='explicit_assumption', timing_parameters=parsed['parameters'],
                  operator_evidence={'status': 'operator_supplied_unverified' if evidence is not None else 'missing', 'content': evidence},
                  device_acceptance=None, device_playback_duration_s=None,
                  directions=[])
    carriers = {}
    for direction in parsed['directions']:
        raw = direction['raw_tables']
        link = raw['LINK']
        name = direction['direction']
        mobile_endpoint = 'RX' if name == 'downlink' else 'TX'
        base_endpoint = 'TX' if name == 'downlink' else 'RX'
        mobile, base = (link[f'{endpoint}_ANT_POSITION'] for endpoint in (mobile_endpoint, base_endpoint))
        if len({tuple(p) for p in base}) != 1:
            raise ValueError('本工具限定下行RX、上行TX移动；原始端点不符合该条件')
        frames = link['FRAME_ID']
        carriers[name] = dict(zip(frames, link['FREQUENCY'], strict=True))
        meta = direction['source_document']['meta']
        row = direction['frames'][0]['sample_rows'][0]
        sample = {key: ({'real': value['real'][row][0], 'imag': value['imag'][row][0]} if key == 'H'
                        else value[row] if value is not None else None)
                  for key, value in raw['CHANNEL'].items()}
        result['directions'].append(dict(direction=name, mobile_endpoint=mobile_endpoint,
            source_metadata=meta, coordinate_system=None, antenna_orientation=None,
            task_id=None, generator_version=None, cross_frame_path_identity=None,
            missing_attachments=direction['missing_attachments'],
            frame_link_identity=[dict(frame_id=f['frame_id'], link_id=f['link_id'], path_count=len(f['sample_rows']),
                                      raw_type_zero=sum(raw['CHANNEL']['CHANNEL_TYPE'][i] == 0 for i in f['sample_rows']))
                                 for f in direction['frames']],
            positions=[dict(frame_id=f, base=b, mobile=m) for f, b, m in zip(frames, base, mobile)],
            route_limits=route_limits(frames, base, mobile, link['FREQUENCY'][0][0]),
            time=direction['time'], raw_sample=sample))
    down, up = result['directions']
    # Revision 15 第13章第81页：CLUSTER/PATH 导入要求上下行中心频率相同。
    dl, ul = carriers['downlink'], carriers['uplink']
    differences = sorted(f for f in dl.keys() | ul.keys() if dl.get(f) != ul.get(f))
    result['cluster_tdd'] = dict(
        same_center_frequency_all_frames=not differences,
        mismatched_frames=differences,
        frequencies_hz={direction: sorted({v for row in rows.values() for v in row})
                        for direction, rows in carriers.items()},
    )
    result['reciprocal_positions_match'] = down['positions'] == up['positions']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--coordinate-units', required=True, choices=['metres'])
    parser.add_argument('--speed-m-s', type=float, required=True, help='显式声明离线时间推导速度，米/秒')
    parser.add_argument('--evidence', type=Path, help='操作者的坐标系/姿态等证据JSON，保留为未独立核实')
    parser.add_argument('--s5c-exports', type=Path, help='本次 S5c 六组簇表与质量表的目录')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('输出已存在，禁止覆盖')
    try:
        evidence_bytes = args.evidence.read_bytes() if args.evidence else None
        evidence = mpdb._json(evidence_bytes) if evidence_bytes is not None else None
        result = audit(args.source, coordinate_units=args.coordinate_units, speed_m_s=args.speed_m_s, evidence=evidence)
        if args.s5c_exports:
            evaluation = Path(__file__).resolve().parents[2] / 'docs/plans/s5c-budget-frames.json'
            hashes = json.loads(evaluation.read_bytes())['input_sha256']
            result['cluster_exports'] = audit_exports(args.s5c_exports, hashes, result)
        if args.evidence:
            result['operator_evidence']['status'] = 'operator_supplied_unverified'
            result['operator_evidence']['file_sha256'] = mpdb.digest(evidence_bytes)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except ValueError as exc:
        # 白名单解析不通过时保留不可证实结果，不制造逐帧数据。
        rejected = dict(schema_version='s5-gcm-input-audit/1', status='unverified',
                        hardware_eligible=False, reason=str(exc),
                        source_sha256=mpdb.digest(args.source.read_bytes()), directions=[])
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(rejected, handle, ensure_ascii=False, indent=2, allow_nan=False)
        print(f'无法核查：{exc}', file=sys.stderr)
        return 2
    except OSError as exc:
        print(f'无法核查：{exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
