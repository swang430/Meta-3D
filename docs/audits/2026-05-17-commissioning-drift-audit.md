# Commissioning Sandbox Drift Audit — 2026-05-17

> **Audit scope**: 暗室首测 (Commissioning Sandbox) workflow, baseline `988cc40` (2026-05-15, PR #19 "mock-data first-call generates real PDF") → HEAD `4f1a7e6` (2026-05-17, post-PFS investigation).
>
> **Why this audit**: After CAICT 2026-05-12/13 on-site trip, 50+ PRs have landed touching commissioning's transitive dependencies (alembic migrations, lab profile model, chamber config, UXM topology profile, capability registry, HAL refactors). User wanted verification that the post-trip optimization didn't drift commissioning's end-to-end behavior before next on-site.
>
> **Audit type**: out-of-roadmap audit, no fixes applied; findings flagged for future PRs / on-site smoke checks.
>
> **Confidence**: **MEDIUM-HIGH (75-80%)** end-to-end workflow still functions on dev server. 2 yellow flags found via live smoke; 4 additional yellow flags inherited from static-read pass that need UI click to confirm.

---

## TL;DR

| Severity | Count | What |
|---|---|---|
| 🔴 Red flag (broken) | **0** | None found. No endpoint signature breakage, no model field removal regression, no broken FK. |
| 🟡 Yellow flag (smoke confirmed via live API) | **2** | Lab validation tightened past seed-data shape (Y1); `mimo_test` result field naming engine-specific but appears in both modes (Y2) |
| 🟡 Yellow flag (inherited from static read, needs GUI smoke) | **4** | Engine-mode switching after session lock (Y3); reference_wait alias UX expectation (Y4); topology profile soft-fail on greenfield (Y5); ambiguity picker no-op narrow case (Y6) |
| 🟢 Notable change (worth knowing) | **4** | PR #27 422 mapper; dual-engine dispatch correctness; PDF generation path with legacy copy; TestCase→TestExecution decomposition |
| ❓ Need live GUI click | **2** | Multi-lab ambiguity 422 picker render; engine-mode swap mid-session UX |

**Recommendation before next on-site**:
1. Spend ~30 min doing the 4 inherited yellow flags' GUI smokes
2. Fix Y1 (lab validation vs seed mismatch) before any operator hits "edit lab" — small fix, ~30 min
3. Decide on Y2 (engine-specific field naming) — either rename `asc_files_loaded` to generic `synthesis_output_loaded` OR clamp it to actually be ASC-only — ~30 min either way
4. Y3-Y6 can ride along to on-site for visual verification

---

## Baseline + Diff Surface

- **Baseline**: `988cc40` (2026-05-15) "fix(commissioning)+test(p0-6): mock-data first-call generates real PDF (#19)"
- **HEAD**: `4f1a7e6` (2026-05-17) main after PR #52 merge
- **Span**: 30+ PRs, 19 files in commissioning's blast radius
- **Stat**: +2855 / -264 lines across the audit surface

### PRs directly touching commissioning files

| PR | Date | What |
|---|---|---|
| #19 | 2026-05-15 | **(baseline)** P0-6 mock-data first-call → real PDF |
| #27 | 2026-05-16 | fix(commissioning): 422 picker for ambiguous LabProfile (was 500) |

### PRs touching commissioning's transitive dependencies

| PR | Family | Impact axis |
|---|---|---|
| #22 / #24 / #25 | P1-1 pre-flight | New `/preflight` endpoint + driver capability gating; commissioning is parallel flow, not affected directly |
| #28 | P2-3 | Per-Model static `model_capabilities` + catalog surface (catalog drives commissioning's instrument readout) |
| #29 / #30 | P3-2/3 | Capability gap viewer + driver_selftest CLI (read-only, no commissioning impact) |
| #34 | P3-5 | Composite HAL readiness snapshot (commissioning precheck reads HAL status — coherent with this) |
| #35 | P2-5 | HAL Reload refuse/force policy (if operator clicks Reload mid-session, gets 409 with blockers — see Y3) |
| #36 / #38 / #39 / #40 | P2-1 | UXM Test App + Topology profile (commissioning UXM bind path uses topology — see Y5) |
| #41 | P3-8 | VRT pydantic regression fix (orthogonal feature, not commissioning) |
| #42 | out-of-roadmap | HAL real-mode init datetime fix (commissioning runs in mock typically, not impacted) |
| #43 | P3-6 | Chamber preset Type-C `has_lna` + `supports_trp` flip (commissioning reads chamber config — coherent) |
| #44 | P3-7 | UXM rename + self._cmds + .vscode (downstream of topology profile) |
| #46/#47/#48/#49 | P3-10..13 | Test isolation fixes (no production behavior change) |
| #50/#51/#52 | various | Roadmap / GUI confirm dialog / PFS docs (orthogonal to commissioning) |

### Database migrations applied since baseline

Three new alembic revisions, all additive (no column drops, no NOT NULL backfill that could break existing rows):

| Revision | Adds |
|---|---|
| `a1b2c3d4e5f6` | `test_steps.needs` for P1-1 preflight |
| `c7a91b3e5d04` | `instrument_topology_profiles` table |
| `d8b412ca9f15` | `test_plans.topology_profile_id` nullable string |

**Verdict**: schema additive → no commissioning regression from migration drift.

---

## Workflow Map (current state, verified live)

End-to-end Commissioning session via API, against running dev backend (mock HAL mode):

| Step | Endpoint | Verified | Notes |
|---|---|---|---|
| 1. Lab list | `GET /api/v1/lab-profiles?include_inactive=false` | ✅ HTTP 200, 1 lab (`CAICT-Lab-1`) | Schema is plain list, not paginated wrapper |
| 2. Session create (ASC) | `POST /api/v1/commissioning/sessions {"engine_mode":"mimo_first_asc"}` | ✅ HTTP 201, `session_id` returned | Auto-picked sole active lab (no ambiguity to trigger 422) |
| 3. Session create (GCM) | `POST /api/v1/commissioning/sessions {"engine_mode":"keysight_gcm"}` | ✅ HTTP 201 | Both modes accepted |
| 4. Precheck | `POST /api/v1/commissioning/sessions/{id}/phase/precheck` | ✅ HTTP 200, `status=success`, `overall_pass=true` | 7/7 instruments online (mock); chamber CAICT-16-Probe-Dual; UE capability + path-loss + QZ ripple all pass |
| 5. Reference | `POST .../phase/reference` | ✅ HTTP 200, `measured_trp_dbm` + `compensation_factor_db` populated | No "wait" intermediate state visible from API (jumps to completed) |
| 6. Reference_wait alias | `POST .../phase/reference_wait` | ✅ HTTP 200, returns current phase status | Confirmed alias works; subsequent calls are idempotent re-reads |
| 7. mimo_test (ASC) | `POST .../phase/mimo_test` (engine=ASC session) | ✅ HTTP 200, `engine_mode=mimo_first_asc` in result | `asc_files_loaded=True` (see Y2) |
| 8. mimo_test (GCM) | `POST .../phase/mimo_test` (engine=GCM session) | ✅ HTTP 200, `engine_mode=keysight_gcm` in result | `asc_files_loaded=True` ALSO present (see Y2) |
| 9. analysis | `POST .../phase/analysis` | ✅ HTTP 200, all KPI keys (`avg_throughput_mbps` / `avg_sinr_db` / `avg_rank_indicator` / `rsrp_variance_db` / `qz_pass` / `rank_pass` / `sinr_pass` / `rsrp_pass` / `margin_db`) | All pass flags True in mock mode |
| 10. Report | `POST .../phase/report` | ✅ HTTP 200, `report_id=MIMO_OTA-<uuid>-<ts>`, `report_db_id=<uuid>` | DB record created with `file_path` + `file_size_bytes=6416` |
| 11. PDF on disk | `data/reports/<uuid>/report_<uuid>.pdf` | ✅ Exists (6416 bytes) | Plus legacy copy in `Result_Report/` |
| 12. Final state | `GET .../sessions/{id}` | ✅ `overall_progress=100`, all phases `completed`, `report_id` populated | Workflow round-trip clean |

---

## Findings

### 🟡 Y1 — Lab profile validation tightened past seed-data shape

**Where**: `app/models/lab_profile.py` request schema + `bootstrap/lab_profile.py` seeder
**Symptom**: `POST /api/v1/lab-profiles` returns 422 with `instrument_bindings: "List should have at least 1 item after validation, not 0"` if `instrument_bindings` is empty. **But the seeded default `CAICT-Lab-1` has `instrument_bindings: []` (0 items)**.

```
$ GET /api/v1/lab-profiles?include_inactive=false
[{"id": "7aea2b69-...", "name": "CAICT-Lab-1", "is_active": true, "instrument_bindings": [], ...}]

$ POST /api/v1/lab-profiles  # try to clone its shape
HTTP 422  detail: "List should have at least 1 item after validation, not 0"
```

**Implication**: 
- Any operator attempt to clone-and-edit the default lab via GUI will fail on the bindings validator
- Direct attempts to create a 2nd lab without bindings (e.g., for ambiguity-picker testing) will fail
- The seeded lab exists in a state that the create endpoint won't accept

**Severity**: 🟡 yellow — not blocking first-call (single-lab path works), but blocks operator workflows that touch lab CRUD.

**Recommendation**: pick one:
- (a) Loosen validator: allow `min_length=0` on `instrument_bindings`, since the model permits empty 
- (b) Tighten seeder: have the default seeder populate at least one binding (probably correct since chamber + instruments are linked anyway)

Estimated fix: ~30 min either way.

### 🟡 Y2 — `mimo_test` result has `asc_files_loaded: True` in BOTH engine modes

**Where**: `app/services/mimo_ota/executors/measure.py` result payload
**Symptom**: `asc_files_loaded` field is True in the `mimo_test` result regardless of `engine_mode`:

```
ASC session mimo_test:  engine_mode=mimo_first_asc, asc_files_loaded=True   ✓ makes sense
GCM session mimo_test:  engine_mode=keysight_gcm,   asc_files_loaded=True   ✗ misleading — GCM doesn't use ASC files
```

**Implication**:
- Field name suggests ASC-specific behavior but is engine-agnostic
- Report rendering / GUI display showing "ASC files loaded" for a GCM session is technically wrong
- Potential confusion in operator log analysis post-trip

**Severity**: 🟡 yellow — cosmetic / semantic, not functional.

**Recommendation**: pick one:
- (a) Rename field to engine-agnostic name (e.g., `synthesis_output_loaded`, `channel_data_ready`)
- (b) Make field engine-specific: omit from GCM result, present in ASC result
- (c) Document that "asc_files_loaded" in GCM context means "GCM equivalent successfully loaded" (least clean)

Estimated fix: ~30 min.

### 🟡 Y3 — Engine-mode switcher in GUI allows mutation post-session-lock (inherited from static read)

**Where**: `gui/src/components/Commissioning/index.tsx:271-273` (engine select) + line 130 useEffect with `engineMode` in deps
**Symptom (per static read; not GUI-clicked in this audit)**: After a session is created, the engine_mode select is still interactive. Changing it re-triggers `initSession()` which silently creates a NEW session via `api.createSession()`. Stepper continues showing old session's phase state.

**Implication**: operator picks GCM, locks session to GCM, accidentally clicks ASC → new ASC session created in background, page UI shows mixed state until refresh.

**Severity**: 🟡 yellow — fragile UX, low probability in real workflow (operator pretty deliberate about engine choice), but worth a notification ("正在创建新会话, 之前的将丢弃") or disabling the select once session is active.

**Recommendation**: disable engine select when `session != null` and add explicit "新建会话(切换引擎)" button. ~30 min GUI change.

**Live verification needed**: click in browser to confirm the static read interpretation.

### 🟡 Y4 — `reference_wait` alias UX expectation (inherited from static read)

**Where**: `app/api/commissioning.py:77-79` aliases `reference_wait` → same step type as `reference`
**Symptom**: `reference_wait` doesn't model an explicit "wait" state — calling it on a completed reference phase returns the completed status without state transition.

**Live verified**: returns HTTP 200 + status (matches static read).

**Implication**: GUI flow shows "已安装, 开始参考测量" button when status is `waiting`; clicking it expects a transition to `running`. If reference already ran once and is `completed`, second click would no-op silently.

**Severity**: 🟡 yellow — likely benign because GUI hides the button when status is `completed`, but UI/backend state-machine mental model differs slightly.

**Recommendation**: clarify with explicit "wait" phase OR document that `reference_wait` is "report current status" semantically. Low priority; document not fix.

### 🟡 Y5 — Topology profile soft-fail on greenfield (inherited from static read)

**Where**: `app/services/mimo_ota/executors/measure.py:219` calls `orchestrate_switch_topology()`
**Symptom**: If `instrument_topology_profiles` table isn't seeded (greenfield deployment), call returns `success=False` with warnings, phase continues (warnings only, not hard failure).

**Live verified**: 7 system-preset profiles ARE seeded on current dev DB (✅ bootstrap working), so this didn't trigger here.

**Implication**: a new deployment that runs migrations but skips bootstrap seeders → topology checks silently soft-fail; commissioning still completes but with degraded confidence.

**Severity**: 🟡 yellow — depends on deployment hygiene; bootstrap seeders DO run on FastAPI startup per current code, so the risk is low for our standard deployment path.

**Recommendation**: smoke-check after each deployment: `GET /api/v1/instruments/baseStation/topology-profiles` should return 7 items.

### 🟡 Y6 — Lab ambiguity picker narrow no-op case (inherited from static read)

**Where**: `gui/src/components/Commissioning/index.tsx:193-197, 214`
**Symptom**: If operator (a) sees multi-lab picker, (b) clicks "启动首测会话" without first selecting a lab, button is disabled. Only escape is to use the Select picker first.

**Severity**: 🟡 yellow — works correctly, just slightly unintuitive.

**Recommendation**: live GUI smoke to confirm UX is acceptable; if confusing, add tooltip on disabled button. Could not API-smoke because of Y1 (can't create 2nd lab via API to trigger ambiguity).

---

## Notable changes (🟢 worth knowing, no action needed)

1. **PR #27 lab resolution 422 mapper** ([`api/commissioning.py:32-59`](../../api-service/app/api/commissioning.py#L32-L59)) — clean implementation, properly catches `LabResolutionError` and produces structured detail body with `kind` / `message` / `active_labs` for direct GUI rendering.
2. **Dual-engine dispatch correctness** — `engine_mode` propagates from `CreateSessionRequest` → `TestCase.configuration` → `mimo_test` executor's strategy selection, verified live for both `mimo_first_asc` and `keysight_gcm`.
3. **PDF generation path** — primary write to `data/reports/<uuid>/`, automatic copy to legacy `Result_Report/` if directory exists ([`report_service.py:344-355`](../../api-service/app/services/report_service.py#L344-L355)). Both locations populated in our smoke run.
4. **TestCase→TestExecution decomposition** — sessions now backed by real DB rows (TestCase + TestExecution), step descriptors live in `configuration` JSON, dispatcher is single source of truth.

---

## Things needing GUI click (❓ not API-smokeable from here)

### ❓ G1 — Multi-lab ambiguity 422 picker GUI render
**Setup**: need ≥2 active labs in DB (currently blocked by Y1 from API path). Either fix Y1 first or insert directly via SQL/`SessionLocal`.
**Verify**:
1. GUI shows yellow alert "Lab 选择不明确 / 请从下方选择"
2. Select picker populated with both labs
3. Picking one enables "启动首测会话" button
4. Submit → session bound to picked lab

### ❓ G2 — Engine-mode swap mid-session UX (Y3)
**Setup**: any session created
**Verify**:
1. Pick `mimo_first_asc`, observe session locked badge
2. Click engine select, pick `keysight_gcm`
3. Notification appears? Stepper resets? Old badge updates?
4. Expected behavior: explicit confirmation OR disabled control

---

## Phase calibration mutex check (cross-reference)

From PFS investigation (PR #52): `probe_phase_jitter=True` is mutually exclusive with applying phase cal cert. Commissioning today does not expose a `probe_phase_jitter` toggle in the UI (it's set in ChannelEgine's Streamlit `app.py`, not in MIMO-First's commissioning sandbox). So **no current commissioning workflow can simultaneously enable both** — mutex is preserved by absence.

**Risk if anyone adds a jitter toggle to commissioning later**: cal cert workflow breaks silently. See [`project_jitter_phasecal_mutex.md`](../../memory/) (cross-project memory) — when wiring jitter into commissioning, mutex enforcement must come together.

---

## On-site smoke checklist (next CAICT trip)

When at CAICT, before kicking off any real test, walk this checklist:

```
[ ] GUI loads Commissioning Sandbox without errors (console clean)
[ ] Active lab(s) listed correctly; "CAICT-Lab-1" present
[ ] Chamber config card displays "CAICT-16-Probe-Dual" with 16 probes, dual-pol
[ ] Engine selector shows both options with operator-friendly labels
[ ] Pick mimo_first_asc, click 启动首测会话 → see "首测会话已创建" notification
[ ] Precheck phase: instruments_online 7/7 (Real mode, not Mock), all messages green
[ ] Reference phase: measured_trp_dbm sensible (-50 to -90 dBm typical for ref horn)
[ ] mimo_test phase: completes within ~60s, azimuth_results populated for 4 azimuths
[ ] analysis: KPIs match expected ranges (avg_throughput > 50 Mbps for 2x2 SCME UMa)
[ ] report: PDF generated, opens cleanly, contains all phase data + plots
[ ] Repeat above with engine=keysight_gcm; verify GCM path produces a different waveform but similar final KPIs (within noise)
[ ] Verify Y1: try to clone CAICT-Lab-1 via GUI lab editor — does it fail with bindings error? If yes, fix before any operator hits this
[ ] Verify Y3: click engine selector after session creation; does it warn/disable?
```

---

## Cross-references

- [`docs/roadmap-first-call.md`](../roadmap-first-call.md) §"Discovered during X" — backlog for any drift findings to promote
- [`docs/features/calibration/pfs-phase-immunity.md`](../features/calibration/pfs-phase-immunity.md) — PFS phase immunity math + project implementation status
- Memory: `project_jitter_phasecal_mutex.md` — mutex rule referenced in cal-related checks
- PR #19 (`988cc40`) — baseline
- PR #27 (`22f45b8`) — direct commissioning change
- PR #52 (`4577cdb`) — PFS investigation + this audit's catalyst

---

## Audit conclusion

**Commissioning Sandbox 没漂死**。End-to-end workflow round-trips cleanly in dev (HTTP 200/201 throughout, PDF actually on disk, both engine modes dispatched correctly). Zero hard-broken paths.

6 yellow flags (2 confirmed live + 4 inherited from static read) are all UX / semantic / hygiene concerns — none block first-call. Highest priority fix is **Y1** (lab validation vs seed mismatch) because it blocks operator lab CRUD workflows.

Confidence post-audit that next on-site can run commissioning successfully: **~80%**, conditioned on Y1 fix + GUI smoke of G1/G2.
