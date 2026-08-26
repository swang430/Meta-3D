export type BaseStationPortRole = 'dl' | 'ul'

export interface BaseStationPortParams {
  ports?: string[]
  port_roles?: Record<string, BaseStationPortRole>
  physical_port_display?: Record<string, string>
}

export interface ResolvedPortHandle {
  id: string
  role: BaseStationPortRole
  handleType: 'source' | 'target'
  physicalPort?: string
}

export const resolvePortHandles = (
  params: BaseStationPortParams = {},
): ResolvedPortHandle[] => (params.ports ?? []).flatMap((id) => {
  const role = params.port_roles?.[id]
  if (role !== 'dl' && role !== 'ul') return []
  const physicalPort = params.physical_port_display?.[id]
  return [{
    id,
    role,
    handleType: role === 'ul' ? 'target' : 'source',
    ...(physicalPort ? { physicalPort } : {}),
  }]
})

export const formatPortLabel = (port: ResolvedPortHandle): string => (
  port.physicalPort ? `${port.id} → ${port.physicalPort}` : port.id
)
