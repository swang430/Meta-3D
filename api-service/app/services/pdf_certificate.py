"""
PDF Certificate Generation Service

Generates professional PDF calibration certificates using ReportLab
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
from datetime import datetime
import os
from typing import Optional

from app.models.calibration import CalibrationCertificate


class PDFCertificateGenerator:
    """
    Generate professional calibration certificates in PDF format
    """

    def __init__(self, output_dir: str = "./certificates"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Define styles
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1864ab'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        self.heading_style = ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1864ab'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        )
        self.body_style = ParagraphStyle(
            'CustomBody',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
        )

    def generate_certificate(self, certificate: CalibrationCertificate) -> str:
        """
        Generate PDF certificate

        Args:
            certificate: CalibrationCertificate model instance

        Returns:
            str: Path to generated PDF file
        """
        # Output file path
        filename = f"{certificate.certificate_number}.pdf"
        output_path = os.path.join(self.output_dir, filename)

        # Create PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        # Build content
        story = []

        # Header / Title
        story.append(Paragraph("校准证书", self.title_style))
        story.append(Paragraph("CALIBRATION CERTIFICATE", self.title_style))
        story.append(Spacer(1, 0.5*cm))

        # Certificate number
        cert_num_style = ParagraphStyle(
            'CertNum',
            parent=self.styles['Normal'],
            fontSize=12,
            alignment=TA_CENTER,
            textColor=colors.grey
        )
        story.append(Paragraph(f"证书编号 / Certificate No.: <b>{certificate.certificate_number}</b>", cert_num_style))
        story.append(Spacer(1, 1*cm))

        # System Information
        story.append(Paragraph("1. 被校准系统信息 / System Information", self.heading_style))

        system_data = [
            ['系统名称 / System Name:', certificate.system_name or 'N/A'],
            ['序列号 / Serial Number:', certificate.system_serial_number or 'N/A'],
            ['探头数量 / Number of Probes:', str(certificate.system_configuration.get('num_probes', 'N/A')) if certificate.system_configuration else 'N/A'],
            ['暗室半径 / Chamber Radius:', f"{certificate.system_configuration.get('chamber_radius_m', 'N/A')} m" if certificate.system_configuration else 'N/A'],
            ['频率范围 / Frequency Range:', f"{certificate.system_configuration.get('frequency_range_mhz', ['N/A', 'N/A'])[0]}-{certificate.system_configuration.get('frequency_range_mhz', ['N/A', 'N/A'])[1]} MHz" if certificate.system_configuration else 'N/A'],
        ]

        system_table = Table(system_data, colWidths=[8*cm, 9*cm])
        system_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f3f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(system_table)
        story.append(Spacer(1, 0.5*cm))

        # Laboratory Information
        story.append(Paragraph("2. 校准实验室信息 / Laboratory Information", self.heading_style))

        lab_data = [
            ['实验室名称 / Laboratory:', certificate.lab_name or 'N/A'],
            ['地址 / Address:', certificate.lab_address or 'N/A'],
            ['认证 / Accreditation:', certificate.lab_accreditation or 'N/A'],
            ['认证机构 / Accreditation Body:', certificate.lab_accreditation_body or 'N/A'],
        ]

        lab_table = Table(lab_data, colWidths=[8*cm, 9*cm])
        lab_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f3f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(lab_table)
        story.append(Spacer(1, 0.5*cm))

        # Calibration Dates
        story.append(Paragraph("3. 校准日期 / Calibration Dates", self.heading_style))

        date_data = [
            ['校准日期 / Calibration Date:', certificate.calibration_date.strftime('%Y-%m-%d')],
            ['有效期至 / Valid Until:', certificate.valid_until.strftime('%Y-%m-%d')],
        ]

        date_table = Table(date_data, colWidths=[8*cm, 9*cm])
        date_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f3f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(date_table)
        story.append(Spacer(1, 0.5*cm))

        # Calibration Results
        story.append(Paragraph("4. 校准结果 / Calibration Results", self.heading_style))

        # Determine colors based on pass/fail
        trp_color = colors.HexColor('#51cf66') if certificate.trp_pass else colors.HexColor('#ff6b6b')
        tis_color = colors.HexColor('#51cf66') if certificate.tis_pass else colors.HexColor('#ff6b6b')
        repeat_color = colors.HexColor('#51cf66') if certificate.repeatability_pass else colors.HexColor('#ff6b6b')
        overall_color = colors.HexColor('#51cf66') if certificate.overall_pass else colors.HexColor('#ff6b6b')

        results_data = [
            ['校准项目 / Item', '结果 / Result', '标准 / Standard', '状态 / Status'],
            [
                'TRP 误差 / TRP Error',
                f'±{certificate.trp_error_db:.2f} dB' if certificate.trp_error_db is not None else 'N/A',
                '±0.5 dB',
                '通过 / PASS' if certificate.trp_pass else '未通过 / FAIL'
            ],
            [
                'TIS 误差 / TIS Error',
                f'±{certificate.tis_error_db:.2f} dB' if certificate.tis_error_db is not None else 'N/A',
                '±1.0 dB',
                '通过 / PASS' if certificate.tis_pass else '未通过 / FAIL'
            ],
            [
                '可重复性 / Repeatability (σ)',
                f'{certificate.repeatability_std_dev_db:.2f} dB' if certificate.repeatability_std_dev_db is not None else 'N/A',
                '< 0.3 dB',
                '通过 / PASS' if certificate.repeatability_pass else '未通过 / FAIL'
            ],
        ]

        results_table = Table(results_data, colWidths=[6*cm, 4*cm, 3*cm, 4*cm])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1864ab')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            # Row-specific status coloring
            ('BACKGROUND', (3, 1), (3, 1), trp_color),
            ('BACKGROUND', (3, 2), (3, 2), tis_color),
            ('BACKGROUND', (3, 3), (3, 3), repeat_color),
        ]))
        story.append(results_table)
        story.append(Spacer(1, 0.3*cm))

        # Overall Result
        overall_data = [
            ['总体结果 / Overall Result:', '合格 / QUALIFIED' if certificate.overall_pass else '不合格 / NOT QUALIFIED']
        ]
        overall_table = Table(overall_data, colWidths=[8*cm, 9*cm])
        overall_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f1f3f5')),
            ('BACKGROUND', (1, 0), (1, 0), overall_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        story.append(overall_table)
        story.append(Spacer(1, 0.5*cm))

        # Standards
        story.append(Paragraph("5. 适用标准 / Applicable Standards", self.heading_style))
        if certificate.standards:
            for std in certificate.standards:
                story.append(Paragraph(f"• {std}", self.body_style))
        else:
            story.append(Paragraph("• 3GPP TS 34.114", self.body_style))
            story.append(Paragraph("• CTIA OTA Test Plan Ver. 4.0", self.body_style))
        story.append(Spacer(1, 0.5*cm))

        # Signatures
        story.append(Paragraph("6. 签名 / Signatures", self.heading_style))

        sig_data = [
            ['校准工程师 / Calibrated By:', certificate.calibrated_by or ''],
            ['技术审核 / Reviewed By:', certificate.reviewed_by or ''],
            ['签发日期 / Issue Date:', certificate.issued_at.strftime('%Y-%m-%d %H:%M:%S')],
        ]

        sig_table = Table(sig_data, colWidths=[8*cm, 9*cm])
        sig_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f3f5')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(sig_table)
        story.append(Spacer(1, 0.5*cm))

        # Digital Signature
        if certificate.digital_signature:
            story.append(Paragraph("数字签名 / Digital Signature:", self.body_style))
            sig_style = ParagraphStyle(
                'Signature',
                parent=self.styles['Code'],
                fontSize=7,
                textColor=colors.grey
            )
            story.append(Paragraph(f"<font face='Courier'>{certificate.digital_signature}</font>", sig_style))

        # Build PDF
        doc.build(story)

        return output_path
