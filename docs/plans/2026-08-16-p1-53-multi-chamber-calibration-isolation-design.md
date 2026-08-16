# P1-53 多暗室探头校准隔离设计

## 可观察故障

`probe_id` 已按暗室局部编号，但探头幅度、相位、极化、方向图的部分 REST 写入、查询、有效性汇总和正式报告仍只按 `probe_id` 工作。两个暗室都存在 `probe_id=1` 时，后写入的 B 暗室记录可能被 A 暗室页面、有效性结论或 PDF 选中，形成没有报错的错误校准数据。

P1-28 已完成“当前暗室”真值源和五张表的 `chamber_id` 基础列；P1-53 只收口这批基础列尚未贯通的生产入口，不扩展到已独立按暗室键控的 path-loss/RF-chain/channel 校准，也不处理无人消费的旧 orchestrator 导入导出死链。

## 入口全集

### 写入

1. `POST /calibration/probe/amplitude/start`
2. `POST /calibration/probe/phase/start`
3. `POST /calibration/probe/phase/import-csv`
4. `POST /calibration/probe/polarization/start`
5. `POST /calibration/probe/pattern/start`
6. `POST /calibration/probe/pattern/import`
7. `AmplitudeCalibrationService`、`PhaseCalibrationService`、`PolarizationCalibrationService`、`PatternCalibrationService` 的生产写入方法

### 读取与判定

1. amplitude / phase / polarization 的 latest 与 history
2. pattern 的列表读取
3. `GET /calibration/probe/{probe_id}/data`
4. validity report / expiring / expired / single-probe status
5. 四类探头校准按 UUID 作废；LinkCalibration 保持全局作废语义
6. `CalibrationValidityService` 的 latest、报告和过期清单
7. `probe_pattern.consumer` 的正式 MIMO/TRP 消费
8. `CalibrationReportGenerator` 的 probe/comprehensive PDF 数据收集与 PDF 家族表

### 前端消费

`probeCalibrationService`、React Query key/hook、Probe Calibration dashboard/grid/detail 与启动/导入表单。缓存键也必须含 chamber，避免切换暗室后复用上一暗室响应。

## 方案比较

### A. 每个入口显式要求 `chamber_id`（采用）

- 写入、读取、有效性和报告都把 `chamber_id` 作为必填契约。
- 后端先确认暗室存在，再按暗室 `num_probes` 校验零基探头编号范围；当前校准链的
  `probe_id` 是 0..N-1，而 `Probe.probe_number` 是一基展示编号，不能拿后者做所有权判据。
- SQL 只接受 `row.chamber_id == requested_chamber_id`；不回退 `NULL` legacy，也不读取其他暗室。
- 前端从 P1-28 的当前 LabProfile/暗室真值取得 ID，并将其贯穿请求和缓存键。

优点是边界清楚、可审计、切换暗室不会依赖进程全局状态；缺配置会在写入或生成报告前明确失败。代价是 REST/GUI 合同需要同步变更，但这是修复跨暗室假数据所需的最小完整改动。

### B. 所有入口隐式解析“当前暗室”（不采用）

改动较小，但历史/报告查询无法稳定表达“查看另一个暗室”，后台任务也会受当前 UI 选择影响。它把显式数据维度重新藏进全局状态。

### C. 只在查询时 prefer exact、再回退 `NULL`（不采用）

这是 P1-28 基础期的单暗室兼容形态。多暗室上线后，`NULL` 无法证明属于哪个暗室；回退会把来源未知的 legacy 行当正式校准，仍可能输出假结论。

## 数据与迁移

- amplitude / phase / polarization / pattern 已有 nullable `chamber_id`，本片不自动猜测或回填 legacy NULL。
- 新写入一律要求非空暗室；历史 NULL 仅保留审计，不进入正式 latest、有效性或报告。
- 七张正式判定可见表（四类探头、全局 Link、RF-chain、multi-frequency）新增 nullable
  `use_mock`：`False` 表示本轮真实测量或厂商文件导入，`True` 表示
  mock/random 流程演练，`NULL` 表示历史来源未知。迁移不回填，避免把旧行伪装成真实。
- `probe_calibration_validity` 当前没有生产写入/读取方，正式有效性由 `CalibrationValidityService` 现算。本片不为死表新增复合主键机制；改为用规则门锁住生产代码不得把它当权威源。将来若恢复物化汇总，须另做 `(probe_id, chamber_id)` 迁移。
- 不加破坏性外键或清理脚本；P1-28 的 orphan 诊断与删除门继续负责存量完整性。

## API 与服务语义

1. 四类 start request 增加必填 `chamber_id`；两个 multipart import 增加必填 form 字段。
2. latest/history/pattern/data/validity/expiring/expired 增加必填 query `chamber_id`。
3. probe/comprehensive report 在包含 probe 数据时要求 `chamber_id`；报告中的四类探头记录，
   以及已经自带暗室维度的 path-loss / RF-chain / multi-frequency 记录都只接受 exact chamber。
   报告 payload 每行携带 chamber ID，PDF 标题或摘要明确暗室。
4. replace-existing 只作废相同 chamber、probe、polarization/frequency 的旧行，绝不触碰其他暗室。
5. invalidate 对四类探头校准要求 `chamber_id` 并按 `(id, chamber_id)` 修改；
   `LinkCalibration` 仍按现有全局语义作废，不伪造暗室归属。
6. lower-level service 的正式消费必须传 chamber；若调用方没有 chamber，不得静默退回全局 probe 编号查询。
7. 正式有效性、报告统计和 pattern 消费只接受 `use_mock is False`；mock 与历史 NULL
   可在审计读取中展示，但判词保持 UNVERIFIED、不得进入正式分母或 MIMO 增益补偿。
   amplitude / phase / polarization 历史项必须同行返回该 provenance；漂移趋势只用
   explicit-real 记录计算，不能把模拟或来源未知数值混入派生趋势。
   全局 Link 可单独展示设施状态，但不参与单探头四类完整性的 overall 判定；其 validity、
   临期/过期汇总同样只接受显式 real，并在 explicit-real 白名单内选最新记录，避免较新的
   mock 遮住仍有效的真实记录。单探头只有 amplitude / phase / polarization / pattern 四族
   齐全且全部有效才可 overall VALID；部分家族缺失时为 PARTIAL，全部缺失时为 UNKNOWN。
   validity report 必须同行返回逐探头权威 `overall_status`，Dashboard 与 Grid 不得再从
   expired/expiring 列表反推状态。当前硬编码 mock 的 RF-chain / multi-frequency 写入口
   必须持久化 `True`，不得因数据库 `status=valid` 在 PDF、正式状态或路损插值数值接口中
   变成 PASS/有效补偿。
8. 报告有效性同时检查 `valid_until`；过期记录不得仅凭持久化 `status=valid` 显示 PASS。
9. PDF 必须渲染 collector 纳入摘要的全部家族；RF-chain 与 multi-frequency 不得只计数不展示。

## 前端行为

- Probe Calibration 页面在当前暗室未解析、冲突或缺失时 fail-closed，显示可操作错误，不发无作用域请求。
- 探头网格数量来自当前 `ChamberConfiguration.num_probes`，不得默认 32 或生成不存在的探头。
- 暗室 ID 进入所有 probe calibration query key；切换暗室会产生新缓存域。
- 四类探头作废客户端契约必须携带同一暗室 ID；Link 作废继续保持全局语义。
- 启动和导入请求使用同一个已解析暗室 ID，不允许表单另藏一个自由文本暗室。
- 页面标题/摘要显示当前暗室名称，避免操作员把 B 暗室结果当作 A 暗室。
- 详情组件对 `use_mock=True` 显示 `SIMULATED · UNVERIFIED`，对历史 `NULL` 显示
  `SOURCE UNKNOWN · UNVERIFIED`；只有显式 `False` 才可显示 VALID/PASS。数值保留用于审计，
  但必须与来源同行展示；只有显式 real 的阈值判词可以使用绿/黄/红，模拟或来源未知数值
  一律使用中性颜色。当前页面尚无生产路由入口，本片只收口已存在的组件/请求契约，
  不借机恢复一条未完成的导航链。

## 错误处理

- 缺 `chamber_id`：FastAPI 422，任何写入/报告生成前失败。
- 暗室不存在：404。
- 探头编号不在该暗室 `0 <= probe_id < num_probes` 范围：400；请求体自身结构错误仍由 FastAPI 返回 422。
- 该暗室只有 legacy NULL 或其他暗室记录：latest 返回 404、有效性返回 unknown，不回退。
- 报告请求缺暗室或找不到该暗室记录：生成 UNKNOWN/空作用域摘要或明确失败；不得混入其他暗室记录来凑数据。

## TDD 验收

1. 同一 `probe_id` 在 A/B 暗室各有不同校准，A 的 latest/history/data/validity/expiring/expired 只返回 A。
2. 六个写入入口均落正确 `chamber_id`；replace-existing 不作废另一暗室。
3. A 无记录、B 有记录、legacy NULL 有记录时，A 不得取 B 或 NULL。
4. pattern consumer 在 A 无 exact 时返回 missing，不回退 B/NULL。
5. probe/comprehensive report 的全部暗室相关数据行（含既有 path-loss / RF-chain /
   multi-frequency 家族）和正式统计仅含请求暗室。
6. GUI 请求与 React Query key 均含当前暗室；无当前暗室时不发请求。
7. 完整 probe calibration 回归、P1-28 真值源回归、报告回归、rule gates、GUI build、compileall 与 diff-check 通过。
8. 跨暗室作废被拒绝；非 32 探头暗室无 phantom probe；mock/legacy/expired 不得正式 PASS；
   极化报告读取持久化隔离字段，RF-chain/multi-frequency 在 PDF 可审计。
9. mock/legacy Link、RF-chain、multi-frequency 在报告、validity 和详情中保持 UNKNOWN/
   UNVERIFIED；Link-only 不得把没有四类可信记录的探头判为 valid。
10. “1 个探头四族齐全 + 1 个探头仅部分齐全”时，report 返回逐探头 valid/partial，
    Dashboard 不得把整个暗室显示为 VALID，Grid 必须直接展示权威 partial 状态；非 real
    polarization/Link 数值不得获得阈值通过或失败颜色。

## 非目标

- 不自动迁移/删除 legacy NULL 或 orphan 校准数据。
- 不重做 path-loss、RF-chain、channel calibration 的测量流程与既有暗室维度；本片只为
  RF-chain 补 provenance 持久化/正式消费门，并要求 probe/comprehensive report 按请求暗室
  过滤这些已有数据源，不能让报告边界成为旁路。
- 不修 `CalibrationOrchestrator.export/import_calibration_data` 无调用死链。
- 不顺手处理 SystemCalibration 页面既有硬编码暗室 ID；它需要以自己的活动入口和数据模型另行 triage。
