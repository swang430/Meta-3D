"""Smoke test for VRT report archival.

Creates a stopped VRT execution in the DB via vrt_execution_service, then
calls _archive_execution_report directly to verify report dump file is
written. Useful for debugging report content without going through the
full lifecycle.

Usage:
    cd api-service
    .venv/bin/python scripts/test_archive_func.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api.road_test import _archive_execution_report
from app.db.database import SessionLocal
from app.schemas.road_test import TestMode
from app.services.road_test.vrt_execution_service import vrt_execution_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestArchive")


async def test_archive():
    print("--- STARTING TEST ARCHIVE ---")

    db = SessionLocal()
    try:
        # 1. Create a VRT execution and drive it to STOPPED state
        row = vrt_execution_service.create(
            db,
            mode=TestMode.OTA,
            scenario_id="sc_uma_001",
            topology_id=None,
            config={},
            notes="Smoke test execution",
            created_by="archive-smoke-test",
        )
        exec_id = str(row.id)
        vrt_execution_service.start(db, exec_id)
        vrt_execution_service.stop(db, exec_id)
        logger.info(f"Created and stopped VRT execution {exec_id}")

        # 2. Trigger archival
        print("Calling _archive_execution_report directly...")
        await _archive_execution_report(exec_id, db)
        print("Call returned successfully.")

        # 3. Inspect the debug dump file
        if os.path.exists("debug_report_dump.txt"):
            print("SUCCESS: debug_report_dump.txt exists!")
            with open("debug_report_dump.txt", "r") as f:
                content = f.read()
            tail = "\n".join(content.splitlines()[-15:])
            print(f"--- last 15 lines ---\n{tail}")
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
