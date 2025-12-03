import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { Box, Title, Text, Group, Badge, Stack } from '@mantine/core'

export interface MetricStatistics {
  metric_name: string
  mean: number
  median: number
  std: number
  min: number
  max: number
  range: number
  count: number
  percentiles?: Record<string, number>
  confidence_interval?: { lower: number; upper: number }
}

export interface ComparisonResult {
  metric_name: string
  report_statistics: Record<string, MetricStatistics>
  overall_mean: number
  overall_std: number
  coefficient_of_variation: number
  significant_differences?: Array<Record<string, any>>
}

interface Props {
  title: string
  comparisonResults: ComparisonResult[]
  reportIds: string[]
  reportNames?: Record<string, string>  // Optional mapping of report IDs to display names
  height?: number
  chartType?: 'box' | 'bar' | 'violin'
}

export default function StatisticsComparisonChart({
  title,
  comparisonResults,
  reportIds,
  reportNames,
  height = 600,
  chartType = 'box'
}: Props) {
  const plotData = useMemo(() => {
    if (!comparisonResults || comparisonResults.length === 0) {
      return []
    }

    const traces: Plotly.Data[] = []
    const colors = ['#228be6', '#40c057', '#fa5252', '#fd7e14', '#7950f2', '#f783ac']

    // Group by metric
    comparisonResults.forEach((result, metricIndex) => {
      reportIds.forEach((reportId, reportIndex) => {
        const stats = result.report_statistics[reportId]
        if (!stats) return

        const reportName = reportNames?.[reportId] || `Report ${reportIndex + 1}`
        const color = colors[reportIndex % colors.length]

        if (chartType === 'box') {
          // Box plot showing distribution
          traces.push({
            y: [stats.min, stats.percentiles?.['25'], stats.median, stats.percentiles?.['75'], stats.max].filter(v => v !== undefined),
            type: 'box',
            name: reportName,
            marker: { color },
            boxmean: 'sd',
            legendgroup: reportName,
            showlegend: metricIndex === 0,
            xaxis: `x${metricIndex + 1}`,
            yaxis: `y${metricIndex + 1}`,
            hovertemplate: `<b>${reportName}</b><br>` +
                           `Metric: ${result.metric_name}<br>` +
                           `Min: ${stats.min.toFixed(2)}<br>` +
                           `Q1: ${stats.percentiles?.['25']?.toFixed(2)}<br>` +
                           `Median: ${stats.median.toFixed(2)}<br>` +
                           `Q3: ${stats.percentiles?.['75']?.toFixed(2)}<br>` +
                           `Max: ${stats.max.toFixed(2)}<br>` +
                           `Mean: ${stats.mean.toFixed(2)}<br>` +
                           `Std: ${stats.std.toFixed(2)}<br>` +
                           '<extra></extra>'
          })
        } else if (chartType === 'bar') {
          // Bar chart with error bars
          traces.push({
            x: [result.metric_name],
            y: [stats.mean],
            type: 'bar',
            name: reportName,
            marker: { color },
            error_y: {
              type: 'data',
              array: [stats.std],
              visible: true,
              color: color
            },
            legendgroup: reportName,
            showlegend: metricIndex === 0,
            hovertemplate: `<b>${reportName}</b><br>` +
                           `${result.metric_name}<br>` +
                           `Mean: ${stats.mean.toFixed(2)} ± ${stats.std.toFixed(2)}<br>` +
                           `Range: [${stats.min.toFixed(2)}, ${stats.max.toFixed(2)}]<br>` +
                           `Count: ${stats.count}<br>` +
                           '<extra></extra>'
          })
        }
      })
    })

    return traces
  }, [comparisonResults, reportIds, reportNames, chartType])

  // Create subplot layout for multiple metrics
  const layout: Partial<Plotly.Layout> = useMemo(() => {
    const numMetrics = comparisonResults.length
    const rows = Math.ceil(numMetrics / 2)
    const cols = Math.min(numMetrics, 2)

    const baseLayout: Partial<Plotly.Layout> = {
      title: undefined,
      showlegend: true,
      legend: {
        orientation: 'h',
        yanchor: 'bottom',
        y: 1.02,
        xanchor: 'right',
        x: 1
      },
      height,
      margin: { l: 60, r: 40, t: 40, b: 100 },
      plot_bgcolor: '#ffffff',
      paper_bgcolor: '#ffffff',
      hovermode: 'closest'
    }

    if (chartType === 'box' && numMetrics > 1) {
      // Create grid layout for box plots
      const grid: any = {
        rows,
        columns: cols,
        pattern: 'independent',
        roworder: 'top to bottom'
      }
      baseLayout.grid = grid

      // Configure axes for each subplot
      comparisonResults.forEach((result, index) => {
        const axisNum = index + 1
        const xaxis = `xaxis${axisNum === 1 ? '' : axisNum}`
        const yaxis = `yaxis${axisNum === 1 ? '' : axisNum}`

        baseLayout[xaxis] = {
          title: result.metric_name,
          showgrid: false
        }
        baseLayout[yaxis] = {
          title: 'Value',
          showgrid: true,
          gridcolor: '#e9ecef'
        }
      })
    } else if (chartType === 'bar') {
      baseLayout.barmode = 'group'
      baseLayout.xaxis = {
        title: 'Metrics',
        showgrid: false
      }
      baseLayout.yaxis = {
        title: 'Mean Value',
        showgrid: true,
        gridcolor: '#e9ecef'
      }
    }

    return baseLayout
  }, [comparisonResults, chartType, height])

  const config: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
    displaylogo: false
  }

  // Calculate summary statistics
  const summaryStats = useMemo(() => {
    if (!comparisonResults || comparisonResults.length === 0) return null

    return comparisonResults.map(result => ({
      metric: result.metric_name,
      overallMean: result.overall_mean,
      overallStd: result.overall_std,
      cv: result.coefficient_of_variation,
      variability: result.coefficient_of_variation < 10 ? 'Low' :
                   result.coefficient_of_variation < 25 ? 'Moderate' : 'High'
    }))
  }, [comparisonResults])

  return (
    <Box>
      <Title order={4} mb="md">{title}</Title>

      <Plot
        data={plotData}
        layout={layout}
        config={config}
        style={{ width: '100%' }}
      />

      {summaryStats && summaryStats.length > 0 && (
        <Stack gap="xs" mt="md">
          <Text size="sm" fw={600}>Summary Statistics:</Text>
          {summaryStats.map((stat, i) => (
            <Group key={i} gap="md">
              <Text size="sm" w={150}>{stat.metric}:</Text>
              <Text size="sm">
                Mean = {stat.overallMean.toFixed(2)} ± {stat.overallStd.toFixed(2)}
              </Text>
              <Badge
                color={stat.variability === 'Low' ? 'green' :
                       stat.variability === 'Moderate' ? 'yellow' : 'red'}
                variant="light"
                size="sm"
              >
                CV = {stat.cv.toFixed(1)}% ({stat.variability} Variability)
              </Badge>
            </Group>
          ))}
        </Stack>
      )}
    </Box>
  )
}
