# Quick Documentation Reorganization Checklist
**Time Required**: 4-6 hours over 2 weeks
**Goal**: Critical cleanup while starting Phase 4 development

---

## Week 1: Archive & Delete (2-3 hours)

### ✅ Step 1: Create Archive Structure (5 min)
```bash
cd /Users/Simon/Tools/MIMO-First
mkdir -p docs/archive/phases
mkdir -p docs/archive/deleted-stubs
```

### ✅ Step 2: Archive Completed Phase Docs (10 min)
```bash
# Move to archive
git mv PHASE1-COMPLETION-SUMMARY.md docs/archive/phases/
git mv PHASE1-EXECUTION-GUIDE.md docs/archive/phases/
git mv PHASE3_SUMMARY.md docs/archive/phases/

# Also archive these from docs/
git mv docs/ChannelEgine-Integration-Plan.md docs/archive/phases/
git mv docs/ProbeLayoutView-Integration-Analysis.md docs/archive/phases/
git mv docs/Test-Plan-Management-Design.md docs/archive/phases/

# Stage changes
git add docs/archive/
```

### ✅ Step 3: Delete Stub Files (5 min)
```bash
# These files have < 1KB, minimal content, no implementations
git rm TESTING-GUIDE.md
git rm docs/CI-CD-Pipeline-Design.md
git rm docs/Data-Analysis-Design.md
git rm docs/Report-Generation-Design.md

# Stage deletions
git add -u
```

### ✅ Step 4: Update Master Progress Tracker (30 min)

**File**: `docs/Master-Progress-Tracker.md`

**Find and replace**:
```diff
- Overall Progress: 6%
+ Overall Progress: ~40%

## Phase 1: Foundation
- Progress: 100% ✓
+ Date Completed: 2025-11-20

## Phase 2: Core Features
- Progress: 0%
+ Progress: 85% ✓

### TestManagement
- Status: Planned
+ Status: ✅ COMPLETED
+ Features: 4 tabs (Plans, Steps, Queue, History) all working
+ Date: 2025-11-28

### Monitoring
- Status: Planned
+ Status: ✅ COMPLETED
+ Features: Real-time monitoring, WebSocket integration
+ Date: 2025-11-25

### Virtual Road Test
- Status: Planned
+ Status: 90% ✓
+ Features: Scenario Library, Run Test, Details, Create Scenario
+ Pending: TestPlan integration (Phase 4)
+ Date: 2025-12-03

## Phase 3: Advanced Features
- Progress: 0%
+ Progress: 60% ✓

### OTA Mapper
- Status: Planned
+ Status: ✅ COMPLETED
+ Features: ChannelEngine integration, 32-probe weight calculation
+ Date: 2025-12-02

### Scenario Library
- Status: Planned
+ Status: ✅ COMPLETED
+ Features: 5 standard scenarios + custom creation
+ Date: 2025-12-03
```

### ✅ Step 5: Commit Week 1 Changes (5 min)
```bash
git commit -m "docs: Archive completed phases and delete stub files

- Archived: PHASE1/3 completion docs, integration plans
- Deleted: 4 stub files (< 1KB, no implementation)
- Updated: Master-Progress-Tracker to 40% accurate
- Reason: Documentation cleanup for Phase 4 start

Part of DOCUMENTATION-REORGANIZATION-PLAN.md (Incremental approach)"

git push origin main
```

**Week 1 Total Time**: ~55 minutes

---

## Week 2: Merge & Organize (2-3 hours)

### ✅ Step 6: Merge VirtualRoadTest Trilogy (45 min)

**Create new consolidated doc**:

```bash
# Create new file
touch docs/architecture/VirtualRoadTest-Complete.md
```

**Content structure**:
```markdown
# Virtual Road Test - Complete Documentation
[Copy content from 3 files and organize]

## 1. Product Overview
[From VirtualRoadTest.md - Product design section]

## 2. System Architecture
[From VirtualRoadTest-Architecture.md - Full architecture]

## 3. Implementation Guide
[From VirtualRoadTest-Implementation.md - Dev guide]

## 4. Current Status (NEW)
- ✅ Scenario Library: 5 standard scenarios
- ✅ Create/Run/Details: All features implemented
- ✅ OTA Mapper: ChannelEngine integration complete
- ⏳ TestPlan Integration: Phase 4 planned

## 5. API Reference
[Consolidate API sections from all 3 files]

## 6. Data Models
[Consolidate data model sections]
```

**Then clean up**:
```bash
# Move old docs to archive
git mv VirtualRoadTest.md docs/archive/
git mv VirtualRoadTest-Architecture.md docs/archive/
git mv VirtualRoadTest-Implementation.md docs/archive/

# Stage new consolidated doc
git add docs/architecture/VirtualRoadTest-Complete.md
```

### ✅ Step 7: Update TestManagement Doc (30 min)

**File**: `TestManagement-Unified-Architecture.md`

**Changes**:
```diff
## Implementation Status

### Tab 1: Plans Tab
- Status: 🏗️ In Progress
+ Status: ✅ COMPLETED
- Completion: 60%
+ Completion: 100%
+ File: gui/src/features/TestManagement/components/PlansTab/
+ Features: CRUD, filtering, wizards, queue actions

### Tab 2: Steps Tab
- Status: 🏗️ In Progress
+ Status: ✅ COMPLETED
- Completion: 70%
+ Completion: 100%
+ Bug Fix: BUG-001 (step save failure) resolved
+ Features: Drag-drop reorder, sequence library integration, parameter editor

### Tab 3: Queue Tab
- Status: 📋 Planned
+ Status: ✅ COMPLETED
- Completion: 0%
+ Completion: 100%
+ Features: Priority queue, start/pause/cancel, auto-refresh (10s)

### Tab 4: History Tab
- Status: 📋 Planned
+ Status: ✅ COMPLETED
- Completion: 0%
+ Completion: 100%
+ Features: Execution records, statistics, filtering, export
```

### ✅ Step 8: Organize Hardware Docs (15 min)

```bash
# Create hardware folder
mkdir -p docs/hardware

# Move all hardware documentation
git mv Hardware.md docs/hardware/
git mv MPAC.md docs/hardware/
git mv MPAC-sideview.md docs/hardware/
git mv MPAC-topview.md docs/hardware/
git mv Meta-3D-Strucutre.md docs/hardware/
git mv Amplifer.md docs/hardware/

# Stage changes
git add docs/hardware/
```

### ✅ Step 9: Update ARCHITECTURE-REVIEW.md (20 min)

**File**: `ARCHITECTURE-REVIEW.md`

**Update phase completion status**:
```diff
## Phase 1: Foundational Development
- Status: In Progress
+ Status: ✅ COMPLETED
- Progress: 80%
+ Progress: 100%
+ Date Completed: 2025-11-20
+ Deliverables: Probe API, Instrument API, Calibration API

## Phase 2: Core Features
- Status: Planned
+ Status: ✅ COMPLETED
+ Progress: 100%
+ Date Completed: 2025-11-28
+ Deliverables: TestManagement v2.0, Monitoring, Bug fixes (BUG-001 to BUG-004)

## Phase 3: Advanced Features & Integration
- Status: Future
+ Status: ✅ COMPLETED
+ Progress: 100%
+ Date Completed: 2025-12-03
+ Deliverables: Virtual Road Test, OTA Mapper, Scenario Library

## Phase 4: System Integration (NEXT)
+ Status: 🏗️ In Progress
+ Progress: 0%
+ Start Date: 2025-12-04
+ Goal: Scenario → TestPlan conversion, OTA execution
```

### ✅ Step 10: Commit Week 2 Changes (5 min)

```bash
git commit -m "docs: Merge redundant docs and organize by category

- Merged: VirtualRoadTest trilogy → VirtualRoadTest-Complete.md
- Updated: TestManagement-Unified-Architecture.md (all tabs complete)
- Updated: ARCHITECTURE-REVIEW.md (Phase 1-3 complete, Phase 4 start)
- Organized: Hardware docs → docs/hardware/
- Reason: Eliminate redundancy, improve discoverability

Part of DOCUMENTATION-REORGANIZATION-PLAN.md (Incremental approach)"

git push origin main
```

**Week 2 Total Time**: ~2 hours

---

## Validation Checklist

After completing both weeks, verify:

### ✅ File Count Reduction
```bash
# Before: 33 root-level .md files
# After: Check current count
find /Users/Simon/Tools/MIMO-First -maxdepth 1 -name "*.md" | wc -l

# Target: < 30 root files (10% reduction)
```

### ✅ Archive Structure Created
```bash
ls -la docs/archive/phases/
# Should contain: 6 phase completion docs
```

### ✅ Hardware Docs Organized
```bash
ls -la docs/hardware/
# Should contain: 6 hardware reference files
```

### ✅ Progress Trackers Updated
```bash
grep "Progress:" docs/Master-Progress-Tracker.md
# Should show: ~40% (not 6%)

grep "Status:" ARCHITECTURE-REVIEW.md
# Phase 1-3 should show: COMPLETED
```

### ✅ VirtualRoadTest Consolidated
```bash
ls -la docs/architecture/VirtualRoadTest-Complete.md
# Should exist as single 200+ line file

ls -la docs/archive/ | grep VirtualRoadTest
# Old versions should be in archive
```

### ✅ Git History Clean
```bash
git log --oneline -5
# Should show: 2 commits (Week 1 & Week 2)
```

---

## Success Metrics

| Metric | Before | After | Target | ✅ |
|--------|--------|-------|--------|----|
| Root .md files | 33 | ? | < 30 | ⬜ |
| Outdated docs | 10 | ? | 0 | ⬜ |
| Redundant files | 9 | ? | 0 | ⬜ |
| Progress accuracy | 6% | ? | 40% | ⬜ |
| Archived docs | 0 | ? | 10 | ⬜ |

---

## Troubleshooting

### Issue: Git merge conflicts
**Solution**: Run `git stash` before starting, then `git stash pop` after

### Issue: Can't find file to move
**Solution**: Use `find . -name "filename.md"` to locate

### Issue: Broken links after move
**Solution**: Search for old path: `grep -r "old/path" *.md`

### Issue: Lost content after merge
**Solution**: Check `git log --follow filename.md` for history

---

## After Completion

### Update README.md
```diff
## Documentation Structure

+ - SYSTEM-INTEGRATION-DESIGN.md - How 3 systems work together ⭐
+ - DOCUMENTATION-REORGANIZATION-PLAN.md - Reorg plan & timeline
  - CLAUDE.md - Developer guide
  - DEV-QUICKSTART.md - Quick start scripts
  - TODO.md - Current tasks

+ ### Active Design Documents
+ See `/docs/architecture/` for system design documents
+ See `/docs/design/` for feature specifications

+ ### Historical Documents
+ See `/docs/archive/` for completed phase documentation
```

### Announce to Team
```
Subject: Documentation Reorganization Complete (Week 1-2)

Changes:
- ✅ Archived: 10 completed phase docs
- ✅ Deleted: 4 stub files
- ✅ Merged: VirtualRoadTest trilogy → single doc
- ✅ Updated: Progress trackers now show 40% (accurate)
- ✅ Organized: Hardware docs in dedicated folder

New Key Document:
📘 SYSTEM-INTEGRATION-DESIGN.md - Integration architecture

Next:
- Phase 4: Scenario → TestPlan conversion starts this week
- Remaining doc updates: Incremental as features develop
```

---

## Time Tracking

| Task | Estimated | Actual | Notes |
|------|-----------|--------|-------|
| Week 1: Archive & Delete | 2-3 hrs | _____ | ____________ |
| Week 2: Merge & Organize | 2-3 hrs | _____ | ____________ |
| **Total** | **4-6 hrs** | **_____** | |

---

## Completion Sign-off

- [ ] Week 1 completed and committed
- [ ] Week 2 completed and committed
- [ ] Validation checklist passed (5/5 checks)
- [ ] README.md updated
- [ ] Team notified

**Completed by**: _____________
**Date**: _____________
**Review notes**: _____________
