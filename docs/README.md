# Meta-3D Documentation

## Quick Navigation

| Category | Description |
|----------|-------------|
| [治理 / Roadmap](roadmap-first-call.md) | First-call 路线图 + WIP=1 治理（单一真相源） |
| [项目历程回顾](project-retrospective.md) | 从第一次现场到现在的全程总结 |
| [现场经验与教训](field-experience.md) | 经验性文档归类索引（现场记录 / 治理 / 现场衍生设计 / 审计） |
| [architecture/](architecture/) | System architecture and design |
| [features/](features/) | Feature modules |
| [hardware/](hardware/) | Hardware abstraction layer |
| [api/](api/) | API documentation |
| [guides/](guides/) | Development guides |
| [archive/](archive/) | Historical documents |

---

## 项目历程 & 现场经验

| Document | Description |
|----------|-------------|
| [project-retrospective](project-retrospective.md) | ⭐ 从第一次现场（CAICT 2026-05）到现在的全程回顾 + 5 条贯穿主线 |
| [field-experience](field-experience.md) | ⭐ 经验性文档归类索引（按"想解决什么"速查现场记录/治理/现场衍生设计/审计/教训） |
| [roadmap-first-call](roadmap-first-call.md) | 路线图 + governance rules + 可规划工作 audit |
| [announcements/2026-05-14-roadmap-baseline](announcements/2026-05-14-roadmap-baseline.md) | Governance baseline 由来 |
| [guides/on-site-debug-protocol](guides/on-site-debug-protocol.md) | 下次现场执行协议（6 铁律 + go/no-go gate） |

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
| [scenario-design](features/virtual-road-test/scenario-design.md) | Scenario design guide |
| [vrt-step-configuration](archive/vrt-step-configuration.md) | ⚠️ 已归档 — 场景→计划步骤继承（ARCH-1 S4 拆除） |
| [scenario-library](features/virtual-road-test/scenario-library.md) | Standard scenario library |

### Calibration

| Document | Description |
|----------|-------------|
| [system-calibration](features/calibration/system-calibration.md) | System calibration |
| [probe-calibration](features/calibration/probe-calibration.md) | Probe calibration |
| [channel-calibration](features/calibration/channel-calibration.md) | Channel calibration |

### Test Management

| Document | Description |
|----------|-------------|
| [test-management-unified-architecture](archive/test-management-unified-architecture.md) | ⚠️ 已归档 — 计划链架构（ARCH-1 S4 拆除）；现状见 `gui/src/features/TestManagement/README.md` |
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
| [state-machine-testplan](archive/state-machine-testplan.md) | ⚠️ 已归档 — TestPlan 状态机（ARCH-1 S4 拆除） |
| [execution-sync-queuetab](archive/execution-sync-queuetab.md) | ⚠️ 已归档 — QueueTab↔监控同步（ARCH-1 S4 拆除） |
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
