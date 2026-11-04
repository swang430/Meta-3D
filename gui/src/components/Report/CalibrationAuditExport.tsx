import { useMutation } from '@tanstack/react-query'
import { Alert, Button, Stack, Text } from '@mantine/core'
import { fetchCalibrationAudit } from '../../api/reportService'

export function CalibrationAuditExport({ reportId }: { reportId: string }) {
  const mutation = useMutation({
    mutationFn: () => fetchCalibrationAudit(reportId),
    onSuccess: (data) => {
      const url = URL.createObjectURL(new Blob([data], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `calibration-audit-${reportId}.json`
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
  })
  const error = mutation.error as (Error & { response?: { data?: { detail?: unknown } } }) | null
  const detail = error?.response?.data?.detail
  return <Stack gap="xs">
    <Button variant="light" loading={mutation.isPending} onClick={() => mutation.mutate()}>
      导出校准审计包（非正式报告）
    </Button>
    <Text size="xs" c="dimmed">保留原报告与关联采集原文；缺失材料保持未知，当前取回内容不等于历史防篡改证明。</Text>
    {error && <Alert color="red" title="审计包导出失败">{typeof detail === 'string' ? detail : error.message}</Alert>}
  </Stack>
}
