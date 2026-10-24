"""PC-04A：固定通路的局部采集方法，不调用开关、不写旧证书或补偿。

F64来源：Propsim User Reference Rev10.2 §20.4.5.22/.20、§20.4.9.1～.9/.26。
接收端来源及完整测量事务见RealRsFsvaDriver.capture_fixed_route_power。
"""
import asyncio
import math
import statistics

from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.rs_fsva import RealRsFsvaDriver, fixed_route_spectrum_commands
from app.schemas.fixed_route_acquisition import FixedRouteResult, FixedRouteSample, PowerExchange
from app.services.instrument_hal_service import is_mock_driver
from app.services.instrument_test_lease import await_completion_despite_cancellation


async def _settle():
    # §20.4.5.22：输出实测固定0.5秒平均窗口；不是硬件同步或设备内部采样时间证明。
    await asyncio.sleep(0.5)


def _number(raw):
    value = float(raw.strip())
    if not math.isfinite(value):
        raise ValueError('仪器未返回有限功率数值')
    return value


async def collect_fixed_route(ce, sa, result: FixedRouteResult, *, output_port: int, cancel: asyncio.Event):
    """调用者持有实验控制权；只使用本次传入的驱动和冻结配置。"""
    request = result.request
    tone_id = 'pc04_' + result.run_id.hex
    tone_commands = RealPropsimF64Driver.calibration_tone_commands(
        str(output_port), tone_id, request.frequency_mhz * 1e6, request.requested_power_dbm)
    # §20.4.9.3/.2：先禁用再移除，只针对本次唯一ID。
    stop_commands = [f'OUTPut:INTERFerence:STatus {tone_id},0', f'OUTPut:INTERFerence:REMove {tone_id}']
    power_command = f'OUTPut:MEASure:RESult:GET? {output_port},1'  # §20.4.5.22，绝不省略参数1。
    simulated = is_mock_driver(ce) or is_mock_driver(sa)
    started = False

    def check_cancel():
        if cancel.is_set():
            raise asyncio.CancelledError()

    async def query(command):
        event = PowerExchange(instrument_id=ce.instrument_id, command=command)
        result.exchanges.append(event)
        try:
            event.response = await ce._query(command)
            if not isinstance(event.response, str):
                raise ValueError(f'F64回复缺失：{command}')
            return event.response.strip()
        except Exception as exc:
            event.error = str(exc)
            raise

    async def errors():
        # §20.4.1 SYSTem:ERRor?：保留每条原文；未知、非零、未排尽都不当成功。
        entries = []
        for _ in range(20):
            raw = await query('SYSTem:ERRor?')
            code = int(raw.split(',', 1)[0])
            if code == 0:
                if entries:
                    raise ValueError('F64错误队列：' + '; '.join(entries))
                return
            entries.append(raw)
        raise ValueError('F64错误队列未排尽')

    async def read(command):
        raw = await query(command)
        await errors()
        return raw

    async def write(command):
        event = PowerExchange(instrument_id=ce.instrument_id, command=command)
        result.exchanges.append(event)
        try:
            await ce._write(command)
            await errors()
        except Exception as exc:
            event.error = str(exc)
            raise

    async def source_power():
        for attempt in range(3):
            check_cancel()
            raw = await read(power_command)
            if raw.lower() != 'not ready':
                return _number(raw)
            if attempt < 2:
                await _settle()
        raise ValueError('F64输出口实测仍未就绪；不使用设定值或旧读数')

    try:
        check_cancel()
        if simulated:
            if not (is_mock_driver(ce) and is_mock_driver(sa)):
                raise ValueError('不允许混合真实仪器与模拟仪器进行校准采集')
            for command in [*tone_commands, power_command, *fixed_route_spectrum_commands(request.frequency_mhz * 1e6), *stop_commands]:
                check_cancel()
                result.exchanges.append(PowerExchange(instrument_id=ce.instrument_id if command.startswith('OUTPut:') else sa.instrument_id,
                    command=command, simulated=True))
                await asyncio.sleep(0.05)
            result.status = 'simulated'
            result.cleanup_confirmed = None
            result.missing_items.append('模拟流程未连接仪器，不含真实功率、损耗或停发确认')
            return result
        if type(ce) is not RealPropsimF64Driver or type(sa) is not RealRsFsvaDriver:
            raise ValueError('首批只支持真实PROPSIM F64与FSVA3000')
        try:
            async with ce._scpi_lock:
                await errors()
                idn = await read('*IDN?')  # §20.4.1.5，型号字段不按其它字段包含字样判定。
                if len(idn.split(',')) != 4 or idn.split(',')[1].strip().upper() not in ('F8800A', 'PROPSIM F64'):
                    raise ValueError('实际仪器不是PROPSIM F64')
                result.states['f64_identity'] = idn
                # §20.4.3.14：STOPPED时读数可能冻结，不得充当本次实测。
                if await read('DIAG:SIMU:STATE?') != 'RUNNING':
                    raise ValueError('请先准备并运行专用校准仿真；停止状态不读取旧功率')
                loss = _number(await read(f'OUTPut:LOSS:GET? {output_port}'))
                result.states['output_loss_db'] = loss
                if loss != 0:
                    raise ValueError('F64输出损耗非零，连接器功率参考位置未核实；不自动清零或猜测换算')
                # §20.4.9.5：0表示没有干扰源；避免删除别人的单音或测成混合总功率。
                if await read('OUTPut:INTERFerence:GET?') != '0':
                    raise ValueError('仿真中已有干扰源，请准备专用校准仿真；不会删除或覆盖已有源')
                if not ce.has_interference_generator:
                    raise ValueError('F64内置单音许可尚未确认')
                # PC-03同源命令，只记录当时状态；不是资格放行条件。
                for key, command in [('auto_alignment', 'SYSTem:CALIBration:VALid?'),
                    ('user_alignment', 'SYSTem:CALIBration:USER:GET?'),
                    ('output_gain_db', f'OUTPut:GAIN:CH? {output_port}')]:
                    result.states[key] = await read(command)
                check_cancel()
                # 首条ADD前即标记可能创建；任何写失败/取消也尝试清理同一唯一ID。
                started = True
                for command in tone_commands:
                    check_cancel()
                    await write(command)
                await _settle()
                for _ in range(request.sample_count):
                    check_cancel()
                    before = await source_power()
                    outcome = await await_completion_despite_cancellation(asyncio.to_thread(
                        sa.capture_fixed_route_power, request.frequency_mhz * 1e6, result.exchanges))
                    if outcome.error:
                        raise outcome.error
                    if outcome.delayed_cancellation:
                        raise outcome.delayed_cancellation
                    check_cancel()
                    after = await source_power()
                    result.samples.append(FixedRouteSample(source_before_dbm=before, received_dbm=outcome.value, source_after_dbm=after))
                    await _settle()
                if await read('DIAG:SIMU:STATE?') != 'RUNNING':
                    raise ValueError('采集期间F64已停止，不能确认本次功率')
                if _number(await read(f'OUTPut:LOSS:GET? {output_port}')) != loss:
                    raise ValueError('采集期间F64输出损耗设置变化，不能确认同一功率参考位置')
                check_cancel()
                if request.receive_cable_loss_db is None or not request.receive_cable_source:
                    result.missing_items.append('缺少本频率的接收线缆损耗及来源，未计算整条路径损耗')
                else:
                    losses = [(s.source_before_dbm + s.source_after_dbm) / 2 -
                        (s.received_dbm + request.receive_cable_loss_db) for s in result.samples]
                    result.net_loss_db = _number(str(statistics.mean(losses)))
                    result.sample_std_db = _number(str(statistics.stdev(losses)))
                result.status = 'completed'
        finally:
            if started:
                async def cleanup():
                    # 安全收尾运行在独立任务中。先退出父任务事务锁，再由收尾任务
                    # 持锁，否则可重入锁的“同任务”约束会把停止命令永久卡住。
                    async with ce._scpi_lock:
                        failures = []
                        for command in stop_commands:
                            try:
                                await write(command)
                            except Exception as exc:
                                failures.append(str(exc))
                        if failures:
                            raise RuntimeError('; '.join(failures))
                stopped = await await_completion_despite_cancellation(cleanup())
                result.cleanup_confirmed = stopped.error is None
                if stopped.error:
                    result.status, result.error = 'cleanup_unconfirmed', f'可能仍在发射；停止未确认：{stopped.error}'
                    result.net_loss_db = None
                elif stopped.delayed_cancellation:
                    result.status, result.net_loss_db = 'cancelled', None
    except (Exception, asyncio.CancelledError) as exc:
        if result.status != 'cleanup_unconfirmed':
            result.status = 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed'
            result.error = '已请求取消' if isinstance(exc, asyncio.CancelledError) else str(exc)
        result.net_loss_db = None
    return result
