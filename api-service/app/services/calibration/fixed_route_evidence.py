"""只核对既有固定通路采集的完整证据，不发仪器指令、不签认证。"""
import csv
import math
import statistics

from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.rs_fsva import FsvaScpi, fixed_route_spectrum_commands
from app.schemas.fixed_route_acquisition import FixedRouteResult
from app.schemas.route_calibration import RouteSelection


def has_explicit_mock_input(result: FixedRouteResult) -> bool:
    return (result.request.mock_input is not None or
            result.simulation_input_source == 'operator_supplied_synthetic')


def check_fixed_route_evidence(result: FixedRouteResult) -> tuple[str,list[str]]:
    """白名单沿原采集事务的顺序及数值核对，不从completed布尔倒推真实来源。"""
    if has_explicit_mock_input(result) or result.status=='simulated' or any(e.simulated for e in result.exchanges):
        return 'simulated',['simulated_measurement']
    try:
        def require(condition,code):
            if not condition:
                raise ValueError(code)

        def number(value):
            require(type(value) in (int,float,str),'invalid_number')
            parsed=float(value)
            require(math.isfinite(parsed),'invalid_number')
            return parsed

        def equal(left,right):
            # 仅消除浮点重算舍入差异，不是不确定度预算或计量合格容差。
            return math.isclose(number(left),number(right),rel_tol=1e-12,abs_tol=1e-9)

        require(result.version==2,'missing_complete_route_snapshot')
        require(result.status=='completed' and result.error is None,'capture_not_completed')
        require(result.cleanup_confirmed is True and result.states.get('f64_control_released') is True,'cleanup_not_confirmed')
        require(len(result.samples)==result.request.sample_count and bool(result.exchanges),'missing_samples_or_exchanges')
        require(result.request.receive_cable_loss_db is not None and bool(result.request.receive_cable_source),'missing_receive_cable_source')
        route=RouteSelection.model_validate(result.configuration.get('route_selection'))
        chain=result.configuration.get('chain',{})
        require(chain.get('chain_id')==route.chain_id and chain.get('ce_port')==route.ce_port,'frozen_chain_mismatch')
        binding=result.configuration.get('binding',{})
        runtime=binding.get('runtime_driver',{})
        require(binding.get('execution_mode')=='real' and runtime.get('simulated') is False and
            binding.get('lab_profile_id')==str(result.lab_profile_id),'unverified_instrument_binding')
        analyzer=result.configuration.get('analyzer_binding',{})
        require(analyzer.get('driver_mode') in ('real','auto'),'unverified_analyzer_binding')
        sa_id=result.configuration.get('analyzer_instrument_id')
        require(isinstance(sa_id,str) and bool(sa_id),'missing_analyzer_identity')
        ce_ids={e.instrument_id for e in result.exchanges if e.instrument_id!=sa_id}
        require(len(ce_ids)==1,'ambiguous_instrument_identity')
        ce_id=next(iter(ce_ids))
        events=result.exchanges
        require(all(e.error is None for e in events),'exchange_error')
        require(all(events[i].host_time<=events[i+1].host_time for i in range(len(events)-1)),'invalid_exchange_order')
        ce=[(i,e) for i,e in enumerate(events) if e.instrument_id==ce_id]
        sa=[(i,e) for i,e in enumerate(events) if e.instrument_id==sa_id]
        require(bool(sa),'missing_analyzer_exchanges')
        # 原collect_fixed_route依据Propsim User Reference §20.4.1消费该错误队列；这里只读其已存回复。
        ce_error='SYSTem:ERRor?'
        for rows,error_command in ((ce,ce_error),(sa,FsvaScpi.ERR)):
            for index,(_,event) in enumerate(rows):
                if event.command==error_command:
                    require(isinstance(event.response,str) and int(event.response.split(',',1)[0])==0,'instrument_error_queue')
                else:
                    require(index+1<len(rows) and rows[index+1][1].command==error_command,'missing_error_queue_evidence')
        def identity(rows):
            ids=[e.response for _,e in rows if e.command==FsvaScpi.IDN]
            require(bool(ids) and len(set(ids))==1,'missing_or_changed_identity')
            parts=ids[0].split(',')
            require(len(parts)==4 and bool(parts[2].strip()),'unknown_physical_identity')
            return ids[0],parts[1].strip().upper()
        ce_identity,ce_model=identity(ce)
        _,sa_model=identity(sa)
        require(ce_model in ('F8800A','PROPSIM F64') and sa_model.startswith('FSVA3') and sa_model[5:].isdigit(),'unsupported_instrument_identity')
        require(result.states.get('f64_identity')==ce_identity and equal(result.states.get('output_loss_db'),0),'unverified_source_reference_plane')
        output=RealPropsimF64Driver._ce_port_to_output_num(route.ce_port)
        # 与collect_fixed_route同源：User Reference §20.4.5.22参数1实测、§20.4.5.20输出损耗及§20.4.3.14运行态。
        power_command=f'OUTPut:MEASure:RESult:GET? {output},1'
        loss_command=f'OUTPut:LOSS:GET? {output}'
        state_command='DIAG:SIMU:STATE?'
        powers=[(i,e) for i,e in ce if e.command==power_command and e.response and e.response.lower()!='not ready']
        require(len(powers)==2*len(result.samples),'missing_source_measurements')
        states=[(i,e) for i,e in ce if e.command==state_command]
        losses=[(i,e) for i,e in ce if e.command==loss_command]
        require(len(states)==2 and all(e.response=='RUNNING' for _,e in states) and
            states[0][0]<powers[0][0] and states[-1][0]>powers[-1][0],'unverified_running_window')
        require(len(losses)==2 and all(equal(e.response,0) for _,e in losses) and
            losses[0][0]<powers[0][0] and losses[-1][0]>powers[-1][0],'unverified_output_loss')
        tone_id='pc04_'+result.run_id.hex
        tone=RealPropsimF64Driver.calibration_tone_commands(str(output),tone_id,result.request.frequency_mhz*1e6,result.request.requested_power_dbm)
        # 原collect_fixed_route：User Reference §20.4.9.5，创建本run单音前必须无其它源。
        interference=[(i,e) for i,e in ce if e.command=='OUTPut:INTERFerence:GET?']
        tone_start=next(i for i,e in ce if e.command==tone[0])
        require(len(interference)==1 and interference[0][0]<tone_start and
            isinstance(interference[0][1].response,str) and interference[0][1].response.strip()=='0',
            'unverified_interference_free_source')
        def ordered_commands(rows,expected):
            cursor=iter(rows)
            for command in expected:
                require(any(event.command==command for _,event in cursor),'missing_measurement_setup')
        ordered_commands([(i,e) for i,e in ce if i<powers[0][0]],tone)
        # 原采集收尾依据User Reference §20.4.9.3/.2，只验证本run唯一单音的禁用/移除证据。
        ordered_commands([(i,e) for i,e in ce if i>powers[-1][0]],
            [f'OUTPut:INTERFerence:STatus {tone_id},0',f'OUTPut:INTERFerence:REMove {tone_id}'])
        for index,sample in enumerate(result.samples):
            before,after=powers[index*2],powers[index*2+1]
            require(equal(before[1].response,sample.source_before_dbm) and equal(after[1].response,sample.source_after_dbm),'source_sample_mismatch')
            window=[(i,e) for i,e in sa if before[0]<i<after[0]]
            spectrum=fixed_route_spectrum_commands(result.request.frequency_mhz*1e6)
            # 复用capture_fixed_route_power的目录语义：FSV/A3000手册p1339～1341。
            # 前两项为存储量，后续大小/文件名成对；每个文件均需选择及关闭回复。
            catalog_command='SENSe:CORRection:TRANsducer:CATalog?'
            catalogs=[e for _,e in window if e.command==catalog_command]
            require(len(catalogs)==1 and isinstance(catalogs[0].response,str),'missing_transducer_catalog')
            parts=next(csv.reader([catalogs[0].response.strip()],quotechar="'",skipinitialspace=True))
            require(len(parts)>=2 and len(parts)%2==0,'invalid_transducer_catalog')
            expected=[FsvaScpi.IDN,spectrum[0],catalog_command]
            for name in parts[3::2]:
                require(bool(name) and "'" not in name and '\n' not in name,'invalid_transducer_name')
                expected.extend([f"SENSe:CORRection:TRANsducer:SELect '{name}'",
                    'SENSe:CORRection:TRANsducer:STATe?'])
            expected.extend(spectrum[1:])
            # 同原事务的实际顺序，不能用其它文件/其它采样窗口的关闭证据替代。
            actual=[e for _,e in window if e.command!=FsvaScpi.ERR]
            require([e.command for e in actual]==expected,'missing_transducer_verification')
            require(all(isinstance(e.response,str) and e.response.strip()=='0' for e in actual
                if e.command=='SENSe:CORRection:TRANsducer:STATe?'),'external_transducer_correction')
            received=[e for _,e in window if e.command==FsvaScpi.READ_CHP]
            completed=[e for _,e in window if e.command==FsvaScpi.TRIG]
            require(len(received)==1 and equal(received[0].response,sample.received_dbm) and
                len(completed)==1 and completed[0].response=='1','invalid_analyzer_sample')
            require(before[1].host_time<=sample.host_time<=events[-1].host_time,'sample_outside_capture_window')
        losses=[(s.source_before_dbm+s.source_after_dbm)/2-(s.received_dbm+result.request.receive_cable_loss_db) for s in result.samples]
        require(equal(statistics.mean(losses),result.net_loss_db) and equal(statistics.stdev(losses),result.sample_std_db),'calculation_mismatch')
        return 'real',[]
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,StopIteration,csv.Error) as exc:
        # 不以读取失败补默认值；具体拒绝码由被触发的原始检查提供。
        return 'unknown',[str(exc) or 'incomplete_measurement_evidence']
