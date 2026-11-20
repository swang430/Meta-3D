"""离线函数与真实命令行入口验证；样本为合成数据。"""
import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'gcm_single_frame.py'
spec = importlib.util.spec_from_file_location('gcm_single_frame', MODULE)
gcm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gcm)


def sample():
    return json.loads((ROOT / 'fixtures/gcm_single_frame.json').read_text())


class ConversionTests(unittest.TestCase):
    def test_cartesian_limits_and_source_direction(self):
        for bs_x, ue_x, accepted in [(0, 99999, True), (0, 100000, False), (99999, 100001, False), (-50000, 50000, False)]:
            with self.subTest(bs_x=bs_x, ue_x=ue_x):
                frame = sample()
                frame['common'].update(BSXCOORD=bs_x, UEXCOORD=ue_x, BSZCOORD=0, UEZCOORD=0)
                if accepted:
                    common, _ = gcm.convert_frame(frame)
                    self.assertIn('downlink', common['INFO'])
                else:
                    with self.assertRaises(ValueError):
                        gcm.convert_frame(frame)
        frame = sample()
        frame['source']['direction'] = 'both'
        with self.assertRaises(ValueError):
            gcm.convert_frame(frame)

    def test_source_units_and_provenance(self):
        frame = sample()
        cluster = frame['clusters'][0]
        cluster.pop('power_db')
        cluster.pop('delay_ns')
        cluster.update(pl_db=80, delay_s=1e-7)
        row = gcm.convert_frame(frame)[1][0]
        self.assertEqual((row['POWER'], row['DELAY']), (-80, 100))
        for extra in [dict(power_db=-80), dict(delay_ns=100), dict(pl_db=-80)]:
            invalid = copy.deepcopy(frame)
            invalid['clusters'][0].update(extra)
            with self.assertRaises(ValueError):
                gcm.convert_frame(invalid)
        frame['source']['kind'] = 'real'
        with self.assertRaises(ValueError):
            gcm.convert_frame(frame)

    def test_cluster_import_requires_tdd(self):
        frame = sample()
        frame['common'].update(DLFREQUENCY=2400, ULFREQUENCY=2400)
        self.assertEqual(gcm.convert_frame(frame)[0]['ULFREQUENCY'], 2400)
        for invalid in (0, 100000):
            bad = copy.deepcopy(frame)
            bad['common'].update(DLFREQUENCY=invalid, ULFREQUENCY=invalid)
            with self.assertRaises(ValueError):
                gcm.convert_frame(bad)
        frame['common']['ULFREQUENCY'] = 2400.000001
        with self.assertRaisesRegex(ValueError, '同频'):
            gcm.convert_frame(frame)

    def test_real_materials_cli_and_mismatch_rejection(self):
        # 构造材料仅验证 real 接口的一致性机制，不声称它是真实测量。
        with tempfile.TemporaryDirectory() as temp:
            frame = sample()
            frame['source'].update(kind='real', frame_id='frame-1')
            frame['common'].update(DLFREQUENCY=2400, ULFREQUENCY=2400)
            identity = {k: frame['source'][k] for k in ('kind', 'batch_id', 'frame_id', 'direction')}
            docs = {
                'raw_paths': dict(identity, **{k: frame[k] for k in ('common', 'rotations', 'directions', 'paths', 'propagation')}),
                'final_membership': dict(identity, clusters=[{k: c[k] for k in ('id', 'batch_id', 'members')} for c in frame['clusters']]),
                'cluster_export': dict(identity, clusters=[{k: v for k, v in c.items() if k != 'members'} for c in frame['clusters']]),
            }
            frame['source']['sha256'] = {}
            for key, document in docs.items():
                path = Path(temp)/(key+'.json')
                path.write_text(json.dumps(document))
                frame['source'][key] = str(path)
                frame['source']['sha256'][key] = hashlib.sha256(path.read_bytes()).hexdigest()
            inp, out = Path(temp)/'frame.json', Path(temp)/'frame.csv'
            inp.write_text(json.dumps(frame))
            run = subprocess.run([sys.executable, str(MODULE), str(inp), str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('real-downlink', out.read_text())
            for key in ('raw_paths', 'final_membership', 'cluster_export'):
                material = Path(frame['source'][key])
                original = material.read_bytes()
                for link in ('direct', 'symbolic', 'hard'):
                    target = material if link == 'direct' else Path(temp)/(key+'-'+link)
                    if link == 'symbolic':
                        target.symlink_to(material)
                    elif link == 'hard':
                        os.link(material, target)
                    rejected = subprocess.run([sys.executable, str(MODULE), str(inp), str(target)], capture_output=True, text=True)
                    self.assertEqual(rejected.returncode, 2)
                    self.assertEqual(material.read_bytes(), original)
            for link in ('direct', 'symbolic', 'hard'):
                target = inp if link == 'direct' else Path(temp)/('input-'+link)
                if link == 'symbolic':
                    target.symlink_to(inp)
                elif link == 'hard':
                    os.link(inp, target)
                original = inp.read_bytes()
                rejected = subprocess.run([sys.executable, str(MODULE), str(inp), str(target)], capture_output=True, text=True)
                self.assertEqual(rejected.returncode, 2)
                self.assertEqual(inp.read_bytes(), original)
            for mutate in (
                lambda f: f['source']['sha256'].update(raw_paths='0'*64),
                lambda f: f['source'].update(frame_id='other'),
                lambda f: f['source'].update(direction='uplink'),
                lambda f: f['paths'][0].update(power_db=-79),
                lambda f: f['rotations'].update(arrival=[[1,0,0],[0,1,0],[0,0,1]]),
                lambda f: f['clusters'][0].update(members=['p2','p1']),
                lambda f: f['clusters'][0].update(delay_ns=124),
            ):
                invalid = copy.deepcopy(frame)
                mutate(invalid)
                with self.assertRaises(ValueError):
                    gcm.convert_frame(invalid)
            original = Path(frame['source']['raw_paths']).read_bytes()
            raw_doc = json.loads(original)
            raw_doc['common']['BSID'] = True
            material = Path(frame['source']['raw_paths'])
            material.write_text(json.dumps(raw_doc))
            bad = copy.deepcopy(frame)
            bad['source']['sha256']['raw_paths'] = hashlib.sha256(material.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                gcm.convert_frame(bad)
            material.write_bytes(original)
            combined = json.loads(original)
            combined['clusters'] = docs['final_membership']['clusters']
            material.write_text(json.dumps(combined))
            bad = copy.deepcopy(frame)
            bad['source']['sha256']['raw_paths'] = hashlib.sha256(material.read_bytes()).hexdigest()
            bad['source']['final_membership'] = bad['source']['raw_paths']
            bad['source']['sha256']['final_membership'] = bad['source']['sha256']['raw_paths']
            with self.assertRaises(ValueError):
                gcm.convert_frame(bad)
            material.write_bytes(original+b' ')
            with self.assertRaises(ValueError):
                gcm.convert_frame(frame)

    def test_cli_independent_recalculation(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'out.csv'
            run = subprocess.run([sys.executable, str(MODULE), str(ROOT/'fixtures/gcm_single_frame.json'), str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            with out.open() as stream:
                header, values = list(csv.reader(stream, delimiter=';'))
        start = header.index('CLUSTERID')
        row = dict(zip(header[start:], map(float, values[start:])))
        # 独立解析几何：到达旋转 +90°，离开旋转使第二条径仰角变成 +30°。
        expected = dict(CLUSTERID=7, POWER=-76.98970004336019, DELAY=123.5,
                        AoA=105, AoD=0, ASA=15, ASD=0, ZoA=90, ZoD=75, ZSA=0, ZSD=15)
        self.assertEqual(tuple(header[start:]), gcm.CLUSTER_FIELDS)
        self.assertEqual(len(header), len(values))
        for key, value in expected.items():
            self.assertAlmostEqual(row[key], value, places=10, msg=key)
        self.assertIn('synthetic', values[header.index('INFO')])

    def test_weighted_wrap_and_direction_roles(self):
        frame = sample()
        frame['rotations'] = {r: [[1,0,0],[0,1,0],[0,0,1]] for r in ('arrival','departure')}
        for p, az, power in zip(frame['paths'], (170,-170), (-80,-70)):
            p['power_db'] = power
            p['arrival'] = [math.cos(math.radians(az)), math.sin(math.radians(az)), 0]
            p['departure'] = p['arrival'][:]
        row = gcm.convert_frame(frame)[1][0]
        center = math.degrees(math.atan2(math.sin(math.radians(170))+10*math.sin(math.radians(-170)), math.cos(math.radians(170))+10*math.cos(math.radians(-170))))
        rms = math.sqrt((((170-center+180)%360-180)**2+10*((-170-center+180)%360-180)**2)/11)
        self.assertAlmostEqual(row['AoA'], center)
        self.assertAlmostEqual(row['ASA'], rms)
        frame['directions'] = dict(arrival='propagation', departure='opposite_propagation')
        flipped = gcm.convert_frame(frame)[1][0]
        self.assertAlmostEqual(abs((flipped['AoA']-row['AoA']+360)%360), 180)
        self.assertAlmostEqual(flipped['ASA'], row['ASA'])

    def test_los_and_order_and_exported_values(self):
        frame = sample()
        frame['propagation'] = 'LOS'
        second = copy.deepcopy(frame['clusters'][0])
        frame['clusters'][0].update(id=9, members=['p1'], power_db=-43, delay_ns=900)
        second.update(id=0, members=['p2'])
        frame['clusters'].append(second)
        common, rows = gcm.convert_frame(frame)
        self.assertEqual([r['CLUSTERID'] for r in rows], [9,0])
        self.assertEqual((rows[0]['POWER'], rows[0]['DELAY']), (-43,900))
        self.assertEqual(rows[0]['ASA'], 0)
        self.assertEqual(common['TIMESTAMP'], '15:02:33.324')

    def test_uplink_angle_roles(self):
        frame = sample()
        frame['source']['direction'] = 'uplink'
        row = gcm.convert_frame(frame)[1][0]
        self.assertAlmostEqual(row['AoA'], 0)
        self.assertAlmostEqual(row['AoD'], 105)
        self.assertAlmostEqual(row['ZoA'], 75)
        self.assertAlmostEqual(row['ZoD'], 90)

    def test_cli_repeated_cluster_columns(self):
        frame = sample()
        second = copy.deepcopy(frame['clusters'][0])
        frame['clusters'][0]['members'] = ['p1']
        second.update(id=8, members=['p2'])
        frame['clusters'].append(second)
        with tempfile.TemporaryDirectory() as temp:
            inp, out = Path(temp)/'two.json', Path(temp)/'two.csv'
            inp.write_text(json.dumps(frame))
            run = subprocess.run([sys.executable, str(MODULE), str(inp), str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            with out.open() as stream:
                header, values = list(csv.reader(stream, delimiter=';'))
            start = header.index('CLUSTERID')
            self.assertEqual(header[start:], list(gcm.CLUSTER_FIELDS)*2)
            self.assertEqual(len(header), len(values))
            self.assertEqual([values[start], values[start+11]], ['7','8'])
            self.assertEqual(header.count('CMIMPORTMODE'), 1)

    def test_negative_inputs(self):
        mutations = [
            lambda f: f['common'].pop('TIMESTAMP'),
            lambda f: f['common'].pop('BSZCOORD'),
            lambda f: f['common'].update(UEXCOORD=100000),
            lambda f: f['common'].update(DLFREQUENCY=0),
            lambda f: f['common'].update(ULFREQUENCY=100000),
            lambda f: f['common'].update(BSID=17),
            lambda f: f['common'].update(UEID=True),
            lambda f: f['common'].update(TIMESTAMP='24:00:00.000'),
            lambda f: f['common'].update(TIMESTAMP='1٥:0٢:3٣.٣٢٤'),
            lambda f: f['common'].update(SPEEDKMH=float('inf')),
            lambda f: f['common'].update(UEXCOORD=float('nan')),
            lambda f: f['source'].update(raw_paths=''),
            lambda f: f['paths'][0].update(batch_id='other'),
            lambda f: f['clusters'][0].update(batch_id='other'),
            lambda f: f['clusters'][0].update(members=['missing']),
            lambda f: f['clusters'][0].update(members=['p1','p2','p1']),
            lambda f: f['clusters'][0].update(members=['p1','p1']),
            lambda f: f['clusters'][0].update(members=['p1']),
            lambda f: f['clusters'][0].update(power_db=0),
            lambda f: f['clusters'][0].update(delay_ns=0),
            lambda f: f['clusters'][0].update(id=0),
            lambda f: f.update(propagation='LOS'),
            lambda f: f['rotations'].update(arrival=[[1,1,0],[0,1,0],[0,0,1]]),
            lambda f: f['rotations'].update(arrival=[[1,0,0],[0,2,0],[0,0,1]]),
            lambda f: f['rotations'].update(arrival=[[-1,0,0],[0,1,0],[0,0,1]]),
            lambda f: f['directions'].update(arrival='unknown'),
            lambda f: f['paths'][0].update(arrival=[0,0,0]),
            lambda f: f['paths'][0].update(arrival=[0,0,1]),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(case=i):
                frame = sample()
                mutate(frame)
                with self.assertRaises(ValueError):
                    gcm.convert_frame(frame)

    def test_ambiguous_center_and_spread_range(self):
        for angle in (180, 179):
            frame = sample()
            frame['paths'][1]['arrival'] = [math.cos(math.radians(angle)),math.sin(math.radians(angle)),0]
            if angle == 179:
                # 天顶角扩展 80°，大于手册上限 52°。
                frame['rotations']['arrival'] = [[1,0,0],[0,1,0],[0,0,1]]
                for p, zenith in zip(frame['paths'], (10,170)):
                    p['arrival'] = [math.sin(math.radians(zenith)),0,math.cos(math.radians(zenith))]
            with self.assertRaises(ValueError):
                gcm.convert_frame(frame)

    def test_cluster_limit(self):
        frame = sample()
        frame['paths'], frame['clusters'] = [], []
        for i in range(25):
            p = copy.deepcopy(sample()['paths'][0]); p['id'] = str(i)
            c = copy.deepcopy(sample()['clusters'][0]); c.update(id=i+1, members=[str(i)])
            frame['paths'].append(p); frame['clusters'].append(c)
        with self.assertRaises(ValueError):
            gcm.convert_frame(frame)

    def test_cli_rejection_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            inp, out = Path(temp)/'bad.json', Path(temp)/'out.csv'
            inp.write_text('{}'); out.write_text('保留原文件')
            run = subprocess.run([sys.executable, str(MODULE), str(inp), str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(out.read_text(), '保留原文件')
            self.assertIn('离线转换失败', run.stderr)


if __name__ == '__main__':
    unittest.main()
