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

                anomaly_text = f"<font color='#d62728'>⚠ {anomaly_count} anomalies detected</font> "
                anomaly_text += f"({anomaly_rate:.1f}% of measurements)"
                elements.append(Paragraph(anomaly_text, self.styles['BodyText']))
                elements.append(Spacer(1, 20))

        return elements
