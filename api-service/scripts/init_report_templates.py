"""Initialize default report templates"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.report import ReportTemplate, TemplateType
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_standard_template(db: Session) -> ReportTemplate:
    """Create standard test report template"""
    template = ReportTemplate(
        name="Standard Test Report",
        description="Standard template for single test execution reports",
        template_type=TemplateType.STANDARD,
        applicable_test_types=["TRP", "TIS", "Throughput", "MIMO"],

        # Template sections
        sections=[
            {
                "id": "cover",
                "title": "Cover Page",
                "order": 1,
                "type": "cover",
                "required": True,
                "fields": ["title", "date", "test_plan_name", "dut_info", "company_logo"]
            },
            {
                "id": "executive_summary",
                "title": "Executive Summary",
                "order": 2,
                "type": "text",
                "required": True,
                "content_template": "This report presents the results of {{ test_type }} testing performed on {{ dut_name }}."
            },
            {
                "id": "test_configuration",
                "title": "Test Configuration",
                "order": 3,
                "type": "table",
                "required": True,
                "fields": ["test_type", "frequency", "bandwidth", "power", "channel_model"]
            },
            {
                "id": "measurement_results",
                "title": "Measurement Results",
                "order": 4,
                "type": "mixed",
                "required": True,
                "include_charts": True,
                "include_tables": True
            },
            {
                "id": "pass_fail_criteria",
                "title": "Pass/Fail Analysis",
                "order": 5,
                "type": "table",
                "required": True,
                "fields": ["metric", "measured_value", "threshold", "result"]
            },
            {
                "id": "conclusions",
                "title": "Conclusions",
                "order": 6,
                "type": "text",
                "required": True
            }
        ],

        # Chart configurations
        chart_configs={
            "throughput_chart": {
                "type": "line",
                "title": "Throughput vs Time",
                "x_axis": {"label": "Time (s)", "field": "time"},
                "y_axis": {"label": "Throughput (Mbps)", "field": "throughput_mbps"},
                "color": "#1f77b4"
            },
            "power_chart": {
                "type": "bar",
                "title": "TRP/TIS Results",
                "x_axis": {"label": "Frequency (MHz)", "field": "frequency"},
                "y_axis": {"label": "Power (dBm)", "field": "power_dbm"},
                "color": "#ff7f0e"
            }
        },

        # Table configurations
        table_configs={
            "results_table": {
                "columns": ["Metric", "Value", "Unit", "Pass/Fail"],
                "style": "striped",
                "border": True
            }
        },

        # Page settings
        page_size="A4",
        page_orientation="portrait",
        margins={"top": 25, "right": 20, "bottom": 25, "left": 20},

        # Branding
        color_scheme={
            "primary": "#1f77b4",
            "secondary": "#ff7f0e",
            "accent": "#2ca02c",
            "text": "#333333",
            "background": "#ffffff"
        },

        created_by="system",
        is_active=True,
        is_default=True,
        version="1.0"
    )

    db.add(template)
    db.commit()
    db.refresh(template)
    logger.info(f"Created template: {template.name} (ID: {template.id})")
    return template


def create_comparison_template(db: Session) -> ReportTemplate:
    """Create comparison analysis template"""
    template = ReportTemplate(
        name="Comparison Analysis Report",
        description="Template for comparing multiple test executions",
        template_type=TemplateType.COMPARISON,
        applicable_test_types=["TRP", "TIS", "Throughput", "MIMO"],

        sections=[
            {
                "id": "cover",
                "title": "Cover Page",
                "order": 1,
                "type": "cover",
                "required": True
            },
            {
                "id": "comparison_summary",
                "title": "Comparison Summary",
                "order": 2,
                "type": "text",
                "required": True,
                "content_template": "This report compares {{ num_plans }} test plans."
            },
            {
                "id": "baseline_info",
                "title": "Baseline Test",
                "order": 3,
                "type": "table",
                "required": True
            },
            {
                "id": "comparison_charts",
                "title": "Performance Comparison",
                "order": 4,
                "type": "charts",
                "required": True,
                "chart_types": ["bar", "line", "scatter"]
            },
            {
                "id": "statistical_analysis",
                "title": "Statistical Analysis",
                "order": 5,
                "type": "table",
                "required": True,
                "fields": ["metric", "baseline_mean", "comparison_mean", "difference", "p_value", "significant"]
            },
            {
                "id": "recommendations",
                "title": "Recommendations",
                "order": 6,
                "type": "text",
                "required": False
            }
        ],

        chart_configs={
            "comparison_bar": {
                "type": "grouped_bar",
                "title": "Performance Comparison",
                "x_axis": {"label": "Test Plan", "field": "plan_name"},
                "y_axis": {"label": "Performance Metric", "field": "value"},
                "grouping": "metric",
                "colors": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
            },
            "trend_chart": {
                "type": "line",
                "title": "Performance Trend",
                "x_axis": {"label": "Test Number", "field": "test_index"},
                "y_axis": {"label": "Value", "field": "value"},
                "multiple_series": True
            }
        },

        page_size="A4",
        page_orientation="landscape",
        margins={"top": 20, "right": 20, "bottom": 20, "left": 20},

        color_scheme={
            "primary": "#2ca02c",
            "secondary": "#d62728",
            "accent": "#9467bd",
            "text": "#333333",
            "background": "#ffffff"
        },

        created_by="system",
        is_active=True,
        is_default=False,
        version="1.0"
    )

    db.add(template)
    db.commit()
    db.refresh(template)
    logger.info(f"Created template: {template.name} (ID: {template.id})")
    return template


def create_regulatory_template(db: Session) -> ReportTemplate:
    """Create regulatory compliance template"""
    template = ReportTemplate(
        name="3GPP Regulatory Compliance Report",
        description="Template for 3GPP/FCC/CE regulatory compliance testing",
        template_type=TemplateType.REGULATORY,
        applicable_test_types=["TRP", "TIS"],

        sections=[
            {
                "id": "cover",
                "title": "Cover Page",
                "order": 1,
                "type": "cover",
                "required": True,
                "fields": ["title", "standard", "certification_body", "date"]
            },
            {
                "id": "regulatory_info",
                "title": "Regulatory Information",
                "order": 2,
                "type": "table",
                "required": True,
                "fields": ["standard", "version", "test_method", "uncertainty"]
            },
            {
                "id": "dut_description",
                "title": "Device Under Test",
                "order": 3,
                "type": "table",
                "required": True,
                "fields": ["manufacturer", "model", "serial", "imei", "frequency_bands"]
            },
            {
                "id": "test_setup",
                "title": "Test Setup and Equipment",
                "order": 4,
                "type": "table",
                "required": True,
                "fields": ["equipment", "manufacturer", "model", "serial", "calibration_date"]
            },
            {
                "id": "measurement_results",
                "title": "Measurement Results",
                "order": 5,
                "type": "table",
                "required": True
            },
            {
                "id": "compliance_statement",
                "title": "Compliance Statement",
                "order": 6,
                "type": "text",
                "required": True,
                "content_template": "The device {{ 'COMPLIES' if pass else 'DOES NOT COMPLY' }} with {{ standard }} requirements."
            },
            {
                "id": "uncertainty_analysis",
                "title": "Measurement Uncertainty",
                "order": 7,
                "type": "table",
                "required": True
            }
        ],

        regulatory_standard="3GPP TS 34.114",
        compliance_sections=[
            {"section": "6.2.1", "title": "TRP Requirements", "threshold": -10.0, "unit": "dBm"},
            {"section": "6.2.2", "title": "TIS Requirements", "threshold": -102.0, "unit": "dBm"}
        ],

        page_size="A4",
        page_orientation="portrait",
        margins={"top": 30, "right": 25, "bottom": 30, "left": 25},

        color_scheme={
            "primary": "#000000",
            "secondary": "#666666",
            "accent": "#0066cc",
            "text": "#000000",
            "background": "#ffffff"
        },

        created_by="system",
        is_active=True,
        is_default=False,
        version="1.0"
    )

    db.add(template)
    db.commit()
    db.refresh(template)
    logger.info(f"Created template: {template.name} (ID: {template.id})")
    return template


def main():
    """Initialize all default report templates"""
    logger.info("Initializing database...")
    init_db()

    logger.info("Creating default report templates...")
    db = SessionLocal()

    try:
        # Check if templates already exist
        existing_count = db.query(ReportTemplate).count()
        if existing_count > 0:
            logger.warning(f"Found {existing_count} existing templates. Skipping initialization.")
            logger.info("To reinitialize, delete existing templates first.")
            return

        # Create templates
        standard_template = create_standard_template(db)
        comparison_template = create_comparison_template(db)
        regulatory_template = create_regulatory_template(db)

        logger.info("=" * 60)
        logger.info("Successfully initialized report templates:")
        logger.info(f"  1. {standard_template.name} (default)")
        logger.info(f"  2. {comparison_template.name}")
        logger.info(f"  3. {regulatory_template.name}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error initializing templates: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
