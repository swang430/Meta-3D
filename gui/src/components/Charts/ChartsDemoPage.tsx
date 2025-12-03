import { Container, Title, Stack, Divider } from '@mantine/core'
import {
  TimeSeriesChart,
  StatisticsComparisonChart,
  PerformanceBenchmarkChart,
  type TimeSeriesDataPoint,
  type TrendData,
  type ComparisonResult,
  type BenchmarkMetric
} from './index'

// Mock data for demonstrations
const generateMockTimeSeriesData = (): {
  dataPoints: TimeSeriesDataPoint[]
  trend: TrendData
  rollingMean: number[]
  rollingStd: number[]
} => {
  const now = new Date()
  const dataPoints: TimeSeriesDataPoint[] = []
  const values: number[] = []

  // Generate 30 data points over 30 days
  for (let i = 0; i < 30; i++) {
    const timestamp = new Date(now.getTime() - (29 - i) * 24 * 60 * 60 * 1000)
    const baseValue = 500
    const trend = i * 2 // Slight upward trend
    const noise = (Math.random() - 0.5) * 50
    const anomaly = [10, 20].includes(i) ? 150 : 0 // Add anomalies at days 10 and 20
    const value = baseValue + trend + noise + anomaly

    values.push(value)
    dataPoints.push({
      timestamp: timestamp.toISOString(),
      value,
      execution_id: `exec-${i}`,
      is_anomaly: anomaly !== 0,
      z_score: anomaly !== 0 ? 4.5 : Math.abs(noise / 50)
    })
  }

  // Calculate rolling mean and std
  const windowSize = 5
  const rollingMean: number[] = []
  const rollingStd: number[] = []

  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - windowSize + 1)
    const window = values.slice(start, i + 1)
    const mean = window.reduce((a, b) => a + b, 0) / window.length
    const variance = window.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / window.length
    const std = Math.sqrt(variance)

    rollingMean.push(mean)
    rollingStd.push(std)
  }

  const trend: TrendData = {
    direction: 'increasing',
    slope: 2.0,
    r_squared: 0.85,
    strength: 'strong'
  }

  return { dataPoints, trend, rollingMean, rollingStd }
}

const generateMockComparisonData = (): {
  comparisonResults: ComparisonResult[]
  reportIds: string[]
} => {
  const reportIds = ['report-1', 'report-2', 'report-3']
  const metrics = ['throughput_mbps', 'latency_ms', 'packet_loss_percent']

  const comparisonResults: ComparisonResult[] = metrics.map(metric => {
    const baseMean = metric === 'throughput_mbps' ? 500 :
                     metric === 'latency_ms' ? 50 : 1.5

    const report_statistics: Record<string, any> = {}
    reportIds.forEach((id, i) => {
      const offset = (i - 1) * baseMean * 0.1
      report_statistics[id] = {
        metric_name: metric,
        mean: baseMean + offset,
        median: baseMean + offset - 5,
        std: baseMean * 0.15,
        min: baseMean + offset - baseMean * 0.3,
        max: baseMean + offset + baseMean * 0.3,
        range: baseMean * 0.6,
        count: 100,
        percentiles: {
          '25': baseMean + offset - baseMean * 0.15,
          '50': baseMean + offset - 5,
          '75': baseMean + offset + baseMean * 0.15,
          '90': baseMean + offset + baseMean * 0.25,
          '95': baseMean + offset + baseMean * 0.28
        },
        confidence_interval: {
          lower: baseMean + offset - baseMean * 0.05,
          upper: baseMean + offset + baseMean * 0.05
        }
      }
    })

    return {
      metric_name: metric,
      report_statistics,
      overall_mean: baseMean,
      overall_std: baseMean * 0.15,
      coefficient_of_variation: 15.0,
      significant_differences: []
    }
  })

  return { comparisonResults, reportIds }
}

const generateMockBenchmarkData = (): {
  benchmarkMetrics: BenchmarkMetric[]
  overallPercentile: number
  overallRating: string
  summary: string
} => {
  const benchmarkMetrics: BenchmarkMetric[] = [
    {
      metric_name: 'throughput_mbps',
      value: 520,
      percentile_rank: 85,
      performance_rating: 'good',
      reference_mean: 500,
      reference_std: 50,
      z_score: 0.4
    },
    {
      metric_name: 'latency_ms',
      value: 42,
      percentile_rank: 92,
      performance_rating: 'excellent',
      reference_mean: 50,
      reference_std: 8,
      z_score: -1.0
    },
    {
      metric_name: 'packet_loss_percent',
      value: 0.8,
      percentile_rank: 95,
      performance_rating: 'excellent',
      reference_mean: 1.5,
      reference_std: 0.5,
      z_score: -1.4
    },
    {
      metric_name: 'rsrp_dbm',
      value: -75,
      percentile_rank: 78,
      performance_rating: 'good',
      reference_mean: -80,
      reference_std: 5,
      z_score: 1.0
    },
    {
      metric_name: 'sinr_db',
      value: 18,
      percentile_rank: 88,
      performance_rating: 'good',
      reference_mean: 15,
      reference_std: 3,
      z_score: 1.0
    }
  ]

  return {
    benchmarkMetrics,
    overallPercentile: 87.6,
    overallRating: 'good',
    summary: 'Report performs at 87.6th percentile across 5 metrics, rated as \'good\' compared to 50 reference reports.'
  }
}

export default function ChartsDemoPage() {
  const timeSeriesData = generateMockTimeSeriesData()
  const comparisonData = generateMockComparisonData()
  const benchmarkData = generateMockBenchmarkData()

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <Title order={2}>Advanced Charts Demo - Plotly.js Integration</Title>

        <Divider label="Time Series Analysis" labelPosition="center" />
        <TimeSeriesChart
          title="Throughput Over Time with Anomaly Detection"
          metricName="Throughput (Mbps)"
          dataPoints={timeSeriesData.dataPoints}
          trend={timeSeriesData.trend}
          rollingMean={timeSeriesData.rollingMean}
          rollingStd={timeSeriesData.rollingStd}
          anomalyThreshold={3.0}
        />

        <Divider label="Statistics Comparison" labelPosition="center" />
        <StatisticsComparisonChart
          title="Multi-Report Metrics Comparison (Box Plot)"
          comparisonResults={comparisonData.comparisonResults}
          reportIds={comparisonData.reportIds}
          reportNames={{
            'report-1': 'Baseline Test',
            'report-2': 'Optimized Config',
            'report-3': 'Field Test'
          }}
          chartType="box"
        />

        <StatisticsComparisonChart
          title="Multi-Report Metrics Comparison (Bar Chart)"
          comparisonResults={comparisonData.comparisonResults}
          reportIds={comparisonData.reportIds}
          reportNames={{
            'report-1': 'Baseline Test',
            'report-2': 'Optimized Config',
            'report-3': 'Field Test'
          }}
          chartType="bar"
          height={400}
        />

        <Divider label="Performance Benchmarking" labelPosition="center" />
        <PerformanceBenchmarkChart
          title="Performance Benchmark vs. Reference Data"
          benchmarkMetrics={benchmarkData.benchmarkMetrics}
          overallPercentile={benchmarkData.overallPercentile}
          overallRating={benchmarkData.overallRating}
          summary={benchmarkData.summary}
        />
      </Stack>
    </Container>
  )
}
