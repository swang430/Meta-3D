/**
 * System Calibration Component
 *
 * Main dashboard for system-level calibration management
 */
import { useState } from 'react';
import {
  Container,
  Title,
  Tabs,
  Grid,
  Text,
  Button,
  Group,
  Stack,
  Paper,
  ThemeIcon,
} from '@mantine/core';
import {
  IconCertificate,
  IconChartLine,
  IconFileCheck,
  IconPlus,
} from '@tabler/icons-react';
import { CalibrationWizard } from './CalibrationWizard';
import { CalibrationHistory } from './CalibrationHistory';
import { CertificateViewer } from './CertificateViewer';
import { CalibrationDashboard } from './CalibrationDashboard';
import { PathLossCalibrationCard } from './PathLossCalibrationCard';

// Re-export components for external use
export { PathLossCalibrationCard };

export function SystemCalibration() {
  const [activeTab, setActiveTab] = useState<string | null>('dashboard');
  const [wizardOpen, setWizardOpen] = useState(false);

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        {/* Header */}
        <Group justify="apart">
          <div>
            <Title order={2}>系统校准</Title>
            <Text size="sm" color="dimmed" mt={4}>
              System-Level Calibration
            </Text>
          </div>
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={() => setWizardOpen(true)}
          >
            新建校准
          </Button>
        </Group>

        {/* Status Cards */}
        <Grid data-testid="system-calibration-summary">
          <Grid.Col span={3}>
            <Paper p="md" withBorder>
              <Group justify="apart">
                <div>
                  <Text size="xs" color="dimmed" tt="uppercase" fw={700}>
                    最新证书状态
                  </Text>
                  <Text size="xl" fw={700} mt={4}>
                    未知
                  </Text>
                </div>
                <ThemeIcon size={44} radius="md" variant="light" color="gray">
                  <IconCertificate size={24} />
                </ThemeIcon>
              </Group>
              <Text size="xs" color="dimmed" mt="md">
                当前首页未接入可验证的证书来源
              </Text>
            </Paper>
          </Grid.Col>

          <Grid.Col span={3}>
            <Paper p="md" withBorder>
              <Group justify="apart">
                <div>
                  <Text size="xs" color="dimmed" tt="uppercase" fw={700}>
                    TRP 精度
                  </Text>
                  <Text size="xl" fw={700} mt={4}>
                    未知
                  </Text>
                </div>
                <ThemeIcon size={44} radius="md" variant="light" color="gray">
                  <IconChartLine size={24} />
                </ThemeIcon>
              </Group>
              <Text size="xs" color="dimmed" mt="md">
                当前首页未接入可验证的 TRP 验证结果
              </Text>
            </Paper>
          </Grid.Col>

          <Grid.Col span={3}>
            <Paper p="md" withBorder>
              <Group justify="apart">
                <div>
                  <Text size="xs" color="dimmed" tt="uppercase" fw={700}>
                    TIS 精度
                  </Text>
                  <Text size="xl" fw={700} mt={4}>
                    未知
                  </Text>
                </div>
                <ThemeIcon size={44} radius="md" variant="light" color="gray">
                  <IconChartLine size={24} />
                </ThemeIcon>
              </Group>
              <Text size="xs" color="dimmed" mt="md">
                当前首页未接入可验证的 TIS 验证结果
              </Text>
            </Paper>
          </Grid.Col>

          <Grid.Col span={3}>
            <Paper p="md" withBorder>
              <Group justify="apart">
                <div>
                  <Text size="xs" color="dimmed" tt="uppercase" fw={700}>
                    可重复性
                  </Text>
                  <Text size="xl" fw={700} mt={4}>
                    未知
                  </Text>
                </div>
                <ThemeIcon size={44} radius="md" variant="light" color="gray">
                  <IconChartLine size={24} />
                </ThemeIcon>
              </Group>
              <Text size="xs" color="dimmed" mt="md">
                当前首页未接入可验证的重复性结果
              </Text>
            </Paper>
          </Grid.Col>
        </Grid>

        {/* Main Content Tabs */}
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="dashboard" leftSection={<IconChartLine size={16} />}>
              概览
            </Tabs.Tab>
            <Tabs.Tab value="history" leftSection={<IconFileCheck size={16} />}>
              校准记录
            </Tabs.Tab>
            <Tabs.Tab value="certificates" leftSection={<IconCertificate size={16} />}>
              证书管理
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="dashboard" pt="xl">
            <CalibrationDashboard />
          </Tabs.Panel>

          <Tabs.Panel value="history" pt="xl">
            <CalibrationHistory />
          </Tabs.Panel>

          <Tabs.Panel value="certificates" pt="xl">
            <CertificateViewer />
          </Tabs.Panel>
        </Tabs>
      </Stack>

      {/* Calibration Wizard Modal */}
      <CalibrationWizard
        opened={wizardOpen}
        onClose={() => setWizardOpen(false)}
      />
    </Container>
  );
}
