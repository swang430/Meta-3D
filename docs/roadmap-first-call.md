# MIMO-First — First-Call Roadmap

> **Single source of truth for what we're working on next.** All non-trivial
> development MUST reference an item on this roadmap. Off-roadmap work needs
> explicit justification (see [governance rules](#governance-rules) below).

---

## 🎯 Current Focus

**`P0-1` — DB 自动播种 (chamber presets / instrument catalog / sequences / templates)**

- **WIP limit: 1**. Only one P0 may be `in-progress` at any time.
- Anything that's not the Current Focus item and not a triviality (<30 min)
  gets appended to the backlog instead of done inline.

Last review: 2026-05-14
Baseline commit: see [announcement](announcements/2026-05-14-roadmap-baseline.md)

---

## Governance rules

These rules exist because at CAICT 2026-05-12/13 a 2-day on-site that was
supposed to deliver a chamber first-call ended up consumed by driver-layer
firefighting (F64 IDN / UXM Test App / Aerotech single-axis / idle-close).
The work was real and necessary, but the trip cost was a first-call we
didn't get. Mechanisms below are designed to prevent that pattern.

1. **WIP = 1 on P0.** Finish (PR merged + acceptance criteria verified)
   before starting the next P0.
2. **Read this file before non-trivial work.** Any agent / contributor
   must confirm which item they're working on. Off-roadmap requires an
   explicit `Out-of-roadmap, reason: ...` field in the PR.
3. **Mid-task discoveries → backlog, not detour.** Append to the
   "Discovered during X" section at the bottom of this file with a
   one-line note + date. Triage to P1/P2/P3/dropped at the next weekly
   review.
4. **No "顺手优化".** Mess is not a bug. If it doesn't make the current
   P0 easier, it's a P3 entry, not inline cleanup.
5. **Codex / review fixes that are not on the critical path** get their
   own commit on the next P0 branch, not a separate detour PR — unless
   they block merge.
6. **Periodic review (weekly).** Three questions:
   - Last week's focus was X — what did we actually do?
   - How much did we drift (0% / 30% / 100%)?
   - If we drifted, which of rules 1-5 broke?

---

## ✅ Done — do not redo

| ID | Item | Where it landed |
|----|------|----------------|
| D1 | 3 Codex P2 fixes on PRs #12/#13/#14 + Aerotech idle-close reconnect + HAL pre-flight TCP + startup readiness display | PR #14 (merged 2026-05-13) |
| D2 | F64 channel-model GUI + dropdown (Stage 2) + curated-list CRUD endpoints | PR #15 (in review 2026-05-14) |
| D3 | silent-reconnect pattern broadcast to F64 / FS16 / UXM / ENA (PyVISA) | PR #15 |
| D4 | F64 license probe — SYST:INFO? + soft-probe replacement for `*OPT?` + Codex P1 inline error-payload guard | PR #15 |
| D5 | F64 -100 categorizer regression tests + 5/13 team summary | PR #15 |

---

## 🔴 P0 — Critical path to first-call

Each one is "won't run first-call without it".

### P0-1 — DB auto-bootstrap on startup ⭐ Current Focus

> **Repo path note**: 本项 (以及后续 P0 中提到的 `app/...`) 路径全部相对
> `api-service/` 子包。FastAPI 入口是 [`api-service/app/main.py`](../api-service/app/main.py),
> 播种器在 [`api-service/app/services/bootstrap/`](../api-service/app/services/bootstrap/),
> 手动 CLI 是 `cd api-service && python -m scripts.bootstrap`。
> 不要在仓库根新建 `app/` —— 它不存在。

**What**: [`api-service/app/main.py`](../api-service/app/main.py) lifespan
calls `run_all()` after `init_db()`. The 4 chamber presets (A/B/C/D),
instrument model catalog, sequence library, report templates, and test-case
templates land in the DB on first boot.

**Why**: New installs see empty everything → operators can't get past the
"create your first chamber" step without running
`cd api-service && python -m scripts.bootstrap` manually. The seeders +
idempotent `bootstrap_history` are already built — nobody wired the pipe
to lifespan startup.

**Acceptance**:
- `docker-compose up` on an empty DB seeds 4 chambers + 12+ instrument
  models + 8+ sequences + report templates
- Restart on an already-seeded DB is a no-op (`bootstrap_history` records
  match)
- `BOOTSTRAP_ON_STARTUP=false` env var disables auto-run (escape hatch)
- HAL readiness table shows a `[bootstrap]` row summarising what was seeded
- Tests: empty-DB cold start → 4 chambers visible; warm-restart → no
  duplicates

**Status**: `[ ]` not started
**Estimate**: 1 day

---

### P0-2 — Lab Profile init wizard

**What**: GUI detects `LabProfile.count() == 0` on first launch and shows a
wizard:
1. Pick chamber template (A/B/C/D cards)
2. Adjust dimensions / probe layout if needed
3. Bind instruments (model + IP/port for each category)
4. Done — lab is ready for calibration

**Why**: Without this, even seeded chambers don't help — operators don't
know that the chamber template needs to be cloned + customized + assigned
to a Lab Profile before tests can run.

**Acceptance**:
- Fresh install → GUI shows wizard, not empty dashboard
- Wizard completes → at least one active LabProfile exists with a
  Chamber + at least one Instrument bound
- Cancellable + resumable (don't lose progress on browser refresh)
- Existing lab → wizard does not appear

**Status**: `[ ]` not started — **depends on P0-1**
**Estimate**: 1.5 days

---

### P0-3 — Path-loss calibration (CAL-01) loop closure + cal cert generation

**What**: Run the CE+SA path-loss calibration end-to-end on real hardware,
producing a `CalibrationCertificate` row with the 32-element
`path_loss_db_by_rf_chain` map. The MIMO_OTA `MEASURE` phase already
consumes this — currently fails open with `avg_path_loss_db=0.0` when
absent.

**Why**: Without per-chain path loss, throughput/RSRP measurements are
uncalibrated — the first-call output is unverifiable. Precheck warns but
doesn't block, so operator can "complete" first-call with garbage
numbers.

**Acceptance**:
- Calibration run produces a CalibrationCertificate with all 32 chains
  populated (non-zero)
- `overall_pass = True`
- `valid_until > now()` (typically +30 days)
- Precheck phase sees the cert and stops warning
- A repeat measurement gives the same path-loss values within ±0.5 dB

**Status**: `[ ]` not started — needs SA in HAL (P0-4) + on-site
**Estimate**: on-site 1 day + local 0.5 day

---

### P0-4 — SignalAnalyzer in HAL for reference TRP

**What**: Bind a Keysight N9020B MXA (or equivalent) to the HAL
`signalAnalyzer` category and connect it to a known-gain reference horn
antenna in the chamber. Reference phase reads real channel power, applies
the offset, and emits a real TRP — not the current mock 23.5 dBm fallback.

**Why**: The `_MOCK_TRP_DBM` fallback means the compensation factor is
fake. Real first-call needs the real path:
`measured_TRP = SA_power + offset → compensation_factor = horn_gain - (measured - nominal)`.

**Acceptance**:
- `signalAnalyzer` driver is loaded (readiness table shows ✓)
- Reference phase logs `measurement_source: "hal_signal_analyzer"` (not
  `"mock"`)
- Measured TRP within ±1 dB of horn datasheet TRP at the tested
  frequency

**Status**: `[ ]` not started — `RealKeysightXSeriesSaDriver` exists,
needs config + on-site connection
**Estimate**: on-site 0.5 day + local 0.5 day

---

### P0-5 — DUT attach → bearer → PDSCH on UXM 5G NR

**What**: Put a real DUT in the chamber, attach it to UXM via SIM + RRC,
establish a default bearer, push PDSCH traffic, and read back actual
throughput. The MEASURE phase needs this to compute real RSRP/SINR/Tput.

**Why**: Today the Measure executor simulates RSRP and SINR (the BS
doesn't report them via SCPI). Throughput is real *if a DUT is attached*
— but we never closed the attach loop on-site.

**Acceptance**:
- POST /test-executions/{id}/attach-dut succeeds, records IMSI + RRC
  state
- UE Capability query returns `max_dl_layers >= configured layers`
- One azimuth sweep produces a non-zero throughput reading from UXM
- 4-azimuth sweep gives 4 distinct throughput values (sanity: rotation
  is changing the link)

**Status**: `[ ]` not started — UXM 5G NR profile already supported (PR #10)
**Estimate**: on-site 1-2 days

---

### P0-6 — Mock-data first-call end-to-end (local rehearsal)

**What**: Run all 5 commissioning phases locally with mock cal cert /
mock SA / mock DUT to **confirm the software pipeline has no blind
spots**. The 5 phase executors exist (1386 LOC total) but the full chain
was never exercised in one run.

**Why**: Going on-site without this means we again debug driver layer +
commissioning at the same time. Decouple them: software pipeline first,
hardware second.

**Acceptance**:
- One TestExecution row with `test_type=MIMO_OTA` runs all 5 phases to
  completion
- `phase_statuses` ends at `{"precheck": "passed", "reference":
  "passed", "mimo_test": "passed", "analysis": "passed", "report":
  "passed"}`
- A PDF report is generated
- No phase errors surfaced

**Status**: `[ ]` not started
**Estimate**: 1.5 days
**Dependencies**: none — purely local, can start anytime

---

## 🟠 P1 — First-call confidence / repeatability

### P1-1 — Capability registry + plan-level pre-flight

**What**: Standard vocabulary of capability tokens
(`ce.gcm_native`, `ce.interference_gen`, `bs.5g_nr`, `pos.single_axis_az`,
…). Each step template declares `needs: List[str]`. Each driver, post-
connect, declares `capabilities: Set[str]`. A `validate_plan(plan, lab)`
function returns the gap list. GUI shows a "预检" button on each plan.

**Why**: Discovers capability mismatches at plan-edit time, not at
runtime. Today the chain is "compose plan → run → step 4 fails because
F64 license not installed → diagnose 30 minutes".

**Acceptance**: see [P2-2](#p2-2--capability-集中化) (prerequisite)

**Status**: `[ ]` not started — **depends on P2-2**
**Estimate**: 2 days

### P1-2 — F64 license probe SCPI on-site verification

**What**: The soft-probe SCPIs in PR #15 (`OUTPut:INTERFerence:LIST?` /
`SYSTem:CALibration:USER:LIST?`) are placeholders — they're shaped right
but unverified on real F64. Verify on next site visit.

**Acceptance**: probe correctly reports presence/absence of each license
on a unit where the licensed state is known a priori.

**Status**: `[ ]` not started
**Estimate**: on-site 1 hour

### P1-3 — PyVISA "not installed" investigation

**What**: Reproduce the "PyVISA missing" condition seen during ENA
debugging. Run `which python && python -c "import pyvisa"` in the same
context. Confirm whether it was IDE-warning misread, wrong-venv, or
genuinely missing.

**Acceptance**: root cause documented in a memory entry.

**Status**: `[ ]` not started
**Estimate**: 1 hour

### P1-4 — first-call repeatability test

**What**: Run first-call 3x back-to-back on the same config. Plot RSRP /
SINR / Throughput variance. Establish the noise floor for "this is the
same lab".

**Acceptance**: variance documented; outliers explained.

**Status**: `[ ]` not started — depends on P0-3..P0-5 being on site
**Estimate**: on-site 1 day

### P1-5 — CAL-04 phase calibration

**What**: 32 probes need phase calibration so the spatial sum forms a
proper quiet zone. Endpoint exists (`phase_router`), workflow needs to
be exercised on-site.

**Acceptance**: phase cal cert generated; quiet zone metric improves
vs uncalibrated baseline.

**Status**: `[ ]` not started
**Estimate**: on-site 0.5 day + local 0.5 day

### P1-6 — FS16 / UXM / ENA silent-reconnect integration tests

**What**: F64 has 12 integration tests for the silent-reconnect pattern
(PR #15). FS16, UXM, ENA inherit the pattern but don't have driver-
specific integration tests. Add them once we see real idle-close
evidence.

**Status**: `[ ]` not started — pulled forward only if a real
production idle-close is seen on those drivers
**Estimate**: 0.5 day

---

## 🟡 P2 — Abstraction debt

### P2-1 — InstrumentProfile abstraction layer

**What**: Insert a `Profile` layer between `Model` and `Connection`. UXM
Test App, CMW500 mode, multi-carrier topology become first-class
profiles instead of bolt-on per-driver hacks.

**Why**: PR #10's UXM multi-app system is bolt-on. Next host-style
instrument (CMW500, CMP200) will hit the same gap.

**Status**: `[ ]` not started
**Estimate**: 3-5 days

### P2-2 — Capability centralisation

**What**: Collapse scattered `has_interference_generator` /
`is_single_axis` / `has_user_alignment` into `driver.capabilities:
Set[str]`. Single source of truth for "what does this driver expose
right now".

**Status**: `[ ]` not started — **blocks P1-1**
**Estimate**: 1 day

### P2-3 — Per-model capability discovery

**What**: Move capability declaration from per-Category to per-Model.
F64 ≠ FS16 even though both are channelEmulator — driver-level
capability sets resolve this without `if model == "FS16"` branches.

**Status**: `[ ]` not started — depends on P2-2
**Estimate**: 1.5 days

### P2-4 — NAT/firewall idle-drop hypothesis verification

**What**: TCP keepalive on Aerotech was added on the *assumption* that
CAICT's NAT/firewall drops idle TCP entries. Never verified. Run an
idle-then-poke test to confirm.

**Status**: `[ ]` not started
**Estimate**: 0.5 day

### P2-5 — HAL Reload behaviour audit

**What**: When operator clicks HAL Reload mid-test, what happens to the
in-flight diagnostic? Today: silently fails. Decide policy
(refuse / pause / let-fail) and document.

**Status**: `[ ]` not started
**Estimate**: 1 day

---

## 🟢 P3 — Polish / tooling

### P3-1 — HAL Reload confirm dialog
0.5 day. Prevent accidental reload mid-test.

### P3-2 — Driver self-test CLI
0.5 day. `python -m scripts.driver_selftest` dumps capabilities for every
loaded driver.

### P3-3 — Capability gap viewer in GUI
1 day. Depends on P1-1.

### P3-4 — F64 SYST:INFO? structured parser
0.5 day. Currently only keyword scan; extract channel_count / bands /
firmware version.

### P3-5 — Startup readiness summary expansion
0.5 day. Add lab-profile status + cal-cert validity + DUT-attach state
to the existing HAL readiness table.

---

## ⚠️ Known unknowns (verify on-site / next session)

| ID | Question | Verification path |
|----|----------|-------------------|
| U-1 | Does CAICT NAT really drop idle TCP entries? | Idle-then-poke test, see [P2-4](#p2-4--natfirewall-idle-drop-hypothesis-verification) |
| U-2 | Are `OUTPut:INTERFerence:LIST?` / `SYSTem:CALibration:USER:LIST?` the right soft-probes on F64? | On-site execution, see [P1-2](#p1-2--f64-license-probe-scpi-on-site-verification) |
| U-3 | Which UXM Test Apps does CAICT actually use (beyond 5G NR / LTE_NR_IRAT)? | Inventory at next on-site |
| U-4 | What are the common DUT attach failure modes (IMSI / SIM / RRC state)? | First DUT attach session, see [P0-5](#p0-5--dut-attach--bearer--pdsch-on-uxm-5g-nr) |

---

## 🗂️ Discovered during X — triage backlog

> Items added mid-task. Reviewed weekly; promoted to P1/P2/P3 or dropped.

- `[discovered 2026-05-14 during P0-1]` `tests/test_chamber_configuration.py::TestChamberPresets::test_preset_type_c_exists` and the two `test_create_chamber_from_preset` variants fail on clean `main` (pre-existing — `has_lna` on Type-C preset is False but tests assert True). Either the seeder default drifted or the test expectations did. Triage: ~30 min in `app/services/bootstrap/chamber_presets.py` vs `tests/test_chamber_configuration.py`.

---

## 📊 Summary

| Priority | Count | Total estimate | On-site share |
|----------|-------|---------------|---------------|
| ✅ Done | 5 | — | — |
| 🔴 P0 (first-call critical) | 6 | 8 days | 4 days |
| 🟠 P1 (confidence) | 6 | 6 days | 2.5 days |
| 🟡 P2 (abstraction debt) | 5 | 7 days | 0 |
| 🟢 P3 (polish) | 5 | 3 days | 0 |
| **Total open** | **22** | **24 days** | **6.5 days** |

---

*This roadmap is a living document. Update Current Focus, append to
backlog, mark items done. All changes go through git so we have an audit
trail of what we said vs what we did.*
