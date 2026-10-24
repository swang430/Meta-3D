"""PC-03A真实HTTP→真实租约→真实connect，仅替换外部VISA资源。"""
from types import SimpleNamespace
from unittest.mock import patch
import pytest

from fastapi.testclient import TestClient

from app.api import diagnostic_sequence
from app.db.database import get_db
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.main import app
from app.services.instrument_test_lease import InstrumentTestLease
from tests.test_p2_58_channel_emulator_binding import db, _configured
from tests.test_p1_66_f64_probe_truth import _ScriptedVisaResource, _ScriptedRM, SYS_INFO_WITH_INT, _connect, _base_replies


def test_read_only_capture_never_activates_saved_alignment_while_connecting(db, monkeypatch):
    _, _, _, lab = _configured(db, driver_mode='real')
    resource = _ScriptedVisaResource({
        '*IDN?': 'Keysight Technologies,F8800A,FI1234567,8.0',
        'SYST:INFO?': SYS_INFO_WITH_INT, 'SYSTem:ERRor?': '0,"No error"',
        'DIAG:SIMU:STATE?': 'STOPPED',
        'SYSTem:CALIBration:USER:GET?': '', 'SYSTem:CALIBration:VALid?': '0,0',
        'GROup:INPUTS:GET? 2': '1,2', 'GROup:OUTputs:GET? 2': '3,4',
        'GROup:CHannels:GET? 2': '7,8', 'GROup:BANDWidth:GET? 2': '20',
        'CALCulate:FILTer:CENTer:CH? 7': '2595', 'INPut:LOSS:GET? 1': '2',
        'INPut:LEVel:AUTO:ENAble? 1': '1', 'INPut:LEVel:AUTO:MODE? 1': '3',
        'OUTPut:LOSS:GET? 3': '12', 'OUTPut:GAIN:CH? 3': '-5',
    })
    ce = RealPropsimF64Driver('f64-read-only', {'ip_address': '192.0.2.10', 'alignment_name': 'saved-other-alignment'})
    hal = SimpleNamespace(drivers={'channelEmulator': ce})
    lease = InstrumentTestLease(lambda: hal)
    monkeypatch.setattr(diagnostic_sequence, 'instrument_test_lease', lease.hold)
    monkeypatch.setattr(diagnostic_sequence, 'get_hal_service', lambda: hal)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db
    try:
        resources = [resource, _ScriptedVisaResource(resource._replies)]
        with patch('pyvisa.ResourceManager', side_effect=[_ScriptedRM(item) for item in resources]):
            for item in resources:
                response = TestClient(app).post(f'/api/v1/lab-profiles/{lab.id}/f64-calibration-state',
                    json={'group_id': 2, 'input_port': 1, 'output_port': 3})
                assert response.status_code == 200, response.text
                assert not any('USER:SET' in command.upper() for command in item.commands), item.commands
                assert item.closed is True
                assert ce.local_control_reserved is True
                result = response.json()['state']
                assert result is not None, response.text
                assert next(f for f in result['fields'] if f['key'] == 'user_enabled')['value'] is False
                assert result['formal_eligible'] is False
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_normal_connection_keeps_existing_alignment_restore_behavior():
    ce, resource, ok = await _connect(_base_replies(), {'alignment_name': 'saved-other-alignment'})
    try:
        assert ok is True
        assert any('USER:SET' in command.upper() for command in resource.commands)
    finally:
        await ce.release_to_local_control()
