"""PC-04A：真实采集算法仅替换外部传输；反例防设定值、旧值和停发失败假成功。"""
import asyncio
from uuid import uuid4

import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.rs_fsva import RealRsFsvaDriver
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.signal_analyzer import MockSignalAnalyzer


def request(**changes):
    from app.schemas.fixed_route_acquisition import FixedRouteRequest
    return FixedRouteRequest(**dict(chain_id='conn_p0v', configuration_digest='a'*64,
        frequency_mhz=2595, requested_power_dbm=-20, reference_antenna='参考天线SN1，静区中心V',
        receive_cable_loss_db=2, receive_cable_source='线缆SN2，2595MHz实测记录',
        fixed_route_confirmed=True, safety_confirmed=True, sample_count=2, **changes))


def instruments(*, receive='-50', state='RUNNING', loss='0', source='-20', stop_error=False):
    ce = RealPropsimF64Driver('ce-test', {'ip': '127.0.0.1'})
    ce.has_interference_generator = True
    sa = RealRsFsvaDriver('sa-test', {'ip': '127.0.0.2'})
    writes, queries = [], []
    ce_errors, sa_errors = [], []
    replies = {'*IDN?': 'Keysight Technologies,F8800A,SN-CE,8.0',
        'DIAG:SIMU:STATE?': state, 'OUTPut:LOSS:GET? 1': loss,
        'OUTPut:MEASure:RESult:GET? 1,1': source, 'OUTPut:INTERFerence:GET?': '0',
        'SYSTem:CALIBration:VALid?': '1,1', 'SYSTem:CALIBration:USER:GET?': '',
        'SYSTem:CALIBration:GET?': 'auto-1', 'OUTPut:GAIN:CH? 1': '0'}

    async def query(command):
        queries.append(('ce', command))
        if command == 'SYSTem:ERRor?':
            return ce_errors.pop(0) if ce_errors else '0,"No error"'
        assert command in replies, command
        value = replies[command]
        if isinstance(value, Exception):
            raise value
        return value

    async def write(command):
        writes.append(('ce', command))
        if stop_error and command.startswith('OUTPut:INTERFerence:STatus ') and command.endswith(',0'):
            ce_errors.append('-200,"stop rejected"')

    def sa_query(command):
        queries.append(('sa', command))
        if command == 'SYST:ERR?':
            return sa_errors.pop(0) if sa_errors else '0,"No error"'
        if command == '*IDN?':
            return 'Rohde&Schwarz,FSVA3044,SN-SA,1.0'
        if command == 'SENSe:CORRection:TRANsducer:CATalog?':
            return '0,10000'
        if command == 'INITiate:IMMediate; *OPC?':
            return '1'
        if command == 'CALCulate:MARKer:FUNCtion:POWer:RESult? CPOWer':
            return receive
        raise AssertionError(command)

    ce._query, ce._write = query, write
    sa._query, sa._write = sa_query, lambda command: writes.append(('sa', command))
    return ce, sa, writes, queries, replies


async def collect(ce, sa, monkeypatch, cancel=None):
    from app.services.calibration import fixed_route_acquisition as module
    from app.schemas.fixed_route_acquisition import FixedRouteResult
    async def settle(*args):
        return None
    monkeypatch.setattr(module, '_settle', settle)
    result = FixedRouteResult(run_id=uuid4(), lab_profile_id=uuid4(), request=request(),
        configuration={'chain_id': 'conn_p0v', 'ce_port': 'B1.1'})
    return await module.collect_fixed_route(ce, sa, result, output_port=1, cancel=cancel or asyncio.Event())


@pytest.mark.parametrize('receive,want', [('-50', 28), ('-10', -12)])
async def test_real_command_chain_computes_from_measured_power_not_requested_power(monkeypatch, receive, want):
    ce, sa, writes, queries, replies = instruments(receive=receive)
    value = await collect(ce, sa, monkeypatch)
    assert value.status == 'completed', value.error
    assert value.net_loss_db == want
    assert len(value.samples) == 2 and value.samples[0].source_before_dbm == -20
    assert ('ce', 'OUTPut:MEASure:RESult:GET? 1,1') in queries
    assert ('ce', 'OUTPut:MEASure:RESult:GET? 1') not in queries
    assert ('sa', 'CALCulate:UNIT:POWer DBM') in writes
    assert value.cleanup_confirmed is True and value.formal_eligible is False
    assert any(event.response == receive for event in value.exchanges)
    assert writes[-1][1].startswith('OUTPut:INTERFerence:REMove ')
    assert not any('ROUT' in command or '*RST' in command for _, command in writes)


@pytest.mark.parametrize('changes', [{'state': 'STOPPED'}, {'loss': '2'}, {'source': 'not ready'},
    {'receive': 'nan'}, {'source': TimeoutError('no result')}])
async def test_unknown_stopped_and_nonfinite_never_produce_loss(monkeypatch, changes):
    ce, sa, writes, _, _ = instruments(**changes)
    value = await collect(ce, sa, monkeypatch)
    assert value.status == 'failed'
    assert value.net_loss_db is None
    if changes.get('state') or changes.get('loss'):
        assert not writes
    else:
        assert value.cleanup_confirmed is True


async def test_stop_rejection_preserves_partial_samples_but_not_success(monkeypatch):
    ce, sa, _, _, _ = instruments(stop_error=True)
    value = await collect(ce, sa, monkeypatch)
    assert value.status == 'cleanup_unconfirmed'
    assert value.cleanup_confirmed is False and value.net_loss_db is None
    assert len(value.samples) == 2


async def test_cancel_during_capture_stops_owned_tone(monkeypatch):
    from app.services.calibration import fixed_route_acquisition as module
    ce, sa, writes, _, _ = instruments()
    cancel = asyncio.Event()
    original = sa._query
    def query(command):
        value = original(command)
        if command.endswith('CPOWer'):
            cancel.set()
        return value
    sa._query = query
    value = await collect(ce, sa, monkeypatch, cancel)
    assert value.status == 'cancelled'
    assert value.cleanup_confirmed is True and value.net_loss_db is None
    assert writes[-1][1].startswith('OUTPut:INTERFerence:REMove ')


async def test_existing_interferer_is_not_removed_or_overwritten(monkeypatch):
    ce, sa, writes, _, replies = instruments()
    replies['OUTPut:INTERFerence:GET?'] = '1,existing,2'
    value = await collect(ce, sa, monkeypatch)
    assert value.status == 'failed' and not writes


async def test_mock_uses_same_commands_without_inventing_measurements(monkeypatch):
    value = await collect(MockChannelEmulator('ce', {}), MockSignalAnalyzer('sa', {}), monkeypatch)
    assert value.status == 'simulated'
    assert not value.samples and value.net_loss_db is None
    assert all(e.simulated and e.response is None for e in value.exchanges)
    assert any(e.command == 'OUTPut:MEASure:RESult:GET? 1,1' for e in value.exchanges)
    assert value.formal_eligible is False


def test_request_refuses_operator_supplied_measurement():
    from pydantic import ValidationError
    from app.schemas.fixed_route_acquisition import FixedRouteRequest
    payload = request().model_dump()
    payload['ce_output_power_dbm'] = -20
    with pytest.raises(ValidationError):
        FixedRouteRequest.model_validate(payload)


async def test_cleanup_can_reenter_real_driver_transaction_lock(monkeypatch):
    ce, sa, _, _, _ = instruments()
    original = ce._write
    async def locked_write(command):
        # 保留真实F64 _do_write的可重入锁；有界超时把死锁变成可观察失败。
        async with asyncio.timeout(.1):
            async with ce._scpi_lock:
                await original(command)
    ce._write = locked_write
    value = await collect(ce, sa, monkeypatch)
    assert value.status == 'completed', value.error
    assert value.cleanup_confirmed is True
