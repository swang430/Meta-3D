"""Test Report Generation

This script tests the PDF report generation functionality.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.report import TestReport, ReportTemplate, ReportFormat, ReportStatus
from app.services.report_service import ReportService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_report_generation():
    """Test PDF report generation with existing template"""
    logger.info("Testing report generation...")

    # Initialize database
    init_db()
    db = SessionLocal()

    try:
        # Get default template
        template = db.query(ReportTemplate).filter(
            ReportTemplate.is_default == True,
            ReportTemplate.is_active == True
        ).first()

        if not template:
            logger.error("No default template found. Run init_report_templates.py first.")
            return False

        logger.info(f"Using template: {template.name} (ID: {template.id})")

        # Create test report service
        report_service = ReportService()

        # Create a new report
        report = report_service.create_report(
            db=db,
            title="Test Report - MIMO OTA System",
            report_type="single_execution",
            format="pdf",
            generated_by="test_script",
            template_id=template.id,
            description="This is a test report to verify PDF generation functionality"
        )

        logger.info(f"Created report: {report.id}")

        # Generate report
        logger.info("Generating PDF report...")
        report = report_service.generate_report(db, report.id)

        if report.status == ReportStatus.COMPLETED:
            logger.info("=" * 60)
            logger.info("Report generation SUCCESSFUL!")
            logger.info(f"Report ID: {report.id}")
            logger.info(f"File Path: {report.file_path}")
            logger.info(f"File Size: {report.file_size} bytes")
            logger.info(f"Status: {report.status}")
            logger.info("=" * 60)
            return True
        else:
            logger.error(f"Report generation FAILED: {report.status}")
            if report.error_message:
                logger.error(f"Error: {report.error_message}")
            return False

    except Exception as e:
        logger.error(f"Exception during test: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = test_report_generation()
    sys.exit(0 if success else 1)
