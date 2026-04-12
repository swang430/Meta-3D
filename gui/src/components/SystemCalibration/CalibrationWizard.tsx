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
    testedBy: '测试工程师',
    referenceLab: 'NIM (National Institute of Metrology)',
    refCertNumber: '',
    repeatabilityTestType: 'TRP' as 'TRP' | 'TIS' | 'EIS',
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

      } else if (calibrationType.startsWith('quiet_zone_')) {
        // Determine validation type from calibrationType
        let validation_type = 'field_uniformity';
        let extraParams: any = {};

        if (calibrationType === 'quiet_zone_field') {
          validation_type = 'field_uniformity';
          extraParams.grid_points = 25;
        } else if (calibrationType === 'quiet_zone_correlation') {
          validation_type = 'spatial_correlation';
          extraParams.num_antennas = 4;  // 4x4 MIMO
          extraParams.target_channel_model = '3GPP_UMa';
        } else if (calibrationType === 'quiet_zone_coupling') {
          validation_type = 'probe_coupling';
          // Test all 32 probes by default
          extraParams.probe_ids = Array.from({ length: 32 }, (_, i) => i + 1);
        } else if (calibrationType === 'quiet_zone_phase') {
          validation_type = 'phase_stability';
          extraParams.duration_sec = 60.0;  // 60 seconds test
        }

        const request: QuietZoneCalibrationRequest = {
          validation_type,
          frequency_mhz: formData.frequency,
          tested_by: formData.testedBy,
          ...extraParams,
        };

        setExecutionProgress(60);
        result = await executeQuietZoneCalibration(request);
      } else if (calibrationType === 'repeatability') {
        // Repeatability test
        const request: RepeatabilityTestRequest = {
          test_type: formData.repeatabilityTestType,
          dut_model: formData.dutModel,
          dut_serial: formData.dutSerial,
          num_runs: 10,
          frequency_mhz: formData.frequency,
          tested_by: formData.testedBy,
        };

        setExecutionProgress(60);
        result = await executeRepeatabilityTest(request);

      } else if (calibrationType === 'path_loss' || calibrationType === 'uplink_chain' || calibrationType === 'downlink_chain') {
        // 路径校准 - 调用路径校准 API
        const chamberId = 'b7cd8de0-da25-473a-9618-4f0795046326'; // TODO: 从 context 获取

        let calibrationEndpoint: string;
        let requestBody: Record<string, any>;

        if (calibrationType === 'path_loss') {
          calibrationEndpoint = '/api/v1/calibration/path-loss/start';
          requestBody = {
            chamber_id: chamberId,
            frequency_mhz: formData.frequency,
            calibrated_by: formData.testedBy,
            sgh_model: 'Standard Gain Horn',
            sgh_gain_dbi: 10.0,
          };
        } else if (calibrationType === 'uplink_chain') {
          calibrationEndpoint = '/api/v1/calibration/path-loss/rf-chain/uplink';
          requestBody = {
            chamber_id: chamberId,
            chain_type: 'uplink',
            frequency_mhz: formData.frequency,
            calibrated_by: formData.testedBy,
          };
        } else {
          calibrationEndpoint = '/api/v1/calibration/path-loss/rf-chain/downlink';
          requestBody = {
            chamber_id: chamberId,
            chain_type: 'downlink',
            frequency_mhz: formData.frequency,
            calibrated_by: formData.testedBy,
          };
        }

        setExecutionProgress(60);

        const response = await fetch(calibrationEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
          const errorDetail = await response.text();
          throw new Error(`路径校准失败: ${response.statusText} - ${errorDetail}`);
        }

        result = await response.json();
        result.validation_pass = true; // 路径校准没有验证阈值

      } else if (calibrationType.startsWith('baseline_')) {
        // 相对校准基线 - 调用基线创建 API
        const baselineType = calibrationType.replace('baseline_', '');
        const chamberId = 'b7cd8de0-da25-473a-9618-4f0795046326'; // TODO: 从 context 获取

        setExecutionProgress(40);

        const response = await fetch(
          `/api/v1/calibration/baseline/create?chamber_id=${chamberId}&calibration_type=${baselineType}&frequency_mhz=${formData.frequency}&reference_channel_id=0&calibrated_by=${encodeURIComponent(formData.testedBy)}`,
          { method: 'POST' }
        );

        setExecutionProgress(80);

        if (!response.ok) {
          throw new Error(`基线创建失败: ${response.statusText}`);
        }

        result = await response.json();
        result.validation_pass = result.success;
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
                {
                  group: '系统验证测试 (System Validation)', items: [
                    { value: 'trp', label: 'TRP 验证测试 - 总辐射功率验证' },
                    { value: 'tis', label: 'TIS 验证测试 - 总全向灵敏度验证' },
                    { value: 'repeatability', label: '可重复性测试' },
                  ]
                },
                {
                  group: '路径校准 (Path Calibration)', items: [
                    { value: 'path_loss', label: '探头路损校准 (Probe Path Loss)' },
                    { value: 'uplink_chain', label: '上行链路校准 (UL/LNA)' },
                    { value: 'downlink_chain', label: '下行链路校准 (DL/PA)' },
                    { value: 'multi_frequency', label: '多频点路损校准（全频段扫描）' },
                    { value: 'baseline_amplitude', label: '⭐ 幅度校准基线 (Quick Mode)' },
                    { value: 'baseline_phase', label: '⭐ 相位校准基线 (Quick Mode)' },
                    { value: 'baseline_path_loss', label: '⭐ 路损校准基线 (Quick Mode)' },
                  ]
                },
                {
                  group: '静区质量验证 (Quiet Zone)', items: [
                    { value: 'quiet_zone_field', label: '场均匀性验证' },
                    { value: 'quiet_zone_correlation', label: '空间相关性验证' },
                    { value: 'quiet_zone_coupling', label: '探头互耦测量' },
                    { value: 'quiet_zone_phase', label: '相位稳定性测试' },
                  ]
                },
              ]}
            />

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="xs">
                {calibrationType === 'trp' && 'TRP 验证测试说明'}
                {calibrationType === 'tis' && 'TIS 验证测试说明'}
                {calibrationType === 'repeatability' && '可重复性测试说明'}
                {calibrationType === 'path_loss' && '探头路损校准说明'}
                {calibrationType === 'uplink_chain' && '上行链路校准说明'}
                {calibrationType === 'downlink_chain' && '下行链路校准说明'}
                {calibrationType === 'quiet_zone_field' && '场均匀性验证说明'}
                {calibrationType === 'quiet_zone_correlation' && '空间相关性验证说明'}
                {calibrationType === 'quiet_zone_coupling' && '探头互耦测量说明'}
                {calibrationType === 'quiet_zone_phase' && '相位稳定性测试说明'}
                {calibrationType === 'multi_frequency' && '多频点路损校准说明'}
                {calibrationType.startsWith('baseline_') && '相对校准基线说明'}
              </Text>
              <Text size="xs" color="dimmed">
                {calibrationType === 'trp' && '使用标准 DUT 验证系统测量辐射功率的准确性，标准: ±0.5 dB'}
                {calibrationType === 'tis' && '使用标准 DUT 验证系统测量接收灵敏度的准确性，标准: ±1.0 dB'}
                {calibrationType === 'repeatability' && '验证系统测量的可重复性，标准: σ < 0.3 dB (TRP) 或 0.5 dB (TIS)'}
                {calibrationType === 'path_loss' && '使用 SGH 测量每个探头到静区中心的空间路损，用于测量补偿'}
                {calibrationType === 'uplink_chain' && '测量上行 RF 链路增益 (探头→LNA→信道仿真器)，用于 TRP 测量补偿'}
                {calibrationType === 'downlink_chain' && '测量下行 RF 链路增益 (信道仿真器→PA→探头)，用于 TIS 测量补偿'}
                {calibrationType === 'quiet_zone_field' && '验证静区场均匀性，在 5x5 网格测量，标准: < 1.0 dB (3GPP TS 34.114)'}
                {calibrationType === 'quiet_zone_correlation' && '验证 MIMO 信道空间相关性矩阵，对比目标 3GPP 信道模型，标准: RMS 误差 < 0.1'}
                {calibrationType === 'quiet_zone_coupling' && '测量探头间 S 参数互耦矩阵，验证探头隔离度，标准: 最大互耦 < -20 dB'}
                {calibrationType === 'quiet_zone_phase' && '验证系统相位稳定性，测量相位漂移，标准: 漂移 < 10° (3GPP)'}
                {calibrationType === 'multi_frequency' && '在多个频率点测量路损，生成频率-路损曲线，支持后续频率插值'}
                {calibrationType.startsWith('baseline_') && '建立通道间 Delta 基线，后续仅需测量参考通道即可推导其他通道值，大幅缩短日常校准时间'}
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

            {calibrationType === 'repeatability' && (
              <Select
                label="测试类型"
                description="选择要进行可重复性测试的类型"
                value={formData.repeatabilityTestType}
                onChange={(value) => setFormData({ ...formData, repeatabilityTestType: (value || 'TRP') as 'TRP' | 'TIS' | 'EIS' })}
                data={[
                  { value: 'TRP', label: 'TRP - 总辐射功率' },
                  { value: 'TIS', label: 'TIS - 总全向灵敏度' },
                  { value: 'EIS', label: 'EIS - 有效全向灵敏度' },
                ]}
                required
              />
            )}

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
                ) : calibrationType.startsWith('quiet_zone_') ? (
                  <Paper p="md" withBorder>
                    <Stack gap="xs">
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">验证类型:</Text>
                        <Text size="sm" fw={600}>{results.validation_type}</Text>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">频率:</Text>
                        <Text size="sm">{results.frequency_mhz} MHz</Text>
                      </Group>

                      {/* Field Uniformity Results */}
                      {results.field_uniformity_db != null && results.field_mean_dbm != null && (
                        <>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">场均匀性:</Text>
                            <Text size="sm" fw={600}>{results.field_uniformity_db.toFixed(2)} dB</Text>
                          </Group>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">平均场强:</Text>
                            <Text size="sm">{results.field_mean_dbm.toFixed(2)} dBm</Text>
                          </Group>
                        </>
                      )}

                      {/* Spatial Correlation Results */}
                      {results.correlation_error_rms != null && (
                        <>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">RMS 误差:</Text>
                            <Badge color={results.correlation_error_rms < 0.1 ? 'green' : 'red'}>
                              {results.correlation_error_rms.toFixed(3)}
                            </Badge>
                          </Group>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">阈值:</Text>
                            <Text size="sm">{'< '}0.1</Text>
                          </Group>
                        </>
                      )}

                      {/* Probe Coupling Results */}
                      {results.max_coupling_db != null && (
                        <>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">最大互耦:</Text>
                            <Badge color={results.max_coupling_db < -20 ? 'green' : 'red'}>
                              {results.max_coupling_db.toFixed(2)} dB
                            </Badge>
                          </Group>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">阈值:</Text>
                            <Text size="sm">{'< '}-20 dB</Text>
                          </Group>
                        </>
                      )}

                      {/* Phase Stability Results */}
                      {results.phase_drift_deg != null && (
                        <>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">相位漂移:</Text>
                            <Badge color={results.phase_drift_deg < 10 ? 'green' : 'red'}>
                              {results.phase_drift_deg.toFixed(2)}°
                            </Badge>
                          </Group>
                          <Group justify="apart">
                            <Text size="sm" color="dimmed">阈值:</Text>
                            <Text size="sm">{'< '}10°</Text>
                          </Group>
                        </>
                      )}
                    </Stack>
                  </Paper>
                ) : calibrationType === 'repeatability' ? (
                  <Paper p="md" withBorder>
                    <Stack gap="xs">
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">测试类型:</Text>
                        <Text size="sm" fw={600}>{results.calibration_type || results.test_type}</Text>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">运行次数:</Text>
                        <Text size="sm">{results.num_runs}</Text>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">平均值:</Text>
                        <Text size="sm" fw={600}>{results.mean?.toFixed(2)} dBm</Text>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">标准差 (σ):</Text>
                        <Badge color={results.std_dev < results.threshold ? 'green' : 'red'}>
                          {results.std_dev?.toFixed(3)} dB
                        </Badge>
                      </Group>
                      <Group justify="apart">
                        <Text size="sm" color="dimmed">阈值:</Text>
                        <Text size="sm">{'< '}{results.threshold} dB</Text>
                      </Group>
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
                      {results.error_db != null && (
                        <Group justify="apart">
                          <Text size="sm" color="dimmed">误差:</Text>
                          <Badge color={Math.abs(results.error_db) < results.threshold_db ? 'green' : 'red'}>
                            {results.error_db > 0 ? '+' : ''}{results.error_db.toFixed(2)} dB
                          </Badge>
                        </Group>
                      )}
                      {results.absolute_error_db != null && (
                        <Group justify="apart">
                          <Text size="sm" color="dimmed">绝对误差:</Text>
                          <Text size="sm">{results.absolute_error_db.toFixed(2)} dB</Text>
                        </Group>
                      )}
                      {results.threshold_db !== undefined && (
                        <Group justify="apart">
                          <Text size="sm" color="dimmed">阈值:</Text>
                          <Text size="sm">±{results.threshold_db} dB</Text>
                        </Group>
                      )}
                      {results.num_probes_used !== undefined && (
                        <Group justify="apart">
                          <Text size="sm" color="dimmed">采样点数:</Text>
                          <Text size="sm">{results.num_probes_used}</Text>
                        </Group>
                      )}
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
            {results?.id && (
              <Text size="sm">
                校准 ID: <Code>{String(results.id)}</Code>
              </Text>
            )}
            {results?.validation_pass !== undefined && (
              <Text size="sm">
                验证结果: <Code>{results.validation_pass ? '通过 ✓' : '未通过 ✗'}</Code>
              </Text>
            )}
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
