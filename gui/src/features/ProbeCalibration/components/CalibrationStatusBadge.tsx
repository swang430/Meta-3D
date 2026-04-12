/**
 * Calibration Status Badge Component
 *
 * Displays calibration validity status with color coding
 */
import { Badge, Tooltip, Group, Text } from '@mantine/core'
import {
  IconCheck,
  IconAlertTriangle,
  IconX,
  IconQuestionMark,
} from '@tabler/icons-react'
import type { ValidityStatus, CalibrationType } from '../../../types/probeCalibration'

interface CalibrationStatusBadgeProps {
  status: ValidityStatus
  calibrationType?: CalibrationType
  daysRemaining?: number
  daysOverdue?: number
  size?: 'xs' | 'sm' | 'md' | 'lg'
  showLabel?: boolean
}

const STATUS_CONFIG: Record<
  ValidityStatus,
  {
    color: string
    label: string
    icon: typeof IconCheck
  }
> = {
  valid: {
    color: 'green',
    label: 'Valid',
    icon: IconCheck,
  },
  expiring_soon: {
    color: 'yellow',
    label: 'Expiring Soon',
    icon: IconAlertTriangle,
  },
  expired: {
    color: 'red',
    label: 'Expired',
    icon: IconX,
  },
  unknown: {
    color: 'gray',
    label: 'Unknown',
    icon: IconQuestionMark,
  },
}

export function CalibrationStatusBadge({
  status,
  calibrationType,
  daysRemaining,
  daysOverdue,
  size = 'sm',
  showLabel = true,
}: CalibrationStatusBadgeProps) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon

  const getTooltipContent = () => {
    const parts: string[] = []

    if (calibrationType) {
      parts.push(`${calibrationType.charAt(0).toUpperCase() + calibrationType.slice(1)} Calibration`)
    }

    if (status === 'valid' && daysRemaining !== undefined) {
      parts.push(`Valid for ${daysRemaining} more days`)
    } else if (status === 'expiring_soon' && daysRemaining !== undefined) {
      parts.push(`Expires in ${daysRemaining} days`)
    } else if (status === 'expired' && daysOverdue !== undefined) {
      parts.push(`Expired ${daysOverdue} days ago`)
    } else if (status === 'unknown') {
      parts.push('No calibration data available')
    }

    return parts.join(' - ')
  }

  const iconSize = size === 'xs' ? 10 : size === 'sm' ? 12 : size === 'md' ? 14 : 16

  return (
    <Tooltip label={getTooltipContent()} withArrow>
      <Badge
        color={config.color}
        variant="light"
        size={size}
        leftSection={<Icon size={iconSize} />}
      >
        {showLabel ? config.label : null}
      </Badge>
    </Tooltip>
  )
}

interface ProbeCalibrationStatusSummaryProps {
  amplitude?: ValidityStatus
  phase?: ValidityStatus
  polarization?: ValidityStatus
  pattern?: ValidityStatus
  link?: ValidityStatus
  size?: 'xs' | 'sm' | 'md'
}

export function ProbeCalibrationStatusSummary({
  amplitude,
  phase,
  polarization,
  pattern,
  link,
  size = 'xs',
}: ProbeCalibrationStatusSummaryProps) {
  const types: { key: CalibrationType; label: string; status?: ValidityStatus }[] = [
    { key: 'amplitude', label: 'Amp', status: amplitude },
    { key: 'phase', label: 'Phs', status: phase },
    { key: 'polarization', label: 'Pol', status: polarization },
    { key: 'pattern', label: 'Pat', status: pattern },
    { key: 'link', label: 'Lnk', status: link },
  ]

  return (
    <Group gap={4}>
      {types.map(({ key, label, status }) => (
        <Tooltip key={key} label={`${key}: ${status || 'unknown'}`} withArrow>
          <Badge
            size={size}
            color={status ? STATUS_CONFIG[status].color : 'gray'}
            variant="dot"
          >
            {label}
          </Badge>
        </Tooltip>
      ))}
    </Group>
  )
}

interface OverallStatusIndicatorProps {
  status: ValidityStatus
  validCount?: number
  expiringSoonCount?: number
  expiredCount?: number
  unknownCount?: number
}

export function OverallStatusIndicator({
  status,
  validCount = 0,
  expiringSoonCount = 0,
  expiredCount = 0,
  unknownCount = 0,
}: OverallStatusIndicatorProps) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon

  return (
    <Group gap="xs">
      <Badge color={config.color} size="lg" leftSection={<Icon size={16} />}>
        {config.label}
      </Badge>
      <Text size="xs" c="dimmed">
        {validCount} valid, {expiringSoonCount} expiring, {expiredCount} expired
        {unknownCount > 0 && `, ${unknownCount} unknown`}
      </Text>
    </Group>
  )
}
