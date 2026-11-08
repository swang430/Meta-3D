import asyncio
from types import SimpleNamespace
import pytest
from app.diagnostics.sequences import uxm_config_truth_probe, uxm_manual_spelling_probe
from app.hal.uxm_command_profiles import UxmLteNrIratProfile

@pytest.mark.parametrize("module", [uxm_config_truth_probe, uxm_manual_spelling_probe])
@pytest.mark.parametrize("reply,expected", [('-221,"busy"',100),('-113,"Undefined header"',2),("",1)])
def test_unconfirmed_queue_never_reaches_probe_or_write(module, reply, expected):
    calls=[]; writes=[]
    class Driver:
        _cmds=UxmLteNrIratProfile()
        async def _query(self, cmd):
            calls.append(cmd)
            return reply
        async def _write(self, cmd): writes.append(cmd)
    result=asyncio.run(module.run(object(),SimpleNamespace(drivers={"baseStation":Driver()}),{},log=lambda _:None))
    assert not result.success
    assert len(calls)==expected
    assert all(c==Driver._cmds.ERR for c in calls)
    assert writes==[]
    assert result.extra["queue_reads"]==[reply]*expected

from app.diagnostics.uxm_error_queue import drain_diagnostic_errors

@pytest.mark.parametrize("replies,failure", [(['-221,"busy"','+0,"No error"'],False),(['-113,"Undefined header"','+0,"No error"'],False),([None],True),(["bad"],True)])
def test_shared_reader_preserves_raw_and_requires_clean(replies,failure):
    values=iter(replies)
    async def query(cmd):
        assert cmd=="PROFILE_ERR"
        return next(values)
    reads,error=asyncio.run(drain_diagnostic_errors(query,"PROFILE_ERR"))
    assert reads==replies
    assert bool(error)==failure

def test_missing_command_and_transport_failure_are_not_clean():
    calls=[]
    async def query(cmd):
        calls.append(cmd)
        raise TimeoutError("offline")
    assert asyncio.run(drain_diagnostic_errors(query,None))[1]
    assert calls==[]
    reads,error=asyncio.run(drain_diagnostic_errors(query,"PROFILE_ERR"))
    assert reads==[] and "TimeoutError" in error
