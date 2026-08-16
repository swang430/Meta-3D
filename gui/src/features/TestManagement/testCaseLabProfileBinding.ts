export interface LabProfileBindingPatchInput {
  labsReady: boolean
  originalLabProfileId: string | null
  selectedLabProfileId: string | null
}

export function buildLabProfileBindingPatch({
  labsReady,
  originalLabProfileId,
  selectedLabProfileId,
}: LabProfileBindingPatchInput): { lab_profile_id?: string | null } {
  if (!labsReady || originalLabProfileId === selectedLabProfileId) {
    return {}
  }
  return { lab_profile_id: selectedLabProfileId }
}

export function labProfileSelectionDisabled({
  labsLoading,
  labsError,
}: {
  labsLoading: boolean
  labsError: string | null
}): boolean {
  return labsLoading || labsError !== null
}
