# P2-72 Category-scoped HAL Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仪器配置或 driver mode 保存成功后，只激活对应类别的 HAL runtime，并让 LabProfile 同步继续保持显式独立操作。

**Architecture:** 保留“数据库提交”与“硬件激活”两个清晰阶段。新增无请求配置载荷的 category activation API；它在既有 blocker、HAL mutation guard 与 lifecycle lock 下复用启动时的单类别 driver 构造路径，只替换目标类别并执行目标类别 idle park。GUI 串行调用保存与激活，并把“保存成功、激活失败”作为一等结果显示。

**Tech Stack:** FastAPI、SQLAlchemy、asyncio、Pydantic v2、pytest/pytest-asyncio、React 18、TanStack Query、Axios、TypeScript、Node test runner。

**Spec:** `docs/plans/2026-09-06-p2-72-category-hal-activation-design.md`

## Global Constraints

- 全程严格 WIP=1；本片不并行启动其他 roadmap 项。
- 自动激活只读最新已提交数据库配置；请求体不得携带 endpoint、model、driver mode 或 preset。
- “同步到 LabProfile”保持独立操作；自动流程不得调用 `sync-current`，不得写 LabProfile binding。
- 锁顺序固定为 `hal_mutation_guard` → HAL lifecycle lock；blocker 必须在 guard 外与 guard 内各检查一次。
- 自动激活绝不支持 `force`；全局 reload 继续作为操作员恢复入口。
- 只替换目标 `category_key`；其他 driver 实例、连接与状态不得改变。
- 不新增或猜测 SCPI，不改变正式 provenance 白名单，不用 Mock 或旧 driver 静默兜底。
- 沿 D19 既有边界：HAL 操作端点进入 live OpenAPI 和手写 GUI 类型，但不扩入 checked `api/openapi.yaml` / generated TypeScript。
- `api-service/.venv` 与 `gui/node_modules` 是本地依赖链接，任何提交都不得包含。

## File Map

- `api-service/app/services/instrument_hal_service.py`：唯一 driver 解析/构造/连接路径、目标类别原子替换、runtime no-op 判定、readiness 单行合并。
- `api-service/app/services/instrument_test_lease.py`：只停放目标类别的 idle park 原语；全局 park 复用共同失败/取消处理。
- `api-service/app/api/instrument.py`：类别激活 wire schema、blocker 双检查、HTTP 错误映射。
- `api-service/tests/test_p2_72_category_hal_activation.py`：目标类别隔离、no-op、失败安全、锁/blocker、live OpenAPI 行为回归。
- `api-service/tests/test_hal_lifecycle_lock_ordering.py`：新增类别激活也不得把 park 移入 lifecycle lock。
- `gui/src/types/api.ts`：手写 `HALCategoryActivationResult` 类型。
- `gui/src/api/service.ts`：`activateInstrumentCategoryHAL(categoryKey)` 客户端。
- `gui/src/App.tsx`：保存与 driver mode 的两阶段 GUI 编排、部分成功提示与 catalog/HAL cache 刷新。
- `gui/src/features/Equipment/categoryHalActivation.test.ts`：保存顺序、部分成功、driver mode、不得自动 sync 的 GUI 契约。
- `gui/src/features/Equipment/baseStationModelPresetDraft.test.ts`：移除“保存后手工全局 reload”的旧文案断言。
- `docs/roadmap-first-call.md`：实现完成后补验证、PR 与状态；合并前仍保持 WIP。

---

### Task 1: 把启动时 driver 构造收敛为可复用的单类别路径

**Files:**
- Modify: `api-service/app/services/instrument_hal_service.py`
- Create: `api-service/tests/test_p2_72_category_hal_activation.py`

**Interfaces:**
- Produces: `ResolvedCategoryRuntime`（冻结 `category_key`、`driver_class`、`driver_config`、`driver_mode`、model/endpoint 展示字段）。
- Produces: `InstrumentHALService._resolve_category_runtime(db, category) -> ResolvedCategoryRuntime | None`。
- Produces: `InstrumentHALService._initialize_from_db(*, only_category_key: str | None = None) -> dict[str, DriverReadinessRow]`。
- Constraint: 无参数调用保持现有全量启动行为；传 key 时只查询、构造、连接该类别，并把该行合并进现有 `last_readiness_report`。

- [x] **Step 1: 写单类别构造 RED**

新测试先锁住：

```python
@pytest.mark.asyncio
async def test_targeted_initialization_connects_only_requested_category(monkeypatch):
    service = InstrumentHALService(mode=DriverMode.MOCK)
    await service._initialize_from_db(only_category_key="baseStation")
    assert set(service.drivers) == {"baseStation"}

@pytest.mark.asyncio
async def test_targeted_initialization_merges_one_readiness_row(monkeypatch):
    service = InstrumentHALService(mode=DriverMode.MOCK)
    service.last_readiness_report = readiness_with_rows("channelEmulator", "positioner")
    await service._initialize_from_db(only_category_key="baseStation")
    assert {row.category for row in service.last_readiness_report.drivers} == {
        "baseStation", "channelEmulator", "positioner"
    }
```

fixture 使用内存 DB 的三类 active category 与无 I/O fake driver registry；不得连接开发库或真仪器。
`readiness_with_rows(*keys)` 是本测试文件的局部 helper：用现有 `ReadinessReport` / `DriverReadinessRow`
构造指定 category 的 ok 行，并给 lab/cal/dut 填现有 dataclass 所需的明确测试值。

- [x] **Step 2: 运行 RED**

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p2_72_category_hal_activation.py -k targeted_initialization
```

Expected: FAIL，因为 `_initialize_from_db` 尚不接受 `only_category_key`，且 readiness 尚无单行合并。

- [x] **Step 3: 提取唯一 runtime 解析 helper**

在 HAL service 定义：

```python
@dataclass(frozen=True)
class ResolvedCategoryRuntime:
    category_key: str
    driver_class: type[InstrumentDriver]
    driver_config: dict[str, Any]
    driver_mode: str
    model_name: str
    model_label: str
    endpoint: str
    instrument_id: str
    simulated: bool
```

把现有循环中 model/connection/config/driver class 解析搬进 `_resolve_category_runtime`，并复用
`_real_driver_registry()`、`_MOCK_FALLBACK_BY_CATEGORY`、`_decide_use_real()` 与
`_instantiate_hal_driver()` 的原有语义。forced real 无实现时仍写 connection error，不允许回落 Mock。

- [x] **Step 4: 加精确类别过滤与 readiness 合并**

```python
query = db.query(InstrumentCategoryModel).filter(InstrumentCategoryModel.is_active == True)
if only_category_key is not None:
    query = query.filter(InstrumentCategoryModel.category_key == only_category_key)
categories = query.order_by(InstrumentCategoryModel.display_order).all()
```

单类别完成后，以 `category` 为键替换旧 readiness 行，再与未变类别行合并；lab/cal/dut 与 subnet 投影
仍调用现有 builder 重新生成。全量启动继续使用本轮全部行。

- [x] **Step 5: 运行 GREEN 与既有启动回归**

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p2_72_category_hal_activation.py api-service/tests/test_hal_reload_policy.py api-service/tests/test_hal_lifecycle_lock_ordering.py
```

Expected: PASS；既有全量 reload 行为不变。

- [x] **Step 6: 提交 Task 1**

```bash
git add api-service/app/services/instrument_hal_service.py api-service/tests/test_p2_72_category_hal_activation.py
git commit -m "refactor: expose single-category HAL initialization"
```

---

### Task 2: 实现目标类别原子激活与目标类别 idle park

**Files:**
- Modify: `api-service/app/services/instrument_hal_service.py`
- Modify: `api-service/app/services/instrument_test_lease.py`
- Modify: `api-service/tests/test_p2_72_category_hal_activation.py`
- Modify: `api-service/tests/test_hal_lifecycle_lock_ordering.py`

**Interfaces:**
- Consumes: Task 1 的 `ResolvedCategoryRuntime` 与 `_initialize_from_db(only_category_key=...)`。
- Produces: `HALCategoryActivation` 数据类，状态为 `activated | unchanged | inactive`。
- Produces: `activate_hal_category_atomic(category_key: str) -> HALCategoryActivation`。
- Produces: `park_idle_instrument(category_key: str) -> bool`。
- Produces: `HALCategoryNotFoundError`、`HALCategoryConfigurationError`、`HALCategoryActivationError`，
  分别表示未知类别、持久配置不可构造、释放/连接失败；API 依此映射 404/422/503。

- [x] **Step 1: 写隔离替换、no-op 与失败安全 RED**

```python
@pytest.mark.asyncio
async def test_activation_replaces_only_target_driver(monkeypatch):
    result = await activate_hal_category_atomic("baseStation")
    assert result.status == "activated"
    assert hal.drivers["channelEmulator"] is original_f64
    assert hal.drivers["positioner"] is original_positioner
    original_base.disconnect.assert_awaited_once()

@pytest.mark.asyncio
async def test_matching_connected_runtime_is_unchanged(monkeypatch):
    result = await activate_hal_category_atomic("baseStation")
    assert result.status == "unchanged"
    loaded.disconnect.assert_not_awaited()
    assert hal.drivers["baseStation"] is loaded

@pytest.mark.asyncio
async def test_failed_new_connect_removes_stale_target_but_keeps_others(monkeypatch):
    with pytest.raises(HALCategoryActivationError, match="connect failed"):
        await activate_hal_category_atomic("baseStation")
    assert "baseStation" not in hal.drivers
    assert hal.drivers["channelEmulator"] is original_f64

@pytest.mark.asyncio
async def test_real_cmw_disconnect_refusal_keeps_old_object(monkeypatch):
    with pytest.raises(HALCategoryActivationError, match="refused unsafe disconnect"):
        await activate_hal_category_atomic("baseStation")
    assert hal.drivers["baseStation"] is original_cmw
```

再覆盖 endpoint/config/driver mode 变化会重建、断开 runtime 不得 no-op、inactive category 只卸载目标、
取消传播且不吞 release error。
inactive 与 unknown 必须先以独立 DB 查询分类；不能把“active 查询无行”同时解释成二者。

- [x] **Step 2: 运行 RED**

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p2_72_category_hal_activation.py -k 'activation or disconnect or unchanged or inactive'
```

Expected: FAIL，因为激活与目标 park 接口尚不存在。

- [x] **Step 3: 实现 runtime 精确匹配与安全替换**

匹配条件固定为：

```python
same_runtime = (
    type(loaded) is resolved.driver_class
    and loaded.status in {InstrumentStatus.CONNECTED, InstrumentStatus.READY}
    and loaded.config == resolved.driver_config
    and bool(is_mock_driver(loaded)) == resolved.simulated
)
```

不匹配时沿现有 `shutdown()` 的 CMW 安全语义断开目标 driver；只有真实 CMW
`disconnect() is True` 才可删除。其他 driver 抛异常后从 registry 移除，避免断开对象继续被消费。
随后调用单类别初始化；目标未登记时从该类别 readiness 取真实错误并抛 `HALCategoryActivationError`。

- [x] **Step 4: 实现目标类别 park 并保持锁顺序**

```python
async def park_idle_instrument(self, category_key: str) -> bool:
    controls = {
        "channelEmulator": (True, False),
        "baseStation": (False, True),
    }.get(category_key)
    if controls is None:
        return True
```

实际实现必须继续使用 `_coordinated()`、`await_completion_despite_cancellation()` 及现有 delayed
cancellation/error 合并逻辑，再以 `controls` 调 `_settle_local_controls`。`activate_hal_category_atomic`
只在 lifecycle lock 外调用模块级 `park_idle_instrument(category_key)`；锁顺序测试钉死该调用位置。

- [x] **Step 5: 运行 GREEN 与 release 回归**

```bash
api-service/.venv/bin/pytest -q \
  api-service/tests/test_p2_72_category_hal_activation.py \
  api-service/tests/test_hal_lifecycle_lock_ordering.py \
  api-service/tests/test_p1_73b_cmw_connect_lifecycle.py \
  api-service/tests/test_f64_local_control_lifecycle.py \
  api-service/tests/test_uxm_local_control_lifecycle.py
```

Expected: PASS；把 targeted park 的两个 control flag 同时设为 True 的变异必须被测试检出。

- [x] **Step 6: 提交 Task 2**

```bash
git add api-service/app/services/instrument_hal_service.py api-service/app/services/instrument_test_lease.py api-service/tests/test_p2_72_category_hal_activation.py api-service/tests/test_hal_lifecycle_lock_ordering.py
git commit -m "feat: activate one HAL instrument category"
```

---

### Task 3: 暴露无 force 的类别激活 API

**Files:**
- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/tests/test_p2_72_category_hal_activation.py`

**Interfaces:**
- Consumes: `activate_hal_category_atomic(category_key)`。
- Produces: `POST /api/v1/instruments/{category_key}/hal/activate`。
- Produces: `HALCategoryActivationResult` 与 `HALCategoryActivationRefusedResult` wire models。

- [x] **Step 1: 写 200/409/失败映射/live OpenAPI RED**

```python
def test_activation_endpoint_returns_runtime_identity(client, monkeypatch):
    response = client.post("/api/v1/instruments/baseStation/hal/activate")
    assert response.status_code == 200
    assert response.json()["status"] == "activated"
    assert response.json()["category_key"] == "baseStation"

def test_activation_endpoint_refuses_blocker_without_force_hint(client, db):
    make_running_execution(db)
    response = client.post("/api/v1/instruments/baseStation/hal/activate")
    assert response.status_code == 409
    assert response.json()["refused"] is True
    assert "force_hint" not in response.json()

def test_activation_endpoint_maps_runtime_failure_to_503(client, monkeypatch):
    response = client.post("/api/v1/instruments/baseStation/hal/activate")
    assert response.status_code == 503
    assert "配置已保存，但 HAL 尚未激活" in response.json()["detail"]
```

`make_running_execution(db)` 是本文件的局部 helper，按 `TestExecution.status="running"` 和
`executed_by="test_case_runner"` 构造现有 reload policy 会识别的最小执行行。另断言 live
`app.openapi()` 含路径、成功状态枚举与 409 schema；checked YAML 不新增该路径。

- [x] **Step 2: 运行 RED**

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p2_72_category_hal_activation.py -k endpoint
```

Expected: FAIL/404，因为路由尚不存在。

- [x] **Step 3: 实现 blocker 双检查与错误映射**

```python
blockers = find_reload_blockers(db)
if blockers:
    return _category_activation_refused(category_key, blockers)
async with hal_mutation_guard():
    blockers = find_reload_blockers(db)
    if blockers:
        return _category_activation_refused(category_key, blockers)
    try:
        result = await activate_hal_category_atomic(category_key)
    except HALCategoryNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except HALCategoryConfigurationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except HALCategoryActivationError as exc:
        raise HTTPException(503, f"配置已保存，但 HAL 尚未激活: {exc}") from exc
```

路由不声明 `force`；409 body 复用 `HalReloadBlocker` 行形态，但不复用带 `force_hint` 的全局 reload body。

- [x] **Step 4: 运行 GREEN 与 reload policy 回归**

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p2_72_category_hal_activation.py api-service/tests/test_hal_reload_policy.py
```

Expected: PASS；全局 reload 的 force 行为保持原样，类别端点无 force。

- [x] **Step 5: 提交 Task 3**

```bash
git add api-service/app/api/instrument.py api-service/tests/test_p2_72_category_hal_activation.py
git commit -m "feat: expose category HAL activation endpoint"
```

---

### Task 4: GUI 保存后自动激活并显示部分成功

**Files:**
- Modify: `gui/src/types/api.ts`
- Modify: `gui/src/api/service.ts`
- Modify: `gui/src/App.tsx`
- Create: `gui/src/features/Equipment/categoryHalActivation.test.ts`
- Modify: `gui/src/features/Equipment/baseStationModelPresetDraft.test.ts`

**Interfaces:**
- Consumes: Task 3 的 `POST /instruments/{categoryKey}/hal/activate`。
- Produces: `activateInstrumentCategoryHAL(categoryKey: string): Promise<HALCategoryActivationResult>`。
- Produces: `EquipmentMutationResult { updatedCategory, activation?, activationError? }`。

- [x] **Step 1: 写 GUI 编排 RED**

```typescript
test('save awaits category activation and never syncs LabProfile', () => {
  assert.match(saveMutation, /await updateInstrumentCategory/)
  assert.match(saveMutation, /await activateInstrumentCategoryHAL\(categoryKey\)/)
  assert.ok(saveMutation.indexOf('updateInstrumentCategory') < saveMutation.indexOf('activateInstrumentCategoryHAL'))
  assert.doesNotMatch(saveMutation, /syncCurrentInstrumentBinding|sync-current/)
})

test('activation failure preserves save and reports partial success', () => {
  assert.match(saveMutation, /activationError/)
  assert.match(saveSuccess, /配置已保存，但 HAL 尚未激活/)
  assert.doesNotMatch(saveSuccess, /请点击页面顶部.*重新加载驱动/)
})

test('driver mode activates the same category once', () => {
  assert.match(driverModeHandler, /await client\.patch/)
  assert.match(driverModeHandler, /await activateInstrumentCategoryHAL\(category\.key\)/)
})
```

service 测试断言 POST 精确为 `/instruments/${categoryKey}/hal/activate` 且没有请求配置 body。

- [x] **Step 2: 运行 RED**

```bash
cd gui && node --import tsx --test src/features/Equipment/categoryHalActivation.test.ts src/features/Equipment/baseStationModelPresetDraft.test.ts
```

Expected: FAIL，旧实现只保存并提示手工全局 reload。

- [x] **Step 3: 增加手写类型与 API client**

```typescript
export type HALCategoryActivationResult = {
  category_key: string
  status: 'activated' | 'unchanged' | 'inactive'
  driver: string | null
  driver_mode: string
  simulated: boolean | null
  message: string
}

export const activateInstrumentCategoryHAL = async (
  categoryKey: string,
): Promise<HALCategoryActivationResult> => {
  const response = await client.post<HALCategoryActivationResult>(
    `/instruments/${categoryKey}/hal/activate`,
  )
  return response.data
}
```

- [x] **Step 4: 把保存 mutation 改为两阶段结果**

`mutationFn` 先 await PUT；第二阶段单独 try/catch activation，并始终返回 `updatedCategory`。`onSuccess`
先写 catalog/draft；有 `activationError` 时显示“配置已保存，但 HAL 尚未激活：…”并刷新 catalog/HAL
status/readiness，没有错误时显示 `activation.message`。`onError` 只代表保存失败。不得调用 LabProfile sync。

- [x] **Step 5: 把 driver mode handler 接到同一 client**

PATCH 成功后 await `activateInstrumentCategoryHAL(category.key)`；激活失败沿同一部分成功文案处理，不回写旧 mode。
active toggle 与 topology handler 不调用 activation。

- [x] **Step 6: 运行 GREEN 与 production build**

```bash
cd gui && node --import tsx --test src/features/Equipment/categoryHalActivation.test.ts src/features/Equipment/baseStationModelPresetDraft.test.ts src/features/Equipment/channelEmulatorModelPresetDraft.test.ts
npm run build
```

Expected: 所有合同 PASS，TypeScript/Vite production build PASS。

- [x] **Step 7: 提交 Task 4**

```bash
git add gui/src/types/api.ts gui/src/api/service.ts gui/src/App.tsx gui/src/features/Equipment/categoryHalActivation.test.ts gui/src/features/Equipment/baseStationModelPresetDraft.test.ts
git commit -m "feat: activate category HAL after instrument save"
```

---

### Task 5: 全链验证、主代理自查与 Ready PR

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Verify only: all files changed since base

**Interfaces:**
- Consumes: Tasks 1–4 完整功能。
- Produces: 可复核验证记录、主代理自查结论、Ready PR 与 Codex R1→R2 外审记录。

- [x] **Step 1: 运行受影响链与规则门**

```bash
api-service/.venv/bin/pytest -q \
  api-service/tests/test_p2_72_category_hal_activation.py \
  api-service/tests/test_hal_reload_policy.py \
  api-service/tests/test_hal_lifecycle_lock_ordering.py \
  api-service/tests/test_base_station_model_presets.py \
  api-service/tests/test_p2_58_2_channel_emulator_model_presets.py \
  api-service/tests/test_p1_73b_cmw_connect_lifecycle.py \
  api-service/tests/test_f64_local_control_lifecycle.py \
  api-service/tests/test_uxm_local_control_lifecycle.py \
  api-service/tests/test_rule_gates.py
```

Expected: PASS；不得把本地回归表述成真机复验。

- [x] **Step 2: 运行全后端与静态检查**

```bash
cd api-service
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app tests
.venv/bin/alembic heads
```

Expected: 全后端零失败；compileall 成功；Alembic 只有一个 head，且本片无 migration。

- [x] **Step 3: 运行受影响 GUI 合同与 build**

```bash
cd gui
npx --yes tsx --test \
  src/features/Equipment/categoryHalActivation.test.ts \
  src/features/Equipment/baseStationModelPresetDraft.test.ts \
  src/features/Equipment/channelEmulatorModelPresetDraft.test.ts
npm run build
```

Expected: 本片受影响 GUI 合同与 production build PASS。仓库历史测试没有一个可受支持的“全文件
单命令”运行器；按 `CLAUDE.md` 验证分档执行受影响交互，不把不兼容的扩展名/导入方式扫描冒充门。

- [x] **Step 4: 做 base-to-HEAD diff-check 与主代理功能自查**

```bash
git diff --check 05c7c0d9..HEAD
git status --short
git diff --stat 05c7c0d9..HEAD
git diff 05c7c0d9..HEAD -- api-service/app/services/instrument_hal_service.py api-service/app/services/instrument_test_lease.py api-service/app/api/instrument.py gui/src/App.tsx gui/src/api/service.ts gui/src/types/api.ts
```

逐项确认：只改目标类别；no-op 不重连；失败不留伪激活；blocker 双检查；park 在 lifecycle lock 外；
保存与激活错误分流；没有 `sync-current` 调用；没有新增 SCPI 字面量；`api-service/.venv` 未暂存。
由于用户指定单 agent 顺序执行，自查必须如实标为“主代理自查，非独立内审”。

- [x] **Step 5: 更新 roadmap 完成证据并提交**

在 P2-72 条目补当前 HEAD 的专项/全量/GUI/build/compileall/Alembic/diff-check 数字；状态写“Ready PR”，
不提前写已合并。

```bash
git add docs/roadmap-first-call.md
git commit -m "docs: record P2-72 verification"
```

- [ ] **Step 6: 推送并创建 Ready PR**

PR 描述只声明实际跑过的验证，并明确可观察故障、两阶段语义、LabProfile sync 未自动化、
主代理自查而非独立内审、零 SCPI / 零 provenance 变化、本地验证不能替代现场复验。

- [ ] **Step 7: 执行 Codex R1→R2 收口**

R1 处理功能 P1 与本片内 P2；修复后重新跑必要回归并触发覆盖最新 HEAD 的 R2。R2 无 P1 且 PR
mergeable/checks 通过或无必需 checks 才可 merge；R2 若仍有 P1，只处理 P1 并续审到覆盖最新 HEAD
的一轮无 P1。R2+ P2/P3 只报告，不阻塞、不自动积压。

- [ ] **Step 8: 合并后同步与清理**

fetch 验证 `origin/main`，主目录 ff-only 同步，保留所有未跟踪仪器资料；删除本 worktree 与本地分支。
roadmap 的 P2-72 状态只在合并事实成立后更新为完成；不得自动启动 P1-76 或其他 feature。
