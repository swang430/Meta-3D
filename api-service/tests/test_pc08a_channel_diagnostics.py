"""四类模拟/未验证信道材料不得作为正式测量。"""
import copy
from datetime import datetime, timedelta
import pytest
from tests.test_pc08a_temporal_boundary import db, client
from app.models.channel_calibration import DopplerCalibration, SpatialCorrelationCalibration, AngularSpreadCalibration, EISValidation
from app.services.channel_calibration_service import ChannelCalibrationService
from app.services.calibration_report_generator import CalibrationReportGenerator

CASES = [
    ('doppler', 'doppler', DopplerCalibration, dict(velocity_kmh=30,expected_doppler_hz=100,measured_spectrum={'frequency_bins_hz':[0], 'power_density_db':[-20]},reference_spectrum={},spectral_correlation=.99), 'spectral_correlation', 'measured_spectrum'),
    ('spatial_correlation', 'spatial-correlation', SpatialCorrelationCalibration, dict(scenario_type='UMa',scenario_condition='LOS',antenna_spacing_wavelengths=.5,measured_correlation_magnitude=.8), 'measured_correlation_magnitude', None),
    ('angular_spread', 'angular-spread', AngularSpreadCalibration, dict(scenario_type='UMa',scenario_condition='LOS',measured_aps={'azimuth_deg':[0], 'power_db':[-20]},fitted_rms_angular_spread_deg=15), 'fitted_rms_angular_spread_deg', 'measured_aps'),
    ('eis', 'eis', EISValidation, dict(dut_model='legacy',eis_map={'eis_dbm':[[-90]]},peak_eis_dbm=-90), 'peak_eis_dbm', 'eis_map'),
]

@pytest.mark.parametrize('kind,path,model,values,metric,array', CASES)
def test_legacy_all_consumers_are_unknown_and_original_is_preserved(db,client,kind,path,model,values,metric,array):
    service=ChannelCalibrationService(db);session=service.create_session(name='legacy')
    row=model(session_id=session.id,fc_ghz=3.5,validation_pass=True,status='valid',valid_until=datetime.utcnow()+timedelta(days=30),**values)
    db.add(row);db.commit();db.refresh(row)
    original={c.name:copy.deepcopy(getattr(row,c.name)) for c in model.__table__.columns}
    response=client.get(f'/api/v1/calibration/channel/{path}/{row.id}')
    assert response.status_code==200,response.text
    result=response.json();assert result['validation_pass'] is None and result['status']=='unknown'
    assert result[metric] is None
    if array: assert result[array]=={}
    assert result['diagnostic_data']['provenance']['source']=='unknown'
    assert result['diagnostic_data']['recorded_results'][metric]==values[metric]
    for verdict in ['true','false']:
        history=client.get('/api/v1/calibration/channel/history',params={'calibration_type':kind,'validation_pass':verdict})
        assert history.status_code==200 and history.json()['items']==[]
    session.overall_pass=True;session.passed_calibrations=1;db.commit()
    view=client.get(f'/api/v1/calibration/channel/sessions/{session.id}')
    assert view.status_code==200,view.text
    assert view.json()['overall_pass'] is None and view.json()['passed_calibrations']==0
    report=CalibrationReportGenerator(db)._collect_channel_data(session.id)
    assert report['execution_summary']['passed']==0
    assert report['execution_summary']['undetermined']==1
    assert report['execution_summary']['pass_rate'] is None
    assert report['channel_calibration'][kind][0]['validation_pass'] is None
    completed=service.complete_session(session.id,True,1,1,0)
    assert completed.overall_pass is None and completed.passed_calibrations==0
    db.refresh(row)
    assert {c.name:getattr(row,c.name) for c in model.__table__.columns}==original

@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['doppler','spatial_correlation','angular_spread','eis'])
async def test_new_simulated_writers_preserve_source_without_formal_verdict(db,kind):
    service=ChannelCalibrationService(db);session=service.create_session(name='simulated')
    if kind=='doppler':row=await service.run_doppler_calibration(30,3.5,session_id=session.id)
    elif kind=='spatial_correlation':row=await service.run_spatial_correlation_calibration('UMa','LOS',3.5,.5,session_id=session.id)
    elif kind=='angular_spread':row=service.run_angular_spread_calibration('UMa','LOS',3.5,session_id=session.id)
    else:row=service.run_eis_validation(dut_model='mock',dut_type='vehicle',fc_ghz=3.5,session_id=session.id)
    assert row.validation_pass is None and row.valid_until is None and row.status=='unknown'
    assert row.diagnostic_provenance['source']=='simulated'
    assert row.diagnostic_provenance['formal_eligible'] is False
    db.refresh(session);assert kind in session.configuration['requested_calibration_types']

@pytest.mark.asyncio
@pytest.mark.parametrize('actual_mock', [True,False])
async def test_real_request_does_not_prove_real_or_qualified_measurement(db,monkeypatch,actual_mock):
    from types import SimpleNamespace
    from app.hal.signal_analyzer import MockSignalAnalyzer
    from app.services import instrument_hal_service
    class UnverifiedAnalyzer:
        async def measure_doppler_spectrum(self, **kwargs):
            import numpy as np
            count=kwargs['num_bins'];return np.linspace(-1,1,count).tolist(),np.linspace(-30,-10,count).tolist()
    driver=MockSignalAnalyzer('isolated',{}) if actual_mock else UnverifiedAnalyzer()
    monkeypatch.setattr(instrument_hal_service,'get_hal_service',lambda:SimpleNamespace(drivers={'signalAnalyzer':driver}))
    row=await ChannelCalibrationService(db).run_doppler_calibration(30,3.5,use_mock=False)
    assert row.diagnostic_provenance['source']==('simulated' if actual_mock else 'unverified')
    assert row.validation_pass is None

@pytest.mark.parametrize('kind,body', [
    ('doppler', {'velocity_kmh':30,'fc_ghz':3.5,'calibrated_by':'test'}),
    ('spatial-correlation', {'scenario':{'type':'UMa','condition':'LOS','fc_ghz':3.5},'test_dut':{'antenna_spacing_wavelengths':.5},'calibrated_by':'test'}),
    ('angular-spread', {'scenario':{'type':'UMa','condition':'LOS','fc_ghz':3.5},'calibrated_by':'test'}),
    ('eis', {'test_config':{'fc_ghz':3.5},'dut':{'type':'vehicle','model':'simulation'},'min_eis_dbm':-80,'measured_by':'test'}),
])
def test_actual_start_http_creates_only_diagnostic_records(client,kind,body):
    response=client.post(f'/api/v1/calibration/channel/{kind}/start',json=body)
    assert response.status_code==202,response.text
    detail=client.get(f"/api/v1/calibration/channel/{kind}/{response.json()['calibration_job_id']}")
    assert detail.status_code==200,detail.text
    data=detail.json();assert data['validation_pass'] is None
    assert data['diagnostic_data']['provenance']['source']=='simulated'
    if kind=='eis':assert data['min_eis_dbm']==-80

@pytest.mark.asyncio
async def test_failed_real_request_keeps_session_scope(db,monkeypatch):
    from types import SimpleNamespace
    from app.services import instrument_hal_service
    service=ChannelCalibrationService(db);session=service.create_session(name='failed request')
    monkeypatch.setattr(instrument_hal_service,'get_hal_service',lambda:SimpleNamespace(drivers={}))
    with pytest.raises(RuntimeError):
        await service.run_doppler_calibration(30,3.5,session_id=session.id,use_mock=False)
    db.refresh(session);assert session.configuration['requested_calibration_types']==['doppler']
    data=CalibrationReportGenerator(db)._collect_channel_data(session.id)
    assert data['execution_summary']['undetermined']==1 and data['execution_summary']['pass_rate'] is None


def test_channel_contracts_match_live_and_checked():
    from pathlib import Path
    import yaml
    from app.main import app
    live=app.openapi();checked=yaml.safe_load((Path(__file__).parents[2]/'api/openapi.yaml').read_text())
    for kind,_,model,_,_,_ in CASES:
        name = 'EISValidationResponse' if kind=='eis' else model.__name__+'Response'
        assert checked['components']['schemas'][name]==live['components']['schemas'][name]
        assert 'diagnostic_data' in checked['components']['schemas'][name]['properties']


def test_old_temporal_manifest_cannot_authorize_four_other_methods(tmp_path):
    import json
    from app.api.calibration_report import _has_provenance_aware_calibration_manifest
    from app.services.calibration_report_generator import _write_report_provenance_manifest
    path=str(tmp_path/'report.pdf')
    (tmp_path/'report.pdf.provenance.json').write_text(json.dumps(dict(schema_version=2,path_loss_provenance_disclosed=True,quiet_zone_provenance_sanitized=True,temporal_method_sanitized=True)))
    assert not _has_provenance_aware_calibration_manifest(path)
    _write_report_provenance_manifest(path,{},path_loss_provenance_disclosed=True)
    assert _has_provenance_aware_calibration_manifest(path)


def test_provenance_migration_keeps_old_data_and_does_not_backfill(tmp_path):
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).parents[1]/'alembic/versions/d5e7f9012345_channel_diagnostic_provenance.py'
    spec=importlib.util.spec_from_file_location('migration',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=sa.create_engine('sqlite:///'+str(tmp_path/'legacy.db'))
    with engine.begin() as connection:
        for table in module.TABLES:
            connection.exec_driver_sql(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, original TEXT)')
            connection.exec_driver_sql(f"INSERT INTO {table} VALUES (1, 'original')")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade();module.upgrade()
            for table in module.TABLES:
                assert connection.exec_driver_sql(f'SELECT original, diagnostic_provenance FROM {table}').one()==('original',None)
            module.downgrade()
            for table in module.TABLES:
                assert connection.exec_driver_sql(f'SELECT original FROM {table}').scalar()=='original'
            module.upgrade()

@pytest.mark.parametrize('raw', ['legacy-note', ['unknown-source'], None])
def test_diagnostic_retains_nonobject_provenance_verbatim(db,client,raw):
    row=DopplerCalibration(fc_ghz=3.5,velocity_kmh=30,expected_doppler_hz=100,measured_spectrum={},reference_spectrum={},diagnostic_provenance=raw)
    db.add(row);db.commit()
    response=client.get(f'/api/v1/calibration/channel/doppler/{row.id}')
    assert response.status_code==200,response.text
    assert response.json()['diagnostic_data']['recorded_provenance']==raw
    assert response.json()['validation_pass'] is None
