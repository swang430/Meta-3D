"""离线轨迹验证；绝不调用应用、网络或硬件。

格式依据：Channel Studio GCM User Guide Rev15.0 §14.2/§14.2.3，
每链路每时刻一行，固定列定义，簇在生命周期内位置不变。
本工具检查实际文件和身份依据的内容一致性，不替代物理身份认证。
"""
import argparse
import csv
import copy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))


def frames_sha256(frames):
    """以有序帧列表的规范JSON绑定全部输入，拒绝非有限数值。"""
    try:
        raw = json.dumps(frames, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError) as exc:
        raise ValueError('帧内容必须是有限数值组成的JSON') from exc
    return hashlib.sha256(raw).hexdigest()


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name}必须是大于等于{minimum}的整数')
    return value


def _rounded_time(value):
    # 输入保留十进制秒；Rev15 §14.2要求CSV毫秒，本工具明确半入取整。
    if not isinstance(value, str):
        raise ValueError('原始时间必须为十进制秒字符串')
    try:
        seconds = Decimal(value)
        if not seconds.is_finite() or not 0 <= seconds < 86400:
            raise ValueError('时间必须在同一天内')
        with localcontext() as context:
            context.prec = max(32, len(seconds.as_tuple().digits) + abs(seconds.as_tuple().exponent) + 8)
            ms = int((seconds * 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError('原始时间无效') from exc
    if ms >= 86400000:
        raise ValueError('毫秒取整后不能跨日')
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    sec, milli = divmod(rem, 1000)
    return seconds, ms, f'{h:02}:{m:02}:{sec:02}.{milli:03}'


def _load_bound(reference, base_dir):
    if not isinstance(reference, dict) or not isinstance(reference.get('path'), str):
        raise ValueError('必须提供实际证据文件及SHA256')
    try:
        data = (Path(base_dir) / reference['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != reference.get('sha256'):
            raise ValueError('证据文件内容校验失败')
        return json.loads(data)
    except (OSError, TypeError) as exc:
        raise ValueError('证据文件无法读取') from exc


def _verify_evidence(document, frames, base_dir):
    evidence = _load_bound(document.get('identity_evidence'), base_dir)
    if not isinstance(evidence, dict) or evidence.get('schema') != 'gcm-identity/1':
        raise ValueError('缺少跨帧身份依据')
    if evidence.get('frames_sha256') != frames_sha256(frames):
        raise ValueError('身份依据没有绑定本次有序帧内容')
    batch, direction = document.get('batch_id'), document.get('direction')
    if not isinstance(batch, str) or not batch or direction not in ('downlink', 'uplink'):
        raise ValueError('必须明确同一批次和来源方向')
    if evidence.get('batch_id') != batch or evidence.get('direction') != direction:
        raise ValueError('身份文件批次或方向不匹配')
    inputs = document.get('inputs')
    if not isinstance(inputs, dict) or set(inputs) != {'raw_paths', 'final_membership', 'cluster_export'}:
        raise ValueError('必须提供实际逐径、最终成员表及簇导出文件')
    sources = {name: _load_bound(ref, base_dir) for name, ref in inputs.items()}
    expected_ids = [f.get('frame_id') for f in frames]
    if any(not isinstance(x, str) or not x for x in expected_ids) or len(set(expected_ids)) != len(frames):
        raise ValueError('每帧必须有唯一的明确帧ID')
    for source in [evidence] + list(sources.values()):
        if not isinstance(source, dict) or source.get('batch_id') != batch or source.get('direction') != direction:
            raise ValueError('实际来源批次或方向不一致')
        records = source.get('frames')
        if not isinstance(records, list) or len(records) != len(frames) or [r.get('frame_id') for r in records] != expected_ids:
            raise ValueError('实际来源必须覆盖全部有序帧ID，不能混批或截取首帧')
    mappings = []
    for i, frame in enumerate(frames):
        model = frame['model']
        # 原始时序取实际逐径材料，不允许包装层重新声明替换。
        timing = sources['raw_paths']['frames'][i]
        if timing.get('time_seconds') != frame.get('time_seconds') or type(timing.get('frame_index')) is not int or timing.get('frame_index') != frame.get('frame_index'):
            raise ValueError('原始时间或帧索引与实际逐径来源不一致')
        _, _, timestamp = _rounded_time(timing['time_seconds'])
        if model['common'].get('TIMESTAMP') != timestamp:
            raise ValueError('来源模型时间与原始时间的毫秒取整不一致')
        source = model['source']
        if source['batch_id'] != batch or source['direction'] != direction or source['kind'] != document['provenance']:
            raise ValueError('模型来源与实际输入批次、方向或类型不一致')
        for name, ref in inputs.items():
            if source[name] != ref['path']:
                raise ValueError('模型来源路径与实际读取文件不一致')
        if frames_sha256(sources['raw_paths']['frames'][i].get('paths')) != frames_sha256(model['paths']):
            raise ValueError('原始逐径内容与实际文件不一致')
        members = [{'id': c['id'], 'members': c['members']} for c in model['clusters']]
        if frames_sha256(sources['final_membership']['frames'][i].get('clusters')) != frames_sha256(members):
            raise ValueError('最终成员表内容与实际文件不一致')
        exported = {k: model[k] for k in ('common', 'clusters', 'propagation', 'directions', 'rotations')}
        if frames_sha256(sources['cluster_export']['frames'][i].get('model')) != frames_sha256(exported):
            raise ValueError('簇导出内容与实际文件不一致')
        record = evidence['frames'][i]
        if record.get('frame_sha256') != frames_sha256(frame):
            raise ValueError('身份映射未绑定对应帧内容')
        mappings.append(record.get('mapping'))
    return mappings

def _verify_associations(document, frames, mappings, base_dir):
    """独立来源提供相邻帧关联；不从同名成员、功率或距离推算。"""
    reference = document.get('association_evidence')
    association = _load_bound(reference, base_dir)
    # 映射文件与关联来源文件必须独立，不能拿输出映射自身充作关联来源。
    if (Path(base_dir) / reference['path']).resolve() == (Path(base_dir) / document['identity_evidence']['path']).resolve():
        raise ValueError('跨帧关联来源必须独立于输出身份映射文件')
    if not isinstance(association, dict) or association.get('schema') != 'gcm-associations/1':
        raise ValueError('缺少独立来源的跨帧关联依据')
    if association.get('batch_id') != document['batch_id'] or association.get('direction') != document['direction']:
        raise ValueError('跨帧关联来源批次或方向不匹配')
    if association.get('frames_sha256') != frames_sha256(frames):
        raise ValueError('跨帧关联来源未绑定完整输入帧')
    if association.get('input_sha256') != {k: v['sha256'] for k, v in document['inputs'].items()}:
        raise ValueError('跨帧关联来源未绑定实际逐径、成员和簇导出文件')
    producer = association.get('producer')
    if not isinstance(producer, dict) or any(not isinstance(producer.get(k), str) or not producer[k].strip() for k in ('name', 'version', 'method')):
        raise ValueError('跨帧关联来源必须说明产生方、版本和关联方法')
    links = association.get('links')
    if not isinstance(links, list) or len(links) != len(frames) - 1:
        raise ValueError('独立关联必须覆盖每个相邻帧间隔')
    for index, link in enumerate(links):
        if link.get('from_frame_id') != frames[index]['frame_id'] or link.get('to_frame_id') != frames[index+1]['frame_id']:
            raise ValueError('独立关联两端帧身份不匹配')
        before, after = mappings[index], mappings[index+1]
        if not isinstance(before, list) or not isinstance(after, list):
            raise ValueError('输出映射必须为逐簇列表')
        left = {m['track_id']: m for m in before}
        right = {m['track_id']: m for m in after}
        if len(left) != len(before) or len(right) != len(after):
            raise ValueError('输出持续身份不能重复')
        if set(left) != set(right):
            raise ValueError('出生消失的导入语义未经确认，拒绝同槽替换')
        expected = [{
            'track_id': track, 'from_local_id': left[track]['local_id'],
            'to_local_id': right[track]['local_id'],
            'from_member_ids': left[track]['member_ids'],
            'to_member_ids': right[track]['member_ids'],
        } for track in sorted(left)]
        if frames_sha256(link.get('pairs')) != frames_sha256(expected):
            raise ValueError('输出身份映射与独立跨帧关联来源不一致')


def _position(common, prefix):
    # Rev15.0 表4-2，第19页：各坐标范围及到原点距离<100000m。
    try:
        point = tuple(common[prefix + axis + 'COORD'] for axis in 'XYZ')
        if any(type(x) not in (int, float) or not math.isfinite(x) or
               not -100000 <= x <= 100000 for x in point):
            raise ValueError('坐标必须是范围内的有限数值')
        if math.hypot(*point) >= 100000:
            raise ValueError('位置到原点距离必须小于100000米')
    except KeyError as exc:
        raise ValueError('轨迹只接受明确的笛卡尔坐标') from exc
    return point


def _convert_trajectory(document, base_dir):
    """核验实际证据文件后返回CSV数据；不赋予正式或设备验收资格。"""
    if not isinstance(document, dict) or document.get('schema') != 'gcm-trajectory/1':
        raise ValueError('不支持的轨迹格式；须提供可核验的身份依据')
    if document.get('provenance') not in ('synthetic', 'real'):
        raise ValueError('真实或合成来源必须明确，未知拒绝')
    frames = document.get('frames')
    if not isinstance(frames, list) or not 2 <= len(frames) <= 38:
        raise ValueError('必须提供相邻的2至38帧')
    indices = [f.get('frame_index') for f in frames if isinstance(f, dict)]
    if len(indices) != len(frames) or any(type(x) is not int or x < 0 for x in indices) or any(b != a + 1 for a, b in zip(indices, indices[1:])):
        raise ValueError('必须提供相邻且连续的帧索引')
    mappings = _verify_evidence(document, frames, base_dir)
    _verify_associations(document, frames, mappings, base_dir)
    digest = frames_sha256(frames)

    # 延迟导入：未知来源在调用单帧转换前即拒绝。
    from gcm_single_frame import CLUSTER_FIELDS, convert_frame, _convert

    rows, times, points, identities = [], [], [], []
    previous_active, retired, slots = set(), set(), {}
    original_times = []
    decimals = []
    first_common, header, count, link, bs_position = None, None, None, None, None
    for index, (frame, mapping) in enumerate(zip(frames, mappings)):
        model = copy.deepcopy(frame['model'])
        seconds, time, timestamp = _rounded_time(frame.get('time_seconds'))
        model['common']['TIMESTAMP'] = timestamp
        # 单帧交付者授权受信适配器使用_convert；仅在全套实际材料核验后调用。
        try:
            common, clusters = (_convert(model) if document['provenance'] == 'real' else convert_frame(model))
        except (KeyError, TypeError, OverflowError, RecursionError) as exc:
            raise ValueError('单帧内容结构不完整或数值无效') from exc
        if model['common']['DLFREQUENCY'] != model['common']['ULFREQUENCY']:
            raise ValueError('CLUSTER只接受上下行载频相同的时分双工，手册第13章')
        if not clusters or not isinstance(mapping, list) or len(mapping) != len(clusters):
            raise ValueError('每帧所有簇必须填满固定槽位并有身份依据')
        if index == 0:
            first_common = common
            count = len(clusters)
            header = list(common) + list(CLUSTER_FIELDS) * count
            link = tuple(common[k] for k in ('BSID', 'SID', 'UEID', 'DLFREQUENCY', 'ULFREQUENCY'))
            bs_position = _position(common, 'BS')
        if list(common) != list(first_common) or len(clusters) != count:
            raise ValueError('各帧必须使用相同公共列和簇槽位数，不能补空值或虚构功率')
        if tuple(common[k] for k in ('BSID', 'SID', 'UEID', 'DLFREQUENCY', 'ULFREQUENCY')) != link:
            raise ValueError('只允许同一链路和同一载频的相邻帧')
        if _position(common, 'BS') != bs_position:
            raise ValueError('本工具仅支持固定基站的轨迹')
        point = _position(common, 'UE')
        if math.dist(point, bs_position) >= 100000:
            raise ValueError('基站到移动台距离必须小于100000米')
        # Rev15 §13.2.1 的 CLUSTER 导入规则。
        if points and math.dist(point, points[-1]) < 0.3:
            raise ValueError('CLUSTER 导入要求相邻位置至少0.3米')
        points.append(point)
        if times and (time <= times[-1] or seconds <= decimals[-1]):
            raise ValueError('原始及毫秒取整后的时间必须严格递增，不能碰撞或逆序')
        times.append(time)
        decimals.append(seconds)
        original_times.append(frame['time_seconds'])
        local_clusters = {c['CLUSTERID']: c for c in clusters}
        if len(local_clusters) != len(clusters):
            raise ValueError('单帧簇标识不能重复')
        seen_local, active, occupied = set(), set(), set()
        ordered = [None] * count
        frame_ids = []
        for entry in mapping:
            if not isinstance(entry, dict):
                raise ValueError('身份映射必须是对象')
            local = _integer(entry.get('local_id'), '局部簇标识')
            track = _integer(entry.get('track_id'), '持续簇标识')
            slot = _integer(entry.get('slot'), '列槽位')
            if local not in local_clusters or local in seen_local or track in active or slot in occupied or slot >= count:
                raise ValueError('身份映射必须完整且一一对应')
            if track in retired:
                raise ValueError('已消失的身份不得重新出现')
            # §13.2.5/§14.2.3：LOS始终0，NLOS非0，生命周期列位置固定。
            if (local == 0) != (track == 0):
                raise ValueError('直射簇身份必须保持0，非直射簇不能使用0')
            if track in slots and slots[track] != slot:
                raise ValueError('同一簇在生命周期中必须保持列槽位')
            actual_members = next(c['members'] for c in model['clusters'] if c['id'] == local)
            if entry.get('member_ids') != sorted(actual_members):
                raise ValueError('跨帧映射成员与同批最终成员表不一致')
            slots[track] = slot
            cluster = dict(local_clusters[local])
            cluster['CLUSTERID'] = track
            ordered[slot] = cluster
            seen_local.add(local)
            active.add(track)
            occupied.add(slot)
            frame_ids.append({'local_id': local, 'track_id': track, 'slot': slot})
        if seen_local != set(local_clusters) or occupied != set(range(count)):
            raise ValueError('身份映射缺项，不能填充未知槽位')
        if index and active != previous_active:
            raise ValueError('簇出生或消失的槽位语义未经厂商确认，拒绝同槽替换或虚构缺位')
        retired.update(previous_active - active)
        previous_active = active
        identities.append(sorted(frame_ids, key=lambda x: x['slot']))
        rows.append(list(common.values()) + [c[field] for c in ordered for field in CLUSTER_FIELDS])
    # Rev15.0 §13.2.1：多位置总路长>=25波长。取两载频较长波长是本工具的保守策略。
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    required_length = 25 * 299792458 / (min(link[-2:]) * 1e6)
    if length < required_length:
        raise ValueError('轨迹总长度不足25倍较长波长')
    manifest = {
        'schema': 'gcm-trajectory-result/1', 'provenance': document['provenance'],
        'formal_eligible': False, 'hardware_called': False,
        'frames_sha256': digest, 'frame_count': len(rows),
        'source_inputs': document['inputs'], 'identity_evidence': document['identity_evidence'],
        'association_evidence': document['association_evidence'],
        'batch_id': document['batch_id'], 'direction': document['direction'],
        'original_time_seconds': original_times,
        'timestamps': [r[header.index('TIMESTAMP')] for r in rows],
        'intervals_ms': [b - a for a, b in zip(times, times[1:])],
        'identity_mapping': identities, 'route_length_m': length,
        'minimum_route_length_m': required_length,
        'limitations': '仅离线CSV；未导入厂商软件、未播放；厂商模型可能调整时间；不代表独立复现上下行',
    }
    return header, rows, manifest


def convert_trajectory(document, base_dir):
    """核验实际证据文件并规范错误；此函数不访问网络或硬件。"""
    try:
        return _convert_trajectory(document, base_dir)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError('轨迹或证据结构不完整或类型无效') from exc


def main():
    parser = argparse.ArgumentParser(description='有证据绑定的离线GCM轨迹；不调用硬件')
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path, help='新建输出目录，含CSV与证据清单')
    args = parser.parse_args()
    try:
        document = json.loads(args.input.read_text(encoding='utf-8'))
        header, rows, manifest = convert_trajectory(document, args.input.parent)
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, delimiter=';', lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)
        data = stream.getvalue().encode('utf-8')
        manifest['csv_sha256'] = hashlib.sha256(data).hexdigest()
        # 先完成全部验证，拒绝已有目录，避免失败时覆盖既有交付。
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / 'trajectory.csv').write_bytes(data)
        (args.output / 'evidence.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f'拒绝转换：{exc}\n')


if __name__ == '__main__':
    main()
