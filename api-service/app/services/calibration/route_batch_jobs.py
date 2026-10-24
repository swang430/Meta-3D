"""PC06A1单进程批作业：同task跨项独占，真实释放后父子事务交接。

重启只读中断事实，绝不从当前HAL补历史安全状态或自动续跑。
"""
import asyncio
import copy
import logging
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic import ValidationError
from app.db.database import SessionLocal
from app.models.diagnostic_run import DiagnosticRun
from app.schemas.diagnostic_evidence import SequenceEvidence
from app.schemas.fixed_route_acquisition import FixedRouteResult
from app.schemas.route_batch import BatchPlan
from app.services.calibration import fixed_route_jobs as single
from app.services.calibration.route_batch_plan import build_batch_plan, snapshot_switch_connection
from app.models.instrument import InstrumentConnection
from app.services.calibration.fixed_route_acquisition import collect_fixed_route
from app.services.instrument_hal_service import get_hal_service
from app.services.instrument_test_lease import instrument_test_lease, await_completion_despite_cancellation
from app.services.execution_exclusion_guard import try_acquire_unsafe_diagnostic, release_unsafe_diagnostic
from app.services.test_case_runner import has_active_case_run, has_running_case_run_row
from app.services.calibration.route_batch_switch import apply_batch_switch_steps
from app.services.instrument_hal_service import is_mock_driver

logger=logging.getLogger(__name__)
TARGET='route_calibration_batch'
ACTIVE={'running','waiting_manual','paused_failure'}
TERMINAL={'completed','cancelled','failed','cleanup_unconfirmed','interrupted','incomplete'}


class BatchPersistenceError(RuntimeError):
    """批进度未提交，不允许最终事务重存后洗成可采用。"""


@dataclass(frozen=True)
class BatchItemContext:
    job_id: UUID
    item_id: str


@dataclass
class RunningBatch:
    task: asyncio.Task | None = None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    resume: asyncio.Event = field(default_factory=asyncio.Event)
    hal: object = None
    last_prepared: object = None
    switch_identities: dict = field(default_factory=dict)
    switch_driver: object = None


_running: dict[UUID,RunningBatch]={}


def _payload(row):
    value=SequenceEvidence.model_validate(row.sequence_evidence).extra.get(TARGET)
    if not isinstance(value,dict) or value.get('job_id')!=str(row.id) or value.get('lab_id')!=str(row.lab_profile_id):
        raise ValueError('批审计身份损坏，不能恢复或补历史')
    if (value.get('status') not in ACTIVE|TERMINAL or not isinstance(value.get('items'),list)
        or not isinstance(value.get('plan'),dict) or any(not isinstance(i,dict) or 'status' not in i for i in value['items'])):
        raise ValueError('批审计内容缺损，不能恢复或补历史')
    return copy.deepcopy(value)


def _save_parent(row,value):
    row.sequence_evidence=SequenceEvidence(summary='逐通路批采集（不签发校准资格）',duration_ms=0,
        steps=[],log=[value['error']] if value.get('error') else [],extra={TARGET:copy.deepcopy(value)}).model_dump(mode='json')
    row.success=value['status']=='completed'
    row.error_message=value.get('error')


def record(db,row):
    try:
        value=_payload(row)
    except (ValueError,TypeError,ValidationError):
        return dict(job_id=str(row.id),lab_id=str(row.lab_profile_id),status='incomplete',
            finalization_committed=False,f64_control_released=None,items=[],error='批审计记录缺损，需现场核验')
    if row.id in _running:
        value['cancel_requested']=_running[row.id].cancel.is_set()
    if value['status'] in ACTIVE and row.id not in _running:
        value.update(status='interrupted',f64_control_released=None,finalization_committed=False,
            error='服务已中断；未自动续跑，历史中断不等于已停发，请现场核验')
        for item in value['items']:
            if item['status'] in ('measuring','waiting_manual'):
                item['status']='interrupted'
    return value


def validated_batch_item(db,lab_id,request,context):
    """内部上下文只读本lab同事务已flush或已提交的服务器冻结计划，不能传True绕过集合门。"""
    if not isinstance(context,BatchItemContext):
        raise ValueError('缺少服务器批项身份')
    row=db.get(DiagnosticRun,context.job_id)
    if row is None or row.target_name!=TARGET or row.lab_profile_id!=lab_id:
        raise ValueError('批项不属于当前实验室')
    value=_payload(row)
    if value['status'] not in ACTIVE or value.get('finalization_committed'):
        raise ValueError('批已结束，不能重新开始采集')
    plan=BatchPlan.model_validate(value['plan'])
    items=[i for i in plan.items if i.item_id==context.item_id]
    if len(items)!=1 or items[0].request.model_dump(mode='json')!=request.model_dump(mode='json'):
        raise ValueError('批项请求与服务器冻结项不一致')
    return items[0]


def batch_child_context(db,row):
    """数据库父子归属/lease/finalization是权威；运行表只提供当前活动事实。"""
    denied=dict(active=False,finalized=False)
    try:
        child=FixedRouteResult.model_validate(SequenceEvidence.model_validate(row.sequence_evidence).extra.get('fixed_route_acquisition'))
        states=child.states
        if not states.get('batch_job_id'):
            return None
        parent=db.get(DiagnosticRun,UUID(states['batch_job_id']))
        if parent is None or parent.target_name!=TARGET or parent.lab_profile_id!=row.lab_profile_id:
            return denied
        value=_payload(parent)
        matches=[i for i in value['items'] if i.get('item_id')==states.get('batch_item_id') and i.get('run_id')==str(row.id)]
        if len(matches)!=1 or not states.get('lease_id') or states['lease_id']!=value.get('lease_id'):
            return denied
        active=parent.id in _running
        finalized=(not active and value['status'] in TERMINAL-{'cleanup_unconfirmed','interrupted','incomplete'}
            and value.get('persistence_failed') is False
            and value.get('finalization_committed') is True and value.get('f64_control_released') is True
            and value.get('all_started_cleanup_confirmed') is True
            and bool(value.get('finalization_id')) and states.get('batch_finalization_id')==value['finalization_id']
            and states.get('f64_control_released') is True)
        return dict(active=active,finalized=finalized,job_id=str(parent.id),lease_id=value.get('lease_id'),
            finalization_id=value.get('finalization_id'))
    except (ValueError,TypeError,KeyError,ValidationError):
        return denied


async def start(db,lab_id,request,*,idempotency_key):
    if not request.preview_digest:
        raise ValueError('必须先预览并提交preview_digest，不能直接开始批采集')
    if not isinstance(idempotency_key,UUID):
        raise ValueError('批启动需要幂等UUID')
    # 先重读保存计划，幂等重放不派第二个task。
    for row in db.query(DiagnosticRun).filter_by(lab_profile_id=lab_id,target_name=TARGET).all():
        evidence=row.sequence_evidence
        extra=evidence.get('extra') if isinstance(evidence,dict) else None
        candidate=extra.get(TARGET) if isinstance(extra,dict) else None
        if not isinstance(candidate,dict) or candidate.get('idempotency_key')!=str(idempotency_key):
            continue  # 无关历史缺损只影响其读取，不作为新批启动前置。
        value=_payload(row)
        if value.get('request')!=request.model_dump(mode='json'):
            raise single.AcquisitionBusy('幂等键已用于不同批请求')
        return record(db,row)
    if has_active_case_run() or has_running_case_run_row(db):
        raise single.AcquisitionBusy('已有测试执行在运行，不能开始批采集')
    token=try_acquire_unsafe_diagnostic(TARGET)
    if token is None:
        raise single.AcquisitionBusy('已有测试或诊断占用仪器')
    try:
        plan=build_batch_plan(db,lab_id,request,get_hal_service())
        ident=uuid4()
        value=dict(version=1,job_id=str(ident),lab_id=str(lab_id),idempotency_key=str(idempotency_key),
            request=request.model_dump(mode='json'),plan=plan.model_dump(mode='json'),preview_digest=plan.preview_digest,
            status='running',current_index=0,transition_id=None,cancel_requested=False,error=None,
            lease_id=None,f64_control_released=None,finalization_id=None,finalization_committed=False,
            persistence_failed=False,
            all_started_cleanup_confirmed=None,items=[dict(item_id=i.item_id,request=i.request.model_dump(mode='json'),
                status='pending',run_id=None,error=None) for i in plan.items])
        row=DiagnosticRun(id=ident,lab_profile_id=lab_id,target_name=TARGET,kind='scpi_sequence',
            params=request.model_dump(mode='json'),success=False)
        _save_parent(row,value);db.add(row);db.flush()
        # 启动核验消费同事务服务器上下文；通过前不留下无task的running记录。
        for item in plan.items:
            single.resolve_configuration(db,lab_id,item.request,get_hal_service(),
                batch_item_context=BatchItemContext(ident,item.item_id))
        db.commit()
        active=RunningBatch()
        _running[ident]=active
        active.task=asyncio.create_task(_execute(ident,token,active))
        return record(db,row)
    except BaseException:
        try:
            db.rollback()
        finally:
            release_unsafe_diagnostic(token)
        raise


def _commit_progress(ident,value,result=None):
    try:
        with SessionLocal() as db:
            parent=db.get(DiagnosticRun,ident)
            if parent is None: raise RuntimeError('批审计记录丢失')
            if result is not None:
                row=db.get(DiagnosticRun,result.run_id)
                if row is None: db.add(single.build_record_row(result))
                else: single.save_record_result(row,result)
            _save_parent(parent,value)
            db.commit()
    except Exception as exc:
        raise BatchPersistenceError('批进度落盘失败，禁止后续项及采用') from exc


async def _wait_manual(ident,value,item,active):
    """等待只消费当前transition；取消唤醒不等于确认。"""
    value.update(status='waiting_manual',transition_id=uuid4().hex)
    value['items'][value['current_index']]['status']='waiting_manual'
    active.resume.clear()
    _commit_progress(ident,value)
    await active.resume.wait()
    value['cancel_requested']=active.cancel.is_set()
    value.update(status='running',transition_id=None)


async def _prepare_item(ident,value,item,active):
    """无活动tone的边界才可换线；固定直连完全不碰开关。"""
    simulated=is_mock_driver(active.hal.drivers.get('channelEmulator'))
    previous=active.last_prepared
    # 参考位置变化或固定直连换路要人工；同位置由开关换路不需要人工换线。
    manual=(previous is None or previous.request.reference_antenna!=item.request.reference_antenna
        or (previous.request.chain_id!=item.request.chain_id and
            not (previous.switch_steps and item.switch_steps)))
    value['manual_notice']=('模拟人工步骤；未确认任何实物停发或接线安全' if simulated
        else '请核对本项参考天线位置及接线；之前已启动tone均已确认清理')
    if manual:
        await _wait_manual(ident,value,item,active)
    if active.cancel.is_set():
        return
    # 人工等待期间保存图/绑定仍可能变化：必须在首个开关I/O之前重读冻结scope。
    with SessionLocal() as db:
        single.resolve_configuration(db,UUID(value['lab_id']),item.request,active.hal,
            batch_item_context=BatchItemContext(ident,item.item_id))
        for step in item.switch_steps:
            connection=db.get(InstrumentConnection,step.connection_id)
            if connection is None or snapshot_switch_connection(connection)!=step.connection_config:
                raise ValueError('保存开关连接/封装配置已变化，请重新预览并确认；未操作旧连接')
    if item.switch_steps:
        if not simulated:
            if value['plan'].get('switch_wiring_confirmation') is None:
                raise ValueError('自动切换缺少本清单范围的操作员接线声明，未开始测量')
            driver=active.hal.drivers.get('rfSwitch')
            if active.switch_driver is not None and active.switch_driver is not driver:
                raise ValueError('本作业开关驱动身份已变化')
            active.switch_driver=driver
        progress=value['items'][value['current_index']]
        def sink(receipt):
            receipt.update(job_id=str(ident),item_id=item.item_id,attempt=1)
            if receipt.get('kind')=='identity' and not receipt.get('error'):
                key=(receipt['driver_id'],receipt['command'])
                expected=active.switch_identities.get(key)
                if expected is not None and expected!=receipt['raw']:
                    receipt['error']='本作业开关机箱/卡身份已变化'
                else:
                    active.switch_identities[key]=receipt['raw']
            progress.setdefault('switch_receipts',[]).append(receipt)
            _commit_progress(ident,value)
            if receipt.get('error')=='本作业开关机箱/卡身份已变化':
                raise ValueError(receipt['error'])
            if active.cancel.is_set():
                raise asyncio.CancelledError()
        # VXI-11可能正在线程里写：外层task取消也必须等在途操作落定，不能提前放lease/guard。
        outcome=await await_completion_despite_cancellation(apply_batch_switch_steps(active.hal,item.switch_steps,sink,simulated=simulated))
        if outcome.error:
            raise outcome.error
        if outcome.delayed_cancellation:
            raise outcome.delayed_cancellation
        if outcome.value is not True:
            raise ValueError('开关资格或本次严格写读失败，未开始测量；请查看逐项receipt')
    active.last_prepared=item


async def _pause_failure(ident,value,item,active,error):
    """保留失败项；继续只跳过，绝不自动重试。"""
    active.last_prepared=None  # 人工可能已移位但准备未成功；下项必须重新确认，不能沿用旧摆位。
    progress=value['items'][value['current_index']]
    progress.update(status='failed',error=str(error))
    value.update(status='paused_failure',error=str(error),transition_id=uuid4().hex)
    active.resume.clear()
    _commit_progress(ident,value)
    if not active.cancel.is_set():
        await active.resume.wait()
    value.update(status='running',transition_id=None)


async def _execute(ident,token,active):
    results=[];lease=None;value=None
    try:
        with SessionLocal() as db:
            value=_payload(db.get(DiagnosticRun,ident))
        plan=BatchPlan.model_validate(value['plan'])
        lab_id=plan.lab_profile_id
        selected_hal=None
        def validate(hal):
            nonlocal selected_hal
            try:
                with SessionLocal() as db:
                    if has_active_case_run() or has_running_case_run_row(db):
                        return '测试已开始，拒绝进入控制'
                    for item in plan.items:
                        single.resolve_configuration(db,lab_id,item.request,hal,
                            batch_item_context=BatchItemContext(ident,item.item_id))
                selected_hal=hal
                return None
            except (ValueError,LookupError) as exc:
                return str(exc)
        if active.cancel.is_set():
            value['status']='cancelled'
        else:
            async with instrument_test_lease(f'calibration-batch:{ident}',control_f64=True,control_uxm=False,
                enable_monitoring=False,restore_f64_alignment=False,validate_before_remote=validate) as lease:
                value['lease_id']=lease.lease_id
                if selected_hal is None: raise ValueError('未核对批仪器身份，不能开始发射')
                active.hal=selected_hal
                _commit_progress(ident,value)
                for index,item in enumerate(plan.items):
                    value['current_index']=index
                    if active.cancel.is_set(): break
                    try:
                        await _prepare_item(ident,value,item,active)
                    except BatchPersistenceError:
                        raise
                    except Exception as exc:
                        await _pause_failure(ident,value,item,active,exc)
                        continue
                    if active.cancel.is_set(): break
                    with SessionLocal() as db:
                        config,output,ce,sa=single.resolve_configuration(db,lab_id,item.request,selected_hal,
                            batch_item_context=BatchItemContext(ident,item.item_id))
                    result=FixedRouteResult(version=2,run_id=uuid4(),lab_profile_id=lab_id,request=item.request,
                        configuration=config,states=dict(batch_job_id=str(ident),batch_item_id=item.item_id,
                            lease_id=lease.lease_id,f64_control_released=None))
                    results.append(result)
                    progress=value['items'][index]
                    progress.update(status='measuring',run_id=str(result.run_id))
                    _commit_progress(ident,value,result)
                    await collect_fixed_route(ce,sa,result,output_port=output,cancel=active.cancel)
                    # collect的tone收尾不构成外层Remote释放。
                    result.states['f64_control_released']=None
                    if result.status=='cancelled': active.cancel.set()
                    progress.update(status=result.status,error=result.error)
                    _commit_progress(ident,value,result)
                    if result.status=='cleanup_unconfirmed' or (result.status!='simulated' and result.cleanup_confirmed is not True):
                        value.update(status='cleanup_unconfirmed',error=result.error or '可能仍在发射；本项tone停止未确认，禁止换线或继续')
                        break
                    if result.status not in ('completed','simulated'):
                        if result.status=='cancelled' or active.cancel.is_set():
                            value['status']='cancelled';break
                        await _pause_failure(ident,value,item,active,result.error or '本项采集失败')
                if value['status'] not in ('cleanup_unconfirmed','failed','cancelled'):
                    value['status']=('cancelled' if active.cancel.is_set() else
                        'failed' if any(i['status']=='failed' for i in value['items']) else 'completed')
    except (Exception,asyncio.CancelledError) as exc:
        if value is not None:
            if isinstance(exc,asyncio.CancelledError): active.cancel.set()
            if isinstance(exc,BatchPersistenceError): value['persistence_failed']=True
            value['status']='cleanup_unconfirmed' if any(r.cleanup_confirmed is False or r.status=='cleanup_unconfirmed' for r in results) else ('cancelled' if isinstance(exc,asyncio.CancelledError) else 'failed')
            value['error']=str(exc) or '服务取消批采集'
            for result in results:
                if result.status=='running':
                    result.status='interrupted';result.net_loss_db=None
    finally:
        try:
            if value is not None:
                released=getattr(lease,'channel_emulator_transport_released_confirmed',None)
                value['f64_control_released']=released
                clean=all(r.cleanup_confirmed is True for r in results)
                value['all_started_cleanup_confirmed']=clean
                if results and not clean and any(r.status!='simulated' for r in results):
                    value['status']='cleanup_unconfirmed'
                if (lease is not None and (released is False or (results and any(r.status!='simulated' for r in results) and released is not True))
                    and value['status']!='cleanup_unconfirmed'):
                    value['status']='cleanup_unconfirmed'
                if value['status']=='cleanup_unconfirmed':
                    value['error']='可能仍在发射或控制释放未确认；禁止换线或继续，请现场核验。'+(value.get('error') or '')
                value.update(finalization_id=uuid4().hex,finalization_committed=True,transition_id=None,
                    cancel_requested=active.cancel.is_set())
                for item in value['items']:
                    if active.cancel.is_set() and item['status'] in ('pending','waiting_manual'):
                        item['status']='cancelled'
                _finalize(ident,value,results)
        except Exception:
            logger.exception('批最终事务未提交，子记录保持不可采用：%s',ident)
        finally:
            _running.pop(ident,None)
            release_unsafe_diagnostic(token)


def _finalize(ident,value,results):
    """只在真实lease退出后调用；一个事务提交父与所有子释放来源。"""
    with SessionLocal() as db:
        parent=db.get(DiagnosticRun,ident)
        if parent is None: raise RuntimeError('批审计记录丢失')
        for result in results:
            row=db.get(DiagnosticRun,result.run_id)
            if row is None: raise RuntimeError('批子记录缺失，不能提交释放证明')
            result.states.update(f64_control_released=value['f64_control_released'],batch_finalization_id=value['finalization_id'])
            single.save_record_result(row,result)
        _save_parent(parent,value)
        db.commit()


def request_cancel(job_id):
    active=_running.get(job_id)
    if active is None:
        raise single.AcquisitionBusy('批已结束或服务已重启；不能声称仪器已停发，请现场核验')
    active.cancel.set();active.resume.set()


def continue_job(db,lab_id,job_id,*,item_id,transition_id,reference_antenna,manual_confirmed,skip_failed=False):
    active=_running.get(job_id)
    row=db.get(DiagnosticRun,job_id)
    if row is None or row.lab_profile_id!=lab_id or row.target_name!=TARGET:
        raise LookupError('本实验室中没有此批记录')
    value=_payload(row)
    if active is None or active.cancel.is_set() or active.resume.is_set() or value['status'] not in ('waiting_manual','paused_failure'):
        raise single.AcquisitionBusy('批不在可继续的人工等待状态')
    item=value['items'][value['current_index']]
    if (manual_confirmed is not True or skip_failed is not (value['status']=='paused_failure') or value['transition_id']!=transition_id or
        item['item_id']!=item_id or item['request']['reference_antenna']!=reference_antenna):
        raise ValueError('人工确认与当前冻结步骤或参考位置不一致')
    active.resume.set()


async def shutdown_route_batch_jobs():
    """取消并等待真实lease退出及最终落盘尝试，然后才允许HAL关闭。"""
    tasks=[]
    for ident,active in list(_running.items()):
        request_cancel(ident);tasks.append(active.task)
    if tasks:
        outcome=await await_completion_despite_cancellation(asyncio.gather(*tasks,return_exceptions=True))
        if outcome.error: raise outcome.error
