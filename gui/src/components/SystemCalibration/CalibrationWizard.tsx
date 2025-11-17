/**
 * Calibration Wizard Component
 *
 * Step-by-step wizard for executing system calibration
 */
import { useState } from 'react';
import {
  Modal,
  Stepper,
  Button,
  Group,
  TextInput,
  Select,
  NumberInput,
  Stack,
  Text,
  Alert,
  Progress,
  Code,
  Paper,
  Badge,
  Divider,
  MultiSelect,
  Textarea,
} from '@mantine/core';
import {
  IconInfoCircle,
  IconCheck,
  IconAlertCircle,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import {
  executeTRPCalibration,
  executeTISCalibration,
  executeRepeatabilityTest,
  executeQuietZoneCalibration,
  executeMultiFrequencyCalibration,
  type TRPCalibrationRequest,
  type TISCalibrationRequest,
  type RepeatabilityTestRequest,
  type QuietZoneCalibrationRequest,
  type MultiFrequencyCalibrationRequest,
} from '../../api/calibrationService';

interface CalibrationWizardProps {
  opened: boolean;
  onClose: () => void;
}

export function CalibrationWizard({ opened, onClose }: CalibrationWizardProps) {
  const [active, setActive] = useState(0);
  const [calibrationType, setCalibrationType] = useState<string>('trp');
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionProgress, setExecutionProgress] = useState(0);
  const [results, setResults] = useState<any>(null);

  // Form data
  const [formData, setFormData] = useState({
    dutModel: 'Standard Dipole λ/2',
    dutSerial: 'DIP-2024-001',
    referenceTRP: 10.5,
    referenceTIS: -90.2,
    frequency: 3500,
    txPower: 23,
    testedBy: '',
    referenceLab: 'NIM (National Institute of Metrology)',
    refCertNumber: '',
  });

  // 探头选择配置
  const [probeSelectionMode, setProbeSelectionMode] = useState<string>('all');
  const [selectedRings, setSelectedRings] = useState<string[]>([]);
  const [selectedPolarizations, setSelectedPolarizations] = useState<string[]>([]);

  // 多频点校准配置
  const [frequencyList, setFrequencyList] = useState<string>('700, 1800, 2600, 3500, 5200');

  const nextStep = () => setActive((current) => (current < 4 ? current + 1 : current));
  const prevStep = () => setActive((current) => (current > 0 ? current - 1 : current));

  const executeCalibration = async () => {
    setIsExecuting(true);
    setExecutionProgress(0);

    try {
      // Progress updates (simulated UI feedback while backend processes)
      const progressUpdates = [
        { progress: 10, message: '连接仪器...', delay: 500 },
        { progress: 25, message: '加载标准 DUT...', delay: 500 },
        { progress: 40, message: '执行球面采样 (0/336)...', delay: 0 },
      ];

      // Run initial progress updates
      for (const step of progressUpdates) {
        if (step.delay > 0) {
          await new Promise(resolve => setTimeout(resolve, step.delay));
        }
        setExecutionProgress(step.progress);
      }

      // Call real API based on calibration type
      let result;

      if (calibrationType === 'trp') {
        const request: TRPCalibrationRequest = {
          dut_model: formData.dutModel,
          dut_serial: formData.dutSerial,
          reference_trp_dbm: formData.referenceTRP,
          frequency_mhz: formData.frequency,
          theta_step_deg: 15,
          phi_step_deg: 15,
          tested_by: formData.testedBy,
          reference_lab: formData.referenceLab,
          ref_cert_number: formData.refCertNumber || undefined,
        };

        // 添加探头选择配置
        if (probeSelectionMode !== 'all') {
          request.probe_selection = {
            mode: probeSelectionMode as 'all' | 'ring' | 'custom' | 'polarization',
            rings: probeSelectionMode === 'ring' ? selectedRings as ('upper' | 'middle' | 'lower')[] : undefined,
            polarizations: probeSelectionMode === 'polarization' ? selectedPolarizations as ('V' | 'H')[] : undefined,
          };
        }

        // Update progress during API call
        setExecutionProgress(60);
        result = await executeTRPCalibration(request);

      } else if (calibrationType === 'tis') {
        const request: TISCalibrationRequest = {
          dut_model: formData.dutModel,
          dut_serial: formData.dutSerial,
          reference_tis_dbm: formData.referenceTIS,
          frequency_mhz: formData.frequency,
          theta_step_deg: 15,
          phi_step_deg: 15,
          tested_by: formData.testedBy,
          reference_lab: formData.referenceLab,
          ref_cert_number: formData.refCertNumber || undefined,
        };

        // 添加探头选择配置
        if (probeSelectionMode !== 'all') {
          request.probe_selection = {
            mode: probeSelectionMode as 'all' | 'ring' | 'custom' | 'polarization',
            rings: probeSelectionMode === 'ring' ? selectedRings as ('upper' | 'middle' | 'lower')[] : undefined,
            polarizations: probeSelectionMode === 'polarization' ? selectedPolarizations as ('V' | 'H')[] : undefined,
          };
        }

        setExecutionProgress(60);
        result = await executeTISCalibration(request);

      } else if (calibrationType === 'multi_frequency') {
        // 解析频率列表
        const frequencies = frequencyList
          .split(',')
          .map(f => parseFloat(f.trim()))
          .filter(f => !isNaN(f) && f > 0);

        if (frequencies.length === 0) {
          throw new Error('请输入有效的频率列表');
        }

        const request: MultiFrequencyCalibrationRequest = {
          calibration_type: 'TRP', // 默认使用 TRP
          frequency_list_mhz: frequencies,
          dut_model: formData.dutModel,
          dut_serial: formData.dutSerial,
          reference_trp_dbm: formData.referenceTRP,
          tested_by: formData.testedBy,
        };

        setExecutionProgress(60);
        result = await executeMultiFrequencyCalibration(request);

      } else if (calibrationType === 'quiet_zone') {
        const request: QuietZoneCalibrationRequest = {
          validation_type: 'field_uniformity',
          frequency_mhz: formData.frequency,
          tested_by: formData.testedBy,
          grid_points: 25,
        };

        setExecutionProgress(60);
        result = await executeQuietZoneCalibration(request);
      } else {
        // Repeatability test
        const request: RepeatabilityTestRequest = {
          calibration_type: calibrationType.toUpperCase() as 'TRP' | 'TIS' | 'EIS',
          dut_model: formData.dutModel,
          num_runs: 10,
          tested_by: formData.testedBy,
        };

        setExecutionProgress(60);
        result = await executeRepeatabilityTest(request);
      }

      // Complete progress
      setExecutionProgress(90);
      await new Promise(resolve => setTimeout(resolve, 500));
      setExecutionProgress(100);

      setResults(result);
      setIsExecuting(false);
      nextStep();

      notifications.show({
        title: '校准完成',
        message: `${calibrationType.toUpperCase()} 校准成功完成`,
        color: 'green',
        icon: <IconCheck size={16} />,
      });

    } catch (error) {
      setIsExecuting(false);
      console.error('Calibration execution failed:', error);

      notifications.show({
        title: '校准失败',
        message: error instanceof Error ? error.message : '无法连接到校准服务，请确保 API Service 已启动',
        color: 'red',
        icon: <IconAlertCircle size={16} />,
      });
    }
  };

  const handleClose = () => {
    setActive(0);
    setResults(null);
    setExecutionProgress(0);
    onClose();
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title="系统校准向导"
      size="xl"
      closeOnClickOutside={false}
    >
      <Stepper active={active} onStepClick={setActive}>
        {/* Step 1: Select Calibration Type */}
        <Stepper.Step label="选择类型" description="校准类型">
          <Stack gap="md" mt="xl">
            <Alert icon={<IconInfoCircle size={16} />} title="校准类型选择">
              选择需要执行的系统级校准类型
            </Alert>

            <Select
              label="校准类型"
              placeholder="选择校准类型"
              value={calibrationType}
              onChange={(value) => setCalibrationType(value || 'trp')}
              data={[
                { value: 'trp', label: 'TRP - 总辐射功率校准' },
                { value: 'tis', label: 'TIS - 总全向灵敏度校准' },
                { value: 'repeatability', label: '可重复性测试' },
                { value: 'quiet_zone', label: '静区质量验证 - 场均匀性' },
                { value: 'multi_frequency', label: '多频点校准（全频段扫描）' },
              ]}
            />

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="xs">
                {calibrationType === 'trp' && 'TRP 校准说明'}
                {calibrationType === 'tis' && 'TIS 校准说明'}
                {calibrationType === 'repeatability' && '可重复性测试说明'}
                {calibrationType === 'quiet_zone' && '静区质量验证说明'}
                {calibrationType === 'multi_frequency' && '多频点校准说明'}
              </Text>
              <Text size="xs" color="dimmed">
                {calibrationType === 'trp' && '验证系统测量辐射功率的准确性，标准: ±0.5 dB'}
                {calibrationType === 'tis' && '验证系统测量接收灵敏度的准确性，标准: ±1.0 dB'}
                {calibrationType === 'repeatability' && '验证系统测量的可重复性，标准: σ < 0.3 dB (TRP) 或 0.5 dB (TIS)'}
                {calibrationType === 'quiet_zone' && '验证静区场均匀性，在 5x5 网格测量，标准: < 1.0 dB (3GPP TS 34.114)'}
                {calibrationType === 'multi_frequency' && '在多个频率点执行校准测试，验证系统全频段性能'}
              </Text>
            </Paper>
          </Stack>
        </Stepper.Step>

        {/* Step 2: Configure DUT */}
        <Stepper.Step label="配置 DUT" description="标准被测设备">
          <Stack gap="md" mt="xl">
            <TextInput
              label="DUT 型号"
              placeholder="例如: Standard Dipole λ/2"
              value={formData.dutModel}
              onChange={(e) => setFormData({ ...formData, dutModel: e.target.value })}
              required
            />

            <TextInput
              label="DUT 序列号"
              placeholder="例如: DIP-2024-001"
              value={formData.dutSerial}
              onChange={(e) => setFormData({ ...formData, dutSerial: e.target.value })}
              required
            />

            {calibrationType === 'trp' && (
              <NumberInput
                label="参考 TRP (dBm)"
                description="来自参考实验室的已知 TRP 值"
                value={formData.referenceTRP}
                onChange={(value) => setFormData({ ...formData, referenceTRP: typeof value === 'number' ? value : 0 })}
                decimalScale={2}
                step={0.1}
                required
              />
            )}

            {calibrationType === 'tis' && (
              <NumberInput
                label="参考 TIS (dBm)"
                description="来自参考实验室的已知 TIS 值"
                value={formData.referenceTIS}
                onChange={(value) => setFormData({ ...formData, referenceTIS: typeof value === 'number' ? value : 0 })}
                decimalScale={2}
                step={0.1}
                required
              />
            )}

            <TextInput
              label="参考实验室"
              placeholder="例如: NIM"
              value={formData.referenceLab}
              onChange={(e) => setFormData({ ...formData, referenceLab: e.target.value })}
            />

            <TextInput
              label="参考证书编号"
              placeholder="例如: NIM-CAL-2024-001"
              value={formData.refCertNumber}
              onChange={(e) => setFormData({ ...formData, refCertNumber: e.target.value })}
            />
          </Stack>
        </Stepper.Step>

        {/* Step 3: Test Configuration */}
        <Stepper.Step label="测试配置" description="频率和功率">
          <Stack gap="md" mt="xl">
            {calibrationType !== 'multi_frequency' ? (
              <NumberInput
                label="测试频率 (MHz)"
                value={formData.frequency}
                onChange={(value) => setFormData({ ...formData, frequency: typeof value === 'number' ? value : 0 })}
                min={600}
                max={6000}
                step={100}
                required
              />
            ) : (
              <Textarea
                label="频率列表 (MHz，逗号分隔)"
                placeholder="700, 1800, 2600, 3500, 5200"
                value={frequencyList}
                onChange={(e) => setFrequencyList(e.target.value)}
                description="输入要测试的频率点，例如：700, 1800, 2600, 3500"
                required
                minRows={3}
              />
            )}

            {calibrationType === 'trp' && (
              <NumberInput
                label="发射功率 (dBm)"
                value={formData.txPower}
                onChange={(value) => setFormData({ ...formData, txPower: typeof value === 'number' ? value : 0 })}
                min={0}
                max={30}
                step={1}
                required
              />
            )}

            {(calibrationType === 'trp' || calibrationType === 'tis') && (
              <>
                <Divider label="探头选择配置" />

                <Select
                  label="探头选择模式"
                  value={probeSelectionMode}
                  onChange={(value) => setProbeSelectionMode(value || 'all')}
                  data={[
                    { value: 'all', label: '全部探头（32个，3层）' },
                    { value: 'ring', label: '选择特定环' },
                    { value: 'polarization', label: '选择极化' },
                  ]}
                />

                {probeSelectionMode === 'ring' && (
                  <MultiSelect
                    label="选择探头环"
                    value={selectedRings}
                    onChange={setSelectedRings}
                    data={[
                      { value: 'upper', label: '上层环（8探头）' },
                      { value: 'middle', label: '中层环（16探头）' },
                      { value: 'lower', label: '下层环（8探头）' },
                    ]}
                    placeholder="选择一个或多个探头环"
                  />
                )}

                {probeSelectionMode === 'polarization' && (
                  <MultiSelect
                    label="选择极化"
                    value={selectedPolarizations}
                    onChange={setSelectedPolarizations}
                    data={[
                      { value: 'V', label: '垂直极化（V）' },
                      { value: 'H', label: '水平极化（H）' },
                    ]}
                    placeholder="选择一个或多个极化"
                  />
                )}
              </>
            )}

            <TextInput
              label="测试工程师"
              placeholder="您的姓名"
              value={formData.testedBy}
              onChange={(e) => setFormData({ ...formData, testedBy: e.target.value })}
              required
            />

            <Divider />

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="xs">
                测试参数汇总
              </Text>
              <Stack gap={4}>
                <Group justify="apart">
                  <Text size="xs" color="dimmed">DUT:</Text>
                  <Text size="xs">{formData.dutModel}</Text>
                </Group>
                <Group justify="apart">
                  <Text size="xs" color="dimmed">频率:</Text>
                  <Text size="xs">{formData.frequency} MHz</Text>
                </Group>
                {calibrationType === 'trp' && (
                  <>
                    <Group justify="apart">
                      <Text size="xs" color="dimmed">参考 TRP:</Text>
                      <Text size="xs">{formData.referenceTRP} dBm</Text>
                    </Group>
                    <Group justify="apart">
                      <Text size="xs" color="dimmed">发射功率:</Text>
                      <Text size="xs">{formData.txPower} dBm</Text>
                    </Group>
                  </>
                )}
                {calibrationType === 'tis' && (
                  <Group justify="apart">
                    <Text size="xs" color="dimmed">参考 TIS:</Text>
                    <Text size="xs">{formData.referenceTIS} dBm</Text>
                  </Group>
                )}
              </Stack>
            </Paper>
          </Stack>
        </Stepper.Step>

        {/* Step 4: Execute */}
        <Stepper.Step label="执行校准" description="运行测试">
          <Stack gap="md" mt="xl">
            {!isExecuting && !results && (
              <Alert icon={<IconInfoCircle size={16} />} title="准备执行">
                点击"开始校准"按钮执行 {calibrationType.toUpperCase()} 校准测试。
                <br />
                预计时间: ~5-10 分钟
              </Alert>
            )}

            {isExecuting && (
              <Stack gap="md">
                <Text size="sm" fw={600}>
                  正在执行校准...
                </Text>
                <Progress value={executionProgress} animated />
                <Text size="xs" color="dimmed">
                  进度: {executionProgress}%
                </Text>
              </Stack>
            )}

            {results && (
              <Stack gap="md">
                <Alert
                  icon={results.validation_pass || results.overall_pass ? <IconCheck size={16} /> : <IconAlertCircle size={16} />}
                  title={(results.validation_pass || results.overall_pass) ? '校准通过' : '校准未通过'}
                  color={(results.validation_pass || results.overall_pass) ? 'green' : 'red'}
                >
                  {(results.validation_pass || results.overall_pass)
                    ? '校准结果符合标准要求'
                    : '校准结果超出允许误差范围'}
                </Alert>

                {calibrationType === 'multi_frequency' && results.results ? (
                  <Paper p="md" withBorder>
                    <Text size="sm" fw={600} mb="xs">多频点校准结果</Text>
                    <Stack gap="xs">
                      {results.results.map((r: any, idx: number) => (
                        <Group key={idx} justify="apart">
                          <Text size="xs" color="dimmed">{r.frequency_mhz} MHz:</Text>
                          <Group gap="xs">
                            <Text size="xs">{r.measured_value_dbm.toFixed(2)} dBm</Text>
                            <Badge size="xs" color={r.validation_pass ? 'green' : 'red'}>
                              {r.error_db > 0 ? '+' : ''}{r.error_db.toFixed(2)} dB
                            </Badge>
                          </Group>
                        </Group>
                      ))}
                    </Stack>
                  </Paper>
                ) : (
                  <Paper p="md" withBorder>
                    <Stack gap="xs">
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">测量值:</Text>
                        <Text size="sm" fw={600}>
                          {results.measured_trp_dbm?.toFixed(2) || results.measured_tis_dbm?.toFixed(2)} dBm
                        </Text>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">误差:</Text>
                        <Badge color={Math.abs(results.error_db) < results.threshold_db ? 'green' : 'red'}>
                          {results.error_db > 0 ? '+' : ''}{results.error_db.toFixed(2)} dB
                        </Badge>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">绝对误差:</Text>
                        <Text size="sm">{results.absolute_error_db.toFixed(2)} dB</Text>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">阈值:</Text>
                        <Text size="sm">±{results.threshold_db} dB</Text>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">采样点数:</Text>
                        <Text size="sm">{results.num_probes_used}</Text>
                      </Group>
                    </Stack>
                  </Paper>
                )}

                <Code block>
                  {JSON.stringify(results, null, 2)}
                </Code>
              </Stack>
            )}
          </Stack>
        </Stepper.Step>

        {/* Completion Step */}
        <Stepper.Completed>
          <Stack gap="md" mt="xl">
            <Alert icon={<IconCheck size={16} />} title="校准完成" color="green">
              系统校准已成功完成并保存到数据库
            </Alert>
            <Text size="sm">
              校准 ID: <Code>{results?.id}</Code>
            </Text>
            <Text size="sm" color="dimmed">
              您可以在"校准记录"页面查看详细结果
            </Text>
          </Stack>
        </Stepper.Completed>
      </Stepper>

      <Group justify="right" mt="xl">
        {active > 0 && active < 4 && (
          <Button variant="default" onClick={prevStep}>
            上一步
          </Button>
        )}
        {active < 3 && (
          <Button onClick={nextStep}>
            下一步
          </Button>
        )}
        {active === 3 && !isExecuting && !results && (
          <Button onClick={executeCalibration} loading={isExecuting}>
            开始校准
          </Button>
        )}
        {active === 4 && (
          <Button onClick={handleClose}>
            完成
          </Button>
        )}
      </Group>
    </Modal>
  );
}
