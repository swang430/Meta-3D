"""Report Generation Services"""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
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
        # Convert UUID to string for JSON serialization
        execution_ids_str = [str(eid) for eid in (test_execution_ids or [])]
        comparison_ids = kwargs.pop('comparison_plan_ids', None)
        comparison_ids_str = [str(cid) for cid in (comparison_ids or [])] if comparison_ids else []

        report = TestReport(
            title=title,
            report_type=report_type,
            format=format,
            generated_by=generated_by,
            test_plan_id=test_plan_id,
            test_execution_ids=execution_ids_str,
            comparison_plan_ids=comparison_ids_str,
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
        report_id: UUID,
        content_data_override: Optional[Dict[str, Any]] = None
    ) -> Optional[TestReport]:
        """
        Trigger report generation
        
        Args:
            db: Database session
            report_id: Report ID
            content_data_override: Optional direct data to use, bypassing DB fetch
        """
        report = self.get_report(db, report_id)
        if not report:
            return None

        # Update status to generating
        report.status = ReportStatus.GENERATING
        report.generation_started_at = datetime.now(timezone.utc)
        report.progress_percent = 0
        db.commit()

        logger.info(f"Starting report generation: {report_id}")

        try:
            # Get template
            template = None
            if report.template_id:
                # User explicitly specified a template
                template = db.query(ReportTemplate).filter(
                    ReportTemplate.id == report.template_id
                ).first()
                logger.info(f"Using user-specified template: {template.name if template else 'NOT FOUND'}")

            if not template:
                # Try to find appropriate template based on report type
                if report.report_type == ReportType.SINGLE_EXECUTION and report.road_test_execution_id:
                    # VRT report - try to find VRT-specific template by name pattern
                    template = db.query(ReportTemplate).filter(
                        ReportTemplate.is_active == True,
                        ReportTemplate.name.ilike("%Virtual Road Test%")
                    ).first()
                    if template:
                        logger.info(f"Using VRT template: {template.name}")

                if not template and report.report_type != ReportType.SINGLE_EXECUTION:
                    # Get default template for other report types
                    template = db.query(ReportTemplate).filter(
                        ReportTemplate.is_default == True,
                        ReportTemplate.is_active == True
                    ).first()
                    if template:
                        logger.info(f"Using default template: {template.name}")

            # Log template status
            if template:
                logger.info(f"Report {report_id} will use template '{template.name}' (sections: {len(template.sections or [])})")
            else:
                logger.info(f"Report {report_id} will use auto-generated layout (no template)")

            # Update progress
            report.progress_percent = 10
            db.commit()

            # Gather report data
            report_data_dict = {}
            
            # Use overrides if available (critical for VRT immediate generation)
            source_data = content_data_override or report.content_data
            
            if report.report_type == ReportType.SINGLE_EXECUTION and source_data:
                # For VRT/Single Execution, use the data directly
                report_data_dict = source_data.copy() if hasattr(source_data, 'copy') else dict(source_data)
                
                # Ensure it has basic metadata if missing
                if 'title' not in report_data_dict:
                    report_data_dict['title'] = report.title
                if 'generated_by' not in report_data_dict:
                    report_data_dict['generated_by'] = report.generated_by
                if 'generated_at' not in report_data_dict:
                    report_data_dict['generated_at'] = datetime.now(timezone.utc).isoformat()

                # Transform VRT data structure to PDF Generator expected structure
                # Debug logging
                logger.info(f"Preparing VRT report data. Keys available: {list(report_data_dict.keys())}")
                if 'logs' in report_data_dict:
                     logger.info(f"Logs count: {len(report_data_dict['logs'])}")
                else:
                     logger.warning("No 'logs' key in report_data_dict")
                
                # 1. Execution Summary
                
                # 1. Execution Summary
                if 'execution_summary' not in report_data_dict:
                    report_data_dict['execution_summary'] = {
                        'total_executions': 1,
                        'passed': 1 if report_data_dict.get('overall_result') == 'passed' else 0,
                        'failed': 1 if report_data_dict.get('overall_result') == 'failed' else 0,
                        'pending': 0,
                        'pass_rate': report_data_dict.get('pass_rate', 0),
                        'total_duration_sec': report_data_dict.get('duration_s', 0),
                        'first_execution': report_data_dict.get('start_time'),
                        'last_execution': report_data_dict.get('end_time')
                    }

                # 2. Statistics (Map kpi_summary -> statistics)
                if 'statistics' not in report_data_dict and 'kpi_summary' in report_data_dict:
                    stats = {}
                    for kpi in report_data_dict.get('kpi_summary', []):
                        name = kpi.get('name')
                        if name:
                            stats[name] = {
                                'metric_name': name,
                                'mean': kpi.get('mean', 0),
                                'median': kpi.get('median', kpi.get('mean', 0)),  # Use median if available, fallback to mean
                                'std': kpi.get('std', 0),
                                'min': kpi.get('min', 0),
                                'max': kpi.get('max', 0),
                                'count': kpi.get('count', 0)
                            }
                    report_data_dict['statistics'] = stats

                # 3. Chart Data (Map time_series -> chart_data)
                if 'chart_data' not in report_data_dict and 'time_series' in report_data_dict:
                    ts_data = report_data_dict.get('time_series', [])
                    if ts_data:
                        timestamps = []
                        metrics_series = {}
                        
                        for point in ts_data:
                            t_val = point.get('time_s', 0)
                            timestamps.append(t_val)
                            
                            for k, v in point.items():
                                if k not in ['time_s', 'position', 'event'] and isinstance(v, (int, float)):
                                    if k not in metrics_series:
                                        metrics_series[k] = []
                                    metrics_series[k].append(v)
                        
                        chart_data = {}
                        for metric, values in metrics_series.items():
                             chart_data[f"time_series_{metric}"] = {
                                 "timestamps": timestamps,
                                 "values": values,
                                 "anomaly_indices": []
                             }
                        report_data_dict['chart_data'] = chart_data
            else:
                # For standard reports, collect data from DB
                data_collector = ReportDataCollector()
                report_data = data_collector.collect(db, report)
                if report_data is None:
                    raise ValueError(f"Failed to collect report data for report {report_id}")
                report_data_dict = report_data.to_dict()

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

                # Generate PDF using the dict data
                pdf_generator.generate_report(report_data_dict, template_dict, output_path)

                # Update report with file path and metadata
                report.file_path = output_path
                report.file_size_bytes = os.path.getsize(output_path)
                
                # Check if specific result directory exists (User preference)
                import shutil
                # Assumption: running from api-service/ or root
                legacy_result_dir = os.path.abspath(os.path.join(os.getcwd(), '..', 'Result_Report'))
                if not os.path.exists(legacy_result_dir):
                    # Try current directory
                    legacy_result_dir = os.path.abspath(os.path.join(os.getcwd(), 'Result_Report'))
                
                if os.path.exists(legacy_result_dir):
                    try:
                        target_path = os.path.join(legacy_result_dir, f'report_{report.id}.pdf')
                        shutil.copy2(output_path, target_path)
                        logger.info(f"Copied report to legacy path: {target_path}")
                    except Exception as e:
                        logger.warning(f"Failed to copy report to Result_Report: {e}")

                # Extract stats for metadata
                
                # Extract stats for metadata
                if 'chart_data' in report_data_dict:
                    report.chart_count = len(report_data_dict['chart_data'])
                if 'table_data' in report_data_dict:
                    report.table_count = len(report_data_dict['table_data'])

            # Update status to completed
            report.status = ReportStatus.COMPLETED
            report.generation_completed_at = datetime.now(timezone.utc)
            report.progress_percent = 100

            db.commit()
            db.refresh(report)

            logger.info(f"Report generation completed: {report_id}")
            return report

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Error generating report {report_id}: {e}\n{error_details}")

            # Update status to failed with detailed error info
            report.status = ReportStatus.FAILED
            report.error_message = str(e)
            report.error_details = error_details  # Save full traceback for debugging
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
