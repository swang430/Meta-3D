# PC-04A-3 拓扑编辑完整性与恢复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 本片沿用已经批准的连续实施授权，按下列复选框逐项执行；WIP=1，不另开并行功能片，不重复要求用户批准。

**Goal:** 普通操作员能在原画布中恢复隐藏器件、声明双端线缆并接入原路径，安全改接、删除、保存及刷新；显式通路不会因编辑被静默降级为另一条自动推断路径。

**Architecture:** 保留 `TopologyEditor`、同一份 `draft` 与现有 LabProfile 限定的 `switch-topologies` API。优先收窄空显示模式和破坏显式引用的编辑，复用已有端口声明、探头路径声明与 `resolve_saved_rf_path`；不新建编辑器、路径引擎或损耗数据模型。新增的“器件列表”只打开现有属性抽屉，为历史全隐藏节点恢复编辑入口。

**Tech Stack:** React、TypeScript、Mantine、@xyflow/react；FastAPI、Pydantic v2、SQLAlchemy；Node test/tsx、pytest、真实浏览器及隔离文件 SQLite（生产仍为 PostgreSQL）。

**Spec:** [总计划](2026-10-25-topology-editor-calibration-consolidation.md)、[拓扑校准设计](../design/2026-10-24-topology-calibration-integration.md)。本片只细化 PC-04A-3，不修改两份上位文档或 roadmap 的完成状态。

## 全局约束

- 基线：`b870e91a`，分支 `codex/pc04a3-topology-editing-recovery`；实施前重新核对实际 HEAD 和工作区，保留 `.venv`、`output/`、`.playwright-cli/`、scratch 及用户资料。
- WIP=1；PC-06A-2 其余入口整合不在本片。每个任务独立 TDD/审查/提交，整片沿用 AGENTS 的外审收口规则，不复制第二套规则。
- 不改变仪器绑定、地址、驱动、自动控制资格、校准采用、补偿优先级、安全收尾及历史测量/执行。没有新增仪器语义，NotebookLM 不适用；若执行时发现必须改 HAL/SCPI，停止扩域并报告。
- 校准接线不进入正常模式；配置变化只提醒操作员复核，不自动降低就绪状态或强制重校准；Mock 不授予正式校准资格，PC-04B/05B/06B 和 PC-09/10 HOLD 不变。
- 保存失败保留草稿；既有位置、未知扩展参数、无关模式及历史数据不重写。读历史图不执行迁移；修复历史隐藏节点是用户明确保存的草稿修改。
- 线缆节点只是物理接线声明。继续以连线的 `calibrated_loss_db`（非空时）或 `cable_loss_db` 表示该段损耗，不在节点再存一份参与计算的损耗，不把整条实测损耗写入单段。
- 本片共享保存行为会修改，最终稳定输入须全后端一次；各任务先跑相关回归，GUI production build 必跑。不得把本计划中的预期结果写成已完成验证。

## 1. 已核验现状与缺口

本节是基线源码与隔离诊断的事实，不是实施后的验收。目标文件自身禁令已检查：显式端口替换旧 handles、不能 DOM 共存；dirty 切 LabProfile 不得丢草稿或改绑定；跨暗室默认行不能顺手改写。

### 全器件能力矩阵

图例：`有`表示存在生产入口，尚不代表逐类浏览器通过；`空`表示新增统一 `ports=[]`，应用属性前须声明非空端口；`通用`表示现有名称/端口/模式抽屉。连接用 ReactFlow 拖线；改接仅能在边抽屉改 pin，换源/目标器件须新增边再删旧边，不承诺拖动边端点重连。

| 器件 type | 新增 | 属性 | 新增端口 / 历史无声明回退 | 连接 / 改接 | 删除 | 模式 | 保存 / 重载 |
|---|---|---|---|---|---|---|---|
| cable | 有 | 通用 | 空 / out,in | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| receive_cable | 有 | 通用 | 空 / out,in | 有 / pin或重建边 | 有 | 仅 calibration | PATCH / GET |
| pad | 有 | 通用 | 空 / in,out | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| amplifier | 有 | 通用 | 空 / in,out | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| combiner | 有 | 通用 | 空 / in1..in4,out | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| termination | 有 | 通用 | 空 / in | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| probe | 有 | 通用+编号/极化/显式路径 | 空 / in | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| channel_emulator | 有 | 通用+目录关联 | 空 / in1..in4,out | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| communication_tester | 有 | 通用+目录关联 | 空 / 无 | 有；角色限制 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| emcenter | 有 | 通用+目录关联 | 空 / switch_in,pa_out,sw_out,pa_in | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| vna | 有 | 通用+目录关联 | 空 / Port1,Port2 | 有 / pin或重建边 | 有 | 当前模式 | PATCH / GET |
| reference_antenna | 有 | 通用 | 空 / rf | 有 / pin或重建边 | 有 | 仅 calibration | PATCH / GET |
| signal_analyzer | 有 | 通用+目录关联 | 空 / rf_in | 有 / pin或重建边 | 有 | 仅 calibration | PATCH / GET |
| air_path | 有 | 通用 | 空 / out,in | 有 / pin或重建边 | 有 | 仅 calibration | PATCH / GET |
| ce_port | 仅导入/已有图 | 通用+目录关联 | 历史 out | 有 / pin或重建边 | 有 | 原模式 | PATCH / GET |
| bse_port | 仅导入/已有图 | 通用+目录关联 | 历史 out | 有；角色限制 / pin或重建边 | 有 | 原模式 | PATCH / GET |
| switch_slot | 仅导入/已有图 | 通用+目录关联/映射指引 | 历史 P1..P4 | 有 / pin或重建边 | 有 | 原模式 | PATCH / GET |
| antenna | 仅导入/已有图 | 通用 | 历史 P1 | 有 / pin或重建边 | 有 | 原模式 | PATCH / GET |
| sa_port | 仅导入/已有图 | 通用 | 历史 in | 有 / pin或重建边 | 有 | 原模式 | PATCH / GET |

权威锚点：`TopologyEditor.nodeTypeOptions/addNode/applyNodeEdit/applyConnectionEdit`、`CustomNodes.originalNodeTypes/customNodeTypes/withDeclaredPorts`、`nodePortHelpers.getNodePorts`。14 个新增菜单类型、5 个仅导入渲染类型；不为覆盖矩阵擅自给旧类型增加菜单。上表“历史回退”只描述画布，不是物理仪器能力证明。

普通器件共同缺口：空 `visible_modes` 可应用后失去全部画布入口；无独立器件列表。校准scope器件的模式选择当前禁用，但历史空数组同样全隐藏，不能靠禁止新空选择解决。所有行共同保护：已连端口从端口集合移除会被 `updateDraftNode` 拒绝，后端也拒绝未声明 pin；删节点清关联边/模式，不删仪器资源/历史。只有 probe 的显式声明可能引用本节点之外的边/节点，需要 Task 2 的引用保护。

### 已实跑的最小复现

2026-10-25 在基线用原 `topologyDraft` 执行 Node/tsx，以及既有 `test_p1_57_topology_lab_context` 的 TestClient、dependency override 和内存隔离数据库执行生产 API；无 HAL 操作、无浏览器响应拦截：

| 操作 | 实际结果 | 本片判断 |
|---|---|---|
| 对线缆应用 visible_modes=[] | 草稿保留 []，`initialNodes` 的 includes 对所有模式均为 false | 失去入口，Task 1 收窄并增加恢复入口 |
| CE→线缆→probe 显式声明保存 | PATCH 200；route-calibration-paths GET 200，1条 | 正例 |
| 删除被声明引用的上游边，清模式引用 | PATCH 200；选路 GET 422“显式路径连接缺失、重复或终端不匹配” | 保存边界漏引用校验，不是已证实错误执行 |
| 删除中间线缆及其两边 | PATCH 200；选路 GET 200，[]；probe声明仍在 | 不能把空列表当成已修复或自动换路 |
| 将已连 A 端口改名 NEW，边仍指 A | 前端抛“该端口仍有连线”；PATCH 422，原合法路径GET仍1条 | 已有保护，保留并回归，不做自动重命名迁移 |
| 显式路径内边 pin 从 A 改到已声明 B | 结构校验与解析均接受新 pin | 操作会改物理声明，前端须指出被影响路径并要求重新声明/换边 |
| node.params.cable_loss_db=2 且一条边 cable_loss_db=2 | TopologyService.resolve_paths 总损耗=2 | 当前不计节点损耗；不引入节点损耗计算 |

另一个必须区分的现状：`mimo_ota/switch_orchestrator._build_probe_binding` 的 `cable_loss_db` 只取探头终端边，并非上述展示路径的逐边求和。本片不改变这份正式补偿契约，浏览器CE→cable→probe示例将2dB填在 `cable→probe`，`CE→cable` 为0；不能据路径/矩阵显示2dB声称任意上游段损耗已自动进入正式补偿。上游分段损耗与正式补偿关系不在本片重构，不以本片编辑功能解除实际校准/采用前置。

诊断启动时先 `from app.main import app`，再 import API/service，避免绕过正式加载顺序形成循环导入。文件 SQLite 的 engine 配置可用，裸 `sqlite:///:memory:` 直接加载默认 engine 因 `max_overflow` 不适用失败；隔离 HTTP 测试沿现有 StaticPool fixture，不修改生产数据库配置掩盖该诊断差异。

## 2. 全集关系：入口 → 权威 → 消费者 → 可观察断言

| 生产入口全集 | 权威判据/数据 | 消费者全集（本片相关） | 可观察断言 |
|---|---|---|---|
| 新增、双击属性、器件列表恢复、拖动 | draft.nodes/params/position；getNodePorts；目录只引用现有category | initialNodes、withDeclaredPorts、handleSave | 新线缆可声明A/B；旧位置未知参数不变；历史[]节点能打开同一抽屉、只在明确模式恢复 |
| 正常/校准模式选择、显示模式MultiSelect | operating_modes；connection_scope；getDraftModeConnectionIds 的旧标签回退 | initialNodes/initialEdges、routeCanvasConnections、TopologyService.get_mode_connections | 模式切换不丢草稿；校准器件恢复也不进入正常图/活动边；不把无关模式标签重写 |
| ReactFlow onConnect、边抽屉应用、边移除回调、删除连线按钮 | 声明ports；probe.params.rf_path_selection；完整边端点 | add/removeDraftConnections、新updateDraftConnection、保存、routeMatchesSaved | 端口不猜；影响显式路径时拒绝且给probe ID；数值编辑不冒充改接；dirty旧route不能采集 |
| 节点移除回调、删除器件按钮 | 所有关联边及所有存活probe声明 | removeDraftNodes、模式清理、保存 | 删除自身probe可连同自身声明删除；其他probe受影响则整次拒绝、草稿不变 |
| probe路径MultiSelect及应用；显式取消声明 | probePathDeclaration；resolve_saved_rf_path | route_calibration._route_selections、configuration_scope、route_batch_plan、switch_orchestrator、rf_execution_identity/执行冻结 | 换边先重声明再删旧边；取消显式声明须专门确认“恢复服务器唯一链解析”；不由编辑器自动清声明 |
| POST创建、PATCH合并、模板导入替换 | switch_topology._validate_structure；声明路径的有序边、所属probe和开关引用 | DB、GET、正常选路、校准scope/批清单/正式绑定 | 悬空声明全部422且未写库；历史GET仍可读；未声明旧图不新增路径资格限制 |
| 损耗编辑、路径/矩阵GET、采集及采用 | 原连线损耗；整条校准采用独立记录 | TopologyService.resolve_paths/get_end_to_end_loss/get_calibration_matrix；既有补偿/冻结链 | 同一线缆只在一条邻边计损耗，另一边0；节点不再计一份；不改正式补偿引擎 |
| 保存按钮、失败重试、reload、LabProfile切换 | 真实PATCH/GET；savingRef/collectionBusyRef/dirty、OperationalLab guard | 当前画布/route面板及下次页面加载 | 离线失败草稿还在；恢复后GET一致；采集中所有新旧编辑入口禁用；跨lab不丢草稿、不读错图 |

保存引用校验只验证结构，不检查驱动/绑定/端口能力，不将可编辑的中间草稿当作可执行路径。模式可执行性仍由现有消费者核验。不得把所有模式的边揉在一起送完整路径解析器，制造“其他模式分叉”误拒绝。

## 3. 文件边界与任务分解

仅两个独立任务：Task 1 可独立交付“不会再丢失编辑入口、看得懂双端线缆”；Task 2 可独立交付“重接/删除不留下损坏显式声明”，并完成整片真实浏览器矩阵。前者不依赖新的后端规则，后者复用前者恢复/标签入口。

生产文件均标“修”：`TopologyEditor.tsx`（入口、提示、统一错误展示）、`topologyDraft.ts`（纯草稿约束）、`nodePortHelpers.ts`（仅双端声明建议）、`CustomNodes.tsx`（端口可辨标签）、`app/api/switch_topology.py`（三个写入口共用结构校验）。`declared_rf_routes.py` 只消费现有函数，不预定修改；不动损耗算法、HAL、DB模型/迁移及生成契约。

测试文件：修改 `gui/test/topologyDraft.test.ts`、`gui/test/topologyEditing.browser.js`；新增 `api-service/tests/test_pc04a3_topology_recovery.py`、`api-service/tests/pc04a3_browser_fixture.py`、`gui/test/pc04a3TopologyRecovery.browser.js`。最终验证摘要写 `docs/validation/2026-10-25-pc04a3-topology-editing-recovery.md`。若最后无需修改某文件，从提交列表移除；禁止顺手重构。

### Task 1：恢复所有器件的编辑入口并明确双端线缆声明

**Files:** 修改上述四个 GUI 生产文件和 `gui/test/topologyDraft.test.ts`；浏览器断言加入 `gui/test/pc04a3TopologyRecovery.browser.js`（Task 2 接续完整运行）。

**Interfaces:**
- 保留 `updateDraftNode(draft: SwitchTopology,node: TopologyNode,declaredPorts?: string[]): SwitchTopology`，在实际应用显式模式声明时拒绝空、未知模式；校准scope仅允许 calibration。
- 在 `nodePortHelpers.ts` 增加 `suggestedPassivePorts(type: string): string[]`，只为 cable/receive_cable 返回 `['A','B']`，其他类型返回[]；是可修改的输入建议，不是 getNodePorts 默认能力，也不自动写入新增节点。
- 器件列表直接消费 `draft.nodes`，不依赖 initialNodes；选择后复用现有属性抽屉，设置 `portText=getNodePorts(node).join(', ')`。选择只查看，不自动改模式/草稿/仪器绑定。

- [ ] **Step 1：写失败测试。** 加入同一个 `topologyDraft.test.ts`，沿用其 fixture；并补校准恢复只允许 calibration、未知参数/位置不变的断言。

```ts
test('显式空显示模式不能应用，历史隐藏节点可以恢复到明确模式',()=>{
  const draft=fixture();
  assert.throws(()=>updateDraftNode(draft,{...draft.nodes[0],
    params:{...draft.nodes[0].params,visible_modes:[]}}),/显示模式/);
  draft.nodes[0].params.visible_modes=[]; // 历史读取保留，不偷偷迁移
  const next=updateDraftNode(draft,{...draft.nodes[0],
    params:{...draft.nodes[0].params,visible_modes:['mimo_ota']}});
  assert.deepEqual(next.nodes[0].params.visible_modes,['mimo_ota']);
  assert.deepEqual(next.nodes[0].params.unknown,{keep:1});
  assert.deepEqual(next.nodes[0].position,{x:12,y:34});
});
test('只对线缆给双端声明建议，不猜测仪器端口',()=>{
  assert.deepEqual(suggestedPassivePorts('cable'),['A','B']);
  assert.deepEqual(suggestedPassivePorts('receive_cable'),['A','B']);
  assert.deepEqual(suggestedPassivePorts('channel_emulator'),[]);
  assert.deepEqual(getNodePorts({...fixture().nodes[0],params:{ports:[]}}),[]);
});
```

同文件从 `nodePortHelpers` 增加建议函数 import。浏览器先写失败断言：`getByRole('textbox',{name:'器件列表',exact:true})` 必须存在，选择 params.visible_modes=[] 的普通/校准节点均能打开“器件属性”；空选择应用显示错误且节点未消失；恢复只发生在应用+保存之后。

- [ ] **Step 2：跑 RED。** cwd=`gui`：`npx --yes tsx --test test/topologyDraft.test.ts`。记录新增断言失败（函数未导出或未拒绝空模式），不是依赖安装/编译错误冒充功能RED；浏览器首次RED命令见Task 2启动段。
- [ ] **Step 3：最小实现。** 使用下面的约束形状，不自动补全用户空选择；抽屉保留错误后的用户输入。

```ts
// updateDraftNode，在返回新draft前；无visible_modes的历史语义保持。
const modes=node.params.visible_modes;
if(Array.isArray(modes) && (!modes.length || modes.some(mode=>
  !draft.operating_modes.some(item=>item.id===mode))))
  throw new Error('至少选择一个有效显示模式；可从器件列表恢复隐藏器件');
if(node.params.connection_scope==='calibration' && Array.isArray(modes) &&
  (modes.length!==1 || modes[0]!==CALIBRATION_MODE))
  throw new Error('校准器件只能显示在校准接线模式');
// nodePortHelpers：建议只进入表单草稿，仍需操作员核对并点击应用。
export function suggestedPassivePorts(type:string):string[] {
  return ['cable','receive_cable'].includes(type)?['A','B']:[];
}
```

`addNode` 的 params.ports 仍[]；仅设置新线缆 `portText` 为建议文本。属性提示明确“A/B是同一物理线缆两端，可按实际名称修改；画布左为连入、右为连出，同名左右接点是同一个物理端口，不是两根线”。在 `withDeclaredPorts` 的既有handle旁显示端口名称和连入/连出提示，保持基站dl/ul角色限制、同一handle ID及旧组件替换逻辑；不根据 in/out 字符串新增硬件方向规则。

Toolbar增加可搜索“器件列表”，选项全部来自draft.nodes，显示label+id+是否当前模式隐藏；`disabled={editingBlocked}`。选中隐藏器件打开同一Drawer。校准器件的MultiSelect继续禁用防止扩域；为历史[]/错误模式的校准器件在同一抽屉提供“恢复到校准接线模式”按钮，仅修改selectedNode的visible_modes为['calibration']，仍需点击应用；如果该模式不存在，提示先关闭抽屉点击已有“校准接线”创建，再从列表重开，不自动塞入正常模式。所有更新仍走changeDraft；不新建平行节点缓存。

边抽屉注明“线缆节点不另计损耗；同一物理线缆的损耗只填一条相邻连线，另一条保持0。整条实测校准在校准面板采用，不填此处”。不隐藏/覆盖历史边损耗，不对已有同值边武断去重；源码无法识别两条边是否同一物理线，靠明确归属和操作流程，不能按数值相等删除真实损耗。

- [ ] **Step 4：跑 GREEN 与相关回归。** cwd=`gui`：`npx --yes tsx --test test/topologyDraft.test.ts test/pc04a2RouteCalibration.test.ts test/topologyOperationalLabContext.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts`；`npm run build`。浏览器验证历史全隐藏恢复、普通/接收线缆建议可修改、画布标签、目录空端口不猜测。移除空模式约束做一次变异，核心断言应红；恢复后核对输入差异，不为此扩大测试平台。
- [ ] **Step 5：审查与提交。** 精确add实际修改的上述GUI文件及测试，`git diff --cached --check`，提交 `fix: 恢复隐藏拓扑器件并明确双端线缆声明`。记录结果版本、命令、退出码和统计；不把未跑浏览器写成已通过。

### Task 2：显式通路安全改接/删除与真实持久化验收

**Files:** 修改 `topologyDraft.ts`、`TopologyEditor.tsx`、`app/api/switch_topology.py`、`gui/test/topologyDraft.test.ts`、`gui/test/topologyEditing.browser.js`；新增上述后端测试/隔离fixture/浏览器脚本，完成验证摘要。

**Interfaces:**
- `updateDraftConnection(draft:SwitchTopology,connection:TopologyConnection):SwitchTopology` 在原模块替换当前边抽屉的直接map；数值参数修改允许，source/target/pin修改若被存活probe显式引用则拒绝，错误列明probe label/id及连接id。
- `removeDraftConnections`、`removeDraftNodes` 签名不变，删除前检查所有存活probe的声明；删除probe自身不受它自己的声明拦截，但不得破坏其他存活probe。整次操作先校验再生成新draft，任何拒绝均不部分清边/模式。
- 后端 `_validate_structure(nodes,connections,modes)` 签名不变，三个写入口共用；只对带 `rf_path_selection` 的probe检查声明内部结构与引用。复用 `resolve_saved_rf_path` 对“该声明列出的边集合”解释，不拿全模式混合边做分叉判断；运行模式、绑定及资格仍由原消费者判。

- [ ] **Step 1：先落失败用例。** 新建后端测试，复用现有隔离fixture，不启动真实硬件；下面代码可作为该文件开头及核心RED。

```python
import copy
import pytest
from tests.test_p1_57_topology_lab_context import client, setup_database, world, _mk_row

def explicit_graph():
    return dict(nodes=[
        dict(id='ce',type='ce_port',label='B1.1',params={'ports':['out']}),
        dict(id='c',type='cable',label='线缆',params={'ports':['A','B']}),
        dict(id='p',type='probe',label='探头',params={'ports':['in'],'probe_id':0,
             'polarization':'V','rf_path_selection':{'connection_ids':['a','b'],'switch_mappings':[]}})],
        connections=[dict(id='a',source='ce',source_pin='out',target='c',target_pin='A'),
                     dict(id='b',source='c',source_pin='B',target='p',target_pin='in')],
        operating_modes=[dict(id='mimo_ota',name='正常',active_connections=['a','b'])])

@pytest.mark.parametrize('remove_middle',[False,True])
def test_patch_rejects_dangling_explicit_path_atomically(world,remove_middle):
    row=_mk_row(world['db'],world['switch_id'],world['chamber_a'].id)
    before=explicit_graph()
    for key,value in before.items(): setattr(row,key,copy.deepcopy(value))
    world['db'].commit()
    changed=copy.deepcopy(before)
    changed['connections']=[] if remove_middle else changed['connections'][1:]
    changed['operating_modes'][0]['active_connections']=[] if remove_middle else ['b']
    if remove_middle: changed['nodes']=[n for n in changed['nodes'] if n['id']!='c']
    response=client.patch(f'/api/v1/switch-topologies/{row.id}',
        params={'lab_profile_id':str(world['lab_a'].id)},json=changed)
    assert response.status_code==422,response.text
    assert 'p' in str(response.json()['detail'])
    world['db'].refresh(row)
    assert {key:getattr(row,key) for key in before}==before
```

同文件按真实API补：POST坏声明422；模板替换坏声明422且旧行不变；仅PATCH名称仍验证合并后的坏声明且不写库；声明重复/未知边、乱序、目标非所属probe、失效switch_mappings分别422；有效原子换线200；删除probe及其声明200；历史坏图GET200；无显式声明的旧图/跨模式合法分支不被新规则误拒绝。不得给历史读接口加校验或补声明。

前端追加下面测试（从同模块 import 新update函数），以及“删自身probe允许、另一个probe受影响拒绝、端口集合改名仍拒绝”的正反例。

```ts
test('删除显式路径边或中间节点会指出受影响探头且不改原草稿',()=>{
  const draft=fixture();
  draft.nodes[2].type='probe';
  draft.nodes[2].params.rf_path_selection={connection_ids:['ab','bc'],switch_mappings:[]};
  const before=structuredClone(draft);
  assert.throws(()=>removeDraftConnections(draft,['ab']),/c/);
  assert.throws(()=>removeDraftNodes(draft,['b']),/c/);
  assert.deepEqual(draft,before);
  assert.throws(()=>updateDraftConnection(draft,{...draft.connections[0],target_pin:'out'}),/c/);
  assert.equal(updateDraftConnection(draft,{...draft.connections[0],cable_loss_db:2})
    .connections[0].cable_loss_db,2);
});
```

- [ ] **Step 2：跑 RED。** cwd=`api-service`：`USE_MOCK_INSTRUMENTS=true .venv/bin/python -m pytest tests/test_pc04a3_topology_recovery.py -q`；cwd=`gui`：`npx --yes tsx --test test/topologyDraft.test.ts`。预期基线悬空声明PATCH仍200，前端删除未抛错；记录真实结尾，不将导入错误算成功RED。
- [ ] **Step 3：最小实现后端保存引用检查。** `_validate_structure` 的已存在节点/连线索引之后加入以下形状；不要新增路径解析实现或要求所有尚未接线节点成为可执行图。

```python
from app.services.declared_rf_routes import resolve_saved_rf_path
for node in nodes:
    params=node.get('params') or {}
    if node.get('type')!='probe' or params.get('rf_path_selection') is None:
        continue
    declaration=params['rf_path_selection']
    try:
        ids=declaration.get('connection_ids') if isinstance(declaration,dict) else None
        if not isinstance(ids,list) or not ids or any(
                not isinstance(ident,str) or ident not in conn_index for ident in ids):
            raise ValueError('显式路径连接缺失或不存在')
        mappings=declaration.get('switch_mappings')
        if not isinstance(mappings,list) or any(not isinstance(item,dict) or
                not isinstance(item.get('node_id'),str) or
                not isinstance(item.get('path_name'),str) for item in mappings):
            raise ValueError('显式路径开关映射结构无效')
        selected=[conn_index[ident] for ident in ids]
        if selected[-1].get('target')!=node['id']:
            raise ValueError('显式路径终端不属于此探头')
        resolve_saved_rf_path(nodes,selected,ids[-1])
    except ValueError as exc:
        raise HTTPException(422,detail=f"探头 {node['id']} 的显式路径无效：{exc}") from exc
```

端口合法性仍交给原连接检查；缺失或null声明沿原消费者的“无显式声明”语义。保存只验证声明所选子图的形状，不验证实际开关/绑定、不看硬件状态。若现有真实fixture暴露不合法历史声明，只修fixture或通过明确原子编辑修复该图，不放松正式资格、不批量迁移历史。

- [ ] **Step 4：最小实现前端引用保护。** 在原模块内部检查 `draft.nodes.filter(type==='probe')` 的显式connection_ids；删除节点先算关联边，再仅对未删除probe检查。对边更新仅比较 `source/target/source_pin/target_pin`；误拒绝数值编辑不符合本计划。拒绝消息形如“探头 c（c）显式路径引用连线 ab，请先在探头属性重新声明路径”。`changeDraft` 改成先在try中计算next再setDraft，统一显示错误；禁止把可能throw的校验留在React state updater内部，导致事件层catch接不住。拖线、两种删除回调、删除按钮、边应用均走相同纯helper。

```ts
function assertUnreferencedConnections(draft:SwitchTopology,ids:string[],removedNodeIds:string[]=[]):void {
  const changed=new Set(ids),removed=new Set(removedNodeIds);
  const probes=draft.nodes.filter(node=>node.type==='probe'&&!removed.has(node.id)&&
    Array.isArray(node.params.rf_path_selection?.connection_ids)&&
    node.params.rf_path_selection.connection_ids.some((id:string)=>changed.has(id)));
  if(probes.length)throw new Error(`探头 ${probes.map(p=>`${p.label}（${p.id}）`).join('、')}`+
    ` 显式路径引用连线 ${ids.join('、')}，请先在探头属性重新声明路径`);
}
export function updateDraftConnection(draft:SwitchTopology,connection:TopologyConnection):SwitchTopology {
  const old=draft.connections.find(edge=>edge.id===connection.id);
  if(!old)throw new Error('连线已不存在，请重新选择');
  if(old.source!==connection.source || old.target!==connection.target ||
    (old.source_pin??'out')!==(connection.source_pin??'out') ||
    (old.target_pin??'in')!==(connection.target_pin??'in'))
    assertUnreferencedConnections(draft,[connection.id]);
  return {...draft,connections:draft.connections.map(edge=>edge.id===connection.id?{...connection}:edge)};
}
```

`removeDraftConnections` 在现有清理前调用该assert。`removeDraftNodes` 先在原draft上调用带removedNodeIds的assert，然后在剩余节点的draft上调用原边清理，避免第二次检查又把正在删除的probe算进去。`changeDraft` 返回boolean；只有true时才关闭删除/边编辑抽屉或显示成功，拒绝后旧画布、抽屉和输入保留。applyConnectionEdit不再额外setEdges制造与draft分叉的成功视图，交既有initialEdges effect更新。

保留现有probe路径MultiSelect：从已有显式声明变为无声明时，在应用前专门确认“取消显式RF路径声明后，将恢复服务器唯一链解析；这可能改变所选通路”，取消则不应用。其他编辑绝不自动delete rf_path_selection、不自动补switch_mappings、不自动挑另一条边；重新声明仍复用probePathDeclaration，最终资格仍由服务器核验。

操作员插线流程写在图内短提示，并在浏览器实跑：添加线缆→核对A/B并应用→拖两条新边→在probe属性按CE→探头选择替代完整路径→删除已不被引用的旧边→保存→重新选择服务器返回的新路径。旧边如已带校准值不复制给新边；旧链chain_id/route_digest失效时重新取服务器选择，不冒充沿用旧校准。改端口名采用“先加新端口、建替代边、重声明、删旧边、再删旧端口”，不自动迁移。

- [ ] **Step 5：真实API/临时SQLite/默认bootstrap全HAL Mock浏览器。** 新fixture仅允许 `USE_MOCK_INSTRUMENTS=true` 且数据库位于 `mktemp -d /tmp/pc04a3-XXXXXX` 返回目录；先加载app.main、Base.metadata.create_all、`run_bootstrap_on_startup(SessionLocal)`，断言返回true。使用默认seed后已有category/model/connection，测试库内把所有category.driver_mode设为mock，为两个新暗室各建LabProfile和拓扑（名PC04自动采集甲/乙），绑定快照引用该库实际选中型号/connection；不调用会重复插入同key类别的 configured.__wrapped__，不复用带pc06a1路径限制的fixture。输出数据库路径及两组lab/topology ID，并保留数据库。

浏览器脚本使用与页面同源的 `http://127.0.0.1:5187/api/v1`，现有 `topologyEditing.browser.js` 的硬编码18080改为这个同源地址，并在这个新数据库运行。脚本运行前检查 `/instruments/hal/status` 的mode为mock；默认bootstrap/HAL初始化日志必须保留，不能只用手工最小种子代替默认启动。测试数据可以通过真实API布置；历史visible_modes=[]可经真实PATCH保存来模拟，因为保存schema未禁止空显示模式。不响应拦截、不改window里的draft制造交互通过。

启动命令（仓库根；先确认8000和5187没有现有监听，冲突时不得停用户服务，改用测试专用Vite代理配置后记录实际端口）：

```bash
lsof -nP -iTCP:8000 -iTCP:5187 -sTCP:LISTEN
task_db_dir=$(mktemp -d /tmp/pc04a3-XXXXXX)
export DATABASE_URL="sqlite:///$task_db_dir/browser.sqlite"
export USE_MOCK_INSTRUMENTS=true
export BOOTSTRAP_ON_STARTUP=true
cd api-service
.venv/bin/python -m tests.pc04a3_browser_fixture
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另一个终端，cwd=`gui`：`npm run dev -- --host 127.0.0.1 --port 5187 --strictPort`。CLI前置 `command -v npx`；仓库根运行：

```bash
npx --yes --package @playwright/cli playwright-cli -s=pc04a3 open http://127.0.0.1:5187 --headed
npx --yes --package @playwright/cli playwright-cli -s=pc04a3 snapshot
npx --yes --package @playwright/cli playwright-cli -s=pc04a3 run-code "$(cat gui/test/pc04a3TopologyRecovery.browser.js)"
npx --yes --package @playwright/cli playwright-cli -s=pc04a3 run-code "$(cat gui/test/topologyEditing.browser.js)"
```

脚本沿既有 `async page=>{...}` 形式，等待DOM/真实response，禁止固定sleep等成功。节点/边操作复用旧脚本的真实鼠标、handle boundingBox与clickCurve；这是既有浏览器函数的扩展，不新建测试框架。至少写入下列真实断言：

```js
const response=await page.request.get(endpoint);
if(!response.ok())throw new Error(await response.text());
const saved=await response.json();
const cable=saved.nodes.find(n=>n.label==='PC04A3双端线缆');
if(JSON.stringify(cable?.params.ports)!=='["A","B"]')throw new Error('双端声明未真实保存');
const incident=saved.connections.filter(e=>e.source===cable.id||e.target===cable.id);
if(incident.length!==2 || incident.reduce((sum,e)=>sum+(e.cable_loss_db??0),0)!==2)
  throw new Error('该物理线缆的标称损耗未保持单一归属');
```

完整浏览器矩阵必须覆盖：14类逐类新增、名称/端口应用、拖动、至少一次真实接线、pin修改/拒绝、无引用删除、保存GET/reload；5类导入节点逐类属性、端口、拖线/改接、删除、保存reload（不要求不存在的新增菜单）。额外正反例：普通/校准历史全隐藏恢复；清空模式拒绝；校准正常模式隔离；被引用删边/删节点/改pin明确拒绝且草稿未变；上述插线及改名替代流程；物理线缆总标称2dB而非4dB；节点未知参数/旧位置保留；无关模式集合不变。

再跑离线保存失败保留草稿→恢复网络重试→真实GET→reload；dirty切lab拒绝；清洁切到乙读乙图不带甲草稿；实际全Mock采集开始时检查新器件列表、添加、属性/连线、模式、保存全部禁用，结束后可再编辑。采集状态检查复用 `pc04a2RouteCalibration.browser.js` 的开始pending窗口与真实服务，不延迟/伪造响应；模拟结果仍无正式值且不能采用。截图、network/console、结果JSON放 `output/playwright/pc04a3/`，摘要逐行记矩阵实际通过/未通过，不以总数代替。

- [ ] **Step 6：GREEN、同根回归与最终全量。** cwd=`api-service`：

```bash
USE_MOCK_INSTRUMENTS=true .venv/bin/python -m pytest tests/test_pc04a3_topology_recovery.py tests/test_pc04a1_topology_editing.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_gui_contract.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_freeze.py tests/test_pc06a1_batch_plan.py -q
USE_MOCK_INSTRUMENTS=true .venv/bin/python -m pytest tests -q
```

cwd=`gui`：`npx --yes tsx --test test/topologyDraft.test.ts test/pc04a2RouteCalibration.test.ts test/topologyOperationalLabContext.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts`；`npm run build`。补纯 `TopologyService` 断言：CE→cable→probe两边2和0，总损耗/矩阵为2；节点任意未知loss字段不参与；calibrated_loss_db已有优先规则不变。此处不声称该总数自动用于正式补偿，正式补偿仍由既有route_compensation回归证明未受本片影响。

本任务核心变异两处：移除前端引用拒绝，前端具体失败场景应红；跳过保存端显式引用检查，真实PATCH原子拒绝用例应红。连同Task 1的空模式约束，共三处核心变异。变异恢复后确认输入与待审版本一致，再保存最终GREEN记录；不触碰或放松历史有效期/硬件资格。

- [ ] **Step 7：独立任务审查与提交。** 精确add本任务实际文件及验证摘要，`git diff --cached --check`，提交 `fix: 保持拓扑显式通路编辑与保存引用完整`。验证摘要含基准SHA、工作区输入/依赖、命令全文、退出码、结尾统计、变异、浏览器矩阵和证据路径、耗时及复跑原因；累计独立内审后交主代理开Ready PR，外审按AGENTS执行。任何未通过项明示，不抢先勾上位PC条目。

## 4. 计划自审与待核边界

- [x] 覆盖总计划PC-04A-3全部条目：全器件矩阵、全隐藏恢复、线缆物理端口/画布方向、引用改接删除、损耗单一归属、真实API/浏览器/隔离/冻结编辑。
- [x] TDD每任务给出文件、接口、RED命令、核心代码/断言、GREEN命令与提交边界；任务2覆盖三个后端写入口，不改历史读取。
- [x] 最小修法：空模式收窄；已有属性入口换为完整draft.nodes来源；编辑引用收窄；保存换用现有解析器。仅器件列表是必要新入口，因为拒绝新空值无法恢复已有全隐藏节点，其他三种修法不能提供历史编辑入口。
- [x] 已连端口改名和损耗机制不重复重建；没有发现静默自动换路，不把推测写成已发生错误执行；没有把Mock结果或计划当成现场/正式验收。
- [x] 本计划基线命令只用于定位，未跑功能实现后的build、完整浏览器或全后端；这些均由执行者按任务记录。

实施时仍需软件交互核验而非猜测：19种节点逐类渲染后的handle/标签重叠及拖线可达性；默认bootstrap后的目录与新隔离lab绑定；全隐藏校准节点缺calibration模式时恢复的明确按钮流程；真实全Mock采集pending窗口内新增入口是否确实禁用。它们已有对应任务/断言，不是留给实现者另定方案的范围缺口；若暴露必须重构硬件/补偿链的问题则停止扩域并报告。
