export type DiagnosticTarget = {
  payload?: { ip?: string; port?: number }
  error?: string
}

export function diagnosticErrorMessage(error: unknown): string {
  const candidate = error as {
    message?: string
    response?: {
      data?: {
        detail?: unknown
        reason?: unknown
        blockers?: unknown
      }
    }
  }
  const data = candidate?.response?.data
  const detail = data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  const reason = data?.reason
  if (typeof reason === 'string' && reason.trim()) {
    const blockers = Array.isArray(data?.blockers)
      ? data.blockers.flatMap((raw) => {
          if (raw === null || typeof raw !== 'object') return []
          const blocker = raw as Record<string, unknown>
          const parts = ['name', 'kind', 'status', 'detail'].flatMap((key) => {
            const value = blocker[key]
            return typeof value === 'string' && value.trim() ? [value.trim()] : []
          })
          return parts.length ? [parts.join(' / ')] : []
        })
      : []
    return blockers.length
      ? `${reason.trim()}：${blockers.join('；')}`
      : reason.trim()
  }
  if (typeof candidate?.message === 'string' && candidate.message.trim()) {
    return candidate.message
  }
  return '未知错误'
}

export function parseEndpointToIpPort(
  endpoint: string,
): { ip?: string; port?: number } {
  const ep = endpoint.trim()
  if (!ep) return {}

  if (ep.toUpperCase().startsWith('TCPIP')) {
    const parts = ep.split('::')
    if (parts.length < 2) return {}
    const ip = parts[1].trim()
    const parsedPort = parts.length >= 3
      ? Number.parseInt(parts[2].trim(), 10)
      : Number.NaN
    const port = Number.isInteger(parsedPort) && parsedPort > 0 && parsedPort < 65536
      ? parsedPort
      : undefined
    return { ip, port }
  }

  if (ep.includes(':')) {
    const lastColon = ep.lastIndexOf(':')
    const host = ep.slice(0, lastColon).trim()
    const parsedPort = Number.parseInt(ep.slice(lastColon + 1).trim(), 10)
    if (Number.isInteger(parsedPort) && parsedPort > 0 && parsedPort < 65536) {
      return { ip: host, port: parsedPort }
    }
    return { ip: ep }
  }

  return { ip: ep }
}

export function buildDiagnosticTarget(
  categoryKey: string,
  draftEndpoint: string,
  savedEndpoint: string,
): DiagnosticTarget {
  const singleSession = categoryKey === 'baseStation' || categoryKey === 'channelEmulator'
  if (singleSession) {
    if (draftEndpoint.trim() !== savedEndpoint.trim()) {
      return {
        error: '单会话仪表地址已修改；请先保存配置并重新加载 HAL',
      }
    }
    return { payload: {} }
  }
  return { payload: parseEndpointToIpPort(draftEndpoint) }
}
