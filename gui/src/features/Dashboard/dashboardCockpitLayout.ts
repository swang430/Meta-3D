export type DashboardMainZone = 'recentExecutions' | 'liveLogs'

const MAIN_ZONES: readonly DashboardMainZone[] = [
  'recentExecutions',
  'liveLogs',
]

/** The cockpit's two operator-useful main panels, in display order. */
export function dashboardMainZones(): readonly DashboardMainZone[] {
  return MAIN_ZONES
}
