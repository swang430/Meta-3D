# P2-38：Dashboard readiness 显式消费当前 LabProfile 设计

## 可观察故障

P1-57 已把运行态唯一真值收敛为浏览器顶部显式选择的 LabProfile。Dashboard 的
`ZoneReadiness` 仍调用无参数 `/instruments/hal/readiness`，而后端把 HAL 初始化时按
“唯一 active LabProfile”生成的 `lab_profile` 与 `calibration` 快照直接返回。

当数据库存在两个活动 LabProfile、操作员在顶部明确选择其中一个时，Dashboard 仍显示
`ambiguous`，并把系统总判写成与当前工作区不一致的状态；切换顶部选择后，readiness 的
React Query 缓存键也不变，不会立即换到新 LabProfile。

## 真值与产生/消费全集

### 唯一选择真值

- `OperationalLabContext.selectedLabProfileId`：当前浏览器工作区唯一显式选择；
- `OperationalLabContext.selectedLabProfile`：由活动 LabProfile 白名单派生；
- `LabProfile.chamber_config_id`：所选 LabProfile 对应暗室的真值，顶部已展示；
- `LabProfile.active_calibration_certificate_id`：readiness 校准灯的服务端真值。

### 当前产生方

- `InstrumentHALService.last_readiness_report`：HAL 初始化/重载时生成，适合作为驱动、子网、
  DUT attach 的快照，不适合作为浏览器当前 LabProfile 的真值；
- `build_lab_profile_readiness()`：当前只按数据库 active 行数推断；
- `build_calibration_readiness()`：消费传入的 LabProfile readiness，再读取证书；
- `GET /instruments/hal/readiness`：当前无数据库依赖、原样序列化上述 HAL 快照。

### 当前消费方

- `gui/src/api/service.ts::fetchReadiness()`：当前不能传 `lab_profile_id`；
- `ZoneReadiness`：唯一 GUI 消费方；查询键固定为 `['cockpit', 'readiness']`；
- `api/openapi.yaml` 与 `api.generated.ts`：当前没有该查询参数；
- `mockServer` / `mockDatabase`：只提供静态 readiness 响应，查询参数不改变其返回契约。

未发现第二个活动 GUI readiness 消费方，也未发现服务端其他 HTTP 入口复用该响应。

## 方案比较

### A. 请求级重建 LabProfile 与校准部分（采用）

readiness 接受可选 `lab_profile_id`。驱动、子网和 DUT attach 继续使用 HAL 快照；LabProfile
与校准在每次 HTTP 请求中从数据库重建。显式 ID 通过既有 `resolve_lab_profile()` 白名单解析，
不存在或停用时 422，不回退；省略参数继续保留现有 unique-active 的 missing / inactive /
ambiguous / ok 兼容语义。

优点：只替换已经失真的两段来源；切 Lab 不触碰 HAL 生命周期；没有共享选择状态；旧脚本仍可
无参数调用。缺点：每次 10 秒轮询多两次轻量数据库读取。

### B. 每次请求重建整份 readiness

会重新探测驱动、网络和仪器状态，成本与副作用远超本故障，也可能与正在运行的硬件会话争用。

### C. 顶部选择写回服务端全局状态

多个浏览器会互相覆盖，重新制造 P1-57 刚删除的全局/页面平行真值，拒绝采用。

## 采用设计

1. `build_lab_profile_readiness(db, lab_profile_id=None)` 增加可选显式 ID：
   - 有 ID：复用 `resolve_lab_profile()`；精确活动行返回 `ok`；不存在/停用让调用方得到明确错误；
   - 无 ID：保持现有四态与 deterministic detail，作为旧调用方兼容路径。
2. `GET /instruments/hal/readiness` 接受可选 UUID query 与 `get_db`；无论 HAL 是否已初始化，
   LabProfile 和校准段都使用本次请求的数据库真值。`available` 只表达 HAL 驱动快照是否存在。
3. 显式解析错误转 422，并保留服务端 detail；绝不静默回到另一活动 LabProfile。
4. `fetchReadiness(labProfileId?)` 只在有值时发送 query；`ZoneReadiness` 从
   `useOperationalLab()` 取选择，查询键包含该 ID，因此切换立即形成新请求与独立缓存。
5. LabProfile 列表仍由 `OperationalLabProvider` 唯一拉取；Dashboard 不新增列表请求或页面级选择。
6. 同步 live OpenAPI、checked-in YAML 与生成 TypeScript；响应字段形态不扩张。

## 失败与保守方向

- 显式 ID 已停用/删除：返回 422，Dashboard 显示读取失败；不得回退别的实验室形成假绿。
- 顶部尚未选中：Dashboard 禁用查询并明确显示“不可开测”；无参数四态只保留给脚本与旧调用方，
  显式选择消费者不得借兼容路径回退到另一活动 LabProfile。
- HAL 未初始化：驱动段不可用，但所选 LabProfile 与校准仍显示数据库真值；`available=false`
  直接进入红色“不可开测”总判，不只依赖提示 banner。
- 已成功后轮询失败：不再渲染 React Query 缓存中的旧 Lab/校准与绿色总判。
- 切换 LabProfile：React Query key 变化，旧 Lab 的响应不能覆盖新 Lab。
- LabProfile 绑定暗室缺失：顶部选择器继续用 P1-57 的 `chamber_config_id/chamber_name` 明确显示
  “未绑定暗室”；本片不重复新增第二套 chamber 字段或状态枚举。

## TDD 与验收

1. 后端 RED：两个活动 Lab、HAL 快照指向 A，显式请求 B 时修前仍返回 A/ambiguous；GREEN 后
   返回 B 与 B 的证书。
2. 后端 RED：显式不存在/停用 ID 修前被忽略；GREEN 后 422，且不回退。
3. 兼容回归：无参数多活动仍 ambiguous；唯一活动仍 ok；HAL 未初始化时显式 Lab/证书仍可读。
4. GUI RED：`fetchReadiness` 不转发 ID、`ZoneReadiness` 不消费全局上下文、queryKey 不含 ID；
   GREEN 后三项同时成立，且不新增 `fetchLabProfiles` 调用方。
5. 契约：live OpenAPI、checked-in YAML 与生成 TypeScript 都声明可选 `lab_profile_id`。
6. 回归：readiness、LabProfile resolver/P1-57 契约、OpenAPI 规则门、GUI production build、
   `compileall`、`git diff --check` 与全后端。

## 非目标

- 不重连、重载或重新探测 HAL 驱动；
- 不把浏览器选择写进服务端全局状态；
- 不新增页面级 LabProfile 选择器；
- 不改变 LabProfile→暗室的 P1-57 真值链；
- 不执行 P2-40 的任何备份、隔离、移动或删除。

## 实施与验证（2026-08-22）

- 后端显式 ID 复用 active 白名单解析；Lab/校准按请求重建，drivers/subnets/DUT 保持 HAL 快照；
- Dashboard 只有在顶部存在显式选择时才请求，query key 与参数均含同一 ID；HAL unavailable、
  无选择、422/传输错误三类路径全部 fail-closed，不发布缓存旧绿；
- live OpenAPI、`api/openapi.yaml` 与生成 TypeScript 已同步；
- focused readiness / resolver / OpenAPI / 完整 rule gates：**116 passed**；GUI 契约：
  **21 passed**；全后端：**4201 passed / 5 skipped**；production build、`compileall`、
  `diff-check` 通过；
- 首轮 fresh 内审发现 3 条功能 P1，均按 TDD 修复；修后 fresh 内审 **P1=0、P2=1、P3=1**。
  P2 为本设计/计划旧镜像，已在当前提交同步；P3 为可选组件运行时测试建议，按规则不阻塞。
