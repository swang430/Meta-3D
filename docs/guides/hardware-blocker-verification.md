# 现场 hardware blocker 验证清单

P2-87 文档交付：PR #513。适用基线：2026-10-07，P2-86 / PR #512 已合并。当前分类/排期唯一源为 [roadmap](../roadmap-first-call.md#现场验证分类与执行顺序)；本文整理现有入口的使用边界，不新增硬件命令、脚本、阈值或正式资格。历史现场记录保留原样。

## 1. 出发前与现场共同约束

- 记录实际代码 commit、服务版本、活动 LabProfile、selected model/endpoint、loaded adapter、绑定摘要、场景资产和 DUT/SIM。仪器型号/固件只能取已确认的真实连接身份；声明值不能补真。
- 保存仪器配置后检查该分类 HAL 激活结果，再显式同步 LabProfile；检查服务器 readiness/compatibility。不能整体 reload 掩盖错误绑定，也不能跳过被服务器拒绝的配置。
- 一次只有一个硬件工作项。正式执行/功率观察期间不并跑诊断序列，尤其是消费错误队列、`*CLS`、状态切换和运动的序列；“只读”不等于无副作用。F64 单客户端约束照旧。
- 目标为先恢复真实诊断运行：配置→Attach→真实吞吐→停止释放→再次执行。缺校准/现场认证时仅使用既有允许的诊断策略，结果保持 UNKNOWN/N/A；默认严格门拒绝时先解决前置，不能据本文自行放宽。
- 操作员负责接线、运动安全范围和面板观察；开发者负责核对 raw、执行身份及解除条件。记录 operator、时间、instrument/model/firmware、execution/attempt、诊断 run ID、requested/applied、失败与 cleanup。字段不可得明确 unknown。

## 2. “调试序列 + 单阶段”如何选择

GUI：调试维护 → 调试序列 / 单阶段 ad-hoc / 转台控制。调试序列是设备级探针；单阶段是独立的 diagnostic_ad_hoc 执行，不继承先前阶段的成功证据，不成为正式报告资格。

| 入口 | 可以证明 | 不能证明 / 注意 |
|---|---|---|
| `instrument_idn_sweep` | 活动 LabProfile 与启用目录的绑定、连接时已采集的 adapter 身份投影 | 不发送新 IDN 查询；缺实时型号/固件仍 unknown，不能以配置补真；不要求所有历史绑定仪器到场 |
| `emcenter_switch_health` | 机箱/继电器/互锁回复的分类 | 已知不支持的 ERROR 3 不等于互锁安全；不代替实际路径切换验证 |
| `propsim_f64_output_level_windows` | 当前已加载场景的活动输出口及其合法电平窗 | 不能证明 DUT 到端功率、校准或吞吐；结束会读错误队列，不并跑测试 |
| `aerotech_positioner_motion_truth` | 明确 degree 单位、安全范围下的小步运动/返回与 PFBK/VFBK raw | 不能解除长距离移动或 HOME；运动前人工清场，失败不能重放未知结局的命令 |
| `propsim_f64_local_handback_check` | release 后人工观察面板，再 confirm 记录 Local/Remote 原文 | socket released 不等于 Local；先观察再 confirm，空选择/空原文不解除 |
| `propsim_f64_license_truth` | 许可、校准、用户对齐各自的已确认/未知状态 | 许可通过不等于校准有效；错误/空回复不能绿色兜底，维护窗口独占 |
| `uxm_window_boundary_probe` | 已有 UXM 测量 STATe 只读边界及 raw | 不下发未获匹配方言出处的清窗/结束配置；CMW500 不使用 |
| `propsim_f64_p08_gate` | 服务器确认真实 UXM 环境下的专用链验证 | UXM-only；CMW500 使用保存的 LTE TestCase，不用它绕过型号门；P0-8 已关闭不重开 |

其他已登记序列按服务器 metadata 的 required_categories、参数、破坏性/安全标记运行；无载体不能临时拼 SCPI 或以公共 health 代替事项验收。

### 单阶段边界

当前 GUI 只提供 phase 与 phase_overrides，API 另接受 config_overrides；不要假设 GUI 能完整编辑 LTE 配置。CMW500 LTE baseline 使用已保存并校验通过的 LTE TestCase，不把临时“暗室首测”缺 LTE 编辑能力当现场前置。

| 单阶段 | 现场用途 | 解除限制 |
|---|---|---|
| precheck | 定位配置、绑定、校准前置失败 | 只证明该独立诊断检查；模板里的 skip 参数不代表服务器必然接受，更不授予正式资格 |
| reference | 单独定位参考配置链故障 | 未测到真实量值不能当校准完成；不自动生成合法校准来源 |
| mimo_test | 定位 measure 阶段问题；会操作信号链与转台 | 必须先有合法完整执行配置及安全前置；不假定已跑 precheck/reference，更不能拼接不同执行证据 |
| analysis | 不纳入现场验证：该入口新建 execution，无法选择或消费既有执行的测量输入 | 没有 measure 的 azimuth_results 会失败；不从另一单阶段复制/拼接结果，不补为 0 或 PASS。分析验证用完整 TestCase 的同次执行链 |
| report | 不纳入已有执行报告的现场验证：独立新建 execution，不绑定此前 analysis/measure | 如需报告验证，使用完整 TestCase 的报告链；PDF 存在不证明真实完成/正式合格，现有 source execution/outcome 门不变 |

“mimo_test 成功”不得解除统计窗口、完整 cleanup、重复运行或正式资格项。需要这些事实时使用同一保存 TestCase 的完整执行与执行过滤日志导出，保留 App/DB 证据，不用泛化 HAL trace 替代归属。

## 3. CMW500 + F64 六个现场验证包

以下是验证包，不新增六个重复 backlog ID。顺序按 roadmap；每包可局部完成，整行解除仍须覆盖该条目的全部关闭条件。

| 包 | 前置与操作载体 | 必留证据 / 解除边界 |
|---|---|---|
| V1 活动 RF 路径与安全 | 当前实际使用开关/接线核对；`emcenter_switch_health`，场景已加载后 `propsim_f64_output_level_windows` | 活动口集、映射、逐口窗与当前值、互锁已确认安全或独立可审计安全依据。无拓扑/互锁依据保持 blocked。NEW-1 需同场景 SUCCESS；P2-9 的真实切换与 mapping 还要分别验 |
| V2 当前 main 固定方位 LTE baseline | 真实 DUT 支持的频段、合法 LTE MAC/frame/route、已加载资产、已确认安全站位；保存的 MIMO_OTA TestCase | 同 execution 的 route/config、Cell ON、Attach、真实吞吐、终态与 cleanup/release raw。这是当前版本回归，P0-9/P2-55/56 不重新开项；一份运行结果不解除其余验证包 |
| V3 Cell-ready 三种输入条件 | V1 安全通过；在独占窗口由操作员设置无输入/缺一路/正常输入，使用同一 TestCase 的功率观察配置 | 同固件、活动输入口、本窗口 avg/crest、错误队列和 strict 拒绝/non-strict warning；失败需排除过强等原因。P2-86 只确认测量语义，不以有限功率判 LTE 有效。改线前按站点安全流程停输出，禁止带功率拔接 |
| V4 统计长度与连续执行 | V2 可运行；在 GUI 保存两个不同且服务器接受的合法 MAC statistical_window.count 配置，完整连续执行 | 两次各自 frozen requested/applied、receipt、起止/真实吞吐/错误队列、无旧窗口残留。按 adapter 域选择，不在本文另设数值范围。P1-74 解除仍需边界证据；P1-4 要保留同一配置的两次 execution 与 ReportComparison/repeatability 记录，改长度的两次不能代替重复性对比 |
| V5 多方位、长运动与返回 | 人工清场，已验证 coordinate profile/degree/偏置与批准安全范围；先 `aerotech_positioner_motion_truth`，后同一 TestCase 多方位及 offset-aware 返回 | 各方位实际 PFBK/VFBK、到位/静止、长运动未因 socket idle 中断。小步序列不足以解除 P2-74 长运动；先按该条目在原超时下复验。当前非零 +90° 偏置下 GUI HOME 在 I/O 前拒绝，独立 HOME 无批准载体，继续 blocked；cleanup 的 MOVEABS(0) 不是 HOME，不补真。HOME 与 P1-79E 身份缺口另待方案/资料，不自动解除整行 |
| V6 停止、释放、Local 与再入 | V2 后正常 cleanup，再用 `propsim_f64_local_handback_check` release→面板观察→confirm，随后第二次完整执行 | P2-85 同事务终态及 GOS 拒绝 raw，不把 STOPPED 当 rewind/RF off；NEW-2 需面板 Local 原文；第二次执行无残留资源冲突。正式末态 CLOSED 仍按现有门判 invalid，不据 stop 的安全终态放行 |

最小固定方位通路先做 V1→V2→V6；功率异常优先插 V3。统计窗口正确性做 V4，真实多方位做 V5。V1 不过不得发射/运动；任何未知停止/运动结局按现有安全机制终止，不能为了完成顺序放行。

## 4. 其余验证出口与交接

- UXM 单独排期：P1-17 `uxm_fresh_start_truth` → 合法配置与身份 → P0-5 同一 TestCase；P1-17 含显式导入而非纯只读。NEW-3 `uxm_offset_to_carrier_probe` 仅在已证实本配置需要且原有显式确认/Cell OFF 前置下使用；候选原因不写成必需修复。P2-52/P2-54 无匹配方言结束窗口出处时继续 blocked，不靠 CMW500 结果解除。
- 校准：P1-2 复跑 license_truth 分类，错误/空回复归档；P2-32B 需权威天线口径与对应 SA 标量功率来源及真实链验收。无依据不试探，不要求首次诊断吞吐先完成全部校准。P1-5 不在当前队列。
- 正式资格：P2-61/62 按既有 CE commissioning→认证激活→下一真实执行→冷释放/再入流程；P1-79E 先取得匹配现场控制器的 runtime identity 资料/批准采集载体。运行通不能解除资格。
- 扩域/维护：P2-4 使用 `connection_idle_hold_probe`；P2-13 使用 `uxm_sim_identity_truth`；P2-77 用同资产两合法频点、一越界频点及全组 raw。P2-10/P2-12 未完成事项需先拆验收；P2-71 health 仅支持分类维护，写入/字节验约/回滚缺受控载体仍 blocked。P1-6/P2-63 HOLD 不启动。

解除记录模板（写入既有现场结果文档并回链 roadmap，禁止改历史实测）：

`ID / 子项 | 基线commit与服务版本 | 日期/操作员/站点 | 型号/固件/绑定/资产 | execution/attempt/diagnostic_run | 原始证据位置 | 前置及操作 | requested/applied/终态 | 成功/失败/未知 | 满足哪些关闭条件 | 未覆盖条件 | 解除决定`

只有证据覆盖全部条件才关闭条目；局部通过记“子项完成，仍 blocked”，复测失败保留 raw，超时/载体缺失记阻塞原因及下一步。不建立自动解除端点，不把序列 success、Mock、本地测试或 PDF 存在当解除依据。
