/**
 * Test Execution Modal
 *
 * Display test execution progress and status
 */

import { useEffect, useState } from 'react'
import {
  Modal,
  Button,
  Stack,
  Progress,
  Group,
  Text,
  Badge,
  Alert,
  Timeline,
  Card,
  SimpleGrid,
} from '@mantine/core'
import {
  IconCheck,
  IconClock,
  IconPlayerPlay,
} from '@tabler/icons-react'
import type { ScenarioSummary } from '../../types/roadTest'

interface Props {
  opened: boolean
  onClose: () => void
  scenario: ScenarioSummary
  testMode?: string
}

const TEST_PHASES = [
  { name: '初始化', duration: 5 },
  { name: '配置网络', duration: 10 },
  { name: '启动基站', duration: 8 },
  { name: '连接DUT', duration: 7 },
  { name: '运行测试', duration: 30 },
  { name: '收集数据', duration: 10 },
  { name: '生成报告', duration: 5 },
]

export function TestExecutionModal({ opened, onClose, scenario, testMode }: Props) {
  const [progress, setProgress] = useState(0)
  const [currentPhase, setCurrentPhase] = useState(0)
  const [isRunning, setIsRunning] = useState(false)
  const [executionId, setExecutionId] = useState<string>('')

  // Simulate test execution
  useEffect(() => {
    if (!isRunning) return

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          setIsRunning(false)
          return 100
        }

        const increment = Math.random() * 5 + 2
        const newProgress = Math.min(prev + increment, 100)

        // Update phase based on progress
        const phaseIndex = Math.floor((newProgress / 100) * (TEST_PHASES.length - 1))
        setCurrentPhase(phaseIndex)

        return newProgress
      })
    }, 800)

    return () => clearInterval(interval)
  }, [isRunning])

  const handleStart = () => {
    setProgress(0)
    setCurrentPhase(0)
    setIsRunning(true)
    setExecutionId(`exec-${Date.now()}`)
  }

  const handleStop = () => {
    setIsRunning(false)
  }

  const totalDuration = TEST_PHASES.reduce((sum, phase) => sum + phase.duration, 0)
  const estimatedTime = Math.round((totalDuration * (100 - progress)) / 100)

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`执行测试: ${scenario.name}`}
      size="lg"
      centered
    >
      <Stack gap="md">
        {/* Execution Info */}
        <Card withBorder p="md">
          <SimpleGrid cols={2} spacing="md">
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                场景
              </Text>
              <Text size="sm">{scenario.name}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                测试模式
              </Text>
              <Text size="sm">{testMode || '未指定'}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                执行 ID
              </Text>
              <Text size="sm" ff="monospace">
                {executionId || '-'}
              </Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                预计时间
              </Text>
              <Text size="sm">
                {estimatedTime}s / {totalDuration}s
              </Text>
            </div>
          </SimpleGrid>
        </Card>

        {/* Progress */}
        <div>
          <Group justify="space-between" mb="xs">
            <Text fw={500}>执行进度</Text>
            <Badge color={progress === 100 ? 'green' : 'blue'}>
              {Math.round(progress)}%
            </Badge>
          </Group>
          <Progress value={progress} size="lg" />
        </div>

        {/* Current Phase */}
        <Card withBorder p="md" bg={progress === 100 ? 'green.0' : 'blue.0'}>
          <Group>
            <IconPlayerPlay size={20} color={progress === 100 ? 'green' : 'blue'} />
            <div>
              <Text size="sm" fw={500}>
                当前阶段: {TEST_PHASES[currentPhase]?.name || '完成'}
              </Text>
              <Text size="xs" c="dimmed">
                {progress === 100 ? '测试已完成' : `${Math.round(TEST_PHASES[currentPhase]?.duration * (progress / 100))}s`}
              </Text>
            </div>
          </Group>
        </Card>

        {/* Phase Timeline */}
        <div>
          <Text fw={500} size="sm" mb="md">
            执行阶段
          </Text>
          <Timeline active={currentPhase + 1} bulletSize={24} lineWidth={2}>
            {TEST_PHASES.map((phase, index) => (
              <Timeline.Item
                key={phase.name}
                bullet={
                  index <= currentPhase ? (
                    <IconCheck size={12} />
                  ) : (
                    <IconClock size={12} />
                  )
                }
                title={phase.name}
              >
                <Text c="dimmed" size="sm">
                  {phase.duration}s
                </Text>
              </Timeline.Item>
            ))}
          </Timeline>
        </div>

        {/* Results (when complete) */}
        {progress === 100 && (
          <Alert icon={<IconCheck size={16} />} title="测试完成" color="green">
            <Stack gap="xs">
              <Text size="sm">
                ✓ 所有测试阶段已完成
              </Text>
              <Text size="sm">
                ✓ 数据已收集并保存
              </Text>
              <Text size="sm">
                可以点击下方按钮查看报告
              </Text>
            </Stack>
          </Alert>
        )}

        {/* Actions */}
        <Group justify="flex-end">
          {!isRunning && progress < 100 && (
            <Button onClick={handleStart} leftSection={<IconPlayerPlay size={16} />}>
              开始执行
            </Button>
          )}
          {isRunning && (
            <Button onClick={handleStop} variant="light" color="red">
              停止执行
            </Button>
          )}
          {progress === 100 && (
            <Button variant="light" onClick={() => alert('报告功能 - 开发中')}>
              查看报告
            </Button>
          )}
          <Button variant="subtle" onClick={onClose}>
            {progress === 100 ? '关闭' : '取消'}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
