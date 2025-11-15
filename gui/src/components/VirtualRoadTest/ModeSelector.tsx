/**
 * ModeSelector - 测试模式选择器
 * 用户选择三种测试模式之一：数字孪生、传导测试、OTA辐射测试
 */

import { useState } from 'react'
import {
  Stack,
  Title,
  Grid,
  Card,
  Text,
  ThemeIcon,
  List,
  Badge,
  Button,
  Table,
} from '@mantine/core'
import { IconCpu, IconPlugConnected, IconRadar2, IconCheck } from '@tabler/icons-react'
import { TestMode } from '../../types/roadTest'

interface ModeSelectorProps {
  onModeSelected: (mode: TestMode) => void
}

export function ModeSelector({ onModeSelected }: ModeSelectorProps) {
  const [selectedMode, setSelectedMode] = useState<TestMode>()

  const handleSelectMode = (mode: TestMode) => {
    setSelectedMode(mode)
  }

  const handleNext = () => {
    if (selectedMode) {
      onModeSelected(selectedMode)
    }
  }

  return (
    <Stack gap="xl">
      <div>
        <Title order={2}>选择测试模式</Title>
        <Text size="sm" c="dimmed" mt="xs">
          虚拟路测支持三种测试模式，从低成本仿真到高精度OTA测试
        </Text>
      </div>

      <Grid>
        {/* 模式1: 数字孪生 */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card
            shadow="sm"
            padding="lg"
            withBorder
            onClick={() => handleSelectMode(TestMode.DIGITAL_TWIN)}
            style={{
              cursor: 'pointer',
              border:
                selectedMode === TestMode.DIGITAL_TWIN
                  ? '2px solid var(--mantine-color-blue-6)'
                  : undefined,
            }}
          >
            <ThemeIcon size="xl" variant="light" color="blue" mb="md">
              <IconCpu size={32} />
            </ThemeIcon>

            <Text fw={600} size="lg">
              全数字仿真
            </Text>
            <Text size="sm" c="dimmed" mt="xs">
              数字孪生，纯软件仿真
              <br />
              成本最低，速度最快
              <br />
              适合早期研发验证
            </Text>

            <List
              mt="md"
              size="sm"
              spacing="xs"
              icon={<IconCheck size={16} color="green" />}
            >
              <List.Item>无需硬件设备</List.Item>
              <List.Item>支持极端场景</List.Item>
              <List.Item>快速迭代 (10x)</List.Item>
            </List>

            <Badge mt="md" color="blue">
              仿真精度: 中
            </Badge>
          </Card>
        </Grid.Col>

        {/* 模式2: 传导测试 */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card
            shadow="sm"
            padding="lg"
            withBorder
            onClick={() => handleSelectMode(TestMode.CONDUCTED)}
            style={{
              cursor: 'pointer',
              border:
                selectedMode === TestMode.CONDUCTED
                  ? '2px solid var(--mantine-color-green-6)'
                  : undefined,
            }}
          >
            <ThemeIcon size="xl" variant="light" color="green" mb="md">
              <IconPlugConnected size={32} />
            </ThemeIcon>

            <Text fw={600} size="lg">
              传导测试
            </Text>
            <Text size="sm" c="dimmed" mt="xs">
              仪表-DUT射频直连
              <br />
              成本中等，精度较高
              <br />
              适合功能验证和调试
            </Text>

            <List
              mt="md"
              size="sm"
              spacing="xs"
              icon={<IconCheck size={16} color="green" />}
            >
              <List.Item>真实RF链路</List.Item>
              <List.Item>隔离干扰</List.Item>
              <List.Item>快速定位问题</List.Item>
            </List>

            <Badge mt="md" color="green">
              测试精度: 高
            </Badge>
          </Card>
        </Grid.Col>

        {/* 模式3: OTA测试 */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card
            shadow="sm"
            padding="lg"
            withBorder
            onClick={() => handleSelectMode(TestMode.OTA)}
            style={{
              cursor: 'pointer',
              border:
                selectedMode === TestMode.OTA
                  ? '2px solid var(--mantine-color-orange-6)'
                  : undefined,
            }}
          >
            <ThemeIcon size="xl" variant="light" color="orange" mb="md">
              <IconRadar2 size={32} />
            </ThemeIcon>

            <Text fw={600} size="lg">
              OTA辐射测试
            </Text>
            <Text size="sm" c="dimmed" mt="xs">
              MPAC暗室空中辐射
              <br />
              成本最高，精度最高
              <br />
              适合最终认证测试
            </Text>

            <List
              mt="md"
              size="sm"
              spacing="xs"
              icon={<IconCheck size={16} color="green" />}
            >
              <List.Item>完整RF链路</List.Item>
              <List.Item>天线真实辐射</List.Item>
              <List.Item>认证级别</List.Item>
            </List>

            <Badge mt="md" color="orange">
              测试精度: 最高
            </Badge>
          </Card>
        </Grid.Col>
      </Grid>

      {/* 对比表 */}
      <Card withBorder padding="md">
        <Title order={4} mb="md">
          模式对比
        </Title>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>对比维度</Table.Th>
              <Table.Th>全数字仿真</Table.Th>
              <Table.Th>传导测试</Table.Th>
              <Table.Th>OTA测试</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            <Table.Tr>
              <Table.Td>成本</Table.Td>
              <Table.Td>
                <Badge color="green">低</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="yellow">中</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="red">高</Badge>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>测试周期</Table.Td>
              <Table.Td>
                <Badge color="green">分钟</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="yellow">小时</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="red">天</Badge>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>场景覆盖</Table.Td>
              <Table.Td>
                <Badge color="green">无限</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="yellow">有限</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="yellow">有限</Badge>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>测试精度</Table.Td>
              <Table.Td>
                <Badge color="yellow">中</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="green">高</Badge>
              </Table.Td>
              <Table.Td>
                <Badge color="green">最高</Badge>
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
      </Card>

      <Button mt="xl" size="lg" disabled={!selectedMode} onClick={handleNext}>
        下一步：选择测试场景
      </Button>
    </Stack>
  )
}
