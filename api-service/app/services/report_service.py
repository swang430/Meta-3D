"""Report Generation Services"""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import os
import logging

from app.models.report import (
    TestReport,
    ReportTemplate,
    ReportComparison,
    ReportSchedule,
    ReportStatus,
    ReportType,
    ReportFormat,
)
from app.models.test_plan import TestPlan, TestExecution
from app.services.pdf_generator import PDFGenerator
from app.services.report_data_collector import ReportDataCollector

logger = logging.getLogger(__name__)


class ReportService:
    """Service for managing test reports"""

    def create_report(
        self,
        db: Session,
        title: str,
        report_type: str,
        format: str,
        generated_by: str,
        test_plan_id: Optional[UUID] = None,
        test_execution_ids: Optional[List[UUID]] = None,
        template_id: Optional[UUID] = None,
        **kwargs
    ) -> TestReport:
        """Create a new report"""
        report = TestReport(
            title=title,
            report_type=report_type,
            format=format,
            generated_by=generated_by,
            test_plan_id=test_plan_id,
            test_execution_ids=test_execution_ids or [],
            template_id=template_id,
            status=ReportStatus.PENDING,
            progress_percent=0,
            **kwargs
        )

        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info(f"Created report: {report.id} - {title}")
        return report

    def get_report(self, db: Session, report_id: UUID) -> Optional[TestReport]:
        """Get a report by ID"""
        return db.query(TestReport).filter(TestReport.id == report_id).first()

    def list_reports(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        format: Optional[str] = None,
        generated_by: Optional[str] = None
    ) -> List[TestReport]:
        """List reports with filters"""
        query = db.query(TestReport)

        if report_type:
            query = query.filter(TestReport.report_type == report_type)
        if status:
            query = query.filter(TestReport.status == status)
        if format:
            query = query.filter(TestReport.format == format)
        if generated_by:
            query = query.filter(TestReport.generated_by == generated_by)

        query = query.order_by(TestReport.generated_at.desc())
        return query.offset(skip).limit(limit).all()

    def count_reports(
        self,
        db: Session,
        report_type: Optional[str] = None,
        status: Optional[str] = None,
        format: Optional[str] = None,
        generated_by: Optional[str] = None
    ) -> int:
        """Count reports with filters"""
        query = db.query(TestReport)

        if report_type:
            query = query.filter(TestReport.report_type == report_type)
        if status:
            query = query.filter(TestReport.status == status)
        if format:
            query = query.filter(TestReport.format == format)
        if generated_by:
            query = query.filter(TestReport.generated_by == generated_by)

        return query.count()

    def update_report(
        self,
        db: Session,
        report_id: UUID,
        **kwargs
    ) -> Optional[TestReport]:
        """Update a report"""
        report = self.get_report(db, report_id)
        if not report:
            return None

        for key, value in kwargs.items():
            if hasattr(report, key) and value is not None:
                setattr(report, key, value)

        db.commit()
        db.refresh(report)

        logger.info(f"Updated report: {report_id}")
        return report

    def delete_report(self, db: Session, report_id: UUID) -> bool:
        """Delete a report"""
        report = self.get_report(db, report_id)
        if not report:
            return False

        db.delete(report)
        db.commit()

        logger.info(f"Deleted report: {report_id}")
        return True

    def generate_report(
        self,
        db: Session,
        report_id: UUID
    ) -> Optional[TestReport]:
        """
        Trigger report generation

        NOTE: In production, this should be moved to a background task
        (Celery/FastAPI BackgroundTasks) for better performance
        """
        report = self.get_report(db, report_id)
        if not report:
            return None

        # Update status to generating
        report.status = ReportStatus.GENERATING
        report.generation_started_at = datetime.utcnow()
        report.progress_percent = 0
        db.commit()

        logger.info(f"Starting report generation: {report_id}")

        try:
            # Get template
            template = None
            if report.template_id:
                template = db.query(ReportTemplate).filter(
                    ReportTemplate.id == report.template_id
                ).first()

            if not template:
                # Get default template for report type
                template = db.query(ReportTemplate).filter(
                    ReportTemplate.is_default == True,
                    ReportTemplate.is_active == True
                ).first()

            # Update progress
            report.progress_percent = 10
            db.commit()

            # Gather report data using the data collector
            data_collector = ReportDataCollector()
            report_data = data_collector.collect(db, report)

            # Update progress
            report.progress_percent = 50
            db.commit()

            # Generate PDF
            if report.format == ReportFormat.PDF or report.format == "pdf":
                output_dir = os.path.join('data', 'reports', str(report.id))
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f'report_{report.id}.pdf')

                pdf_generator = PDFGenerator()

                # Convert template model to dict (if template exists)
                template_dict = None
                if template:
                    template_dict = {
                        'sections': template.sections,
                        'chart_configs': template.chart_configs or {},
                        'table_configs': template.table_configs or {},
                        'page_size': template.page_size or 'A4',
                        'page_orientation': template.page_orientation or 'portrait',
                        'margins': template.margins or {},
                        'logo_path': template.logo_path,
                        'color_scheme': template.color_scheme or {}
                    }

                # Convert ReportData to dict for PDF generator
                pdf_generator.generate_report(report_data.to_dict(), template_dict, output_path)

                # Update report with file path and metadata
                report.file_path = output_path
                report.file_size_bytes = os.path.getsize(output_path)
                report.chart_count = len(report_data.chart_data)
                report.table_count = 1 if report_data.table_data else 0

            # Update status to completed
            report.status = ReportStatus.COMPLETED
            report.generation_completed_at = datetime.utcnow()
            report.progress_percent = 100

            db.commit()
            db.refresh(report)

            logger.info(f"Report generation completed: {report_id}")
            return report

        except Exception as e:
            logger.error(f"Error generating report {report_id}: {e}")

            # Update status to failed
            report.status = ReportStatus.FAILED
            report.error_message = str(e)
            report.progress_percent = 0
            db.commit()

            raise

class ReportTemplateService:
    """Service for managing report templates"""

    def create_template(
        self,
        db: Session,
        name: str,
        template_type: str,
        sections: List[Dict[str, Any]],
        created_by: str,
        **kwargs
    ) -> ReportTemplate:
        """Create a new report template"""
        template = ReportTemplate(
            name=name,
            template_type=template_type,
            sections=sections,
            created_by=created_by,
            **kwargs
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        logger.info(f"Created report template: {template.id} - {name}")
        return template

    def get_template(self, db: Session, template_id: UUID) -> Optional[ReportTemplate]:
        """Get a template by ID"""
        return db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()

    def list_templates(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        template_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[ReportTemplate]:
        """List templates with filters"""
        query = db.query(ReportTemplate)

        if template_type:
            query = query.filter(ReportTemplate.template_type == template_type)
        if is_active is not None:
            query = query.filter(ReportTemplate.is_active == is_active)

        query = query.order_by(ReportTemplate.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def update_template(
        self,
        db: Session,
        template_id: UUID,
        **kwargs
    ) -> Optional[ReportTemplate]:
        """Update a template"""
        template = self.get_template(db, template_id)
        if not template:
            return None

        for key, value in kwargs.items():
            if hasattr(template, key) and value is not None:
                setattr(template, key, value)

        db.commit()
        db.refresh(template)

        logger.info(f"Updated template: {template_id}")
        return template

    def delete_template(self, db: Session, template_id: UUID) -> bool:
        """Delete a template"""
        template = self.get_template(db, template_id)
        if not template:
            return False

        db.delete(template)
        db.commit()

        logger.info(f"Deleted template: {template_id}")
        return True


class ReportComparisonService:
    """Service for managing report comparisons"""

    def create_comparison(
        self,
        db: Session,
        name: str,
        baseline_plan_id: UUID,
        comparison_plan_ids: List[UUID],
        created_by: str,
        **kwargs
    ) -> ReportComparison:
        """Create a new comparison analysis"""
        comparison = ReportComparison(
            name=name,
            baseline_plan_id=baseline_plan_id,
            comparison_plan_ids=comparison_plan_ids,
            created_by=created_by,
            **kwargs
        )

        db.add(comparison)
        db.commit()
        db.refresh(comparison)

        logger.info(f"Created comparison: {comparison.id} - {name}")
        return comparison

    def get_comparison(self, db: Session, comparison_id: UUID) -> Optional[ReportComparison]:
        """Get a comparison by ID"""
        return db.query(ReportComparison).filter(ReportComparison.id == comparison_id).first()

    def list_comparisons(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        created_by: Optional[str] = None
    ) -> List[ReportComparison]:
        """List comparisons with filters"""
        query = db.query(ReportComparison)

        if created_by:
            query = query.filter(ReportComparison.created_by == created_by)

        query = query.order_by(ReportComparison.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def perform_comparison_analysis(
        self,
        db: Session,
        comparison_id: UUID
    ) -> Optional[ReportComparison]:
        """
        Perform statistical comparison analysis

        This is a placeholder for actual comparison logic.
        In production, this would:
        1. Fetch data from baseline and comparison test plans
        2. Perform statistical tests (t-test, ANOVA, etc.)
        3. Calculate summary statistics
        4. Identify significant differences
        5. Generate comparison charts
        """
        comparison = self.get_comparison(db, comparison_id)
        if not comparison:
            return None

        # TODO: Implement actual comparison analysis
        logger.info(f"Performing comparison analysis: {comparison_id}")

        return comparison


class ReportScheduleService:
    """Service for managing report schedules"""

    def create_schedule(
        self,
        db: Session,
        name: str,
        template_id: UUID,
        report_type: str,
        schedule_type: str,
        created_by: str,
        **kwargs
    ) -> ReportSchedule:
        """Create a new report schedule"""
        schedule = ReportSchedule(
            name=name,
            template_id=template_id,
            report_type=report_type,
            schedule_type=schedule_type,
            created_by=created_by,
            **kwargs
        )

        db.add(schedule)
        db.commit()
        db.refresh(schedule)

        logger.info(f"Created report schedule: {schedule.id} - {name}")
        return schedule

    def get_schedule(self, db: Session, schedule_id: UUID) -> Optional[ReportSchedule]:
        """Get a schedule by ID"""
        return db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()

    def list_schedules(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[ReportSchedule]:
        """List schedules with filters"""
        query = db.query(ReportSchedule)

        if is_active is not None:
            query = query.filter(ReportSchedule.is_active == is_active)

        query = query.order_by(ReportSchedule.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def update_schedule(
        self,
        db: Session,
        schedule_id: UUID,
        **kwargs
    ) -> Optional[ReportSchedule]:
        """Update a schedule"""
        schedule = self.get_schedule(db, schedule_id)
        if not schedule:
            return None

        for key, value in kwargs.items():
            if hasattr(schedule, key) and value is not None:
                setattr(schedule, key, value)

        db.commit()
        db.refresh(schedule)

        logger.info(f"Updated schedule: {schedule_id}")
        return schedule

    def delete_schedule(self, db: Session, schedule_id: UUID) -> bool:
        """Delete a schedule"""
        schedule = self.get_schedule(db, schedule_id)
        if not schedule:
            return False

        db.delete(schedule)
        db.commit()

        logger.info(f"Deleted schedule: {schedule_id}")
        return True
