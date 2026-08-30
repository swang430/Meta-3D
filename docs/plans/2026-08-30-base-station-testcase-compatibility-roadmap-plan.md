# BaseStation TestCase × Adapter Compatibility Roadmap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把已批准的 P1-75、P2-64～P2-67 按既有优先级写入单一 roadmap，并让 Current Focus、正式条目与 Discovered 出口保持一致。

**Architecture:** 本片只维护文档真值，不改生产代码。P1-75 插在 P1-74 后，P2-64～P2-67 追加到既有 P2-63 后；所有现状镜像引用同一顺序，Discovered 只记录证据与正式条目出口。

**Tech Stack:** Markdown、Git、`rg`、`git diff --check`

---

### Task 1: 同步顶部执行顺序与现状镜像

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-30-cmw-mac-channel-emulator-roadmap-design.md`

**Step 1: 定位所有旧顺序镜像**

Run: `rg -n 'P1-74|P2-54|P2-63|雷达顺序|HOLD' docs/roadmap-first-call.md docs/plans/2026-08-30-cmw-mac-channel-emulator-roadmap-design.md`

Expected: 找到 Current Focus、LOCAL-OPEN、设计摘要与交付顺序中的旧序列。

**Step 2: 更新为批准后的唯一顺序**

写成 `P1-74 → P1-75 → P2-54～P2-63 → P2-64～P2-67`，保留 P2-63 HOLD 与当前 WIP=0，不声称任何新条目已经启动。

**Step 3: 检查镜像没有互相矛盾**

Run: `rg -n 'P1-74.*P1-75|P2-64|P2-67|当前非现场 WIP' docs/roadmap-first-call.md docs/plans/2026-08-30-cmw-mac-channel-emulator-roadmap-design.md`

Expected: 所有现状镜像包含批准后的顺序，未出现旧的“P1-74 后直接 P2-54”承诺。

### Task 2: 写入正式 P1/P2 条目

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Step 1: 在 P1-74 后新增 P1-75**

写明可观察故障、结构化判据、首次 I/O 前 fail-loud、所有执行模式同门、冻结 digest、非目标与非现场地点。

**Step 2: 在 P2-63 后新增 P2-64～P2-67**

分别写入 Adapter-scoped Mock、共用 Preview/Readiness、证据与终态语义、日志与导出可追溯性；每条都包含依赖、验收与现场/非现场边界。

**Step 3: 核对编号唯一**

Run: `for id in P1-75 P2-64 P2-65 P2-66 P2-67; do test "$(rg -c "^### ${id} —" docs/roadmap-first-call.md)" = 1 || exit 1; done`

Expected: 每个正式条目标题恰好出现一次。

### Task 3: 维护 Discovered 出口并验证文档

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Step 1: 新增本次调查证据**

登记附件重复、Mock UXM 接受 LTE、Readiness 只证明在线、证据矛盾、公共日志硬编码 UXM、导出名缺 execution id，并给每条明确出口 P1-75 或 P2-64～P2-67。

**Step 2: 保持事实与推断分开**

已证实项写执行 ID 与观测；bandwidth/MIMO/duplex/attach/measurement/MAC 等扩散风险写成待 P1-75 需求投影审计，不声称已复现。

**Step 3: 运行文档校验**

Run: `git diff --check main...HEAD`

Expected: 无空白错误。

Run: `rg -n 'P1-74 → P1-75|P2-64|P2-65|P2-66|P2-67|7ae66c69|31d3e29d' docs/roadmap-first-call.md docs/plans/2026-08-30-*.md`

Expected: 顺序、正式条目、调查证据和出口均可检索。

**Step 4: 提交 roadmap 更新**

```bash
git add docs/roadmap-first-call.md \
  docs/plans/2026-08-30-cmw-mac-channel-emulator-roadmap-design.md \
  docs/plans/2026-08-30-base-station-testcase-compatibility-roadmap-plan.md
git commit -m "docs: prioritize base station compatibility fixes"
```
