"""PC-04A-13隔离完整链路；模型系数均人为合成，不是用户图或实测。"""
import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import json
import sys

from tests.pc04a8_browser_fixture import bootstrap_mock_database


def full_graph():
    graph = dict(nodes=[], connections=[], operating_modes=[
        dict(id='mimo_ota', name='正常测试', active_connections=[]),
        dict(id='calibration', name='参考接线', active_connections=[])])
    for index in range(1, 33):
        prefix = f'pc13-{index:02d}-'
        def node(name, kind, offset, value=None, key='loss_db'):
            params = dict(ports=['in', 'out'], port_directions={'in': 'input', 'out': 'output'},
                          internal_paths=[dict(from_port='in', to_port='out')])
            if value is not None:
                params['simulation_model'] = dict(frequency_mhz=3500., **{key: value})
            return dict(id=prefix+name, type=kind, label=prefix+name,
                        position=dict(x=offset*180, y=index*150), params=params)
        nodes = [node('ce', 'ce_port', 0), node('tx1', 'cable', 1, 1.),
                 node('pa', 'amplifier', 2, 10., 'gain_db'), node('tx2', 'cable', 3, 2.),
                 node('probe', 'probe', 4, 3., 'gain_db'),
                 node('air', 'air_path', 5, 40.+index/10),
                 node('sgh', 'reference_antenna', 6, 4., 'gain_db'),
                 node('rx', 'receive_cable', 7, .2+index/100),
                 node('sa', 'signal_analyzer', 8)]
        nodes[0]['params'] = dict(ports=['out'], port_directions={'out':'output'}, ce_port=f'B{index}')
        nodes[4]['params'].update(probe_id=(index-1)//2, polarization='V' if index%2 else 'H')
        nodes[-1]['params'] = dict(ports=['in'], port_directions={'in':'input'})
        edges = []
        for position, (left, right) in enumerate(zip(nodes, nodes[1:])):
            mode = 'mimo_ota' if position < 4 else 'calibration'
            edge = dict(id=prefix+str(position), source=left['id'], source_pin='out',
                        target=right['id'], target_pin='in', modes=[mode])
            edges.append(edge)
            graph['operating_modes'][0 if mode=='mimo_ota' else 1]['active_connections'].append(edge['id'])
        nodes[4]['params']['rf_path_selection'] = dict(connection_ids=[e['id'] for e in edges[:4]], switch_mappings=[])
        for n in nodes[5:]:
            n['params']['connection_scope'] = 'calibration'
        graph['nodes'].extend(nodes)
        graph['connections'].extend(edges)
    return graph


def seed_world(db):
    from app.models.chamber import ChamberType, create_chamber_from_preset
    from app.models.instrument import InstrumentCategory
    from app.models.lab_profile import LabProfile
    from app.models.switch_topology import SwitchTopology
    chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name='PC13完整模拟隔离暗室')
    db.add(chamber); db.flush()
    lab = LabProfile(name='PC13完整模拟隔离实验室', chamber_config_id=chamber.id, is_active=True,
                     instrument_bindings=deepcopy(db.query(LabProfile).first().instrument_bindings))
    db.add(lab); db.flush()
    sa = db.query(InstrumentCategory).filter_by(category_key='signalAnalyzer').one()
    rf = db.query(InstrumentCategory).filter_by(category_key='rfSwitch').one()
    graph = full_graph()
    for node in graph['nodes']:
        if node['type']=='signal_analyzer':
            node['params']['instrument_category_id'] = str(sa.id)
    topology = SwitchTopology(name='PC13完整32路合成链路', chamber_id=chamber.id,
        switch_category_id=rf.id, is_active=True, is_default=False, **graph)
    topology.update_statistics(); db.add(topology); db.commit()
    return dict(lab_id=str(lab.id), topology_id=str(topology.id), chamber_id=str(chamber.id),
                chain_ids=[f'pc13-{i:02d}-3' for i in range(1,33)],
                expected_net_losses={f'pc13-{i:02d}-3':26+i/10 for i in range(1,33)},
                model_note='各链独立虚拟参考件；系数均人为合成。SGH接FSVA的阶段不连接VNA，不代表用户实物接线。')


if __name__ == '__main__':
    with redirect_stdout(sys.stderr):
        # 复用带目录/空库/Mock前置保护的既有bootstrap，故临时目录沿pc04a8前缀。
        result = bootstrap_mock_database('browser')
        from app.db.database import SessionLocal
        from tests.pc04a5d_browser_fixture import audit_mock, verify_hal
        with SessionLocal() as db:
            result.update(seed_world(db))
            result['mock_audit'] = audit_mock(db)
        result['selected_hal'] = asyncio.run(verify_hal())
    print(json.dumps(result, ensure_ascii=False, indent=2))
