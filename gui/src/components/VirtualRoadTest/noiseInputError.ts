import { isAxiosError } from 'axios'

export function noiseInputError(e: unknown): string {
  const detail = isAxiosError(e) ? e.response?.data?.detail : undefined
  const reasons = Array.isArray(detail) ? detail.flatMap(issue => {
    if (typeof issue?.msg !== 'string') return []
    const location = Array.isArray(issue.loc) ? issue.loc.filter((part: unknown) => part !== 'body').join('.') : ''
    return [location ? `${location}：${issue.msg}` : issue.msg]
  }).join('；') : ''
  return (typeof detail === 'string' && detail.trim()) || reasons ||
    (e instanceof Error ? e.message : '无法读取仿真文件')
}
