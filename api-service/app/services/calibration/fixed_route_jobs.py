"""PC-04A单条链采集作业；复用单进程执行互斥与DiagnosticRun，不自动续跑。"""
import asyncio
import logging
from datetime import timezone
from time import perf_counter
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.hal.base import resolve_configured_tcpip_connection
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.rs_fsva import RealRsFsvaDriver
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.diagnostic_run import DiagnosticRun
from app.schemas.fixed_route_acquisition import FixedRouteRequest, FixedRouteResult, FixedRouteRecord
from app.schemas.diagnostic_evidence import SequenceEvidence
from app.services.calibration.configuration_scope import build_calibration_scope, build_selected_route_calibration_scope
from app.services.calibration.fixed_route_acquisition import collect_fixed_route
from app.services.calibration.route_calibration import list_route_selections
from app.services.channel_emulator_binding import resolve_channel_emulator_binding
from app.services.instrument_hal_service import get_hal_service, get_real_driver_class, is_mock_driver
from app.services.instrument_test_lease import instrument_test_lease
from app.services.instrument_test_lease import await_completion_despite_cancellation
from app.services.execution_exclusion_guard import try_acquire_unsafe_diagnostic, release_unsafe_diagnostic
from app.services.test_case_runner import has_active_case_run, has_running_case_run_row

logger = logging.getLogger(__name__)
TARGET = 'fixed_route_power_acquisition'
_running: dict[UUID, tuple[asyncio.Task, asyncio.Event]] = {}


class AcquisitionBusy(ValueError):
    pass


def resolve_configuration(db: Session, lab_id: UUID, request: FixedRouteRequest, hal, *, batch_item_context=None):
    """保存、绑定及装载驱动同次核对；零I/O，不将配置声明升级成实物确认。"""
    lab = db.get(LabProfile, lab_id)
    if lab is None or not lab.is_active:
        raise ValueError('实验室配置不存在或已停用')
    try:
        if batch_item_context is not None:
            from app.services.calibration.route_batch_jobs import validated_batch_item
            item = validated_batch_item(db, lab_id, request, batch_item_context)
            snapshot = build_selected_route_calibration_scope(db, lab_id, request.operating_mode,
                topology_id=item.route_selection.topology_id, chain_id=item.request.chain_id)
        else:
            snapshot = build_calibration_scope(db, lab_id, request.operating_mode, topology_id=request.topology_id)
    except LookupError as exc:
        raise ValueError(str(exc)) from exc
    if snapshot.digest != request.configuration_digest:
        raise ValueError('采集配置已变化，请重新读取并确认所选链；这不改变校准就绪状态')
    topology_id = request.topology_id or snapshot.payload.topology.get('id')
    if topology_id is None:
        raise ValueError('没有可供采集的已保存拓扑')
    try:
        if batch_item_context is not None:
            from app.services.calibration.route_calibration import resolve_explicit_route_selection
            routes = [resolve_explicit_route_selection(db, lab_id, UUID(str(topology_id)), request.operating_mode,
                item.request.chain_id, item.route_selection.connection_ids)]
        else:
            routes = list_route_selections(db,lab_id,UUID(str(topology_id)),request.operating_mode)
    except LookupError as exc:
        raise ValueError(str(exc)) from exc
    matches = [r for r in routes if r.chain_id == request.chain_id]
    if len(matches) != 1:
        raise ValueError('所选链不存在或重复，不能确定采集通路')
    chain = matches[0]
    if request.route_digest is not None and request.route_digest != chain.route_digest:
        raise ValueError('所选完整通路已变化，请重新读取并确认接线；不会自动要求重新校准')
    ce_category = db.query(InstrumentCategory).filter_by(category_key='channelEmulator').one_or_none()
    if ce_category is None or not ce_category.is_active:
        raise ValueError('F64类别不存在或已停用；不会自动启用或控制残留驱动')
    chamber = snapshot.payload.chamber
    if not chamber['freq_min_mhz'] <= request.frequency_mhz <= chamber['freq_max_mhz']:
        raise ValueError('工作频率不在暗室已声明频段内')
    ce_binding = resolve_channel_emulator_binding(db, hal, lab, lock=True)
    if ce_binding.manifest is None or ce_binding.manifest.adapter_id != 'propsim_f64':
        raise ValueError('本采集方法只接受实验室明确绑定的F64')
    ce = hal.drivers.get('channelEmulator')
    sa = hal.drivers.get('signalAnalyzer')
    if ce is None or sa is None:
        raise ValueError('F64或分析仪尚未加载，请检查分类HAL激活结果')
    category = db.query(InstrumentCategory).filter_by(category_key='signalAnalyzer').one_or_none()
    if category is None or not category.is_active:
        raise ValueError('分析仪类别不存在或已停用；不会自动启用')
    model = db.get(InstrumentModel, category.selected_model_id) if category.selected_model_id else None
    connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
    bindings = [b for b in lab.instrument_bindings or [] if isinstance(b, dict) and b.get('category_id') == str(category.id)]
    if model is None or connection is None or len(bindings) != 1:
        raise ValueError('分析仪缺少唯一的实验室绑定、型号或连接')
    binding = bindings[0]
    if (str(model.id) != str(binding.get('instrument_model_id')) or
        connection.endpoint != binding.get('connection_endpoint') or category.driver_mode != binding.get('driver_mode')):
        raise ValueError('保存的分析仪配置与实验室绑定不一致，请单独同步实验室配置')
    if get_real_driver_class('signalAnalyzer', model.model) is not RealRsFsvaDriver:
        raise ValueError('首批只支持已核对的FSVA3000分析仪')
    if is_mock_driver(ce) != is_mock_driver(sa):
        raise ValueError('不允许真实与模拟仪器混合采集')
    if not is_mock_driver(sa):
        if category.driver_mode == 'mock' or type(sa) is not RealRsFsvaDriver:
            raise ValueError('已加载分析仪与所选模式/型号不一致')
        config = dict(endpoint=connection.endpoint, ip=connection.controller_ip, port=connection.port, protocol=connection.protocol)
        config.update(connection.connection_params or {})
        host, port, resource, error = resolve_configured_tcpip_connection(config)
        if error or not host or (host, port, resource) != (sa._connection_host, sa._connection_port, sa._connection_resource):
            raise ValueError('已加载分析仪连接与保存连接不一致')
    elif category.driver_mode == 'real':
        raise ValueError('分析仪配置为真实模式，但只加载了模拟驱动')
    output = int(RealPropsimF64Driver._ce_port_to_output_num(chain.ce_port))
    # 是首批支持的F64物理口集合，不接受解析器的历史宽松正整数域。
    if not 1 <= output <= 32:
        raise ValueError('F64输出口必须为1到32')
    return dict(snapshot=snapshot.model_dump(mode='json'), chain=dict(chain_id=chain.chain_id,ce_port=chain.ce_port,
        probe_id=chain.probe_id,polarization=chain.polarization), route_selection=chain.model_dump(mode='json'),
        binding=ce_binding.model_dump(mode='json'), analyzer_binding=binding,
        analyzer_connection_id=str(connection.id), analyzer_instrument_id=sa.instrument_id), output, ce, sa


def _sequence_evidence(result: FixedRouteResult, duration_ms: int = 0):
    """遵守共享诊断详情契约；完整采集载荷只存于既有extra，不另造读取入口。"""
    verdict = ('ABORTED' if result.status == 'cancelled' else 'BLOCKER'
        if result.status in ('failed', 'cleanup_unconfirmed', 'interrupted', 'incomplete') else 'UNDETERMINED')
    summary = '固定通路自动采集记录（未签发校准资格）'
    if result.status == 'simulated':
        summary = '模拟流程完成（无实测功率、无校准资格）'
    elif result.status == 'cleanup_unconfirmed':
        summary = '可能仍在发射：停止未确认'
    return SequenceEvidence(summary=summary, duration_ms=duration_ms,
        log=([result.error] if result.error else []) + result.missing_items, steps=[],
        extra={'verdict': verdict, 'fixed_route_acquisition': result.model_dump(mode='json')}).model_dump(mode='json')


def build_record_row(result: FixedRouteResult) -> DiagnosticRun:
    """单项与批子项共用审计封套，调用者决定事务边界。"""
    return DiagnosticRun(id=result.run_id, kind='scpi_sequence', lab_profile_id=result.lab_profile_id,
        target_name=TARGET, params=result.request.model_dump(mode='json'), success=False,
        sequence_evidence=_sequence_evidence(result))


def save_record_result(row: DiagnosticRun, result: FixedRouteResult, duration_ms: int = 0):
    row.duration_ms = duration_ms
    row.sequence_evidence = _sequence_evidence(result, duration_ms)
    row.success = result.status in ('completed', 'simulated')
    row.error_message = result.error


def record(row: DiagnosticRun, *, batch_context=None) -> FixedRouteRecord:
    value = None
    try:
        envelope = SequenceEvidence.model_validate(row.sequence_evidence)
        value = FixedRouteResult.model_validate(envelope.extra.get('fixed_route_acquisition'))
        if value.run_id != row.id or value.lab_profile_id != row.lab_profile_id:
            value = None
    except (ValidationError, TypeError):
        pass  # 缺损历史返回incomplete；不从当前配置或仪器回填。
    status = value.status if value else 'incomplete'
    batch_id = value.states.get('batch_job_id') if value else None
    active = (batch_context or {}).get('active') is True if batch_id else row.id in _running
    if batch_id and (batch_context or {}).get('finalized') is not True:
        value = value.model_copy(deep=True)
        if value.states.get('f64_control_released') is True:
            value.states['f64_control_released'] = None
        value.states['batch_finalization_verified'] = False
    elif batch_id:
        value = value.model_copy(deep=True)
        value.states['batch_finalization_verified'] = True
    if status == 'running' and not active:
        status = 'interrupted'
        value = value.model_copy(update={'status': status, 'cleanup_confirmed': None,
            'net_loss_db': None, 'error': '服务已中断本次采集，未自动续跑；仪器停发状态需现场确认'})
    stamp = row.run_at if row.run_at.tzinfo is not None else row.run_at.replace(tzinfo=timezone.utc)
    return FixedRouteRecord(run_id=row.id, lab_profile_id=row.lab_profile_id, run_at=stamp, status=status,
        result=value,batch_context=batch_context if batch_id else None)


async def start(db: Session, lab_id: UUID, request: FixedRouteRequest):
    if has_active_case_run() or has_running_case_run_row(db):
        raise AcquisitionBusy('已有测试执行在运行，不能开始校准采集')
    token = try_acquire_unsafe_diagnostic(TARGET)
    if token is None:
        raise AcquisitionBusy('已有测试或诊断占用仪器，请等待结束')
    try:
        config, _, _, _ = resolve_configuration(db, lab_id, request, get_hal_service())
        run_id = uuid4()
        result = FixedRouteResult(version=2, run_id=run_id, lab_profile_id=lab_id, request=request, configuration=config)
        row = build_record_row(result)
        db.add(row)
        db.commit()
        db.refresh(row)
        cancel = asyncio.Event()
        task = asyncio.create_task(_execute(result, token, cancel))
        _running[run_id] = (task, cancel)
        return record(row)
    except BaseException:
        release_unsafe_diagnostic(token)
        raise


async def _execute(result, token, cancel):
    """独立DB session，只在进入控制权前读配置；采集中不补当前值。"""
    started_at = perf_counter()
    try:
        if cancel.is_set():
            result.status, result.error = 'cancelled', '采集开始前已取消，未操作仪器'
            return
        selected = None
        def validate(hal):
            nonlocal selected
            with SessionLocal() as db:
                try:
                    if has_active_case_run() or has_running_case_run_row(db):
                        return '测试已开始，停止本次采集'
                    selected = resolve_configuration(db, result.lab_profile_id, result.request, hal)
                    expected_route = result.configuration.get('route_selection')
                    if expected_route and selected[0].get('route_selection', {}).get('route_digest') != expected_route.get('route_digest'):
                        return '进入仪器控制前完整路径或参考接线变化，未开始采集；请重新读取并确认'
                except ValueError as exc:
                    return str(exc)
            return None

        async with instrument_test_lease(f'calibration:{result.run_id}', control_f64=True,
            control_uxm=False, enable_monitoring=False, restore_f64_alignment=False,
            validate_before_remote=validate) as lease:
            if selected is None:
                raise ValueError('未完成采集配置核对')
            result.configuration, output, ce, sa = selected
            result.states['lease_id'] = lease.lease_id
            await collect_fixed_route(ce, sa, result, output_port=output, cancel=cancel)
        result.states['f64_control_released'] = lease.channel_emulator_transport_released_confirmed
    except (Exception, asyncio.CancelledError) as exc:
        if result.status != 'cleanup_unconfirmed':
            result.status = 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed'
        detail = str(exc) or '采集已被服务取消'
        result.error = f'{result.error}；归还控制权或采集失败：{detail}' if result.error else detail
        result.net_loss_db = None
    finally:
        # 持有互斥直到最终记录保存，失败仍释放，日志不声称已持久化成功。
        try:
            with SessionLocal() as db:
                row = db.get(DiagnosticRun, result.run_id)
                if row is None:
                    raise RuntimeError('采集审计记录丢失')
                save_record_result(row, result, int((perf_counter() - started_at) * 1000))
                db.commit()
        except Exception:
            logger.exception('PC-04采集结果保存失败：%s', result.run_id)
        finally:
            _running.pop(result.run_id, None)
            release_unsafe_diagnostic(token)


def request_cancel(run_id: UUID):
    item = _running.get(run_id)
    if item is None:
        raise AcquisitionBusy('本次采集已结束或服务已重启，不能声称已停止仪器；请查看结果或现场确认')
    item[1].set()


async def shutdown_fixed_route_jobs():
    """正常服务退出先请求停止并等记录落盘，再允许HAL关闭连接。"""
    tasks = []
    for task, cancel in list(_running.values()):
        cancel.set()
        tasks.append(task)
    if tasks:
        outcome = await await_completion_despite_cancellation(asyncio.gather(*tasks, return_exceptions=True))
        if outcome.error:
            raise outcome.error
