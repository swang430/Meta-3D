# P1-58 实施 plan

> 设计稿：`2026-08-21-p1-58-irat-compat-sequence-design.md`（判据换源方案、双实证、
> 边界论证都在那边，本文件只列执行步骤与核对项）

## 步骤

1. **RED** —— 新建 `api-service/tests/test_p1_58_irat_compat_sequence.py`（四门：
   ①a IRAT 未定义不冒充实测失败 / ①b 5GNR 全 clean 但存在未定义 critical 时保持
   `UNDETERMINED` 非绿 / ② 真缺失仍失败且 BLOCKER 不夹带
   未定义名字 / ③ partition 不变量）。实跑，确认 ①a ①b ②后半 ③ 红、② 前半绿
   （守既有 fail-closed，价值由变异 M2 证明）。
2. **GREEN** —— 改 `uxm_scpi_compatibility.py`：
   - 加 `_critical_partition(profile)`；
   - `is_critical` 两处换 `critical_applicable`；
   - `critical_undefined` 失败因子 → `critical_not_in_profile` 披露
     （log 信息行 + `extra` 字段 + summary 披露；BLOCKER 失败清单不混入未定义项）；
   - `success` 同时要求未定义清单为空；summary/`extra.verdict` 明确四态
     `ABORTED / BLOCKER / UNDETERMINED / SUCCESS`；
   - docstring「The 22 "critical" commands」句更新为按方言派生的表述。
   同步改造 `test_diagnostic_sequences.py` 三个既有用例。实跑两个测试文件全绿。
3. **全量**（改动收口后、内审风格纪律：跑完不再碰文件）：
   `cd api-service && .venv/bin/python -m pytest -q --color=no -p no:cacheprovider`
   （已知失败 `test_p1_36_execution_id::test_no_execution_means_default_not_empty`
   不属本片；除它零失败）。
4. **commit**（中文、`git commit -F`、trailer `Co-Authored-By: Claude Fable 5
   <noreply@anthropic.com>`）。
5. **变异实跑**（在已 commit 的树上，python 脚本 replace 必 assert 命中，跑完
   `git checkout -- <file>` 还原，还原后 `git status` 必须干净）：
   M1 判据回退全局清单 → ①a/③ 红；M2 真缺失放行 → ② 红；M3 披露归零 → ①a 红。
6. 变异后把两个目标测试文件再实跑一遍确认还原正确，push 分支（**不开 PR**）。
7. 报告（NotebookLM 记录 / 方案 / 文件清单 / 门与变异输出 / 全量尾行 / 未做事项）。

## R1 尾修

- Codex R1 P1：初版让 5GNR 的未探测 critical 穿过 `success=True`，会在 GUI 上假绿。
  后端按上述四态收窄；GUI 再通过 `sequenceVerdictView()` 消费同一 `extra.verdict`，
  `UNDETERMINED` 显示黄色 `undetermined`，不再折叠成绿色 success 或笼统 failure。
- Codex R1 P2：设计稿补齐厂商手册原件文件、章节、行号与查无命中的反向 grep 证据。
- GUI RED：`diagnosticSequenceEvidence.test.ts` 在 helper 不存在时以缺少导出失败；GREEN 后
  6 passed，production build 通过。

## 核对项

- [ ] 改前 grep 目标文件禁令（已做：132 / 140-141 行 ACTION 相关，本片不碰）
- [ ] 不动 roadmap；不动他片文件；不碰错误队列读取（P3-21）
- [ ] 措辞恒「未定义/未探测/无结论」，绝不写「不支持」
- [ ] `test_immediate_apply_actions_*`（P1-46 门）保持零 diff 全绿
- [ ] 变异还原后 `git status` 干净、测试复绿

## R2 尾修记录（2026-08-21）

最终外审 R2 指出“最近运行”仍只消费 `success`，刷新后会把已持久化的
`UNDETERMINED` 折叠成红色失败。尾修按 TDD 增加轻量 `sequence_verdict` 摘要字段：
后端只从服务端持久化的 `sequence_evidence.extra.verdict` 精确白名单取值，前端与即时结果
复用同一四态映射；旧记录无该字段时继续保守回退布尔值。该 P1 修复必须触发 R3，直到
覆盖最新 HEAD 的 Codex 外审无 P1 后才可合并。
