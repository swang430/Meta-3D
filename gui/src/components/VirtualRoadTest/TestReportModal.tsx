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
    network_config_detail: report.network_config_detail
      ? {
          authentication: report.network_config_detail.authentication
            ? {
                method: String(report.network_config_detail.authentication.method ?? ''),
                sim_profile: report.network_config_detail.authentication.sim_profile
                  && typeof report.network_config_detail.authentication.sim_profile === 'object'
                  && !Array.isArray(report.network_config_detail.authentication.sim_profile)
                    ? report.network_config_detail.authentication.sim_profile as Record<string, unknown>
                    : undefined,
              }
            : undefined,
          qos: report.network_config_detail.qos
            ? {
                fiveqi: Number(report.network_config_detail.qos.fiveqi ?? 0),
                gbr_enabled: Boolean(report.network_config_detail.qos.gbr_enabled),
                max_dl_bitrate: report.network_config_detail.qos.max_dl_bitrate !== undefined
                  ? String(report.network_config_detail.qos.max_dl_bitrate)
                  : undefined,
                max_ul_bitrate: report.network_config_detail.qos.max_ul_bitrate !== undefined
                  ? String(report.network_config_detail.qos.max_ul_bitrate)
                  : undefined,
              }
            : undefined,
          pdu_session: report.network_config_detail.pdu_session
            ? {
                type: String(report.network_config_detail.pdu_session.type ?? ''),
                sst: Number(report.network_config_detail.pdu_session.sst ?? 0),
                dnn: String(report.network_config_detail.pdu_session.dnn ?? ''),
              }
            : undefined,
          applications: Array.isArray(report.network_config_detail.applications)
            ? report.network_config_detail.applications.map((app) => String(app))
            : undefined,
        }
      : undefined,
    base_station_config_detail: report.base_station_config_detail
      ? {
          rf: report.base_station_config_detail.rf
            ? {
                frequency_mhz: Number(report.base_station_config_detail.rf.frequency_mhz ?? 0),
                mimo_layers: Number(report.base_station_config_detail.rf.mimo_layers ?? 0),
                carrier_aggregation: typeof report.base_station_config_detail.rf.carrier_aggregation === 'boolean'
                  ? report.base_station_config_detail.rf.carrier_aggregation
                  : undefined,
              }
            : undefined,
          antenna: report.base_station_config_detail.antenna
            ? {
                type: String(report.base_station_config_detail.antenna.type ?? ''),
                mimo_config: String(report.base_station_config_detail.antenna.mimo_config ?? ''),
                gain_dbi: Number(report.base_station_config_detail.antenna.gain_dbi ?? 0),
                tilt_deg: report.base_station_config_detail.antenna.tilt_deg !== undefined
                  ? Number(report.base_station_config_detail.antenna.tilt_deg)
                  : undefined,
              }
            : undefined,
          beamforming: report.base_station_config_detail.beamforming
            ? {
                enabled: Boolean(report.base_station_config_detail.beamforming.enabled),
                mode: String(report.base_station_config_detail.beamforming.mode ?? ''),
                num_ssb_beams: Number(report.base_station_config_detail.beamforming.num_ssb_beams ?? 0),
                tracking_mode: report.base_station_config_detail.beamforming.tracking_mode !== undefined
                  ? String(report.base_station_config_detail.beamforming.tracking_mode)
                  : undefined,
              }
            : undefined,
          handover: report.base_station_config_detail.handover
            ? {
                a3_offset_db: report.base_station_config_detail.handover.a3_offset_db !== undefined
                  ? Number(report.base_station_config_detail.handover.a3_offset_db)
                  : undefined,
                hysteresis_db: report.base_station_config_detail.handover.hysteresis_db !== undefined
                  ? Number(report.base_station_config_detail.handover.hysteresis_db)
                  : undefined,
                time_to_trigger_ms: report.base_station_config_detail.handover.time_to_trigger_ms !== undefined
                  ? Number(report.base_station_config_detail.handover.time_to_trigger_ms)
                  : undefined,
              }
            : undefined,
        }
      : undefined,
    digital_twin_config: report.digital_twin_config
      ? {
          channel_model: report.digital_twin_config.channel_model
            ? {
                type: String(report.digital_twin_config.channel_model.type ?? ''),
                scenario: report.digital_twin_config.channel_model.scenario !== undefined
                  ? String(report.digital_twin_config.channel_model.scenario)
                  : undefined,
              }
            : undefined,
          ray_tracing: report.digital_twin_config.ray_tracing
            ? {
                enabled: Boolean(report.digital_twin_config.ray_tracing.enabled),
                max_reflections: report.digital_twin_config.ray_tracing.max_reflections !== undefined
                  ? Number(report.digital_twin_config.ray_tracing.max_reflections)
                  : undefined,
                diffraction: report.digital_twin_config.ray_tracing.diffraction !== undefined
                  ? Boolean(report.digital_twin_config.ray_tracing.diffraction)
                  : undefined,
              }
            : undefined,
          weather: report.digital_twin_config.weather
            ? {
                condition: String(report.digital_twin_config.weather.condition ?? ''),
                rain_rate_mm_h: report.digital_twin_config.weather.rain_rate_mm_h !== undefined
                  ? Number(report.digital_twin_config.weather.rain_rate_mm_h)
                  : undefined,
                temperature_c: report.digital_twin_config.weather.temperature_c !== undefined
                  ? Number(report.digital_twin_config.weather.temperature_c)
                  : undefined,
              }
            : undefined,
          interference: report.digital_twin_config.interference
            ? {
                enabled: Boolean(report.digital_twin_config.interference.enabled),
                model: report.digital_twin_config.interference.model !== undefined
                  ? String(report.digital_twin_config.interference.model)
                  : undefined,
              }
            : undefined,
        }
      : undefined,

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
