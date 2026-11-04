"""目标频点只读查询与真实执行冻结同源；不能据选源齐全签认证。"""
import pytest
from sqlalchemy import event
from uuid import uuid4

from tests.test_pc04a2_route_application import db_session, payload, confirm
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured
from tests.test_pc04a2_route_eligibility import real_capture
from tests.test_pc04a2_route_freeze import legacy, launch, entries


def read(client, lab, frequency=2595):
    return client.get(f'/api/v1/lab-profiles/{lab.id}/route-calibration-availability',
                      params={'frequency_mhz': frequency, 'operating_mode': 'mimo_ota'})


@pytest.mark.asyncio
async def test_target_preview_matches_execution_sources_without_writes(
        client, configured, real_capture, legacy, launch, db_session):
    saved = confirm(client, configured, payload(client, configured, real_capture())).json()
    writes = []
    def collect(connection, cursor, statement, *args):
        if statement.lstrip().upper().startswith(('UPDATE ', 'INSERT ', 'DELETE ')):
            writes.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, 'before_cursor_execute', collect)
    try:
        response = read(client, configured)
    finally:
        event.remove(engine, 'before_cursor_execute', collect)
    assert response.status_code == 200, response.text
    assert writes == []
    result = response.json()
    assert result['all_chains_have_sources'] is True
    assert result['covered_chain_count'] == result['required_chain_count'] == 2
    assert result['formal_scope_status'] == 'unknown'
    assert result['limitations']
    preview = {row['chain_id']: row for row in result['routes']}
    assert preview['conn_p0v']['source_id'] == saved['id']
    execution = await launch()
    for chain, actual in entries(execution).items():
        for field in ('source_kind', 'source_id', 'value_db', 'measurement_provenance', 'reason'):
            assert preview[chain][field] == actual[field]
    # 撤销后不能缓存旧可用状态；另一个独立旧证书仍按原判据可用。
    assert client.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications/{saved["id"]}/revocation',
        json={'confirmed': True, 'reason': '失效'}).status_code == 201
    refreshed = read(client, configured).json()
    rows = {row['chain_id']: row for row in refreshed['routes']}
    assert rows['conn_p0v']['source_kind'] == 'legacy_certificate'
    assert rows['conn_p0v']['source_id'] == str(legacy.id)
    missing = read(client, configured, 3500).json()
    assert missing['all_chains_have_sources'] is False and missing['covered_chain_count'] == 0
    assert all(row['value_db'] is None for row in missing['routes'])


def test_missing_source_is_not_qualified_and_frequency_must_be_explicit(client, configured, db_session):
    response = read(client, configured)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['required_chain_count'] == 2 and result['covered_chain_count'] == 0
    assert result['all_chains_have_sources'] is False and result['formal_scope_status'] == 'unknown'
    url = f'/api/v1/lab-profiles/{configured.id}/route-calibration-availability'
    for params in ({}, {'frequency_mhz': 0}, {'frequency_mhz': -1}, {'frequency_mhz': 'inf'}, {'frequency_mhz': 'nan'}):
        assert client.get(url, params=params).status_code == 422
    configured.chamber_config_id = None
    db_session.commit()
    empty = read(client, configured).json()
    assert empty['required_chain_count'] == 0 and empty['all_chains_have_sources'] is False
    assert empty['warnings']
    missing = client.get(f'/api/v1/lab-profiles/{uuid4()}/route-calibration-availability',
                         params={'frequency_mhz': 2595})
    assert missing.status_code == 400 and isinstance(missing.json()['detail'], str)


def test_target_availability_contract_matches_live_and_generated_types():
    from pathlib import Path
    import yaml
    from app.main import app
    root = Path(__file__).resolve().parents[2]
    checked = yaml.safe_load((root / 'api/openapi.yaml').read_text())
    live = app.openapi()
    route = '/api/v1/lab-profiles/{lab_profile_id}/route-calibration-availability'
    assert checked['paths'][route] == live['paths'][route]
    for name in ('RouteAvailabilityRow', 'RouteCalibrationAvailability'):
        assert checked['components']['schemas'][name] == live['components']['schemas'][name]
        assert name in (root / 'gui/src/types/api.generated.ts').read_text()
        assert name in (root / 'gui/src/types/api.ts').read_text()
