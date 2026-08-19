# P1-57 Global Lab / Chamber Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让所有运行态暗室页面只消费一个浏览器级 LabProfile 上下文，并由后端统一通过 `LabProfile.chamber_config_id` 解析暗室，消除探头配置、拓扑编辑和暗室首测之间的暗室分叉。

**Architecture:** GUI 新增 `OperationalLabProvider` 和 App header 唯一选择器；页面只读该上下文，危险页面通过最小 guard 阻止不安全切换。Topology API 以 `lab_profile_id` 为输入，复用 `resolve_current_chamber()` 派生并校验持久化 `chamber_id`。TestCase/历史记录的持久化绑定保持独立，不被当前上下文改写。

**Tech Stack:** React 18、TypeScript、Mantine、TanStack Query、FastAPI、Pydantic v2、SQLAlchemy、pytest、Node `node:test`。

---

## 开工前约束

- 工作树：`/Users/simon/Tools/MIMO-First/.worktrees/p1-57-global-lab-chamber-context`
- 分支：`codex/p1-57-global-lab-chamber-context`
- 基线：`f59d76f59b23a5c9788aae64b5db39359fb4f042`
- 已验证基线：

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest \
  api-service/tests/test_p1_28_chamber_truth_source.py \
  api-service/tests/test_switch_topology_chamber_binding.py \
  api-service/tests/test_lab_resolution.py -q
# 34 passed
```

- 每个任务严格 RED → GREEN → 相关回归 → commit。
- 开始 Task 1 前先执行一次全集搜索并把命中分类追加到设计文档的消费方清单：

```bash
rg -n "fetchLabProfiles|selectedLab(Profile)?Id|selectedLabId|lastLab|LAST_LAB|fetchActiveChamber|selectedChamberId" gui/src
rg -n "chamber_id|lab_profile_id|resolve_current_chamber" api-service/app/api/switch_topology.py api-service/app/schemas/switch_topology.py gui/src/api/switchTopologyService.ts
```

## Task 1：锁住全局选择状态机

**Files:**
- Create: `gui/src/features/OperationalLab/operationalLabSelection.ts`
- Create: `gui/test/operationalLabSelection.test.ts`

**Step 1: 写 RED 测试**

覆盖：0 个无选择；1 个自动选择；多个且无持久化值不选第一项；有效持久化值恢复；失效/停用/
无 chamber binding 的值拒绝；旧 commissioning/probe key 只能迁移到仍有效的 LabProfile。

**Step 2: 运行并确认 RED**

```bash
cd gui
npx tsx --test test/operationalLabSelection.test.ts
```

**Step 3: 实现纯函数**

保持纯函数只做 allowlist 决策，不访问 React/localStorage，不猜第一项。

**Step 4: GREEN 并提交**

```bash
npx tsx --test test/operationalLabSelection.test.ts
git add gui/src/features/OperationalLab/operationalLabSelection.ts gui/test/operationalLabSelection.test.ts
git commit -m "test: define operational lab selection contract"
```

## Task 2：建立 App 级 Provider、唯一选择器与切换 guard

**Files:**
- Create: `gui/src/features/OperationalLab/OperationalLabContext.tsx`
- Create: `gui/src/features/OperationalLab/OperationalLabSelector.tsx`
- Create: `gui/src/features/OperationalLab/index.ts`
- Modify: `gui/src/main.tsx`
- Modify: `gui/src/App.tsx`
- Create: `gui/test/operationalLabContextWiring.test.ts`

**Step 1: 写 RED 契约测试**

要求 provider：只用 `fetchLabProfiles(true)`；localStorage 唯一 key 为
`mimo.operationalLabProfileId`；暴露 lab/chamber identity；header 渲染 selector；多个活动项不默认首行；
guard 有阻断时 `requestLabChange()` 不更新 ID/localStorage。

**Step 2: 实现 provider 与 selector**

在 `QueryClientProvider` 内挂 provider。selector 同时显示 `<lab.name> / <lab.chamber_name>`；
loading、error、无绑定状态分开。新增最小 `useOperationalLabSwitchGuard(key, reason | null)`，只注册阻断
理由，不自动保存/丢弃。

**Step 3: 迁移旧 key**

只在新 key 不存在时读取已知旧 key；候选必须仍在 active allowlist 且有 chamber binding。成功或失败后
删除旧 key，不能继续双读。

**Step 4: GREEN、build、提交**

```bash
cd gui
npx tsx --test test/operationalLabSelection.test.ts test/operationalLabContextWiring.test.ts
npm run build
git add gui/src/features/OperationalLab gui/src/main.tsx gui/src/App.tsx gui/test
git commit -m "feat: add global operational lab context"
```

## Task 3：把 Topology API 的暗室真值换成 LabProfile resolver

**Files:**
- Modify: `api-service/app/api/switch_topology.py`
- Modify: `api-service/app/schemas/switch_topology.py`
- Modify: `api-service/tests/test_switch_topology_chamber_binding.py`
- Create: `api-service/tests/test_p1_57_topology_lab_context.py`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`

**Step 1: 写 RED 行为测试**

至少覆盖：

- 除 `/templates` 外，list/create/import/get/update/delete/validate/paths/calibration-matrix 都必须消费
  `lab_profile_id`；
- lab A→chamber A 只能读写 A 的 topology；
- 请求附带 chamber B 时在 commit 前拒绝且行不变；
- topology stored chamber B 不能在 lab A 上读取、验证、解析路径、更新或删除；
- inactive/missing/unbound/orphan LabProfile 均 fail-closed；
- 旧 topology 不迁移、不删除。

**Step 2: 运行 RED**

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest \
  api-service/tests/test_p1_57_topology_lab_context.py \
  api-service/tests/test_switch_topology_chamber_binding.py -q
```

**Step 3: 复用单一 resolver 实现**

抽取 topology 路由内的轻量 resolver-to-HTTP 映射；不得复制 active-lab 选择规则。`chamber_id` 若保留
兼容，只做一致性断言；任何不一致在 default flag 更新、add、delete、setattr 之前失败。

注意 reimport 当前是 delete→import：不得在新上下文里继续先删后验。先完整解析 lab/chamber/template，
再只删除同一 `(switch_category_id, resolved_chamber_id)` 的行。

**Step 4: 同步 OpenAPI/生成类型并 GREEN**

```bash
cd gui && npm run openapi:generate && cd ..
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest \
  api-service/tests/test_p1_57_topology_lab_context.py \
  api-service/tests/test_switch_topology_chamber_binding.py \
  api-service/tests/test_p1_28_chamber_truth_source.py \
  api-service/tests/test_rule_gates.py -q
git add api-service/app/api/switch_topology.py api-service/app/schemas/switch_topology.py \
  api-service/tests api/openapi.yaml gui/src/types/api.generated.ts
git commit -m "feat: resolve topology chamber from lab profile"
```

## Task 4：TopologyEditor 删除独立暗室选择并接入全局 guard

**Files:**
- Modify: `gui/src/api/switchTopologyService.ts`
- Modify: `gui/src/features/TopologyEditor/TopologyEditor.tsx`
- Create: `gui/test/topologyOperationalLabContext.test.ts`

**Step 1: 写 RED 测试**

锁住：service 发送 `lab_profile_id`；编辑器不再拉全部 chamber、不再渲染“目标暗室”、不再从最新
topology 播种 chamber；query key/request 按全局 lab/chamber；保存/import/update 都携带 lab truth；dirty
状态注册切换阻断。

**Step 2: 实现并处理 dirty 上报**

给 `TopologyFlow` 增加 `onDirtyChange`；outer editor 注册 guard。lab 切换只会在 dirty=false 时发生，
切换后立即丢弃旧 topology/drawer/selection，再加载新 scope。禁止自动把旧 topology 改绑到新 chamber。

**Step 3: GREEN、build、提交**

```bash
cd gui
npx tsx --test test/topologyOperationalLabContext.test.ts test/operationalLabContextWiring.test.ts
npm run build
git add gui/src/api/switchTopologyService.ts gui/src/features/TopologyEditor/TopologyEditor.tsx gui/test
git commit -m "feat: bind topology editor to operational lab"
```

## Task 5：迁移探头配置与 Commissioning

**Files:**
- Modify: `gui/src/App.tsx`
- Modify: `gui/src/components/ChamberConfigCard.tsx`
- Modify: `gui/src/components/Commissioning/index.tsx`
- Create: `gui/test/operationalLabPrimaryConsumers.test.ts`

**Step 1: 写 RED 测试**

验证 ProbeManager 不再声明自己的 `selectedLabProfileId`；ChamberConfigCard 读取 context；
Commissioning 不再读取/写入 `mimo.commissioning.lastLabId`，createSession 使用全局 ID；session 存在时
注册 guard；页面同时显示 lab/chamber。

**Step 2: 实现**

Commissioning session 创建后保留响应里的实际 lab/chamber identity 作为会话事实；全局切换被阻断，
而不是把已创建 session 重新解释为新上下文。

**Step 3: GREEN、build、提交**

```bash
cd gui
npx tsx --test test/operationalLabSelection.test.ts \
  test/operationalLabContextWiring.test.ts \
  test/operationalLabPrimaryConsumers.test.ts
npm run build
git add gui/src/App.tsx gui/src/components/ChamberConfigCard.tsx \
  gui/src/components/Commissioning/index.tsx gui/test
git commit -m "feat: unify probe and commissioning lab context"
```

## Task 6：收口其余运行态消费者，保留记录绑定

**Files:**
- Modify: `gui/src/components/OTAMapper/ProbeArraySelector.tsx`
- Modify: `gui/src/features/Diagnostics/CommissioningAdhocPanel.tsx`
- Modify: `gui/src/features/Diagnostics/SequenceRunnerPanel.tsx`
- Modify: `gui/src/features/ProbeCalibration/components/RFChainDiagramPanel.tsx`
- Create: `gui/test/operationalLabConsumerInventory.test.ts`
- Modify only if inventory proves operational: other `gui/src/**` consumers found by the opening `rg`

**Step 1: 写 RED 全集门**

对每个运行态消费者断言它使用 `useOperationalLab()` 且不再调用 `fetchLabProfiles`/维护 page-local current
lab。明确允许 TestCase create/edit 与 LabProfile wizard/manager 保留独立记录编辑器，测试不要误删它们。

**Step 2: 实现并收敛 query keys**

所有 chamber-scoped query key 至少包含解析后的 `labProfileId` 或 `chamberId`；context 未 ready 时
`enabled=false`。切换后不得复用旧 lab 的 detail/draft。

**Step 3: GREEN、全集 grep、提交**

```bash
cd gui
npx tsx --test test/operationalLab*.test.ts test/topologyOperationalLabContext.test.ts
rg -n "fetchLabProfiles|selectedLab(Profile)?Id|selectedLabId|lastLab|LAST_LAB" src
npm run build
git add gui/src gui/test
git commit -m "refactor: consume one operational lab context"
```

## Task 7：完整回归、事实镜像与交付

**Files:**
- Modify: `docs/plans/2026-08-19-p1-57-global-lab-chamber-context-design.md`
- Modify: `docs/roadmap-first-call.md`
- Modify if API contract changed: `api/openapi.yaml`, `gui/src/types/api.generated.ts`

**Step 1: 后端相关与门**

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest \
  api-service/tests/test_p1_57_topology_lab_context.py \
  api-service/tests/test_switch_topology_chamber_binding.py \
  api-service/tests/test_p1_28_chamber_truth_source.py \
  api-service/tests/test_lab_resolution.py \
  api-service/tests/test_commissioning_lab_resolution_http.py \
  api-service/tests/test_commissioning_smoke.py \
  api-service/tests/test_rule_gates.py -q
```

**Step 2: GUI、编译、diff**

```bash
cd gui
npx tsx --test test/operationalLab*.test.ts test/topologyOperationalLabContext.test.ts
npm run build
cd ..
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m compileall -q api-service/app
git diff --check
```

**Step 3: 手工验收**

使用至少两个绑定不同 chamber 的 active LabProfile：

1. 多项且无有效持久化选择时，header 要求显式选择；
2. 选 `CAICT-Lab-1`，探头、拓扑、commissioning 三页显示同一 chamber；
3. 拓扑 dirty 时切换被阻断；保存/放弃后可切；
4. commissioning session 创建后切换被阻断；
5. 切换后旧 chamber topology 不闪现、不被保存；
6. 直接构造错 lab/chamber topology 请求，后端拒绝且 DB 不变。

**Step 4: fresh 内审与 roadmap**

按 AGENTS.md 先列产生/消费全集，再 fresh 内审到 P1=0；同步 Current Focus、验证数字与外审状态，
不要提前写“已完成”。

**Step 5: 提交、推送、Ready PR**

```bash
git add docs api-service gui api/openapi.yaml
git commit -m "docs: close P1-57 lab chamber truth source"
git push -u origin codex/p1-57-global-lab-chamber-context
```

随后按仓库流程：R1 处理本片意见后触发 R2；若 R2 仍有 P1，修复并继续 P1-only 外审，直到覆盖最新
HEAD 的 Codex review 无 P1，再 merge commit。
