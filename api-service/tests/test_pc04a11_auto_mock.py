"""auto 是选择策略；合成样本资格来自本次实际驱动，不改变保存配置。"""
from uuid import UUID

import pytest

from app.models.instrument import InstrumentCategory
from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured, client, start, finish
from tests.test_pc04a8_mock_contract import mock_payload
from tests.test_pc04a8_mock_safety import (
    batch_mock, test_batch_http_replay_drift_and_manual_boundary as run_batch_boundary,
)
from tests.test_pc06a1_batch_plan import shared_switch


def set_policy(db, lab, policy='auto'):
    bindings = [dict(binding) for binding in lab.instrument_bindings]
    for binding in bindings:
        db.get(InstrumentCategory, UUID(binding['category_id'])).driver_mode = policy
        binding['driver_mode'] = policy
    lab.instrument_bindings = bindings
    db.commit()


def test_auto_mock_http_samples_remain_nonformal(client, configured, db_session):
    set_policy(db_session, configured)
    response = start(client, configured, mock_input=mock_payload())
    assert response.status_code == 202, response.text
    run_id = response.json()['run_id']
    record = finish(client, configured, run_id)
    assert record['status'] == 'simulated'
    assert record['result']['net_loss_db'] == 29.
    assert record['result']['formal_eligible'] is False
    preview = client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}/application-preview')
    assert preview.status_code == 200, preview.text
    assert preview.json()['new_net_loss_db'] is None
    assert preview.json()['eligibility']['measurement_provenance'] == 'simulated'
    db_session.expire_all()
    assert all(b['driver_mode'] == 'auto' for b in configured.instrument_bindings)
    assert all(c.driver_mode == 'auto' for c in db_session.query(InstrumentCategory).all())


@pytest.mark.parametrize('fault', ['none', 'runtime_after_wait', 'binding_after_preview'])
def test_auto_batch_preserves_waiting_runtime_and_binding_guards(
    client, configured, db_session, topology_two_chains, batch_mock, fault,
):
    set_policy(db_session, configured)
    # 原绑定漂移用 mock -> auto；此处反向起始以保留相同不一致反例。
    if fault == 'binding_after_preview':
        set_policy(db_session, configured, 'mock')
    run_batch_boundary(client, configured, db_session, topology_two_chains, batch_mock, fault)


@pytest.mark.parametrize('fault', ['real_policy', 'real_ce', 'real_sa', 'missing_driver'])
def test_auto_does_not_authorize_real_or_missing_drivers(
    client, configured, db_session, batch_mock, monkeypatch, fault,
):
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.rs_fsva import RealRsFsvaDriver
    from app.models.diagnostic_run import DiagnosticRun

    set_policy(db_session, configured, 'real' if fault == 'real_policy' else 'auto')
    _, hal = batch_mock
    if fault == 'real_ce':
        hal.drivers['channelEmulator'] = RealPropsimF64Driver('ce', {'ip': '192.0.2.10'})
    elif fault == 'real_sa':
        hal.drivers['signalAnalyzer'] = RealRsFsvaDriver('sa', {'ip': '192.0.2.10'})
    elif fault == 'missing_driver':
        hal.drivers.pop('signalAnalyzer')
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('拒绝必须早于硬件 I/O')

    for driver in hal.drivers.values():
        for method in ('connect', '_query', '_write', 'acquire_remote', 'release_remote'):
            monkeypatch.setattr(driver, method, forbidden, raising=False)
    response = start(client, configured, mock_input=mock_payload())
    assert response.status_code == 422, response.text
    assert calls == []
    assert db_session.query(DiagnosticRun).count() == 0


@pytest.mark.asyncio
async def test_auto_mock_switch_plan_keeps_policy_and_only_previews(
    client, configured, db_session, shared_switch, batch_mock, monkeypatch,
):
    from app.hal.rf_switch import MockRfSwitch
    from app.schemas.route_batch import BatchPlanRequest
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.services.calibration.route_batch_switch import apply_batch_switch_steps
    from tests.test_pc04a8_mock_safety import batch_body

    topo, _ = shared_switch
    set_policy(db_session, configured)
    _, hal = batch_mock
    switch = MockRfSwitch('switch', {})
    hal.drivers['rfSwitch'] = switch
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('模拟开关不得进行 I/O')

    for method in ('connect', 'set_path', '_query', '_write'):
        monkeypatch.setattr(switch, method, forbidden, raising=False)
    plan = build_batch_plan(db_session, configured.id,
        BatchPlanRequest.model_validate(batch_body(topo, ('ov',))), hal)
    steps = plan.items[0].switch_steps
    assert len(steps) == 1 and steps[0].driver_mode == 'auto'
    receipts = []
    assert await apply_batch_switch_steps(hal, steps, receipts.append, simulated=True)
    assert len(receipts) == 1
    assert receipts[0]['kind'] == 'command_preview'
    assert receipts[0]['command'] and receipts[0]['simulated'] is True
    assert receipts[0]['raw'] is None and calls == []
