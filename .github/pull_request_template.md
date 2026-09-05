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
- [ ] **Independently triaged findings**, if any: ……
  *(写明裁决出口；外审后续轮次的 P2/P3 不自动写入 Discovered/backlog，见 AGENTS §10)*

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

<!-- 按 CLAUDE.md「验证分档与结果复用」，不按 push 次数要求全量。
     保留实际适用的项目；纯文档不要勾选“后端全量通过”。 -->
- 验证档位与影响面依据：
- 实跑/复用：命令、退出码、结尾统计、版本/输入差异、耗时；未运行及原因：
- 内审来源：独立审查 / 用户单 agent 模式下自查（非独立）/ 未发生及原因：

## Review tracking

<!-- 更新本段，不为状态记账另加代码提交。按 CLAUDE.md「外审请求与等待」去重。
     同 HEAD 的 R2 仍是独立轮次，不能把 R1 的结论复用为 R2。 -->
| Round | Target HEAD | Request URL / time / prior review id | Reviewed SHA / result URL | Status / consumed at |
|---|---|---|---|---|
| R1 | | | | |

## Out of scope (deferred)

<!-- 本 PR 期间未解决的事项只报告；后续独立 triage 后才写裁决出口。
     不得把外审 R2+ P2/P3 自动变成 Discovered、backlog 或 roadmap。 -->

- 

🤖 Generated with [Claude Code](https://claude.com/claude-code) (if applicable)
