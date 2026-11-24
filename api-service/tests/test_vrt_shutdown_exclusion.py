import pytest
from fastapi import HTTPException

from app.api.instrument import _exclusive_f64_control_operation
from app.services import execution_exclusion_guard as guard
from app.services.instrument_test_lease import instrument_test_lease, InstrumentTestLeaseError
from app.services.road_test import conducted_runner as runner
from app.schemas.road_test import TestMode
from tests.test_road_test_executions import _isolated_db, _TestingSessionLocal


@pytest.mark.asyncio
async def test_failed_execution_blocks_other_equipment_users_after_restart(client):
    with _TestingSessionLocal() as db:
        row = runner.executions.create(db, mode=TestMode.CONDUCTED, scenario_id="fixture")
        row.status = "failed"
        row.hardware_status = {"conducted_shutdown_ports": [7], "conducted_stop_confirmed": False}
        db.commit()
        status_url = f"/api/v1/road-test/executions/{row.id}/status"
        runner.recover_conducted_runs(db)
        try:
            assert client.get(status_url).json()["conducted_stop_pending"] is True
            with pytest.raises(HTTPException) as blocked:
                async with _exclusive_f64_control_operation(db):
                    pytest.fail("停止未确认时仍允许切换控制权")
            assert blocked.value.status_code == 409
            assert guard.try_acquire_unsafe_diagnostic("fixed_route") is None
            with pytest.raises(InstrumentTestLeaseError, match="停止"):
                async with instrument_test_lease("其他基站测试", control_f64=False):
                    pytest.fail("停止未确认时仍取得其他测试租约")
        finally:
            runner._record_shutdown(db, row, None)
        assert client.get(status_url).json()["conducted_stop_pending"] is False
        async with _exclusive_f64_control_operation(db):
            pass
