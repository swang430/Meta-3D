# 2026-09-05 开发复盘与待办裁决

本次核验基线为 `a0c671c4e9c015417db7564fd94d594c2f62e5dd`；本地 main 与 fetch 后的 origin/main 一致。
本文件记录复盘证据与流程优化建议。**待办状态与顺序唯一入口仍是 `docs/roadmap-first-call.md`**。
本次只整理文档，不执行产品修复、现场操作、数据清理或 P2-63。

## 1. 这一轮交付到哪里

| 主线 | 已合并交付 | 尚不代表什么 |
|---|---|---|
| 基站配置完整性 | #425/#426/#427：诊断生命周期、分型号 preset、原子保存与 LabProfile 同步、HAL reload 后 adapter 身份 | 不代表操作员已填写正确的真实 endpoint 或取得现场认证 |
| 用例与设备一致性 | P1-75、P2-64～67（#431/#433/#434/#435/#436）：兼容性、Mock 约束、共同终态、可追溯导出 | 流水线 completed 不等于正式有效测量或 KPI 通过 |
| MAC | P2-54～56（#437/#440/#444/#446）：RAT 冻结 profile、FDD/TDD 能力声明、当前受限 LTE TDD 实现 | LTE profile 仍限 TM3/2 层；矩阵里的其他组合不等于可从 GUI 保存并执行；真机复验未关闭 |
| 信道仿真器平台 | P2-57～62（#448/#450/#452/#454/#456/#457/#458/#459）：能力、binding/preset、计划/会话、回执、认证与测试域第三 adapter | P2-57 声明面仍有残项；certfake 不等于第三台真实仪器接入；P2-63 继续 HOLD |

P2-62 最终合并为本次基线；其功能 HEAD 为 `757dd2e6`，频率证据最终绑定 adapter、instrument 与
measurement attempt。PR 留存的最终验证为 **6393 passed / 5 skipped、focused 242 passed**。
这是 PR 的历史验证记录，本次文档整理没有重新运行全后端，不能称为本次实跑结果。

## 2. 测试要优化，但先分清哪种成本

应保留功能 P1 的修复与复审。可以减少的是同一版本重复全量、无关构建、审查者重新收集上下文，
以及功能已经正确后继续改测试门。现有材料不足以计算全轮实际测试耗时、重复运行占比或 agent 利用率；
不根据 heartbeat 次数、测试总数、空 review 或提交数量推算这些数字。

本次通过 `gh pr view` 与 `gh api repos/swang430/Meta-3D/pulls/<编号>/comments --paginate`
读取原始记录，排除 `in_reply_to_id` 非空的回复后，得到以下**行内发现记录数**，不是独立根因数，
也不是审查轮数或接受率：

| PR | 原始行内发现 | 有代表性的机制缺陷 |
|---|---:|---|
| [#435](https://github.com/swang430/Meta-3D/pull/435) | 12 P1 + 1 P2 | 同一非正式/未完成状态，报告列表、详情、历史、commissioning、比较等消费者分轮才接齐 |
| [#442](https://github.com/swang430/Meta-3D/pull/442) | 15 条，全部在 `test_p2_55_capability_matrix.py` | 自然语言检查器的正则边界不断扩大；原问题是三条手册说明文字 |
| [#457](https://github.com/swang430/Meta-3D/pull/457) | 9 P1 + 2 P2 | 真实 F64 各加载管线与输入调节未全部产生门要求的证明；缺 crest 又被补成零 |
| [#458](https://github.com/swang430/Meta-3D/pull/458) | 7 P1 + 3 P2 | 认证要求互斥操作同时存在、释放后空缓存被当身份失配、引导认证来源约束分轮补齐 |
| [#459](https://github.com/swang430/Meta-3D/pull/459) | 3 P1 + 1 P2 | legacy 判据过宽 → 漏共同正式消费方 → 漏 attempt 身份，连续三次修不同断点 |

#442 的轮数“内审 5 轮、外审 8 轮”来自既有进度记录；本次独立核实的是上述 15 条同文件意见，
不把该历史轮数当成重新计算的实测。

## 3. 失效的是哪些机制

### 3.1 全集枚举做成了文件搜索，没有形成验收关系

AGENTS §0.5/§8 早已要求枚举，但 #435、#457、#459 仍反复漏消费者和生产路径。
列出文件不等于证明它们接通：需要知道“哪个入口产生什么证据、经过哪个判据、到哪个用户出口”。
修复一个条件后只跑同一个 helper 的测试，无法发现另一个出口继续读取旧字段。

改法：每片在既有设计/计划内保留一张小表，列真实生产者、权威校验、全部正式出口与一个可观察断言。
收到同根 P1 时一次检查这张表，而不是把搜索结果全部升级为新开发任务。

### 3.2 证据有摘要，却没有完整的归属与时序

摘要只能证明载荷的一致性，不能独立证明内容真实、属于本仪器、本次测量或正确时间。
#459 直到第三轮才补 attempt；#435 的 stored compatible verdict 曾未按冻结 requirements/manifest 重算。

改法：设计时列出每类证据实际需要的身份关系：execution、attempt、lease/session、instrument/adapter、
binding/profile/plan/asset 与测量窗口。逐项注明权威产生方及核对边界；不是要求所有对象盲目复制所有字段。
现代缺字段、显式 null、旧版合法原始载荷、新版控制面配旧 worker 必须分别定语义。
历史 fixture 保留原始结构与摘要，不为通过新 schema 偷补新字段后继续自称历史。

### 3.3 测试夹具造出了生产系统永远造不出的“成功”

[#458 的互斥配置发现](https://github.com/swang430/Meta-3D/pull/458#discussion_r3938164553)
说明认证曾要求 output level 与 output gain 同时存在，而正式入口禁止两者同时设置。
[#459 的生产覆盖发现](https://github.com/swang430/Meta-3D/pull/459#discussion_r3938575210)
指出手填第三 adapter 证据绕过了 MeasureExecutor，撤掉生产者仍会绿。
这不是多加畸形输入就能解决的问题。

改法：关键新链至少保留一条从真实生产入口、真实 parser/builder/session 到最终消费者的成功路径，
只替换 transport/时钟/外部存储。然后单独破坏一个事实得到失败路径。
至少覆盖两次连续执行（首次认证后再执行、release 后重新 acquire、同 execution 新 attempt），
检查状态复位。有效输入误拒也必须测；“永远拒绝正式执行”同样是功能缺陷。

### 3.4 审查在追求测试完备，主代理没有落实停止条件

#442 所有行内发现都在测试文件，是功能审查被测试自审替代的直接证据。
独立审查有价值，但重复给同一审查者同一种合成夹具，会重复相同盲区。
主代理选择修法、扩大范围和重复跑全量，责任不能归咎于 subagent。
此前多 agent 同改共享证据链，也会增加交接与相互失效的验证；本次没有可核验时间账，不能量化归因。
后续遵守用户已选的单 agent 顺序执行，外审保留独立渠道，不恢复并行开发。

现有执行文档还有直接冲突：

- `CLAUDE.md` 一方面写轻量修复，另一方面要求每次修复推送全量；又将“全量后改了文档”作为重跑案例。
- `.claude/agents/pre-commit-reviewer.md` 末尾仍写“改进默认 backlog”，与 AGENTS §10 冲突。
- 本机旧 memory `feedback_review_loop_scope_discipline.md` 仍有“两轮一律停/P3 默认 backlog”的历史口径。
  它不能推翻 AGENTS 当前的“有功能 P1 必须续审、后续 P2/P3 不自动积压”。本次不改历史复盘原文。

改法优先是删掉矛盾指令、引用 AGENTS 唯一判据；不是再写一份更长的强制审查清单。

### 3.5 交付分解只按模块，没有独立验收“用户能走通”

P2-55 矩阵有 authoritative 组合，LTE 输入 schema 仍限 TM3/2 层；P2-57 的部分 manifest 交付被顶部
“已完成”掩盖；P2-62 合并后 roadmap 仍排为 WIP。这些都是交付状态与可达能力混淆。

改法：声明、可达实现、现场认证分别记状态。每片以用户操作和可观察结果结束，不能以字段存在、
单元测试绿或 PR merged 替代现场验收。

## 4. 回归策略优化方案（待落实，不声称现行强制流程已改变）

| 场景 | 建议验证 | 何时再跑全量 |
|---|---|---|
| 纯文档/进度更新 | diff、链接、编号/顺序、引用源核对 | 不触发后端全量或 GUI build |
| 局部功能修复 | RED→GREEN + 同根读写方的受影响回归 | 影响共享契约、状态/并发/迁移、依赖或影响面不确定时 |
| 新增共享证据/冻结/安全生命周期 | 真实生产路径正反例 + 全部正式消费者回归 + 最终全量 | 功能输入或共享行为再次改变时重新验证 |
| GUI/API 契约变化 | 受影响交互、实际响应对 schema、四镜像和 production build | 涉后端共享功能时再加后端全量 |
| 修复后复审 | 当前增量 diff、同根路径枚举、关键反例 | 审查者不重复已有效完成的全量 |

优化落地前，仍按当前适用流程完成必要验证。落地时将 `CLAUDE.md` 与 reviewer 的**执行方法**一起
调整，判据仍引用 AGENTS。禁止通过“轻量”标签跳过无法界定影响面的共享改动。

验证记录复用已有 PR/计划，记命令、退出码、结尾统计、代码版本或 diff 指纹、耗时及触发原因。
文档变更可复用同代码输入的测试结果，但必须明确结果对应哪个版本；功能、测试、fixture、依赖、
生成契约改变不能复用旧结果伪称当前通过。无需新建测试编排平台。

审查顺序建议：先查功能关系与生产可达路径 → 修复同根问题 → 相关回归 → 稳定版本最终全量。
变异只回答核心修复是否受保护，已回答即停。功能 P1 继续阻塞；测试发现上限 P2/P3。
出现两轮同根遗漏时先重画该局部证据关系，再最小修复；不是放弃 P1 或强行合并。

后续两个实际功能 PR 记录四项：R1 逃逸的功能缺陷类型、同代码版本重复全量次数、
审查/测试耗时、因审查修复引入的新功能缺陷。先积累基线，不承诺未经测量的提速百分比。

## 5. 本次 triage 的证据与边界

### 已在当前代码构造复现

使用 `.venv/bin/python`，`USE_MOCK_INSTRUMENTS=true`、临时 `LOG_DIR`、内存对象和假的 DB query，
直接调用生产 `get_instrument_catalog`；没有启动应用 lifespan、连接仪器或读写用户数据库。
同一 category/connection 仅改变 certification 字段：

```text
malformed certification catalog categories: 0
absent certification catalog categories: 1
undocumented output fields: ['dimensions']
additionalProperties: False
formal TDD options: ['KS510', 'KS520', 'KS550']
```

前两行证明损坏认证会被整个目录的异常兜底洗成空列表，**不代表配置被数据库删除**。
中间两行来自真实 CMW manifest 的 model_dump 与 checked OpenAPI 属性集比较，说明契约遗漏仍在。
最后一行来自 `cmw500_lte_formal_options('tdd')`；其生产消费者包括
`evaluate_lte_2x2_formal_capability` 与 `base_station_execution_evidence`，所以旧 discovered
“缺 KS510 不会被拒”的当前时态结论已过期。矩阵逐值固件/选件通用求值仍是另一项扩域前工作。

另以 camelCase 三类 driver 键、AsyncMock transport 返回两个不同读数，直接调用生产
`InstrumentHALService.get_aggregated_metrics`（内存 cache，未连接硬件/数据库），得到：

```text
input 10 output {'throughput': 0.0, 'snr': 0.0, 'eirp': 0.0, 'temperature': 23.0}
input 90 output {'throughput': 0.0, 'snr': 0.0, 'eirp': 0.0, 'temperature': 23.0}
fallback throughput fields: ['status', 'timestamp', 'unit', 'value']
```

源代码还确认 `monitoring.generate_monitoring_data` 在 HAL 为空/异常时调用随机 fallback，且无
provenance 字段。它由测试租约控制开放，经 REST/WS 提供；本次未证明它进入正式报告。
此项是产品假读数，不是测试门缺陷，独立 triage 后列为 P1-76 并前置。

### 分类裁决

- 当前可修产品缺陷：监控固定/随机假读数优先，其后损坏认证隐藏仪器目录、MAC capability 响应契约缺 dimensions。
- 已批准能力的残项：CMW TM1/1 天线抽样的载体/可达路径、P2-57 声明面剩余项；按后续范围单独设计。
- 现场工作：P0-9/P0-8b、P1-74、P2-51/55/56、UXM P0-5/P2-52、CE 认证实际冷启动/再次执行。
- 手册证据缺口：UXM IRAT error queue / 窗口边界；未确认前保持 unknown，不能用本地 fake 解除。
- `.smu` 活动端口拓扑归 ChannelAsset，不归 per-driver manifest（2026-09-03 用户拍板）；
  当前 parser 只解析中心频率。拓扑残项先取得 OTA 样本与 Direction 手册依据，另片设计。
- 已覆盖：P2-59 会话已有 clear_passthrough_mode 终态所有权；#458 的 acquisition 前 identity 初始化和
  GUI scoped certification preview 已在 main。对应旧“永远不撤直通”等结论不再当成现状。
- 保留待评估：窗口级结构化证据持久化、诊断侧旧 capability 标志、手册页码进 digest 与说明文字纠偏。
  页码变更前需核对实际认证/历史冻结数据分布；本次没有查询开发库或现场库，旧计数不能复用为现状。
- 配置完整性下一批候选：SCD 按 connection 而非型号归属，以及 W2-W4 与切型号的并发锁。
  本次核实相关源码仍存在，未在 PG 重跑历史并发反例；不混入目录读取修复。
- 维护：自然语言检查器、顺序/链接自动检查、测试冗余；不自动晋升功能 P1、不用来阻塞现场主线。

本次重点复核本轮开发相关条目与活动状态镜像。早期 Discovered 原文保留为取证材料；
未逐项复现的历史候选仍待评估，不把整池宣称为“已清零”，也不批量删除历史证据。
