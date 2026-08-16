# P1-52 TestCase LabProfile Binding Safety Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent a failed LabProfile list request from clearing an existing TestCase binding while preserving unrelated TestCase edits.

**Architecture:** Split TestCase detail loading from LabProfile option loading. A small pure policy helper decides whether the PATCH may carry `lab_profile_id`; the edit modal freezes the selector and surfaces a retryable error until the option list is authoritative.

**Tech Stack:** React 18, TypeScript, Mantine 8, Node test runner, Axios TestCase service.

---

### Task 1: Lock the PATCH omission contract

**Files:**
- Create: `gui/test/testCaseLabProfileBinding.test.ts`
- Create: `gui/src/features/TestManagement/testCaseLabProfileBinding.ts`

**Step 1: Write the failing tests**

Add Node tests for a pure `buildLabProfileBindingPatch()` helper:

```ts
assert.deepEqual(buildLabProfileBindingPatch({
  labsReady: false,
  originalLabProfileId: 'lab-a',
  selectedLabProfileId: null,
}), {})

assert.deepEqual(buildLabProfileBindingPatch({
  labsReady: true,
  originalLabProfileId: 'lab-a',
  selectedLabProfileId: null,
}), { lab_profile_id: null })
```

Also cover unchanged binding omission and explicit rebind to `lab-b`.

**Step 2: Run the test to verify RED**

Run:

```bash
cd gui && npx tsx --test test/testCaseLabProfileBinding.test.ts
```

Expected: FAIL because the module/helper does not exist.

**Step 3: Implement the minimal pure helper**

Create:

```ts
export function buildLabProfileBindingPatch(input: {
  labsReady: boolean
  originalLabProfileId: string | null
  selectedLabProfileId: string | null
}): { lab_profile_id?: string | null } {
  if (!input.labsReady || input.originalLabProfileId === input.selectedLabProfileId) {
    return {}
  }
  return { lab_profile_id: input.selectedLabProfileId }
}
```

**Step 4: Run the test to verify GREEN**

Run the same command. Expected: 4 passed.

**Step 5: Commit**

```bash
git add gui/src/features/TestManagement/testCaseLabProfileBinding.ts \
  gui/test/testCaseLabProfileBinding.test.ts
git commit -m "test: lock TestCase lab binding patch policy"
```

### Task 2: Make LabProfile loading explicit and retryable

**Files:**
- Modify: `gui/src/components/TestPlanManagement/TestCaseEditModal.tsx`
- Test: `gui/test/testCaseLabProfileBinding.test.ts`

**Step 1: Extend the failing policy test**

Add assertions for `labProfileSelectionDisabled({ labsLoading, labsError })`: loading and error are disabled; a successful empty list is enabled.

**Step 2: Run the focused test to verify RED**

Run the Node test. Expected: FAIL because the disabled-state helper does not exist.

**Step 3: Implement the state split**

- Add `labsLoading`, `labsError`, `labsReady`, `originalLabProfileId` and a request-generation ref.
- Load TestCase details independently; detail failure still closes the modal.
- Add `loadLabProfiles()` for initial load and retry. It must ignore stale responses after close/switch/retry.
- Never convert list failure into `[]` as a successful result.
- Disable the LabProfile Select during loading/error and show the backend/client error with a retry button.
- When the current binding is absent from the available options, add a disabled display-only option so the UI never appears unbound merely because the list is unavailable.

**Step 4: Use the PATCH policy**

Build the normal TestCase payload, then spread `buildLabProfileBindingPatch()` into it. Convert the UI sentinel to `null` only when calling the helper. This keeps `lab_profile_id` absent while the list is unavailable or the selection is unchanged.

**Step 5: Run focused tests and build**

```bash
cd gui
npx tsx --test test/testCaseLabProfileBinding.test.ts
npm run build
```

Expected: focused tests pass and production build exits 0.

**Step 6: Commit**

```bash
git add gui/src/components/TestPlanManagement/TestCaseEditModal.tsx \
  gui/src/features/TestManagement/testCaseLabProfileBinding.ts \
  gui/test/testCaseLabProfileBinding.test.ts
git commit -m "fix: preserve TestCase lab binding on list failure"
```

### Task 3: Close roadmap facts and verify the whole slice

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-16-p1-52-testcase-lab-profile-edit-safety-design.md` only if implementation facts differ.

**Step 1: Update roadmap mirrors**

Mark P1-52 as locally implemented/under review, remove the stale Discovered future promise, and set Current Focus to P1-52 until merge. Do not mark P1-53 current before P1-52 is merged.

**Step 2: Run relevant backend contract regression**

```bash
cd api-service
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_arch1_case_runner.py \
  tests/test_rule_gates.py \
  --no-header --tb=short
```

Expected: all selected tests pass.

**Step 3: Run final GUI and repository checks**

```bash
cd gui
npx tsx --test test/testCaseLabProfileBinding.test.ts
npm run build
cd ..
git diff --check
```

Expected: all commands exit 0.

**Step 4: Internal review**

Review the full LabProfile binding lifecycle: initial bound/unbound/inactive values, loading/error/retry, stale responses, explicit clear/rebind, unchanged save, and backend omitted-field semantics. Fix functional P1 findings with RED→GREEN until P1=0; record P2/P3 separately.

**Step 5: Commit roadmap closeout**

```bash
git add docs/roadmap-first-call.md \
  docs/plans/2026-08-16-p1-52-testcase-lab-profile-edit-safety-design.md
git commit -m "docs: close P1-52 implementation status"
```

### Task 4: Publish, review, and merge

**Step 1:** Push the branch, open a Ready PR, and request `@codex review`.

**Step 2:** Apply the two-round review rule exactly: R1 fixes then R2; R2 P1 tail fixes merge without R3.

**Step 3:** Merge with a merge commit after required checks and the applicable review gate pass.

**Step 4:** Verify `origin/main`, delete the P1-52 automation, and start P1-53 from the verified merge commit in a new isolated worktree.
