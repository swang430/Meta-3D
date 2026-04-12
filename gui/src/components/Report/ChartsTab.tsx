/**
 * Charts Tab Component
 *
 * Display time series charts for KPI metrics using Plotly.js
 */

import { useMemo } from 'react'
import { Stack, Card, Text, SimpleGrid, Alert } from '@mantine/core'
import { IconChartLine } from '@tabler/icons-react'
import Plot from 'react-plotly.js'

interface TimeSeriesPoint {
  time_s: number
  rsrp_dbm?: number
  rsrq_db?: number
  sinr_db?: number
  dl_throughput_mbps?: number
  ul_throughput_mbps?: number
  latency_ms?: number
}

interface Props {
  timeSeries?: TimeSeriesPoint[]
}

export function ChartsTab({ timeSeries }: Props) {
  if (!timeSeries || timeSeries.length === 0) {
    return (
      <Alert icon={<IconChartLine size={16} />} color="gray" title="无时间序列数据">
        该报告没有可用的时间序列数据用于图表展示
      </Alert>
    )
  }

  // Prepare chart data
  const chartData = useMemo(() => {
    const times = timeSeries.map((p) => p.time_s)
    const dl = timeSeries.map((p) => p.dl_throughput_mbps)
    const ul = timeSeries.map((p) => p.ul_throughput_mbps)
    const rsrp = timeSeries.map((p) => p.rsrp_dbm)
    const sinr = timeSeries.map((p) => p.sinr_db)
    const latency = timeSeries.map((p) => p.latency_ms)

    return { times, dl, ul, rsrp, sinr, latency }
  }, [timeSeries])

  const commonLayout = {
    margin: { l: 50, r: 20, t: 30, b: 40 },
    showlegend: true,
    legend: { orientation: 'h' as const, y: 1.1 },
  }

  return (
    <Stack gap="md">
      {/* Throughput Chart */}
      <Card withBorder p="md">
        <Text fw={500} mb="sm">
          吞吐量
        </Text>
        <Plot
          data={[
            {
              x: chartData.times,
              y: chartData.dl,
              type: 'scatter',
              mode: 'lines',
              name: '下行吞吐量',
              line: { color: '#228be6', width: 2 },
            },
            {
              x: chartData.times,
              y: chartData.ul,
              type: 'scatter',
              mode: 'lines',
              name: '上行吞吐量',
              line: { color: '#40c057', width: 2 },
            },
          ]}
          layout={{
            ...commonLayout,
            xaxis: { title: '时间 (s)' },
            yaxis: { title: 'Mbps' },
            height: 280,
          }}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </Card>

      <SimpleGrid cols={2}>
        {/* RSRP Chart */}
        <Card withBorder p="md">
          <Text fw={500} mb="sm">
            RSRP
          </Text>
          <Plot
            data={[
              {
                x: chartData.times,
                y: chartData.rsrp,
                type: 'scatter',
                mode: 'lines',
                name: 'RSRP',
                line: { color: '#fa5252', width: 2 },
              },
            ]}
            layout={{
              ...commonLayout,
              showlegend: false,
              xaxis: { title: '时间 (s)' },
              yaxis: { title: 'dBm', range: [-120, -60] },
              height: 220,
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </Card>

        {/* SINR Chart */}
        <Card withBorder p="md">
          <Text fw={500} mb="sm">
            SINR
          </Text>
          <Plot
            data={[
              {
                x: chartData.times,
                y: chartData.sinr,
                type: 'scatter',
                mode: 'lines',
                name: 'SINR',
                line: { color: '#7950f2', width: 2 },
              },
            ]}
            layout={{
              ...commonLayout,
              showlegend: false,
              xaxis: { title: '时间 (s)' },
              yaxis: { title: 'dB', range: [0, 30] },
              height: 220,
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </Card>
      </SimpleGrid>

      {/* Latency Chart */}
      <Card withBorder p="md">
        <Text fw={500} mb="sm">
          端到端延迟
        </Text>
        <Plot
          data={[
            {
              x: chartData.times,
              y: chartData.latency,
              type: 'scatter',
              mode: 'lines',
              name: '延迟',
              line: { color: '#fd7e14', width: 2 },
              fill: 'tozeroy',
              fillcolor: 'rgba(253, 126, 20, 0.1)',
            },
          ]}
          layout={{
            ...commonLayout,
            showlegend: false,
            xaxis: { title: '时间 (s)' },
            yaxis: { title: 'ms' },
            height: 220,
          }}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </Card>
    </Stack>
  )
}

export default ChartsTab
