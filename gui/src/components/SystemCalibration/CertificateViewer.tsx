/**
 * Certificate Viewer Component
 *
 * View and manage calibration certificates
 */
import { useState } from 'react';
import {
  Text,
  Badge,
  Button,
  Group,
  Stack,
  Grid,
  Paper,
  Divider,
  ThemeIcon,
  Timeline,
  Modal,
  List,
} from '@mantine/core';
import {
  IconCertificate,
  IconDownload,
  IconCheck,
  IconAlertCircle,
  IconCalendar,
  IconFileText,
} from '@tabler/icons-react';
import { jsPDF } from 'jspdf';
import { notifications } from '@mantine/notifications';

interface Certificate {
  id: string;
  certificateNumber: string;
  systemName: string;
  calibrationDate: string;
  validUntil: string;
  overallPass: boolean;
  trpError: number;
  trpPass: boolean;
  tisError: number;
  tisPass: boolean;
  repeatabilityStdDev: number;
  repeatabilityPass: boolean;
  calibratedBy: string;
  reviewedBy: string;
}

const mockCertificate: Certificate = {
  id: '1',
  certificateNumber: 'MPAC-SYS-CAL-2025-11-16-1200',
  systemName: 'Meta-3D MPAC OTA Test System',
  calibrationDate: '2025-11-16',
  validUntil: '2026-11-16',
  overallPass: true,
  trpError: 0.02,
  trpPass: true,
  tisError: 0.15,
  tisPass: true,
  repeatabilityStdDev: 0.18,
  repeatabilityPass: true,
  calibratedBy: 'Engineer A',
  reviewedBy: 'Technical Manager B',
};

export function CertificateViewer() {
  const [detailsOpened, setDetailsOpened] = useState(false);

  const downloadPDF = () => {
    try {
      const doc = new jsPDF();
      const pageWidth = doc.internal.pageSize.getWidth();
      const pageHeight = doc.internal.pageSize.getHeight();
      const margin = 20;
      let yPos = margin;

      // Header
      doc.setFontSize(20);
      doc.setFont('helvetica', 'bold');
      doc.text('System Calibration Certificate', pageWidth / 2, yPos, { align: 'center' });
      yPos += 15;

      // Certificate Number
      doc.setFontSize(12);
      doc.setFont('helvetica', 'normal');
      doc.text(`Certificate No: ${mockCertificate.certificateNumber}`, pageWidth / 2, yPos, { align: 'center' });
      yPos += 10;

      // Line separator
      doc.setLineWidth(0.5);
      doc.line(margin, yPos, pageWidth - margin, yPos);
      yPos += 15;

      // System Information
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('System Information', margin, yPos);
      yPos += 8;

      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.text(`System Name: ${mockCertificate.systemName}`, margin + 5, yPos);
      yPos += 7;
      doc.text(`Calibration Date: ${mockCertificate.calibrationDate}`, margin + 5, yPos);
      yPos += 7;
      doc.text(`Valid Until: ${mockCertificate.validUntil}`, margin + 5, yPos);
      yPos += 12;

      // Overall Status
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('Overall Status', margin, yPos);
      yPos += 8;

      if (mockCertificate.overallPass) {
        doc.setTextColor(0, 150, 0); // Green
        doc.text('PASS', margin + 5, yPos);
      } else {
        doc.setTextColor(200, 0, 0); // Red
        doc.text('FAIL', margin + 5, yPos);
      }
      doc.setTextColor(0, 0, 0); // Reset to black
      yPos += 12;

      // TRP Calibration Results
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('TRP Calibration Results', margin, yPos);
      yPos += 8;

      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.text(`Absolute Error: ${mockCertificate.trpError.toFixed(2)} dB`, margin + 5, yPos);
      yPos += 7;
      doc.text(`Status: ${mockCertificate.trpPass ? 'PASS' : 'FAIL'}`, margin + 5, yPos);
      yPos += 12;

      // TIS Calibration Results
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('TIS Calibration Results', margin, yPos);
      yPos += 8;

      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.text(`Absolute Error: ${mockCertificate.tisError.toFixed(2)} dB`, margin + 5, yPos);
      yPos += 7;
      doc.text(`Status: ${mockCertificate.tisPass ? 'PASS' : 'FAIL'}`, margin + 5, yPos);
      yPos += 12;

      // Repeatability Test Results
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('Repeatability Test Results', margin, yPos);
      yPos += 8;

      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.text(`Standard Deviation: ${mockCertificate.repeatabilityStdDev.toFixed(2)} dB`, margin + 5, yPos);
      yPos += 7;
      doc.text(`Status: ${mockCertificate.repeatabilityPass ? 'PASS' : 'FAIL'}`, margin + 5, yPos);
      yPos += 12;

      // Check if we need a new page
      if (yPos > pageHeight - 50) {
        doc.addPage();
        yPos = margin;
      }

      // Signatures
      doc.setLineWidth(0.5);
      doc.line(margin, yPos, pageWidth - margin, yPos);
      yPos += 10;

      doc.setFontSize(12);
      doc.setFont('helvetica', 'bold');
      doc.text('Signatures', margin, yPos);
      yPos += 10;

      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.text(`Calibrated by: ${mockCertificate.calibratedBy}`, margin + 5, yPos);
      yPos += 10;
      doc.text(`Reviewed by: ${mockCertificate.reviewedBy}`, margin + 5, yPos);
      yPos += 15;

      // Footer
      doc.setFontSize(9);
      doc.setTextColor(128, 128, 128);
      doc.text(
        `Generated on ${new Date().toLocaleString()}`,
        pageWidth / 2,
        pageHeight - 10,
        { align: 'center' }
      );

      // Save the PDF
      const filename = `${mockCertificate.certificateNumber}.pdf`;
      doc.save(filename);

      notifications.show({
        title: '下载成功',
        message: `证书已保存为 ${filename}`,
        color: 'green',
      });
    } catch (error) {
      console.error('PDF generation error:', error);
      notifications.show({
        title: '下载失败',
        message: '无法生成 PDF 证书',
        color: 'red',
      });
    }
  };

  return (
    <Stack gap="xl">
      {/* Latest Certificate Card */}
      <Paper p="xl" withBorder>
        <Grid>
          <Grid.Col span={8}>
            <Stack gap="md">
              <Group>
                <ThemeIcon size={48} radius="md" color="green" variant="light">
                  <IconCertificate size={28} />
                </ThemeIcon>
                <div>
                  <Text size="lg" fw={700}>
                    {mockCertificate.systemName}
                  </Text>
                  <Text size="sm" color="dimmed">
                    证书编号: {mockCertificate.certificateNumber}
                  </Text>
                </div>
              </Group>

              <Divider />

              <Grid gutter="md">
                <Grid.Col span={6}>
                  <Paper p="sm" withBorder>
                    <Group justify="apart">
                      <Text size="xs" color="dimmed">校准日期</Text>
                      <Badge leftSection={<IconCalendar size={12} />} variant="light">
                        {mockCertificate.calibrationDate}
                      </Badge>
                    </Group>
                  </Paper>
                </Grid.Col>
                <Grid.Col span={6}>
                  <Paper p="sm" withBorder>
                    <Group justify="apart">
                      <Text size="xs" color="dimmed">有效期至</Text>
                      <Badge color="green" leftSection={<IconCalendar size={12} />} variant="light">
                        {mockCertificate.validUntil}
                      </Badge>
                    </Group>
                  </Paper>
                </Grid.Col>
              </Grid>

              <Timeline active={3} bulletSize={24} lineWidth={2}>
                <Timeline.Item
                  bullet={<IconCheck size={12} />}
                  title="TRP 校准"
                  color={mockCertificate.trpPass ? 'green' : 'red'}
                >
                  <Text size="xs" color="dimmed">
                    误差: ±{mockCertificate.trpError.toFixed(2)} dB (标准: ±0.5 dB)
                  </Text>
                  <Badge size="sm" color={mockCertificate.trpPass ? 'green' : 'red'} mt={4}>
                    {mockCertificate.trpPass ? '通过' : '未通过'}
                  </Badge>
                </Timeline.Item>

                <Timeline.Item
                  bullet={<IconCheck size={12} />}
                  title="TIS 校准"
                  color={mockCertificate.tisPass ? 'green' : 'red'}
                >
                  <Text size="xs" color="dimmed">
                    误差: ±{mockCertificate.tisError.toFixed(2)} dB (标准: ±1.0 dB)
                  </Text>
                  <Badge size="sm" color={mockCertificate.tisPass ? 'green' : 'red'} mt={4}>
                    {mockCertificate.tisPass ? '通过' : '未通过'}
                  </Badge>
                </Timeline.Item>

                <Timeline.Item
                  bullet={<IconCheck size={12} />}
                  title="可重复性测试"
                  color={mockCertificate.repeatabilityPass ? 'green' : 'red'}
                >
                  <Text size="xs" color="dimmed">
                    标准差: {mockCertificate.repeatabilityStdDev.toFixed(2)} dB (标准: &lt; 0.3 dB)
                  </Text>
                  <Badge size="sm" color={mockCertificate.repeatabilityPass ? 'green' : 'red'} mt={4}>
                    {mockCertificate.repeatabilityPass ? '通过' : '未通过'}
                  </Badge>
                </Timeline.Item>

                <Timeline.Item
                  bullet={mockCertificate.overallPass ? <IconCheck size={12} /> : <IconAlertCircle size={12} />}
                  title="总体结果"
                  color={mockCertificate.overallPass ? 'green' : 'red'}
                >
                  <Badge size="sm" color={mockCertificate.overallPass ? 'green' : 'red'}>
                    {mockCertificate.overallPass ? '合格' : '不合格'}
                  </Badge>
                </Timeline.Item>
              </Timeline>

              <Divider />

              <Grid gutter="xs">
                <Grid.Col span={6}>
                  <Text size="xs" color="dimmed">校准工程师:</Text>
                  <Text size="sm">{mockCertificate.calibratedBy}</Text>
                </Grid.Col>
                <Grid.Col span={6}>
                  <Text size="xs" color="dimmed">技术审核:</Text>
                  <Text size="sm">{mockCertificate.reviewedBy}</Text>
                </Grid.Col>
              </Grid>
            </Stack>
          </Grid.Col>

          <Grid.Col span={4}>
            <Stack>
              <Button
                leftSection={<IconDownload size={16} />}
                onClick={downloadPDF}
                fullWidth
              >
                下载 PDF 证书
              </Button>
              <Button
                leftSection={<IconFileText size={16} />}
                variant="light"
                onClick={() => setDetailsOpened(true)}
                fullWidth
              >
                查看详细信息
              </Button>
            </Stack>
          </Grid.Col>
        </Grid>
      </Paper>

      {/* Certificate Details Modal */}
      <Modal
        opened={detailsOpened}
        onClose={() => setDetailsOpened(false)}
        title="证书详细信息"
        size="lg"
      >
        <Stack gap="md">
          <Paper p="md" withBorder>
            <Text size="sm" fw={600} mb="xs">系统信息</Text>
            <List size="sm" spacing="xs">
              <List.Item>系统名称: {mockCertificate.systemName}</List.Item>
              <List.Item>序列号: MPAC-001</List.Item>
              <List.Item>探头数量: 32</List.Item>
              <List.Item>暗室半径: 10.0 m</List.Item>
              <List.Item>频率范围: 600-6000 MHz</List.Item>
            </List>
          </Paper>

          <Paper p="md" withBorder>
            <Text size="sm" fw={600} mb="xs">实验室信息</Text>
            <List size="sm" spacing="xs">
              <List.Item>实验室: Meta-3D Test Laboratory</List.Item>
              <List.Item>地址: 123 Test Street, City, Country</List.Item>
              <List.Item>认证: ISO/IEC 17025:2017</List.Item>
              <List.Item>认证机构: CNAS</List.Item>
            </List>
          </Paper>

          <Paper p="md" withBorder>
            <Text size="sm" fw={600} mb="xs">适用标准</Text>
            <List size="sm" spacing="xs">
              <List.Item>3GPP TS 34.114</List.Item>
              <List.Item>CTIA OTA Test Plan Ver. 4.0</List.Item>
            </List>
          </Paper>
        </Stack>
      </Modal>
    </Stack>
  );
}
