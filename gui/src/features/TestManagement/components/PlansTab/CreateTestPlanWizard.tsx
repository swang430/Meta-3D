/**
 * Create Test Plan Wizard
 *
 * Multi-step wizard for creating a new test plan.
 * Uses TanStack Query hooks for data management.
 *
 * @version 2.0.0
 */

import { useState, useEffect } from 'react'
import {
  Modal,
  Stepper,
  Button,
  Group,
  TextInput,
  Textarea,
  NumberInput,
  Stack,
  Text,
  Paper,
  Select,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useCreateTestPlan } from '../../hooks'
import type { CreateTestPlanRequest, DUTInfo, TestEnvironment } from '../../types'

interface CreateTestPlanWizardProps {
  opened: boolean
  onClose: () => void
  onCreated: () => void
}

export function CreateTestPlanWizard({
  opened,
  onClose,
  onCreated,
}: CreateTestPlanWizardProps) {
  const [active, setActive] = useState(0)

  // Step 1: Basic Info
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<number>(5)
  const [tags, setTags] = useState<string>('')

  // Step 2: DUT Info
  const [dutModel, setDutModel] = useState('')
  const [dutSerial, setDutSerial] = useState('')
  const [dutImei, setDutImei] = useState('')
  const [dutManufacturer, setDutManufacturer] = useState('')
  const [dutFirmware, setDutFirmware] = useState('')

  // Step 3: Test Environment
  const [chamberId, setChamberId] = useState('MPAC-001')
  const [temperature, setTemperature] = useState<number>(25)
  const [humidity, setHumidity] = useState<number>(50)
  const [atmosphericPressure, setAtmosphericPressure] = useState<number | undefined>(
    101.325,
  )
  const [envNotes, setEnvNotes] = useState('')

  const { mutate: createPlan, isPending } = useCreateTestPlan()

  const nextStep = () => {
    // Validation
    if (active === 0) {
      if (!name.trim()) {
        notifications.show({
          title: '验证失败',
          message: '请输入测试计划名称',
          color: 'red',
        })
        return
      }
    }

    if (active === 1) {
      if (!dutModel.trim()) {
        notifications.show({
          title: '验证失败',
          message: '请输入 DUT 型号',
          color: 'red',
        })
        return
      }
      if (!dutSerial.trim()) {
        notifications.show({
          title: '验证失败',
          message: '请输入序列号',
          color: 'red',
        })
        return
      }
    }

    if (active === 2) {
      if (!chamberId.trim()) {
        notifications.show({
          title: '验证失败',
          message: '请选择暗室',
          color: 'red',
        })
        return
      }
    }

    setActive((current) => (current < 3 ? current + 1 : current))
  }

  const prevStep = () => setActive((current) => (current > 0 ? current - 1 : current))

  const handleCreate = () => {
    const dutInfo: DUTInfo = {
      model: dutModel,
      serial: dutSerial,
      imei: dutImei || undefined,
      manufacturer: dutManufacturer || undefined,
      firmware_version: dutFirmware || undefined,
    }

    const testEnvironment: TestEnvironment = {
      chamber_id: chamberId,
      temperature,
      humidity,
      atmospheric_pressure: atmosphericPressure,
      notes: envNotes || undefined,
    }

    const request: CreateTestPlanRequest = {
      name,
      description: description || undefined,
      dut_info: dutInfo,
      test_environment: testEnvironment,
      priority,
      tags: tags ? tags.split(',').map((t) => t.trim()) : undefined,
      created_by: '当前用户', // TODO: Get from auth context
    }

    createPlan(request, {
      onSuccess: () => {
        handleClose()
        onCreated()
      },
    })
  }

  const handleClose = () => {
    // Reset form
    setActive(0)
    setName('')
    setDescription('')
    setPriority(5)
    setTags('')
    setDutModel('')
    setDutSerial('')
    setDutImei('')
    setDutManufacturer('')
    setDutFirmware('')
    setChamberId('MPAC-001')
    setTemperature(25)
    setHumidity(50)
    setAtmosphericPressure(101.325)
    setEnvNotes('')
    onClose()
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
      onClose={handleClose}
      title="创建测试计划"
      size="xl"
      closeOnClickOutside={false}
    >
      <Stepper active={active} onStepClick={setActive}>
        {/* Step 1: Basic Info */}
        <Stepper.Step label="基本信息" description="测试计划基本信息">
          <Stack gap="md" mt="xl">
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
        </Stepper.Step>

        {/* Step 2: DUT Info */}
        <Stepper.Step label="DUT 信息" description="被测设备信息">
          <Stack gap="md" mt="xl">
            <Text size="sm" c="dimmed">
              配置被测设备（DUT）的基本信息
            </Text>

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

            <TextInput
              label="固件版本"
              placeholder="例如：iOS 17.0.1"
              value={dutFirmware}
              onChange={(e) => setDutFirmware(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </Stack>
        </Stepper.Step>

        {/* Step 3: Test Environment */}
        <Stepper.Step label="测试环境" description="测试环境配置">
          <Stack gap="md" mt="xl">
            <Text size="sm" c="dimmed">
              配置测试执行的环境参数
            </Text>

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
        </Stepper.Step>

        {/* Step 4: Summary */}
        <Stepper.Step label="确认" description="检查并创建">
          <Stack gap="md" mt="xl">
            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="md">
                测试计划概要
              </Text>
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    名称:
                  </Text>
                  <Text size="sm" fw={500}>
                    {name}
                  </Text>
                </Group>
                {description && (
                  <Group justify="space-between" align="flex-start">
                    <Text size="sm" c="dimmed">
                      描述:
                    </Text>
                    <Text size="sm" style={{ flex: 1, textAlign: 'right' }}>
                      {description}
                    </Text>
                  </Group>
                )}
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    优先级:
                  </Text>
                  <Text size="sm">P{priority}</Text>
                </Group>
                {tags && (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      标签:
                    </Text>
                    <Text size="sm">{tags}</Text>
                  </Group>
                )}
              </Stack>
            </Paper>

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="md">
                DUT 信息
              </Text>
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    型号:
                  </Text>
                  <Text size="sm">{dutModel}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    序列号:
                  </Text>
                  <Text size="sm">{dutSerial}</Text>
                </Group>
                {dutImei && (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      IMEI:
                    </Text>
                    <Text size="sm">{dutImei}</Text>
                  </Group>
                )}
                {dutManufacturer && (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      制造商:
                    </Text>
                    <Text size="sm">{dutManufacturer}</Text>
                  </Group>
                )}
                {dutFirmware && (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      固件版本:
                    </Text>
                    <Text size="sm">{dutFirmware}</Text>
                  </Group>
                )}
              </Stack>
            </Paper>

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="md">
                测试环境
              </Text>
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    暗室:
                  </Text>
                  <Text size="sm">{chamberId}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    温度:
                  </Text>
                  <Text size="sm">{temperature}°C</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    湿度:
                  </Text>
                  <Text size="sm">{humidity}%</Text>
                </Group>
                {atmosphericPressure && (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      大气压:
                    </Text>
                    <Text size="sm">{atmosphericPressure} kPa</Text>
                  </Group>
                )}
              </Stack>
            </Paper>
          </Stack>
        </Stepper.Step>
      </Stepper>

      <Group justify="right" mt="xl">
        {active > 0 && (
          <Button variant="default" onClick={prevStep} disabled={isPending}>
            上一步
          </Button>
        )}
        {active < 3 && <Button onClick={nextStep}>下一步</Button>}
        {active === 3 && (
          <Button onClick={handleCreate} loading={isPending}>
            创建测试计划
          </Button>
        )}
      </Group>
    </Modal>
  )
}

export default CreateTestPlanWizard
