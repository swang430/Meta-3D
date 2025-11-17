/**
 * Certificate Viewer Component
 *
 * View and manage calibration certificates
 */
import { useState } from 'react';
import {
  Card,
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
    // TODO: Implement PDF download
    console.log('Download PDF certificate');
  };

  return (
    <Stack spacing="xl">
      {/* Latest Certificate Card */}
      <Paper p="xl" withBorder>
        <Grid>
          <Grid.Col span={8}>
            <Stack spacing="md">
              <Group>
                <ThemeIcon size={48} radius="md" color="green" variant="light">
                  <IconCertificate size={28} />
                </ThemeIcon>
                <div>
                  <Text size="lg" weight={700}>
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
                    <Group position="apart">
                      <Text size="xs" color="dimmed">校准日期</Text>
                      <Badge leftIcon={<IconCalendar size={12} />} variant="light">
                        {mockCertificate.calibrationDate}
                      </Badge>
                    </Group>
                  </Paper>
                </Grid.Col>
                <Grid.Col span={6}>
                  <Paper p="sm" withBorder>
                    <Group position="apart">
                      <Text size="xs" color="dimmed">有效期至</Text>
                      <Badge color="green" leftIcon={<IconCalendar size={12} />} variant="light">
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
                leftIcon={<IconDownload size={16} />}
                onClick={downloadPDF}
                fullWidth
              >
                下载 PDF 证书
              </Button>
              <Button
                leftIcon={<IconFileText size={16} />}
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
        <Stack spacing="md">
          <Paper p="md" withBorder>
            <Text size="sm" weight={600} mb="xs">系统信息</Text>
            <List size="sm" spacing="xs">
              <List.Item>系统名称: {mockCertificate.systemName}</List.Item>
              <List.Item>序列号: MPAC-001</List.Item>
              <List.Item>探头数量: 32</List.Item>
              <List.Item>暗室半径: 10.0 m</List.Item>
              <List.Item>频率范围: 600-6000 MHz</List.Item>
            </List>
          </Paper>

          <Paper p="md" withBorder>
            <Text size="sm" weight={600} mb="xs">实验室信息</Text>
            <List size="sm" spacing="xs">
              <List.Item>实验室: Meta-3D Test Laboratory</List.Item>
              <List.Item>地址: 123 Test Street, City, Country</List.Item>
              <List.Item>认证: ISO/IEC 17025:2017</List.Item>
              <List.Item>认证机构: CNAS</List.Item>
            </List>
          </Paper>

          <Paper p="md" withBorder>
            <Text size="sm" weight={600} mb="xs">适用标准</Text>
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
