
import sys
import os
import logging
from datetime import datetime

# Setup path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.database import SessionLocal
from app.models.report import TestReport
from app.services.report_service import ReportService
from sqlalchemy import desc

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DebugReport")

def debug_latest_report():
    db = SessionLocal()
    try:
        # 1. Get latest report
        latest_report = db.query(TestReport).order_by(desc(TestReport.generated_at)).first()
        
        if not latest_report:
            logger.error("NO REPORTS FOUND IN DATABASE!")
            print("ERROR: Database table 'test_reports' is empty.")
            return

        logger.info(f"Checking latest report: {latest_report.id}")
        logger.info(f"Title: {latest_report.title}")
        logger.info(f"Created At: {latest_report.generated_at}")
        
        # 2. Check Content Data
        content = latest_report.content_data
        if not content:
            logger.error("CONTENT_DATA IS EMPTY/NULL!")
        else:
            logger.info("="*20 + " CONTENT DATA KEYS " + "="*20)
            logger.info(f"Keys: {list(content.keys())}")
            
            if 'logs' in content: logger.info(f"Logs: {len(content['logs'])}")
            else: logger.warning("MISSING: logs")
            
            if 'kpi_summary' in content: logger.info(f"KPI Summary: {len(content['kpi_summary'])}")
            else: logger.warning("MISSING: kpi_summary")
            
            if 'time_series' in content: logger.info(f"Time Series: {len(content['time_series'])}")
            else: logger.warning("MISSING: time_series")
            
            if 'execution' in content: logger.info("FOUND: execution")
            else: logger.warning("MISSING: execution")

            if 'step_configs' in content: logger.info(f"Step Configs: {len(content['step_configs'])}")
            else: logger.warning("MISSING: step_configs")

            # Check for mapped keys
            if 'execution_summary' in content: logger.info("FOUND: execution_summary (Already in DB?)")
            if 'statistics' in content: logger.info("FOUND: statistics (Already in DB?)")
            
            logger.info("="*60)
            
        # 3. Manually Trigger Generation
        logger.info("-" * 30)
        logger.info("Attempting Manual PDF Generation...")
        service = ReportService()
        generated_report = service.generate_report(db, latest_report.id)
        
        if generated_report:
            logger.info("Generation function returned success.")
            logger.info(f"File Path: {generated_report.file_path}")
            
            if generated_report.file_path and os.path.exists(generated_report.file_path):
                 size = os.path.getsize(generated_report.file_path)
                 logger.info(f"File Size on Disk: {size} bytes")
                 if size < 1000:
                     logger.warning("FILE IS SUSPICIOUSLY SMALL (< 1KB)!")
            else:
                logger.error("FILE DOES NOT EXIST ON DISK!")
        else:
            logger.error("Generation function returned None/Failure")

    except Exception as e:
        logger.exception("An error occurred during verification")
    finally:
        db.close()

if __name__ == "__main__":
    debug_latest_report()
