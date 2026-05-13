# Site debug retrospective — CAICT 2026-05-12 / 05-13

**Engineer:** Simon · **Lab:** CAICT-Lab-1 · **Trip:** 2-day chamber commissioning prep + first-day instrument bring-up

Goal of this doc: capture the failure modes, root causes, and engineering lessons from two days of bringing real SCPI instruments online for the first time. Future on-site engineers — or anyone touching the HAL layer — should read this before doing the same work.

## TL;DR

We hit eight distinct "driver won't load / probe won't run" failures over two days. All eight had different surface symptoms but shared the same DNA: **state about whether a driver is alive is independently tracked in 3+ places, and any two of them can disagree without anyone noticing**.

The fixes were small per-failure. The follow-up work to make these classes of failure *visible* and *reversible without a backend restart* is in [TODO follow-ups](#post-trip-follow-ups).

---

## Failure timeline

### Day 1 (2026-05-12) — Keysight E5071C ENA

| # | Surface | Real cause | Bucket |
|---|---|---|---|
| 1.1 | GUI 「调试序列」 → vna_ena_health → fail: `No vna driver loaded — check HAL init logs` | Backend started **before** GUI configured the ENA. `HAL.initialize_hal_service()` runs once at FastAPI `lifespan` startup and never re-reads DB. | **Init timing** |
| 1.2 | After backend restart, same error | `pyvisa` not installed in `.venv` (it's in requirements.txt lines 35-36, but `pip install -r requirements.txt` was never re-run after they were added). Driver's `import pyvisa` inside `connect()` raised `ImportError`, HAL caught it as "connection failed", swallowed the error message, displayed generic `"Connection failed during HAL init"` to GUI. | **Env drift** |
| 1.3 | pyvisa installed, restart — `VI_ERROR_TMO (-1073807339)` on every query | E5071C `System → Misc Setup → Network Setup` exposes **three** servers: SICL-LAN, Socket, "VNA" (Agilent-era name for VXI-11). Only SICL-LAN was on; driver tries VXI-11 resource string `TCPIP::ip::INSTR` — wrong protocol, server doesn't answer. Operator couldn't tell from the menu which protocol was which. | **Protocol dialect invisible** |
| 1.4 | After enabling VXI-11, IDN works + setup_sweep works + measure_s_param works — but `get_trace_data()` returns `[]` after a 10 s VISA timeout | Driver used `CALC1:DATA? SDATA` — PNA "B"-series syntax. E5071C answers `-113 "Undefined header"`. Native syntax is `:CALC1:SEL:DATA:SDAT?`. Driver was clearly written from Keysight ENA Programming Guide assumptions, never tested against real E5071C firmware. | **SCPI dialect wrong** |

### Day 2 (2026-05-13) — Keysight F8820A / PROPSIM FS16

| # | Surface | Real cause | Bucket |
|---|---|---|---|
| 2.1 | `vna_ena_health` ran clean overnight. PROPSIM probe: `No channelEmulator driver loaded` | GUI had `PROPSIM F64` selected as channelEmulator model. Actual rack instrument was **PROPSIM FS16 (F8820A)** — same brand, different chassis, **different SCPI dialect**. F64 driver's `connect()` failed parsing FS16's response shape. `conn.status="error"` but with generic message. | **Wrong model selected** |
| 2.2 | Wrote new `RealPropsimFs16Driver`, switched DB selection, restart — still `No channelEmulator driver loaded` | `InstrumentDriver._query()` in base class is **synchronous**: it calls `self._do_query(cmd)` and immediately passes the result to `self._log_scpi_response(cmd, response)`. When `_do_query` is `async` (any driver using `asyncio.to_thread(pyvisa.query, ...)` — i.e. all PROPSIM/SOCKET drivers), the base hands a **coroutine object** to the logger. `_log_scpi_response` calls `response.strip()` — `AttributeError: 'coroutine' object has no attribute 'strip'`. Connect() catches it as "Connection failed during HAL init". F64 driver has the *same* latent bug, never exposed because no one had connected to a real F64 yet via SOCKET. | **HAL framework bug** |
| 2.3 | Fixed `_query`/`_write` override, probe loaded — but ran for 4 minutes with no result | Probe SCPI list included `*TST?`. IEEE 488.2 §10.36 says `*TST?` **triggers** an internal self-test, not a query of cached results. F8820A self-test takes ~30 s during which the SCPI channel does not respond to any other command. Every subsequent command in the probe (~20 commands × 10 s VISA timeout each) timed out. No circuit breaker. | **SCPI side-effect not audited** |
| 2.4 | Removed `*TST?` + added circuit breaker. Probe ran. Tried a second standalone test from CLI minutes later — `VI_ERROR_TMO` on every command | FS16 SOCKET only allows one client. Backend worker held `ESTABLISHED` state on its side; FS16 had timed out the idle connection from its side without our worker noticing. Standalone test got blocked at the SOCKET layer because the FS16's single-client port was "still in use" from the worker's POV. | **Stuck channel / half-close** |

---

## Root-cause categorization

All eight failures map to one of **six** root-cause buckets:

### A. State divergence between 3 sources of truth

The system tracks "is this instrument healthy" in three places that update independently:

1. **`InstrumentConnection.status`** in DB — written by the GUI 「测试连接」 button (TCP ping)
2. **`HAL.drivers[category_key]`** — populated by HAL `initialize_hal_service()` at FastAPI startup
3. **GUI's view of the connection** — reflects whatever the last poll returned

Operator sees `status=connected` in GUI, assumes HAL has a working driver. False. `conn.status=connected` only proves `nc -zv <ip> <port>` succeeded once. The actual VISA session may not exist.

**Symptom**: 1.1, 1.2, 2.1 — every failure where "GUI says it's connected" but "diagnostic sequence says no driver loaded".

### B. Init-once, never reload (architectural)

HAL service initializes from DB at FastAPI `lifespan` startup and has no reload mechanism. Once running, instrument-config changes via GUI don't take effect until backend restart.

This creates a chicken-and-egg loop:
- Operator wants to configure an instrument → needs backend running
- Backend's HAL didn't see new config → no driver loaded → 「调试序列」 fails
- Operator can't tell that they need to restart → frustration

**Symptom**: 1.1, 2.1 first attempts.

### C. Environment drift

`requirements.txt` and the actual `.venv` can fall out of sync if `safe-start.sh` doesn't enforce `pip install -r requirements.txt` on every start.

**Symptom**: 1.2 — pyvisa missing for the entire ENA bring-up first attempt.

### D. Protocol/dialect knowledge gaps

Real instruments differ from their programming guides in three ways the codebase didn't account for:

1. **Multiple protocols on one IP**: ENA exposes SICL-LAN + Socket + VXI-11 on the same chassis; menu names are vendor-era-specific ("VNA" = VXI-11 on Agilent-era firmware). Driver needs to know which protocol it's expecting.
2. **SCPI dialect drift across same vendor**: PNA `CALC1:DATA? SDATA` ≠ ENA `:CALC1:SEL:DATA:SDAT?`. The driver was written from a Keysight VNA Programming Guide that conflated the two.
3. **Same brand, different SCPI**: PROPSIM F64 vs FS16 share <60% of their SCPI surface. F64 driver can't drive FS16; same `*OPT?` returns valid data on F64 but `-100 ATE command not supported` on FS16.

**Symptom**: 1.3, 1.4, 2.1.

### E. SCPI side-effect audit gap

Probes built for "verify the box is alive" must use *only* idempotent query commands. `*TST?` (triggers self-test), `*RST` (factory reset), `DIAG:SIMU:GO`, `MEAS:*:START` — all forbidden in a probe.

We had `*TST?` in the FS16 probe initially. The IEEE 488.2 spec is explicit it's an action; the driver review process didn't catch it.

**Symptom**: 2.3.

### F. Error message ergonomics

Two strings the operator saw repeatedly and gained nothing from:
- `"Connection failed during HAL init"` — actual exception (e.g. `ModuleNotFoundError: pyvisa`) was logged but didn't reach the GUI or `conn.last_error`.
- `"No vna driver loaded — check HAL init logs"` — but the logs were in a 200-line stdout mix from `npm run dev:safe:all`, nobody could read them.

**Symptom**: 1.1, 1.2, 2.1, 2.2 all required SSH-into-logs to actually diagnose.

---

## Lessons for SCPI driver development

### L1. Probes must be side-effect free

Before adding a SCPI to a probe list, check the vendor's programming reference for the command's "action" vs "query" classification. If it has side effects on instrument state, **do not put it in a probe**. Even if it returns a value.

Forbidden categories: `*TST?`, `*RST`, `*CLS` (acceptable only at probe start), anything with `START`, `STOP`, `RUN`, `GO`, `APPLY`, `INIT`, `SEND`, `AUTOSET`, `CALIBRATION:START`, `MEAS:*:START`.

### L2. Identity check must accept multiple substrings

Brands rename. `Agilent Technologies` → `Keysight Technologies` is the famous one, but smaller renames happen at the model level too — FS16's IDN says `F8820A` with no "PROPSIM" word; only `SYST:INFO?` carries the brand.

Probe identity gate: try IDN substring first, fall back to `SYST:INFO?` substring. Document both expected tags in the probe metadata.

### L3. Same brand ≠ shared SCPI

PROPSIM F64 and FS16 are the same Keysight product family. The SCPI surface they accept overlaps by ~60% on IEEE 488.2 basics and a handful of `SYST:*`, `DIAG:SIMU:*`, channel-indexed reads. The other 40% is genuinely different:

- F64 has `*OPT?` for license enumeration; FS16 returns `-100 ATE not supported`.
- F64's signature pipeline is `CALC:FILT:FILE` + `DIAG:SIMU:GO` (GCM-native model loading); FS16 only does file-based playback via `MMEM` namespace.
- F64 supports `OUTPut:INTERFerence:*` for internal CW generation; FS16 doesn't.
- F64's working directory is `D:\User Emulations`; FS16 uses `D:\User Playbacks`.
- F64 supports `SYSTem:EXTernal:UNIT:LIST?` for SGH discovery; FS16 doesn't.

**Always empirically verify against real firmware before declaring a driver "works on family X".**

### L4. Cross-vendor SCPI lookalikes are landmines

`CALC1:DATA? SDATA` on Keysight PNA `≠` `:CALC1:SEL:DATA:SDAT?` on Keysight ENA. The whitespace and colon differences look cosmetic; the firmware treats them as different commands. Don't extrapolate.

### L5. Driver should expose raw SCPI primitives (`_query`/`_write`) consistently

Probes and ad-hoc diagnostic tools depend on `driver._query(scpi)` to inspect the live instrument without opening a second VISA session. Any HAL driver that doesn't expose this can't be probed live. Make it part of the driver contract, not an implementation detail.

### L6. Standalone pyvisa probe is the first-touch tool, not the HAL

Every bug this trip was diagnosed by writing a 10-line pyvisa script before touching the driver:

1. `rm.list_resources()` + try N resource strings → narrow down the transport layer
2. Send ~10 canonical SCPI → categorize each by `SYST:ERR?` response
3. From the response matrix, decide: is this a driver bug, a firmware quirk, or a misconfigured instrument?

These ad-hoc scripts should be sediments, not throw-aways. The follow-up work [`scripts/site-debug/<vendor>_<model>_probe.py`](#post-trip-follow-ups) sediments them.

---

## What we shipped during the trip

Two PRs and one branch:

- **PR #7 (merged to main)** — `fix(hal): E5071C ENA driver — native :CALC1:SEL:DATA:SDAT? + add health probe`. Driver SCPI fix + `vna_ena_health` sequence.
- **`site-debug/caict-2026-05-13-d2-simon` branch** — `feat(hal): PROPSIM FS16 (Keysight F8820A) driver + health probe`. New `RealPropsimFs16Driver` MVP + `propsim_fs16_health` sequence + tests. End-to-end verified on the field unit.
- **`site-debug/caict-2026-05-13-d2-simon` continued** — `refactor(hal): backport FS16 lessons to F64 driver + health probe`. The `_query`/`_write` async fix and Phase A circuit breaker and `SYST:INFO?` identity fallback pulled into the F64 driver/probe pre-emptively, so the next F64 bring-up doesn't repeat 2.2 / 2.3 / 2.4.

---

## Post-trip follow-ups

Tracked in the project todo list. Priority order:

| # | Item | Status | Reason |
|---|------|--------|--------|
| 1 | **Base `InstrumentDriver._query`/`_write` polymorphic — sniff async, await automatically** | done in same commit as this doc | Fixes the root cause of 2.2 once for *all* HAL drivers, not just F64/FS16 |
| 2 | **HAL READINESS REPORT at startup tail + surface real `connect()` exceptions to `conn.last_error`** | done in same commit | Operator-visible alternative to "go SSH and grep" for 1.1 / 1.2 / 2.1 / 2.2 |
| 3 | **`POST /api/v1/instruments/hal/reload` + GUI button** | done in same commit | Eliminates the configure→restart→configure loop, fixes B (init-once) |
| 4 | **`scripts/site-debug/<vendor>_<model>_probe.py` sediments** | deferred | Each instrument we bring up should leave a 20-line pyvisa probe behind, callable from CLI before touching HAL |
| 5 | **`safe-start.sh` to `pip install -r requirements.txt` before launching** | deferred (1 line change) | Closes the env-drift category. Trivial, low-risk. |
| 6 | **Dev log stream split** — `logs/dev/{api,ce,gui}.log` instead of mixed stdout | deferred | Operator-facing improvement; current state forced grep-the-haystack |

---

## Quick-reference: instrument-bring-up checklist

Distilled from these two days. Before declaring a new instrument "ready", verify all of these:

1. **Env**: `cd api-service && .venv/bin/pip install -r requirements.txt` — never assume.
2. **Reachability**: `ping <ip>` succeeds, `nc -zv <ip> <port>` returns "succeeded".
3. **VISA layer**: standalone pyvisa probe with at least 3 candidate resource strings (`TCPIP0::ip::inst0::INSTR`, `TCPIP0::ip::<gpib>,<addr>::INSTR`, `TCPIP::ip::5025::SOCKET`). Note which one returns IDN.
4. **Identity**: IDN substring matches expected model OR `SYST:INFO?` substring matches. Never just one.
5. **SCPI surface**: send the driver's full critical-command list as queries (append `?` to actions, swallow responses, inspect `SYST:ERR?` after each). Classify SUPPORTED / UNSUPPORTED / STATE-REJECTED. Cross-check against the driver's expectations.
6. **Probe in 「调试序列」 GUI**: passes end-to-end in < 10 s.
7. **Reload test**: change a config field in GUI → click HAL reload → driver reflects the change. (Once #3 above lands.)

If any step fails, *stop and root-cause before moving on*. Do not paper over with retries.
