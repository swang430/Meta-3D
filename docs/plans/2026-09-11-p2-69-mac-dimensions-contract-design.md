# P2-69 — MAC capability `dimensions` 输出契约补齐设计

> 状态：**✅ 已由 PR #473 合并**（merge `4ca4aba6`；用户于 2026-09-11 选择方案 A）。
> roadmap 条目：`docs/roadmap-first-call.md` `### P2-69`。

## 1. 可观察故障与目标

真实 `GET /api/v1/instruments/catalog` 会把
`RealCmw500Driver.adapter_manifest.mac_profiles[].dimensions` 序列化到响应中。后端 Pydantic
模型和 live OpenAPI 已定义 `BaseStationMacDimensionCapability` /
`BaseStationMacDimensionValueCapability`，但 checked-in `api/openapi.yaml` 的
`BaseStationMacProfileCapability` 没有 `dimensions`，同时设置了 `additionalProperties: false`。
因此，严格按 checked OpenAPI 校验响应的客户端会拒绝服务器自己的合法 CMW500 响应；由该 YAML
生成的 TypeScript 和 GUI 手写类型也看不到这部分能力。

目标是让 live OpenAPI、checked OpenAPI、generated TypeScript、手写 TypeScript 与真实目录响应
精确一致。只补输出契约，不改变 adapter manifest、compatibility digest、CMW 能力范围、正式资格门、
HAL/Adapter 行为或任何 SCPI。

## 2. 全集与验收关系

| 环节 | 权威源 / 站点 | 本片结论 |
|---|---|---|
| 生产能力声明 | `app/hal/cmw500_base_station.py::RealCmw500Driver.adapter_manifest` | 已输出完整 `dimensions`；不改 |
| 公共结构定义 | `app/hal/base_station_manifest.py::{BaseStationMacProfileCapability, BaseStationMacDimensionCapability, BaseStationMacDimensionValueCapability}` | Pydantic 与 live OpenAPI 已完整；不改 |
| 正式兼容性 | `app/hal/base_station_compatibility.py` | `dimensions` 不进入既有 manifest digest；不改 |
| API 生产入口 | `app/api/instrument.py::_convert_model` → `GET /api/v1/instruments/catalog` | 使用真实序列化响应做验收；不改 |
| checked 契约 | `api/openapi.yaml` | 补两个嵌套 schema 和 profile 的 `dimensions` |
| generated 客户端 | `gui/src/types/api.generated.ts` | 只通过 `npm run openapi:generate` 重生成 |
| 手写客户端镜像 | `gui/src/types/baseStationManifest.ts` | 补精确等价的 dimension/value 类型 |
| 既有语义测试 | `test_p2_55_capability_matrix.py`、`test_p2_56_lte_tdd_capability.py` | 保护现有 CMW 值域；只回归，不改能力 |
| 契约测试 | `test_p2_46_openapi_contract.py` + P2-69 新测试 | 从真实目录响应证明 checked 契约可接收合法 CMW payload |

产生/消费方枚举结果中没有需要另行排期的相邻功能缺陷；GUI 当前不渲染维度矩阵，本片也不新增
界面，因为可观察故障是输出契约拒绝合法响应，不是缺少新的能力编辑器。

## 3. 方案与边界

采用方案 A：精确镜像现有 Pydantic 结构。

- `BaseStationMacProfileCapability.dimensions` 是数组，元素引用
  `BaseStationMacDimensionCapability`；与 live schema 一致，它有默认空数组但不是 required 字段。
- dimension 含 `dimension` 与非空语义由后端模型维护的 `values` 数组。
- value capability 精确表达 `value: string | integer | boolean | null`、support 枚举、OR/AND 选件、
  nullable firmware、前置条件、reason 与 source reference。
- `additionalProperties: false` 保持，不能降级成 `object[]` 或自由字典。
- 不隐藏服务器现有 `dimensions` 输出；不为契约补齐顺带开放新的 CMW 组合。

拒绝的替代方案：

1. `dimensions: object[]`：严格客户端仍不知道值类型、选件关系和前置条件，失去契约意义。
2. 从 API 响应删除 `dimensions`：会隐藏已经由 P2-55/P2-56 建立的真实能力声明。
3. 修改后端模型使字段 required：会改变 UXM 等空维度 manifest 的公开契约，超出本片。

## 4. 严格 TDD 与变异

1. **RED：真实响应**。从真实 `TestClient` 目录响应提取 CMW500 manifest，以 checked OpenAPI 的
   `BaseStationMacProfileCapability` 递归校验每个 MAC profile。当前应因额外属性 `dimensions` 失败。
2. **RED：镜像精确性**。断言 live/checked 的三个 MAC capability schema 具有相同 property、required、
   enum/const、引用和 nullable/value 联合结构；当前 checked YAML 缺 schema，应失败。
3. **GREEN：checked YAML**。只补上述三个 schema 的缺口。
4. **GREEN：TS 两镜像**。重生成 `api.generated.ts`，给手写类型增加精确等价结构，并用 TypeScript
   类型夹具覆盖 string/integer/boolean/null 与空/非空 dimensions。
5. **变异实跑**：临时删掉 checked YAML 的 `dimensions` 属性，真实响应校验必须红；恢复后重新跑绿。

## 5. 验证与交付

本片按“GUI/API 契约”档验证：P2-69 RED→GREEN、P2-46 OpenAPI、真实目录响应、P2-55/P2-56
能力回归、GUI 类型契约和 production build。生产后端行为不变，因此默认不机械跑全后端；若实现 diff
触及后端运行代码或共享行为，则升级到后端全量。

主代理顺序完成实现、验证和自查，PR 明记“主代理自查，非独立内审”。Ready PR 后按仓库规则走
Codex R1→R2；只有覆盖最新 HEAD 的 R2 无 P1 且 mergeable/checks 通过或无必需 checks 才合并。

NotebookLM：本片不修改仪器语义、SCPI、参数范围或硬件动作，明确不适用。
