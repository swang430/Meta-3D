"""PC-03A：真实读取算法仅替换传输，保留值、来源和错误归属。"""
import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.channel_emulator import MockChannelEmulator


def driver(replacements=None, query_errors=None):
    ce = RealPropsimF64Driver('f64-test', {'ip': '127.0.0.1', 'port': 3334})
    replies = {
        '*IDN?': 'Keysight Technologies,F8800A,FI64201631,8.0',
        'DIAG:SIMU:STATE?': 'STOPPED',
        'SYSTem:CALIBration:VALid?': '1,1', 'SYSTem:CALIBration:GET?': 'Auto-1',
        'SYSTem:CALIBration:USER:GET?': '', 'SYSTem:CALIBration:USER:INFO?': 'user-info',
        'GROup:INPUTS:GET? 2': '1,2', 'GROup:OUTputs:GET? 2': '3,4',
        'GROup:CHannels:GET? 2': '7,8', 'GROup:BANDWidth:GET? 2': '20',
        'CALCulate:FILTer:CENTer:CH? 7': '2595',
        'INPut:LOSS:GET? 1': '-2.5', 'OUTPut:LOSS:GET? 3': '12',
        'OUTPut:GAIN:CH? 3': '-5', 'INPut:LEVel:AUTO:ENAble? 1': '1',
        'INPut:LEVel:AUTO:MODE? 1': '3',
    }
    replies.update(replacements or {})
    ce.queries = []
    errors = []

    async def query(command):
        ce.queries.append(command)
        if command == 'SYSTem:ERRor?':
            return errors.pop(0) if errors else '0,"No error"'
        assert command in replies, f'脚本外命令：{command}'
        value = replies[command]
        if isinstance(value, Exception):
            raise value
        errors.extend((query_errors or {}).get(command, []))
        return value
    ce._query = query
    return ce


async def read(ce):
    from app.schemas.f64_calibration_state import F64StateRequest
    from app.diagnostics.sequences.propsim_f64_calibration_state import read_state
    return await read_state(ce, F64StateRequest(group_id=2, input_port=1, output_port=3), 'a' * 64)


def fields(value):
    return {field.key: field for field in value.fields}


async def test_record_keeps_real_values_raw_and_units_without_changing_hardware():
    ce = driver()
    value = await read(ce)
    found = fields(value)
    assert found['input_loss_db'].value == -2.5
    assert found['input_loss_db'].raw == '-2.5'
    assert found['input_loss_db'].status == 'confirmed'
    assert found['group_frequency_mhz'].value == 2595
    assert found['group_bandwidth_mhz'].value == 20
    assert found['output_gain_db'].value == -5
    assert found['user_enabled'].value is False
    assert found['user_enabled'].raw == ''
    assert found['output_adjust_mode'].status == 'unknown'
    assert value.formal_eligible is False
    assert value.binding_digest == 'a' * 64
    assert all(command.split(' ')[0].endswith('?') for command in ce.queries)
    assert 'SYSTem:CALIBration:USER:INFO?' not in ce.queries


@pytest.mark.parametrize('reply', [None, TimeoutError('timeout'), '-100,"ATE command not supported"'])
async def test_failed_user_query_is_unknown_not_disabled(reply):
    found = fields(await read(driver({'SYSTem:CALIBration:USER:GET?': reply})))
    assert found['user_enabled'].status == 'unknown'
    assert found['user_enabled'].value is None


async def test_nonzero_error_queue_prevents_numeric_reply_from_becoming_confirmed():
    found = fields(await read(driver(query_errors={'OUTPut:LOSS:GET? 3': ['-200,"bad query"']})))
    assert found['output_loss_db'].status == 'unknown'
    assert found['output_loss_db'].value is None
    assert found['output_loss_db'].raw == '12'


async def test_enabled_user_alignment_may_have_empty_additional_information():
    found = fields(await read(driver({'SYSTem:CALIBration:USER:GET?': 'alignment-1',
        'SYSTem:CALIBration:USER:INFO?': ''})))
    assert found['user_enabled'].value is True
    assert found['user_info'].status == 'confirmed'
    assert found['user_info'].raw == ''
    assert found['user_info'].value == ''


@pytest.mark.parametrize('state', ['CLOSED', 'RUNNING', 'BROKEN'])
async def test_unstable_or_missing_simulation_never_queries_ports(state):
    ce = driver({'DIAG:SIMU:STATE?': state})
    found = fields(await read(ce))
    assert found['output_loss_db'].status == 'unknown'
    assert not any(command.startswith(('GROup:', 'OUTPut:', 'INPut:', 'CALCulate:')) for command in ce.queries)


async def test_wrong_output_membership_never_queries_that_output():
    ce = driver({'GROup:OUTputs:GET? 2': '5,6'})
    found = fields(await read(ce))
    assert found['output_loss_db'].value is None
    assert not any(command.startswith('OUTPut:') for command in ce.queries)


async def test_mock_is_explicitly_simulated_and_does_not_invent_readbacks():
    ce = MockChannelEmulator('mock-ce', {})
    value = await read(ce)
    assert value.acquisition_status == 'simulated'
    assert all(item.status == 'simulated' and item.value is None and item.raw is None for item in value.fields)
    assert value.formal_eligible is False


@pytest.mark.parametrize('params', [{'group_id': 0, 'input_port': 1, 'output_port': 3},
    {'group_id': True, 'input_port': 1, 'output_port': 3},
    {'group_id': 2, 'input_port': 1, 'output_port': 3, 'formal_eligible': True}])
def test_invalid_request_rejected_before_remote(params):
    from app.diagnostics.sequences.propsim_f64_calibration_state import validate_before_lease
    with pytest.raises(ValueError):
        validate_before_lease(params)


@pytest.mark.parametrize('identity', ['Keysight,FS16,123,1', 'Keysight,FS16,F8800A,1'])
async def test_wrong_identity_stops_before_calibration_queries(identity):
    ce = driver({'*IDN?': identity})
    result = await read(ce)
    assert fields(result)['instrument_identity'].status == 'unknown'
    assert not any(command.startswith(('SYSTem:CALIBration:', 'GROup:')) for command in ce.queries)


@pytest.mark.parametrize('raw', ['nan', 'inf', '-inf', 'garbage'])
async def test_nonfinite_or_malformed_numbers_are_not_readings(raw):
    found = fields(await read(driver({'OUTPut:LOSS:GET? 3': raw})))
    assert found['output_loss_db'].status == 'unknown'
    assert found['output_loss_db'].value is None
