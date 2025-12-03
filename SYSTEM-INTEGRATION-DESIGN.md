# MIMO-First System Integration Design
**Version**: 1.0
**Date**: 2025-12-03
**Status**: APPROVED - Phase 4 Implementation Plan

---

## Executive Summary

This document defines how **Virtual Road Test**, **OTA Mapper**, and **Test Management** integrate to create a unified testing workflow for the MIMO-First OTA test system.

**Key Decision**: Implement **Option B** - Allow Road Test scenarios to convert into Test Plans, enabling scenario reuse and reducing configuration effort.

---

## 1. Three-System Overview

### 1.1 Virtual Road Test (Scenario Definition Layer)

**Purpose**: Define **what to test**

**Components**:
- **Scenario Library**: 5 standard scenarios (Urban, Highway, Tunnel, Cell Edge, Beam Switching)
- **Custom Scenario Creator**: User-defined scenarios with network config, route, environment
- **Mode Selector**: Digital Twin / Conducted / OTA

**Data Model**: `RoadTestScenario`
```python
class RoadTestScenario:
    id: str
    name: str
    category: ScenarioCategory  # standard, functional, performance, etc.
    source: ScenarioSource      # standard, custom

    # Test Configuration
    network: NetworkConfig      # type, band, bandwidth, duplex
    base_stations: List[BaseStationConfig]  # positions, TX power
    route: Route               # waypoints, duration, distance
    environment: Environment   # channel_model, weather
    traffic: TrafficConfig     # type, direction, data_rate

    # Test Events
    events: List[ScenarioEvent]  # handover, beam switch, impairment
    kpi_definitions: List[KPIDefinition]  # throughput, latency targets
```

**User Actions**:
- Browse scenario library
- Create custom scenarios
- Run test (opens TestExecutionModal)
- View details (opens ScenarioDetailModal)
- **[NEW]** Convert to Test Plan

**Output**: `RoadTestScenario` object

---

### 1.2 OTA Mapper (Hardware Translation Layer)

**Purpose**: Convert scenarios to **hardware control commands**

**Process**:
```
RoadTestScenario
    ↓ (Input)
OTAScenarioMapper.map_scenario()
    ├─→ Map environment → 3GPP channel model
    ├─→ Calculate max Doppler from velocity
    ├─→ Generate positioner sequence (azimuth/elevation)
    └─→ Call ChannelEngine: calculate 32-probe weights
    ↓ (Output)
OTAConfig
```

**Data Model**: `OTAConfig`
```python
class OTAConfig:
    positioner_sequence: List[Dict]  # {time_s, azimuth_deg, elevation_deg}
    channel_model: str               # "3GPP_38.901_UMa"
    max_doppler_hz: float
    probe_weights: List[ProbeWeight]  # 32 probes: {probe_id, amplitude, phase_deg, polarization}
    fading_enabled: bool
```

**ChannelEngine Integration**:
```python
# app/services/road_test/ota_scenario_mapper.py

def _calculate_probe_weights(self, scenario, probe_array, mimo_config):
    """Call ChannelEngine service to compute probe weights"""
    response = requests.post(
        "http://localhost:8000/api/v1/ota/generate-probe-weights",
        json={
            "scenario": scenario.dict(),
            "probe_array": probe_array.dict(),
            "mimo_config": mimo_config.dict()
        }
    )
    return response.json()["probe_weights"]
```

**User Actions**:
- Configure MIMO settings (antenna config, spacing)
- Select probe array layout (32-probe MPAC)
- Generate weights (calls ChannelEngine)
- View weight visualization

**Output**: `OTAConfig` for MPAC controller

---

### 1.3 Test Management (Execution Orchestration Layer)

**Purpose**: Orchestrate **how to test**

**Components**:
- **Plans Tab**: Test plan CRUD, lifecycle management
- **Steps Tab**: Step sequence editor with drag-drop reordering
- **Queue Tab**: Execution queue with priority scheduling
- **History Tab**: Execution records and analytics

**Data Model**: `TestPlan`
```python
class TestPlan:
    id: UUID
    name: str
    status: TestPlanStatus  # draft, ready, queued, running, completed, failed
    version: str
    priority: int  # 1-10

    # Configuration
    dut_info: DUTInfo           # model, serial, IMEI
    test_environment: TestEnvironment  # chamber_id, temperature

    # Test Steps
    steps: List[TestStep]       # Ordered execution sequence

    # Linking (NEW - Phase 4)
    scenario_id: Optional[str]  # Link to RoadTestScenario

    # Execution State
    queue_position: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    actual_duration_minutes: float
```

**TestStep Model**:
```python
class TestStep:
    id: UUID
    plan_id: UUID
    order: int
    sequence_library_id: UUID  # Template from sequence library
    name: str
    parameters: Dict[str, StepParameter]  # Configurable parameters
    timeout_seconds: int
    continue_on_failure: bool
    status: StepStatus  # pending, running, passed, failed, skipped
```

**User Actions**:
- Create test plan
- Add/edit/reorder steps
- Configure step parameters
- Add to execution queue
- Start/pause/cancel execution
- View execution history

**Output**: `TestExecution` records with results

---

## 2. Integration Architecture

### 2.1 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                 USER WORKFLOW                                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ↓
        ┌──────────────────────────────────────┐
        │   1. Virtual Road Test               │
        │   (Scenario Definition)              │
        │                                      │
        │   - Browse scenario library          │
        │   - Create custom scenario           │
        │   - Select test mode                 │
        └──────────┬───────────────────────────┘
                   │
                   ├─────────────────┐
                   │                 │
                   ↓                 ↓
    ┌──────────────────────┐  ┌──────────────────────┐
    │   2a. OTA Mapper     │  │  2b. Convert to      │
    │   (If OTA mode)      │  │  Test Plan (NEW)     │
    │                      │  │                      │
    │   - Configure MIMO   │  │  - Generate steps    │
    │   - Call CE          │  │  - Fill parameters   │
    │   - Get probe wts    │  │  - Link scenario     │
    └──────────┬───────────┘  └──────────┬───────────┘
               │                         │
               │                         ↓
               │              ┌──────────────────────┐
               │              │   3. Test Management │
               │              │   (Orchestration)    │
               │              │                      │
               │              │   - Edit plan/steps  │
               │              │   - Add to queue     │
               └──────────────┤   - Execute          │
                              │   - Monitor          │
                              │   - View results     │
                              └──────────┬───────────┘
                                         │
                                         ↓
                              ┌──────────────────────┐
                              │   4. Test Execution  │
                              │                      │
                              │   For OTA steps:     │
                              │   - Load OTAConfig   │
                              │   - Control MPAC     │
                              │   - Collect data     │
                              └──────────────────────┘
```

### 2.2 Integration Points

#### **Integration Point 1: Scenario → OTA Config**

**When**: User selects OTA mode in Virtual Road Test

**Frontend Flow**:
```typescript
// gui/src/components/VirtualRoadTest/index.tsx

const handleModeSelect = (mode: TestMode) => {
  if (mode === 'ota') {
    setShowOTAMapper(true)
  }
}

// OTAMapper component
const handleGenerateWeights = async () => {
  const response = await channelEngineClient.generateProbeWeights({
    scenario: selectedScenario,
    probe_array: probeArrayConfig,
    mimo_config: mimoConfig
  })
  setProbeWeights(response.probe_weights)
}
```

**Backend Flow**:
```python
# api-service/app/services/road_test/ota_scenario_mapper.py

class OTAScenarioMapper:
    def map_scenario(
        self,
        scenario: RoadTestScenario,
        probe_array: ProbeArrayConfig,
        mimo_config: MIMOConfig
    ) -> OTAConfig:
        # 1. Map channel model
        channel_model_name = self._map_channel_model(scenario.environment.channel_model)

        # 2. Calculate Doppler
        max_doppler = self._calculate_max_doppler(scenario)

        # 3. Generate positioner sequence
        positioner_seq = self._generate_positioner_sequence(scenario.route)

        # 4. Calculate probe weights (calls ChannelEngine)
        probe_weights = self._calculate_probe_weights(scenario, probe_array, mimo_config)

        return OTAConfig(
            positioner_sequence=positioner_seq,
            channel_model=channel_model_name,
            max_doppler_hz=max_doppler,
            probe_weights=probe_weights,
            fading_enabled=True
        )
```

**Key API**:
```
POST /api/v1/ota/generate-probe-weights
Body: {
  scenario: RoadTestScenario,
  probe_array: ProbeArrayConfig,
  mimo_config: MIMOConfig
}
Response: {
  probe_weights: [
    {probe_id: 1, amplitude: 0.8, phase_deg: 45, polarization: "V"},
    ...
  ]
}
```

---

#### **Integration Point 2: Scenario → Test Plan** (NEW - Phase 4)

**When**: User clicks "Convert to Test Plan" in ScenarioCard

**UI Changes**:
```typescript
// gui/src/components/VirtualRoadTest/ScenarioCard.tsx

// Add new button
<Button
  variant="outline"
  leftSection={<IconTransform size={14} />}
  onClick={handleConvertToTestPlan}
>
  Convert to Test Plan
</Button>

// Handler
const handleConvertToTestPlan = async () => {
  try {
    // 1. Generate test plan from scenario
    const testPlan = generateTestPlanFromScenario(scenario)

    // 2. Create test plan via API
    const created = await createTestPlan(testPlan)

    // 3. Navigate to Test Management
    notifications.show({
      title: 'Test Plan Created',
      message: `Created plan "${created.name}" with ${testPlan.steps.length} steps`,
      color: 'green'
    })
    navigate(`/test-management/plans?id=${created.id}`)
  } catch (error) {
    notifications.show({
      title: 'Error',
      message: 'Failed to create test plan',
      color: 'red'
    })
  }
}
```

**Step Generation Logic**:
```typescript
// gui/src/utils/scenarioToTestPlan.ts

export function generateTestPlanFromScenario(
  scenario: RoadTestScenario
): CreateTestPlanRequest {
  return {
    name: `${scenario.name} - Test Plan`,
    description: scenario.description || '',
    version: '1.0',
    priority: 5,

    // Link to source scenario
    scenario_id: scenario.id,

    // Extract DUT info (user will complete)
    dut_info: {
      model: 'TBD',
      serial_number: 'TBD',
      imei: null
    },

    // Copy environment settings
    test_environment: {
      chamber_id: 'MPAC-1',
      temperature_c: 25,
      humidity_percent: 50,
      channel_model: scenario.environment.channel_model,
      route_type: scenario.route.type
    },

    // Generate steps from scenario
    steps: [
      // Step 1: Initialize chamber
      {
        order: 1,
        sequence_library_id: getSequenceId('init-chamber'),
        name: 'Initialize OTA Chamber',
        parameters: {
          chamber_id: 'MPAC-1',
          probe_count: 32
        },
        timeout_seconds: 300,
        continue_on_failure: false
      },

      // Step 2: Configure network
      {
        order: 2,
        sequence_library_id: getSequenceId('configure-network'),
        name: 'Configure Network',
        parameters: {
          network_type: scenario.network.type,
          band: scenario.network.band,
          bandwidth_mhz: scenario.network.bandwidth_mhz,
          duplex_mode: scenario.network.duplex_mode,
          scs_khz: scenario.network.scs_khz
        },
        timeout_seconds: 180,
        continue_on_failure: false
      },

      // Step 3: Setup base stations
      {
        order: 3,
        sequence_library_id: getSequenceId('setup-base-stations'),
        name: 'Setup Base Stations',
        parameters: {
          base_stations: scenario.base_stations.map(bs => ({
            bs_id: bs.bs_id,
            position: bs.position,
            tx_power_dbm: bs.tx_power_dbm,
            antenna_config: bs.antenna_config
          }))
        },
        timeout_seconds: 240,
        continue_on_failure: false
      },

      // Step 4: Configure OTA mapper
      {
        order: 4,
        sequence_library_id: getSequenceId('configure-ota'),
        name: 'Configure OTA Mapper',
        parameters: {
          scenario_id: scenario.id,
          channel_model: scenario.environment.channel_model,
          max_velocity_kmh: getMaxVelocity(scenario.route),
          probe_array_type: '32-probe-sphere'
        },
        timeout_seconds: 300,
        continue_on_failure: false
      },

      // Step 5: Run route test
      {
        order: 5,
        sequence_library_id: getSequenceId('run-route-test'),
        name: 'Execute Route Test',
        parameters: {
          waypoints: scenario.route.waypoints,
          duration_s: scenario.route.duration_s,
          total_distance_m: scenario.route.total_distance_m,
          traffic_type: scenario.traffic.type,
          traffic_direction: scenario.traffic.direction,
          data_rate_mbps: scenario.traffic.data_rate_mbps
        },
        timeout_seconds: scenario.route.duration_s + 120,  // Add buffer
        continue_on_failure: false
      },

      // Step 6: Validate KPIs
      {
        order: 6,
        sequence_library_id: getSequenceId('validate-kpis'),
        name: 'Validate KPIs',
        parameters: {
          kpi_definitions: scenario.kpi_definitions.map(kpi => ({
            type: kpi.kpi_type,
            target_value: kpi.target_value,
            unit: kpi.unit,
            threshold_min: kpi.threshold_min,
            threshold_max: kpi.threshold_max,
            percentile: kpi.percentile
          }))
        },
        timeout_seconds: 180,
        continue_on_failure: true  // Allow test to complete even if KPIs not met
      },

      // Step 7: Generate report
      {
        order: 7,
        sequence_library_id: getSequenceId('generate-report'),
        name: 'Generate Test Report',
        parameters: {
          include_plots: true,
          include_raw_data: false,
          format: 'PDF'
        },
        timeout_seconds: 300,
        continue_on_failure: true
      }
    ]
  }
}

function getMaxVelocity(route: Route): number {
  if (route.waypoints.length === 0) return 0
  return Math.max(...route.waypoints.map(wp => wp.velocity.speed_kmh))
}

function getSequenceId(sequence_name: string): UUID {
  // Lookup sequence ID from sequence library
  const sequences = useSequenceLibrary()
  return sequences.find(s => s.name === sequence_name)?.id || null
}
```

**Backend API**:
```python
# api-service/app/api/test_plan.py

@router.post("/test-plans", response_model=TestPlan, status_code=201)
async def create_test_plan(plan_data: CreateTestPlanRequest):
    """Create test plan, optionally linked to a scenario"""

    # Validate scenario_id if provided
    if plan_data.scenario_id:
        scenario = get_scenario_by_id(plan_data.scenario_id)
        if not scenario:
            raise HTTPException(404, f"Scenario {plan_data.scenario_id} not found")

    # Create test plan
    plan = TestPlanService.create(plan_data)

    # Create steps
    for step_data in plan_data.steps:
        TestStepService.create(plan.id, step_data)

    return plan
```

**Database Schema Update**:
```sql
-- Migration: Add scenario_id foreign key to test_plans table

ALTER TABLE test_plans
ADD COLUMN scenario_id VARCHAR(255) REFERENCES road_test_scenarios(id);

CREATE INDEX idx_test_plans_scenario_id ON test_plans(scenario_id);
```

---

#### **Integration Point 3: Test Execution with OTA Config**

**When**: Test plan contains OTA scenario step

**Execution Flow**:
```python
# api-service/app/services/test_execution_service.py

class TestExecutionService:
    async def execute_plan(self, plan_id: UUID):
        """Execute test plan with all steps"""
        plan = TestPlanService.get(plan_id)

        # Update status
        plan.status = TestPlanStatus.RUNNING
        plan.started_at = datetime.now()

        # Execute steps in order
        for step in sorted(plan.steps, key=lambda s: s.order):
            try:
                # Check if step is OTA-related
                if step.sequence_library_id in OTA_SEQUENCE_IDS:
                    result = await self._execute_ota_step(plan, step)
                else:
                    result = await self._execute_standard_step(step)

                step.status = StepStatus.PASSED if result.success else StepStatus.FAILED

                if not result.success and not step.continue_on_failure:
                    break

            except Exception as e:
                step.status = StepStatus.FAILED
                step.error_message = str(e)
                if not step.continue_on_failure:
                    break

        # Finalize
        plan.status = TestPlanStatus.COMPLETED
        plan.completed_at = datetime.now()
        plan.actual_duration_minutes = (plan.completed_at - plan.started_at).total_seconds() / 60

        return plan

    async def _execute_ota_step(self, plan: TestPlan, step: TestStep):
        """Execute OTA-specific test step"""

        # Get linked scenario
        if plan.scenario_id:
            scenario = get_scenario_by_id(plan.scenario_id)
        else:
            # Fallback: get scenario from step parameters
            scenario_id = step.parameters.get('scenario_id')
            scenario = get_scenario_by_id(scenario_id)

        # Map scenario to OTA config
        ota_config = OTAScenarioMapper.map_scenario(
            scenario=scenario,
            probe_array=step.parameters['probe_array'],
            mimo_config=step.parameters['mimo_config']
        )

        # Send to MPAC controller
        mpac = MPACController()
        mpac.configure_probes(ota_config.probe_weights)
        mpac.set_positioner_sequence(ota_config.positioner_sequence)
        mpac.set_channel_model(ota_config.channel_model)
        mpac.set_doppler(ota_config.max_doppler_hz)

        # Execute test
        result = await mpac.execute(
            duration_s=step.parameters['duration_s'],
            waypoints=step.parameters['waypoints']
        )

        # Collect results
        metrics = mpac.get_metrics()

        return ExecutionResult(
            success=result.status == 'completed',
            metrics=metrics,
            logs=result.logs
        )
```

---

## 3. User Workflows

### Workflow 1: Quick Road Test (Current - Implemented)

```
User Journey:
1. Navigate to Virtual Road Test
2. Select test mode (Digital Twin / Conducted / OTA)
3. Browse Scenario Library
4. Select scenario (e.g., "Urban Street Test")
5. Click "Run Test"
6. TestExecutionModal opens
   - Shows 7-phase execution progress
   - Real-time status updates
   - Timeline visualization
7. Test completes
8. Click "View Report"
9. Results displayed

Status: ✅ IMPLEMENTED
Components: VirtualRoadTest, ScenarioLibrary, TestExecutionModal
```

---

### Workflow 2: Custom OTA Test with Mapper (Current - Implemented)

```
User Journey:
1. Navigate to Virtual Road Test
2. Select "OTA" mode
3. Browse Scenario Library or create custom scenario
4. Select scenario
5. OTA Mapper panel opens
   - Configure MIMO (TX/RX antennas, spacing, polarization)
   - Select probe array (32-probe MPAC)
   - Click "Generate Weights"
6. ChannelEngine calculates probe weights
7. Weight visualization displayed (32 probes with amplitude/phase)
8. Click "Apply Configuration"
9. Test executes with MPAC
10. Results collected

Status: ✅ IMPLEMENTED
Components: VirtualRoadTest, OTAMapper, ChannelEngine integration
```

---

### Workflow 3: Scenario-to-TestPlan Integration (Phase 4 - PLANNED)

```
User Journey:
1. Navigate to Virtual Road Test → Scenario Library
2. Browse or create custom scenario
3. Click "Convert to Test Plan" button (NEW)
4. System generates test plan:
   - 7 steps automatically created
   - Parameters pre-filled from scenario
   - Scenario linked to plan
5. Navigates to Test Management → Plans Tab
6. Plan opens in edit mode
7. User reviews and customizes:
   - Fill in DUT info (model, serial, IMEI)
   - Adjust step parameters if needed
   - Add additional steps (e.g., RF calibration)
   - Set step timeouts
8. Click "Save" → Plan status = "Draft"
9. Click "Mark as Ready" → Plan status = "Ready"
10. Click "Add to Queue"
    - Set priority (1-10)
    - Optional: Add dependencies
    - Optional: Schedule time
11. Queue Tab shows plan in queue
12. Click "Start" → Execution begins
13. Real-time monitoring:
    - Current step highlighted
    - Progress bar per step
    - Live metrics dashboard
14. Test completes
15. History Tab shows execution record
    - Duration, status, pass/fail
    - Per-step results
    - KPI validation
16. Click "View Report" → Detailed analytics

Status: 📋 PLANNED (Phase 4)
New Components:
- ConvertToTestPlanButton in ScenarioCard
- generateTestPlanFromScenario() utility
- scenario_id FK in TestPlan model
- OTA step executor in TestExecutionService
```

---

### Workflow 4: Iterative Testing (Phase 4+)

```
User Journey:
1. User runs test plan (converted from scenario)
2. Test fails at Step 5 (Execute Route Test)
3. User reviews logs → identifies issue
4. User clicks on linked scenario in Test Plan
5. Scenario detail modal opens
6. User edits scenario:
   - Adjusts route waypoints
   - Changes channel model
   - Updates KPI thresholds
7. System prompts: "Update linked test plan?"
8. User confirms
9. Test plan steps auto-update with new parameters
10. User re-runs test
11. Test passes

Status: 🔮 FUTURE (Phase 5)
Requires:
- Bi-directional scenario ↔ plan linking
- Scenario versioning
- Change propagation logic
```

---

## 4. Data Model Integration

### 4.1 Database Schema

```sql
-- Road Test Scenarios
CREATE TABLE road_test_scenarios (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    description TEXT,

    -- JSON columns for complex data
    network_config JSONB NOT NULL,
    base_stations JSONB NOT NULL,
    route JSONB NOT NULL,
    environment JSONB NOT NULL,
    traffic JSONB NOT NULL,
    events JSONB,
    kpi_definitions JSONB NOT NULL,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    author VARCHAR(255),
    version VARCHAR(50) DEFAULT '1.0'
);

-- Test Plans (with scenario linking)
CREATE TABLE test_plans (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL,
    version VARCHAR(50),
    priority INTEGER DEFAULT 5,

    -- Linking to scenario (NEW)
    scenario_id VARCHAR(255) REFERENCES road_test_scenarios(id) ON DELETE SET NULL,

    -- Configuration
    dut_info JSONB,
    test_environment JSONB,

    -- Execution state
    queue_position INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    actual_duration_minutes FLOAT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Test Steps
CREATE TABLE test_steps (
    id UUID PRIMARY KEY,
    plan_id UUID REFERENCES test_plans(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    sequence_library_id UUID,
    name VARCHAR(255) NOT NULL,
    parameters JSONB,
    timeout_seconds INTEGER DEFAULT 300,
    continue_on_failure BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(plan_id, order_index)
);

-- Indexes
CREATE INDEX idx_test_plans_scenario_id ON test_plans(scenario_id);
CREATE INDEX idx_test_plans_status ON test_plans(status);
CREATE INDEX idx_test_steps_plan_id ON test_steps(plan_id);
CREATE INDEX idx_test_steps_order ON test_steps(plan_id, order_index);
```

### 4.2 Pydantic Models

```python
# app/schemas/integration.py

from pydantic import BaseModel, UUID4
from typing import Optional, List
from app.schemas.road_test import RoadTestScenario
from app.schemas.test_plan import TestPlan, TestStep

class CreateTestPlanRequest(BaseModel):
    """Create test plan from scenario"""
    name: str
    description: Optional[str] = None
    version: str = "1.0"
    priority: int = 5

    # Scenario linking
    scenario_id: Optional[str] = None

    # Configuration
    dut_info: DUTInfo
    test_environment: TestEnvironment

    # Steps
    steps: List[CreateTestStepRequest]

class TestPlanWithScenario(TestPlan):
    """Extended test plan with scenario info"""
    scenario: Optional[RoadTestScenario] = None  # Eager-loaded

class ScenarioUsageInfo(BaseModel):
    """Track where a scenario is used"""
    scenario_id: str
    scenario_name: str
    test_plans: List[TestPlanSummary]
    usage_count: int
```

---

## 5. Implementation Roadmap

### Phase 4.1: Basic Scenario-to-Plan Conversion (2 weeks)

**Tasks**:
- [ ] Add `scenario_id` column to `test_plans` table (migration)
- [ ] Create `scenarioToTestPlan.ts` utility
- [ ] Add "Convert to Test Plan" button to `ScenarioCard`
- [ ] Implement `generateTestPlanFromScenario()` logic
- [ ] Update `createTestPlan` API to accept `scenario_id`
- [ ] Add step generation for 7 standard steps
- [ ] Create sequence templates in sequence library
- [ ] Test end-to-end flow

**Acceptance Criteria**:
- User can convert scenario to test plan with 1 click
- Generated plan has 7 steps with correct parameters
- Plan correctly links to source scenario
- User can edit generated plan before execution

---

### Phase 4.2: OTA Execution Integration (2 weeks)

**Tasks**:
- [ ] Implement `_execute_ota_step()` in `TestExecutionService`
- [ ] Add OTA sequence IDs to step templates
- [ ] Integrate `OTAScenarioMapper` into execution flow
- [ ] Add MPAC controller interface
- [ ] Implement probe weight configuration
- [ ] Add positioner control
- [ ] Add real-time monitoring for OTA tests
- [ ] Test with mock MPAC hardware

**Acceptance Criteria**:
- Test plan can execute OTA steps
- OTA config correctly applied to MPAC
- Real-time status updates during execution
- Metrics collected and stored

---

### Phase 4.3: Bi-directional Linking (1 week)

**Tasks**:
- [ ] Add "View Linked Scenario" button in TestPlan detail
- [ ] Add "Used in Test Plans" section in ScenarioDetail
- [ ] Implement `GET /scenarios/{id}/usage` endpoint
- [ ] Add cascade behavior for scenario updates
- [ ] Prompt user when scenario changes affect plans

**Acceptance Criteria**:
- User can navigate from plan → scenario
- User can see all plans using a scenario
- Warning shown when editing linked scenario

---

### Phase 4.4: Parameter Override (1 week)

**Tasks**:
- [ ] Allow step parameters to override scenario values
- [ ] Add "Use Scenario Value" checkbox in step editor
- [ ] Implement parameter merge logic
- [ ] Add validation for overridden parameters

**Acceptance Criteria**:
- Step parameters can override scenario defaults
- Clear UI indication of overrides
- Validation prevents invalid overrides

---

### Phase 4.5: Testing & Documentation (1 week)

**Tasks**:
- [ ] Write unit tests for conversion logic
- [ ] Add E2E test: scenario → plan → execution
- [ ] Update user documentation
- [ ] Create video tutorial
- [ ] Performance testing (large scenarios)

**Acceptance Criteria**:
- 95% test coverage for new code
- E2E test passes consistently
- Documentation complete and reviewed

---

## 6. Open Questions & Decisions

### Q1: Should multiple test plans share the same scenario?

**Answer**: **YES** (Reference relationship)

**Rationale**:
- Scenarios are reusable templates
- Multiple teams may use same scenario
- Changes to scenario can propagate to all plans

**Implementation**: Foreign key with cascade options

---

### Q2: Can test plan override scenario parameters?

**Answer**: **YES** (Step parameters take precedence)

**Rationale**:
- Flexibility for edge cases
- Allow tuning without modifying scenario
- Preserve scenario as "baseline"

**Example**:
```
Scenario: bandwidth_mhz = 100
Step 2 Override: bandwidth_mhz = 50
Actual Used: 50 MHz
```

---

### Q3: Should scenarios be versioned?

**Answer**: **Phase 5 feature** (Semantic versioning)

**Rationale**:
- Essential for reproducibility
- Allows regression testing
- Tracks evolution of test definitions

**Proposed Schema**:
```python
class ScenarioVersion(BaseModel):
    scenario_id: str
    version: str  # "1.2.3"
    changes: str  # Changelog
    created_at: datetime
```

---

### Q4: Should OTA config be cached?

**Answer**: **YES** (Cache by (scenario_id, mimo_config) key)

**Rationale**:
- ChannelEngine calculation expensive (5-10s)
- Same scenario + config → same weights
- Cache valid until scenario changes

**Implementation**:
```python
# Redis cache
cache_key = f"ota_config:{scenario_id}:{mimo_config.hash()}"
cached = redis.get(cache_key)
if cached:
    return OTAConfig.parse_raw(cached)
else:
    config = OTAScenarioMapper.map_scenario(...)
    redis.setex(cache_key, 3600, config.json())  # 1 hour TTL
    return config
```

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Conversion Success Rate | > 95% | % of conversions without errors |
| Generated Plan Accuracy | > 90% | % of plans executable without edits |
| User Time Savings | > 50% | Time to create plan: manual vs. auto |
| OTA Execution Success | > 85% | % of OTA tests completing successfully |
| Scenario Reuse Rate | > 3x | Avg # of plans per scenario |

---

## 8. See Also

- **Virtual Road Test**: [VirtualRoadTest-Complete.md](docs/architecture/VirtualRoadTest-Complete.md)
- **Test Management**: [TestManagement-Unified-Architecture.md](TestManagement-Unified-Architecture.md)
- **OTA Mapper**: [Hybrid-Test-Framework-Design.md](docs/design/testing/Hybrid-Test-Framework-Design.md)
- **API Reference**: [API-DESIGN-GUIDE.md](API-DESIGN-GUIDE.md)
- **Database Migrations**: [api-service/alembic/versions/](api-service/alembic/versions/)

---

## 9. Approval & Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| System Architect | Simon | 2025-12-03 | _Approved_ |
| Technical Lead | TBD | - | - |
| QA Lead | TBD | - | - |

**Status**: ✅ APPROVED - Proceed to Phase 4.1 Implementation
