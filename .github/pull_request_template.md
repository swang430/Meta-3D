<!--
PR 模板 — 强制声明 roadmap 对齐, 避免再次出现"两天现场, 全部消耗在 driver 调试"的情况。
详见 docs/roadmap-first-call.md 的 governance rules 段落。
-->

## Roadmap alignment

<!-- 选一个, 其他删掉 -->

- [ ] **On roadmap**: `P0-X` / `P1-X` / `P2-X` / `P3-X`
  *(单 PR 原则上只对应一个 roadmap 项。如果跨项, 说明为什么不能拆。)*
- [ ] **Out of roadmap**, justified because: ……
  *(典型场景: blocking bug fix / security fix / 紧急回滚)*
- [ ] **Drive-by fixes** appended to roadmap backlog as: ……
  *(在 docs/roadmap-first-call.md 的 "Discovered during X" 区添加了对应条目)*

## Summary

<!-- 1-3 行说明改了什么。重点是 WHY, 不是 WHAT (diff 已经说了 what)。 -->

## Scope check

<!-- 把这个 PR 实际触碰的所有文件类别列出来。
     如果触碰了不在 roadmap 项预期范围内的文件, 说明原因。
     这是反"顺手优化"的硬约束。 -->

- 触及范围：
- 是否有 out-of-scope 改动？如有，说明原因：

## Test plan

<!-- 验证步骤。Acceptance criteria 在 roadmap 里, 这里说明本 PR 是否满足。 -->

- [ ] 满足 roadmap 项的 acceptance criteria
- [ ] 新增测试: ……
- [ ] 现有测试通过, 无回归
- [ ] (如适用) 手工验证步骤: ……

## Out of scope (deferred)

<!-- 本 PR 期间发现但没在本 PR 解决的事项。
     必须同步追加到 docs/roadmap-first-call.md 的 "Discovered during X" backlog。 -->

- 

🤖 Generated with [Claude Code](https://claude.com/claude-code) (if applicable)
