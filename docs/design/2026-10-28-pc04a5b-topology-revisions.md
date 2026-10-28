# PC-04A-5b：拓扑持久修订、冲突拒绝与显式恢复

状态：2026-10-28实施验证快照。用户已批准完整契约；计划审查及Task1～3独立规格/质量审查已完成，Task4隔离API/浏览器与唯一最终全量已执行，详见[验证记录](../validation/2026-10-28-pc04a5b-topology-revisions.md)。Task4独立/整片累计审查及Ready PR外审、合并尚未完成；最终交付以功能PR合并回执为准，不另开递归状态PR。全量残留3项历史规则失败，不称全绿。

基线：PC04A5a PR545 已合并，`ce4bec1140d34fff7c029dfa04e38a71de5aad63`。承接已批准的[总体设计](2026-10-27-topology-library-pa-recovery.md)第5节，不启动5c/5d，不修改用户原CAICT、默认数据库或用户服务。额度例外授权仅本片；原自动化继续暂停。

## 1. 目标与选择

解决：误保存后无法找回此前保存内容；两个客户端先后保存时旧草稿静默覆盖新图；转换已有raw图CAS但普通保存不具备同等保护。

选择不可变完整快照及独立整数修订号。时间戳受精度和执行选图语义影响，不能作并发令牌；现有`version`是用户描述，不能作令牌。JSON差异补丁可节约空间，但恢复依赖重放/版本算法，本片不采用。快照不等于仪器状态、校准证书或已冻结执行。

保留topology UUID及5a浏览器偏好。修订属于该图，不是另一个库条目。恢复历史为当前图的新修订，不回退修订号，不修改历史行。

## 2. 存储与旧数据

- `switch_topologies.revision`：非空整数，旧行从0开始；GET只读，不为查看历史写库。
- 新表`switch_topology_revisions`：UUID主键、topology_id限制删除外键、revision、operation（baseline/create/copy/import/update/conversion/restore）、created_at、restored_from_revision（可空）、snapshot JSON。`(topology_id,revision)`唯一。
- snapshot从ORM原始列深复制，不经typed GET重建。包含name/description/version/site_name/system_model/installed_date/installed_by、nodes/connections/operating_modes；三图数组保持缺键/null、JSON数值类型、opaque字段、顺序、ID、引用。日期用明确ISO字符串表示；不包含执行记录、证书、采用记录或可执行授权。
- scope、topology UUID、created_at、updated_at、created_by、is_active/is_default不作为可恢复数据。历史预览并列展示当时信息与不可恢复边界，不能将旧active标志恢复成当前激活。
- 旧行首次成功修改，在同一事务先保存revision0 baseline，再写revision1当前快照；失败或冲突不留baseline孤行。只读旧图显示“尚无修订留痕，从首次保存开始记录”，不编造更早历史。
- 新建/复制/模板导入的图在创建事务保存revision1快照；复制不复制源图修订历史，保留5a已存在calibrated两字段置空例外。
- 应用不提供修改/删除修订接口，不自动清理历史。新增外键RESTRICT及两个现有删除入口检查，禁止通过拓扑DELETE或暗室bulk DELETE删除已有修订。模板覆盖仍沿5a已有库409。历史资格/证书引用保护不能因新表而放宽。
- 迁移只新增列与表，不读取/重写用户图JSON、不批量补默认端口。模型注册及Alembic走当前真实head；实现前核迁移头，不凭文件名排序猜head。

## 3. 写入口与原子性

普通PATCH、仅名称PATCH、conversion PATCH、restore POST均要求`expected_revision`非负整数。缺失/坏类型明确422，过期409；不允许旧客户端无令牌绕过。响应返回当前revision，GUI仅在成功后接纳新令牌。

统一事务：读取当前raw与revision → 校验候选及scope → `UPDATE ... WHERE id/chamber/revision = expected`（转换同时保留现有raw/source_digest CAS）→ 仅rowcount=1才插入baseline/新快照 → 事务commit。任何快照插入/唯一性/写入失败全部rollback；不能先commit图再另存历史。候选统计及响应序列化可行性在commit前完成。

不能使用“Python先比较后ORM无条件保存”代替CAS。两连接同时从rN提交至多一方成功，输方409且无默认位、快照、统计或其他行副作用。SQLite BUSY/LOCKED按现有明确分类409，不能吞所有数据库错误伪装冲突。

`is_default`让位会写同scope其它图，必须在同一事务纳入各行修订快照及CAS，失败全部回滚；GUI不新增此控制。scope字段维持原有一致性限制，不允许借修订改chamber/category。名称单独修改仍用`updated_at=SwitchTopology.updated_at`列自赋值，避免改变正式执行选图排序；其它保存的updated_at沿既有语义，不引入自动激活。

实施澄清（decision0010）：所有拓扑写入口和两个删除入口在读取目标/默认peer之前取得同暗室事务锁。PostgreSQL锁暗室行；SQLite以`id=id, updated_at=updated_at`无内容变化UPDATE取得事务写锁，不改变暗室时间或其它字段。锁后重新读取图，仍逐行revision CAS；因此空scope并发create默认图也不能绕过保护。只读历史/预览不取SQLite写锁。`is_active/is_default`实际变化亦推进修订；另存只读`recorded_metadata`记录当时UUID/scope/状态/创建更新时间及创建者，供历史并列展示，不进入可恢复白名单。此为已批准原子性和审计边界的实施澄清，不增加激活或资格能力。

无实际改动的合法PATCH保持原revision，不新增假历史；与旧revision冲突仍先409。判断JSON等价需区分true与1、缺键与null，不用普通Python相等折叠。

显式restore不适用PATCH无变化例外：即使候选与当前内容相同，仍新增operation=restore修订并记录来源，不回退或改写历史。

## 4. API与恢复

- 列表/详情响应增加revision；写四镜像同步API/schema/OpenAPI/TS，开发mock不伪造历史成功。
- `GET /switch-topologies/{id}/revisions?lab_profile_id=...&skip=0&limit=50`：分页摘要，包含total，按revision降序；不会lazy写baseline。
- `GET /switch-topologies/{id}/revisions/{revision}?lab_profile_id=...`：只读raw快照，不按当前GET模型补pin/端口；跨Lab暗室沿现有scope拒绝，其他图修订不可读取。
- `POST /switch-topologies/{id}/restore-preview?lab_profile_id=...`：body `{revision,expected_revision}`；只读返回当前令牌、目标快照、将写候选、逐字段差异与警告。不自动保存或调用HAL。
- `POST /switch-topologies/{id}/restore?lab_profile_id=...`：同body，服务器重新取不可变目标、重建候选并复核，不信客户端提交候选。最新令牌CAS成功后追加operation=restore新修订，关联原revision编号。
- 恢复仅替换可恢复字段，保留当前scope/状态/创建元数据。旧connections已存在`calibrated_loss_db`、`calibrated_phase_deg`置null，缺键保持；原快照不变。不创建/恢复Application、Selection、run、confirmed、证书，不自动重新采用，不宣称通路重新合格。
- 历史预览可展示当时原值并明确只读；恢复候选单独展示清空校准值的差异。历史结构不再符合当前保存门时preview返回422及原因，当前图零写入，不用恢复放宽端口、内部路径、引用、loss owner或数值门。
- 既有无关旧图保形规则继续适用，但不能从当前GET默认化值推定历史声明；未知不补0。历史恢复不承诺阻断既有NULL topology_id证书兼容，也不改变冻结政策。
- 恢复后未变的链是否仍匹配现有confirmed沿当前真实身份门判断；恢复动作本身不创建新资格、不重写历史baseline/冻结，也不以“新revision”一刀切取消既有资格。

## 5. GUI状态与错误

原编辑器增加历史入口、分页列表、只读预览、当前与候选差异及显式二次确认。预览不替换draft或影响dirty；“放弃未保存改动”继续只恢复已知当前保存快照，不能叫历史恢复。

dirty阻止执行恢复，先保存或显式放弃。保存/转换/恢复/库写入/采集开始或终态未知均互斥；请求前同步ref锁，响应只在scope/图ID/请求代数仍匹配时生效。沿用5a的组件内状态保护，dirty/unknown阻断图、Lab/category切换及写操作；不新增全局SPA离页守卫或跨卸载草稿/unknown持久存储。实际在途beginWork跨组件卸载保留至该网络任务落定，迟到响应不写已卸载UI。离开不会取消服务器请求；返回时从服务器GET当前图/列表重新建立保存基线，提示核查最新修订，不使用离页前缓存令牌/草稿，不显示原写成功、不自动POST。真实采集未知的既有保守锁不变。

409保留草稿和输入，明确提示服务器已变化；可显式刷新查看最新，不自动重试、不自动合并、不悄悄用新令牌重放旧内容。写超时保留未知提示，禁止自动再次恢复；刷新服务器修订核对结果。恢复成功重读详情、更新revision/draft并清理旧选择，不把preview raw当GET模型。采集真实busy不能因finally或网络失败解除。

## 6. 消费方全集与不改范围

| 范围 | 核查/处置 |
|---|---|
| switch_topology.py create/copy/import | 原事务创建当前快照，复制raw及校准边界不变 |
| 普通PATCH/name-only/conversion | expected_revision原子CAS+原快照；保留转换source_digest/raw CAS |
| DELETE与chamber.py bulk DELETE | 新修订引用拒绝删除，无删除UI，不移除原采用/证书保护 |
| TopologyEditor保存/改名/转换、service、types、OpenAPI、mock | 令牌/冲突四镜像全接；不会从旧props取过期令牌后自动覆盖 |
| orchestrate_switch_topology / rf_chain_resolver | 仍按既有active/updated_at，name-only不改选图；恢复不自动切活跃状态 |
| route_calibration / freeze / configuration_scope / topology_loss | 只读消费图沿原门；确认采用模型独立，历史snapshot不喂正式消费者；回归当前/冻结两端 |
| 通用topologies、instrument_topology_profiles、路测网络 | 不是此对象，不扩展 |

以上为源码路径核查，不是已实施或现场结论。NotebookLM不适用：本片不修改仪器命令/回读量纲/SCPI。memory仅用于交叉核对保存前保护及草稿撤销与已保存恢复的区别，真实源码及最新用户授权为准。

## 7. 实施与验证出口

用户确认此细化契约后按writing-plans拆为：持久修订及全部写入口事务 → 历史/恢复API与资格隔离 → 原GUI历史/冲突生命周期 → 完整真实API/browser矩阵及最终全量。各任务独立规格/质量审查，整片累计审查；WIP1。

测试必须Python导入前新临时SQLite、Mock/bootstrap环境，bootstrap后显式核全部Mock绑定；不接默认DB/用户服务，不碰原CAICT。新迁移覆盖已有raw图保形及rollback；双连接CAS冲突与快照失败回滚，name-only正式选图不变，复制/模板、不适用旧客户端422、删除保护均覆盖。

恢复旧快照清空内嵌校准与历史原件不变；有效普通/参考路径的confirmed一次补偿、现有freeze身份变化两端拒绝、同身份沿原门验证。GUI真实鼠标编辑保存、历史预览不写、误保存恢复新修订、冲突保留草稿、超时核查、跨scope迟到、dirty/busy及采集未知锁留存请求/截图/只读库证据。

本片共享持久化与并发行为变化，稳定输入后唯一责任人执行最终后端全量、相关GUI及production build；不按review身份重复全量。5a的8003/17/3只作前片基线说明，不能当本片验证，不改历史/门造绿。ReadyPR R1/R2按最新HEAD全通道及SHA约束收口；软件完成不代表现场B/HOLD。
