"""单帧 GCM CLUSTER 离线转换；定义与来源边界见 gcm_single_frame.md。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

CLUSTER_FIELDS = ('CLUSTERID', 'POWER', 'DELAY', 'AoA', 'AoD', 'ASA', 'ASD', 'ZoA', 'ZoD', 'ZSA', 'ZSD')
COMMON_FIELDS = ('TIMESTAMP', 'UEXCOORD', 'UEYCOORD', 'UEZCOORD', 'DLFREQUENCY', 'ULFREQUENCY', 'BSID', 'SID', 'UEID', 'BSXCOORD', 'BSYCOORD', 'BSZCOORD')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(type(value) in (int, float) and math.isfinite(value), '数值必须为有限实数，不能使用布尔值或空值')
    return value


def _power_db(record):
    _require(('power_db' in record) != ('pl_db' in record), '须单独指定功率 power_db 或正损耗 pl_db')
    if 'pl_db' in record:
        loss = _number(record['pl_db'])
        _require(loss > 0, '按正损耗定义的 PL 必须大于零')
        return -loss
    return _number(record['power_db'])


def _delay_ns(cluster):
    _require(('delay_s' in cluster) != ('delay_ns' in cluster), '须单独指定以秒或纳秒表示的绝对时延')
    if 'delay_s' in cluster:
        return _number(_number(cluster['delay_s']) * 1e9)
    return _number(cluster['delay_ns'])


def _rotation(matrix):
    _require(isinstance(matrix, list) and len(matrix) == 3 and all(isinstance(r, list) and len(r) == 3 for r in matrix), '旋转必须为三行三列矩阵')
    for row in matrix:
        for value in row:
            _number(value)
    for i in range(3):
        for j in range(3):
            _require(abs(sum(matrix[k][i]*matrix[k][j] for k in range(3)) - (i == j)) < 1e-9, '旋转矩阵必须正交')
    a, b, c = matrix
    determinant = a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    _require(abs(determinant-1) < 1e-9, '旋转不能包含镜像反射')
    return matrix


def _angles(vector, matrix, reverse):
    _require(isinstance(vector, list) and len(vector) == 3, '方向必须为三个分量')
    norm = math.hypot(*[_number(v) for v in vector])
    _require(norm > 0, '方向不能为零向量')
    v = [sum(row[j]*vector[j]/norm for j in range(3)) * (-1 if reverse else 1) for row in matrix]
    _require(math.hypot(v[0], v[1]) > 1e-12, '天顶或天底方向的方位角无法确定')
    return math.degrees(math.atan2(v[1], v[0])), math.degrees(math.acos(max(-1, min(1, v[2]))))


def _statistics(angles, weights):
    total = sum(weights)
    x = sum(w*math.cos(math.radians(a)) for (a, _), w in zip(angles, weights))
    y = sum(w*math.sin(math.radians(a)) for (a, _), w in zip(angles, weights))
    _require(math.hypot(x, y)/total > 1e-12, '成员方位角的圆周中心无法确定')
    azimuth = math.degrees(math.atan2(y, x))
    zenith = sum(w*z for (_, z), w in zip(angles, weights))/total
    az_spread = math.sqrt(sum(w*((a-azimuth+180) % 360-180)**2 for (a, _), w in zip(angles, weights))/total)
    ze_spread = math.sqrt(sum(w*(z-zenith)**2 for (_, z), w in zip(angles, weights))/total)
    return azimuth, zenith, az_spread, ze_spread


def _convert(frame):
    source = frame['source']
    _require(source['kind'] in ('synthetic', 'real'), '来源类别必须为 synthetic 或 real')
    for key in ('batch_id', 'raw_paths', 'final_membership', 'cluster_export'):
        _require(isinstance(source[key], str) and bool(source[key].strip()), '必须提供同批逐径、最终成员及簇导出来源')
    common = frame['common']
    _require(set(common) <= set(COMMON_FIELDS) | {'SPEEDKMH'}, '公共字段包含不支持的列；此接口仅接受完整全局直角坐标')
    result = {'CMIMPORTMODE': 'CLUSTER'}
    for key in COMMON_FIELDS:
        value = common[key]
        if key == 'TIMESTAMP':
            _require(isinstance(value, str) and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{3}', value), '时间必须为 hh:mm:ss.mmm')
        else:
            _number(value)
        result[key] = value
    # GCM Rev 15 表 4-2：场景坐标及链路长度，单位 m。
    bs, ue = (tuple(common[f'{role}{axis}COORD'] for axis in 'XYZ') for role in ('BS', 'UE'))
    _require(max(math.hypot(*bs), math.hypot(*ue)) < 100000, '基站和移动端到场景原点必须小于 100000 米')
    _require(math.dist(bs, ue) < 100000, '基站和移动端的链路距离必须小于 100000 米')
    _require(source['direction'] in ('downlink', 'uplink'), '须明确这组簇来自下行还是上行')
    for key in ('DLFREQUENCY', 'ULFREQUENCY'):
        _require(0 < common[key] < 100000, '频率必须大于 0 且小于 100000 MHz')
    # GCM Revision 15 第 13 章第 81 页：CLUSTER 与 PATH 仅接受 TDD。
    _require(common['DLFREQUENCY'] == common['ULFREQUENCY'], 'CLUSTER 导入要求上下行同频')
    for key, maximum in (('BSID', 16), ('UEID', 64)):
        _require(type(common[key]) is int and 1 <= common[key] <= maximum, key+' 超出手册编号范围')
    _require(type(common['SID']) is int and common['SID'] >= 1, '小区编号必须为正整数')
    if 'SPEEDKMH' in common:
        _require(_number(common['SPEEDKMH']) >= 0, '速度不能为负')
        result['SPEEDKMH'] = common['SPEEDKMH']
    # 手册 §14.2 INFO 可选。保留来源类别，合成样本不得冒充真实导出。
    result['INFO'] = source['kind'] + '-' + source['direction']
    directions = frame['directions']
    _require(directions['arrival'] in ('toward_source', 'propagation'), '必须明确到达方向角色')
    _require(directions['departure'] in ('toward_receiver', 'opposite_propagation'), '必须明确离开方向角色')
    rotations = {role: _rotation(frame['rotations'][role]) for role in ('arrival', 'departure')}
    paths = {}
    _require(isinstance(frame['paths'], list) and frame['paths'], '必须提供原始逐径')
    for path in frame['paths']:
        _require(isinstance(path['id'], str) and bool(path['id']) and path['id'] not in paths, '逐径编号必须唯一且非空')
        _require(path['batch_id'] == source['batch_id'], '逐径与最终簇必须来自同一批次')
        _power_db(path)
        paths[path['id']] = path
    clusters = frame['clusters']
    _require(isinstance(clusters, list) and clusters, '必须提供最终簇')
    ids, used, output = set(), set(), []
    for cluster in clusters:
        cid = cluster['id']
        _require(type(cid) is int and cid >= 0 and cid not in ids, '簇编号必须为唯一非负整数')
        ids.add(cid)
        _require(cluster['batch_id'] == source['batch_id'], '簇导出与逐径必须来自同一批次')
        members = cluster['members']
        _require(isinstance(members, list) and members, '最终簇成员不能为空')
        _require(all(isinstance(m, str) and m in paths and m not in used for m in members) and len(set(members)) == len(members), '成员必须存在且不能重复分配')
        used.update(members)
        power, delay = _power_db(cluster), _delay_ns(cluster)
        # User Guide Revision 15.0 §14.2.3 Table 14-5：绝对功率 <0 dB，绝对时延 >0 ns。
        _require(power < 0 and delay > 0, '簇绝对功率必须小于 0 dB，绝对时延必须大于 0 ns')
        peak = max(_power_db(paths[m]) for m in members)
        weights = [10**((_power_db(paths[m])-peak)/10) for m in members]
        stats = {}
        for role in ('arrival', 'departure'):
            reverse = directions[role] in ('propagation', 'opposite_propagation')
            stats[role] = _statistics([_angles(paths[m][role], rotations[role], reverse) for m in members], weights)
        # 手册 §22.2：GCM 到达角由移动端观察，离开角由基站观察（下行约定）。
        a, d = stats['arrival'], stats['departure']
        if source['direction'] == 'uplink':
            a, d = d, a
        _require(a[2] <= 104 and d[2] <= 104 and a[3] <= 52 and d[3] <= 52, '角度扩展超出手册范围：方位 0–104°，天顶 0–52°')
        output.append(dict(zip(CLUSTER_FIELDS, (cid, power, delay, a[0], d[0], a[2], d[2], a[1], d[1], a[3], d[3]))))
    _require(used == set(paths), '原始逐径必须全部由同批最终簇成员覆盖，不能静默丢径')
    _require(len(ids - {0}) <= 24, '非直达簇不能超过 24 个')
    _require(frame['propagation'] in ('LOS', 'NLOS') and (0 in ids) == (frame['propagation'] == 'LOS'), '直达条件必须与编号为 0 的簇一致')
    return result, output


def _validate_real_source(frame):
    """核实独立材料的字节哈希和逐项对应；不把一致性当作测量真实性认证。"""
    source = frame['source']
    identity = {key: source[key] for key in ('batch_id', 'frame_id', 'direction')}
    _require(isinstance(identity['frame_id'], str) and bool(identity['frame_id'].strip()), '真实材料必须提供帧编号')
    documents, paths, hashes = {}, [], set()
    for key in ('raw_paths', 'final_membership', 'cluster_export'):
        path = Path(source[key])
        _require(path.is_absolute() and path.is_file(), '真实材料须使用可读取的绝对文件路径：'+key)
        _require(all(not path.samefile(previous) for previous in paths), '三份来源材料必须为不同文件')
        paths.append(path)
        content = path.read_bytes()
        digest = source['sha256'][key]
        _require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) is not None, '材料哈希必须为小写 SHA-256：'+key)
        _require(digest not in hashes, '三份来源材料内容必须独立')
        hashes.add(digest)
        _require(hashlib.sha256(content).hexdigest() == digest, '材料内容与哈希不符：'+key)
        document = json.loads(content)
        _require(isinstance(document, dict) and all(json.dumps(document.get(k), sort_keys=True) == json.dumps(v, sort_keys=True) for k, v in identity.items()), '材料批次、帧编号或方向不符：'+key)
        _require(document.get('kind') == 'real', '材料必须明确声明真实来源：'+key)
        documents[key] = document
    raw = documents['raw_paths']
    for key in ('common', 'rotations', 'directions', 'paths', 'propagation'):
        _require(json.dumps(raw[key], sort_keys=True) == json.dumps(frame[key], sort_keys=True), '原始材料与输入内容不符：'+key)
    membership = [{'id': c['id'], 'batch_id': c['batch_id'], 'members': c['members']} for c in frame['clusters']]
    exported = [{k: v for k, v in c.items() if k != 'members'} for c in frame['clusters']]
    _require(json.dumps(documents['final_membership']['clusters'], sort_keys=True) == json.dumps(membership, sort_keys=True), '最终成员表与输入簇不符')
    _require(json.dumps(documents['cluster_export']['clusters'], sort_keys=True) == json.dumps(exported, sort_keys=True), '簇功率时延导出与输入不符')


def convert_frame(frame: dict) -> tuple[dict, list[dict]]:
    """按冻结接口返回公共列和输入顺序的簇列；任何输入错误抛 ValueError。"""
    try:
        if frame['source']['kind'] == 'real':
            _validate_real_source(frame)
        return _convert(frame)
    except (KeyError, TypeError, OverflowError, RecursionError, OSError, UnicodeError) as exc:
        raise ValueError('输入结构不完整或字段类型错误：'+str(exc)) from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        frame = json.loads(args.input.read_text(encoding='utf-8'))
        protected = [args.input]
        if isinstance(frame, dict) and isinstance(frame.get('source'), dict) and frame['source'].get('kind') == 'real':
            protected += [Path(frame['source'][key]) for key in ('raw_paths', 'final_membership', 'cluster_export')]
        for path in protected:
            _require(args.output.resolve() != path.resolve() and not (args.output.exists() and path.exists() and args.output.samefile(path)), '输出不能覆盖输入或来源材料，包括符号链接和硬链接')
        common, clusters = convert_frame(frame)
        with args.output.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, delimiter=';')
            writer.writerow(list(common) + list(CLUSTER_FIELDS)*len(clusters))
            writer.writerow(list(common.values()) + [value for cluster in clusters for value in cluster.values()])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('离线转换失败：'+str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
