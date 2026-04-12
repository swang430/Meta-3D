/**
 * Trajectory Map Tab Component
 *
 * Display vehicle trajectory and base station locations
 * Uses a simple SVG visualization (can be upgraded to Mapbox/Leaflet later)
 */

import { useMemo } from 'react'
import { Stack, Card, Text, Alert, Table, Group, Badge, ThemeIcon } from '@mantine/core'
import { IconMap, IconMapPin, IconAntenna } from '@tabler/icons-react'

interface TrajectoryPoint {
  lat: number
  lon: number
  alt?: number
  time_s?: number
}

interface BaseStationInfo {
  bs_id: string
  name: string
  tx_power_dbm: number
  antenna_config: string
  antenna_height_m: number
}

interface Props {
  trajectory?: TrajectoryPoint[]
  baseStations?: BaseStationInfo[]
}

export function TrajectoryMapTab({ trajectory, baseStations }: Props) {
  if (!trajectory || trajectory.length === 0) {
    return (
      <Alert icon={<IconMap size={16} />} color="gray" title="无轨迹数据">
        该报告没有可用的路径轨迹数据
      </Alert>
    )
  }

  // Calculate bounds and normalize coordinates for SVG
  const { normalizedPoints, bounds, stats } = useMemo(() => {
    const lats = trajectory.map((p) => p.lat)
    const lons = trajectory.map((p) => p.lon)

    const minLat = Math.min(...lats)
    const maxLat = Math.max(...lats)
    const minLon = Math.min(...lons)
    const maxLon = Math.max(...lons)

    const latRange = maxLat - minLat || 0.001
    const lonRange = maxLon - minLon || 0.001

    // Normalize to 0-400 for SVG viewBox
    const normalized = trajectory.map((p) => ({
      x: ((p.lon - minLon) / lonRange) * 380 + 10,
      y: 390 - ((p.lat - minLat) / latRange) * 380,
      time_s: p.time_s,
    }))

    // Calculate total distance (approximate)
    let totalDistance = 0
    for (let i = 1; i < trajectory.length; i++) {
      const dlat = trajectory[i].lat - trajectory[i - 1].lat
      const dlon = trajectory[i].lon - trajectory[i - 1].lon
      // Rough km conversion at this latitude
      totalDistance += Math.sqrt(dlat * dlat + dlon * dlon) * 111
    }

    return {
      normalizedPoints: normalized,
      bounds: { minLat, maxLat, minLon, maxLon },
      stats: {
        totalPoints: trajectory.length,
        totalDistance: totalDistance.toFixed(2),
        duration: trajectory[trajectory.length - 1]?.time_s?.toFixed(1) || '-',
      },
    }
  }, [trajectory])

  // Generate SVG path
  const pathD = useMemo(() => {
    if (normalizedPoints.length === 0) return ''
    return normalizedPoints.reduce((path, point, i) => {
      return path + (i === 0 ? `M ${point.x} ${point.y}` : ` L ${point.x} ${point.y}`)
    }, '')
  }, [normalizedPoints])

  return (
    <Stack gap="md">
      {/* Trajectory Visualization */}
      <Card withBorder p="md">
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <ThemeIcon size="sm" variant="light" color="blue">
              <IconMap size={14} />
            </ThemeIcon>
            <Text fw={500}>车辆轨迹</Text>
          </Group>
          <Group gap="xs">
            <Badge size="sm" variant="light">
              {stats.totalPoints} 点
            </Badge>
            <Badge size="sm" variant="light" color="green">
              {stats.totalDistance} km
            </Badge>
            <Badge size="sm" variant="light" color="orange">
              {stats.duration} s
            </Badge>
          </Group>
        </Group>

        <svg
          viewBox="0 0 400 400"
          style={{
            width: '100%',
            height: 350,
            background: '#f8f9fa',
            borderRadius: 8,
          }}
        >
          {/* Grid */}
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#dee2e6" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="400" height="400" fill="url(#grid)" />

          {/* Trajectory path */}
          <path d={pathD} fill="none" stroke="#228be6" strokeWidth="3" strokeLinecap="round" />

          {/* Start point */}
          {normalizedPoints.length > 0 && (
            <circle cx={normalizedPoints[0].x} cy={normalizedPoints[0].y} r="8" fill="#40c057" />
          )}

          {/* End point */}
          {normalizedPoints.length > 1 && (
            <circle
              cx={normalizedPoints[normalizedPoints.length - 1].x}
              cy={normalizedPoints[normalizedPoints.length - 1].y}
              r="8"
              fill="#fa5252"
            />
          )}

          {/* Legend */}
          <g transform="translate(10, 370)">
            <circle cx="8" cy="8" r="5" fill="#40c057" />
            <text x="18" y="12" fontSize="10" fill="#495057">
              起点
            </text>
            <circle cx="58" cy="8" r="5" fill="#fa5252" />
            <text x="68" y="12" fontSize="10" fill="#495057">
              终点
            </text>
          </g>
        </svg>

        {/* Coordinate info */}
        <Text size="xs" c="dimmed" mt="xs">
          范围: {bounds.minLat.toFixed(4)}°N ~ {bounds.maxLat.toFixed(4)}°N,{' '}
          {bounds.minLon.toFixed(4)}°E ~ {bounds.maxLon.toFixed(4)}°E
        </Text>
      </Card>

      {/* Base Stations Table */}
      {baseStations && baseStations.length > 0 && (
        <Card withBorder p="md">
          <Group gap="xs" mb="sm">
            <ThemeIcon size="sm" variant="light" color="violet">
              <IconAntenna size={14} />
            </ThemeIcon>
            <Text fw={500}>基站信息 ({baseStations.length})</Text>
          </Group>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>名称</Table.Th>
                <Table.Th>发射功率</Table.Th>
                <Table.Th>天线配置</Table.Th>
                <Table.Th>高度</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {baseStations.map((bs) => (
                <Table.Tr key={bs.bs_id}>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {bs.bs_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>{bs.name}</Table.Td>
                  <Table.Td>{bs.tx_power_dbm} dBm</Table.Td>
                  <Table.Td>{bs.antenna_config}</Table.Td>
                  <Table.Td>{bs.antenna_height_m} m</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}
    </Stack>
  )
}

export default TrajectoryMapTab
