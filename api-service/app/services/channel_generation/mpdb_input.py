"""S5a 离线格式适配；没有正式执行消费者，不能作为硬件输入。

只读版本3 route_link、单频、单标量V/V端口。原始单位与候选解释分开；
不聚簇，不推断跨帧路径身份，不执行pickle，不写原件。
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import zipfile

import numpy as np

SCHEMA_VERSION = 's5-raw-paths/1'
MAX_BYTES = 256 * 1024 * 1024
DTYPES = {'I64': ('<i8', 'torch.int64'), 'I32': ('<i4', 'torch.int32'),
          'F32': ('<f4', 'torch.float32'), 'F64': ('<f8', 'torch.float64'),
          'C64': ('<c8', 'torch.complex64'), 'C128': ('<c16', 'torch.complex128')}
LINK_COLUMNS = {'LINK_ID', 'FRAME_ID', 'TX', 'RX', 'TX_ANT', 'RX_ANT',
                'FREQUENCY', 'TX_ANT_POSITION', 'RX_ANT_POSITION'}
PATH_COLUMNS = {'LINK_ID', 'CHANNEL_TYPE', 'H', 'DELAY', 'AOA', 'AOD', 'ZOA', 'ZOD',
                'PATH_LENGTH', 'DOPPLER'}
POWER_COLUMNS = {'LINK_ID', 'CHANNEL_TYPE', 'H', 'DELAY'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'JSON重复字段：{key}')
        result[key] = value
    return result


def _finite_tree(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'JSON含非有限数值')
    elif isinstance(value, dict):
        for child in value.values():
            _finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child)


def _json(data):
    result = json.loads(data, object_pairs_hook=_pairs)
    _finite_tree(result)
    return result


def _archive(data):
    require(len(data) <= MAX_BYTES, '压缩文件超过本工具大小限制')
    archive = zipfile.ZipFile(io.BytesIO(data))
    infos = archive.infolist()
    names = [i.filename for i in infos]
    require(len(names) == len(set(names)), 'ZIP含重复成员名')
    require(sum(i.file_size for i in infos) <= MAX_BYTES, 'ZIP解压大小超过本工具限制')
    for i in infos:
        name = i.filename
        require(not i.is_dir() and not PurePosixPath(name).is_absolute()
                and '..' not in PurePosixPath(name).parts and '\\' not in name
                and not (i.flag_bits & 1), f'不支持或不安全的ZIP成员：{name}')
    return archive


def _tensor(data):
    require(len(data) >= 8, 'safetensors头部截断')
    size = int.from_bytes(data[:8], 'little')
    require(0 < size <= min(1024 * 1024, len(data)-8), 'safetensors头部长度无效')
    header = _json(data[8:8+size])
    require(set(header) == {'data'}, '列分片必须恰有一个data张量')
    item = header['data']
    require(set(item) == {'dtype', 'shape', 'data_offsets'}, '不支持的张量头部')
    require(item['dtype'] in DTYPES, '不支持的张量类型')
    shape = item['shape']
    require(isinstance(shape, list) and 1 <= len(shape) <= 2
            and all(type(n) is int and n >= 0 for n in shape), '张量维度无效')
    dtype, declared = DTYPES[item['dtype']]
    expected = math.prod(shape) * np.dtype(dtype).itemsize
    require(item['data_offsets'] == [0, expected] and len(data)-8-size == expected,
            '张量偏移或数据长度不一致')
    array = np.frombuffer(data, dtype=dtype, offset=8+size).reshape(shape)
    require(bool(np.isfinite(array).all()), '张量含非有限数值')
    return array, declared


def _column(archive, descriptor, used):
    require(isinstance(descriptor, dict) and descriptor.get('__mpdb_column_v2__') is True
            and descriptor.get('kind') == 'tensor' and descriptor.get('encoding') == 'safetensors',
            '只支持safetensors列描述')
    require(set(descriptor) == {'__mpdb_column_v2__', 'kind', 'encoding', 'rowCount', 'shards', 'shape', 'dtype'},
            '列描述包含未支持字段')
    shape = descriptor['shape']
    require(isinstance(shape, list) and shape and all(type(n) is int and n >= 0 for n in shape)
            and type(descriptor['rowCount']) is int and descriptor['rowCount'] == shape[0], '列行数或形状无效')
    chunks, cursor = [], 0
    require(isinstance(descriptor['shards'], list) and descriptor['shards'], '缺少列分片')
    for shard in descriptor['shards']:
        require(set(shard) == {'entry', 'rowStart', 'rowEnd'}, '不支持的分片描述')
        name = shard['entry']
        require(name.endswith('.safetensors') and name not in used, '分片被重复引用或类型错误')
        require(type(shard['rowStart']) is int and type(shard['rowEnd']) is int
                and shard['rowStart'] == cursor and cursor < shard['rowEnd'] <= shape[0],
                '分片范围有缺口、重叠或越界')
        array, dtype = _tensor(archive.read(name))
        require(dtype == descriptor['dtype'] and list(array.shape) == [shard['rowEnd']-cursor, *shape[1:]],
                '分片类型或形状与描述不一致')
        chunks.append(array)
        used.add(name)
        cursor = shard['rowEnd']
    require(cursor == shape[0], '分片未覆盖全部行')
    return np.concatenate(chunks, axis=0)


def _table(archive, columns, table, used):
    allowed = {'LINK': LINK_COLUMNS, 'CHANNEL': PATH_COLUMNS, 'LAURAYCS_POWER_CHANNEL': POWER_COLUMNS}[table]
    required = LINK_COLUMNS if table == 'LINK' else {'LINK_ID', 'CHANNEL_TYPE', 'H'}
    require(required <= set(columns) <= allowed, f'{table}缺必要列或包含未支持列')
    arrays = {name: _column(archive, desc, used) for name, desc in columns.items()}
    count = len(arrays['LINK_ID'])
    require(count > 0, f'{table}不支持空表')
    for name, array in arrays.items():
        integer = name in {'LINK_ID', 'FRAME_ID', 'TX', 'RX', 'TX_ANT', 'RX_ANT', 'CHANNEL_TYPE'}
        width = 3 if name.endswith('_POSITION') else 1
        expected = (count,) if integer else (count, width)
        require(array.shape == expected, f'{table}.{name}必须为支持的单频单端口形状')
        require(array.dtype.kind in ('iu' if integer else 'c' if name == 'H' else 'fiu'),
                f'{table}.{name}数值类型不匹配')
    return arrays


def _raw(arrays):
    return {key: {'real': a.real.tolist(), 'imag': a.imag.tolist()} if np.iscomplexobj(a) else a.tolist()
            for key, a in arrays.items()}


def _read_direction(data, direction):
    with _archive(data) as archive:
        document = _json(archive.read('mpdb.json'))
        require(set(document) <= {'mpdbFormatVersion', 'storageLayout', 'shardRows', 'meta', 'records', 'indexes'},
                'MPDB包含未支持的顶层字段')
        require(document['mpdbFormatVersion'] == 3 and document['storageLayout'] == 'portable-row-sharded',
                '只支持MPDB版本3 portable-row-sharded')
        meta = document['meta']
        require(meta.get('mode') == 'CIR' and meta.get('numFrequency') == 1, '只支持单频CIR')
        platform = meta.get('lauraycsPlatform', {})
        require(platform.get('format') == 'route_link' and platform.get('direction') == direction,
                '方向或route_link格式不一致')
        polarization = meta.get('polarization', {})
        require(polarization.get('txModeOrder') == ['V'] and polarization.get('rxModeOrder') == ['V']
                and polarization.get('txDualPolarized') is False and polarization.get('rxDualPolarized') is False,
                '本工具仅支持明确声明的单V/V极化')
        require({'LINK', 'CHANNEL'} <= set(document['records']) <= {'LINK', 'CHANNEL', 'LAURAYCS_POWER_CHANNEL'},
                '缺少必要表或存在未支持表')
        used = {'mpdb.json'}
        tables = {name: _table(archive, columns, name, used) for name, columns in document['records'].items()}
        # 索引仅为缓存，不用于路径关联；保留原描述，明确列出不参与适配的成员。
        indexes = document.get('indexes', {})
        index_entries = {v['entry'] for v in indexes.values()}
        require(all(n.startswith('indexes/') and n.endswith('.safetensors') for n in index_entries), '索引成员无效')
        require(set(archive.namelist()) == used | index_entries, 'ZIP含未引用数据或缺少声明成员')
    link, channel = tables['LINK'], tables['CHANNEL']
    ids = link['LINK_ID'].tolist()
    require(len(set(ids)) == len(ids) and len(set(link['FRAME_ID'].tolist())) == len(ids), '重复LINK或FRAME身份')
    for name in ('TX', 'RX', 'TX_ANT', 'RX_ANT', 'FREQUENCY'):
        require(np.unique(link[name]).size == 1, f'{name}不是单频单端口')
    require(float(link['FREQUENCY'][0, 0]) > 0, '频点必须为正数')
    for name, table in tables.items():
        require(set(table['LINK_ID'].tolist()) <= set(ids), f'{name}含未知LINK_ID')
    frames = []
    for i, link_id in enumerate(ids):
        rows = np.flatnonzero(channel['LINK_ID'] == link_id).tolist()
        require(bool(rows), '存在没有CHANNEL路径的帧，本工具不支持空帧')
        frames.append({'frame_id': int(link['FRAME_ID'][i]), 'link_id': link_id,
                       'link_row': i, 'sample_rows': rows})
    raw = {name: _raw(values) for name, values in tables.items()}
    provenance = {}
    for name in sorted(PATH_COLUMNS):
        present = name in channel
        provenance[name] = {'origin': 'raw_record' if present else 'missing',
                            'source': f'records.CHANNEL.{name}' if present else None,
                            'physical_meaning_verified': False}
        if not present:
            raw['CHANNEL'][name] = None
    geometry = meta.get('multipathGeometry', {}).get('file')
    crosscheck = None
    if 'DELAY' in channel and 'PATH_LENGTH' in channel:
        crosscheck = float(np.max(np.abs(channel['DELAY'].astype('float64') * 299792458
                                        - channel['PATH_LENGTH'].astype('float64'))))
    return {'direction': direction, 'source_document': document, 'raw_tables': raw, 'frames': frames,
            'sample_identity': 'CHANNEL原始行号；不是跨帧物理路径身份',
            'units': {name: None for name in sorted(PATH_COLUMNS | LINK_COLUMNS)},
            'candidate_units': {'DELAY': 's', 'PATH_LENGTH': 'm', 'FREQUENCY': 'Hz',
                                'AOA': 'deg', 'AOD': 'deg', 'ZOA': 'deg', 'ZOD': 'deg'},
            'unit_evidence': {'delay_length_max_abs_difference_float64': crosscheck,
                              'formula': 'abs(float64(DELAY)*299792458-float64(PATH_LENGTH))',
                              'status': '候选单位数值交叉检查，不是源单位确认'},
            'provenance': provenance, 'polarization': polarization,
            'missing_attachments': [geometry] if geometry else [],
            'ignored_cache_entries': sorted(index_entries)}, link


def _times(link, timestamps_s, speed_m_s, coordinate_units):
    count = len(link['LINK_ID'])
    if timestamps_s is not None:
        require(speed_m_s is None, '显式时间与速度推导不能同时选择')
        require(isinstance(timestamps_s, list) and len(timestamps_s) == count
                and all(type(v) in (int, float) and math.isfinite(v) for v in timestamps_s), '显式时间长度或数值无效')
        times = list(timestamps_s)
        origin = 'explicit_timestamps'
    else:
        require(type(speed_m_s) in (int, float) and math.isfinite(speed_m_s) and speed_m_s > 0
                and coordinate_units == 'metres', '时间需要显式时刻，或正的恒速及metres坐标假设')
        frame_ids = link['FRAME_ID'].tolist()
        require(all(b > a for a, b in zip(frame_ids, frame_ids[1:])),
                '按速度推导要求原LINK行的FRAME_ID严格递增；否则需要显式时间')
        tx = np.linalg.norm(np.diff(link['TX_ANT_POSITION'].astype('float64'), axis=0), axis=1)
        rx = np.linalg.norm(np.diff(link['RX_ANT_POSITION'].astype('float64'), axis=0), axis=1)
        require(count > 1 and ((np.all(tx == 0) and np.all(rx > 0))
                              or (np.all(rx == 0) and np.all(tx > 0))),
                '零位移、双端运动或移动端切换：需要显式时间')
        times = [0., *np.cumsum((tx+rx)/speed_m_s).tolist()]
        origin = 'distance_over_user_speed'
    require(all(math.isfinite(v) for v in times) and all(b > a for a,b in zip(times,times[1:])),
            '时间必须有限且严格递增')
    require(all(math.isfinite(b-a) for a, b in zip(times, times[1:]))
            and math.isfinite(times[-1]-times[0]), '时间差及首末跨度必须有限')
    return times, origin


def inspect_mpdb(path, *, timestamps_s=None, speed_m_s=None, coordinate_units=None, speed_source="declared"):
    """只读适配；显式时间以秒、原LINK行顺序给定。缺依据不生成时间轴。"""
    try:
        require(speed_source in {"declared", "user_confirmed"}, "速度来源声明不受支持")
        return _inspect(Path(path), timestamps_s, speed_m_s, coordinate_units, speed_source)
    except (KeyError, TypeError, AttributeError, IndexError, zipfile.BadZipFile, UnicodeError, OverflowError) as exc:
        raise ValueError(f'MPDB结构或编码不受支持：{exc}') from exc


def _inspect(path, timestamps_s, speed_m_s, coordinate_units, speed_source):
    require(path.stat().st_size <= MAX_BYTES, '源文件超过本工具大小限制')
    data = path.read_bytes()
    sources = [{'path': path.name, 'sha256': digest(data)}]
    results, links = [], []
    with _archive(data) as archive:
        manifest = _json(archive.read('mpdb_manifest.json'))
        require(manifest.get('version') == 2 and manifest.get('fileRule') == 'lauraycs-platform', '不支持的manifest版本或规则')
        files = manifest['files']
        require(len(files) == 2 and {f['direction'] for f in files} == {'downlink', 'uplink'},
                '需要且只支持上下行各一份')
        require(len({f['name'] for f in files}) == 2 and set(archive.namelist()) == {'mpdb_manifest.json', *(f['name'] for f in files)},
                'manifest成员有缺失、重复或额外文件')
        for item in sorted(files, key=lambda f: f['direction']):
            require(item.get('format') == 'route_link' and item.get('frameColumn') == 'FRAME_ID'
                    and item.get('linkColumn') == 'LINK_ID' and item['name'].endswith('.mpdb'), '只支持route_link帧映射')
            payload = archive.read(item['name'])
            result, link = _read_direction(payload, item['direction'])
            sources.append({'path': item['name'], 'sha256': digest(payload)})
            results.append(result)
            links.append(link)
    down, up = links
    for a,b in [('FRAME_ID','FRAME_ID'), ('FREQUENCY','FREQUENCY'),
                ('TX_ANT_POSITION','RX_ANT_POSITION'), ('RX_ANT_POSITION','TX_ANT_POSITION')]:
        require(np.array_equal(down[a], up[b]), f'上下行逐帧对应关系不一致：{a}/{b}')
    times, origin = _times(down, timestamps_s, speed_m_s, coordinate_units)
    for result in results:
        for frame, time in zip(result['frames'], times):
            frame['time_s'] = time
        result['time'] = {'origin': origin, 'span_s': times[-1]-times[0],
                          'intervals_s': [b-a for a,b in zip(times,times[1:])],
                          'formula': None if timestamps_s is not None else '累计三维Euclidean相邻距离/恒速；首帧0秒',
                          'device_playback_duration_s': None}
    timestamp_bytes = json.dumps(timestamps_s, separators=(',', ':'), allow_nan=False).encode() if timestamps_s is not None else None
    return {'schema_version': SCHEMA_VERSION, 'adapter_version': '1',
            'adapter_source_sha256': digest(Path(__file__).read_bytes()),
            'source_files': sources, 'manifest': manifest, 'directions': results,
            'coordinate_system': None, 'generator_version': None, 'scene_transform': None,
            'parameters': {'speed_m_s': speed_m_s, 'speed_source': speed_source if speed_m_s is not None else None,
                           'coordinate_units': coordinate_units,
                           'coordinate_unit_source': 'explicit_assumption' if coordinate_units is not None else None,
                           'timestamps_s': timestamps_s, 'timestamps_canonical_sha256': digest(timestamp_bytes) if timestamp_bytes else None},
            'eligibility': '仅离线格式保真；不证明物理绝对精度，不接正式执行，不证明设备播放',
            'missing_metadata': ['坐标参考系', '生成版本', '原始单位确认', 'H归一化与相位约定', 'DOPPLER产生方法与符号约定']}
