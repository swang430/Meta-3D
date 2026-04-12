
import sys
import os
import asyncio
import logging
from datetime import datetime

# Setup path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api.road_test import _archive_execution_report, _executions, _execution_status
from app.schemas.road_test.execution import ExecutionStatus, TestExecution, TestStatus, TestMetrics, ExecutionMetricsSubmit
from app.db.database import SessionLocal
from app.api import road_test

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestArchive")

async def test_archive():
    print("--- STARTING TEST ARCHIVE ---")
    
    # 1. Setup Mock Execution in Memory
    exec_id = "test-exec-unit-001"
    
    # Mock global dicts in road_test module
    road_test._executions[exec_id] = TestExecution(
        execution_id=exec_id,
        scenario_id="sc_uma_001",
        mode="ota",
        status=ExecutionStatus.STOPPED,
        start_time=datetime.now(),
        notes="Unit Test Execution",
        # Fix missing fields if any
        topology_id=None,
        config={},
        end_time=None,
        duration_s=None,
        created_by="Unit Test",
        logs=[]
    )
    
    road_test._execution_status[exec_id] = TestStatus(
        execution_id=exec_id,
        status=ExecutionStatus.RUNNING,
        progress_percent=50.0,
        message="Running",
        error=None,
        step_index=0,
        total_steps=10,
        elapsed_time_s=60.0
    )
    
    road_test._execution_metrics[exec_id] = TestMetrics(
        execution_id=exec_id,
        kpi_samples=[], # Empty for now, or add some dummy data
        summary={},
        events=[],
        kpi_results={}
    )
    
    logger.info(f"Mocked execution {exec_id} prepared.")

    # 2. Call Archive Function
    db = SessionLocal()
    try:
        print("Calling _archive_execution_report directly...")
        await _archive_execution_report(exec_id, db)
        print("Call returned successfully.")
        
        # 3. Check File
        if os.path.exists("debug_report_dump.txt"):
            print("SUCCESS: debug_report_dump.txt exists!")
            with open("debug_report_dump.txt", "r") as f:
                print(f"File content:\n{f.read()}")
        else:
            print("FAILURE: debug_report_dump.txt NOT found!")

    except Exception as e:
        logger.error(f"Function raised exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_archive())
