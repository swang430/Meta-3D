/**
 * Step Editor Component
 *
 * Edits parameters and configuration for a selected test step.
 */

import { useState, useEffect } from 'react'
import {
  Stack,
  Paper,
  Text,
  TextInput,
  Textarea,
  NumberInput,
  Select,
  Switch,
  Group,
  Button,
  Badge,
  Divider,
  Code,
  Loader,
  Center,
} from '@mantine/core'
import { IconDeviceFloppy, IconX } from '@tabler/icons-react'
import { useTestSteps, useUpdateTestStep } from '../../hooks'
import type { StepParameter, ParametersMap } from '../../types'

interface StepEditorProps {
  planId: string
  stepId: string
  readOnly: boolean
}

export function StepEditor({ planId, stepId, readOnly }: StepEditorProps) {
  const [parameters, setParameters] = useState<ParametersMap>({})
  const [timeoutSeconds, setTimeoutSeconds] = useState<number>(300)
  const [retryCount, setRetryCount] = useState<number>(0)
  const [continueOnFailure, setContinueOnFailure] = useState<boolean>(false)
  const [hasChanges, setHasChanges] = useState(false)

  // Query hooks
  const { data: steps } = useTestSteps(planId)
  const { mutate: updateStep, isPending } = useUpdateTestStep()

  const step = steps?.find((s) => s.id === stepId)

  // Load step parameters and config
  useEffect(() => {
    if (step) {
      setParameters(step.parameters || {})
      setTimeoutSeconds(step.timeout_seconds || 300)
      setRetryCount(step.retry_count || 0)
      setContinueOnFailure(step.continue_on_failure || false)
      setHasChanges(false)
    }
  }, [step])

  const handleParameterChange = (key: string, value: any) => {
    setParameters((prev) => ({
      ...prev,
      [key]: {
        ...prev[key],
        value,
      },
    }))
    setHasChanges(true)
  }

  const handleSave = () => {
    updateStep(
      {
        planId,
        stepId,
        payload: {
          parameters,
          timeout_seconds: timeoutSeconds,
          retry_count: retryCount,
          continue_on_failure: continueOnFailure,
        },
      },
      {
        onSuccess: () => {
          setHasChanges(false)
        },
      },
    )
  }

  const handleReset = () => {
    if (step) {
      setParameters(step.parameters || {})
      setTimeoutSeconds(step.timeout_seconds || 300)
      setRetryCount(step.retry_count || 0)
      setContinueOnFailure(step.continue_on_failure || false)
      setHasChanges(false)
    }
  }

  if (!step) {
    return (
      <Paper p="md" withBorder>
        <Center>
          <Loader size="sm" />
        </Center>
      </Paper>
    )
  }

  const parameterKeys = Object.keys(parameters)

  return (
    <Stack gap="md">
      {/* Header */}
      <Paper p="md" withBorder>
        <Stack gap="xs">
          <Group justify="space-between">
            <Text size="lg" fw={600}>
              {step.title}
            </Text>
            <Badge color="blue" variant="light">
              步骤 {step.order + 1}
            </Badge>
          </Group>
          {step.description && (
            <Text size="sm" c="dimmed">
              {step.description}
            </Text>
          )}
          <Group gap="xs">
            <Badge size="sm" variant="dot">
              {step.category}
            </Badge>
            <Code size="xs">ID: {step.sequence_library_id}</Code>
          </Group>
        </Stack>
      </Paper>

      {/* Parameters */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            参数配置
          </Text>

          {parameterKeys.length === 0 ? (
            <Text size="sm" c="dimmed" ta="center" py="md">
              此步骤无可配置参数
            </Text>
          ) : (
            <Stack gap="md">
              {parameterKeys.map((key) => {
                const param = parameters[key]
                return (
                  <div key={key}>
                    {renderParameterInput(
                      key,
                      param,
                      handleParameterChange,
                      readOnly,
                    )}
                  </div>
                )
              })}
            </Stack>
          )}
        </Stack>
      </Paper>

      {/* Execution Config */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            执行配置
          </Text>

          <Group grow>
            <NumberInput
              label="超时时间 (秒)"
              value={timeoutSeconds}
              onChange={(value) => {
                setTimeoutSeconds(Number(value))
                setHasChanges(true)
              }}
              min={0}
              disabled={readOnly}
            />
            <NumberInput
              label="重试次数"
              value={retryCount}
              onChange={(value) => {
                setRetryCount(Number(value))
                setHasChanges(true)
              }}
              min={0}
              max={5}
              disabled={readOnly}
            />
          </Group>

          <Switch
            label="失败后继续执行"
            description="如果此步骤失败，是否继续执行后续步骤"
            checked={continueOnFailure}
            onChange={(e) => {
              setContinueOnFailure(e.currentTarget.checked)
              setHasChanges(true)
            }}
            disabled={readOnly}
          />
        </Stack>
      </Paper>

      {/* Action Buttons */}
      {!readOnly && hasChanges && (
        <Group justify="flex-end">
          <Button
            variant="default"
            leftSection={<IconX size={16} />}
            onClick={handleReset}
            disabled={isPending}
          >
            重置
          </Button>
          <Button
            leftSection={<IconDeviceFloppy size={16} />}
            onClick={handleSave}
            loading={isPending}
          >
            保存更改
          </Button>
        </Group>
      )}
    </Stack>
  )
}

/**
 * Render appropriate input component based on parameter type
 */
function renderParameterInput(
  key: string,
  param: StepParameter,
  onChange: (key: string, value: any) => void,
  readOnly: boolean,
) {
  const commonProps = {
    label: param.label,
    description: param.description,
    placeholder: param.placeholder,
    required: param.required,
    disabled: readOnly,
  }

  switch (param.type) {
    case 'text':
      return (
        <TextInput
          {...commonProps}
          value={param.value || ''}
          onChange={(e) => onChange(key, e.target.value)}
        />
      )

    case 'number':
      return (
        <NumberInput
          {...commonProps}
          value={param.value}
          onChange={(value) => onChange(key, value)}
          min={param.validation?.min}
          max={param.validation?.max}
          suffix={param.unit ? ` ${param.unit}` : undefined}
        />
      )

    case 'select':
      return (
        <Select
          {...commonProps}
          value={param.value}
          onChange={(value) => onChange(key, value)}
          data={param.validation?.options || []}
        />
      )

    case 'textarea':
      return (
        <Textarea
          {...commonProps}
          value={param.value || ''}
          onChange={(e) => onChange(key, e.target.value)}
          minRows={3}
        />
      )

    case 'boolean':
      return (
        <Switch
          label={param.label}
          description={param.description}
          checked={param.value || false}
          onChange={(e) => onChange(key, e.currentTarget.checked)}
          disabled={readOnly}
        />
      )

    case 'json':
      return (
        <Textarea
          {...commonProps}
          value={
            typeof param.value === 'string'
              ? param.value
              : JSON.stringify(param.value, null, 2)
          }
          onChange={(e) => {
            try {
              const parsed = JSON.parse(e.target.value)
              onChange(key, parsed)
            } catch {
              onChange(key, e.target.value)
            }
          }}
          minRows={5}
          styles={{ input: { fontFamily: 'monospace' } }}
        />
      )

    default:
      return (
        <TextInput
          {...commonProps}
          value={param.value || ''}
          onChange={(e) => onChange(key, e.target.value)}
        />
      )
  }
}

export default StepEditor
