# PC-04A-5a 拓扑库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（仅用户授权时）或 superpowers:executing-plans，逐任务执行。步骤以复选框跟踪。

**Goal:** 让操作员能复制已保存拓扑、命名、选回原图并记住编辑器默认图，而不切换执行图、不复制旧采用记录或内嵌测量值。

**Architecture:** 服务端从 SwitchTopology 原始 JSON 复制 inactive 副本；GUI 保持同 Lab/category 库和独立浏览器偏好。名称更新不影响执行选图的 updated_at；模板导入只追加非活跃图，禁止已有库覆盖。

**Tech Stack:** 现有 FastAPI/Pydantic/SQLAlchemy、React/Mantine/ReactFlow、node:test、pytest；不新增依赖或数据库表。

**Spec:** [总体设计](../design/2026-10-27-topology-library-pa-recovery.md)。状态：**用户已明确授权审清两风险后按流程实施、不改原CAICT配置；待独立增量审查门确认**。该门通过即串行执行，无需重复索取同一授权。

## Global Constraints

- WIP=1，仅5a，不执行5b修订/5c用户库改接/5d综合验收，不重做4a–4e。
- 复制直接读ORM原始图；仅副本已有 calibrated_loss_db/calibrated_phase_deg 置null，缺键仍缺键；其余原始JSON保形；源图及历史/confirmed不变。
- 副本 inactive、非default；偏好只按Lab/category存本浏览器；不改执行解析器/仪器绑定、不发硬件命令、未知不补0。
- 不复制旧采用/内嵌测量且inactive不自动执行，不承诺永久排除旧证书；未来显式激活时NULL topology_id旧证书兼容仍需执行绑定片审查。首次模板导入也是inactive草稿，5a不提供激活按钮。
- 名称trim后1–200字符、禁控制字符，允许重名但显示短ID；name-only PATCH不得改updated_at。
- dirty/busy阻断上下文及库写操作；错误保留输入；迟到响应不能覆盖新作用域；超时写操作不自动重试。
- 新SQLite隔离必须早于app导入；bootstrap后所有类别和Lab binding显式mock并核对。不读写用户DB，不停止用户服务。
- 本片新增后端共享写行为，最终后端全量由唯一执行者跑；中间任务只定点/累计，不为审查身份重复全量。

## 0. 开工、文件边界与安全环境

- [ ] 读AGENTS、CLAUDE、roadmap、设计；运行skillctl resolve并读取当前PROJECT/handoff。执行者认领，编制代理不释放主claim。确认用户最新授权、独立增量审查结论和HEAD；审查门未通过停止生产改动，不重复询问同一授权。
- [ ] 运行设计第2节三条全集检索，记录新增命中及消费关系。核对所有计划路径存在；以下Create文件为本片新文件，不把计划函数当成已存在。

| 单元 | 文件职责 |
|---|---|
| API契约与copy | 修改 `api-service/app/api/switch_topology.py`、`app/schemas/switch_topology.py`；现有copy/import/name规则在此，不另造通用topologies服务 |
| 四镜像 | `api/openapi.yaml`、`gui/src/api/switchTopologyService.ts`、生成 `gui/src/types/api.generated.ts`、GUI文案；现有开发mock按CLAUDE新增端点同步，不让真实验证走mockServer |
| 库状态 | 新建 `gui/src/features/TopologyEditor/topologyLibraryState.ts`；只管纯选择/偏好键/请求身份判断 |
| 界面 | 修改 `gui/src/features/TopologyEditor/TopologyEditor.tsx`；保留现有Flow画布，外层增加库与命名操作 |
| 回归 | 新建 `api-service/tests/test_pc04a5a_topology_library.py`、`gui/test/topologyLibraryState.test.ts`；扩展既有scope/import测试的新语义 |
| 浏览器证据 | 新建 `api-service/tests/pc04a5a_browser_fixture.py`、`gui/vite.pc04a5a.config.ts`（专用代理，不改变默认vite配置）；验证摘要 `docs/validation/2026-10-27-pc04a5a-topology-library.md` |

- [ ] 每次pytest前用新目录（在api-service执行；不要复用已污染库）：

```bash
pc04a5a_test_dir=$(mktemp -d /tmp/pc04a5a-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a5a_test_dir/test.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_test_dir/logs" .venv/bin/python -m pytest tests/test_pc04a5a_topology_library.py -q
```

首次文件尚未创建时不以“找不到文件”冒充有效RED；每任务先写对应行为断言，再运行捕捉预期失败。

- [ ] **Task1生产实现前完成真实浏览器RED前置**：先执行Task3中fixture安全检查、ORM seed、隔离API/Vite启动与RED步骤。RED seed仅ORM建立原有多图，不调用尚不存在的copy API；记录基线SHA、浏览器多图无选择入口及真实copy请求404/405。随后回Task1实施；Task3只复用这份RED证据并做GREEN，不能在新实现上追认原始RED。专用测试fixture/代理配置是此前置的测试准备，不是生产功能实现。

## Task 1：原始图复制、命名与安全导入 API

**Files:** 修改API/schema及OpenAPI；新建上述后端测试；修改 `tests/test_switch_topology_chamber_binding.py`、`tests/test_p1_57_topology_lab_context.py` 中与模板覆盖/激活冲突的旧期望（保留跨Lab保护）。

**Interfaces:**

- 消费现有 `_resolve_scope(db, lab_profile_id)`、`_load_scoped_topology(db,id,chamber.id)`、`SwitchTopology`；不从GET响应反建。
- 产出 `SwitchTopologyCopy(BaseModel)`（name唯一字段、extra='forbid'）；`POST /{id}/copy`返回SwitchTopologyResponse、201。
- 既有PATCH增加name约束和name-only更新时间保留；模板追加强制inactive/非default、已有行replace返回409。

- [ ] 写fixture：参考 `test_switch_topology_chamber_binding.py` 的StaticPool/get_db覆盖；建立两暗室、两个Lab、两个category；另建共享暗室Lab。源用ORM写含opaque/缺键/null/字符串数字的旧图，并有两个活跃图且更新时间明确不相同。不得从用户库复制fixture。
- [ ] 写以下实际断言（fixture在本文件定义 `client,db,lab,source,other_active`；`source`含节点和模式，边id为e；JSON比较用序列化避免True==1掩盖类型）：

```python
import json
from copy import deepcopy
from uuid import UUID
from app.models.switch_topology import SwitchTopology
from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology

def test_copy_preserves_raw_except_calibration(client, db, lab, source):
    before = deepcopy([source.nodes, source.connections, source.operating_modes])
    selected = orchestrate_switch_topology(db, lab.chamber_config_id).topology_id
    response = client.post(f'/api/v1/switch-topologies/{source.id}/copy',
        params={'lab_profile_id': str(lab.id)}, json={'name': '  接线副本  '})
    assert response.status_code == 201
    copied = db.get(SwitchTopology, UUID(response.json()['id']))
    assert str(copied.id) != str(source.id)
    assert copied.name == '接线副本'
    assert copied.is_active is False and copied.is_default is False
    expected = deepcopy(before)
    for edge in expected[1]:
        for key in ('calibrated_loss_db', 'calibrated_phase_deg'):
            if key in edge:
                edge[key] = None
    actual = [copied.nodes, copied.connections, copied.operating_modes]
    assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
    db.refresh(source)
    assert json.dumps([source.nodes, source.connections, source.operating_modes], sort_keys=True) == json.dumps(before, sort_keys=True)
    assert orchestrate_switch_topology(db, lab.chamber_config_id).topology_id == selected
```

fixture中的源图构造必须能被现有路径解析器读取，opaque和缺键放在不影响图结构的字段；不能以解析异常代替“执行选择未变”的断言。

- [ ] 增加name-only更改旧active图断言：保存原updated_at和当前解析ID，PATCH name后两者不变，图JSON不变；空白、null、201字符、控制字符422且行不变；重复名成功并不同UUID；跨暗室copy409不新增，坏Lab422，源404，额外body字段422。副本无Application/Selection/证书新增；源证据行保持完全一致。
- [ ] 跑Task1测试捕捉RED：copy当前404/405、name-only更新时间变化、replace已有图当前会删除、模板会写默认位；保存统计与版本，不以全部错误笼统充当RED。
- [ ] 最小实现算法：

```python
# copy端点内部；request为SwitchTopologyCopy
chamber = _resolve_scope(db, lab_profile_id)
source = _load_scoped_topology(db, topology_id, chamber.id)
graph = {key: deepcopy(getattr(source, key))
         for key in ('nodes', 'connections', 'operating_modes')}
for edge in graph['connections']:
    for key in ('calibrated_loss_db', 'calibrated_phase_deg'):
        if key in edge:
            edge[key] = None
copy = SwitchTopology(switch_category_id=source.switch_category_id,
    chamber_id=source.chamber_id, name=request.name,
    description=source.description, version=source.version,
    site_name=source.site_name, system_model=source.system_model,
    installed_date=source.installed_date, installed_by=source.installed_by,
    is_active=False, is_default=False, **graph)
copy.update_statistics()
db.add(copy)
db.flush()
# 返回模型可序列化校验必须在commit前；失败rollback并422，不提交半成品。
SwitchTopologyResponse.model_validate(copy).model_dump(mode='json')
db.commit()
db.refresh(copy)
return copy
```

字段校验捕获ValidationError转422；异常必须rollback。名称校验用 `unicodedata.category(char)=='Cc'`，不把可见Unicode字符错误禁掉；Create/Update/copy共用相同函数。PATCH恰好仅name时采用以下SQL表达式，使UPDATE的SET包含列自赋值；禁止Python旧datetime赋回（相同值可被忽略，强制旧值又可能回退并发时间）。其他PATCH仍沿原流程，不借本片改变description/状态等更新语义。不要通过临时置is_active绕过选图。

```python
# 在现有ORM赋值完成后、commit之前；update_data为本次实际字段
if set(update_data) == {'name'}:
    topology.updated_at = SwitchTopology.updated_at
# SQL: UPDATE switch_topologies SET name=?, updated_at=switch_topologies.updated_at ...
```

生产PATCH测试须用两active图重读时间与resolver ID，不能仅复用独立内存ORM实验；并发场景不得将已提交图保存的新时间回写为旧时间。

- [ ] 模板处理在生成/验证后、任何delete或默认位修改前核对已有行：replace且已有行返回409；无论replace参数，新增图inactive/非default并不清旧默认。源模板数据中的布尔值先显式覆盖，避免重复kwargs异常。此为保护原库的有意契约改变，同步OpenAPI描述/旧测试/GUI文案。
- [ ] GREEN运行本文件及scope、chamber binding、4a/4b/4c/4d相关保存与转换测试；同进程无新增硬件调用。记录通过/失败原文；失败按实际影响修，不盲改fixture。
- [ ] `git diff --check` 后只暂存本任务文件，提交 `feat: 增加保形拓扑副本和库元数据保护`。先规格审查再代码质量审查；独立计划增量审查门未通过不得执行本步。

## Task 2：库选择、默认偏好与异步交互

**Files:** 上述GUI三文件、GUI测试、OpenAPI生成类型；开发mock新增copy方法，真实验证保持禁用mockServer。

**Interfaces:** 新增 `copyTopology(id,labId,name):Promise<SwitchTopology>`；扩展 `getTopologies(labId,categoryId,skip=0,limit=100)`；新纯函数如下，组件不得复制另一套规则。

```typescript
export const preferenceKey = (lab: string, category: string) =>
  `meta3d.topology-editor.default.v1:${lab}:${category}`;
export const requestMatches = (a: {scope: string; generation: number},
  b: {scope: string; generation: number}) =>
  a.scope === b.scope && a.generation === b.generation;
export const canLeaveTopology = (dirty: boolean, busy: boolean) => !dirty && !busy;
// chooseTopology(items, preferredId): string | null
// preferred存在则用；否则唯一is_default；否则created_at倒序及id稳定排序；空数组null。
```

- [ ] 写node:test行为例：优先合法偏好、不存在偏好回退、重复名按ID选择、多个历史default稳定回退、空列表、dirty/busy四组合、旧generation拒绝。测试断言示例：

```typescript
assert.notEqual(preferenceKey('lab-a','switch'), preferenceKey('lab-b','switch'));
assert.equal(canLeaveTopology(true,false), false);
assert.equal(canLeaveTopology(false,true), false);
assert.equal(requestMatches({scope:'a',generation:1},{scope:'a',generation:2}), false);
```

- [ ] 在gui执行 `node --experimental-strip-types --test test/topologyLibraryState.test.ts`，确认函数缺失为RED；现有同目录测试也采用node:test，不捏造npm test脚本。
- [ ] 实现纯函数及API方法；库分页循环到累计items≥total，每页必须进展，否则报错误而非无限循环。收到全部列表才能判偏好失效。GET失败保留偏好，当前作用域不显示旧Lab图。
- [ ] 外层加入库Select、重命名Modal、复制Modal、“设为本浏览器默认编辑图”。所有选项标短ID/active状态；成功copy选择新inactive副本，但不自动设默认。新库选择传入Flow key=`lab/category/topologyId`并递增conversionEpoch；先通过dirty/busy guard再改key，防卸载丢草稿。
- [ ] 用同步ref整合flowDirty/flowBusy/libraryBusy；锁定切Lab/category/图、复制、命名、导入。请求捕获scope/generation/id，只在匹配时setState；取消/失败finally只释放自己持有的操作状态。保存中不能另存，采集未知结束状态不能解锁。
- [ ] 去掉列表effect中的自动import；旧“重导入默认拓扑”改显式“从模板新增副本”，不传replaceExisting=true。模板查询失败显示“模板加载失败”与重试，不当作模板为空。显式导入也受同一锁与迟到响应规则保护。
- [ ] 编辑器默认写localStorage try/catch；成功才通知保存，失败只保留当次选择。无效UUID/过期偏好仅在列表成功且全集已知后清除并通知。旧is_default只作读取回退，不PATCH它。
- [ ] `npm run openapi:generate`、`node --experimental-strip-types --test test/topologyLibraryState.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/topologyOperationalLabContext.test.ts`、`npm run build`；记录GREEN统计。
- [ ] 提交 `feat: 增加作用域拓扑库与独立编辑器默认选择`；规格/质量两阶段审查，重点看真实组件是否消费guard，而非只测纯函数。

## Task 3：真实API浏览器与最终累计验收

**Files:** fixture、专用Vite配置、验证摘要。后端全量只在本任务稳定版本运行一次。

- [ ] 新fixture参考 `tests/pc04a3_browser_fixture.py`，但不得导入执行旧seed。app导入前检查下面条件；随后默认bootstrap、设置全类别driver_mode='mock'、Lab所有instrument_bindings driver_mode='mock'并提交后重读核验。仅新夹具允许文档网段地址。

```python
import os, re
from pathlib import Path
url = os.environ.get('DATABASE_URL', '')
path = Path(url.removeprefix('sqlite:///'))
assert re.fullmatch(r'sqlite:////tmp/pc04a5a-[A-Za-z0-9]+/browser.sqlite', url)
assert path.parent.is_dir() and not path.exists()
assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'
# 只有以上通过后才能导入app/main、database、bootstrap。
```

- [ ] 构造两个暗室、共享暗室的第二Lab、两个category；每范围多图、至少101图（超过实际page size=100）验证分页、两旧active图、原始缺键和旧数值字符串图。RED初始化只用ORM seed原有多图，不依赖copy API；GREEN才通过真实copy API产生inactive副本。manifest写stdout，包含数据库绝对路径、Lab/category/topology UUID与Mock核验，不输出凭据。
- [ ] 专用 `gui/vite.pc04a5a.config.ts` 用mergeConfig导入原配置并只覆写 `/api` 与 `/api/v1/ws` 到127.0.0.1:18105；不用用户8000。启动前检查端口空闲，占用则停止并选未占端口同步配置，不杀用户进程。命令：

```bash
# api-service目录；首次创建并seed，不复用目录
pc04a5a_browser_dir=$(mktemp -d /tmp/pc04a5a-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a5a_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_browser_dir/logs" .venv/bin/python -m tests.pc04a5a_browser_fixture
env DATABASE_URL="sqlite:///$pc04a5a_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_browser_dir/logs" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18105
# gui目录，单独终端
npm run dev -- --config vite.pc04a5a.config.ts --host 127.0.0.1 --port 15105 --strictPort
```

- [ ] **本项在Task1实现前执行**：捕捉真实API/浏览器RED，多图无选择入口、无法选回非首图；对API的copy请求404/405。使用当轮可用浏览器技能、连隔离端口，保留真实请求，不用拦截伪造成功响应。进入Task3时只核验此前基线证据，不在已实现版本重复宣称RED。UI竞态故障可用浏览器网络节流/断网，记录手法。
- [ ] GREEN逐项：选原图→改名→复制→确认两个旧校准字段不继承→选择副本→设浏览器默认→重载→回原图；API重读确认原图JSON不变、source解析ID不变。共享暗室不同Lab偏好独立，跨category偏好不串；第101张可选且实际发生第二页请求；不存在偏好正常提示；网络失败不自动导入。空库首次模板导入明确显示inactive库草稿，未改变正式执行选择，不出现“已用于正式测试”成功文案。
- [ ] 浏览器改一节点为dirty后切Lab/category/图/复制均阻断；保存中双击不二次copy；采集锁保持；切换时迟到GET不回滚新作用域；断网保存失败保留草稿；写超时提示核查，不自动重试。验证过程不得触发真实仪器连接，Mock读数不作为正式实测。
- [ ] 原有图保存/转换/校准资格和冻结定点回归，至少包括 `test_pc04a2_route_selection.py`、`test_pc04a2_route_eligibility.py`、`test_pc04a2_route_application.py`、`test_pc04a2_route_freeze.py`、`test_pc04a4d_conversion.py`、`test_pc04a4d_loss_truth.py`。旧confirmed、证书、历史执行内容保持原始快照，不重算历史。
- [ ] 稳定HEAD由本片指定执行者执行唯一最终全量（api-service）：

```bash
pc04a5a_full_dir=$(mktemp -d /tmp/pc04a5a-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a5a_full_dir/full.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_full_dir/logs" .venv/bin/python -m pytest tests -q
```

- [ ] 写验证摘要：SHA、每条命令/退出码/结尾统计、真实API保存重读、截图路径、Mock范围、未验项。已知历史失败也照实列，不称全绿。最终GUI build结果附同一版本；后续共享契约修改使全量失效，按CLAUDE补跑，不凭审查次数重跑。
- [ ] 自查源码/四镜像/默认文案，运行 `git diff --check`；提交 `test: 验证拓扑库保护与选择链路`。按AGENTS规格/质量/累计审查，后续PR授权下Ready、R1/R2；本编制任务不push、不建PR、不建automation。

## 交接与覆盖自查

| 设计要求 | 执行任务 |
|---|---|
| 原始JSON、校准字段例外、名称、原图保留 | Task1 API/数据库断言 + Task3真实重读 |
| 默认不等于执行、复制inactive、改名排序不变 | Task1解析ID断言 + Task2偏好 + Task3累计 |
| Lab/category全集分页、同名、错误、迟到、dirty/busy | Task2状态/真实组件 + Task3浏览器 |
| 非破坏导入、未新增删除、历史与confirmed不变 | Task1导入/历史断言 + Task3回归 |
| 后续恢复与PA改接 | 仅设计接口边界；本片无实现任务，防止越界 |

编制阶段只进行文档自查，不称独立代码内审，不声称测试已跑。用户已授权按流程实施；独立计划增量审查确认两风险处理后按主代理既定串行SDD执行，不重复索取授权，不改原CAICT配置，不提前进入5b/5c。
