/**
 * Calibration Dashboard Component
 *
 * Overview dashboard with charts and statistics
 * 
 * 包含两类校准状态展示：
 * 1. 系统验证测试 (TRP/TIS Validation) - 使用标准DUT验证测量准确性
 * 2. 路径校准 (Path Calibration) - DL/UL链路路损/增益校准
 */
import {
  Grid,
  Paper,
  Text,
  Stack,
  Group,
  RingProgress,
  ThemeIcon,
  Badge,
  Table,
  Divider,
} from '@mantine/core';
import {
  IconTrendingDown,
  IconCircleCheck,
  IconAlertTriangle,
} from '@tabler/icons-react';
import { PathLossCalibrationCard } from './PathLossCalibrationCard';
import { CalibrationTimeline } from './CalibrationTimeline';
import { CalibrationDependencyGraph } from './CalibrationDependencyGraph';
import { BaselineCalibrationCard } from './BaselineCalibrationCard';

export function CalibrationDashboard() {
  // Mock data for dashboard
  const stats = {
    trpAccuracy: 0.12,
    tisAccuracy: 0.35,
    repeatability: 0.18,
    certificateValid: true,
    validUntil: '2026-11-16',
    totalCalibrations: 15,
    passRate: 93.3,
  };

  const recentTrends = [
    { date: '2025-11', trpError: 0.12, tisError: 0.35, repeatability: 0.18 },
    { date: '2025-10', trpError: 0.15, tisError: 0.42, repeatability: 0.22 },
    { date: '2025-09', trpError: 0.18, tisError: 0.38, repeatability: 0.25 },
    { date: '2025-08', trpError: 0.22, tisError: 0.45, repeatability: 0.28 },
  ];

  return (
    <Grid>
      {/* Overall Performance */}
      <Grid.Col span={4}>
        <Paper p="md" withBorder>
          <Group justify="apart" mb="md">
            <Text size="sm" fw={600}>系统合格率</Text>
            <ThemeIcon color="green" variant="light" size="lg">
              <IconCircleCheck size={20} />
            </ThemeIcon>
          </Group>
          <Group justify="center">
            <RingProgress
              size={140}
              thickness={12}
              sections={[
                { value: stats.passRate, color: 'green' },
              ]}
              label={
                <Text size="xl" fw={700} ta="center">
                  {stats.passRate}%
                </Text>
              }
            />
          </Group>
          <Text size="xs" color="dimmed" ta="center" mt="md">
            {stats.totalCalibrations} 次校准中 {Math.round(stats.totalCalibrations * stats.passRate / 100)} 次通过
          </Text>
        </Paper>
      </Grid.Col>

      {/* TRP Accuracy */}
      <Grid.Col span={4}>
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="md">TRP 精度趋势</Text>
          <Stack gap="xs">
            <Group justify="apart">
              <Text size="xl" fw={700}>±{stats.trpAccuracy} dB</Text>
              <Badge color="green" leftSection={<IconTrendingDown size={12} />}>
                改善
              </Badge>
            </Group>
            <Text size="xs" color="dimmed">
              标准要求: ±0.5 dB
            </Text>
            <Group gap={4} mt="sm">
              {recentTrends.map((trend, idx) => (
                <div
                  key={idx}
                  style={{
                    flex: 1,
                    height: 40,
                    backgroundColor: trend.trpError < 0.5 ? '#51cf66' : '#ffa94d',
                    opacity: 1 - idx * 0.15,
                    borderRadius: 4,
                  }}
                />
              ))}
            </Group>
            <Text size="xs" color="dimmed">
              过去 4 个月
            </Text>
          </Stack>
        </Paper>
      </Grid.Col>

      {/* TIS Accuracy */}
      <Grid.Col span={4}>
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="md">TIS 精度趋势</Text>
          <Stack gap="xs">
            <Group justify="apart">
              <Text size="xl" fw={700}>±{stats.tisAccuracy} dB</Text>
              <Badge color="green" leftSection={<IconTrendingDown size={12} />}>
                改善
              </Badge>
            </Group>
            <Text size="xs" color="dimmed">
              标准要求: ±1.0 dB
            </Text>
            <Group gap={4} mt="sm">
              {recentTrends.map((trend, idx) => (
                <div
                  key={idx}
                  style={{
                    flex: 1,
                    height: 40,
                    backgroundColor: trend.tisError < 1.0 ? '#51cf66' : '#ffa94d',
                    opacity: 1 - idx * 0.15,
                    borderRadius: 4,
                  }}
                />
              ))}
            </Group>
            <Text size="xs" color="dimmed">
              过去 4 个月
            </Text>
          </Stack>
        </Paper>
      </Grid.Col>

      {/* Repeatability Trend */}
      <Grid.Col span={12}>
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="md">可重复性趋势</Text>
          <Table>
            <thead>
              <tr>
                <th>月份</th>
                <th>TRP 误差 (dB)</th>
                <th>TIS 误差 (dB)</th>
                <th>可重复性 σ (dB)</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {recentTrends.map((trend, idx) => (
                <tr key={idx}>
                  <td>{trend.date}</td>
                  <td>
                    <Badge
                      color={trend.trpError < 0.5 ? 'green' : 'yellow'}
                      variant="light"
                    >
                      ±{trend.trpError.toFixed(2)}
                    </Badge>
                  </td>
                  <td>
                    <Badge
                      color={trend.tisError < 1.0 ? 'green' : 'yellow'}
                      variant="light"
                    >
                      ±{trend.tisError.toFixed(2)}
                    </Badge>
                  </td>
                  <td>
                    <Badge
                      color={trend.repeatability < 0.3 ? 'green' : 'yellow'}
                      variant="light"
                    >
                      {trend.repeatability.toFixed(2)}
                    </Badge>
                  </td>
                  <td>
                    <Badge
                      color={
                        trend.trpError < 0.5 && trend.tisError < 1.0 && trend.repeatability < 0.3
                          ? 'green'
                          : 'yellow'
                      }
                    >
                      {trend.trpError < 0.5 && trend.tisError < 1.0 && trend.repeatability < 0.3
                        ? '合格'
                        : '需关注'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Paper>
      </Grid.Col>

      {/* 分隔线 - 路径校准区域 */}
      <Grid.Col span={12}>
        <Divider
          my="sm"
          label="路径校准 (Path Calibration)"
          labelPosition="center"
          styles={{ label: { fontWeight: 600, color: 'var(--mantine-color-violet-6)' } }}
        />
      </Grid.Col>

      {/* 路径校准状态卡片 */}
      <Grid.Col span={12}>
        <PathLossCalibrationCard />
      </Grid.Col>

      {/* CAL-08: 校准时间线和依赖图 */}
      <Grid.Col span={6}>
        <CalibrationTimeline />
      </Grid.Col>
      <Grid.Col span={6}>
        <CalibrationDependencyGraph />
      </Grid.Col>

      {/* 相对校准 (Quick Mode) */}
      <Grid.Col span={12}>
        <BaselineCalibrationCard />
      </Grid.Col>

      {/* Alerts and Recommendations */}
      <Grid.Col span={12}>
        <Paper p="md" withBorder>
          <Group mb="md">
            <ThemeIcon color="blue" variant="light">
              <IconAlertTriangle size={16} />
            </ThemeIcon>
            <Text size="sm" fw={600}>建议和提醒</Text>
          </Group>
          <Stack gap="xs">
            <Group>
              <Badge color="green">✓</Badge>
              <Text size="sm">所有校准参数均在标准范围内</Text>
            </Group>
            <Group>
              <Badge color="blue">ℹ</Badge>
              <Text size="sm">下次校准建议时间: {stats.validUntil}</Text>
            </Group>
            <Group>
              <Badge color="yellow">!</Badge>
              <Text size="sm">建议每月执行一次可重复性测试以监控系统稳定性</Text>
            </Group>
          </Stack>
        </Paper>
      </Grid.Col>
    </Grid>
  );
}

