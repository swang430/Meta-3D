# PC-04A-5c CAICT 副本逐路独立 PA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development 或 superpowers:executing-plans，逐任务执行；主任务安排独立规格、质量与累计审查。步骤用复选框跟踪。本计划编制者只交付文档，不实施、不派子代理、不释放主任务 claim。

**Goal:** 在用户指定 CAICT 原图的 inactive、非 default 副本中，将 32 条 F64→probe 复合边逐路替换为 F64→独立 PA.in/out→原 probe，并提供可复核映射、损耗未知边界及恢复证据。

**Architecture:** 复用 5a 服务端原始 JSON copy 和 5b revision/CAS、历史快照与恢复；新增一个只处理文件的离线纯 JSON 转换器，不新增 GUI/API/数据库迁移。4d 只能编辑既有节点/边，不支持插入或拆边，因此不扩其通用协议，也不把 PA 两侧伪装成同线缆 owner。候选经现有普通 PATCH 保存到副本，源图不进入任何写请求。Task2必须用完整模式对照正常绑定；若插入PA触发既有中转分支过宽CE回接拒绝，经主任务裁决仅收窄该判据，保留真回路拒绝，并升级相关回归及唯一最终全量。

**Tech Stack:** Python 标准库、现有 pytest/FastAPI/SQLAlchemy、现有 React/Mantine/ReactFlow 和真实浏览器；没有新增运行依赖。

**Spec:** [已批准总体设计](../design/2026-10-27-topology-library-pa-recovery.md) §5 的 5c；基线 `46402d6e51af305e00a2e3d968187d26dbdc602a`。2026-10-28 用户已确定准确源 UUID；以下量值处理是主任务接受的最小实施裁决，不代表新增现场证据。

**状态：** 仅计划；本文的测试、浏览器、备份恢复和最终副本写入均尚未执行。不可把 5b 的通过数、旧备份或旧截图当作本片证据。当前分支 `codex/pc04a5c-independent-pa`。

## Global Constraints

- 原 CAICT 只读，准确源 `87df2355-00f2-4fd6-9a38-ebacb2ccb2e5`，Lab `7aea2b69-19d7-4e43-a6ec-9c0691156fc8`（CAICT-Lab-1），chamber `59c73fbe-7362-4004-9a80-f72dd8779c3e`，category `1d04e85c-6a27-4153-94a2-d2b07f2ff4a0`；不得按同名 CAICT 选择。
- WIP=1；仅实施 5c，非 5d 综合交付。原图、历史修订、证书、Application、Selection、采集记录和执行冻结不得回写；副本始终 `is_active=false,is_default=false`，不改 Lab binding、port_maps 或编辑器默认偏好。
- 不使用默认 DB，不碰用户运行服务，不连接硬件；测试应用导入前指定全新 SQLite、显式 Mock，bootstrap 后再次设置并核对所有类别与全部 Lab binding 为 Mock，再检查实际驱动 `is_mock_driver()`。
- 原 `ce_port` 是对应声明来源，坐标、名称、ID 拼写、型号不是物理事实。原 source_pin=`out`→新 B# 必须列明为本次显式声明，不能说原 pin 已是 B#。
- PA `ports=['in','out']`，`port_directions={'in':'input','out':'output'}`，`internal_paths=[{'from_port':'in','to_port':'out'}]`；一条原边对应一个 PA 和两条新边，禁止共享 PA 或重排原 CE→probe 身份。
- 原 20 dB 仅旧版标称，绝不变实测；未知不补零，原复合损耗不得重复计算。软件声明不等于现场导通、RF 认证、校准合格或 B/HOLD 解除。
- 最终本机副本写入仅由主任务在合并、验证、新备份和恢复演练之后执行；实施子任务只在自己的隔离库写入。
- 主任务维护台账 claim、进度与释放。NotebookLM 本片不适用：不改 HAL、SCPI 或仪器语义；发现需要断言仪器事实时停止扩展并报告。

---

## 0. 已核原图、全集与实施裁决

### 0.1 原始证据与非承诺范围

本机证据 `output/pc04a5b-deploy-D5Zfe4/topologies-after-ui.jsonl` 有三行，必须按上述 UUID 选一行。文件 SHA-256 为 `7d3b4a6e3786121d72b59137f9d701ca0cba4a00655c8d7c2b27ebdb38d33bed`。以下命令输出的“排序键紧凑 JSON + 换行”摘要为 `b087c6060bdd4918192d5d49b74869de10c9f2d28fb479ba5e15716a6635e626`；它与转换器无换行 canonical digest 是两种格式，不可混比较。

```bash
jq -cS 'select(.id=="87df2355-00f2-4fd6-9a38-ebacb2ccb2e5")' output/pc04a5b-deploy-D5Zfe4/topologies-after-ui.jsonl | shasum -a 256
```

原始证据包含 88 节点、90 边、5 模式；没有 `revision` 字段，不能把缺字段补成已核 r0。实施时从真实 GET 只取当前身份/整数 revision，原图内容以新 raw 导出和摘要为准。原 F64 节点 `ce_f64` 没有 `ports`，仅保存 inputs=4/outputs=32；四条入边 target_pin 为 `in1`～`in4`。32 条目标边均 source_pin=`out`、target_pin=`in`、`pa_gain_db=20.0`、`cable_loss_db=0.8`、`cable_length_m=5.0`、复合 cable_type=`Phase-matched N-N + 集成PA + Semi-rigid`，calibrated 两字段均 null。32 个水平探头没有 ports；无 `rf_path_selection`、无 `loss_owner_connection_id`。其余 48 个垂直探头及所有参考器件不改。

32 路原对应关系（V/H 来自 probe.params，不从 ID 猜）：

| CE | 原 probe | CE | 原 probe |
|---|---|---|---|
| B1 | hprobe_1v | B2 | hprobe_1h |
| B3 | hprobe_9v | B4 | hprobe_9h |
| B5 | hprobe_2v | B6 | hprobe_2h |
| B7 | hprobe_10v | B8 | hprobe_10h |
| B9 | hprobe_3v | B10 | hprobe_3h |
| B11 | hprobe_11v | B12 | hprobe_11h |
| B13 | hprobe_4v | B14 | hprobe_4h |
| B15 | hprobe_12v | B16 | hprobe_12h |
| B17 | hprobe_5v | B18 | hprobe_5h |
| B19 | hprobe_13v | B20 | hprobe_13h |
| B21 | hprobe_6v | B22 | hprobe_6h |
| B23 | hprobe_14v | B24 | hprobe_14h |
| B25 | hprobe_7v | B26 | hprobe_7h |
| B27 | hprobe_15v | B28 | hprobe_15h |
| B29 | hprobe_8v | B30 | hprobe_8h |
| B31 | hprobe_16v | B32 | hprobe_16h |

边 ID 全量来源用下面命令复算，manifest 保存真实原 ID，而非用表格重建 ID：

```bash
jq -r 'select(.id=="87df2355-00f2-4fd6-9a38-ebacb2ccb2e5") | .connections[] | select(.source=="ce_f64") | [.id,.ce_port,.target,.target_pin]|@tsv' output/pc04a5b-deploy-D5Zfe4/topologies-after-ui.jsonl
```

### 0.2 损耗裁决与明确代价

2026-10-28 主任务裁决：复合边的 0.8 dB、5 m、cable_type 无两侧分配依据。两条新边 `cable_loss_db=null`，不写 0、不把 0.8 任意塞到某侧，也不在两侧复制 0.8；长度缺键，不将 5 m 分摊或复制。原边完整 JSON 同时保存到 manifest 与新 PA 的 `params.pc04a5c_legacy_connection`（不透明历史资料）；这不是有效线缆量值，也不是校准依据。

PA `params.gain_db` 沿原 `pa_gain_db` 数值复制，`nominal_metadata.gain_db.source_note` 写准确源 UUID/原 edge ID，并注明“旧版标称/来源未核；原复合线缆 0.8 dB、5 m 未分配，不进入当前补偿”。新边不带 `pa_gain_db`，不把旧值转换为任何 calibrated 字段。不新增聚合损耗机制，不修改 `topology_loss_ownership.ownership_groups` 只允许 cable/receive_cable 的边界。

代价明确：副本的逐路通用总损耗和正式末边损耗为 unknown，直到操作员逐段声明或另行完成适用校准。原图与历史计算不变；已有 confirmed 整链数值也不得再加 PA 标称或两侧线缆。历史原值保留与当前补偿未知是不同声明，不得把前者包装成后者已知。

### 0.3 实施前消费全集（每行有可观察断言）

| 入口 / 写方 | 权威读取与消费者 | 本片处理 / 验收 |
|---|---|---|
| raw 文件→转换器 | `.id/chamber_id/switch_category_id`，原 edge.ce_port、probe.params | 唯一准确源；32 个 B# 与 probe/pol 元组完全相同；坐标只参与排版 |
| 5a copy | `app/api/switch_topology.py::copy_switch_topology`，ORM raw、两 calibrated 字段清空 | 新 UUID/r1/inactive/非default；原图 raw、revision、updated_at 不变；不以 typed GET 重建 |
| 普通 PATCH | `update_switch_topology`，`preserve_graph_rows/preserve_connection_rows`，所有结构/端口/内部路径/owner 门，5b CAS | 只写副本三个图数组 + expected_revision；新图 120 节点、122 边；失败零修订，过期409 |
| 4d conversion | `build_conversion` 仅既有对象白名单；`conversion_differences` 按旧 ID 查行 | 本片不调用它来增加/删除对象，不扩4d；复用的是其既有保存校验边界，不宣称复用其拆边能力 |
| 普通与模式引用 | edge.modes；mode.active_connections 非空优先，空时回退 edge.modes | 原边在原位置替换为入/出两ID；两边复制原 modes。mimo_ota 37→69，calibration_e2e 39→71；其它3模式49/49/50不变 |
| 显式路径 | probe.params.rf_path_selection.connection_ids + switch_mappings；`declared_rf_routes.resolve_saved_rf_path` | 本源数量为0。转换器遇本源之外新增显式引用就报输入已变，不猜路径；测试证明拒绝，不悄悄丢引用 |
| loss owner | `topology_loss_ownership`、`topology_loss.loss_sources_for_path/loss_source_for_terminal` | 本源数量为0。目标边参与owner或被owner指向则拒绝转换，不能扩展到PA；非目标owner保形且走现有门 |
| 量值 | `TopologyService`、矩阵、`_build_probe_binding`、`configuration_scope._scope_chain_for_route` | 隔离逐路已保存两边解析为unknown；PA旧标称不被加减；读取缺值不得写0 |
| 普通正式选图 | `mimo_ota/switch_orchestrator.orchestrate_switch_topology` 按chamber/is_active/updated_at，`rf_chain_resolver` | 源活跃、副本inactive；选择ID和源行为前后不变，不激活副本来凑通过 |
| 参考段 | `calibration/route_calibration._route_selections`；只有 `calibration` 模式沿probe追参考段 | 不把历史 `calibration_e2e` 改名为 `calibration`，不加虚构air_path/参考仪器；参考节点/边逐字段不变 |
| 采用与冻结 | `route_calibration`、`configuration_scope`、`mimo_ota/route_calibration_freeze`、`mimo_ota/executors/measure.py` | 副本不产生Application/Selection/证书；原confirmed整链只计一次，原execution frozen payload逐字不变；已有NULL topology_id兼容不声称被修复 |
| 历史恢复 | `topology_revisions`、`restore-preview/restore` | 预览不写；副本恢复为新修订，不恢复active/default或资格；原图不参与恢复 |
| GUI | `TopologyEditor`、`NominalPropertyFields`、`CustomEdges` | 用既有库选择副本，显示32独立PA与两边损耗未知；来源说明可见；保存重载与历史恢复不丢opaque历史资料 |

实施前再查全集；新增命中先判断是否涉及本转换，不顺带修全仓：

```bash
git grep -n 'pa_gain_db\|loss_owner_connection_id\|rf_path_selection' -- api-service/app gui/src
git grep -n 'SwitchTopology\|switch_topology_id' -- api-service/app
git grep -n 'active_connections\|connection_ids' -- api-service/app/services/calibration api-service/app/services/mimo_ota gui/src/features/TopologyEditor
```

**完整模式必须区分既有拒绝与新回归：** raw 的 mimo_ota 同时包含4条 BSE→CE 入边；`_build_probe_binding` 原直连分支只将输出两端送入末尾校验，中转分支却额外检查完整active图任意CE入边。插PA后可能从原正常32路变成“CE源端存在回接”，这是本片引入的功能回归，不能称为旧问题。Task2完整原raw/候选raw、同一完整active模式对照是阻塞验收；逐路两边子图绿不能替代它。`resolve_saved_rf_path` 显式路径对完整active也会拒绝CE入边，所以不新增无效rf_path_selection绕门；不删除BSE入边、不改模式。`TopologyService`全图DFS和route-calibration的既有拒绝分别记录，不能与新正常binding回归混称。inactive副本的route-calibration-paths拒绝仍是预期，不自动激活副本。只有主任务确认Task2的RED归因后，才实施下述条件小修。

### 0.4 原图保形例外白名单与最小文件集

候选只允许：新增32 PA、32原边原位置替换64新边；F64补 ports（原四个输入pin + 原显式32个ce_port）及输出方向；32目标probe补 ports=['in']（方向仍未知，不猜）；两模式active引用替换。不新增probe显式路径、不改F64输入角色、不改所有原坐标/标签/其它params、不修历史模式说明。新PA可用原probe坐标安排画布位置，但这些坐标不得参与映射、方向或量值判断。

| 任务 | 文件与职责（均为“修”；条件生产修改需单独裁决） |
|---|---|
| 1 | `api-service/scripts/pc04a5c_independent_pa.py`：纯函数+离线CLI；`api-service/tests/test_pc04a5c_independent_pa.py`：契约TDD；`api-service/tests/fixtures/pc04a5c_caict_source.json`：从准确raw原行取出的图内容与来源标记，非现场新测量 |
| 2 | `api-service/tests/test_pc04a5c_copy_roundtrip.py`：真实API持久化/恢复/资格；`api-service/tests/pc04a5c_browser_fixture.py`：新SQLite全Mock夹具；`gui/vite.pc04a5c.config.ts`：隔离代理；`docs/validation/2026-10-28-pc04a5c-independent-pa.md`：命令、原始结果、截图、hash、已知未验边界 |
| 2（只有完整模式RED证实且主任务裁决后） | 修改 `api-service/app/services/mimo_ota/switch_orchestrator.py::_build_probe_binding` 中转分支的CE入边拒绝；本Task测试新增完整模式与真环路正反例。不修改通用显式路径、参考校准、owner、schema或HAL |

浏览器使用真实已有页面，不新增批改产品界面。真实浏览器验证可依环境技能保存操作回执，不强制新增自动化框架。除本计划状态记录外，不改历史计划、门或已归档数字。若实现需要修改上表以外的生产文件，先报告可观察故障与最小方案。

## Task 1：只读离线转换器与32路映射契约

**Interfaces:** `select_source(rows: list[dict], source_id: str) -> dict` 唯一选源；`build_candidate(source: dict) -> tuple[dict,dict]` 返回仅含三图数组的candidate和manifest；`canonical_sha256(value: object) -> str` 使用 UTF-8、sort_keys、紧凑分隔、ensure_ascii=False、allow_nan=False、无尾换行。CLI 必填 `--source-jsonl --source-id --output-dir`，只读文件/写新证据目录，无HTTP、DB、app或HAL导入，不接收数据库URL或任意目标UUID写入。

- [ ] **Step 1：建立最小可信夹具并写RED。** 复制准确raw原行到新 fixture，保留节点/边/模式原JSON；注明来源SHA和“配置快照，非新测量”，不要通过schema导出。用 `importlib.util.spec_from_file_location` 按脚本路径加载纯函数，避免导入应用。测试直接核对原映射和未知，不只断言数量。

```python
def test_candidate_has_exact_mapping_and_no_invented_loss(source):
    before = deepcopy(source)
    graph, manifest = build_candidate(source)
    assert source == before
    assert len(graph['nodes']) == 120
    assert len(graph['connections']) == 122
    assert len(manifest['routes']) == 32
    edges = {e['id']: e for e in graph['connections']}
    nodes = {n['id']: n for n in graph['nodes']}
    for row in manifest['routes']:
        old = next(e for e in source['connections'] if e['id'] == row['original_connection_id'])
        first, last = [edges[x] for x in row['replacement_connection_ids']]
        pa = nodes[row['pa_node_id']]
        assert (first['source'], first['source_pin'], first['target_pin']) == ('ce_f64', old['ce_port'], 'in')
        assert (last['target'], last['target_pin'], last['source_pin']) == (old['target'], old['target_pin'], 'out')
        assert first['target'] == last['source'] == pa['id']
        assert first['cable_loss_db'] is None and last['cable_loss_db'] is None
        assert 'cable_length_m' not in first and 'cable_length_m' not in last
        assert 'pa_gain_db' not in first and 'pa_gain_db' not in last
        assert pa['params']['gain_db'] == old['pa_gain_db']
        assert pa['params']['pc04a5c_legacy_connection'] == old
        assert old['id'] not in edges
    assert manifest['source_graph_sha256'] == canonical_sha256({k: source[k] for k in ('nodes','connections','operating_modes')})
```

fixture `source` 用 `json.loads(Path(...).read_text())` 读取上述已跟踪 fixture；`deepcopy` 从copy导入。RED首先因为脚本/函数不存在而失败，不能是错连默认DB或缺依赖失败。

- [ ] **Step 2：导入前隔离，运行RED并存真实输出。** 从api-service执行；每个任务新建目录，变量不覆盖系统变量。

```bash
pc04a5c_run_dir=$(mktemp -d /tmp/pc04a5c-XXXXXX)
export DATABASE_URL="sqlite:///$pc04a5c_run_dir/test.sqlite"
export USE_MOCK_INSTRUMENTS=true
export BOOTSTRAP_ON_STARTUP=false
export LOG_DIR="$pc04a5c_run_dir/logs"
.venv/bin/python -m pytest tests/test_pc04a5c_independent_pa.py -q
```

- [ ] **Step 3：实现限定源的预检及纯转换。** 预检唯一源ID/chamber/category；唯一nodes/edges；32目标均 source=ce_f64、target type=probe，ce_port集合恰B1～B32且无重复，source_pin=out、target_pin=in；target.params的ce_port与边一致，probe_id为整数、polarization为V/H。核对本节32路对应元组和原20/0.8/5m数值，且三个图数组canonical hash与已跟踪原raw fixture一致，不根据名字重新生成。目标相关显式路径/owner、新增参考入出边、已有候选ID、已转换PA或源形态不符，一律ValueError，且不写任何输出文件；不把错误输入部分转换。未知扩展仅存原边历史资料，不赋予新边有效含义。核心构造如下：

```python
graph = {key: deepcopy(source[key]) for key in ('nodes','connections','operating_modes')}
targets = [e for e in source['connections'] if e['source'] == 'ce_f64']
replacement, routes, added = {}, [], []
for old in targets:  # 顺序来自raw；CE/probe身份来自显式字段
    pa_id = 'pc04a5c_pa_' + old['ce_port']
    incoming_id, outgoing_id = old['id'] + '__pa_in', old['id'] + '__pa_out'
    note = (f"旧版标称/来源未核：{source['id']}/{old['id']}.pa_gain_db；"
            "原复合线缆0.8 dB、5 m未分配，不进入当前补偿；非实测/非资格")
    target = next(n for n in source['nodes'] if n['id'] == old['target'])
    added.append(dict(id=pa_id,type='amplifier',label='独立 PA '+old['ce_port'],
        position={'x':550.0,'y':float(target['position']['y'])},params={
            'ports':['in','out'],'port_directions':{'in':'input','out':'output'},
            'internal_paths':[{'from_port':'in','to_port':'out'}],
            'gain_db':old['pa_gain_db'],
            'nominal_metadata':{'gain_db':{'unit':'dB','source_note':note,'frequency_range_mhz':None}},
            'pc04a5c_legacy_connection':deepcopy(old)}))
    common = dict(ce_port=old['ce_port'], direction=old['direction'],
                  modes=deepcopy(old['modes']), cable_loss_db=None,
                  calibrated_loss_db=None,calibrated_phase_deg=None)
    first = dict(common,id=incoming_id,source=old['source'],source_pin=old['ce_port'],
                 target=pa_id,target_pin='in')
    last = dict(common,id=outgoing_id,source=pa_id,source_pin='out',
                target=old['target'],target_pin=old['target_pin'])
    replacement[old['id']] = [first,last]
    routes.append(dict(original_connection_id=old['id'],original_connection=deepcopy(old),
        original_source_pin=old['source_pin'],declared_source_pin=old['ce_port'],
        ce_port=old['ce_port'],probe_node_id=old['target'],probe_id=target['params']['probe_id'],
        polarization=target['params']['polarization'],target_pin=old['target_pin'],
        pa_node_id=pa_id,replacement_connection_ids=[incoming_id,outgoing_id]))
graph['nodes'].extend(added)
graph['connections'] = [part for edge in source['connections']
    for part in replacement.get(edge['id'], [deepcopy(edge)])]
for mode in graph['operating_modes']:
    if 'active_connections' in mode:
        mode['active_connections'] = [part['id'] if isinstance(part,dict) else part
            for ident in mode['active_connections']
            for part in replacement.get(ident,[ident])]
```

对F64只补 `ports=['in1','in2','in3','in4',*原ce_port顺序]` 和B#→output，输入方向不填；32个probe只补原保存 target_pin=`in` 到ports。不改变现有四输入边，不新增CE内部路径。manifest还包含source身份、原文件SHA、原图/候选graph SHA、每个模式引用before/after、每个补声明节点before/after、量值裁决文案和 `software_only=true`。源元信息不混入candidate；候选没有 `is_active/is_default`，不会成为激活请求。

CLI预检和构造全部成功后才建立新的output-dir；若已存在拒绝覆盖。生成 `candidate.json`、`manifest.json`、`preview.md`，全部用标准JSON/UTF-8，preview列出32行原ID、B#、原probe/pol、新PA/两边、out→B#及损耗“未分配/未知”。不写PATCH请求令牌：令牌属于最终副本，不能从源/旧文件推定。

- [ ] **Step 4：GREEN和负例。** 同一命令重跑；新增参数化反例：0/2个同UUID、缺/重复B#、probe身份冲突、目标引用显式路径、owner指向/被指向、已存在PA ID、源输入pin变化、目标新参考边、第二次转换。所有反例断言ValueError且source未变、CLI没有半套输出；正例断言58非目标边完全相同、55非目标原节点完全相同、F64/32probe仅白名单键变化、其它3模式完全相同。固定全部旧边量值字段为原始证据而非typed默认。
- [ ] **Step 5：核心反向验证。** 在临时副本中去掉模式替换/复用同PA/把一侧损耗置0/让脚本接受重复CE，每种至少对应一个断言变红；恢复后核对文件hash一致。仅用于证明核心修复，测试强度建议不扩散成新门。
- [ ] **Step 6：向主任务交接，主任务唯一派独立规格审查→质量审查；定点回归后提交。** 实施者不自行派审查。审查者只读；重点审32路对应与0.8未分配，不要求扩展任意拓扑转换。提交仅Task1三个文件，中文提交说明如 `feat: 增加CAICT独立PA离线候选转换器`。

## Task 2：隔离真实API、真实浏览器、恢复与交付证据

**Interfaces:** 使用Task1 `build_candidate` 与manifest；只复用现有 `POST /api/v1/switch-topologies/{id}/copy?lab_profile_id=...`、`PATCH /{id}`、`GET /{id}/revisions/{revision}`、`POST /{id}/restore-preview` 和 `/restore`。copy body仅name；PATCH body仅expected_revision及三个数组；restore body恰 `{revision,expected_revision}`。新 `pc04a5c_browser_fixture.py` 提供 `bootstrap_mock_database() -> dict`、`seed() -> dict`；夹具不接任意DB URL。

- [ ] **Step 1：新库先隔离bootstrap、再导入应用。** 路径守卫限定 `/tmp/pc04a5c-[A-Za-z0-9]+/browser.sqlite` 且文件事前不存在，bootstrap-only路径限定同目录 `test.sqlite`。参考 `tests/pc04a5b_browser_fixture.py` 的完整安全顺序，不修改旧文件/硬编码5b路径，也不复用其数据库：

```python
url = os.environ['DATABASE_URL']
assert re.fullmatch(r'sqlite:////tmp/pc04a5c-[A-Za-z0-9]+/(browser|test)\.sqlite', url)
path = Path(url.removeprefix('sqlite:///'))
assert path.parent.is_dir() and not path.exists()
assert os.environ['USE_MOCK_INSTRUMENTS'] == 'true'
assert os.environ['BOOTSTRAP_ON_STARTUP'] == 'true'
# 以上通过以后才能导入app.main、database、bootstrap。
```

bootstrap后逐类别 `driver_mode='mock'`；全部Lab绑定 `driver_mode='mock',connection_endpoint='192.0.2.10'`；重新查询非空类别/绑定并assert all mock。调用 `InstrumentHALService.initialize()` 后以 `is_mock_driver` 核对每个已加载驱动并shutdown；输出实际class，不把环境变量当实际状态。专用服务随后使用 `BOOTSTRAP_ON_STARTUP=false`，避免再播种覆盖Mock。增加两个隔离Lab/chamber；将完整原图作为明确legacy ORM夹具导入第一暗室（并记录仅替换外层数据库身份，三图数组原样）。第二暗室只做跨scope拒绝。禁止这段fixture执行于默认库。

- [ ] **Step 2：既有真实API组合验证。** 新 `test_pc04a5c_copy_roundtrip.py` 复用5a的 `db/client/world/lab` 命名fixtures，独立建立原raw行，不以ORM直接创建最终副本。已有正确copy/PATCH无需回退生产代码制造RED，先对真实候选运行GREEN；本片新增转换的核心保护另做变异。核心生产入口序列如下（辅助 `raw_graph(db,id)` 只读ORM三个数组；`graph`来自Task1）：

```python
before = raw_graph(db, source.id)
params = {'lab_profile_id':str(lab.id)}
copy_response = client.post(f'/api/v1/switch-topologies/{source.id}/copy',
    params=params, json={'name':'CAICT 独立PA副本（隔离软件验证）'})
assert copy_response.status_code == 201
copied = copy_response.json()
assert copied['id'] != str(source.id)
assert copied['is_active'] is False and copied['is_default'] is False
assert copied['revision'] == 1
saved = client.patch(f"/api/v1/switch-topologies/{copied['id']}", params=params,
    json={'expected_revision':1, **graph})
assert saved.status_code == 200, saved.text
assert saved.json()['revision'] == 2
assert raw_graph(db, source.id) == before
assert raw_graph(db, copied['id']) == graph
assert client.patch(f"/api/v1/switch-topologies/{copied['id']}", params=params,
    json={'expected_revision':1, **graph}).status_code == 409
```

GREEN使用Task1真实candidate。单独核心变异撤销“插PA”，32PA/64边断言须失败，不把变异实跑写成新生产行为的RED。source所有列、revision、updated_at、历史计数前后不变；copy r1→PATCH r2，历史r1是清过校准的raw副本，r2是candidate。保存的raw与candidate的数值/缺键/opaque完全比较，不能只比较typed GET。

- [ ] **Step 3：32路与消费者正反例。** 对每行manifest从数据库保存raw只选对应两条边，调用 `resolve_saved_rf_path`，断言节点序列 `[ce_f64,PA,原probe]`、CE号/编号/极化完全相同、`validate_internal_traversals` 只得到PA.in→out；`loss_sources_for_path` 给出两条未知量值、`loss_source_for_terminal`有效值None。用仅含这条已声明输出子路径的TopologyService输入验证 `total_loss_db is None`、矩阵compensation为None；明确标注是输出子图，禁止冒充完整模式。反向PA pair、删除任一边、重复CE身份、错probe须拒绝或对应断言失败。

对完整原raw和候选raw分别调用完整模式解析、保存状态和显式topology校准查询，记录实际成功/422及理由；inactive副本的校准入口必须拒绝。源正式选图ID不变。正常binding必须从完整active_connections传入 `_build_probe_binding`，不能先过滤BSE入边；若原32路成功、候选失败，停止Task2并报告主任务，不交付退化副本。用纯函数调用完整保存图不需要激活副本；生产选图仍沿真实orchestrator核对源ID。参考节点/边/模式保形，比对没有新增采集资格。

**条件TDD：仅修实证中的过宽CE入边判据。** 测试收集完整mimo_ota活动边（mode.active_connections优先），对所有target type=probe的末边逐一调用 `_build_probe_binding(edge,node_index,完整active)`；原raw应保持32个原 `(ce_port,probe_id,polarization)` 元组，candidate应是同32元组、chain_id变manifest新出边、loss=None。若候选在过宽判据上RED，先向主任务附该输出。建议修法形状是“收窄”，不是新机制：允许真实源节点类型属于现有BSE_TYPES的上游BSE→CE输入；其它CE回接保持拒绝，不能依据source名字或label排除。示意仅替换中转分支现有拒绝条件，最终具体diff由主任务核准：

```python
from app.schemas.topology_ports import BSE_TYPES
bad_ce_input = any(
    edge.get('target') == current['id']
    and (edge.get('source') in seen
         or nodes_by_id.get(edge.get('source'), {}).get('type') not in BSE_TYPES)
    for edge in active_connections or []
)
if current['id'] in seen or bad_ce_input:
    raise ValueError('正常测试CE源端存在回接')
```

GREEN必须同时覆盖：完整4条BSE输入+32 PA输出正常；去掉BSE输入仍32路；probe→CE、PA→CE、PA自环/多父边、中转环路拒绝；源节点只改名为baseStation而type仍probe不能放行；不把BSE作为CE→probe输出链的中转。固定的正式模拟证据仍不能成为实测。此条件若触发，Task2增加相关rf_chain_resolver/拓扑执行回归，稳定版本后由Task2执行者唯一跑全量；主任务/审查者不得重复跑。若示意仍不能保持这些边界，停报根因，不继续加新分类器。

为“confirmed只计一次”复用已有 `test_pc04a5b_restore_qualification.py`、`test_pc04a2_route_freeze.py` 正向断言，保留其synthetic fixture属性；增加本片copy/PATCH前后四张记录表及原execution freeze逐字相同断言。不能把Mock采集做成confirmed，也不能凭副本新UUID宣称所有旧证书兼容被取消。

- [ ] **Step 4：副本恢复演练与失败事务。** r2→restore-preview r1 只读；restore r1 expected=2→r3，图回到copy基线且inactive/非default；再PATCH原candidate expected=3→r4。每步原图hash不变；原r1/r2历史immutable。过期恢复409、跨暗室409、缺令牌422、候选错pin/半链422且revision/history不变。网络未知不自动重试copy/PATCH，读列表/最新revision核实。保存回执必须带实际副本UUID，而非复用源UUID。

- [ ] **Step 5：真实浏览器和build。** 新隔离API使用18116、Vite18117（运行前只读确认端口空闲，有占用换空闲端口并同步本片配置，不停用户进程）。Vite专用配置在原config之上同时覆盖 `/api/v1/ota`、`/api/v1/ws` 和 `/api`，避免默认代理漏回8000；其目标均为 `http://127.0.0.1:18116`。启动命令从对应目录运行：

```bash
# api-service；DATABASE_URL指向本Task全新browser.sqlite，Mock核查通过之后
BOOTSTRAP_ON_STARTUP=false .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18116
# gui
npm run dev -- --config vite.pc04a5c.config.ts --host 127.0.0.1 --port 18117
```

先读适用浏览器技能，真实点击库选择源→复制已保存版本→选择副本；服务端回读确认ID/inactive/非default后，将离线预览已核candidate经真实PATCH送副本并刷新页面。不用route mock拦截。确认32独立PA、ports/方向/pair、原B#对应probe；至少首/中/末路真点击PA及两侧边，来源说明显示旧标称且0.8未分配、线缆损耗为空/未知；截图与网络回执关联同UUID/revision。真实拖动一个PA→保存→刷新，增益20、两边null、opaque原边均保留；用已有历史面板预览/恢复到候选修订，来源/未知/对应关系复核。另页过期保存409保留草稿，库切换仍走既有dirty/busy守卫；不新增跨SPA机制。真实操作结尾只读审计源raw和副本raw哈希。

```bash
# api-service（新test.sqlite + Mock，安全bootstrap完成后）
.venv/bin/python -m pytest tests/test_pc04a5c_independent_pa.py tests/test_pc04a5c_copy_roundtrip.py tests/test_pc04a4d_loss_truth.py tests/test_pc04a4c_internal_identity.py tests/test_pc04a5a_topology_library.py tests/test_pc04a5b_topology_revisions.py tests/test_pc04a5b_topology_restore.py tests/test_pc04a5b_restore_qualification.py -q
# gui
node --experimental-strip-types --test test/topologyDraft.test.ts test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts
npm run build
```

命令以实际node支持为准，失败不换成假通过；保存SHA、差异/输入hash、环境、退出码和完整结尾统计。若最终仅离线脚本/tests/专用隔离配置，无共享生产后端改动，不因5b曾全量就重跑8066项。若条件小修触发或其它共享后端、冻结、schema或依赖实际变更，立即升档；唯一最终后端全量责任人是Task2执行者（由主任务明确指定），另建新SQLite安全bootstrap后在稳定输入上运行 `.venv/bin/python -m pytest tests -q`，主任务和审查者不重复跑。记录测试前后tracked/未跟踪输入hash，输入变化后旧结果过期；不改三项历史门来刷绿。

- [ ] **Step 6：交主任务唯一派独立规格/质量审查、整片累计审查并提交。** 实施者不自行派审查。Task2验证文档含当前实际结果（未跑项明确未跑）、所有回执/截图/manifest路径和hash、完整模式对照及条件修法、原图不变/副本恢复结论。每任务两阶段独立审查，累计复核只看本片两任务，不擅自清理用户output/venv/数据库。之后由主任务按AGENTS第10条R1→R2及P1续审规则处理PR；合并前不得写用户副本。

## 3. 主任务合并后本机落地检查清单（不属于子任务写权限）

- [ ] 软件验证和本机落地分开。若条件生产修复实际合并，现有运行服务仍是旧代码，不能直接把候选交给旧进程后称正常绑定已修。主任务先说明必要部署/服务重启目标并取得本片授权；5b的特定重启授权不泛化到5c。未获授权时软件工作可完成，但本机落地暂停，不擅自停用户服务。
- [ ] 新做完整数据库备份，记录时间、DB身份、大小、SHA；另导出本源全部列raw（包括当前revision）与三图数组raw。旧5b备份只能是历史参考。备份列表验证不等于恢复验证：恢复到全新明确命名演练库，检查本源原值/数量/hash和修订表可读；绝不恢复覆盖用户默认库。
- [ ] 只读重核Lab/chamber/category/source UUID、is_active/is_default和当前revision；source新raw与计划证据三图数组canonical hash一致才能继续。差异即停在预览重新核对，不“顺便更新”基线。源r0没有历史时通过只读raw SQL导出，不能为了获取raw先PATCH原图补历史。typed GET只取身份、revision，不用于整图重建。
- [ ] 运行已合并纯转换器生成新candidate、32路manifest和preview；由主任务核对量值未分配、完整模式缺口、每一路映射。离线工具不直接连本机API，也没有apply开关。
- [ ] 调5a copy，名称明确“CAICT 独立PA副本”，保存请求/响应；不自动重试未知结果。新UUID必须非源且inactive/非default/r1；读取副本r1历史raw，核对其与新源raw在仅两calibrated字段清空的例外下同形。整个源图hash必须仍相同。
- [ ] 用副本最新revision普通PATCH候选；冲突409立即停止、重读核对，不覆盖。回读raw/history确认32 PA/64替代边、120节点/122边、模式69/71及其余不变；核对PA gain20仅旧标称、两边null、复合0.8/5m只在历史资料；源摘要/updated_at/revision全部不变。
- [ ] 本机真实页面只读确认库可在原图/副本间选择，副本非活跃非默认，原图内容与默认保持；不启动采集、不激活、不改仪器绑定。最终交付源/副本UUID、raw hash、manifest hash、备份及恢复证据路径、实际修订。软件输出子路径通过不等于完整模式/现场校准通过。
- [ ] 写回项目台账、生成handoff并由主任务释放claim；原自动化不因本片自动恢复。

## 4. 计划自检

- [ ] 总体设计5c逐项对应：备份/恢复→§3；源UUID→§0.1；32路映射→Task1；两新边完整才替原边→Task1内存原子构造/Task2事务；模式和所有引用→§0.3；未知/旧标称→§0.2；真实API/浏览器→Task2；最终本机写→主任务。
- [ ] 不包含新通用转换API、新owner/聚合损耗机制、全局GUI批改入口、自动激活、硬件动作或5d综合验收；文件新增/机制扩大须主任务先裁决。
- [ ] 自查函数/字段/API名字与现有源码及本文接口一致，命令中的5c路径不复用5b库；检查无占位施工条目。所有统计在实际执行后填，不预写passed。
