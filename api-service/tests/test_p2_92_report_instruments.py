from datetime import datetime
from types import SimpleNamespace

import pytest

from app.hal.base_station_compatibility import canonical_payload_digest
from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from tests.test_p2_66_execution_evidence_outcome import _freeze
from tests.test_p2_21_report_flags_cert_cjk import _rendered_text


def _execution():
    frozen = _freeze()
    frozen['resolved_binding']['expected_transport'] = {
        'host': '192.168.1.132', 'port': None,
        'resource': 'TCPIP0::192.168.1.132::hislip0::INSTR',
    }
    frozen['digest'] = canonical_payload_digest({k: v for k, v in frozen.items() if k != 'digest'})
    return SimpleNamespace(id='execution-1', config={FREEZE_CONFIG_KEY: frozen},
                           measurements={}, status='completed', started_at=None,
                           completed_at=None, duration_sec=1, validation_pass=None)


@pytest.mark.parametrize('custom', [False, True])
def test_frozen_instrument_configuration_is_mandatory_readable_pdf(custom, tmp_path):
    from app.services.pdf_generator import PDFGenerator
    from pypdf import PdfReader
    ex = _execution()
    ex.config['credentials'] = {'password': 'DO-NOT-EXPORT'}
    content = _build_mimo_ota_content_data(ex, datetime.utcnow())
    inventory = content['instrument_configuration']
    row = inventory['instruments'][0]
    assert row['category'] == 'baseStation'
    assert row['model'] == 'UXM 5G E7515B'
    assert row['endpoint'] == 'TCPIP0::192.168.1.132::hislip0::INSTR'
    assert row['provenance'] == 'frozen_request'
    assert 'DO-NOT-EXPORT' not in str(inventory)
    path = tmp_path / 'instrument.pdf'
    template = {'sections': [{'type': 'cover', 'order': 0}]} if custom else None
    PDFGenerator().generate_report(content, template, str(path))
    text = '\n'.join(page.extract_text() for page in PdfReader(path).pages)
    assert '测试仪器配置' in text and '192.168.1.132' in text
    assert '冻结配置请求' in text and '不代表实测确认' in text


@pytest.mark.parametrize('invalid', ['missing', 'tampered'])
def test_missing_or_tampered_freeze_cannot_read_current_instruments(invalid):
    ex = _execution()
    if invalid == 'missing':
        ex.config = {}
    else:
        ex.config[FREEZE_CONFIG_KEY]['resolved_binding']['expected_transport']['host'] = 'BAD-HOST'
    ex.test_case = SimpleNamespace(configuration={'endpoint': 'CURRENT-ENDPOINT'})
    content = _build_mimo_ota_content_data(ex, datetime.utcnow())
    row = content['instrument_configuration']['instruments'][0]
    assert row['model'] is None and row['endpoint'] is None
    assert row['provenance'] == 'unavailable'
    assert 'CURRENT-ENDPOINT' not in str(content['instrument_configuration'])


def test_mock_instrument_configuration_is_not_live_identity():
    ex = _execution()
    frozen = ex.config[FREEZE_CONFIG_KEY]
    frozen['resolution']['execution_mode'] = 'simulated'
    frozen['digest'] = canonical_payload_digest({k: v for k, v in frozen.items() if k != 'digest'})
    content = _build_mimo_ota_content_data(ex, datetime.utcnow())
    assert content['instrument_configuration']['instruments'][0]['execution_mode'] == 'simulated'
    assert '模拟' in _rendered_text(content)


def test_channel_emulator_snapshot_does_not_follow_current_connection(db):
    from tests.test_p2_58_channel_emulator_freeze import _configured, _hal, _f64, _execution as ce_execution
    from app.services.channel_emulator_binding import freeze_channel_emulator_binding, CE_FREEZE_CONFIG_KEY
    from app.services.mimo_ota.report_traceability import report_instrument_configuration
    _, _, connection, lab = _configured(db)
    execution = ce_execution(db)
    freeze_channel_emulator_binding(db, _hal(_f64()), execution, lab)
    connection.endpoint = 'CURRENT-MUST-NOT-LEAK'
    row = report_instrument_configuration(execution, {})['instruments'][1]
    assert row['model'] == 'PROPSIM F64' and row['endpoint'] == '192.0.2.10'
    execution.config[CE_FREEZE_CONFIG_KEY]['digest'] = 'broken'
    assert report_instrument_configuration(execution, {})['instruments'][1]['endpoint'] is None


from tests.test_p2_58_channel_emulator_freeze import db


def test_malformed_historical_inventory_fails_closed_without_crashing():
    from app.services.mimo_ota.report_traceability import report_instrument_configuration
    payload = {'resolved_binding': 'malformed historical binding'}
    frozen = {**payload, 'digest': canonical_payload_digest(payload)}
    ex = SimpleNamespace(config={FREEZE_CONFIG_KEY: frozen})
    assert report_instrument_configuration(ex, {})['instruments'][0]['model'] is None


def test_malformed_historical_route_is_not_projected():
    from app.services.mimo_ota.report_traceability import report_instrument_configuration
    payload = {'resolved_binding': {}, 'resolution': {'profile': {'lte_2x2_internal_route': 'pcc_bb_board'}}}
    frozen = {**payload, 'digest': canonical_payload_digest(payload)}
    ex = SimpleNamespace(config={FREEZE_CONFIG_KEY: frozen})
    assert report_instrument_configuration(ex, {})['instruments'][0]['route'] is None


def test_historical_scalar_fields_cannot_export_nested_credentials():
    from app.services.mimo_ota.report_traceability import report_instrument_configuration
    secret = {'password': 'SHOULD-NOT-BE-EXPORTED'}
    payload = {'resolved_binding': {'manifest': {'model_name': secret, 'adapter_id': secret},
                                   'expected_transport': {'resource': secret, 'host': secret}},
               'resolution': {'execution_mode': secret}}
    frozen = {**payload, 'digest': canonical_payload_digest(payload)}
    result = report_instrument_configuration(SimpleNamespace(config={FREEZE_CONFIG_KEY: frozen}), {})
    assert 'SHOULD-NOT-BE-EXPORTED' not in str(result)
    assert result['instruments'][0]['model'] is None


@pytest.mark.parametrize('host,expected', [('192.168.1.132', '192.168.1.132:5025'),
                                         ('::1', '[::1]:5025'), ('[::1]', '[::1]:5025')])
def test_raw_tcp_endpoint_includes_frozen_port(host, expected):
    from app.services.mimo_ota.report_traceability import report_instrument_configuration
    ex = _execution()
    frozen = ex.config[FREEZE_CONFIG_KEY]
    frozen['resolved_binding']['expected_transport'] = {'host': host, 'port': 5025, 'resource': None}
    frozen['digest'] = canonical_payload_digest({k: v for k, v in frozen.items() if k != 'digest'})
    assert report_instrument_configuration(ex, {})['instruments'][0]['endpoint'] == expected


@pytest.mark.parametrize('mode', ['real', 'simulated'])
def test_positioner_frozen_adapter_mode_and_endpoint_are_displayed(mode):
    from app.services.mimo_ota.report_traceability import report_instrument_configuration
    from app.services.positioner_coordinate_profile import FREEZE_CONFIG_KEY as KEY, _canonical_digest
    payload = {'schema_version': 1, 'resolution': {'schema_version': 1, 'adapter': 'aerotech',
               'execution_mode': mode, 'status': 'verified' if mode == 'real' else 'diagnostic'},
               'expected_driver_connection': {'host': '192.168.0.16', 'port': 8000, 'resource': None} if mode == 'real' else None,
               'profile': {'schema_version': 1, 'user_units': 'degree', 'units_verified': True,
                           'coordinate_offset_deg': 0, 'coordinate_offset_verified': True,
                           'coordinate_offset_verification_source': 'site verification',
                           'coordinate_offset_verified_at': '2026-10-08T00:00:00Z',
                           'minimum_deg': -360, 'maximum_deg': 360, 'xf_speed': 10,
                           'position_tolerance_deg': .5, 'azimuth_axis': 'X'} if mode == 'real' else None}
    freeze = {**payload, 'digest': _canonical_digest(payload)}
    ex = SimpleNamespace(config={KEY: freeze})
    row = report_instrument_configuration(ex, {})['instruments'][2]
    assert row['adapter'] == 'aerotech' and row['execution_mode'] == mode
    assert row['endpoint'] == ('192.168.0.16:8000' if mode == 'real' else None)
    freeze['digest'] = 'broken'
    assert report_instrument_configuration(ex, {})['instruments'][2]['adapter'] is None
