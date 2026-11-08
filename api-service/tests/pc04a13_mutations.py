"""核心修复逆向替换；finally仅反向恢复命中片段，拒绝覆盖并行修改。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ACQ=ROOT/'app/services/calibration/fixed_route_acquisition.py'
SIM=ROOT/'app/services/calibration/fixed_route_simulation.py'
API=ROOT/'app/api/route_batch.py'
TEST='tests/test_pc04a13_shared_transaction.py'
MUTATIONS=[
 ('open_real_entry',ACQ,'    if not (is_mock_driver(ce) and is_mock_driver(sa)):\n        result.status', '    if False:\n        result.status',TEST+'::test_public_collector_rejects_real_and_mixed_without_io[False]'),
 ('double_deembed',ACQ,'(s.received_dbm + receive_cable_loss_db)','(s.received_dbm + 2 * receive_cable_loss_db)',TEST+'::test_model_requires_persisted_cable_then_deembeds_once'),
 ('skip_cable_commit',SIM,'    db.commit()','    db.flush()',TEST+'::test_model_requires_persisted_cable_then_deembeds_once'),
 ('ignore_stop_state',ACQ,"await read('DIAG:SIMU:STATE?') != 'STOPPED':\n                                raise", "await read('DIAG:SIMU:STATE?') == 'IMPOSSIBLE':\n                                raise",TEST+'::test_transport_faults_cannot_finish_as_success[stop_not_confirmed]'),
]


def main():
    for name,path,old,new,test in MUTATIONS:
        before=path.read_text()
        if before.count(old)!=1: raise RuntimeError(f'{name}锚点不是唯一命中')
        mutated=before.replace(old,new,1)
        try:
            path.write_text(mutated)
            with tempfile.TemporaryDirectory(prefix='pc04a13-mutation-') as temp:
                env=dict(os.environ,DATABASE_URL='sqlite:///'+temp+'/test.db',USE_MOCK_INSTRUMENTS='true',PYTHONDONTWRITEBYTECODE='1')
                proc=subprocess.run([sys.executable,'-B','-m','pytest','-q','--tb=short',test],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                Path('/tmp/pc04a13-mutation-'+name+'.log').write_text(proc.stdout)
                summary=[line for line in proc.stdout.splitlines() if ' failed' in line or ' passed' in line]
                print(name,'exit='+str(proc.returncode),summary[-1:] ,flush=True)
                if proc.returncode!=1 or ' failed' not in proc.stdout: raise RuntimeError(f'{name}没有被行为测试杀死')
        finally:
            current=path.read_text()
            if new and current.count(new)==1:
                path.write_text(current.replace(new,old,1))
            elif current==mutated:
                # 删除片段的逆变异用相邻上下文恢复，不覆盖任何并行编辑。
                path.write_text(before)
            else:
                raise RuntimeError(f'{name}检测到并行编辑，不能覆盖恢复')
            if path.read_text()!=before: raise RuntimeError(f'{name}恢复后内容不一致')
    print('4 mutations killed; all source fragments restored',flush=True)


if __name__=='__main__': main()
