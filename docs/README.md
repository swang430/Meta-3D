# Meta-3D Documentation

## Quick Navigation

| Category | Description |
|----------|-------------|
| [architecture/](architecture/) | System architecture and design |
| [features/](features/) | Feature modules |
| [hardware/](hardware/) | Hardware abstraction layer |
| [api/](api/) | API documentation |
| [guides/](guides/) | Development guides |
| [archive/](archive/) | Historical documents |

---

## Architecture

| Document | Description |
|----------|-------------|
| [system-overview](architecture/system-overview.md) | System architecture overview |
| [data-architecture](architecture/data-architecture.md) | Data model and storage |
| [data-acquisition](architecture/data-acquisition.md) | Data acquisition design |
| [data-storage](architecture/data-storage.md) | Data storage design |
| [hardware-sync](architecture/hardware-sync.md) | Hardware synchronization |
| [system-integration](architecture/system-integration.md) | System integration design |
| [system-configuration](architecture/system-configuration.md) | System configuration |
| [system-synchronization](architecture/system-synchronization.md) | System synchronization |

---

## Features

### Virtual Road Test

| Document | Description |
|----------|-------------|
| [**parameter-reference**](features/virtual-road-test/parameter-reference.md) | **All parameters at a glance (manual)** |
| [parameter-reference-generated](features/virtual-road-test/parameter-reference-generated.md) | Auto-generated from schemas |
| [overview](features/virtual-road-test/overview.md) | Virtual road test overview |
| [architecture](features/virtual-road-test/architecture.md) | Architecture design |
| [implementation](features/virtual-road-test/implementation.md) | Implementation details |
| [scenario-design](features/virtual-road-test/scenario-design.md) | Scenario design guide |
| [step-configuration](features/virtual-road-test/step-configuration.md) | Test step configuration |
| [scenario-library](features/virtual-road-test/scenario-library.md) | Standard scenario library |
| [custom-scenario](features/virtual-road-test/custom-scenario.md) | Custom scenario creation |

### Calibration

| Document | Description |
|----------|-------------|
| [system-calibration](features/calibration/system-calibration.md) | System calibration |
| [probe-calibration](features/calibration/probe-calibration.md) | Probe calibration |
| [channel-calibration](features/calibration/channel-calibration.md) | Channel calibration |

### Test Management

| Document | Description |
|----------|-------------|
| [unified-architecture](features/test-management/unified-architecture.md) | Unified test management |
| [execution-engine](features/test-management/execution-engine.md) | Test execution engine |
| [monitoring](features/test-management/monitoring.md) | Test monitoring |
| [workflow-templates](features/test-management/workflow-templates.md) | Workflow templates |
| [hybrid-framework](features/test-management/hybrid-framework.md) | Hybrid test framework |

---

## Hardware Abstraction Layer

| Document | Description |
|----------|-------------|
| [channel-emulator](hardware/channel-emulator.md) | Channel emulator HAL |
| [base-station](hardware/base-station.md) | Base station HAL |
| [signal-analyzer](hardware/signal-analyzer.md) | Signal analyzer HAL |
| [positioner](hardware/positioner.md) | Positioner HAL |
| [probe-control](hardware/probe-control.md) | Probe control HAL |
| [flexible-probe-array](hardware/flexible-probe-array.md) | Flexible probe array design |

---

## API Documentation

| Document | Description |
|----------|-------------|
| [design-guide](api/design-guide.md) | API design principles |
| [swagger-guide](api/swagger-guide.md) | Swagger UI usage |
| [data-model](api/data-model.md) | Data model reference |

---

## Development Guides

| Document | Description |
|----------|-------------|
| [quickstart](guides/quickstart.md) | Quick start guide |
| [state-machine](guides/state-machine.md) | State machine design |
| [execution-sync](guides/execution-sync.md) | Execution synchronization |
| [monitoring-components](guides/monitoring-components.md) | Monitoring components |
| [implementation-checklist](guides/implementation-checklist.md) | Implementation checklist |
| [implementation-roadmap](guides/implementation-roadmap.md) | Implementation roadmap |

---

## Archive

Historical documents from previous development phases are stored in [archive/](archive/).

---

## Scripts

| Script | Usage |
|--------|-------|
| [generate_parameter_docs.py](scripts/generate_parameter_docs.py) | Auto-generate parameter docs from schemas |

```bash
# Regenerate parameter documentation
cd api-service
python ../docs/scripts/generate_parameter_docs.py
```
