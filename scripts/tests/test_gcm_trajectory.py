"""实际文件绑定的离线轨迹回归；不导入应用或仪器。"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('gcm_trajectory', ROOT / 'scripts/gcm_trajectory.py')
gcm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gcm)


class TrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        shutil.copytree(ROOT / 'scripts/fixtures/gcm_trajectory', self.base, dirs_exist_ok=True)
        self.doc = json.loads((self.base / 'input.json').read_text())
        self.evidence = json.loads((self.base / 'identity.json').read_text())

    def save(self, filename, value):
        data = json.dumps(value, ensure_ascii=False, indent=2).encode()
        (self.base / filename).write_bytes(data)
        return {'path': filename, 'sha256': hashlib.sha256(data).hexdigest()}

    def bind(self):
        """模拟生成端写出同批材料，测试有意识变动的语义而非只撞哈希门。"""
        for frame in self.doc['frames']:
            try:
                frame['model']['common']['TIMESTAMP'] = gcm._rounded_time(frame['time_seconds'])[2]
            except ValueError:
                pass
        self.evidence['frames_sha256'] = gcm.frames_sha256(self.doc['frames'])
        for f, e in zip(self.doc['frames'], self.evidence['frames']):
            e['frame_id'] = f['frame_id']
            e['frame_sha256'] = gcm.frames_sha256(f)
        for name in self.doc['inputs']:
            source = {'batch_id': self.doc['batch_id'], 'direction': self.doc['direction'], 'frames': []}
            for frame in self.doc['frames']:
                model = frame['model']
                record = {'frame_id': frame['frame_id']}
                if name == 'raw_paths':
                    record['paths'] = model['paths']
                    record['time_seconds'] = frame['time_seconds']
                    record['frame_index'] = frame['frame_index']
                elif name == 'final_membership':
                    record['clusters'] = [{'id': c['id'], 'members': c['members']} for c in model['clusters']]
                else:
                    record['model'] = {k: model[k] for k in ('common','clusters','propagation','directions','rotations')}
                source['frames'].append(record)
            self.doc['inputs'][name] = self.save(name+'.json', source)
        self.doc['identity_evidence'] = self.save('identity.json', self.evidence)
        links=[]
        for i in range(len(self.doc['frames'])-1):
            left={m['track_id']:m for m in self.evidence['frames'][i]['mapping']}
            right={m['track_id']:m for m in self.evidence['frames'][i+1]['mapping']}
            pairs=[{'track_id':t,'from_local_id':left[t]['local_id'],'to_local_id':right[t]['local_id'],
                    'from_member_ids':left[t]['member_ids'],'to_member_ids':right[t]['member_ids']}
                   for t in sorted(t for t in set(left)&set(right) if type(t) is int)]
            links.append({'from_frame_id':self.doc['frames'][i]['frame_id'],
                          'to_frame_id':self.doc['frames'][i+1]['frame_id'],'pairs':pairs})
        association={'schema':'gcm-associations/1','batch_id':self.doc['batch_id'],'direction':self.doc['direction'],
                     'frames_sha256':gcm.frames_sha256(self.doc['frames']),
                     'input_sha256':{k:v['sha256'] for k,v in self.doc['inputs'].items()},
                     'producer':{'name':'构造测试来源','version':'1','method':'显式构造身份真值，非算法推断'},'links':links}
        self.doc['association_evidence']=self.save('associations.json',association)

    def run_conversion(self):
        return gcm.convert_trajectory(self.doc, self.base)

    def test_38_preserve_time_power_slots_and_last_frame(self):
        header, rows, manifest = self.run_conversion()
        self.assertEqual(len(rows), 38)
        self.assertTrue(all(len(row) == len(header) for row in rows))
        self.assertFalse(manifest['formal_eligible'])
        self.assertFalse(manifest['hardware_called'])
        self.assertEqual(manifest['original_time_seconds'], [f['time_seconds'] for f in self.doc['frames']])
        self.assertEqual(manifest['timestamps'][-1], '00:00:37.018')
        slots = [i for i,h in enumerate(header) if h == 'CLUSTERID']
        self.assertEqual([[r[c] for c in slots] for r in rows], [[1,2]]*38)
        self.assertEqual(rows[0][slots[0]+1], -60)
        self.assertEqual(rows[1][slots[0]+1], -80)
        self.assertEqual(rows[-1][header.index('UEXCOORD')], 10+37*.73)
        self.assertGreaterEqual(min(manifest['intervals_ms']), 1000)
        self.assertGreater(max(manifest['intervals_ms']), min(manifest['intervals_ms']))

    def test_two_adjacent_frames(self):
        self.doc['frames'] = self.doc['frames'][:2]
        self.evidence['frames'] = self.evidence['frames'][:2]
        # 两点 .73m 不够25波长，使用30m；CLUSTER不套用PATH的30m上限。
        self.doc['frames'][1]['model']['common']['UEXCOORD'] = 41
        self.bind()
        self.assertEqual(len(self.run_conversion()[1]), 2)

    def test_real_provenance_with_content_bound_evidence_supported(self):
        # 构造真实来源接口的文件契约；不是实测传播数据。
        self.doc['provenance'] = 'real'
        for f in self.doc['frames']:
            f['model']['source']['kind'] = 'real'
        self.bind()
        self.assertEqual(self.run_conversion()[2]['provenance'], 'real')
        self.assertFalse(self.run_conversion()[2]['formal_eligible'])

    def test_actual_files_not_just_hash_claims(self):
        for name in ('raw_paths','final_membership','cluster_export','identity_evidence'):
            with self.subTest(name=name):
                doc=copy.deepcopy(self.doc)
                ref=doc[name] if name=='identity_evidence' else doc['inputs'][name]
                ref['path']='missing.json'
                with self.assertRaises(ValueError):
                    gcm.convert_trajectory(doc,self.base)

    def test_file_byte_hash_verified(self):
        path=self.base/'raw_paths.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'校验'):
            self.run_conversion()

    def test_changed_input_not_bound(self):
        self.doc['frames'][0]['time_seconds'] = '0.0001'
        self.evidence['frames'][0]['frame_sha256'] = gcm.frames_sha256(self.doc['frames'][0])
        self.doc['identity_evidence'] = self.save('identity.json', self.evidence)
        with self.assertRaisesRegex(ValueError,'绑定'):
            self.run_conversion()

    def test_actual_source_mismatch_even_with_new_hash(self):
        for name in self.doc['inputs']:
            with self.subTest(name=name):
                original=copy.deepcopy(self.doc['inputs'][name])
                source=json.loads((self.base/original['path']).read_text())
                source['frames'][0]['frame_id']='other'
                self.doc['inputs'][name]=self.save(name+'.json',source)
                with self.assertRaisesRegex(ValueError,'帧ID'):
                    self.run_conversion()
                source['frames'][0]['frame_id']='f00'
                self.doc['inputs'][name]=self.save(name+'.json',source)

    def test_reject_unknown_or_real_without_evidence(self):
        for provenance in ('unknown',None,'real'):
            doc=copy.deepcopy(self.doc);doc['provenance']=provenance;doc.pop('identity_evidence')
            with self.subTest(provenance=provenance),self.assertRaises(ValueError):
                gcm.convert_trajectory(doc,self.base)

    def test_birth_death_same_slot_rejected(self):
        for e in self.evidence['frames'][20:]:
            e['mapping'][1]['track_id']=3
        self.bind()
        with self.assertRaisesRegex(ValueError,'出生|消失'):
            self.run_conversion()

    def test_continuing_track_with_frame_local_path_id(self):
        frame = self.doc['frames'][1]['model']
        path = next(p for p in frame['paths'] if p['id'] == 'p1')
        path['id'] = 'frame1-ray42'
        cluster = next(c for c in frame['clusters'] if c['members'] == ['p1'])
        extra=copy.deepcopy(path)
        extra['id']='frame1-ray99'
        extra['power_db']=-85
        frame['paths'].append(extra)
        cluster['members'] = [path['id'],extra['id']]
        mapping = next(m for m in self.evidence['frames'][1]['mapping']
                       if m['local_id'] == cluster['id'])
        cluster['id']=42
        mapping['local_id']=42
        mapping['member_ids'] = sorted(cluster['members'])
        self.bind()
        header, rows, manifest = self.run_conversion()
        slot = mapping['slot']
        column = [i for i, field in enumerate(header) if field == 'CLUSTERID'][slot]
        self.assertEqual([row[column] for row in rows[:3]], [mapping['track_id']] * 3)

    def test_same_named_members_without_independent_associations_rejected(self):
        self.doc.pop('association_evidence',None)
        with self.assertRaises(ValueError):self.run_conversion()

    def test_association_source_mismatch_rejected_even_with_valid_file_hash(self):
        association=json.loads((self.base/'associations.json').read_bytes())
        association['links'][0]['pairs'][0]['to_local_id']=999
        self.doc['association_evidence']=self.save('associations.json',association)
        with self.assertRaisesRegex(ValueError,'独立跨帧关联'):
            self.run_conversion()

    def test_mapping_rejected(self):
        for mode in ('missing','duplicate','slot_change','unknown','wrong_members'):
            evidence=copy.deepcopy(self.evidence)
            m=self.evidence['frames'][1]['mapping']
            if mode=='missing': m.pop()
            elif mode=='duplicate':m[1]['track_id']=1
            elif mode=='slot_change':m[0]['slot'],m[1]['slot']=1,0
            elif mode=='unknown':m[0]['track_id']=None
            else:m[0]['member_ids']=['p2']
            self.bind()
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_conversion()
            self.evidence=evidence
        self.bind()

    def test_direction_batch_and_members_must_match_actual_content(self):
        for mode in ('direction','batch','members','frame_index'):
            doc=copy.deepcopy(self.doc)
            if mode=='direction':doc['frames'][1]['model']['source']['direction']='uplink'
            elif mode=='batch':doc['frames'][1]['model']['paths'][0]['batch_id']='other'
            elif mode=='members':doc['frames'][1]['model']['clusters'][0]['members']=['not-there']
            else:doc['frames'][1]['frame_index']=3
            original=self.doc;self.doc=doc;self.bind()
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_conversion()
            self.doc=original
        self.bind()

    def test_spacing_0299_reject_073_pass(self):
        self.doc['frames'][1]['model']['common']['UEXCOORD']=10.299
        self.bind()
        with self.assertRaisesRegex(ValueError,'0.3'):self.run_conversion()
        self.doc['frames'][1]['model']['common']['UEXCOORD']=10.73
        self.bind()
        self.assertEqual(len(self.run_conversion()[1]),38)

    def test_fdd_and_coordinate_limits_rejected(self):
        for mode in ('fdd','origin','link_distance'):
            original=copy.deepcopy(self.doc)
            if mode=='fdd':self.doc['frames'][1]['model']['common']['ULFREQUENCY']=3400
            elif mode=='origin':self.doc['frames'][1]['model']['common']['UEXCOORD']=100000
            else:
                for frame in self.doc['frames']:
                    frame['model']['common'].update(BSXCOORD=-99999,UEXCOORD=99999)
            self.bind()
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_conversion()
            self.doc=original
        self.bind()

    def test_route_25_wavelength_minimum(self):
        self.doc['frames']=self.doc['frames'][:2];self.evidence['frames']=self.evidence['frames'][:2]
        self.bind()
        with self.assertRaisesRegex(ValueError,'25'):self.run_conversion()

    def test_decimal_rounding_collision_reverse_and_day_boundary(self):
        self.doc['frames'][1]['time_seconds']='1.0005';self.bind()
        self.assertEqual(self.run_conversion()[2]['timestamps'][1],'00:00:01.001')
        for value in ('0.0004','0','-1','NaN','86400','86399.9999'):
            self.doc['frames'][1]['time_seconds']=value;self.bind()
            with self.subTest(value=value),self.assertRaises(ValueError):self.run_conversion()

    def test_source_timing_and_index_not_replaced_by_wrapper(self):
        for key, value in (('time_seconds', '1.5'), ('frame_index', 2)):
            doc=copy.deepcopy(self.doc)
            doc['frames'][1][key]=value
            evidence=copy.deepcopy(self.evidence)
            evidence['frames_sha256']=gcm.frames_sha256(doc['frames'])
            evidence['frames'][1]['frame_sha256']=gcm.frames_sha256(doc['frames'][1])
            doc['identity_evidence']=self.save('modified-identity.json', evidence)
            with self.subTest(key=key),self.assertRaises(ValueError):
                gcm.convert_trajectory(doc,self.base)
        self.assertEqual(gcm._rounded_time('1.0004999999999999999999999999999999999')[1],1000)
        self.assertEqual(gcm._rounded_time('1.0005000000000000000000000000000000000')[1],1001)

    def test_cli_positive_and_failure_do_not_create_output(self):
        output=self.base/'result'
        result=subprocess.run([sys.executable,str(ROOT/'scripts/gcm_trajectory.py'),str(self.base/'input.json'),str(output)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        manifest=json.loads((output/'evidence.json').read_text())
        self.assertEqual(hashlib.sha256((output/'trajectory.csv').read_bytes()).hexdigest(),manifest['csv_sha256'])
        self.doc.pop('identity_evidence');self.save('bad.json',self.doc)
        bad=self.base/'bad-result'
        result=subprocess.run([sys.executable,str(ROOT/'scripts/gcm_trajectory.py'),str(self.base/'bad.json'),str(bad)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertFalse(bad.exists())


if __name__ == '__main__':unittest.main()
