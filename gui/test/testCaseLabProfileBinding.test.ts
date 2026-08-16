import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildLabProfileBindingPatch,
  labProfileSelectionDisabled,
} from '../src/features/TestManagement/testCaseLabProfileBinding.ts'

test('omits lab binding while the option list is unavailable', () => {
  assert.deepEqual(
    buildLabProfileBindingPatch({
      labsReady: false,
      originalLabProfileId: 'lab-a',
      selectedLabProfileId: null,
    }),
    {},
  )
})

test('omits an unchanged lab binding', () => {
  assert.deepEqual(
    buildLabProfileBindingPatch({
      labsReady: true,
      originalLabProfileId: 'lab-a',
      selectedLabProfileId: 'lab-a',
    }),
    {},
  )
})

test('sends null only for an explicit clear with an authoritative option list', () => {
  assert.deepEqual(
    buildLabProfileBindingPatch({
      labsReady: true,
      originalLabProfileId: 'lab-a',
      selectedLabProfileId: null,
    }),
    { lab_profile_id: null },
  )
})

test('sends a new id only for an explicit rebind', () => {
  assert.deepEqual(
    buildLabProfileBindingPatch({
      labsReady: true,
      originalLabProfileId: 'lab-a',
      selectedLabProfileId: 'lab-b',
    }),
    { lab_profile_id: 'lab-b' },
  )
})

test('disables lab selection until the option list is authoritative', () => {
  assert.equal(
    labProfileSelectionDisabled({ labsLoading: true, labsError: null }),
    true,
  )
  assert.equal(
    labProfileSelectionDisabled({
      labsLoading: false,
      labsError: 'LabProfile 列表加载失败',
    }),
    true,
  )
  assert.equal(
    labProfileSelectionDisabled({ labsLoading: false, labsError: null }),
    false,
  )
})
