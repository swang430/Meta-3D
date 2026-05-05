/**
 * Phase 2a-import: ProbePattern 文件上传组件
 *
 * 业界常态是探头厂商出厂带 .cut/.csv/.json pattern 数据, 实验室一次性导入,
 * 12-24 月有效期。本组件给运维人员一个 GUI 入口选文件 + 填元数据 + 上传。
 *
 * 与 PatternCalibrationStart (实测路径) 是双进料口共享同一 ProbePattern sink。
 */
import { useState } from 'react'
import {
  Stack,
  Paper,
  Title,
  Text,
  TextInput,
  NumberInput,
  Select,
  Switch,
  Button,
  Group,
  Alert,
  FileInput,
  Code,
  Badge,
} from '@mantine/core'
import {
  IconUpload,
  IconCheck,
  IconAlertCircle,
  IconFileImport,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import {
  importProbePattern,
  type ImportPatternResponse,
} from '../../../api/probeCalibrationService'
import { logFrontendEvent } from '../../../observability/frontendLogger'

const POLARIZATION_OPTIONS = [
  { value: 'V', label: 'V (Vertical)' },
  { value: 'H', label: 'H (Horizontal)' },
  { value: 'LHCP', label: 'LHCP (Left-Hand Circular)' },
  { value: 'RHCP', label: 'RHCP (Right-Hand Circular)' },
]

const FILE_FORMAT_OPTIONS = [
  { value: 'auto', label: 'Auto-detect (by file extension)' },
  { value: 'ticra_cut', label: 'TICRA .cut' },
  { value: 'csv', label: 'CSV (long: az,el,gain or wide grid)' },
  { value: 'json', label: 'JSON' },
]

export function PatternImportPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [probeId, setProbeId] = useState<number>(0)
  const [polarization, setPolarization] = useState<string>('V')
  const [frequencyMhz, setFrequencyMhz] = useState<number>(3500)
  const [fileFormat, setFileFormat] = useState<string>('auto')
  const [probeModel, setProbeModel] = useState<string>('')
  const [probeVendor, setProbeVendor] = useState<string>('')
  const [probeSerial, setProbeSerial] = useState<string>('')
  const [replaceExisting, setReplaceExisting] = useState<boolean>(true)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<ImportPatternResponse | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const canSubmit =
    file !== null && probeId >= 0 && polarization && frequencyMhz > 0

  const handleSubmit = async () => {
    if (!file) return
    setSubmitting(true)
    setErrorMsg(null)
    setResult(null)
    try {
      const resp = await importProbePattern({
        file,
        probeId,
        polarization,
        frequencyMhz,
        fileFormat: fileFormat === 'auto' ? undefined : (fileFormat as 'ticra_cut' | 'csv' | 'json'),
        probeModel: probeModel || undefined,
        probeVendor: probeVendor || undefined,
        probeSerial: probeSerial || undefined,
        replaceExisting,
      })
      setResult(resp)
      notifications.show({
        title: 'Pattern 导入成功',
        message: `Probe ${probeId} ${polarization} @ ${frequencyMhz} MHz, peak ${resp.peak_gain_dbi?.toFixed(1)} dBi`,
        color: 'green',
        icon: <IconCheck size={18} />,
      })
      logFrontendEvent({
        action: 'probe_pattern.imported',
        component: 'PatternImportPanel',
        message: `probe=${probeId} pol=${polarization} freq=${frequencyMhz}MHz vendor=${probeVendor || '-'} model=${probeModel || '-'} peak=${resp.peak_gain_dbi?.toFixed(1)}dBi`,
      })
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e as Error)?.message ||
        '上传失败'
      setErrorMsg(detail)
      notifications.show({
        title: 'Pattern 导入失败',
        message: detail,
        color: 'red',
        icon: <IconAlertCircle size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'probe_pattern.import_failed',
        component: 'PatternImportPanel',
        error: detail,
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Stack gap="md">
      <Paper p="md" withBorder>
        <Stack gap="xs">
          <Title order={4}>厂商 Datasheet Pattern 导入</Title>
          <Text size="sm" c="dimmed">
            上传探头厂商出厂的 .cut / .csv / .json 方向图文件。导入后该频点 +
            极化的 Pattern 立即被 measure / analysis 阶段消费 (Phase 2f),
            12 个月有效期。
          </Text>
        </Stack>
      </Paper>

      <Paper p="md" withBorder>
        <Stack gap="md">
          <FileInput
            label="Pattern 数据文件"
            description="支持 .cut (TICRA), .csv, .json — 单文件单频点单极化"
            placeholder="选择文件..."
            value={file}
            onChange={setFile}
            leftSection={<IconFileImport size={16} />}
            accept=".cut,.csv,.json"
            required
          />

          <Group grow>
            <NumberInput
              label="Probe ID"
              description="探头编号 (0..N-1)"
              value={probeId}
              onChange={(v) => setProbeId(Number(v))}
              min={0}
              max={1023}
              required
            />
            <Select
              label="极化"
              data={POLARIZATION_OPTIONS}
              value={polarization}
              onChange={(v) => setPolarization(v || 'V')}
              required
            />
            <NumberInput
              label="频率"
              description="MHz; 应与方向图测量频率一致"
              value={frequencyMhz}
              onChange={(v) => setFrequencyMhz(Number(v))}
              min={100}
              max={100000}
              suffix=" MHz"
              required
            />
          </Group>

          <Select
            label="文件格式"
            description="留 Auto-detect 由文件扩展名判断 (.cut/.csv/.json)"
            data={FILE_FORMAT_OPTIONS}
            value={fileFormat}
            onChange={(v) => setFileFormat(v || 'auto')}
          />

          <Group grow>
            <TextInput
              label="探头型号"
              placeholder="e.g. SGA-3500"
              value={probeModel}
              onChange={(e) => setProbeModel(e.currentTarget.value)}
            />
            <TextInput
              label="探头厂商"
              placeholder="e.g. MVG / Satimo / Keysight"
              value={probeVendor}
              onChange={(e) => setProbeVendor(e.currentTarget.value)}
            />
            <TextInput
              label="序列号"
              description="同型号不同实例时填写"
              value={probeSerial}
              onChange={(e) => setProbeSerial(e.currentTarget.value)}
            />
          </Group>

          <Switch
            label="替换已有有效 Pattern"
            description="True (默认): 同 (probe, pol, freq) 旧 VALID 记录置 INVALIDATED, 新记录 VALID。False: 旧记录保留, 共存 (谨慎使用)"
            checked={replaceExisting}
            onChange={(e) => setReplaceExisting(e.currentTarget.checked)}
          />

          <Group justify="flex-end">
            <Button
              leftSection={<IconUpload size={16} />}
              onClick={handleSubmit}
              disabled={!canSubmit || submitting}
              loading={submitting}
            >
              上传并导入
            </Button>
          </Group>
        </Stack>
      </Paper>

      {errorMsg && (
        <Alert color="red" icon={<IconAlertCircle size={18} />} title="导入失败">
          {errorMsg}
        </Alert>
      )}

      {result?.success && (
        <Paper p="md" withBorder>
          <Stack gap="xs">
            <Group justify="space-between">
              <Title order={5}>
                <Group gap="xs">
                  导入成功
                  <Badge color="green">VALID</Badge>
                </Group>
              </Title>
              <Code>{result.pattern_id?.slice(0, 8)}...</Code>
            </Group>
            {result.invalidated_id && (
              <Text size="sm" c="dimmed">
                旧记录{' '}
                <Code>{result.invalidated_id.slice(0, 8)}...</Code>{' '}
                已置 INVALIDATED
              </Text>
            )}
            <Group gap="lg">
              <Stack gap={2}>
                <Text size="xs" c="dimmed">峰值增益</Text>
                <Text fw={600}>{result.peak_gain_dbi?.toFixed(2)} dBi</Text>
              </Stack>
              <Stack gap={2}>
                <Text size="xs" c="dimmed">峰值方向</Text>
                <Text fw={600}>
                  az={result.peak_azimuth_deg?.toFixed(1)}° el={result.peak_elevation_deg?.toFixed(1)}°
                </Text>
              </Stack>
              <Stack gap={2}>
                <Text size="xs" c="dimmed">HPBW (az × el)</Text>
                <Text fw={600}>
                  {result.hpbw_azimuth_deg?.toFixed(1)}° × {result.hpbw_elevation_deg?.toFixed(1)}°
                </Text>
              </Stack>
              <Stack gap={2}>
                <Text size="xs" c="dimmed">前后比</Text>
                <Text fw={600}>{result.front_to_back_ratio_db?.toFixed(1)} dB</Text>
              </Stack>
              <Stack gap={2}>
                <Text size="xs" c="dimmed">网格点数</Text>
                <Text fw={600}>{result.num_az_points} × {result.num_el_points}</Text>
              </Stack>
            </Group>
            {result.warnings.length > 0 && (
              <Alert color="yellow" variant="light">
                {result.warnings.map((w, i) => (
                  <Text key={i} size="sm">{w}</Text>
                ))}
              </Alert>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}
