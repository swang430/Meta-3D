# P2-58 ② 设计稿 — 信道仿真器分型号 saved presets + GUI 消费 ① 的 binding 真值

> 状态：**待 review，未动代码**（⓪⁺②）。依赖 ① = PR #450 合并。
> 本稿在 ① 外审期间写成，放 scratchpad，① 合并后随 ② 分支进 `docs/plans/`。

## ⓪ 动手前四行

```
搜索命中：memory —— feedback_addcolumn_migration_dialect_agnostic（加列迁移方言无关 + column_exists 守门）、
          feedback_api_contract_sync_after_pydantic_change（Pydantic 响应字段改动 → 契约四步）、
          feedback_react_query_shape_change_needs_new_key、feedback_react_latch_state_not_trigger、
          feedback_gui_two_verification_gates（build + 浏览器实测两道门）；
          仓库权威参照 —— app/services/base_station_model_preset.py（save_base_station_model_preset 原子保存）、
          gui/src/features/Equipment/baseStationModelPresetDraft.ts、alembic f2a4c6e8b0d1（加列迁移形状）
必要性：切换 CE 型号（F64 ↔ FS16）会**覆盖**当前连接字段，另一型号的 endpoint / alignment_name 丢失 ——
       BS 在 #426 已治，CE 没有。且 ① 的 preview/readiness 真值 GUI 尚无消费方。
范围：见 §3；枚举到 ①/G/B/C 留下的 8 处镜像站点，本片全收（它们就是 ② 的目的）
爆炸半径：原 bug 最坏 = 切型号静默丢另一型号的配置（无提示）；修完最坏 = 切型号前弹确认、保存 422（吵）。Y ≤ X ✅
```

## 1. NotebookLM 适用性：**不适用**（显式记）

纯配置持久化 + GUI；本片没有任何一句断言「仪器怎么样」。

## 2. 参照物与差别（有意的）

| | BaseStation（#426，已在） | CE ②（镜像） |
|---|---|---|
| 持久化 | `instrument_connections.base_station_model_presets` JSON nullable，键 = `InstrumentModel.id` | 新列 `channel_emulator_model_presets` JSON nullable，同键 |
| 迁移 | `f2a4c6e8b0d1`：add-column + `column_exists` 守门，所有方言跑 | 同形状新迁移（**不要**套约束手术的 PG-only 模板）|
| 单个 preset | `BaseStationModelPreset(schema_version, model_id, endpoint, controller, notes, connection_params, base_station_adapter_profile)` frozen | `ChannelEmulatorModelPreset(schema_version, model_id, endpoint, controller, notes, connection_params)` —— **无 adapter_profile 槽**（CE 无 profile 层，与 ① 契约一致）；`alignment_name` 继续住在 `connection_params` 里 |
| 原子保存 | `save_base_station_model_preset`：快照旧活动型号（若未存过）→ 校验目标 → 写整张 map → `flag_modified` → 目标投影成活动连接字段 | `save_channel_emulator_model_preset` 同形；**不覆盖其他型号**靠「只改 map 里 target 键」这一条 |
| 运行期参数剔除 | `BASE_STATION_RUNTIME_CONNECTION_PARAM_KEYS = {"detected_test_app"}`（HAL **连接时**回读的 Test App，真运行期观测） | **`CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS = set()`** —— CE 今天**没有**连接期回读进 `connection_params` 的键。外审 #451 R2 纠正了本稿初版：`available_channel_models` 曾被我按 `detected_test_app` 类比成「运行期观测、剔除」，实测其 4 个写入点（`api/instrument.py:1981/2056` 操作员增删 curated list、`standard_channel_service.py:363` SCD 关联投影、`smu_project_inventory.py:746` 操作员触发的 smu-sync 扫描）**全是操作员/同步触发的持久化**，且 F64 ATE 模式无 MMEM/FTP **无法运行期重新发现** —— 它是**型号专属配置资产，必须保留在 preset**，否则切 F64→FS16→F64 会把操作员维护的模型清单清空。`topology_profile_id` / `default_emulation_file` / `smu_project_scan` 亦为操作员配置，保留。空集合保留是为与 BS 同形并给将来真正的运行期键留位 |
| 前端切型号 | `handleModelChange` 的 `baseStation` 分支 → `draftForBaseStationModel(category, modelId)`，**无确认**，静默换草稿 | 加 `channelEmulator` 分支 → `draftForChannelEmulatorModel`；**切换前弹确认**（用户决定 ③：丢未保存草稿）。⚠️ BS 今天没有这个确认 —— 要不要补给 BS 是越界，进 Discovered |
| 保存路径 | `sync-current` 里 BS 分支 | ① 已加 CE 分支的 fail-closed 校验；② 在它之前接 `save_channel_emulator_model_preset` |

## 3. 范围（预估 11 文件，其中 4 个是 ① 留下的镜像站点）

**后端（5）**
1. `app/models/instrument.py` —— 加列 `channel_emulator_model_presets`
2. `alembic/versions/<new>_add_channel_emulator_model_presets.py` —— 镜像 `f2a4c6e8b0d1`
3. `app/services/channel_emulator_model_preset.py`（新）—— `ChannelEmulatorModelPreset` / `parse_*` / `save_*`
4. `app/api/instrument.py` —— 连接更新端点在 CE 品类下调 `save_*`；`FEInstrumentConnection`（:89，嵌在 `FEInstrumentCategory` 里返回）加 `channel_emulator_model_presets`（Pydantic 响应字段 → 契约四步）
5. `tests/test_p2_58_2_channel_emulator_model_presets.py`（新）

**契约（2）**
6. `api/openapi.yaml` —— `InstrumentConnection.channel_emulator_model_presets`（schema 在 :2495）+ 复核 ① 那两个 schema
7. `gui/src/types/api.generated.ts` —— 重生

**前端（4，全部是 ①/G/B/C 登记的镜像站点）**
8. `gui/src/api/labProfileService.ts:115` 旁 —— `fetchChannelEmulatorBindingPreview`（契约第 3 步）
9. `gui/src/api/mockServer.ts` + `mockDatabase.ts:99` —— 两个新端点的 mock（第 4 步）
10. `gui/src/types/api.ts:403` —— 手写 readiness 类型补 `channel_emulator_binding`（非 `?:`，① 已定 required）；`gui/src/features/Equipment/channelEmulatorModelPresetDraft.ts`（新，镜像 BS 那份）；`App.tsx` 的 `handleModelChange` CE 分支 + 确认弹窗
11. `gui/src/features/Dashboard/ZoneReadiness.tsx:142` —— readiness 灯消费 `channel_emulator_binding.status`

**① 留下的两格判定**（B 的歧义 #1，归 ②）：preview 端点对「TestCase 存在但 `test_type != "MIMO_OTA"`」或「其 `lab_profile_id` 与所选 LabProfile 不一致」—— 建议 **404 + 中文 detail**（CE 无 compatibility 槽位，返回 null 会伪装成「没选资产」；与 B 对「TestCase 不存在 → 404」同口径）。

## 4. 门的设想（每条配让它变红的变异）

1. **不覆盖其他型号**：先存 F64 preset，再切到 FS16 保存 → F64 的 map 项**逐字节不变**；变异：保存时整张 map 重写 → 红
2. **切型号前旧活动被快照**：从未存过 F64、活动连接是 F64、切到 FS16 保存 → map 里出现 F64 快照；变异：删快照分支 → 红
3. **运行期观测键不进 preset**：`connection_params` 带运行期键保存 → preset 里没有它；变异：不剔除 → 红
4. **迁移双向 + 幂等**：`column_exists` 守门，二次 upgrade 不炸（照 f2a4c6e8b0d1 的既有测试形状）
5. **契约四步对齐**：G11（yaml ⊆ live）+ P2-27（required == properties）+ `npm run build` + **浏览器实测**切型号确认弹窗（memory：GUI 两道门缺一不可）
6. **确认弹窗**：有未保存草稿时切型号 → 弹确认；取消 → 草稿不变、型号不变；确认 → 草稿替换；变异：跳过确认 → 红
7. **readiness 灯**：`channel_emulator_binding.status` 四态各自映射到灯色/文案，`invalid` 必须可见（不许沦为灰）；变异：`invalid` 映射成与 `configured` 同色 → 红

## 5. Discovered（本稿枚举、不在 ② 做）

- **Discovered-4**：BS 的 `handleModelChange` 切型号**无确认**，静默换草稿 —— ② 给 CE 加了确认，BS 与之不一致。补给 BS 是越界，另评。
- **Discovered-5**：`_freeze_instrument_lease` 的 `validation_identity` 纳入 CE digest（= ① 的 Discovered-3 后半）—— 与 preset 无关，不进 ②。

## 6. 需要你拍板的（② 开工前）—— 只剩一个

1. **F64 ↔ FS16 切换时，`alignment_name` 算型号 preset 的一部分吗？** 我倾向算（它住在 `connection_params`，随 preset 走；切回 F64 不必重填）。

~~2. readiness 灯的 `invalid` 显示为红还是黄？~~ **不需拍板，照抄 BS**：`gui/src/features/Dashboard/baseStationBindingTruth.ts:46-66` 已定 —— `invalid` → **红**（:51-53）、`simulated` / `diagnostic_unbound` → 黄（:58-60）、`configured` 真驱动 → 绿（:66）。CE 的 `channelEmulatorBindingTruth.ts` 镜像同一映射；与 ① 「判不出 = 吵的一侧」一致。

**脚注 `smu_project_scan`**：只被 `app/services/smu_project_inventory.py:301` **读**（`params.get("smu_project_scan")`，操作员配置的只读挂载 `local_mount_root` / `instrument_root`，:118-136 校验必须是绝对路径），驱动从不写 → **操作员配置，保留在 preset 里**。
