import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { Box, Title, Text, Group, Badge } from '@mantine/core'
import { IconTrendingUp, IconTrendingDown, IconMinus } from '@tabler/icons-react'

export interface TimeSeriesDataPoint {
  timestamp: string
  value: number
  execution_id: string
  is_anomaly?: boolean
  z_score?: number
}

export interface TrendData {
  direction: 'increasing' | 'decreasing' | 'stable'
  slope: number
  r_squared: number
  strength: 'strong' | 'moderate' | 'weak'
}

interface Props {
  title: string
  metricName: string
  dataPoints: TimeSeriesDataPoint[]
  trend?: TrendData
  rollingMean?: number[]
  rollingStd?: number[]
  anomalyThreshold?: number
  height?: number
}

export default function TimeSeriesChart({
  title,
  metricName,
  dataPoints,
  trend,
  rollingMean,
  rollingStd,
  anomalyThreshold = 3.0,
  height = 500
}: Props) {
  const plotData = useMemo(() => {
    if (!dataPoints || dataPoints.length === 0) {
      return []
    }

    const timestamps = dataPoints.map(p => new Date(p.timestamp))
    const values = dataPoints.map(p => p.value)
    const anomalyIndices = dataPoints
      .map((p, i) => (p.is_anomaly ? i : -1))
      .filter(i => i >= 0)

    const traces: Plotly.Data[] = []

    // Main time series line
    traces.push({
      x: timestamps,
      y: values,
      type: 'scatter',
      mode: 'lines+markers',
      name: metricName,
      line: { color: '#228be6', width: 2 },
      marker: { size: 6 },
      hovertemplate: '<b>%{x}</b><br>' +
                     `${metricName}: %{y:.2f}<br>` +
                     '<extra></extra>'
    })

    // Anomaly points
    if (anomalyIndices.length > 0) {
      traces.push({
        x: anomalyIndices.map(i => timestamps[i]),
        y: anomalyIndices.map(i => values[i]),
        type: 'scatter',
        mode: 'markers',
        name: 'Anomalies',
        marker: {
          color: '#fa5252',
          size: 12,
          symbol: 'x',
          line: { color: '#c92a2a', width: 2 }
        },
        hovertemplate: '<b>Anomaly Detected</b><br>' +
                       '%{x}<br>' +
                       `${metricName}: %{y:.2f}<br>` +
                       `Z-score: ${dataPoints.find((_, i) => anomalyIndices.includes(i))?.z_score?.toFixed(2) || 'N/A'}<br>` +
                       '<extra></extra>'
      })
    }

    // Rolling mean
    if (rollingMean && rollingMean.length === timestamps.length) {
      traces.push({
        x: timestamps,
        y: rollingMean,
        type: 'scatter',
        mode: 'lines',
        name: 'Rolling Mean',
        line: { color: '#40c057', width: 1.5, dash: 'dash' },
        hovertemplate: '<b>Rolling Mean</b><br>' +
                       '%{x}<br>' +
                       'Value: %{y:.2f}<br>' +
                       '<extra></extra>'
      })
    }

    // Rolling std bounds (mean ± threshold * std)
    if (rollingMean && rollingStd && rollingMean.length === rollingStd.length && rollingMean.length === timestamps.length) {
      const upperBound = rollingMean.map((m, i) => m + anomalyThreshold * rollingStd[i])
      const lowerBound = rollingMean.map((m, i) => m - anomalyThreshold * rollingStd[i])

      // Upper bound
      traces.push({
        x: timestamps,
        y: upperBound,
        type: 'scatter',
        mode: 'lines',
        name: `+${anomalyThreshold}σ Threshold`,
        line: { color: '#fd7e14', width: 1, dash: 'dot' },
        showlegend: true,
        hovertemplate: '<b>Upper Threshold</b><br>' +
                       '%{x}<br>' +
                       'Value: %{y:.2f}<br>' +
                       '<extra></extra>'
      })

      // Lower bound
      traces.push({
        x: timestamps,
        y: lowerBound,
        type: 'scatter',
        mode: 'lines',
        name: `-${anomalyThreshold}σ Threshold`,
        line: { color: '#fd7e14', width: 1, dash: 'dot' },
        showlegend: true,
        fill: 'tonexty',
        fillcolor: 'rgba(253, 126, 20, 0.1)',
        hovertemplate: '<b>Lower Threshold</b><br>' +
                       '%{x}<br>' +
                       'Value: %{y:.2f}<br>' +
                       '<extra></extra>'
      })
    }

    // Trend line
    if (trend && timestamps.length > 1) {
      const firstTime = timestamps[0].getTime()
      const lastTime = timestamps[timestamps.length - 1].getTime()
      const timeSpan = (lastTime - firstTime) / 1000 // seconds

      const firstValue = values[0] + trend.slope * 0
      const lastValue = values[0] + trend.slope * timeSpan

      traces.push({
        x: [timestamps[0], timestamps[timestamps.length - 1]],
        y: [firstValue, lastValue],
        type: 'scatter',
        mode: 'lines',
        name: `Trend (R²=${trend.r_squared.toFixed(3)})`,
        line: { color: '#7950f2', width: 2, dash: 'dashdot' },
        hovertemplate: '<b>Trend Line</b><br>' +
                       '%{x}<br>' +
                       'Value: %{y:.2f}<br>' +
                       `Slope: ${trend.slope.toExponential(3)}<br>` +
                       `R²: ${trend.r_squared.toFixed(3)}<br>` +
                       '<extra></extra>'
      })
    }

    return traces
  }, [dataPoints, trend, rollingMean, rollingStd, metricName, anomalyThreshold])

  const layout: Partial<Plotly.Layout> = {
    title: undefined,
    xaxis: {
      title: 'Time',
      showgrid: true,
      gridcolor: '#e9ecef',
      zeroline: false
    },
    yaxis: {
      title: metricName,
      showgrid: true,
      gridcolor: '#e9ecef',
      zeroline: true
    },
    hovermode: 'closest',
    showlegend: true,
    legend: {
      orientation: 'h',
      yanchor: 'bottom',
      y: 1.02,
      xanchor: 'right',
      x: 1
    },
    margin: { l: 60, r: 40, t: 40, b: 60 },
    plot_bgcolor: '#ffffff',
    paper_bgcolor: '#ffffff'
  }

  const config: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
    displaylogo: false
  }

  const getTrendIcon = () => {
    if (!trend) return null
    switch (trend.direction) {
      case 'increasing':
        return <IconTrendingUp size={20} color="#40c057" />
      case 'decreasing':
        return <IconTrendingDown size={20} color="#fa5252" />
      default:
        return <IconMinus size={20} color="#868e96" />
    }
  }

  const getTrendColor = () => {
    if (!trend) return 'gray'
    switch (trend.direction) {
      case 'increasing':
        return 'green'
      case 'decreasing':
        return 'red'
      default:
        return 'gray'
    }
  }

  return (
    <Box>
      <Group justify="space-between" mb="md">
        <Title order={4}>{title}</Title>
        {trend && (
          <Group gap="xs">
            {getTrendIcon()}
            <Badge color={getTrendColor()} variant="light">
              {trend.direction.toUpperCase()} ({trend.strength})
            </Badge>
            <Text size="sm" c="dimmed">
              R² = {trend.r_squared.toFixed(3)}
            </Text>
          </Group>
        )}
      </Group>

      <Plot
        data={plotData}
        layout={{ ...layout, height }}
        config={config}
        style={{ width: '100%' }}
      />

      {dataPoints.filter(p => p.is_anomaly).length > 0 && (
        <Text size="sm" c="red" mt="xs">
          {dataPoints.filter(p => p.is_anomaly).length} anomaly(ies) detected (Z-score &gt; {anomalyThreshold})
        </Text>
      )}
    </Box>
  )
}
