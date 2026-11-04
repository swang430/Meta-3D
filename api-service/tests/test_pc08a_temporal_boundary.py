"""时域代理不得升级为标准PDP；测试不访问真实仪器。"""
import copy
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.db.database import Base, get_db
from app.main import app
from app.models.channel_calibration import TemporalChannelCalibration
from app.services.channel_calibration_service import ChannelCalibrationService
from app.services.calibration_report_generator import CalibrationReportGenerator

@pytest.fixture
def db():
    engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db]=lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db,None)

def legacy(db, session_id=None):
    row=TemporalChannelCalibration(session_id=session_id,scenario_type='UMa',scenario_condition='LOS',fc_ghz=3.5,measured_pdp={'delay_bins_ns':[0,25],'power_db':[0,-6]},measured_rms_delay_spread_ns=10,reference_rms_delay_spread_ns=10,rms_error_percent=0,validation_pass=True,status='valid',valid_until=datetime.utcnow()+timedelta(days=30))
    db.add(row);db.commit();db.refresh(row);return row

@pytest.mark.asyncio
async def test_mock_capture_is_diagnostic_and_cannot_pass(db):
    row=await ChannelCalibrationService(db).run_temporal_calibration('UMa','LOS',3.5,use_mock=True)
    assert row.validation_pass is None
    assert row.status=='unknown' and row.valid_until is None
    assert row.rms_error_percent is None and row.cluster_count_match is None
    assert row.measured_pdp['provenance']['source']=='simulated'


def test_legacy_http_detail_history_status_are_unknown_without_rewriting(db,client):
    row=legacy(db);original=copy.deepcopy(row.measured_pdp)
    base='/api/v1/calibration/channel'
    for path in (f'/temporal/{row.id}','/temporal/latest'):
        r=client.get(base+path);assert r.status_code==200,r.text
        d=r.json();assert d['validation_pass'] is None and d['measured_pdp']=={}
        assert d['measured_rms_delay_spread_ns'] is None
        assert d['diagnostic_data']['recorded_pdp']==original
        assert d['diagnostic_data']['formal_eligible'] is False
    status=client.get(base+'/status').json()
    assert status['temporal_status']=='unknown' and status['temporal_next_due'] is None
    for verdict in ('true','false'):
        r=client.get(base+'/history',params={'calibration_type':'temporal','validation_pass':verdict})
        assert r.status_code==200,r.text
        assert r.json()['items']==[]
    db.refresh(row);assert row.validation_pass is True and row.measured_pdp==original


def test_temporal_cannot_make_session_or_report_pass(db):
    service=ChannelCalibrationService(db);session=service.create_session(name='diagnostic')
    row=legacy(db,session.id)
    completed=service.complete_session(session.id,True,1,1,0)
    assert completed.overall_pass is None and completed.passed_calibrations==0
    d=CalibrationReportGenerator(db)._collect_channel_data(session.id)
    summary=d['execution_summary']
    assert summary['passed']==0 and summary['undetermined']==1 and summary['pass_rate'] is None
    item=d['channel_calibration']['temporal'][0]
    assert item['validation_pass'] is None and item['rms_delay_spread_measured_ns'] is None
    db.refresh(row);assert row.validation_pass is True

@pytest.mark.asyncio
async def test_failed_temporal_request_remains_unknown_in_session_read_and_report(db,client,monkeypatch):
    from types import SimpleNamespace
    import app.services.instrument_hal_service as hal
    service=ChannelCalibrationService(db);session=service.create_session(name='failed capture')
    session.overall_pass=True;session.passed_calibrations=1;db.commit()
    monkeypatch.setattr(hal,'get_hal_service',lambda:SimpleNamespace(drivers={}))
    with pytest.raises(RuntimeError):
        await service.run_temporal_calibration('UMa','LOS',3.5,session_id=session.id,use_mock=False)
    db.refresh(session);assert 'temporal' in session.configuration['requested_calibration_types']
    r=client.get(f'/api/v1/calibration/channel/sessions/{session.id}')
    assert r.status_code==200,r.text
    assert r.json()['overall_pass'] is None
    report=CalibrationReportGenerator(db)._collect_report_data(session.id,None,False,True)
    assert report['session']['overall_pass'] is None
    assert report['execution_summary']['pass_rate'] is None
    db.refresh(session);assert session.overall_pass is True


def test_old_pdf_manifest_does_not_prove_temporal_sanitization(tmp_path):
    import json
    from app.api.calibration_report import _has_provenance_aware_calibration_manifest
    from app.services.calibration_report_generator import _write_report_provenance_manifest
    pdf=str(tmp_path/'report.pdf')
    manifest=tmp_path/'report.pdf.provenance.json'
    manifest.write_text(json.dumps(dict(schema_version=2,path_loss_provenance_disclosed=True,quiet_zone_provenance_sanitized=True)))
    assert not _has_provenance_aware_calibration_manifest(pdf)
    _write_report_provenance_manifest(pdf,{},path_loss_provenance_disclosed=True)
    assert _has_provenance_aware_calibration_manifest(pdf)


def test_temporal_contract_matches_runtime():
    from pathlib import Path
    import yaml
    root=Path(__file__).resolve().parents[2]
    checked=yaml.safe_load((root/'api/openapi.yaml').read_text())
    live=app.openapi()
    assert checked['components']['schemas']['TemporalCalibrationResponse']==live['components']['schemas']['TemporalCalibrationResponse']
    for path in ['/api/v1/calibration/channel/temporal/latest','/api/v1/calibration/channel/temporal/{calibration_id}']:
        assert checked['paths'][path]==live['paths'][path]
    assert 'diagnostic_data' in (root/'gui/src/types/api.generated.ts').read_text()


def test_autocorrelation_is_not_an_independent_pdp_reference():
    import numpy as np
    # 独立确定性反例：单个脉冲响应含两个实振幅径，FFT功率谱的IFFT有交叉项。
    h=np.zeros(16);h[0]=1;h[3]=0.5
    proxy=np.abs(np.fft.ifft(abs(np.fft.fft(h))**2))
    true_power=abs(h)**2
    assert proxy[3]/proxy[0] != pytest.approx(true_power[3]/true_power[0])
    assert proxy[-3] > 0 and true_power[-3] == 0

@pytest.mark.parametrize('requested',[1,True,{},'temporal'])
def test_arbitrary_session_configuration_is_not_a_type_error(client,requested):
    r=client.post('/api/v1/calibration/channel/sessions',json={'name':'legacy config','created_by':'isolated','configuration':{'requested_calibration_types':requested}})
    assert r.status_code==201,r.text
    assert client.get('/api/v1/calibration/channel/sessions/'+r.json()['id']).status_code==200

@pytest.mark.asyncio
async def test_real_request_bound_to_mock_driver_is_marked_simulated(db,monkeypatch):
    from types import SimpleNamespace
    from app.hal.signal_analyzer import MockSignalAnalyzer
    import app.services.instrument_hal_service as hal
    driver=MockSignalAnalyzer("isolated", {})
    monkeypatch.setattr(hal,'get_hal_service',lambda:SimpleNamespace(drivers={'signalAnalyzer':driver}))
    row=await ChannelCalibrationService(db).run_temporal_calibration('UMa','LOS',3.5,use_mock=False)
    assert row.measured_pdp['provenance']['source']=='simulated'
    assert row.validation_pass is None
