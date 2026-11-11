"""独立解析构造，不读取用户样本，不依赖数据库或仪器。"""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

import numpy as np
import pytest

MODULE = Path(__file__).resolve().parents[1] / 'app/services/channel_generation/mpdb_input.py'
spec = importlib.util.spec_from_file_location('mpdb_input', MODULE)
mpdb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mpdb)


def tensor(values, dtype):
    array = np.asarray(values, dtype=dtype)
    codes = {'<i8': 'I64', '<f4': 'F32', '<c8': 'C64'}
    header = json.dumps({'data': {'dtype': codes[array.dtype.str], 'shape': list(array.shape),
                                 'data_offsets': [0, array.nbytes]}}).encode()
    header += b' ' * (-len(header) % 8)
    return struct.pack('<Q', len(header)) + header + array.tobytes()


def fixture_zip(path, times=(0, .1, .25), speed=5, static=False, dual=False, mutate=None):
    """独立公式生成两条路径；方向位置互换但不假设响应互易。"""
    times = np.asarray(times)
    positions = [[30 + (0 if static else speed*t), 5, 0] for t in times]
    length = np.array([[np.linalg.norm(p), np.linalg.norm([15,10,0])+np.linalg.norm(np.array(p)-[15,10,0])]
                       for p in positions])
    h = np.exp(1j*np.array([0, np.pi/3]) - 2j*np.pi*2.4e9*(length-length[0])/299792458)*[1,.5]
    files = {}
    for direction in ('downlink', 'uplink'):
        n = len(times)
        tx = [[0,0,0]]*n
        rx = positions
        if dual: tx = [[float(t),0,0] for t in times]
        if direction == 'uplink': tx,rx = rx,tx
        tables = {'LINK': {'LINK_ID': (list(range(n)), '<i8'), 'FRAME_ID': (list(range(n)), '<i8'),
                    **{k: ([0]*n, '<i8') for k in ('TX','RX','TX_ANT','RX_ANT')},
                    'FREQUENCY': ([[2400000000]]*n, '<i8'), 'TX_ANT_POSITION': (tx,'<f4'), 'RX_ANT_POSITION': (rx,'<f4')},
                  'CHANNEL': {'LINK_ID': (np.repeat(np.arange(n),2),'<i8'), 'CHANNEL_TYPE': ([1,2]*n,'<i8'),
                    'H': (h.reshape(-1,1),'<c8'), 'DELAY': ((length/299792458).reshape(-1,1),'<f4'),
                    'PATH_LENGTH': (length.reshape(-1,1),'<f4'), 'DOPPLER': ([[0]]*(n*2),'<f4'),
                    **{k: ([[10]]*(n*2),'<f4') for k in ('AOA','AOD','ZOA','ZOD')}}}
        meta = {'mpdbFormatVersion':3, 'storageLayout':'portable-row-sharded','shardRows':65536,
                'meta': {'mode':'CIR','numFrequency':1,'lauraycsPlatform':{'direction':direction,'format':'route_link'},
                         'polarization':{'txModeOrder':['V'],'rxModeOrder':['V'],'txDualPolarized':False,'rxDualPolarized':False}},
                'records':{},'indexes':{}}
        entries = {}
        for table, cols in tables.items():
            meta['records'][table] = {}
            for key,(values,dtype) in cols.items():
                a=np.asarray(values,dtype=dtype); entry=f'{table}/{key}.safetensors'
                entries[entry]=tensor(values,dtype)
                meta['records'][table][key]={'__mpdb_column_v2__':True,'kind':'tensor','encoding':'safetensors',
                    'rowCount':len(a),'shape':list(a.shape),'dtype':{'<i8':'torch.int64','<f4':'torch.float32','<c8':'torch.complex64'}[dtype],
                    'shards':[{'entry':entry,'rowStart':0,'rowEnd':len(a)}]}
        if mutate: mutate(meta,entries,direction)
        entries['mpdb.json']=json.dumps(meta).encode()
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            for key,value in entries.items(): z.writestr(key,value)
        files[f'{direction}.mpdb']=stream.getvalue()
    manifest={'version':2,'fileRule':'lauraycs-platform','files':[
        {'name':f'{d}.mpdb','format':'route_link','direction':d,'frameColumn':'FRAME_ID','linkColumn':'LINK_ID'}
        for d in ('downlink','uplink')]}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('mpdb_manifest.json',json.dumps(manifest))
        for name,data in files.items(): z.writestr(name,data)
    return length,h


def test_reference_trajectory_complex_and_nonuniform_time(tmp_path):
    p=tmp_path/'input.zip'; length,h=fixture_zip(p)
    result=mpdb.inspect_mpdb(p,speed_m_s=5,coordinate_units='metres')
    d=result['directions'][0]
    assert result['schema_version']=='s5-raw-paths/1'
    assert result['source_files'][0]['sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert [f['time_s'] for f in d['frames']]==pytest.approx([0,.1,.25])
    assert [f['sample_rows'] for f in d['frames']]==[[0,1],[2,3],[4,5]]
    raw=d['raw_tables']['CHANNEL']; restored=np.array(raw['H']['real'])+1j*np.array(raw['H']['imag'])
    np.testing.assert_array_equal(restored.reshape(-1),h.astype('<c8').reshape(-1))
    np.testing.assert_allclose(np.angle(restored.reshape(h.shape)),np.angle(h),atol=1e-7)
    np.testing.assert_array_equal(raw['DELAY'],(length/299792458).astype('<f4').reshape(-1,1))
    assert d['provenance']['DOPPLER']['physical_meaning_verified'] is False
    assert d['units']['DOPPLER'] is None
    assert result['coordinate_system'] is None and result['generator_version'] is None
    assert d['time']['span_s']==pytest.approx(.25)


@pytest.mark.parametrize('speed',[10,-10])
def test_independent_constant_velocity_reference(tmp_path,speed):
    p=tmp_path/'input.zip'; times=[0,.001,.002,.003]
    _,h=fixture_zip(p,times=times,speed=speed)
    r=mpdb.inspect_mpdb(p,timestamps_s=times)
    raw=r['directions'][0]['raw_tables']['CHANNEL']['H']
    np.testing.assert_array_equal(np.array(raw['real'])+1j*np.array(raw['imag']),h.astype('<c8').reshape(-1,1))
    assert [f['time_s'] for f in r['directions'][1]['frames']]==times


def test_static_requires_explicit_time_and_preserves_known_raw_zero(tmp_path):
    p=tmp_path/'input.zip'; fixture_zip(p,static=True)
    with pytest.raises(ValueError,match='时间'): mpdb.inspect_mpdb(p,speed_m_s=5,coordinate_units='metres')
    r=mpdb.inspect_mpdb(p,timestamps_s=[0,.1,.2])
    assert r['directions'][0]['raw_tables']['CHANNEL']['DOPPLER']==[[0.]]*6
    assert r['directions'][0]['raw_tables']['CHANNEL']['H']['imag'][0]==[0.]


@pytest.mark.parametrize('kwargs',[{}, {'speed_m_s':5}, {'speed_m_s':0,'coordinate_units':'metres'},
    {'speed_m_s':float('nan'),'coordinate_units':'metres'}, {'timestamps_s':[0,0,.2]},
    {'timestamps_s':[0,.1]}, {'timestamps_s':[0,.1,float('inf')]},
    {'timestamps_s':[0,.1,.2],'speed_m_s':5,'coordinate_units':'metres'}])
def test_invalid_time_rejected(tmp_path,kwargs):
    p=tmp_path/'input.zip'; fixture_zip(p)
    with pytest.raises(ValueError): mpdb.inspect_mpdb(p,**kwargs)


def test_dual_motion_requires_time(tmp_path):
    p=tmp_path/'input.zip'; fixture_zip(p,dual=True)
    with pytest.raises(ValueError,match='时间'): mpdb.inspect_mpdb(p,speed_m_s=5,coordinate_units='metres')
    assert len(mpdb.inspect_mpdb(p,timestamps_s=[0,.1,.25])['directions'])==2


def test_missing_optional_is_null_not_zero(tmp_path):
    def mutate(meta,entries,d):
        del meta['records']['CHANNEL']['DOPPLER']; del entries['CHANNEL/DOPPLER.safetensors']
    p=tmp_path/'input.zip'; fixture_zip(p,mutate=mutate)
    d=mpdb.inspect_mpdb(p,timestamps_s=[0,.1,.25])['directions'][0]
    assert d['raw_tables']['CHANNEL']['DOPPLER'] is None
    assert d['provenance']['DOPPLER']['origin']=='missing'


@pytest.mark.parametrize('fault',['version','layout','frequency','port','unknown_column','unknown_table','gap',
    'shape','dtype','offset','nan','orphan','duplicate_frame','direction','position','unsafe','pickle'])
def test_bad_input_fails_loud(tmp_path,fault):
    def mutate(meta,entries,d):
        if fault=='version': meta['mpdbFormatVersion']=2
        elif fault=='layout': meta['storageLayout']='pickle'
        elif fault=='frequency': meta['meta']['numFrequency']=2
        elif fault=='port': entries['LINK/TX_ANT.safetensors']=tensor([0,1,0],'<i8')
        elif fault=='unknown_column': meta['records']['CHANNEL']['H2']=copy.deepcopy(meta['records']['CHANNEL']['H'])
        elif fault=='unknown_table': meta['records']['OTHER']={}
        elif fault=='gap': meta['records']['CHANNEL']['H']['shards'][0]['rowStart']=1
        elif fault=='shape': entries['CHANNEL/H.safetensors']=tensor([1+2j]*6,'<c8')
        elif fault=='dtype': meta['records']['CHANNEL']['H']['dtype']='torch.float32'
        elif fault=='offset': entries['CHANNEL/H.safetensors']=entries['CHANNEL/H.safetensors'][:-1]
        elif fault=='nan': entries['CHANNEL/DELAY.safetensors']=tensor([[float('nan')]]*6,'<f4')
        elif fault=='orphan': entries['CHANNEL/LINK_ID.safetensors']=tensor([0,0,1,1,9,9],'<i8')
        elif fault=='duplicate_frame': entries['LINK/FRAME_ID.safetensors']=tensor([0,0,2],'<i8')
        elif fault=='direction': meta['meta']['lauraycsPlatform']['direction']='unknown'
        elif fault=='position' and d=='uplink': entries['LINK/RX_ANT_POSITION.safetensors']=tensor([[1,0,0]]*3,'<f4')
        elif fault=='unsafe': entries['../bad']=b'bad'
        elif fault=='pickle': entries['data.pkl']=b'not executable'
    p=tmp_path/'input.zip'; fixture_zip(p,mutate=mutate)
    with pytest.raises(ValueError): mpdb.inspect_mpdb(p,timestamps_s=[0,.1,.25])


def test_cli_does_not_overwrite_input_or_existing_output(tmp_path):
    p=tmp_path/'input.zip'; fixture_zip(p); original=p.read_bytes()
    script=Path(__file__).resolve().parents[2]/'scripts/inspect_mpdb.py'
    base=[sys.executable,str(script),str(p),'--speed-m-s','5','--coordinate-units','metres','--output']
    assert subprocess.run(base+[str(p)],capture_output=True).returncode!=0
    assert p.read_bytes()==original
    output=tmp_path/'result.json'
    assert subprocess.run(base+[str(output)],capture_output=True).returncode==0
    assert json.loads(output.read_text())['schema_version']=='s5-raw-paths/1'
    assert json.loads(output.read_text())['parameters']['speed_source']=='user_confirmed'
    assert subprocess.run(base+[str(output)],capture_output=True).returncode!=0


def test_multiple_shards_preserve_rows_and_missing_geometry(tmp_path):
    def mutate(meta,entries,d):
        desc=meta['records']['CHANNEL']['H']
        # 独立按已知实部/虚部顺序构造两个分片。
        entries['CHANNEL/H.safetensors']=tensor([[1+2j],[3+4j]],'<c8')
        entries['CHANNEL/H-tail.safetensors']=tensor([[5+6j],[7+8j],[9+10j],[11+12j]],'<c8')
        desc['shards']=[{'entry':'CHANNEL/H.safetensors','rowStart':0,'rowEnd':2},
                        {'entry':'CHANNEL/H-tail.safetensors','rowStart':2,'rowEnd':6}]
        meta['meta']['multipathGeometry']={'file':'absent.mpgeom'}
    p=tmp_path/'input.zip'; fixture_zip(p,mutate=mutate)
    result=mpdb.inspect_mpdb(p,speed_m_s=5,coordinate_units='metres')
    d=result['directions'][0]
    assert d['raw_tables']['CHANNEL']['H']['imag']==[[2],[4],[6],[8],[10],[12]]
    assert d['missing_attachments']==['absent.mpgeom']
    assert result['parameters']['coordinate_unit_source']=='explicit_assumption'
    assert result['parameters']['speed_source']=='declared'
    assert result['adapter_source_sha256']==hashlib.sha256(MODULE.read_bytes()).hexdigest()


@pytest.mark.parametrize('fault',['dual_polarization','inf_h','metadata_nan','duplicate_json','unknown_member',
                                  'multiple_frequency_values','moving_end_switch','zero_segment'])
def test_additional_contract_rejections(tmp_path,fault):
    def mutate(meta,entries,d):
        if fault=='dual_polarization': meta['meta']['polarization']['txModeOrder']=['V','H']
        elif fault=='inf_h': entries['CHANNEL/H.safetensors']=tensor([[complex(1,float('inf'))]]*6,'<c8')
        elif fault=='metadata_nan': meta['meta']['unknown_number']=float('nan')
        elif fault=='duplicate_json':
            b=entries['CHANNEL/H.safetensors']; n=int.from_bytes(b[:8],'little'); header=b[8:8+n].rstrip()
            header=header[:-1]+b',"data":{}}'; entries['CHANNEL/H.safetensors']=struct.pack('<Q',len(header))+header+b[8+n:]
        elif fault=='unknown_member': entries['unknown.safetensors']=tensor([0],'<i8')
        elif fault=='multiple_frequency_values': entries['LINK/FREQUENCY.safetensors']=tensor([[1],[2],[1]],'<i8')
        elif fault in ('moving_end_switch','zero_segment'):
            fixed=[[0,0,0],[0,0,0],[1,0,0]] if fault=='moving_end_switch' else [[0,0,0]]*3
            moving=[[30,5,0],[31,5,0],[31,5,0]]
            tx,rx=(fixed,moving) if d=='downlink' else (moving,fixed)
            entries['LINK/TX_ANT_POSITION.safetensors']=tensor(tx,'<f4')
            entries['LINK/RX_ANT_POSITION.safetensors']=tensor(rx,'<f4')
    p=tmp_path/'input.zip'; fixture_zip(p,mutate=mutate)
    with pytest.raises(ValueError): mpdb.inspect_mpdb(p,speed_m_s=5,coordinate_units='metres')


def test_explicit_time_cli_provenance(tmp_path):
    p=tmp_path/'input.zip'; fixture_zip(p,static=True)
    timestamps=tmp_path/'time.json'; timestamps.write_text('[1, 1.2, 1.25]\n')
    output=tmp_path/'output.json'
    script=Path(__file__).resolve().parents[2]/'scripts/inspect_mpdb.py'
    run=subprocess.run([sys.executable,str(script),str(p),'--timestamps',str(timestamps),'--output',str(output)],capture_output=True)
    assert run.returncode==0,run.stderr
    result=json.loads(output.read_text()); params=result['parameters']
    assert params['timestamps_s']==[1,1.2,1.25]
    assert params['timestamps_file']['sha256']==hashlib.sha256(timestamps.read_bytes()).hexdigest()
    assert params['timestamps_canonical_sha256']==hashlib.sha256(b'[1,1.2,1.25]').hexdigest()
    assert params['speed_source'] is None
    assert result['directions'][0]['time']['span_s']==.25


@pytest.mark.parametrize('manifest',[[], {'version':2,'fileRule':'lauraycs-platform','files':[{'name':2,'direction':'downlink'}, {'name':3,'direction':'uplink'}]}])
def test_malformed_manifest_is_clear_rejection(tmp_path,manifest):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z: z.writestr('mpdb_manifest.json',json.dumps(manifest))
    with pytest.raises(ValueError): mpdb.inspect_mpdb(p,timestamps_s=[0])


def test_malformed_indexes_is_clear_rejection(tmp_path):
    def mutate(meta,entries,d): meta['indexes']=[]
    p=tmp_path/'bad.zip'; fixture_zip(p,mutate=mutate)
    with pytest.raises(ValueError): mpdb.inspect_mpdb(p,timestamps_s=[0,.1,.2])


def test_speed_rejects_unordered_frame_ids(tmp_path):
    def mutate(meta, entries, direction):
        entries['LINK/FRAME_ID.safetensors'] = tensor([2, 0, 1], '<i8')
    p = tmp_path / 'input.zip'
    fixture_zip(p, mutate=mutate)
    with pytest.raises(ValueError, match='显式时间'):
        mpdb.inspect_mpdb(p, speed_m_s=5, coordinate_units='metres')


def test_speed_accepts_increasing_nonconsecutive_frame_ids(tmp_path):
    def mutate(meta, entries, direction):
        entries['LINK/FRAME_ID.safetensors'] = tensor([2, 5, 11], '<i8')
    p = tmp_path / 'input.zip'
    fixture_zip(p, mutate=mutate)
    result = mpdb.inspect_mpdb(p, speed_m_s=5, coordinate_units='metres')
    for direction in result['directions']:
        assert [f['frame_id'] for f in direction['frames']] == [2, 5, 11]
        assert [f['time_s'] for f in direction['frames']] == pytest.approx([0, .1, .25])


def test_explicit_time_preserves_unordered_frame_ids(tmp_path):
    def mutate(meta, entries, direction):
        entries['LINK/FRAME_ID.safetensors'] = tensor([2, 0, 1], '<i8')
    p = tmp_path / 'input.zip'
    fixture_zip(p, mutate=mutate)
    result = mpdb.inspect_mpdb(p, timestamps_s=[0, .1, .25])
    for direction in result['directions']:
        assert [f['frame_id'] for f in direction['frames']] == [2, 0, 1]
        assert [f['time_s'] for f in direction['frames']] == [0, .1, .25]
        assert [f['sample_rows'] for f in direction['frames']] == [[0, 1], [2, 3], [4, 5]]


@pytest.mark.parametrize('times', [[-1e308, 1e308], [-1e308, 0., 1e308]])
def test_time_difference_overflow_rejected(tmp_path, times):
    p = tmp_path / 'input.zip'
    fixture_zip(p, times=list(range(len(times))), static=True)
    with pytest.raises(ValueError, match='时间差'):
        mpdb.inspect_mpdb(p, timestamps_s=times)
