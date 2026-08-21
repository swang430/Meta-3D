import type {
  DiagnosticRunDetail,
  SequenceRunResponse,
} from '../../api/diagnosticService'


export type DiagnosticSequenceEvidenceView =
  | { kind: 'complete'; result: SequenceRunResponse }
  | { kind: 'legacy'; notice: string; excerpt: string | null }


export interface DiagnosticSequenceVerdictView {
  label: 'success' | 'failure' | 'undetermined' | 'blocker' | 'aborted'
  color: 'green' | 'orange' | 'yellow' | 'red'
  notificationTitle: string
}


export function sequenceVerdictView(
  result: Pick<SequenceRunResponse, 'success' | 'extra'>,
): DiagnosticSequenceVerdictView {
  switch (result.extra.verdict) {
    case 'SUCCESS':
      return result.success
        ? { label: 'success', color: 'green', notificationTitle: '序列执行成功' }
        : { label: 'failure', color: 'orange', notificationTitle: '序列报告失败' }
    case 'UNDETERMINED':
      return { label: 'undetermined', color: 'yellow', notificationTitle: '序列结果未判定' }
    case 'BLOCKER':
      return { label: 'blocker', color: 'red', notificationTitle: '序列存在阻塞项' }
    case 'ABORTED':
      return { label: 'aborted', color: 'orange', notificationTitle: '序列已中止' }
    default:
      return result.success
        ? { label: 'success', color: 'green', notificationTitle: '序列执行成功' }
        : { label: 'failure', color: 'orange', notificationTitle: '序列报告失败' }
  }
}


export function evidenceViewFromDiagnosticRun(
  run: DiagnosticRunDetail,
): DiagnosticSequenceEvidenceView {
  if (!run.sequence_evidence) {
    return {
      kind: 'legacy',
      notice: '旧记录未持久化完整证据',
      excerpt: run.output_excerpt ?? null,
    }
  }

  return {
    kind: 'complete',
    result: {
      diagnostic_run_id: run.id,
      success: run.success,
      ...run.sequence_evidence,
    },
  }
}
