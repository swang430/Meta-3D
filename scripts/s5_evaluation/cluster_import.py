"""读取Lauraycs完整聚簇轨迹；仅离线交接，不聚簇、不生成硬件文件。"""
from __future__ import annotations

import argparse
import cmath
import json
import math
from pathlib import Path


UNITS = dict(time='s', delay='ns', angles='deg', doppler='Hz',
             carrier='Hz', response='complex_scalar')
MAX_BYTES = 256 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), '必须是有限数值，不能用布尔值代替')
    return value


def integer(value):
    require(type(value) is int and value >= 0, '必须是非负整数')
    return value


def _finite_tree(value):
    if isinstance(value, float):
        require(math.isfinite(value), '文件含非有限数值')
    elif isinstance(value, dict):
        for child in value.values():
            _finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child)


def validate_trajectory(data):
    """原样保留完整结果；校验不代表来源已验证或允许正式执行。"""
    try:
        _finite_tree(data)
        require(data['schemaVersion'] == 'lauraycs-cluster-trajectory/1', '不支持的聚簇轨迹版本')
        require(data['units'] == UNITS, '聚簇轨迹单位不符合版本约定')
        require(data['clusterIdentity'] == 'frame-local-only', '本版簇编号仅表示帧内身份')
        require(data['angleCoordinateSystem'] in ('LCS', 'GCS', None), '角度坐标系声明无效')
        source = data['source']
        for key in ('taskId', 'mpdbPath'):
            require(isinstance(source[key], str) and source[key].strip(), '缺少来源任务或MPDB身份')
        for key in ('contentVersion', 'softwareVersion', 'additionalLoss'):
            require(key in source, '来源未知项必须显式保留')
        require(number(data['carrierHz']) > 0, '载频必须为正数')
        integer(data['txAnt'])
        integer(data['rxAnt'])
        budget = integer(data['requestedClusterCount'])
        require(1 <= budget <= 24, '本版聚簇预算须为1至24')
        timing = data['timing']
        require(isinstance(timing['source'], str) and timing['source'].strip(), '缺少时间来源')
        times, frames = timing['timesSeconds'], data['frames']
        require(isinstance(times, list) and isinstance(frames, list) and frames
                and len(times) == len(frames), '时间轴与帧数不一致或为空')
        previous = None
        seen = set()
        for i, (time, frame) in enumerate(zip(times, frames)):
            time = number(time)
            require(time >= 0 and (previous is None or time > previous), '时间必须非负且严格递增')
            previous = time
            require(integer(frame['sampleIndex']) == i, '样本次序不完整')
            require(number(frame['timeSeconds']) == time, '帧时刻与时间轴不一致')
            identity = (frame['frameId'], integer(frame['internalLinkId']))
            require(frame['frameId'] is None or type(frame['frameId']) is int, '原始帧身份无效')
            require(identity not in seen, '重复的帧与链路身份')
            seen.add(identity)
            count = integer(frame['inputPathCount'])
            result = frame['clustering']
            status = frame['status']
            if status in ('no_paths', 'no_valid_paths'):
                require(result is None and ((status == 'no_paths' and count == 0)
                                            or (status == 'no_valid_paths' and count > 0)), '空帧状态不一致')
                continue
            require(status == 'clustered' and isinstance(result, dict), '算法失败不能冒充有效帧')
            require(integer(result['rawPaths']) == count, '输入路径计数不一致')
            valid = integer(result['filteredPaths'])
            paths = result['paths']
            require(isinstance(paths, list) and 0 < len(paths) <= min(budget, valid)
                    and valid <= count and integer(result['nCluster']) == len(paths), '实际簇数、有效路径或预算不一致')
            ids = set()
            for path in paths:
                cid = integer(path['clusterId'])
                require(cid not in ids, '帧内簇编号重复')
                ids.add(cid)
                require(number(path['delayNs']) >= 0, '聚簇时延不能为负')
                for key in ('hReal', 'hImag', 'aoaPhi', 'aodPhi'):
                    number(path[key])
                for key in ('aoaTheta', 'aodTheta'):
                    require(0 <= number(path[key]) <= 180, '天顶角超出度制范围')
                require(path['channelType'] is None or type(path['channelType']) is int, '传播类型无效')
                if path['dopplerHz'] is not None:
                    number(path['dopplerHz'])
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f'聚簇轨迹缺字段或结构错误：{exc}') from exc
    return data


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'JSON重复字段：{key}')
        result[key] = value
    return result


def read_trajectory(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, '聚簇轨迹超过读取大小限制')
    return validate_trajectory(json.loads(raw, object_pairs_hook=_pairs))


def sampled_responses(data, offsets_hz):
    """只在已有时刻重建模型频响ΣH·exp(-j2πΔfτ)，不插值或猜跨帧身份。"""
    validate_trajectory(data)
    require(isinstance(offsets_hz, list) and offsets_hz, '频率偏移网格必须明确给出')
    for offset in offsets_hz:
        number(offset)
    rows = []
    for frame in data['frames']:
        row = dict(sampleIndex=frame['sampleIndex'], timeSeconds=frame['timeSeconds'],
                   status='unavailable', reason=frame['status'], real=None, imag=None)
        if frame['status'] == 'clustered':
            paths = frame['clustering']['paths']
            response = [sum(complex(p['hReal'], p['hImag']) * cmath.exp(
                -2j * math.pi * offset * p['delayNs'] * 1e-9) for p in paths)
                for offset in offsets_hz]
            require(all(math.isfinite(v.real) and math.isfinite(v.imag) for v in response),
                    '重建频响溢出，不能输出有效数值')
            row.update(status='model_reconstruction', reason=None,
                       real=[v.real for v in response], imag=[v.imag for v in response])
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--frequency-offsets-hz', nargs='+', type=float)
    args = parser.parse_args()
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
