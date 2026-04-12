/**
 * Test Report Modal (Virtual Road Test)
 *
 * Uses the unified ReportViewer component to display execution reports
 */

import { useQuery } from '@tanstack/react-query'
import { Modal, ScrollArea, Alert, Loader, Center, Text } from '@mantine/core'
import { IconAlertCircle } from '@tabler/icons-react'
import { fetchExecutionReport } from '../../api/roadTestService'
import { ReportViewer } from '../Report'
import type { ExecutionReport } from '../../types/roadTest'
import type { ReportContentData } from '../../types/report'

interface Props {
  opened: boolean
  onClose: () => void
  executionId: string
}

/**
 * Convert ExecutionReport (VRT format) to ReportContentData (unified format)
 */
function convertToReportContentData(report: ExecutionReport): ReportContentData {
  return {
    source: 'road_test',
    execution_id: report.execution_id,
    title: report.scenario_name,
    description: report.scenario?.description,

    execution: {
      mode: report.mode,
      status: report.status,
      start_time: report.start_time,
      end_time: report.end_time,
      duration_s: report.duration_s,
      notes: report.notes,
    },

    scenario: report.scenario
      ? {
          id: report.scenario.id,
          name: report.scenario.name,
          category: report.scenario.category,
          description: report.scenario.description,
          tags: report.scenario.tags,
        }
      : undefined,

    network: report.network
      ? {
          type: report.network.type,
          band: report.network.band,
          bandwidth_mhz: report.network.bandwidth_mhz,
          duplex_mode: report.network.duplex_mode,
          scs_khz: report.network.scs_khz,
        }
      : undefined,

    environment: report.environment
      ? {
          type: report.environment.type,
          channel_model: report.environment.channel_model,
          weather: report.environment.weather,
          traffic_density: report.environment.traffic_density,
        }
      : undefined,

    route: report.route
      ? {
          duration_s: report.route.duration_s,
          distance_m: report.route.distance_m,
          waypoint_count: report.route.waypoint_count,
          avg_speed_kmh: report.route.avg_speed_kmh,
        }
      : undefined,

    base_stations: report.base_stations?.map((bs) => ({
      bs_id: bs.bs_id,
      name: bs.name,
      tx_power_dbm: bs.tx_power_dbm,
      antenna_config: bs.antenna_config,
      antenna_height_m: bs.antenna_height_m,
    })),

    step_configs: report.step_configs?.map((step) => ({
      step_name: step.step_name,
      enabled: step.enabled,
      parameters: step.parameters,
    })),

    phases: report.phases.map((phase) => ({
      name: phase.name,
      status: phase.status,
      duration_s: phase.duration_s,
      start_time: phase.start_time,
      end_time: phase.end_time,
      notes: phase.notes,
    })),

    kpi_summary: report.kpi_summary.map((kpi) => ({
      name: kpi.name,
      unit: kpi.unit,
      mean: kpi.mean,
      min: kpi.min,
      max: kpi.max,
      std: kpi.std,
      target: kpi.target,
      passed: kpi.passed,
    })),

    overall_result: report.overall_result,
    pass_rate: report.pass_rate,

    events: report.events.map((event) => ({
      time: event.time,
      type: event.type,
      description: event.description,
    })),

    // Time series data for charts
    time_series: report.time_series?.map((point) => ({
      time_s: point.time_s,
      position: point.position,
      rsrp_dbm: point.rsrp_dbm,
      rsrq_db: point.rsrq_db,
      sinr_db: point.sinr_db,
      dl_throughput_mbps: point.dl_throughput_mbps,
      ul_throughput_mbps: point.ul_throughput_mbps,
      latency_ms: point.latency_ms,
      event: point.event,
    })),

    // Trajectory for map
    trajectory: report.trajectory?.map((point) => ({
      lat: point.lat,
      lon: point.lon,
      alt: point.alt,
      time_s: point.time_s,
    })),

    // Detailed configurations
    network_config_detail: report.network_config_detail,
    base_station_config_detail: report.base_station_config_detail,
    digital_twin_config: report.digital_twin_config,

    // Custom config highlights
    custom_config_highlights: report.custom_config_highlights?.map((h) => ({
      category: h.category,
      label: h.label,
      value: h.value,
      description: h.description,
    })),
  }
}

export function TestReportModal({ opened, onClose, executionId }: Props) {
  const {
    data: report,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['execution-report', executionId],
    queryFn: () => fetchExecutionReport(executionId),
    enabled: opened && !!executionId,
  })

  if (!opened) return null

  // Convert VRT report to unified format
  const contentData = report ? convertToReportContentData(report) : undefined

  return (
    <Modal opened={opened} onClose={onClose} title="测试报告" size="xl" centered>
      <ScrollArea h="80vh">
        {isLoading ? (
          <Center py="xl">
            <Loader size="lg" />
            <Text ml="md" c="dimmed">
              加载报告...
            </Text>
          </Center>
        ) : error ? (
          <Alert icon={<IconAlertCircle size={16} />} title="加载失败" color="red">
            {(error as Error).message}
          </Alert>
        ) : contentData ? (
          <ReportViewer contentData={contentData} />
        ) : null}
      </ScrollArea>
    </Modal>
  )
}
