"""模拟连接参数的HTTP保形保存、读取、删除及身份摘要。"""
import copy
import pytest
from tests.test_rf_chain_resolver import db_session,chamber,topology_two_chains,lab_profile
from tests.test_pc_04a_fixed_route_api import client,configured
from app.services.calibration.configuration_scope import build_calibration_scope,build_selected_route_calibration_scope
from app.services.calibration.route_calibration import list_route_selections


def test_saved_edge_model_roundtrip_scope_and_route_identity(client,configured,topology_two_chains,db_session):
    topo=topology_two_chains
    url=f'/api/v1/switch-topologies/{topo.id}'
    query={'lab_profile_id':str(configured.id)}
    def scope():return build_calibration_scope(db_session,configured.id,'mimo_ota',topology_id=topo.id)
    def route():return next(r for r in list_route_selections(db_session,configured.id,topo.id,'mimo_ota') if r.chain_id=='conn_p0v')
    initial_scope,initial_route=scope(),route()
    for loss in (1.25,2.5,None):
        saved=client.get(url,params=query).json()
        edges=copy.deepcopy(saved['connections'])
        if loss is None:edges[0].pop('simulation_model')
        else:edges[0]['simulation_model']={'frequency_mhz':2595.,'loss_db':loss}
        response=client.patch(url,params=query,json={'expected_revision':saved['revision'],'connections':edges})
        assert response.status_code==200,response.text
        fetched=client.get(url,params=query).json()
        assert fetched['connections']==edges
        db_session.expire_all()
        current_scope,current_route=scope(),route()
        selected=build_selected_route_calibration_scope(db_session,configured.id,'mimo_ota',topology_id=topo.id,chain_id='conn_p0v')
        projected=next(e for e in current_scope.payload.topology['connections'] if e['id']=='conn_p0v')
        if loss is None:
            assert 'simulation_model' not in projected
            assert current_scope.digest==initial_scope.digest
            assert current_route.route_digest==initial_route.route_digest
        else:
            assert projected['simulation_model']==edges[0]['simulation_model']
            assert current_scope.digest!=initial_scope.digest
            assert current_route.route_digest!=initial_route.route_digest
            assert selected.payload.topology['selected_route_digest']==current_route.route_digest


@pytest.mark.parametrize('model',[None,{'frequency_mhz':3500.,'loss_db':True},
    {'frequency_mhz':3500.,'loss_db':1.,'gain_db':2.}])
def test_invalid_edge_model_http_rejects_without_saving(client,configured,topology_two_chains,model):
    url=f'/api/v1/switch-topologies/{topology_two_chains.id}'
    query={'lab_profile_id':str(configured.id)}
    before=client.get(url,params=query).json()
    edges=copy.deepcopy(before['connections']);edges[0]['simulation_model']=model
    response=client.patch(url,params=query,json={'expected_revision':before['revision'],'connections':edges})
    assert response.status_code==422,response.text
    assert client.get(url,params=query).json()==before


def test_mode_membership_fallback_preserves_edge_model_in_scope(configured,topology_two_chains,db_session):
    topo=topology_two_chains
    modes=copy.deepcopy(topo.operating_modes);modes[0]['active_connections']=[];topo.operating_modes=modes
    edges=copy.deepcopy(topo.connections);edges[0]['simulation_model']={'frequency_mhz':2595.,'loss_db':1.25}
    topo.connections=edges;db_session.commit()
    snapshot=build_calibration_scope(db_session,configured.id,'mimo_ota',topology_id=topo.id)
    assert any(e.get('simulation_model')==edges[0]['simulation_model'] for e in snapshot.payload.topology['connections'])
