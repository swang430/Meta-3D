"""批项只消费冻结映射；写成功与本次位置报告均必需，非RF现场验收。"""
import asyncio
import re
from datetime import datetime, timezone

from app.hal.rf_switch import EtslSwitchDriver, build_emcenter_switch_command
from app.hal.base import resolve_configured_tcpip_connection
from app.services.instrument_hal_service import is_mock_driver


def _connection_matches(driver, step):
    """复用纯地址规范化；比较实际生效字段，不构造/连接第二个驱动。"""
    config=step.connection_config
    if not config:
        return False
    host,port,resource,error=resolve_configured_tcpip_connection(config)
    endpoint_host,endpoint_port,endpoint_resource,endpoint_error=resolve_configured_tcpip_connection({'endpoint':step.endpoint})
    transport=str(config.get('transport') or 'vxi11').lower()
    style=str(config.get('command_style') or 'raw').lower()
    terminator=str(config.get('line_terminator','cr')).lower()
    return (not error and not endpoint_error and host==endpoint_host==driver._connection_host
        and (endpoint_port is None or endpoint_port==port)
        and (endpoint_resource is None or endpoint_resource==resource)
        and port==driver._connection_port and resource==driver._connection_resource
        and transport in ('raw','vxi11') and transport==driver._transport
        and style=='raw' and style==driver._command_style
        and terminator in EtslSwitchDriver._TERMINATOR_MAP
        and EtslSwitchDriver._TERMINATOR_MAP[terminator]==driver._line_terminator)


async def apply_batch_switch_steps(hal, frozen_steps, receipt_sink):
    """返回False必须阻止测量；sink先持久化，失败不得继续下发。

    仅允许真实已核验HAL；模拟分支由协调器标明“模拟人工步骤”。
    身份查询复用emcenter_switch_health既有命令，不发探测/复位/清错。
    """
    for step in frozen_steps:
        driver = hal.drivers.get('rfSwitch')
        base = dict(path_name=step.path_name, node_id=step.node_id,
            connection_id=str(step.connection_id), category_id=str(step.category_id),
            instrument_model_id=str(step.instrument_model_id), endpoint=step.endpoint,
            driver_id=getattr(driver, 'instrument_id', None), simulated=is_mock_driver(driver),
            host_time=datetime.now(timezone.utc).isoformat(), error=None, raw=None, command=None)
        def emit(**extra):
            receipt_sink({**base, 'host_time':datetime.now(timezone.utc).isoformat(), **extra})
        mapping = step.mapping
        relay = mapping.get('switch_id', mapping.get('relay'))
        kind = mapping.get('relay_type')
        target = mapping.get('output_port', mapping.get('position'))
        valid_target = ((kind == 'spdt' and type(target) is str and target in ('NC', 'NO')) or
            (kind == 'sp6t' and type(target) is int and 1 <= target <= 6))
        if (type(driver) is not EtslSwitchDriver or is_mock_driver(driver) or step.driver_mode != 'real'
            or driver._connection_config_error or not _connection_matches(driver,step)
            or driver._mappings.get(step.path_name) != mapping
            or not isinstance(relay, str) or not re.fullmatch(r'[1-7]:INT_RELAY_[A-D]', relay)
            or (kind == 'sp6t' and relay[-1] not in 'AB')
            or not valid_target or type(mapping.get('input_port')) is not int):
            emit(error='开关绑定、驱动、连接或完整映射资格不一致')
            return False
        try:
            # Part #1801188 Rev A p6 Common General：*IDN?及<slot>:*IDN?。
            for command, product in (('*IDN?', 'EMCenter'), (f'{relay[0]}:*IDN?', 'EMSwitch')):
                raw = await driver._send_command(command)
                error = None if isinstance(raw, str) and raw.startswith('ETS-Lindgren') and product in raw and 'ERROR' not in raw else '开关身份未知'
                emit(kind='identity', command=command, raw=raw, error=error)
                if error:
                    return False
            # 同原health序列裸查询；Part #1801188 Rev A p11：仅0/1，ERROR不当0。
            command = 'INTLK? SAFETYRELAY'
            raw = await driver._send_command(command)
            emit(kind='interlock', command=command, raw=raw, error=None if raw == '0' else '互锁激活或未知')
            if raw != '0':
                return False
            # p9 SPDT写NC/NO；p12 SP6T写1..6，同HAL builder，不额外拼模拟命令。
            command = build_emcenter_switch_command(relay, target)
            written = await driver.set_mapped_path(step.path_name)
            emit(kind='write', command=command, raw=None, write_return=written,
                error=None if written is True else '开关写操作失败')
            if written is not True:
                return False
            receipt = await driver.read_mapped_path_receipt(step.path_name)
            if receipt['error'] is None and receipt['position'] != target:
                receipt['error'] = '本次位置回读不匹配冻结目标（0全开不等于选通）'
            emit(**receipt, kind='position')
            if receipt['error']:
                return False
        except asyncio.CancelledError:
            emit(command=command,error='开关操作被取消，未开始测量')
            raise
        except Exception as exc:
            emit(command=command,error=f'开关操作失败：{exc}')
            return False
    return True
