# P2-27 前端手写契约与 live OpenAPI 对齐设计

## 可观察故障

P3-18 的递归审计发现，仍有九组活动前端手写请求/响应类型不能按正确方向赋值给
live `app.openapi()` 生成的 TypeScript。当前多数端点依靠 Pydantic 在响应序列化时补齐
默认字段，所以界面尚未稳定复现崩溃；但手写契约、OpenAPI 和真实 JSON 三者分叉，后续
生成客户端或收紧消费方时会把“运行时恒有”误当“可能缺失”，也会漏掉真实新增字段。

## 全集与裁决

| 组 | 真实差异 | 裁决 |
|---|---|---|
| `ProbesResponse` | list/bulk 信封不同；`ProbeResponse.chamber_config_id` 有默认值而被 OpenAPI 标成可选；手写信封漏 `total` | list/bulk 共用最小公共响应 `{total, probes}`；响应模型声明序列化默认字段必出 |
| `HALReadinessResponse` | `subnets=[]` 运行时必出、OpenAPI 可选 | 响应序列化 schema 标为必出，不把 GUI 改成可选 |
| `TestExecutionListResponse` | item 的 nullable/default 字段运行时必出、OpenAPI 可选 | `ExecutionHistoryItem` 序列化 schema 标为必出 |
| `SystemLogTailResponse` | entry 默认上下文与 tail cursor/has_older 运行时必出、OpenAPI 可选 | entry/tail 序列化 schema 标为必出 |
| `InstrumentsResponse` / `InstrumentCategory` | `selectedModelId` 等默认字段被标可选；手写漏 `usagePhase/driverMode` | response schema 标必出；手写补齐活动 wire 字段 |
| `ChamberListResponse` / `ChamberConfiguration` | response 继承的默认字段被标可选；手写漏 `probe_distribution` | response serialization schema 标必出；手写补枚举字段 |
| `CreateChamberPayload` | 从完整 response `Omit` 派生，错误地把有后端默认值的创建字段设成必填；同时漏 `probe_distribution` | 单独定义 writable 字段：仅 `name`/`chamber_radius_m` 必填，其余 create 字段可选 |

九组中的 list/bulk、嵌套 category/chamber 按上述合并后仍保持九组审计口径，不另造编号。

## 备选方案

1. **推荐：修正响应序列化真值 + 精确修前端。** 在实际 response model 上启用
   `json_schema_serialization_defaults_required=True`，使 OpenAPI 描述真实响应；前端只补
   `total`、`usagePhase`、`driverMode`、`probe_distribution`，并把 create payload 与 response
   分开。这是换源/收窄，运行行为不变。
2. **把九组手写字段全部改成可选。** 改动少，但会把后端实际恒出的响应字段虚构成不稳定，
   迫使消费方增加无意义 fallback，并掩盖服务端回归；拒绝。
3. **扩充 checked-in `api/openapi.yaml` 并让 GUI 全面改用生成类型。** 长期方向合理，但当前
   YAML 是受 G11 管理的覆盖子集；一次扩入九组端点会把范围扩大到整套文档生成治理，超出
   “修复九组活动契约”故障；本片不做。

## 数据流与边界

- 后端 response model 是 wire 真值。FastAPI 正常响应序列化不会排除未显式设置的默认字段，
  因此 serialization schema 必须把它们列为 required。
- 请求模型保持 validation 语义：有默认值的创建字段仍可省略，不能因响应必出而变成请求必填。
- GUI service 不增加运行时翻译层；只把类型声明改成与既有 JSON 一致。这样不会出现一份新的
  “normalized DTO”副本。
- nullable 与 optional 分开：nullable 表示键存在但值可为 `null`；optional 只用于请求可省略字段。
- 不改变端点、数据库、默认值、分页、错误处理或 UI 行为。

## 保护与验收

1. live OpenAPI 的相关 response model（含 readiness/catalog 嵌套模型）将所有实际序列化字段列入 `required`。
2. list 与 bulk probe 都可赋值给 `{total, probes}`，nested probe 不再因默认字段产生假 optional。
3. 手写 category/chamber 覆盖真实活动字段；create chamber 仅两项必填且不含 response-only 字段。
4. 重新执行 P3-18 同形的 live OpenAPI → TypeScript 方向性递归审计，九组全部通过。
5. 相关/完整 rule gates、GUI production build、compileall、diff-check 全绿。
