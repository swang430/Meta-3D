"""PDF Generation Service for Reports

This module generates PDF reports using ReportLab.
Integrates with ChartGenerator and TemplateRenderer for complete report generation.
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
    PageBreak, Image, KeepTogether
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

    def generate_report(
        self,
        report_data: Dict[str, Any],
        template: Dict[str, Any],
        output_path: str
    ) -> str:
        """
        Generate PDF report

        Args:
            report_data: Report content and test data
            template: Report template configuration
            output_path: Path to save PDF file

        Returns:
            Path to generated PDF file
        """
        try:
            logger.info(f"Generating PDF report: {output_path}")

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

        elements.append(Spacer(1, 20))

        return elements

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

        # Metadata table
        metadata = [
            ['Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['Test Plan:', data.get('test_plan_name', 'N/A')],
            ['Report Type:', data.get('report_type', 'Standard')],
            ['Generated By:', data.get('generated_by', 'System')],
        ]

        if 'dut_info' in data:
            metadata.append(['Device Under Test:', data['dut_info']])

        table = Table(metadata, colWidths=[120, 300])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
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

            if chart_type == 'line':
                chart_bytes = self.chart_generator.generate_line_chart(chart_data, chart_config)
            elif chart_type == 'bar' or chart_type == 'grouped_bar':
                chart_bytes = self.chart_generator.generate_bar_chart(chart_data, chart_config)
            elif chart_type == 'scatter':
                chart_bytes = self.chart_generator.generate_scatter_plot(chart_data, chart_config)
            elif chart_type == 'heatmap':
                chart_bytes = self.chart_generator.generate_heatmap(chart_data, chart_config)
            else:
                logger.warning(f"Unknown chart type: {chart_type}")
                return elements

            # Convert bytes to Image
            img_buffer = BytesIO(chart_bytes)
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
