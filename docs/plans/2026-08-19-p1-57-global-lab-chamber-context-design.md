# P1-57：全局 LabProfile / 当前暗室上下文统一设计

**状态**：✅ 已于 2026-08-20 由 PR #353 收口（Task 1–6 + 外审 R1–R3 修复 + R4 Gemini 复核无 P1）；本稿为开工前方案，最终形态以 main 为准
**可观察故障**：同一次人工操作中，「探头与暗室配置」显示 `CAICT-16-Probe-Dual`，
「射频拓扑编辑器」却独立选中 `CAICT-5-13`，「暗室首测」又独立记住
`CAICT-Lab-1`。操作员无法确认后续保存、校准或首测究竟作用于哪个暗室。

## 1. 设计结论

运行态唯一真值链固定为：

```text
当前浏览器显式选择的 LabProfile
  -> LabProfile.chamber_config_id
  -> ChamberConfiguration
```

`LabProfile` 是操作上下文的选择单位，暗室是其派生事实。界面不再允许各页面独立选择
“当前暗室”，后端也不再相信客户端自由提交的 `chamber_id`。需要编辑另一个暗室时，
操作员必须先在全局入口切换到绑定该暗室的 LabProfile。

这个“全局”是当前浏览器工作区的全局上下文，不是数据库里的跨用户全局单例。每个请求仍
显式携带 `lab_profile_id`，服务端通过既有
`app.services.chamber_resolution.resolve_current_chamber()` 解析暗室。这样不同操作员可以
同时工作，又不会依赖 `ChamberConfiguration.is_active`、列表首行或进程内全局变量。

## 2. 当前根因

后端 P1-28 已经把正式“当前暗室”收敛到 LabProfile 绑定，但 GUI 仍有多套页面级状态：

- `App.tsx::ProbeManager` 自己维护 `selectedLabProfileId`，并据此读取 active chamber；
- `TopologyEditor` 拉取全部暗室，自有 `selectedChamberId`，首屏还可由最新拓扑行反向播种；
- `Commissioning` 使用 `mimo.commissioning.lastLabId` 单独记忆 LabProfile；
- OTA Mapper、诊断序列、commissioning adhoc、RF chain/calibration 面板各自再次拉取
  LabProfile 并维护本地选择；
- TestCase 创建/编辑中的 LabProfile 是**业务记录绑定**，不是运行态当前上下文，不能与上述
  选择器混为一谈。

因此问题不是数据库缺少关系，而是 GUI 与 topology API 仍允许绕过既有权威 resolver。

## 3. 范围与非目标

### 本片包含

1. App 顶层提供唯一的当前 LabProfile 选择器，并同时显示 LabProfile 与派生暗室名称。
2. 探头/暗室、拓扑编辑、暗室首测、OTA Mapper、调试序列、commissioning adhoc、
   RF chain/calibration 等**运行态暗室消费者**改为读取同一上下文。
3. topology list/create/import/update 以 `lab_profile_id` 为请求真值，服务端派生并校验
   `chamber_id`。
4. 切换 LabProfile 时，对未保存拓扑与已创建 commissioning session 做 fail-closed 阻断。
5. 切换成功后先清掉旧暗室页面状态和缓存，再加载新暗室数据。
6. 旧页面 localStorage key 只做一次迁移，随后删除；不得继续作为真值源。

### 本片不包含

- 不改变 LabProfile 与 ChamberConfiguration 的数据库关系，也不新增“当前 lab”数据库列。
- 不复活或同步 `ChamberConfiguration.is_active`。
- 不迁移、删除或改写 `CAICT-5-13` 等既有 topology/history/calibration 行。
- 不把 TestCase 的持久化 `lab_profile_id` 强行改成当前上下文；它仍是可编辑的记录绑定。
- 不让历史记录随当前上下文重新解释；历史读取继续使用记录自身的 `chamber_id` / lab identity。
- 不顺带重做 LabProfile 管理、权限或跨浏览器同步。

## 4. 全局上下文模型

新增 `OperationalLabProvider`，状态至少包含：

- `activeLabs`、`loading`、`error`；
- `selectedLabProfileId` 与完整 `selectedLabProfile`；
- 从 `selectedLabProfile.chamber_config_id/chamber_name` 派生的 `chamberId/chamberName`；
- `requestLabChange(nextId)`：全局选择的唯一写入口；
- 一个最小的 switch guard 注册接口，供拥有瞬时危险状态的页面只上报阻断原因。

持久化 key 统一为 `mimo.operationalLabProfileId`。初始化规则是白名单：

| 活动 LabProfile 状态 | 选择结果 |
|---|---|
| 0 个 | 无选择，进入既有 LabProfile wizard / 明确错误 |
| 1 个 | 自动选择唯一活动项 |
| 多个 + 持久化 ID 仍在活动集合 | 恢复该 ID |
| 多个 + 无/失效持久化 ID | 无选择，要求操作员显式选择 |
| 选中 LabProfile 无 chamber 绑定或指向缺失 | fail-closed，不加载暗室消费者 |

不得使用 `activeLabs[0]`、第一个 chamber、最新 topology、legacy `is_active` 或页面自己的旧
默认值来填补歧义。

## 5. 切换安全语义

全局选择器调用 `requestLabChange()` 前读取 guard：

- TopologyEditor 有未保存节点/连线修改时，拒绝切换并提示先保存或放弃；
- Commissioning 已创建 session 时，拒绝切换，直到该 session 明确结束或页面重置；
- 其他仅查询页面不注册 guard。

这里需要一个极小 guard 注册表，因为危险状态由子页面拥有，而选择器位于 App header。
把全部页面状态上提到 App 会扩大耦合；让页面各自拦截又会保留多个写入口。guard 只返回
阻断理由，不执行自动保存、自动丢弃或自动结束 session。

切换成功的顺序：

1. 更新全局 LabProfile ID；
2. 清理旧 lab/chamber 作用域的 selection、detail 与 draft；
3. 使用包含 `labProfileId/chamberId` 的 query key 加载新数据；
4. 页面同时显示 `LabProfile / Chamber`，不可只显示其中一个名字。

## 6. Topology 后端契约

拓扑仍持久化 `SwitchTopology.chamber_id`，因为它描述物理接线所属暗室；但请求的权威输入改成
`lab_profile_id`：

- list：必须给 `lab_profile_id`，后端 resolve chamber 后按该 chamber 过滤；
- create/import：必须给 `lab_profile_id`，持久化 resolver 得出的 chamber；
- get/update/delete/validate/paths/calibration-matrix：必须给 `lab_profile_id`，先确认目标
  topology 的 stored chamber 与当前解析 chamber 一致，再允许读取、计算或写入；
- 若为了兼容暂时仍接收 `chamber_id`，它只能是 consistency assertion，和解析结果不一致时
  必须在任何 DB 写入前 409/422；不能覆盖 resolver；
- LabProfile 不存在、已停用、未绑暗室、暗室缺失或 topology 属于另一暗室，都明确失败。

响应继续返回实际 `chamber_id`，并在适合的 response 中补充 lab/chamber identity，供 GUI 审计
显示。`CAICT-5-13` 的旧拓扑不会被迁移；只有切换到绑定它的 LabProfile 后才能读取或编辑。

## 7. GUI 消费方全集裁决

必须换成全局运行态上下文：

- App header 的全局 selector；
- `ProbeManager` / `ChamberConfigCard`；
- `TopologyEditor`（删除“目标暗室”下拉与 latest-row seed）；
- `Commissioning`；
- `OTAMapper/ProbeArraySelector`；
- `Diagnostics/CommissioningAdhocPanel`；
- `Diagnostics/SequenceRunnerPanel`；
- `ProbeCalibration/RFChainDiagramPanel`；
- 施工时全仓再次搜索 `fetchLabProfiles`、`selectedLab*`、`lastLab*`，逐个分类，不能只改上述可见三页。

保留独立记录绑定，不作为当前上下文写方：

- TestCase create/edit 的 `lab_profile_id`；
- LabProfile wizard/manager 中创建或编辑 LabProfile 的 chamber binding；
- 历史 execution/report/calibration 的已记录 lab/chamber identity。

### 7.1 开工实证（2026-08-19，Claude 按计划执行的全集搜索）

`rg "fetchLabProfiles|selectedLab(Profile)?Id|selectedLabId|lastLab|LAST_LAB|fetchActiveChamber|selectedChamberId" gui/src` 命中文件与裁决：

| 文件 | 命中 | 裁决 |
|---|---|---|
| `features/TopologyEditor/TopologyEditor.tsx` | 25 | 运行态 → Task 4 |
| `components/ChamberConfigCard.tsx` | 23 | 运行态 → Task 5 |
| `components/OTAMapper/ProbeArraySelector.tsx` | 18 | 运行态 → Task 6 |
| `features/ProbeCalibration/components/RFChainDiagramPanel.tsx` | 14 | 运行态 → Task 6 |
| `App.tsx`（ProbeManager） | 14 | 运行态 → Task 5 |
| `components/Commissioning/index.tsx` | 7 | 运行态 → Task 5 |
| `features/Diagnostics/SequenceRunnerPanel.tsx` | 6 | 运行态 → Task 6 |
| `features/Diagnostics/CommissioningAdhocPanel.tsx` | 6 | 运行态 → Task 6 |
| `components/TestPlanManagement/TestCaseEditModal.tsx` | 10 | **记录绑定，保留** |
| `components/TestPlanManagement/TestCaseCreateModal.tsx` | 6 | **记录绑定，保留** |
| `features/TestManagement/testCaseLabProfileBinding.ts` | 4 | **记录绑定，保留** |
| `api/labProfileService.ts` / `api/service.ts` | 3+1 | API 层定义，非选择状态 |

与 §7 预判清单一致，无新增站点。topology 链（api/schema/service）28 处命中，Task 3 处理。

## 8. 错误与展示

- 多活动 LabProfile 未选择：所有暗室依赖页面显示统一“请选择当前 LabProfile”，不发请求。
- 绑定缺失/孤儿：显示 LabProfile 名、坏的 chamber ID 与修复入口；不回退其他暗室。
- 列表加载失败：保留当前已解析上下文但禁止切换；不得当成 0 个 LabProfile。
- topology 属于其他暗室：显示“请先切换到对应 LabProfile”，不自动改 topology 的 chamber。
- 页面标题或关键操作区固定展示 `当前：<LabProfile> / <Chamber>`。

## 9. 验收标准

1. 手工切换到 `CAICT-Lab-1` 后，探头配置、拓扑编辑器和暗室首测都显示其绑定的同一暗室。
2. TopologyEditor 不再出现可独立选择的“目标暗室”。
3. 想编辑 `CAICT-5-13` 时，必须先切换到绑定它的 LabProfile；无绑定则先在 LabProfile 管理中绑定。
4. 多活动 LabProfile 且无有效持久化选择时，不自动选择第一项。
5. topology API 传入错 chamber 或错 lab 时在读取/计算/写入前失败，数据库行不变。
6. 未保存拓扑或活动 commissioning session 存在时，LabProfile 切换失败且原上下文不变。
7. 切换后旧暗室的 topology/probe/calibration 缓存不在新页面闪现或被保存。
8. TestCase 的历史/显式 LabProfile 绑定不被全局切换静默改写。
9. 全仓不再有运行态页面以 page-local LabProfile/chamber selector 形成平行真值源。


---

## 10. 实施记录（2026-08-19，Claude）

| Task | commit | 落地物 |
|---|---|---|
| 1 选择状态机 | `78fe9fb` | `operationalLabSelection.ts` 纯函数 + 11 条契约测试 |
| 2 Provider/选择器/guard | `c8172f3` | `OperationalLabContext.tsx` / `OperationalLabSelector.tsx`，main.tsx 挂载，App header 渲染 |
| 3 topology API 换真值 | `57a418e` | 全端点 lab_profile_id；跨暗室 409；PATCH 禁改绑；import 服务端 replace_existing |
| 4 TopologyEditor | `bf833e8` | 删「目标暗室」下拉与播种；dirty guard；重导入单次调用 |
| 5 探头/首测 | `a2f2ed2` | ProbeManager/ChamberConfigCard/Commissioning 收编；重绑后刷新全局上下文 |
| 6 其余消费者 | `2646c43` | OTAMapper/两个诊断面板/RFChain 收编 + 全仓 fetchLabProfiles ⊆ allowlist 门 |

**与设计稿的偏差（如实记录）**：
- §4 初始化表补了一格实测语义：持久化值失效后若只剩一个活动项，按「恰好 1 个」
  规则自动选择（测试 `持久化值停用后只剩唯一活动项` 钉住）。
- import 端点保留可选 `chamber_id` 兼容参数（仅一致性断言）；`replace_existing`
  是新增 query 参数，GUI 重导入走它，初次导入不走。
- PATCH 对 legacy NULL-chamber 行的旧契约（可改名 / 可绑定）被作用域检查取代 ——
  两条旧测试改写为「409 且行不变」（`test_switch_topology_chamber_binding.py`）。
- openapi.yaml 未动：checked-in 契约里本没有 switch-topologies 面（grep 0 命中），
  G11 子集门不受影响。

**验证**：GUI 契约测试 34 条全绿；`npm run build` 通过；`compileall` / `git diff --check`
通过；后端 topology 新门 22 条 + 改写旧门 11 条 + P1-28/lab_resolution/rule_gates 回归全绿。
手工验收（设计 §9 的 1–9 条）**未做**，留给用户在真实环境执行 —— 需要两个绑定
不同暗室的活动 LabProfile，且不能在用户测试会话期间起第二个后端进程。
