
import sys
import os
import logging
from datetime import datetime
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.database import SessionLocal, init_db
from app.models.report import TestReport, ReportType, ReportStatus
from app.services.report_service import ReportService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VerifyVRT")

def verify_vrt_generation():
    db = SessionLocal()
    try:
        service = ReportService()
        
        # 1. Create a dummy report entry (needed for ID)
        report_id = uuid.uuid4()
        report = TestReport(
            id=report_id,
            title="Verification VRT Report",
            report_type=ReportType.SINGLE_EXECUTION,
            generated_by="Admin",
            status=ReportStatus.PENDING
        )
        db.add(report)
        db.commit()
        logger.info(f"Created dummy report: {report_id}")

        # 2. Mock VRT Data
        mock_content = {
            "title": "Verification VRT Report",
            "generated_by": "Debug Script",
            "generated_at": datetime.now().isoformat(),
            "overall_result": "passed",
            "pass_rate": 100.0,
            "duration_s": 120,
            "start_time": datetime.now().isoformat(),
            "end_time": datetime.now().isoformat(),
            # Sub-structures
            "step_configs": [
                {"step_name": "Step 1: Init", "parameters": {"freq": "3.5GHz", "bw": "100MHz"}},
                {"step_name": "Step 2: Traffic", "parameters": {"throughput": "Target", "duration": "60s"}}
            ],
            "logs": [
                {"timestamp": datetime.now().isoformat(), "level": "INFO", "source": "System", "message": "Test started"},
                {"timestamp": datetime.now().isoformat(), "level": "WARNING", "source": "Radio", "message": "Signal fluctuation detected"},
                {"timestamp": datetime.now().isoformat(), "level": "INFO", "source": "System", "message": "Test finished"}
            ],
            "kpi_summary": [
                {"name": "Throughput", "mean": 150.5, "unit": "Mbps", "passed": True},
                {"name": "Latency", "mean": 12.0, "unit": "ms", "passed": True}
            ],
            "time_series": []
        }

        # 3. Generate using Override
        logger.info("Triggering generation with content_data_override...")
        result_report = service.generate_report(db, report_id, content_data_override=mock_content)

        if result_report and result_report.status == ReportStatus.COMPLETED:
            logger.info("SUCCESS: Report generated.")
            logger.info(f"File Path: {result_report.file_path}")
            if os.path.exists(result_report.file_path):
                 size = os.path.getsize(result_report.file_path)
                 logger.info(f"File Size: {size} bytes")
                 if size > 1000:
                     logger.info("Size check passed (>1KB).")
                     return True
                 else:
                     logger.error("File is too small!")
            else:
                logger.error("File not found on disk!")
        else:
            logger.error(f"Generation failed. Status: {result_report.status if result_report else 'None'}")
            if result_report and result_report.error_message:
                logger.error(f"Error: {result_report.error_message}")

        return False

    except Exception as e:
        logger.exception("Exception during verification")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if verify_vrt_generation():
        sys.exit(0)
    else:
        sys.exit(1)
