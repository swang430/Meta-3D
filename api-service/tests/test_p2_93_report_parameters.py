from datetime import datetime

import pytest

from app.hal.base_station_compatibility import canonical_payload_digest
from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from tests.test_p2_92_report_instruments import _execution
from app.services.mimo_ota.report_traceability import SOURCE_KEY, capture_report_sources


@pytest.mark.parametrize('custom', [False, True])
def test_parameters_have_readable_mandatory_pdf_and_same_gui_content(custom, tmp_path):
    from app.services.pdf_generator import PDFGenerator
    from pypdf import PdfReader
    ex = _execution()
    frozen = ex.config[FREEZE_CONFIG_KEY]
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration, dump_canonical_mimo_ota_configuration
    frozen['mimo_ota_configuration'] = dump_canonical_mimo_ota_configuration(
        MIMOOTAConfiguration.model_validate(frozen['mimo_ota_configuration']))
    frozen[SOURCE_KEY] = capture_report_sources('one shot', {})
    frozen['digest'] = canonical_payload_digest({k: v for k, v in frozen.items() if k != 'digest'})
    content = _build_mimo_ota_content_data(ex, datetime.utcnow())
    rows = [r for group in content['parameter_groups'] for r in group['rows']]
    row = next(r for r in rows if r['path'] == 'target_rsrp_dbm')
    assert row['label'] == '目标 RSRP' and row['unit'] == 'dBm'
    assert row['requested'] == '-85' and '默认值' in row['source']
    assert row['applied'] == '未确认'
    assert {r['path'].split('[', 1)[0] for r in rows} >= set(content['execution_traceability']['parameters'])
    gui_rows = content['step_configs'][1:]
    assert gui_rows and any('目标 RSRP' in str(s) for s in gui_rows)
    output = tmp_path / 'parameters.pdf'
    PDFGenerator().generate_report(content, {'sections': [{'type': 'cover'}]} if custom else None, str(output))
    text = '\n'.join(p.extract_text() for p in PdfReader(output).pages)
    for expected in ('测试参数与生效值', '载波', 'MAC', '目标 RSRP', '-85', '默认值', '未确认', '不控制本次测量'):
        assert ''.join(expected.split()) in ''.join(text.split())


def test_long_azimuths_are_paginated_without_one_giant_table_row(tmp_path):
    from app.services.mimo_ota.report_parameter_presentation import report_parameter_groups
    from app.services.pdf_generator import PDFGenerator
    audit = {'status': 'frozen_request', 'parameters': {'azimuths_deg': {'requested': list(range(361)), 'source': 'saved_configuration'}}}
    groups = report_parameter_groups(audit)
    assert len(groups[0]['rows']) == 23
    assert all(len(row['requested']) < 110 for row in groups[0]['rows'])
    PDFGenerator().generate_report({'title': '方位', 'parameter_groups': groups}, None, str(tmp_path / 'long.pdf'))


@pytest.mark.parametrize('kind', ['confirmed', 'simulated', 'mismatch', 'unknown'])
def test_applied_value_requires_existing_confirmed_non_simulated_matching_receipt(kind):
    from app.services.mimo_ota.report_parameter_presentation import report_parameter_groups
    audit = {'status': 'frozen_request', 'parameters': {'target_tx_power_dbm': {'requested': -20, 'source': 'launch_default'}},
             'application_fields': {'config.downlink_power_dbm': {
                 'requested': -20 if kind != 'mismatch' else -30, 'applied': -19,
                 'status': 'confirmed' if kind != 'unknown' else 'unknown', 'simulated': kind == 'simulated', 'reason': 'fixture'}}}
    row = report_parameter_groups(audit)[0]['rows'][0]
    assert row['applied'] == ('-19' if kind == 'confirmed' else '未确认')
    if kind != 'confirmed':
        assert 'fixture' in row['note']


@pytest.mark.parametrize('ordered', [True, False, 'mixed'])
def test_custom_template_keeps_cover_then_parameters_before_results(ordered, tmp_path):
    from app.services.pdf_generator import PDFGenerator
    from pypdf import PdfReader
    sections = [{'type': 'cover'}, {'type': 'text', 'title': 'RESULT-MARKER', 'content_template': 'RESULT-MARKER'}]
    if ordered is True:
        for index, section in enumerate(sections):
            section['order'] = index
    elif ordered == 'mixed':
        sections[1]['order'] = 1
    path = tmp_path / 'order.pdf'
    PDFGenerator().generate_report({'title': 'COVER-MARKER', 'parameter_groups': []}, {'sections': sections}, str(path))
    text = '\n'.join(p.extract_text() for p in PdfReader(path).pages)
    assert text.index('COVER-MARKER') < text.index('测试参数与生效值') < text.index('RESULT-MARKER')


def test_historical_missing_parameters_have_no_new_defaults():
    from app.services.mimo_ota.report_parameter_presentation import report_parameter_groups
    assert report_parameter_groups({'status': 'unavailable', 'parameters': {}}) == []


def test_effective_channel_request_is_not_hidden_by_requested_engine():
    from app.services.pdf_generator import PDFGenerator
    audit = {'channel_load_request': {'effective_engine_mode': 'mimo_first_asc',
                                     'requested_load_mode': 'external_waveform'}}
    parts = PDFGenerator()._generate_parameter_groups_section({'parameter_groups': [], 'execution_traceability': audit})
    text = ' '.join(getattr(part, 'text', '') for part in parts)
    assert 'mimo_first_asc' in text and 'external_waveform' in text
    assert '不代表已加载' in text


def test_scheduler_reads_config_receipt_not_nonexistent_mac_control():
    from app.services.mimo_ota.report_parameter_presentation import report_parameter_groups
    audit = {'status': 'frozen_request', 'parameters': {'mac_profile.profile.scheduler_algorithm': {
        'requested': 'fixed', 'source': 'saved_configuration'}}, 'application_fields': {
            'config.scheduler_algorithm': {'requested': 'fixed', 'applied': 'fixed',
                'status': 'confirmed', 'simulated': False}}}
    assert report_parameter_groups(audit)[0]['rows'][0]['applied'] == 'fixed'


@pytest.mark.parametrize('field', ['bandwidth_mhz', 'band', 'lte_dl_earfcn', 'nr_arfcn', 'duplex', 'lte_transmission_mode', 'subcarrier_spacing_khz'])
def test_pcell_controls_consume_matching_receipts_without_borrowing_for_scell(field):
    from app.services.mimo_ota.report_parameter_presentation import report_parameter_groups
    audit = {'status': 'frozen_request', 'parameters': {
        f'component_carriers.{index}.{field}': {'requested': 100, 'source': 'saved_configuration'}
        for index in (0, 1)}, 'application_fields': {f'config.{field}': {
            'requested': 100, 'applied': 100, 'status': 'confirmed', 'simulated': False}}}
    rows = report_parameter_groups(audit)[0]['rows']
    assert rows[0]['applied'] == '100'
    assert rows[1]['applied'] == '未确认'
