import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { commitThenActivateCategory } from './categoryHalActivation.ts'
import { diagnosticErrorMessage } from './diagnosticTarget.ts'

test('committed instrument write is followed by activation for the same category', async () => {
  const calls: string[] = []

  const result = await commitThenActivateCategory(
    'baseStation',
    async () => {
      calls.push('commit')
      return { key: 'baseStation' }
    },
    async (categoryKey) => {
      calls.push(`activate:${categoryKey}`)
      return {
        category_key: categoryKey,
        status: 'activated',
        driver_class: 'RealUxmDriver',
        instrument_id: 'baseStation_12345678',
        simulated: false,
        message: '已激活',
      }
    },
  )

  assert.deepEqual(calls, ['commit', 'activate:baseStation'])
  assert.equal(result.committed.key, 'baseStation')
  assert.equal(result.activation?.status, 'activated')
  assert.equal(result.activationError, undefined)
})

test('activation refusal preserves the successful committed write', async () => {
  const committed = { key: 'channelEmulator' }
  const activationFailure = new Error('instrument lease is active')

  const result = await commitThenActivateCategory(
    'channelEmulator',
    async () => committed,
    async () => {
      throw activationFailure
    },
  )

  assert.equal(result.committed, committed)
  assert.equal(result.activation, undefined)
  assert.equal(result.activationError, activationFailure)
})

test('failed committed write does not attempt HAL activation', async () => {
  let activationCalls = 0
  const saveFailure = new Error('save rejected')

  await assert.rejects(
    commitThenActivateCategory(
      'baseStation',
      async () => {
        throw saveFailure
      },
      async () => {
        activationCalls += 1
        throw new Error('must not run')
      },
    ),
    saveFailure,
  )
  assert.equal(activationCalls, 0)
})

test('equipment saves and driver-mode writes both use commit-then-activate orchestration', () => {
  const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
  const saveMutation = app.slice(
    app.indexOf('const instrumentMutation'),
    app.indexOf('const siteCertificationMutation'),
  )
  const driverModeControl = app.slice(
    app.indexOf('value={(category as any).driverMode'),
    app.indexOf('<Switch', app.indexOf('value={(category as any).driverMode')),
  )

  assert.match(saveMutation, /commitThenActivateCategory\(/)
  assert.match(saveMutation, /activationError/)
  assert.match(
    saveMutation,
    /invalidateQueries\(\{ queryKey: \['instruments', 'catalog'\] \}\)/,
  )
  assert.match(driverModeControl, /commitThenActivateCategory\(/)
  assert.doesNotMatch(saveMutation, /请点击页面顶部「↻ 重新加载驱动」/)
  assert.doesNotMatch(app, /改完仪器配置后必须点这个/)
})

test('lab setup wizard activates every saved category before advancing', () => {
  const wizard = readFileSync(
    new URL('../../components/LabProfile/LabProfileWizard.tsx', import.meta.url),
    'utf8',
  )
  const updateMutation = wizard.slice(
    wizard.indexOf('const updateCategoryMutation'),
    wizard.indexOf('const createMutation'),
  )
  const step2Next = wizard.slice(
    wizard.indexOf('const onStep2Next'),
    wizard.indexOf('// ---- Step 3 actions'),
  )

  assert.match(updateMutation, /commitThenActivateCategory\(/)
  assert.match(updateMutation, /activateInstrumentCategoryHAL/)
  assert.match(step2Next, /activationError/)
  assert.ok(
    step2Next.indexOf('activationError') < step2Next.indexOf('active: 2'),
    'activation failure must be handled before the wizard advances',
  )
})

test('lab setup wizard persists the selected driver mode before activation', () => {
  const wizard = readFileSync(
    new URL('../../components/LabProfile/LabProfileWizard.tsx', import.meta.url),
    'utf8',
  )
  const updateMutation = wizard.slice(
    wizard.indexOf('const updateCategoryMutation'),
    wizard.indexOf('const createMutation'),
  )
  const step2Next = wizard.slice(
    wizard.indexOf('const onStep2Next'),
    wizard.indexOf('// ---- Step 3 actions'),
  )

  assert.match(updateMutation, /driverMode: DriverMode/)
  assert.match(updateMutation, /\/driver-mode/)
  assert.match(updateMutation, /mode: driverMode/)
  assert.ok(
    updateMutation.indexOf('/driver-mode') <
      updateMutation.indexOf('activateInstrumentCategoryHAL'),
    'driver mode must be committed before category activation',
  )
  assert.match(step2Next, /driverMode: b\.driverMode/)
})

test('lab setup wizard seeds driver mode from the persisted catalog truth', () => {
  const wizard = readFileSync(
    new URL('../../components/LabProfile/LabProfileWizard.tsx', import.meta.url),
    'utf8',
  )
  const bindingSeed = wizard.slice(
    wizard.indexOf('const seeded: BindingDraft[]'),
    wizard.indexOf('setState((s) => ({ ...s, bindings: seeded }))'),
  )

  assert.match(bindingSeed, /driverMode: cat\.driverMode/)
  assert.doesNotMatch(bindingSeed, /driverMode: ['"]auto['"]/)
})

test('lab setup wizard invalidates pre-mode-source v1 drafts', () => {
  const wizard = readFileSync(
    new URL('../../components/LabProfile/LabProfileWizard.tsx', import.meta.url),
    'utf8',
  )
  const persistence = wizard.slice(
    wizard.indexOf('const LEGACY_WIZARD_STORAGE_KEY'),
    wizard.indexOf('interface LabProfileWizardProps'),
  )

  assert.match(persistence, /LEGACY_WIZARD_STORAGE_KEY = ['"]mimo-first-lab-wizard-state-v1['"]/)
  assert.match(persistence, /WIZARD_STORAGE_KEY = ['"]mimo-first-lab-wizard-state-v2['"]/)
  assert.match(persistence, /localStorage\.removeItem\(LEGACY_WIZARD_STORAGE_KEY\)/)
  assert.match(persistence, /localStorage\.getItem\(WIZARD_STORAGE_KEY\)/)
  assert.doesNotMatch(persistence, /localStorage\.getItem\(LEGACY_WIZARD_STORAGE_KEY\)/)
})

test('automatic category activation remains separate from LabProfile sync', () => {
  const helper = readFileSync(new URL('./categoryHalActivation.ts', import.meta.url), 'utf8')

  assert.doesNotMatch(helper, /syncCurrentInstrumentBinding|LabProfile|sync-current/)
})

test('activation refusal exposes the execution or lease blocker reason', () => {
  const message = diagnosticErrorMessage({
    message: 'Request failed with status code 409',
    response: {
      data: {
        reason: 'HAL category activation refused: 1 active blocker(s).',
        blockers: [
          {
            kind: 'execution',
            name: '暗室首测',
            status: 'running',
            detail: 'execution is still active',
          },
        ],
      },
    },
  })

  assert.match(message, /HAL category activation refused/)
  assert.match(message, /暗室首测/)
  assert.match(message, /execution is still active/)
})
