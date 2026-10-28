# PC-04A-5：可恢复拓扑库与 CAICT 独立 PA 设计

状态：**用户已授权审清复制/改名与校准两项风险后按流程实施；当前等待独立审查增量确认**。用户已批准 5a → 5b → 5c → 5d 顺序和“先保护、后改图”的方向，无需重复索取同一授权。本次修订只改文档，不访问用户数据库，不运行硬件；后续5a也不得修改原CAICT配置。

## 1. 故障与切片

可观察故障：同一 Lab/开关有多张图时，编辑器只显示列表第一张，没有选回原图、命名副本和误保存恢复的完整入口；直接重导入会替换同范围已有图。仅增加“另存为”按钮可能让副本抢占执行图或继承旧校准数值。

| 切片 | 交付边界 | 不包含 |
|---|---|---|
| 5a | 已保存图的库选择、重命名、复制/另存为、编辑器默认选择，保护原图和执行选择 | 历史修订、用户库改接、执行绑定体系重构 |
| 5b | 持久修订、保存前快照、原子并发拒绝、历史预览、显式恢复为新修订 | 回写历史执行/证书、恢复旧 confirmed 资格 |
| 5c | 备份验证后逐条原 F64 输出 → 独立 PA.in/out → 原 probe，预览差异后保存 | 批量猜测端口、重新编号原映射、未知补零 |
| 5d | 原图/副本/恢复/冲突/采集锁及逐链映射综合验收和指南 | 真实硬件 B/HOLD、校准或正式验收通过声明 |

WIP=1；前片收口才进入后片。实施计划仅覆盖 5a；5b–d 各自再审计划。沿用原画布、拖动、器件/端口/连线编辑和现有校准区，不重做已交付 4a–4e。

## 2. 已核实的真实路径与消费关系

以下是当前源码事实，不是用户库的实测状态。稳定锚点可用 `git grep` 重查。

| 入口/权威源 | 正式消费者/关联写入 | 5a 断言与处置 |
|---|---|---|
| `app/api/switch_topology.py::list_switch_topologies`，Lab → `resolve_current_chamber` | `TopologyEditor.tsx` 外层 effect 当前 `items[0]`；API 默认分页 50、最大 100，按创建时间排序 | 完整分页或明确分页 UI；可选旧图，不能把未取到当不存在 |
| `SwitchTopology` 的 `chamber_id/switch_category_id` | CRUD 的 `_load_scoped_topology` 只核暗室；列表另滤 category | GUI 状态键 `(lab_profile_id, switch_category_id)`；副本继承源 category/chamber，不接受跨范围字段 |
| `SwitchTopologyCreate/Update/Response` 和 `switchTopologyService.ts` | typed GET 可能默认化字段、丢失模型外顶层图字段；4a–4d PATCH 有保形/转换分支 | 复制直接读取 ORM 原始 JSON，不使用 GET → POST 重建；不得将显示默认值写回副本 |
| `create_switch_topology/update_switch_topology/import_topology_from_template` 的 `is_default` | 让位范围为 `(chamber,category)`，不同 Lab 可共享同一 chamber | 5a 不把这个布尔值作为新的编辑器偏好写入；显示为“历史默认标记”，不声称执行绑定 |
| `switch_orchestrator.py::orchestrate_switch_topology` | 按 **chamber + is_active + updated_at DESC** 取第一行；不按 category、不读 is_default | 副本必须 inactive；改名不得改变更新时间排序；编辑器选择/默认不改变解析结果 |
| `calibration/rf_chain_resolver.py::resolve_rf_chains` | `lab_profile.py` 的 RF chain 查询、path-loss/probe calibration、configuration_scope、route_calibration_freeze | 复制/改名/偏好前后解析到同一 topology_id；无自动改绑 |
| `route_calibration.py::_route_selections` 的显式 topology_id | RouteCalibrationPanel、RouteBatchPanel、route_batch_plan、configuration_scope | inactive 副本可编辑，不表示校准合格；明确 topology_id 的校准入口仍走原资格门 |
| `topology_loss.py::effective_connection_loss` | TopologyService 路径/矩阵、声明路径/执行补偿读旧 calibrated_loss_db | 新 UUID 本身不够隔离旧实测；复制必须处理下述两个字段 |
| `route_calibration.py::assert_route_topologies_deletable` | DELETE、模板 replace、`chamber.py` 删除；当前保护 Application/Selection | 不绕过现有保护；5a 不提供库删除按钮，不以模板替换删除备份 |
| `models/probe_calibration.py` 的拓扑 ID（UUID 与 String 两种） | MultiFrequencyPathLoss、ProbePathLossCalibration 等历史证书、freeze 查询 | 不复制、不移动、不修改历史；本片不新增任意删除行为 |
| `route_calibration_freeze.py` 冻结/核验 | `mimo_ota/executors/measure.py`、TestExecution 冻结载荷和正式报告链 | 不重写已冻结 ID/补偿；图副本不能靠默认选择进入正式执行 |
| `TopologyEditorFlow::handleSave` / conversion commit | 原 PATCH、`conversion` 的 source_digest/原子比较；`legacyConversionState` | 继续使用既有保存和转换；5a 不把版本字符串说成历史版本 |
| 模板导入 `replace_existing=True` | 删除同 chamber/category 全部行，随后修改默认位 | 5a GUI移除自动导入/替换入口；显式导入只能追加 inactive、非default；已有行时 replace 明确 409 |
| `useOperationalLabSwitchGuard`、dirty/busy callbacks | Lab、开关切换、重导入、保存、采集、转换抽屉 | 纳入库切换和命名/复制按钮；迟到响应不能覆盖新上下文 |

全集重查命令（实施前再跑；不是把所有命中文件都修改）：

```bash
git grep -n 'SwitchTopology\|switch_topologies\|switch_topology_id' -- api-service/app gui/src api/openapi.yaml
git grep -n 'topology_id\|is_default\|is_active' -- api-service/app/services/calibration api-service/app/services/mimo_ota gui/src/features/TopologyEditor
git grep -n 'importFromTemplate\|replace_existing\|updated_at.desc' -- api-service/app gui/src
```

通用 `topologies`、road-test network topology、仪器 topology profile 是其他领域；只核其引用边界，不改成此库。

## 3. 方案比较与推荐

| 方案 | 优点 | 风险/代价 |
|---|---|---|
| A：服务端复制原始图 + 浏览器作用域偏好（推荐） | 不迁移旧库；默认不碰执行；副本可可靠保形；5a可独立验收 | 偏好仅本浏览器；校准字段需显式例外；active旧图改名须保持执行排序 |
| B：复用 is_default 或最新更新作为默认 | 少一个偏好存储 | Lab共享暗室、category与执行选图不一致，元数据修改可能切执行图；不推荐 |
| C：服务端每Lab默认与显式执行拓扑绑定/历史一并重构 | 跨浏览器统一，能彻底解除更新时间选图 | 增表迁移、执行/冻结消费者变更，超出5a保护性增量；单独批准后另片 |

采用 A，按用户最新授权先完成两项风险的独立审查门再实施。不能悄悄以 B 实现 A 的界面。如果用户要求跨浏览器默认或副本直接用于正式执行，暂停并审 C，而非自动激活副本。

## 4. 5a 契约

### 4.1 库与名称

同Lab的派生暗室、同 category 列出所有活跃和非活跃图，标签显示名称、短ID、活跃状态，避免同名误认。Lab仅是操作上下文：共享 chamber 的两个 Lab 看见相同图记录，不伪装为数据隔离；偏好仍按两个 Lab 独立。

名称先 trim，长度 1–200 Unicode 字符，禁止控制字符；重复名称允许，列表和确认框同时显示短ID，避免引入旧库唯一约束与隐式重命名。空白/null/超长/控制字符 422。复制默认建议“原名称 副本”，提交前可编辑；服务端不按名称查源。

新增 `POST /api/v1/switch-topologies/{id}/copy?lab_profile_id=...`，body仅 `{name: string}`，201返回新图；不接收图内容、状态、category或校准记录。源不存在404、跨暗室409、Lab无法解析422。同暗室category从源继承。复制的是点击前已保存版本，不是未保存草稿。

另存为的准确文案为“复制已保存版本为…”；dirty时先保存或放弃再复制，不能偷偷先覆盖原图。原图只读不改；新 UUID、created/updated 时间、inactive、非default。名称 PATCH 仅提交 name，不发送图数组，SQL UPDATE必须包含 `updated_at=SwitchTopology.updated_at` 列自赋值（该列目前影响执行选图），不能将Python已读旧datetime赋回：相同标量可能被ORM忽略并触发onupdate，强制写旧值又可能回退并发新时间。若与图数组一起提交，则仍按图保存语义处理并更新时间；GUI不得混合。

### 4.2 原始 JSON 保形与校准边界

深拷贝 ORM `nodes/connections/operating_modes`：保留顺序、缺键/null区别、number/string/bool类型、opaque字段、ID、坐标、端口、模式、显式路径和loss owner引用；不调用 typed GET 的 model_dump 重建，不重新自动声明端口或补0。复制不是“修图”，旧声明不因复制被升级成新硬件能力。

**唯一图内容例外：** 新副本的每条 connection 中，已存在的 `calibrated_loss_db`、`calibrated_phase_deg` 置 null；缺键保持缺键。原因：真实消费者会优先使用旧 calibrated 数值，并可显示 valid，不能只靠新UUID承诺“不继承校准”。原图原值完整保留。复制确认框须披露这两个字段不沿用，保留标称值不等于实测。不能把旧数值改写成 nominal 再冒充声明。

不复制 Application、Selection、采集 run、证书、confirmed记录或历史执行；副本无新采用记录。保形断言应明确排除上述两个字段，而不是虚称全量字节相等。源本身含无法被现有Response序列化的数据时，应在事务提交前检测并422，避免“已创建但响应500”；原始复制仍从ORM取值。

准确承诺是“不复制旧采用记录/内嵌测量值，inactive副本不自动用于正式执行”，不是全系统永久禁止沿用旧证书。`route_calibration_freeze.py` 仍兼容 `certificate.topology_id is None`：未来经既有PATCH显式激活且chain/CE/probe/polarization相同的副本可能使用该旧证书。5a无激活入口、不改冻结政策；未来执行绑定片须独立审查此兼容边界。

### 4.3 编辑器默认与执行分离

localStorage键 `meta3d.topology-editor.default.v1:<labId>:<categoryId>` 只存 topology UUID，不缓存图和资格。明确按钮“设为本浏览器默认编辑图”。重载先取完整列表，再选合法偏好；无偏好可选唯一历史 `is_default`，否则按稳定 `created_at DESC,id` 选第一张。偏好失效显示提示并清除；列表失败不能清除偏好或导入模板。localStorage不可用时当前选择仍可用，提示偏好未保存，不报成功。

默认/库选择不改变 `is_active/is_default`、Lab instrument_bindings、port_maps、正式 topology resolver 或冻结内容。副本 inactive 意味着不会自动用于正式测试；用户若要启用副本，须在后续显式执行绑定设计中处理，不提供误导性“已应用”按钮。

### 4.4 状态与错误

作用域键 `(labId,categoryId)` 加请求代数；所有 list/detail/copy/name/import 响应只在请求代数与对象ID仍匹配时写当前UI，迟到结果不得切新Lab或清新草稿。服务器成功而客户端超时不自动重试写请求，提示刷新列表核查副本（名称非幂等键）。

dirty阻断切图、切category、切Lab、复制和导入，提供现有保存/放弃入口；busy（保存、转换提交、采集尚未确认结束、库写操作）阻断全部上述操作。锁在请求前用ref同步设置，成功/失败finally复位；采集结束未确认不能仅靠网络错误解除。失败保留原选择、草稿与输入，提示真实错误；成功后重读服务端，再允许选择副本。空库只显示显式新建/模板导入选择，不触发自动写入。

实施核对修订：原组件只有保存、没有放弃按钮。经主任务裁决，5a补最小“放弃未保存改动”入口：显式确认后仅恢复同scope/current ID的已知保存快照，不发写请求；取消保留草稿，busy或采集结束未知时拒绝。这不是5b历史修订恢复。

### 4.5 导入和删除保护

5a不增加删除按钮。不把删除当撤销，不移除现有Application/Selection外键保护。已有行的 `replace_existing=true` 在任何删除前409，提示另存/后续恢复；显式模板导入为追加 inactive/非default，不清其他默认位。原自动导入effect改只读，避免跨Lab迟到写入和意外激活。

兼容代价：空库首次模板导入也只有inactive库草稿，不再自动获得执行拓扑；5a不提供激活按钮，不能显示“已用于正式测试”。这是有意行为变化，不为恢复便利自动激活，也不改动既有原CAICT配置。

历史证书、执行冻结和原有活跃图的全面删除政策不在5a扩做；现有直接DELETE仍有仅保护采用记录的局限，必须明确披露。5a副本保护依靠“不暴露删除”和“禁止覆盖式模板替换”，不能声称已解决全系统任意删除。5b持久修订设计必须重新枚举这些历史引用，不能凭外键不存在放行。

## 5. 后续接口边界（不施工）

5b：保存/转换/恢复都必须在同一事务产生不可变原始JSON修订；预期修订不匹配409；恢复是新的当前修订，不覆盖旧行历史，不恢复旧资格。`version`是图描述字符串，不充当并发令牌。保留5a topology UUID；偏好仍指图、不指修订。

5c：仅在5b备份可读且恢复演练成功后，确认用户指定源UUID。输出逐边映射表（原connection ID、F64原端口、原probe ID/pin/polarization、新PA ID、两新边ID、模式/显式路径替换）。PA显式ports=['in','out']、方向input/output、internal_paths=[{from_port:'in',to_port:'out'}]。保留源/终点身份，不按画面位置猜映射。原损耗只归属一次；旧20dB仅有出处的标称，不转实测；未知保留未知。原直边仅在替代链完整后移除；不泛删其他PA或器件。预览前后均不发硬件命令。

5d：真实API+浏览器保存重载、逐链解析、恢复、并发、跨Lab、采集锁、冻结/confirmed不重复计量；软件通过不等于现场导通、实测校准或B/HOLD解除。

## 6. 验证与批准点

5a需真实API RED/GREEN、GUI交互、build、四镜像和所有受影响消费者回归。因为新增共享后端写接口和导入行为，最终稳定版本只由指定一名执行者跑一次后端全量；修后共享输入变化则该结果过期，不能用早先全绿替代。本次文档未执行这些测试。

所有app导入前指定新SQLite及显式Mock；bootstrap后再次设置并核对全部类别和Lab binding为mock。真实浏览器连隔离API，不修改用户8000服务，不用默认Vite代理误连。保存命令、SHA、退出码、统计、请求/响应和截图；旧验证数字不可当本片证据。

用户最新授权为审清两风险后按流程实施、不改原CAICT配置。独立审查门应确认：①本浏览器默认与执行分离；②副本inactive且name-only通过SQL列自赋值不改变执行排序；③两旧calibrated字段例外及NULL topology_id旧证书边界；④不新增删除界面、禁止已有库模板覆盖、首次模板导入也只为inactive草稿、另存只复制已保存版本。增量审查确认后按5a计划执行，不重复请求同一授权。
