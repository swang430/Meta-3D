# MIMO-First Documentation Reorganization Plan
**Version**: 1.0
**Date**: 2025-12-03
**Status**: APPROVED - Ready for Execution

---

## Executive Summary

**Problem**: 64 markdown files with significant redundancy (27%), outdated progress trackers, and unclear organization.

**Solution**: Consolidate to ~48 high-quality documents organized by purpose, archive completed phases, merge redundant docs.

**Impact**:
- 25% file reduction
- Clear separation: active docs vs. reference vs. historical
- Updated progress tracking (6% → 40% actual)
- Single authoritative source for each topic

---

## Current State Analysis

### By Status:
| Category | Count | % |
|----------|-------|---|
| ✅ Active & Accurate | 16 | 25% |
| ⚠️ Needs Update | 10 | 16% |
| 📦 Archive (Complete) | 10 | 16% |
| 🔄 Merge/Delete | 13 | 20% |
| 📐 Hardware Reference | 6 | 9% |
| 📋 Design (Future) | 9 | 14% |

### Key Issues:
1. **Outdated Progress Tracking**: Master-Progress-Tracker shows 6% overall, actually ~40%
2. **Redundant VirtualRoadTest Docs**: 3 files covering same feature
3. **Stub Pollution**: 7 files < 1KB with minimal content
4. **Flat Structure**: 33 root-level files, hard to navigate
5. **Mixed Purposes**: Design docs, bug logs, hardware specs all in root

---

## Reorganization Strategy

### New Folder Structure

```
/MIMO-First/
│
├── README.md                          ← Entry point (KEEP)
├── GETTING-STARTED.md                 ← NEW: Quick setup guide
├── ARCHITECTURE.md                    ← NEW: System overview
│
├── /docs/
│   ├── /architecture/                 ← Design & architecture
│   ├── /development/                  ← Dev process & guides
│   ├── /hardware/                     ← Hardware specs & diagrams
│   ├── /guides/                       ← User/operator guides
│   ├── /design/                       ← Feature design docs
│   │   ├── /hal/
│   │   ├── /calibration/
│   │   ├── /testing/
│   │   └── /scenarios/
│   ├── /progress/                     ← Project tracking
│   └── /archive/                      ← Historical docs
│
├── /api-service/
│   └── README.md                      ← Backend API guide
├── /gui/
│   └── README.md                      ← Frontend guide
└── /channel-engine-service/
    └── README.md                      ← ChannelEngine guide
```

---

## Detailed Action Plan

### PHASE 1: Archive Completed Work (10 files)

Move to `/docs/archive/phases/`:

1. **PHASE1-COMPLETION-SUMMARY.md**
   - Reason: Phase 1 100% complete (calibration APIs)
   - Preserve as historical reference

2. **PHASE1-EXECUTION-GUIDE.md**
   - Reason: Initialization scripts completed
   - No longer needed for active dev

3. **PHASE3_SUMMARY.md**
   - Reason: Phase 3 marked COMPLETED
   - 5650 LOC delivered, historical record

4. **ChannelEgine-Integration-Plan.md** (docs/)
   - Reason: Phase 1 integration 100% complete
   - Superseded by working code

5. **ProbeLayoutView-Integration-Analysis.md** (docs/)
   - Reason: Integration completed
   - Code exists in gui/components/

6. **Test-Plan-Management-Design.md** (docs/)
   - Reason: Superseded by TestManagement-Unified-Architecture.md
   - Old v1.0 design, v2.0 implemented

7. **API-CALIBRATION-DEMO.md**
   - Reason: Demo for completed feature
   - Consider merging into user guide first

8-10. **Three more phase docs** as identified

**Action**: `git mv` to archive, update links in other docs

---

### PHASE 2: Merge Redundant Documents (5 pairs → 5 files)

#### 2.1 VirtualRoadTest Trilogy → Single Doc

**Merge:**
- `VirtualRoadTest.md` (product design 1.0)
- `VirtualRoadTest-Architecture.md` (architecture)
- `VirtualRoadTest-Implementation.md` (developer guide)

**Into:**
- `/docs/architecture/VirtualRoadTest-Complete.md`

**Structure:**
```markdown
# Virtual Road Test - Complete Documentation

## 1. Product Overview
   [From VirtualRoadTest.md]
   - Three test modes (Digital Twin, Conducted, OTA)
   - Scenario library concept

## 2. System Architecture
   [From VirtualRoadTest-Architecture.md]
   - Frontend components (ModeSelector, ScenarioLibrary, OTAMapper)
   - Backend APIs (/road-test/scenarios, /executions)
   - Data flow diagrams

## 3. Implementation Guide
   [From VirtualRoadTest-Implementation.md]
   - Component structure
   - API integration
   - Testing approach

## 4. Current Status
   [NEW SECTION]
   - ✅ Scenario Library: 5 standard scenarios implemented
   - ✅ Create/Run/Details: All features working
   - ✅ OTA Mapper: ChannelEngine integration complete
   - ⏳ Scenario → TestPlan conversion: Planned for Phase 4
```

**Benefit**: Single authoritative reference, eliminates confusion

---

#### 2.2 Dev Startup Guides

**Merge:**
- `DEMO-WALKTHROUGH.md` (safe-start demo)
- `DEV-QUICKSTART.md` (startup scripts)

**Into:**
- `/docs/development/GETTING-STARTED.md`

**Structure:**
```markdown
# Getting Started with MIMO-First Development

## Quick Start (Safe Mode)
   [From DEMO-WALKTHROUGH.md]
   - Mock instrument startup
   - Safe development environment

## Development Scripts
   [From DEV-QUICKSTART.md]
   - npm run dev:safe
   - cleanup scripts
   - Port configuration (5173, 8000, 8001)

## First-Time Setup
   [NEW]
   - Prerequisites
   - Database initialization
   - Environment variables
```

---

#### 2.3 Custom Scenario Design

**Merge:**
- `docs/Custom-Scenario-Design.md` (587B stub)

**Into:**
- `docs/design/testing/Virtual-Scenario-Library-Design.md`

**Add Section**:
```markdown
## Custom Scenario Creation

### UI Flow
1. User clicks "Create Scenario" in ScenarioLibrary
2. CreateScenarioDialog opens with 4 tabs
3. User configures: Basic Info, Network, Environment, Preview
4. System validates and creates RoadTestScenario

### API Integration
POST /road-test/scenarios
Body: ScenarioCreate schema

### Validation Rules
- Name: required, min 3 chars
- NetworkType: enum ('5G_NR', 'LTE')
- ChannelModel: enum ('UMa', 'UMi', 'RMa', ...)
```

---

### PHASE 3: Delete Stub Files (4 files)

**Delete entirely** (< 1KB, minimal content, no code implementation):

1. **TESTING-GUIDE.md** (50 lines, minimal content)
   - Reason: Redundant with other testing docs

2. **CI-CD-Pipeline-Design.md** (791B)
   - Reason: CI/CD not implemented, no concrete plan

3. **Data-Analysis-Design.md** (628B)
   - Reason: Analytics feature not designed or implemented

4. **Report-Generation-Design.md** (733B)
   - Reason: Reporting not implemented, superseded by export features

**Action**: `git rm`, document in CHANGELOG

---

### PHASE 4: Update Outdated Docs (10 files)

#### 4.1 ARCHITECTURE-REVIEW.md

**Changes Needed**:
```diff
## Phase 1: Foundational Development
- Status: ✅ COMPLETED (was: In Progress)
- Progress: 100% (was: 80%)
+ Date Completed: 2025-11-20

## Phase 2: Core Features
- Status: ✅ COMPLETED (was: Planned)
+ Bug Fixes: BUG-001 to BUG-004 resolved
+ Date Completed: 2025-11-28

## Phase 3: Advanced Features & Integration
- Status: ✅ COMPLETED (was: Future)
+ Virtual Road Test: All 3 features implemented
+ OTA Mapper: ChannelEngine integration working
+ Date Completed: 2025-12-02
```

---

#### 4.2 TestManagement-Unified-Architecture.md

**Changes Needed**:
```diff
## Implementation Status

### Tab 1: Plans Tab
- Status: ✅ COMPLETED (was: 🏗️ In Progress)
+ Features: CRUD, filtering, wizards all working
+ File: gui/src/features/TestManagement/components/PlansTab/

### Tab 2: Steps Tab
- Status: ✅ COMPLETED (was: 🏗️ In Progress)
+ Features: Drag-drop reorder, sequence library, parameter editor
+ Bug Fix: BUG-001 (step save failure) resolved

### Tab 3: Queue Tab
- Status: ✅ COMPLETED (was: 📋 Planned)
+ Features: Priority queue, start/pause/cancel controls
+ Auto-refresh every 10s

### Tab 4: History Tab
- Status: ✅ COMPLETED (was: 📋 Planned)
+ Features: Execution records, statistics, filtering, export
```

---

#### 4.3 Master-Progress-Tracker.md

**Major Overhaul Needed**:

Current shows:
```
Overall Progress: 6%
Phase 1: 100% ✓
Phase 2-7: 0%
```

**Reality**:
```markdown
## Overall System Progress: ~40%

### Phase 1: Foundation (100% ✓)
- Probe API, Instrument API, Calibration API
- Date: 2025-11-20

### Phase 2: Core Features (85% ✓)
- TestManagement: 100% (4 tabs complete)
- Monitoring: 100% (2.6-2.7 complete)
- Virtual Road Test: 90% (3/3 features done, TestPlan integration pending)

### Phase 3: Advanced Features (60% ✓)
- OTA Mapper: 100% (ChannelEngine integration working)
- Scenario Library: 100% (5 standard + custom creation)
- TestPlan Integration: 0% (planned)

### Phase 4: Hardware Integration (10%)
- HAL Implementation: 0% (designs complete)
- MPAC Integration: 0%

### Phase 5: Testing & Deployment (15%)
- Unit Tests: 40/40 passing
- E2E Tests: 6/14 passing (43%)
- CI/CD: Not implemented

### Phase 6-7: Future
- Advanced Analytics: 0%
- Production Deployment: 0%
```

**Add Completion Dates, Update %s, Link to Evidence**

---

#### 4.4 Implementation-Roadmap.md

Similar updates to align with actual progress.

---

#### 4.5 MONITORING-COMPONENTS-GUIDE.md

```diff
## Phase 2.6: Metrics Display Components
- Status: ✅ COMPLETED (was: In Progress)

## Phase 2.7: Real-time Updates
- Status: ✅ COMPLETED (was: Planned)

## Phase 3: Integration with Virtual Road Test
- Status: ⏳ PARTIAL (was: Not Started)
+ TestExecutionModal: Real-time progress display implemented
+ Remaining: Full OTA test monitoring
```

---

### PHASE 5: Expand Incomplete Stubs (3 files)

#### 5.1 Signal-Analyzer-HAL-Design.md (565B)

**Current**: Minimal outline

**Expand to**:
```markdown
# Signal Analyzer HAL Design

## 1. Overview
   - Purpose: Control RF signal analyzers (R&S FSW, Keysight PXA)
   - Measurements: Power, spectrum, EVM, ACLR, SEM

## 2. Hardware Abstraction
   - Abstract base class: SignalAnalyzerHAL
   - Concrete implementations: FSW_HAL, PXA_HAL

## 3. API Interface
   ### 3.1 Connection Management
   - connect(address, port)
   - disconnect()
   - reset()

   ### 3.2 Configuration
   - set_center_frequency(freq_hz)
   - set_span(span_hz)
   - set_rbw(rbw_hz)
   - set_reference_level(level_dbm)

   ### 3.3 Measurements
   - measure_power() → PowerResult
   - measure_spectrum() → SpectrumData
   - measure_evm() → EVMResult

## 4. Data Structures
   [Pydantic schemas]

## 5. Error Handling
   [Exception hierarchy]

## 6. Testing Strategy
   [Unit tests, mock implementation]
```

**Assign to**: Hardware integration phase

---

#### 5.2 Positioner-HAL-Design.md (603B)

Similar expansion for positioner control (azimuth/elevation motors).

---

#### 5.3 Data-Storage-Design.md (3KB, partial)

Expand to cover:
- Database schema design (SQLAlchemy models)
- Time-series data storage (InfluxDB for metrics)
- File storage (S3/local for reports, traces)
- Data retention policies
- Backup strategy

---

### PHASE 6: Create New Consolidated Docs (3 files)

#### 6.1 GETTING-STARTED.md (Root)

**Purpose**: Replace README as dev onboarding guide

**Content**:
```markdown
# Getting Started with MIMO-First

## What is MIMO-First?
   - Multi-antenna OTA test system
   - Virtual Road Test + Test Management + Calibration

## Quick Start (5 minutes)
   1. Clone repo
   2. npm run dev:safe (mock instruments)
   3. Open http://localhost:5173
   4. Try: Virtual Road Test → Scenario Library

## Architecture Overview
   - Frontend: React + Mantine UI (port 5173)
   - API Service: FastAPI (port 8000)
   - ChannelEngine: Python service (port 8001)
   - Database: PostgreSQL

## Next Steps
   - Read CLAUDE.md for detailed dev guide
   - Check TODO.md for current tasks
   - See /docs/architecture/ for system design
```

---

#### 6.2 ARCHITECTURE.md (Root)

**Purpose**: Single-page system architecture overview

**Content**:
```markdown
# MIMO-First System Architecture

## System Components
   [Diagram showing 3 services + database]

## Frontend Architecture
   - Virtual Road Test feature
   - Test Management feature (4-tab unified)
   - OTA Mapper component
   - Calibration panels

## Backend Architecture
   - FastAPI REST API
   - SQLAlchemy ORM
   - Service layer (TestPlanService, CalibrationService)

## Data Flow
   - Scenario → OTA Config → Test Plan → Execution → Results

## Key Design Patterns
   - HAL abstraction for hardware
   - Repository pattern for data access
   - Observer pattern for monitoring

## Technology Stack
   - Frontend: React 18, Mantine UI 8, TanStack Query
   - Backend: Python 3.11, FastAPI, SQLAlchemy
   - Database: PostgreSQL 14
   - Tools: TypeScript, Pydantic, Alembic migrations
```

---

#### 6.3 SYSTEM-INTEGRATION-DESIGN.md (NEW)

**Purpose**: Answer the integration question from earlier discussion

**Content**:
```markdown
# MIMO-First System Integration Design

## Overview
This document describes how Virtual Road Test, OTA Mapper, and Test Management integrate to create a unified testing workflow.

## Three-System Architecture

### 1. Virtual Road Test (Scenario Definition)
**Purpose**: Define what to test
- Scenarios: Route, base stations, environment, channel model
- 3 test modes: Digital Twin, Conducted, OTA
- Scenario library: 5 standard + custom creation

**Output**: RoadTestScenario object

### 2. OTA Mapper (Hardware Translation)
**Purpose**: Convert scenarios to hardware commands
- Input: RoadTestScenario
- Process: Calculate probe weights, positioner sequence, Doppler
- ChannelEngine integration: 32-probe MPAC configuration
- Output: OTAConfig

### 3. Test Management (Execution Orchestration)
**Purpose**: Orchestrate test execution
- Test plans with steps
- Execution queue with priority
- Real-time monitoring
- History and analytics

**Output**: TestExecution records

## Integration Points

### Point 1: Scenario → OTA Config
**When**: User selects OTA mode in Virtual Road Test
**Flow**:
```python
# Backend: app/services/road_test/ota_scenario_mapper.py
scenario = get_scenario_by_id(scenario_id)
ota_config = OTAScenarioMapper.map_scenario(
    scenario=scenario,
    probe_array=probe_array_config,
    mimo_config=mimo_config
)
# Calls ChannelEngine: POST /api/v1/ota/generate-probe-weights
```

### Point 2: Scenario → Test Plan (PLANNED - Phase 4)
**When**: User clicks "Convert to Test Plan" in Scenario card
**Flow**:
```typescript
// Frontend: ScenarioCard.tsx
const handleConvertToTestPlan = () => {
  const testPlan = {
    name: scenario.name,
    description: scenario.description,
    dut_info: { model: 'Auto', serial: 'TBD' },
    test_environment: {
      channel_model: scenario.environment.channel_model,
      route_duration: scenario.route.duration_s
    },
    steps: generateStepsFromScenario(scenario)
  }
  createTestPlan(testPlan)
  navigate('/test-management/plans')
}
```

**Step Generation Logic**:
```typescript
function generateStepsFromScenario(scenario: RoadTestScenario): TestStep[] {
  return [
    {
      order: 1,
      sequence_library_id: 'seq-init-chamber',
      parameters: { ... }
    },
    {
      order: 2,
      sequence_library_id: 'seq-configure-network',
      parameters: {
        band: scenario.network.band,
        bandwidth: scenario.network.bandwidth_mhz
      }
    },
    {
      order: 3,
      sequence_library_id: 'seq-run-route',
      parameters: {
        waypoints: scenario.route.waypoints,
        duration: scenario.route.duration_s
      }
    },
    // ... more steps
  ]
}
```

### Point 3: OTA Config → Test Execution
**When**: Test plan contains OTA scenario step
**Flow**:
```python
# During test execution
for step in test_plan.steps:
    if step.sequence_library_id == 'seq-run-ota-scenario':
        scenario_id = step.parameters['scenario_id']
        ota_config = OTAScenarioMapper.map_scenario(...)

        # Send to MPAC controller
        mpac.configure_probes(ota_config.probe_weights)
        mpac.set_positioner_sequence(ota_config.positioner_sequence)

        # Execute test
        execute_test_step(step, ota_config)
```

## User Workflows

### Workflow 1: Quick Road Test (Current)
1. Virtual Road Test → Select mode
2. Choose scenario from library
3. Click "Run Test"
4. TestExecutionModal shows progress
5. View results

### Workflow 2: Custom OTA Test (Current)
1. Virtual Road Test → OTA mode
2. Select scenario
3. OTA Mapper opens → Configure probes
4. Generate weights (calls ChannelEngine)
5. Execute test with MPAC

### Workflow 3: Integrated Test Plan (Phase 4 - Planned)
1. Virtual Road Test → Select scenario
2. Click "Convert to Test Plan"
3. Test Management opens with pre-filled plan
4. User edits/adds steps
5. Add to queue → Execute
6. Results in History tab

## Data Model Relationships

```
RoadTestScenario
    ├── scenario_id (primary key)
    ├── route (waypoints, duration, distance)
    ├── environment (channel_model, weather)
    └── network (band, bandwidth, duplex_mode)

OTAConfig (derived from scenario)
    ├── positioner_sequence
    ├── probe_weights [32]
    ├── channel_model_name
    └── max_doppler_hz

TestPlan
    ├── plan_id (primary key)
    ├── scenario_id (foreign key - PLANNED)
    ├── steps []
    │   └── parameters (can include scenario_id)
    └── execution_records []
```

## Implementation Roadmap

### Phase 4.1: Scenario → TestPlan Conversion
- [ ] Add "Convert to Test Plan" button to ScenarioCard
- [ ] Implement generateStepsFromScenario() logic
- [ ] Add scenario_id FK to TestPlan model
- [ ] Create sequence templates for road test steps

### Phase 4.2: Test Plan → Scenario Linking
- [ ] Show linked scenario in TestPlan details
- [ ] Allow editing scenario from TestPlan
- [ ] Scenario changes trigger TestPlan update prompt

### Phase 4.3: OTA Execution Integration
- [ ] Add OTA step executor in TestExecutionService
- [ ] Integrate OTAScenarioMapper into execution flow
- [ ] Real-time monitoring of OTA tests

## Open Questions

1. **Scenario Reusability**: Should multiple test plans share same scenario?
   - Proposed: Yes, via foreign key reference

2. **Parameter Override**: Can test plan override scenario parameters?
   - Proposed: Yes, step parameters take precedence

3. **Scenario Versioning**: Track scenario changes over time?
   - Proposed: Phase 5 feature, use semantic versioning

4. **OTA Config Caching**: Cache probe weights to avoid recalculation?
   - Proposed: Yes, cache by (scenario_id, mimo_config) key

## See Also
- Virtual Road Test: `/docs/architecture/VirtualRoadTest-Complete.md`
- Test Management: `/docs/architecture/TestManagement-Unified-Architecture.md`
- OTA Mapper: `/docs/design/testing/Hybrid-Test-Framework-Design.md`
```

---

## Execution Timeline

### Week 1: Preparation
- [ ] Review and approve this plan
- [ ] Create `/docs/archive/` folder structure
- [ ] Backup current doc state (git tag `pre-reorg`)

### Week 2: Archive & Delete
- [ ] Execute PHASE 1: Archive 10 completed docs
- [ ] Execute PHASE 3: Delete 4 stub files
- [ ] Update inter-doc links

### Week 3: Merge & Create
- [ ] Execute PHASE 2: Merge redundant docs (5 merges)
- [ ] Execute PHASE 6: Create 3 new consolidated docs
- [ ] Review and test all links

### Week 4: Update
- [ ] Execute PHASE 4: Update 10 outdated docs
- [ ] Execute PHASE 5: Expand 3 incomplete stubs
- [ ] Final review and cleanup

### Week 5: Validation
- [ ] Test all documentation links
- [ ] Update README with new structure
- [ ] Create CHANGELOG entry
- [ ] Git tag `post-reorg-v1.0`

---

## Success Metrics

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Total files | 64 | ~48 | 25% reduction |
| Root files | 33 | 4 | 88% reduction |
| Outdated docs | 10 | 0 | 100% accuracy |
| Redundant files | 9 | 0 | 100% elimination |
| Progress tracking | 6% | 40% | Accurate |
| Nav structure | Flat | 3-level | Clear hierarchy |

---

## Risk Mitigation

### Risk 1: Broken Links
**Mitigation**:
- Search all .md files for old paths before moving
- Update links atomically with moves
- Test all links with link checker

### Risk 2: Lost Content
**Mitigation**:
- Git backup tag before starting
- Archive instead of delete where possible
- Code review for all deletions

### Risk 3: Team Confusion
**Mitigation**:
- Announce plan in team meeting
- Create MIGRATION-GUIDE.md
- Keep old structure for 1 sprint in archive

---

## Next Steps

1. **Decision Point**: Approve this plan (GO/NO-GO)
2. **If GO**: Assign to Simon for execution
3. **Timeline**: 5 weeks (2025-12-03 to 2026-01-07)
4. **Review Checkpoint**: End of Week 3 (merge/create complete)
5. **Final Review**: End of Week 5 (all updates complete)

---

## Appendix A: File Movement Checklist

[Detailed checklist for each of 64 files will be added during execution]

## Appendix B: Link Update Log

[Log of all inter-document link updates will be maintained here]

## Appendix C: Deleted Content Archive

[Index of deleted content with justification for each]
