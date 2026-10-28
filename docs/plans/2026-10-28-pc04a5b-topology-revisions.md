# PC-04A-5b 拓扑持久修订与显式恢复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（本片用户已授权串行任务及独立审查）或 superpowers:executing-plans，逐任务执行。步骤以复选框跟踪；本计划编制者不派工、不实施。

**Goal:** 阻止旧客户端草稿静默覆盖新保存图，并让误保存可通过不可变历史显式恢复为新修订。

**Architecture:** `SwitchTopology.revision` 是独立整数CAS令牌；原始列快照与当前图在同一事务落库。所有同暗室拓扑写入口先取得事务锁，再对目标和默认让位图逐行CAS；历史预览只读，恢复只重放可恢复声明、不重放资格。GUI保留当前编辑器、5a库选择及采集互斥，409不丢草稿、超时不自动重试。

**Tech Stack:** 现有 FastAPI / Pydantic v2 / SQLAlchemy / Alembic（生产PostgreSQL、隔离测试SQLite）、React / Mantine / ReactFlow、node:test / pytest；无新增运行依赖。

**Spec:** [已批准细化设计](../design/2026-10-28-pc04a5b-topology-revisions.md)。2026-10-28用户已确认完整契约，含缺 `expected_revision` 的旧写请求422、过期409；同暗室事务锁及只读元信息的实施澄清经主任务接受并记decision0010，不改变已批准语义。

**状态：** 计划待独立审查，尚无5b功能或验证完成声明。基线5a PR545已合并至 `ce4bec1140d34fff7c029dfa04e38a71de5aad63`；额度例外仅5b，5c/5d不启动，原自动化保持PAUSED。保护原CAICT、用户数据库、用户服务、worktree、venv、DB、output和scratch，不清理现场。

## 0. 执行前置、已核边界与接口约定

- [ ] 运行 `python3 /Users/simon/Tools/Skills_Pool/skillctl.py work resolve --json`，读PROJECT/handoff、AGENTS审查规则、CLAUDE当前流程及批准设计；由主任务维护claim，子任务不释放主claim。先通过独立计划审查，再按Task1→4串行实施；每任务规格/质量审查，整片累计审查。
- [ ] 查memory索引核对保存/资格边界；NotebookLM明确不适用：本片不改HAL、SCPI、仪器返回量纲或仪器能力结论。若实施中触及它们，停止该扩展并报告，不猜命令。
- [ ] 复核真实写入口，不把通用 `topologies` / `instrument_topology_profiles` 当作本对象：

```bash
rg -n 'SwitchTopology|switch_topologies' api-service/app
rg -n 'commit|\.update\(|\.delete\(|_commit_conversion' api-service/app/api/switch_topology.py api-service/app/api/chamber.py
rg -n 'updateTopology|topologyUpdatePayload|previewConversion' gui/src gui/test
rg -n 'switch-topologies|update_switch_topology|SwitchTopologyUpdate' api-service/tests
rg -n '绝不|不许|禁止|must not|别把' api-service/app/api/switch_topology.py api-service/app/api/chamber.py gui/src/features/TopologyEditor/TopologyEditor.tsx
```

| 生产入口 | 权威判据 / 写方 | 正式消费方 | 本片可观察断言 |
|---|---|---|---|
| create、copy、import | `api-service/app/api/switch_topology.py` 三函数 | 当前图GET、执行选图 | 新图r1及快照同事务；copy/import仍inactive、非default |
| 普通PATCH、name-only | 同文件 `update_switch_topology` | `mimo_ota/switch_orchestrator.py`、`rf_chain_resolver.py` | SQL CAS；改名更新时间不动，正式选图ID不变 |
| conversion PATCH | `_conversion_snapshot/_commit_conversion` | 当前图、loss truth | revision + 原有source_digest/raw文本CAS同时成立 |
| create/PATCH is_default | 两处bulk update（须替换） | 同scope其它默认图 | 让位图也推进修订、快照；无peer并发create也最多一个default |
| topology DELETE | `_assert_deletable`及FK | 历史图、采用/证书 | 有修订409；保留原引用保护 |
| chamber bulk DELETE | `api-service/app/api/chamber.py::delete_chamber` | 拓扑/探头/暗室 | 新修订保护在任何bulk删除前；整个事务零副作用 |
| restore（新增） | 服务器历史行 + 当前保存门 + CAS | route_calibration / freeze / configuration_scope / topology_loss | 不创建资格、历史不改、当前与冻结两端沿原身份门 |
| 编辑器保存、改名、转换 | `gui/src/api/switchTopologyService.ts` 三个活调用 | 当前draft及已保存图 | 使用保存成功时的整数令牌，不自动重放过期内容 |

静态迁移图核查（非文件名排序）得到当前唯一head `e19d87fa4269`，文件 `api-service/alembic/versions/e19d87fa4269_add_immutable_route_adoption_and_.py`。执行前仍须在隔离环境运行 `alembic heads` 验证；若变化，重新确定真实父迁移，不能制造双head。`alembic/env.py` 遍历models目录；运行时 `app/models/__init__.py` 仍需显式注册新模型。

### 0.1 新增/修改文件及职责

| Task | 文件 |
|---|---|
| 1 | 修改 `api-service/app/models/switch_topology.py`、`app/models/__init__.py`、`app/schemas/switch_topology.py`、`app/schemas/topology_conversion.py`（转换预览revision）、`app/api/switch_topology.py`、`app/api/chamber.py`、`gui/src/features/TopologyEditor/TopologyEditor.tsx`（保存/改名/转换三个活写调用）；新增 `app/models/switch_topology_revision.py`、`app/services/topology_revisions.py`、`alembic/versions/f28a91c7d6b3_switch_topology_revisions.py`、`tests/test_pc04a5b_topology_revisions.py`、`tests/test_pc04a5b_revision_migration.py` |
| 1/2 | 四镜像：`api/openapi.yaml`、`gui/src/types/api.generated.ts`、`gui/src/api/switchTopologyService.ts`、`gui/src/api/mockServer.ts`；原Pydantic schema与真实路由同步 |
| 2 | 新增 `api-service/tests/test_pc04a5b_topology_restore.py`；在Task1 service/schema/API扩展历史与恢复，不创建第二套校验器 |
| 3 | 修改 `gui/src/features/TopologyEditor/TopologyEditor.tsx`、`LegacyConversionPanel.tsx`；新增 `TopologyHistoryPanel.tsx`、`topologyRevisionState.ts`、`gui/test/topologyRevisionState.test.ts`；更新受令牌影响的现有GUI测试 |
| 4 | 新增 `api-service/tests/pc04a5b_browser_fixture.py`、`pc04a5b_browser_audit.py`、`gui/vite.pc04a5b.config.ts`、`gui/test/pc04a5bRevisions.browser.js`、`docs/validation/2026-10-28-pc04a5b-topology-revisions.md`；完成本计划复选框与roadmap状态 |

Task1也允许迁移检索命中的旧测试HTTP请求：每次正常PATCH前GET最新revision并显式提交；保留原语义断言、跨scope/无效输入断言，不改历史规则门、不将状态码宽化成集合、不给缺令牌反例自动补值。`gui/src/api/service.ts`及`TopologyProfileEditor`只命中名字相近对象，没有该写路由，不扩展。

### 0.2 隔离命令（所有Python应用导入之前）

每个执行者使用新临时目录，下面命令从 `api-service` 运行。不得复用5a库或默认 `.env` 的数据库。进程、日志和DB路径写入本片证据；不删除生成目录。

```bash
pc04a5b_run_dir=$(mktemp -d /tmp/pc04a5b-XXXXXX)
export DATABASE_URL="sqlite:///$pc04a5b_run_dir/test.sqlite"
export USE_MOCK_INSTRUMENTS=true
export BOOTSTRAP_ON_STARTUP=true
export LOG_DIR="$pc04a5b_run_dir/logs"
.venv/bin/python -m alembic heads
```

期望迁移前输出唯一 `e19d87fa4269 (head)`；这里只列计划命令，编制阶段未执行。旧conftest只setdefault Mock并覆盖日志目录，不替执行者设置数据库，不能省略外层环境。真实浏览器库bootstrap后再次逐类别和所有Lab binding设为Mock并重新查询断言；Mock声明只能证明软件行为。

### 0.3 对外契约（API路径均带 `/api/v1`）

| 操作 | 参数 / body | 成功响应 / 拒绝 |
|---|---|---|
| GET list/detail | 保留 `lab_profile_id`、列表skip/limit/category | 原模型新增必填整数 `revision`，旧行0；只读不补历史 |
| POST create | 保留现有body，lab在body；不接收revision作状态 | 201，r1/create |
| POST copy | 原 `{name}`，query lab | 201，独立新UUID r1/copy，无源历史复制 |
| POST import/from-template | 原switch_category_id/lab_profile_id/template_id/chamber_id/replace_existing query | 200，r1/import；已有库覆盖仍409 |
| PATCH 普通/名称 | 原字段加必填 `expected_revision: StrictInt >= 0` | 200新revision；合法no-op仍原revision；过期即使no-op也409 |
| PATCH 转换 | 恰为 `{expected_revision, conversion:{source_digest,changes}}` | 200；不能混name/graph/null；digest/raw CAS不取消 |
| GET revisions | query lab、skip≥0默认0、limit 1..100默认50 | `{total,items}`，revision降序，空旧图total0 |
| GET revisions/{revision} | query lab，path非负整数 | 单个历史raw快照；本图缺revision404、scope沿现有拒绝 |
| POST restore-preview | query lab，body `{revision,expected_revision}` 严格非负整数 | 当前令牌、目标snapshot、清理后的candidate、逐字段差异、警告；零写 |
| POST restore | 同preview请求；禁止客户端candidate | 200当前详情，新revision、operation=restore、restored_from_revision；相同内容也新增 |

缺令牌、bool、浮点、字符串、null、负数→422；合法旧令牌→409。create/copy/import没有“现存目标revision”要求。新历史API额外字段禁止；PATCH令牌要在 `model_dump` 后pop，不能setattr成ORM字段。`SwitchTopologyResponse.revision` 无默认伪值，模型列为 `default=0,server_default='0'`；新建显式revision=1并flush后才做响应验证，防未flush ORM列默认仍为None导致500。

## Task 1：持久化、全部写入口事务、四镜像与旧调用迁移

**目标：** 只要一次写对外成功，当前图和对应不可变快照就同时存在；失败、冲突和无效请求不留baseline、不改peer默认位。

- [ ] **Step 1（RED）：新增真实路由测试，复用5a已存在隔离夹具。** `tests/test_pc04a5b_topology_revisions.py` 直接导入5a命名fixtures，不运行5a服务：

```python
from copy import deepcopy
import pytest
from sqlalchemy import select
from app.models.switch_topology import SwitchTopology
from tests.test_pc04a5a_topology_library import db, client, world, lab, source, other_active, ROOT, raw

def patch(client, lab, source, body):
    return client.patch(f'{ROOT}/{source.id}', params={'lab_profile_id':str(lab.id)}, json=body)

def rows(db, source):
    from app.models.switch_topology_revision import SwitchTopologyRevision
    db.expire_all()
    return db.scalars(select(SwitchTopologyRevision).where(
        SwitchTopologyRevision.topology_id==source.id).order_by(SwitchTopologyRevision.revision)).all()

def test_old_row_first_write_and_stale_noop(client, db, lab, source):
    before=deepcopy(source.connections)
    assert client.get(f'{ROOT}/{source.id}',params={'lab_profile_id':str(lab.id)}).json()['revision']==0
    saved=patch(client,lab,source,{'name':'修订一','expected_revision':0})
    assert saved.status_code==200, saved.text
    assert saved.json()['revision']==1
    history=rows(db,source)
    assert [(x.revision,x.operation) for x in history]==[(0,'baseline'),(1,'update')]
    assert raw(history[0].snapshot['connections'])==raw(before)
    assert patch(client,lab,source,{'name':'修订一','expected_revision':0}).status_code==409
    assert patch(client,lab,source,{'name':'修订一','expected_revision':1}).json()['revision']==1
    assert len(rows(db,source))==2

@pytest.mark.parametrize('token',[None,True,False,-1,1.0,'0'])
def test_invalid_tokens_rejected(client,db,lab,source,token):
    assert patch(client,lab,source,{'name':'不得写','expected_revision':token}).status_code==422
    assert rows(db,source)==[]

def test_missing_token_rejected(client,db,lab,source):
    assert patch(client,lab,source,{'name':'旧客户端'}).status_code==422
    db.refresh(source)
    assert source.name=='原图'
    assert rows(db,source)==[]
```

- [ ] **Step 2：只跑上述定点RED。** `.venv/bin/python -m pytest tests/test_pc04a5b_topology_revisions.py -q`；预期缺revision字段或新模型失败，不是环境/默认库连接失败。保存实际输出及SHA，不预写通过计数。
- [ ] **Step 3：模型和迁移。** 新模型如下（该段为完整新模型）；`switch_topology.py` 加revision列，`models/__init__.py` 导入新类。

```python
import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.database import Base
from app.models.switch_topology import _JSON_PG_OR_SQLITE

class SwitchTopologyRevision(Base):
    __tablename__='switch_topology_revisions'
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    topology_id=Column(UUID(as_uuid=True),ForeignKey('switch_topologies.id',ondelete='RESTRICT'),nullable=False)
    revision=Column(Integer,nullable=False)
    operation=Column(String(20),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    restored_from_revision=Column(Integer,nullable=True)
    snapshot=Column(_JSON_PG_OR_SQLITE,nullable=False)
    recorded_metadata=Column(_JSON_PG_OR_SQLITE,nullable=False)
    __table_args__=(UniqueConstraint('topology_id','revision',name='uq_switch_topology_revision'),)
```

```python
# app/models/switch_topology.py 的 SwitchTopology
revision=Column(Integer,nullable=False,default=0,server_default='0')
```

迁移文件 `revision='f28a91c7d6b3'`、`down_revision='e19d87fa4269'`；使用现有 `column_exists/table_exists` 做逐操作guard，适配baseline先create_all。upgrade仅加非空server_default0整数列、新表及唯一约束；表列与上面模型一致，UUID用 `sa.UUID()`，JSON用 `sa.JSON().with_variant(postgresql.JSONB(),'postgresql')`，FK RESTRICT。不扫描图、不修JSON、不生成历史。downgrade只针对本迁移表/列且仅测试库验证，禁止在用户库尝试。

```python
def upgrade():
    if not column_exists('switch_topologies','revision'):
        op.add_column('switch_topologies',sa.Column('revision',sa.Integer(),nullable=False,server_default='0'))
    if not table_exists('switch_topology_revisions'):
        op.create_table('switch_topology_revisions',
            sa.Column('id',sa.UUID(),primary_key=True),
            sa.Column('topology_id',sa.UUID(),sa.ForeignKey('switch_topologies.id',ondelete='RESTRICT'),nullable=False),
            sa.Column('revision',sa.Integer(),nullable=False),
            sa.Column('operation',sa.String(20),nullable=False),
            sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
            sa.Column('restored_from_revision',sa.Integer(),nullable=True),
            sa.Column('snapshot',sa.JSON().with_variant(postgresql.JSONB(),'postgresql'),nullable=False),
            sa.Column('recorded_metadata',sa.JSON().with_variant(postgresql.JSONB(),'postgresql'),nullable=False),
            sa.UniqueConstraint('topology_id','revision',name='uq_switch_topology_revision'))

def downgrade():
    if table_exists('switch_topology_revisions'):
        op.drop_table('switch_topology_revisions')
    if column_exists('switch_topologies','revision'):
        op.drop_column('switch_topologies','revision')
```

迁移测试新建最小brownfield表（id、原三JSON列），放入含bool/数字/字符串/缺键/null/opaque图，Alembic `MigrationContext` + `Operations.context` 调用该upgrade，再用SQL比较原JSON文本完全相同、revision0、历史空；重复upgrade幂等。另用新SQLite运行 `alembic upgrade head`，确保fresh baseline不重复建表；FK测试显式开启SQLite `PRAGMA foreign_keys=ON`，直接SQL删除有历史图被拒绝。所有测试DB用tmp_path，不借用当前应用DB。

- [ ] **Step 4：新增单一修订service，先定义raw及锁边界。** `recorded_metadata`只存当时scope/UUID/状态/创建与更新时间，供预览说明，**不在restore白名单**；这是设计“并列展示当时信息”的只读实现，不改变可恢复范围。

```python
from copy import deepcopy
from datetime import date, datetime
import json
from sqlalchemy import select, update
from fastapi import HTTPException
from app.models.chamber import ChamberConfiguration
from app.models.switch_topology import SwitchTopology
from app.models.switch_topology_revision import SwitchTopologyRevision

RESTORABLE=('name','description','version','site_name','system_model','installed_date',
            'installed_by','nodes','connections','operating_modes')
RECORDED=('id','chamber_id','switch_category_id','created_at','updated_at','created_by','is_active','is_default')

def json_value(value):
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    return deepcopy(value)

def raw_snapshot(row):
    return {key:json_value(getattr(row,key)) for key in RESTORABLE}

def recorded_metadata(row):
    return {key:(str(getattr(row,key)) if key in ('id','chamber_id','switch_category_id')
                 and getattr(row,key) is not None else json_value(getattr(row,key))) for key in RECORDED}

def same_json(left,right):
    return json.dumps(left,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')) == json.dumps(
        right,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))

def lock_chamber(db,chamber_id):
    # PG锁一条稳定存在的暗室行；SQLite无FOR UPDATE，用无变化UPDATE取得事务写锁。
    if db.bind.dialect.name=='sqlite':
        result=db.execute(update(ChamberConfiguration).where(ChamberConfiguration.id==chamber_id).values(
            id=ChamberConfiguration.id,updated_at=ChamberConfiguration.updated_at).execution_options(synchronize_session=False))
        if result.rowcount!=1:
            raise HTTPException(404,detail='暗室不存在')
    else:
        row=db.execute(select(ChamberConfiguration.id).where(
            ChamberConfiguration.id==chamber_id).with_for_update()).one_or_none()
        if row is None:
            raise HTTPException(404,detail='暗室不存在')

def add_revision(db,row,operation,restored_from_revision=None):
    db.add(SwitchTopologyRevision(topology_id=row.id,revision=row.revision,operation=operation,
        restored_from_revision=restored_from_revision,snapshot=raw_snapshot(row),recorded_metadata=recorded_metadata(row)))

def assert_revision_deletable(db,topology_ids):
    if topology_ids and db.query(SwitchTopologyRevision.id).filter(
            SwitchTopologyRevision.topology_id.in_(topology_ids)).first() is not None:
        raise HTTPException(409,detail='拓扑已有不可变修订历史，不允许删除')
```

所有写和两个删除入口在目标/peer SELECT前调用lock_chamber；先由Lab解析chamber，锁后重取目标（`populate_existing`或expire），不能读旧identity map。锁粒度暂取暗室，避免引入lock表/散列碰撞/进程本地mutex。锁只串行化持久化，不能代表硬件空闲。SQLite读取scope后升级写锁遇BUSY/LOCKED按既有底层错误码409，必须回滚；其它DB错误原样失败并回滚。两个并发create同scope空peer时，后一个锁后重读必见前一个并对其让位；不同category虽然串行，但查询和CAS绝不越category。

- [ ] **Step 5：写入原语和原路由接入，保留原校验。** 在同service提供下面接口；函数不commit，唯一commit由API事务边界负责。候选 `values` 只含真实修改的ORM列，日期先解析为datetime；request令牌/connection_numeric_declarations/conversion不能落列。

```python
def cas_revision(db,row,expected_revision,values,*,operation='update',raw_conditions=(),
                 restored_from_revision=None,preserve_updated_at=False,force_revision=False):
    if row.revision!=expected_revision:
        raise HTTPException(409,detail='服务器拓扑已变化，请刷新核对；草稿未覆盖')
    changed=any(not same_json(json_value(getattr(row,key)),json_value(value)) for key,value in values.items())
    if not changed and not force_revision:
        return row
    before=raw_snapshot(row)
    before_meta=recorded_metadata(row)
    old_revision=row.revision
    writes=dict(values,revision=old_revision+1)
    if preserve_updated_at:
        writes['updated_at']=SwitchTopology.updated_at
    result=db.execute(update(SwitchTopology).where(SwitchTopology.id==row.id,
        SwitchTopology.chamber_id==row.chamber_id,
        SwitchTopology.switch_category_id==row.switch_category_id,
        SwitchTopology.revision==expected_revision,*raw_conditions).values(**writes)
        .execution_options(synchronize_session=False))
    if result.rowcount!=1:
        raise HTTPException(409,detail='服务器拓扑已变化，请刷新核对；草稿未覆盖')
    if old_revision==0:
        db.add(SwitchTopologyRevision(topology_id=row.id,revision=0,operation='baseline',
            snapshot=before,recorded_metadata=before_meta))
    db.refresh(row)
    add_revision(db,row,operation,restored_from_revision)
    return row
```

API `try`必须包住lock、候选构造、CAS、peer写、flush、响应校验、commit；`except Exception: db.rollback(); raise`只用于回滚重抛，不吞错、不泛化409。已有OperationalError仅精确SQLite BUSY/LOCKED映射409。

接入顺序明确为：

1. create：lock→原schema/nominal/structure/ports/internal_paths/loss_owner校验→构建 `revision=1` 新图→flush/统计/响应预校验→**仅 `request.is_default is True` 时**读取同chamber/category、`is_default IS TRUE`且 `id != 新图.id` 的peer→每个 `cas_revision(..., {'is_default':False})`→新图 `add_revision(...,'create')`→flush历史→序列化所有被写响应候选→commit。新图已flush，必须排除自身，不能自让位；非默认create不读写peer。peer任一个CAS/历史失败整个create回滚，不能沿用原bulk update。
2. copy：lock→同scope读source→原raw复制及已有校准两字段清null→新图显式r1/inactive/nondefault→flush→原响应校验→统计→add_revision(copy)→flush/响应预校验→commit。不复制source历史，源图revision不变。
3. import：lock→原模板校验和已有库覆盖409→显式r1/inactive/nondefault→flush/统计/响应预校验→add_revision(import)→flush→commit。失败不留新图。
4. PATCH：lock→新鲜目标→先核expected→从 `model_dump(exclude_unset=True)` pop expected和非列控制键→沿现有preserve与全部验证器构造候选（禁止typed GET重建raw）→算统计（临时对象，不挂Session）→**仅本次显式提交 `is_default=True` 且当前目标非默认（false→true）时**，对同chamber/category、`is_default IS TRUE`且 `id != 目标.id` 的peer逐行CAS让位→目标cas_revision→flush→`SwitchTopologyResponse.model_validate(row).model_dump(mode='json')`→commit。name-only、普通图保存、未提交default、显式false或已default仍true均不进入peer写路径，不改变peer的revision/default/updated_at。仅名称字段时 `preserve_updated_at=True`，即使还含expected也必须命中；同值chamber断言不当内容变更。
5. conversion：envelope允许且仅允许 `{'expected_revision','conversion'}`；`_commit_conversion`新增expected_revision参数。源快照同时取revision；沿原 `_conversion_candidate`、source_digest及三个cast(raw,Text)等式，用 `cas_revision(...,operation='conversion',raw_conditions=...)`；不把metadata放进既有digest造成兼容漂移。no-op转换仍检查digest/expected后返回原revision，不编造转换历史。
6. DELETE：lock→原 `_assert_deletable` + `assert_revision_deletable`→删除；chamber bulk DELETE锁同暗室、在删图/探头/暗室之前执行两个保护，RESTRICT是最后防线。竞争失败必须回滚探头和暗室；不能将新修订表cascade删除。

`is_active/is_default`实际变化也推进revision，即使可恢复snapshot同值；recorded_metadata展示状态变化。历史行没有update/delete API，没有自动清理，没有revision驱动的自动激活。

两个默认让位入口共用以下查询形状，调用条件分别如上；锁/CAS/回滚边界保持不变，不引入新机制：

```python
peers=db.query(SwitchTopology).filter(
    SwitchTopology.chamber_id==target.chamber_id,
    SwitchTopology.switch_category_id==target.switch_category_id,
    SwitchTopology.is_default.is_(True),
    SwitchTopology.id!=target.id,
).all()
for peer in peers:
    cas_revision(db,peer,peer.revision,{'is_default':False})
```

此处target为当前入口已加载/已flush的目标图。create条件为 `request.is_default is True`；PATCH条件为 `'is_default' in request.model_fields_set and request.is_default is True and not target.is_default`，使用锁后重读的旧状态、在目标CAS前判断，不用新candidate状态作判据。

- [ ] **Step 6：四镜像和三个活GUI写调用先迁移令牌。** Schema增加strict字段；OpenAPI请求required同步，响应revision必填，生成TS；服务手工类型中 `SwitchTopology.revision:number`，创建草稿测试补0但不拿0冒充已保存GET令牌。`TopologyUpdatePayload`排除只读revision/id/统计列，强制expected_revision；图保存helper返回 `expected_revision:draft.revision`，改名使用当前已保存topology.revision，转换用预览对应保存版本的整数令牌。转换preview响应增加revision并在同次源查询取值，避免预览后重新读令牌自动确认旧candidate。

```python
from typing import Annotated
from pydantic import Field
Revision=Annotated[int,Field(strict=True,ge=0)]
# SwitchTopologyUpdate 中新增，无默认值
expected_revision: Revision
# SwitchTopologyResponse 中新增，无默认值
revision: Revision
```

```ts
export type TopologyUpdatePayload = Partial<Pick<SwitchTopology,
  'name'|'description'|'version'|'site_name'|'system_model'|'installed_date'|'installed_by'|
  'is_active'|'is_default'|'nodes'|'connections'|'operating_modes'|'chamber_id'>> & {
  expected_revision: number;
  connection_numeric_declarations?: ConnectionNumericDeclarations;
  conversion?: {source_digest:string;changes:TopologyConversionRequest};
};
// topologyUpdatePayload 的现有返回对象增加 expected_revision:draft.revision。
// 改名调用：
await switchTopologyService.updateTopology(id,labProfileId,{name,expected_revision:topology.revision});
// 转换调用；TopologyConversionPreview 同步增加 revision:number：
await switchTopologyService.updateTopology(topology.id,labProfileId,{
  expected_revision:preview.revision,
  conversion:{source_digest:preview.source_digest,changes:preview.changes},
});
```

开发mock没有权威raw历史，新增PATCH拒绝处理器明确422“请连接真实API核验修订”；不生成200伪历史。新历史端点Task2增加拒绝处理器。`mockDatabase.ts`不添加虚构记录；现有Mock通路继续只作演示。

- [ ] **Step 7：补全集事务测试并GREEN。** 下列测试必须各自实际调用生产入口，不能只测helper：

| 测试函数（新revision测试文件） | 构造和断言 |
|---|---|
| `test_create_copy_import_record_revision_one` | 分别调用三入口，查询history恰一行r1正确operation；copy无baseline、不复制源历史；所有response可JSON序列化 |
| `test_snapshot_failure_rolls_back_target_and_default_peers` | SQLAlchemy事件仅在INSERT revision表时抛IntegrityError；create/PATCH default分别调用，断言原revision/name/default/updated_at及history计数全不变 |
| `test_two_sessions_same_revision_one_winner` | tmp_path文件SQLite两独立Session和连接，以Barrier同时PATCH同r0；恰一200一409，history恰0/1，无孤baseline；不要共享单Session跨线程 |
| `test_two_default_creates_empty_scope` | 空scope两连接同时POST default；可串行两201或其中明确409，成功后默认计数恰1；若两201则先图有让位修订 |
| `test_default_peer_scope_and_metadata` | 同暗室两category、另一暗室；本scope旧default r0→r1且metadata false，其它图原revision/default不变 |
| `test_name_does_not_change_execution_selection` | 复用5a source/other_active，取orchestrator前后ID及updated_at相同 |
| `test_boolean_to_number_is_not_noop` | opaque true改1（允许声明路径），JSON字面类型变化触发revision；缺键→null亦非no-op |
| `test_conversion_requires_both_tokens` | 使用真实conversion-preview；metadata写后revision过期但digest相同仍409；graph变更后digest错误仍409；混合body422 |
| `test_delete_and_chamber_delete_keep_history` | 先保存历史，再调用两删除路径，先解除Lab引用以真正走到chamber修订守门；409且图/探头/暗室/历史仍在 |
| `test_response_failure_precedes_commit` | source包含GET不可序列化图后copy/import/PATCH构造候选，422且新图/peer/history零改变；不利用返回500当成功 |

旧请求迁移用显式GET，不在全局TestClient自动注入（否则缺令牌反例会被掩盖）：

```python
detail=client.get(f'{ROOT}/{source.id}',params={'lab_profile_id':str(lab.id)})
assert detail.status_code==200
body={'name':'新名称','expected_revision':detail.json()['revision']}
response=client.patch(f'{ROOT}/{source.id}',params={'lab_profile_id':str(lab.id)},json=body)
assert response.status_code==200
```

迁移旧跨Lab请求时从正确Lab取目标令牌，再用错误Lab提交，保持原跨scope拒绝断言；畸形UUID原测试仍按原语义，无需发无效GET。旧直调 `SwitchTopologyUpdate` 和函数调用也要显式令牌。不得自动重试HTTP409；并发测试只发一次。

```bash
.venv/bin/python -m pytest tests/test_pc04a5b_topology_revisions.py tests/test_pc04a5b_revision_migration.py tests/test_pc04a5a_topology_library.py tests/test_pc04a4d_conversion.py tests/test_p1_57_topology_lab_context.py tests/test_switch_topology_chamber_binding.py -q
```

期望本次新增/受影响契约测试PASS。GUI运行 `npm run openapi:generate` 和相关node测试；本任务不全后端、不production build。记录RED/GREEN真实统计、失败残余；通过独立规格/质量审查后提交 `feat: 持久化拓扑修订并对全部写入口实施原子冲突保护`。

## Task 2：历史、恢复API与资格隔离

- [ ] **Step 1（RED）：写恢复生产路由测试。** 新文件复用Task1及5afixtures，代码中的 `rows` 为Task1已定义函数：

```python
from copy import deepcopy
from tests.test_pc04a5a_topology_library import db,client,world,lab,source,ROOT,raw
from tests.test_pc04a5b_topology_revisions import patch,rows

def test_preview_read_only_restore_is_new_revision(client,db,lab,source):
    original=deepcopy(source.connections)
    saved=patch(client,lab,source,{'expected_revision':0,'name':'误保存'})
    assert saved.status_code==200
    params={'lab_profile_id':str(lab.id)}
    body={'revision':0,'expected_revision':1}
    preview=client.post(f'{ROOT}/{source.id}/restore-preview',params=params,json=body)
    assert preview.status_code==200,preview.text
    assert raw(preview.json()['snapshot']['connections'])==raw(original)
    assert preview.json()['candidate']['connections'][0]['calibrated_loss_db'] is None
    assert 'calibrated_loss_db' not in preview.json()['candidate']['connections'][1]
    assert len(rows(db,source))==2
    restored=client.post(f'{ROOT}/{source.id}/restore',params=params,json=body)
    assert restored.status_code==200,restored.text
    assert restored.json()['revision']==2 and restored.json()['name']=='原图'
    history=rows(db,source)
    assert history[-1].operation=='restore' and history[-1].restored_from_revision==0
    assert raw(history[0].snapshot['connections'])==raw(original)
    assert client.post(f'{ROOT}/{source.id}/restore',params=params,json=body).status_code==409
    assert len(rows(db,source))==3

def test_read_old_history_never_lazy_writes(client,db,lab,source):
    response=client.get(f'{ROOT}/{source.id}/revisions',params={'lab_profile_id':str(lab.id)})
    assert response.status_code==200 and response.json()=={'total':0,'items':[]}
    assert rows(db,source)==[]
```

- [ ] **Step 2：运行RED。** `.venv/bin/python -m pytest tests/test_pc04a5b_topology_restore.py -q`；预期新路由404，不因真实库/硬件失败。
- [ ] **Step 3：Schema/路由/服务，实现明确类型。** 摘要包含revision/operation/created_at/restored_from_revision/recorded_metadata；详情另加snapshot。所有raw字段用 `dict[str,JsonValue]`，绝不 `SwitchTopologyResponse`。预览candidate是同样raw恢复字段对象；differences逐字段包含before_present/after_present及可选值，不将缺键写成null。

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, JsonValue
from app.schemas._datetime import UTCDateTime

class TopologyRestoreRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision: Revision
    expected_revision: Revision

class TopologyRevisionSummary(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    revision: Revision
    operation: Literal['baseline','create','copy','import','update','conversion','restore']
    created_at: UTCDateTime
    restored_from_revision: Revision|None
    recorded_metadata: dict[str,JsonValue]

class TopologyRevisionDetail(TopologyRevisionSummary):
    snapshot: dict[str,JsonValue]

class TopologyRevisionList(BaseModel):
    total: int
    items: list[TopologyRevisionSummary]

class TopologyFieldDifference(BaseModel):
    field: str
    before_present: bool
    after_present: bool
    before: JsonValue=None
    after: JsonValue=None

class TopologyRestorePreview(BaseModel):
    current_revision: Revision
    target_revision: Revision
    snapshot: dict[str,JsonValue]
    candidate: dict[str,JsonValue]
    differences: list[TopologyFieldDifference]
    warnings: list[str]
```

预览/详情路由用 `response_model_exclude_unset=True` 保持difference值缺失。实现 `restore_candidate(snapshot)`：只拷RESTORABLE；三图必须列表且每项对象，否则422；已有两个calibrated键置null，缺键保持。构造快照不typed化，唯一日期解析在将values传SQL之前。

```python
def restore_candidate(snapshot):
    if set(snapshot)!=set(RESTORABLE):
        raise HTTPException(422,detail='历史快照可恢复字段不完整')
    candidate=deepcopy(snapshot)
    for key in ('nodes','connections','operating_modes'):
        if not isinstance(candidate[key],list) or any(not isinstance(x,dict) for x in candidate[key]):
            raise HTTPException(422,detail='历史图必须为对象列表')
    for edge in candidate['connections']:
        for key in ('calibrated_loss_db','calibrated_phase_deg'):
            if key in edge:
                edge[key]=None
    return candidate

def field_differences(before,after):
    result=[]
    for key in sorted(set(before)|set(after)):
        if key in before and key in after and same_json(before[key],after[key]):
            continue
        item={'field':key,'before_present':key in before,'after_present':key in after}
        if key in before: item['before']=deepcopy(before[key])
        if key in after: item['after']=deepcopy(after[key])
        result.append(item)
    return result
```

顶层graph数组差异完整呈现raw前后内容（保持每个内部缺键/类型），不默默归一化；GUI可折叠JSON。restore-preview：scope→当前fresh图→expected匹配→按topology_id/revision查历史→candidate→下面六道保存门→临时对象统计及响应序列化验证→返回。读端不调用lock写SQLite暗室、不flush、不插baseline。restore：在写事务lock后重新执行同样选择/构造/门，不信preview候选；values从RESTORABLE取，installed_date用 `datetime.fromisoformat`（null保持）； `cas_revision(...,operation='restore',restored_from_revision=request.revision,force_revision=True)`，flush/响应预校验/commit。恢复不写scope/is_active/is_default/created_at/created_by。

校验门按当前源raw与candidate传参，复用 `switch_topology.py` 内 `_validate_nominal`、`_validate_structure`、`_validate_ports`、`_validate_internal_paths`、`_validate_loss_owners` 及Pydantic名称/日期字段验证。**不调用preserve_graph_rows把当前默认值灌进历史**；不把历史自己当previous绕过声明变化校验。previous必须当前raw，只有与当前同ID同字段且JSON类型/值未变的旧声明才能沿原保形例外；候选恢复了现在不允许的旧结构→preview422、restore422，当前零写。

数值门精确复用 `app/schemas/topology_nominal.py::validate_number`：`validate_nominal_write`本身不校验 `cable_loss_db`，该字段现有写规则位于 `preserve_connection_rows` 的 `validate_number(value,key='cable_loss_db',nonnegative=True)` 分支。恢复不走typed GET/显示值等价例外，按当前raw同ID同键比较，新增/改变的cable_loss_db显式调用该函数，拒绝bool、字符串、非有限和负值，允许null；缺键保持缺键。复用规则而不调用会回填/转换JSON的保形函数，不新建校验框架，其它字段继续各自现有规则。

```python
old_edges={edge['id']:edge for edge in current.connections}
for edge in candidate['connections']:
    if 'cable_loss_db' not in edge:
        continue
    previous=old_edges.get(edge['id'],{})
    value=edge['cable_loss_db']
    if 'cable_loss_db' not in previous or not same_json(value,previous['cable_loss_db']):
        try:
            validate_number(value,key='cable_loss_db',nonnegative=True)
        except ValueError as exc:
            raise HTTPException(422,detail=str(exc)) from exc
```

`validate_number`从 `app.schemas.topology_nominal`导入，current是锁后（preview为只读fresh）取到的当前ORM图；历史自身不作previous。恢复不能用缺connection_numeric_declarations跳过上述检查；未知不补0。

- [ ] **Step 4：服务TS镜像与开发mock。** `SwitchTopologyRevisionSummary/Detail`、`TopologyRestorePreview`字段对应上面schema；raw使用已有 `JsonValue`。服务方法参数完整：

```ts
async listRevisions(id:string,labProfileId:string,skip=0,limit=50):Promise<TopologyRevisionList> {
  return (await apiClient.get(`/switch-topologies/${id}/revisions`,{
    params:{lab_profile_id:labProfileId,skip,limit},
  })).data;
},
async getRevision(id:string,labProfileId:string,revision:number):Promise<TopologyRevisionDetail> {
  return (await apiClient.get(`/switch-topologies/${id}/revisions/${revision}`,{
    params:{lab_profile_id:labProfileId},
  })).data;
},
async previewRestore(id:string,labProfileId:string,revision:number,expectedRevision:number):Promise<TopologyRestorePreview> {
  return (await apiClient.post(`/switch-topologies/${id}/restore-preview`,
    {revision,expected_revision:expectedRevision},{params:{lab_profile_id:labProfileId}})).data;
},
async restoreTopology(id:string,labProfileId:string,revision:number,expectedRevision:number):Promise<SwitchTopology> {
  return (await apiClient.post(`/switch-topologies/${id}/restore`,
    {revision,expected_revision:expectedRevision},{params:{lab_profile_id:labProfileId}})).data;
},
```

`TopologyRevisionList={total:number;items:TopologyRevisionSummary[]}`，差异类型与schema相同并将before/after标可选；create未保存对象不产生历史。mock新GET返回404“页面演示无服务器修订历史”，新POST返回422“页面演示不恢复服务器图，请连接真实API”；不以空历史成功冒充查询到了服务器。

- [ ] **Step 5：补恢复边界正反例并GREEN。** 独立测试函数：`test_restore_same_candidate_still_appends`（连续恢复已相同r2内容，携带最新令牌，增加r3）；`test_restore_keeps_scope_status_and_creation_metadata`；`test_history_pagination_and_foreign_revision_404`（101次保存，total正确、降序、第二页、不读其它图编号）；`test_invalid_history_cannot_relax_current_save_gates`（端口、内部路径、引用、loss owner、非有限/负损耗分别preview422零写）；`test_restore_snapshot_insert_failure_rolls_back`；`test_stale_preview_rejected_at_restore`；`test_raw_history_does_not_gain_default_pins`。

资格回归不造一套采用判据。复用 `tests/test_pc04a2_route_application.py`、`test_pc04a2_route_freeze.py`、`test_pc04a4d_loss_truth.py` 的有效普通/参考路径生产入口夹具，实际通过restore API后断言：Application/Selection/run/证书数量及历史record字节不变；恢复清空当前内嵌值；身份相同沿既有confirmed门仍匹配、恰一次补偿；身份变化则当前和freeze两端拒绝旧匹配；新revision自身不使所有链失效。不改生产资格/freeze逻辑来迁就测试，也不承诺NULL topology_id旧证书被本片阻断。

```bash
.venv/bin/python -m pytest tests/test_pc04a5b_topology_restore.py tests/test_pc04a5b_topology_revisions.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a4d_loss_truth.py -q
```

只定点/累计，不全量。生成OpenAPI TS并检查契约，独立规格/质量审查后提交 `feat: 提供拓扑历史预览和保留资格边界的显式恢复`。

## Task 3：原GUI历史、冲突与生命周期

- [ ] **Step 1（RED）：纯状态测试先行，组件浏览器稍后验真。** 新增 `topologyRevisionState.ts` 定义以下API与 `gui/test/topologyRevisionState.test.ts`：

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import {canRestore,ownsRevisionRequest,revisionFailure} from '../src/features/TopologyEditor/topologyRevisionState.ts';

test('恢复与dirty、全部写、采集未知互斥',()=>{
  const ready={dirty:false,writing:false,collectionBusy:false,unknownWrite:false};
  assert.equal(canRestore(ready),true);
  for(const key of Object.keys(ready)) assert.equal(canRestore({...ready,[key]:true}),false);
});
test('scope图ID代数有一项变化就丢弃迟到响应',()=>{
  const current={scope:'lab/category',topologyId:'t',generation:2};
  assert.equal(ownsRevisionRequest(current,{...current}),true);
  assert.equal(ownsRevisionRequest(current,{...current,generation:1}),false);
  assert.equal(ownsRevisionRequest(current,{...current,topologyId:'other'}),false);
  assert.equal(ownsRevisionRequest(current,{...current,scope:'lab2/category'}),false);
});
test('409和超时均不自动重试',()=>{
  assert.equal(revisionFailure(409).kind,'conflict');
  assert.equal(revisionFailure(undefined).kind,'unknown');
  assert.equal(revisionFailure(422).kind,'rejected');
});
```

- [ ] **Step 2：运行RED。** gui中 `node --experimental-strip-types --test test/topologyRevisionState.test.ts`；预期新模块缺失，保存输出。
- [ ] **Step 3：最小状态实现，不建立第二套采集锁。**

```ts
export type RevisionContext={scope:string;topologyId:string;generation:number};
export type RevisionGuards={dirty:boolean;writing:boolean;collectionBusy:boolean;unknownWrite:boolean};
export function ownsRevisionRequest(a:RevisionContext,b:RevisionContext):boolean {
  return a.scope===b.scope&&a.topologyId===b.topologyId&&a.generation===b.generation;
}
export function canRestore(s:RevisionGuards):boolean {
  return !s.dirty&&!s.writing&&!s.collectionBusy&&!s.unknownWrite;
}
export function revisionFailure(status:number|undefined):{kind:'conflict'|'unknown'|'rejected';message:string} {
  if(status===409) return {kind:'conflict',message:'服务器已变化，草稿和输入已保留；请显式刷新核对，不会自动覆盖。'};
  if(status===undefined||status>=500) return {kind:'unknown',message:'保存结果未知；请刷新服务器修订核对，禁止自动重试恢复。'};
  return {kind:'rejected',message:'请求被拒绝，草稿和输入已保留。'};
}
```

API已返回200但随后详情GET失败也归unknown（写已确认、展示未核对），保留阻断直到显式核查；不能重新POST。错误框可同时显示服务端detail，不丢错误原因。

- [ ] **Step 4：新增 `TopologyHistoryPanel.tsx`，接入现有Flow。** 组件props明确为 `{opened,labId,topology,dirty,blocked,isBlocked,onClose,onRestore,onInspectLatest}`；`onRestore(targetRevision:number,expectedRevision:number):Promise<void>`由父Flow统一持写锁/guard，子组件只请求只读列表/详情/preview。Panel独立state为skip、items、total、selectedRevision、detail、preview、confirmed、error、pending；每次选择/预览/scope变化使request代数递增，清confirmed/preview，迟到回包仅owns匹配时显示。关闭不改draft，不复用转换候选为图。

固定界面内容：标题“保存修订历史”；列表每页50，显示r编号/操作/时间/恢复来源；空旧图显示“尚无修订留痕，从首次保存开始记录”；detail raw只读；recorded_metadata标“当时状态，仅供查阅，不恢复”；preview对照“历史原件 / 将写入候选 / 当前差异”，显示“恢复清空内嵌校准值，不自动重新采用，不代表通路合格”。复选框“确认将此历史声明恢复为新的保存修订”默认false；确认按钮须preview.current_revision等于当前保存revision且canRestore及confirmed。dirty允许只读历史，不允许restore-preview后执行恢复；提示先保存或显式放弃。

```tsx
<Alert color="orange">历史原件只读。恢复将生成新修订、清空已有内嵌校准值；不恢复采用、证书或执行资格。</Alert>
<Checkbox checked={confirmed} onChange={e=>setConfirmed(e.currentTarget.checked)}
  label="确认将此历史声明恢复为新的保存修订" disabled={blocked||dirty||!preview}/>
<Button data-testid="topology-restore-confirm" disabled={blocked||dirty||!confirmed||!preview}
  onClick={()=>{if(!isBlocked()&&!dirty&&confirmed&&preview)void onRestore(preview.target_revision,preview.current_revision)}}>
  恢复为新修订
</Button>
```

代码接入保留Mantine原语，历史JSON用 `<pre>`/Text，不能innerHTML。分页实际请求skip与limit，不只前端截断第一页。完整列表/preview不修改原 `numericDeclarations`、selectedNode/edge或dirty。

- [ ] **Step 5：父Flow统一保存/恢复上下文，原库写共享锁。** `savingRef`、`collectionBusyRef`、`isLibraryBusy()`仍为即时门；开始恢复同步置savingRef，注册beginWork，再await。每次操作捕获lab/category/topologyId/generation；结束只有当前请求可更新state或解除其锁，离页/换scope后旧finally不能解除新请求。恢复成功先服务端restore，再GET detail，令牌/draft从该GET取；清理selected node/edge/connection、drawers、highlightedRoute、numericDeclarations及转换旧preview，更新库当前项。失败不清草稿、不接纳409返回的新令牌重试。

```ts
const ticket={scope,topologyId:topology.id,generation:++requestGeneration.current};
savingRef.current=true;
setSaving(true);
try {
  await switchTopologyService.restoreTopology(ticket.topologyId,labProfileId,targetRevision,expectedRevision);
  const current=await switchTopologyService.getTopology(ticket.topologyId,labProfileId);
  if(!mounted.current||!ownsRevisionRequest(liveRequest.current,ticket))return;
  setDraft(current);
  setNumericDeclarations({});
  setEdgeNumericDeclarations([]);
  setHighlightedRoute(null);
  setSelectedConnectionId(null);
  setDrawerOpen(false);
  updateDirty(false);
  onTopologyUpdated(current);
} catch(err) {
  if(mounted.current&&ownsRevisionRequest(liveRequest.current,ticket)) {
    const failure=revisionFailure((err as {response?:{status?:number}}).response?.status);
    setRevisionError(failure.message);
    if(failure.kind==='unknown')setUnknownWrite(true);
  }
} finally {
  if(mounted.current&&ownsRevisionRequest(liveRequest.current,ticket)) {
    savingRef.current=false;
    setSaving(false);
    onBusyChange(collectionBusyRef.current||unknownWriteRef.current);
  }
}
```

上述变量在Flow初始化：`requestGeneration=useRef(0)`、`liveRequest=useRef<RevisionContext>({scope,topologyId:topology.id??'',generation:0})`、revisionError字符串、unknownWrite布尔及同步ref；启动前同时设置liveRequest=ticket。复用现有beginWork release，release只结清本网络任务，unknownWrite的持久阻断由state/ref和离页guard消费；禁止finally把采集或未知状态强制false。selectedNode/selectedEdge具体setter沿原Flow名清理，不保留指向被恢复图不存在对象的选择。

显式“刷新查看服务器最新”只GET当前图/历史并展示比较，dirty草稿仍保留，不能用新的revision配旧draft直接保存；用户必须明确放弃旧草稿后采用最新详情，或保留草稿取消。结果未知时强制核对GET revision/历史中的operation与内容，不自动判恢复成功；用户确认采用服务器最新后清unknownWrite。与已有“放弃未保存改动”按钮区分：后者仅回到已知保存快照，不叫历史恢复。保存/名称/转换也统一409/超时提示；conversion输入保持，重新预览须显式。

`RouteCalibrationPanel`既有 `revision:string` 是JSON queryKey，不改成整数令牌。新Flow变量称 `savedRevision`（来自topology.revision），仍传原graph JSON queryKey给校准组件。恢复改变graph时queryKey自然失效；纯名称修订不触发错误的资格取消。

- [ ] **Step 6：GREEN与真组件准备。** gui运行以下命令，不跑完整后端/build；纯helper通过不能代替Task4真浏览器：

```bash
npx --no-install tsx --test test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/legacyConversionState.test.ts test/topologyOperationalLabContext.test.ts
npm run openapi:generate
```

累计套件含 `CustomEdges.tsx` 和无扩展名import，不能用Node strip-types跑，否则得到工具错误而非产品RED。沿用5a的no-install命令；编制时已核本机缓存 `/Users/simon/.npm/_npx/fd45a72a545557e9/node_modules/tsx/dist/cli.mjs` 存在、package版本4.23.15。执行前核实际runner版本，若缓存不可用向主任务报告再裁决固定版本，不自动下载最新、不改package/lock、不将加载错误算修复失败。仅新纯state RED可用Step2的strip-types。

检查请求体普通保存/改名/转换均带正确整数；mock/history错误不显示成功toast。独立规格/质量审查后提交 `feat: 在拓扑编辑器提供历史预览恢复及冲突保稿`。

## Task 4：新库真实API/浏览器、唯一最终全量与正式摘要

**唯一最终全量责任：本任务执行者。** Task1～3和所有审查者只复用输出或跑必要定点，不因身份重复全量。稳定输入后再全量；其后生产共享契约若变，旧全量失效，由同一责任者按CLAUDE重新安排最终版，不谎称旧结果覆盖新版。

- [ ] **Step 1（RED/基线）：建全新隔离浏览器夹具。** 新文件沿 `tests/pc04a5a_browser_fixture.py` 的真实bootstrap结构，前置环境path断言替换为 `/tmp/pc04a5b-[A-Za-z0-9]+/browser.sqlite`；必须不存在新文件再seed，`Base.metadata.create_all`→`run_bootstrap_on_startup`→每个InstrumentCategory.driver_mode=mock→全部Lab.instrument_bindings每个driver_mode=mock→commit→重新查询all断言。保留原所有bootstrap模板；新增两个测试暗室、两个Lab及共享暗室Lab、两个switch category。只在该新库种legacy r0图，使用真实API保存101次得到分页历史；不得向用户原库写CAICT副本。

bootstrap后核查实际HAL选择使用 `is_mock_driver()`，而非名字前缀或只读env。manifest记录全Mock类别/binding、DB绝对路径、Lab/category/图UUID、当前revision及历史条数；不输出凭据。当前新图创建统一走API以有r1历史，legacy r0仅夹具明确直写并记录来源。

`gui/vite.pc04a5b.config.ts`只改专用代理目标 `http://127.0.0.1:18106`，GUI端口15186；若端口占用，报告并选择空闲新端口同步fixture，不停用户服务。启动前检查 `lsof -nP -iTCP:18106 -sTCP:LISTEN` 与15186；只负责本次精确PID。

```bash
pc04a5b_browser_dir=$(mktemp -d /tmp/pc04a5b-XXXXXX)
export DATABASE_URL="sqlite:///$pc04a5b_browser_dir/browser.sqlite"
export USE_MOCK_INSTRUMENTS=true
export BOOTSTRAP_ON_STARTUP=true
export LOG_DIR="$pc04a5b_browser_dir/logs"
.venv/bin/python -m tests.pc04a5b_browser_fixture
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18106
```

GUI独立终端在gui目录：`npm run dev -- --host 127.0.0.1 --port 15186 --strictPort --config vite.pc04a5b.config.ts`。服务仅本轮临时库，默认用户8000及其GUI不操作。浏览器工具遵循当前可用browser skill，真实鼠标/表单动作主证据；接口脚本用于构造第二客户端冲突和只读SQL核验，不冒充鼠标操作。

- [ ] **Step 2：真实浏览器矩阵。** 新 `gui/test/pc04a5bRevisions.browser.js` 跟踪每项请求方法/body/status、UI状态和截图；手工或既有浏览器执行器跑完同一矩阵，证据放 `output/playwright/pc04a5b/`，保留文件。

| 编号 | 鼠标/真实请求序列 | 数据与界面断言 |
|---|---|---|
| H01 | legacy r0打开历史→拖节点→保存→重载 | 打开不写；保存r1且baseline0；真实坐标持久化，历史raw不补pin |
| H02 | 改名保存→再次修改误保存→历史选前版→预览→二次确认恢复 | 预览draft/dirty不变；恢复rN+1，不倒退；当前清内嵌校准，历史原件保留 |
| H03 | 两浏览器同rN；A保存，B保存旧草稿 | A200、B409；B内容/输入不变，无自动PATCH；刷新查看最新仍不覆盖B草稿 |
| H04 | 转换预览后A仅改名，再确认旧转换 | digest可能不变但revision409；输入保留，显式重新预览后才可保存 |
| H05 | 后端已完成restore但阻断响应/GET或浏览器断网 | 结果未知提示持续，不自动再POST；显式GET/history核查后方可采用最新 |
| H06 | 历史列表第2页、同名图、共享暗室Lab、跨category | total/skip实际请求正确，不串图修订；Lab/category偏好不改 |
| H07 | dirty点击恢复、保存中双击、库写中恢复、采集start/unknown时恢复 | 无第二写/恢复请求；blocked/ref即时生效；finally不解采集锁 |
| H08 | 切Lab/图后人工延迟的历史/preview/保存回包到达，离页后返回 | scope/图ID/代数不匹配不更新draft，不释放新锁 |
| H09 | 显式放弃草稿；再单独打开历史 | 放弃仅回已知保存版本，不追加history；历史恢复必须二次确认 |
| H10 | 恢复同内容、invalid历史、跨scope及缺令牌写 | 同内容新增restore行；其它422/409/既有scope拒绝且无写 |

Mock采集只验证busy生命周期，不把Mock值当正式实测、confirmed或B/HOLD通过。需构造真实confirmed软件正例时沿现有测试生产入口/证据夹具，明确synthetic软件证据，不能现场采集冒充。

- [ ] **Step 3：只读库审计与正式消费者回归。** `tests/pc04a5b_browser_audit.py` 导入前验证同一新库路径、Mock环境；只SELECT，不init/seed。审计：history每图revision唯一、当前rev等于max、legacy未写历史空、source/copy UUID及历史独立、calibrated只在候选清null、scope/active/default/created字段不恢复、历史record前后不改；请求日志与截图逐项对应当前SHA。执行/证书/采用计数与内容摘要前后比对，不能只看toast。API定点包含Task1/2新测试及 `test_pc04a2_route_selection.py`、`test_pc04a2_route_eligibility.py`、`test_pc04a2_route_application.py`、`test_pc04a2_route_freeze.py`、`test_pc04a4d_loss_truth.py`。

- [ ] **Step 4：冻结输入，唯一最终后端全量。** 记录git HEAD、tracked diff以及实际Python测试输入清单hash（包含本片未提交文件，排除venv/output/scratch）；全量前后列表一致才可复用。另起新/tmp目录，不使用browser.sqlite。环境同0.2；全量运行前bootstrap新库并明确所有类别/所有Lab bindings Mock，再重新查询核验，禁止依靠环境变量代替绑定检查。可用Task4夹具拆出 `bootstrap_mock_database()` 供browser/full共同调用；输入路径严格限制新/tmp/pc04a5b目录，full.sqlite与browser.sqlite分别守卫，不能接受任意DB URL。

```bash
pc04a5b_full_dir=$(mktemp -d /tmp/pc04a5b-XXXXXX)
export DATABASE_URL="sqlite:///$pc04a5b_full_dir/full.sqlite"
export USE_MOCK_INSTRUMENTS=true
export BOOTSTRAP_ON_STARTUP=true
export LOG_DIR="$pc04a5b_full_dir/logs"
.venv/bin/python -m tests.pc04a5b_browser_fixture --bootstrap-only
.venv/bin/python -m pytest tests -q
```

`--bootstrap-only`在新夹具中明确实现：只schema/bootstrap/强制Mock/核验，不种浏览器业务图；严格允许full.sqlite全新路径。最终GUI命令：`npx --no-install tsx --test test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyDraft.test.ts test/topologyNominalTransport.test.ts test/legacyConversionState.test.ts test/topologyOperationalLabContext.test.ts`、`npm run build`。保存原输出、退出码和结尾统计，不仅截图绿色；5a的8003/17/3不是本片结果，不改G8/G11或.gitignore历史规则来造绿。

- [ ] **Step 5：正式摘要、独立累计审查与交接。** 新validation写明SHA/命令/环境新库路径/全Mock绑定证明、迁移与CAS两连接证据、每项浏览器截图和请求、资格/freeze两端、唯一全量实际统计、残余失败/未验边界。写明纯软件完成不等于现场B/HOLD；原CAICT未动，5c/5d未启动。更新roadmap仅将5b改为当前真实进度，不凭计划标完成。`git diff --check`后提交 `test: 验证拓扑修订恢复全链路并记录隔离证据`。
- [ ] 后续Ready PR按AGENTS R1/R2最新HEAD全通道及SHA覆盖规则收口，P1修复必须下一轮外审覆盖，R2无P1即收口；本计划编制不push、不建PR、不改自动化。主任务结束前写work record/handoff/release；本子任务不释放主claim。

## 自查与交付覆盖

| 批准设计条款 | 计划位置 |
|---|---|
| 独立revision、baseline、原始JSON/日期/不恢复字段 | Task1 Step3–5、Task2 Step3 |
| 所有入口CAS、默认peer/空peer并发、name排序、响应先验与回滚 | Task1 Step4–7 |
| 双删除入口+FK、模板保留旧库 | Task1 Step3/5/7 |
| 四镜像、旧客户端422、转换envelope及双CAS | 0.3、Task1 Step6–7、Task2 Step4 |
| 历史分页/raw、restore清校准/重新校验/不授资格 | Task2全任务 |
| dirty、冲突保稿、超时未知、scope/代数、采集互斥 | Task3 Step3–5、H03–H09 |
| 新库、全Mock、真实浏览器、最终唯一全量、软件/现场区分 | 0.2、Task4全任务 |

编制自查必须检索占位词、核类型与函数名、逐条对照spec；本文件是施工计划，不把所列测试命令/代码示例称为已执行证据。`recorded_metadata`仅供审计；恢复对当前资格的匹配判断继续由既有身份门完成，不按revision号一刀切取消资格。
