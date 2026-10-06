# P3-24 GUI 回归基线治理

用户已批准 P3-24 并要求连续完成。仅维护测试，不改变产品、协议、依赖或正式证据资格。

## 当前复现与全集

基准 `5f58c26664a05982717d249aeb4b8923bdd672e6`，仓库根目录执行：

```sh
npx --yes tsx --test $(rg --files gui/src gui/test | rg '\.test\.(ts|tsx)$')
```

退出 1，292 tests / 283 pass / 9 fail。下列九项全部复现；统计不是固定未来基线。

| 失败项 / 文件 | 分类、现状依据 | 最小修复与保留保护 |
|---|---|---|
| CE confirm / channelEmulatorModelPresetDraft.test.ts | 过时源码形状；App 的 next 还增加 operator 来源 | 要求 next spread 与 operator 标记，保留确认/取消与无 PUT 断言 |
| generic capabilities / baseStationCapabilityManifest.test.ts | 匹配范围错误；UXM topology 分支不是能力投影 | 分别定位能力投影构造和渲染边界，保留通用 projection、tone、第三 adapter 正反例 |
| unbound TestCase / baseStationCompatibilityReadiness.test.ts | 匹配范围错误；enabled 正则跨进独立 windowBindingQuery | 只在 cmwReadinessQuery 中检查，无 Lab 时 readiness 仍可请求，window query 不混入 |
| channelHal.test.ts | 运行问题；Jest globals 没有对应 runner | 转为现有 node:test/assert，使用真实 ChannelEmulatorHAL，仅替换外部 transport，保留 connect/load/config/start/status/stop/disconnect 行为 |
| unsaved endpoint / equipmentDiagnosticTarget.test.ts | 过时预期；保存后分类激活已替代整体 reload | 精确断言当前 actionable error 与无 payload，覆盖 BS/CE，不放行覆盖地址 |
| save feedback / labProfileInstrumentBindingSync.test.ts | 过时预期；placeholder 已由 manifest 提供 | 要求 field.placeholder 及原 drawer 不关闭/保存失败反馈 |
| LTE PCell / lteOperatingPointTruth.test.ts | fixture 缺少当前必填 lte_transmission_mode | 明确 TM3 输入/输出，同时证明缺失 mode 返回 null，无 NR 字段继承 |
| LTE commissioning / lteOperatingPointTruth.test.ts | 过时预期；operator 默认已是 keysight_gcm | 明确 GCM 请求结果，保留 LTE identity/no NR fields |
| p1_56_positioner_unknown_position.test.ts | 运行问题；路径依赖 cwd=gui | 用 import.meta.url 定位，原未知坐标/容差保护不删 |

这九项未证实产品缺陷；不改生产去迎合旧预期。真正产品故障若出现，独立 triage。

## 验收关系与边界

生产入口 → 权威判据 → 消费者 → 断言：App CE switch → preset planner/operator provenance → 草稿及确认 modal → 无请求、确认才切换；MIMO form → readiness query 自身 enabled → server compatibility → 无 Lab 不压掉请求；manifest → generic projection → badge tone → 不以 adapter 名推资格；carrier/session builder → 显式 LTE identity → 请求 → TM 与无 NR 字段；positioner response → nullable feedback → panel → 未知不写入坐标/不判失败。

无需新增框架。复用 `gui/test/p2_83bEffectiveState.browser.js` 与 `labWorkspace.browser.js`，独立 Vite 5198，仅替换 HTTP/WS，不连接硬件。不改 API/OpenAPI/后端共享逻辑，无后端全量触发；完整 GUI、production build、定点保护变异由主代理负责。

NotebookLM 不适用：无仪器语义、命令或值域变化。P2-85 软件已由 #510 合并；本片同步当前 roadmap 镜像，不改历史验证记录。P2-86 仍取证阻塞，HOLD/现场项不动。
