"""PC06A2入口 专属新文件库：默认bootstrap目录，全类别Mock，不复用其他证据库。"""
import json
import os
import re
import sys
from pathlib import Path

_url = os.environ.get('DATABASE_URL', '')
_path = Path(_url.removeprefix('sqlite:///'))
_legacy = sys.argv[1:] == ['--seed-legacy']
if sys.argv[1:] not in ([], ['--seed-legacy']):
    raise RuntimeError('仅接受空参数或 --seed-legacy')
if (os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'
        or not re.fullmatch(r'sqlite:////tmp/pc06a2-entry-[A-Za-z0-9]+/browser.sqlite', _url)
        or not _path.parent.is_dir()
        or (not _legacy and _path.exists()) or (_legacy and not _path.is_file())):
    raise RuntimeError('仅允许mktemp新建/tmp/pc06a2-entry-*目录中的新文件SQLite及全Mock默认bootstrap')

from app.main import app
from app.db.database import Base, engine, SessionLocal
from app.services.bootstrap import run_bootstrap_on_startup
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology


def seed():
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal) is True
    with SessionLocal() as db:
        bindings = []
        categories = db.query(InstrumentCategory).all()
        assert categories
        for category in categories:
            category.driver_mode = 'mock'
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            # 默认目录保留空地址/FSW43；本专属全Mock夹具明确选已有首批支持型号，
            # 并只给测试连接写文档网段端点。生产绑定/资格门保持原样。
            if category.category_key == 'signalAnalyzer':
                selected = db.query(InstrumentModel).filter_by(category_id=category.id, model='FSVA3000').one()
                category.selected_model_id = selected.id
            if connection is not None and category.category_key in ('channelEmulator', 'signalAnalyzer'):
                connection.endpoint = '192.0.2.10' if category.category_key == 'channelEmulator' else '192.0.2.11'
            model = db.get(InstrumentModel, category.selected_model_id)
            if model is not None and connection is not None:
                bindings.append(dict(category_id=str(category.id), instrument_model_id=str(model.id),
                    connection_endpoint=connection.endpoint, driver_mode='mock'))
        switch = next(c for c in categories if c.category_key == 'rfSwitch')
        assert {'channelEmulator', 'signalAnalyzer'} <= {c.category_key for c in categories
            if c.selected_model_id and c.connection is not None}
        manifest = {'database': str(engine.url), 'labs': [], 'evidence_boundary': '全HAL Mock，非现场验收'}
        for suffix in ('甲', '乙'):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC06A2入口暗室{suffix}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC06A2入口{suffix}', chamber_config_id=chamber.id,
                is_active=True, instrument_bindings=bindings)
            db.add(lab); db.flush()
            nodes = [dict(id=f'ce{i}', type='ce_port', label=f'B1.{i}', position={'x':30,'y':60+(i-1)*240}, params={'ports':['out']}) for i in (1,2)]
            nodes += [dict(id=f'probe{i}', type='probe', label=f'探头0{pol}', position={'x':540,'y':60+(i-1)*240},
                params={'ports':['in'], 'probe_id':0, 'polarization':pol,
                    'rf_path_selection':{'connection_ids':[f'fixed-{pol.lower()}'], 'switch_mappings':[]}}) for i,pol in ((1,'V'),(2,'H'))]
            nodes += [dict(id='hidden-normal',type='pad',label='隐藏普通器件',position={'x':200,'y':500},params={'ports':['in','out'],'visible_modes':[],'unknown':{'keep':1}}),
                dict(id='hidden-calibration',type='receive_cable',label='隐藏校准器件',position={'x':400,'y':500},params={'ports':['in','out'],'visible_modes':[],'connection_scope':'calibration','unknown':{'keep':1}})]
            edges = [dict(id=f'fixed-{pol}', source=f'ce{i}', source_pin='out', target=f'probe{i}', target_pin='in', cable_loss_db=0) for i,pol in ((1,'v'),(2,'h'))]
            topology = SwitchTopology(switch_category_id=switch.id, chamber_id=chamber.id,
                name=f'PC06A2入口显式路径{suffix}', is_active=True, is_default=True, nodes=nodes, connections=edges,
                operating_modes=[dict(id='mimo_ota',name='MIMO OTA 测试',active_connections=['fixed-v','fixed-h']),
                    dict(id='calibration',name='校准接线',active_connections=[])])
            topology.update_statistics()
            db.add(topology); db.flush()
            manifest['labs'].append({'name':lab.name,'lab_id':str(lab.id),'chamber_id':str(chamber.id),'topology_id':str(topology.id),'switch_id':str(switch.id)})
        no_chamber = LabProfile(name='PC06A2入口无暗室', is_active=True, instrument_bindings=[])
        db.add(no_chamber); db.flush()
        manifest['labs'].append({'name': no_chamber.name, 'lab_id': str(no_chamber.id), 'chamber_id': None, 'topology_id': None})
        db.commit()
        assert all(c.driver_mode == 'mock' for c in categories)
        print(json.dumps(manifest,ensure_ascii=False))


def seed_legacy():
    """仅API暂停后显式补入旧记录；不清空、覆盖或重复seed。"""
    from datetime import datetime
    from app.models.calibration import SystemTRPCalibration, SystemTISCalibration, RepeatabilityTest, CalibrationCertificate
    from app.models.probe_calibration import CalibrationBaseline
    with SessionLocal() as db:
        labs = db.query(LabProfile).all()
        assert {row.name for row in labs} == {'PC06A2入口甲', 'PC06A2入口乙', 'PC06A2入口无暗室'}
        assert all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory).all())
        assert all(binding.get('driver_mode') == 'mock' for lab in labs for binding in lab.instrument_bindings)
        tables = (SystemTRPCalibration, SystemTISCalibration, RepeatabilityTest, CalibrationCertificate, CalibrationBaseline)
        assert all(db.query(model).count() == 0 for model in tables), '旧档案必须为空；禁止重复seed或清空'
        now = datetime(2026, 10, 26)
        for index in range(22):
            db.add(SystemTRPCalibration(standard_dut_model='隔离旧TRP',
                standard_dut_serial='fixture-trp' if index == 0 else f'fixture-trp-{index}',
                reference_trp_dbm=10, frequency_mhz=3500, measured_trp_dbm=10.2,
                trp_error_db=.2, absolute_error_db=.2, num_probes_used=1,
                validation_pass=True, threshold_db=.5, tested_at=now))
        db.add(SystemTISCalibration(standard_dut_model='隔离旧TIS', standard_dut_serial='fixture-tis',
            reference_tis_dbm=-90, frequency_mhz=3500, measured_tis_dbm=-88, tis_error_db=2,
            absolute_error_db=2, num_probes_used=1, validation_pass=False, threshold_db=1, tested_at=now))
        db.add(RepeatabilityTest(test_type='execution_metrics', measurements=[], num_runs=2,
            mean_dbm=None, std_dev_db=None, validation_pass=None, metric_deltas={}, tested_at=now))
        db.add(CalibrationCertificate(certificate_number='PC06A2-ISOLATED-LEGACY', system_name='隔离旧证书',
            calibration_date=now, valid_until=datetime(2027,10,26), issued_at=now,
            overall_pass=True, trp_pass=True, tis_pass=False, repeatability_pass=False, pdf_path=None))
        for name, frequency in (('PC06A2入口甲',2595), ('PC06A2入口乙',3500)):
            lab = next(row for row in labs if row.name == name)
            db.add(CalibrationBaseline(chamber_id=lab.chamber_config_id, calibration_type='path_loss',
                frequency_mhz=frequency, reference_channel_id=0, reference_value_db=10,
                delta_matrix={}, total_channels=1, baseline_date=now,
                valid_until=datetime(2027,10,26), status='valid'))
        db.commit()
        print(json.dumps({'database': str(engine.url), 'legacy_rows': {model.__tablename__: db.query(model).count() for model in tables},
            'formal_acceptance': False}, ensure_ascii=False))


if __name__ == '__main__':
    seed_legacy() if _legacy else seed()

