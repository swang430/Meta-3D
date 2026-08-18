import type {
  DiagnosticRunDetail,
  SequenceRunResponse,
} from '../../api/diagnosticService'


export type DiagnosticSequenceEvidenceView =
  | { kind: 'complete'; result: SequenceRunResponse }
  | { kind: 'legacy'; summary: string }


export function evidenceViewFromDiagnosticRun(
  run: DiagnosticRunDetail,
): DiagnosticSequenceEvidenceView {
  if (!run.sequence_evidence) {
    return {
      kind: 'legacy',
      summary: '旧记录未持久化完整证据',
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
