"""PC-03A 只读 F64 状态；命令出处为 Propsim User Reference Rev 10.2。

组频率不是变频后的物理口频率。读取成功不证明校准有效；不执行对齐或写补偿。
此模块的 read_state 由持有诊断租约和 SCPI 事务锁的入口调用。
"""
from datetime import datetime, timezone
import math

from app.diagnostics.sequences.propsim_f64_license_truth import _Recorder, _parse_valid
from app.diagnostics.sequences.propsim_f64_state_machine import classify_state
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.schemas.f64_calibration_state import F64CalibrationState, F64StateField, F64StateRequest
from app.services.instrument_hal_service import is_mock_driver
from app.diagnostics.protocol import SequenceMetadata, SequenceRunResult, SequenceStepResult
from app.schemas.diagnostic_evidence import SequenceStepEvidence
from dataclasses import asdict


metadata = SequenceMetadata(
    name='F64 对齐与补偿状态记录',
    description='只读指定组及输入/输出端口，保留原始回复；不自动校准、不写补偿、不改变就绪状态。',
    required_categories=['channelEmulator'], safe_during_test=False,
    params_schema=[{'name': key, 'label': label, 'type': 'number'} for key, label in (
        ('group_id', '信道组编号'), ('input_port', '物理输入口编号'), ('output_port', '物理输出口编号'))],
)


async def run(ctx, hal, params, *, log, resolved_binding):
    request = F64StateRequest.model_validate(params)
    driver = hal.drivers.get('channelEmulator')
    if driver is None or resolved_binding is None:
        raise ValueError('缺少已核对的 F64 实验室绑定')
    state = await read_state(driver, request, resolved_binding.binding_digest)
    success = state.acquisition_status == 'simulated' or (
        not state.warnings and not state.query_evidence.get('failed_queries')
        and all(item.status == 'confirmed' for item in state.fields
            if item.key not in ('output_adjust_mode', 'user_info', 'auto_name')))
    summary = '模拟记录，不含真实仪器读数' if state.acquisition_status == 'simulated' else '已记录当时回复；未知项需人工复核，不代表校准有效'
    log(summary)
    return SequenceRunResult(success=success, summary=summary,
        steps=[SequenceStepResult(**item.model_dump()) for item in state.steps],
        extra={'calibration_state': state.model_dump(mode='json'),
               'binding': resolved_binding.model_dump(mode='json'), 'formal_eligible': False})


_FIELDS = {
    'instrument_identity': ('仪器身份', '20.4.1.5'),
    'emulation_state': ('仿真状态', '20.4.3.14'),
    'auto_in_use': ('自动校准正在使用', '20.4.2.13'),
    'auto_valid': ('仪器返回的自动校准有效标志', '20.4.2.13'),
    'auto_name': ('当前自动校准名称', '20.4.2.11'),
    'user_enabled': ('用户对齐已启用', '20.4.2.19'),
    'user_name': ('用户对齐名称', '20.4.2.19'),
    'user_info': ('用户对齐信息', '20.4.2.21'),
    'group_inputs': ('组内输入端口', '20.4.7.2'),
    'group_outputs': ('组内输出端口', '20.4.7.3'),
    'group_channels': ('组内逻辑信道', '20.4.7.4'),
    'group_bandwidth_mhz': ('信道组带宽（MHz）', '20.4.7.7'),
    'group_frequency_mhz': ('信道组中心频率（MHz，非物理口频率）', '20.4.6.2'),
    'input_loss_db': ('输入损耗设置（dB）', '20.4.4.21'),
    'output_loss_db': ('输出损耗设置（dB）', '20.4.5.20'),
    'output_gain_db': ('输出增益设置（dB）', '20.4.5.7'),
    'input_level_control_enabled': ('输入电平自动控制已启用', '20.4.4.49'),
    'input_level_control_mode': ('输入电平控制模式', '20.4.4.51'),
    'output_adjust_mode': ('输出调整模式', '未核实读取命令，不查询'),
}


def validate_before_lease(params):
    F64StateRequest.model_validate(params)


def _number(raw):
    value = float(raw.strip())
    if not math.isfinite(value):
        raise ValueError('不是有限数值')
    return value


def _ports(raw):
    parts = raw.strip().split(',')
    if not parts or any(not p.strip().isdigit() or int(p) <= 0 for p in parts):
        raise ValueError('不是正整数列表')
    values = [int(p) for p in parts]
    if len(set(values)) != len(values):
        raise ValueError('端口或信道重复')
    return values


def _choice(raw, allowed):
    value = raw.strip()
    if value not in allowed:
        raise ValueError('不符合手册枚举')
    return allowed[value]


async def read_state(driver, request: F64StateRequest, binding_digest: str):
    """只消费本次实际回复，不从驱动缓存或实验室配置填补缺失值。"""
    simulated = is_mock_driver(driver)
    found = {key: F64StateField(key=key, label=label,
        source_reference=f'Propsim User Reference Rev 10.2 §{section}' if section[0].isdigit() else section,
        status='simulated' if simulated else 'unknown',
        detail='模拟模式，不编造仪器读数' if simulated else '前置条件未满足或尚未读取')
        for key, (label, section) in _FIELDS.items()}
    result = F64CalibrationState(requested=request, captured_at=datetime.now(timezone.utc),
        binding_digest=binding_digest, instrument_id=driver.instrument_id,
        acquisition_status='simulated' if simulated else 'recorded', fields=list(found.values()))
    if simulated:
        return result
    if not isinstance(driver, RealPropsimF64Driver):
        raise ValueError('只允许读取已绑定的 PROPSIM F64 驱动')
    recorder = _Recorder(driver._query, lambda message: None)

    async def read(key, command, parse=lambda raw: raw.strip()):
        parsed = None

        def validate(raw):
            nonlocal parsed
            try:
                parsed = parse(raw)
                if parsed is None:
                    return '回复无法解析'
            except (ValueError, TypeError, OverflowError) as error:
                return f'回复无法解析：{error}'
            return None

        raw = await recorder.read(command, lambda value: '已读取（不代表校准有效）', validate=validate)
        step = recorder.steps[-1]  # read 必定追加且仅追加本查询的步骤。
        field = found[key]
        field.raw, field.detail = step.raw, step.detail
        if raw is not None:
            field.status, field.value = 'confirmed', parsed
        return field.value

    if not await recorder.archive_opening_residue():
        result.warnings.append('开场错误队列不可判，未继续读取')
        result.query_evidence = recorder.evidence()
        result.steps = [SequenceStepEvidence(**asdict(step)) for step in recorder.steps]
        return result
    # §20.4.1.5 *IDN?：manufacturer,model,serial,revision；仅核对model位置。
    def identity(raw):
        value = raw.strip()
        parts = value.split(',')
        if len(parts) != 4 or parts[1].strip().upper() not in ('F8800A', 'PROPSIM F64'):
            raise ValueError('仪器身份不是 F64')
        return value
    if await read('instrument_identity', '*IDN?', identity) is None:
        result.warnings.append('F64 身份未确认，未继续读取')
    else:
        # §20.4.3.14：仿真状态；本片仅在 STOPPED 稳定状态查询仿真内设置。
        state = await read('emulation_state', 'DIAG:SIMU:STATE?',
            lambda raw: classify_state(raw)[0])
        # §20.4.2.13：<in use 0/1>,<valid 0/1>；两个标志不得互相推导。
        pair = await read('auto_in_use', 'SYSTem:CALIBration:VALid?',
            lambda raw: list(_parse_valid(raw)) if None not in _parse_valid(raw) else None)
        found['auto_valid'].raw = found['auto_in_use'].raw
        found['auto_valid'].detail = found['auto_in_use'].detail
        if pair is not None:
            found['auto_in_use'].value = pair[0]
            found['auto_valid'].status, found['auto_valid'].value = 'confirmed', pair[1]
            if pair[0]:
                # §20.4.2.11：当前使用的校准名；未使用时不盲查。
                await read('auto_name', 'SYSTem:CALIBration:GET?', lambda raw: raw.strip() or None)
        # §20.4.2.19 原文：empty string if no user alignment is enabled。
        name = await read('user_name', 'SYSTem:CALIBration:USER:GET?')
        found['user_enabled'].raw = found['user_name'].raw
        found['user_enabled'].detail = found['user_name'].detail
        if name is not None:
            found['user_enabled'].status, found['user_enabled'].value = 'confirmed', bool(name)
            if name:
                # §20.4.2.21：已启用用户对齐的信息。
                await read('user_info', 'SYSTem:CALIBration:USER:INFO?')
        if state == 'STOPPED':
            group = request.group_id
            # §20.4.7.2/.3/.4：各返回本组物理输入、物理输出、逻辑信道列表。
            inputs = await read('group_inputs', f'GROup:INPUTS:GET? {group}', _ports)
            outputs = await read('group_outputs', f'GROup:OUTputs:GET? {group}', _ports)
            channels = await read('group_channels', f'GROup:CHannels:GET? {group}', _ports)
            # §20.4.7.7：信道组带宽，单位 MHz。
            await read('group_bandwidth_mhz', f'GROup:BANDWidth:GET? {group}', _number)
            if channels:
                # §20.4.6.2：指定逻辑信道所属组的中心频率，单位 MHz。
                await read('group_frequency_mhz', f'CALCulate:FILTer:CENTer:CH? {channels[0]}', _number)
            if inputs and request.input_port in inputs:
                port = request.input_port
                # §20.4.4.21：输入损耗设置，dB；不是实测输入功率。
                await read('input_loss_db', f'INPut:LOSS:GET? {port}', _number)
                # §20.4.4.49：输入自动控制启用 0/1。
                await read('input_level_control_enabled', f'INPut:LEVel:AUTO:ENAble? {port}', lambda raw: _choice(raw, {'0': False, '1': True}))
                # §20.4.4.51：1 防削顶，2 AGC，3 AGC 保持路损。
                await read('input_level_control_mode', f'INPut:LEVel:AUTO:MODE? {port}', lambda raw: _choice(raw, {'1': 1, '2': 2, '3': 3}))
            if outputs and request.output_port in outputs:
                port = request.output_port
                # §20.4.5.20：输出损耗设置，dB；不是实测输出功率。
                await read('output_loss_db', f'OUTPut:LOSS:GET? {port}', _number)
                # §20.4.5.7：指定物理输出端口的增益，dB。
                await read('output_gain_db', f'OUTPut:GAIN:CH? {port}', _number)
    if not await recorder.residue():
        result.warnings.append('收尾错误队列不可判或有残留，请复核本次读取')
    result.query_evidence = recorder.evidence()
    result.steps = [SequenceStepEvidence(**asdict(step)) for step in recorder.steps]
    return result
