/**
 * 场景库测试组件
 *
 * 用于在浏览器中验证场景数据的完整性
 */

import { useEffect, useState } from 'react'
import { Stack, Text, Card, Badge, Table, Alert, Group } from '@mantine/core'
import { IconCheck, IconX, IconInfoCircle } from '@tabler/icons-react'
import { scenarioList, getScenarioById, filterScenarios, getScenarioStatistics } from '../../data/scenarioLibrary'

interface TestResult {
  name: string
  passed: boolean
  message: string
}

export function ScenarioLibraryTest() {
  const [testResults, setTestResults] = useState<TestResult[]>([])
  const [allPassed, setAllPassed] = useState(false)

  useEffect(() => {
    runTests()
  }, [])

  const runTests = () => {
    const results: TestResult[] = []

    // 测试1: 场景列表长度
    results.push({
      name: '场景列表长度',
      passed: scenarioList.length === 10,
      message: `场景总数: ${scenarioList.length} (预期: 10)`,
    })

    // 测试2: 场景ID唯一性
    const ids = scenarioList.map((s) => s.id)
    const uniqueIds = new Set(ids)
    results.push({
      name: '场景ID唯一性',
      passed: uniqueIds.size === 10,
      message: `唯一ID数量: ${uniqueIds.size} (预期: 10)`,
    })

    // 测试3: 数据完整性
    const allComplete = scenarioList.every((s) => s.isComplete)
    results.push({
      name: '数据完整性',
      passed: allComplete,
      message: allComplete ? '所有场景数据完整' : '部分场景数据不完整',
    })

    // 测试4: getScenarioById 函数
    const scenario001 = getScenarioById('scenario-001')
    const hasScenario = scenario001 && scenario001.name === '北京CBD早高峰通勤'
    results.push({
      name: 'getScenarioById 函数',
      passed: !!hasScenario,
      message: scenario001 ? `成功获取: ${scenario001.name}` : '未找到场景',
    })

    // 测试5: 场景详情结构
    if (scenario001) {
      const hasAllFields =
        !!scenario001.networkConfig &&
        !!scenario001.trajectory &&
        !!scenario001.environment &&
        !!scenario001.traffic &&
        scenario001.kpiTargets.length > 0

      results.push({
        name: '场景详情结构',
        passed: hasAllFields,
        message: hasAllFields ? '所有必需字段完整' : '缺少必需字段',
      })
    }

    // 测试6: filterScenarios 函数
    const urbanScenarios = filterScenarios({ geographyType: 'urban' })
    results.push({
      name: 'filterScenarios (城市)',
      passed: urbanScenarios.length === 4,
      message: `城市场景数量: ${urbanScenarios.length} (预期: 4)`,
    })

    // 测试7: 统计信息
    const stats = getScenarioStatistics()
    results.push({
      name: 'getScenarioStatistics',
      passed: stats.total === 10,
      message: `总数: ${stats.total}, 真实: ${stats.bySource.realWorld}, 合成: ${stats.bySource.synthetic}`,
    })

    // 测试8: 射线跟踪数据
    let rayTracingCount = 0
    scenarioList.forEach((scenario) => {
      const detail = getScenarioById(scenario.id)
      if (detail?.rayTracingOutput) {
        rayTracingCount++
      }
    })
    results.push({
      name: '射线跟踪数据',
      passed: rayTracingCount >= 2 && rayTracingCount <= 3,
      message: `射线跟踪场景数量: ${rayTracingCount} (预期: 2-3)`,
    })

    // 测试9: 场景分类标签
    const allHaveTaxonomy = scenarioList.every(
      (s) => s.taxonomy && s.taxonomy.source && s.taxonomy.geographyType && s.taxonomy.network
    )
    results.push({
      name: '场景分类标签',
      passed: allHaveTaxonomy,
      message: allHaveTaxonomy ? '所有场景有完整分类' : '部分场景缺少分类',
    })

    // 测试10: 可执行性标记
    const otaCount = scenarioList.filter((s) => s.canExecute.ota).length
    const digitalTwinCount = scenarioList.filter((s) => s.canExecute.digitalTwin).length
    results.push({
      name: '可执行性标记',
      passed: otaCount >= 9 && digitalTwinCount >= 9,
      message: `OTA: ${otaCount}/10, 数字孪生: ${digitalTwinCount}/10`,
    })

    setTestResults(results)
    setAllPassed(results.every((r) => r.passed))
  }

  const passedCount = testResults.filter((r) => r.passed).length
  const totalCount = testResults.length

  return (
    <Stack gap="lg">
      <Alert
        variant="light"
        color={allPassed ? 'green' : 'orange'}
        icon={<IconInfoCircle />}
        title="场景库测试结果"
      >
        <Text size="sm">
          通过: {passedCount}/{totalCount} 项测试
        </Text>
        <Text size="sm" c="dimmed" mt={4}>
          {allPassed ? '所有测试通过，场景数据就绪！' : '部分测试未通过，请检查场景数据。'}
        </Text>
      </Alert>

      <Card withBorder>
        <Text fw={600} size="lg" mb="md">
          测试详情
        </Text>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 60 }}>状态</Table.Th>
              <Table.Th>测试项</Table.Th>
              <Table.Th>结果</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {testResults.map((test, index) => (
              <Table.Tr key={index}>
                <Table.Td>
                  {test.passed ? (
                    <Badge color="green" leftSection={<IconCheck size={14} />}>
                      通过
                    </Badge>
                  ) : (
                    <Badge color="red" leftSection={<IconX size={14} />}>
                      失败
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text fw={500}>{test.name}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {test.message}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>

      <Card withBorder>
        <Text fw={600} size="lg" mb="md">
          场景统计信息
        </Text>
        <Group gap="md">
          <Badge size="lg" variant="light">
            总数: {scenarioList.length}
          </Badge>
          <Badge size="lg" variant="light" color="blue">
            真实场景: {getScenarioStatistics().bySource.realWorld}
          </Badge>
          <Badge size="lg" variant="light" color="cyan">
            合成场景: {getScenarioStatistics().bySource.synthetic}
          </Badge>
          <Badge size="lg" variant="light" color="green">
            城市: {getScenarioStatistics().byGeography.urban}
          </Badge>
          <Badge size="lg" variant="light" color="yellow">
            高速: {getScenarioStatistics().byGeography.highway}
          </Badge>
        </Group>
      </Card>
    </Stack>
  )
}
