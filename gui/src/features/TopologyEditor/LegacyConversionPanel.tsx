import React,{useEffect,useRef,useState} from 'react';
import {Modal,Stack,Alert,Select,Text,Textarea,Button,Group,Checkbox,Paper} from '@mantine/core';
import {switchTopologyService} from '../../api/switchTopologyService';
import type {SwitchTopology,ConversionNodeEdit,ConversionConnectionEdit,TopologyConversionPreview} from '../../api/switchTopologyService';
import {buildConversionRequest,conversionContextKey,clearConversionSession} from './legacyConversionState';
import {revisionFailure} from './topologyRevisionState';

type Props={opened:boolean;topology:SwitchTopology;labId:string;dirty:boolean;blocked:boolean;
  isBlocked:()=>boolean;onClose:()=>void;onSave:(preview:TopologyConversionPreview)=>Promise<void>;onInspectLatest:()=>Promise<void>};
const jsonFields=['ports','port_directions','port_roles','internal_paths'] as const;
const typePairs=[['ce_port','channel_emulator'],['bse_port','communication_tester'],['sa_port','signal_analyzer']];
const failure=(err:any)=>{const detail=err.response?.data?.detail??err.message;return typeof detail==='string'?detail:JSON.stringify(detail)};

export function LegacyConversionPanel({opened,topology,labId,dirty,blocked,isBlocked,onClose,onSave,onInspectLatest}:Props){
  const [nodeId,setNodeId]=useState<string|null>(null),[edgeId,setEdgeId]=useState<string|null>(null);
  const [nodeEdits,setNodeEdits]=useState<Record<string,Record<string,string>>>({});
  const [edgeEdits,setEdgeEdits]=useState<Record<string,Record<string,string|boolean>>>({});
  const [preview,setPreview]=useState<TopologyConversionPreview|null>(null),[error,setError]=useState('');
  const [pending,setPending]=useState(false);
  const serial=useRef(0),live=useRef(true);
  const context=conversionContextKey(labId,topology.id??'');
  // 同context的每次请求也有独立序号；编辑改回原值同样使旧结果无效。
  const invalidate=()=>{serial.current++;setPreview(null);setError('');setPending(false)};
  useEffect(()=>{const cleared=clearConversionSession(topology);live.current=true;serial.current++;setPreview(cleared.preview);setError('');setPending(false);
    setNodeEdits(cleared.nodeEdits);setEdgeEdits(cleared.connectionEdits);setNodeId(null);setEdgeId(null);
    return ()=>{live.current=false;serial.current++};
  },[context,opened,topology]);
  const changeNode=(field:string,value:string)=>{if(isBlocked()||!nodeId)return;invalidate();setNodeEdits(old=>({...old,[nodeId]:{...old[nodeId],[field]:value}}))};
  const changeEdge=(field:string,value:string|boolean)=>{if(isBlocked()||!edgeId)return;invalidate();setEdgeEdits(old=>({...old,[edgeId]:{...old[edgeId],[field]:value}}))};
  const node=topology.nodes.find(n=>n.id===nodeId),edge=topology.connections.find(e=>e.id===edgeId);
  const ne=nodeId?nodeEdits[nodeId]??{}:{},ee=edgeId?edgeEdits[edgeId]??{}:{};
  const previewChanges=async()=>{
    if(isBlocked()||dirty||!topology.id)return;
    const ticket=++serial.current;setPreview(null);setError('');setPending(true);
    try{
      const nodes=Object.entries(nodeEdits).map(([node_id,fields])=>{
        const row:Record<string,unknown>={node_id};
        for(const [key,value] of Object.entries(fields))if(value!=='')row[key]=(jsonFields as readonly string[]).includes(key)?JSON.parse(value):value;
        return row as unknown as ConversionNodeEdit;
      }).filter(row=>Object.keys(row).length>1);
      const connections=Object.entries(edgeEdits).map(([connection_id,fields])=>{
        const row:Record<string,unknown>={connection_id};
        for(const [key,value] of Object.entries(fields)){
          if(key==='same_physical_cable_confirmed'){if(value===true)row[key]=true;continue}
          if(value===''||(key==='cable_loss_db'&&String(value).trim()===''))continue;
          row[key]=key==='cable_loss_db'?JSON.parse(String(value)):key==='loss_owner_connection_id'&&value==='__remove__'?null:value;
        }
        if(Object.hasOwn(row,'cable_loss_db')&&row.cable_loss_db!==null&&
          (typeof row.cable_loss_db!=='number'||!Number.isFinite(row.cable_loss_db)))throw Error('损耗必须是有限数值或 null');
        return row as unknown as ConversionConnectionEdit;
      }).filter(row=>Object.keys(row).length>1);
      const result=await switchTopologyService.previewConversion(topology.id,labId,buildConversionRequest(nodes,connections));
      if(live.current&&serial.current===ticket)setPreview(result);
    }catch(err){if(live.current&&serial.current===ticket)setError(failure(err))}
    finally{if(live.current&&serial.current===ticket)setPending(false)}
  };
  const confirm=async()=>{if(isBlocked()||dirty||!preview)return;const ticket=++serial.current;
    try{await onSave(preview)}catch(err){if(live.current&&serial.current===ticket){setPreview(null);setError(`${revisionFailure((err as any).response?.status).message} ${failure(err)}；输入已保留，重新预览须显式操作。`)}}};
  return <Modal opened={opened} onClose={()=>{if(isBlocked())return;invalidate();onClose()}} title="转换旧配置" size="xl" closeOnClickOutside={false}>
    <Stack>
      <Alert color="orange">仅转换应用声明，不证明实物接线、仪器能力或校准资格。空白字段不提交，不猜端口、方向或CE身份。预览候选不覆盖原画布草稿。</Alert>
      <Text size="xs">Lab {labId} · 原图 {topology.id}</Text>
      {dirty&&<Alert color="yellow">原拓扑草稿未保存；请先原保存，或关闭转换继续草稿。转换不会自动覆盖。</Alert>}
      <Select label="转换器件" searchable value={nodeId} data={topology.nodes.map(n=>({value:n.id,label:`${n.id} · ${n.type} · ${n.label} · GET展示值，原保存声明待核`}))}
        disabled={blocked} onChange={id=>{if(isBlocked())return;setNodeId(id)}}/>
      {node&&<Paper withBorder p="sm"><Stack gap="xs">
        <Text size="xs" style={{overflowWrap:'anywhere'}}>GET展示值，原保存声明待核（器件）：{JSON.stringify(node)}；读模型可能默认化或转换格式，不据此判断原JSON缺键；未填写的转换项不提交、不自动补齐。</Text>
        <Select label="显式目标类型" placeholder="不修改类型" value={ne.target_type??null} clearable
          data={(typePairs.find(pair=>pair.includes(node.type))??[]).map(value=>({value,label:value}))}
          disabled={blocked||!typePairs.some(pair=>pair.includes(node.type))} onChange={v=>changeNode('target_type',v??'')}/>
        <Textarea label="显式端口清单 ports（JSON数组）" placeholder='例如 ["P1"]，空白不提交' value={ne.ports??''} disabled={blocked} onChange={e=>changeNode('ports',e.currentTarget.value)}/>
        <Textarea label="显式端口方向 port_directions（JSON对象）" placeholder='input / output / bidirectional / unknown' value={ne.port_directions??''} disabled={blocked} onChange={e=>changeNode('port_directions',e.currentTarget.value)}/>
        <Textarea label="显式BSE角色 port_roles（JSON对象）" placeholder='dl / ul；不得覆盖原权威关系' value={ne.port_roles??''} disabled={blocked} onChange={e=>changeNode('port_roles',e.currentTarget.value)}/>
        <Textarea label="显式内部通路 internal_paths（JSON数组）" placeholder='[{"from_port":"IN","to_port":"OUT"}]；[]表示无贯通' value={ne.internal_paths??''} disabled={blocked} onChange={e=>changeNode('internal_paths',e.currentTarget.value)}/>
        <Textarea label="显式CE身份 ce_port" placeholder="不从label猜测" value={ne.ce_port??''} disabled={blocked} onChange={e=>changeNode('ce_port',e.currentTarget.value)}/>
      </Stack></Paper>}
      <Select label="转换连线" searchable value={edgeId} data={topology.connections.map(e=>({value:e.id,label:`${e.id} · ${e.source}:${e.source_pin??'GET未提供'} → ${e.target}:${e.target_pin??'GET未提供'} · GET展示值，原保存声明待核`}))}
        disabled={blocked} onChange={id=>{if(isBlocked())return;setEdgeId(id)}}/>
      {edge&&<Paper withBorder p="sm"><Stack gap="xs">
        <Text size="xs" style={{overflowWrap:'anywhere'}}>GET展示值，原保存声明待核（端点/损耗/来源）：{JSON.stringify(edge)}；out/in、0及数值格式可能来自读模型，不视为原保存声明。</Text>
        {edge.loss_owner_connection_id&&<Alert>旧值保留、不参与本组计算；owner：{edge.loss_owner_connection_id}<Button size="xs" onClick={()=>{if(!isBlocked())setEdgeId(edge.loss_owner_connection_id!)}}>定位owner原边</Button></Alert>}
        <Textarea label="显式源端口 source_pin" value={String(ee.source_pin??'')} disabled={blocked} onChange={e=>changeEdge('source_pin',e.currentTarget.value)}/>
        <Textarea label="显式目标端口 target_pin" value={String(ee.target_pin??'')} disabled={blocked} onChange={e=>changeEdge('target_pin',e.currentTarget.value)}/>
        <Textarea label="显式标称损耗 cable_loss_db" description="空白不提交；输入 null 清为未知；0 是已知零" value={String(ee.cable_loss_db??'')} disabled={blocked||!!edge.loss_owner_connection_id} onChange={e=>changeEdge('cable_loss_db',e.currentTarget.value)}/>
        <Select label="同一物理线缆量值owner原边" placeholder="不改变归属" clearable value={String(ee.loss_owner_connection_id||'')||null}
          data={[{value:'__remove__',label:'显式解组：两侧旧值恢复各自参与'},...topology.connections.filter(e=>e.id!==edge.id).map(e=>({value:e.id,label:`${e.id} · GET cable=${e.cable_loss_db??'未提供数值'} · calibrated=${e.calibrated_loss_db??'未提供数值'} · GET展示值，原保存声明待核`}))]}
          disabled={blocked} onChange={v=>changeEdge('loss_owner_connection_id',v??'')}/>
        <Checkbox label="这两条边表示同一条物理线缆（设置或撤销归属均明确确认）" checked={ee.same_physical_cable_confirmed===true} disabled={blocked} onChange={e=>changeEdge('same_physical_cable_confirmed',e.currentTarget.checked)}/>
        {ee.loss_owner_connection_id==='__remove__'&&<Alert color="orange">解组后两侧保留的原量值恢复各自参与；不是清空或复制损耗。</Alert>}
      </Stack></Paper>}
      {error&&<Alert color="red" data-testid="conversion-error">{error}<Button variant="light" onClick={()=>void onInspectLatest()}>刷新查看服务器最新</Button></Alert>}
      {preview&&<Paper withBorder p="sm" data-testid="conversion-preview"><Text fw={600}>预览差异（尚未保存）</Text>
        <Text size="xs">以下差异的before_present/缺键判据仅来自本次服务器预览涉及字段；不反向证明上方GET展示值是原保存值。</Text>
        {preview.differences.map((d,i)=><Text size="sm" key={i}>{d.object_kind} {d.object_id} {d.field}：{d.before_present?JSON.stringify(d.before):'缺键'} → {JSON.stringify(d.after)}</Text>)}
        {preview.warnings.map((w,i)=><Text size="sm" key={i}>{w}</Text>)}
        <Text size="xs">候选原始JSON（只读；包含两侧保留值与量值采用源，不回填草稿）</Text><pre style={{whiteSpace:'pre-wrap',maxHeight:220,overflow:'auto'}}>{JSON.stringify(preview.candidate,null,2)}</pre>
      </Paper>}
      <Group justify="flex-end"><Button variant="default" disabled={blocked} onClick={()=>{if(isBlocked())return;invalidate();onClose()}}>取消转换</Button>
        <Button disabled={blocked||dirty} loading={pending} onClick={previewChanges}>预览转换差异</Button>
        <Button disabled={blocked||dirty||!preview} onClick={confirm}>确认转换并保存</Button></Group>
    </Stack>
  </Modal>;
}
