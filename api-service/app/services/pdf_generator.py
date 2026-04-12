"""PDF Generation Service for Reports

This module generates PDF reports using ReportLab.
Integrates with ChartGenerator and TemplateRenderer for complete report generation.
Supports advanced chart types including time series with anomalies, box plots,
radar charts, and comparison bar charts.
"""
import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4, LETTER, landscape, portrait
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, ListFlowable, ListItem
)
from reportlab.pdfgen import canvas

from app.services.chart_generator import ChartGenerator
from app.services.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Service for generating PDF reports"""

    def __init__(self):
        self.chart_generator = ChartGenerator()
        self.template_renderer = TemplateRenderer()
        self.styles = getSampleStyleSheet()

        # Add custom styles
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=30,
            alignment=1  # Center
        ))

        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#333333'),
            spaceAfter=12,
            spaceBefore=12
        ))

        self.styles.add(ParagraphStyle(
            name='SubsectionTitle',
            parent=self.styles['Heading3'],
            fontSize=13,
            textColor=colors.HexColor('#555555'),
            spaceAfter=8,
            spaceBefore=8
        ))

        self.styles.add(ParagraphStyle(
            name='MetricValue',
            parent=self.styles['BodyText'],
            fontSize=11,
            textColor=colors.HexColor('#1f77b4'),
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='PassStatus',
            parent=self.styles['BodyText'],
            fontSize=11,
            textColor=colors.HexColor('#2ca02c'),  # Green
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='FailStatus',
            parent=self.styles['BodyText'],
            fontSize=11,
            textColor=colors.HexColor('#d62728'),  # Red
            fontName='Helvetica-Bold'
        ))

    def generate_report(
        self,
        report_data: Dict[str, Any],
        template: Optional[Dict[str, Any]],
        output_path: str
    ) -> str:
        """
        Generate PDF report

        Args:
            report_data: Report content and test data
            template: Report template configuration (optional - will use defaults if None)
            output_path: Path to save PDF file

        Returns:
            Path to generated PDF file
        """
        try:
            logger.info(f"Generating PDF report: {output_path}")

            # Use empty dict if template is None
            if template is None:
                template = {}

            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Get page configuration
            page_size = self._get_page_size(template.get('page_size', 'A4'))
            page_orientation = template.get('page_orientation', 'portrait')

            if page_orientation == 'landscape':
                page_size = landscape(page_size)
            else:
                page_size = portrait(page_size)

            # Get margins
            margins = template.get('margins', {})
            left_margin = margins.get('left', 20) * mm
            right_margin = margins.get('right', 20) * mm
            top_margin = margins.get('top', 25) * mm
            bottom_margin = margins.get('bottom', 25) * mm

            # Create PDF document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=page_size,
                leftMargin=left_margin,
                rightMargin=right_margin,
                topMargin=top_margin,
                bottomMargin=bottom_margin,
                title=report_data.get('title', 'Test Report'),
                author=report_data.get('generated_by', 'MIMO OTA System')
            )

            # Build story (document elements)
            story = []
            sections = template.get('sections', [])

            # If no sections defined, auto-generate based on report data
            if not sections:
                sections = self._auto_generate_sections(report_data)

            # Sort sections by order
            sections = sorted(sections, key=lambda x: x.get('order', 999))

            for section in sections:
                section_elements = self._generate_section(section, report_data, template)
                story.extend(section_elements)

                # Add page break if not the last section
                if section != sections[-1] and section.get('page_break_after', False):
                    story.append(PageBreak())

            # Build PDF
            doc.build(story)

            logger.info(f"PDF report generated successfully: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error generating PDF report: {e}")
            raise

    def _generate_section(
        self,
        section_config: Dict[str, Any],
        data: Dict[str, Any],
        template: Dict[str, Any]
    ) -> List:
        """Generate elements for a section"""
        elements = []
        section_type = section_config.get('type', 'text')

        # Add section title
        title = section_config.get('title', '')
        if title and section_type != 'cover':
            elements.append(Paragraph(title, self.styles['SectionTitle']))
            elements.append(Spacer(1, 12))

        # Generate content based on type
        if section_type == 'cover':
            elements.extend(self._generate_cover_page(data, template))
        elif section_type == 'text':
            elements.extend(self._generate_text_section(section_config, data))
        elif section_type == 'table':
            elements.extend(self._generate_table_section(section_config, data))
        elif section_type == 'mixed':
            elements.extend(self._generate_mixed_section(section_config, data, template))
        elif section_type == 'charts':
            elements.extend(self._generate_charts_section(section_config, data, template))
        elif section_type == 'execution_summary':
            elements.extend(self._generate_execution_summary_section(data))
        elif section_type == 'statistics':
            elements.extend(self._generate_statistics_section(data, template))
        elif section_type == 'time_series':
            elements.extend(self._generate_time_series_section(data, template))
        elif section_type == 'logs':
            elements.extend(self._generate_logs_section(data))
        elif section_type == 'step_details':
            elements.extend(self._generate_step_details_section(data))
        # VRT specific section types
        elif section_type == 'vrt_scenario':
            elements.extend(self._generate_vrt_scenario_section(section_config, data))
        elif section_type == 'vrt_kpi_summary':
            elements.extend(self._generate_vrt_kpi_summary_section(section_config, data))
        elif section_type == 'vrt_phases':
            elements.extend(self._generate_vrt_phases_section(data))
        elif section_type == 'vrt_trajectory':
            elements.extend(self._generate_vrt_trajectory_section(data))
        elif section_type == 'vrt_network_config':
            elements.extend(self._generate_vrt_network_config_section(data))
        elif section_type == 'vrt_events':
            elements.extend(self._generate_vrt_events_section(data))
        # Calibration specific section types
        elif section_type == 'calibration_probe_summary':
            elements.extend(self._generate_calibration_probe_section(data))
        elif section_type == 'calibration_channel_summary':
            elements.extend(self._generate_calibration_channel_section(data))

        elements.append(Spacer(1, 20))

        return elements

    def _auto_generate_sections(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Auto-generate sections based on available report data"""
        sections = []
        order = 0

        # Always add cover page
        sections.append({
            'type': 'cover',
            'order': order,
            'title': ''
        })
        order += 1

        # Add test plan info if available
        if data.get('test_plan'):
            sections.append({
                'type': 'text',
                'order': order,
                'title': 'Test Plan Information',
                'content_template': self._get_test_plan_template()
            })
            order += 1

        # Add execution summary if available
        if data.get('execution_summary'):
            sections.append({
                'type': 'execution_summary',
                'order': order,
                'title': 'Execution Summary',
                'page_break_after': False
            })
            order += 1

        # Add statistics section if available
        if data.get('statistics'):
            sections.append({
                'type': 'statistics',
                'order': order,
                'title': 'Statistical Analysis',
                'page_break_after': True
            })
            order += 1

        # Add time series charts if available
        if data.get('time_series') and data.get('chart_data'):
            sections.append({
                'type': 'time_series',
                'order': order,
                'title': 'Time Series Analysis',
                'page_break_after': True
            })
            order += 1

        # Add results table if available
        if data.get('table_data'):
            sections.append({
                'type': 'table',
                'order': order,
                'title': 'Test Results',
                'fields': ['Metric', 'Mean', 'Median', 'Std Dev', 'Min', 'Max', 'Count'],
                'style': 'striped'
            })
            order += 1

        # Add step details if available (NEW)
        if data.get('step_results') or data.get('step_configs'):
            sections.append({
                'type': 'step_details',
                'order': order,
                'title': 'Test Steps Configuration',
                'page_break_after': True
            })
            order += 1

        # Add logs if available (NEW)
        if data.get('logs'):
            sections.append({
                'type': 'logs',
                'order': order,
                'title': 'Execution Logs',
                'page_break_after': True
            })
            order += 1

        return sections

    def _get_test_plan_template(self) -> str:
        """Get template for test plan information"""
        return """
<b>Test Plan:</b> {{ test_plan.name }}

<b>Description:</b> {{ test_plan.description or 'N/A' }}

<b>Status:</b> {{ test_plan.status }}

<b>Created By:</b> {{ test_plan.created_by }}

<b>Created At:</b> {{ test_plan.created_at }}
"""

    def _generate_cover_page(
        self,
        data: Dict[str, Any],
        template: Dict[str, Any]
    ) -> List:
        """Generate cover page"""
        elements = []

        # Add logo if specified
        logo_path = template.get('logo_path')
        if logo_path and os.path.exists(logo_path):
            logo = Image(logo_path, width=100, height=100)
            logo.hAlign = 'CENTER'
            elements.append(logo)
            elements.append(Spacer(1, 30))

        # Report title
        title = data.get('title', 'Test Report')
        elements.append(Paragraph(title, self.styles['ReportTitle']))
        elements.append(Spacer(1, 50))

        # Extract test plan name from nested data if available
        test_plan_name = 'N/A'
        dut_info = 'N/A'
        if data.get('test_plan'):
            test_plan = data['test_plan']
            test_plan_name = test_plan.get('name', 'N/A')
            if test_plan.get('dut_info'):
                dut_info_dict = test_plan['dut_info']
                if isinstance(dut_info_dict, dict):
                    dut_info = dut_info_dict.get('model', dut_info_dict.get('name', str(dut_info_dict)))
                else:
                    dut_info = str(dut_info_dict)

        # Metadata table
        metadata = [
            ['Report Date:', data.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))],
            ['Test Plan:', test_plan_name],
            ['Report Type:', data.get('report_type', 'Standard')],
            ['Generated By:', data.get('generated_by', 'System')],
        ]

        if dut_info != 'N/A':
            metadata.append(['Device Under Test:', dut_info])

        # Add execution summary if available
        if data.get('execution_summary'):
            exec_summary = data['execution_summary']
            metadata.append(['Total Executions:', str(exec_summary.get('total_executions', 0))])
            pass_rate = exec_summary.get('pass_rate', 0)
            metadata.append(['Pass Rate:', f"{pass_rate:.1f}%"])

        table = Table(metadata, colWidths=[140, 300])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))

        elements.append(table)
        elements.append(PageBreak())

        return elements

    def _generate_text_section(
        self,
        config: Dict[str, Any],
        data: Dict[str, Any]
    ) -> List:
        """Generate text section"""
        elements = []

        # Render template if present
        content_template = config.get('content_template')
        if content_template:
            content = self.template_renderer.render_template(content_template, data)
        else:
            content = data.get('content', '')

        # Convert to paragraphs
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                elements.append(Paragraph(para, self.styles['BodyText']))
                elements.append(Spacer(1, 12))

        return elements

    def _generate_table_section(
        self,
        config: Dict[str, Any],
        data: Dict[str, Any]
    ) -> List:
        """Generate table section"""
        elements = []

        fields = config.get('fields', [])
        table_data = data.get('table_data', [])

        if not table_data:
            elements.append(Paragraph("No data available", self.styles['BodyText']))
            return elements

        # Build table data with headers
        table_rows = [[Paragraph(f'<b>{field}</b>', self.styles['BodyText']) for field in fields]]

        for row in table_data:
            table_row = []
            for field in fields:
                value = row.get(field, 'N/A')
                table_row.append(Paragraph(str(value), self.styles['BodyText']))
            table_rows.append(table_row)

        # Create table
        table = Table(table_rows, repeatRows=1)

        # Apply style
        table_style = config.get('style', 'striped')
        if table_style == 'striped':
            style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]
        else:
            style = [
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ]

        table.setStyle(TableStyle(style))
        elements.append(table)

        return elements

    def _generate_mixed_section(
        self,
        config: Dict[str, Any],
        data: Dict[str, Any],
        template: Dict[str, Any]
    ) -> List:
        """Generate mixed content section (text + charts + tables)"""
        elements = []

        # Add description
        if 'description' in data:
            elements.append(Paragraph(data['description'], self.styles['BodyText']))
            elements.append(Spacer(1, 12))

        # Add charts
        if config.get('include_charts', False):
            chart_data = data.get('chart_data', {})
            chart_configs = template.get('chart_configs', {})

            for chart_id, chart_config in chart_configs.items():
                if chart_id in chart_data:
                    chart_elements = self._generate_chart(chart_id, chart_data[chart_id], chart_config)
                    elements.extend(chart_elements)

        # Add tables
        if config.get('include_tables', False) and 'table_data' in data:
            # Use table_configs from template instead of section config
            table_configs = template.get('table_configs', {})

            # Use the first available table config or default to results_table
            if table_configs:
                table_config_key = list(table_configs.keys())[0]
                table_config = table_configs[table_config_key]

                # Build a config dict with fields from table_configs
                table_section_config = {
                    'title': config.get('title', ''),
                    'fields': table_config.get('columns', []),
                    'style': table_config.get('style', 'striped')
                }
                table_elements = self._generate_table_section(table_section_config, data)
                elements.extend(table_elements)

        return elements

    def _generate_charts_section(
        self,
        config: Dict[str, Any],
        data: Dict[str, Any],
        template: Dict[str, Any]
    ) -> List:
        """Generate charts section"""
        elements = []

        chart_configs = template.get('chart_configs', {})
        chart_data = data.get('chart_data', {})

        for chart_id, chart_config in chart_configs.items():
            if chart_id in chart_data:
                chart_elements = self._generate_chart(chart_id, chart_data[chart_id], chart_config)
                elements.extend(chart_elements)
                elements.append(Spacer(1, 20))

        return elements

    def _generate_chart(
        self,
        chart_id: str,
        chart_data: Dict[str, Any],
        chart_config: Dict[str, Any]
    ) -> List:
        """Generate a single chart"""
        elements = []

        try:
            # Generate chart based on type
            chart_type = chart_config.get('type', 'line')
            chart_bytes = None

            if chart_type == 'line':
                chart_bytes = self.chart_generator.generate_line_chart(chart_data, chart_config)
            elif chart_type == 'bar' or chart_type == 'grouped_bar':
                chart_bytes = self.chart_generator.generate_bar_chart(chart_data, chart_config)
            elif chart_type == 'scatter':
                chart_bytes = self.chart_generator.generate_scatter_plot(chart_data, chart_config)
            elif chart_type == 'heatmap':
                chart_bytes = self.chart_generator.generate_heatmap(chart_data, chart_config)
            elif chart_type == 'time_series_anomaly':
                chart_bytes = self.chart_generator.generate_time_series_with_anomalies(chart_data, chart_config)
            elif chart_type == 'box_plot':
                chart_bytes = self.chart_generator.generate_statistics_box_plot(chart_data, chart_config)
            elif chart_type == 'radar':
                chart_bytes = self.chart_generator.generate_performance_radar(chart_data, chart_config)
            elif chart_type == 'comparison_bar':
                chart_bytes = self.chart_generator.generate_comparison_bar(chart_data, chart_config)
            else:
                logger.warning(f"Unknown chart type: {chart_type}")
                return elements

            if chart_bytes:
                # Convert bytes to Image
                img_buffer = BytesIO(chart_bytes)
                # Adjust size based on chart type
                if chart_type == 'radar':
                    img = Image(img_buffer, width=350, height=350)
                elif chart_type in ('time_series_anomaly', 'box_plot', 'comparison_bar'):
                    img = Image(img_buffer, width=450, height=280)
                else:
                    img = Image(img_buffer, width=400, height=250)
                img.hAlign = 'CENTER'
                elements.append(img)

        except Exception as e:
            logger.error(f"Error generating chart {chart_id}: {e}")
            elements.append(Paragraph(f"Error generating chart: {chart_id}", self.styles['BodyText']))

        return elements

    def _get_page_size(self, size_name: str):
        """Get page size from name"""
        sizes = {
            'A4': A4,
            'LETTER': LETTER,
        }
        return sizes.get(size_name.upper(), A4)

    def _generate_execution_summary_section(self, data: Dict[str, Any]) -> List:
        """Generate execution summary section with pass/fail statistics"""
        elements = []

        exec_summary = data.get('execution_summary', {})
        if not exec_summary:
            elements.append(Paragraph("No execution data available", self.styles['BodyText']))
            return elements

        # Create summary statistics table
        total = exec_summary.get('total_executions', 0)
        passed = exec_summary.get('passed', 0)
        failed = exec_summary.get('failed', 0)
        pending = exec_summary.get('pending', 0)
        pass_rate = exec_summary.get('pass_rate', 0)
        duration = exec_summary.get('total_duration_sec', 0)

        # Format duration
        if duration >= 3600:
            duration_str = f"{duration/3600:.1f} hours"
        elif duration >= 60:
            duration_str = f"{duration/60:.1f} minutes"
        else:
            duration_str = f"{duration:.1f} seconds"

        summary_data = [
            ['Metric', 'Value'],
            ['Total Executions', str(total)],
            ['Passed', Paragraph(f'<font color="green">{passed}</font>', self.styles['BodyText'])],
            ['Failed', Paragraph(f'<font color="red">{failed}</font>', self.styles['BodyText'])],
            ['Pending', str(pending)],
            ['Pass Rate', f"{pass_rate:.1f}%"],
            ['Total Duration', duration_str],
        ]

        # Add time range if available
        first_exec = exec_summary.get('first_execution')
        last_exec = exec_summary.get('last_execution')
        if first_exec:
            summary_data.append(['First Execution', str(first_exec)[:19]])
        if last_exec:
            summary_data.append(['Last Execution', str(last_exec)[:19]])

        table = Table(summary_data, colWidths=[150, 200])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))

        elements.append(table)

        # Add pass/fail visualization bar if we have data
        if total > 0:
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("<b>Pass/Fail Distribution</b>", self.styles['SubsectionTitle']))

            # Create a simple visual bar using table
            pass_width = int((passed / total) * 300)
            fail_width = int((failed / total) * 300)
            pending_width = 300 - pass_width - fail_width

            bar_data = [['', '', '']]
            bar_table = Table(
                bar_data,
                colWidths=[max(pass_width, 1), max(fail_width, 1), max(pending_width, 1)]
            )
            bar_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#2ca02c')),  # Green for pass
                ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#d62728')),  # Red for fail
                ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#cccccc')),  # Gray for pending
                ('MINROWHEIGHT', (0, 0), (-1, -1), 25),
            ]))
            elements.append(bar_table)

            # Legend
            legend_text = f"<font color='#2ca02c'>■</font> Passed ({passed}) &nbsp;&nbsp; "
            legend_text += f"<font color='#d62728'>■</font> Failed ({failed}) &nbsp;&nbsp; "
            legend_text += f"<font color='#cccccc'>■</font> Pending ({pending})"
            elements.append(Spacer(1, 5))
            elements.append(Paragraph(legend_text, self.styles['BodyText']))

        return elements

    def _generate_statistics_section(
        self,
        data: Dict[str, Any],
        template: Dict[str, Any]
    ) -> List:
        """Generate statistics section with charts and tables"""
        elements = []

        statistics = data.get('statistics', {})
        if not statistics:
            elements.append(Paragraph("No statistical data available", self.styles['BodyText']))
            return elements

        # Add statistics comparison chart (bar chart with means and std)
        chart_data = data.get('chart_data', {})
        if 'statistics_comparison' in chart_data:
            elements.append(Paragraph("<b>Metrics Overview</b>", self.styles['SubsectionTitle']))
            elements.append(Spacer(1, 10))

            chart_config = {
                'type': 'comparison_bar',
                'title': 'Statistics Comparison',
                'x_axis': {'label': 'Metric'},
                'y_axis': {'label': 'Value'},
                'show_values': True
            }
            chart_elements = self._generate_chart(
                'statistics_comparison',
                chart_data['statistics_comparison'],
                chart_config
            )
            elements.extend(chart_elements)
            elements.append(Spacer(1, 20))

        # Add detailed statistics table
        elements.append(Paragraph("<b>Detailed Statistics</b>", self.styles['SubsectionTitle']))
        elements.append(Spacer(1, 10))

        # Build statistics table
        table_rows = [[
            Paragraph('<b>Metric</b>', self.styles['BodyText']),
            Paragraph('<b>Mean</b>', self.styles['BodyText']),
            Paragraph('<b>Median</b>', self.styles['BodyText']),
            Paragraph('<b>Std Dev</b>', self.styles['BodyText']),
            Paragraph('<b>Min</b>', self.styles['BodyText']),
            Paragraph('<b>Max</b>', self.styles['BodyText']),
            Paragraph('<b>Count</b>', self.styles['BodyText']),
        ]]

        for metric_name, stats in statistics.items():
            if isinstance(stats, dict):
                table_rows.append([
                    Paragraph(metric_name, self.styles['BodyText']),
                    f"{stats.get('mean', 0):.3f}",
                    f"{stats.get('median', 0):.3f}",
                    f"{stats.get('std', 0):.3f}",
                    f"{stats.get('min', 0):.3f}",
                    f"{stats.get('max', 0):.3f}",
                    str(stats.get('count', 0)),
                ])

        if len(table_rows) > 1:
            table = Table(table_rows, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(table)

        # Add box plot for distribution visualization if we have measurements
        measurements = data.get('measurements', {})
        if measurements:
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("<b>Value Distribution</b>", self.styles['SubsectionTitle']))
            elements.append(Spacer(1, 10))

            box_data = {
                'metrics': list(measurements.keys())[:8],  # Limit to 8 metrics for readability
                'values': {k: v for k, v in list(measurements.items())[:8]}
            }
            box_config = {
                'type': 'box_plot',
                'title': 'Metric Value Distribution',
                'show_mean': True
            }
            chart_elements = self._generate_chart('box_plot', box_data, box_config)
            elements.extend(chart_elements)

        return elements

    def _generate_time_series_section(
        self,
        data: Dict[str, Any],
        template: Dict[str, Any]
    ) -> List:
        """Generate time series section with anomaly detection charts"""
        elements = []

        time_series = data.get('time_series', [])
        chart_data = data.get('chart_data', {})

        if not time_series and not chart_data:
            elements.append(Paragraph("No time series data available", self.styles['BodyText']))
            return elements

        # Find time series chart data
        time_series_charts = {k: v for k, v in chart_data.items() if k.startswith('time_series_')}

        if not time_series_charts:
            elements.append(Paragraph("No time series charts available", self.styles['BodyText']))
            return elements

        # Generate charts for each metric
        for chart_id, ts_data in time_series_charts.items():
            metric_name = chart_id.replace('time_series_', '')

            elements.append(Paragraph(f"<b>{metric_name}</b>", self.styles['SubsectionTitle']))
            elements.append(Spacer(1, 10))

            chart_config = {
                'type': 'time_series_anomaly',
                'title': f'{metric_name} Over Time',
                'metric_name': metric_name,
                'x_axis': {'label': 'Time'},
                'y_axis': {'label': metric_name}
            }
            chart_elements = self._generate_chart(chart_id, ts_data, chart_config)
            elements.extend(chart_elements)
            elements.append(Spacer(1, 15))

            # Add anomaly summary if there are anomalies
            anomaly_indices = ts_data.get('anomaly_indices', [])
            if anomaly_indices:
                anomaly_count = len(anomaly_indices)
                total_points = len(ts_data.get('values', []))
                anomaly_rate = (anomaly_count / total_points * 100) if total_points > 0 else 0

                elements.append(Paragraph(
                    f"<i>Detected {anomaly_count} anomalies ({anomaly_rate:.1f}% of data points)</i>",
                    self.styles['BodyText']
                ))
                elements.append(Spacer(1, 20))

        return elements

    def _generate_logs_section(self, data: Dict[str, Any]) -> List:
        """Generate execution logs section"""
        elements = []
        logs = data.get('logs', [])
        
        if not logs:
            elements.append(Paragraph("No execution logs available", self.styles['BodyText']))
            return elements

        # Log table header
        table_rows = [[
            Paragraph('<b>Time</b>', self.styles['BodyText']),
            Paragraph('<b>Level</b>', self.styles['BodyText']),
            Paragraph('<b>Source</b>', self.styles['BodyText']),
            Paragraph('<b>Message</b>', self.styles['BodyText']),
        ]]

        for log in logs:
            # Format timestamp
            timestamp_str = str(log.get('timestamp', ''))
            if 'T' in timestamp_str:
                timestamp_str = timestamp_str.replace('T', ' ')[:19]
            
            # Color code level
            level = log.get('level', 'INFO')
            level_color = "black"
            if level == 'ERROR':
                level_color = "red"
            elif level == 'WARNING':
                level_color = "orange"
                
            table_rows.append([
                Paragraph(timestamp_str, self.styles['BodyText']),
                Paragraph(f'<font color="{level_color}">{level}</font>', self.styles['BodyText']),
                Paragraph(log.get('source', '-'), self.styles['BodyText']),
                Paragraph(log.get('message', ''), self.styles['BodyText']),
            ])

        if len(table_rows) > 1:
            table = Table(table_rows, colWidths=[90, 50, 60, 250], repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#666666')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elements.append(table)

        return elements

    def _generate_step_details_section(self, data: Dict[str, Any]) -> List:
        """Generate detailed step configuration section"""
        elements = []
        
        # Try to get steps from step_results (General) or step_configs (VRT)
        steps = data.get('step_results') or data.get('step_configs') or []
        
        if not steps:
            elements.append(Paragraph("No step configuration available", self.styles['BodyText']))
            return elements

        for i, step in enumerate(steps):
            # Step Header
            step_name = step.get('name') or step.get('step_name') or f"Step {i+1}"
            elements.append(Paragraph(f"{i+1}. {step_name}", self.styles['SubsectionTitle']))
            
            # Parameters Table
            params = step.get('parameters', {})
            if params:
                param_rows = [[
                    Paragraph('<b>Parameter</b>', self.styles['BodyText']),
                    Paragraph('<b>Value</b>', self.styles['BodyText'])
                ]]
                
                for k, v in params.items():
                    # Handle nested dict/list in values
                    val_str = str(v)
                    if isinstance(v, (dict, list)):
                        import json
                        try:
                            val_str = json.dumps(v, ensure_ascii=False)
                        except (TypeError, ValueError) as e:
                            logger.warning(f"Failed to serialize parameter '{k}': {e}")
                            val_str = str(v)
                            
                    param_rows.append([
                        Paragraph(k, self.styles['BodyText']),
                        Paragraph(val_str, self.styles['BodyText'])
                    ])
                
                if len(param_rows) > 1:
                    table = Table(param_rows, colWidths=[150, 300])
                    table.setStyle(TableStyle([
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('PADDING', (0, 0), (-1, -1), 4),
                    ]))
                    elements.append(table)
            else:
                elements.append(Paragraph("<i>No parameters configured</i>", self.styles['BodyText']))
            
            elements.append(Spacer(1, 10))

        return elements

    # ==================== VRT Specific Section Generators ====================

    def _generate_vrt_scenario_section(
        self,
        section_config: Dict[str, Any],
        data: Dict[str, Any]
    ) -> List:
        """Generate VRT scenario information section"""
        elements = []

        scenario = data.get('scenario', {})
        if not scenario and 'scenario_name' in data:
            # Fallback: construct from flat data
            scenario = {
                'name': data.get('scenario_name', 'Unknown'),
                'category': data.get('category', 'N/A'),
                'description': data.get('description', ''),
            }

        if not scenario:
            elements.append(Paragraph("<i>No scenario information available</i>", self.styles['BodyText']))
            return elements

        # Scenario info table
        info_rows = [
            [Paragraph('<b>Property</b>', self.styles['BodyText']),
             Paragraph('<b>Value</b>', self.styles['BodyText'])]
        ]

        field_mapping = {
            'name': 'Scenario Name',
            'category': 'Category',
            'description': 'Description',
            'duration_s': 'Duration (s)',
            'total_distance_km': 'Distance (km)',
            'average_speed_kmh': 'Avg Speed (km/h)',
            'max_speed_kmh': 'Max Speed (km/h)',
        }

        for key, label in field_mapping.items():
            value = scenario.get(key)
            if value is not None:
                info_rows.append([
                    Paragraph(label, self.styles['BodyText']),
                    Paragraph(str(value), self.styles['BodyText'])
                ])

        if len(info_rows) > 1:
            table = Table(info_rows, colWidths=[150, 350])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565c0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (0, -1), colors.whitesmoke),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(table)

        # Route info if available
        route = data.get('route', scenario.get('route', {}))
        if route:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph('<b>Route Information</b>', self.styles['BodyText']))
            elements.append(Spacer(1, 6))

            route_text = f"Start: {route.get('start_location', 'N/A')} → End: {route.get('end_location', 'N/A')}"
            if route.get('waypoints'):
                route_text += f" (via {len(route.get('waypoints', []))} waypoints)"
            elements.append(Paragraph(route_text, self.styles['BodyText']))

        return elements

    def _generate_vrt_kpi_summary_section(
        self,
        section_config: Dict[str, Any],
        data: Dict[str, Any]
    ) -> List:
        """Generate VRT KPI summary section with pass/fail indicators"""
        elements = []

        kpi_summary = data.get('kpi_summary', [])
        if not kpi_summary:
            elements.append(Paragraph("<i>No KPI data available</i>", self.styles['BodyText']))
            return elements

        # KPI summary table
        kpi_rows = [
            [Paragraph('<b>KPI Metric</b>', self.styles['BodyText']),
             Paragraph('<b>Mean</b>', self.styles['BodyText']),
             Paragraph('<b>Min</b>', self.styles['BodyText']),
             Paragraph('<b>Max</b>', self.styles['BodyText']),
             Paragraph('<b>Target</b>', self.styles['BodyText']),
             Paragraph('<b>Result</b>', self.styles['BodyText'])]
        ]

        for kpi in kpi_summary:
            name = kpi.get('name', 'Unknown')
            mean = kpi.get('mean', 0)
            min_val = kpi.get('min', 0)
            max_val = kpi.get('max', 0)
            target = kpi.get('target', 'N/A')
            passed = kpi.get('passed', None)

            # Format result with color indicator
            if passed is True:
                result_text = '✓ PASS'
                result_color = colors.HexColor('#43a047')
            elif passed is False:
                result_text = '✗ FAIL'
                result_color = colors.HexColor('#e53935')
            else:
                result_text = '- N/A'
                result_color = colors.gray

            kpi_rows.append([
                Paragraph(name, self.styles['BodyText']),
                Paragraph(f'{mean:.2f}' if isinstance(mean, (int, float)) else str(mean), self.styles['BodyText']),
                Paragraph(f'{min_val:.2f}' if isinstance(min_val, (int, float)) else str(min_val), self.styles['BodyText']),
                Paragraph(f'{max_val:.2f}' if isinstance(max_val, (int, float)) else str(max_val), self.styles['BodyText']),
                Paragraph(str(target), self.styles['BodyText']),
                Paragraph(f'<font color="{result_color}">{result_text}</font>', self.styles['BodyText'])
            ])

        table = Table(kpi_rows, colWidths=[100, 70, 70, 70, 70, 70])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565c0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ]))
        elements.append(table)

        # Overall pass rate
        overall_result = data.get('overall_result', 'incomplete')
        pass_rate = data.get('pass_rate', 0)
        elements.append(Spacer(1, 12))

        result_color = '#43a047' if overall_result == 'passed' else '#e53935' if overall_result == 'failed' else '#ff9800'
        elements.append(Paragraph(
            f'<b>Overall Result:</b> <font color="{result_color}">{overall_result.upper()}</font> '
            f'(Pass Rate: {pass_rate}%)',
            self.styles['BodyText']
        ))

        return elements

    def _generate_vrt_phases_section(self, data: Dict[str, Any]) -> List:
        """Generate VRT phases/stages results section"""
        elements = []

        phases = data.get('phases', [])
        if not phases:
            elements.append(Paragraph("<i>No phase data available</i>", self.styles['BodyText']))
            return elements

        # Phases table
        phase_rows = [
            [Paragraph('<b>Phase</b>', self.styles['BodyText']),
             Paragraph('<b>Duration</b>', self.styles['BodyText']),
             Paragraph('<b>Status</b>', self.styles['BodyText']),
             Paragraph('<b>Pass Rate</b>', self.styles['BodyText']),
             Paragraph('<b>Notes</b>', self.styles['BodyText'])]
        ]

        for phase in phases:
            name = phase.get('name') or phase.get('phase_name') or 'Unknown'
            duration = phase.get('duration_s') or phase.get('duration') or 0
            status = phase.get('status') or phase.get('result') or 'unknown'
            pass_rate = phase.get('pass_rate', 100 if status == 'passed' else 0)
            notes = phase.get('notes') or phase.get('description') or ''

            # Color based on status
            if status in ['passed', 'pass', 'success']:
                status_text = f'<font color="#43a047">✓ {status}</font>'
            elif status in ['failed', 'fail', 'error']:
                status_text = f'<font color="#e53935">✗ {status}</font>'
            else:
                status_text = str(status)

            # Safely handle notes that might be None
            notes_str = str(notes) if notes else ''
            notes_display = notes_str[:50] + '...' if len(notes_str) > 50 else notes_str

            phase_rows.append([
                Paragraph(str(name), self.styles['BodyText']),
                Paragraph(f'{duration:.1f}s' if isinstance(duration, (int, float)) else str(duration), self.styles['BodyText']),
                Paragraph(status_text, self.styles['BodyText']),
                Paragraph(f'{pass_rate}%', self.styles['BodyText']),
                Paragraph(notes_display, self.styles['BodyText'])
            ])

        table = Table(phase_rows, colWidths=[100, 70, 80, 70, 130])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565c0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(table)

        return elements

    def _generate_vrt_trajectory_section(self, data: Dict[str, Any]) -> List:
        """Generate VRT trajectory visualization section"""
        elements = []

        trajectory = data.get('trajectory', [])
        if not trajectory:
            elements.append(Paragraph("<i>No trajectory data available</i>", self.styles['BodyText']))
            return elements

        # Summary statistics
        if trajectory:
            total_points = len(trajectory)
            start_point = trajectory[0] if trajectory else {}
            end_point = trajectory[-1] if trajectory else {}

            elements.append(Paragraph(
                f'<b>Trajectory Summary:</b> {total_points} data points recorded',
                self.styles['BodyText']
            ))
            elements.append(Spacer(1, 6))

            if start_point.get('lat') and start_point.get('lon'):
                elements.append(Paragraph(
                    f'Start: ({start_point.get("lat", 0):.6f}, {start_point.get("lon", 0):.6f})',
                    self.styles['BodyText']
                ))
            if end_point.get('lat') and end_point.get('lon'):
                elements.append(Paragraph(
                    f'End: ({end_point.get("lat", 0):.6f}, {end_point.get("lon", 0):.6f})',
                    self.styles['BodyText']
                ))

        # Note about visualization
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            '<i>Note: Interactive trajectory map is available in the web interface.</i>',
            self.styles['BodyText']
        ))

        return elements

    def _generate_vrt_network_config_section(self, data: Dict[str, Any]) -> List:
        """Generate VRT network configuration section"""
        elements = []

        network = data.get('network', data.get('network_config_detail', {}))
        if not network:
            elements.append(Paragraph("<i>No network configuration available</i>", self.styles['BodyText']))
            return elements

        # Network config table
        config_rows = [
            [Paragraph('<b>Parameter</b>', self.styles['BodyText']),
             Paragraph('<b>Value</b>', self.styles['BodyText'])]
        ]

        # Extract common network parameters
        network_params = {
            'Technology': network.get('technology', network.get('rat', 'N/A')),
            'Frequency Band': network.get('frequency_band', network.get('band', 'N/A')),
            'Bandwidth': network.get('bandwidth', 'N/A'),
            'Duplex Mode': network.get('duplex_mode', 'N/A'),
            'MIMO Config': network.get('mimo_config', network.get('antenna_config', 'N/A')),
            'Channel Model': network.get('channel_model', 'N/A'),
        }

        for param, value in network_params.items():
            if value and value != 'N/A':
                config_rows.append([
                    Paragraph(param, self.styles['BodyText']),
                    Paragraph(str(value), self.styles['BodyText'])
                ])

        if len(config_rows) > 1:
            table = Table(config_rows, colWidths=[150, 300])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565c0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (0, 1), (0, -1), colors.whitesmoke),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(table)

        # Base station info if available
        base_stations = data.get('base_stations', [])
        if base_stations:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(f'<b>Base Stations:</b> {len(base_stations)} configured', self.styles['BodyText']))

        return elements

    def _generate_vrt_events_section(self, data: Dict[str, Any]) -> List:
        """Generate VRT events and handovers section"""
        elements = []

        events = data.get('events', [])
        if not events:
            elements.append(Paragraph("<i>No events recorded during execution</i>", self.styles['BodyText']))
            return elements

        # Events table
        event_rows = [
            [Paragraph('<b>Time</b>', self.styles['BodyText']),
             Paragraph('<b>Event Type</b>', self.styles['BodyText']),
             Paragraph('<b>Details</b>', self.styles['BodyText'])]
        ]

        for event in events[:50]:  # Limit to first 50 events
            time_s = event.get('time_s', event.get('timestamp', 0))
            event_type = event.get('type', event.get('event_type', 'Unknown'))
            details = event.get('details', event.get('description', event.get('message', '')))

            # Format time
            time_str = f'{time_s:.1f}s' if isinstance(time_s, (int, float)) else str(time_s)

            event_rows.append([
                Paragraph(time_str, self.styles['BodyText']),
                Paragraph(event_type, self.styles['BodyText']),
                Paragraph(details[:80] + '...' if len(str(details)) > 80 else str(details), self.styles['BodyText'])
            ])

        table = Table(event_rows, colWidths=[60, 100, 290])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565c0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(table)

        if len(events) > 50:
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(
                f'<i>Showing first 50 of {len(events)} events. Full log available in execution details.</i>',
                self.styles['BodyText']
            ))

        return elements

    # ==================== Calibration Report Section Generators ====================

    def _generate_calibration_probe_section(self, data: Dict[str, Any]) -> List:
        """Generate probe calibration summary section"""
        elements = []

        probe_cal = data.get('probe_calibration', {})
        if not probe_cal:
            elements.append(Paragraph("<i>No probe calibration data available</i>", self.styles['BodyText']))
            return elements

        # Probe summary statistics
        probe_summary = data.get('probe_summary', {})
        if probe_summary:
            elements.append(Paragraph('<b>Probe Calibration Overview</b>', self.styles['SubsectionTitle']))
            elements.append(Spacer(1, 8))

            summary_data = [
                ['Metric', 'Value'],
                ['Total Calibrations', str(probe_summary.get('total_executions', 0))],
                ['Passed', Paragraph(f'<font color="green">{probe_summary.get("passed", 0)}</font>', self.styles['BodyText'])],
                ['Failed', Paragraph(f'<font color="red">{probe_summary.get("failed", 0)}</font>', self.styles['BodyText'])],
                ['Pass Rate', f"{probe_summary.get('pass_rate', 0):.1f}%"],
            ]

            table = Table(summary_data, colWidths=[150, 150])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4caf50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 15))

        # Calibration type breakdown
        cal_types = [
            ('amplitude', 'Amplitude Calibration', '探头 TX/RX 增益校准'),
            ('phase', 'Phase Calibration', '相位偏差和群时延校准'),
            ('polarization', 'Polarization Calibration', 'XPD 和轴比校准'),
            ('pattern', 'Pattern Calibration', '3D 辐射方向图校准'),
            ('link', 'Link Calibration', '端到端链路验证'),
        ]

        for cal_type, title, description in cal_types:
            cal_data = probe_cal.get(cal_type, [])
            if cal_data:
                elements.append(Paragraph(f'<b>{title}</b>', self.styles['SubsectionTitle']))
                elements.append(Paragraph(f'<i>{description}</i>', self.styles['BodyText']))
                elements.append(Spacer(1, 6))

                # Create table for this calibration type
                if cal_type == 'amplitude':
                    headers = ['Probe ID', 'Polarization', 'Status', 'Calibrated At']
                    rows = [headers]
                    for cal in cal_data[:20]:  # Limit to 20 entries
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            str(cal.get('probe_id', '-')),
                            cal.get('polarization', '-'),
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                            str(cal.get('calibrated_at', '-'))[:19],
                        ])
                elif cal_type == 'phase':
                    headers = ['Probe ID', 'Ref Probe', 'Status', 'Calibrated At']
                    rows = [headers]
                    for cal in cal_data[:20]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            str(cal.get('probe_id', '-')),
                            str(cal.get('reference_probe_id', '-')),
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                            str(cal.get('calibrated_at', '-'))[:19],
                        ])
                else:
                    headers = ['Probe ID', 'Status', 'Calibrated At']
                    rows = [headers]
                    for cal in cal_data[:20]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            str(cal.get('probe_id', '-')),
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                            str(cal.get('calibrated_at', '-'))[:19],
                        ])

                if len(rows) > 1:
                    table = Table(rows, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#81c784')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('PADDING', (0, 0), (-1, -1), 4),
                    ]))
                    elements.append(table)

                if len(cal_data) > 20:
                    elements.append(Paragraph(
                        f'<i>Showing 20 of {len(cal_data)} calibrations</i>',
                        self.styles['BodyText']
                    ))

                elements.append(Spacer(1, 12))

        return elements

    def _generate_calibration_channel_section(self, data: Dict[str, Any]) -> List:
        """Generate channel calibration summary section"""
        elements = []

        channel_cal = data.get('channel_calibration', {})
        if not channel_cal:
            elements.append(Paragraph("<i>No channel calibration data available</i>", self.styles['BodyText']))
            return elements

        # Channel summary statistics
        channel_summary = data.get('channel_summary', {})
        if channel_summary:
            elements.append(Paragraph('<b>Channel Calibration Overview</b>', self.styles['SubsectionTitle']))
            elements.append(Spacer(1, 8))

            summary_data = [
                ['Metric', 'Value'],
                ['Total Calibrations', str(channel_summary.get('total_executions', 0))],
                ['Passed', Paragraph(f'<font color="green">{channel_summary.get("passed", 0)}</font>', self.styles['BodyText'])],
                ['Failed', Paragraph(f'<font color="red">{channel_summary.get("failed", 0)}</font>', self.styles['BodyText'])],
                ['Pass Rate', f"{channel_summary.get('pass_rate', 0):.1f}%"],
            ]

            table = Table(summary_data, colWidths=[150, 150])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976d2')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 15))

        # Calibration type breakdown
        cal_types = [
            ('temporal', 'Temporal (PDP) Calibration', 'RMS 时延扩展验证'),
            ('doppler', 'Doppler Calibration', 'Jakes 多普勒频谱验证'),
            ('spatial_correlation', 'Spatial Correlation Calibration', 'MIMO 空间相关性验证'),
            ('angular_spread', 'Angular Spread Calibration', '角度扩展验证'),
            ('quiet_zone', 'Quiet Zone Calibration', '静区场均匀性验证'),
            ('eis', 'EIS Validation', '等效全向灵敏度验证'),
        ]

        for cal_type, title, description in cal_types:
            cal_data = channel_cal.get(cal_type, [])
            if cal_data:
                elements.append(Paragraph(f'<b>{title}</b>', self.styles['SubsectionTitle']))
                elements.append(Paragraph(f'<i>{description}</i>', self.styles['BodyText']))
                elements.append(Spacer(1, 6))

                # Create table for this calibration type
                if cal_type == 'temporal':
                    headers = ['Scenario', 'Condition', 'Freq (GHz)', 'RMS Delay Error', 'Status']
                    rows = [headers]
                    for cal in cal_data[:15]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        error = cal.get('rms_delay_spread_error_percent', 0)
                        rows.append([
                            cal.get('scenario_type', '-'),
                            cal.get('scenario_condition', '-'),
                            str(cal.get('fc_ghz', '-')),
                            f"{error:.1f}%" if error else '-',
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                        ])
                elif cal_type == 'doppler':
                    headers = ['Velocity (km/h)', 'Freq (GHz)', 'Doppler (Hz)', 'Target (Hz)', 'Status']
                    rows = [headers]
                    for cal in cal_data[:15]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            str(cal.get('velocity_kmh', '-')),
                            str(cal.get('fc_ghz', '-')),
                            f"{cal.get('max_doppler_measured_hz', 0):.1f}",
                            f"{cal.get('max_doppler_target_hz', 0):.1f}",
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                        ])
                elif cal_type == 'spatial_correlation':
                    headers = ['Scenario', 'Condition', 'Spacing (λ)', 'Correlation', 'Status']
                    rows = [headers]
                    for cal in cal_data[:15]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            cal.get('scenario_type', '-'),
                            cal.get('scenario_condition', '-'),
                            str(cal.get('antenna_spacing_wavelengths', '-')),
                            f"{cal.get('measured_correlation', 0):.3f}",
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                        ])
                elif cal_type == 'angular_spread':
                    headers = ['Scenario', 'Condition', 'Measured (°)', 'Target (°)', 'Status']
                    rows = [headers]
                    for cal in cal_data[:15]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            cal.get('scenario_type', '-'),
                            cal.get('scenario_condition', '-'),
                            f"{cal.get('azimuth_spread_measured_deg', 0):.1f}",
                            f"{cal.get('azimuth_spread_target_deg', 0):.1f}",
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                        ])
                elif cal_type == 'quiet_zone':
                    headers = ['Shape', 'Diameter (m)', 'Amp Uniform (dB)', 'Phase Uniform (°)', 'Status']
                    rows = [headers]
                    for cal in cal_data[:15]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            cal.get('quiet_zone_shape', '-'),
                            str(cal.get('quiet_zone_diameter_m', '-')),
                            f"±{cal.get('amplitude_uniformity_db', 0):.2f}",
                            f"±{cal.get('phase_uniformity_deg', 0):.1f}",
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                        ])
                elif cal_type == 'eis':
                    headers = ['DUT Model', 'Type', 'Measured (dBm)', 'Error (dB)', 'Status']
                    rows = [headers]
                    for cal in cal_data[:15]:
                        status = '✓ PASS' if cal.get('validation_pass') else '✗ FAIL'
                        status_color = '#43a047' if cal.get('validation_pass') else '#e53935'
                        rows.append([
                            cal.get('dut_model', '-')[:20],
                            cal.get('dut_type', '-'),
                            f"{cal.get('eis_measured_dbm', 0):.1f}",
                            f"{cal.get('eis_error_db', 0):.2f}",
                            Paragraph(f'<font color="{status_color}">{status}</font>', self.styles['BodyText']),
                        ])
                else:
                    continue

                if len(rows) > 1:
                    table = Table(rows, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#64b5f6')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('PADDING', (0, 0), (-1, -1), 4),
                    ]))
                    elements.append(table)

                if len(cal_data) > 15:
                    elements.append(Paragraph(
                        f'<i>Showing 15 of {len(cal_data)} calibrations</i>',
                        self.styles['BodyText']
                    ))

                elements.append(Spacer(1, 12))

        return elements
