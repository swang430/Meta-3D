/**
 * Path Loss Calibration Card Component
 *
 * 显示 DL/UL 路径校准状态，包括：
 * - 探头路损校准状态
 * - 上行链路 (LNA) 校准状态
 * - 下行链路 (PA) 校准状态
 * - 多频点校准覆盖
 */
import { useState } from 'react';
import {
  Paper,
  Text,
  Stack,
  Group,
  Badge,
  Progress,
  ThemeIcon,
  Tooltip,
  SimpleGrid,
  Divider,
  Button,
} from '@mantine/core';
import {
  IconAntenna,
  IconArrowUp,
  IconArrowDown,
  IconCircleCheck,
  IconAlertTriangle,
  IconClock,
  IconRefresh,
} from '@tabler/icons-react';

interface PathLossStatus {
  calibrated: boolean;
  lastCalibration?: string;
  validUntil?: string;
  probesCovered: number;
  totalProbes: number;
  frequencyRange?: { min: number; max: number };
}

interface RFChainStatus {
  calibrated: boolean;
  lastCalibration?: string;
  gainDb?: number;
  uncertaintyDb?: number;
}

interface PathLossCalibrationData {
  pathLoss: PathLossStatus;
  uplinkChain: RFChainStatus;
  downlinkChain: RFChainStatus;
  multiFrequency: {
    calibrated: boolean;
    frequencies: number[];
    lastCalibration?: string;
  };
}

export function PathLossCalibrationCard() {
  // Mock data - 实际应从 API 获取
  const [data, _setData] = useState<PathLossCalibrationData>({
    pathLoss: {
      calibrated: true,
      lastCalibration: '2026-01-20 15:30',
      validUntil: '2026-04-20',
      probesCovered: 32,
      totalProbes: 32,
      frequencyRange: { min: 3300, max: 3800 },
    },
    uplinkChain: {
      calibrated: true,
      lastCalibration: '2026-01-20 16:00',
      gainDb: 25.3,
      uncertaintyDb: 0.3,
    },
    downlinkChain: {
      calibrated: true,
      lastCalibration: '2026-01-20 16:30',
      gainDb: 30.1,
      uncertaintyDb: 0.4,
    },
    multiFrequency: {
      calibrated: true,
      frequencies: [3300, 3400, 3500, 3600, 3700, 3800],
      lastCalibration: '2026-01-20 17:00',
    },
  });

  const [loading, setLoading] = useState(false);

  // TODO: 从 API 获取真实数据
  // useEffect(() => {
  //   fetchPathLossStatus();
  // }, []);

  const getStatusColor = (calibrated: boolean) => calibrated ? 'green' : 'red';
  const getStatusIcon = (calibrated: boolean) =>
    calibrated ? <IconCircleCheck size={14} /> : <IconAlertTriangle size={14} />;

  const handleRefresh = async () => {
    setLoading(true);
    // TODO: 调用 API 刷新数据
    await new Promise(resolve => setTimeout(resolve, 1000));
    setLoading(false);
  };

  return (
    <Paper p="md" withBorder>
      <Group justify="space-between" mb="md">
        <Group>
          <ThemeIcon color="violet" variant="light" size="lg">
            <IconAntenna size={20} />
          </ThemeIcon>
          <Text size="sm" fw={600}>路径校准状态 (DL/UL Path Calibration)</Text>
        </Group>
        <Button
          variant="subtle"
          size="xs"
          leftSection={<IconRefresh size={14} />}
          loading={loading}
          onClick={handleRefresh}
        >
          刷新
        </Button>
      </Group>

      <SimpleGrid cols={2} spacing="md">
        {/* 探头路损校准 */}
        <Paper p="sm" withBorder radius="md" bg="gray.0">
          <Group justify="space-between" mb="xs">
            <Text size="xs" fw={500} c="dimmed">探头路损校准</Text>
            <Badge
              size="xs"
              color={getStatusColor(data.pathLoss.calibrated)}
              leftSection={getStatusIcon(data.pathLoss.calibrated)}
            >
              {data.pathLoss.calibrated ? '有效' : '需校准'}
            </Badge>
          </Group>
          <Group justify="space-between" mb="xs">
            <Text size="sm">探头覆盖</Text>
            <Text size="sm" fw={500}>
              {data.pathLoss.probesCovered}/{data.pathLoss.totalProbes}
            </Text>
          </Group>
          <Progress
            value={(data.pathLoss.probesCovered / data.pathLoss.totalProbes) * 100}
            color="violet"
            size="sm"
            mb="xs"
          />
          {data.pathLoss.frequencyRange && (
            <Text size="xs" c="dimmed">
              频段: {data.pathLoss.frequencyRange.min}-{data.pathLoss.frequencyRange.max} MHz
            </Text>
          )}
        </Paper>

        {/* 多频点校准 */}
        <Paper p="sm" withBorder radius="md" bg="gray.0">
          <Group justify="space-between" mb="xs">
            <Text size="xs" fw={500} c="dimmed">多频点校准</Text>
            <Badge
              size="xs"
              color={getStatusColor(data.multiFrequency.calibrated)}
              leftSection={getStatusIcon(data.multiFrequency.calibrated)}
            >
              {data.multiFrequency.calibrated ? '有效' : '需校准'}
            </Badge>
          </Group>
          <Group gap={4} wrap="wrap">
            {data.multiFrequency.frequencies.map((freq) => (
              <Tooltip key={freq} label={`${freq} MHz 已校准`}>
                <Badge size="xs" variant="light" color="violet">
                  {freq}
                </Badge>
              </Tooltip>
            ))}
          </Group>
          <Text size="xs" c="dimmed" mt="xs">
            {data.multiFrequency.frequencies.length} 个频点
          </Text>
        </Paper>
      </SimpleGrid>

      <Divider my="md" label="RF 链路增益" labelPosition="center" />

      <SimpleGrid cols={2} spacing="md">
        {/* 上行链路 (UL) */}
        <Paper p="sm" withBorder radius="md" bg="blue.0">
          <Group justify="space-between" mb="xs">
            <Group gap="xs">
              <IconArrowUp size={14} color="var(--mantine-color-blue-6)" />
              <Text size="xs" fw={500} c="dimmed">上行链路 (UL/LNA)</Text>
            </Group>
            <Badge
              size="xs"
              color={getStatusColor(data.uplinkChain.calibrated)}
              leftSection={getStatusIcon(data.uplinkChain.calibrated)}
            >
              {data.uplinkChain.calibrated ? '有效' : '需校准'}
            </Badge>
          </Group>
          {data.uplinkChain.gainDb !== undefined && (
            <Stack gap={2}>
              <Group justify="space-between">
                <Text size="sm">增益</Text>
                <Text size="sm" fw={600} c="blue">
                  +{data.uplinkChain.gainDb.toFixed(1)} dB
                </Text>
              </Group>
              <Group justify="space-between">
                <Text size="xs" c="dimmed">不确定度</Text>
                <Text size="xs" c="dimmed">
                  ±{data.uplinkChain.uncertaintyDb?.toFixed(2)} dB
                </Text>
              </Group>
            </Stack>
          )}
        </Paper>

        {/* 下行链路 (DL) */}
        <Paper p="sm" withBorder radius="md" bg="teal.0">
          <Group justify="space-between" mb="xs">
            <Group gap="xs">
              <IconArrowDown size={14} color="var(--mantine-color-teal-6)" />
              <Text size="xs" fw={500} c="dimmed">下行链路 (DL/PA)</Text>
            </Group>
            <Badge
              size="xs"
              color={getStatusColor(data.downlinkChain.calibrated)}
              leftSection={getStatusIcon(data.downlinkChain.calibrated)}
            >
              {data.downlinkChain.calibrated ? '有效' : '需校准'}
            </Badge>
          </Group>
          {data.downlinkChain.gainDb !== undefined && (
            <Stack gap={2}>
              <Group justify="space-between">
                <Text size="sm">增益</Text>
                <Text size="sm" fw={600} c="teal">
                  +{data.downlinkChain.gainDb.toFixed(1)} dB
                </Text>
              </Group>
              <Group justify="space-between">
                <Text size="xs" c="dimmed">不确定度</Text>
                <Text size="xs" c="dimmed">
                  ±{data.downlinkChain.uncertaintyDb?.toFixed(2)} dB
                </Text>
              </Group>
            </Stack>
          )}
        </Paper>
      </SimpleGrid>

      {/* 最后校准时间 */}
      <Group justify="center" mt="md" gap="xs">
        <IconClock size={12} color="gray" />
        <Text size="xs" c="dimmed">
          最后校准: {data.pathLoss.lastCalibration}
        </Text>
        <Text size="xs" c="dimmed">•</Text>
        <Text size="xs" c="dimmed">
          有效期至: {data.pathLoss.validUntil}
        </Text>
      </Group>
    </Paper>
  );
}
