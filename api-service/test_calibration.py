import asyncio
import sys
import uuid
sys.path.insert(0, '.')
from app.db.database import SessionLocal
from app.services.path_loss_calibration_service import ProbePathLossCalibrationService
import traceback

async def run_test():
    db = SessionLocal()
    try:
        service = ProbePathLossCalibrationService(db, use_mock=True)
        result = await service.start_calibration(
            chamber_id=uuid.UUID("b7cd8de0-da25-473a-9618-4f0795046326"),
            frequency_mhz=3500.0,
            sgh_model="test",
            sgh_gain_dbi=10.0,
            calibrated_by="test"
        )
        print("Success:", result.success)
        if not result.success:
            print("Message:", result.message)
    except Exception as e:
        print("EXCEPTION CAUGHT:")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_test())
