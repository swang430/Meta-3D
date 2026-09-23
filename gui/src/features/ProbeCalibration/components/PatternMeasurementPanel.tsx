import { useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Grid,
  Group,
  MultiSelect,
  NumberInput,
  Paper,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { IconAlertTriangle, IconAntenna, IconCircleCheck } from '@tabler/icons-react'

import { useStartPatternCalibration } from '../../../hooks/useProbeCalibration'
import type { CalibrationJobResponse, PolarizationType } from '../../../types/probeCalibration'
import { useOperationalLab } from '../../OperationalLab'
import {
  assertPatternCalibrationJobResponse,
  buildPatternMeasurementRequest,
} from '../patternMeasurement'

interface PatternMeasurementPanelProps {
  labProfileId: string
  chamberId: string
  probeCount: number
}

const OPERATING_MODES = [
  { value: 'mimo_ota', label: 'MIMO OTA' },
  { value: 'siso_trp', label: 'SISO TRP' },
  { value: 'tis', label: 'TIS' },
  { value: 'passive', label: 'Passive' },
]

const POLARIZATIONS = ['V', 'H', 'LHCP', 'RHCP'].map((value) => ({ value, label: value }))

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail !== undefined) return JSON.stringify(detail)
  return error instanceof Error ? error.message : '方向图校准失败'
}

export function PatternMeasurementPanel({
  labProfileId,
  chamberId,
  probeCount,
}: PatternMeasurementPanelProps) {
  const { beginWork } = useOperationalLab()
  const mutation = useStartPatternCalibration()
  const [mode, setMode] = useState<'real' | 'mock' | null>(null)
  const [operatingMode, setOperatingMode] = useState<string | null>('mimo_ota')
  const [probeIds, setProbeIds] = useState('0')
  const [polarizations, setPolarizations] = useState<PolarizationType[]>(['V'])
  const [frequencyMhz, setFrequencyMhz] = useState(3500)
  const [azimuthStepDeg, setAzimuthStepDeg] = useState(30)
  const [elevationStepDeg, setElevationStepDeg] = useState(30)
  const [measurementDistanceM, setMeasurementDistanceM] = useState(3)
  const [ceTxPowerDbm, setCeTxPowerDbm] = useState(-20)
  const [sghGainDbi, setSghGainDbi] = useState(10)
  const [chainCorrectionDb, setChainCorrectionDb] = useState<number | string>('')
  const [calibratedBy, setCalibratedBy] = useState('')
  const [result, setResult] = useState<CalibrationJobResponse | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  const handleStart = async () => {
    setFailure(null)
    setResult(null)
    let request
    try {
      request = buildPatternMeasurementRequest({
        labProfileId,
        chamberId,
        operatingMode,
        probeCount,
        probeIds,
        polarizations,
        frequencyMhz,
        azimuthStepDeg,
        elevationStepDeg,
        measurementDistanceM,
        ceTxPowerDbm,
        sghGainDbi,
        chainCorrectionDb: typeof chainCorrectionDb === 'number' ? chainCorrectionDb : null,
        calibratedBy,
        mode,
      })
    } catch (error) {
      setFailure(errorMessage(error))
      return
    }

    const release = beginWork(
      'probe-pattern-calibration',
      `方向图校准正在使用 LabProfile ${labProfileId}，完成前不能切换`,
    )
    try {
      const response = await mutation.mutateAsync(request)
      setResult(assertPatternCalibrationJobResponse(response, request.use_mock))
    } catch (error) {
      setFailure(errorMessage(error))
    } finally {
      release()
    }
  }

  return (
    <Stack gap="md">
      <Paper withBorder radius="md" p="lg">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <Group gap="sm">
              <IconAntenna size={24} />
              <div>
                <Title order={3}>方向图测量</Title>
                <Text size="sm" c="dimmed">
                  服务端按当前 LabProfile、运行模式和探头极化解析唯一 RF 链路；页面不指定 CE 端口。
                </Text>
              </div>
            </Group>
            <Badge color="blue" variant="light">P2-32B</Badge>
          </Group>

          <Grid>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Select
                required
                label="执行来源"
                placeholder="必须显式选择"
                value={mode}
                onChange={(value) => setMode(value as 'real' | 'mock' | null)}
                data={[
                  { value: 'real', label: '真实硬件校准' },
                  { value: 'mock', label: 'Mock 诊断' },
                ]}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Select
                required
                label="运行模式"
                value={operatingMode}
                onChange={setOperatingMode}
                data={OPERATING_MODES}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <TextInput
                required
                label="探头编号"
                description={`以逗号分隔，当前暗室范围 0–${Math.max(probeCount - 1, 0)}`}
                value={probeIds}
                onChange={(event) => setProbeIds(event.currentTarget.value)}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <MultiSelect
                required
                label="极化"
                data={POLARIZATIONS}
                value={polarizations}
                onChange={(value) => setPolarizations(value as PolarizationType[])}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <NumberInput required label="频率 (MHz)" min={100} max={100000} value={frequencyMhz} onChange={(value) => setFrequencyMhz(Number(value))} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <NumberInput required label="方位步进 (°)" min={1} max={30} value={azimuthStepDeg} onChange={(value) => setAzimuthStepDeg(Number(value))} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <NumberInput required label="俯仰步进 (°)" min={1} max={30} value={elevationStepDeg} onChange={(value) => setElevationStepDeg(Number(value))} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <NumberInput required label="测量距离 (m)" min={0.5} max={10} decimalScale={2} value={measurementDistanceM} onChange={(value) => setMeasurementDistanceM(Number(value))} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <NumberInput required label="CE 校准音功率 (dBm)" min={-50} max={20} value={ceTxPowerDbm} onChange={(value) => setCeTxPowerDbm(Number(value))} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <NumberInput required label="标准增益喇叭增益 (dBi)" value={sghGainDbi} onChange={(value) => setSghGainDbi(Number(value))} />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
              <NumberInput
                required={mode === 'real'}
                label="链路修正 (dB)"
                description="真实测量必填：取自有效 RF 链路/路损校准；不要猜测或默认填 0"
                value={chainCorrectionDb}
                onChange={setChainCorrectionDb}
              />
            </Grid.Col>
            <Grid.Col span={12}>
              <TextInput required label="操作员" value={calibratedBy} onChange={(event) => setCalibratedBy(event.currentTarget.value)} />
            </Grid.Col>
          </Grid>

          {mode === 'real' ? (
            <Alert icon={<IconAlertTriangle size={18} />} color="orange" title="真实硬件动作">
              将按服务端冻结的链路依次控制信道仿真器、转台和信号分析仪。请确认暗室清场、仪器连通和射频安全状态。
            </Alert>
          ) : null}
          {mode === 'mock' ? (
            <Alert color="yellow" title="仅诊断，不具备正式资格">
              Mock 数据会明确标记为模拟，正式方向图判定与 KPI 均为 N/A。
            </Alert>
          ) : null}

          <Group justify="flex-end">
            <Button loading={mutation.isPending} onClick={handleStart}>
              开始方向图测量
            </Button>
          </Group>
        </Stack>
      </Paper>

      {failure ? <Alert color="red" title="方向图测量未完成">{failure}</Alert> : null}
      {result ? (
        <Alert icon={<IconCircleCheck size={18} />} color="green" title="方向图测量完成">
          <Stack gap={4}>
            <Text size="sm">任务：{result.calibration_job_id}</Text>
            <Text size="sm">来源：{result.use_mock ? 'Mock 诊断（N/A）' : '真实硬件'}</Text>
            {result.warnings?.map((warning) => <Text size="sm" key={warning}>警告：{warning}</Text>)}
          </Stack>
        </Alert>
      ) : null}
    </Stack>
  )
}
