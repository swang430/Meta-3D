"""32×2×5生产链验收：独立代数期望能抓到重复PA补偿与样本丢失。"""
import json
import os
from pathlib import Path
import time
import subprocess
import sys
from uuid import uuid4

import pytest


def samples_for(route_index, frequency_index):
    return [dict(source_before_dbm=-30.+j*.2, source_after_dbm=-29.8+j*.2,
                 received_dbm=-48.+route_index*.7+frequency_index*.3+j*.1)
            for j in range(5)]


def expected_for(route_index, frequency_index):
    # Lrx=2，j均值2；不调用生产损耗函数或PA/拓扑声明。
    return 16.3-route_index*.7-frequency_index*.3, .025**.5


def test_synthetic_graph_has_independent_paths_and_expected_table():
    from tests.pc04a8_browser_fixture import synthetic_graph_32
    graph = synthetic_graph_32()
    assert len(graph['nodes']) == 192 and len(graph['connections']) == 160
    assert len({n['id'] for n in graph['nodes']}) == 192
    assert len({e['id'] for e in graph['connections']}) == 160
    for i in range(32):
        prefix = f'synthetic-{i+1:02d}-'
        nodes = {n['id']: n for n in graph['nodes']}
        assert nodes[prefix+'ce']['params']['ce_port'] == f'B{i+1}'
        probe = nodes[prefix+'probe']['params']
        assert (probe['probe_id'], probe['polarization']) == (i//2, 'V' if i%2 == 0 else 'H')
        assert probe['rf_path_selection']['connection_ids'] == [prefix+'a', prefix+'b']
    assert expected_for(0, 0)[0] == 16.3
    assert expected_for(31, 1)[0] == pytest.approx(-5.7)


def matrix_body(manifest):
    chains = list(manifest['chain_to_index'])
    frequencies = [2595., 3500.]
    return dict(topology_id=manifest['matrix_id'], operating_mode='mimo_ota', chain_ids=chains,
        frequencies_mhz=frequencies, requested_power_dbm=-30., sample_count=5,
        fixed_route_confirmed=True, safety_confirmed=True,
        references=[dict(chain_id=c, frequency_mhz=f, reference_antenna='synthetic REF '+c,
            receive_cable_loss_db=2., receive_cable_source='synthetic, cable') for c in chains for f in frequencies],
        mock_inputs=[dict(chain_id=c, frequency_mhz=f, samples=samples_for(i,k),
            expected_loss_db=expected_for(i,k)[0]) for c,i in manifest['chain_to_index'].items()
            for k,f in enumerate(frequencies)])


def test_real_api_matrix_in_new_mock_database(tmp_path):
    # 子进程在任何app导入前新建隔离环境；不依赖CI/调用者默认DATABASE_URL。
    directory = Path(subprocess.check_output(['mktemp', '-d', '/tmp/pc04a8-XXXXXX'], text=True).strip())
    env = {**os.environ, 'DATABASE_URL':f'sqlite:///{directory}/test.sqlite',
        'USE_MOCK_INSTRUMENTS':'true', 'BOOTSTRAP_ON_STARTUP':'true', 'AUTH_MODE':'disabled',
        'LOG_DIR':str(directory/'logs')}
    output = Path(env.get('PC04A8_ACCEPTANCE_OUTPUT', str(directory/'evidence')))
    output.mkdir(parents=True, exist_ok=True)
    with (output/'subprocess.log').open('w') as log:
        result = subprocess.run([sys.executable, '-m', 'tests.test_pc04a8_acceptance'],
            env=env, stdout=log, stderr=subprocess.STDOUT, timeout=720)
    assert result.returncode == 0, f'隔离验收退出{result.returncode}；保留{output}/subprocess.log和{directory}'


def run_isolated_acceptance(output):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import SessionLocal
    from tests.pc04a8_browser_fixture import seed_world
    from tests.pc04a5d_browser_fixture import audit_mock, verify_hal
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation
    import asyncio
    # 只有新建且已bootstrap的/tmp隔离库可运行；全量同样使用独立full.sqlite。
    assert os.environ['DATABASE_URL'].startswith('sqlite:////tmp/pc04a8-')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    def save(name, value):
        (output/(name+'.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    with SessionLocal() as db:
        manifest = seed_world(db)
        manifest['mock_audit'] = audit_mock(db)
    manifest['actual_hal'] = asyncio.run(verify_hal())
    save('manifest', manifest)
    with TestClient(app) as client:
        lab = manifest['matrix_lab_id']
        base = f'/api/v1/lab-profiles/{lab}'
        response = client.get(base+'/route-calibration-paths', params=dict(topology_id=manifest['matrix_id'],
            operating_mode='mimo_ota', selection_scope='individual'))
        assert response.status_code == 200, response.text
        routes = response.json(); save('routes', routes)
        assert len(routes) == 32
        assert {r['chain_id'] for r in routes} == set(manifest['chain_to_index'])
        body = matrix_body(manifest); save('request', body)
        response = client.post(base+'/route-calibration-batches/preview', json=body)
        assert response.status_code == 200, response.text
        preview = response.json(); save('preview', preview)
        assert len(preview['items']) == 64
        body['preview_digest'] = preview['preview_digest']
        response = client.post(base+'/route-calibration-batches', json=body, headers={'Idempotency-Key':str(uuid4())})
        assert response.status_code == 202, response.text
        url = base+'/route-calibration-batches/'+response.json()['job_id']
        deadline = time.monotonic()+600
        transitions = []
        while time.monotonic() < deadline:
            value = client.get(url).json(); save('parent-last', value)
            if value['status'] == 'completed': break
            assert value['status'] not in ('failed','paused_failure','cleanup_unconfirmed','interrupted'), value
            if value['status'] == 'waiting_manual':
                item = value['items'][value['current_index']]
                transition = dict(item_id=item['item_id'], transition_id=value['transition_id'],
                    reference_antenna=item['request']['reference_antenna'], manual_confirmed=True, skip_failed=False)
                response = client.post(url+'/continue', json=transition)
                assert response.status_code == 200, response.text
                transitions.append(transition)
            time.sleep(.01)
        else: pytest.fail('批运行600秒超时，parent-last已保留')
        save('transitions', transitions); save('parent', value)
        assert len(value['items']) == 64 and value['finalization_committed'] is True
        assert value['f64_control_released'] is None
        children = [client.get(base+'/fixed-route-acquisitions/'+item['run_id']).json() for item in value['items']]
        save('children', children)
        assert len({(r['result']['request']['chain_id'],r['result']['request']['frequency_mhz']) for r in children}) == 64
        assert sum(len(r['result']['samples']) for r in children) == 320
        actual = []
        for record in children:
            result = record['result']; request = result['request']
            i = manifest['chain_to_index'][request['chain_id']]
            k = [2595.,3500.].index(request['frequency_mhz'])
            mean,std = expected_for(i,k)
            actual.append(dict(chain=request['chain_id'],frequency=request['frequency_mhz'],expected_mean=mean,
                expected_std=std,actual_mean=result['net_loss_db'],actual_std=result['sample_std_db'],
                mean_diff=result['net_loss_db']-mean,std_diff=result['sample_std_db']-std))
            assert record['status'] == 'simulated' and result['formal_eligible'] is False
            assert result['cleanup_confirmed'] is None
            assert result['simulation_input_source'] == 'operator_supplied_synthetic'
            assert result['net_loss_db'] == pytest.approx(mean,abs=1e-9)
            assert result['sample_std_db'] == pytest.approx(std,abs=1e-9)
        save('independent-expected-actual-diff', actual)
        from tests.test_pc06a1_batch_api import adoption
        response = client.post(base+'/route-calibration-applications',json=adoption(children[0]))
        save('adoption-rejection',dict(status=response.status_code,detail=response.json()))
        assert response.status_code == 422
        with SessionLocal() as db:
            frozen = resolve_effective_route_compensation(db,lab,'mimo_ota',2595.)
        save('formal-freeze',frozen)
        assert all(e['source_kind'] != 'confirmed_route' for e in frozen['route_entries'])
        # 完整批之后真正单路启动、取消、再进入；不混入上面的成功矩阵统计。
        # 非batch入口消费整图scope；individual选路的selected_route摘要不能用于单路。
        current = client.get(base+'/route-calibration-paths', params=dict(topology_id=manifest['matrix_id'],
            operating_mode='mimo_ota')).json()
        route = next(r for r in current if r['chain_id'] == preview['items'][0]['request']['chain_id'])
        single = {**preview['items'][0]['request'], 'configuration_digest':route['configuration_digest'],
            'route_digest':route['route_digest']}
        for cancel in (True,False):
            response = client.post(base+'/fixed-route-acquisitions',json=single)
            assert response.status_code == 202,response.text
            single_url = base+'/fixed-route-acquisitions/'+response.json()['run_id']
            if cancel: assert client.post(single_url+'/cancel').status_code == 200
            for _ in range(500):
                record = client.get(single_url).json()
                if record['status'] != 'running': break
                time.sleep(.01)
            save('single-cancel' if cancel else 'single-reentry',record)
            assert record['status'] == ('cancelled' if cancel else 'simulated')


if __name__ == '__main__':
    from tests.pc04a8_browser_fixture import bootstrap_mock_database
    manifest = bootstrap_mock_database('test')
    output = Path(os.environ.get('PC04A8_ACCEPTANCE_OUTPUT', str(Path(manifest['database']).parent/'evidence')))
    output.mkdir(parents=True, exist_ok=True)
    (output/'bootstrap.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    run_isolated_acceptance(output)
