"""固定通路的合成数据与通信状态；不继承真实驱动，不发送任何真实命令。

命令形式与参数意义来自既有calibration_tone_commands和fixed_route_spectrum_commands；
此处只实现这些命令的模拟响应，不增加仪器能力或真实VNA测量。
"""
import asyncio
import math
import threading
from uuid import uuid4

from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.rs_fsva import FsvaScpi, fixed_route_spectrum_commands
from app.models.diagnostic_run import DiagnosticRun
from app.schemas.diagnostic_evidence import SequenceEvidence
from app.schemas.fixed_route_acquisition import SimulatedReceiveCableRecord
from app.schemas.route_calibration import RouteSelection


def model_quantities(configuration, request):
    route = RouteSelection.model_validate(configuration.get('route_selection'))
    types=[n['type'] for n in route.nodes]
    node_cables = types[1:]==['cable','amplifier','cable','probe']
    edge_cables = types[1:]==['amplifier','probe']
    if (types[0] not in ('ce_port','channel_emulator') or not (node_cables or edge_cables) or
            [n['type'] for n in route.calibration_nodes] !=
            ['air_path','reference_antenna','receive_cable','signal_analyzer']):
        raise ValueError('完整模型需要F64、两段发射线缆、PA、探头、空气段、参考天线、接收线缆及分析仪；线缆须统一用节点或连接表示')
    if any('simulation_model' in e for e in route.calibration_connections) or (node_cables and
            any('simulation_model' in e for e in route.connections)):
        raise ValueError('同一物理线缆不能同时在节点和连接声明模拟模型，参考段只接受节点模型')
    if (route.reference_antenna_id != route.calibration_nodes[1]['id'] or
            not route.analyzer_category_id or route.analyzer_category_id !=
            configuration.get('analyzer_binding', {}).get('category_id') or
            route.calibration_nodes[-1].get('params',{}).get('instrument_category_id') != route.analyzer_category_id):
        raise ValueError('完整模拟参考天线或分析仪绑定身份缺失或不一致')
    values={}
    def quantity(model,key,identity):
        if not isinstance(model,dict) or set(model)!={'frequency_mhz',key}:
            raise ValueError(f'{identity}缺少明确的模拟频率及{key}')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in model.values()) or model['frequency_mhz']!=request.frequency_mhz:
            raise ValueError(f'{identity}模拟量值无效或频率不匹配')
        if key=='loss_db' and model[key]<0:
            raise ValueError('模拟无源线缆和空气段损耗不能为负')
        return model[key] if key=='loss_db' else -model[key]
    for node in [*route.nodes[1:],*route.calibration_nodes[:-1]]:
        key='gain_db' if node['type'] in ('amplifier','probe','reference_antenna') else 'loss_db'
        values[('node',node['id'])]=quantity(node.get('params',{}).get('simulation_model'),key,'节点'+node['id'])
    if edge_cables:
        for edge in route.connections:
            if edge.get('loss_owner_connection_id'):
                raise ValueError('两段模拟发射线缆不能引用同一线缆的损耗归属')
            values[('connection',edge['id'])]=quantity(edge.get('simulation_model'),'loss_db','连接'+edge['id'])
    cable=route.calibration_nodes[2]
    incoming,outgoing=route.calibration_connections[2:4]
    for edge,key in ((incoming,'target_pin'),(outgoing,'source_pin')):
        if not isinstance(edge.get(key),str) or not edge[key].strip():
            raise ValueError('接收线缆参考面缺少保存端口')
    return route,values,dict(cable_node_id=cable['id'],frequency_mhz=request.frequency_mhz,
        input_reference_plane=f"{cable['id']}:{incoming['target_pin']}",
        output_reference_plane=f"{cable['id']}:{outgoing['source_pin']}")


def prepare_model_record(db, result):
    """先提交独立观测，再交给完整路径；不覆盖或重生成历史，不使用旧线损声明。"""
    route,values,identity=model_quantities(result.configuration,result.request)
    if result.receive_cable_calibration is not None:
        raise ValueError('本次模型记录已经关联，不能重新生成历史')
    loss=values[('node',identity['cable_node_id'])]
    record=SimulatedReceiveCableRecord(run_id=uuid4(),lab_profile_id=result.lab_profile_id,
        **identity,source_power_dbm=-20.,received_power_dbm=-20.-loss,loss_db=-20.-(-20.-loss),
        formula='P_RX_SYNTH = P_SOURCE_SYNTH - MODEL_LOSS; L_RX = P_SOURCE_SYNTH - P_RX_SYNTH')
    envelope=SequenceEvidence(summary='模拟接收线缆观测；未操作VNA，不具备正式校准资格',steps=[],duration_ms=0,log=[],
        extra={'verdict':'UNDETERMINED','receive_cable_calibration':record.model_dump(mode='json')})
    db.add(DiagnosticRun(id=record.run_id,kind='scpi_sequence',lab_profile_id=result.lab_profile_id,
        target_name='simulated_receive_cable_calibration',params=identity,success=True,
        sequence_evidence=envelope.model_dump(mode='json')))
    db.commit()
    result.receive_cable_calibration=record
    result.states['reference_connection_phases']=[
        {'phase':'synthetic_cable_observation','simulated':True,'sgh_connection':'disconnected','vna_commands_executed':False},
        {'phase':'full_route_capture','simulated':True,'sgh_connection':'signal_analyzer','vna_connected':False}]
    result.states['model_formula']='P_SA = P_CE - sum(loss_db) + sum(gain_db); L_NET = P_CE - (P_SA + L_RX)'


class SimulatedRouteTransport:
    """每次采集独立的合成仪器状态；严格执行共享构造器发出的合法次序。"""
    def __init__(self, ce_id, sa_id, result, output_port):
        if not 1<=output_port<=32:
            raise ValueError('模拟输出口必须为1到32')
        self.instrument_id=ce_id
        self._scpi_lock=asyncio.Lock()
        self.has_interference_generator=True
        self.state='STOPPED'
        self.output_port=output_port
        self.result=result
        self.tone_id='pc04_'+result.run_id.hex
        self.commands=RealPropsimF64Driver.calibration_tone_commands(str(output_port),self.tone_id,
            result.request.frequency_mhz*1e6,result.request.requested_power_dbm)
        self.setup_index=0
        self.created=False
        self.enabled=False
        self.frequency_mhz=None
        self.power_dbm=None
        self.sample_index=0
        self.phase='before'
        self.total_loss=None
        if result.request.mock_model:
            route,values,identity=model_quantities(result.configuration,result.request)
            record=result.receive_cable_calibration
            if (record is None or record.lab_profile_id!=result.lab_profile_id or
                    any(getattr(record,k)!=v for k,v in identity.items()) or
                    not math.isclose(record.source_power_dbm-record.received_power_dbm,record.loss_db,abs_tol=1e-12) or
                    not math.isclose(record.loss_db,values[('node',identity['cable_node_id'])],abs_tol=1e-12)):
                raise ValueError('缺少已保存且身份、频率、参考面一致的模拟线缆记录')
            if int(RealPropsimF64Driver._ce_port_to_output_num(route.ce_port))!=output_port:
                raise ValueError('模拟输出口与保存通路不一致')
            self.total_loss=sum(values.values())
        self.analyzer=SimulatedAnalyzerTransport(sa_id,self)

    def _active(self):
        if (self.state!='RUNNING' or not self.enabled or self.setup_index!=len(self.commands) or
                self.frequency_mhz is None or self.power_dbm is None):
            raise ValueError('模拟测量缺少当前端口、频率、功率或运行状态')
        if self.sample_index>=self.result.request.sample_count:
            raise ValueError('模拟样本已耗尽')

    def _power(self,kind):
        self._active()
        explicit=self.result.request.mock_input
        if explicit is not None:
            return getattr(explicit.samples[self.sample_index],kind+'_dbm')
        if self.total_loss is None:
            raise ValueError('未选择完整模型且未提供显式模拟样本；不合成默认功率')
        return self.power_dbm-(self.total_loss if kind=='received' else 0.)

    async def _query(self,command):
        # 既有User Reference §20.4.1/.2/.3/.5；回复本身标记simulated，非真实身份。
        if command=='SYSTem:ERRor?': return '0,"No error"'
        if command=='*IDN?': return 'Keysight Technologies,F8800A,SIMULATED,1.0'
        if command=='*OPC?': return '1'
        if command=='DIAG:SIMU:STATE?': return self.state
        if command==f'OUTPut:LOSS:GET? {self.output_port}': return '0'
        if command=='OUTPut:INTERFerence:GET?': return self.tone_id if self.created else '0'
        if command=='SYSTem:CALIBration:VALid?': return '1,1'
        if command=='SYSTem:CALIBration:USER:GET?': return ''
        if command==f'OUTPut:GAIN:CH? {self.output_port}': return '0'
        if command==f'OUTPut:MEASure:RESult:GET? {self.output_port},1':
            if self.phase not in ('before','after'): raise ValueError('模拟功率读取顺序不正确')
            value=self._power('source_'+self.phase)
            if self.phase=='before': self.phase='received'
            else: self.phase='before'; self.sample_index+=1
            return str(value)
        raise ValueError('未定义的模拟查询：'+command)

    async def _write(self,command):
        # ADD/REMOVE仅STOPPED：ATE environment and practices AN Rev2.2 p14 §2.4.1。
        if self.setup_index<len(self.commands) and command==self.commands[self.setup_index]:
            if self.state!='STOPPED': raise ValueError('创建与设置模拟单音要求停止状态')
            if self.setup_index==0: self.created=True
            elif self.setup_index==2: self.frequency_mhz=float(command.rsplit(',',1)[1])
            elif self.setup_index==3: self.power_dbm=float(command.rsplit(',',1)[1])
            elif self.setup_index==4: self.enabled=True
            self.setup_index+=1
            return
        if command=='DIAG:SIMU:GO':
            if self.state!='STOPPED' or self.setup_index!=len(self.commands): raise ValueError('模拟单音尚未准备完成')
            self.state='RUNNING'; return
        if command==f'OUTPut:INTERFerence:STatus {self.tone_id},0':
            self.enabled=False; return
        if command=='DIAG:SIMU:STOP': self.state='STOPPED'; return
        if command==f'OUTPut:INTERFerence:REMove {self.tone_id}':
            if self.state!='STOPPED' or self.enabled: raise ValueError('模拟停止未确认，不能删除单音')
            self.created=False; return
        raise ValueError('未知、错误端口或错误时序的模拟命令：'+command)


class SimulatedAnalyzerTransport:
    def __init__(self,ident,source):
        self.instrument_id=ident
        self._scpi_rlock=threading.RLock()
        self.source=source
        self.index=0
        self.commands=fixed_route_spectrum_commands(source.result.request.frequency_mhz*1e6)

    def _write(self,command):
        if self.index>=len(self.commands) or command!=self.commands[self.index]:
            raise ValueError('分析仪模拟设置缺失或顺序不正确：'+command)
        self.index+=1

    def _query(self,command):
        if command==FsvaScpi.ERR: return '0,"No error"'
        if command=='*IDN?': return 'Rohde&Schwarz,FSVA3044,SIMULATED,1.0'
        if command=='SENSe:CORRection:TRANsducer:CATalog?' and self.index==1: return '0,10000'
        if self.index>=len(self.commands) or command!=self.commands[self.index]:
            raise ValueError('未知或错误时序的分析仪模拟查询：'+command)
        self.source._active()
        if command==FsvaScpi.TRIG:
            if self.source.phase!='received': raise ValueError('模拟扫描不在源功率采样窗口内')
            self.index+=1
            return '1'
        if command==FsvaScpi.READ_CHP:
            value=self.source._power('received')
            self.source.phase='after'
            self.index=0
            return str(value)
        raise ValueError('未定义的分析仪模拟查询：'+command)

    def _abort_failed_measurement(self,operation,error):
        self.index=0
        self.source.result.states['simulated_analyzer_abort']=str(error)
