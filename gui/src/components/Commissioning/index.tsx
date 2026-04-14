import { useState, useEffect } from 'react'
import { Container, Title, Text, Stepper, Group, Button, Paper, Stack, Divider, Loader } from '@mantine/core'
import { IconTestPipe, IconPlayerPlay, IconPlayerTrackNext } from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import { PrecheckPhase, ReferencePhase, MIMOTestPhase, AnalysisPhase, ReportPhase } from './Phases'
import * as api from './api'
import type { SessionResponse } from './api'

const PHASE_STEPS = [
  { id: 'precheck', label: '系统预检', desc: '仪表状态与校准验证' },
  { id: 'reference', label: '参考测量', desc: '基线TRP测量与补偿' },
  { id: 'mimo_test', label: 'MIMO测试', desc: '3GPP CDL 吞吐量' },
  { id: 'analysis', label: '分析判定', desc: 'CTIA 门限对比' },
  { id: 'report', label: '报告归档', desc: '生成标准报告' },
]

export function CommissioningSandbox() {
  const [session, setSession] = useState<SessionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeStep, setActiveStep] = useState(0)

  // Initialization
  const initSession = async () => {
    try {
      setLoading(true)
      const res = await api.createSession()
      setSession(res.data)
      setActiveStep(0)
      notifications.show({ title: '首测会话已创建', message: `ID: ${res.data.session_id}`, color: 'blue' })
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message
      notifications.show({ title: '初始化失败', message: detail, color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    initSession()
  }, [])

  const handleRunPhase = async (phaseId: string) => {
    if (!session) return
    try {
      setLoading(true)
      await api.runPhase(session.session_id, phaseId)
      // refresh status
      const res = await api.getSession(session.session_id)
      setSession(res.data)
      
      const newStatus = res.data.phase_statuses[phaseId]
      if (newStatus === 'completed') {
        setActiveStep(prev => prev + 1)
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message
      notifications.show({ title: '执行失败', message: String(detail).substring(0, 200), color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  const handleRunAll = async () => {
    if (!session) return
    try {
      setLoading(true)
      // Step through automatically or just call runAll
      await api.runAll(session.session_id)
      const res = await api.getSession(session.session_id)
      setSession(res.data)
      setActiveStep(5)
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message
      notifications.show({ title: '执行全流程失败', message: String(detail).substring(0, 200), color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  if (!session) {
    return (
      <Container size="xl" py="md">
        <Loader /> <Text>初始化会话中...</Text>
      </Container>
    )
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="lg">
        {/* Header */}
        <div>
          <Group gap="sm" align="center">
            <IconTestPipe size={28} />
            <Title order={2}>暗室首测 (Sandbox)</Title>
          </Group>
          <Text size="sm" c="dimmed" mt={4}>
            3GPP Static MIMO OTA 调试专区 - 基于 UMa CDL-C 模型与 CTIA 门限
          </Text>
        </div>

        {/* Stepper */}
        <Paper withBorder p="xl" radius="md">
          <Stepper active={activeStep} onStepClick={setActiveStep}>
            {PHASE_STEPS.map((step, idx) => {
              const status = session.phase_statuses[step.id]
              const hasError = status === 'failed'
              return (
                <Stepper.Step 
                  key={step.id} 
                  label={step.label} 
                  description={step.desc}
                  color={hasError ? 'red' : undefined}
                >
                  <Stack gap="xl" mt="xl">
                    <Text size="xl" fw={500}>阶段 {idx + 1}: {step.label}</Text>
                    
                    {/* Render Phase Content */}
                    {step.id === 'precheck' && <PrecheckPhase data={session.precheck} />}
                    {step.id === 'reference' && 
                      <ReferencePhase 
                        data={session.reference} 
                        status={session.phase_statuses['reference']} 
                        onConfirm={() => handleRunPhase('reference')}
                      />
                    }
                    {step.id === 'mimo_test' && <MIMOTestPhase data={session.mimo_test} config={session.config} />}
                    {step.id === 'analysis' && <AnalysisPhase data={session.analysis} />}
                    {step.id === 'report' && <ReportPhase data={session} />}

                    {/* Controls */}
                    <Divider />
                    <Group justify="right">
                      {step.id === 'reference' && status === 'waiting' ? (
                        <Text c="dimmed" size="sm">请确认天线安装后继续</Text>
                      ) : (
                        <Button 
                          loading={loading}
                          onClick={() => handleRunPhase(step.id === 'reference' ? 'reference_wait' : step.id)}
                          leftSection={<IconPlayerPlay size={16} />}
                          disabled={status === 'completed'}
                        >
                          {status === 'completed' ? '重新执行' : '执行此阶段'}
                        </Button>
                      )}
                      {(status === 'completed' || step.id === 'report') && idx < 4 && (
                        <Button 
                          variant="light" 
                          rightSection={<IconPlayerTrackNext size={16} />}
                          onClick={() => setActiveStep(idx + 1)}
                        >
                          下一步
                        </Button>
                      )}
                    </Group>
                  </Stack>
                </Stepper.Step>
              )
            })}
            
            <Stepper.Completed>
              <Stack gap="md" align="center" mt="xl" py="xl">
                <IconTestPipe size={48} color="teal" />
                <Title order={3}>首测全流程已完成</Title>
                <Text c="dimmed">测试数据已生成。您可以点击上方各个步骤的圆圈，查看详尽的测量数据、MIMO 吞吐量表格及分析结论。</Text>
                <Text fw={500}>Session: {session.session_id}</Text>
                <Group>
                  <Button variant="light" onClick={() => setActiveStep(2)}>查看 MIMO 吞吐量表格</Button>
                  <Button variant="light" color="grape" onClick={() => setActiveStep(3)}>查看 CTIA 分析结果</Button>
                </Group>
                <Button variant="outline" onClick={initSession} mt="md">开启新会话</Button>
              </Stack>
            </Stepper.Completed>
          </Stepper>
        </Paper>
        
        {/* Debug Controls */}
        <Group justify="space-between">
          <Button variant="light" color="gray" onClick={initSession}>重置会话</Button>
          <Button variant="light" color="grape" onClick={handleRunAll}>一键执行全流程(Mock)</Button>
        </Group>

      </Stack>
    </Container>
  )
}
