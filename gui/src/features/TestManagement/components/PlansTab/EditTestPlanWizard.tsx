/**
 * Edit Test Plan Wizard
 *
 * Modal for editing an existing test plan's metadata.
 * Uses TanStack Query hooks for data management.
 *
 * @version 2.0.0
 */

import { useState, useEffect } from 'react'
import {
  Modal,
  Button,
  Group,
  TextInput,
  Textarea,
  NumberInput,
  Stack,
  Text,
  LoadingOverlay,
  Paper,
  Select,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useTestPlan, useUpdateTestPlan } from '../../hooks'

interface EditTestPlanWizardProps {
  opened: boolean
  planId: string
  onClose: () => void
  onUpdated: () => void
}

export function EditTestPlanWizard({
  opened,
  planId,
  onClose,
  onUpdated,
}: EditTestPlanWizardProps) {
  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<number>(5)
  const [tags, setTags] = useState<string>('')

  // DUT Info
  const [dutModel, setDutModel] = useState('')
  const [dutSerial, setDutSerial] = useState('')
  const [dutImei, setDutImei] = useState('')
  const [dutManufacturer, setDutManufacturer] = useState('')
  const [dutFirmware, setDutFirmware] = useState('')

  // Test Environment
  const [chamberId, setChamberId] = useState('')
  const [temperature, setTemperature] = useState<number>(25)
  const [humidity, setHumidity] = useState<number>(50)
  const [atmosphericPressure, setAtmosphericPressure] = useState<number | undefined>(
    101.325,
  )
  const [envNotes, setEnvNotes] = useState('')

  // Query hooks
  const { data: testPlan, isLoading } = useTestPlan(opened ? planId : undefined)
  const { mutate: updatePlan, isPending } = useUpdateTestPlan()

  // Load test plan data into form
  useEffect(() => {
    if (testPlan) {
      setName(testPlan.name)
      setDescription(testPlan.description || '')
      setPriority(testPlan.priority)
      setTags(testPlan.tags?.join(', ') || '')

      // DUT Info
      if (testPlan.dut_info) {
        setDutModel(testPlan.dut_info.model)
        setDutSerial(testPlan.dut_info.serial)
        setDutImei(testPlan.dut_info.imei || '')
        setDutManufacturer(testPlan.dut_info.manufacturer || '')
        setDutFirmware(testPlan.dut_info.firmware_version || '')
      }

      // Test Environment
      if (testPlan.test_environment) {
        setChamberId(testPlan.test_environment.chamber_id)
        setTemperature(testPlan.test_environment.temperature)
        setHumidity(testPlan.test_environment.humidity)
        setAtmosphericPressure(testPlan.test_environment.atmospheric_pressure)
        setEnvNotes(testPlan.test_environment.notes || '')
      }
    }
  }, [testPlan])

  const handleSave = () => {
    if (!name.trim()) {
      notifications.show({
        title: '验证失败',
        message: '请输入测试计划名称',
        color: 'red',
      })
      return
    }

    if (!dutModel.trim()) {
      notifications.show({
        title: '验证失败',
        message: '请输入 DUT 型号',
        color: 'red',
      })
      return
    }

    updatePlan(
      {
        planId,
        payload: {
          name,
          description: description || undefined,
          priority,
          tags: tags ? tags.split(',').map((t) => t.trim()) : undefined,
          dut_info: {
            model: dutModel,
            serial: dutSerial,
            imei: dutImei || undefined,
            manufacturer: dutManufacturer || undefined,
            firmware_version: dutFirmware || undefined,
          },
          test_environment: {
            chamber_id: chamberId,
            temperature,
            humidity,
            atmospheric_pressure: atmosphericPressure,
            notes: envNotes || undefined,
          },
        },
      },
      {
        onSuccess: () => {
          onUpdated()
        },
      },
    )
  }

  // Prevent form submission on Enter
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
    }
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="编辑测试计划"
      size="xl"
      closeOnClickOutside={false}
    >
      <LoadingOverlay visible={isLoading} />

      <Stack gap="lg">
        {/* Basic Info Section */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="md">
            基本信息
          </Text>
          <Stack gap="md">
            <TextInput
              label="测试计划名称"
              placeholder="例如：5G NR 性能测试 - 版本 1.0"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={handleKeyDown}
              required
            />

            <Textarea
              label="描述"
              placeholder="测试计划的详细说明..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              minRows={3}
            />

            <NumberInput
              label="优先级"
              description="1 = 最高优先级，10 = 最低优先级"
              value={priority}
              onChange={(val) => setPriority(typeof val === 'number' ? val : 5)}
              min={1}
              max={10}
              required
            />

            <TextInput
              label="标签"
              placeholder="用逗号分隔，例如：5G, LTE, MIMO"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </Stack>
        </Paper>

        {/* DUT Info Section */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="md">
            DUT 信息
          </Text>
          <Stack gap="md">
            <TextInput
              label="DUT 型号"
              placeholder="例如：iPhone 15 Pro"
              value={dutModel}
              onChange={(e) => setDutModel(e.target.value)}
              onKeyDown={handleKeyDown}
              required
            />

            <TextInput
              label="序列号"
              placeholder="例如：SN123456789"
              value={dutSerial}
              onChange={(e) => setDutSerial(e.target.value)}
              onKeyDown={handleKeyDown}
              required
            />

            <Group grow>
              <TextInput
                label="IMEI"
                placeholder="例如：123456789012345"
                value={dutImei}
                onChange={(e) => setDutImei(e.target.value)}
                onKeyDown={handleKeyDown}
              />

              <TextInput
                label="制造商"
                placeholder="例如：Apple"
                value={dutManufacturer}
                onChange={(e) => setDutManufacturer(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </Group>

            <TextInput
              label="固件版本"
              placeholder="例如：iOS 17.0.1"
              value={dutFirmware}
              onChange={(e) => setDutFirmware(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </Stack>
        </Paper>

        {/* Test Environment Section */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="md">
            测试环境
          </Text>
          <Stack gap="md">
            <Select
              label="暗室 ID"
              placeholder="选择暗室"
              value={chamberId}
              onChange={(value) => setChamberId(value || 'MPAC-001')}
              data={[
                { value: 'MPAC-001', label: 'MPAC-001 (主暗室)' },
                { value: 'MPAC-002', label: 'MPAC-002 (备用暗室)' },
              ]}
              required
            />

            <Group grow>
              <NumberInput
                label="温度 (°C)"
                value={temperature}
                onChange={(val) => setTemperature(typeof val === 'number' ? val : 25)}
                min={-10}
                max={50}
                step={0.5}
                decimalScale={1}
                required
              />

              <NumberInput
                label="湿度 (%)"
                value={humidity}
                onChange={(val) => setHumidity(typeof val === 'number' ? val : 50)}
                min={0}
                max={100}
                step={1}
                required
              />
            </Group>

            <NumberInput
              label="大气压 (kPa)"
              value={atmosphericPressure}
              onChange={(val) =>
                setAtmosphericPressure(typeof val === 'number' ? val : undefined)
              }
              min={80}
              max={120}
              step={0.1}
              decimalScale={2}
            />

            <Textarea
              label="环境备注"
              placeholder="其他环境相关说明..."
              value={envNotes}
              onChange={(e) => setEnvNotes(e.target.value)}
              minRows={2}
            />
          </Stack>
        </Paper>
      </Stack>

      <Group justify="right" mt="xl">
        <Button variant="default" onClick={onClose} disabled={isPending}>
          取消
        </Button>
        <Button onClick={handleSave} loading={isPending}>
          保存更改
        </Button>
      </Group>
    </Modal>
  )
}

export default EditTestPlanWizard
