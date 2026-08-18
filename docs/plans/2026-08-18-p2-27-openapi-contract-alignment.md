# P2-27 OpenAPI Contract Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让九组活动 GUI 手写契约、live OpenAPI 与 FastAPI 实际序列化 JSON 按请求/响应方向一致。

**Architecture:** 响应端在 Pydantic response model 上声明“默认字段在序列化输出中必出”，不把 GUI 响应机械可选化；请求端单独定义 chamber writable shape。前端只补真实漏字段与信封字段，不增加运行时 DTO 翻译层。

**Tech Stack:** FastAPI, Pydantic v2, TypeScript, React/Vite, pytest, openapi-typescript

---

### Task 1: 用 RED 锁住 live response serialization schema

**Files:**
- Create: `api-service/tests/test_p2_27_openapi_contract_alignment.py`
- Modify: `api-service/app/schemas/probe.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/app/schemas/test_plan.py`
- Modify: `api-service/app/api/system_logs.py`
- Modify: `api-service/app/schemas/chamber.py`
- Modify: `api-service/app/services/readiness.py`

**Step 1: Write the failing test**

从 `app.openapi()` 读取 `ProbeResponse`、`HALReadinessResponse` 及其嵌套 readiness 状态、
`ExecutionHistoryItem`、`LogEntry`、`LogTailResponse`、`FEInstrumentCategory`、
`ChamberConfigurationResponse`，逐组断言所有运行时必出的 default/nullable 字段在 `required`。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_27_openapi_contract_alignment.py`

Expected: FAIL，至少 `subnets`、`older_cursor`、`selectedModelId`、`probe_distribution` 不在 required。

**Step 3: Write minimal implementation**

仅在上述 response model（含实际独立出现在 OpenAPI components 中的嵌套 response model）设置
`ConfigDict(json_schema_serialization_defaults_required=True)`；已有 ORM model 同时保留
`from_attributes=True`。readiness/catalog 状态只按现有写方全集收窄为白名单；请求模型不加该配置。

**Step 4: Run test to verify it passes**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_27_openapi_contract_alignment.py`

Expected: PASS。

**Step 5: Commit**

Commit: `fix(api): describe serialized response defaults as required`

### Task 2: 用 RED 锁住 GUI 的真实漏字段与请求方向

**Files:**
- Create: `gui/test/apiContractAlignment.test.ts`
- Modify: `gui/src/types/api.ts`

**Step 1: Write the failing test**

用 TypeScript compiler AST 读取 `types/api.ts`，断言：

- `ProbesResponse` 有 required `total`；
- `InstrumentCategory` 有 required `usagePhase` 与 `driverMode`；
- `ChamberConfiguration` 有 required `probe_distribution`；
- `CreateChamberPayload` 不是 response 的直接 `Omit`，而是仅 `name`、
  `chamber_radius_m` 必填的 writable shape。

**Step 2: Run test to verify it fails**

Run: `cd gui && npx tsx --test test/apiContractAlignment.test.ts`

Expected: FAIL，四组真实漏项均被命中。

**Step 3: Write minimal implementation**

在 `gui/src/types/api.ts`：

- 将 `ProbesResponse` 改为 `{ total: number; probes: Probe[] }`；
- 给 `InstrumentCategory` 补 `usagePhase: string[]`、`driverMode`；
- 给 `ChamberConfiguration` 补 `probe_distribution` 枚举；
- 提取不含 response-only 字段的 `ChamberWritableFields`，定义仅两个必填字段的
  `CreateChamberPayload`，`UpdateChamberPayload` 继续为其 Partial 加 `is_active`。

**Step 4: Run test and production build**

Run: `cd gui && npx tsx --test test/apiContractAlignment.test.ts && npm run build`

Expected: PASS；production build 成功。

**Step 5: Commit**

Commit: `fix(gui): align handwritten API contracts with live schema`

### Task 3: 重跑九组方向性递归审计

**Files:**
- Modify if required by audit only: files from Tasks 1–2

**Step 1: Export current live OpenAPI to a temporary directory**

使用 `app.openapi()`，不得提交临时 schema 或生成 TypeScript。

**Step 2: Generate temporary TypeScript truth**

Run from `gui`: `npx openapi-typescript <temporary-openapi.json> --default-non-nullable false -o <temporary-generated.ts>`

`--default-non-nullable false` 必须保留：本审计验证的是请求可省略语义；若使用生成器默认值，
带后端 default 的 validation 字段会被 TypeScript 误标为 required，与 FastAPI 实际请求契约相反。

**Step 3: Type-check the 18 existing request/response assignments**

保持 response `live → manual`、request `manual → live`；重点确认原九组全部通过，原九组安全契约仍通过。

Expected: 18/18 direction-safe。

**Step 4: If any assignment fails, return to RED before changing code**

不得通过批量加 `?` 或 `any` 消音。

### Task 4: 回归、roadmap 与内审

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Step 1: Run focused and rule gates**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_27_openapi_contract_alignment.py api-service/tests/test_p3_18_handwritten_type_recursive_audit.py api-service/tests/test_rule_gates.py`

Expected: PASS。

**Step 2: Run compile/build hygiene**

Run: `api-service/.venv/bin/python -m compileall -q api-service/app api-service/tests`

Run: `cd gui && npm run build`

Run: `git diff --check`

Expected: all pass/clean。

**Step 3: Update roadmap with actual evidence**

把 Current Focus、P2-27 表项与 LOCAL-OPEN 镜像为当前事实；不得预写未运行的数字。

**Step 4: Fresh internal review**

按 AGENTS.md 先列九组产生/消费全集；P1 修到 0，P2/P3 分栏登记。

**Step 5: Commit and open Ready PR**

Commit: `docs: mark P2-27 ready for review`

触发最多两轮 Codex 外审并按仓库规则收口。
