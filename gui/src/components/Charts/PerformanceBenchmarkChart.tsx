import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { Box, Title, Text, Group, Badge, Stack, Progress } from '@mantine/core'
import { IconTrophy, IconMedal, IconAward } from '@tabler/icons-react'

export interface BenchmarkMetric {
  metric_name: string
  value: number
  percentile_rank: number
  performance_rating: 'excellent' | 'good' | 'average' | 'below_average' | 'poor'
  reference_mean: number
  reference_std: number
  z_score: number
}

interface Props {
  title: string
  benchmarkMetrics: BenchmarkMetric[]
  overallPercentile: number
  overallRating: string
  summary?: string
  height?: number
}

const getRatingColor = (rating: string): string => {
  switch (rating) {
    case 'excellent': return '#40c057'
    case 'good': return '#12b886'
    case 'average': return '#fd7e14'
    case 'below_average': return '#fa5252'
    case 'poor': return '#c92a2a'
    default: return '#868e96'
  }
}

const getRatingIcon = (rating: string) => {
  switch (rating) {
    case 'excellent': return <IconTrophy size={20} color="#40c057" />
    case 'good': return <IconMedal size={20} color="#12b886" />
    case 'average': return <IconAward size={20} color="#fd7e14" />
    default: return null
  }
}

export default function PerformanceBenchmarkChart({
  title,
  benchmarkMetrics,
  overallPercentile,
  overallRating,
  summary,
  height = 500
}: Props) {
  const plotData = useMemo(() => {
    if (!benchmarkMetrics || benchmarkMetrics.length === 0) {
      return []
    }

    const traces: Plotly.Data[] = []

    // Percentile rank bar chart
    const metricNames = benchmarkMetrics.map(m => m.metric_name)
    const percentiles = benchmarkMetrics.map(m => m.percentile_rank)
    const colors = benchmarkMetrics.map(m => getRatingColor(m.performance_rating))

    traces.push({
      x: percentiles,
      y: metricNames,
      type: 'bar',
      orientation: 'h',
      marker: {
        color: colors,
        line: { color: '#fff', width: 1 }
      },
      text: percentiles.map(p => `${p.toFixed(1)}%`),
      textposition: 'outside',
      hovertemplate: '<b>%{y}</b><br>' +
                     'Percentile: %{x:.1f}%<br>' +
                     '<extra></extra>'
    })

    // Reference lines for performance thresholds
    const referenceShapes: Partial<Plotly.Shape>[] = [
      // Excellent threshold (90%)
      {
        type: 'line',
        x0: 90, x1: 90,
        y0: -0.5, y1: metricNames.length - 0.5,
        line: { color: '#40c057', width: 2, dash: 'dash' }
      },
      // Good threshold (70%)
      {
        type: 'line',
        x0: 70, x1: 70,
        y0: -0.5, y1: metricNames.length - 0.5,
        line: { color: '#12b886', width: 2, dash: 'dash' }
      },
      // Average threshold (40%)
      {
        type: 'line',
        x0: 40, x1: 40,
        y0: -0.5, y1: metricNames.length - 0.5,
        line: { color: '#fd7e14', width: 2, dash: 'dash' }
      }
    ]

    return { traces, shapes: referenceShapes }
  }, [benchmarkMetrics])

  const layout: Partial<Plotly.Layout> = {
    title: undefined,
    xaxis: {
      title: 'Percentile Rank (%)',
      range: [0, 105],
      showgrid: true,
      gridcolor: '#e9ecef'
    },
    yaxis: {
      title: '',
      automargin: true
    },
    showlegend: false,
    margin: { l: 150, r: 60, t: 20, b: 60 },
    plot_bgcolor: '#ffffff',
    paper_bgcolor: '#ffffff',
    shapes: plotData.shapes,
    annotations: [
      {
        x: 90, y: benchmarkMetrics.length,
        text: 'Excellent',
        showarrow: false,
        xanchor: 'center',
        yanchor: 'bottom',
        font: { size: 10, color: '#40c057' }
      },
      {
        x: 70, y: benchmarkMetrics.length,
        text: 'Good',
        showarrow: false,
        xanchor: 'center',
        yanchor: 'bottom',
        font: { size: 10, color: '#12b886' }
      },
      {
        x: 40, y: benchmarkMetrics.length,
        text: 'Average',
        showarrow: false,
        xanchor: 'center',
        yanchor: 'bottom',
        font: { size: 10, color: '#fd7e14' }
      }
    ]
  }

  const config: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d', 'pan2d'],
    displaylogo: false
  }

  return (
    <Box>
      <Group justify="space-between" mb="md">
        <Title order={4}>{title}</Title>
        <Group gap="xs">
          {getRatingIcon(overallRating)}
          <Badge
            size="lg"
            color={getRatingColor(overallRating)}
            variant="filled"
          >
            {overallRating.toUpperCase()}
          </Badge>
          <Text size="sm" fw={600}>
            {overallPercentile.toFixed(1)}th Percentile
          </Text>
        </Group>
      </Group>

      {summary && (
        <Text size="sm" c="dimmed" mb="md">
          {summary}
        </Text>
      )}

      <Plot
        data={plotData.traces}
        layout={{ ...layout, height }}
        config={config}
        style={{ width: '100%' }}
      />

      <Stack gap="md" mt="md">
        <Text size="sm" fw={600}>Performance Breakdown:</Text>
        {benchmarkMetrics.map((metric, i) => (
          <Box key={i}>
            <Group justify="space-between" mb={4}>
              <Text size="sm">{metric.metric_name}</Text>
              <Group gap="xs">
                <Badge
                  size="sm"
                  color={getRatingColor(metric.performance_rating)}
                  variant="light"
                >
                  {metric.performance_rating}
                </Badge>
                <Text size="xs" c="dimmed">
                  {metric.percentile_rank.toFixed(1)}%
                </Text>
              </Group>
            </Group>
            <Progress
              value={metric.percentile_rank}
              color={getRatingColor(metric.performance_rating)}
              size="sm"
            />
            <Group justify="space-between" mt={4}>
              <Text size="xs" c="dimmed">
                Value: {metric.value.toFixed(2)}
              </Text>
              <Text size="xs" c="dimmed">
                Z-score: {metric.z_score.toFixed(2)}
              </Text>
              <Text size="xs" c="dimmed">
                Ref: {metric.reference_mean.toFixed(2)} ± {metric.reference_std.toFixed(2)}
              </Text>
            </Group>
          </Box>
        ))}
      </Stack>
    </Box>
  )
}
