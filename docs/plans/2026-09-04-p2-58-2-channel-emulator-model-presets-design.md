# P2-58 ② 设计稿 — 信道仿真器分型号 saved presets + GUI 消费 ① 的 binding 真值

> 状态：**已实现并合并** —— ② PR #452（squash `e8861adc`，2026-09-04）；① PR #450 / 收口 #451。实现与本稿的差异以 roadmap 条目「② 实际结果」为准，§8 补遗见文末。
> 本稿随 #451 入仓（外审 R1–R5 五轮纠正见 git log），§8 补遗随 ② 分支并入。**§6-① 已按实测定（见 §6），用户可否决。**

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
| 运行期参数剔除 | `BASE_STATION_RUNTIME_CONNECTION_PARAM_KEYS = {"detected_test_app"}`（HAL **连接时**回读的 Test App，真运行期观测） | **`CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS = frozenset()`** —— CE 今天**没有**连接期回读进 `connection_params` 的键。外审 #451 R2 纠正了本稿初版：`available_channel_models` 曾被我按 `detected_test_app` 类比成「运行期观测、剔除」，实测其 4 个写入点（`api/instrument.py:1981/2056` 操作员增删 curated list、`standard_channel_service.py:363` SCD 关联投影、`smu_project_inventory.py:746` 操作员触发的 smu-sync 扫描）**全是操作员/同步触发的持久化**，且 F64 ATE 模式无 MMEM/FTP **无法运行期重新发现** —— 它是**型号专属配置资产，必须保留在 preset**，否则切 F64→FS16→F64 会把操作员维护的模型清单清空。`topology_profile_id` / `default_emulation_file` / `smu_project_scan` 亦为操作员配置，保留。空集合保留是为与 BS 同形并给将来真正的运行期键留位 |
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
10. `gui/src/types/api.ts` —— 在 :403 `base_station_binding` 旁**新增** `channel_emulator_binding`（该字段今天在此文件**尚不存在**，全文件 grep 为零；非 `?:`，① 已定 required）；`gui/src/features/Equipment/channelEmulatorModelPresetDraft.ts`（新，镜像 BS 那份）；`App.tsx` 的 `handleModelChange` CE 分支 + 确认弹窗
11. `gui/src/features/Dashboard/ZoneReadiness.tsx:142` —— readiness 灯消费 `channel_emulator_binding.status`

**① 留下的两格判定**（B 的歧义 #1，归 ②）：preview 端点对「TestCase 存在但 `test_type != "MIMO_OTA"`」或「其 `lab_profile_id` 与所选 LabProfile 不一致」—— **422 + 中文 detail**（外审 #451 R3 纠正：资源存在但不可用该 422 不该 404；仓内口径 `lab_profile.py` 404×5 全给「不存在」、422×11 给「存在但不可用」。CE 无 compatibility 槽位，返回 null 会伪装成「没选资产」；「TestCase 不存在」仍 404，与 B 同口径）。**lab 不一致的判定仅在 `test_case.lab_profile_id` 非空时触发**（外审 #451 R4 纠正；镜像 BS compat `base_station_compatibility.py:181-184` 的 `is not None and !=`）：preview 是只读面，`null` lab 视为「不约束 LabProfile」不拦。⚠️ **执行侧口径相反、勿混**：CE freeze（`channel_emulator_binding.py:662-663`）、BS freeze（`base_station_adapter_profile.py:320-321`）与认证（`execution_qualification.py:454`）对 `lab_profile_id is None` 一律拒 —— 没有 lab 就没有 binding 可解析。preview 放行 ≠ 能执行，② 的门要两面各钉一条。

## 4. 门的设想（每条配让它变红的变异）

1. **不覆盖其他型号**：先存 F64 preset，再切到 FS16 保存 → F64 的 map 项**逐字节不变**；变异：保存时整张 map 重写 → 红
2. **切型号前旧活动被快照**：从未存过 F64、活动连接是 F64、切到 FS16 保存 → map 里出现 F64 快照；变异：删快照分支 → 红
3. **`available_channel_models` 完整进 preset，剔除集合为空**（③⁺：本条初稿写「运行期观测键不进 preset」，与 §2 被 R2 纠正后的分类相反，R3 期间自查抓出）：保存 F64 preset 后，preset 里的 `available_channel_models` 与活动连接**逐字节相等**；`CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS == frozenset()`。变异：把 `available_channel_models` 加进剔除集合 → 红。另一条判定器自测：往剔除集合加任意键 → 门要求该键在全仓有 HAL `connect()` 路径的写入点，否则红（防再次错分类）
4. **迁移双向 + 幂等**：`column_exists` 守门，二次 upgrade 不炸（照 f2a4c6e8b0d1 的既有测试形状）
5. **契约四步对齐**：G11（yaml ⊆ live）+ P2-27（required == properties）+ `npm run build` + **浏览器实测**切型号确认弹窗（memory：GUI 两道门缺一不可）
6. **确认弹窗**：有未保存草稿时切型号 → 弹确认；取消 → 草稿不变、型号不变；确认 → 草稿替换；变异：跳过确认 → 红
7. **readiness 灯**：`channel_emulator_binding.status` 四态各自映射到灯色/文案，`invalid` 必须可见（不许沦为灰）；变异：`invalid` 映射成与 `configured` 同色 → 红

## 5. Discovered（本稿枚举、不在 ② 做）

- **Discovered-4**：BS 的 `handleModelChange` 切型号**无确认**，静默换草稿 —— ② 给 CE 加了确认，BS 与之不一致。补给 BS 是越界，另评。
- **Discovered-5**：`_freeze_instrument_lease` 的 `validation_identity` 纳入 CE digest（= ① 的 Discovered-3 后半）—— 与 preset 无关，不进 ②。

## 6. 需要你拍板的（② 开工前）—— 只剩一个

1. ~~**F64 ↔ FS16 切换时，`alignment_name` 算型号 preset 的一部分吗？**~~ **按实测定为「算」**（2026-09-04；三次请用户拍板未答，实测后不再是偏好）：作为 `connection_params` 键它**只被 F64 驱动读**（`app/hal/propsim_f64.py:556-561` → connect 后 `SYST:CALIB:USER:SET 1,<name>`）；FS16 驱动唯一命中是 `query_user_alignment_name()`（:443，只读回读，不消费该键）。F64 型号专属配置，随 preset 走。抽屉里该字段**仍始终渲染**（不按型号隐藏）：`FEInstrumentModel` / 手写 `InstrumentModel` 无 CE `adapter_id`/manifest 可判，隐藏只能靠 `model.model` 名字匹配 —— 脆判据，不做；见 §8.E Discovered。**用户若反对，改法是一处**：`draftForChannelEmulatorModel` 不还原该键。

~~2. readiness 灯的 `invalid` 显示为红还是黄？~~ **不需拍板，照抄 BS**：`gui/src/features/Dashboard/baseStationBindingTruth.ts:46-66` 已定 —— `invalid` → **红**（:51-53）、`simulated` / `diagnostic_unbound` → 黄（:58-60）、`configured` 真驱动 → 绿（:66）。CE 的 `channelEmulatorBindingTruth.ts` 镜像同一映射；与 ① 「判不出 = 吵的一侧」一致。

**脚注 `smu_project_scan`**：只被 `app/services/smu_project_inventory.py:301` **读**（`params.get("smu_project_scan")`，操作员配置的只读挂载 `local_mount_root` / `instrument_root`，:118-136 校验必须是绝对路径），驱动从不写 → **操作员配置，保留在 preset 里**。

## 8. 补遗（① 收口期间所得，2026-09-04）

### 8.A 迁移不只加列，还回填（镜像 `f2a4c6e8b0d1` :42-84）
BS 迁移在 `add_column` 之后：`SELECT` 品类为 `baseStation`、`selected_model_id` 非空、`endpoint` 非空、
`base_station_model_presets IS NULL` 的连接行 → 用活动连接字段（endpoint / protocol / notes / connection_params）
为 `selected_model_id` 生成首个 preset 写回。目的：升级后现有连接立刻有一份 preset，不用等第一次切型号才快照。
CE 版同形：品类 `channelEmulator`，回填时**保留** `available_channel_models`（外审 #451 R2 纠正：它是操作员/同步维护的型号配置资产，F64 ATE 模式无法运行期重新发现，剔除会在切型号时清空；见设计稿 §2 实测表）。CE 今天**没有**真正的连接期回读键，`CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS = frozenset()`。
**门**（镜像 BS `…recovery.py` 那条的形状但**方向相反**）：回填后的 CE preset 里 `available_channel_models` 必须与活动连接逐字节相等；变异：回填把它剔掉 → 红。另一条：若将来有人往 `CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS` 加键，门要求该键在全仓有 HAL `connect()` 路径的写入点（否则是又一次错分类）。
⚠️ 回填是**便利不是正确性**：即便不回填，`save_channel_emulator_model_preset` 的「旧活动未存过就先快照」分支也会在
首次切型号时补上。所以回填失败不阻断升级（镜像 BS：`table_exists` 守门先 return）。

### 8.B ② 的门文件镜像 BS 的四个
| BS（已在） | CE ② |
|---|---|
| `tests/test_base_station_model_presets.py`（preset 模型：JSON-safe、拒空 endpoint、专用存储无写字段） | `tests/test_p2_58_2_channel_emulator_model_presets.py` |
| `tests/test_base_station_atomic_model_save.py`（原子保存：不覆盖其他型号、快照旧活动） | 并入同一文件或独立 `…_atomic_save.py` |
| `tests/test_base_station_model_preset_recovery.py`（回填不提运行期键；HAL connect 不落运行期键） | `…_recovery.py` |
| `tests/test_base_station_model_preset_openapi.py`（契约：yaml ⊆ live、required == properties） | `…_openapi.py`（P2-27 门会自动覆盖 required；这里钉 preset 字段形状） |

### 8.C 迁移语法要点（照抄，别自创）
`from app.db.migration_helpers import column_exists, table_exists`；`upgrade()` 开头 `if not table_exists(...): return`；
`sa.JSON()` nullable + comment；`downgrade()` 同样双守门后 `drop_column`。方言无关（memory
`feedback_addcolumn_migration_dialect_agnostic`）。**新迁移的 `down_revision` 必须是当前唯一 head**（G1 门守着）：
2026-09-04 00:26 实测 `alembic heads` = **`f2a4c6e8b0d1 (head)`**（恰一个，就是 BS preset 那份迁移）→ ② 新迁移 `down_revision = "f2a4c6e8b0d1"`。开工前再跑一次核对，若 ① 收口后有别的迁移合入则以当时 head 为准。

### 8.F Agent I 落地时的判定（活动 connection_params 写方全集 —— ⓪②⁺）
活动 `connection_params` 的写方**五处**（一次 `grep '\.connection_params = '` 即得清单；行号随上游加行漂移，这里只写符号名 —— 复审 F1）：W1 `PUT /instruments/{key}` 通用路径 `update_instrument_category` 里的 `setattr(connection, key, value)`（CE 现走独立块，不再落此）、W2 `add_channel_model_entry`、W3 `remove_channel_model_entry`、W4 `standard_channel_service._sync_projection_for_binding`（SCD 关联投影）、W5 `smu_project_inventory.sync_smu_project_truth`（smu-sync）。
- **`synchronize_saved_active_channel_emulator_preset_params(*, selected_model_id, connection) -> bool`**（I 追加到 H 模块末尾）：把活动 `connection_params` 回写到当前型号的 preset，无 preset 时 **no-op**（有意与 BS topology-profile 的「无 preset → 422」不同：增删端点今天没有"先保存"前置、甚至会自建连接行，422 会弄坏既有流程；无 preset 时安全，因 `save_*` 首次切型号的快照分支会带上 —— 门 7 钉住）。**已接 W2/W3**（Agent I）与 **W4/W5**（Agent K，各 9 行同形调用，`selected_model_id` 取该连接所属品类的；W5 放在 `try` 内，preset 与活动清单同事务提交/回滚）。主 agent 核实两处都**天然只处理 CE 连接**、无需额外品类判定：W4 的 `instrument_connection_id` 来自 SCD，而 SCD 绑定时 `_resolve_channel_emulator_binding`（`standard_channel_service.py:50`）已校验连接是 `channelEmulator` 品类；W5 在 `smu_project_inventory.py:286` 自己过滤 `category_key == "channelEmulator"`。**但 W4 不分型号**（内审 F1，P2）：SCD 只挂 connection（`StandardChannelDefinition.instrument_connection_id`）、没有型号归属，`_sync_projection_for_binding` 用该连接下**全部**已关联 SCD 重建派生条目再回写进**当前活动型号**的 preset；非 F64 型号活动时关联 SCD，F64 的派生条目会灌进活动型号的清单与 preset，切回 F64 后清单相对 SCD 表陈旧到下次在 F64 活动时重建。修法是加机制（SCD 记型号 / 投影按型号分桶），「只在 F64 活动时投影」是 §8.E 拒掉的按名判；② 按 ⑤ 未动，已进 Discovered。
- **`require_saved_active_channel_emulator_preset`**（镜像 BS `base_station_model_preset.py:186-223` 去掉 adapter_profile 比对）：sync-current 的 fail-closed 检测器。**顺序必须是先接 W4/W5 再落它**——它是漂移的检测器不是修复，W4/W5 未接时接上它，每次 smu-sync / SCD 关联后同步 LabProfile 都 422「请重新保存」，纯噪音。**已落地**（Agent K）：接入 `lab_profile.py` sync-current CE 分支、位于 ① 的 `resolve_channel_emulator_binding` 之前（先钉活动 == preset，再解析 binding）；① 的两条 sync-current 用例**接上即红**（预言应验：`detail = "channelEmulator 当前型号没有已保存配置…"`），已补 `PUT {"connection": {}}` 存当前型号 preset 一步，断言一字未动。
- **P1 级 I↔J 耦合**：`App.tsx:1960-1968` 对非 BS 品类切型号**立刻只发 `{modelId}`**，CE 块镜像 BS「model 与 connection 必须一起保存」后此请求 422。**J 必须同 PR 落地**（BS 在 #426 同形处理）。
- 变异 M1c（`_convert_connection` 不 `model_dump` 直传 Pydantic 对象）**绿且不可观察**：字段类型 `Dict[str, ChannelEmulatorModelPreset]` 下 Pydantic 把 dict 也校验成实例，FastAPI 序列化结果逐字节相同。外审 R5 那句「直接吐 Pydantic 对象」只在 `Dict[str, Any]` 时成立；`model_dump(mode="json")` 是与 BS 同形的冗余，保留。

### 8.E Agent H 落地时发现（越界未动，进 Discovered）
- **BS 迁移 `f2a4c6e8b0d1` 在 SQLite 下回填出非规范 UUID 键**：`postgresql.UUID(as_uuid=True)` 裸 `SELECT` 在 SQLite 返回 32-hex 无连字符，`str(row["selected_model_id"])` 直接当 map 键，而 `parse_base_station_model_presets` 要求键 `== str(UUID)`（带连字符）→ 回填出的 map 会让 parse 抛错。生产 PG 原生 UUID 无此问题；BS 那条迁移门是**存在性门**（只查源码 token）从未真跑过回填，所以没暴露。CE 版用 `str(uuid.UUID(str(raw)))` 规范化，变异 M8 证明照抄 BS 写法会红。**修 BS 迁移不在 ② 范围**（⑦），已进 roadmap Discovered。
- **JSON `'null'` ≠ SQL NULL**（值的形态空间）：ORM 显式传 `xxx_model_presets=None` 时 SQLAlchemy `JSON` 存文本 `'null'`，迁移的 `IS NULL` 认不到；生产 API 建行从不设该列（= SQL NULL）。BS 原子测试 fixture 也传了 `None` 但那边不跑迁移故无害。
- **「alignment 字段仅 F64 型号时渲染」需先让型号 DTO 暴露 CE 判据**（`FEInstrumentModel` 今天只有 `id/vendor/model/summary/interfaces/capabilities`；BS 靠 `model.base_station_manifest`，CE 在 ① 只把 manifest 挂在 binding 上）。② 保持始终渲染；另片评估是否给 `FEInstrumentModel` 加 `channel_emulator_manifest` 或 `adapter_id`。
- CE 迁移门是**真跑** `upgrade()/downgrade()`（`MigrationContext` + `Operations.context`，`tests/` 里此前无此形态），比 BS 的存在性门高一档。

### 8.D 外审 #451 R5 三条实现提示（均采纳，② 开工清单；R5 无 P1 按规则合并、未再推）
1. `ChannelEmulatorModelPreset` 必须 `model_config = ConfigDict(extra="forbid", frozen=True)`（镜像 `BaseStationModelPreset`；设计稿 §2 表里 CE 行漏写了 frozen）。
2. `app/api/instrument.py` 的 `_convert_connection` 要对 `channel_emulator_model_presets` 做与 `base_station_model_presets` 同形的字典序列化（`parse_*` → `model_dump(mode="json")`），否则响应里直接吐 Pydantic 对象。② 开工时先读 :235-247 那段 BS 处理再镜像。
3. `gui/src/types/api.ts` 不只补 `channel_emulator_binding` 字段，还要补 **`ChannelEmulatorBindingPreviewResponse` 的手写类型定义**（该类型在手写文件里尚不存在；生成文件 `api.generated.ts` 里已有，可对照抄）。
